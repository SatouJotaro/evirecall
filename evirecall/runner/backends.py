"""Trusted, importable backend factories and reproducible source identities."""
import hashlib
import importlib
import inspect
from pathlib import Path
import pickle
import keyword

from evirecall.agents.fixture import FixtureAgent
from evirecall.memory.fixture import FixtureMemory
from evirecall.contracts import ContractError


def factory_identity(factory):
    implementation = factory if inspect.isfunction(factory) or inspect.isclass(factory) else type(factory)
    return f'{implementation.__module__}.{implementation.__qualname__}'


def factory_provenance(factory, requested_spec=None):
    implementation = factory if inspect.isfunction(factory) or inspect.isclass(factory) else type(factory)
    try:
        source = Path(inspect.getsourcefile(implementation)).resolve()
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
    except (TypeError, OSError) as exc:
        raise ContractError('Backend factory must have readable Python source') from exc
    return {'requested_spec': requested_spec, 'identity': factory_identity(factory),
            'module': implementation.__module__, 'source_path': str(source), 'source_sha256': digest}


def resolve_backend(spec, role):
    """Import without constructing. Adapter modules must avoid provider calls at import."""
    if not isinstance(spec, str):
        raise ContractError('Backend must be fixture or module:factory_name')
    if spec == 'fixture':
        factory = {'agent': FixtureAgent, 'memory': FixtureMemory}[role]
    else:
        parts = spec.split(':')
        if len(parts) != 2 or not all(part and all(token.isidentifier() and not keyword.iskeyword(token)
            for token in part.split('.')) for part in parts) or '.' in parts[1]:
            raise ContractError('Backend must be fixture or module:factory_name')
        try:
            factory = getattr(importlib.import_module(parts[0]), parts[1])
        except Exception as exc:
            raise ContractError(f'Cannot import backend {spec}') from exc
    try:
        if not (inspect.isfunction(factory) or inspect.isclass(factory)):
            raise TypeError('configured factory must be a top-level function or class')
        inspect.signature(factory).bind()
        pickle.dumps(factory)
        if '<locals>' in getattr(factory, '__qualname__', ''):
            raise TypeError('not top-level')
    except Exception as exc:
        raise ContractError('Backend must be an importable zero-argument callable for spawn') from exc
    return factory, factory_provenance(factory, spec)
