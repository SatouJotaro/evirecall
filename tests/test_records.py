import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evirecall.contracts import ContractError
from evirecall.runner.records import append_jsonl, read_jsonl, write_json


class RecordsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'nested' / 'records.jsonl'

    def test_append_is_durable_and_missing_is_empty(self):
        self.assertEqual(read_jsonl(self.path).records, [])
        with patch('evirecall.runner.records.os.fsync') as sync:
            append_jsonl(self.path, {'text': '中文'})
            self.assertEqual(sync.call_count, 1)
        self.assertEqual(read_jsonl(self.path).records, [{'text': '中文'}])

    def test_recovery_only_skips_unterminated_malformed_tail(self):
        self.path.parent.mkdir()
        original = b'{"a":1}\n{"broken":'
        self.path.write_bytes(original)
        with self.assertRaises(ContractError):
            read_jsonl(self.path)
        result = read_jsonl(self.path, recover_tail=True)
        self.assertEqual(result.records, [{'a': 1}])
        self.assertEqual(len(result.warnings), 1)
        self.assertEqual(self.path.read_bytes(), original)
        for payload in (b'{bad}\n', b'{bad}\n{"ok":1}', b'[]'):
            self.path.write_bytes(payload)
            with self.assertRaises(ContractError):
                read_jsonl(self.path, recover_tail=True)

    def test_recovery_preserves_and_warns_for_complete_unterminated_tail(self):
        self.path.parent.mkdir()
        for original, expected in ((b'{}', [{}]), (b'{"a":1}\n{"b":2}', [{'a': 1}, {'b': 2}])):
            with self.subTest(original=original):
                self.path.write_bytes(original)
                self.assertEqual(read_jsonl(self.path).records, expected)
                result = read_jsonl(self.path, recover_tail=True)
                self.assertEqual(result.records, expected)
                self.assertEqual(len(result.warnings), 1)
                self.assertIn('unterminated final line', result.warnings[0])
                self.assertEqual(self.path.read_bytes(), original)

    def test_finite_json_and_atomic_replace(self):
        write_json(self.path, {'old': 1})
        for value in ({'x': float('nan')}, {'x': float('inf')}):
            with self.assertRaises(ContractError):
                write_json(self.path, value)
            with self.assertRaises(ContractError):
                append_jsonl(self.path, value)
        self.assertEqual(json.loads(self.path.read_text()), {'old': 1})
        write_json(self.path, {'new': 2})
        self.assertEqual(json.loads(self.path.read_text()), {'new': 2})
