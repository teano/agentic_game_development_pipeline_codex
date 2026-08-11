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
        self.feature_dir = self.root / "docs" / "Features" / "template" / self.feature
        self.feature_dir.mkdir(parents=True)
        self.prd = self.feature_dir / "product-requirements.md"
        self.spec = self.feature_dir / "technical-specification.md"
        self.plan = self.feature_dir / "development-plan.md"
        self.ledger = self.feature_dir / "decision-ledger.jsonl"
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
product_authority:
  path: docs/Features/template/{self.feature}/product-requirements.md
  revision: 2
  sha256: {prd_hash}
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
                    "prd": {
                        "path": self.prd.relative_to(self.root).as_posix(),
                    },
                    "specification": {
                        "path": self.spec.relative_to(self.root).as_posix(),
                    },
                    "ready": {"prd_sha256": prd_hash, "spec_sha256": spec_hash},
                }
            ),
            encoding="utf-8",
        )

    def initialize(self, mode: str = "single_owner") -> dict:
        state = controller.command_init(
            self.args(
                feature=self.feature,
                prd=self.prd.relative_to(self.root).as_posix(),
                spec=self.spec.relative_to(self.root).as_posix(),
                plan=self.plan.relative_to(self.root).as_posix(),
                decision_ledger=self.ledger.relative_to(self.root).as_posix(),
                analyst_id="planning-analyst-1",
            )
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

Controller-generated schema-2 handoff with decision_ids, coverage_state,
documentation_state, and open_assumptions.

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

### Coverage Contract

- acceptance_ids: PRD-AC-{number:03d}
- automated_identity_namespace: AUTO-SLICE-{number:03d}-*
- manual_identity_namespace: MANUAL-SLICE-{number:03d}-*
- mandatory_identity_ids: AUTO-SLICE-{number:03d}-CORE, MANUAL-SLICE-{number:03d}-RUNTIME
- automation_feasibility: deterministic logic automated; runtime topology manual
- capability_prerequisites: studio-editor-sync, test-server-two-clients, window-control-path
- planned_manifest: tests/sample-feature/verification/SLICE-{number:03d}-planned.json
- finalized_manifest: tests/sample-feature/verification/SLICE-{number:03d}-finalized.json
- amendment_authorities: DEC-*, normalized finding, or approved rebaseline

### Documentation Contract

- normative_pre_review_paths: docs/contracts/feature.md
- derived_post_qa_paths: docs/operators/feature.md
- decision_ids: none
- evidence_sources: controller handoff, Review, and QA IDs

### Context Capsule Budget

- max_authority_files: 8
- max_evidence_files: 12
- max_total_files: 20
- max_payload_bytes: 160000
- max_estimated_tokens: 40000
- metric_scope: capsule_plus_referenced_files
- authority_paths: approved feature documents and exact edit files
- evidence_paths: bounded research and verification artifacts

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
product_authority:
  path: docs/Features/template/{self.feature}/product-requirements.md
  revision: 2
  sha256: {prd_hash}
specification_authority:
  path: docs/Features/template/{self.feature}/technical-specification.md
  revision: 4
  sha256: {spec_hash}
decision_ledger_path: docs/Features/template/{self.feature}/decision-ledger.jsonl
slice_count: {slice_count}
---

# Development Plan

## Decision

Writer sequencing: one-at-a-time
Ownership meaning: phase-scoped write lease
Use the selected bounded ownership mode.

## Planning Analysis

Complexity, seams, dependencies, conflicts, and verification were assessed.

## Scope Boundaries

Only the approved feature and named shared symbol are in scope.

## Decision Ledger

- ledger_path: docs/Features/template/{self.feature}/decision-ledger.jsonl
- active_decision_ids: none
- new_decision_route: explicit authority -> Decision Recorder -> controller append validation

## Coverage Strategy

- manifest_path: tests/sample-feature/verification/coverage-schema-2.json
- automated_identity_namespace: AUTO-FEATURE-*
- manual_identity_namespace: MANUAL-FEATURE-*
- mandatory_rule: explicit identities mapped to PRD-AC IDs
- automation_feasibility: deterministic logic automated
- capability_prerequisites: studio-editor-sync, test-server-two-clients, window-control-path
- gates: plan-before-engineering, finalize-after-code-freeze

## Documentation Strategy

- normative_pre_review: docs/contracts/feature.md
- derived_post_qa: docs/operators/feature.md

## Context Budget

- max_authority_files: 12
- max_evidence_files: 20
- max_total_files: 32
- max_payload_bytes: 250000
- max_estimated_tokens: 60000
- metric_scope: capsule_plus_referenced_files
- estimation_recipe: ceil(payload bytes / 4)

{milestones}{''.join(slices)}""",
            encoding="utf-8",
        )

    def test_init_requires_exact_spec_ready_hashes(self) -> None:
        self.spec.write_text(self.spec.read_text(encoding="utf-8") + "drift\n", encoding="utf-8")
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "SPEC_READY evidence"):
            controller.command_init(
                self.args(
                    feature=self.feature,
                    prd=self.prd.relative_to(self.root).as_posix(),
                    spec=self.spec.relative_to(self.root).as_posix(),
                    plan=self.plan.relative_to(self.root).as_posix(),
                    decision_ledger=self.ledger.relative_to(self.root).as_posix(),
                    analyst_id="planning-analyst-1",
                )
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

    def test_plan_requires_exact_resolved_decision_ledger_path(self) -> None:
        self.initialize()
        self.write_plan()
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8").replace(
                f"decision_ledger_path: docs/Features/template/{self.feature}/decision-ledger.jsonl",
                "decision_ledger_path: docs/other/ledger.jsonl",
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "decision_ledger_path"):
            controller.command_validate(self.args())

    def test_global_context_budget_requires_all_five_positive_limits(self) -> None:
        self.initialize()
        self.write_plan()
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8").replace(
                "- max_payload_bytes: 250000", "- max_payload_bytes: 0"
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "limits must be positive"):
            controller.command_validate(self.args())

    def test_slice_requires_coverage_documentation_and_capsule_contracts(self) -> None:
        self.initialize()
        self.write_plan()
        text = self.plan.read_text(encoding="utf-8")
        start = text.index("### Coverage Contract")
        end = text.index("### Documentation Contract")
        self.plan.write_text(text[:start] + text[end:], encoding="utf-8")
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "Coverage Contract"):
            controller.command_validate(self.args())

    def test_slice_accepts_exact_research_not_required_sentinel(self) -> None:
        self.initialize()
        self.write_plan()
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8").replace(
                "- RESEARCH-001 | question=find exact feature entry point | paths=src/feature | exclusions=unrelated systems | evidence=owners and contracts | stop=entry point confirmed",
                "- research_not_required | reason=approved specification and exact edit files fully identify the implementation surface",
            ),
            encoding="utf-8",
        )
        controller.command_validate(self.args())

    def test_slice_rejects_brief_plus_research_not_required(self) -> None:
        self.initialize()
        self.write_plan()
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8").replace(
                "### Coverage Contract",
                "- research_not_required | reason=conflicting duplicate decision\n\n### Coverage Contract",
                1,
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "briefs or research_not_required"):
            controller.command_validate(self.args())

    def test_global_context_budget_rejects_duplicate_exact_limit(self) -> None:
        self.initialize()
        self.write_plan()
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8").replace(
                "- max_authority_files: 12",
                "- max_authority_files: 12\n- max_authority_files: 11",
                1,
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "repeats numeric limit"):
            controller.command_validate(self.args())

    def test_global_context_budget_rejects_unsupported_numeric_limit(self) -> None:
        self.initialize()
        self.write_plan()
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8").replace(
                "- max_estimated_tokens: 60000",
                "- max_estimated_tokens: 60000\n- max_transcript_bytes: 10",
                1,
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "unsupported numeric limit"):
            controller.command_validate(self.args())

    def test_slice_context_budget_cannot_exceed_global_authority_limit(self) -> None:
        self.initialize()
        self.write_plan()
        text = self.plan.read_text(encoding="utf-8")
        marker = text.index("### Context Capsule Budget")
        before, after = text[:marker], text[marker:]
        after = after.replace("- max_authority_files: 8", "- max_authority_files: 13", 1)
        self.plan.write_text(before + after, encoding="utf-8")
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "exceeds global limits"):
            controller.command_validate(self.args())

    def test_slice_context_budget_cannot_exceed_global_payload_limit(self) -> None:
        self.initialize()
        self.write_plan()
        text = self.plan.read_text(encoding="utf-8")
        marker = text.index("### Context Capsule Budget")
        before, after = text[:marker], text[marker:]
        after = after.replace("- max_payload_bytes: 160000", "- max_payload_bytes: 250001", 1)
        self.plan.write_text(before + after, encoding="utf-8")
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "exceeds global limits"):
            controller.command_validate(self.args())

    def test_slice_context_budget_rejects_duplicate_limit(self) -> None:
        self.initialize()
        self.write_plan()
        text = self.plan.read_text(encoding="utf-8")
        marker = text.index("### Context Capsule Budget")
        before, after = text[:marker], text[marker:]
        after = after.replace(
            "- max_evidence_files: 12",
            "- max_evidence_files: 12\n- max_evidence_files: 11",
            1,
        )
        self.plan.write_text(before + after, encoding="utf-8")
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "repeats numeric limit"):
            controller.command_validate(self.args())

    def test_slice_context_budget_rejects_unsupported_numeric_limit(self) -> None:
        self.initialize()
        self.write_plan()
        text = self.plan.read_text(encoding="utf-8")
        marker = text.index("### Context Capsule Budget")
        before, after = text[:marker], text[marker:]
        after = after.replace(
            "- max_estimated_tokens: 40000",
            "- max_estimated_tokens: 40000\n- max_chat_messages: 5",
            1,
        )
        self.plan.write_text(before + after, encoding="utf-8")
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "unsupported numeric limit"):
            controller.command_validate(self.args())

    def test_context_total_files_cannot_be_smaller_than_component_limit(self) -> None:
        self.initialize()
        self.write_plan()
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8").replace(
                "- max_total_files: 32", "- max_total_files: 10", 1
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "cannot be smaller"):
            controller.command_validate(self.args())

    def test_plan_rejects_prose_capability_prerequisites(self) -> None:
        self.initialize()
        self.write_plan()
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8").replace(
                "studio-editor-sync, test-server-two-clients, window-control-path",
                "studio-editor-sync, server plus two clients, window-control-path",
                1,
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "capability ID"):
            controller.command_validate(self.args())

    def test_context_budget_requires_exact_metric_scope(self) -> None:
        self.initialize()
        self.write_plan()
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8").replace(
                "- metric_scope: capsule_plus_referenced_files\n", "", 1
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "metric_scope"):
            controller.command_validate(self.args())

    def test_context_budget_rejects_duplicate_metric_scope(self) -> None:
        self.initialize()
        self.write_plan()
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8").replace(
                "- metric_scope: capsule_plus_referenced_files\n",
                "- metric_scope: capsule_plus_referenced_files\n"
                "- metric_scope: capsule_plus_referenced_files\n",
                1,
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "exactly one metric_scope"):
            controller.command_validate(self.args())

    def test_context_budget_rejects_wrong_metric_scope(self) -> None:
        self.initialize()
        self.write_plan()
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8").replace(
                "- metric_scope: capsule_plus_referenced_files",
                "- metric_scope: capsule_only",
                1,
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "metric_scope"):
            controller.command_validate(self.args())

    def test_skill_metadata_is_explicit_only(self) -> None:
        skill_root = Path(__file__).resolve().parents[1]
        skill = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        metadata = (skill_root / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("description: Explicit-invocation only.", skill)
        self.assertIn("## Activation gate", skill)
        self.assertIn("allow_implicit_invocation: false", metadata)


if __name__ == "__main__":
    unittest.main()
