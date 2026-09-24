"""Acceptance-method, completeness, and unchanged-plan compatibility regressions."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline_v2.qa_contract import (
    QAContractError, contract_digest, expand_slice_contract, slice_contract, validate_contract, validate_results,
)

_path = Path(__file__).resolve().parents[5] / "scripts" / "development_plan_contract.py"
_spec = importlib.util.spec_from_file_location("qa_plan_contract_tests", _path)
plan_parser = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(plan_parser)


def sample_contract():
    def assertion(identifier):
        return {"id": identifier, "expected": "The approved transition completes.",
                "methods": [{"id": "observed-action", "source": "docs/plan.md#verification",
                             "description": "Perform the approved action and observe completion.",
                             "capabilities": ["interaction"], "evidence_types": ["observation"]}],
                "applicability": {"kind": "always", "condition": "always", "evidence_types": []},
                "depends_on": []}
    return {"schema": 1, "confirm_approved_plan": True, "slices": {
        "SLICE-001": {"identities": [
            {"id": "MANUAL-FEATURE-RUNTIME", "source": "docs/plan.md#verification",
             "assertions": [assertion("enter"), assertion("reset")]},
            {"id": "AUTO-FEATURE-CORE", "source": "docs/plan.md#verification",
             "assertions": [assertion("core")]},
        ]}}}


def passing_checks(contract):
    return [{"id": identity["id"], "outcome": "pass", "evidence": "Actual production path observed.",
             "assertions": [{"id": item["id"], "outcome": "pass", "method_id": "observed-action",
                             "environment": "Assigned runtime session with interaction capability.",
                             "evidence": [{"type": "observation", "ref": "tool-observation:123",
                                           "observation": "Approved transition completed."}]}
                            for item in identity["assertions"]]}
            for identity in contract["slices"]["SLICE-001"]["identities"]]


def compact_contract(contract):
    result = deepcopy(contract)
    for definition in result["slices"].values():
        registry = definition["method_definitions"] = {}
        references = {}
        for identity in definition["identities"]:
            for assertion in identity["assertions"]:
                methods = []
                for method in assertion["methods"]:
                    key = json.dumps(method, sort_keys=True)
                    if key not in references:
                        reference = f"shared-{len(registry) + 1}"
                        references[key] = reference
                        registry[reference] = method
                    methods.append({"ref": references[key]})
                assertion["methods"] = methods
    return result


def plan_text(contract=None):
    text = """---
document_type: development-plan
status: approved
revision: 1
feature: sample
mode: single_owner
writer_strategy: sequential
planning_analyst_id: analyst
decision_ledger_path: docs/decisions.jsonl
slice_count: 1
source_prd_path: docs/prd.md
source_prd_revision: 1
source_prd_sha256: abc
source_spec_path: docs/spec.md
source_spec_revision: 1
source_spec_sha256: def
approved_by: user
approved_at: 2026-09-22
---
# Plan
"""
    if contract is not None:
        text += "\n## QA Acceptance Contract\n\n```json\n" + json.dumps(contract) + "\n```\n"
    return text + """
## Slice SLICE-001

### Coverage Contract

- mandatory_identity_ids: MANUAL-FEATURE-RUNTIME, AUTO-FEATURE-CORE

### Verification and Exit Criteria

Keep the exact existing approved methods.
"""


class QAContractFixture(unittest.TestCase):
    def setUp(self):
        self.contract = sample_contract()
        self.required = {"SLICE-001": ["MANUAL-FEATURE-RUNTIME", "AUTO-FEATURE-CORE"]}
        self.definition = self.contract["slices"]["SLICE-001"]
        self.checks = passing_checks(self.contract)

    def validate(self, outcome="pass"):
        return validate_results(self.checks, self.definition, outcome=outcome)

    def not_run(self, index=0, assertion=0, kind="capability_unavailable", refs=None):
        result = self.checks[index]["assertions"][assertion]
        result.update(outcome="not_run", method_id=None, evidence=[], reason={
            "kind": kind, "detail": "Observed prerequisite unavailable in the assigned session.",
            "refs": refs if refs is not None else ["interaction"],
        })
        self.checks[index]["outcome"] = "not_run"


class QAContractTests(QAContractFixture):
    def test_canonical_contract_and_results_round_trip_without_aliasing(self):
        result = validate_contract(self.contract, self.required, source_paths={"docs/plan.md"})
        self.assertEqual(result, self.contract)
        self.assertEqual(self.validate(), self.checks)
        self.assertEqual(slice_contract(result, "SLICE-001"), self.definition)
        result["slices"]["SLICE-001"]["identities"].clear()
        self.assertEqual(len(self.definition["identities"]), 2)

    def test_digest_binds_method_and_evidence_semantics(self):
        changed = deepcopy(self.contract)
        changed["slices"]["SLICE-001"]["identities"][0]["assertions"][0]["methods"][0]["evidence_types"].append("trace")
        self.assertNotEqual(contract_digest(changed), contract_digest(self.contract))

    def test_unapproved_source_and_missing_identity_are_rejected(self):
        with self.assertRaisesRegex(QAContractError, "approved authority path"):
            validate_contract(self.contract, self.required, source_paths={"docs/spec.md"})
        self.definition["identities"].pop()
        with self.assertRaisesRegex(QAContractError, "mandatory inventory"):
            validate_contract(self.contract, self.required)

    def test_assertion_dependencies_are_exact_and_acyclic(self):
        items = self.definition["identities"][0]["assertions"]
        items[0]["depends_on"] = ["missing"]
        with self.assertRaisesRegex(QAContractError, "unknown dependency"):
            validate_contract(self.contract, self.required)
        items[0]["depends_on"] = ["reset"]
        items[1]["depends_on"] = ["enter"]
        with self.assertRaisesRegex(QAContractError, "cycle"):
            validate_contract(self.contract, self.required)

    def test_every_terminal_outcome_requires_every_identity_and_assertion(self):
        for outcome in ("pass", "fail", "blocked"):
            with self.subTest(outcome=outcome):
                with self.assertRaisesRegex(QAContractError, "every assigned identity"):
                    validate_results(self.checks[:1], self.definition, outcome=outcome)
        self.checks[0]["assertions"].pop()
        with self.assertRaisesRegex(QAContractError, "every assigned assertion"):
            self.validate("blocked")

    def test_unknown_method_and_missing_evidence_are_not_equivalent(self):
        result = self.checks[0]["assertions"][0]
        result["method_id"] = "substitute"
        with self.assertRaisesRegex(QAContractError, "approved method ID"):
            self.validate()
        result["method_id"] = "observed-action"
        result["evidence"] = []
        with self.assertRaisesRegex(QAContractError, "required types"):
            self.validate()

    def test_explicit_alternative_is_accepted_with_its_own_evidence(self):
        methods = self.definition["identities"][0]["assertions"][0]["methods"]
        alternative = {**methods[0], "id": "equivalent-observation", "evidence_types": ["trace"]}
        methods.append(alternative)
        result = self.checks[0]["assertions"][0]
        result["method_id"] = alternative["id"]
        result["evidence"][0]["type"] = "trace"
        self.validate()

    def test_not_applicable_needs_approved_condition_and_observed_proof(self):
        result = self.checks[0]["assertions"][0]
        result.update(outcome="not_applicable", method_id=None)
        with self.assertRaisesRegex(QAContractError, "approved condition"):
            self.validate()
        self.definition["identities"][0]["assertions"][0]["applicability"] = {
            "kind": "conditional", "condition": "Approved optional input exists.", "evidence_types": ["input-inventory"]}
        with self.assertRaisesRegex(QAContractError, "required types"):
            self.validate()
        result["evidence"][0].update(type="input-inventory", observation="Approved optional input is absent.")
        self.validate()

    def test_not_run_cannot_claim_capability_block_with_a_remaining_alternative(self):
        methods = self.definition["identities"][0]["assertions"][0]["methods"]
        methods.append({**methods[0], "id": "alternate", "capabilities": ["other-access"]})
        self.not_run()
        with self.assertRaisesRegex(QAContractError, "every approved alternative"):
            self.validate("blocked")
        self.checks[0]["assertions"][0]["reason"]["refs"].append("other-access")
        self.validate("blocked")

    def test_unrelated_results_remain_required_while_dependencies_can_block(self):
        self.definition["identities"][0]["assertions"][1]["depends_on"] = ["enter"]
        self.not_run()
        self.not_run(assertion=1, kind="dependency_unsatisfied", refs=["enter"])
        self.validate("blocked")
        self.checks[1]["assertions"][0]["environment"] = ""
        with self.assertRaisesRegex(QAContractError, "environment"):
            self.validate("blocked")

    def test_not_run_rejects_discretionary_stop_and_satisfied_dependencies(self):
        self.not_run(kind="time_limit")
        with self.assertRaisesRegex(QAContractError, "reason must identify"):
            self.validate("blocked")
        self.definition["identities"][0]["assertions"][0]["depends_on"] = ["core"]
        self.checks[0]["assertions"][0]["reason"].update(kind="dependency_unsatisfied", refs=["core"])
        with self.assertRaisesRegex(QAContractError, "genuinely unsatisfied"):
            self.validate("blocked")

    def test_partial_assertion_failure_cannot_close_compound_identity(self):
        self.checks[0]["assertions"][1]["outcome"] = "fail"
        with self.assertRaisesRegex(QAContractError, "outcome must be fail"):
            self.validate()
        self.checks[0]["outcome"] = "fail"
        self.validate("fail")

    def test_malformed_dependency_result_is_a_contract_error_not_internal_exception(self):
        self.definition["identities"][0]["assertions"][0]["depends_on"] = ["core"]
        self.checks[1]["assertions"][0]["outcome"] = []
        with self.assertRaisesRegex(QAContractError, "outcome must be one of"):
            self.validate()

    def test_failed_independent_assertion_is_retained_alongside_unavailable_scenario(self):
        self.not_run()
        self.checks[1]["assertions"][0]["outcome"] = "fail"
        self.checks[1]["outcome"] = "fail"
        self.validate("fail")

    def test_legacy_plan_is_unchanged_and_has_no_invented_contract(self):
        text = plan_text()
        self.assertIsNone(plan_parser.parse_qa_contract(text))
        self.assertEqual(text, plan_text())
        with self.assertRaisesRegex(plan_parser.PlanContractError, "explicit authority-bound"):
            plan_parser.parse_qa_contract(text, required=True)

    def test_embedded_plan_and_external_manifest_share_exact_validator(self):
        text = plan_text(self.contract)
        self.assertEqual(plan_parser.parse_qa_contract(text, source_paths={"docs/plan.md"}), self.contract)
        text = text.replace('"schema": 1', '"schema": 1, "schema": 1')
        with self.assertRaisesRegex(plan_parser.PlanContractError, "repeats JSON key"):
            plan_parser.parse_qa_contract(text)


class CompactQAContractTests(QAContractFixture):
    def assert_same_results(self, outcome="pass", error=None):
        compact = compact_contract(self.contract)["slices"]["SLICE-001"]
        self.assertEqual(expand_slice_contract(compact), self.definition)
        messages = []
        for definition in (self.definition, compact):
            if error is None:
                self.assertEqual(validate_results(self.checks, definition, outcome=outcome), self.checks)
            else:
                with self.assertRaisesRegex(QAContractError, error) as raised:
                    validate_results(self.checks, definition, outcome=outcome)
                messages.append(str(raised.exception))
        if messages:
            self.assertEqual(messages[0], messages[1])

    def test_compact_round_trip_preserves_bytes_shape_and_has_no_aliasing(self):
        compact = compact_contract(self.contract)
        before = deepcopy(compact)
        validated = validate_contract(compact, self.required, source_paths={"docs/plan.md"})
        self.assertEqual(validated, before)
        self.assertEqual(contract_digest(validated), contract_digest(before))
        selected = slice_contract(validated, "SLICE-001")
        expanded = expand_slice_contract(selected)
        self.assertEqual(expanded, self.definition)
        expanded["identities"][0]["assertions"][0]["methods"][0]["evidence_types"].append("trace")
        self.assertEqual(expanded["identities"][0]["assertions"][1]["methods"][0]["evidence_types"], ["observation"])
        selected["method_definitions"]["shared-1"]["capabilities"].append("other")
        validated["slices"]["SLICE-001"]["method_definitions"]["shared-1"]["evidence_types"].append("trace")
        self.assertEqual(compact, before)
        self.assertNotEqual(contract_digest(validated), contract_digest(before))
        self.assertEqual(plan_parser.parse_qa_contract(plan_text(compact), source_paths={"docs/plan.md"}), compact)

    def test_compact_and_flat_have_identical_method_evidence_and_failure_results(self):
        self.assert_same_results()
        result = self.checks[0]["assertions"][0]
        result["method_id"] = "shared-1"
        self.assert_same_results(error="approved method ID")
        result["method_id"] = "observed-action"
        evidence = result["evidence"]
        result["evidence"] = []
        self.assert_same_results(error="required types")
        result["evidence"] = evidence
        result["outcome"] = "fail"
        self.assert_same_results(error="outcome must be fail")
        self.checks[0]["outcome"] = "fail"
        self.assert_same_results(outcome="fail")

    def test_compact_and_flat_keep_conditional_and_dependency_rules(self):
        definition = self.definition["identities"][0]["assertions"][0]
        definition["applicability"] = {"kind": "conditional", "condition": "Optional input exists.",
                                       "evidence_types": ["input-inventory"]}
        result = self.checks[0]["assertions"][0]
        result.update(outcome="not_applicable", method_id=None)
        self.assert_same_results(error="required types")
        result["evidence"][0]["type"] = "input-inventory"
        self.assert_same_results()
        self.definition["identities"][0]["assertions"][1]["depends_on"] = ["enter"]
        self.not_run()
        self.assert_same_results(outcome="blocked", error="unsatisfied approved dependency")
        self.not_run(assertion=1, kind="dependency_unsatisfied", refs=["enter"])
        self.assert_same_results(outcome="blocked")
        self.checks[1]["assertions"].clear()
        self.assert_same_results(outcome="blocked", error="every assigned assertion")

    def test_compact_and_flat_require_every_alternative_to_be_unavailable(self):
        methods = self.definition["identities"][0]["assertions"][0]["methods"]
        methods.append({**methods[0], "id": "alternative", "capabilities": ["other-access"],
                        "evidence_types": ["trace"]})
        self.not_run()
        self.assert_same_results(outcome="blocked", error="every approved alternative")
        self.checks[0]["assertions"][0]["reason"]["refs"].append("other-access")
        self.assert_same_results(outcome="blocked")
        methods[1]["capabilities"] = []
        self.assert_same_results(outcome="blocked", error="every approved alternative")

    def test_references_and_inline_alternatives_keep_distinct_evidence_requirements(self):
        compact = compact_contract(self.contract)
        definition = compact["slices"]["SLICE-001"]
        methods = definition["identities"][0]["assertions"][0]["methods"]
        methods.append({**definition["method_definitions"]["shared-1"], "id": "alternative",
                        "evidence_types": ["trace"]})
        self.assertEqual(validate_contract(compact, self.required, source_paths={"docs/plan.md"}), compact)
        result = self.checks[0]["assertions"][0]
        result["method_id"] = "alternative"
        with self.assertRaisesRegex(QAContractError, "required types: trace"):
            validate_results(self.checks, definition, outcome="pass")
        result["evidence"][0]["type"] = "trace"
        self.assertEqual(validate_results(self.checks, definition, outcome="pass"), self.checks)

    def test_compact_references_require_exact_shape_and_defined_local_target(self):
        for entry in ({"ref": "absent"}, {"ref": []}, {"ref": "shared-1", "id": "override"}, {}, "shared-1"):
            with self.subTest(entry=entry):
                compact = compact_contract(self.contract)
                compact["slices"]["SLICE-001"]["identities"][0]["assertions"][0]["methods"] = [entry]
                with self.assertRaises(QAContractError):
                    validate_contract(compact, self.required)
        compact = compact_contract(self.contract)
        definition = compact["slices"]["SLICE-001"]
        del definition["method_definitions"]
        with self.assertRaisesRegex(QAContractError, "unknown method reference"):
            validate_contract(compact, self.required)
        definition["method_definitions"] = {"shared-1": deepcopy(self.definition["identities"][0]["assertions"][0]["methods"][0])}
        definition["identities"][0]["assertions"][0]["methods"] = []
        with self.assertRaisesRegex(QAContractError, "at least one approved method"):
            validate_contract(compact, self.required)

    def test_unused_and_recursive_definitions_cannot_bypass_validation(self):
        method = self.definition["identities"][0]["assertions"][0]["methods"][0]
        registries = [[], None, {"bad key": method}, {"unused": {"ref": "unused"}},
                      {"first": {"ref": "second"}, "second": {"ref": "first"}},
                      {"unused": {**method, "extra": True}},
                      {"unused": {**method, "source": "docs/unapproved.md#method"}},
                      {"unused": {**method, "capabilities": ["bad capability"]}},
                      {"unused": {**method, "evidence_types": []}}]
        for registry in registries:
            with self.subTest(registry=registry):
                contract = deepcopy(self.contract)
                contract["slices"]["SLICE-001"]["method_definitions"] = registry
                with self.assertRaises(QAContractError):
                    validate_contract(contract, self.required, source_paths={"docs/plan.md"})

    def test_resolved_method_ids_are_unique_even_across_distinct_registry_keys(self):
        for duplicate in ({"ref": "shared-1"}, {"ref": "another-key"},
                          self.definition["identities"][0]["assertions"][0]["methods"][0]):
            with self.subTest(duplicate=duplicate):
                compact = compact_contract(self.contract)
                definition = compact["slices"]["SLICE-001"]
                definition["method_definitions"]["another-key"] = deepcopy(definition["method_definitions"]["shared-1"])
                definition["identities"][0]["assertions"][0]["methods"].append(duplicate)
                with self.assertRaisesRegex(QAContractError, "repeats an approved method ID"):
                    validate_contract(compact, self.required)


if __name__ == "__main__":
    unittest.main()
