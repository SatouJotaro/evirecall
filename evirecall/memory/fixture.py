"""Deterministic wiring stub; no semantic retrieval, summarization, or invalidation."""

from evirecall.contracts import (
    ContractError, EvidenceItem, EvidencePacket, MemoryScope, Observation, RetrievalBudget,
)


class FixtureMemory:
    def __init__(self) -> None:
        self.scope: MemoryScope | None = None
        self.records: dict[str, Observation] = {}

    def reset(self, scope: MemoryScope) -> None:
        self.scope = scope
        self.records.clear()

    def observe(self, event: Observation) -> None:
        if self.scope is None:
            raise ContractError("Memory scope must be initialized")
        previous = self.records.get(event.source_id)
        if previous is not None and previous != event:
            raise ContractError("An immutable source ID cannot be overwritten")
        self.records[event.source_id] = event

    def apply_update(self, event: Observation) -> None:
        # The fixture only appends observations. Real validity handling belongs to WP1.
        self.observe(event)

    def summarize(self, source_ids: tuple[str, ...]) -> str:
        raise NotImplementedError("Summarization belongs to the live memory adapter")

    def retrieve(self, query: str, budget: RetrievalBudget) -> EvidencePacket:
        items: list[EvidenceItem] = []
        used = 0
        for event in reversed(list(self.records.values())):
            if not event.text.strip():
                continue
            if len(items) == budget.max_items:
                break
            if used + len(event.text) > budget.max_characters:
                continue
            items.append(EvidenceItem(event.source_id, event.text, (event.source_id,),
                                      event.writer_role, event.timestamp,
                                      source_time_raw=event.source_time_raw))
            used += len(event.text)
        return EvidencePacket(tuple(items), route="fixture-recent-observations")
