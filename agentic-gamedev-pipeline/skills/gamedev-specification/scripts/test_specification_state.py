#!/usr/bin/env python3
"""Tests for the bounded specification convergence controller."""

from __future__ import annotations

import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import specification_state as controller


PRD = """---
document_type: product-requirements
status: approved
revision: 3
language: English
approved_at: 2026-08-09T00:00:00Z
---
# Product Requirements
"""


class SpecificationStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.feature_dir = self.root / "docs" / "features" / "sample-feature"
        self.feature_dir.mkdir(parents=True)
        self.prd = self.feature_dir / "product-requirements.md"
        self.spec = self.feature_dir / "technical-specification.md"
        self.prd.write_text(PRD, encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def args(self, **values: object) -> Namespace:
        return Namespace(project_root=str(self.root), **values)

    def write_spec(self, status: str = "draft", suffix: str = "") -> None:
        trace = controller.sha256(self.prd)
        self.spec.write_text(
            f"""---
document_type: technical-specification
status: {status}
revision: 1
language: English
source_prd_path: docs/features/sample-feature/product-requirements.md
source_prd_revision: 3
source_prd_sha256: {trace}
---
# Technical Specification
{suffix}
""",
            encoding="utf-8",
        )

    def initialize(self, with_spec: bool = True) -> dict:
        if with_spec:
            self.write_spec()
        return controller.command_init(
            self.args(feature="sample-feature", architect_id="architect-1")
        )

    def start_and_record(self, number: int, **overrides: object) -> None:
        controller.command_start_cycle(
            self.args(architect_id="architect-1", proofreader_id=f"proofreader-{number}")
        )
        values = {
            "proofreader_id": f"proofreader-{number}",
            "critical": 0,
            "major": 1,
            "minor": 0,
            "product_questions": 0,
            "scope_questions": 0,
            "boundary_questions": 0,
            "ownership_questions": 0,
            "public_contract_questions": 0,
            "minors_engineer_resolvable": False,
            "coverage_complete": True,
            "report_path": f"proofreader-{number}.md",
            "finding_id": ["SPEC-FINDING-1"],
            "question_id": [],
        }
        values.update(overrides)
        finding_count = int(values["critical"]) + int(values["major"]) + int(values["minor"])
        question_count = sum(
            int(values[key])
            for key in (
                "product_questions",
                "scope_questions",
                "boundary_questions",
                "ownership_questions",
                "public_contract_questions",
            )
        )
        if "finding_id" not in overrides:
            values["finding_id"] = [
                f"SPEC-FINDING-{index}" for index in range(1, finding_count + 1)
            ]
        if "question_id" not in overrides:
            values["question_id"] = [
                f"SPEC-QUESTION-{index}" for index in range(1, question_count + 1)
            ]
        controller.command_record_proofread(self.args(**values))

    def test_init_marks_missing_spec_for_generation(self) -> None:
        state = self.initialize(with_spec=False)
        self.assertEqual(state["status"], "needs_generation")
        self.assertIn("specification is missing", state["specification"]["trace_errors"])

    def test_accept_spec_requires_exact_current_prd_trace(self) -> None:
        self.initialize(with_spec=False)
        self.write_spec()
        state = controller.command_accept_spec(self.args())
        self.assertEqual(state["status"], "reviewing")
        self.assertEqual(state["specification"]["sha256"], controller.sha256(self.spec))

    def test_init_is_idempotent_and_cannot_reset_cycle_history(self) -> None:
        self.initialize()
        self.start_and_record(1)
        controller.command_complete_cycle(
            self.args(
                architect_id="architect-1",
                resolution_note="batch 1",
                user_decision_note=None,
            )
        )
        state = controller.command_init(
            self.args(feature="sample-feature", architect_id="replacement")
        )
        self.assertEqual(state["active_architect_id"], "architect-1")
        self.assertEqual(state["total_cycles_completed"], 1)
        self.assertEqual(len(state["waves"]), 1)

    def test_attempted_sixth_cycle_enters_hold(self) -> None:
        self.initialize()
        for number in range(1, 6):
            self.start_and_record(number)
            controller.command_complete_cycle(
                self.args(
                    architect_id="architect-1",
                    resolution_note=f"batch {number}",
                    user_decision_note=None,
                )
            )
        with self.assertRaisesRegex(controller.SpecificationStateError, "sixth cycle"):
            controller.command_start_cycle(
                self.args(architect_id="architect-1", proofreader_id="proofreader-6")
            )
        state = controller.load_state(self.root)
        self.assertEqual(state["status"], "spec_convergence_hold")
        self.assertEqual(state["total_cycles_completed"], 5)
        self.assertEqual(len(state["waves"]), 5)
        self.assertEqual(len(state["hold_history"]), 1)

    def test_handoff_preserves_global_history_and_resets_only_new_owner(self) -> None:
        self.test_attempted_sixth_cycle_enters_hold()
        state = controller.command_handoff(
            self.args(new_architect_id="architect-2", decision_note="explicit bounded handoff")
        )
        self.assertEqual(state["active_architect_id"], "architect-2")
        self.assertEqual(state["total_cycles_completed"], 5)
        self.assertEqual(len(state["waves"]), 5)
        self.assertEqual(state["architects"][0]["cycles_completed"], 5)
        self.assertEqual(state["architects"][1]["cycles_completed"], 0)
        self.assertEqual(state["hold_history"][-1]["resolved_by"], "handoff-architect")

    def test_proofreader_identity_must_be_fresh_across_all_cycles(self) -> None:
        self.initialize()
        self.start_and_record(1)
        controller.command_complete_cycle(
            self.args(
                architect_id="architect-1",
                resolution_note="first complete response",
                user_decision_note=None,
            )
        )
        with self.assertRaisesRegex(controller.SpecificationStateError, "fresh identity"):
            controller.command_start_cycle(
                self.args(architect_id="architect-1", proofreader_id="proofreader-1")
            )

    def test_proofreader_counts_require_exact_ids_and_report(self) -> None:
        self.initialize()
        controller.command_start_cycle(
            self.args(architect_id="architect-1", proofreader_id="proofreader-1")
        )
        with self.assertRaisesRegex(controller.SpecificationStateError, "finding counts"):
            controller.command_record_proofread(
                self.args(
                    proofreader_id="proofreader-1",
                    critical=0,
                    major=1,
                    minor=0,
                    product_questions=0,
                    scope_questions=0,
                    boundary_questions=0,
                    ownership_questions=0,
                    public_contract_questions=0,
                    minors_engineer_resolvable=False,
                    coverage_complete=True,
                    report_path="proofreader-1.md",
                    finding_id=[],
                    question_id=[],
                )
            )

    def test_ready_requires_clean_complete_same_sha_pass(self) -> None:
        self.initialize()
        self.write_spec(status="approved")
        controller.command_accept_spec(self.args())
        self.start_and_record(
            1,
            major=0,
            minor=2,
            minors_engineer_resolvable=True,
            coverage_complete=True,
        )
        state = controller.command_confirm_ready(
            self.args(architect_id="architect-1", confirmation="same SHA confirmed")
        )
        self.assertEqual(state["status"], "spec_ready")
        self.assertEqual(state["ready"]["spec_sha256"], controller.sha256(self.spec))

    def test_ready_rejects_spec_changed_after_proofread(self) -> None:
        self.initialize()
        self.write_spec(status="approved")
        controller.command_accept_spec(self.args())
        self.start_and_record(1, major=0, coverage_complete=True)
        self.spec.write_text(self.spec.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
        with self.assertRaisesRegex(controller.SpecificationStateError, "same specification SHA"):
            controller.command_confirm_ready(
                self.args(architect_id="architect-1", confirmation="confirm")
            )

    def test_ready_rejects_unresolved_product_question(self) -> None:
        self.initialize()
        self.write_spec(status="approved")
        controller.command_accept_spec(self.args())
        self.start_and_record(
            1, major=0, product_questions=1, coverage_complete=True
        )
        with self.assertRaisesRegex(controller.SpecificationStateError, "questions remain"):
            controller.command_confirm_ready(
                self.args(architect_id="architect-1", confirmation="confirm")
            )

    def test_product_question_requires_recorded_user_decision_before_fix(self) -> None:
        self.initialize()
        self.start_and_record(1, product_questions=1)
        with self.assertRaisesRegex(
            controller.SpecificationStateError, "recorded user decision"
        ):
            controller.command_complete_cycle(
                self.args(
                    architect_id="architect-1",
                    resolution_note="cannot decide product semantics technically",
                    user_decision_note=None,
                )
            )

    def test_skill_metadata_is_explicit_only(self) -> None:
        skill_root = Path(__file__).resolve().parents[1]
        skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        openai_yaml = (skill_root / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("description: Explicit-invocation only.", skill_text)
        self.assertIn("## Activation gate", skill_text)
        self.assertIn("allow_implicit_invocation: false", openai_yaml)


if __name__ == "__main__":
    unittest.main()
