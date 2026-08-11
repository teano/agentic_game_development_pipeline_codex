#!/usr/bin/env python3
"""Structural corpus validation and external-candidate grader tests."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = Path(__file__).with_name("semantic_forward_eval_cases.v1.json")
GRADER_PATH = Path(__file__).resolve().parents[1] / "grade_semantic_forward_eval.py"
FIXTURES = Path(__file__).with_name("fixtures")
CONTROLLER_PATH = (
    PLUGIN_ROOT / "skills" / "gamedev-pipeline" / "scripts" / "pipeline_state.py"
)
sys.path.insert(0, str(CONTROLLER_PATH.parent))
MODULE_SPEC = importlib.util.spec_from_file_location(
    "semantic_forward_eval_grader_tested", GRADER_PATH
)
assert MODULE_SPEC and MODULE_SPEC.loader
grader = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(grader)
CONTROLLER_SPEC = importlib.util.spec_from_file_location(
    "pipeline_state_semantic_eval_tested", CONTROLLER_PATH
)
assert CONTROLLER_SPEC and CONTROLLER_SPEC.loader
controller = importlib.util.module_from_spec(CONTROLLER_SPEC)
CONTROLLER_SPEC.loader.exec_module(controller)
REQUIRED_SCENARIOS = {
    "ordinary_non_trigger",
    "direct_stage",
    "pipeline_delegated_stage",
    "prohibited_stage_to_stage_execution",
    "stale_or_missing_capsule",
    "prd_spec_plan_order",
    "optional_research_not_required",
    "mixed_qa_gates",
    "recovery",
    "long_resume",
}
EXPECTED_ORACLE_FIELDS = {
    "activation",
    "allowed_action",
    "completion_token",
    "next_action",
    "forbidden_actions",
    "required_references",
    "stop_result",
    "authority_result",
}


class SemanticForwardEvalCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
        cls.cases = cls.corpus["cases"]
        cls.skill_names = {
            path.parent.name
            for path in (PLUGIN_ROOT / "skills").glob("*/SKILL.md")
        }

    def test_version_and_required_scenario_coverage(self) -> None:
        self.assertEqual(1, self.corpus["schema_version"])
        self.assertEqual(1, self.corpus["candidate_schema_version"])
        self.assertIn("not an LLM unit test", self.corpus["purpose"])
        ids = [case["id"] for case in self.cases]
        self.assertEqual(len(ids), len(set(ids)))
        scenarios = {case["scenario"] for case in self.cases}
        self.assertEqual(set(), REQUIRED_SCENARIOS - scenarios)

    def test_expectations_are_structurally_gradable(self) -> None:
        for case in self.cases:
            with self.subTest(case=case["id"]):
                self.assertTrue(case["prompt"].strip())
                expected = case["expected"]
                self.assertEqual(EXPECTED_ORACLE_FIELDS, set(expected))
                self.assertIsInstance(expected["activation"], list)
                self.assertIsInstance(expected["forbidden_actions"], list)
                self.assertIsInstance(expected["required_references"], list)
                self.assertIsInstance(expected["allowed_action"], str)
                self.assertIsInstance(expected["stop_result"], str)
                self.assertIsInstance(expected["authority_result"], str)
                self.assertTrue(expected["forbidden_actions"])
                self.assertEqual(
                    len(expected["forbidden_actions"]),
                    len(set(expected["forbidden_actions"])),
                )
                for skill_name in expected["activation"]:
                    self.assertIn(skill_name, self.skill_names)
                for relative in expected["required_references"]:
                    path = (PLUGIN_ROOT / relative).resolve()
                    self.assertTrue(path.is_file(), relative)
                    path.relative_to(PLUGIN_ROOT.resolve())

    def test_activation_authority_and_reference_routing_invariants(self) -> None:
        by_id = {case["id"]: case for case in self.cases}
        self.assertEqual([], by_id["ordinary_non_trigger"]["expected"]["activation"])
        self.assertEqual(
            ["gamedev-engineer"],
            by_id["pipeline_delegated_engineering"]["expected"]["activation"],
        )
        self.assertEqual(
            "$gamedev-requirements",
            by_id["upstream_order_prd_before_spec_plan"]["expected"]["next_action"],
        )
        self.assertIn(
            "execute_coverage_stage",
            by_id["stage_to_stage_execution_prohibited"]["expected"][
                "forbidden_actions"
            ],
        )
        prohibited = by_id["stage_to_stage_execution_prohibited"]
        self.assertEqual("slice_engineering", prohibited["setup"]["controller_phase"])
        self.assertEqual("valid_current_revision", prohibited["setup"]["capsule"])
        self.assertEqual("active_exact_scope", prohibited["setup"]["write_lease"])
        self.assertEqual(
            "ENGINEERING_COMPLETE: yes",
            prohibited["expected"]["completion_token"],
        )
        self.assertEqual(
            "$gamedev-coverage-steward", prohibited["expected"]["next_action"]
        )
        self.assertEqual(
            [], by_id["stale_capsule_rejected"]["expected"]["activation"]
        )
        self.assertEqual(
            [], by_id["missing_capsule_rejected"]["expected"]["activation"]
        )
        self.assertIn(
            "load_full_status_by_default",
            by_id["long_resume_compact_status"]["expected"]["forbidden_actions"],
        )
        self.assertEqual(
            ["gamedev-engineer"],
            by_id["optional_research_not_required"]["expected"]["activation"],
        )
        self.assertEqual(
            "authorize_exact_qa_credentials",
            by_id["mixed_qa_gates_preserved"]["expected"]["next_action"],
        )
        mixed_qa = by_id["mixed_qa_gates_preserved"]
        probe = mixed_qa["setup"]["qa_capability_probe"]
        self.assertEqual("blocked", probe["status"])
        self.assertNotEqual("ready", probe["status"])
        self.assertEqual(
            {
                "config-credentials": "blocked_user",
                "persistence-datastore": "blocked_environment",
            },
            probe["capabilities"],
        )
        self.assertEqual(
            set(probe["capabilities"]), set(probe["minimum_resume_actions"])
        )
        self.assertEqual(
            {"blocked_user", "blocked_environment"},
            {gate["category"] for gate in mixed_qa["setup"]["open_gates"]},
        )
        for gate in mixed_qa["setup"]["open_gates"]:
            contract = probe["minimum_resume_actions"][gate["capability_id"]]
            self.assertEqual(contract, gate["minimum_resume_action"])
        self.assertEqual("blocked_user", mixed_qa["setup"]["overall_qa_status"])
        self.assertEqual("blocked", mixed_qa["setup"]["readiness"])
        self.assertEqual([], mixed_qa["expected"]["activation"])
        self.assertIsNone(mixed_qa["expected"]["completion_token"])
        self.assertEqual(
            "stop_before_qa_readiness_blocked",
            mixed_qa["expected"]["stop_result"],
        )
        self.assertEqual(
            "user_authority_input_required",
            mixed_qa["expected"]["authority_result"],
        )
        self.assertEqual(
            "resolve_qa_gate",
            by_id["long_resume_compact_status"]["expected"]["next_action"],
        )

    def test_capability_probe_gates_cannot_claim_a_ready_probe(self) -> None:
        for case in self.cases:
            setup = case["setup"]
            capability_gates = [
                gate
                for gate in setup.get("open_gates", [])
                if isinstance(gate, dict)
                and gate.get("origin") == "qa_capability_probe"
            ]
            if not capability_gates:
                continue
            with self.subTest(case=case["id"]):
                probe = setup.get("qa_capability_probe")
                self.assertIsInstance(probe, dict)
                self.assertEqual("blocked", probe["status"])
                self.assertNotEqual("ready", probe["status"])
                self.assertEqual(
                    set(probe["capabilities"]),
                    {gate["capability_id"] for gate in capability_gates},
                )
                for gate in capability_gates:
                    self.assertEqual(
                        probe["minimum_resume_actions"][gate["capability_id"]],
                        gate["minimum_resume_action"],
                    )

    def test_mixed_qa_oracle_matches_controller_selected_resume_route(self) -> None:
        mixed_qa = next(
            case for case in self.cases if case["id"] == "mixed_qa_gates_preserved"
        )
        probe = mixed_qa["setup"]["qa_capability_probe"]
        controller_state = {
            "phase": "qa",
            "qa_capability": {
                "status": probe["status"],
                "revision": probe["revision"],
                "probe_id": probe["probe_id"],
                "capabilities": probe["capabilities"],
                "minimum_resume_actions": probe["minimum_resume_actions"],
            },
        }
        actual = controller.blocked_capability_next_action(
            controller_state["qa_capability"]["capabilities"],
            controller_state["qa_capability"]["minimum_resume_actions"],
            probe_id=controller_state["qa_capability"]["probe_id"],
            missing_action="record_missing_qa_resume_contract",
        )
        expected = mixed_qa["expected"]
        self.assertEqual(expected["allowed_action"], actual["action"])
        self.assertEqual(expected["next_action"], actual["action"])
        self.assertEqual("config-credentials", actual["capability_id"])
        self.assertEqual("user", actual["owner"])
        self.assertTrue(actual["user_input_required"])
        self.assertEqual(2, actual["capability_summary"]["total"])
        self.assertEqual(
            {"blocked_user": 1, "blocked_environment": 1},
            actual["capability_summary"]["by_status"],
        )
        self.assertNotIn("capabilities", actual)
        self.assertNotIn("minimum_resume_actions", actual)


class SemanticForwardEvalGraderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.corpus = grader.load_corpus(CORPUS_PATH)

    def grade_fixture(self, name: str, case_id: str | None = None) -> dict:
        responses = grader.load_candidate(FIXTURES / name)
        selected = [case_id] if case_id else None
        return grader.grade_candidates(self.corpus, responses, selected)

    def test_passing_fixture_grades_every_case_and_dimension(self) -> None:
        report = self.grade_fixture("semantic_candidate_pass.v1.json")
        self.assertTrue(report["summary"]["pass"])
        self.assertEqual(11, report["summary"]["graded_cases"])
        self.assertEqual(11, report["summary"]["passed_cases"])
        for result in report["results"]:
            self.assertTrue(result["pass"])
            self.assertTrue(all(item["pass"] for item in result["dimensions"].values()))

    def test_forbidden_stage_execution_attempt_is_caught(self) -> None:
        report = self.grade_fixture(
            "semantic_candidate_fail_forbidden_stage.v1.json",
            "stage_to_stage_execution_prohibited",
        )
        result = report["results"][0]
        self.assertFalse(report["summary"]["pass"])
        self.assertFalse(result["dimensions"]["attempted_actions"]["pass"])
        self.assertEqual(
            ["execute_coverage_stage"],
            result["dimensions"]["attempted_actions"]["forbidden_attempts"],
        )

    def test_wrong_next_action_jsonl_is_caught_and_cli_is_nonzero(self) -> None:
        fixture = "semantic_candidate_fail_wrong_next.v1.jsonl"
        report = self.grade_fixture(fixture, "stage_to_stage_execution_prohibited")
        self.assertFalse(report["results"][0]["dimensions"]["next_action"]["pass"])
        result = subprocess.run(
            [
                sys.executable,
                str(GRADER_PATH),
                "--candidate",
                str(FIXTURES / fixture),
                "--case",
                "stage_to_stage_execution_prohibited",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertFalse(json.loads(result.stdout)["summary"]["pass"])

    def test_stale_capsule_write_attempt_is_caught(self) -> None:
        report = self.grade_fixture(
            "semantic_candidate_fail_stale_write.v1.json",
            "stale_capsule_rejected",
        )
        result = report["results"][0]
        self.assertFalse(report["summary"]["pass"])
        self.assertEqual(
            ["edit_product_files"],
            result["dimensions"]["attempted_actions"]["forbidden_attempts"],
        )

    def test_cli_accepts_complete_passing_candidate_and_documents_format(self) -> None:
        help_result = subprocess.run(
            [sys.executable, str(GRADER_PATH), "--help"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, help_result.returncode, help_result.stderr)
        self.assertIn("forbidden_actions", help_result.stdout)
        result = subprocess.run(
            [
                sys.executable,
                str(GRADER_PATH),
                "--candidate",
                str(FIXTURES / "semantic_candidate_pass.v1.json"),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(json.loads(result.stdout)["summary"]["pass"])


if __name__ == "__main__":
    unittest.main()
