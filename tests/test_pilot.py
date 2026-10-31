import json
from pathlib import Path
import tempfile
import unittest

from evirecall.tasks.longmemeval import prepare_dataset, build_split
from evirecall.tasks.pilot import prepare_pilot


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        rows = []
        for i, qid in enumerate(('a', 'a_abs', 'b', 'c', 'd')):
            rows.append(dict(question_id=qid, question_type='secret-category', question='Which?', answer='secret-gold', question_date='2023-05-30', haystack_session_ids=[f's{i}'], haystack_dates=['2023-05-20'], haystack_sessions=[[dict(role='user', content=f'observation {i}')]], answer_session_ids=[f's{i}']))
        source = self.root / 'source.json'
        source.write_text(json.dumps(rows), encoding='utf-8')
        self.prepared, self.split = self.root / 'prepared', self.root / 'split'
        prepare_dataset(source, self.prepared, revision='r')
        build_split(self.prepared, self.split, dev_units=3, test_questions=1, seed=2)

    def run_pilot(self, name='pilot', **kwargs):
        return prepare_pilot(self.prepared, self.split, self.root / name, **kwargs)

    def test_deterministic_isolated_unchanged_payloads(self):
        before = (self.split / 'manifest.json').read_bytes()
        first = self.run_pilot(max_questions=3, seed=4)
        self.assertEqual(first, self.run_pilot('again', max_questions=3, seed=4))
        self.assertEqual(before, (self.split / 'manifest.json').read_bytes())
        selected = first['task_ids']
        self.assertEqual(len(selected), 3)
        self.assertEqual(len(set(first['selected_split_group_ids'])), 3)
        assignments = json.loads(before)['assignments']
        self.assertTrue(all(assignments[t] == 'dev' for t in selected))
        originals = {r['task_id']: r for r in map(json.loads, (self.prepared / 'public/tasks.jsonl').read_text().splitlines())}
        public = (self.root / 'pilot/public/tasks.jsonl').read_text()
        for row in map(json.loads, public.splitlines()):
            self.assertEqual(row, originals[row['task_id']])
        for hidden in ('secret-gold', 'secret-category', 'question_id', 'answer_session_ids'):
            self.assertNotIn(hidden, public)
        refs = list(map(json.loads, (self.root / 'pilot/evaluator/references.jsonl').read_text().splitlines()))
        self.assertEqual([r['task_id'] for r in refs], selected)

    def test_invalid_counts_and_existing_output(self):
        for value in (0, -1, True, 1.5, 4):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.run_pilot(max_questions=value)
            self.assertFalse((self.root / 'pilot').exists())
        self.run_pilot()
        with self.assertRaises(FileExistsError):
            self.run_pilot()

    def test_unicode_content_separators_are_not_jsonl_boundaries(self):
        source = self.root / 'source.json'
        rows = json.loads(source.read_text(encoding='utf-8'))
        content = 'before\u2028middle\u0085next\u2029after'
        for row in rows:
            row['haystack_sessions'][0][0]['content'] = content + row['question_id']
        source.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
        self.prepared, self.split = self.root / 'unicode-prepared', self.root / 'unicode-split'
        prepare_dataset(source, self.prepared, revision='r')
        build_split(self.prepared, self.split, dev_units=3, test_questions=1, seed=2)
        manifest = self.run_pilot()
        task = json.loads((self.root / 'pilot/public/tasks.jsonl').read_text(encoding='utf-8'))
        self.assertTrue(task['events'][0]['text'].startswith(content))
        self.assertEqual(manifest['task_ids'], [task['task_id']])

    def test_tampering_fails_without_output(self):
        for base, name in ((self.prepared, 'evaluator/references.jsonl'), (self.split, 'dev/tasks.jsonl')):
            path = base / name
            original = path.read_bytes()
            path.write_bytes(original + b' ')
            with self.assertRaises(ValueError):
                self.run_pilot()
            self.assertFalse((self.root / 'pilot').exists())
            path.write_bytes(original)

    def test_invalid_assignment_and_inventory_link(self):
        path = self.split / 'manifest.json'
        original = json.loads(path.read_text())
        for change in ('assignment', 'inventory', 'group'):
            report = json.loads(json.dumps(original))
            if change == 'assignment':
                report['assignments'].pop('lme-q000000')
            elif change == 'inventory':
                report['inventory_sha256'] = '0' * 64
            else:
                report['assignments']['lme-q000000'] = 'test'
                report['assignments']['lme-q000001'] = 'dev'
            path.write_text(json.dumps(report))
            with self.assertRaises(ValueError):
                self.run_pilot()
            self.assertFalse((self.root / 'pilot').exists())
