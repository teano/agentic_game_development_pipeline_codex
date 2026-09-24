from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[2]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from pipeline_v2.tests import test_core as fixtures
from pipeline_v2.cli import parser, run
from pipeline_v2.delivery import execute_step
from pipeline_v2.model import PipelineError, default_assignment, digest, status_view, validate_state
from pipeline_v2.no_progress import no_progress_hold
from pipeline_v2.reducer import reduce
from pipeline_v2.runner import Controller


class NoProgressTests(unittest.TestCase):
    def setUp(self):
        self.h = fixtures.PipelineV2CoreTests()
        self.h.setUp()
        self.controller = Controller(self.h.store)

    def tearDown(self):
        self.h.tearDown()

    def issue(self):
        action = self.controller.status()["next_action"]
        return self.controller.next(command_id=action["command_id"], expected_generation=action["expected_generation"])

    def complete(self, artifact):
        self.h._write_artifact(artifact)
        action = self.controller.status()["next_action"]
        state = self.controller.complete(command_id=action["command_id"], expected_generation=action["expected_generation"])
        return state, action

    def reviewed_residual(self):
        self.h._reach_candidate()
        self.issue()
        # Saved RC11 g49 -> g51/g53/g55 shape: exact original identities,
        # four remaining conditions, the first three in one composite finding.
        findings = [
            {"id": "REVIEW-AUTO-COVERAGE-001", "text": "Missing actual scenario coverage.",
             "kind": "verification", "severity": "high", "conditions": [
                 {"id": key, "text": text} for key, text in (
                     ("C10", "Execute the distinct effect-triggered path."),
                     ("C16", "Execute rejection of a terminal swap."),
                     ("C17", "Execute restart from the active state."))]},
            {"id": "REVIEW-MATCH-TARGETS-001", "text": "The rejected transformation branch remains unchanged.",
             "kind": "correctness", "severity": "high",
             "conditions": [{"id": "C1", "text": "Preserve the initial normal-match targets through transformation."}]},
        ]
        self.complete({"outcome": "fail", "findings": findings})
        self.issue()
        return [{"finding_id": item["id"], "condition_id": condition["id"],
                 "status": "unresolved", "evidence": "Existing scenario remains unchanged."}
                for item in findings for condition in item["conditions"]]

    def held(self, *, reviewed=True):
        if reviewed:
            rows = self.reviewed_residual()
        else:
            self.h._reach_engineering()
            self.issue()
            rows = []
        artifact = {"outcome": "fail", "summary": "Conditions remain unresolved pending a new distinction.",
                    "finding_resolutions": rows}
        state, action = self.complete(artifact)
        return state, action, artifact

    def resolution(self, text="Independent clarification identifies the distinct rejected input.", *, source="game.txt"):
        action = self.controller.status()["next_action"]
        source_path = self.h.root / source
        packet = {"binding": action["no_progress_binding"], "kind": "clarification",
                  "affected_conditions": action["affected_conditions"],
                  "evidence": [{"path": source, "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
                                "observation": text}], "answer": "Implement the exact distinguished input and retain independent Review."}
        command = {"name": "answer", "id": action["command_id"], "expected_generation": action["expected_generation"],
                   "question_id": action["question_id"], "resolution": packet}
        return command

    def test_rc11_failure_consumed_once_and_every_native_redispatch_path_holds(self):
        state, complete_action, artifact = self.held()
        action = self.controller.status()["next_action"]
        self.assertEqual("no_progress_resolution_required", action["result"])
        self.assertEqual("review", action["resolver_role"])
        self.assertEqual(4, len(action["affected_conditions"]))
        self.assertEqual(artifact, state["artifacts"]["engineering"]["worker"])
        record = state["artifacts"]["engineering"]
        self.assertEqual(record["controller"]["base_tree_oid"], record["controller"]["candidate_tree_oid"])
        self.assertNotEqual(record["candidate"]["base_tree_oid"], record["controller"]["base_tree_oid"])
        before = self.h.store.path.read_bytes()
        replay = self.controller.complete(command_id=complete_action["command_id"], expected_generation=complete_action["expected_generation"])
        self.assertEqual(state, replay)
        self.assertEqual(before, self.h.store.path.read_bytes())
        self.assertEqual({}, state["questions"])
        for identity in ("fresh-nonce", action["command_id"]):
            with self.assertRaisesRegex(PipelineError, "no-progress"):
                self.controller.next(command_id=identity, expected_generation=state["generation"])
        with self.assertRaisesRegex(PipelineError, "no-progress"):
            reduce(state, {"name": "next", "id": "REDUCER-NONCE", "expected_generation": state["generation"],
                           "assignment": default_assignment(state),
                           "controller_base": {"candidate_tree_oid": record["controller"]["candidate_tree_oid"]}})
        response = execute_step(self.controller, self.h.root, state["generation"], action["command_id"], through_handoff=True)
        self.assertEqual("stopped", response["result"])
        self.assertEqual(before, self.h.store.path.read_bytes())
        rotated = self.controller.control_action("rotate-owner", command_id="ROTATE-FOR-FRESH-NONCE",
                                                expected_generation=state["generation"], reason="New specialist session.")
        self.assertEqual(action["no_progress_binding"], status_view(rotated)["next_action"]["no_progress_binding"])
        with self.assertRaisesRegex(PipelineError, "no-progress"):
            self.controller.next(command_id="NEW-WORKER-NONCE", expected_generation=rotated["generation"])

    def test_rewritten_failure_receipt_ids_checks_and_journal_prose_are_not_progress(self):
        state, _, _ = self.held()
        hold = no_progress_hold(state)
        for label in ("summary", "receipt", "generation", "journal"):
            changed = deepcopy(state)
            if label == "summary":
                changed["artifacts"]["engineering"]["worker"]["summary"] = "Rewritten failure with nonce 42."
            elif label == "receipt":
                changed["artifacts"]["engineering"]["diagnostic_checks"] = {"results": [{"receipt_id": "new", "returncode": 0}]}
            elif label == "generation":
                changed["generation"] += 2
            else:
                changed["technical_decisions"] = {"TD-NONCE": {"situation": "New wording", "decision": "Same basis"}}
            self.assertEqual(hold["binding"], no_progress_hold(changed)["binding"], label)

    def test_first_unchanged_failure_holds_but_productive_partial_failure_can_continue(self):
        self.h._reach_engineering()
        self.issue()
        (self.h.root / "game.txt").write_text("Partial actual repair.\n", encoding="utf-8")
        state, _ = self.complete({"outcome": "fail", "summary": "One remaining defect."})
        self.assertEqual("next", status_view(state)["next_action"]["command"])
        self.issue()
        state, _ = self.complete({"outcome": "fail", "summary": "Still unchanged."})
        self.assertEqual("no_progress_resolution_required", status_view(state)["next_action"]["result"])

    def test_initial_unchanged_failure_holds_without_a_fabricated_product_question(self):
        state, _, _ = self.held(reviewed=False)
        action = status_view(state)["next_action"]
        self.assertEqual([], action["affected_conditions"])
        self.assertEqual([action["question_id"]], status_view(state)["open_questions"])
        self.assertFalse(action["user_input_required"])
        self.assertEqual("engineer", action["resolver_role"])
        from pipeline_v2.execution import classify_error
        classified = classify_error(PipelineError("no-progress hold forbids unchanged Engineering redispatch"))
        self.assertEqual("no_progress", classified["category"])
        self.assertFalse(classified["retryable"])
        with self.assertRaisesRegex(PipelineError, "no-progress"):
            self.controller.transition({"name": "answer", "id": action["command_id"],
                                        "expected_generation": state["generation"], "question_id": action["question_id"],
                                        "answer": "Retry unchanged."})

    def test_proof_only_pass_still_requires_and_reaches_independent_review(self):
        rows = self.reviewed_residual()
        tree = self.h.store.load()["active_assignment"]["base"]["candidate_tree_oid"]
        state, _ = self.complete({"outcome": "pass", "summary": "Exact existing source establishes the required distinctions.",
                                  "finding_resolutions": [{**row, "status": "addressed", "evidence": "Concrete retained source proof."} for row in rows]})
        self.assertEqual(tree, state["artifacts"]["engineering"]["controller"]["candidate_tree_oid"])
        self.assertEqual("accept", status_view(state)["next_action"]["command"])
        self.h._accept("proof-only")
        review = self.issue()
        self.assertEqual("review", review["phase"])
        self.assertEqual(4, len(review["active_assignment"]["capsule"]["context"]["convergence"]["engineering_resolutions"]))

    def test_bound_resolution_grants_one_attempt_and_replay_cannot_release_the_next_hold(self):
        self.held()
        before = deepcopy(self.h.store.load()["execution"]["findings"])
        command = self.resolution()
        answered = self.controller.transition(command)
        self.assertEqual(before, answered["execution"]["findings"])
        self.assertEqual("next", status_view(answered)["next_action"]["command"])
        saved = self.h.store.path.read_bytes()
        self.assertEqual(answered, self.controller.transition(command))
        self.assertEqual(saved, self.h.store.path.read_bytes())
        active = self.issue()["active_assignment"]
        self.assertEqual(command["resolution"], active["capsule"]["context"]["decisions"][0]["resolution"])
        from pipeline_v2.finding_contract import current_record, required_conditions
        pairs = required_conditions(current_record(self.h.store.load()), "engineering")
        state, _ = self.complete({"outcome": "fail", "summary": "Rewritten but still unchanged.", "finding_resolutions": [
            {"finding_id": a, "condition_id": b, "status": "unresolved", "evidence": "Still unchanged."} for a, b in sorted(pairs)]})
        held = status_view(state)["next_action"]
        self.assertEqual("no_progress_resolution_required", held["result"])
        self.controller.transition(command)  # Old successful command replay only returns current state.
        self.assertEqual(held, self.controller.status()["next_action"])
        repeated = self.resolution()
        repeated["resolution"]["kind"] = "counterexample"
        repeated["resolution"]["answer"] = "\n  " + repeated["resolution"]["answer"] + "\t"
        with self.assertRaisesRegex(PipelineError, "duplicates"):
            self.controller.transition(repeated)
        new = self.resolution("The same source exposes a different premise: the previously assumed input never enters the rejected branch.")
        new["resolution"]["answer"] = "Established source control flow excludes the prior fixture. The residual is that rejected branch. Use the distinguished input; the prior answer incorrectly assumed branch entry."
        new["resolution"]["kind"] = "counterexample"
        self.controller.transition(new)
        self.assertEqual("next", self.controller.status()["next_action"]["command"])

    def test_stale_binding_unknown_pairs_missing_source_and_bookkeeping_fail_closed(self):
        self.held()
        command = self.resolution()
        before = self.h.store.path.read_bytes()
        variants = []
        wrong = deepcopy(command); wrong["resolution"]["binding"]["assignment_id"] = "old"; variants.append(wrong)
        wrong = deepcopy(command); wrong["resolution"]["affected_conditions"][0]["condition_id"] = "invented"; variants.append(wrong)
        wrong = deepcopy(command); wrong["resolution"]["evidence"][0]["sha256"] = "0" * 64; variants.append(wrong)
        wrong = deepcopy(command); wrong["resolution"]["nonce"] = 42; variants.append(wrong)
        wrong = deepcopy(command); wrong["resolution"]["evidence"][0]["path"] = self.h.workflow_path + "/pipeline-state.json"; variants.append(wrong)
        for wrong in variants:
            with self.assertRaises(PipelineError):
                self.controller.transition(wrong)
            self.assertEqual(before, self.h.store.path.read_bytes())

    def test_cli_resolution_is_callable_workflow_local_and_exclusive_with_text(self):
        self.held(reviewed=False)
        command = self.resolution("Resolved local prerequisite has concrete fresh evidence.")
        command["resolution"]["kind"] = "prerequisite"
        path = self.h.root / self.h.workflow_path / "resolution.json"
        path.write_text(json.dumps(command["resolution"]), encoding="utf-8")
        prefix = ["--root", str(self.h.root), "--feature", self.h.feature, "answer", "--id", command["id"],
                  "--expected-generation", str(command["expected_generation"]), "--question-id", command["question_id"]]
        with mock.patch("sys.stderr"):
            with self.assertRaises(SystemExit):
                parser().parse_args(prefix + ["--text", "retry", "--resolution", str(path)])
        outside = self.h.root / "outside.json"
        outside.write_bytes(path.read_bytes())
        try:
            with self.assertRaisesRegex(PipelineError, "workflow-local"):
                run(parser().parse_args(prefix + ["--resolution", str(outside)]))
        finally:
            outside.unlink()
        result = run(parser().parse_args(prefix + ["--resolution", str(path)]))
        self.assertEqual("next", result["next_action"]["command"])

    def test_identical_init_cannot_reset_hold_and_real_runtime_rebind_preserves_obligations(self):
        state, _, _ = self.held()
        from pipeline_v2.model import reconfiguration_action
        action = reconfiguration_action(state, state["authority"]["items"],
                                        candidate_tree_oid=state["artifacts"]["engineering"]["controller"]["candidate_tree_oid"])
        before = self.h.store.path.read_bytes()
        with self.assertRaisesRegex(PipelineError, "did not change"):
            self.controller.reconfigure(self.h._baseline_init_command(action))
        self.assertEqual(before, self.h.store.path.read_bytes())
        with mock.patch("pipeline_v2.runner.pipeline_runtime_digest", return_value=digest("real-new-approved-runtime")):
            action = self.controller.status()["next_action"]
            self.assertEqual("init", action["command"])
            result = self.controller.reconfigure(self.h._baseline_init_command(action))
            self.assertEqual(state["execution"]["findings"], result["execution"]["findings"])
            self.assertEqual(state["artifacts"]["engineering"], result["history"][-1]["prior"]["product_evidence"]["engineering"])
            self.assertIsNone(no_progress_hold(result))

    def test_reconcile_requires_relevant_changed_candidate_not_an_unrelated_nonce(self):
        state, _, _ = self.held()
        def packet(path):
            return {"run_id": state["run_id"], "feature": state["feature"], "generation": state["generation"],
                    "candidate_tree_oid": fixtures.candidate_tree_oid(self.h.root), "authority_digest": state["authority"]["digest"],
                    "paths": [{"path": path, "authorization": "Exact authorized external change.", "provenance": "User-owned editor."}]}
        unrelated = self.h.root / "nonce.txt"
        unrelated.write_text("A fresh unrelated nonce.\n", encoding="utf-8")
        with self.assertRaisesRegex(PipelineError, "unrelated"):
            self.controller.control_action("reconcile", command_id="UNRELATED-NONCE", expected_generation=state["generation"], packet=packet("nonce.txt"))
        unrelated.unlink()
        (self.h.root / "game.txt").write_text("Actual authorized correction of the rejected branch.\n", encoding="utf-8")
        result = self.controller.control_action("reconcile", command_id="ACTUAL-CHANGE", expected_generation=state["generation"], packet=packet("game.txt"))
        self.assertEqual("next", status_view(result)["next_action"]["command"])
        self.assertEqual(state["execution"]["findings"], result["execution"]["findings"])

    def test_complete_through_handoff_stops_after_unchanged_controller_failure(self):
        from pipeline_v2.process_tree import ProcessEvidence
        self.h._reach_engineering()
        self.issue()
        self.h._write_artifact({"outcome": "pass", "summary": "No product changes; controller will observe failure."})
        action = self.controller.status()["next_action"]
        with mock.patch("pipeline_v2.runner.run_process_tree", return_value=ProcessEvidence(7, digest("stdout"), digest("stderr"))):
            result = execute_step(self.controller, self.h.root, action["expected_generation"], action["command_id"], through_handoff=True)
        self.assertEqual(["complete"], [step["command"] for step in result["steps"]])
        self.assertEqual("no_progress_resolution_required", result["next_action"]["result"])
        self.assertIsNone(self.h.store.load()["active_assignment"])

    def fail_again(self):
        self.issue()
        from pipeline_v2.finding_contract import current_record, required_conditions
        pairs = required_conditions(current_record(self.h.store.load()), "engineering")
        return self.complete({"outcome": "fail", "summary": "No candidate change; the residual remains.",
                              "finding_resolutions": [{"finding_id": a, "condition_id": b, "status": "unresolved",
                                                       "evidence": "Same source and unresolved cause."} for a, b in sorted(pairs)]})[0]

    def test_same_source_can_clarify_a_different_condition_and_prior_assessments_stay_visible(self):
        self.held()
        first = self.resolution()
        all_pairs = deepcopy(first["resolution"]["affected_conditions"])
        first["resolution"]["affected_conditions"] = all_pairs[:1]
        self.controller.transition(first)
        self.fail_again()
        second = self.resolution("The same source establishes a different exact residual premise.")
        second["resolution"]["affected_conditions"] = all_pairs[1:2]
        self.controller.transition(second)
        self.fail_again()
        self.assertEqual(2, len(self.controller.status()["next_action"]["prior_assessments"]))
        repeated = self.resolution("The same source establishes a different exact residual premise.")
        repeated["resolution"]["affected_conditions"] = all_pairs[1:2]
        with self.assertRaisesRegex(PipelineError, "duplicates"):
            self.controller.transition(repeated)

    def test_renamed_source_copy_and_nonce_wrapped_workflow_receipt_do_not_count_as_fresh_support(self):
        duplicate = self.h.root / "tests/source-copy.txt"
        duplicate.parent.mkdir(parents=True, exist_ok=True)
        duplicate.write_bytes((self.h.root / "specification.md").read_bytes())
        self.h._commit_fixture_and_restart("fixture exact source copy")
        self.controller = Controller(self.h.store)
        self.held()
        self.controller.transition(self.resolution(source="specification.md"))
        self.fail_again()
        with self.assertRaisesRegex(PipelineError, "duplicates"):
            self.controller.transition(self.resolution(source="tests/source-copy.txt"))
        for name in ("qa-evidence/renamed-receipt.json", "resolution-evidence/fresh-report.json"):
            path = self.h.root / self.h.workflow_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"nonce": name, "receipt": {"returncode": 0}, "summary": "Fresh wrapper"}), encoding="utf-8")
            packet = self.resolution(source=path.relative_to(self.h.root).as_posix())
            with self.assertRaisesRegex(PipelineError, "candidate-bound source"):
                self.controller.transition(packet)

    def test_resolution_is_bound_to_physical_project_and_cannot_bypass_controller_source_validation(self):
        from pipeline_v2.transaction import StateStore
        self.held()
        command = self.resolution()
        with self.assertRaisesRegex(PipelineError, "controller-only"):
            self.h.store.dispatch(command)
        for answered in (False, True):
            if answered:
                self.controller.transition(command)
            with tempfile.TemporaryDirectory() as temporary:
                cloned = Path(temporary) / "cloned-project"
                shutil.copytree(self.h.root, cloned)
                path = cloned / self.h.workflow_path / "pipeline-state.json"
                state = json.loads(path.read_text(encoding="utf-8"))
                state["project_root"] = str(cloned.resolve())
                path.write_text(json.dumps(state), encoding="utf-8")
                controller = Controller(StateStore(path))
                with self.assertRaisesRegex(PipelineError, "no-progress"):
                    controller.transition(command)

    def test_line_ending_representation_cannot_make_an_identical_assessment_new(self):
        subprocess.run(["git", "-C", str(self.h.root), "config", "core.autocrlf", "true"], check=True)
        self.held()
        source = self.h.root / "game.txt"
        # write_text uses CRLF on Windows, so establish LF explicitly first.
        source.write_bytes(source.read_bytes().replace(b"\r\n", b"\n"))
        original = self.resolution()
        original["resolution"]["answer"] = "The source is unchanged. The remaining distinction is the literal 'a b'. Correct that exact input under approved scope."
        answered = self.controller.transition(original)
        identities = answered["questions"][original["question_id"]]["resolution_sources"]
        self.assertTrue(identities[0].startswith("git_blob:"))
        self.fail_again()
        tree = fixtures.candidate_tree_oid(self.h.root)
        source.write_bytes(source.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        repeated = self.resolution()
        repeated["resolution"]["answer"] = "\n  " + original["resolution"]["answer"] + "\t"
        self.assertEqual(tree, fixtures.candidate_tree_oid(self.h.root))
        self.assertNotEqual(original["resolution"]["evidence"][0]["sha256"], repeated["resolution"]["evidence"][0]["sha256"])
        before = self.h.store.path.read_bytes()
        with self.assertRaisesRegex(PipelineError, "duplicates"):
            self.controller.transition(repeated)
        self.assertEqual(before, self.h.store.path.read_bytes())
        revised = deepcopy(repeated)
        # Internal literal spaces carry meaning; only outer formatting is noise.
        revised["resolution"]["answer"] = original["resolution"]["answer"].replace("'a b'", "'a  b'")
        result = self.controller.transition(revised)
        self.assertEqual(identities, result["questions"][revised["question_id"]]["resolution_sources"])
        self.assertEqual("next", status_view(result)["next_action"]["command"])

    def test_missing_or_invalid_controller_source_identities_cannot_release_a_hold(self):
        held, _, _ = self.held(reviewed=False)
        command = self.resolution()
        with self.assertRaisesRegex(PipelineError, "controller-owned canonical source"):
            reduce(held, command)
        fake = "git_blob:" + "f" * 40
        command["controller"] = {"resolution_sources": [fake]}
        answered = self.controller.transition(command)
        self.assertNotEqual([fake], answered["questions"][command["question_id"]]["resolution_sources"])
        for sources in (None, [], ["raw-sha256:" + "a" * 64], ["git_blob:invalid"]):
            changed = deepcopy(answered)
            question = changed["questions"][command["question_id"]]
            if sources is None:
                question.pop("resolution_sources")
            else:
                question["resolution_sources"] = sources
            with self.assertRaisesRegex(PipelineError, "controller-owned canonical source"):
                status_view(changed)
            with self.assertRaisesRegex(PipelineError, "controller-owned canonical source"):
                no_progress_hold(changed)
        ordinary = deepcopy(held)
        ordinary["questions"]["legacy-answer"] = {"status": "answered", "phase": "engineering", "prompt": "Existing choice?", "answer": "Use the existing approved choice."}
        validate_state(ordinary)
        self.assertEqual("no_progress_resolution_required", status_view(ordinary)["next_action"]["result"])


if __name__ == "__main__":
    unittest.main()
