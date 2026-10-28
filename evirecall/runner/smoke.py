"""Sequential offline integration check with scope isolation and inspectable artifacts."""

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
from time import perf_counter
from typing import Callable
from uuid import uuid4

from evirecall.agents.fixture import FixtureAgent
from evirecall.contracts import (
    AgentBackend, AgentOutput, ContractError, EpisodeResult, EvidencePacket,
    MemoryBackend, MemoryScope, Observation, RetrievalBudget, SCHEMA_VERSION,
    TaskInput, TraceEvent, Usage, check_fields,
)
from evirecall.evaluation.fixtures import FixtureExpectation, load_expectations, score_fixture
from evirecall.memory.fixture import FixtureMemory
from evirecall.tasks.loading import load_tasks

ROOT = Path(__file__).resolve().parents[2]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def git_state() -> dict:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                                capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, check=True,
                               capture_output=True, text=True).stdout != ""
        return {"commit": commit, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


def validate_output(output: AgentOutput, records: dict[str, Observation], budget: RetrievalBudget) -> None:
    if output.status not in ("completed", "abstained", "failed"):
        raise ContractError("Unknown terminal status")
    if output.status == "completed" and not isinstance(output.prediction, str):
        raise ContractError("Completed output must have a prediction")
    if len(output.evidence.items) > budget.max_items:
        raise ContractError("Adapter exceeded evidence item budget")
    if sum(len(item.text) for item in output.evidence.items) > budget.max_characters:
        raise ContractError("Adapter exceeded evidence character budget")
    for item in output.evidence.items:
        if not item.source_ids or any(source not in records for source in item.source_ids):
            raise ContractError("Evidence refers to an unavailable source in this task group")


def run_tasks(
    tasks: list[TaskInput], expectations: dict[str, FixtureExpectation], output_dir: Path,
    *, condition: str = "fixture", budget: RetrievalBudget = RetrievalBudget(),
    agent_factory: Callable[[], AgentBackend] = FixtureAgent,
    memory_factory: Callable[[], MemoryBackend] = FixtureMemory,
    provenance: dict | None = None,
) -> dict:
    if not tasks or len({task.task_id for task in tasks}) != len(tasks):
        raise ContractError("Expected non-empty tasks with unique IDs")
    if {task.task_id for task in tasks} != set(expectations):
        raise ContractError("Evaluator and public task IDs must match exactly")
    output_dir.mkdir(parents=True, exist_ok=False)
    run_id = uuid4().hex
    write_json(output_dir / "manifest.json", {
        "schema_version": SCHEMA_VERSION, "run_id": run_id, "mode": "smoke",
        "condition": condition, "created_at": now(), "python": platform.python_version(),
        "code": git_state(), "budget": asdict(budget), "inputs": provenance or {},
        "task_ids": [task.task_id for task in tasks],
        "notice": "Synthetic fixtures and deterministic stubs; not a Smurfs/Jev experiment.",
    })
    memories: dict[tuple[str, str], MemoryBackend] = {}
    sources: dict[tuple[str, str], dict[str, Observation]] = {}
    results, scores = [], []
    step = 0
    started = perf_counter()
    with (output_dir / "trace.jsonl").open("w", encoding="utf-8") as trace:
        for task in tasks:
            task_started = perf_counter()

            def emit(role: str, operation: str, payload: dict) -> None:
                nonlocal step
                step += 1
                event = TraceEvent(SCHEMA_VERSION, run_id, condition, task.dataset,
                                   task.task_id, task.group_id, task.session_id, step, now(),
                                   role, operation, payload)
                trace.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")

            emit("runner", "task.started", {"query": task.query, "budget": asdict(budget)})
            error = None
            try:
                key = task.group_key
                if key not in memories:
                    memory = memory_factory()
                    memory.reset(MemoryScope(run_id, condition, *key))
                    memories[key] = memory
                    sources[key] = {}
                for observation in task.events:
                    previous = sources[key].get(observation.source_id)
                    if previous is not None and previous != observation:
                        raise ContractError("An immutable source ID cannot be overwritten")
                    sources[key][observation.source_id] = observation
                # No expectation, gold answer, or scoring state reaches the agent API.
                output = agent_factory().run(task, memories[key], budget, emit)
                validate_output(output, sources[key], budget)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                output = AgentOutput(None, "failed", EvidencePacket((), "failed"), Usage())
            result = EpisodeResult(task.task_id, task.dataset, task.group_id, task.session_id,
                                   output.status, output.prediction, output.evidence, output.usage,
                                   round((perf_counter() - task_started) * 1000, 3),
                                   "trace.jsonl", error)
            emit("runner", "task.finished", result.to_dict())
            results.append(result)
            scores.append(score_fixture(result, expectations[task.task_id]))
    for filename, values in (("results.jsonl", [result.to_dict() for result in results]),
                             ("scores.jsonl", scores)):
        (output_dir / filename).write_text(
            "".join(json.dumps(value, ensure_ascii=False) + "\n" for value in values), encoding="utf-8")
    statuses = Counter(result.status for result in results)
    summary = {
        "mode": "smoke", "run_id": run_id, "condition": condition, "episodes": len(results),
        "terminal_statuses": {key: statuses[key] for key in ("completed", "abstained", "failed")},
        "fixture_checks_passed": sum(score["passed"] for score in scores),
        "fixture_checks_total": len(scores),
        "runner_wall_ms": round((perf_counter() - started) * 1000, 3),
        "provider_usage": None,
        "notice": "Checks wiring only. No model calls, benchmark accuracy, or measured provider costs.",
    }
    write_json(output_dir / "summary.json", summary)
    return summary


def run_config(config_path: Path, output_dir: Path | None = None) -> tuple[Path, dict]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    check_fields(config, {"mode", "backend", "condition", "tasks", "expectations", "budget"})
    if config["mode"] != "smoke" or config["backend"] != "fixture":
        raise ContractError("Only the explicit fixture backend is implemented; live adapters are pending")
    check_fields(config["budget"], {"max_items", "max_characters"})
    budget = RetrievalBudget(**config["budget"])
    # Fixture paths are relative to the config, independent of the caller's cwd.
    task_path = (config_path.parent / config["tasks"]).resolve()
    label_path = (config_path.parent / config["expectations"]).resolve()
    tasks = load_tasks(task_path)
    expectations = load_expectations(label_path)
    provenance = {
        "config": config,
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "tasks_sha256": hashlib.sha256(task_path.read_bytes()).hexdigest(),
        "expectations_sha256": hashlib.sha256(label_path.read_bytes()).hexdigest(),
    }
    directory = output_dir or ROOT / "runs" / ("setup-" + uuid4().hex[:12])
    return directory, run_tasks(tasks, expectations, directory,
                                condition=config["condition"], budget=budget, provenance=provenance)
