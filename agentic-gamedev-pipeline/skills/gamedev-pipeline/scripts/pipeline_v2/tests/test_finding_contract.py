from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[2]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from pipeline_v2.execution import convergence_context, finding_updates, record_finding_resolutions
from pipeline_v2.finding_contract import validate_artifact, validate_findings, validate_resolutions
from pipeline_v2.model import PipelineError


class FindingContractTests(unittest.TestCase):
    def setUp(self):
        self.state = {"authority": {"digest": "a" * 64}, "phase": "review", "slices": [{"id": "S1"}],
                      "active_assignment": {"capsule": {"context": {"acceptance_contract_version": 1}}}}
        self.finding = {"id": "REVIEW-M3-002", "text": "Six mandatory scenarios have incomplete proof.",
                        "severity": "high", "kind": "acceptance",
                        "conditions": [{"id": f"C{n}", "text": f"Execute approved scenario {n} through its actual production path."}
                                       for n in range(1, 7)]}

    def start(self):
        finding_updates(self.state, [self.finding], [], outcome="fail")

    def rows(self, phase, *, unresolved=()):
        good = "resolved" if phase == "review" else "addressed"
        return [{"finding_id": self.finding["id"], "condition_id": condition["id"],
                 "status": "unresolved" if condition["id"] in unresolved else good,
                 "evidence": f"Concrete source and execution evidence for {condition['id']}."}
                for condition in self.finding["conditions"]]

    def test_five_omitted_conditions_cannot_be_hidden_by_aggregate_engineer_pass(self):
        self.start()
        snapshot = deepcopy(self.state)
        with self.assertRaisesRegex(PipelineError, "missing=.*C2.*C6"):
            validate_artifact(self.state, "engineering", {"outcome": "pass", "summary": "Fixed finding; suite passes.",
                                                          "finding_resolutions": self.rows("engineering")[:1]})
        self.assertEqual(snapshot, self.state)
        with self.assertRaisesRegex(PipelineError, "addressed"):
            validate_artifact(self.state, "engineering", {"outcome": "pass", "summary": "First scenario only.",
                                                          "finding_resolutions": self.rows("engineering", unresolved={f"C{n}" for n in range(2, 7)})})

    def test_engineer_claims_never_close_and_review_cannot_omit_five_conditions(self):
        self.start()
        artifact = {"outcome": "pass", "summary": "Completed the bounded repair.", "finding_resolutions": self.rows("engineering")}
        record_finding_resolutions(self.state, "engineering", artifact)
        context = convergence_context(self.state)
        self.assertEqual(6, len(context["engineering_resolutions"]))
        self.assertTrue(all(row["status"] == "unresolved" for row in context["condition_status"][self.finding["id"]].values()))
        with self.assertRaisesRegex(PipelineError, "exact assigned conditions"):
            validate_artifact(self.state, "review", {"outcome": "pass", "findings": [], "finding_resolutions": self.rows("review")[:1]})

    def test_partial_review_preserves_all_original_conditions_and_only_open_repair_work(self):
        self.start()
        rows = self.rows("review", unresolved={f"C{n}" for n in range(2, 7)})
        validate_artifact(self.state, "review", {"outcome": "fail", "findings": [], "finding_resolutions": rows})
        actual = finding_updates(self.state, [], rows, outcome="fail")
        self.assertEqual([self.finding], actual)
        context = convergence_context(self.state)
        self.assertEqual("resolved", context["condition_status"][self.finding["id"]]["C1"]["status"])
        validate_artifact(self.state, "engineering", {"outcome": "pass", "summary": "Remaining five repaired.",
                                                       "finding_resolutions": self.rows("engineering")[1:]})
        with self.assertRaisesRegex(PipelineError, "C1"):
            validate_artifact(self.state, "review", {"outcome": "pass", "findings": [], "finding_resolutions": self.rows("review")[1:]})
        finding_updates(self.state, [], self.rows("review"), outcome="pass")
        context = convergence_context(self.state)
        self.assertEqual({}, context["open"])
        self.assertEqual([self.finding["id"]], context["resolved"])
        self.assertNotIn("retained", context)

    def test_review_pass_with_explicit_unresolved_condition_is_rejected(self):
        self.start()
        with self.assertRaisesRegex(PipelineError, "unresolved finding condition"):
            finding_updates(self.state, [], self.rows("review", unresolved={"C6"}), outcome="pass")
        self.assertEqual(6, len(convergence_context(self.state)["open"][self.finding["id"]]["conditions"]))

    def test_restatement_cannot_drop_or_rewrite_original_conditions(self):
        self.start()
        for change in ("drop", "rewrite"):
            with self.subTest(change=change):
                partial = deepcopy(self.finding)
                if change == "drop":
                    partial["conditions"] = partial["conditions"][:1]
                else:
                    partial["conditions"][0]["text"] = "A weaker condition."
                with self.assertRaisesRegex(PipelineError, "retain every original condition"):
                    finding_updates(self.state, [partial], self.rows("review", unresolved={"C6"}), outcome="fail")

    def test_legacy_finding_is_one_full_text_condition_and_absence_never_resolves(self):
        legacy = {key: value for key, value in self.finding.items() if key != "conditions"}
        self.state["execution"] = {"version": 1, "owners": {}, "receipts": {}, "read_admissions": {},
            "findings": {f"{'a' * 64}:S1:review": {"open": {legacy["id"]: legacy}, "resolved": [], "repeat_count": 0}}}
        context = convergence_context(self.state)
        self.assertEqual([{"id": "C1", "text": legacy["text"]}], context["open"][legacy["id"]]["conditions"])
        finding_updates(self.state, [])
        self.assertIn(legacy["id"], convergence_context(self.state)["open"])
        with self.assertRaisesRegex(PipelineError, "missing"):
            validate_artifact(self.state, "review", {"outcome": "pass", "findings": []})

    def test_new_contract_requires_explicit_conditions_and_legacy_shape_remains_readable(self):
        legacy = {key: value for key, value in self.finding.items() if key not in {"id", "conditions"}}
        self.assertEqual("C1", validate_findings([legacy], require_conditions=False)[0]["conditions"][0]["id"])
        with self.assertRaisesRegex(PipelineError, "explicit conditions"):
            validate_artifact(self.state, "review", {"outcome": "fail", "findings": [legacy]})
        validate_artifact(self.state, "review", {"outcome": "pass", "findings": []})
        explicit = {key: value for key, value in self.finding.items() if key != "id"}
        self.assertEqual(validate_findings([explicit]), validate_findings([explicit]))

    def test_duplicate_unknown_rows_or_empty_evidence_cannot_prove_coverage(self):
        self.start()
        rows = self.rows("review")
        with self.assertRaisesRegex(PipelineError, "duplicate"):
            validate_resolutions(rows + rows[:1], "review")
        rows[0]["condition_id"] = "invented"
        with self.assertRaisesRegex(PipelineError, "unexpected"):
            validate_artifact(self.state, "review", {"outcome": "pass", "findings": [], "finding_resolutions": rows})
        rows = self.rows("engineering")
        rows[0]["evidence"] = " "
        with self.assertRaisesRegex(PipelineError, "evidence"):
            validate_resolutions(rows, "engineering")

    def test_docs_repairs_use_same_condition_contract_without_self_acceptance(self):
        self.start()
        artifact = {"outcome": "pass", "summary": "Documentation corrected.", "finding_resolutions": self.rows("docs")}
        record_finding_resolutions(self.state, "docs", artifact)
        self.assertIn(self.finding["id"], convergence_context(self.state)["open"])
        artifact["finding_resolutions"][0]["status"] = "resolved"
        with self.assertRaises(PipelineError):
            validate_artifact(self.state, "docs", artifact)

    def test_blocked_review_retains_unassessed_conditions_without_closing_them(self):
        self.start()
        rows = self.rows("review", unresolved={f"C{n}" for n in range(1, 7)})
        finding_updates(self.state, [], rows, outcome="blocked")
        self.assertEqual([self.finding], list(convergence_context(self.state)["open"].values()))


if __name__ == "__main__":
    unittest.main()
