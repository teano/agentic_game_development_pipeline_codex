"""Truthful repair routing for absent acceptance evidence, without false execution."""
from copy import deepcopy
import unittest

from pipeline_v2.qa_contract import QAContractError, validate_results
from pipeline_v2.model import validate_state, status_view
from pipeline_v2.tests.test_qa_contract import sample_contract, passing_checks
from pipeline_v2.tests import test_acceptance_integration as integration_fixtures


def mark_gap(check, assertion=0, methods=None):
    row = check["assertions"][assertion]
    row.update(outcome="not_run", method_id=None,
        evidence=[{"type": "verification-gap", "ref": "tests/current-suite:required-reset-case",
                   "observation": "The inspected current suite omits the required reset action and observation; its green receipt covers other cases only."}],
        reason={"kind": "verification_incomplete",
                "detail": "The delivered checks do not execute the approved mandatory reset case; the existing method alternatives supply no equivalent proof.",
                "refs": methods or ["observed-action"]})
    check["outcome"] = "fail"


class VerificationGapContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = sample_contract()
        self.definition = self.contract["slices"]["SLICE-001"]
        self.checks = passing_checks(self.contract)

    def test_missing_case_routes_to_fail_without_claiming_execution(self):
        mark_gap(self.checks[0])
        actual = validate_results(self.checks, self.definition, outcome="fail")
        self.assertEqual("not_run", actual[0]["assertions"][0]["outcome"])
        self.assertIsNone(actual[0]["assertions"][0]["method_id"])
        self.assertEqual("pass", actual[1]["outcome"])
        with self.assertRaisesRegex(QAContractError, "outcome must be fail"):
            validate_results(self.checks, self.definition, outcome="blocked")

    def test_unknown_or_partial_method_alternatives_are_rejected(self):
        alternate = deepcopy(self.definition["identities"][0]["assertions"][0]["methods"][0])
        alternate["id"] = "alternate-action"
        self.definition["identities"][0]["assertions"][0]["methods"].append(alternate)
        for refs in (["observed-action"], ["invented", "observed-action"], []):
            mark_gap(self.checks[0], methods=["observed-action", "alternate-action"])
            self.checks[0]["assertions"][0]["reason"]["refs"] = refs
            with self.subTest(refs=refs), self.assertRaises(QAContractError):
                validate_results(self.checks, self.definition, outcome="fail")
        mark_gap(self.checks[0], methods=["observed-action", "alternate-action"])
        validate_results(self.checks, self.definition, outcome="fail")

    def test_green_aggregate_or_empty_evidence_is_not_gap_evidence(self):
        for evidence in ([], [{"type": "controller-check-receipt", "ref": "receipt:green",
                               "observation": "The aggregate command exited zero."}]):
            mark_gap(self.checks[0])
            self.checks[0]["assertions"][0]["evidence"] = evidence
            with self.subTest(evidence=evidence), self.assertRaisesRegex(QAContractError, "verification-gap"):
                validate_results(self.checks, self.definition, outcome="fail")

    def test_gap_does_not_weaken_executed_failure_requirements(self):
        mark_gap(self.checks[0])
        row = self.checks[0]["assertions"][0]
        row.update(outcome="fail", method_id="observed-action")
        row.pop("reason")
        with self.assertRaisesRegex(QAContractError, "observation"):
            validate_results(self.checks, self.definition, outcome="fail")

    def test_unrelated_capability_block_survives_gap_repair(self):
        mark_gap(self.checks[0])
        self.checks[1]["outcome"] = "not_run"
        self.checks[1]["assertions"][0].update(outcome="not_run", method_id=None, evidence=[],
            reason={"kind": "capability_unavailable", "detail": "Assigned interaction surface remains unavailable.",
                    "refs": ["interaction"]})
        validate_results(self.checks, self.definition, outcome="fail")
        self.checks[0] = passing_checks(self.contract)[0]
        validate_results(self.checks, self.definition, outcome="blocked")


class VerificationGapNativeTests(unittest.TestCase):
    def test_proof_gap_returns_full_evidence_to_engineering_without_credit(self):
        h = integration_fixtures.AcceptanceIntegrationTests("runTest")
        h.setUp()
        self.addCleanup(h.doCleanups)
        h.bind()
        h.h._reach_engineering()
        h.issue()
        (h.h.root / "game.txt").write_text("current candidate\n", encoding="utf-8")
        h.submit({"outcome": "pass", "summary": "Current behavior and existing tests implemented."})
        h.h._accept("engineering")
        h.issue()
        h.submit({"outcome": "pass", "findings": []})
        h.h._accept("review")
        h.issue()
        # Previous bound QA assignments remain readable under controlled runtime
        # maintenance; the descriptive reason addition cannot strand their lease.
        previous = deepcopy(h.h.store.load())
        previous["active_assignment"]["artifact_schema"]["item_shapes"]["checks[]"]["assertions"]["reason"] = (
            "{kind,detail,refs[]} required for not_run; kind capability_unavailable|dependency_unsatisfied|authority_unresolved"
        )
        validate_state(previous)
        self.assertEqual("qa", status_view(previous)["phase"])
        checks = integration_fixtures.checks_for(h.contract)
        mark_gap(checks[0])
        result = h.submit({"outcome": "fail", "checks": checks})
        self.assertEqual("engineering", result["phase"])
        self.assertIsNone(result["active_assignment"])
        repair = h.issue()["active_assignment"]
        failure = repair["capsule"]["context"]["verification_failure"]
        self.assertEqual("qa", failure["phase"])
        self.assertEqual(checks, failure["checks"])
        self.assertFalse(h.h.controller.status()["ready"])


if __name__ == "__main__":
    unittest.main()
