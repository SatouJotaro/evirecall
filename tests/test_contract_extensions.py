import unittest
from dataclasses import asdict
from evirecall.contracts import Observation, TaskInput, ContractError
from evirecall.contracts import MemoryScope, RetrievalBudget
from evirecall.memory.fixture import FixtureMemory


class ContractExtensions(unittest.TestCase):
    def test_unknown_source_timezone_is_preserved_without_fabricating_utc(self):
        raw = {'source_id': 's1', 'text': 'public', 'writer_role': 'user', 'timestamp': None,
               'source_time_raw': '2023/05/30 (Tue) 23:40'}
        observation = Observation.from_dict(raw)
        self.assertIsNone(observation.timestamp)
        self.assertEqual(observation.source_time_raw, raw['source_time_raw'])
        task = TaskInput.from_dict({'dataset': 'lme', 'task_id': 't1', 'group_id': 'g1',
            'session_id': 'q1', 'query': 'When?', 'query_time': raw['source_time_raw'], 'events': [raw]})
        self.assertEqual(task.query_time, raw['source_time_raw'])
        self.assertNotIn('answer', asdict(task))

    def test_v1_timestamp_still_requires_timezone(self):
        with self.assertRaises(ContractError):
            Observation('s', 't', 'user', '2023-05-30T23:40:00')
        with self.assertRaises(ContractError):
            Observation('s', 't', 'user', None)

    def test_evidence_retains_unknown_timezone_source_time(self):
        memory = FixtureMemory()
        memory.reset(MemoryScope('run', 'fixture', 'lme', 'group'))
        raw = '2023/05/30 (Tue) 23:40'
        memory.observe(Observation('s', 'text', 'user', None, source_time_raw=raw))
        evidence = memory.retrieve('query', RetrievalBudget()).items[0]
        self.assertIsNone(evidence.event_time)
        self.assertEqual(evidence.source_time_raw, raw)

    def test_empty_history_turn_is_preserved_but_not_selected_as_evidence(self):
        observation = Observation('empty', '', 'assistant', None, source_time_raw='2023/05/30 (Tue) 23:40')
        memory = FixtureMemory()
        memory.reset(MemoryScope('run', 'fixture', 'lme', 'group'))
        memory.observe(observation)
        self.assertEqual(memory.records['empty'].text, '')
        self.assertEqual(memory.retrieve('query', RetrievalBudget()).items, ())
        with self.assertRaises(ContractError):
            Observation('invalid', None, 'assistant', '2023-05-30T23:40:00Z')
