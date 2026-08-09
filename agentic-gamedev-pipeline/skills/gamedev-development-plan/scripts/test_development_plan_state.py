#!/usr/bin/env python3
"""Tests for the development-plan controller and contract."""

from __future__ import annotations

import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import development_plan_state as controller


PRD = """---
document_type: product-requirements
status: approved
revision: 2
---
# PRD
"""


class DevelopmentPlanStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.feature = "sample-feature"
        self.feature_dir = self.root / "docs" / "features" / self.feature
        self.feature_dir.mkdir(parents=True)
        self.prd = self.feature_dir / "product-requirements.md"
        self.spec = self.feature_dir / "technical-specification.md"
        self.plan = self.feature_dir / "development-plan.md"
        self.prd.write_text(PRD, encoding="utf-8")
        self.write_spec_and_ready_state()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def args(self, **values: object) -> Namespace:
        return Namespace(project_root=str(self.root), **values)

    def write_spec_and_ready_state(self) -> None:
        prd_hash = controller.sha256(self.prd)
        self.spec.write_text(
            f"""---
document_type: technical-specification
status: approved
revision: 4
source_prd_path: docs/features/{self.feature}/product-requirements.md
source_prd_revision: 2
source_prd_sha256: {prd_hash}
---
# Specification
""",
            encoding="utf-8",
        )
        spec_hash = controller.sha256(self.spec)
        state_path = self.root / ".agentic-pipeline" / "specification-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            __import__("json").dumps(
                {
                    "feature": self.feature,
                    "status": "spec_ready",
                    "ready": {"prd_sha256": prd_hash, "spec_sha256": spec_hash},
                }
            ),
            encoding="utf-8",
        )

    def initialize(self, mode: str = "single_owner") -> dict:
        state = controller.command_init(
            self.args(feature=self.feature, analyst_id="planning-analyst-1")
        )
        self.assertEqual(state["status"], "analyzing")
        return controller.command_accept_analysis(
            self.args(
                analyst_id="planning-analyst-1",
                mode=mode,
                rationale="bounded ownership decision",
                working_set="8 files, 3 tests, one research packet",
                seams_assessment="one coherent integration seam",
            )
        )

    def slice_text(self, number: int, dependencies: str) -> str:
        return f"""## Slice SLICE-{number:03d}

### Vertical Outcome

End-to-end: yes
Observable result: verified playable outcome {number}.

### Requirements

- PRD-REQ-{number:03d}
- PRD-AC-{number:03d}

### Dependencies

- {dependencies}

### Base Contract

Exact reviewed base revision and evidence.

### Handoff Contract

Sealed result hash, checks, evidence, and open risks.

### Owned Paths

- src/feature-{number}.lua

### Expected Paths

- src/contracts.lua

### Forbidden Scope

- unrelated systems and cleanup

### Scope Contract

- acceptance_ids: PRD-AC-{number:03d}
- editable_paths: src/feature-{number}.lua
- shared_touchpoints: see structured rows below
- shared_touchpoint: TP-{number:03d} | path=src/contracts.lua | symbols=FeatureContract | allowed_change=additive type only | forbidden_change=lifecycle, ownership, removals
- excluded_components: save-system, commerce
- excluded_paths: src/save/**, src/commerce/**
- max_product_files: 8
- max_product_lines_changed: 400
- verification_scope: tests/feature-{number}.spec.lua and affected feature suite
- scope_baseline_revision: base-{number}

### Research Briefs

- RESEARCH-{number:03d} | question=find exact feature entry point | paths=src/feature | exclusions=unrelated systems | evidence=owners and contracts | stop=entry point confirmed

### Verification and Exit Criteria

Mapped acceptance checks pass and handoff is sealed.

### Rollback and Recovery

Revert owned paths; retain prior contract revision.

### Downstream Consumers

- none
"""

    def write_plan(self, mode: str = "single_owner", slice_count: int = 1) -> None:
        prd_hash = controller.sha256(self.prd)
        spec_hash = controller.sha256(self.spec)
        slices = [self.slice_text(1, "none")]
        if slice_count == 2:
            slices.append(self.slice_text(2, "SLICE-001"))
        milestones = "" if mode != "single_owner" else """## Integration Milestones

- MILESTONE-001: complete integrated acceptance checkpoint.

"""
        self.plan.write_text(
            f"""---
document_type: development-plan
status: draft
revision: 1
feature: {self.feature}
mode: {mode}
writer_strategy: sequential
planning_analyst_id: planning-analyst-1
source_prd_path: docs/features/{self.feature}/product-requirements.md
source_prd_revision: 2
source_prd_sha256: {prd_hash}
source_spec_path: docs/features/{self.feature}/technical-specification.md
source_spec_revision: 4
source_spec_sha256: {spec_hash}
slice_count: {slice_count}
---

# Development Plan

## Decision

Writer sequencing: one-at-a-time
Use the selected bounded ownership mode.

## Planning Analysis

Complexity, seams, dependencies, conflicts, and verification were assessed.

## Scope Boundaries

Only the approved feature and named shared symbol are in scope.

## Context Budget

Eight files, three tests, one research packet, and bounded evidence.

{milestones}{''.join(slices)}""",
            encoding="utf-8",
        )

    def test_init_requires_exact_spec_ready_hashes(self) -> None:
        self.spec.write_text(self.spec.read_text(encoding="utf-8") + "drift\n", encoding="utf-8")
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "SPEC_READY evidence"):
            controller.command_init(
                self.args(feature=self.feature, analyst_id="planning-analyst-1")
            )

    def test_single_owner_submit_and_explicit_approval(self) -> None:
        self.initialize()
        self.write_plan()
        submitted = controller.command_submit(self.args())
        self.assertEqual(submitted["status"], "awaiting_user_approval")
        self.assertIn("status: draft", self.plan.read_text(encoding="utf-8"))
        approved = controller.command_approve(
            self.args(approved_by="user", approval_note="User approved exact submitted SHA")
        )
        self.assertEqual(approved["status"], "approved")
        self.assertIn("status: approved", self.plan.read_text(encoding="utf-8"))
        self.assertEqual(
            approved["approval"]["submitted_sha256"], submitted["submission"]["sha256"]
        )

    def test_approval_rejects_changed_submitted_draft(self) -> None:
        self.initialize()
        self.write_plan()
        controller.command_submit(self.args())
        self.plan.write_text(self.plan.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "changed after submission"):
            controller.command_approve(
                self.args(approved_by="user", approval_note="approval")
            )

    def test_approved_plan_hash_is_immutable(self) -> None:
        self.initialize()
        self.write_plan()
        controller.command_submit(self.args())
        controller.command_approve(
            self.args(approved_by="user", approval_note="exact SHA approved")
        )
        self.plan.write_text(self.plan.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "changed after user approval"):
            controller.command_validate(self.args())

    def test_sequential_slices_require_vertical_ordered_dependencies(self) -> None:
        self.initialize(mode="sequential_slices")
        self.write_plan(mode="sequential_slices", slice_count=2)
        result = controller.command_validate(self.args())
        self.assertEqual(result["slice_ids"], ["SLICE-001", "SLICE-002"])

    def test_rejects_duplicate_shared_touchpoint_path(self) -> None:
        self.initialize()
        self.write_plan()
        text = self.plan.read_text(encoding="utf-8").replace(
            "- excluded_components: save-system, commerce",
            "- shared_touchpoint: TP-999 | path=src/contracts.lua | symbols=OtherContract | allowed_change=additive type only | forbidden_change=lifecycle, ownership, removals\n- excluded_components: save-system, commerce",
        )
        self.plan.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "repeats shared touchpoint path"):
            controller.command_validate(self.args())

    def test_rejects_layer_like_slice_without_vertical_contract(self) -> None:
        self.initialize()
        self.write_plan()
        text = self.plan.read_text(encoding="utf-8").replace("End-to-end: yes", "Layer: backend")
        self.plan.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "End-to-end"):
            controller.command_validate(self.args())

    def test_source_drift_marks_plan_stale(self) -> None:
        self.initialize()
        self.write_plan()
        controller.command_submit(self.args())
        self.prd.write_text(self.prd.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
        state = controller.command_status(self.args())
        self.assertEqual(state["status"], "stale")
        self.assertTrue(state["drift"])

    def test_stale_state_reinitializes_only_after_new_spec_ready(self) -> None:
        self.initialize()
        self.prd.write_text(self.prd.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
        self.assertEqual(controller.command_status(self.args())["status"], "stale")
        self.write_spec_and_ready_state()
        renewed = controller.command_reinitialize(
            self.args(analyst_id="planning-analyst-2")
        )
        self.assertEqual(renewed["status"], "analyzing")
        self.assertEqual(renewed["analyst_id"], "planning-analyst-2")
        self.assertEqual(len(renewed["history"]), 1)
        self.assertEqual(renewed["prd"]["sha256"], controller.sha256(self.prd))

    def test_reinitialize_cannot_reuse_any_historical_analyst(self) -> None:
        self.test_stale_state_reinitializes_only_after_new_spec_ready()
        state = controller.load_state(self.root)
        state["status"] = "stale"
        controller.save_state(self.root, state)
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "all planning history"):
            controller.command_reinitialize(
                self.args(analyst_id="planning-analyst-1")
            )

    def test_skill_metadata_is_explicit_only(self) -> None:
        skill_root = Path(__file__).resolve().parents[1]
        skill = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        metadata = (skill_root / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("description: Explicit-invocation only.", skill)
        self.assertIn("## Activation gate", skill)
        self.assertIn("allow_implicit_invocation: false", metadata)


if __name__ == "__main__":
    unittest.main()
