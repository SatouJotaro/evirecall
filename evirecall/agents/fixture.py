"""An offline interface check, not Smurfs or a research baseline."""

from dataclasses import asdict

from evirecall.contracts import AgentOutput, Emit, MemoryBackend, RetrievalBudget, TaskInput


class FixtureAgent:
    def run(self, task: TaskInput, memory: MemoryBackend,
            budget: RetrievalBudget, emit: Emit) -> AgentOutput:
        for event in task.events:
            if event.kind == "update":
                memory.apply_update(event)
            else:
                memory.observe(event)
            emit("fixture", "memory.observe", {"observation": asdict(event)})
        evidence = memory.retrieve(task.query, budget)
        emit("fixture", "memory.retrieve", {"query": task.query, "packet": asdict(evidence)})
        prediction = evidence.items[0].text if evidence.items else None
        output = AgentOutput(prediction, "completed" if prediction is not None else "abstained", evidence)
        emit("fixture", "agent.output", asdict(output))
        return output
