from dataclasses import asdict, replace
import json
from pathlib import Path
import tempfile
import unittest

from evirecall.agents.fixture import FixtureAgent
from evirecall.contracts import (
    AgentOutput, ContractError, EvidenceItem, EvidencePacket, MemoryScope,
    Observation, RetrievalBudget, TaskInput,
)
from evirecall.evaluation.fixtures import FixtureExpectation, load_expectations
from evirecall.memory.fixture import FixtureMemory
from evirecall.runner.smoke import ROOT, run_config, run_tasks
from evirecall.tasks.loading import load_tasks


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name) / "run"
        self.tasks = load_tasks(ROOT / "fixtures/public/tasks.jsonl")
        self.labels = load_expectations(ROOT / "fixtures/evaluator/expectations.jsonl")

    def test_three_cases_complete_with_trace_and_no_provider_usage(self):
        _, summary = run_config(ROOT / "configs/smoke.json", self.output)
        self.assertEqual(summary["fixture_checks_passed"], 3)
        self.assertEqual(summary["terminal_statuses"], {"completed": 2, "abstained": 1, "failed": 0})
        self.assertIsNone(summary["provider_usage"])
        trace = [json.loads(line) for line in (self.output / "trace.jsonl").read_text().splitlines()]
        self.assertEqual([item["step"] for item in trace], list(range(1, len(trace) + 1)))
        self.assertEqual(sum(item["operation"] == "task.finished" for item in trace), 3)
        self.assertNotIn("expected_prediction", json.dumps(trace))
        manifest = json.loads((self.output / "manifest.json").read_text())
        self.assertEqual(len(manifest["inputs"]["tasks_sha256"]), 64)

    def test_gold_fields_are_rejected_at_both_input_levels(self):
        raw = json.loads((ROOT / "fixtures/public/tasks.jsonl").read_text().splitlines()[0])
        for field in ("answer", "has_answer", "answer_session_ids", "explanation"):
            with self.subTest(field=field):
                with self.assertRaises(ContractError):
                    TaskInput.from_dict({**raw, field: "evaluator-only"})
        raw["events"][0]["gold_answer"] = "evaluator-only"
        with self.assertRaises(ContractError):
            TaskInput.from_dict(raw)

    def test_memory_source_ids_are_immutable(self):
        memory = FixtureMemory()
        memory.reset(MemoryScope("run", "condition", "data", "group"))
        event = self.tasks[0].events[0]
        memory.observe(event)
        memory.observe(event)  # An identical observation is idempotent.
        with self.assertRaises(ContractError):
            memory.observe(replace(event, text="A conflicting record with the same ID"))

    def test_retrieval_respects_character_and_item_budgets(self):
        memory = FixtureMemory()
        memory.reset(MemoryScope("run", "condition", "data", "group"))
        for event in self.tasks[1].events:
            memory.observe(event)
        self.assertEqual(len(memory.retrieve("budget", RetrievalBudget(1, 2000)).items), 1)
        self.assertEqual(memory.retrieve("budget", RetrievalBudget(2, 1)).items, ())
        with self.assertRaises(ContractError):
            RetrievalBudget(max_items=-1)

    def test_history_survives_within_group_but_not_across_dataset_or_group(self):
        first = self.tasks[0]
        followup = replace(first, task_id="followup", session_id="session-2", events=())
        other_dataset = replace(followup, task_id="other-dataset", dataset="another")
        other_group = replace(followup, task_id="other-group", group_id="another")
        labels = {
            first.task_id: self.labels[first.task_id],
            "followup": FixtureExpectation("followup", "completed", first.events[0].text, ("recall-001",)),
            "other-dataset": FixtureExpectation("other-dataset", "abstained", None, ()),
            "other-group": FixtureExpectation("other-group", "abstained", None, ()),
        }
        summary = run_tasks([first, followup, other_dataset, other_group], labels, self.output)
        self.assertEqual(summary["fixture_checks_passed"], 4)

    def test_agent_receives_public_contract_only(self):
        fields_seen = []

        class SpyAgent(FixtureAgent):
            def run(self, task, memory, budget, emit):
                fields_seen.append(set(asdict(task)))
                return super().run(task, memory, budget, emit)

        run_tasks(self.tasks, self.labels, self.output, agent_factory=SpyAgent)
        public_fields = {"dataset", "task_id", "group_id", "session_id", "query", "events", "tools", "query_time"}
        self.assertTrue(all(fields == public_fields for fields in fields_seen))

    def test_failed_runs_remain_in_denominator_and_trace(self):
        class BrokenAgent:
            def run(self, task, memory, budget, emit):
                raise RuntimeError("intentional fixture failure")

        summary = run_tasks(self.tasks, self.labels, self.output, agent_factory=BrokenAgent)
        self.assertEqual(summary["episodes"], 3)
        self.assertEqual(summary["terminal_statuses"]["failed"], 3)
        self.assertEqual(summary["fixture_checks_total"], 3)
        self.assertEqual(summary["fixture_checks_passed"], 0)
        results = [json.loads(x) for x in (self.output / "results.jsonl").read_text().splitlines()]
        self.assertTrue(all(x["error"] and x["usage"]["cost_usd"] is None for x in results))

    def test_unknown_citation_from_backend_is_a_failed_episode(self):
        class InvalidEvidence:
            def run(self, task, memory, budget, emit):
                item = EvidenceItem("invented", "unsupported", ("unseen",), "agent", "2026-10-28T00:00:00Z")
                return AgentOutput("unsupported", "completed", EvidencePacket((item,), "invalid"))

        summary = run_tasks(self.tasks, self.labels, self.output, agent_factory=InvalidEvidence)
        self.assertEqual(summary["terminal_statuses"]["failed"], 3)

    def test_backend_cannot_exceed_budget(self):
        class OversizedEvidence:
            def run(self, task, memory, budget, emit):
                event = task.events[0]
                item = EvidenceItem(event.source_id, event.text, (event.source_id,), "user", event.timestamp)
                return AgentOutput(event.text, "completed", EvidencePacket((item,), "oversized"))

        first = self.tasks[0]
        summary = run_tasks([first], {first.task_id: self.labels[first.task_id]}, self.output,
                            agent_factory=OversizedEvidence, budget=RetrievalBudget(1, 1))
        self.assertEqual(summary["terminal_statuses"]["failed"], 1)

    def test_existing_run_directory_is_never_overwritten(self):
        self.output.mkdir()
        sentinel = self.output / "keep.txt"
        sentinel.write_text("keep")
        with self.assertRaises(FileExistsError):
            run_tasks(self.tasks, self.labels, self.output)
        self.assertEqual(sentinel.read_text(), "keep")

    def test_missing_evaluator_labels_fail_before_execution(self):
        with self.assertRaises(ContractError):
            run_tasks(self.tasks, {}, self.output)
        self.assertFalse(self.output.exists())

    def test_live_backend_never_silently_uses_fixture(self):
        config = json.loads((ROOT / "configs/smoke.json").read_text())
        config["backend"] = "jev"
        path = Path(self.temporary.name) / "config.json"
        path.write_text(json.dumps(config))
        with self.assertRaises(ContractError):
            run_config(path, self.output)


if __name__ == "__main__":
    unittest.main()
