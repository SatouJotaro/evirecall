"""Strict explicit backend configuration for the independent execution harness."""

from dataclasses import fields
import hashlib
import json
from pathlib import Path

from evirecall.contracts import ContractError, RetrievalBudget, check_fields
from evirecall.runner.backends import resolve_backend
from evirecall.runner.core import execute_tasks
from evirecall.runner.runtime import ExecutionLimits
from evirecall.tasks.loading import load_tasks


def _validated_config(config_path):
    """Validate every input before execute_tasks creates its fresh output directory."""
    path = Path(config_path).resolve()
    config = json.loads(path.read_text(encoding='utf-8'))
    check_fields(config, {'agent_backend', 'memory_backend', 'condition', 'tasks',
                          'budget', 'limits', 'repetition', 'history_mode'})
    agent_factory, agent_info = resolve_backend(config['agent_backend'], 'agent')
    memory_factory, memory_info = resolve_backend(config['memory_backend'], 'memory')
    if not isinstance(config['condition'], str) or not config['condition'].strip():
        raise ContractError('condition must be nonempty')
    if config['history_mode'] not in ('sequential', 'independent'):
        raise ContractError('Unknown history_mode')
    if type(config['repetition']) is not int or config['repetition'] < 1:
        raise ContractError('repetition must be a positive integer')
    for key, cls in (('budget', RetrievalBudget), ('limits', ExecutionLimits)):
        check_fields(config[key], set(), {item.name for item in fields(cls)})
    budget, limits = RetrievalBudget(**config['budget']), ExecutionLimits(**config['limits'])
    if not isinstance(config['tasks'], str) or not config['tasks'].strip():
        raise ContractError('tasks must be a nonempty path')
    tasks_path = (path.parent / config['tasks']).resolve()
    tasks = load_tasks(tasks_path)
    provenance = dict(config_path=str(path), tasks_path=str(tasks_path), expanded_config=config,
                      config_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                      tasks_sha256=hashlib.sha256(tasks_path.read_bytes()).hexdigest())
    provenance['backends'] = {'agent': agent_info, 'memory': memory_info}
    return config, tasks, budget, limits, agent_factory, memory_factory, provenance


def inspect_config(config_path):
    """Read-only preflight: trusted imports, no factory construction or run files."""
    config, tasks, _, _, _, _, provenance = _validated_config(config_path)
    return {'config': config, 'task_count': len(tasks), 'backends': provenance['backends'],
            'input_statistics': {'observations': sum(len(t.events) for t in tasks),
                                 'history_characters': sum(len(e.text) for t in tasks for e in t.events)},
            'inputs': provenance}


def run_config(config_path, output_dir):
    config, tasks, budget, limits, agent_factory, memory_factory, provenance = _validated_config(config_path)
    return execute_tasks(tasks, output_dir, condition=config['condition'], repetition=config['repetition'],
                         budget=budget, limits=limits, agent_factory=agent_factory,
                         memory_factory=memory_factory, history_mode=config['history_mode'],
                         provenance=provenance)
