"""Shared contracts, jointly reviewed by all three owners. No evaluator labels here."""

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Callable, Literal, Protocol

SCHEMA_VERSION = 1
Status = Literal["completed", "abstained", "failed"]


class ContractError(ValueError):
    """An input or adapter output violates the shared interface."""


def check_fields(value: dict, required: set[str], optional: set[str] | None = None) -> None:
    if not isinstance(value, dict):
        raise ContractError("Expected a JSON object")
    missing = required - value.keys()
    extra = value.keys() - required - (optional or set())
    if missing or extra:
        raise ContractError(f"Missing fields: {sorted(missing)}; unexpected fields: {sorted(extra)}")


def require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be a non-empty string")
    return value


@dataclass(frozen=True)
class Observation:
    source_id: str
    text: str
    writer_role: str
    timestamp: str
    kind: Literal["observation", "update"] = "observation"

    def __post_init__(self) -> None:
        for field in ("source_id", "text", "writer_role", "timestamp"):
            require_text(getattr(self, field), field)
        if self.kind not in ("observation", "update"):
            raise ContractError("Unknown observation kind")
        try:
            time = datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ContractError("timestamp must be ISO 8601") from exc
        if time.utcoffset() is None:
            raise ContractError("timestamp must include a timezone")

    @classmethod
    def from_dict(cls, value: dict) -> "Observation":
        check_fields(value, {"source_id", "text", "writer_role", "timestamp"}, {"kind"})
        return cls(**value)


@dataclass(frozen=True)
class TaskInput:
    dataset: str
    task_id: str
    group_id: str
    session_id: str
    query: str
    events: tuple[Observation, ...]
    tools: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field in ("dataset", "task_id", "group_id", "session_id", "query"):
            require_text(getattr(self, field), field)
        if len({event.source_id for event in self.events}) != len(self.events):
            raise ContractError("Duplicate source ID within one task")
        for tool in self.tools:
            require_text(tool, "tool")

    @property
    def group_key(self) -> tuple[str, str]:
        return self.dataset, self.group_id

    @classmethod
    def from_dict(cls, value: dict) -> "TaskInput":
        check_fields(value, {"dataset", "task_id", "group_id", "session_id", "query", "events"}, {"tools"})
        if not isinstance(value["events"], list) or not isinstance(value.get("tools", []), list):
            raise ContractError("events and tools must be arrays")
        fields = dict(value)
        fields["events"] = tuple(Observation.from_dict(event) for event in value["events"])
        fields["tools"] = tuple(value.get("tools", []))
        return cls(**fields)


@dataclass(frozen=True)
class MemoryScope:
    run_id: str
    condition: str
    dataset: str
    group_id: str


@dataclass(frozen=True)
class RetrievalBudget:
    max_items: int = 2
    max_characters: int = 2000

    def __post_init__(self) -> None:
        for value in (self.max_items, self.max_characters):
            if type(value) is not int or value <= 0:
                raise ContractError("Retrieval budgets must be positive integers")


@dataclass(frozen=True)
class Usage:
    requests: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    provider: str | None = None
    model: str | None = None


@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: str
    text: str
    source_ids: tuple[str, ...]
    writer_role: str
    event_time: str
    validity: Literal["unreviewed", "current", "superseded", "uncertain"] = "unreviewed"


@dataclass(frozen=True)
class EvidencePacket:
    items: tuple[EvidenceItem, ...]
    route: str
    usage: Usage = Usage()


@dataclass(frozen=True)
class AgentOutput:
    prediction: str | None
    status: Status
    evidence: EvidencePacket
    usage: Usage = Usage()


@dataclass(frozen=True)
class TraceEvent:
    schema_version: int
    run_id: str
    condition: str
    dataset: str
    task_id: str
    group_id: str
    session_id: str
    step: int
    timestamp: str
    role: str
    operation: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class EpisodeResult:
    task_id: str
    dataset: str
    group_id: str
    session_id: str
    status: Status
    prediction: str | None
    evidence: EvidencePacket
    usage: Usage
    elapsed_ms: float
    trace_file: str
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


Emit = Callable[[str, str, dict[str, Any]], None]


class MemoryBackend(Protocol):
    def reset(self, scope: MemoryScope) -> None: ...
    def observe(self, event: Observation) -> None: ...
    def apply_update(self, event: Observation) -> None: ...
    def summarize(self, source_ids: tuple[str, ...]) -> str: ...
    def retrieve(self, query: str, budget: RetrievalBudget) -> EvidencePacket: ...


class AgentBackend(Protocol):
    def run(self, task: TaskInput, memory: MemoryBackend,
            budget: RetrievalBudget, emit: Emit) -> AgentOutput: ...
