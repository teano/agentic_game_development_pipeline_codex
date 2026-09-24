"""Native controller coverage for structured acceptance and finding closure."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline_v2.tests import test_core as fixtures
from pipeline_v2.model import PipelineError, current_candidate, qa_credit_complete, qa_contract_context


def contract_for(h):
    slices = {}
    for selected in h.slices:
        identities = []
        for prefix, suffix in (("AUTO", "CORE"), ("MANUAL", "RUNTIME")):
            identity = f"{prefix}-{selected['id']}-{suffix}"
            identities.append({"id": identity, "source": "plan.md#test-plan", "assertions": [{
                "id": identity + "-OBSERVE", "expected": "Observe the assigned result.",
                "methods": [{"id": "observed-action", "source": "requirements.md#acceptance-criteria",
                    "description": "Act through the assigned integration and observe the result.",
                    "capabilities": ["interaction"], "evidence_types": ["observation"]}],
                "applicability": {"kind": "always", "condition": "always", "evidence_types": []},
                "depends_on": []}]})
        slices[selected["id"]] = {"identities": identities}
    return {"schema": 1, "confirm_approved_plan": True, "slices": slices}


def checks_for(contract):
    selected = next(iter(contract["slices"].values()))
    return [{"id": item["id"], "outcome": "pass", "evidence": "Assigned result observed.",
             "assertions": [{"id": row["id"], "outcome": "pass", "method_id": "observed-action",
                 "environment": "Fixture integration session 1", "evidence": [{"type": "observation",
                 "ref": "fixture:observed-action", "observation": "Actual result matches the approved result."}]}
                 for row in item["assertions"]]} for item in selected["identities"]]


class AcceptanceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.h = fixtures.PipelineV2CoreTests("runTest")
        self.h.include_qa_contract = False
        self.h.setUp()
        self.addCleanup(self.h.tearDown)
        self.contract = contract_for(self.h)

    def issue(self):
        action = self.h.controller.status()["next_action"]
        return self.h.controller.next(command_id=action["command_id"], expected_generation=action["expected_generation"])

    def bind(self, contract=None):
        state = self.h.store.load()
        return self.h.controller.reconfigure({"name": "init", "id": "bind-qa-" + str(state["generation"]),
            "expected_generation": state["generation"], "run_id": state["run_id"], "feature": state["feature"],
            "workflow_path": state["workflow_path"], "project_root": state["project_root"],
            "authority_paths": {key: value["path"] for key, value in state["authority"]["items"].items()},
            "slices": state["slices"], "qa_contract": self.contract if contract is None else contract})

    def submit(self, artifact):
        self.h._write_artifact(artifact)
        action = self.h.controller.status()["next_action"]
        return self.h.controller.complete(command_id=action["command_id"], expected_generation=action["expected_generation"])

    def rejected_without_execution(self, artifact, pattern):
        before = self.h.store.path.read_bytes()
        with mock.patch("pipeline_v2.runner.run_process_tree") as process:
            with self.assertRaisesRegex(PipelineError, pattern):
                self.submit(artifact)
            process.assert_not_called()
        self.assertEqual(before, self.h.store.path.read_bytes())

    def test_bound_contract_is_shared_and_incomplete_qa_rejected_before_checks(self):
        sources = {p: (self.h.root / p).read_bytes() for p in ("requirements.md", "specification.md", "plan.md")}
        self.bind()
        self.h._reach_engineering()
        engineering = self.issue()["active_assignment"]
        definition = engineering["capsule"]["context"]["qa_contract"]
        self.assertEqual("bound", definition["status"])
        (self.h.root / "game.txt").write_text("candidate\n", encoding="utf-8")
        self.submit({"outcome": "pass", "summary": "Implemented the approved behavior."})
        self.h._accept("engineering")
        review = self.issue()["active_assignment"]
        self.assertEqual(definition, review["capsule"]["context"]["qa_contract"])
        self.submit({"outcome": "pass", "findings": []})
        self.h._accept("review")
        qa = self.issue()["active_assignment"]
        self.assertEqual(definition, qa["capsule"]["context"]["qa_contract"])
        checks = checks_for(self.contract)
        incomplete = deepcopy(checks)
        incomplete[0]["assertions"] = []
        self.rejected_without_execution({"outcome": "pass", "checks": incomplete}, "assertion")
        wrong = deepcopy(checks)
        wrong[0]["assertions"][0]["method_id"] = "invented-equivalence"
        self.rejected_without_execution({"outcome": "pass", "checks": wrong}, "method")
        result = self.submit({"outcome": "pass", "checks": checks})
        self.assertTrue(qa_credit_complete(result["artifacts"]["qa"]))
        for path, original in sources.items():
            self.assertEqual(original, (self.h.root / path).read_bytes())
        self.h._accept("qa")
        self.h._docs_no_change("docs")
        state = self.h.store.load()
        final = self.h.controller.ready(command_id="ready-structured", expected_generation=state["generation"])
        self.assertTrue(self.h.controller.status()["ready"])

    def test_shared_methods_remain_compact_through_native_assignment_and_acceptance(self):
        definition = self.contract["slices"]["SLICE-1"]
        common = deepcopy(definition["identities"][0]["assertions"][0]["methods"][0])
        definition["method_definitions"] = {"shared-observation": common}
        for identity in definition["identities"]:
            for assertion in identity["assertions"]:
                self.assertEqual([common], assertion["methods"])
                assertion["methods"] = [{"ref": "shared-observation"}]
        self.test_bound_contract_is_shared_and_incomplete_qa_rejected_before_checks()
        retained = self.h.store.load()["execution"]["qa_contract"]["slices"]["SLICE-1"]
        self.assertEqual([{"ref": "shared-observation"}], retained["identities"][0]["assertions"][0]["methods"])

    def test_missing_contract_blocks_credit_and_idle_binding_preserves_candidate(self):
        candidate = self.h._reach_candidate()
        self.h._review_pass("review-legacy")
        self.issue()
        self.rejected_without_execution({"outcome": "pass", "checks": self.h._qa_checks("legacy prose")}, "contract is unresolved")
        blocked = self.submit({"outcome": "blocked", "checks": [], "blocker": "QA methods are not bound.", "required_action": "Bind methods from approved sources."})
        self.assertFalse(qa_credit_complete(blocked["artifacts"]["qa"]))
        rebound = self.bind()
        self.assertEqual("review", rebound["phase"])
        self.assertEqual(candidate, current_candidate(rebound))
        self.assertNotIn("qa", rebound["artifacts"])
        self.assertFalse(any(key.startswith("TD-BLOCK") for key in rebound.get("technical_decisions", {})))
        self.assertIn("qa", rebound["history"][-1]["prior_artifacts"])

    def test_contract_cannot_change_in_flight_or_override_source_inventory(self):
        self.bind()
        self.h._reach_candidate()
        self.issue()
        changed = deepcopy(self.contract)
        changed["slices"]["SLICE-1"]["identities"][0]["assertions"][0]["methods"][0]["description"] += " changed"
        before = self.h.store.path.read_bytes()
        with self.assertRaisesRegex(PipelineError, "active assignment"):
            self.bind(changed)
        self.assertEqual(before, self.h.store.path.read_bytes())

    def test_compound_findings_require_all_six_conditions_and_independent_closure(self):
        self.bind()
        self.h._reach_candidate()
        self.issue()
        finding = {"id": "REVIEW-M3-002", "text": "Six mandatory scenarios are unexecuted.", "severity": "high", "kind": "correctness",
                   "conditions": [{"id": f"C{i}", "text": f"Execute approved scenario {i}."} for i in range(1, 7)]}
        self.submit({"outcome": "fail", "findings": [finding]})
        self.issue()
        rows = [{"finding_id": finding["id"], "condition_id": f"C{i}", "status": "addressed", "evidence": f"Executed scenario {i}: fixture:case-{i}"} for i in range(1, 7)]
        self.rejected_without_execution({"outcome": "pass", "summary": "Only first repaired", "finding_resolutions": rows[:1]}, "exact assigned conditions")
        self.submit({"outcome": "pass", "summary": "All scenarios executed", "finding_resolutions": rows})
        self.h._accept("repair")
        review = self.issue()["active_assignment"]
        self.assertEqual(rows, review["capsule"]["context"]["convergence"]["engineering_resolutions"])
        self.rejected_without_execution({"outcome": "pass", "findings": []}, "exact assigned conditions")
        self.rejected_without_execution({"outcome": "fail", "findings": [], "finding_resolutions": None}, "must be a list")
        review_rows = [{**row, "status": "resolved" if i == 0 else "unresolved"} for i, row in enumerate(rows)]
        partial = self.submit({"outcome": "fail", "findings": [], "finding_resolutions": review_rows})
        self.assertEqual(finding["conditions"], partial["artifacts"]["review"]["worker"]["findings"][0]["conditions"])
        self.issue()
        self.submit({"outcome": "pass", "summary": "Remaining five repaired", "finding_resolutions": rows[1:]})
        self.h._accept("remaining-repair")
        self.issue()
        closed = self.submit({"outcome": "pass", "findings": [], "finding_resolutions": [{**row, "status": "resolved"} for row in rows]})
        self.assertEqual([], closed["artifacts"]["review"]["worker"]["findings"])

    def test_contract_rebind_cannot_keep_completed_slice_credit_for_changed_methods(self):
        self.h.slices.append({**deepcopy(self.h.slices[0]), "id": "SLICE-2"})
        self.h._write_approved_plan(self.h.slices)
        self.h._commit_fixture_and_restart("two approved slices")
        self.contract = contract_for(self.h)
        self.bind()
        self.h._reach_candidate()
        self.h._review_pass("first-review")
        self.issue()
        self.submit({"outcome": "pass", "checks": checks_for(self.contract)})
        self.h._accept("first-qa")
        if self.h.store.load()["phase"] == "docs":
            self.h._docs_no_change("first-docs")
        changed = deepcopy(self.contract)
        changed["slices"]["SLICE-1"]["identities"][0]["assertions"][0]["expected"] = "Different approved interpretation"
        before = self.h.store.path.read_bytes()
        with self.assertRaisesRegex(PipelineError, "completed slices"):
            self.bind(changed)
        self.assertEqual(before, self.h.store.path.read_bytes())
        future_only = deepcopy(self.contract)
        future_only["slices"]["SLICE-2"]["identities"][0]["assertions"][0]["methods"][0]["description"] += " Retain this approved method in the next slice."
        prior_phase = self.h.store.load()["phase"]
        rebound = self.bind(future_only)
        self.assertEqual("engineering", prior_phase)
        self.assertEqual(prior_phase, rebound["phase"], "A previous slice candidate cannot skip the next slice's Engineering")

    def test_bound_blocked_qa_still_requires_every_independent_result(self):
        self.bind()
        self.h._reach_candidate()
        self.h._review_pass("review")
        self.issue()
        checks = checks_for(self.contract)
        first = checks[0]["assertions"][0]
        first.update(outcome="not_run", method_id=None, evidence=[], reason={"kind": "capability_unavailable", "detail": "Interaction session unavailable.", "refs": ["interaction"]})
        checks[0]["outcome"] = "not_run"
        packet = {"outcome": "blocked", "checks": checks[:1], "blocker": "Interaction unavailable", "required_action": "Restore interaction"}
        self.rejected_without_execution(packet, "identity")
        packet["checks"] = checks
        result = self.submit(packet)
        self.assertFalse(qa_credit_complete(result["artifacts"]["qa"]))


if __name__ == "__main__":
    unittest.main()
