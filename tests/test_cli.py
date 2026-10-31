import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def invoke(self, *args, ok=True):
        result = subprocess.run([sys.executable, '-m', 'evirecall', *map(str, args)],
                                cwd=ROOT, text=True, capture_output=True, timeout=35)
        self.assertEqual(result.returncode, 0 if ok else 2, result.stderr + result.stdout)
        return json.loads(result.stdout) if ok else result

    def test_run_score_summarize_and_provenance(self):
        run, scores = self.root / 'run', self.root / 'scores'
        result = self.invoke('run', '--output', run)
        self.assertEqual(result['counts']['planned'], 3)
        self.assertEqual(result['counts']['scored'], 0)
        scored = self.invoke('score', run, '--expectations', ROOT / 'fixtures/evaluator/expectations.jsonl', '--output', scores)
        self.assertEqual(scored['scored_subset_accuracy'], 1)
        replay = self.invoke('summarize', run, '--evaluation', scores)
        self.assertEqual(scored['counts'], replay['counts'])
        manifest = json.loads((run / 'manifest.json').read_text())
        self.assertEqual(manifest['inputs']['config_sha256'], hashlib.sha256((ROOT / 'configs/run-fixture.json').read_bytes()).hexdigest())
        self.assertEqual(manifest['inputs']['tasks_sha256'], hashlib.sha256((ROOT / 'fixtures/public/tasks.jsonl').read_bytes()).hexdigest())
        self.assertEqual((run / 'code/tests/fixtures/longmemeval/LICENSE').read_bytes(),
                         (ROOT / 'tests/fixtures/longmemeval/LICENSE').read_bytes())
        self.invoke('run', '--output', run, ok=False)

    def test_unknown_backend_unknown_key_and_invalid_limits_fail_before_output(self):
        baseline = dict(agent_backend='fixture', memory_backend='fixture', condition='fixture-wiring',
                        tasks=str(ROOT / 'fixtures/public/tasks.jsonl'), budget={}, limits={},
                        repetition=1, history_mode='sequential')
        for index, change in enumerate((dict(agent_backend='misspelled'), dict(memory_backend='misspelled'),
                                        dict(extra=True), dict(limits=dict(max_calls=0)),
                                        dict(history_mode='typo'), dict(repetition=True))):
            config, output = self.root / f'config{index}.json', self.root / f'run{index}'
            config.write_text(json.dumps({**baseline, **change}), encoding='utf-8')
            self.invoke('run', '--config', config, '--output', output, ok=False)
            self.assertFalse(output.exists())

    def test_doctor_and_smoke_are_preserved(self):
        self.assertFalse(self.invoke('doctor')['live_api_tested'])
        self.assertEqual(self.invoke('smoke', '--output', self.root / 'smoke')['fixture_checks_passed'], 3)

    def test_backend_preflight_is_read_only(self):
        before = set(self.root.iterdir())
        report = self.invoke('preflight', '--config', ROOT / 'configs/run-fixture.json')
        self.assertEqual(report['task_count'], 3)
        self.assertEqual(set(self.root.iterdir()), before)

    def test_pilot_command_selects_only_bounded_dev_inputs(self):
        from tests.test_longmemeval import sample
        from evirecall.tasks.longmemeval import prepare_dataset, build_split
        source, prepared, split = self.root / 'source.json', self.root / 'prepared', self.root / 'split'
        source.write_text(json.dumps([sample()]), encoding='utf-8')
        prepare_dataset(source, prepared, revision='synthetic')
        build_split(prepared, split, dev_units=1, test_questions=0)
        target = self.root / 'pilot'
        report = self.invoke('prepare-pilot', prepared, '--split', split, '--output', target)
        self.assertEqual(report['task_count'], 1)
        self.assertTrue((target / 'public/tasks.jsonl').is_file())
        self.invoke('prepare-pilot', prepared, '--split', split, '--output', self.root / 'too-large',
                    '--max-questions', 2, ok=False)
        self.assertFalse((self.root / 'too-large').exists())

    def test_longmemeval_commands_prepare_split_export_and_replay(self):
        from tests.test_longmemeval import sample
        source, prepared, split = self.root / 'source.json', self.root / 'prepared', self.root / 'split'
        source.write_text(json.dumps([sample()]), encoding='utf-8')
        self.invoke('prepare-longmemeval', source, '--revision', 'local-fixture', '--output', prepared,
                    '--sha256', hashlib.sha256(source.read_bytes()).hexdigest())
        self.invoke('split-longmemeval', prepared, '--output', split, '--dev-units', 1,
                    '--test-questions', 0, '--seed', 0)
        config = self.root / 'lme-config.json'
        config.write_text(json.dumps(dict(agent_backend='fixture', memory_backend='fixture',
            condition='fixture-wiring', tasks=str(prepared / 'public/tasks.jsonl'), budget={}, limits={},
            repetition=1, history_mode='independent')), encoding='utf-8')
        run, exported = self.root / 'lme-run', self.root / 'exported'
        self.invoke('run', '--config', config, '--output', run)
        self.invoke('export-longmemeval', run, '--references', prepared / 'evaluator/references.jsonl', '--output', exported)
        judge_config = self.root / 'judge-config.json'
        judge_config.write_text(json.dumps(dict(endpoint='http://127.0.0.1:9/v1/chat/completions',
            model='gpt-4o-2024-08-06', official_source_dir=str(ROOT / 'tests/fixtures/longmemeval'),
            request_timeout_s=1, limits=dict(max_calls=1, max_attempts=1, max_cost_usd=0))), encoding='utf-8')
        check = self.invoke('judge-longmemeval', exported, '--config', judge_config, '--check')
        self.assertFalse(check['ready'])
        self.assertFalse(check['judge_calls_performed'])
        self.assertEqual(check['prediction_count'], 1)
        self.invoke('judge-longmemeval', exported, '--config', judge_config, ok=False)
        predictions = [json.loads(line) for line in (exported / 'predictions.jsonl').read_text().splitlines()]
        for row in predictions:
            row['autoeval_label'] = dict(model='gpt-4o-2024-08-06', label=True)
        scores = self.root / 'official.jsonl'
        scores.write_text(''.join(json.dumps(row) + '\n' for row in predictions), encoding='utf-8')
        replay = self.invoke('import-longmemeval', exported, '--scores', scores, '--output', self.root / 'replay')
        self.assertEqual(replay['official']['overall_accuracy'], 1)
        scores.write_text('', encoding='utf-8')
        partial = self.invoke('import-longmemeval', exported, '--scores', scores, '--output', self.root / 'partial', '--allow-partial')
        self.assertEqual(partial['coverage']['judge_unknown'], 1)


if __name__ == '__main__':
    unittest.main()
