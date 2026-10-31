import hashlib
import json
from pathlib import Path
import tempfile
import sys
import unittest

from evirecall.agents.fixture import FixtureAgent
from evirecall.memory.fixture import FixtureMemory
from evirecall.contracts import ContractError
from evirecall.runner.config import inspect_config, run_config

ROOT = Path(__file__).resolve().parents[1]
CONSTRUCTIONS = []
NOT_CALLABLE = 3

class InstanceFactory:
    def __call__(self):
        return FixtureAgent()

    def __reduce__(self):
        return (custom_agent, ())

INSTANCE_FACTORY = InstanceFactory()

def custom_agent():
    CONSTRUCTIONS.append('agent')
    return FixtureAgent()

def custom_memory():
    CONSTRUCTIONS.append('memory')
    return FixtureMemory()

def requires_argument(value):
    return value

class BackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def config(self, **changes):
        config = json.loads((ROOT / 'configs/run-fixture.json').read_text())
        config['tasks'] = str(ROOT / 'fixtures/public/tasks.jsonl')
        config.update(changes)
        path = self.root / 'config.json'
        path.write_text(json.dumps(config), encoding='utf-8')
        return path

    def test_preflight_never_constructs_and_is_serializable(self):
        CONSTRUCTIONS.clear()
        report = inspect_config(self.config(agent_backend='test_backends:custom_agent'))
        self.assertEqual(CONSTRUCTIONS, [])
        self.assertEqual(report['task_count'], 3)
        self.assertEqual(report['backends']['agent']['identity'], 'test_backends.custom_agent')
        json.dumps(report)
        self.assertEqual(list(self.root.iterdir()), [self.root / 'config.json'])

    def test_invalid_specs_fail_before_output(self):
        for spec in ['unknown', 'missing_module_xyz:factory', 'test_backends:missing',
                     'test_backends:NOT_CALLABLE', 'test_backends:requires_argument',
                     'test_backends:custom_agent()', 'tests..test_backends:custom_agent']:
            with self.subTest(spec=spec), self.assertRaises(ContractError):
                run_config(self.config(agent_backend=spec), self.root / 'run')
            self.assertFalse((self.root / 'run').exists())

    def test_custom_factories_spawn_and_snapshot_actual_source(self):
        run = self.root / 'run'
        summary = run_config(self.config(agent_backend='test_backends:custom_agent',
                                         memory_backend='test_backends:custom_memory'), run)
        self.assertEqual(summary['counts']['planned'], 3)
        results = [json.loads(line) for line in (run / 'results.jsonl').read_text().splitlines()]
        self.assertTrue(all(row['status'] != 'failed' for row in results))
        manifest = json.loads((run / 'manifest.json').read_text())
        digest = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        for role in ('agent', 'memory'):
            self.assertEqual(hashlib.sha256((run / 'code/backend-sources' / f'{role}.py').read_bytes()).hexdigest(), digest)
            self.assertEqual(manifest['code']['backend_sources'][role]['source_sha256'], digest)
            self.assertEqual(manifest['inputs']['backends'][role]['source_sha256'], digest)

    def test_fixture_alias_retained(self):
        self.assertEqual(inspect_config(self.config())['backends']['agent']['identity'],
                         'evirecall.agents.fixture.FixtureAgent')

    def test_external_reexport_snapshots_implementation_module(self):
        implementation = self.root / 'external_implementation_m3.py'
        implementation.write_text('from evirecall.agents.fixture import FixtureAgent\ndef make_agent():\n    return FixtureAgent()\n')
        (self.root / 'external_export_m3.py').write_text('from external_implementation_m3 import make_agent\n')
        sys.path.insert(0, str(self.root))
        self.addCleanup(sys.path.remove, str(self.root))
        self.addCleanup(sys.modules.pop, 'external_export_m3', None)
        self.addCleanup(sys.modules.pop, 'external_implementation_m3', None)
        config = self.config(agent_backend='external_export_m3:make_agent')
        report = inspect_config(config)
        self.assertEqual(report['backends']['agent']['identity'], 'external_implementation_m3.make_agent')
        run_config(config, self.root / 'external-run')
        self.assertEqual((self.root / 'external-run/code/backend-sources/agent.py').read_bytes(), implementation.read_bytes())

    def test_callable_instance_rejected_without_unpickling_or_construction(self):
        CONSTRUCTIONS.clear()
        with self.assertRaises(ContractError):
            inspect_config(self.config(agent_backend='test_backends:INSTANCE_FACTORY'))
        self.assertEqual(CONSTRUCTIONS, [])
