"""Technical autonomy never waives exact scope, authority, or independent verification."""
from copy import deepcopy
import json
import sys
import tempfile
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline_v2.tests import test_core
from pipeline_v2.checkout import candidate_tree_oid
from pipeline_v2.model import PipelineError, ConflictError, compact_assignment_context, current_slice, journal_digest, status_view
from pipeline_v2.technical_decisions import technical_decisions_context


class TechnicalDecisionTests(unittest.TestCase):
    def setUp(self):
        self.h = test_core.PipelineV2CoreTests()
        self.h.setUp()
        self.addCleanup(self.h.tearDown)
        if "check_order" in self._testMethodName:
            self.h.slices[0]["planned_commands"].append([self.h.command[0], "-c", "print('second check')"])
            self.h._write_approved_plan(self.h.slices)
            (self.h.root / "check-order-fixture.txt").write_text("two checks", encoding="utf-8")
            self.h._commit_fixture_and_restart("two required verification checks")
        self.h._reach_engineering("-technical")
        self.h.controller.next(command_id="NEXT-technical")

    def entry(self, decision="Use the existing editor integration"):
        return {"id": "TD-EDITOR", "situation": "Editor requires a persistent companion asset",
                "decision": decision, "basis": "Observed canonical editor save output",
                "checks": ["Inspected the exact generated asset diff"],
                "downstream": "Review and QA must verify the companion asset"}

    def packet(self, **extra):
        return {"assignment_id": self.h.store.load()["active_assignment"]["id"],
                "observed_tree_oid": candidate_tree_oid(self.h.root), "entry": self.entry(), **extra}

    def apply(self, packet, identifier="TD-APPLY", generation=None):
        return self.h.controller.technical_action(command_id=identifier,
            expected_generation=self.h.store.load()["generation"] if generation is None else generation, packet=packet)

    def observe(self):
        return self.h.controller.technical_action(command_id="TD-OBSERVE",
            expected_generation=self.h.store.load()["generation"], action="Save the existing scene in its owning editor")

    def test_known_scope_amendment_and_same_id_correction_are_current_and_replay_safe(self):
        stale_output = self.h._write_artifact({"outcome": "pass", "summary": "Written before the technical amendment"})
        state = self.apply(self.packet(additional_paths=["companion.asset"]))
        with self.assertRaises(PipelineError):
            self.h.controller.complete(command_id="STALE-ARTIFACT", expected_generation=state["generation"], artifact_path=stale_output)
        original_authority = deepcopy(state["authority"])
        self.assertIn("companion.asset", state["active_assignment"]["access"]["write"])
        (self.h.root / "companion.asset").write_text("asset", encoding="utf-8")
        packet = self.packet(entry=self.entry("Use the corrected existing integration"))
        generation = state["generation"]
        corrected = self.apply(packet, "TD-CORRECT", generation)
        self.assertEqual(1, len(corrected["technical_decisions"]))
        self.assertEqual(packet["entry"]["decision"], corrected["technical_decisions"]["TD-EDITOR"]["decision"])
        self.assertEqual(original_authority, corrected["authority"])
        self.assertEqual(corrected, self.apply(packet, "TD-CORRECT", generation))
        context = technical_decisions_context(self.h.root, self.h.feature)
        self.assertEqual(journal_digest(corrected["technical_decisions"]), context["sha256"])
        self.assertEqual(context["sha256"], corrected["active_assignment"]["capsule"]["context"]["technical_journal"]["sha256"])
        self.h._complete("COMPLETE-technical", {"outcome": "pass", "summary": "Implemented"})
        self.h._accept("engineering-technical")
        review = self.h.controller.next(command_id="NEXT-review-technical")
        self.assertIn("companion.asset", review["active_assignment"]["capsule"]["context"]["review_target"]["candidate_changes"])

    def test_unknown_editor_side_effect_requires_pre_action_controller_observation(self):
        self.observe()
        (self.h.root / "companion.asset").write_text("editor output", encoding="utf-8")
        status = self.h.controller.status()
        self.assertEqual("checkout_recovery_required", status["next_action"]["result"])
        self.assertEqual(candidate_tree_oid(self.h.root), status["technical_actions"]["observed_tree_oid"])
        before = self.h.store.path.read_bytes()
        with self.assertRaisesRegex(PipelineError, "controller observation"):
            self.apply(self.packet(additional_paths=["companion.asset"]))
        self.assertEqual(before, self.h.store.path.read_bytes())
        reconciled = self.apply(self.packet(additional_paths=["companion.asset"], observation_id="TD-OBSERVE"))
        self.assertNotIn("technical_observation", reconciled["active_assignment"])
        self.assertEqual("editor output", (self.h.root / "companion.asset").read_text())

    def test_observation_refuses_existing_foreign_user_changes_and_reconciliation_refuses_unlisted_changes(self):
        (self.h.root / "user.txt").write_text("user data", encoding="utf-8")
        before = self.h.store.path.read_bytes()
        with self.assertRaisesRegex(PipelineError, "forbidden"):
            self.observe()
        self.assertEqual(before, self.h.store.path.read_bytes())
        with self.assertRaisesRegex(PipelineError, "controller observation"):
            self.apply(self.packet(additional_paths=["user.txt"], observation_id="invented"))
        self.assertEqual("user data", (self.h.root / "user.txt").read_text())

    def test_stale_generation_tree_and_authority_or_policy_scope_fail_without_mutation(self):
        packet = self.packet()
        (self.h.root / "game.txt").write_text("new worker bytes", encoding="utf-8")
        before = self.h.store.path.read_bytes()
        with self.assertRaisesRegex(PipelineError, "observed tree is stale"):
            self.apply(packet)
        with self.assertRaises(ConflictError):
            self.apply(self.packet(), generation=0)
        for path in ["requirements.md", ".gitignore", ".agentic-pipeline/evil.json", "**"]:
            with self.subTest(path=path), self.assertRaises(PipelineError):
                self.apply(self.packet(additional_paths=[path]))
        self.assertEqual(before, self.h.store.path.read_bytes())

    def test_check_order_cannot_drop_replace_or_duplicate_mandatory_checks(self):
        before = self.h.store.path.read_bytes()
        for order in [[], [["echo", "skip"]], [self.h.command, self.h.command]]:
            with self.assertRaisesRegex(PipelineError, "mandatory check"):
                self.apply(self.packet(command_order=order))
        self.assertEqual(before, self.h.store.path.read_bytes())
        reversed_commands = list(reversed(self.h.slices[0]["planned_commands"]))
        state = self.apply(self.packet(command_order=reversed_commands))
        self.assertEqual(reversed_commands, state["active_assignment"]["commands"])
        completed = self.h._complete("COMPLETE-reordered", {"outcome": "pass", "summary": "Verified corrected check ordering"})
        self.assertEqual(reversed_commands, [item["argv"] for item in completed["artifacts"]["engineering"]["controller"]["commands"]])

    def test_blocker_is_recorded_as_unresolved_and_preserved_through_init(self):
        self.apply(self.packet(additional_paths=["companion.asset"]))
        (self.h.root / "companion.asset").write_text("preserved editor output", encoding="utf-8")
        blocked = self.h._complete("COMPLETE-block-technical", {
            "outcome": "blocked", "summary": "External prerequisite unavailable",
            "blocker": "Missing user-owned upload capability", "required_action": "Provide that capability"})
        journal = deepcopy(blocked["technical_decisions"])
        self.assertTrue(any(item["decision"].startswith("Unresolved:") for item in journal.values()))
        action = self.h.controller.status()["next_action"]
        self.assertEqual("init", action["command"])
        self.assertTrue(action["user_input_required"])
        self.h.controller.reconfigure({"name": "init", "id": action["command_id"],
            "expected_generation": action["expected_generation"], "run_id": action["run_id"],
            "feature": self.h.feature, "workflow_path": self.h.workflow_path, "project_root": str(self.h.root),
            "authority_paths": action["authority"], "slices": action["slices"]})
        self.assertEqual(journal, self.h.store.load()["technical_decisions"])
        self.h._reach_engineering("-technical-resumed")
        issued = self.h.controller.next(command_id="NEXT-resumed-overlay")
        self.assertIn("companion.asset", issued["active_assignment"]["access"]["write"])
        self.assertEqual("preserved editor output", (self.h.root / "companion.asset").read_text())

    def test_worker_blocker_entry_does_not_create_duplicate_unresolved_fallback(self):
        blocked = self.h._complete("COMPLETE-worker-block", {
            "outcome": "blocked", "summary": "External prerequisite unavailable",
            "blocker": "Missing upload capability", "required_action": "Provide capability",
            "technical_decisions": [self.entry("Unresolved: provide capability")]})
        self.assertEqual(["TD-EDITOR"], list(blocked["technical_decisions"]))

    def test_same_id_rebinds_fresh_authority_without_inheriting_old_execution(self):
        self.apply(self.packet(additional_paths=["old-companion.asset"]))
        plan = self.h.root / "plan.md"
        plan.write_text(plan.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        action = self.h.controller.status()["next_action"]
        self.h.controller.reconfigure({"name": "init", "id": action["command_id"],
            "expected_generation": action["expected_generation"], "run_id": action["run_id"],
            "feature": self.h.feature, "workflow_path": self.h.workflow_path, "project_root": str(self.h.root),
            "authority_paths": action["authority"], "slices": action["slices"]})
        self.h._reach_engineering("-fresh-technical-authority")
        self.h.controller.next(command_id="NEXT-fresh-technical-authority")
        refreshed = self.apply(self.packet(additional_paths=["new-companion.asset"]), "TD-FRESH-BINDING")
        self.assertEqual(["TD-EDITOR"], list(refreshed["technical_decisions"]))
        self.assertIn("new-companion.asset", refreshed["active_assignment"]["access"]["write"])
        self.assertNotIn("old-companion.asset", refreshed["active_assignment"]["access"]["write"])
        self.assertEqual(refreshed["authority"]["digest"], refreshed["technical_decisions"]["TD-EDITOR"]["execution"]["authority"])

    def test_qa_journal_update_rechecks_review_instead_of_reusing_stale_credit(self):
        self.h._complete("COMPLETE-eng-freshness", {"outcome": "pass", "summary": "Implemented"})
        self.h._accept("engineering-freshness")
        self.h._review_pass("review-freshness")
        self.h._complete_readonly("qa", "qa-freshness", {"outcome": "pass", "checks": self.h._qa_checks("Observed real acceptance"), "technical_decisions": [self.entry()]})
        resumed = self.h._accept("qa-freshness")
        self.assertEqual("review", resumed["phase"])
        self.assertNotIn("review", resumed["artifacts"])
        self.h._review_pass("review-refreshed")
        self.h._accept("qa-refreshed")  # QA already checked this journal revision; only Review was stale.
        self.h._complete_readonly("docs", "docs-journal-update", {"outcome": "pass", "summary": "Documented verified correction", "technical_decisions": [self.entry("Document the verified existing integration")]})
        after_docs = self.h._accept("docs-journal-update")
        self.assertEqual("review", after_docs["phase"])
        self.h._review_pass("review-after-docs-journal")
        self.h._qa_pass("qa-after-docs-journal")
        self.h._accept("docs-refreshed")
        ready = self.h.controller.ready(command_id="READY-refreshed", expected_generation=self.h.store.load()["generation"])
        self.assertTrue(status_view(ready)["ready"])


    def test_review_decision_correction_requires_fresh_qa_context(self):
        self.h._complete("COMPLETE-eng-journal", {"outcome": "pass", "summary": "Implemented", "technical_decisions": [self.entry()]})
        self.h._accept("engineering-journal")
        reviewed = self.h._complete_readonly("review", "review-journal", {"outcome": "pass", "findings": [], "technical_decisions": [self.entry("Verified the corrected existing integration")]})
        self.h._accept("review-journal")
        qa = self.h.controller.next(command_id="NEXT-qa-journal")
        self.assertEqual(journal_digest(reviewed["technical_decisions"]), qa["active_assignment"]["capsule"]["context"]["technical_journal"]["sha256"])


class JournalReadBoundaryTests(unittest.TestCase):
    def test_bounded_capsule_explicitly_requires_full_current_retrieval_when_an_entry_is_omitted(self):
        entries = {f"TD-{i}": {"id": f"TD-{i}", "decision": str(i)} for i in range(5)}
        entries["TD-0"]["decision"] = "Corrected earlier entry relevant to this slice"
        context = compact_assignment_context({"technical_decisions": list(entries.values()),
            "technical_journal": {"path": "current.json#technical_decisions", "sha256": journal_digest(entries), "count": 5}}, None)
        self.assertEqual(4, len(context["technical_decisions"]))
        self.assertEqual(1, context["technical_journal"]["omitted_entry_count"])
        self.assertTrue(context["technical_journal"]["requires_current_journal_read"])
        self.assertEqual(context, compact_assignment_context(context, None))

    def test_upstream_loader_rejects_missing_empty_and_relative_project_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            state_path = root / ".agentic-pipeline/Workflows/test-feature/pipeline-state.json"
            state_path.parent.mkdir(parents=True)
            for stored_root in (None, "", ".", "relative/path"):
                state = {"feature": "test-feature", "workflow_path": ".agentic-pipeline/Workflows/test-feature", "technical_decisions": {}}
                if stored_root is not None:
                    state["project_root"] = stored_root
                state_path.write_text(json.dumps(state), encoding="utf-8")
                with self.subTest(root=stored_root), self.assertRaisesRegex(ValueError, "explicit absolute"):
                    technical_decisions_context(root, "test-feature")

if __name__ == "__main__":
    unittest.main()
