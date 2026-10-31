"""Serial group execution with a supervised worker and durable parent-owned results."""

from collections import OrderedDict
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import errno
import json
import multiprocessing
from pathlib import Path
import pickle
import platform
import shutil
import time
from uuid import uuid4

from evirecall.agents.fixture import FixtureAgent
from evirecall.contracts import ContractError, MemoryScope, RetrievalBudget, Usage
from evirecall.memory.fixture import FixtureMemory
from evirecall.runner.backends import factory_identity, factory_provenance
from evirecall.runner.accounting import CallLedger, aggregate_calls
from evirecall.runner.records import append_jsonl, read_jsonl, write_json
from evirecall.runner.runtime import ExecutionLimits, ExecutionStopped, RuntimeContext, validate_agent_output

ROOT = Path(__file__).resolve().parents[2]
RUN_SCHEMA_VERSION = 2


def now():
    return datetime.now(timezone.utc).isoformat()


def _code_snapshot(directory, backend_sources):
    from evirecall.runner.smoke import git_state
    state = git_state()
    # Capture only code/configuration inputs; never copy local credentials or runs.
    selected = [ROOT / 'pyproject.toml']
    for folder in ('evirecall', 'configs', 'tests'):
        selected.extend(p for p in (ROOT / folder).rglob('*')
                        if p.is_file() and (p.suffix in ('.py', '.json') or p.name in (
                            'LICENSE', 'NOTICE.txt', 'longmemeval-MIT-LICENSE.txt'))
                        and '__pycache__' not in p.parts)
    hashes = {}
    for source in selected:
        relative = source.relative_to(ROOT)
        target = directory / 'code' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        hashes[relative.as_posix()] = hashlib.sha256(source.read_bytes()).hexdigest()
    captured = {}
    for role, info in backend_sources.items():
        relative = f'backend-sources/{role}.py'
        target = directory / 'code' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(info['source_path'], target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest != info['source_sha256']:
            raise ContractError('Backend source changed after validation')
        hashes[relative] = digest
        captured[role] = {**info, 'snapshot_path': f'code/{relative}'}
    return {**state, 'snapshot': 'code', 'sha256': hashes, 'backend_sources': captured}


def _result(task, status, prediction=None, evidence=None, *, error_kind=None, elapsed_ms=0,
            queue_ms=0, usage=None):
    return {'schema_version': RUN_SCHEMA_VERSION, 'task_id': task.task_id, 'dataset': task.dataset,
            'group_id': task.group_id, 'session_id': task.session_id, 'status': status,
            'prediction': prediction, 'evidence': evidence or {'items': [], 'route': 'failed'},
            'usage': usage or asdict(Usage()), 'elapsed_ms': elapsed_ms, 'queue_ms': queue_ms,
            'end_to_end_ms': queue_ms + elapsed_ms, 'trace_file': 'trace.jsonl',
            'error_kind': error_kind, 'error': error_kind}


def _worker(tasks, directory, store_path, run_id, condition, repetition, budget, limits,
            agent_factory, memory_factory, connection):
    directory = Path(directory)
    ledger = CallLedger(directory / 'calls.jsonl', {'run_id': run_id, 'condition': condition,
                                                  'repetition': repetition})
    memory, sources = None, {}
    sequence = 0
    try:
        for task in tasks:
            connection.send(('started', task.task_id))
            if not connection.recv():
                return
            started = time.monotonic()

            def emit(role, operation, payload):
                nonlocal sequence
                sequence += 1
                append_jsonl(directory / 'trace.jsonl', {
                    'schema_version': RUN_SCHEMA_VERSION, 'event_id': uuid4().hex,
                    'run_id': run_id, 'condition': condition, 'repetition': repetition,
                    'dataset': task.dataset, 'task_id': task.task_id, 'group_id': task.group_id,
                    'session_id': task.session_id, 'sequence': sequence, 'timestamp': now(),
                    'role': role, 'operation': operation, 'payload': payload})

            def register(event):
                append_jsonl(directory / 'sources.jsonl', {
                    'run_id': run_id, 'condition': condition, 'task_id': task.task_id,
                    'dataset': task.dataset, 'group_id': task.group_id,
                    'observation': asdict(event)})
                emit('runner', 'source.registered', {'source_id': event.source_id})

            context = RuntimeContext(task, emit, register, sources, ledger, store_path, limits)
            emit('runner', 'task.started', {'query': task.query, 'budget': asdict(budget)})
            try:
                if memory is None:
                    memory = memory_factory()
                    scope = MemoryScope(run_id, condition, task.dataset, task.group_id,
                                        repetition=repetition, store_path=str(store_path))
                    memory.reset(scope)
                for event in task.events:
                    context.register_source(event)
                output = agent_factory().run(task, memory, budget, context)
                context.check_limits()
                validate_agent_output(output, sources, budget)
                result = _result(task, output.status, output.prediction, asdict(output.evidence),
                                 usage=ledger.summary(task.task_id),
                                 elapsed_ms=(time.monotonic() - started) * 1000,
                                 error_kind='adapter_failed' if output.status == 'failed' else None)
            except Exception as exc:
                kind = exc.kind if isinstance(exc, ExecutionStopped) else (
                    'invalid_output' if isinstance(exc, ContractError) else type(exc).__name__)
                result = _result(task, 'failed', error_kind=kind,
                                 usage=ledger.summary(task.task_id),
                                 elapsed_ms=(time.monotonic() - started) * 1000)
            emit('runner', 'task.finished', result)
            connection.send(('finished', result))
            # Parent fsyncs the result before permitting the next dependent task.
            if not connection.recv() or result['status'] == 'failed':
                return
    finally:
        if memory is not None and callable(getattr(memory, 'close', None)):
            memory.close()
        connection.close()


def execute_tasks(tasks, output_dir, *, condition='fixture-wiring', repetition=1,
                  budget=RetrievalBudget(), limits=ExecutionLimits(),
                  agent_factory=FixtureAgent, memory_factory=FixtureMemory,
                  history_mode='sequential', provenance=None):
    """Run sequential groups in fresh spawn workers. No scoring or provider fallback."""
    tasks = list(tasks)
    if not tasks or len({t.task_id for t in tasks}) != len(tasks):
        raise ContractError('Expected nonempty tasks with unique IDs')
    if history_mode not in ('sequential', 'independent'):
        raise ContractError('history_mode must be sequential or independent')
    if type(repetition) is not int or repetition < 1:
        raise ContractError('repetition must be a positive integer')
    if not isinstance(condition, str) or not condition.strip():
        raise ContractError('condition must be nonempty')
    # Spawn requires importable factories. Fail before creating any run artifact.
    try:
        pickle.dumps((agent_factory, memory_factory))
    except Exception as exc:
        raise ContractError('Factories must be importable top-level objects for spawn workers') from exc
    backend_sources = {role: factory_provenance(factory, (provenance or {}).get('backends', {}).get(role, {}).get('requested_spec'))
                       for role, factory in (('agent', agent_factory), ('memory', memory_factory))}
    provenance = {**(provenance or {}), 'backends': backend_sources}
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    run_id, queued_at = uuid4().hex, now()
    groups = OrderedDict()
    for task in tasks:
        key = (*task.group_key, task.task_id if history_mode == 'independent' else 'shared')
        groups.setdefault(key, []).append(task)
    manifest = {'schema_version': RUN_SCHEMA_VERSION, 'mode': 'execution', 'run_id': run_id,
                'condition': condition, 'repetition': repetition, 'created_at': queued_at,
                'python': platform.python_version(), 'code': _code_snapshot(output_dir, backend_sources),
                'budget': asdict(budget), 'limits': asdict(limits), 'history_mode': history_mode,
                'agent_backend': factory_identity(agent_factory),
                'memory_backend': factory_identity(memory_factory),
                'task_ids': [t.task_id for t in tasks], 'inputs': provenance or {},
                'notice': 'Backend identity is explicit; fixture outputs are wiring checks only.'}
    write_json(output_dir / 'manifest.json', manifest)
    for task in tasks:
        append_jsonl(output_dir / 'tasks.jsonl', asdict(task))
    stores = {}
    for key, members in groups.items():
        namespace = hashlib.sha256(json.dumps(key).encode()).hexdigest()[:24]
        path = output_dir / 'stores' / namespace
        path.mkdir(parents=True)
        stores[key] = path
        for task in members:
            append_jsonl(output_dir / 'schedule.jsonl', {'task_id': task.task_id, 'state': 'queued',
                         'timestamp': queued_at, 'store_path': str(path)})
    for name in ('results.jsonl', 'calls.jsonl', 'trace.jsonl', 'sources.jsonl'):
        (output_dir / name).touch()
    clock_started = time.monotonic()
    finished, stop_reason = set(), None
    context = multiprocessing.get_context('spawn')
    try:
        for key, members in groups.items():
            if stop_reason:
                for task in members:
                    append_jsonl(output_dir / 'schedule.jsonl', {'task_id': task.task_id,
                                 'state': 'skipped', 'reason': stop_reason, 'timestamp': now()})
                continue
            parent, child = context.Pipe()
            worker = context.Process(target=_worker, args=(members, str(output_dir), stores[key], run_id,
                condition, repetition, budget, limits, agent_factory, memory_factory, child), daemon=True)
            active, active_started, active_queue_ms = None, None, 0
            group_reason = 'dependency_failed'
            try:
                worker.start()
                child.close()
                while True:
                    current = time.monotonic()
                    if current - clock_started >= limits.run_timeout_s:
                        stop_reason, group_reason = 'run_timeout', 'run_timeout'
                        break
                    if active is not None and current - active_started >= limits.episode_timeout_s:
                        group_reason = 'timeout'
                        break
                    if parent.poll(.02):
                        try:
                            kind, value = parent.recv()
                        except EOFError:
                            break
                        if kind == 'started':
                            active = next(t for t in members if t.task_id == value)
                            active_started = time.monotonic()
                            active_queue_ms = (active_started - clock_started) * 1000
                            append_jsonl(output_dir / 'schedule.jsonl', {'task_id': value,
                                         'state': 'started', 'timestamp': now()})
                            parent.send(True)
                        elif kind == 'finished':
                            value['queue_ms'] = active_queue_ms
                            value['end_to_end_ms'] = active_queue_ms + value['elapsed_ms']
                            append_jsonl(output_dir / 'results.jsonl', value)
                            finished.add(value['task_id'])
                            if value.get('error_kind') == 'budget_exhausted':
                                stop_reason = 'budget_exhausted'
                            parent.send(stop_reason is None)
                            active = None
                    elif not worker.is_alive():
                        break
            except KeyboardInterrupt:
                stop_reason, group_reason = 'interrupted', 'interrupted'
            except (EOFError, BrokenPipeError, ConnectionResetError):
                group_reason = 'worker_crash'
            except OSError as exc:
                # Windows can report a closed multiprocessing pipe as WinError 109
                # instead of EOFError, including after a final result was saved.
                if getattr(exc, 'winerror', None) not in (109, 232, 233) and exc.errno not in (errno.EPIPE, errno.ECONNRESET):
                    raise
                group_reason = 'worker_crash'
            finally:
                if worker.pid is not None:
                    worker.join(.1)
                    if worker.is_alive():
                        worker.terminate()
                        worker.join(3)
                    if worker.is_alive():
                        worker.kill()
                        worker.join()
                parent.close()
                child.close()
            if active is not None and active.task_id not in finished:
                calls = read_jsonl(output_dir / 'calls.jsonl', recover_tail=True)
                result = _result(active, 'failed', error_kind=group_reason if group_reason != 'dependency_failed'
                                 else 'worker_crash', elapsed_ms=(time.monotonic() - active_started) * 1000,
                                 queue_ms=active_queue_ms, usage=aggregate_calls(calls.records, active.task_id))
                append_jsonl(output_dir / 'results.jsonl', result)
                finished.add(active.task_id)
            # A killed worker can leave any of its streams unfinished. Never append
            # a subsequent group's events onto that tail: keep it recoverable.
            for filename in ('calls.jsonl', 'trace.jsonl', 'sources.jsonl'):
                if read_jsonl(output_dir / filename, recover_tail=True).warnings:
                    stop_reason = 'incomplete_worker_log'
            for task in members:
                if task.task_id not in finished:
                    append_jsonl(output_dir / 'schedule.jsonl', {'task_id': task.task_id, 'state': 'skipped',
                                 'reason': stop_reason or group_reason, 'timestamp': now()})
    finally:
        write_json(output_dir / 'execution.json', {'run_id': run_id, 'finished_at': now(),
                   'wall_ms': (time.monotonic() - clock_started) * 1000, 'stop_reason': stop_reason})
    from evirecall.evaluation.aggregate import summarize_run
    summary = summarize_run(output_dir)
    write_json(output_dir / 'summary.json', summary)
    return summary
