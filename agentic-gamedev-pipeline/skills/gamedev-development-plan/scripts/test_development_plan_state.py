#!/usr/bin/env python3
"""Tests for the development-plan controller and contract."""

from __future__ import annotations

import hashlib
import sys
import subprocess
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import development_plan_state as controller


PRD = """---
document_type: product-requirements
status: approved
revision: 2
language: English
approved_at: 2026-08-03T12:00:00Z
---
# Product Requirements

## Product Outcome

Playable outcome.

## Target Audience

Feature players.

## Core Gameplay Loop

Start, act, and observe the result.

## Release Target

One production-ready vertical slice.

## Scope

### In Scope

The approved feature.

### Out of Scope

Unrelated systems.

## Functional Requirements

- PRD-REQ-001: The feature starts.
- PRD-REQ-002: The feature completes.

## Quality Requirements

- PRD-NFR-001: Verification is deterministic.

## Acceptance Criteria

- PRD-AC-001: primary criterion
- PRD-AC-002: secondary criterion

## Assumptions

The current project baseline is available.

## Open Questions

None.

## Risks

Shared contract drift.
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

    def cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(Path(controller.__file__).resolve()),
                "--project-root",
                str(self.root),
                *arguments,
            ],
            text=True,
            capture_output=True,
            check=False,
        )

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
                    "schema_version": 2,
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

    def assert_init_rejected_direct_and_cli_without_mutation(
        self, message: str
    ) -> None:
        spec_state_path = self.root / controller.SPEC_STATE_RELATIVE_PATH
        upstream = {
            path: path.read_bytes()
            for path in (self.prd, self.spec, spec_state_path)
        }
        values = {
            "feature": self.feature,
            "prd": self.prd.relative_to(self.root).as_posix(),
            "spec": self.spec.relative_to(self.root).as_posix(),
            "plan": self.plan.relative_to(self.root).as_posix(),
            "decision_ledger": self.ledger.relative_to(self.root).as_posix(),
            "analyst_id": "planning-analyst-1",
        }
        with self.assertRaisesRegex(controller.DevelopmentPlanError, message):
            controller.command_init(self.args(**values))
        self.assertFalse(controller.state_path(self.root).exists())
        result = self.cli(
            "init",
            "--feature",
            values["feature"],
            "--prd",
            values["prd"],
            "--spec",
            values["spec"],
            "--plan",
            values["plan"],
            "--decision-ledger",
            values["decision_ledger"],
            "--analyst-id",
            values["analyst_id"],
        )
        self.assertEqual(2, result.returncode, msg=result.stdout or result.stderr)
        self.assertIn(message, result.stderr)
        self.assertFalse(controller.state_path(self.root).exists())
        self.assertEqual(upstream, {path: path.read_bytes() for path in upstream})

    def leave_approval_pending_after_replace(self) -> Namespace:
        self.initialize()
        self.write_plan()
        controller.command_submit(self.args())
        approval_args = self.args(
            approved_by="user", approval_note="exact interrupted approval"
        )
        real_save_state = controller.save_state
        save_count = 0

        def fail_final_save(root: Path, state: dict) -> None:
            nonlocal save_count
            save_count += 1
            if save_count == 2:
                raise OSError("simulated crash after approved plan replacement")
            real_save_state(root, state)

        with mock.patch.object(controller, "save_state", side_effect=fail_final_save):
            with self.assertRaisesRegex(OSError, "simulated crash"):
                controller.command_approve(approval_args)
        self.assertEqual("approval_pending", controller.load_state(self.root)["status"])
        return approval_args

    def accept_revised_analysis(
        self, analyst_id: str = "planning-analyst-2", mode: str = "single_owner"
    ) -> dict:
        return controller.command_accept_analysis(
            self.args(
                analyst_id=analyst_id,
                mode=mode,
                rationale="fresh analysis for the revised plan authority",
                working_set="8 files, 3 tests, one revised planning packet",
                seams_assessment="fresh review confirms one coherent integration seam",
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
        else:
            slices[0] = slices[0].replace(
                "- PRD-AC-001\n", "- PRD-AC-001\n- PRD-AC-002\n", 1
            ).replace(
                "- acceptance_ids: PRD-AC-001",
                "- acceptance_ids: PRD-AC-001, PRD-AC-002",
            )
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

    def test_init_rejects_invalid_prd_without_mutating_upstream_direct_and_cli(self) -> None:
        invalid_prds = (
            PRD.replace(
                "- PRD-REQ-001: The feature starts.",
                "PRD-REQ-001: legacy declaration without the canonical marker.",
            ),
            PRD.replace(
                "- PRD-AC-001: primary criterion",
                "- PRD-AC-001: ~~primary criterion~~",
            ),
        )
        for invalid_prd in invalid_prds:
            with self.subTest(invalid_prd=invalid_prd):
                self.prd.write_text(invalid_prd, encoding="utf-8")
                self.write_spec_and_ready_state()
                self.assert_init_rejected_direct_and_cli_without_mutation(
                    "full approved requirements contract"
                )

    def test_init_rejects_legacy_spec_state_without_mutation_direct_and_cli(self) -> None:
        spec_state_path = self.root / controller.SPEC_STATE_RELATIVE_PATH
        spec_state = __import__("json").loads(spec_state_path.read_text(encoding="utf-8"))
        spec_state["schema_version"] = 1
        spec_state_path.write_text(
            __import__("json").dumps(spec_state), encoding="utf-8"
        )
        self.assert_init_rejected_direct_and_cli_without_mutation("current schema")

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

    def test_approval_recovers_after_plan_replace_and_is_idempotent(self) -> None:
        self.initialize()
        self.write_plan()
        controller.command_submit(self.args())
        approval_args = self.args(
            approved_by="user", approval_note="exact resumable approval"
        )
        real_save_state = controller.save_state
        save_count = 0

        def fail_final_save(root: Path, state: dict) -> None:
            nonlocal save_count
            save_count += 1
            if save_count == 2:
                raise OSError("simulated crash after approved plan replacement")
            real_save_state(root, state)

        with mock.patch.object(controller, "save_state", side_effect=fail_final_save):
            with self.assertRaisesRegex(OSError, "simulated crash"):
                controller.command_approve(approval_args)

        pending = controller.load_state(self.root)
        self.assertEqual("approval_pending", pending["status"])
        self.assertIn("status: approved", self.plan.read_text(encoding="utf-8"))
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "exact original"):
            controller.command_approve(
                self.args(approved_by="user", approval_note="different retry")
            )
        approved = controller.command_approve(approval_args)
        replay = controller.command_approve(approval_args)
        self.assertEqual("approved", approved["status"])
        self.assertEqual(approved, replay)

    def test_completed_approval_replay_is_noop_after_normal_runtime_binding(self) -> None:
        self.initialize()
        self.write_plan()
        controller.command_submit(self.args())
        approval_args = self.args(
            approved_by="user", approval_note="exact replay after runtime binding"
        )
        approved = controller.command_approve(approval_args)
        controller_dir = self.root / ".agentic-pipeline"
        (controller_dir / "state.json").write_text(
            '{"phase":"preflight"}\n', encoding="utf-8"
        )
        (controller_dir / "findings.json").write_text("{}\n", encoding="utf-8")
        plan_before = self.plan.read_bytes()
        state_before = controller.state_path(self.root).read_bytes()

        replay = controller.command_approve(approval_args)
        self.assertEqual(approved, replay)
        self.assertEqual(plan_before, self.plan.read_bytes())
        self.assertEqual(state_before, controller.state_path(self.root).read_bytes())

        result = self.cli(
            "approve",
            "--approved-by",
            "user",
            "--approval-note",
            "exact replay after runtime binding",
        )
        self.assertEqual(0, result.returncode, msg=result.stdout or result.stderr)
        self.assertEqual(plan_before, self.plan.read_bytes())
        self.assertEqual(state_before, controller.state_path(self.root).read_bytes())

    def test_approval_rejects_changed_submitted_draft(self) -> None:
        self.initialize()
        self.write_plan()
        controller.command_submit(self.args())
        self.plan.write_text(self.plan.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "changed after submission"):
            controller.command_approve(
                self.args(approved_by="user", approval_note="approval")
            )

    def test_pending_approval_survives_drift_init_and_resumes(self) -> None:
        approval_args = self.leave_approval_pending_after_replace()
        original_prd = self.prd.read_text(encoding="utf-8")
        self.prd.write_text(original_prd + "source drift\n", encoding="utf-8")

        self.assertEqual("approval_pending", controller.command_status(self.args())["status"])
        status_cli = self.cli("status")
        self.assertEqual(0, status_cli.returncode, status_cli.stderr)
        self.assertEqual("approval_pending", __import__("json").loads(status_cli.stdout)["status"])
        reinitialized = controller.command_init(
            self.args(
                feature=self.feature,
                prd=self.prd.relative_to(self.root).as_posix(),
                spec=self.spec.relative_to(self.root).as_posix(),
                plan=self.plan.relative_to(self.root).as_posix(),
                decision_ledger=self.ledger.relative_to(self.root).as_posix(),
                analyst_id="ignored-during-idempotent-init",
            )
        )
        self.assertEqual("approval_pending", reinitialized["status"])

        with self.assertRaisesRegex(controller.DevelopmentPlanError, "stale"):
            controller.command_approve(approval_args)
        self.assertEqual("approval_pending", controller.load_state(self.root)["status"])
        self.prd.write_text(original_prd, encoding="utf-8")
        resumed = controller.command_approve(approval_args)
        self.assertEqual("approved", resumed["status"])
        self.assertEqual([], resumed["drift"])

    def test_pending_approval_no_drift_requires_exact_resume_direct_and_cli(self) -> None:
        for route in ("direct", "cli"):
            with self.subTest(route=route):
                if route == "direct":
                    approval_args = self.leave_approval_pending_after_replace()
                    with self.assertRaisesRegex(
                        controller.DevelopmentPlanError, "resume approve"
                    ):
                        controller.command_reinitialize(
                            self.args(analyst_id="planning-analyst-2")
                        )
                    resumed = controller.command_approve(approval_args)
                else:
                    self.leave_approval_pending_after_replace()
                    reinitialize = self.cli(
                        "reinitialize", "--analyst-id", "planning-analyst-2"
                    )
                    self.assertEqual(2, reinitialize.returncode)
                    self.assertIn("resume approve", reinitialize.stderr)
                    result = self.cli(
                        "approve",
                        "--approved-by",
                        "user",
                        "--approval-note",
                        "exact interrupted approval",
                    )
                    self.assertEqual(0, result.returncode, result.stderr)
                    resumed = __import__("json").loads(result.stdout)
                self.assertEqual("approved", resumed["status"])
                if route == "direct":
                    self.temp.cleanup()
                    self.setUp()

    def test_pending_approval_drift_reinitializes_direct_and_cli(self) -> None:
        for route in ("direct", "cli"):
            with self.subTest(route=route):
                self.leave_approval_pending_after_replace()
                pending = controller.load_state(self.root)
                submitted_sha = pending["approval_transition"]["submitted_sha256"]
                recovered_draft_sha = hashlib.sha256(
                    controller.recovered_submitted_plan_bytes(self.plan)
                ).hexdigest()
                self.assertNotEqual(submitted_sha, recovered_draft_sha)
                self.prd.write_text(
                    self.prd.read_text(encoding="utf-8") + "source drift\n",
                    encoding="utf-8",
                )
                self.write_spec_and_ready_state()
                expected_drift = controller.source_drift(self.root, pending)
                self.assertTrue(expected_drift)
                if route == "direct":
                    renewed = controller.command_reinitialize(
                        self.args(analyst_id="planning-analyst-2")
                    )
                else:
                    result = self.cli(
                        "reinitialize", "--analyst-id", "planning-analyst-2"
                    )
                    self.assertEqual(0, result.returncode, result.stderr)
                    renewed = __import__("json").loads(result.stdout)
                self.assertEqual("analyzing", renewed["status"])
                self.assertEqual("planning-analyst-2", renewed["analyst_id"])
                self.assertNotIn("approval_transition", renewed)
                self.assertEqual(recovered_draft_sha, controller.sha256(self.plan))
                self.assertIn("status: draft", self.plan.read_text(encoding="utf-8"))
                event = renewed["history"][-1]
                self.assertEqual(
                    "plan_approval_superseded_by_reinitialize", event["event"]
                )
                self.assertEqual(expected_drift, event["source_drift"])
                self.assertEqual(recovered_draft_sha, event["resulting_draft_sha256"])
                self.assertEqual("planning-analyst-2", event["reinitialized_by_analyst_id"])
                if route == "direct":
                    self.temp.cleanup()
                    self.setUp()

    def test_pending_approval_drift_reinitialize_is_crash_idempotent(self) -> None:
        self.leave_approval_pending_after_replace()
        pending = controller.load_state(self.root)
        submitted_sha = pending["approval_transition"]["submitted_sha256"]
        recovered_draft_sha = hashlib.sha256(
            controller.recovered_submitted_plan_bytes(self.plan)
        ).hexdigest()
        self.prd.write_text(
            self.prd.read_text(encoding="utf-8") + "source drift\n",
            encoding="utf-8",
        )
        self.write_spec_and_ready_state()
        with mock.patch.object(
            controller, "save_state", side_effect=OSError("simulated reinitialize crash")
        ):
            with self.assertRaisesRegex(OSError, "simulated reinitialize crash"):
                controller.command_reinitialize(
                    self.args(analyst_id="planning-analyst-2")
                )
        self.assertNotEqual(submitted_sha, recovered_draft_sha)
        self.assertEqual(recovered_draft_sha, controller.sha256(self.plan))
        self.assertEqual("approval_pending", controller.load_state(self.root)["status"])
        renewed = controller.command_reinitialize(
            self.args(analyst_id="planning-analyst-2")
        )
        self.assertEqual("analyzing", renewed["status"])
        self.assertEqual(
            1,
            sum(
                item.get("event") == "plan_approval_superseded_by_reinitialize"
                for item in renewed["history"]
                if isinstance(item, dict)
            ),
        )

    def test_pending_reinitialize_crash_can_resume_approval_if_sources_are_restored(self) -> None:
        approval_args = self.leave_approval_pending_after_replace()
        original_prd = self.prd.read_text(encoding="utf-8")
        self.prd.write_text(original_prd + "source drift\n", encoding="utf-8")
        self.write_spec_and_ready_state()
        with mock.patch.object(
            controller, "save_state", side_effect=OSError("simulated reinitialize crash")
        ):
            with self.assertRaisesRegex(OSError, "simulated reinitialize crash"):
                controller.command_reinitialize(
                    self.args(analyst_id="planning-analyst-2")
                )
        self.assertIn("status: draft", self.plan.read_text(encoding="utf-8"))
        self.prd.write_text(original_prd, encoding="utf-8")
        self.write_spec_and_ready_state()
        resumed = controller.command_approve(approval_args)
        self.assertEqual("approved", resumed["status"])
        self.assertEqual([], resumed["drift"])

    def test_pending_approval_drift_reinitialize_rejects_tampered_transition_and_bytes(self) -> None:
        for tamper, route in (("transition", "direct"), ("plan-bytes", "cli")):
            with self.subTest(tamper=tamper, route=route):
                self.leave_approval_pending_after_replace()
                self.prd.write_text(
                    self.prd.read_text(encoding="utf-8") + "source drift\n",
                    encoding="utf-8",
                )
                self.write_spec_and_ready_state()
                before_plan = self.plan.read_bytes()
                if tamper == "transition":
                    state = controller.load_state(self.root)
                    state["approval_transition"]["approved_by"] = "director"
                    controller.save_state(self.root, state)
                    with self.assertRaisesRegex(
                        controller.DevelopmentPlanError, "transition is malformed"
                    ):
                        controller.command_reinitialize(
                            self.args(analyst_id="planning-analyst-2")
                        )
                    self.assertEqual(before_plan, self.plan.read_bytes())
                else:
                    self.plan.write_bytes(before_plan + b"unexpected\n")
                    result = self.cli(
                        "reinitialize", "--analyst-id", "planning-analyst-2"
                    )
                    self.assertEqual(2, result.returncode)
                    self.assertIn("unexpected development-plan bytes", result.stderr)
                self.assertEqual(
                    "approval_pending", controller.load_state(self.root)["status"]
                )
                if route == "direct":
                    self.temp.cleanup()
                    self.setUp()

    def test_abort_approval_surface_is_absent_direct_and_cli(self) -> None:
        self.leave_approval_pending_after_replace()
        before_state = controller.load_state(self.root)
        before_sha = controller.sha256(self.plan)
        self.assertFalse(hasattr(controller, "command_abort_approval"))
        result = self.cli(
            "abort-approval",
            "--aborted-by",
            "untrusted-arbitrary-string",
            "--reason",
            "cancel user approval",
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("invalid choice", result.stderr)
        self.assertEqual(before_state, controller.load_state(self.root))
        self.assertEqual(before_sha, controller.sha256(self.plan))

    def test_completed_approval_replay_checks_source_freshness_direct_and_cli(self) -> None:
        for route in ("direct", "cli"):
            with self.subTest(route=route):
                self.initialize()
                self.write_plan()
                controller.command_submit(self.args())
                approval_args = self.args(
                    approved_by="user", approval_note="freshness-bound approval"
                )
                controller.command_approve(approval_args)
                self.prd.write_text(
                    self.prd.read_text(encoding="utf-8") + "source drift\n",
                    encoding="utf-8",
                )
                if route == "direct":
                    with self.assertRaisesRegex(controller.DevelopmentPlanError, "stale"):
                        controller.command_approve(approval_args)
                else:
                    result = self.cli(
                        "approve",
                        "--approved-by",
                        "user",
                        "--approval-note",
                        "freshness-bound approval",
                    )
                    self.assertEqual(2, result.returncode)
                    self.assertIn("stale", result.stderr)
                self.assertEqual("stale", controller.load_state(self.root)["status"])
                if route == "direct":
                    self.temp.cleanup()
                    self.setUp()

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

    def test_acceptance_ranges_are_rejected_in_every_slice_contract_surface(self) -> None:
        self.initialize()
        self.write_plan()
        original = self.plan.read_text(encoding="utf-8")
        replacements = (
            (
                "### Requirements\n\n- PRD-REQ-001\n- PRD-AC-001",
                "### Requirements\n\n- PRD-REQ-001\n- PRD-AC-001..003",
                "range shorthand",
            ),
            (
                "### Scope Contract\n\n- acceptance_ids: PRD-AC-001",
                "### Scope Contract\n\n- acceptance_ids: PRD-AC-001..003",
                "non-literal acceptance ID",
            ),
            (
                "### Coverage Contract\n\n- acceptance_ids: PRD-AC-001",
                "### Coverage Contract\n\n- acceptance_ids: PRD-AC-001..003",
                "non-literal acceptance ID",
            ),
        )
        for before, after, expected in replacements:
            with self.subTest(surface=before.splitlines()[0]):
                self.plan.write_text(original.replace(before, after), encoding="utf-8")
                with self.assertRaisesRegex(controller.DevelopmentPlanError, expected):
                    controller.command_validate(self.args())
        self.plan.write_text(original, encoding="utf-8")

    def test_approved_plan_revision_requires_fresh_submit_and_approval(self) -> None:
        self.initialize()
        self.write_plan()
        submitted = controller.command_submit(self.args())
        approved = controller.command_approve(
            self.args(approved_by="user", approval_note="initial exact SHA approval")
        )
        prior_approved_sha = approved["approval"]["approved_sha256"]

        reopened = controller.command_revise_approved(
            self.args(
                reason="replace legacy acceptance ranges with literal IDs",
                reopened_by="development-plan-director-2",
                analyst_id="planning-analyst-2",
            )
        )

        self.assertEqual("analyzing", reopened["status"])
        self.assertEqual("planning-analyst-2", reopened["analyst_id"])
        self.assertIsNone(reopened["analysis"])
        self.assertIsNone(reopened["submission"])
        self.assertIsNone(reopened["approval"])
        plan_text = self.plan.read_text(encoding="utf-8")
        self.assertIn("status: draft", plan_text)
        self.assertIn("revision: 2", plan_text)
        self.assertIn("planning_analyst_id: planning-analyst-2", plan_text)
        self.assertNotIn("approved_by:", plan_text)
        event = reopened["history"][-1]
        self.assertEqual("approved_plan_revision_opened", event["event"])
        self.assertEqual(prior_approved_sha, event["prior_approved_sha256"])
        self.assertEqual(
            "revoked_by_plan_revision", event["prior_approval_disposition"]
        )
        self.assertEqual(event["opened_at"], event["approval_revoked_at"])
        self.assertEqual(
            submitted["submission"]["sha256"],
            event["prior_submission"]["sha256"],
        )
        self.assertEqual(
            prior_approved_sha, event["prior_approval"]["approved_sha256"]
        )
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "submitted draft"):
            controller.command_approve(
                self.args(approved_by="user", approval_note="cannot reuse approval")
            )

        with self.assertRaisesRegex(controller.DevelopmentPlanError, "analyzing"):
            controller.command_submit(self.args())
        self.accept_revised_analysis()
        revised_submission = controller.command_submit(self.args())
        self.assertNotEqual(
            submitted["submission"]["sha256"],
            revised_submission["submission"]["sha256"],
        )
        revised_approval = controller.command_approve(
            self.args(approved_by="user", approval_note="fresh revision 2 approval")
        )
        self.assertEqual("approved", revised_approval["status"])
        self.assertNotEqual(
            prior_approved_sha, revised_approval["approval"]["approved_sha256"]
        )
        self.assertEqual(
            "approved_plan_revision_opened", revised_approval["history"][-1]["event"]
        )

    def test_approved_plan_revision_rejects_unapproved_byte_drift(self) -> None:
        self.initialize()
        self.write_plan()
        controller.command_submit(self.args())
        controller.command_approve(
            self.args(approved_by="user", approval_note="exact SHA approval")
        )
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "approval SHA"):
            controller.command_revise_approved(
                self.args(
                    reason="attempt revision",
                    reopened_by="director",
                    analyst_id="planning-analyst-2",
                )
            )

    def test_legacy_approved_range_plan_can_only_be_repaired_after_reopen(self) -> None:
        self.initialize()
        self.write_plan()
        controller.command_submit(self.args())
        controller.command_approve(
            self.args(approved_by="user", approval_note="legacy validator approval")
        )
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8").replace(
                "- acceptance_ids: PRD-AC-001",
                "- acceptance_ids: PRD-AC-001..003",
            ),
            encoding="utf-8",
        )
        legacy_state = controller.load_state(self.root)
        legacy_state["approval"]["approved_sha256"] = controller.sha256(self.plan)
        controller.save_state(self.root, legacy_state)

        reopened = controller.command_revise_approved(
            self.args(
                reason="repair legacy range syntax",
                reopened_by="migration-director",
                analyst_id="planning-analyst-2",
            )
        )

        self.assertEqual("analyzing", reopened["status"])
        self.accept_revised_analysis()
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "non-literal"):
            controller.command_submit(self.args())

    def test_approved_plan_revision_requires_fresh_analyst(self) -> None:
        self.initialize()
        self.write_plan()
        controller.command_submit(self.args())
        controller.command_approve(
            self.args(approved_by="user", approval_note="exact SHA approval")
        )

        with self.assertRaisesRegex(controller.DevelopmentPlanError, "fresh"):
            controller.command_revise_approved(
                self.args(
                    reason="repair plan",
                    reopened_by="director",
                    analyst_id="planning-analyst-1",
                )
            )

    def test_revise_freshness_normalizes_current_and_nested_history_aliases(self) -> None:
        self.initialize()
        self.write_plan()
        controller.command_submit(self.args())
        controller.command_approve(
            self.args(approved_by="user", approval_note="exact SHA approval")
        )
        state = controller.load_state(self.root)
        state["history"] = [
            {"legacy_cycle": {"planning_analyst_id": " History-Agent "}},
            {"revision_reopen": {"new_analyst_id": "Earlier-Agent"}},
        ]
        controller.save_state(self.root, state)
        for alias in (
            "  PLANNING-ANALYST-１ ",
            "history-agent",
            "ＥＡＲＬＩＥＲ-agent",
        ):
            with self.subTest(alias=alias):
                with self.assertRaisesRegex(controller.DevelopmentPlanError, "fresh"):
                    controller.command_revise_approved(
                        self.args(
                            reason="repair plan",
                            reopened_by="director",
                            analyst_id=alias,
                        )
                    )

    def test_approved_plan_revision_is_blocked_after_runtime_binding(self) -> None:
        self.initialize()
        self.write_plan()
        controller.command_submit(self.args())
        controller.command_approve(
            self.args(approved_by="user", approval_note="exact SHA approval")
        )
        runtime_state = self.root / controller.RUNTIME_STATE_RELATIVE_PATH
        runtime_state.write_text("{}\n", encoding="utf-8")

        with self.assertRaisesRegex(controller.DevelopmentPlanError, "runtime pipeline state"):
            controller.command_revise_approved(
                self.args(
                    reason="unsafe late repair",
                    reopened_by="director",
                    analyst_id="planning-analyst-2",
                )
            )

    def test_bound_approved_plan_revision_requires_exact_authority_recovery_hold(self) -> None:
        self.initialize()
        self.write_plan()
        controller.command_submit(self.args())
        controller.command_approve(
            self.args(approved_by="user", approval_note="exact SHA approval")
        )
        approved_sha = controller.sha256(self.plan)
        runtime_dir = self.root / ".agentic-pipeline"
        hold = {
            "status": "open",
            "reason": "repair authority",
            "opened_at": "2026-08-13T00:00:00+00:00",
            "authorized_by": "director",
            "feature": self.feature,
            "revision": "runtime-revision",
            "requirements": {"sha256": controller.sha256(self.prd)},
            "specification": {"sha256": controller.sha256(self.spec)},
            "development_plan": {"sha256": approved_sha},
        }
        payload = {
            "feature": hold["feature"],
            "opened_at": hold["opened_at"],
            "authorized_by": hold["authorized_by"],
            "reason": hold["reason"],
            "requirements_sha256": hold["requirements"]["sha256"],
            "spec_sha256": hold["specification"]["sha256"],
            "plan_sha256": approved_sha,
            "revision": hold["revision"],
        }
        exact_token = "ARH-" + __import__("hashlib").sha256(
            __import__("json").dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()[:32].upper()
        hold["token"] = exact_token
        (runtime_dir / "state.json").write_text(
            __import__("json").dumps(
                {
                    "phase": "authority_recovery_hold",
                    "authority_recovery_hold": hold,
                }
            ),
            encoding="utf-8",
        )
        (runtime_dir / "findings.json").write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "exact open"):
            controller.command_revise_approved(
                self.args(
                    reason="repair authority",
                    reopened_by="director",
                    analyst_id="planning-analyst-2",
                    recovery_token="ARH-WRONG",
                )
            )
        reopened = controller.command_revise_approved(
            self.args(
                reason="repair authority",
                reopened_by="director",
                analyst_id="planning-analyst-2",
                    recovery_token=exact_token,
            )
        )
        self.assertEqual("analyzing", reopened["status"])
        self.assertEqual(exact_token, reopened["recovery_authorization"]["token"])
        self.assertIsNone(reopened["approval"])

    def test_interrupted_approved_plan_revision_resumes_fail_closed(self) -> None:
        self.initialize()
        self.write_plan()
        controller.command_submit(self.args())
        controller.command_approve(
            self.args(approved_by="user", approval_note="exact SHA approval")
        )
        real_save_state = controller.save_state
        save_count = 0

        def fail_final_save(root: Path, state: dict) -> None:
            nonlocal save_count
            save_count += 1
            if save_count == 2:
                raise OSError("simulated interruption after draft replacement")
            real_save_state(root, state)

        args = self.args(
            reason="resumable repair",
            reopened_by="director",
            analyst_id="planning-analyst-2",
        )
        with mock.patch.object(controller, "save_state", side_effect=fail_final_save):
            with self.assertRaisesRegex(OSError, "simulated interruption"):
                controller.command_revise_approved(args)

        pending = controller.load_state(self.root)
        self.assertEqual("revision_reopen_pending", pending["status"])
        self.assertIn("status: draft", self.plan.read_text(encoding="utf-8"))
        original_prd = self.prd.read_text(encoding="utf-8")
        self.prd.write_text(original_prd + "source drift\n", encoding="utf-8")
        status = controller.command_status(self.args())
        self.assertEqual("revision_reopen_pending", status["status"])
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "source-authority drift"):
            controller.command_revise_approved(args)
        self.prd.write_text(original_prd, encoding="utf-8")
        resumed = controller.command_revise_approved(args)
        self.assertEqual("analyzing", resumed["status"])
        self.assertNotIn("revision_reopen", resumed)
        self.assertEqual(
            "approved_plan_revision_opened", resumed["history"][-1]["event"]
        )

    def test_coverage_acceptance_set_must_equal_scope_set(self) -> None:
        self.initialize()
        self.write_plan()
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8").replace(
                "### Coverage Contract\n\n- acceptance_ids: PRD-AC-001, PRD-AC-002",
                "### Coverage Contract\n\n- acceptance_ids: PRD-AC-002",
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "exactly equal"):
            controller.command_validate(self.args())

    def test_slice_union_must_cover_every_prd_acceptance_direct_and_cli(self) -> None:
        self.initialize()
        self.write_plan()
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8")
            .replace("- PRD-AC-002\n", "", 1)
            .replace(
                "- acceptance_ids: PRD-AC-001, PRD-AC-002",
                "- acceptance_ids: PRD-AC-001",
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "missing PRD-AC-002"):
            controller.command_submit(self.args())
        result = self.cli("submit")
        self.assertEqual(2, result.returncode)
        self.assertIn("missing PRD-AC-002", result.stderr)

    def test_cross_slice_overlap_is_allowed_when_union_is_complete(self) -> None:
        self.initialize(mode="sequential_slices")
        self.write_plan(mode="sequential_slices", slice_count=2)
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8")
            .replace("- PRD-AC-002\n", "- PRD-AC-001\n- PRD-AC-002\n", 1)
            .replace(
                "- acceptance_ids: PRD-AC-002",
                "- acceptance_ids: PRD-AC-001, PRD-AC-002",
            ),
            encoding="utf-8",
        )
        submitted = controller.command_submit(self.args())
        self.assertEqual("awaiting_user_approval", submitted["status"])
        self.assertEqual(0, self.cli("submit").returncode)

    def test_duplicate_acceptance_rows_within_one_requirements_surface_fail(self) -> None:
        self.initialize()
        self.write_plan()
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8").replace(
                "- PRD-AC-001\n", "- PRD-AC-001\n- PRD-AC-001\n", 1
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "repeats acceptance ID row"):
            controller.command_validate(self.args())
        result = self.cli("validate-plan")
        self.assertEqual(2, result.returncode)
        self.assertIn("repeats acceptance ID row", result.stderr)

    def test_unknown_only_acceptance_id_is_rejected_against_prd_inventory(self) -> None:
        self.initialize()
        self.write_plan()
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8").replace(
                "PRD-AC-001", "PRD-AC-unknown-only"
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "absent from the approved PRD"):
            controller.command_validate(self.args())

    def test_incidental_acceptance_id_outside_canonical_section_has_no_authority(self) -> None:
        self.prd.write_text(
            PRD.replace(
                "The current project baseline is available.",
                "The current project baseline is available.\n\n"
                "Example only: PRD-AC-incidental.",
            ),
            encoding="utf-8",
        )
        self.write_spec_and_ready_state()
        self.initialize()
        self.write_plan()
        controller.command_validate(self.args())
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8").replace(
                "PRD-AC-001", "PRD-AC-incidental"
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "absent from the approved PRD"):
            controller.command_validate(self.args())
        result = self.cli("validate-plan")
        self.assertEqual(2, result.returncode)
        self.assertIn("absent from the approved PRD", result.stderr)

    def test_planner_direct_and_cli_reject_ambiguous_or_duplicate_criteria(self) -> None:
        invalid_sections = (
            "- PRD-AC-001",
            "- PRD-AC-001:",
            "- PRD-AC-001_invalid: adjacent invalid token",
            "- PRD-AC-001…003 — Unicode ellipsis range",
            "- PRD-AC-001 to PRD-AC-003 — textual range",
            "- PRD-AC-001\n  ..\n  003: multiline range",
            "- PRD-AC-001 to\n  PRD-AC-003: multiline textual range",
            "- PRD-AC-001: first\n- PRD-AC-001: duplicate",
        )
        for invalid in invalid_sections:
            with self.subTest(invalid=invalid):
                self.prd.write_text(
                    PRD.replace(
                        "- PRD-AC-001: primary criterion\n- PRD-AC-002: secondary criterion",
                        invalid,
                    ),
                    encoding="utf-8",
                )
                self.write_spec_and_ready_state()
                self.assert_init_rejected_direct_and_cli_without_mutation(
                    "full approved requirements contract"
                )
                self.temp.cleanup()
                self.setUp()

    def test_planner_direct_and_cli_use_markdown_structural_prd_authority(self) -> None:
        examples = (
            "```md\n## Acceptance Criteria\n- PRD-AC-fenced: no\n```",
            "~~~~ markdown\n## Acceptance Criteria\n- PRD-AC-fenced: no\n~~~~",
            "    ## Acceptance Criteria\n    - PRD-AC-indented: no",
            "> ## Acceptance Criteria\n> - PRD-AC-quoted: no",
        )
        for example in examples:
            with self.subTest(example=example):
                self.prd.write_text(
                    PRD.replace(
                        "## Acceptance Criteria\n",
                        "## Acceptance Criteria\n\n" + example + "\n",
                    ),
                    encoding="utf-8",
                )
                self.write_spec_and_ready_state()
                self.initialize()
                self.write_plan()
                controller.command_validate(self.args())
                self.assertEqual(0, self.cli("validate-plan").returncode)
                self.temp.cleanup()
                self.setUp()

    def test_planner_direct_and_cli_use_terminator_aware_html_authority(self) -> None:
        hidden = "\n".join(
            (
                "<pre>\n\n## Acceptance Criteria\n- PRD-AC-pre: hidden\n</pre>",
                "<script>\n\n## Acceptance Criteria\n- PRD-AC-script: hidden\n</script>",
                "<style>\n\n## Acceptance Criteria\n- PRD-AC-style: hidden\n</style>",
                "<textarea>\n\n## Acceptance Criteria\n- PRD-AC-textarea: hidden\n</textarea>",
                "<!--\n\n## Acceptance Criteria\n- PRD-AC-comment: hidden\n-->",
                "<?example\n\n## Acceptance Criteria\n- PRD-AC-pi: hidden\n?>",
                "<!DOCTYPE\n\n## Acceptance Criteria\n- PRD-AC-declaration: hidden\n>",
                "<![CDATA[\n\n## Acceptance Criteria\n- PRD-AC-cdata: hidden\n]]>",
            )
        )
        self.prd.write_text(
            PRD.replace("## Acceptance Criteria", hidden + "\n## Acceptance Criteria"),
            encoding="utf-8",
        )
        self.write_spec_and_ready_state()
        self.initialize()
        self.write_plan()
        controller.command_validate(self.args())
        self.assertEqual(0, self.cli("validate-plan").returncode)

    def test_planner_direct_and_cli_accept_public_alnum_hyphen_id(self) -> None:
        self.prd.write_text(PRD.replace("PRD-AC-001", "PRD-AC-save-v2"), encoding="utf-8")
        self.write_spec_and_ready_state()
        self.initialize()
        self.write_plan()
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8").replace("PRD-AC-001", "PRD-AC-save-v2"),
            encoding="utf-8",
        )
        controller.command_validate(self.args())
        self.assertEqual(0, self.cli("validate-plan").returncode)

    def test_planner_direct_and_cli_reject_fenced_only_or_near_prd_heading(self) -> None:
        replacements = (
            "```\n## Acceptance Criteria\n- PRD-AC-001: hidden\n```",
            "    ## Acceptance Criteria\n    - PRD-AC-001: hidden",
            "> ## Acceptance Criteria\n> - PRD-AC-001: hidden",
            "### Acceptance Criteria\n- PRD-AC-001: near",
        )
        canonical = (
            "## Acceptance Criteria\n\n"
            "- PRD-AC-001: primary criterion\n- PRD-AC-002: secondary criterion"
        )
        for replacement in replacements:
            with self.subTest(replacement=replacement):
                self.prd.write_text(PRD.replace(canonical, replacement), encoding="utf-8")
                self.write_spec_and_ready_state()
                self.assert_init_rejected_direct_and_cli_without_mutation(
                    "full approved requirements contract"
                )
                self.temp.cleanup()
                self.setUp()

    def test_planner_requirements_reject_shared_full_and_short_range_matrix(self) -> None:
        ranges = (
            "PRD-AC-001.002",
            "PRD-AC-001 .. PRD-AC-002",
            "PRD-AC-001…002",
            "PRD-AC-001 – PRD-AC-002",
            "PRD-AC-001—002",
            "PRD-AC-001 to PRD-AC-002",
            "PRD-AC-save-v1 TO save-v2",
            "PRD-AC-001\n  .. 002",
            "PRD-AC-save-v1\n  to save-v2",
        )
        for acceptance_range in ranges:
            with self.subTest(acceptance_range=acceptance_range):
                self.initialize()
                self.write_plan()
                self.plan.write_text(
                    self.plan.read_text(encoding="utf-8").replace(
                        "- PRD-AC-001\n", f"- {acceptance_range}\n"
                    ),
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(controller.DevelopmentPlanError, "range shorthand"):
                    controller.command_validate(self.args())
                self.assertEqual(2, self.cli("validate-plan").returncode)
                self.temp.cleanup()
                self.setUp()

    def test_planner_requirements_reject_adjacent_invalid_id_direct_and_cli(self) -> None:
        self.initialize()
        self.write_plan()
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8").replace(
                "- PRD-AC-001\n", "- PRD-AC-001_invalid\n"
            ),
            encoding="utf-8",
        )
        with self.assertRaises(controller.DevelopmentPlanError):
            controller.command_validate(self.args())
        result = self.cli("validate-plan")
        self.assertEqual(2, result.returncode)

    def test_planner_rejects_hidden_rendering_and_unicode_boundary_direct_cli(self) -> None:
        canonical = "- PRD-AC-001: primary criterion"
        for invalid in (
            "- PRD-AC-001: <!-- hidden -->",
            "- PRD-AC-001: <br>",
            "- `PRD-AC-001: unmatched",
            "- PRD-AC-001\u200d: invalid boundary",
            "- PRD-AC-001: *emphasized outcome*",
            "- PRD-AC-001: under_scored outcome",
            "- PRD-AC-001: ~~struck outcome~~",
            "- PRD-AC-001: escaped \\* outcome",
            "- PRD-AC-001: encoded &amp; outcome",
        ):
            with self.subTest(invalid=invalid):
                self.prd.write_text(PRD.replace(canonical, invalid), encoding="utf-8")
                self.write_spec_and_ready_state()
                self.assert_init_rejected_direct_and_cli_without_mutation(
                    "full approved requirements contract"
                )
                self.temp.cleanup()
                self.setUp()

    def test_mixed_valid_and_unknown_acceptance_id_is_rejected(self) -> None:
        self.initialize()
        self.write_plan()
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8")
            .replace(
                "### Requirements\n\n- PRD-REQ-001\n- PRD-AC-001",
                "### Requirements\n\n- PRD-REQ-001\n- PRD-AC-001\n- PRD-AC-unknown-mixed",
            )
            .replace(
                "- acceptance_ids: PRD-AC-001",
                "- acceptance_ids: PRD-AC-001, PRD-AC-unknown-mixed",
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "unknown-mixed"):
            controller.command_validate(self.args())

    def test_revise_approved_rejects_same_director_and_analyst_after_normalization(self) -> None:
        self.initialize()
        self.write_plan()
        controller.command_submit(self.args())
        controller.command_approve(
            self.args(approved_by="user", approval_note="exact SHA approval")
        )
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "distinct Director"):
            controller.command_revise_approved(
                self.args(
                    reason="repair plan",
                    reopened_by="  DIRECTOR-２  ",
                    analyst_id="director-2",
                )
            )

    def test_plan_validation_rejects_duplicate_or_malformed_top_level_revision(self) -> None:
        for replacement in (
            "revision: 1\nrevision: 2",
            "revision: not-an-integer",
            "revision: 0",
            'revision: "1"',
            "revision: '1'",
        ):
            with self.subTest(replacement=replacement):
                self.initialize()
                self.write_plan()
                self.plan.write_text(
                    self.plan.read_text(encoding="utf-8").replace(
                        "revision: 1", replacement, 1
                    ),
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(
                    controller.DevelopmentPlanError,
                    "exactly one top-level revision|one positive integer",
                ):
                    controller.command_validate(self.args())
                self.assertEqual(2, self.cli("validate-plan").returncode)
                with self.assertRaises(controller.DevelopmentPlanError):
                    controller.command_submit(self.args())
                self.assertEqual(2, self.cli("submit").returncode)
                self.temp.cleanup()
                self.setUp()

    def test_revise_approved_rejects_duplicate_or_malformed_revision_authority(self) -> None:
        for replacement in (
            "revision: 1\nrevision: bogus",
            "revision: bogus",
            'revision: "1"',
            "revision: '1'",
        ):
            with self.subTest(replacement=replacement):
                self.initialize()
                self.write_plan()
                controller.command_submit(self.args())
                controller.command_approve(
                    self.args(approved_by="user", approval_note="exact SHA approval")
                )
                self.plan.write_text(
                    self.plan.read_text(encoding="utf-8").replace(
                        "revision: 1", replacement, 1
                    ),
                    encoding="utf-8",
                )
                state = controller.load_state(self.root)
                state["approval"]["approved_sha256"] = controller.sha256(self.plan)
                controller.save_state(self.root, state)
                with self.assertRaisesRegex(
                    controller.DevelopmentPlanError,
                    "exactly one top-level revision|one positive integer",
                ):
                    controller.command_revise_approved(
                        self.args(
                            reason="repair malformed revision",
                            reopened_by="director",
                            analyst_id="planning-analyst-2",
                        )
                    )
                result = self.cli(
                    "revise-approved",
                    "--reason", "repair malformed revision",
                    "--reopened-by", "director",
                    "--analyst-id", "planning-analyst-2",
                )
                self.assertEqual(2, result.returncode)
                self.temp.cleanup()
                self.setUp()

    def test_approve_rejects_quoted_revision_direct_and_cli(self) -> None:
        for use_cli in (False, True):
            with self.subTest(use_cli=use_cli):
                self.initialize()
                self.write_plan()
                controller.command_submit(self.args())
                self.plan.write_text(
                    self.plan.read_text(encoding="utf-8").replace(
                        "revision: 1", 'revision: "1"', 1
                    ),
                    encoding="utf-8",
                )
                state = controller.load_state(self.root)
                state["submission"]["sha256"] = controller.sha256(self.plan)
                controller.save_state(self.root, state)
                if use_cli:
                    result = self.cli(
                        "approve", "--approved-by", "user",
                        "--approval-note", "quoted revision must fail",
                    )
                    self.assertEqual(2, result.returncode)
                else:
                    with self.assertRaisesRegex(
                        controller.DevelopmentPlanError, "positive integer"
                    ):
                        controller.command_approve(
                            self.args(
                                approved_by="user",
                                approval_note="quoted revision must fail",
                            )
                        )
                self.temp.cleanup()
                self.setUp()

    def test_sequential_slices_require_vertical_ordered_dependencies(self) -> None:
        self.initialize(mode="sequential_slices")
        self.write_plan(mode="sequential_slices", slice_count=2)
        result = controller.command_validate(self.args())
        self.assertEqual(result["slice_ids"], ["SLICE-001", "SLICE-002"])

    def test_scope_contract_omits_technical_baseline_and_ignores_legacy_field(self) -> None:
        self.initialize()
        self.write_plan()
        self.assertNotIn("scope_baseline_revision", self.plan.read_text(encoding="utf-8"))
        self.assertEqual(["SLICE-001"], controller.command_validate(self.args())["slice_ids"])

        text = self.plan.read_text(encoding="utf-8").replace(
            "- verification_scope: tests/feature-1.spec.lua and affected feature suite",
            "- verification_scope: tests/feature-1.spec.lua and affected feature suite\n"
            "- scope_baseline_revision: legacy-controller-digest",
        )
        self.plan.write_text(text, encoding="utf-8")
        self.assertEqual(["SLICE-001"], controller.command_validate(self.args())["slice_ids"])

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

    def test_reinitialize_rejects_normalized_alias_from_reinitialized_history(self) -> None:
        self.test_stale_state_reinitializes_only_after_new_spec_ready()
        state = controller.load_state(self.root)
        state["status"] = "stale"
        state["history"].append(
            {"reinitialized": {"planning_analyst_id": " Nested-History-３ "}}
        )
        controller.save_state(self.root, state)
        for alias in (" PLANNING-ANALYST-２ ", "nested-history-3"):
            with self.subTest(alias=alias):
                with self.assertRaisesRegex(controller.DevelopmentPlanError, "all planning history"):
                    controller.command_reinitialize(self.args(analyst_id=alias))

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

    def test_slice_research_briefs_are_unique_and_bounded_to_three(self) -> None:
        self.initialize()
        self.write_plan()
        row = "- RESEARCH-001 | question=find exact feature entry point | paths=src/feature | exclusions=unrelated systems | evidence=owners and contracts | stop=entry point confirmed"
        duplicate = self.plan.read_text(encoding="utf-8").replace(row, row + "\n" + row)
        self.plan.write_text(duplicate, encoding="utf-8")
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "must be unique"):
            controller.command_validate(self.args())

        self.write_plan()
        rows = "\n".join(
            row.replace("RESEARCH-001", f"RESEARCH-{index:03d}")
            for index in range(1, 5)
        )
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8").replace(row, rows),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(controller.DevelopmentPlanError, "at most three"):
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
