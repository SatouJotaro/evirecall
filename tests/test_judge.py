import ast
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from evirecall.evaluation import longmemeval

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL = ROOT / 'tests/fixtures/longmemeval'


@contextmanager
def service(responses):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            status, payload, delay = responses[min(len(calls) - 1, len(responses) - 1)]
            time.sleep(max(0, delay))
            self.send_response(status)
            if status == 302:
                self.send_header('Location', f'http://127.0.0.1:{self.server.server_port}/redirect')
            self.end_headers()
            try:
                if delay < 0:
                    for byte in json.dumps(payload).encode():
                        self.wfile.write(bytes([byte])); self.wfile.flush()
                        time.sleep(.05)
                else:
                    self.wfile.write(json.dumps(payload).encode())
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/v1/chat/completions', calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def response(model='gpt-4o-2024-08-06', content=' YES '):
    return dict(model=model, choices=[dict(message=dict(content=content))],
                usage=dict(prompt_tokens=20, completion_tokens=1))


class JudgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        run = self.root / 'source-run'; run.mkdir()
        (run / 'results.jsonl').write_text(json.dumps(dict(task_id='t', status='completed', prediction='blue')) + '\n')
        refs = self.root / 'refs.jsonl'
        refs.write_text(json.dumps(dict(task_id='t', question_id='q', question_type='single-session-user',
                                        question='Color?', answer='blue')) + '\n')
        self.prepared = self.root / 'prepared'
        longmemeval.export_predictions(run, refs, self.prepared)

    def config(self, target_endpoint, **updates):
        value = dict(endpoint=target_endpoint, model='gpt-4o-2024-08-06', official_source_dir=str(OFFICIAL),
                     request_timeout_s=1, limits=dict(max_calls=4, max_attempts=2, max_cost_usd=1,
                        episode_timeout_s=3, run_timeout_s=15, retry_backoff_s=0),
                     pricing=dict(source='test-declared', input_usd_per_million=1, output_usd_per_million=2))
        value.update(updates)
        path = self.root / 'judge.json'; path.write_text(json.dumps(value))
        return path

    def test_inspection_is_offline_and_reports_readiness(self):
        from evirecall.evaluation.judge import inspect_judge_config
        path = self.config('https://example.invalid/v1/chat/completions', api_key_env='EVIRECALL_TEST_MISSING')
        with patch.dict(os.environ, {}, clear=True):
            report = inspect_judge_config(self.prepared, path)
        self.assertFalse(report['ready'])
        self.assertFalse(report['credential_present'])
        self.assertEqual(report['prediction_count'], 1)
        self.assertFalse((self.root / 'out').exists())
        with patch.dict(os.environ, {'EVIRECALL_TEST_MISSING': '   '}):
            self.assertFalse(inspect_judge_config(self.prepared, path)['credential_present'])

    def test_all_prompt_categories_and_abstention_match_pinned_function(self):
        from evirecall.evaluation.judge import load_official_prompt, official_label
        actual = load_official_prompt(OFFICIAL)
        source = (OFFICIAL / 'src/evaluation/evaluate_qa.py').read_text()
        function = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'get_anscheck_prompt')
        scope = {}; exec(compile(ast.Module(body=[function], type_ignores=[]), 'official', 'exec'), scope)
        for category in longmemeval.CATEGORIES:
            for abstention in (True, False):
                self.assertEqual(actual(category, 'Q', 12, 'A', abstention=abstention),
                                 scope['get_anscheck_prompt'](category, 'Q', 12, 'A', abstention=abstention))
        self.assertTrue(official_label(' yesterday '))
        self.assertFalse(official_label(' NO '))

    def test_success_preserves_inputs_params_model_usage_and_secret(self):
        from evirecall.evaluation.judge import run_judge
        before = (self.prepared / 'predictions.jsonl').read_bytes()
        secret = uuid4().hex
        with service([(200, response(), 0)]) as (endpoint, calls), patch.dict(os.environ, {'JUDGE_TEST_KEY': secret}):
            path = self.config(endpoint, api_key_env='JUDGE_TEST_KEY')
            summary = run_judge(self.prepared, path, self.root / 'out')
        self.assertEqual(len(calls), 1)
        self.assertEqual({k: calls[0][k] for k in ('n', 'temperature', 'max_tokens')}, dict(n=1, temperature=0, max_tokens=10))
        self.assertEqual(summary['coverage']['scored'], 1)
        self.assertEqual(summary['usage']['requests'], 1)
        self.assertEqual(summary['usage']['input_tokens'], 20)
        self.assertAlmostEqual(summary['usage']['cost_usd'], .000022)
        self.assertTrue(json.loads((self.root / 'out/official-results.jsonl').read_text())['autoeval_label']['label'])
        records = [json.loads(x) for x in (self.root / 'out/execution/calls.jsonl').read_text().splitlines()]
        self.assertEqual(records[-1]['actual_model'], 'gpt-4o-2024-08-06')
        self.assertEqual(before, (self.prepared / 'predictions.jsonl').read_bytes())
        for file in (self.root / 'out').rglob('*'):
            if file.is_file():
                self.assertNotIn(secret.encode(), file.read_bytes(), str(file))
        replay = longmemeval.import_scores(self.root / 'out/inputs', self.root / 'out/official-results.jsonl', self.root / 'replay', allow_partial=True)
        self.assertEqual(replay['official']['overall_accuracy'], 1)

    def test_429_unknown_cost_stops_retry_without_fabricating_label(self):
        from evirecall.evaluation.judge import run_judge
        with service([(429, {'error': 'do not retain error bodies'}, 0), (200, response(), 0)]) as (endpoint, calls):
            summary = run_judge(self.prepared, self.config(endpoint), self.root / 'out')
        self.assertEqual(len(calls), 1)
        self.assertEqual(summary['usage']['requests'], 1)
        self.assertEqual(summary['coverage']['judge_unknown'], 1)
        self.assertIsNone(summary['usage']['cost_usd'])
        self.assertIn('budget_exhausted', (self.root / 'out/execution/results.jsonl').read_text())

    def test_timeout_unknown_and_redirect_does_not_follow(self):
        from evirecall.evaluation.judge import run_judge
        for index, spec in enumerate(((200, response(), 1), (302, {}, 0))):
            with self.subTest(spec=spec), service([spec]) as (endpoint, calls):
                config = self.config(endpoint, request_timeout_s=.1,
                                     limits=dict(max_calls=3, max_attempts=1, max_cost_usd=1,
                                                 episode_timeout_s=3, run_timeout_s=15))
                summary = run_judge(self.prepared, config, self.root / f'out{index}')
                self.assertEqual(summary['coverage']['judge_unknown'], 1)
                self.assertEqual(len(calls), 1)

    def test_invalid_config_and_credentials_precede_output_or_http(self):
        from evirecall.evaluation.judge import run_judge
        for index, updates in enumerate((dict(api_key='inline-secret'), dict(endpoint='http://remote.invalid/x'),
                dict(endpoint='https://example.invalid/x', api_key_env='EVIRECALL_TEST_MISSING'),
                dict(limits=dict(max_calls=3, max_attempts=1)), dict(endpoint='https://key@example.invalid/x'))):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                run_judge(self.prepared, self.config('http://127.0.0.1:9/x', **updates), self.root / f'bad{index}')
            self.assertFalse((self.root / f'bad{index}').exists())

    def test_zero_cap_blocks_first_request_and_variant_is_explicit(self):
        from evirecall.evaluation.judge import run_judge, inspect_judge_config
        with service([(200, response(), 0)]) as (endpoint, calls):
            config = self.config(endpoint, limits=dict(max_calls=1, max_attempts=1, max_cost_usd=0))
            self.assertFalse(inspect_judge_config(self.prepared, config)['ready'])
            summary = run_judge(self.prepared, config, self.root / 'out')
        self.assertEqual(calls, [])
        self.assertEqual(summary['coverage']['judge_unknown'], 1)
        with service([(200, response('local-test-model'), 0)]) as (endpoint, calls):
            summary = run_judge(self.prepared, self.config(endpoint, model='local-test-model'), self.root / 'variant')
        self.assertFalse(summary['provenance']['official_print_metrics_compatible'])

    def test_existing_directory_is_preserved(self):
        from evirecall.evaluation.judge import run_judge
        output = self.root / 'out'; output.mkdir(); (output / 'official-results.jsonl').write_text('saved')
        with self.assertRaises(FileExistsError):
            run_judge(self.prepared, self.config('http://127.0.0.1:9/x'), output)
        self.assertEqual((output / 'official-results.jsonl').read_text(), 'saved')

    def test_invalid_model_and_content_preserve_known_charges(self):
        from evirecall.evaluation.judge import run_judge
        cases = [response(model=None), response(content=None)]
        for index, payload in enumerate(cases):
            with self.subTest(index=index), service([(200, payload, 0)]) as (endpoint, calls):
                summary = run_judge(self.prepared, self.config(endpoint), self.root / f'out{index}')
            self.assertEqual(summary['usage']['requests'], 1)
            self.assertAlmostEqual(summary['usage']['cost_usd'], .000022)
            self.assertEqual(summary['coverage']['judge_unknown'], 1)

    def test_hard_deadline_leaves_started_call_and_unknown_label(self):
        from evirecall.evaluation.judge import run_judge
        with service([(200, response(), -1)]) as (endpoint, calls):
            path = self.config(endpoint, request_timeout_s=10,
                               limits=dict(max_calls=3, max_attempts=1, max_cost_usd=1,
                                           episode_timeout_s=2, run_timeout_s=15))
            summary = run_judge(self.prepared, path, self.root / 'out')
        self.assertEqual(len(calls), 1, summary)
        self.assertEqual(summary['usage']['unfinished_calls'], 1)
        self.assertEqual(summary['coverage']['judge_unknown'], 1)

    def test_unpriced_or_cached_usage_stops_subsequent_calls(self):
        from evirecall.evaluation.judge import run_judge
        prediction = json.loads((self.prepared / 'predictions.jsonl').read_text())
        (self.prepared / 'predictions.jsonl').write_text(json.dumps(prediction) + '\n' + json.dumps(dict(prediction, question_id='q2')) + '\n')
        refs = json.loads((self.prepared / 'evaluator_reference.json').read_text())
        refs.append(dict(refs[0], question_id='q2'))
        (self.prepared / 'evaluator_reference.json').write_text(json.dumps(refs))
        manifest = json.loads((self.prepared / 'manifest.json').read_text())
        manifest['coverage'].update(planned=2, exported=2, completed=2)
        manifest['episodes'].append(dict(task_id='t2', question_id='q2', status='completed'))
        for name in manifest['artifact_sha256']:
            manifest['artifact_sha256'][name] = hashlib.sha256((self.prepared / name).read_bytes()).hexdigest()
        (self.prepared / 'manifest.json').write_text(json.dumps(manifest))
        for index, pricing in enumerate((None, dict(source='declared', input_usd_per_million=1, output_usd_per_million=1))):
            result = response()
            if pricing:
                result['usage']['prompt_tokens_details'] = dict(cached_tokens=10)
            with self.subTest(index=index), service([(200, result, 0)]) as (endpoint, calls):
                summary = run_judge(self.prepared, self.config(endpoint, pricing=pricing), self.root / f'out{index}')
            self.assertEqual(len(calls), 1)
            self.assertEqual(summary['coverage']['scored'], 1)
            self.assertEqual(summary['coverage']['judge_unknown'], 1)
            self.assertIsNone(summary['usage']['cost_usd'])

    def test_provider_credential_echo_is_not_persisted(self):
        from evirecall.evaluation.judge import run_judge
        secret = uuid4().hex
        with service([(200, response(content='yes ' + secret), 0)]) as (endpoint, calls), patch.dict(os.environ, {'JUDGE_TEST_KEY': secret}):
            summary = run_judge(self.prepared, self.config(endpoint, api_key_env='JUDGE_TEST_KEY'), self.root / 'out')
        self.assertEqual(summary['coverage']['scored'], 1)
        for file in (self.root / 'out').rglob('*'):
            if file.is_file():
                self.assertNotIn(secret.encode(), file.read_bytes(), str(file))

    def test_model_credential_echo_preserves_usage_without_persisting_secret(self):
        from evirecall.evaluation.judge import run_judge
        secret = uuid4().hex
        with service([(200, response(model=secret), 0)]) as (endpoint, calls), patch.dict(os.environ, {'JUDGE_TEST_KEY': secret}):
            summary = run_judge(self.prepared, self.config(endpoint, api_key_env='JUDGE_TEST_KEY'), self.root / 'out')
        self.assertEqual(summary['coverage']['judge_unknown'], 1)
        self.assertAlmostEqual(summary['usage']['cost_usd'], .000022)
        for file in (self.root / 'out').rglob('*'):
            if file.is_file():
                self.assertNotIn(secret.encode(), file.read_bytes(), str(file))

    def test_pinned_source_tamper_is_refused_before_output(self):
        from evirecall.evaluation.judge import run_judge
        source = self.root / 'official/src/evaluation/evaluate_qa.py'
        source.parent.mkdir(parents=True)
        source.write_bytes((OFFICIAL / 'src/evaluation/evaluate_qa.py').read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            run_judge(self.prepared, self.config('http://127.0.0.1:9/x', official_source_dir='official'), self.root / 'out')
        self.assertFalse((self.root / 'out').exists())

    def test_wrapper_failure_keeps_complete_judgment_and_ignores_abandoned_atomic_tail(self):
        from evirecall.evaluation.judge import run_judge
        from evirecall.runner.records import append_jsonl, write_json

        def interrupted(tasks, output_dir, **kwargs):
            directory = Path(output_dir).parent
            row = dict(question_id='q', hypothesis='blue',
                       autoeval_label=dict(model='gpt-4o-2024-08-06', label=True))
            write_json(directory / 'judge/judgments/judge-000000.json', row)
            (directory / 'judge/judgments/abandoned.tmp').write_text('{"partial":')
            append_jsonl(directory / 'execution/results.jsonl', dict(task_id='judge-000000', status='completed'))
            raise RuntimeError('wrapper interrupted after completed worker')

        with patch('evirecall.evaluation.judge.execute_tasks', side_effect=interrupted):
            summary = run_judge(self.prepared, self.config('http://127.0.0.1:9/x'), self.root / 'out')
        self.assertEqual(summary['coverage']['scored'], 1)
        self.assertEqual(summary['judge']['wrapper_error'], 'RuntimeError')
        self.assertTrue((self.root / 'out/judge/judgments/abandoned.tmp').exists())
        self.assertTrue(json.loads((self.root / 'out/official-results.jsonl').read_text())['autoeval_label']['label'])

    def test_bad_coverage_and_episodes_are_refused_before_http_or_output(self):
        from evirecall.evaluation.judge import inspect_judge_config, run_judge
        manifest_path = self.prepared / 'manifest.json'
        baseline = json.loads(manifest_path.read_text())
        mutations = [lambda m: m['coverage'].update(planned=0),
                     lambda m: m['coverage'].update(exported=0),
                     lambda m: m['coverage'].update(completed=True),
                     lambda m: m['coverage'].update(missing=-1),
                     lambda m: m['coverage'].pop('failed'),
                     lambda m: m['coverage'].update(completed=0, failed=1),
                     lambda m: m.update(episodes=[]),
                     lambda m: m['episodes'][0].update(question_id='unknown'),
                     lambda m: m['episodes'][0].update(status='unknown'),
                     lambda m: m['episodes'][0].update(status='failed')]
        with service([(200, response(), 0)]) as (endpoint, calls):
            config = self.config(endpoint)
            for index, mutate in enumerate(mutations):
                manifest = json.loads(json.dumps(baseline)); mutate(manifest)
                manifest_path.write_text(json.dumps(manifest))
                with self.subTest(index=index, action='inspect'), self.assertRaises(ValueError):
                    inspect_judge_config(self.prepared, config)
                with self.subTest(index=index, action='run'), self.assertRaises(ValueError):
                    run_judge(self.prepared, config, self.root / f'bad{index}')
                self.assertFalse((self.root / f'bad{index}').exists())
            self.assertEqual(calls, [])

    def test_actual_model_mismatch_is_reported_as_protocol_variant(self):
        from evirecall.evaluation.judge import run_judge
        for index, content in enumerate(('yes', None)):
            with self.subTest(index=index), service([(200, response('different-actual-model', content=content), 0)]) as (endpoint, calls):
                summary = run_judge(self.prepared, self.config(endpoint), self.root / f'out{index}')
            self.assertEqual(summary['judge_model'], 'different-actual-model' if content else None)
            self.assertTrue(summary['judge']['protocol_variant'])
            self.assertFalse(summary['judge']['requested_protocol_variant'])
            self.assertFalse(summary['provenance']['official_print_metrics_compatible'])


if __name__ == '__main__':
    unittest.main()
