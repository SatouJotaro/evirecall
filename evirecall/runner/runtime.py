"""Observable, bounded adapter context; remains callable as the v1 emit hook."""

from dataclasses import dataclass
import math
from pathlib import Path
import time
from uuid import uuid4

from evirecall.contracts import ContractError, Observation, require_text
from evirecall.runner.accounting import validate_usage


class ExecutionStopped(RuntimeError):
    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class ExecutionLimits:
    episode_timeout_s: float = 60
    run_timeout_s: float = 600
    max_calls: int = 100
    max_events_per_episode: int = 1000
    max_attempts: int = 1
    retry_backoff_s: float = 0.1
    max_cost_usd: float | None = None

    def __post_init__(self):
        for key in ('episode_timeout_s', 'run_timeout_s'):
            value = getattr(self, key)
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ContractError(f'{key} must be finite and positive')
        for key in ('max_calls', 'max_events_per_episode', 'max_attempts'):
            if type(getattr(self, key)) is not int or getattr(self, key) < 1:
                raise ContractError(f'{key} must be a positive integer')
        for key in ('retry_backoff_s', 'max_cost_usd'):
            value = getattr(self, key)
            if value is not None and (type(value) not in (int, float)
                                      or not math.isfinite(value) or value < 0):
                raise ContractError(f'{key} must be finite and nonnegative')
        if self.retry_backoff_s is None:
            raise ContractError('retry_backoff_s is required')


class RuntimeContext:
    def __init__(self, task, emit, register, sources, ledger, store_path, limits):
        self.task = task
        self._emit = emit
        self._register = register
        self.sources = sources
        self.ledger = ledger
        self.store_path = Path(store_path)
        self.limits = limits
        self.deadline = time.monotonic() + limits.episode_timeout_s
        self.events = 0

    def check_limits(self):
        if time.monotonic() >= self.deadline:
            raise ExecutionStopped('timeout', 'Episode deadline reached')

    @property
    def remaining_seconds(self):
        return max(0, self.deadline - time.monotonic())

    def __call__(self, role, operation, payload):
        self.check_limits()
        if self.events >= self.limits.max_events_per_episode:
            raise ExecutionStopped('event_limit', 'Observable event limit reached')
        if not isinstance(payload, dict):
            raise ContractError('Trace payload must be an object')
        self.events += 1
        self._emit(role, operation, payload)

    def register_source(self, observation: Observation):
        """Register an adapter-approved public observation, not an authority judgment."""
        self.check_limits()
        if not isinstance(observation, Observation):
            raise ContractError('Expected an Observation')
        previous = self.sources.get(observation.source_id)
        if previous is not None and previous != observation:
            raise ContractError('An immutable source ID cannot be overwritten')
        if previous is None:
            self._register(observation)
            self.sources[observation.source_id] = observation

    def call(self, request, *, role, operation, phase, provider, model,
             usage_fn=None, actual_model_fn=None, metadata=None, retry_on=(), max_attempts=None):
        """Record physical attempts; adapters must disable hidden SDK retries.

        HTTP clients should use remaining_seconds as their timeout. The runner
        additionally supervises the worker process to stop a non-cooperative call.
        """
        attempts = self.limits.max_attempts if max_attempts is None else max_attempts
        if type(attempts) is not int or not 1 <= attempts <= self.limits.max_attempts:
            raise ContractError('max_attempts exceeds configured retry limit')
        if not isinstance(retry_on, tuple) or any(not isinstance(t, type) or not issubclass(t, Exception)
                                                 for t in retry_on):
            raise ContractError('retry_on must contain exception types')
        if phase not in ('ingestion', 'execution', 'evaluation'):
            raise ContractError('Unknown accounting phase')
        if metadata is not None and (not isinstance(metadata, dict) or set(metadata) - {
                'request_sha256', 'request_ref', 'prompt_template_sha256', 'price_ref', 'cache_policy'}):
            raise ContractError('Only reproducibility references belong in call metadata')
        logical_id = uuid4().hex
        for attempt in range(1, attempts + 1):
            self.check_limits()
            total = self.ledger.summary()
            if total['requests'] >= self.limits.max_calls:
                raise ExecutionStopped('budget_exhausted', 'Run request limit reached')
            if self.limits.max_cost_usd is not None:
                if total['known_cost_usd'] >= self.limits.max_cost_usd or (
                        total['requests'] and total['cost_usd'] is None):
                    raise ExecutionStopped('budget_exhausted', 'Cost cap reached or prior charges unknown')
            call_id = self.ledger.start(task_id=self.task.task_id, role=role, operation=operation,
                                        phase=phase, provider=provider, model=model,
                                        logical_call_id=logical_id, attempt=attempt,
                                        request_metadata=dict(metadata or {}))
            try:
                response = request()
            except Exception as exc:
                self.ledger.finish(call_id, status='failed', error_kind=type(exc).__name__)
                if not isinstance(exc, retry_on) or attempt == attempts:
                    raise
                delay = min(self.limits.retry_backoff_s * 2 ** (attempt - 1), self.remaining_seconds)
                self(role, 'call.retry', {'call_id': call_id, 'logical_call_id': logical_id,
                                         'next_attempt': attempt + 1, 'backoff_s': delay})
                time.sleep(delay)
                continue
            try:
                usage = validate_usage(usage_fn(response) if usage_fn else None)
            except Exception:
                # A bad usage adapter must not erase a completed remote request.
                self.ledger.finish(call_id, status='failed', error_kind='usage_error')
                raise
            try:
                actual_model = actual_model_fn(response) if actual_model_fn else None
                if actual_model is not None:
                    require_text(actual_model, 'actual_model')
            except Exception:
                self.ledger.finish(call_id, status='failed', usage=usage, error_kind='model_metadata_error')
                raise
            self.ledger.finish(call_id, usage=usage, actual_model=actual_model)
            self.check_limits()
            return response


def validate_agent_output(output, sources, budget):
    from evirecall.contracts import AgentOutput
    from evirecall.runner.smoke import validate_output
    if not isinstance(output, AgentOutput):
        raise ContractError('Agent must return AgentOutput')
    validate_output(output, sources, budget)
    if output.status == 'completed' and not output.prediction.strip():
        raise ContractError('Completed output must not be empty')
    if output.prediction is not None and not isinstance(output.prediction, str):
        raise ContractError('Prediction must be text or null')
    for item in output.evidence.items:
        if item.validity not in ('unreviewed', 'current', 'superseded', 'uncertain'):
            raise ContractError('Invalid evidence validity')
        if not isinstance(item.text, str) or not item.text.strip():
            raise ContractError('Evidence text must not be empty')
    # Output usage is an informational legacy field, never an accounting source.
    for usage in (output.usage, output.evidence.usage):
        for key in ('requests', 'input_tokens', 'output_tokens', 'cost_usd'):
            value = getattr(usage, key)
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
                raise ContractError(f'Invalid output usage: {key}')
