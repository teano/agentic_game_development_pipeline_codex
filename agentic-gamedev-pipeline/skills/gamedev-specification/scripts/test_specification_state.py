#!/usr/bin/env python3
"""Tests for the bounded specification convergence controller."""

from __future__ import annotations

import sys
import json
import hashlib
import subprocess
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

## Product Outcome

Playable result.

## Target Audience

Players.

## Core Gameplay Loop

Act and observe.

## Release Target

Android build.

## Scope

### In Scope

Simulation evidence.

### Out of Scope

Physical-device smoke.

## Functional Requirements

- PRD-REQ-001: Feature works.

## Quality Requirements

- PRD-NFR-001: Behavior is deterministic.

## Acceptance Criteria

- PRD-AC-001: Feature works in Unity simulation.

## Assumptions

Unity Device Simulator is available.

## Open Questions

None.

## Risks

Android build gate remains.
"""


class SpecificationStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.feature_dir = self.root / "docs" / "Features" / "template" / "sample-feature"
        self.feature_dir.mkdir(parents=True)
        self.prd = self.feature_dir / "product-requirements.md"
        self.spec = self.feature_dir / "technical-specification.md"
        self.prd.write_text(PRD, encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def args(self, **values: object) -> Namespace:
        return Namespace(project_root=str(self.root), **values)

    def write_spec(
        self,
        status: str = "draft",
        suffix: str = "",
        nested_trace: bool = True,
        revision: int = 1,
    ) -> None:
        trace = controller.sha256(self.prd)
        authority = (
            f"""product_authority:
  path: docs/Features/template/sample-feature/product-requirements.md
  revision: 3
  sha256: {trace}"""
            if nested_trace
            else f"""source_prd_path: docs/Features/template/sample-feature/product-requirements.md
source_prd_revision: 3
source_prd_sha256: {trace}"""
        )
        self.spec.write_text(
            f"""---
document_type: technical-specification
status: {status}
revision: {revision}
language: English
{authority}
---
# Technical Specification
{suffix}
""",
            encoding="utf-8",
        )

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

    def make_ready(self) -> dict:
        self.initialize()
        self.write_spec(status="approved")
        controller.command_accept_spec(self.args())
        self.start_and_record(1, major=0, coverage_complete=True)
        return controller.command_confirm_ready(
            self.args(architect_id="architect-1", confirmation="same SHA confirmed")
        )

    def write_full_approved_prd(self, revision: int, approved_at: str) -> None:
        self.prd.write_text(
            f"""---
document_type: product-requirements
status: approved
revision: {revision}
language: English
approved_at: {approved_at}
---
# Product Requirements

## Product Outcome

Playable result.

## Target Audience

Players.

## Core Gameplay Loop

Act and observe.

## Release Target

Android build.

## Scope

### In Scope

Simulation evidence.

### Out of Scope

Physical-device smoke.

## Functional Requirements

- PRD-REQ-001: Feature works.

## Quality Requirements

- PRD-NFR-001: Deterministic behavior.

## Acceptance Criteria

- PRD-AC-001: Feature works in Unity simulation.

## Assumptions

Unity Device Simulator is available.

## Open Questions

None.

## Risks

Android build gate remains.
""",
            encoding="utf-8",
        )

    def bind_authority_recovery(self, ready: dict, reason: str = "fresh PRD authority") -> str:
        state_dir = self.root / ".agentic-pipeline"
        prd_sha = ready["prd"]["sha256"]
        spec_sha = ready["ready"]["spec_sha256"]
        hold = {
            "schema": 1,
            "status": "open",
            "reason": reason,
            "authorized_by": "technical-director",
            "opened_at": "2026-08-10T00:00:00+00:00",
            "feature": "sample-feature",
            "revision": "runtime-revision",
            "product_revision": "runtime-product-revision",
            "requirements": {
                "path": ready["prd"]["path"],
                "revision": ready["prd"]["revision"],
                "sha256": prd_sha,
            },
            "specification": {
                "path": ready["specification"]["path"],
                "revision": "1",
                "sha256": spec_sha,
            },
            "development_plan": {
                "path": "docs/Features/template/sample-feature/development-plan.md",
                "sha256": "a" * 64,
            },
            "ordered_slices": ["SLICE-001"],
        }
        payload = {
            "feature": hold["feature"],
            "opened_at": hold["opened_at"],
            "authorized_by": hold["authorized_by"],
            "reason": hold["reason"],
            "requirements_sha256": prd_sha,
            "spec_sha256": spec_sha,
            "plan_sha256": "a" * 64,
            "revision": hold["revision"],
        }
        token = "ARH-" + hashlib.sha256(
            json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()[:32].upper()
        hold["token"] = token
        runtime = {
            "phase": "authority_recovery_hold",
            "authority_recovery_hold": hold,
            "active_write_lease": None,
            "write_lease_history": [],
            "engineer_runs": [],
            "engineer_clean": None,
            "last_engineer_run_id": None,
            "last_engineer_outcome": None,
            "pending_engineer_completion": None,
            "implementation_state": {"status": "pending"},
            "feature_verification_state": {"status": "pending"},
            "ordered_slices": ["SLICE-001"],
            "slices": {
                "SLICE-001": {
                    "status": "active",
                    "sealed_at": None,
                    "result_revision": None,
                    "scope_pre_edit_check": None,
                }
            },
        }
        (state_dir / "state.json").write_text(json.dumps(runtime), encoding="utf-8")
        (state_dir / "findings.json").write_text("{}\n", encoding="utf-8")
        return token

    def initialize(self, with_spec: bool = True) -> dict:
        if with_spec:
            self.write_spec()
        state = controller.command_init(
            self.args(
                feature="sample-feature",
                prd=self.prd.relative_to(self.root).as_posix(),
                spec=self.spec.relative_to(self.root).as_posix(),
                architect_id="architect-1",
            )
        )
        if with_spec:
            state = controller.command_accept_spec(self.args())
        return state

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

    def test_init_rejects_invalid_approved_prd_before_state_direct_and_cli(self) -> None:
        acceptance = "- PRD-AC-001: Feature works in Unity simulation."
        invalid_rows = (
            "- PRD-AC-001..003: ambiguous short range",
            "- PRD-AC-001 and PRD-AC-002: ambiguous multiple IDs",
            "",
        )
        for invalid in invalid_rows:
            with self.subTest(invalid=invalid):
                self.prd.write_text(PRD.replace(acceptance, invalid), encoding="utf-8")
                self.write_spec()
                args = self.args(
                    feature="sample-feature",
                    prd=self.prd.relative_to(self.root).as_posix(),
                    spec=self.spec.relative_to(self.root).as_posix(),
                    architect_id="architect-1",
                )
                with self.assertRaisesRegex(
                    controller.SpecificationStateError,
                    "full approved requirements contract",
                ):
                    controller.command_init(args)
                self.assertFalse((self.root / controller.STATE_RELATIVE_PATH).exists())

                cli = self.cli(
                    "init",
                    "--feature", "sample-feature",
                    "--prd", self.prd.relative_to(self.root).as_posix(),
                    "--spec", self.spec.relative_to(self.root).as_posix(),
                    "--architect-id", "architect-1",
                )
                self.assertEqual(2, cli.returncode)
                self.assertIn("full approved requirements contract", cli.stderr)
                self.assertFalse((self.root / controller.STATE_RELATIVE_PATH).exists())
                self.temp.cleanup()
                self.setUp()

    def test_accept_spec_rejects_invalid_legacy_prd_before_migration_direct_and_cli(self) -> None:
        self.initialize(with_spec=False)
        self.prd.write_text(
            PRD.replace(
                "## Acceptance Criteria\n\n"
                "- PRD-AC-001: Feature works in Unity simulation.\n\n",
                "",
            ),
            encoding="utf-8",
        )
        self.write_spec()
        state_path = self.root / controller.STATE_RELATIVE_PATH
        legacy = json.loads(state_path.read_text(encoding="utf-8"))
        legacy["schema_version"] = 1
        legacy.pop("identity_history", None)
        legacy["prd"]["sha256"] = controller.sha256(self.prd)
        state_path.write_text(json.dumps(legacy, sort_keys=True), encoding="utf-8")
        before = state_path.read_bytes()

        with self.assertRaisesRegex(
            controller.SpecificationStateError,
            "legacy state approved PRD.*full approved requirements contract",
        ):
            controller.command_accept_spec(self.args())
        self.assertEqual(before, state_path.read_bytes())

        cli = self.cli("accept-spec")
        self.assertEqual(2, cli.returncode)
        self.assertIn("full approved requirements contract", cli.stderr)
        self.assertEqual(before, state_path.read_bytes())

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
            self.args(
                feature="sample-feature",
                prd=self.prd.relative_to(self.root).as_posix(),
                spec=self.spec.relative_to(self.root).as_posix(),
                architect_id="replacement",
            )
        )
        self.assertEqual(state["active_architect_id"], "architect-1")
        self.assertEqual(state["total_cycles_completed"], 1)
        self.assertEqual(len(state["waves"]), 1)

    def test_flat_source_prd_trace_remains_compatible(self) -> None:
        self.write_spec(nested_trace=False)
        state = controller.command_init(
            self.args(
                feature="sample-feature",
                prd=self.prd.relative_to(self.root).as_posix(),
                spec=self.spec.relative_to(self.root).as_posix(),
                architect_id="architect-1",
            )
        )
        self.assertEqual(state["status"], "reviewing")

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

    def test_identity_aliases_are_normalized_for_ownership_and_freshness(self) -> None:
        self.initialize()
        controller.command_start_cycle(
            self.args(
                architect_id="  ＡＲＣＨＩＴＥＣＴ－１  ",
                proofreader_id="proofreader-1",
            )
        )
        controller.command_record_proofread(
            self.args(
                proofreader_id="  ＰＲＯＯＦＲＥＡＤＥＲ－１  ",
                critical=0,
                major=0,
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
        controller.command_complete_cycle(
            self.args(
                architect_id=" ARCHITECT-1 ",
                resolution_note="normalized ownership",
                user_decision_note=None,
            )
        )
        with self.assertRaisesRegex(controller.SpecificationStateError, "fresh identity"):
            controller.command_start_cycle(
                self.args(
                    architect_id="architect-1",
                    proofreader_id=" ＰＲＯＯＦＲＥＡＤＥＲ－１ ",
                )
            )
        cli = self.cli(
            "start-cycle",
            "--architect-id",
            "architect-1",
            "--proofreader-id",
            " ＰＲＯＯＦＲＥＡＤＥＲ－１ ",
        )
        self.assertEqual(2, cli.returncode)
        self.assertIn("fresh identity", cli.stderr)

    def test_handoff_rejects_aliases_of_every_prior_role(self) -> None:
        self.test_attempted_sixth_cycle_enters_hold()
        for identity in (" ＡＲＣＨＩＴＥＣＴ－１ ", " ＰＲＯＯＦＲＥＡＤＥＲ－１ "):
            with self.subTest(identity=identity):
                with self.assertRaisesRegex(controller.SpecificationStateError, "fresh"):
                    controller.command_handoff(
                        self.args(
                            new_architect_id=identity,
                            decision_note="must not reuse a prior role",
                        )
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

    def test_revise_ready_bound_happy_path_requires_fresh_full_convergence(self) -> None:
        ready = self.make_ready()
        token = self.bind_authority_recovery(ready)
        self.write_full_approved_prd(4, "2099-08-11T00:00:00Z")
        reopened = controller.command_revise_ready(
            self.args(
                reason="fresh PRD authority",
                architect_id="architect-2",
                recovery_token=token,
            )
        )
        self.assertEqual("awaiting_accept", reopened["status"])
        self.assertIsNone(reopened["ready"])
        self.assertEqual("4", reopened["prd"]["revision"])
        self.assertEqual("architect-2", reopened["active_architect_id"])
        self.assertIn("status: draft", self.spec.read_text(encoding="utf-8"))
        self.assertIn("revision: 2", self.spec.read_text(encoding="utf-8"))
        self.assertEqual(
            "ready_specification_revision_opened", reopened["history"][-1]["event"]
        )
        with self.assertRaisesRegex(controller.SpecificationStateError, "fresh Proofreader"):
            controller.command_confirm_ready(
                self.args(architect_id="architect-2", confirmation="cannot skip proofreading")
            )
        with self.assertRaisesRegex(controller.SpecificationStateError, "awaiting_accept"):
            controller.command_start_cycle(
                self.args(architect_id="architect-2", proofreader_id="proofreader-2")
            )
        draft_text = self.spec.read_text(encoding="utf-8")
        self.spec.write_text(
            draft_text.replace("status: draft", "status: approved", 1),
            encoding="utf-8",
        )
        controller.command_accept_spec(self.args())
        controller.command_start_cycle(
            self.args(architect_id="architect-2", proofreader_id="proofreader-2")
        )
        controller.command_record_proofread(
            self.args(
                proofreader_id="proofreader-2",
                critical=0,
                major=0,
                minor=0,
                product_questions=0,
                scope_questions=0,
                boundary_questions=0,
                ownership_questions=0,
                public_contract_questions=0,
                minors_engineer_resolvable=False,
                coverage_complete=True,
                report_path="fresh-proofread.md",
                finding_id=[],
                question_id=[],
            )
        )
        fresh = controller.command_confirm_ready(
            self.args(architect_id="architect-2", confirmation="fresh exact SHA confirmed")
        )
        self.assertEqual("spec_ready", fresh["status"])
        self.assertEqual(controller.sha256(self.prd), fresh["ready"]["prd_sha256"])

    def test_revise_ready_rejects_no_prd_change_and_stale_spec_bytes(self) -> None:
        ready = self.make_ready()
        with self.assertRaisesRegex(controller.SpecificationStateError, "newly approved higher"):
            controller.command_revise_ready(
                self.args(
                    reason="no authority change",
                    architect_id="architect-2",
                    recovery_token=None,
                )
            )
        self.write_full_approved_prd(4, "2099-08-11T00:00:00Z")
        self.spec.write_text(self.spec.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(controller.SpecificationStateError, "SPEC_READY SHA"):
            controller.command_revise_ready(
                self.args(
                    reason="stale spec",
                    architect_id="architect-2",
                    recovery_token=None,
                )
            )

    def test_specification_only_reopen_preserves_exact_prd_direct(self) -> None:
        ready = self.make_ready()
        prior_prd = dict(ready["prd"])
        reopened = controller.command_revise_ready(
            self.args(
                reason="clarify specification without product change",
                architect_id="architect-2",
                recovery_token=None,
                specification_only=True,
            )
        )
        self.assertEqual("awaiting_accept", reopened["status"])
        self.assertEqual(prior_prd, reopened["prd"])
        self.assertEqual(
            "specification_only", reopened["history"][-1]["revision_kind"]
        )
        self.assertEqual(
            "revoked_by_specification_revision",
            reopened["history"][-1]["spec_ready_disposition"],
        )
        self.assertIn("revision: 2", self.spec.read_text(encoding="utf-8"))
        self.assertIn("status: draft", self.spec.read_text(encoding="utf-8"))

    def test_specification_only_reopen_cli(self) -> None:
        self.make_ready()
        result = self.cli(
            "revise-ready",
            "--reason",
            "CLI specification correction",
            "--architect-id",
            "architect-2",
            "--specification-only",
        )
        self.assertEqual(0, result.returncode, result.stderr)
        cli_state = json.loads(result.stdout)
        self.assertEqual("specification_only", cli_state["history"][-1]["revision_kind"])

    def test_specification_only_reopen_rejects_invalid_prd_before_mutation_direct_cli(self) -> None:
        ready = self.make_ready()
        old_prd_sha = ready["prd"]["sha256"]
        self.prd.write_text(
            PRD.replace(
                "- PRD-AC-001: Feature works in Unity simulation.",
                "- PRD-AC-001 and PRD-AC-002: ambiguous authority",
            ),
            encoding="utf-8",
        )
        new_prd_sha = controller.sha256(self.prd)
        self.spec.write_text(
            self.spec.read_text(encoding="utf-8").replace(old_prd_sha, new_prd_sha),
            encoding="utf-8",
        )
        new_spec_sha = controller.sha256(self.spec)
        state_path = self.root / controller.STATE_RELATIVE_PATH
        state = controller.load_state(self.root)
        state["prd"]["sha256"] = new_prd_sha
        state["specification"]["sha256"] = new_spec_sha
        state["ready"]["prd_sha256"] = new_prd_sha
        state["ready"]["spec_sha256"] = new_spec_sha
        state["acceptance"]["prd_sha256"] = new_prd_sha
        state["acceptance"]["specification_sha256"] = new_spec_sha
        controller.save_state(self.root, state)
        state_before = state_path.read_bytes()
        spec_before = self.spec.read_bytes()
        args = self.args(
            reason="must not reopen invalid product authority",
            architect_id="architect-2",
            recovery_token=None,
            specification_only=True,
        )

        with self.assertRaisesRegex(
            controller.SpecificationStateError,
            "unchanged specification-only PRD.*full approved requirements contract",
        ):
            controller.command_revise_ready(args)
        self.assertEqual(state_before, state_path.read_bytes())
        self.assertEqual(spec_before, self.spec.read_bytes())

        cli = self.cli(
            "revise-ready",
            "--reason", "must not reopen invalid product authority",
            "--architect-id", "architect-2",
            "--specification-only",
        )
        self.assertEqual(2, cli.returncode)
        self.assertIn("full approved requirements contract", cli.stderr)
        self.assertEqual(state_before, state_path.read_bytes())
        self.assertEqual(spec_before, self.spec.read_bytes())

    def test_schema1_migrates_identity_history_and_preserves_alias_rejection(self) -> None:
        self.initialize()
        state_path = self.root / controller.STATE_RELATIVE_PATH
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["schema_version"] = 1
        state.pop("identity_history", None)
        state_path.write_text(json.dumps(state), encoding="utf-8")

        cli = self.cli("status")
        self.assertEqual(0, cli.returncode, cli.stderr)
        self.assertEqual(controller.SCHEMA_VERSION, json.loads(cli.stdout)["schema_version"])
        migrated = controller.load_state(self.root)
        self.assertEqual(controller.SCHEMA_VERSION, migrated["schema_version"])
        self.assertIn("architect-1", migrated["identity_history"])
        persisted = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(controller.SCHEMA_VERSION, persisted["schema_version"])

        controller.command_start_cycle(
            self.args(architect_id="architect-1", proofreader_id="proofreader-1")
        )
        controller.command_record_proofread(
            self.args(
                proofreader_id="proofreader-1",
                critical=0,
                major=0,
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
        controller.command_complete_cycle(
            self.args(
                architect_id="architect-1",
                resolution_note="migration proof",
                user_decision_note=None,
            )
        )
        with self.assertRaisesRegex(controller.SpecificationStateError, "fresh identity"):
            controller.command_start_cycle(
                self.args(
                    architect_id="architect-1",
                    proofreader_id=" ＰＲＯＯＦＲＥＡＤＥＲ－１ ",
                )
            )

    def test_revise_ready_rejects_unapproved_or_invalid_prd_and_reused_worker(self) -> None:
        self.make_ready()
        self.write_full_approved_prd(4, "2099-08-11T00:00:00Z")
        self.prd.write_text(
            self.prd.read_text(encoding="utf-8").replace("status: approved", "status: draft"),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(controller.SpecificationStateError, "approved"):
            controller.command_revise_ready(
                self.args(reason="bad PRD", architect_id="architect-2", recovery_token=None)
            )
        self.write_full_approved_prd(4, "2099-08-11T00:00:00Z")
        with self.assertRaisesRegex(controller.SpecificationStateError, "fresh"):
            controller.command_revise_ready(
                self.args(reason="reuse", architect_id="PROOFREADER-1", recovery_token=None)
            )

    def test_revise_ready_bound_rejects_wrong_token_non_hold_and_late_evidence(self) -> None:
        ready = self.make_ready()
        token = self.bind_authority_recovery(ready)
        self.write_full_approved_prd(4, "2099-08-11T00:00:00Z")
        with self.assertRaisesRegex(controller.SpecificationStateError, "exact"):
            controller.command_revise_ready(
                self.args(
                    reason="fresh PRD authority",
                    architect_id="architect-2",
                    recovery_token="ARH-WRONG",
                )
            )
        runtime_path = self.root / controller.RUNTIME_STATE_RELATIVE_PATH
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        runtime["phase"] = "slice_engineering"
        runtime_path.write_text(json.dumps(runtime), encoding="utf-8")
        with self.assertRaisesRegex(controller.SpecificationStateError, "exact"):
            controller.command_revise_ready(
                self.args(
                    reason="fresh PRD authority",
                    architect_id="architect-2",
                    recovery_token=token,
                )
            )
        runtime["phase"] = "authority_recovery_hold"
        runtime["engineer_runs"] = [{"run_id": "engineer-1"}]
        runtime_path.write_text(json.dumps(runtime), encoding="utf-8")
        with self.assertRaisesRegex(controller.SpecificationStateError, "Engineer/product"):
            controller.command_revise_ready(
                self.args(
                    reason="fresh PRD authority",
                    architect_id="architect-2",
                    recovery_token=token,
                )
            )

    def test_revise_ready_cli_help_and_alias(self) -> None:
        help_result = self.cli("revise-ready", "--help")
        self.assertEqual(0, help_result.returncode)
        self.assertIn("--recovery-token", help_result.stdout)
        self.assertIn("--specification-only", help_result.stdout)
        alias_result = self.cli("reopen-ready", "--help")
        self.assertEqual(0, alias_result.returncode)

    def test_revise_ready_cli_requires_fresh_accept_receipt_before_cycle(self) -> None:
        ready = self.make_ready()
        token = self.bind_authority_recovery(ready)
        self.write_full_approved_prd(4, "2099-08-11T00:00:00Z")
        reopened = self.cli(
            "revise-ready",
            "--reason",
            "fresh PRD authority",
            "--architect-id",
            "architect-2",
            "--recovery-token",
            token,
        )
        self.assertEqual(0, reopened.returncode, reopened.stderr)
        draft = self.spec.read_text(encoding="utf-8")
        self.spec.write_text(
            draft.replace("status: draft", "status: approved", 1), encoding="utf-8"
        )
        blocked = self.cli(
            "start-cycle",
            "--architect-id",
            "architect-2",
            "--proofreader-id",
            "proofreader-2",
        )
        self.assertEqual(2, blocked.returncode)
        self.assertIn("awaiting_accept", blocked.stderr)
        accepted = self.cli("accept-spec")
        self.assertEqual(0, accepted.returncode, accepted.stderr)
        started = self.cli(
            "start-cycle",
            "--architect-id",
            "architect-2",
            "--proofreader-id",
            "proofreader-2",
        )
        self.assertEqual(0, started.returncode, started.stderr)

    def test_start_cycle_rejects_stale_acceptance_receipt(self) -> None:
        self.initialize()
        state = controller.load_state(self.root)
        state["acceptance"]["specification_sha256"] = "0" * 64
        controller.save_state(self.root, state)
        with self.assertRaisesRegex(controller.SpecificationStateError, "fresh accept-spec"):
            controller.command_start_cycle(
                self.args(architect_id="architect-1", proofreader_id="proofreader-stale")
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
