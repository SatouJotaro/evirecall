import json
from pathlib import Path
import tempfile
import unittest

from evirecall.tasks import longmemeval as lme


def sample(qid='q1', content='Remember blue', sid='answer_secret'):
    return dict(question_id=qid, question_type='single-session-user', question='Which color?', answer='blue', question_date='2023/05/30 (Tue) 23:40', haystack_session_ids=[sid], haystack_dates=['2023/05/20 (Sat) 12:30'], haystack_sessions=[[dict(role='user', content=content, has_answer=True), dict(role='assistant', content='Okay', has_answer=False)]], answer_session_ids=[sid])


class LongMemEvalPreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def prepare(self, rows, name='out'):
        source = self.root / (name + '.json')
        source.write_text(json.dumps(rows), encoding='utf-8')
        target = self.root / name
        result = lme.prepare_dataset(source, target, revision='locked-revision')
        return target, result

    def test_public_view_blinds_nested_labels_and_preserves_order_dates(self):
        target, manifest = self.prepare([sample('q_abs')])
        public = (target / 'public/tasks.jsonl').read_text()
        for hidden in ('answer_secret', 'q_abs', 'has_answer', 'question_type', 'answer_session_ids'):
            self.assertNotIn(hidden, public)
        task = json.loads(public)
        self.assertEqual(task['query_time'], '2023/05/30 (Tue) 23:40')
        self.assertEqual([e['text'] for e in task['events']], ['Remember blue', 'Okay'])
        self.assertIsNone(task['events'][0]['timestamp'])
        self.assertEqual(task['events'][0]['source_time_raw'], '2023/05/20 (Sat) 12:30')
        ref = json.loads((target / 'evaluator/references.jsonl').read_text())
        self.assertTrue(ref['abstention'])
        self.assertEqual(ref['answer_session_ids'], ['answer_secret'])
        self.assertEqual(ref['source_id_mapping'][task['events'][0]['source_id']]['session_id'], 'answer_secret')
        self.assertEqual(manifest['task_count'], 1)

    def test_invalid_inputs_leave_no_output(self):
        cases = []
        for field, value in [('haystack_dates', []), ('question_date', 'bad'), ('question_type', 8), ('answer_session_ids', ['missing']), ('haystack_session_ids', [''])]:
            row = sample(); row[field] = value; cases.append([row])
        cases.append([sample(), sample()])
        for index, rows in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.prepare(rows, 'bad' + str(index))
            self.assertFalse((self.root / ('bad' + str(index))).exists())

    def test_hash_mismatch_and_existing_directory_are_refused(self):
        source = self.root / 'source.json'; source.write_text(json.dumps([sample()]))
        with self.assertRaises(ValueError):
            lme.prepare_dataset(source, self.root / 'wrong', revision='r', expected_sha256='0' * 64)
        target, _ = self.prepare([sample()])
        before = (target / 'manifest.json').read_bytes()
        with self.assertRaises(FileExistsError):
            lme.prepare_dataset(source, target, revision='r')
        self.assertEqual(before, (target / 'manifest.json').read_bytes())

    def test_grouped_split_keeps_family_history_and_evidence_together(self):
        rows = [sample('a'), sample('a_abs', 'different', 'answer_other'), sample('b', 'Remember blue', 'answer_new'), sample('c', 'distinct', 'answer_c'), sample('d', 'last', 'answer_d')]
        target, _ = self.prepare(rows)
        report = lme.build_split(target, self.root / 'split', dev_units=1, test_questions=100, seed=3)
        again = lme.build_split(target, self.root / 'split2', dev_units=1, test_questions=100, seed=3)
        self.assertEqual(report, again)
        self.assertFalse(report['official_split'])
        self.assertTrue(report['insufficient_test_questions'])
        assignment = report['assignments']
        self.assertEqual(assignment['lme-q000000'], assignment['lme-q000001'])
        self.assertEqual(assignment['lme-q000000'], assignment['lme-q000002'])
        original = {x['task_id']: x for x in map(json.loads, (target / 'public/tasks.jsonl').read_text().splitlines())}
        for split in ('dev', 'test', 'unused'):
            for task in map(json.loads, (self.root / 'split' / split / 'tasks.jsonl').read_text().splitlines()):
                self.assertEqual(task, original[task['task_id']])
        self.assertEqual(report['cross_split_overlap']['history'], [])
        self.assertEqual(report['cross_split_overlap']['evidence'], [])


if __name__ == '__main__':
    unittest.main()

class LongMemEvalAuditTests(unittest.TestCase):
    setUp = LongMemEvalPreparationTests.setUp
    prepare = LongMemEvalPreparationTests.prepare
    def test_shared_filler_is_reported_without_collapsing_all_groups(self):
        rows = []
        for index in range(3):
            row = sample(f'q{index}', f'evidence {index}', f'answer_{index}')
            row['haystack_session_ids'].append('shared_filler')
            row['haystack_dates'].append('2023/05/20 (Sat) 12:30')
            row['haystack_sessions'].append([dict(role='user', content='filler')])
            rows.append(row)
        target, manifest = self.prepare(rows)
        self.assertEqual(manifest['split_group_count'], 3)
        report = lme.build_split(target, self.root / 'split', dev_units=1, test_questions=2)
        self.assertTrue(report['cross_split_overlap']['all_sessions'])
        self.assertEqual(report['cross_split_overlap']['evidence'], [])

    def test_malformed_turn_and_date_are_rejected(self):
        for index, edit in enumerate((lambda r: r['haystack_sessions'][0][0].update(role='bad'), lambda r: r.update(haystack_dates=['2023/02/31 (Fri) 12:30']), lambda r: r['haystack_sessions'][0][0].update(content=23))):
            row = sample(); edit(row)
            with self.assertRaises(ValueError):
                self.prepare([row], f'invalid{index}')

    def test_source_ids_reject_whitespace_and_controls(self):
        row = sample(sid='answer_bad\nidentifier')
        with self.assertRaises(ValueError):
            self.prepare([row])

    def test_reused_evidence_content_is_grouped_despite_date_changes(self):
        first, second = sample('first'), sample('second', sid='answer_second')
        second['haystack_dates'] = ['2023/05/21 (Sun) 12:30']
        target, manifest = self.prepare([first, second])
        self.assertEqual(manifest['split_group_count'], 1)




class EvidenceFillerIsolationTests(unittest.TestCase):
    setUp = LongMemEvalPreparationTests.setUp
    prepare = LongMemEvalPreparationTests.prepare
    def test_evidence_reused_as_filler_cannot_cross_split(self):
        first = sample('first', 'shared evidence', 'answer_first')
        second = sample('second', 'different evidence', 'answer_second')
        second['haystack_session_ids'].append('filler_shared')
        second['haystack_dates'].append('2023/05/20 (Sat) 12:30')
        second['haystack_sessions'].append(first['haystack_sessions'][0])
        target, manifest = self.prepare([first, second])
        self.assertEqual(manifest['split_group_count'], 1)
        report = lme.build_split(target, self.root / 'split', dev_units=1, test_questions=1)
        self.assertEqual(len(set(report['assignments'].values())), 1)
        self.assertEqual(report['cross_split_overlap']['evidence'], [])




class RealSchemaCompatibilityTests(unittest.TestCase):
    setUp = LongMemEvalPreparationTests.setUp
    prepare = LongMemEvalPreparationTests.prepare

    def test_numeric_answers_preserve_source_type(self):
        row = sample(); row['answer'] = 3
        target, _ = self.prepare([row])
        reference = json.loads((target / 'evaluator/references.jsonl').read_text())
        self.assertEqual(reference['answer'], 3)
        self.assertIs(type(reference['answer']), int)

    def test_repeated_filler_session_ids_resolve_by_ordinal(self):
        row = sample()
        row['haystack_session_ids'].extend(['filler', 'filler'])
        row['haystack_dates'].extend(['2023/05/20 (Sat) 12:30'] * 2)
        row['haystack_sessions'].extend([[dict(role='user', content='one')], [dict(role='user', content='two')]])
        target, manifest = self.prepare([row])
        self.assertEqual(manifest['audit']['repeated_session_id_occurrences'], 1)
        reference = json.loads((target / 'evaluator/references.jsonl').read_text())
        matches = [v for v in reference['source_id_mapping'].values() if v['session_id'] == 'filler']
        self.assertEqual([v['session_index'] for v in matches], [1, 2])

    def test_nonfinite_or_boolean_answers_are_rejected(self):
        for index, value in enumerate((True, float('inf'), float('nan'))):
            row=sample(); row['answer']=value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.prepare([row], f'invalid-answer-{index}')

    def test_unicode_line_separators_remain_within_jsonl_records(self):
        from evirecall.tasks.loading import load_tasks
        row=sample(content='one\u2028two\u0085three\u2029four')
        row['question']='q\u2028q\u0085q\u2029q'
        target, _ = self.prepare([row])
        tasks=load_tasks(target / 'public/tasks.jsonl')
        self.assertEqual(tasks[0].query, row['question'])
        report=lme.build_split(target, self.root/'split',dev_units=1,test_questions=0)
        self.assertEqual(report['actual_dev_units'],1)


    def test_split_refuses_tampered_prepared_artifacts(self):
        for index, relative in enumerate(('public/tasks.jsonl', 'evaluator/references.jsonl', 'inventory.json')):
            target, manifest = self.prepare([sample()], f'prepared-{index}')
            self.assertIn(relative, manifest['artifact_sha256'])
            path=target / relative
            path.write_bytes(path.read_bytes() + b' ')
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                lme.build_split(target,self.root/f'split-{index}',dev_units=1,test_questions=0)
            self.assertFalse((self.root/f'split-{index}').exists())


if __name__ == '__main__':
    unittest.main()
