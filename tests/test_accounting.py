from pathlib import Path
import tempfile
import unittest

from evirecall.contracts import ContractError
from evirecall.runner.accounting import CallLedger, aggregate_calls
from evirecall.runner.records import read_jsonl


class AccountingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'calls.jsonl'
        self.ledger = CallLedger(self.path, metadata={'run_id': 'run'})

    def start(self, **kwargs):
        return self.ledger.start(task_id='t', role='worker', operation='answer',
                                 phase='execution', provider='one', model='requested', **kwargs)

    def test_retry_unknown_and_unfinished_are_physical_requests(self):
        first = self.start(logical_call_id='logical', attempt=1)
        self.assertEqual(len(read_jsonl(self.path).records), 1)
        self.ledger.finish(first, status='failed', error_kind='timeout')
        second = self.start(logical_call_id='logical', attempt=2)
        self.ledger.finish(second, usage={'input_tokens': 3, 'output_tokens': 2, 'cost_usd': .5}, actual_model='actual')
        self.start()
        summary = self.ledger.summary()
        self.assertEqual(summary['requests'], 3)
        self.assertEqual(summary['known_cost_usd'], .5)
        self.assertIsNone(summary['cost_usd'])
        self.assertIsNone(summary['input_tokens'])
        self.assertEqual(summary['unknown_usage_calls'], 2)
        self.assertEqual(summary['unfinished_calls'], 1)
        self.assertEqual(summary['failed_calls'], 1)
        self.assertEqual(summary['completed_calls'], 1)
        self.assertAlmostEqual(summary['usage_coverage'], 1 / 3)
        self.assertEqual(summary['by_phase']['execution']['requests'], 3)
        self.assertEqual(aggregate_calls(read_jsonl(self.path).records), summary)
        self.assertEqual(read_jsonl(self.path).records[3]['actual_model'], 'actual')

    def test_reload_finish_and_duplicate_terminal_rejected(self):
        call = self.start()
        loaded = CallLedger(self.path)
        loaded.finish(call, usage={'input_tokens': 0, 'output_tokens': 0})
        with self.assertRaises(ContractError):
            loaded.finish(call)
        with self.assertRaises(ContractError):
            loaded.finish('missing')
        self.assertEqual(loaded.summary()['input_tokens'], 0)
        self.assertIsNone(loaded.summary()['cost_usd'])
        self.assertEqual(loaded.summary(task_id='other')['requests'], 0)
        self.assertIsNone(loaded.summary(task_id='other')['input_tokens'])

    def test_invalid_usage_cannot_close_or_write_call(self):
        call = self.start()
        for bad in (-1, float('nan'), float('inf'), True, 1.5):
            with self.assertRaises(ContractError):
                self.ledger.finish(call, usage={'input_tokens': bad})
        self.assertEqual(len(read_jsonl(self.path).records), 1)
        self.ledger.finish(call)

    def test_mixed_providers_phases_and_malformed_transitions(self):
        call = self.start()
        self.ledger.finish(call, usage={'input_tokens': 1, 'output_tokens': 2, 'cost_usd': 0})
        other = self.ledger.start(task_id='u', role='judge', operation='score', phase='evaluation', provider='two', model='m')
        self.ledger.finish(other, usage={'cost_usd': .2})
        self.assertEqual(self.ledger.summary(task_id='t')['cost_usd'], 0)
        self.assertEqual(self.ledger.summary()['by_phase']['evaluation']['requests'], 1)
        events = read_jsonl(self.path).records
        for invalid in ([events[1]], [events[0], events[0]], events + [events[1]]):
            with self.assertRaises(ContractError):
                aggregate_calls(invalid)

    def test_replay_rejects_invalid_timing_and_identity(self):
        call = self.start()
        self.ledger.finish(call)
        events = read_jsonl(self.path).records
        for key, value in (('task_id', 'changed'), ('elapsed_ms', -1), ('finished_at', 'bad')):
            changed = [events[0], {**events[1], key: value}]
            with self.assertRaises(ContractError):
                aggregate_calls(changed)
        with self.assertRaises(ContractError):
            aggregate_calls([{**events[0], 'started_at': '2026-01-01'}])
