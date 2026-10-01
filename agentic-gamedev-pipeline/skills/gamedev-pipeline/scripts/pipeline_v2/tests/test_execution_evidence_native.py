"""Run after the collective writer freeze: native candidate/authority evidence."""
from copy import deepcopy
from dataclasses import replace
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
import unittest
from unittest import mock

from pipeline_v2.checkout import candidate_tree_oid
from pipeline_v2.model import PipelineError
from pipeline_v2.tests import test_acceptance_integration as fixtures


class EvidenceNativeTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.AcceptanceIntegrationTests("runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.h = self.f.h

    def fast_init(self, contract):
        return self.h.controller.reconfigure({"name": "init", "id": "fast-init", "run_id": "RUN-TEST",
            "feature": self.h.feature, "workflow_path": self.h.workflow_path, "project_root": str(self.h.root),
            "authority_paths": {"requirements": "requirements.md", "specification": "specification.md", "plan": "plan.md"},
            "slices": self.h.slices, "qa_contract": contract,
            "verification": {"version": 1, "confirm_approved_plan": True, "pure_documentation_paths": [],
                "slices": {"SLICE-1": [{"id": "build-only", "argv": self.h.command, "kind": "environment",
                                        "timeout_seconds": 10, "independent": False}]}}})

    def tool_contract(self):
        result = deepcopy(self.f.contract)
        for identity in result["slices"]["SLICE-1"]["identities"]:
            identity["assertions"][0]["methods"][0]["producer"] = {
                "kind": "tool", "channel": "fixture-observer", "probe_ref": "execution-evidence:route-probe"}
        return result

    def test_qa_prepare_cli_preserves_issued_receipt_across_reader_environment_change(self):
        from pipeline_v2.cli import main
        from pipeline_v2.execution import machine_check_inputs, execution_environment, recipe_for
        state = self.h.store.load()
        check_id = recipe_for(state, self.h.command, 0, 30)["id"]
        contract = deepcopy(self.f.contract)
        assertion = contract["slices"]["SLICE-1"]["identities"][0]["assertions"][0]
        method = assertion["methods"][0]
        method.update(evidence_types=["controller-check-receipt"], producer={"kind": "controller_check", "check_ids": [check_id]})
        # A contract-only rebind retains verification recipes. Initialize this
        # temporary fixture with deterministic semantics for its actual check.
        self.h.store.path.unlink()
        initialized = self.h.controller.reconfigure({"name": "init", "id": "bind-native-method",
            "run_id": state["run_id"], "feature": state["feature"], "workflow_path": state["workflow_path"], "project_root": state["project_root"],
            "authority_paths": {key: value["path"] for key, value in state["authority"]["items"].items()},
            "slices": self.h.slices, "qa_contract": contract,
            "verification": {"version": 1, "confirm_approved_plan": True, "pure_documentation_paths": [], "slices": {
                "SLICE-1": [{"id": check_id, "argv": self.h.command, "kind": "deterministic", "timeout_seconds": 30, "independent": False, "input_paths": []}]}}})
        self.assertEqual("engineering", initialized["phase"])
        self.assertEqual(check_id, recipe_for(initialized, self.h.command, 0, 30)["id"])
        self.f.issue()
        self.f.submit({"outcome": "pass", "summary": "Actual native fixture check completed."})
        self.h._accept("engineering"); self.f.issue()
        self.f.submit({"outcome": "pass", "findings": []})
        self.h._accept("review"); self.f.issue()
        state = self.h.store.load()
        active = state["active_assignment"]
        issued = active["capsule"]["context"]["machine_checks"]
        self.assertEqual([], issued["pending_check_ids"])
        original = self.h.store.path.read_bytes()
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"QA_READ_ONLY_ENV_VARIANT": "different-reader-process"}), mock.patch("pipeline_v2.runner.run_process_tree") as process:
            reusable = machine_check_inputs(state, issued["candidate_tree_oid"], execution_environment())
            self.assertEqual([check_id], reusable["pending_check_ids"])
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main(["--root", str(self.h.root), "--feature", self.h.feature, "qa-prepare", "--assignment-id", active["id"],
                             "--assertion-id", assertion["id"], "--method-id", method["id"], "--format", "json", "--assemble"])
            process.assert_not_called()
        self.assertEqual((0, ""), (code, stderr.getvalue()))
        result = json.loads(stdout.getvalue())["value"]
        self.assertEqual("receipts_available", result["producer_context"][0]["prerequisite"]["status"])
        self.assertEqual(issued["checks"], result["producer_context"][0]["receipts"])
        self.assertEqual(issued["checks"][0]["execution_evidence"], result["record_request"]["assessments"][0]["evidence"][0]["ref"])
        self.assertEqual(original, self.h.store.path.read_bytes())
        self.assertIsNone(result["record_request"]["assessments"][0]["assessment"]["comparison"])
        self.assertFalse(result["semantic_credit"])
        # A real later diagnostic publishes a new observation in the same assignment.
        with mock.patch.dict(os.environ, {"QA_DIAGNOSTIC_ENV_VARIANT": "new-real-check"}):
            state = self.h.controller.control_action("check", command_id="qa-diagnostic-new-observation",
                expected_generation=state["generation"], assignment_id=active["id"], quiescence="No product writer or external session is active.")
        latest = state["active_assignment"]["capsule"]["context"]["machine_checks"]
        self.assertNotEqual(issued["checks"][0]["execution_evidence"], latest["checks"][0]["execution_evidence"])
        diagnostic_state = self.h.store.path.read_bytes()
        with mock.patch("pipeline_v2.runner.run_process_tree") as process:
            prepared = self.h.controller.qa_prepare(active["id"], [assertion["id"]], method["id"])
            process.assert_not_called()
        self.assertEqual(latest["checks"], prepared["producer_context"][0]["receipts"])
        self.assertEqual(diagnostic_state, self.h.store.path.read_bytes())

    def test_preinit_tool_probe_allows_fastpath_without_native_probe_assignment(self):
        self.h.store.path.unlink()
        before = candidate_tree_oid(self.h.root)
        request = {"record_id": "route-probe", "preflight": True, "project_root": str(self.h.root),
                   "feature": self.h.feature, "authority_paths": {"requirements": "requirements.md", "specification": "specification.md", "plan": "plan.md"},
                   "invocation": {"channel": "fixture-observer", "action": "read-current-capability"},
                   "environment": {"session": "fixture", "version": 1}, "input_paths": []}
        self.h.controller.evidence_begin(request)
        raw = self.h.store.path.parent / "probe-response.bin"
        raw.write_bytes(b'{"actual_tool_result":"readable"}\r\n')
        self.h.controller.evidence_record("route-probe", raw, request["environment"])
        self.assertFalse(self.h.store.path.exists())
        self.assertEqual(before, candidate_tree_oid(self.h.root))
        state = self.fast_init(self.tool_contract())
        self.assertEqual("engineering", state["phase"])
        self.assertFalse(self.h.controller.status()["ready"])
        # Producer route probes remain applicable across product-tree changes,
        # but an altered producer runtime/source/input binding is rejected.
        record_path = self.h.store.path.parent / "Evidence/route-probe/result.bin"
        record_path.write_bytes(b"tampered")
        action = self.h.controller.status()["next_action"]
        with self.assertRaisesRegex(PipelineError, "producer alternatives"):
            self.h.controller.next(command_id=action["command_id"], expected_generation=action["expected_generation"])

    def test_fastpath_receipt_without_producer_is_rejected_before_engineering(self):
        self.h.store.path.unlink()
        contract = deepcopy(self.f.contract)
        contract["slices"]["SLICE-1"]["identities"][0]["assertions"][0]["methods"][0]["evidence_types"] = ["bound-machine-receipt"]
        with self.assertRaisesRegex(PipelineError, "producer mismatch before Engineering"):
            self.fast_init(contract)
        self.assertFalse(self.h.store.path.exists())

    def test_normal_slice_accept_rechecks_probe_before_engineering(self):
        request = {"record_id": "route-probe", "preflight": True, "project_root": str(self.h.root),
                   "feature": self.h.feature, "authority_paths": {"requirements": "requirements.md", "specification": "specification.md", "plan": "plan.md"},
                   "invocation": {"channel": "fixture-observer", "action": "read-current-capability"},
                   "environment": {"session": "fixture", "version": 1}, "input_paths": []}
        self.h.controller.evidence_begin(request)
        raw = self.h.store.path.parent / "probe-response.bin"
        raw.write_bytes(b'{"actual_tool_result":"readable"}\r\n')
        self.h.controller.evidence_record("route-probe", raw, request["environment"])
        self.f.bind(self.tool_contract())
        self.f.issue()
        self.f.submit({"outcome": "pass", "summary": "Approved plan and usable declared producer route."})
        self.h._accept("normal-plan")
        self.f.issue()
        self.f.submit({"outcome": "pass", "summary": "Slice confirmed before implementation."})
        (self.h.store.path.parent / "Evidence/route-probe/result.bin").write_bytes(b"corrupted after slice confirmation")
        before = self.h.store.path.read_bytes()
        action = self.h.controller.status()["next_action"]
        with self.assertRaisesRegex(PipelineError, "producer alternatives"):
            self.h.controller.transition({"name": "accept", "id": action["command_id"],
                                          "expected_generation": action["expected_generation"]})
        self.assertEqual(before, self.h.store.path.read_bytes())
        self.assertEqual("slice", self.h.store.load()["phase"])
        self.assertIsNone(self.h.store.load()["active_assignment"])

    def test_external_only_qa_stays_blocked_in_qa(self):
        self.f.bind()
        self.h._reach_engineering()
        self.f.issue()
        self.f.submit({"outcome": "pass", "summary": "Implemented."})
        self.h._accept("engineering")
        self.f.issue()
        self.f.submit({"outcome": "pass", "findings": []})
        self.h._accept("review")
        self.f.issue()
        checks = fixtures.checks_for(self.f.contract)
        row = checks[1]["assertions"][0]
        row.update(outcome="not_run", method_id=None,
                   reason={"kind": "external_wait", "detail": "Assigned human observation is pending under decision-1.", "refs": ["decision-1"]},
                   evidence=[{"type": "external-prerequisite", "ref": "decision:1", "observation": "User owns pending external observation; no waiver."}])
        checks[1]["outcome"] = "not_run"
        state = self.f.submit({"outcome": "blocked", "checks": checks, "blocker": "External observation pending.",
                               "required_action": "Owner provides the exact approved observation."})
        self.assertEqual("qa", state["phase"])
        self.assertIsNone(state["active_assignment"])
        self.assertEqual("recover-capability", self.h.controller.status()["next_action"]["command"])

    def test_writer_is_bound_and_native_stream_record_does_not_change_candidate(self):
        self.f.bind()
        self.h._reach_engineering()
        issued = self.f.issue()["active_assignment"]
        source = self.h.store.path.parent / "draft.json"
        source.write_text(json.dumps({"outcome": "pass", "summary": "Unicode ☃" * 30000}), encoding="utf8")
        before = candidate_tree_oid(self.h.root)
        with self.assertRaisesRegex(PipelineError, "assignment_id"):
            self.h.controller.artifact_write(source, assignment_id="old-owner")
        result = self.h.controller.artifact_write(source, assignment_id=issued["id"])
        self.assertTrue(result["valid"])
        self.assertEqual(before, candidate_tree_oid(self.h.root))
        action = self.h.controller.status()["next_action"]
        state = self.h.controller.complete(command_id=action["command_id"], expected_generation=action["expected_generation"])
        command_result = state["artifacts"]["engineering"]["controller"]["commands"][0]
        record_id = command_result["execution_evidence"].partition(":")[2]
        record = self.h.controller.evidence_read(record_id)["record"]
        self.assertTrue(record["capture_complete"])
        self.assertEqual(before, candidate_tree_oid(self.h.root))

    def test_feasibility_is_retained_in_actual_issued_capsule_and_export(self):
        from pipeline_v2.delivery import export_assignment, read_delivery_unit
        self.f.bind()
        issued = self.f.issue()
        expected = issued["active_assignment"]["capsule"]["context"]["verification_feasibility"]
        self.assertEqual("legacy_unverified", expected["status"])
        view = self.h.controller.status()
        packet = export_assignment(self.h.root, view)
        restored = read_delivery_unit(self.h.root, self.h.workflow_path, packet["packet_digest"],
                                      "/assignment/context/verification_feasibility", "value")
        self.assertEqual(expected, restored["value"])

    def test_native_capture_failure_commits_attempt_and_same_id_replay_runs_once(self):
        import pipeline_v2.runner as runner
        self.f.bind()
        self.h._reach_engineering()
        issued = self.f.issue()
        active = issued["active_assignment"]
        real = runner.run_process_tree
        calls = []

        def failed_sink(*args, **kwargs):
            result = real(*args, **kwargs)
            calls.append(result.returncode)
            return replace(result, capture_error="injected write failure after actual process exit")

        with mock.patch.object(runner, "run_process_tree", side_effect=failed_sink):
            arguments = {"command_id": "same-capture-failure", "expected_generation": issued["generation"],
                         "assignment_id": active["id"], "quiescence": "No writer or external action is active."}
            first = self.h.controller.control_action("check", **arguments)
            second = self.h.controller.control_action("check", **arguments)
        self.assertEqual([0], calls)
        self.assertEqual(first, second)
        event = next(row for row in first["history"] if row["id"] == "same-capture-failure")
        anchor = event["execution_records"][0]
        self.assertEqual(125, anchor["returncode"])
        record = self.h.controller.evidence_read(anchor["ref"].partition(":")[2])["record"]
        self.assertFalse(record["capture_complete"])
        self.assertEqual(0, record["result"]["process_returncode"])

    def test_mixed_qa_residual_survives_changed_engineer_review_and_next_qa(self):
        self.f.bind()
        self.h._reach_engineering()
        self.f.issue()
        self.f.submit({"outcome": "pass", "summary": "Initial implementation."})
        self.h._accept("engineering-initial")
        self.f.issue()
        self.f.submit({"outcome": "pass", "findings": []})
        self.h._accept("review-initial")
        self.f.issue()
        checks = fixtures.checks_for(self.f.contract)
        from pipeline_v2.tests.test_qa_verification_gap import mark_gap
        mark_gap(checks[0], root=self.h.root,
                 expected=self.f.contract["slices"]["SLICE-1"]["identities"][0]["assertions"][0]["expected"])
        external = checks[1]["assertions"][0]
        external.update(outcome="not_run", method_id=None,
            reason={"kind": "external_wait", "detail": "Named user still owes the approved two-actor observation.", "refs": ["owner-observation"]},
            evidence=[{"type": "external-prerequisite", "ref": "user-decision:1", "observation": "Observation deferred to the named user, without waiving acceptance."}])
        checks[1]["outcome"] = "not_run"
        failed = self.f.submit({"outcome": "fail", "checks": checks})
        old_qa = deepcopy(failed["artifacts"]["qa"])
        self.assertEqual("engineering", failed["phase"])
        engineer = self.f.issue()["active_assignment"]
        self.assertEqual(checks, engineer["capsule"]["context"]["qa_previous_observations"]["checks"])
        # Only the executable gap is addressed. The external action remains open.
        (self.h.root / "game.txt").write_text("partial remediation: reset observation\n", encoding="utf8")
        self.f.submit({"outcome": "pass", "summary": "Addressed executable gap; external observation still pending."})
        self.h._accept("engineering-partial")
        review_state = self.f.issue()
        review = review_state["active_assignment"]
        history = review["capsule"]["context"]["qa_previous_observations"]
        self.assertEqual(old_qa["candidate_binding"], history["candidate_binding"])
        self.assertNotEqual(history["candidate_binding"], review["capsule"]["candidate"])
        self.assertEqual(checks, history["checks"])
        self.assertFalse(history["grants_credit"])
        self.assertFalse(history["complete_inventory"])
        self.assertIn("/history/", history["source_locator"])
        archived = next(row["prior_artifacts"]["qa"] for row in review_state["history"] if row.get("prior_artifacts", {}).get("qa") == old_qa)
        self.assertEqual(old_qa, archived)
        self.assertNotIn("qa", review_state["artifacts"])
        self.f.submit({"outcome": "pass", "findings": []})
        self.h._accept("review-remediation")
        next_qa = self.f.issue()["active_assignment"]
        pending = next_qa["capsule"]["context"]["qa_previous_observations"]
        self.assertEqual(checks, pending["checks"])
        required = next_qa["capsule"]["context"]["qa_contract"]["definition"]["identities"]
        self.assertIn(external["id"], [a["id"] for identity in required for a in identity["assertions"]])
        revised = fixtures.checks_for(self.f.contract)
        revised[1] = deepcopy(checks[1])
        blocked = self.f.submit({"outcome": "blocked", "checks": revised,
                                "blocker": "Only the user's external observation remains.",
                                "required_action": "Obtain that exact observation, then reassess QA."})
        self.assertEqual("qa", blocked["phase"])
        self.assertFalse(self.h.controller.status()["ready"])


if __name__ == "__main__":
    unittest.main()
