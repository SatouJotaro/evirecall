from pathlib import Path
import tempfile
import unittest

from evirecall.contracts import TaskInput
from evirecall.runner.accounting import CallLedger
from evirecall.runner.records import read_jsonl
from evirecall.runner.runtime import ExecutionLimits, RuntimeContext


class RuntimeTests(unittest.TestCase):
    def test_request_identity_and_actual_model_survive_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            task = TaskInput('fixture', 't', 'g', 's', 'Q', ())
            context = RuntimeContext(task, lambda *a: None, lambda *a: None, {},
                                     CallLedger(path / 'calls.jsonl'), path, ExecutionLimits())
            context.call(lambda: {'model': 'model-snapshot'}, role='answer', operation='generate',
                         phase='execution', provider='test', model='model-alias',
                         metadata={'request_sha256': 'saved-request-hash'},
                         actual_model_fn=lambda response: response['model'])
            rows = read_jsonl(path / 'calls.jsonl').records
            self.assertEqual(rows[0]['request_metadata']['request_sha256'], 'saved-request-hash')
            self.assertEqual(rows[1]['model'], 'model-alias')
            self.assertEqual(rows[1]['actual_model'], 'model-snapshot')
            self.assertIsNone(context.ledger.summary()['cost_usd'])

    def test_model_metadata_error_does_not_discard_observed_charge(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            task = TaskInput('fixture', 't', 'g', 's', 'Q', ())
            context = RuntimeContext(task, lambda *a: None, lambda *a: None, {},
                                     CallLedger(path / 'calls.jsonl'), path, ExecutionLimits())
            with self.assertRaises(KeyError):
                context.call(lambda: {}, role='answer', operation='generate', phase='execution',
                             provider='test', model='model-alias',
                             usage_fn=lambda response: {'input_tokens': 4, 'output_tokens': 2, 'cost_usd': .25},
                             actual_model_fn=lambda response: response['model'])
            summary = context.ledger.summary()
            self.assertEqual(summary['cost_usd'], .25)
            self.assertEqual(summary['input_tokens'], 4)
            self.assertEqual(summary['requests'], 1)
