"""Public task loading. Evaluator answers are rejected instead of passed through."""

import json
from pathlib import Path

from evirecall.contracts import ContractError, TaskInput


def load_tasks(path: Path) -> list[TaskInput]:
    tasks = [TaskInput.from_dict(json.loads(line))
             for line in path.read_text(encoding="utf-8").split('\n') if line.strip()]
    if not tasks or len({task.task_id for task in tasks}) != len(tasks):
        raise ContractError("Task IDs must be unique and the task set must be non-empty")
    return tasks
