"""Run only after writer freeze: real QA continuation and draft finalization."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest import mock

from pipeline_v2.model import WorkerArtifactValidationError
from pipeline_v2.tests import test_acceptance_integration as fixtures
from pipeline_v2.tests.test_qa_verification_gap import mark_gap


class QAWorkingNativeTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.AcceptanceIntegrationTests("runTest"); self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.h = self.f.h
        self.f.bind(); self.h._reach_engineering(); self.f.issue()
        self.f.submit({"outcome": "pass", "summary": "Current implementation."})
        self.h._accept("engineering"); self.f.issue()
        self.f.submit({"outcome": "pass", "findings": []})
        self.h._accept("review")
        self.active = self.f.issue()["active_assignment"]

    def rows(self):
        rows = [deepcopy(c["assertions"][0]) for c in fixtures.checks_for(self.f.contract)]
        for row in rows:
            row.pop("outcome")
            row["assessment"] = {"observed": "Actual fixture observation matches.", "comparison": "matches"}
        return rows

    def test_old_generic_gap_terminal_is_rejected_without_engineering_or_checks(self):
        checks = fixtures.checks_for(self.f.contract)
        mark_gap(checks[0])  # Preserved old format: no actionable owner/target/source.
        self.h._write_artifact({"outcome": "fail", "checks": checks})
        action = self.h.controller.status()["next_action"]
        before = self.h.store.path.read_bytes()
        with mock.patch("pipeline_v2.runner.run_process_tree") as process:
            with self.assertRaisesRegex(WorkerArtifactValidationError, "concrete Engineering repair"):
                self.h.controller.complete(command_id=action["command_id"], expected_generation=action["expected_generation"])
            process.assert_not_called()
        self.assertEqual(before, self.h.store.path.read_bytes())
        self.assertEqual("qa", self.h.controller.status()["phase"])
        self.assertEqual(self.active["id"], self.h.controller.status()["active_assignment"]["id"])

    def test_partial_group_survives_diagnostic_cursor_and_check_replay(self):
        controller, assignment = self.h.controller, self.active["id"]
        controller.qa_draft(assignment)
        rows = self.rows()
        recorded = controller.qa_record(assignment, {"expected_revision": 0, "assessments": rows[:1]})
        self.assertTrue(recorded["valid"], recorded.get("errors"))
        original = Path(recorded["working_path"]).read_bytes()
        before = self.h.store.load()
        packet = {"command_id": "draft-diagnostic", "expected_generation": before["generation"],
                  "assignment_id": assignment, "quiescence": "QA owns no ongoing product mutation."}
        controller.control_action("check", **packet)
        with mock.patch("pipeline_v2.runner.run_process_tree") as process:
            controller.control_action("check", **packet)
            resumed = controller.qa_read(assignment)
            refused = controller.qa_finalize(assignment, 1)
            process.assert_not_called()
        self.assertEqual(1, resumed["assessed"])
        self.assertEqual(1, resumed["pending"])
        self.assertEqual(original, Path(recorded["working_path"]).read_bytes())
        self.assertFalse(refused["valid"])
        self.assertTrue(controller.qa_record(assignment, {"expected_revision": 1, "assessments": rows[1:]})["valid"])
        finalized = controller.qa_finalize(assignment, 2)
        self.assertTrue(finalized["valid"], finalized.get("errors"))
        self.assertEqual("pass", finalized["outcome"])

    def test_prepared_first_group_records_and_resumes_without_executing_or_resetting(self):
        controller, assignment = self.h.controller, self.active["id"]
        rows = self.rows()
        identifiers = [row["id"] for row in rows]
        with mock.patch("pipeline_v2.runner.run_process_tree") as process:
            prepared = controller.qa_prepare(assignment, identifiers[:1], rows[0]["method_id"])
            self.assertFalse(Path(prepared["working_path"]).exists())
            self.assertFalse(controller.qa_record(assignment, prepared["record_request"])["valid"])
            prepared["record_request"]["assessments"][0].update(rows[0])
            first = controller.qa_record(assignment, prepared["record_request"])
            self.assertTrue(first["valid"], first.get("errors"))
            original = Path(first["working_path"]).read_bytes()
            resumed = controller.qa_prepare(assignment, identifiers, rows[0]["method_id"])
            self.assertEqual(1, resumed["revision"])
            self.assertEqual("recorded", resumed["prepared_methods"][0]["assessment_status"])
            self.assertEqual("pending", resumed["prepared_methods"][1]["assessment_status"])
            self.assertEqual(original, Path(first["working_path"]).read_bytes())
            self.assertFalse(controller.qa_finalize(assignment, 1)["valid"])
            process.assert_not_called()

    def test_specific_source_gap_and_external_remainder_finalize_then_route_engineering(self):
        controller, assignment = self.h.controller, self.active["id"]
        checks = fixtures.checks_for(self.f.contract)
        expected = self.f.contract["slices"]["SLICE-1"]["identities"][0]["assertions"][0]["expected"]
        mark_gap(checks[0], root=self.h.root, expected=expected)
        external = checks[1]["assertions"][0]
        external.update(outcome="not_run", method_id=None,
            assessment={"observed": "Named user has reserved this real session observation.", "comparison": "insufficient"},
            evidence=[{"type": "external-prerequisite", "ref": "user-decision:1", "observation": "External user action pending, no waiver."}],
            reason={"kind": "external_wait", "detail": "Named user provides the real session result.", "refs": ["owner-check"]})
        rows = [check["assertions"][0] for check in checks]
        result = controller.qa_record(assignment, {"expected_revision": 0, "assessments": rows})
        self.assertTrue(result["valid"], result.get("errors"))
        finalized = controller.qa_finalize(assignment, 1)
        self.assertTrue(finalized["valid"], finalized.get("errors"))
        self.assertEqual("fail", finalized["outcome"])
        action = controller.status()["next_action"]
        completed = controller.complete(command_id=action["command_id"], expected_generation=action["expected_generation"])
        self.assertEqual("engineering", completed["phase"])
        historical = self.f.issue()["active_assignment"]["capsule"]["context"]["qa_previous_observations"]
        self.assertEqual("tests/reset_test.py", historical["checks"][0]["assertions"][0]["reason"]["repair"]["target"])
        self.assertEqual("external_wait", historical["checks"][1]["assertions"][0]["reason"]["kind"])


if __name__ == "__main__":
    unittest.main()
