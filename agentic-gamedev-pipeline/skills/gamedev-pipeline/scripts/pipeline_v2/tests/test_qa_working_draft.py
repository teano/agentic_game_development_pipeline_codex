"""Incremental assessment and the preserved unfinished-mapping counterexample.

Pure runner tests mock only native checkout/context acquisition; the actual
working artifact, schemas, evidence/source checks and compiler are exercised.
"""
from copy import deepcopy
from contextlib import redirect_stdout, redirect_stderr
import io
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from pipeline_v2.artifact_io import read_json, write_json
from pipeline_v2.execution_evidence import begin, capture
from pipeline_v2.model import PipelineError, qa_contract_context
from pipeline_v2.qa_contract import contract_digest, validate_results, source_reference
from pipeline_v2.qa_draft import load, prepare_update, assemble, validate_projection
from pipeline_v2.runner import Controller
from pipeline_v2.transaction import StateStore
from pipeline_v2.tests.test_qa_contract import sample_contract, compact_contract


class QAWorkingDraftTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "game.txt").write_text("state = initialized\n", encoding="utf8")
        self.contract = compact_contract(sample_contract())
        self.definition = self.contract["slices"]["SLICE-001"]
        original = self.definition["method_definitions"].pop("shared-1")
        self.definition["method_definitions"]["METHOD-fe82d465e8433451"] = original
        for identity in self.definition["identities"]:
            for row in identity["assertions"]:
                row["methods"] = [{"ref": "METHOD-fe82d465e8433451"}]
        self.binding = {"kind": "assignment", "project_root": str(self.root), "feature": "feature", "run_id": "run",
                        "assignment_id": "qa-current", "phase": "qa", "slice_id": "SLICE-001",
                        "candidate_tree_oid": "c" * 40, "authority_digest": "a" * 64, "pipeline_runtime_digest": "b" * 64}
        self.state = {"phase": "qa", "feature": "feature", "project_root": str(self.root), "workflow_path": ".agentic-pipeline/Workflows/feature",
                      "authority": {"digest": "a" * 64}, "generation": 19, "history": [],
                      "slices": [{"id": "SLICE-001", "allowed_paths": ["game.txt", "tests/**"]}],
                      "execution": {"qa_contract": self.contract, "qa_contract_binding": {"authority_digest": "a" * 64, "contract_digest": contract_digest(self.contract)}}}
        self.state["active_assignment"] = {"id": "qa-current", "role": "qa", "phase": "qa", "access": {"read": ["game.txt", "tests/**"], "write": []},
                                           "capsule": {"context": {"qa_contract": qa_contract_context(self.state)}}}
        self.store = StateStore(self.root / self.state["workflow_path"] / "pipeline-state.json")
        self.controller = Controller(self.store)
        for name, value in (("_qa_working_context", (self.state, self.root, self.binding)), ("_evidence_binding", self.binding), ("_verify_live_checkout", "c" * 40)):
            patcher = mock.patch.object(self.controller, name, return_value=value); patcher.start(); self.addCleanup(patcher.stop)
        patcher = mock.patch("pipeline_v2.checkout._git", return_value=b"")
        patcher.start(); self.addCleanup(patcher.stop)

    def row(self, identifier="enter"):
        return {"id": identifier, "method_id": "METHOD-fe82d465e8433451", "environment": "Observed fixture session",
                "evidence": [{"type": "observation", "ref": "fixture:observation", "observation": "Required result observed."}],
                "assessment": {"observed": "Required result observed.", "comparison": "matches"}}

    def source(self):
        return {"path": "game.txt", "sha256": hashlib.sha256((self.root / "game.txt").read_bytes()).hexdigest(), "start_line": 1, "end_line": 1}

    def gap(self):
        return {"id": "enter", "environment": "Inspected candidate source", "outcome": "not_run",
                "evidence": [{"type": "verification-gap", "source": self.source(), "observation": "Source has initial state but no reset proof."}],
                "assessment": {"observed": "The approved reset case is absent from the inspected source.", "comparison": "insufficient"},
                "reason": {"kind": "verification_incomplete", "detail": "Add the specific reset case in the existing test scope.",
                           "repair": {"owner": "engineering", "target": "tests/state_test.py", "missing_obligation": "Executed reset then asserted initialized state.",
                                      "attempted_method_ids": ["METHOD-fe82d465e8433451"]}}}

    def external(self, identifier):
        return {"id": identifier, "outcome": "not_run", "environment": "Named external performer is pending",
                "assessment": {"observed": "User reserved the actual two-account check for their own session.", "comparison": "insufficient"},
                "evidence": [{"type": "external-prerequisite", "ref": "user-decision:1", "observation": "User owns the pending check; no waiver."}],
                "reason": {"kind": "external_wait", "detail": "Named user provides actual two-account observation.", "refs": ["user-check"]}}

    def test_pending_is_not_a_verdict_and_partial_group_resumes_after_generation_change(self):
        initial = self.controller.qa_draft("qa-current")
        self.assertEqual((0, 3), (initial["assessed"], initial["pending"]))
        self.assertNotIn("assessments", initial)
        refused = self.controller.qa_finalize("qa-current", 0)
        self.assertFalse(refused["valid"])
        self.assertFalse((self.store.path.parent / "outputs/qa-current.json").exists())
        response = self.controller.qa_record("qa-current", {"expected_revision": 0, "assessments": [self.row()]})
        self.assertTrue(response["valid"])
        original = Path(response["working_path"]).read_bytes()
        self.state["generation"] += 1  # A diagnostic cursor change is not a new candidate.
        selected = self.controller.qa_read("qa-current", assertion_id="enter")
        self.assertEqual("observed-action", selected["assessments"][0]["method_id"])
        self.assertEqual("The approved transition completes.", selected["assessments"][0]["assessment"]["expected"])
        self.assertEqual(original, Path(response["working_path"]).read_bytes())
        self.assertFalse(self.controller.qa_finalize("qa-current", 1)["valid"])

    def test_group_retry_is_idempotent_but_stale_conflicting_revision_is_rejected(self):
        packet = {"expected_revision": 0, "assessments": [self.row()]}
        first = self.controller.qa_record("qa-current", packet)
        again = self.controller.qa_record("qa-current", packet)
        self.assertEqual(first["revision"], again["revision"])
        changed = self.row(); changed["assessment"]["observed"] = "Different later observation"
        rejected = self.controller.qa_record("qa-current", {"expected_revision": 0, "assessments": [changed]})
        self.assertFalse(rejected["valid"])
        self.assertEqual(1, self.controller.qa_read("qa-current")["revision"])

    def test_malformed_nested_rows_return_errors_without_partially_persisting_group(self):
        first = self.controller.qa_record("qa-current", {"expected_revision": 0, "assessments": [self.row()]})
        path = Path(first["working_path"])
        original = path.read_bytes()
        original_access = deepcopy(self.state["active_assignment"]["access"])
        cases = [
            (False, ("reason",), None), (False, ("reason",), []),
            (False, ("reason",), "invalid"), (True, ("evidence",), None),
            (True, ("evidence",), {}), (True, ("evidence",), [None]),
            (True, ("evidence",), [[]]), (True, ("evidence",), ["invalid"]),
            (False, ("evidence", 0, "ref"), None), (True, ("evidence", 0, "ref"), 1),
            (True, ("evidence", 0, "source"), None), (True, ("reason", "refs"), None),
            (True, ("reason", "repair"), None),
            (True, ("reason", "repair", "attempted_method_ids"), None),
        ]
        for is_gap, keys, value in cases:
            with self.subTest(gap=is_gap, keys=keys, value=value):
                row = self.gap() if is_gap else self.row()
                row["id"] = "reset"
                parent = row
                for key in keys[:-1]:
                    parent = parent[key]
                parent[keys[-1]] = value
                request = {"expected_revision": 1, "assessments": [self.row("core"), row]}
                submitted = deepcopy(request)
                result = self.controller.qa_record("qa-current", request)
                self.assertFalse(result["valid"])
                self.assertTrue(result["errors"])
                self.assertTrue(all(error["path"].startswith("/assessments/") for error in result["errors"]))
                self.assertEqual((1, 1, 2), (result["revision"], result["assessed"], result["pending"]))
                self.assertEqual(original, path.read_bytes())
                self.assertEqual(submitted, request)
                self.assertEqual(original_access, self.state["active_assignment"]["access"])
                self.assertFalse((path.parent / "qa-current.json").exists())

    def test_cli_malformed_nested_group_returns_validation_json_and_exit_two(self):
        from pipeline_v2.cli import main
        first = self.controller.qa_draft("qa-current")
        path = Path(first["working_path"])
        original = path.read_bytes()
        bad_reason = self.row(); bad_reason["reason"] = None
        bad_evidence = self.gap(); bad_evidence.update(id="reset", evidence=[None])
        request_path = self.root / "qa-group.json"
        write_json(request_path, {"expected_revision": 0, "assessments": [bad_reason, bad_evidence, self.row("core")]})
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch("pipeline_v2.cli.Controller", return_value=self.controller), redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--root", str(self.root), "--feature", "feature", "qa-record",
                         "--assignment-id", "qa-current", "--source", str(request_path)])
        response = json.loads(stdout.getvalue())
        self.assertEqual(2, code)
        self.assertEqual("", stderr.getvalue())
        self.assertFalse(response["valid"])
        self.assertEqual(2, len(response["errors"]))
        self.assertEqual((0, 0, 3), (response["revision"], response["assessed"], response["pending"]))
        self.assertEqual(original, path.read_bytes())
        self.assertFalse((path.parent / "qa-current.json").exists())

    def test_saved_generic_unfinished_mapping_cannot_become_engineering_repair(self):
        row = self.row()
        row.update(outcome="not_run", method_id=None,
                   evidence=[{"type": "verification-gap", "ref": "observed-action", "observation": "Related browser runs and/or the aggregate controller receipt exist, but this exact assertion has not been completely mapped to every required observation/evidence type and independently compared. No PASS is inferred."}],
                   reason={"kind": "verification_incomplete", "detail": "No complete assertion-level method evidence and independent comparison was recorded for this assertion.", "refs": ["observed-action"]})
        row["assessment"] = {"observed": "No complete assertion-level method evidence and independent comparison was recorded for this assertion.", "comparison": "insufficient"}
        result = self.controller.qa_record("qa-current", {"expected_revision": 0, "assessments": [row]})
        self.assertFalse(result["valid"])
        self.assertIn("concrete Engineering repair", str(result["errors"]))
        self.assertEqual(3, result["pending"])
        row["reason"]["repair"] = {"owner": "engineering", "target": "game.txt", "missing_obligation": "unmapped",
                                    "attempted_method_ids": ["observed-action"], "evidence_refs": ["observed-action"]}
        result = self.controller.qa_record("qa-current", {"expected_revision": 0, "assessments": [row]})
        self.assertFalse(result["valid"])
        self.assertIn("actual bound", str(result["errors"]))

    def test_specific_source_gap_and_mixed_external_wait_derive_fail_mechanically(self):
        result = self.controller.qa_record("qa-current", {"expected_revision": 0, "assessments": [self.gap(), self.row("reset"), self.external("core")]})
        self.assertTrue(result["valid"], result.get("errors"))
        finalized = self.controller.qa_finalize("qa-current", 1)
        self.assertTrue(finalized["valid"], finalized.get("errors"))
        artifact = read_json(Path(finalized["path"]))
        self.assertEqual("fail", artifact["outcome"])
        self.assertEqual("not_run", artifact["checks"][0]["assertions"][0]["outcome"])
        self.assertEqual("not_run", artifact["checks"][1]["outcome"])
        repair = artifact["checks"][0]["assertions"][0]["reason"]["repair"]
        self.assertEqual(["observed-action"], repair["attempted_method_ids"])
        self.assertEqual([source_reference(self.source())], repair["evidence_refs"])

    def test_external_only_finalizes_blocked_only_when_all_rows_assessed(self):
        response = self.controller.qa_record("qa-current", {"expected_revision": 0, "assessments": [self.external(key) for key in ("enter", "reset", "core")]})
        self.assertTrue(response["valid"])
        result = self.controller.qa_finalize("qa-current", 1)
        self.assertTrue(result["valid"], result.get("errors"))
        self.assertEqual("blocked", result["outcome"])
        self.assertFalse(result["semantic_credit"])

    def test_blocked_control_groups_reason_categories_without_losing_dependencies(self):
        definition = deepcopy(self.definition)
        definition["identities"][0]["assertions"][1]["depends_on"] = ["enter"]
        dependent, capability = self.external("reset"), self.external("core")
        dependent["reason"].update(kind="dependency_unsatisfied", refs=["enter"])
        capability["reason"].update(kind="capability_unavailable", refs=["interaction"])
        draft, errors, _ = prepare_update({"revision": 0, "assessments": {}}, definition,
            {"expected_revision": 0, "assessments": [self.external("enter"), dependent, capability]})
        self.assertEqual([], errors)
        artifact = assemble(draft, definition)
        validate_results(artifact["checks"], definition, outcome=artifact["outcome"], strict_gaps=True)
        self.assertEqual("blocked", artifact["outcome"])
        self.assertIn("capability_unavailable=1, dependency_unsatisfied=1, external_wait=1", artifact["blocker"])
        self.assertIn("3 unresolved assertions out of 3", artifact["blocker"])
        self.assertEqual(draft["assessments"]["reset"], artifact["checks"][0]["assertions"][1])
        self.assertEqual(["enter"], artifact["checks"][0]["assertions"][1]["reason"]["refs"])

    def test_large_blocked_assembly_and_public_step_keep_details_only_in_checks(self):
        from pipeline_v2.cli import main
        from pipeline_v2.model import next_action
        template = sample_contract()["slices"]["SLICE-001"]["identities"][0]["assertions"][0]
        definition, rows = {"identities": []}, {}
        for index in range(287):
            if index % 17 == 0:
                definition["identities"].append({"id": f"identity-{index // 17}", "source": "docs/plan.md#verification", "assertions": []})
            spec = deepcopy(template); spec["id"] = f"assertion-{index}"
            definition["identities"][-1]["assertions"].append(spec)
            row = {"id": spec["id"], "outcome": "pass", "method_id": "observed-action", "environment": "Bound observed fixture",
                   "evidence": [{"type": "observation", "ref": f"fixture:result-{index}", "observation": f"Exact observation {index}"}],
                   "assessment": {"expected": spec["expected"], "observed": f"Exact assessed result {index}", "comparison": "matches"}}
            if 76 <= index < 80:
                spec["applicability"] = {"kind": "conditional", "condition": "Approved fixture condition", "evidence_types": ["observation"]}
                row.update(outcome="not_applicable", method_id=None)
            elif index >= 80:
                row.update(outcome="not_run", method_id=None,
                    reason={"kind": "method_unavailable", "refs": ["observed-action"],
                            "detail": f"Exact method prerequisite {index}; " + "Preserved cause and actual producer gap. " * 20})
                row["evidence"][0]["type"] = "method-gap"
                row["assessment"]["comparison"] = "insufficient"
            rows[row["id"]] = row
        draft = {"binding": deepcopy(self.binding), "revision": 17, "assessments": rows}
        original = deepcopy(draft)
        artifact = assemble(draft, definition)
        validate_results(artifact["checks"], definition, outcome=artifact["outcome"], strict_gaps=True)
        self.assertEqual("blocked", artifact["outcome"])
        self.assertEqual(17, len(artifact["checks"]))
        self.assertEqual(rows, {row["id"]: row for check in artifact["checks"] for row in check["assertions"]})
        self.assertEqual(original, draft)
        self.assertIn("207 unresolved assertions out of 287 (method_unavailable=207)", artifact["blocker"])
        self.assertIn("checks[].assertions[]", artifact["blocker"])
        self.assertIn("checks[].assertions[]", artifact["required_action"])
        enlarged = deepcopy(draft)
        for row in enlarged["assessments"].values():
            if row["outcome"] == "not_run":
                row["reason"]["detail"] *= 3
                row["evidence"][0]["observation"] *= 3
        larger_artifact = assemble(enlarged, definition)
        for key in ("blocker", "required_action"):
            self.assertEqual(artifact[key], larger_artifact[key])
        self.assertEqual(enlarged["assessments"], {row["id"]: row for check in larger_artifact["checks"] for row in check["assertions"]})

        state = {**deepcopy(self.state), "active_assignment": None, "run_id": "run", "pipeline_runtime_digest": "b" * 64,
                 "artifacts": {"qa": {"assignment_id": "qa-current", "worker": artifact,
                    "controller": {"candidate_tree_oid": "c" * 40, "authority_digest": "a" * 64, "pipeline_runtime_digest": "b" * 64}}}}
        action = next_action(state)
        view = {"generation": state["generation"], "phase": "qa", "active_assignment": None, "next_action": action}
        controller = mock.Mock()
        controller.status.return_value = view
        controller.store.load.return_value = state
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch("pipeline_v2.cli.Controller", return_value=controller), redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--root", str(self.root), "--feature", "feature", "--brief", "step",
                         "--expected-generation", str(state["generation"]), "--action-id", action["command_id"], "--through-handoff"])
        response = json.loads(stdout.getvalue())
        self.assertEqual(0, code)
        self.assertEqual("", stderr.getvalue())
        self.assertEqual("stopped", response["result"])
        self.assertEqual("user_input_required", response["next_action"]["result"])
        self.assertEqual("recover-capability", response["next_action"]["command"])
        self.assertEqual(action["capability_binding"], response["next_action"]["capability_binding"])
        self.assertEqual(artifact["blocker"], response["next_action"]["blocker"])
        self.assertNotIn("Preserved cause", stdout.getvalue())
        self.assertNotIn("assertion-", stdout.getvalue())
        controller.next.assert_not_called()
        controller.complete.assert_not_called()
        controller.transition.assert_not_called()

    def test_candidate_or_contract_drift_never_resets_and_reuses_old_draft(self):
        response = self.controller.qa_record("qa-current", {"expected_revision": 0, "assessments": [self.row()]})
        original = Path(response["working_path"]).read_bytes()
        with self.assertRaises(PipelineError):
            load(self.state, self.root, {**self.binding, "candidate_tree_oid": "d" * 40}, create=True)
        self.assertEqual(original, Path(response["working_path"]).read_bytes())

    def test_terminal_cannot_override_or_outlive_the_current_working_assessment(self):
        self.controller.qa_record("qa-current", {"expected_revision": 0, "assessments": [self.row(key) for key in ("enter", "reset", "core")]})
        finalized = self.controller.qa_finalize("qa-current", 1)
        original = read_json(Path(finalized["path"]))
        changed = self.row(); changed["assessment"].update(comparison="contradicts", observed="Actual transition failed")
        self.assertTrue(self.controller.qa_record("qa-current", {"expected_revision": 1, "assessments": [changed]})["valid"])
        with self.assertRaisesRegex(PipelineError, "differs"):
            validate_projection(self.state, self.root, self.binding, original)
        self.assertEqual("fail", self.controller.qa_finalize("qa-current", 2)["outcome"])

    def set_producer(self, kind="tool", channel="cua-repl.chrome.extension"):
        method = self.definition["method_definitions"]["METHOD-fe82d465e8433451"]
        method["producer"] = ({"kind": kind, "channel": channel, "probe_ref": "execution-evidence:probe"} if kind != "controller_check"
                              else {"kind": "controller_check", "check_ids": ["native-check"]})
        self.state["execution"]["qa_contract_binding"]["contract_digest"] = contract_digest(self.contract)
        self.state["active_assignment"]["capsule"]["context"]["qa_contract"] = qa_contract_context(self.state)

    def test_saved_cua_vs_external_playwright_capture_is_not_promoted_by_compiler(self):
        self.set_producer()
        request = {"record_id": "layout", "invocation": {"channel": "external-playwright.chromium"},
                   "environment": {"browser": "Chrome"}, "input_paths": []}
        raw = self.root / "capture.bin"; raw.write_bytes(b"real observed layout capture")
        begin(self.root, "feature", request, self.binding)
        captured = capture(self.root, "feature", "layout", raw, request["environment"], self.binding)
        row = self.row(); row["evidence"][0]["ref"] = captured["ref"]
        result = self.controller.qa_record("qa-current", {"expected_revision": 0, "assessments": [row]})
        self.assertFalse(result["valid"])
        self.assertIn("external-playwright.chromium", str(result["errors"]))
        self.assertIn("cua-repl.chrome.extension", str(result["errors"]))
        self.assertEqual(0, result["assessed"])

    def test_source_cannot_replace_required_browser_or_native_producer(self):
        for kind in ("tool", "controller_check"):
            self.set_producer(kind)
            row = self.row(); row["evidence"] = [{"type": "observation", "source": self.source(), "observation": "Static code exists."}]
            result = self.controller.qa_record("qa-current", {"expected_revision": 0, "assessments": [row]})
            self.assertFalse(result["valid"])
            self.assertIn("cannot replace", str(result["errors"]))

    def test_source_hash_scope_and_repair_target_are_verified(self):
        for mutation in ("hash", "read", "target"):
            row = self.gap()
            if mutation == "hash": row["evidence"][0]["source"]["sha256"] = "0" * 64
            if mutation == "read": row["evidence"][0]["source"]["path"] = "outside.txt"
            if mutation == "target": row["reason"]["repair"]["target"] = "outside.txt"
            result = self.controller.qa_record("qa-current", {"expected_revision": 0, "assessments": [row]})
            self.assertFalse(result["valid"], mutation)
            self.assertEqual(0, result["assessed"])

    def test_source_locator_alone_does_not_impersonate_verified_source_metadata(self):
        row = self.row(); row["evidence"][0]["ref"] = source_reference(self.source())
        result = self.controller.qa_record("qa-current", {"expected_revision": 0, "assessments": [row]})
        self.assertFalse(result["valid"])
        self.assertIn("source-reader metadata", str(result["errors"]))


if __name__ == "__main__":
    unittest.main()
