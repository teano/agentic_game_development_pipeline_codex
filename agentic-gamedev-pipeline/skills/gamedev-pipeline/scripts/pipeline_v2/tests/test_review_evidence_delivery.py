"""Read-only Review proof delivery and exact per-role finding navigation."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[2]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from pipeline_v2.delivery import export_assignment, read_delivery_unit
from pipeline_v2.execution import machine_check_inputs, receipt_binding
from pipeline_v2.finding_contract import required_condition_roster, required_conditions, normalized_record
from pipeline_v2.model import PipelineError, _active_assignment_view, artifact_schema, current_candidate, digest, status_view, validate_state


class ReviewEvidenceProjectionTests(unittest.TestCase):
    def test_receipt_projection_uses_exact_current_inputs_and_saved_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "check-tool"
            executable.write_bytes(b"exact executable bytes")
            dependency = root / "declared.input"
            dependency.write_text("input v1", encoding="utf-8")
            recipe = {"id": "rules", "argv": ["check-tool", "test"], "kind": "deterministic",
                      "timeout_seconds": 20, "independent": True, "input_paths": ["declared.input"]}
            state = {"project_root": str(root), "workflow_path": ".agentic-pipeline/Workflows/test",
                     "run_id": "RUN-1", "feature": "test", "authority": {"digest": "a" * 64},
                     "pipeline_runtime_digest": "b" * 64, "history": [],
                     "slices": [{"id": "S1", "allowed_paths": ["src/**"], "planned_commands": [recipe["argv"]]}],
                     "execution": {"verification": {"slices": {"S1": [recipe]}}, "receipts": {}}}
            tree, environment = "c" * 40, {"TEST_ENV": "exact"}
            result = {"check_id": "rules", "argv": recipe["argv"], "returncode": 0,
                      "stdout_sha256": "d" * 64, "stderr_sha256": "e" * 64,
                      "duration_ms": 123, "execution_reason": "new_input_binding"}
            with mock.patch("pipeline_v2.execution.shutil.which", return_value=str(executable)):
                binding = receipt_binding(state, tree, recipe, environment)
                state["execution"]["receipts"][binding] = {
                    "binding": binding, "id": "f" * 64, "result": result, "candidate_tree_oid": tree}
                # Simulate a persisted state, not a worker-authored context packet.
                saved = root / "saved-receipt-shape.json"
                saved.write_text(json.dumps(state), encoding="utf-8")
                restored = json.loads(saved.read_text(encoding="utf-8"))
                projected = machine_check_inputs(restored, tree, environment)
                self.assertEqual({
                    "candidate_tree_oid": tree, "authority_digest": "a" * 64,
                    "pipeline_runtime_digest": "b" * 64,
                    "checks": [{"id": "rules", "outcome": "pass", "receipt_id": "f" * 64,
                                "source_locator": f"{state['workflow_path']}/pipeline-state.json#/execution/receipts/{binding}",
                                "receipt_sha256": digest(result), "returncode": 0,
                                "stdout_sha256": "d" * 64, "stderr_sha256": "e" * 64}],
                    "pending_check_ids": [], "grants_manual_acceptance": False, "grants_semantic_credit": False,
                }, projected)
                self.assertEqual(state, restored)

                variants = []
                changed = deepcopy(state)
                changed["authority"]["digest"] = "1" * 64
                variants.append(("authority", changed, tree, environment))
                changed = deepcopy(state)
                changed["pipeline_runtime_digest"] = "2" * 64
                variants.append(("runtime", changed, tree, environment))
                changed = deepcopy(state)
                changed["execution"]["verification"]["slices"]["S1"][0]["argv"].append("new-scope")
                changed["slices"][0]["planned_commands"] = [changed["execution"]["verification"]["slices"]["S1"][0]["argv"]]
                variants.append(("command scope", changed, tree, environment))
                changed = deepcopy(state)
                changed["execution"]["verification"]["slices"]["S1"][0]["kind"] = "environment"
                variants.append(("environment-sensitive recipe", changed, tree, environment))
                variants.extend([("candidate", state, "3" * 40, environment),
                                 ("environment", state, tree, {"TEST_ENV": "changed"})])
                foreign_root = root / "foreign"
                foreign_root.mkdir()
                (foreign_root / "declared.input").write_bytes(dependency.read_bytes())
                changed = deepcopy(state)
                changed["project_root"] = str(foreign_root)
                variants.append(("foreign declared dependency root", changed, tree, environment))
                for label, changed, selected_tree, selected_environment in variants:
                    with self.subTest(binding=label):
                        actual = machine_check_inputs(changed, selected_tree, selected_environment)
                        self.assertEqual([], actual["checks"])
                        self.assertEqual(["rules"], actual["pending_check_ids"])
                dependency.write_text("input v2", encoding="utf-8")
                self.assertEqual([], machine_check_inputs(state, tree, environment)["checks"])
                dependency.write_text("input v1", encoding="utf-8")
                executable.write_bytes(b"changed executable")
                self.assertEqual([], machine_check_inputs(state, tree, environment)["checks"])

    def test_saved_partial_roster_uses_original_order_and_latest_independent_result(self):
        saved = {
            "open": {"F/~": {"id": "F/~", "text": "Original aggregate finding", "severity": "high", "kind": "acceptance",
                              "conditions": [{"id": "C2", "text": "Second ID comes first"},
                                             {"id": "C/~", "text": "Exact original condition 🌍\r\n"}]}},
            "resolved": [], "repeat_count": 1,
            "condition_status": {"F/~": {"C2": {"status": "resolved", "evidence": "Latest independent proof"},
                                            "C/~": {"status": "unresolved", "evidence": "Latest independent gap"}}},
            "engineering_resolutions": [{"finding_id": "F/~", "condition_id": "C/~", "status": "addressed",
                                         "evidence": "Engineer claim must not replace independent gap"}],
        }
        restored = json.loads(json.dumps(saved))
        expected = [
            {"finding_id": "F/~", "condition_id": "C2",
             "original_condition_pointer": "/assignment/context/convergence/open/F~1~0/conditions/0",
             "latest_independent_result_pointer": "/assignment/context/convergence/condition_status/F~1~0/C2"},
            {"finding_id": "F/~", "condition_id": "C/~",
             "original_condition_pointer": "/assignment/context/convergence/open/F~1~0/conditions/1",
             "latest_independent_result_pointer": "/assignment/context/convergence/condition_status/F~1~0/C~1~0"},
        ]
        self.assertEqual(expected, required_condition_roster(restored, "review"))
        self.assertEqual(expected[1:], required_condition_roster(restored, "engineering"))
        self.assertEqual(expected[1:], required_condition_roster(restored, "docs"))
        for phase in ("review", "engineering", "docs"):
            self.assertEqual(required_conditions(normalized_record(restored), phase),
                             {(row["finding_id"], row["condition_id"]) for row in required_condition_roster(restored, phase)})
        self.assertEqual(saved, restored)
        self.assertNotIn("Original aggregate", json.dumps(expected))
        self.assertNotIn("Latest independent", json.dumps(expected))
        self.assertEqual([], required_condition_roster(None, "review"))


class NativeReviewEvidenceDeliveryTests(unittest.TestCase):
    def setUp(self):
        from pipeline_v2.tests.test_execution_cycle import ExecutionCycleTests
        self.cycle = ExecutionCycleTests("runTest")
        self.cycle.setUp()
        self.addCleanup(self.cycle.tearDown)
        self.h = self.cycle.h
        self.cycle.restart(self.cycle.manifest(confirm=True))

    def candidate(self):
        self.cycle.issue()
        with mock.patch("pipeline_v2.runner.run_process_tree", return_value=self.cycle.passing()):
            self.h._complete("ENGINEERING-PROOF", {"outcome": "pass", "summary": "Implementation proof recorded."})
        self.h._accept("engineering-proof")
        return self.cycle.issue()

    def test_review_reads_existing_receipt_without_execution_or_state_access_and_new_run_drops_it(self):
        issued = self.candidate()
        active = issued["active_assignment"]
        self.assertEqual("review", active["phase"])
        before = self.h.store.path.read_bytes()
        with mock.patch("pipeline_v2.runner.run_process_tree", side_effect=AssertionError("Review must not execute checks")) as process:
            view = self.h.controller.status()
            assignment = view["active_assignment"]
            checks = assignment["context"]["machine_checks"]
            self.assertEqual([], assignment["checks"])
            self.assertEqual([], assignment["access"]["write"])
            self.assertNotIn(f"{self.h.workflow_path}/pipeline-state.json", assignment["access"]["read"])
            self.assertEqual(self.h.controller._machine_check_inputs(issued, current_candidate(issued)["candidate_tree_oid"]), checks)
            self.assertEqual(["check-0"], [row["id"] for row in checks["checks"]])
            self.assertEqual([], checks["pending_check_ids"])
            self.assertFalse(checks["grants_semantic_credit"])
            self.assertFalse(checks["grants_manual_acceptance"])
            exported = export_assignment(self.h.root, view)
            decoded = read_delivery_unit(self.h.root, self.h.workflow_path, exported["packet_digest"],
                                         "/assignment/context/machine_checks", "value")
            self.assertEqual(checks, decoded["value"])
            self.assertEqual(before, self.h.store.path.read_bytes())
            self.assertNotIn("machine_checks", issued["active_assignment"]["capsule"]["context"])
            with mock.patch("pipeline_v2.execution.execution_environment", return_value={"FOREIGN": "environment"}):
                stale = self.h.controller.status()["active_assignment"]["context"]["machine_checks"]
                self.assertEqual([], stale["checks"])
                self.assertEqual(["check-0"], stale["pending_check_ids"])
            foreign_candidate = deepcopy(issued)
            foreign_candidate["active_assignment"]["capsule"]["candidate"]["generation"] += 1
            self.assertNotIn("machine_checks", status_view(foreign_candidate)["active_assignment"]["context"])
            with self.assertRaisesRegex(PipelineError, "Engineering/QA"):
                self.cycle.action("check", "REVIEW-CANNOT-CHECK", assignment_id=active["id"], quiescence="No writer")
            process.assert_not_called()
        self.assertEqual(before, self.h.store.path.read_bytes())

        old_run = issued["run_id"]
        self.h.store.path.unlink()
        fresh = self.h.controller.reconfigure({"name": "init", "id": "NEW-RUN-PROOF", "expected_generation": None,
            "run_id": old_run + "-fresh", "feature": self.h.feature, "workflow_path": self.h.workflow_path,
            "project_root": str(self.h.root), "authority_paths": {"requirements": "requirements.md",
                "specification": "specification.md", "plan": "plan.md"}, "slices": self.h.slices,
            "verification": self.cycle.manifest(confirm=True)})
        self.assertNotEqual(old_run, fresh["run_id"])
        self.assertEqual({}, fresh["execution"]["receipts"])
        absent = self.h.controller._machine_check_inputs(fresh, current_candidate(issued)["candidate_tree_oid"])
        self.assertEqual([], absent["checks"])
        self.assertEqual(["check-0"], absent["pending_check_ids"])

    def test_native_partial_findings_expose_exact_role_roster_and_prior_qa_schema_remains_readable(self):
        self.candidate()
        finding = {"id": "F/~", "text": "Two original requirements", "severity": "high", "kind": "acceptance",
                   "conditions": [{"id": "C1", "text": "First original requirement"},
                                  {"id": "C/~", "text": "Second original requirement 🌍\r\n"}]}
        self.h._complete("REVIEW-ORIGINAL-FINDINGS", {"outcome": "fail", "findings": [finding], "finding_resolutions": []})
        engineering = self.cycle.issue()
        roster = self.h.controller.status()["active_assignment"]["context"]["required_finding_conditions"]
        self.assertEqual([("F/~", "C1"), ("F/~", "C/~")], [(row["finding_id"], row["condition_id"]) for row in roster])
        self.assertNotIn("required_finding_conditions", engineering["active_assignment"]["capsule"]["context"])
        self.h._complete("ENGINEERING-CLAIMS", {"outcome": "pass", "summary": "Both conditions addressed."})
        self.h._accept("engineering-claims")
        self.cycle.issue()
        rows = [{"finding_id": "F/~", "condition_id": "C1", "status": "resolved", "evidence": "Independent verified first condition"},
                {"finding_id": "F/~", "condition_id": "C/~", "status": "unresolved", "evidence": "Independent latest remaining gap"}]
        self.h._complete("REVIEW-PARTIAL", {"outcome": "fail", "findings": [], "finding_resolutions": rows})
        self.cycle.issue()
        view = self.h.controller.status()
        roster = view["active_assignment"]["context"]["required_finding_conditions"]
        self.assertEqual([("F/~", "C/~")], [(row["finding_id"], row["condition_id"]) for row in roster])
        # Docs uses the same existing repair-claim coverage rule. Exercise the
        # public projection against a saved capsule shape without issuing work.
        saved_partial = json.loads(self.h.store.path.read_bytes())
        docs_capsule = deepcopy(saved_partial["active_assignment"])
        docs_capsule.update({"phase": "docs", "role": "documentation_finisher"})
        docs_view = _active_assignment_view(saved_partial, docs_capsule)
        self.assertEqual(roster, docs_view["context"]["required_finding_conditions"])
        self.assertNotIn("machine_checks", docs_view["context"])
        exported = export_assignment(self.h.root, view)
        required = read_delivery_unit(self.h.root, self.h.workflow_path, exported["packet_digest"],
                                     "/assignment/context/required_finding_conditions", "unit")
        self.assertEqual("F/~", required["children"][0]["finding_id"])
        self.assertEqual("C/~", required["children"][0]["condition_id"])
        for field, expected in (("original_condition_pointer", finding["conditions"][1]),
                                ("latest_independent_result_pointer", {"status": "unresolved", "evidence": rows[1]["evidence"]})):
            self.assertEqual(expected, read_delivery_unit(self.h.root, self.h.workflow_path, exported["packet_digest"], roster[0][field], "value")["value"])
        self.h._complete("ENGINEERING-REMAINING", {"outcome": "pass", "summary": "Remaining condition addressed."})
        self.h._accept("engineering-remaining")
        self.cycle.issue()
        review = self.h.controller.status()["active_assignment"]
        self.assertEqual(["C1", "C/~"], [row["condition_id"] for row in review["context"]["required_finding_conditions"]])
        self.assertEqual("Independent latest remaining gap", review["context"]["convergence"]["condition_status"]["F/~"]["C/~"]["evidence"])
        self.h._complete("REVIEW-ALL-RESOLVED", {"outcome": "pass", "findings": []})
        self.h._accept("review-all-resolved")
        issued = self.cycle.issue()
        self.assertEqual("qa", issued["active_assignment"]["phase"])
        self.assertNotIn("required_finding_conditions", status_view(issued)["active_assignment"]["context"])
        schema = artifact_schema("qa", "qa")
        self.assertTrue(schema["item_shapes"]["checks[]"]["evidence"].startswith("non-empty string"))
        self.assertIn("evidence[]", schema["item_shapes"]["checks[]"]["assertions"])
        saved = json.loads(json.dumps(issued))
        saved["active_assignment"]["artifact_schema"]["item_shapes"]["checks[]"]["evidence"] = (
            "non-empty observed execution evidence; distinguish the actual integration from substitutes")
        validate_state(saved)
        self.assertEqual(schema, status_view(saved)["active_assignment"]["artifact_schema"])
        saved["active_assignment"]["artifact_schema"]["item_shapes"]["checks[]"]["evidence"] = "array of evidence"
        with self.assertRaises(PipelineError):
            validate_state(saved)


if __name__ == "__main__":
    unittest.main()
