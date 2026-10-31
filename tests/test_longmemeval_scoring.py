import json
from pathlib import Path
import tempfile
import unittest

from evirecall.evaluation import longmemeval as scoring


class LongMemEvalScoringTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run = self.root / 'run'
        self.run.mkdir()
        self.refs = self.root / 'refs.jsonl'
        self.references = [dict(task_id=f't{i}', question_id=f'q{i}' + ('_abs' if i == 1 else ''),
                                question_type=category, question='Q', answer='A')
                           for i, category in enumerate(scoring.CATEGORIES)]
        self.write(self.refs, self.references)

    def write(self, path, rows):
        path.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')

    def prepare(self):
        self.write(self.run / 'results.jsonl', [
            dict(task_id='t0', status='completed', prediction='A'),
            dict(task_id='t1', status='abstained', prediction='I cannot answer'),
            dict(task_id='t2', status='failed', prediction=None, error_kind='timeout'),
        ])
        target = self.root / 'prepared'
        scoring.export_predictions(self.run, self.refs, target)
        return target

    def test_export_preserves_real_abstention_and_fixed_denominator(self):
        prepared = self.prepare()
        manifest = json.loads((prepared / 'manifest.json').read_text())
        self.assertEqual(manifest['coverage'], dict(planned=6, exported=2, completed=1, abstained=1, failed=1, missing=3))
        predictions = [json.loads(line) for line in (prepared / 'predictions.jsonl').read_text().splitlines()]
        self.assertEqual(predictions[1], dict(question_id='q1_abs', hypothesis='I cannot answer'))

    def test_unicode_line_separators_are_content_not_jsonl_boundaries(self):
        text = 'first\u2028second\u0085third\u2029last'
        self.write(self.run / 'results.jsonl', [dict(task_id='t0', status='completed', prediction=text)])
        self.run.joinpath('results.jsonl').write_text(json.dumps(dict(task_id='t0', status='completed',
                                                                   prediction=text), ensure_ascii=False) + '\n', encoding='utf-8')
        target = self.root / 'unicode'
        scoring.export_predictions(self.run, self.refs, target)
        prediction = json.loads((target / 'predictions.jsonl').read_text(encoding='utf-8'))
        self.assertEqual(prediction['hypothesis'], text)

    def test_replay_has_micro_macro_abstention_and_bounds(self):
        prepared = self.prepare()
        rows = [json.loads(line) for line in (prepared / 'predictions.jsonl').read_text().splitlines()]
        for row, label in zip(rows, [True, False]):
            row['autoeval_label'] = dict(model='gpt-4o-2024-08-06', label=label)
        results = self.root / 'official.jsonl'
        self.write(results, rows)
        summary = scoring.import_scores(prepared, results, self.root / 'scores')
        self.assertEqual(summary['official']['overall_accuracy'], .5)
        self.assertIsNone(summary['official']['category_macro_accuracy'])
        self.assertEqual(summary['official']['available_category_macro_accuracy'], .5)
        self.assertEqual(summary['official']['abstention_accuracy'], 0)
        self.assertEqual(summary['end_to_end']['success_lower_bound'], 1 / 6)
        self.assertEqual(summary['end_to_end']['success_upper_bound'], 1 / 6)

    def test_export_rejects_invalid_predictions_duplicates_and_unknown(self):
        for rows in ([dict(task_id='t0', status='abstained', prediction=None)],
                     [dict(task_id='t0', status='completed', prediction='A')] * 2,
                     [dict(task_id='unknown', status='completed', prediction='A')]):
            with self.subTest(rows=rows):
                self.write(self.run / 'results.jsonl', rows)
                with self.assertRaises(ValueError):
                    scoring.export_predictions(self.run, self.refs, self.root / 'invalid')

    def test_replay_rejects_incomplete_duplicate_unknown_labels_and_tampering(self):
        prepared = self.prepare()
        base = [json.loads(line) for line in (prepared / 'predictions.jsonl').read_text().splitlines()]
        for row in base:
            row['autoeval_label'] = dict(model='gpt-4o-2024-08-06', label=True)
        cases = [base[:1], base + base[:1], [dict(base[0], question_id='unknown'), base[1]],
                 [dict(base[0], autoeval_label=dict(model='gpt-4o-2024-08-06', label='yes')), base[1]],
                 [dict(base[0], hypothesis='changed'), base[1]],
                 [dict(base[0], autoeval_label=dict(model='other', label=True)), base[1]]]
        for rows in cases:
            with self.subTest(rows=rows):
                path = self.root / 'bad.jsonl'
                self.write(path, rows)
                with self.assertRaises(ValueError):
                    scoring.import_scores(prepared, path, self.root / 'bad-scores')

    def test_existing_output_is_never_overwritten(self):
        self.prepare()
        with self.assertRaises(FileExistsError):
            scoring.export_predictions(self.run, self.refs, self.root / 'prepared')

    def test_import_preserves_raw_judgments_and_inputs_for_standalone_replay(self):
        prepared = self.prepare()
        rows = [json.loads(line) for line in (prepared / 'predictions.jsonl').read_text().splitlines()]
        for row in rows:
            row['autoeval_label'] = dict(model='gpt-4o-2024-08-06', label=True)
        original = self.root / 'official.jsonl'
        self.write(original, rows)
        target = self.root / 'archived'
        first = scoring.import_scores(prepared, original, target)
        self.assertEqual((target / 'official-results.jsonl').read_bytes(), original.read_bytes())
        second = scoring.import_scores(target / 'inputs', target / 'official-results.jsonl', self.root / 'replay')
        self.assertEqual(first, second)

    def test_six_category_macro_weights_categories_equally(self):
        extra = dict(self.references[0], task_id='extra', question_id='extra-q')
        self.write(self.refs, self.references + [extra])
        self.write(self.run / 'results.jsonl', [dict(task_id=row['task_id'], status='completed', prediction='text')
                                                for row in self.references + [extra]])
        prepared = self.root / 'all'
        scoring.export_predictions(self.run, self.refs, prepared)
        rows = [json.loads(line) for line in (prepared / 'predictions.jsonl').read_text().splitlines()]
        for row in rows:
            row['autoeval_label'] = dict(model='gpt-4o-2024-08-06', label=row['question_id'] in ('q0', 'extra-q'))
        results = self.root / 'all-results.jsonl'
        self.write(results, rows)
        summary = scoring.import_scores(prepared, results, self.root / 'all-scores')
        self.assertEqual(summary['official']['category_macro_accuracy'], 1 / 6)
        self.assertEqual(summary['official']['overall_accuracy'], 2 / 7)

    def test_zero_exported_predictions_is_unscored_not_zero_accuracy(self):
        self.write(self.run / 'results.jsonl', [])
        prepared = self.root / 'empty'
        scoring.export_predictions(self.run, self.refs, prepared)
        results = self.root / 'empty-results.jsonl'
        self.write(results, [])
        summary = scoring.import_scores(prepared, results, self.root / 'empty-scores')
        self.assertIsNone(summary['official']['overall_accuracy'])
        self.assertEqual(summary['coverage']['missing'], 6)
        self.assertEqual(summary['end_to_end']['success_upper_bound'], 0)

    def test_prepared_artifact_tampering_is_rejected(self):
        prepared = self.prepare()
        (prepared / 'predictions.jsonl').write_text('', encoding='utf-8')
        results = self.root / 'empty-results.jsonl'
        self.write(results, [])
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            scoring.import_scores(prepared, results, self.root / 'tampered')

    def test_partial_replay_explicitly_tracks_unknown_judgments(self):
        prepared = self.prepare()
        row = json.loads((prepared / 'predictions.jsonl').read_text().splitlines()[0])
        row['autoeval_label'] = dict(model='gpt-4o-2024-08-06', label=True)
        results = self.root / 'partial.jsonl'
        self.write(results, [row])
        summary = scoring.import_scores(prepared, results, self.root / 'partial-scores', allow_partial=True)
        self.assertEqual(summary['coverage']['judge_unknown'], 1)
        self.assertEqual(summary['end_to_end']['success_lower_bound'], 1 / 6)
        self.assertEqual(summary['end_to_end']['success_upper_bound'], 2 / 6)

    def test_run_manifest_must_match_frozen_reference_ids(self):
        (self.run / 'manifest.json').write_text(json.dumps(dict(task_ids=['unrelated'])), encoding='utf-8')
        self.write(self.run / 'results.jsonl', [])
        with self.assertRaisesRegex(ValueError, 'manifest'):
            scoring.export_predictions(self.run, self.refs, self.root / 'mismatched')

    def test_import_rejects_inconsistent_frozen_coverage_before_output(self):
        prepared = self.prepare()
        manifest_path = prepared / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['coverage']['planned'] = 0
        manifest_path.write_text(json.dumps(manifest))
        results = self.root / 'empty-results.jsonl'; self.write(results, [])
        with self.assertRaisesRegex(ValueError, 'coverage'):
            scoring.import_scores(prepared, results, self.root / 'scores', allow_partial=True)
        self.assertFalse((self.root / 'scores').exists())


if __name__ == '__main__':
    unittest.main()
