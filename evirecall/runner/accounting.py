"""Single-writer request ledger; persisted events are the accounting source."""

from datetime import datetime, timezone
import math
from pathlib import Path
import time
from uuid import uuid4

from evirecall.contracts import ContractError, require_text
from evirecall.runner.records import append_jsonl, read_jsonl

_USAGE = ('input_tokens', 'output_tokens', 'cost_usd')
_IDENTITY = ('task_id', 'role', 'operation', 'phase', 'provider', 'model', 'logical_call_id', 'attempt')


def _timestamp(value, field):
    try:
        result = datetime.fromisoformat(value)
        if result.utcoffset() is None:
            raise ValueError('timezone required')
        return result
    except (TypeError, ValueError) as exc:
        raise ContractError(f'{field} must be a timezone-aware ISO timestamp') from exc


def validate_usage(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ContractError('usage must be an object or null')
    for key in _USAGE:
        number = value.get(key)
        if key.endswith('_tokens') and number is not None and type(number) is not int:
            raise ContractError(f'{key} must be an integer or null')
        if number is not None and (isinstance(number, bool) or not isinstance(number, (int, float))
                                   or not math.isfinite(number) or number < 0):
            raise ContractError(f'{key} must be a finite nonnegative number or null')
    return dict(value)


def _replay(records):
    calls = {}
    for event in records:
        if not isinstance(event, dict):
            raise ContractError('Call event must be an object')
        call_id = require_text(event.get('call_id'), 'call_id')
        kind = event.get('event')
        if kind == 'call.started':
            if call_id in calls:
                raise ContractError(f'Duplicate call start: {call_id}')
            for key in _IDENTITY[:-1]:
                require_text(event.get(key), key)
            attempt = event.get('attempt')
            if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
                raise ContractError('attempt must be a positive integer')
            _timestamp(event.get('started_at'), 'started_at')
            calls[call_id] = dict(event)
        elif kind == 'call.finished':
            if call_id not in calls or calls[call_id].get('event') != 'call.started':
                raise ContractError(f'Call finish without unmatched start: {call_id}')
            if event.get('status') not in ('completed', 'failed'):
                raise ContractError('Call terminal status must be completed or failed')
            for key in _IDENTITY:
                if event.get(key) != calls[call_id].get(key):
                    raise ContractError(f'Call identity changed at finish: {key}')
            if event.get('started_at') != calls[call_id].get('started_at'):
                raise ContractError('Call start time changed at finish')
            _timestamp(event.get('finished_at'), 'finished_at')
            validate_usage({'cost_usd': event.get('elapsed_ms')})
            if event.get('elapsed_ms') is None:
                raise ContractError('Call finish requires elapsed_ms')
            validate_usage(event.get('usage'))
            if event.get('actual_model') is not None:
                require_text(event['actual_model'], 'actual_model')
            calls[call_id] = {**calls[call_id], **event}
        else:
            raise ContractError(f'Unknown call event: {kind}')
    return calls


def _summary(calls):
    count = len(calls)
    usage = [call.get('usage') or {} for call in calls]
    token_known = sum(all(item.get(key) is not None for key in _USAGE[:2]) for item in usage)
    cost_known = sum(item.get('cost_usd') is not None for item in usage)
    result = {
        'requests': count,
        'known_cost_usd': sum(item.get('cost_usd') or 0 for item in usage),
        'usage_coverage': token_known / count if count else None,
        'cost_coverage': cost_known / count if count else None,
        'unknown_usage_calls': count - token_known,
        'unknown_cost_calls': count - cost_known,
        'unfinished_calls': sum(call['event'] == 'call.started' for call in calls),
        'completed_calls': sum(call.get('status') == 'completed' for call in calls),
        'failed_calls': sum(call.get('status') == 'failed' for call in calls),
    }
    for key in _USAGE:
        result[key] = sum(item[key] for item in usage) if count and all(item.get(key) is not None for item in usage) else None
    return result


def aggregate_calls(records, task_id=None) -> dict:
    """Validate and replay events, counting each physical request once."""
    calls = [call for call in _replay(records).values() if task_id is None or call['task_id'] == task_id]
    result = _summary(calls)
    result['by_phase'] = {phase: _summary([call for call in calls if call['phase'] == phase])
                          for phase in sorted({call['phase'] for call in calls})}
    return result


class CallLedger:
    def __init__(self, path: str | Path, metadata=None):
        self.path = Path(path)
        self.metadata = dict(metadata or {})
        self._clocks = {}
        _replay(read_jsonl(self.path).records)

    def start(self, *, task_id, role, operation, phase, provider, model,
              logical_call_id=None, attempt=1, **metadata) -> str:
        call_id = uuid4().hex
        event = {**self.metadata, **metadata, 'event': 'call.started', 'call_id': call_id,
                 'task_id': task_id, 'role': role, 'operation': operation, 'phase': phase,
                 'provider': provider, 'model': model, 'logical_call_id': logical_call_id or call_id,
                 'attempt': attempt, 'started_at': datetime.now(timezone.utc).isoformat()}
        # Terminal fields cannot be injected through free-form metadata.
        for key in ('status', 'usage', 'finished_at', 'elapsed_ms', 'actual_model', 'error_kind'):
            event.pop(key, None)
        _replay([event])
        append_jsonl(self.path, event)
        self._clocks[call_id] = time.monotonic()
        return call_id

    def finish(self, call_id, *, status='completed', usage=None, error_kind=None, actual_model=None) -> dict:
        calls = _replay(read_jsonl(self.path).records)
        if call_id not in calls or calls[call_id]['event'] != 'call.started':
            raise ContractError(f'No unmatched call start: {call_id}')
        start = calls[call_id]
        now = datetime.now(timezone.utc)
        if call_id in self._clocks:
            elapsed = (time.monotonic() - self._clocks[call_id]) * 1000
        else:
            elapsed = max(0, (now - datetime.fromisoformat(start['started_at'])).total_seconds() * 1000)
        event = {**start, 'event': 'call.finished', 'status': status, 'usage': validate_usage(usage),
                 'finished_at': now.isoformat(), 'elapsed_ms': elapsed,
                 'error_kind': error_kind, 'actual_model': actual_model}
        _replay([start, event])
        append_jsonl(self.path, event)
        self._clocks.pop(call_id, None)
        return event

    def summary(self, task_id=None) -> dict:
        return aggregate_calls(read_jsonl(self.path).records, task_id=task_id)
