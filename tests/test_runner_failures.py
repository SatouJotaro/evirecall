from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import time
import unittest

from evirecall.agents.fixture import FixtureAgent
from evirecall.contracts import AgentOutput, ContractError, EvidenceItem, EvidencePacket, Observation
from evirecall.runner.core import execute_tasks, ExecutionLimits
from evirecall.runner.records import read_jsonl
from evirecall.evaluation.aggregate import summarize_run
from evirecall.evaluation.scoring import score_run
from evirecall.tasks.loading import load_tasks

ROOT = Path(__file__).resolve().parents[1]


class ChargedFailure:
    def run(self, task, memory, budget, emit):
        emit.call(lambda: 'ok', role='answer', operation='generate', phase='execution',
                  provider='test', model='test-model',
                  usage_fn=lambda response: {'input_tokens': 10, 'output_tokens': 2, 'cost_usd': 0.02})
        raise RuntimeError('failed after a successful request')


class RetryAgent(FixtureAgent):
    def run(self, task, memory, budget, emit):
        attempts = []
        def request():
            attempts.append(1)
            if len(attempts) == 1:
                raise TimeoutError('temporary')
            return 'ok'
        emit.call(request, role='answer', operation='generate', phase='execution', provider='test',
                  model='test', retry_on=(TimeoutError,), max_attempts=2,
                  usage_fn=lambda result: {'input_tokens': 1, 'output_tokens': 1, 'cost_usd': .01})
        return super().run(task, memory, budget, emit)


class HangingAgent:
    def run(self, task, memory, budget, emit):
        def request():
            time.sleep(5)
            (emit.store_path / 'late-write').write_text('must not happen')
        emit.call(request, role='answer', operation='generate', phase='execution',
                  provider='test', model='test')


class ToolAgent:
    def run(self, task, memory, budget, emit):
        event = Observation('tool-1', 'A new tool observation', 'tool', '2026-10-30T00:00:00Z')
        emit.register_source(event)
        memory.observe(event)
        evidence = memory.retrieve(task.query, budget)
        return AgentOutput(evidence.items[0].text, 'completed', evidence)


class TornTraceAgent:
    def run(self, task, memory, budget, emit):
        # Simulate a process dying in the middle of a write, before the next group.
        path = emit.store_path.parents[1] / 'trace.jsonl'
        with path.open('ab') as stream:
            stream.write(b'{"cut-short":')
            stream.flush()
        time.sleep(5)


class UnterminatedTraceAgent:
    def run(self, task, memory, budget, emit):
        path = emit.store_path.parents[1] / 'trace.jsonl'
        with path.open('ab') as stream:
            stream.write(b'{}')
            stream.flush()
        time.sleep(5)


class CrashingAgent:
    def run(self, task, memory, budget, emit):
        os._exit(17)


def broken_scorer(result, expectation):
    raise RuntimeError('judge unavailable')


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / 'run'
        self.tasks = load_tasks(ROOT / 'fixtures/public/tasks.jsonl')

    def test_failed_episode_retains_finished_request_and_blocks_dependent_session(self):
        first = self.tasks[0]
        followup = replace(first, task_id='followup', session_id='session-2', events=())
        summary = execute_tasks([first, followup], self.output, agent_factory=ChargedFailure)
        self.assertEqual(summary['counts']['failed'], 1)
        self.assertEqual(summary['counts']['not_run'], 1)
        self.assertEqual(summary['calls']['requests'], 1)
        self.assertAlmostEqual(summary['calls']['cost_usd'], .02)
        self.assertEqual(len(read_jsonl(self.output / 'results.jsonl').records), 1)

    def test_retries_are_separate_physical_requests_and_unknown_cost_is_not_zero(self):
        summary = execute_tasks(self.tasks[:1], self.output, agent_factory=RetryAgent,
                                limits=ExecutionLimits(max_attempts=2, retry_backoff_s=0))
        self.assertEqual(summary['counts']['completed'], 1)
        self.assertEqual(summary['calls']['requests'], 2)
        self.assertIsNone(summary['calls']['cost_usd'])
        self.assertEqual(summary['calls']['known_cost_usd'], .01)

    def test_hard_timeout_leaves_unfinished_call_and_stops_worker_writes(self):
        start = time.monotonic()
        summary = execute_tasks(self.tasks[:1], self.output, agent_factory=HangingAgent,
                                limits=ExecutionLimits(episode_timeout_s=.3))
        self.assertLess(time.monotonic() - start, 4)
        self.assertEqual(summary['counts']['failed'], 1)
        self.assertEqual(summary['calls']['unfinished_calls'], 1)
        result = read_jsonl(self.output / 'results.jsonl').records[0]
        self.assertEqual(result['error_kind'], 'timeout')
        self.assertEqual(list(self.output.rglob('late-write')), [])

    def test_dynamic_source_is_registered_and_returned(self):
        summary = execute_tasks(self.tasks[:1], self.output, agent_factory=ToolAgent)
        self.assertEqual(summary['counts']['completed'], 1)
        sources = read_jsonl(self.output / 'sources.jsonl').records
        self.assertIn('tool-1', [row['observation']['source_id'] for row in sources])

    def test_scoring_failure_is_independent_and_summary_replays_without_api(self):
        execute_tasks(self.tasks, self.output)
        before = (self.output / 'results.jsonl').read_bytes()
        evaluation, scores = score_run(self.output, ROOT / 'fixtures/evaluator/expectations.jsonl',
                                       scorer=broken_scorer)
        self.assertEqual((self.output / 'results.jsonl').read_bytes(), before)
        self.assertEqual(scores['counts']['judge_error'], 3)
        replay = summarize_run(self.output, evaluation)
        self.assertEqual(replay['counts']['planned'], 3)
        self.assertEqual(replay['success_lower_bound'], 0)
        self.assertEqual(replay['success_upper_bound'], 1)

    def test_existing_output_refused_and_each_run_has_distinct_store_namespace(self):
        execute_tasks(self.tasks[:1], self.output)
        with self.assertRaises(FileExistsError):
            execute_tasks(self.tasks[:1], self.output)
        other = Path(self.temp.name) / 'other'
        execute_tasks(self.tasks[:1], other)
        left = read_jsonl(self.output / 'schedule.jsonl').records
        right = read_jsonl(other / 'schedule.jsonl').records
        self.assertNotEqual(left[0]['store_path'], right[0]['store_path'])

    def test_truncated_tail_is_reported_and_raw_file_is_preserved(self):
        execute_tasks(self.tasks[:1], self.output)
        path = self.output / 'trace.jsonl'
        with path.open('ab') as stream:
            stream.write(b'{"unfinished":')
        before = path.read_bytes()
        summary = summarize_run(self.output)
        self.assertTrue(summary['warnings'])
        self.assertEqual(path.read_bytes(), before)

    def test_zero_cost_cap_blocks_first_request(self):
        summary = execute_tasks(self.tasks[:1], self.output, agent_factory=ChargedFailure,
                                limits=ExecutionLimits(max_cost_usd=0))
        self.assertEqual(summary['calls']['requests'], 0)
        self.assertEqual(read_jsonl(self.output / 'results.jsonl').records[0]['error_kind'],
                         'budget_exhausted')

    def test_scoring_replay_rejects_changed_execution_results(self):
        execute_tasks(self.tasks, self.output)
        evaluation, _ = score_run(self.output, ROOT / 'fixtures/evaluator/expectations.jsonl')
        path = self.output / 'results.jsonl'
        rows = read_jsonl(path).records
        rows[0]['prediction'] = 'changed after scoring'
        path.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')
        with self.assertRaisesRegex(ContractError, 'changed'):
            summarize_run(self.output, evaluation)

    def test_independent_branches_do_not_inherit_previous_observations(self):
        first = self.tasks[0]
        second = replace(first, task_id='branch-2', session_id='session-2', events=())
        summary = execute_tasks([first, second], self.output, history_mode='independent')
        self.assertEqual(summary['counts']['abstained'], 1)
        queued = [r for r in read_jsonl(self.output / 'schedule.jsonl').records if r['state'] == 'queued']
        self.assertNotEqual(queued[0]['store_path'], queued[1]['store_path'])

    def test_torn_trace_stops_new_groups_without_turning_tail_into_interior_corruption(self):
        summary = execute_tasks(self.tasks, self.output, agent_factory=TornTraceAgent,
                                limits=ExecutionLimits(episode_timeout_s=.3))
        self.assertEqual(summary['counts']['failed'], 1)
        self.assertEqual(summary['counts']['not_run'], 2)
        self.assertTrue(summary['warnings'])
        self.assertTrue((self.output / 'trace.jsonl').read_bytes().endswith(b'{"cut-short":'))

    def test_complete_unterminated_trace_stops_new_groups_and_preserves_record(self):
        summary = execute_tasks(self.tasks, self.output, agent_factory=UnterminatedTraceAgent,
                                limits=ExecutionLimits(episode_timeout_s=.3))
        self.assertEqual(summary['counts']['failed'], 1)
        self.assertEqual(summary['counts']['not_run'], 2)
        self.assertTrue(summary['warnings'])
        path = self.output / 'trace.jsonl'
        before = path.read_bytes()
        self.assertTrue(before.endswith(b'{}'))
        recovered = read_jsonl(path, recover_tail=True)
        self.assertEqual(recovered.records[-1], {})
        self.assertEqual(len(recovered.warnings), 1)
        self.assertEqual(path.read_bytes(), before)

    def test_worker_crash_is_a_terminal_failure_and_independent_groups_continue(self):
        summary = execute_tasks(self.tasks, self.output, agent_factory=CrashingAgent)
        self.assertEqual(summary['counts']['failed'], 3)
        self.assertEqual(summary['counts']['not_run'], 0)
        self.assertTrue(all(r['error_kind'] == 'worker_crash'
                            for r in read_jsonl(self.output / 'results.jsonl').records))


if __name__ == '__main__':
    unittest.main()
