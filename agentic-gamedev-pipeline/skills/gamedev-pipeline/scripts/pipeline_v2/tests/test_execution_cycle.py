from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[2]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from pipeline_v2.tests import test_core as fixtures
from pipeline_v2.execution import seal_verification, metadata, receipt_binding, finding_updates
from pipeline_v2.reducer import _worker_artifact, _runtime_rebind_can_confirm
from pipeline_v2.model import PipelineError, current_candidate, digest, status_view, passing_artifact
from pipeline_v2.process_tree import ProcessEvidence
from pipeline_v2.technical_decisions import semantic_journal_digest


class ExecutionCycleTests(unittest.TestCase):
    def setUp(self):
        self.h = fixtures.PipelineV2CoreTests()
        self.h.setUp()

    def tearDown(self):
        self.h.tearDown()

    def manifest(self, *, confirm=False, pure=None):
        return {"version": 1, "slices": {
            item["id"]: [{"id": f"check-{index}", "argv": argv, "kind": "deterministic",
                           "timeout_seconds": 20, "independent": False, "input_paths": []}
                          for index, argv in enumerate(item["planned_commands"])] for item in self.h.slices},
            "pure_documentation_paths": pure or [], "confirm_approved_plan": confirm}

    def restart(self, manifest):
        h = self.h
        h.store.path.unlink()
        return h.controller.reconfigure({"name": "init", "id": "INITIAL-RECIPES", "expected_generation": None,
            "run_id": "RUN-RECIPES", "feature": h.feature, "workflow_path": h.workflow_path,
            "project_root": str(h.root), "authority_paths": {"requirements": "requirements.md",
             "specification": "specification.md", "plan": "plan.md"}, "slices": h.slices, "verification": manifest})

    def issue(self):
        action = self.h.controller.status()["next_action"]
        return self.h.controller.next(command_id=action["command_id"], expected_generation=action["expected_generation"])

    def action(self, name, identity, **payload):
        state = self.h.store.load()
        return self.h.controller.control_action(name, command_id=identity, expected_generation=state["generation"], **payload)

    @staticmethod
    def passing():
        return ProcessEvidence(0, digest("stdout"), digest("stderr"))

    def test_approved_noop_and_active_check_receipt_reused_without_phase_credit(self):
        state = self.restart(self.manifest(confirm=True))
        self.assertEqual("engineering", state["phase"])
        issued = self.issue()
        active = issued["active_assignment"]
        with mock.patch("pipeline_v2.runner.run_process_tree", return_value=self.passing()) as process:
            checked = self.action("check", "CHECK-ACTIVE", assignment_id=active["id"], quiescence="Writer stopped at this checkpoint.", collect_independent=False)
            self.assertEqual(active["id"], checked["active_assignment"]["id"])
            self.assertIsNone(current_candidate(checked))
            self.assertFalse(checked["active_assignment"]["capsule"]["context"]["diagnostic_checks"]["grants_semantic_credit"])
            self.h._complete("COMPLETE-CHECKED", {"outcome": "pass", "summary": "Implemented assigned behavior."})
            self.assertEqual(1, process.call_count)
            self.h._accept("checked")
            self.h._review_pass("independent-review")
            self.h._qa_pass("actual-qa")
            self.assertEqual(1, process.call_count)

    def test_same_assignment_checks_accept_new_caller_ids_after_failed_candidate_correction(self):
        from pipeline_v2.cli import parser, run
        from pipeline_v2.delivery import export_assignment

        self.restart(self.manifest(confirm=True))
        issued = self.issue()
        active = issued["active_assignment"]
        original_tree = fixtures.candidate_tree_oid(self.h.root)
        original_assignment = (active["id"], active["worker_id"], active["output_path"])
        generation = issued["generation"]
        prefix = ["--root", str(self.h.root), "--feature", self.h.feature]
        # These IDs are chosen by the caller, not obtained from next_action or
        # the sealed recipe. Only the real process result is stubbed.
        identities = ("WORKER-CHECK-BEFORE-CORRECTION", "WORKER-CHECK-AFTER-CORRECTION")
        results = (ProcessEvidence(1, digest("first stdout"), digest("assertion failed")), self.passing())
        with mock.patch("pipeline_v2.runner.run_process_tree", side_effect=results) as process:
            for index, command_id in enumerate(identities):
                action = self.h.controller.status()["next_action"]
                self.assertEqual("complete", action["command"])
                self.assertNotEqual(command_id, action["command_id"])
                checked = run(parser().parse_args(prefix + [
                    "check", "--id", command_id, "--expected-generation", str(generation),
                    "--assignment-id", active["id"], "--quiescence", "Owned writes and sessions paused.",
                ]))
                generation = checked["generation"]  # Consume the returned CAS; do not calculate it.
                delivery = export_assignment(self.h.root, self.h.controller.status())
                packet = json.loads((self.h.root / delivery["path"]).read_bytes())
                current = packet["assignment"]
                self.assertEqual(original_assignment, (current["id"], current["worker_id"], current["output_path"]))
                diagnostic = current["context"]["diagnostic_checks"]
                self.assertEqual([1 if index == 0 else 0], [row["returncode"] for row in diagnostic["results"]])
                self.assertEqual(["check-0"], [row["check_id"] for row in diagnostic["results"]])
                self.assertEqual(fixtures.candidate_tree_oid(self.h.root), diagnostic["candidate_tree_oid"])
                self.assertFalse(diagnostic["grants_semantic_credit"])
                state = self.h.store.load()
                self.assertEqual("engineering", state["phase"])
                self.assertIsNone(current_candidate(state))
                self.assertNotIn("engineering", state["artifacts"])
                self.assertFalse((self.h.root / current["output_path"]).exists())
                self.assertEqual("complete", checked["next_action"]["command"])
                self.assertEqual(index + 1, process.call_count)
                if index == 0:
                    (self.h.root / "game.txt").write_text("Corrected in-scope candidate after failed assertion\n", encoding="utf-8")
                    self.assertNotEqual(original_tree, fixtures.candidate_tree_oid(self.h.root))
            commands = [row["id"] for row in state["history"] if row["command"] == "check"]
            self.assertEqual(list(identities), commands)

    def rebind_command(self, **extra):
        action = self.h.controller.status()["next_action"]
        self.assertEqual("init", action["command"])
        return {**self.h._baseline_init_command(action), **extra}

    def test_approved_idle_runtime_rebind_confirms_exact_plan_and_native_replay(self):
        h = self.h
        self.restart(self.manifest(confirm=True))
        self.issue()
        (h.root / "game.txt").write_text("Retained implementation\n", encoding="utf-8")
        decision = {"id": "TD-REBIND", "situation": "Retain the implemented integration contract.",
                    "decision": "Use the existing project interface.", "basis": "Approved authority.",
                    "checks": ["Current interface inspected."], "downstream": "Review the retained implementation."}
        h._complete("BEFORE-APPROVED-REBIND", {"outcome": "pass", "summary": "Retained implementation completed.",
                                                "technical_decisions": [decision]})
        before = h.store.load()
        with mock.patch("pipeline_v2.runner.pipeline_runtime_digest", return_value=digest("approved-rebind-runtime")):
            command = self.rebind_command()
            result = h.controller.reconfigure(command)
            self.assertEqual("engineering", result["phase"])
            self.assertEqual(before["generation"] + 3, result["generation"])
            self.assertEqual(before["history"], result["history"][:len(before["history"])])
            self.assertEqual(["init", "confirm-approved", "confirm-approved"],
                             [item["command"] for item in result["history"][-3:]])
            self.assertEqual(before["artifacts"]["engineering"]["candidate"], result["history"][-3]["prior"]["candidate"])
            self.assertEqual(before["authority"], result["authority"])
            self.assertEqual(before["slices"], result["slices"])
            self.assertEqual(before["technical_decisions"], result["technical_decisions"])
            self.assertIsNone(current_candidate(result))
            self.assertFalse(status_view(result)["ready"])
            for phase in ("plan", "slice"):
                self.assertIsNotNone(passing_artifact(result, phase))
                self.assertEqual("controller", result["history"][-2 if phase == "plan" else -1]["actor_id"])
            for phase in ("engineering", "review", "qa", "ready"):
                self.assertIsNone(passing_artifact(result, phase))
            saved = h.store.path.read_bytes()
            self.assertEqual(result, h.controller.reconfigure(command))
            self.assertEqual(saved, h.store.path.read_bytes())
            (h.root / "game.txt").write_text("Late replay drift\n", encoding="utf-8")
            with self.assertRaisesRegex(PipelineError, "drifted"):
                h.controller.reconfigure(command)
            self.assertEqual(saved, h.store.path.read_bytes())
            (h.root / "game.txt").write_text("Retained implementation\n", encoding="utf-8")
            self.issue()
            issued = h.store.path.read_bytes()
            h.controller.reconfigure(command)
            self.assertEqual(issued, h.store.path.read_bytes())
            h._complete("ENGINEER-AFTER-REBIND", {"outcome": "pass", "summary": "Retained implementation checked in the new runtime."})
            h._accept("after-approved-rebind")
            reviewer = self.issue()["active_assignment"]
            self.assertEqual("review", reviewer["phase"])
            self.assertIn("game.txt", reviewer["capsule"]["context"]["review_target"]["candidate_changes"])
            self.assertEqual("Retained implementation\n", (h.root / "game.txt").read_text())

    def test_runtime_rebind_disabled_confirmation_and_prior_reset_can_resume(self):
        h = self.h
        self.restart(self.manifest(confirm=True))
        with mock.patch("pipeline_v2.runner.pipeline_runtime_digest", return_value=digest("disabled-rebind")):
            before = h.store.load()
            result = h.controller.reconfigure(self.rebind_command(verification=self.manifest(confirm=False)))
            self.assertEqual("plan", result["phase"])
            self.assertEqual(before["generation"] + 1, result["generation"])
        # A controller-only reset with identical approval/scope is recoverable;
        # no upstream worker was dispatched and no semantic work was invented.
        with mock.patch("pipeline_v2.runner.pipeline_runtime_digest", return_value=digest("enabled-rebind")):
            command = self.rebind_command(verification=self.manifest(confirm=True))
            result = h.controller.reconfigure(command)
            self.assertEqual("engineering", result["phase"])
            self.assertEqual(result, h.controller.reconfigure(command))

    def test_runtime_rebind_changed_authority_or_scope_still_requires_plan(self):
        h = self.h
        self.restart(self.manifest(confirm=True))
        h._write_approved_plan(h.slices, revision=2)
        with mock.patch("pipeline_v2.runner.pipeline_runtime_digest", return_value=digest("authority-change")):
            result = h.controller.reconfigure(self.rebind_command())
            self.assertEqual("plan", result["phase"])
        # Later runtime-only rebinding cannot conceal the unresolved replan.
        for revision in ("unresolved-replan-one", "unresolved-replan-two"):
            with mock.patch("pipeline_v2.runner.pipeline_runtime_digest", return_value=digest(revision)):
                self.assertEqual("plan", h.controller.reconfigure(self.rebind_command())["phase"])
        h.slices[0]["allowed_paths"] = ["replacement.txt"]
        h._write_approved_plan(h.slices, revision=3)
        with mock.patch("pipeline_v2.runner.pipeline_runtime_digest", return_value=digest("scope-change")):
            result = h.controller.reconfigure(self.rebind_command())
            self.assertEqual("plan", result["phase"])
            self.assertEqual(["replacement.txt"], result["slices"][0]["allowed_paths"])

    def test_runtime_rebind_rejects_unapproved_authority_active_work_and_drift(self):
        h = self.h
        self.restart(self.manifest(confirm=True))
        before = h.store.path.read_bytes()
        with mock.patch("pipeline_v2.runner.pipeline_runtime_digest", return_value=digest("guarded-rebind")):
            command = self.rebind_command()
            (h.root / "game.txt").write_text("Unattributed drift\n", encoding="utf-8")
            with self.assertRaisesRegex(PipelineError, "drifted"):
                h.controller.reconfigure(command)
            (h.root / "game.txt").write_text("old\n", encoding="utf-8")
            plan = h.root / "plan.md"
            approved = plan.read_bytes()
            plan.write_text(plan.read_text().replace("status: approved", "status: draft"), encoding="utf-8")
            with self.assertRaisesRegex(PipelineError, "approved authority chain is not ready"):
                h.controller.reconfigure(command)
            plan.write_bytes(approved)
        self.assertEqual(before, h.store.path.read_bytes())
        self.issue()
        active = h.store.path.read_bytes()
        with mock.patch("pipeline_v2.runner.pipeline_runtime_digest", return_value=digest("active-rebind")):
            with self.assertRaisesRegex(PipelineError, "runtime changed"):
                h.controller.reconfigure(command)
        self.assertEqual(active, h.store.path.read_bytes())

    def test_runtime_rebind_failed_plan_and_pending_questions_are_not_confirmed(self):
        h = self.h
        self.restart(self.manifest(confirm=True))
        with mock.patch("pipeline_v2.runner.pipeline_runtime_digest", return_value=digest("prior-plan-reset")):
            h.controller.reconfigure(self.rebind_command(verification=self.manifest(confirm=False)))
            h._complete_readonly("plan", "unresolved-plan", {"outcome": "fail", "summary": "Plan requires semantic resolution."})
        with mock.patch("pipeline_v2.runner.pipeline_runtime_digest", return_value=digest("failed-plan-rebind")):
            result = h.controller.reconfigure(self.rebind_command(verification=self.manifest(confirm=True)))
            self.assertEqual("plan", result["phase"])
            # Legacy init history lacks the new guard bit. Its real Plan
            # completion still distinguishes a semantic replan from a reset.
            legacy = deepcopy(result)
            for event in legacy["history"]:
                event.get("prior", {}).pop("approved_plan_reuse_allowed", None)
            self.assertFalse(_runtime_rebind_can_confirm(legacy))
            h._complete_readonly("plan", "plan-question", {"outcome": "pass", "summary": "One technical choice remains.",
                                    "questions": ["Choose an existing implementation strategy."]})
        questions = deepcopy(h.store.load()["questions"])
        with mock.patch("pipeline_v2.runner.pipeline_runtime_digest", return_value=digest("question-rebind")):
            result = h.controller.reconfigure(self.rebind_command())
            self.assertEqual("plan", result["phase"])
            self.assertEqual(questions, result["questions"])
            self.assertIsNone(passing_artifact(result, "plan"))

    def test_runtime_rebind_retains_findings_evidence_and_admitted_reads_without_credit(self):
        h = self.h
        dependency = h.root / "dependency.txt"
        dependency.write_text("Required integration contract\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(h.root), "add", "dependency.txt"], check=True)
        subprocess.run(["git", "-C", str(h.root), "commit", "-qm", "fixture dependency"], check=True)
        self.restart(self.manifest(confirm=True))
        self.issue()
        self.action("read-admit", "READ-REBIND-DEPENDENCY", path="dependency.txt", reason="Required integration contract")
        (h.root / "game.txt").write_text("Candidate with a known defect\n", encoding="utf-8")
        h._complete("IMPLEMENT-REBIND-FINDING", {"outcome": "pass", "summary": "Implementation for review."})
        h._accept("before-rebind-finding")
        finding = {"id": "F-REBIND", "text": "Required behavior remains incorrect.", "severity": "high", "kind": "correctness"}
        failed = h._complete_readonly("review", "review-before-rebind", {"outcome": "fail", "findings": [finding]})
        original = deepcopy(failed["artifacts"]["review"])
        with mock.patch("pipeline_v2.runner.pipeline_runtime_digest", return_value=digest("finding-rebind")):
            result = h.controller.reconfigure(self.rebind_command())
            self.assertEqual(failed["execution"]["findings"], result["execution"]["findings"])
            self.assertEqual(failed["execution"]["read_admissions"], result["execution"]["read_admissions"])
            self.assertEqual(original, result["history"][-3]["prior"]["product_evidence"]["review"])
            self.assertIsNone(passing_artifact(result, "review"))
        # A second immediate runtime rebind must not lose the noncredit failure.
        with mock.patch("pipeline_v2.runner.pipeline_runtime_digest", return_value=digest("finding-rebind-again")):
            result = h.controller.reconfigure(self.rebind_command())
            engineer = self.issue()["active_assignment"]
            self.assertIn("dependency.txt", engineer["access"]["read"])
            self.assertNotIn("dependency.txt", engineer["access"]["write"])
            context = engineer["capsule"]["context"]
            self.assertEqual([finding], context["verification_failure"]["findings"])
            self.assertEqual(original["candidate_binding"], context["verification_failure"]["candidate"])
            self.assertEqual(finding, context["convergence"]["open"]["F-REBIND"])
            self.assertIsNone(current_candidate(result))

    def test_runtime_rebind_preserves_external_review_obligation_and_qa_evidence(self):
        h = self.h
        self.restart(self.manifest(confirm=True))
        h._engineer("before-rebind-obligation", "Candidate\n")
        h._accept("before-rebind-obligation")
        external = h.root / "outside-product.txt"
        external.write_text("Authorized external bytes\n", encoding="utf-8")
        state = h.store.load()
        packet = {"run_id": state["run_id"], "feature": h.feature, "generation": state["generation"],
                  "candidate_tree_oid": fixtures.candidate_tree_oid(h.root), "authority_digest": state["authority"]["digest"],
                  "paths": [{"path": "outside-product.txt", "authorization": "Exact user approval", "provenance": "External editor"}]}
        self.action("reconcile", "EXTERNAL-BEFORE-REBIND", packet=packet)
        self.issue()
        h._complete("IMPLEMENT-EXTERNAL", {"outcome": "pass", "summary": "External work needs review."})
        h._accept("external-work")
        h._review_pass("review-external")
        failed = h._complete_readonly("qa", "qa-before-rebind", {
            "outcome": "fail", "checks": h._qa_checks("Observed player failure", outcome="fail")})
        original = deepcopy(failed["artifacts"]["qa"])
        with mock.patch("pipeline_v2.runner.pipeline_runtime_digest", return_value=digest("obligation-rebind")):
            result = h.controller.reconfigure(self.rebind_command())
            self.assertIn("outside-product.txt", result["execution"]["review_obligations"]["SLICE-1"])
            self.assertEqual(original, result["history"][-3]["prior"]["product_evidence"]["qa"])
            engineer = self.issue()["active_assignment"]
            self.assertIn("outside-product.txt", engineer["access"]["read"])
            self.assertNotIn("outside-product.txt", engineer["access"]["write"])
            self.assertEqual(original["worker"]["checks"], engineer["capsule"]["context"]["verification_failure"]["checks"])
            h._complete("ENGINEER-REBIND-OBLIGATION", {"outcome": "pass", "summary": "New runtime verification completed."})
            h._accept("rebound-obligation")
            target = self.issue()["active_assignment"]["capsule"]["context"]["review_target"]
            self.assertIn("outside-product.txt", target["required_scope"])
            self.assertIn("outside-product.txt", target["candidate_changes"])
            self.assertEqual(packet["candidate_tree_oid"], target["retained_provenance"]["outside-product.txt"]["candidate_tree_oid"])

    def test_engineering_failure_delivered_and_same_owner_reused(self):
        self.h._reach_engineering()
        first = self.issue()["active_assignment"]
        failure = ProcessEvidence(1, digest("failure"), digest(""), b"compiler failed", False)
        with mock.patch("pipeline_v2.runner.run_process_tree", return_value=failure):
            self.h._complete("ENGINEERING-FAILED", {"outcome": "pass", "summary": "Assigned edit completed."})
        following = self.issue()["active_assignment"]
        self.assertNotEqual(first["id"], following["id"])
        self.assertEqual(first["worker_id"], following["worker_id"])
        evidence = following["capsule"]["context"]["verification_failure"]
        self.assertEqual("engineering", evidence["phase"])
        self.assertEqual(1, evidence["controller_failure"]["returncode"])
        self.assertIn("compiler failed", evidence["controller_failure"]["stderr_excerpt"])
        last = self.h.store.load()["history"][-1]
        before = self.h.store.path.read_bytes()
        self.h.controller.next(command_id=last["id"], expected_generation=last["generation"] - 1)
        self.assertEqual(before, self.h.store.path.read_bytes())
        self.h._complete("CHECKPOINT-REPLAY", {"outcome": "fail", "summary": "Handing off without another test run."})
        self.action("rotate-owner", "ROTATE-REPLAY", reason="Checkpoint records the exact current assignment.")
        self.issue()
        before = self.h.store.path.read_bytes()
        self.h.controller.next(command_id=last["id"], expected_generation=last["generation"] - 1)
        self.assertEqual(before, self.h.store.path.read_bytes())

    def test_semantic_fail_skips_checks_and_owner_rotation_is_explicit(self):
        self.h._reach_engineering()
        first = self.issue()["active_assignment"]
        with mock.patch("pipeline_v2.runner.run_process_tree") as process:
            self.h._complete("INCOMPLETE", {"outcome": "fail", "summary": "Checkpoint: implementation incomplete; exact remaining work is recorded."})
            process.assert_not_called()
        self.action("rotate-owner", "ROTATE", reason="Durable checkpoint complete; current context no longer fits the next task.")
        following = self.issue()["active_assignment"]
        self.assertNotEqual(first["worker_id"], following["worker_id"])
        self.assertIn("incomplete", following["capsule"]["context"]["verification_failure"]["summary"])

    def test_diagnostic_rejects_missing_quiescence_and_stale_cas(self):
        self.h._reach_engineering()
        active = self.issue()["active_assignment"]
        original = self.h.store.path.read_bytes()
        with mock.patch("pipeline_v2.runner.run_process_tree") as process:
            with self.assertRaises(PipelineError):
                self.action("check", "NO-PAUSE", assignment_id=active["id"], quiescence="")
            with self.assertRaises(PipelineError):
                self.h.controller.control_action("check", command_id="STALE", expected_generation=0,
                    assignment_id=active["id"], quiescence="Paused")
            process.assert_not_called()
        self.assertEqual(original, self.h.store.path.read_bytes())

    def test_observation_digest_preserves_checks_and_counterevidence(self):
        entry = {"id": "TD-ONE", "situation": "Tool probe", "decision": "Use supported channel", "basis": "Existing authority",
                 "checks": ["Original evidence"], "downstream": "No product change"}
        baseline = {"TD-ONE": entry}
        updated = deepcopy(baseline)
        updated["TD-ONE"]["observations"] = ["Same supported channel was reachable again."]
        self.assertEqual(semantic_journal_digest(baseline), semantic_journal_digest(updated))
        updated["TD-ONE"]["checks"].append("Counterevidence invalidates the previous assumption.")
        self.assertNotEqual(semantic_journal_digest(baseline), semantic_journal_digest(updated))

    def test_capability_recovery_keeps_prior_stages_without_qa_credit(self):
        self.h._reach_candidate()
        self.h._review_pass("review-before-capability")
        self.issue()
        blocked = self.h._complete("QA-BLOCKED", {"outcome": "blocked", "checks": [], "blocker": "Player channel unavailable",
                                                "required_action": "Restore the same authorized player channel."})
        review = deepcopy(blocked["artifacts"]["review"])
        action = self.h.controller.status()["next_action"]
        recovered = self.action("recover-capability", action["command_id"], evidence={
            "binding": action["capability_binding"],
            "prerequisite": "Authorized player channel", "resolution": "Channel now answers the safe probe",
            "evidence": "Current read-only probe succeeded", "unchanged_dependencies": "Candidate, toolchain and acceptance inputs unchanged"})
        self.assertEqual("qa", recovered["phase"])
        self.assertEqual(review, recovered["artifacts"]["review"])
        self.assertIsNotNone(passing_artifact(recovered, "review"))
        self.assertIsNotNone(passing_artifact(recovered, "engineering"))
        self.assertEqual("next", status_view(recovered)["next_action"]["command"])
        self.assertEqual("fail", recovered["artifacts"]["qa"]["worker"]["outcome"])

    def test_exact_read_admission_does_not_grant_write_or_foreign_workflow(self):
        h = self.h
        (h.root / "dependency.txt").write_text("Existing dependency", encoding="utf-8")
        subprocess.run(["git", "-C", str(h.root), "add", "dependency.txt"], check=True)
        subprocess.run(["git", "-C", str(h.root), "commit", "-qm", "fixture dependency"], check=True)
        self.restart(self.manifest(confirm=True))
        first = self.issue()["active_assignment"]
        admitted = self.action("read-admit", "READ-DEPENDENCY", path="dependency.txt", reason="Direct integration contract")
        self.assertIn("dependency.txt", admitted["active_assignment"]["access"]["read"])
        self.assertEqual(first["access"]["write"], admitted["active_assignment"]["access"]["write"])
        with self.assertRaises(PipelineError):
            self.action("read-admit", "READ-FOREIGN", path=".agentic-pipeline/Workflows/other/state.json", reason="Not permitted")

    def test_reconcile_external_change_reopens_verification_with_exact_provenance(self):
        h = self.h
        h._reach_candidate()
        h._review_pass("review-before-external")
        h._qa_pass("qa-before-external")
        self.assertEqual("docs", h.store.load()["phase"])
        (h.root / "game.txt").write_text("Explicitly authorized external correction\n", encoding="utf-8")
        state = h.store.load()
        packet = {"run_id": state["run_id"], "feature": h.feature, "generation": state["generation"],
                  "candidate_tree_oid": fixtures.candidate_tree_oid(h.root), "authority_digest": state["authority"]["digest"],
                  "paths": [{"path": "game.txt", "authorization": "User approved this exact correction", "provenance": "User-owned editor save"}]}
        recovered = self.action("reconcile", "RECONCILE-USER", packet=packet)
        self.assertEqual("engineering", recovered["phase"])
        self.assertIsNone(current_candidate(recovered))
        self.assertEqual("next", h.controller.status()["next_action"]["command"])
        self.issue()

    def test_recipe_manifest_cannot_change_argv(self):
        manifest = self.manifest()
        manifest["slices"]["SLICE-1"][0]["argv"] = ["some-unapproved-command"]
        with self.assertRaises(PipelineError):
            seal_verification(manifest, self.h.slices)

    def test_duplicate_finding_ids_rejected_and_generated_duplicates_are_lossless(self):
        finding = {"id": "F-1", "text": "First supported defect", "severity": "high", "kind": "correctness"}
        with self.assertRaisesRegex(PipelineError, "duplicate Review finding IDs"):
            _worker_artifact({"outcome": "fail", "findings": [finding, {**finding, "text": "Second supported defect"}]}, "review", "reviewer")
        no_id = {key: value for key, value in finding.items() if key != "id"}
        findings = finding_updates(self.h.store.load(), [no_id, no_id])
        self.assertEqual(2, len(findings))
        self.assertNotEqual(findings[0]["id"], findings[1]["id"])

    def test_duplicate_command_semantics_rejected(self):
        self.h.slices[0]["planned_commands"].append(self.h.command)
        manifest = self.manifest()
        manifest["slices"]["SLICE-1"][1]["kind"] = "environment"
        with self.assertRaisesRegex(PipelineError, "different execution semantics"):
            seal_verification(manifest, self.h.slices)

    def test_ignored_declared_dependency_change_prevents_success_reuse(self):
        h = self.h
        command = [h.command[0], "-c", "from pathlib import Path;raise SystemExit(0 if Path('generated/input.txt').read_text() == 'ok' else 1)"]
        h.slices[0]["planned_commands"] = [command]
        dependency = h.root / "generated/input.txt"
        dependency.parent.mkdir(parents=True, exist_ok=True)
        dependency.write_text("ok", encoding="utf-8")
        manifest = self.manifest(confirm=True)
        manifest["slices"]["SLICE-1"][0]["input_paths"] = ["generated/input.txt"]
        state = self.restart(manifest)
        unknown = deepcopy(manifest["slices"]["SLICE-1"][0])
        unknown.pop("input_paths")
        self.assertIsNone(receipt_binding(state, fixtures.candidate_tree_oid(h.root), unknown, {}))
        active = self.issue()["active_assignment"]
        checked = self.action("check", "CHECK-IGNORED", assignment_id=active["id"], quiescence="Writer paused; declared dependency observed.")
        self.assertEqual(0, checked["active_assignment"]["capsule"]["context"]["diagnostic_checks"]["results"][0]["returncode"])
        dependency.write_text("fail", encoding="utf-8")
        completed = h._complete("COMPLETE-CHANGED-DEPENDENCY", {"outcome": "pass", "summary": "Semantic work complete; verify current dependencies."})
        self.assertEqual(1, completed["artifacts"]["engineering"]["controller_failure"]["returncode"])
        self.assertIsNone(current_candidate(completed))

    def test_execution_commands_cannot_bypass_the_controller(self):
        for name in ("check", "rotate-owner", "read-admit", "recover-capability", "reconcile"):
            with self.subTest(name=name), self.assertRaisesRegex(PipelineError, "controller-only"):
                self.h.store.dispatch({"name": name, "id": "FORGED", "expected_generation": 0})

    def test_unknown_external_path_stays_visible_until_review_and_qa_close_it(self):
        h = self.h
        h._reach_candidate()
        h._review_pass("review-before-unknown")
        h._qa_pass("qa-before-unknown")
        path = h.root / "outside-product.txt"
        path.write_text("User-authorized new configuration\n", encoding="utf-8")
        state = h.store.load()
        packet = {"run_id": state["run_id"], "feature": h.feature, "generation": state["generation"],
                  "candidate_tree_oid": fixtures.candidate_tree_oid(h.root), "authority_digest": state["authority"]["digest"],
                  "paths": [{"path": "outside-product.txt", "authorization": "User approved this exact external file",
                             "provenance": "User-owned change observed after accepted S1"}]}
        self.action("reconcile", "RECONCILE-UNKNOWN", packet=packet)
        engineer = self.issue()["active_assignment"]
        self.assertIn("outside-product.txt", engineer["access"]["read"])
        self.assertNotIn("outside-product.txt", engineer["access"]["write"])
        h._complete("ENGINEER-AFTER-UNKNOWN", {"outcome": "pass", "summary": "Existing source remains sufficient under approved behavior."})
        h._accept("engineering-after-unknown")
        review = self.issue()["active_assignment"]
        target = review["capsule"]["context"]["review_target"]
        self.assertIn("outside-product.txt", target["candidate_changes"])
        self.assertIn("outside-product.txt", target["required_scope"])
        self.assertEqual(packet["candidate_tree_oid"], target["retained_provenance"]["outside-product.txt"]["candidate_tree_oid"])
        h._complete("REVIEW-UNKNOWN", {"outcome": "pass", "findings": []})
        h._accept("review-unknown")
        h._qa_pass("qa-unknown")
        state = h.store.load()
        self.assertNotIn("SLICE-1", state["execution"]["review_obligations"])
        receipt = state["history"][-1]["review_obligations_closed"]
        self.assertEqual(["outside-product.txt"], receipt["paths"])
        self.assertEqual(review["id"], receipt["review_assignment_id"])
        self.assertEqual("User-authorized new configuration\n", path.read_text(encoding="utf-8"))

    def test_qa_packet_contains_only_exact_applicable_controller_receipts(self):
        self.restart(self.manifest(confirm=True))
        self.issue()
        with mock.patch("pipeline_v2.runner.run_process_tree", return_value=self.passing()):
            self.h._complete("ENGINEERING-RECEIPT", {"outcome": "pass", "summary": "Assigned implementation complete."})
        self.h._accept("engineering-receipt")
        self.h._review_pass("review-receipt")
        state = self.issue()
        packet = state["active_assignment"]["capsule"]["context"]["machine_checks"]
        self.assertEqual(current_candidate(state)["candidate_tree_oid"], packet["candidate_tree_oid"])
        self.assertEqual(state["authority"]["digest"], packet["authority_digest"])
        self.assertFalse(packet["grants_manual_acceptance"])
        self.assertEqual([], packet["pending_check_ids"])
        self.assertEqual(["check-0"], [item["id"] for item in packet["checks"]])
        record = next(iter(state["execution"]["receipts"].values()))
        self.assertEqual(record["id"], packet["checks"][0]["receipt_id"])
        self.assertEqual(digest(record["result"]), packet["checks"][0]["receipt_sha256"])
        self.assertTrue(packet["checks"][0]["source_locator"].endswith(record["binding"]))
        self.assertNotIn("stdout", packet["checks"][0])

    def test_active_qa_check_is_readonly_and_never_grants_semantic_acceptance(self):
        self.h._reach_candidate()
        self.h._review_pass("review-before-qa-check")
        issued = self.issue()
        active = issued["active_assignment"]
        self.assertEqual([], active["access"]["write"])
        self.assertEqual([], active["capsule"]["context"]["machine_checks"]["checks"])
        before_tree = fixtures.candidate_tree_oid(self.h.root)
        with mock.patch("pipeline_v2.runner.run_process_tree", return_value=self.passing()) as process:
            checked = self.action("check", "QA-PREPARATION", assignment_id=active["id"],
                                 quiescence="QA gameplay is paused and no owned persistent writer remains.")
            self.assertEqual(active["id"], checked["active_assignment"]["id"])
            self.assertEqual("qa", checked["phase"])
            self.assertNotIn("qa", checked["artifacts"])
            self.assertEqual(before_tree, fixtures.candidate_tree_oid(self.h.root))
            rows = checked["active_assignment"]["capsule"]["context"]["machine_checks"]["checks"]
            self.assertEqual("pass", rows[0]["outcome"])
            self.assertIn("diagnostic_checks/results/0", rows[0]["source_locator"])
            self.h._complete("QA-AFTER-PREPARATION", {"outcome": "pass", "checks": self.h._qa_checks("Actual fixture scenario and prepared machine check observed.")})
            # Unknown/environment-sensitive recipes remain fresh at the final gate.
            self.assertEqual(2, process.call_count)

    def test_unresolved_reconcile_obligation_survives_upstream_epoch_change(self):
        h = self.h
        h._reach_candidate()
        h._review_pass("review-before-epoch")
        h._qa_pass("qa-before-epoch")
        path = h.root / "outside-product.txt"
        path.write_text("Unreviewed external product bytes\n", encoding="utf-8")
        state = h.store.load()
        packet = {"run_id": state["run_id"], "feature": h.feature, "generation": state["generation"],
                  "candidate_tree_oid": fixtures.candidate_tree_oid(h.root), "authority_digest": state["authority"]["digest"],
                  "paths": [{"path": "outside-product.txt", "authorization": "Exact user approval",
                             "provenance": "User change after accepted slice"}]}
        self.action("reconcile", "RECONCILE-BEFORE-EPOCH", packet=packet)
        narrower = [{**deepcopy(h.slices[0]), "allowed_paths": ["replacement.luau"]}]
        h._write_approved_plan(narrower, revision=2)
        action = h.controller.status()["next_action"]
        restarted = h.controller.reconfigure(h._baseline_init_command(action))
        self.assertIn("outside-product.txt", restarted["execution"]["review_obligations"]["SLICE-1"])
        h._complete_readonly("plan", "epoch-plan", {"outcome": "pass", "summary": "Exact new authority."})
        h._accept("epoch-plan")
        h._complete_readonly("slice", "epoch-slice", {"outcome": "pass", "summary": "Exact new write scope."})
        h._accept("epoch-slice")
        engineer = self.issue()["active_assignment"]
        self.assertNotIn("outside-product.txt", engineer["access"]["write"])
        self.assertIn("outside-product.txt", engineer["access"]["read"])
        h._complete("ENGINEER-EPOCH", {"outcome": "pass", "summary": "New scope completed; retained external bytes need independent judgment."})
        h._accept("engineering-epoch")
        target = self.issue()["active_assignment"]["capsule"]["context"]["review_target"]
        self.assertIn("outside-product.txt", target["candidate_changes"])
        self.assertIn("outside-product.txt", target["required_scope"])
        self.assertEqual(packet["candidate_tree_oid"], target["retained_provenance"]["outside-product.txt"]["candidate_tree_oid"])
        self.assertEqual("Unreviewed external product bytes\n", path.read_text(encoding="utf-8"))

    def test_independent_diagnostic_failures_are_collected_without_credit(self):
        h = self.h
        h.slices[0]["planned_commands"] = [h.command, [*h.command[:-1], "raise SystemExit(1)"]]
        h._write_approved_plan(h.slices)
        manifest = self.manifest(confirm=True)
        for recipe in manifest["slices"]["SLICE-1"]:
            recipe["independent"] = True
        self.restart(manifest)
        active = self.issue()["active_assignment"]
        failure = ProcessEvidence(1, digest("failed"), digest("stderr"), b"Independent test failure", False)
        with mock.patch("pipeline_v2.runner.run_process_tree", return_value=failure) as process:
            state = self.action("check", "CHECK-BATCH", assignment_id=active["id"], quiescence="Writer paused.", collect_independent=True)
            self.assertEqual(2, process.call_count)
            self.assertEqual(2, len(state["active_assignment"]["capsule"]["context"]["diagnostic_checks"]["results"]))
            self.assertIsNone(current_candidate(state))
            h._complete("BATCH-INCOMPLETE", {"outcome": "fail", "summary": "Two independent failures need the same bounded remediation."})
            self.assertEqual(2, process.call_count)
            next_owner = self.issue()["active_assignment"]
            delivered = next_owner["capsule"]["context"]["verification_failure"]["diagnostic_checks"]
            self.assertEqual(2, len(delivered["results"]))
            self.assertEqual(active["worker_id"], next_owner["worker_id"])

    def test_candidate_change_invalidates_active_deterministic_receipt(self):
        self.restart(self.manifest(confirm=True))
        active = self.issue()["active_assignment"]
        with mock.patch("pipeline_v2.runner.run_process_tree", return_value=self.passing()) as process:
            self.action("check", "CHECK-BEFORE-EDIT", assignment_id=active["id"], quiescence="Writer paused.")
            (self.h.root / "game.txt").write_text("Changed after check\n", encoding="utf-8")
            self.h._complete("COMPLETE-NEW-TREE", {"outcome": "pass", "summary": "New candidate requires its own check."})
            self.assertEqual(2, process.call_count)

    def test_pure_documentation_review_reuses_product_qa_with_provenance(self):
        doc_path = "docs/RUN-TEST-verification.md"
        self.restart(self.manifest(confirm=True, pure=[doc_path]))
        self.issue()
        with mock.patch("pipeline_v2.runner.run_process_tree", return_value=self.passing()) as process:
            self.h._complete("CODE-PASS", {"outcome": "pass", "summary": "Assigned behavior already implemented."})
            self.h._accept("code-pass")
            self.h._review_pass("product-review")
            self.h._qa_pass("product-qa")
            original = deepcopy(self.h.store.load()["artifacts"]["qa"])
            self.issue()
            target = self.h.root / doc_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("Source-grounded documentation only.\n", encoding="utf-8")
            self.h._complete("DOCS-PASS", {"outcome": "pass", "summary": "Updated pure documentation."})
            self.h._accept("docs-pass")
            self.h._complete_readonly("review", "docs-review", {"outcome": "pass", "findings": []})
            action = self.h.controller.status()["next_action"]
            self.h.controller.transition({"name": "accept", "id": action["command_id"], "expected_generation": action["expected_generation"]})
            state = self.h.store.load()
            self.assertEqual("ready", state["phase"])
            self.assertEqual(original["worker"], state["artifacts"]["qa"]["worker"])
            self.assertIn("reused_from", state["artifacts"]["qa"])
            self.assertEqual(1, process.call_count)


if __name__ == "__main__":
    unittest.main()
