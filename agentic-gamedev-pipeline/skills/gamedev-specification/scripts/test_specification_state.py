#!/usr/bin/env python3
"""Tests for the bounded specification convergence controller."""

from __future__ import annotations

import sys
import json
import hashlib
import importlib.util
import subprocess
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import specification_state as controller


_PLAN_CONTROLLER_PATH = (
    Path(__file__).resolve().parents[2]
    / "gamedev-development-plan"
    / "scripts"
    / "development_plan_state.py"
)
_PLAN_CONTROLLER_SPEC = importlib.util.spec_from_file_location(
    "gamedev_development_plan_for_specification_tests", _PLAN_CONTROLLER_PATH
)
if _PLAN_CONTROLLER_SPEC is None or _PLAN_CONTROLLER_SPEC.loader is None:
    raise RuntimeError("cannot load the Development Plan controller for tests")
plan_controller = importlib.util.module_from_spec(_PLAN_CONTROLLER_SPEC)
_PLAN_CONTROLLER_SPEC.loader.exec_module(plan_controller)


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

    def prepare_in_progress_revision(self) -> dict:
        self.initialize()
        self.start_and_record(1)
        prior = controller.load_state(self.root)
        self.write_full_approved_prd(4, "2099-08-11T00:00:00Z")
        return prior

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

    def write_v2_plan(self, ready: dict) -> Path:
        plan = self.feature_dir / "development-plan.md"
        plan.write_text(
            f"""---
document_type: development-plan
status: approved
revision: 1
feature: sample-feature
mode: single_owner
writer_strategy: sequential
planning_analyst_id: planning-analyst
product_authority:
  path: {ready['prd']['path']}
  revision: {ready['prd']['revision']}
  sha256: {ready['prd']['sha256']}
specification_authority:
  path: {ready['specification']['path']}
  revision: 1
  sha256: {ready['ready']['spec_sha256']}
decision_ledger_path: docs/decision-ledger.jsonl
slice_count: 1
approved_by: user
approved_at: 2026-08-10T00:00:00Z
---
# Approved Development Plan

## Slice SLICE-001

### Context Capsule Budget

- max_authority_files: 2
- max_evidence_files: 2
- max_total_files: 4
- max_payload_bytes: 40000
- max_estimated_tokens: 10000
- metric_scope: capsule_plus_referenced_files
- authority_paths: docs/context.md
- evidence_paths: tests/evidence.md
""",
            encoding="utf-8",
        )
        return plan

    def bind_direct_v2(self, ready: dict, filename: str = "state.json") -> Path:
        plan = self.write_v2_plan(ready)
        items = {
            "requirements": {
                "path": ready["prd"]["path"],
                "sha256": ready["prd"]["sha256"],
            },
            "specification": {
                "path": ready["specification"]["path"],
                "sha256": ready["ready"]["spec_sha256"],
            },
            "plan": {
                "path": plan.relative_to(self.root).as_posix(),
                "sha256": controller.sha256(plan),
            },
        }
        runtime = plan_controller._pipeline_v2_model.new_state(
            run_id="direct-v2-specification-test",
            project_root=str(self.root.resolve()),
            authority={"items": items},
            slices=[{
                "id": "SLICE-001",
                "allowed_paths": ["src/example.txt"],
                "planned_commands": [[sys.executable, "-B", "-c", "pass"]],
                "read_paths": ["docs/context.md", "tests/evidence.md"],
            }],
        )
        runtime_path = self.root / ".agentic-pipeline-v2" / filename
        runtime_path.parent.mkdir(parents=True, exist_ok=True)
        runtime_path.write_text(json.dumps(runtime), encoding="utf-8")
        self.assertFalse((self.root / controller.RUNTIME_STATE_RELATIVE_PATH).exists())
        self.assertFalse((self.root / controller.RUNTIME_FINDINGS_RELATIVE_PATH).exists())
        status = controller._pipeline_v2_runner.Controller(
            controller._pipeline_v2_transaction.StateStore(runtime_path)
        ).status()
        self.assertIsNone(status["active_assignment"])
        self.assertEqual([], status["open_gates"])
        self.assertEqual([], status["open_questions"])
        self.assertEqual("command", status["next_action"]["kind"])
        self.assertTrue(status["next_action"]["command_id"].startswith("next-plan-"))
        return runtime_path

    def bind_retired_schema10_v2(self, ready: dict) -> Path:
        plan = self.write_v2_plan(ready)
        legacy_generation = 14
        legacy = {
            "schema_version": 10,
            "project_root": str(self.root),
            "feature": "sample-feature",
            "generation": legacy_generation,
            "requirements_path": ready["prd"]["path"],
            "requirements_sha256": ready["prd"]["sha256"],
            "spec_path": ready["specification"]["path"],
            "spec_sha256": ready["ready"]["spec_sha256"],
            "development_plan_path": plan.relative_to(self.root).as_posix(),
            "development_plan_sha256": "a" * 64,
        }
        state_dir = self.root / ".agentic-pipeline"
        (state_dir / "state.json").write_text(json.dumps(legacy), encoding="utf-8")
        (state_dir / "findings.json").write_text(
            json.dumps({
                "schema_version": 10,
                "items": [],
                "generation": legacy_generation,
            }),
            encoding="utf-8",
        )
        slices = [{
            "id": "SLICE-001",
            "allowed_paths": ["src/example.txt"],
            "planned_commands": [[sys.executable, "-B", "-c", "pass"]],
        }]
        imported = plan_controller._pipeline_v2_legacy.import_schema10(legacy, slices)
        migrate = {
            "id": "MIGRATE-SCHEMA10",
            "command": "migrate",
            "command_digest": self.canonical_digest({
                "name": "migrate",
                "id": "MIGRATE-SCHEMA10",
                "imported": imported,
            }),
            "generation": legacy_generation,
            "result": "migrated",
        }
        items = {
            "requirements": {
                "path": ready["prd"]["path"],
                "sha256": ready["prd"]["sha256"],
            },
            "specification": {
                "path": ready["specification"]["path"],
                "sha256": ready["ready"]["spec_sha256"],
            },
            "plan": {
                "path": plan.relative_to(self.root).as_posix(),
                "sha256": controller.sha256(plan),
            },
        }
        runtime = json.loads(json.dumps(imported))
        runtime.update({
            "generation": legacy_generation + 1,
            "authority": {
                "items": items,
                "digest": self.canonical_digest(items),
            },
            "phase": "plan",
            "active_assignment": None,
            "slices": [{
                **slices[0],
                "read_paths": ["docs/context.md", "tests/evidence.md"],
            }],
            "artifacts": {},
            "questions": {},
            "gates": {},
        })
        runtime["history"].extend([
            migrate,
            {
                "id": "reconfigure-current-authority",
                "command": "init",
                "command_digest": self.canonical_digest(
                    ["public-reconfigure", legacy_generation + 1]
                ),
                "generation": legacy_generation + 1,
                "result": "authority_scope_reconfigured",
                "prior": {
                    "phase": imported["phase"],
                    "authority_digest": imported["authority"]["digest"],
                    "slices_digest": self.canonical_digest(imported["slices"]),
                    "candidate": None,
                    "artifact_phases": [],
                    "question_ids": [],
                    "gate_ids": [],
                },
            },
        ])
        plan_controller._pipeline_v2_model.validate_state(runtime)
        runtime_path = self.root / ".agentic-pipeline-v2" / "state.json"
        runtime_path.parent.mkdir(parents=True, exist_ok=True)
        runtime_path.write_text(json.dumps(runtime), encoding="utf-8")
        return runtime_path

    def complete_fresh_v2_reopen(self, report_path: str) -> dict:
        self.spec.write_text(
            self.spec.read_text(encoding="utf-8").replace(
                "status: draft", "status: approved", 1
            ),
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
                report_path=report_path,
                finding_id=[],
                question_id=[],
            )
        )
        return controller.command_confirm_ready(
            self.args(architect_id="architect-2", confirmation="exact SHA confirmed")
        )

    def released_v2_schema1_authorization(self, authorization: dict) -> dict:
        self.assertEqual(2, authorization["schema"])
        self.assertIsNone(authorization["token"])
        return {
            "schema": 1,
            "token": None,
            "reason": authorization["reason"],
            "runtime_state_path": authorization["runtime_state_path"],
            "runtime_state_sha256": authorization["runtime_state_sha256"],
            "prior_spec_sha256": authorization["prior_specification"]["sha256"],
        }

    def persist_released_v2_schema1_authorization(self) -> dict:
        state_path = self.root / controller.STATE_RELATIVE_PATH
        state = controller.load_state(self.root)
        if state["status"] == "ready_revision_pending":
            receipt = state["ready_revision"]
            legacy = self.released_v2_schema1_authorization(
                receipt["recovery_authorization"]
            )
            receipt["recovery_authorization"] = legacy
        else:
            receipt = state["history"][-1]
            self.assertEqual("ready_specification_revision_opened", receipt["event"])
            legacy = self.released_v2_schema1_authorization(
                receipt["recovery_authorization"]
            )
            receipt["recovery_authorization"] = legacy
            state["recovery_authorization"] = dict(legacy)
        controller.write_state_file(state_path, state)
        return legacy

    def assert_committed_ready_replay_byte_noop(
        self, arguments: Namespace, *bound_paths: Path
    ) -> None:
        state_path = self.root / controller.STATE_RELATIVE_PATH
        tracked = (state_path, self.prd, self.spec, *bound_paths)
        before = {path: path.read_bytes() for path in tracked}
        expected = json.loads(before[state_path])

        first_replay = controller.command_revise_ready(arguments)
        self.assertEqual(expected, first_replay)
        self.assertEqual(before, {path: path.read_bytes() for path in tracked})

        second_replay = controller.command_revise_ready(arguments)
        self.assertEqual(expected, second_replay)
        self.assertEqual(before, {path: path.read_bytes() for path in tracked})

    def assert_committed_ready_replay_rejected_without_mutation(
        self, arguments: Namespace, pattern: str, *tracked_paths: Path
    ) -> None:
        state_path = self.root / controller.STATE_RELATIVE_PATH
        tracked = (state_path, self.prd, self.spec, *tracked_paths)
        before = {path: path.read_bytes() for path in tracked}
        with self.assertRaisesRegex(controller.SpecificationStateError, pattern):
            controller.command_revise_ready(arguments)
        self.assertEqual(before, {path: path.read_bytes() for path in tracked})

    def assert_v2_reopen_rejected(self, pattern: str) -> None:
        state_path = self.root / controller.STATE_RELATIVE_PATH
        state_before = state_path.read_bytes()
        spec_before = self.spec.read_bytes()
        with self.assertRaisesRegex(controller.SpecificationStateError, pattern):
            controller.command_revise_ready(
                self.args(
                    reason="bounded v2 specification correction",
                    architect_id="architect-2",
                    recovery_token=None,
                    specification_only=True,
                )
            )
        self.assertEqual(state_before, state_path.read_bytes())
        self.assertEqual(spec_before, self.spec.read_bytes())

    def assert_direct_v2_generation_poison_rejected(self, location: str) -> None:
        ready = self.make_ready()
        runtime = self.bind_direct_v2(ready)
        value = json.loads(runtime.read_text(encoding="utf-8"))
        candidate = {
            "checkout_sha256": self.canonical_digest("direct checkout"),
            "diff_sha256": self.canonical_digest("direct diff"),
            "authority_digest": value["authority"]["digest"],
            "generation": True,
        }
        if location == "top-level":
            value["generation"] = True
        elif location == "history":
            value["history"].append({
                "id": "BOOLEAN-GENERATION-HISTORY",
                "command": "status",
                "command_digest": self.canonical_digest("history command"),
                "generation": True,
                "result": "malformed",
            })
        elif location == "artifact candidate":
            value["artifacts"]["engineering"] = {
                "assignment_id": "boolean-generation-artifact",
                "worker": {"outcome": "blocked", "summary": "audit only"},
                "candidate": candidate,
            }
        elif location == "gate candidate_base":
            value["gates"]["boolean-generation-gate"] = {
                "status": "closed",
                "phase": "review",
                "kind": "worker_result",
                "reason": "fail",
                "candidate_base": candidate,
            }
        else:  # pragma: no cover - test helper contract
            raise AssertionError(location)
        runtime.write_text(json.dumps(value), encoding="utf-8")
        state_path = self.root / controller.STATE_RELATIVE_PATH
        state_before = state_path.read_bytes()
        spec_before = self.spec.read_bytes()
        runtime_before = runtime.read_bytes()

        with self.assertRaisesRegex(controller.SpecificationStateError, "generation|candidate"):
            controller.command_revise_ready(
                self.args(
                    reason="reject malformed direct v2 generation",
                    architect_id="architect-2",
                    recovery_token=None,
                    specification_only=True,
                )
            )

        self.assertEqual(state_before, state_path.read_bytes())
        self.assertEqual(spec_before, self.spec.read_bytes())
        self.assertEqual(runtime_before, runtime.read_bytes())

    @staticmethod
    def canonical_digest(value: object) -> str:
        return hashlib.sha256(
            json.dumps(
                value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()

    def initialize(self, with_spec: bool = True, nested_trace: bool = True) -> dict:
        if with_spec:
            self.write_spec(nested_trace=nested_trace)
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

    def test_revise_in_progress_archives_old_wave_and_requires_fresh_convergence(self) -> None:
        self.initialize(nested_trace=False)
        self.start_and_record(
            1,
            major=1,
            public_contract_questions=1,
            coverage_complete=False,
            finding_id=["F-001"],
            question_id=["F-001"],
        )
        prior = controller.load_state(self.root)
        self.write_full_approved_prd(4, "2099-08-11T00:00:00Z")
        new_prd_sha = controller.sha256(self.prd)

        reopened = controller.command_revise_in_progress(
            self.args(reason="new approved PRD", architect_id="architect-2")
        )

        self.assertEqual("awaiting_accept", reopened["status"])
        self.assertEqual("4", reopened["prd"]["revision"])
        self.assertEqual(new_prd_sha, reopened["prd"]["sha256"])
        self.assertEqual("architect-2", reopened["active_architect_id"])
        self.assertIsNone(reopened["acceptance"])
        self.assertIsNone(reopened["ready"])
        self.assertIsNone(reopened["active_wave"])
        self.assertEqual([], reopened["waves"])
        self.assertEqual(0, reopened["total_cycles_completed"])
        event = reopened["history"][-1]
        self.assertEqual("in_progress_prd_revision_opened", event["event"])
        self.assertEqual("superseded_by_prd_revision", event["in_progress_disposition"])
        self.assertEqual(prior["acceptance"], event["prior_acceptance"])
        self.assertEqual(["F-001"], event["prior_active_wave"]["proofread"]["finding_ids"])
        self.assertEqual(["F-001"], event["prior_active_wave"]["proofread"]["question_ids"])
        self.assertEqual(
            "proofreader-1.md", event["prior_active_wave"]["proofread"]["report_path"]
        )
        self.assertFalse(event["prior_active_wave"]["proofread"]["coverage_complete"])
        self.assertIn("architect-1", reopened["identity_history"])
        self.assertIn("proofreader-1", reopened["identity_history"])
        spec_text = self.spec.read_text(encoding="utf-8")
        self.assertIn("status: draft", spec_text)
        self.assertIn("revision: 2", spec_text)
        self.assertIn("source_prd_revision: 4", spec_text)
        self.assertIn(f"source_prd_sha256: {new_prd_sha}", spec_text)

        with self.assertRaisesRegex(controller.SpecificationStateError, "awaiting_accept"):
            controller.command_start_cycle(
                self.args(architect_id="architect-2", proofreader_id="proofreader-2")
            )

        self.spec.write_text(
            spec_text.replace("status: draft", "status: approved", 1),
            encoding="utf-8",
        )
        controller.command_accept_spec(self.args())
        with self.assertRaisesRegex(controller.SpecificationStateError, "fresh"):
            controller.command_start_cycle(
                self.args(architect_id="architect-2", proofreader_id="proofreader-1")
            )
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
        ready = controller.command_confirm_ready(
            self.args(architect_id="architect-2", confirmation="fresh SHA confirmed")
        )
        self.assertEqual("spec_ready", ready["status"])
        self.assertEqual(new_prd_sha, ready["ready"]["prd_sha256"])
        self.assertEqual([], ready["waves"][-1]["proofread"]["finding_ids"])

    def test_revise_in_progress_cli(self) -> None:
        self.prepare_in_progress_revision()
        result = self.cli(
            "revise-in-progress",
            "--reason",
            "new approved PRD",
            "--architect-id",
            "architect-2",
        )
        self.assertEqual(0, result.returncode, result.stderr)
        state = json.loads(result.stdout)
        self.assertEqual("awaiting_accept", state["status"])
        self.assertEqual("architect-2", state["active_architect_id"])

    def test_revise_in_progress_requires_recorded_active_wave(self) -> None:
        self.initialize()
        controller.command_start_cycle(
            self.args(architect_id="architect-1", proofreader_id="proofreader-1")
        )
        self.write_full_approved_prd(4, "2099-08-11T00:00:00Z")
        state_path = self.root / controller.STATE_RELATIVE_PATH
        state_before = state_path.read_bytes()
        spec_before = self.spec.read_bytes()

        with self.assertRaisesRegex(controller.SpecificationStateError, "recorded Proofreader"):
            controller.command_revise_in_progress(
                self.args(reason="new approved PRD", architect_id="architect-2")
            )

        self.assertEqual(state_before, state_path.read_bytes())
        self.assertEqual(spec_before, self.spec.read_bytes())

    def test_revise_in_progress_rejects_reused_identity(self) -> None:
        self.prepare_in_progress_revision()
        state_path = self.root / controller.STATE_RELATIVE_PATH
        state_before = state_path.read_bytes()
        spec_before = self.spec.read_bytes()
        with self.assertRaisesRegex(controller.SpecificationStateError, "fresh"):
            controller.command_revise_in_progress(
                self.args(reason="new approved PRD", architect_id=" PROOFREADER-1 ")
            )
        self.assertEqual(state_before, state_path.read_bytes())
        self.assertEqual(spec_before, self.spec.read_bytes())

    def test_revise_in_progress_rejects_ready_state(self) -> None:
        self.make_ready()
        self.write_full_approved_prd(4, "2099-08-11T00:00:00Z")
        state_path = self.root / controller.STATE_RELATIVE_PATH
        state_before = state_path.read_bytes()
        spec_before = self.spec.read_bytes()
        with self.assertRaisesRegex(controller.SpecificationStateError, "use revise-ready"):
            controller.command_revise_in_progress(
                self.args(reason="new approved PRD", architect_id="architect-2")
            )
        self.assertEqual(state_before, state_path.read_bytes())
        self.assertEqual(spec_before, self.spec.read_bytes())

    def test_revise_in_progress_rejects_stale_prd_authority_without_mutation(self) -> None:
        self.initialize()
        self.start_and_record(1)
        state_path = self.root / controller.STATE_RELATIVE_PATH
        state_before = state_path.read_bytes()
        spec_before = self.spec.read_bytes()

        with self.assertRaisesRegex(controller.SpecificationStateError, "higher PRD revision"):
            controller.command_revise_in_progress(
                self.args(reason="unchanged PRD", architect_id="architect-2")
            )
        self.assertEqual(state_before, state_path.read_bytes())
        self.assertEqual(spec_before, self.spec.read_bytes())

        self.write_full_approved_prd(2, "2099-08-11T00:00:00Z")
        with self.assertRaisesRegex(controller.SpecificationStateError, "higher PRD revision"):
            controller.command_revise_in_progress(
                self.args(reason="lower PRD", architect_id="architect-2")
            )
        self.assertEqual(state_before, state_path.read_bytes())
        self.assertEqual(spec_before, self.spec.read_bytes())

        self.write_full_approved_prd(4, "2020-08-11T00:00:00Z")
        with self.assertRaisesRegex(controller.SpecificationStateError, "fresh after"):
            controller.command_revise_in_progress(
                self.args(reason="backdated PRD", architect_id="architect-2")
            )
        self.assertEqual(state_before, state_path.read_bytes())
        self.assertEqual(spec_before, self.spec.read_bytes())

    def test_revise_in_progress_rejects_invalid_authority_and_tampered_spec(self) -> None:
        self.prepare_in_progress_revision()
        state_path = self.root / controller.STATE_RELATIVE_PATH
        state_before = state_path.read_bytes()
        self.prd.write_text(
            self.prd.read_text(encoding="utf-8").replace(
                "status: approved", "status: draft", 1
            ),
            encoding="utf-8",
        )
        invalid_prd = self.prd.read_bytes()
        spec_before = self.spec.read_bytes()
        with self.assertRaisesRegex(controller.SpecificationStateError, "full approved"):
            controller.command_revise_in_progress(
                self.args(reason="new approved PRD", architect_id="architect-2")
            )
        self.assertEqual(state_before, state_path.read_bytes())
        self.assertEqual(invalid_prd, self.prd.read_bytes())
        self.assertEqual(spec_before, self.spec.read_bytes())

        self.write_full_approved_prd(4, "2099-08-11T00:00:00Z")
        self.spec.write_text(
            self.spec.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8"
        )
        tampered_spec = self.spec.read_bytes()
        with self.assertRaisesRegex(controller.SpecificationStateError, "controller-recorded SHA"):
            controller.command_revise_in_progress(
                self.args(reason="new approved PRD", architect_id="architect-2")
            )
        self.assertEqual(state_before, state_path.read_bytes())
        self.assertEqual(tampered_spec, self.spec.read_bytes())

    def test_revise_in_progress_rejects_runtime_binding_without_mutation(self) -> None:
        self.prepare_in_progress_revision()
        state_dir = self.root / ".agentic-pipeline"
        (state_dir / "state.json").write_text("{}\n", encoding="utf-8")
        state_path = self.root / controller.STATE_RELATIVE_PATH
        state_before = state_path.read_bytes()
        spec_before = self.spec.read_bytes()

        with self.assertRaisesRegex(controller.SpecificationStateError, "before runtime"):
            controller.command_revise_in_progress(
                self.args(reason="new approved PRD", architect_id="architect-2")
            )

        self.assertEqual(state_before, state_path.read_bytes())
        self.assertEqual(spec_before, self.spec.read_bytes())

    def test_revise_in_progress_resumes_before_specification_write(self) -> None:
        self.prepare_in_progress_revision()
        reason = "  new approved PRD  "
        args = self.args(reason=reason, architect_id="architect-2")
        with mock.patch.object(
            controller, "write_bytes_atomically", side_effect=OSError("interrupted write")
        ):
            with self.assertRaisesRegex(OSError, "interrupted write"):
                controller.command_revise_in_progress(args)

        pending = controller.load_state(self.root)
        self.assertEqual("in_progress_revision_pending", pending["status"])
        self.assertIn("revision: 1", self.spec.read_text(encoding="utf-8"))
        reopened = controller.command_revise_in_progress(args)
        self.assertEqual("awaiting_accept", reopened["status"])
        self.assertIn("revision: 2", self.spec.read_text(encoding="utf-8"))
        self.assertEqual(1, len(reopened["history"]))

    def test_revise_in_progress_resumes_after_specification_write(self) -> None:
        self.prepare_in_progress_revision()
        args = self.args(reason="new approved PRD", architect_id="architect-2")
        original_save = controller.save_state
        calls = 0

        def fail_final_save(root: Path, state: dict) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("interrupted final state write")
            original_save(root, state)

        with mock.patch.object(controller, "save_state", side_effect=fail_final_save):
            with self.assertRaisesRegex(OSError, "interrupted final state write"):
                controller.command_revise_in_progress(args)

        pending = controller.load_state(self.root)
        self.assertEqual("in_progress_revision_pending", pending["status"])
        self.assertIn("revision: 2", self.spec.read_text(encoding="utf-8"))
        reopened = controller.command_revise_in_progress(args)
        self.assertEqual("awaiting_accept", reopened["status"])
        self.assertIn("revision: 2", self.spec.read_text(encoding="utf-8"))
        self.assertEqual(1, len(reopened["history"]))

    def test_pending_in_progress_revision_rejects_changed_resume_inputs(self) -> None:
        self.prepare_in_progress_revision()
        args = self.args(reason="new approved PRD", architect_id="architect-2")
        with mock.patch.object(
            controller, "write_bytes_atomically", side_effect=OSError("interrupted write")
        ):
            with self.assertRaisesRegex(OSError, "interrupted write"):
                controller.command_revise_in_progress(args)

        state_path = self.root / controller.STATE_RELATIVE_PATH
        state_before = state_path.read_bytes()
        spec_before = self.spec.read_bytes()
        with self.assertRaisesRegex(controller.SpecificationStateError, "exact original inputs"):
            controller.command_revise_in_progress(
                self.args(reason="different reason", architect_id="architect-2")
            )
        self.assertEqual(state_before, state_path.read_bytes())
        self.assertEqual(spec_before, self.spec.read_bytes())

        self.prd.write_text(
            self.prd.read_text(encoding="utf-8") + "changed after pending\n",
            encoding="utf-8",
        )
        changed_prd = self.prd.read_bytes()
        with self.assertRaisesRegex(controller.SpecificationStateError, "changed PRD bytes"):
            controller.command_revise_in_progress(args)
        self.assertEqual(state_before, state_path.read_bytes())
        self.assertEqual(spec_before, self.spec.read_bytes())
        self.assertEqual(changed_prd, self.prd.read_bytes())

    def test_pending_in_progress_revision_cannot_escape_through_wave_commands(self) -> None:
        self.initialize()
        self.start_and_record(1)
        prior_prd = self.prd.read_bytes()
        self.write_full_approved_prd(4, "2099-08-11T00:00:00Z")
        args = self.args(reason="new approved PRD", architect_id="architect-2")
        with mock.patch.object(
            controller, "write_bytes_atomically", side_effect=OSError("interrupted write")
        ):
            with self.assertRaisesRegex(OSError, "interrupted write"):
                controller.command_revise_in_progress(args)

        self.prd.write_bytes(prior_prd)
        state_path = self.root / controller.STATE_RELATIVE_PATH
        state_before = state_path.read_bytes()
        spec_before = self.spec.read_bytes()
        commands = (
            lambda: controller.command_start_cycle(
                self.args(architect_id="architect-1", proofreader_id="proofreader-2")
            ),
            lambda: controller.command_record_proofread(self.args()),
            lambda: controller.command_complete_cycle(self.args()),
            lambda: controller.command_confirm_ready(self.args()),
        )
        for command in commands:
            with self.subTest(command=command):
                with self.assertRaisesRegex(
                    controller.SpecificationStateError, "in_progress_revision_pending"
                ):
                    command()
                self.assertEqual(state_before, state_path.read_bytes())
                self.assertEqual(spec_before, self.spec.read_bytes())

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
        with self.assertRaisesRegex(
            controller.SpecificationStateError, "cannot confirm readiness in awaiting_accept"
        ):
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

    def test_specification_only_reopen_accepts_canonical_direct_v2_default_path(self) -> None:
        ready = self.make_ready()
        runtime = self.bind_direct_v2(ready)
        runtime_before = runtime.read_bytes()

        reopened = controller.command_revise_ready(
            self.args(
                reason="clarify specification under a direct v2 runtime",
                architect_id="architect-2",
                recovery_token=None,
                specification_only=True,
            )
        )

        self.assertEqual("awaiting_accept", reopened["status"])
        authorization = reopened["recovery_authorization"]
        self.assertEqual(2, authorization["schema"])
        self.assertEqual(
            ".agentic-pipeline-v2/state.json",
            authorization["runtime_state_path"],
        )
        self.assertEqual(
            hashlib.sha256(runtime_before).hexdigest(),
            authorization["runtime_state_sha256"],
        )
        self.assertEqual("specification_only", authorization["revision_kind"])
        self.assertEqual(
            {"path": ready["prd"]["path"], "sha256": ready["prd"]["sha256"]},
            authorization["prior_requirements"],
        )
        self.assertEqual(
            {
                "path": ready["specification"]["path"],
                "sha256": ready["ready"]["spec_sha256"],
            },
            authorization["prior_specification"],
        )
        self.assertEqual(runtime_before, runtime.read_bytes())
        final = self.complete_fresh_v2_reopen("direct-v2-proofread.md")
        self.assertEqual("spec_ready", final["status"])
        self.assertEqual(runtime_before, runtime.read_bytes())

    def test_specification_only_reopen_replays_canonical_direct_v2_custom_path(self) -> None:
        ready = self.make_ready()
        runtime = self.bind_direct_v2(ready, "custom-run.json")
        runtime_before = runtime.read_bytes()
        arguments = self.args(
            reason="replay specification correction under a direct custom v2 runtime",
            architect_id="architect-2",
            recovery_token=None,
            specification_only=True,
        )

        with mock.patch.object(
            controller, "write_bytes_atomically", side_effect=OSError("lost response")
        ):
            with self.assertRaisesRegex(OSError, "lost response"):
                controller.command_revise_ready(arguments)
        self.assertEqual(
            "ready_revision_pending", controller.load_state(self.root)["status"]
        )
        self.assertEqual(runtime_before, runtime.read_bytes())

        reopened = controller.command_revise_ready(arguments)
        self.assertEqual("awaiting_accept", reopened["status"])
        self.assertEqual(
            ".agentic-pipeline-v2/custom-run.json",
            reopened["recovery_authorization"]["runtime_state_path"],
        )
        self.assertEqual(runtime_before, runtime.read_bytes())
        final = self.complete_fresh_v2_reopen("direct-custom-v2-proofread.md")
        self.assertEqual("spec_ready", final["status"])
        self.assertEqual(runtime_before, runtime.read_bytes())

    def test_direct_v2_reopen_rejects_boolean_top_level_generation_without_mutation(self) -> None:
        self.assert_direct_v2_generation_poison_rejected("top-level")

    def test_direct_v2_reopen_rejects_boolean_history_generation_without_mutation(self) -> None:
        self.assert_direct_v2_generation_poison_rejected("history")

    def test_direct_v2_reopen_rejects_boolean_artifact_candidate_generation_without_mutation(self) -> None:
        self.assert_direct_v2_generation_poison_rejected("artifact candidate")

    def test_direct_v2_reopen_rejects_boolean_gate_candidate_generation_without_mutation(self) -> None:
        self.assert_direct_v2_generation_poison_rejected("gate candidate_base")

    def test_specification_only_reopen_accepts_safe_proven_retired_v2_lineage(self) -> None:
        ready = self.make_ready()
        self.bind_retired_schema10_v2(ready)
        reopened = controller.command_revise_ready(
            self.args(
                reason="clarify specification under the bound v2 runtime",
                architect_id="architect-2",
                recovery_token=None,
                specification_only=True,
            )
        )
        self.assertEqual("awaiting_accept", reopened["status"])
        authorization = reopened["recovery_authorization"]
        self.assertEqual(2, authorization["schema"])
        self.assertEqual(
            ".agentic-pipeline-v2/state.json",
            authorization["runtime_state_path"],
        )
        self.assertEqual(
            ready["ready"]["spec_sha256"],
            authorization["prior_specification"]["sha256"],
        )

        self.spec.write_text(
            self.spec.read_text(encoding="utf-8").replace(
                "status: draft", "status: approved", 1
            ),
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
                report_path="v2-proofread.md",
                finding_id=[],
                question_id=[],
            )
        )
        final = controller.command_confirm_ready(
            self.args(architect_id="architect-2", confirmation="exact SHA confirmed")
        )
        self.assertEqual("spec_ready", final["status"])

    def test_committed_ready_replay_is_byte_noop_for_legacy_binding(self) -> None:
        ready = self.make_ready()
        token = self.bind_authority_recovery(ready)
        self.write_full_approved_prd(4, "2099-08-11T00:00:00Z")
        arguments = self.args(
            reason="fresh PRD authority",
            architect_id="architect-2",
            recovery_token=token,
        )
        controller.command_revise_ready(arguments)

        self.assert_committed_ready_replay_byte_noop(
            arguments,
            self.root / controller.RUNTIME_STATE_RELATIVE_PATH,
            self.root / controller.RUNTIME_FINDINGS_RELATIVE_PATH,
        )

    def test_committed_ready_replay_is_byte_noop_for_direct_v2_binding(self) -> None:
        ready = self.make_ready()
        runtime = self.bind_direct_v2(ready)
        arguments = self.args(
            reason="direct v2 committed replay",
            architect_id="architect-2",
            recovery_token=None,
            specification_only=True,
        )
        controller.command_revise_ready(arguments)

        self.assert_committed_ready_replay_byte_noop(arguments, runtime)

    def test_committed_ready_replay_cli_is_byte_noop(self) -> None:
        ready = self.make_ready()
        runtime = self.bind_direct_v2(ready)
        command = (
            "revise-ready",
            "--reason",
            "public CLI committed replay",
            "--architect-id",
            "architect-2",
            "--specification-only",
        )
        first = self.cli(*command)
        self.assertEqual(0, first.returncode, first.stderr)
        state_path = self.root / controller.STATE_RELATIVE_PATH
        tracked = (state_path, self.prd, self.spec, runtime)
        before = {path: path.read_bytes() for path in tracked}

        replay = self.cli(*command)
        self.assertEqual(0, replay.returncode, replay.stderr)
        self.assertEqual(json.loads(first.stdout), json.loads(replay.stdout))
        self.assertEqual(before, {path: path.read_bytes() for path in tracked})

    def test_committed_ready_replay_is_byte_noop_for_migrated_v2_binding(self) -> None:
        ready = self.make_ready()
        runtime = self.bind_retired_schema10_v2(ready)
        arguments = self.args(
            reason="migrated v2 committed replay",
            architect_id="architect-2",
            recovery_token=None,
            specification_only=True,
        )
        controller.command_revise_ready(arguments)

        self.assert_committed_ready_replay_byte_noop(
            arguments,
            runtime,
            self.root / controller.RUNTIME_STATE_RELATIVE_PATH,
            self.root / controller.RUNTIME_FINDINGS_RELATIVE_PATH,
        )

    def test_committed_ready_replay_accepts_nfkc_equivalent_actor(self) -> None:
        ready = self.make_ready()
        runtime = self.bind_direct_v2(ready)
        first = self.args(
            reason="normalized actor committed replay",
            architect_id="Architect-２",
            recovery_token=None,
            specification_only=True,
        )
        controller.command_revise_ready(first)
        equivalent = self.args(
            reason="normalized actor committed replay",
            architect_id="architect-2",
            recovery_token=None,
            specification_only=True,
        )

        self.assert_committed_ready_replay_byte_noop(equivalent, runtime)

    def test_committed_ready_replay_rejects_changed_inputs_and_authority_without_mutation(
        self,
    ) -> None:
        ready = self.make_ready()
        runtime = self.bind_direct_v2(ready)
        arguments = self.args(
            reason="exact committed replay inputs",
            architect_id="architect-2",
            recovery_token=None,
            specification_only=True,
        )
        controller.command_revise_ready(arguments)
        state_path = self.root / controller.STATE_RELATIVE_PATH

        changed_inputs = {
            "actor": self.args(
                reason="exact committed replay inputs",
                architect_id="architect-3",
                recovery_token=None,
                specification_only=True,
            ),
            "reason": self.args(
                reason="changed committed replay reason",
                architect_id="architect-2",
                recovery_token=None,
                specification_only=True,
            ),
            "mode": self.args(
                reason="exact committed replay inputs",
                architect_id="architect-2",
                recovery_token=None,
                specification_only=False,
            ),
            "token": self.args(
                reason="exact committed replay inputs",
                architect_id="architect-2",
                recovery_token="ARH-CHANGED",
                specification_only=True,
            ),
        }
        for label, changed in changed_inputs.items():
            with self.subTest(label=label):
                self.assert_committed_ready_replay_rejected_without_mutation(
                    changed, "exact original inputs", runtime
                )

        original_prd = self.prd.read_bytes()
        self.prd.write_bytes(original_prd + b"changed after committed reopen\n")
        self.assert_committed_ready_replay_rejected_without_mutation(
            arguments, "changed PRD bytes", runtime
        )
        self.prd.write_bytes(original_prd)

        original_runtime = runtime.read_bytes()
        runtime.write_text(
            json.dumps(json.loads(original_runtime), indent=2), encoding="utf-8"
        )
        self.assert_committed_ready_replay_rejected_without_mutation(
            arguments, "authorization changed", runtime
        )
        runtime.write_bytes(original_runtime)

        original_draft = self.spec.read_bytes()
        self.spec.write_bytes(original_draft + b"Architect draft drift\n")
        self.assert_committed_ready_replay_rejected_without_mutation(
            arguments, "draft bytes changed", runtime
        )
        self.spec.write_bytes(original_draft)

        original_state = state_path.read_bytes()
        projection = json.loads(original_state)
        projection["waves"] = [{"number": 99}]
        controller.write_state_file(state_path, projection)
        self.assert_committed_ready_replay_rejected_without_mutation(
            arguments, "committed state projection changed", runtime
        )
        state_path.write_bytes(original_state)

        receipt = json.loads(original_state)
        receipt["history"][-1]["prior_ready_sha256"] = "f" * 64
        controller.write_state_file(state_path, receipt)
        self.assert_committed_ready_replay_rejected_without_mutation(
            arguments, "committed replay receipt changed", runtime
        )
        state_path.write_bytes(original_state)

    def test_committed_ready_replay_rejects_noncanonical_receipt_archive(
        self,
    ) -> None:
        ready = self.make_ready()
        runtime = self.bind_direct_v2(ready)
        arguments = self.args(
            reason="strict canonical committed receipt",
            architect_id="architect-2",
            recovery_token=None,
            specification_only=True,
        )
        controller.command_revise_ready(arguments)
        state_path = self.root / controller.STATE_RELATIVE_PATH
        original_state = state_path.read_bytes()

        poison_labels = (
            "specification_only_integer",
            "top_level_extra",
            "opened_at_invalid",
            "reason_blank",
            "new_architect_blank",
            "prior_revision_bool",
            "next_revision_float",
            "prior_ready_sha_uppercase",
            "draft_sha_uppercase",
            "prior_specification_extra",
            "prior_specification_changed",
            "prior_ready_extra",
            "prior_prd_extra",
            "new_prd_extra",
            "prior_architects_extra",
            "prior_architects_changed",
            "prior_waves_extra",
            "prior_waves_changed",
            "prior_hold_history_changed",
            "prior_total_cycles_changed",
        )
        for label in poison_labels:
            with self.subTest(label=label):
                poisoned = json.loads(original_state)
                receipt = poisoned["history"][-1]
                if label == "specification_only_integer":
                    receipt["specification_only"] = 1
                elif label == "top_level_extra":
                    receipt["unexpected"] = True
                elif label == "opened_at_invalid":
                    receipt["opened_at"] = "not-a-timestamp"
                elif label == "reason_blank":
                    receipt["reason"] = "  "
                elif label == "new_architect_blank":
                    receipt["new_architect_id"] = "  "
                elif label == "prior_revision_bool":
                    receipt["prior_revision"] = True
                elif label == "next_revision_float":
                    receipt["next_revision"] = 2.0
                elif label == "prior_ready_sha_uppercase":
                    receipt["prior_ready_sha256"] = receipt[
                        "prior_ready_sha256"
                    ].upper()
                elif label == "draft_sha_uppercase":
                    receipt["draft_sha256"] = receipt["draft_sha256"].upper()
                elif label == "prior_specification_extra":
                    receipt["prior_specification"]["unexpected"] = True
                elif label == "prior_specification_changed":
                    receipt["prior_specification"]["status"] = "draft"
                elif label == "prior_ready_extra":
                    receipt["prior_ready"]["unexpected"] = True
                elif label == "prior_prd_extra":
                    receipt["prior_prd"]["unexpected"] = True
                elif label == "new_prd_extra":
                    receipt["new_prd"]["unexpected"] = True
                elif label == "prior_architects_extra":
                    receipt["prior_architects"][0]["unexpected"] = True
                elif label == "prior_architects_changed":
                    receipt["prior_architects"] = []
                elif label == "prior_waves_extra":
                    receipt["prior_waves"][0]["unexpected"] = True
                elif label == "prior_waves_changed":
                    receipt["prior_waves"] = []
                elif label == "prior_hold_history_changed":
                    receipt["prior_hold_history"] = [{}]
                elif label == "prior_total_cycles_changed":
                    receipt["prior_total_cycles_completed"] += 1
                controller.write_state_file(state_path, poisoned)
                self.assert_committed_ready_replay_rejected_without_mutation(
                    arguments, "committed replay receipt changed", runtime
                )
                state_path.write_bytes(original_state)

    def test_recovery_authorization_rejects_noninteger_schema_live_and_archive(
        self,
    ) -> None:
        ready = self.make_ready()
        runtime = self.bind_direct_v2(ready)
        arguments = self.args(
            reason="strict authorization schema",
            architect_id="architect-2",
            recovery_token=None,
            specification_only=True,
        )
        controller.command_revise_ready(arguments)
        state_path = self.root / controller.STATE_RELATIVE_PATH
        schema2 = controller.load_state(self.root)
        schema1 = json.loads(json.dumps(schema2))
        legacy = self.released_v2_schema1_authorization(
            schema1["recovery_authorization"]
        )
        schema1["recovery_authorization"] = dict(legacy)
        schema1["history"][-1]["recovery_authorization"] = dict(legacy)

        cases = (
            ("schema1-bool", schema1, True),
            ("schema1-float", schema1, 1.0),
            ("schema2-float", schema2, 2.0),
        )
        for label, baseline, schema in cases:
            for location in ("live", "archive"):
                with self.subTest(label=label, location=location):
                    poisoned = json.loads(json.dumps(baseline))
                    target = (
                        poisoned["recovery_authorization"]
                        if location == "live"
                        else poisoned["history"][-1]["recovery_authorization"]
                    )
                    target["schema"] = schema
                    controller.write_state_file(state_path, poisoned)
                    self.assert_committed_ready_replay_rejected_without_mutation(
                        arguments, "schema", runtime
                    )

    def test_pending_prd_revision_rejects_coordinated_revision_and_draft_tamper(
        self,
    ) -> None:
        ready = self.make_ready()
        runtime = self.bind_direct_v2(ready)
        self.write_full_approved_prd(4, "2099-08-11T00:00:00Z")
        arguments = self.args(
            reason="reject coordinated pending PRD receipt tamper",
            architect_id="architect-2",
            recovery_token=None,
            specification_only=False,
        )
        with mock.patch.object(
            controller, "write_bytes_atomically", side_effect=OSError("lost response")
        ):
            with self.assertRaisesRegex(OSError, "lost response"):
                controller.command_revise_ready(arguments)

        state_path = self.root / controller.STATE_RELATIVE_PATH
        poisoned = controller.load_state(self.root)
        transition = poisoned["ready_revision"]
        transition["new_prd"]["revision"] = "999"
        draft, _, _ = controller.reopened_specification_bytes(
            self.spec,
            transition["new_prd"]["path"],
            transition["new_prd"]["revision"],
            transition["new_prd"]["sha256"],
        )
        transition["draft_sha256"] = hashlib.sha256(draft).hexdigest()
        controller.write_state_file(state_path, poisoned)
        tracked = (state_path, self.prd, self.spec, runtime)
        before = {path: path.read_bytes() for path in tracked}

        with self.assertRaisesRegex(
            controller.SpecificationStateError, "live approved PRD"
        ):
            controller.command_revise_ready(arguments)
        self.assertEqual(before, {path: path.read_bytes() for path in tracked})

    def test_committed_prd_revision_rejects_coordinated_revision_projection(
        self,
    ) -> None:
        ready = self.make_ready()
        runtime = self.bind_direct_v2(ready)
        self.write_full_approved_prd(4, "2099-08-11T00:00:00Z")
        arguments = self.args(
            reason="reject coordinated committed PRD receipt tamper",
            architect_id="architect-2",
            recovery_token=None,
            specification_only=False,
        )
        controller.command_revise_ready(arguments)

        state_path = self.root / controller.STATE_RELATIVE_PATH
        poisoned = controller.load_state(self.root)
        receipt = poisoned["history"][-1]
        receipt["new_prd"]["revision"] = "999"
        poisoned["prd"]["revision"] = "999"
        self.spec.write_text(
            self.spec.read_text(encoding="utf-8").replace(
                "  revision: 4", "  revision: 999", 1
            ),
            encoding="utf-8",
        )
        poisoned_draft_sha = controller.sha256(self.spec)
        receipt["draft_sha256"] = poisoned_draft_sha
        poisoned["specification"]["sha256"] = poisoned_draft_sha
        controller.write_state_file(state_path, poisoned)

        self.assert_committed_ready_replay_rejected_without_mutation(
            arguments, "live approved PRD", runtime
        )

    def test_committed_ready_replay_rejects_bool_numbers_and_blank_receipt_ids(
        self,
    ) -> None:
        self.initialize()
        self.write_spec(status="approved")
        controller.command_accept_spec(self.args())
        self.start_and_record(
            1,
            major=0,
            product_questions=1,
            coverage_complete=True,
        )
        controller.command_complete_cycle(
            self.args(
                architect_id="architect-1",
                resolution_note="record the product decision",
                user_decision_note="the user resolved the product question",
            )
        )
        self.start_and_record(2, major=0, coverage_complete=True)
        ready = controller.command_confirm_ready(
            self.args(architect_id="architect-1", confirmation="same SHA confirmed")
        )
        runtime = self.bind_direct_v2(ready)
        arguments = self.args(
            reason="strict numeric and ID receipt fields",
            architect_id="architect-2",
            recovery_token=None,
            specification_only=True,
        )
        controller.command_revise_ready(arguments)
        state_path = self.root / controller.STATE_RELATIVE_PATH
        original_state = state_path.read_bytes()

        for label in (
            "wave_number_bool",
            "wave_number_float",
            "blank_finding_id",
            "blank_question_id",
            "nfkc_duplicate_finding_ids",
            "nfkc_duplicate_question_ids",
        ):
            with self.subTest(label=label):
                poisoned = json.loads(original_state)
                receipt = poisoned["history"][-1]
                if label == "wave_number_bool":
                    receipt["prior_waves"][0]["number"] = True
                elif label == "wave_number_float":
                    receipt["prior_waves"][0]["number"] = 1.0
                elif label == "blank_finding_id":
                    proofread = receipt["prior_waves"][-1]["proofread"]
                    proofread["minor"] = 1
                    proofread["minors_engineer_resolvable"] = True
                    proofread["finding_ids"] = [""]
                elif label == "blank_question_id":
                    receipt["prior_waves"][0]["proofread"]["question_ids"] = [""]
                elif label == "nfkc_duplicate_finding_ids":
                    proofread = receipt["prior_waves"][-1]["proofread"]
                    proofread["minor"] = 2
                    proofread["minors_engineer_resolvable"] = True
                    proofread["finding_ids"] = ["FINDING", "ＦＩＮＤＩＮＧ"]
                else:
                    proofread = receipt["prior_waves"][0]["proofread"]
                    proofread["questions"]["product"] = 2
                    proofread["question_ids"] = ["QUESTION", "ＱＵＥＳＴＩＯＮ"]
                controller.write_state_file(state_path, poisoned)
                self.assert_committed_ready_replay_rejected_without_mutation(
                    arguments, "committed replay receipt changed", runtime
                )
                state_path.write_bytes(original_state)

    def test_committed_ready_replay_rejects_architect_edit_and_accepted_state(
        self,
    ) -> None:
        ready = self.make_ready()
        runtime = self.bind_direct_v2(ready)
        arguments = self.args(
            reason="replay only before Architect work",
            architect_id="architect-2",
            recovery_token=None,
            specification_only=True,
        )
        controller.command_revise_ready(arguments)

        original_draft = self.spec.read_bytes()
        self.spec.write_bytes(original_draft + b"Architect content edit\n")
        self.assert_committed_ready_replay_rejected_without_mutation(
            arguments, "draft bytes changed", runtime
        )

        self.spec.write_bytes(original_draft)
        self.spec.write_text(
            self.spec.read_text(encoding="utf-8").replace(
                "status: draft", "status: approved", 1
            ),
            encoding="utf-8",
        )
        controller.command_accept_spec(self.args())
        self.assert_committed_ready_replay_rejected_without_mutation(
            arguments, "requires exact spec_ready state", runtime
        )

    def test_v2_reopen_custom_state_path_revalidates_through_fresh_convergence(self) -> None:
        ready = self.make_ready()
        default_runtime = self.bind_retired_schema10_v2(ready)
        runtime = default_runtime.with_name("custom-run.json")
        default_runtime.replace(runtime)

        reopened = controller.command_revise_ready(
            self.args(
                reason="custom v2 state specification correction",
                architect_id="architect-2",
                recovery_token=None,
                specification_only=True,
            )
        )
        self.assertEqual(
            ".agentic-pipeline-v2/custom-run.json",
            reopened["recovery_authorization"]["runtime_state_path"],
        )
        self.spec.write_text(
            self.spec.read_text(encoding="utf-8").replace(
                "status: draft", "status: approved", 1
            ),
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
                report_path="custom-v2-proofread.md",
                finding_id=[],
                question_id=[],
            )
        )
        final = controller.command_confirm_ready(
            self.args(architect_id="architect-2", confirmation="custom v2 SHA confirmed")
        )
        self.assertEqual("spec_ready", final["status"])

    def test_unrelated_v2_directory_does_not_create_a_runtime_binding(self) -> None:
        self.initialize()
        runtime_directory = self.root / controller.V2_RUNTIME_STATE_RELATIVE_PATH.parent
        runtime_directory.mkdir()
        (runtime_directory / "diagnostics.json").write_text("{}\n", encoding="utf-8")

        state = controller.command_start_cycle(
            self.args(architect_id="architect-1", proofreader_id="proofreader-1")
        )

        self.assertEqual("proofreader-1", state["active_wave"]["proofreader_id"])

    def test_v2_reopen_allows_closed_gate_and_answered_question_audit_history(self) -> None:
        ready = self.make_ready()
        runtime = self.bind_retired_schema10_v2(ready)

        def add_closed_gate(value: dict) -> None:
            value["gates"] = {
                "closed-review-history": {
                    "status": "closed",
                    "phase": "review",
                    "kind": "worker_result",
                }
            }
            value["questions"] = {
                "answered-planning-history": {
                    "status": "answered",
                    "phase": "plan",
                    "prompt": "retain this audit question",
                    "answer": "resolved before the reopen boundary",
                }
            }

        self._rewrite_runtime(runtime, add_closed_gate)
        reopened = controller.command_revise_ready(
            self.args(
                reason="revise with retained closed gate evidence",
                architect_id="architect-2",
                recovery_token=None,
                specification_only=True,
            )
        )

        self.assertEqual("awaiting_accept", reopened["status"])

    def test_v2_reopen_rejects_ambiguous_malformed_foreign_and_unproven_binding(self) -> None:
        cases = {
            "ambiguous": lambda runtime: (
                runtime.parent / "other.json"
            ).write_bytes(runtime.read_bytes()),
            "malformed": lambda runtime: self._rewrite_runtime(
                runtime, lambda value: value.update({"generation": True})
            ),
            "foreign": lambda runtime: self._rewrite_runtime(
                runtime, lambda value: value.update({"project_root": str(self.root.parent)})
            ),
            "incomplete lineage": lambda runtime: (
                self.root / controller.RUNTIME_FINDINGS_RELATIVE_PATH
            ).unlink(),
            "unproven lineage": lambda runtime: self._rewrite_runtime(
                self.root / controller.RUNTIME_STATE_RELATIVE_PATH,
                lambda value: value.update({"generation": 999}),
            ),
        }
        for label, mutate in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                prior_root, prior_temp, prior_feature, prior_prd, prior_spec = (
                    self.root, self.temp, self.feature_dir, self.prd, self.spec
                )
                self.temp = None
                self.root = Path(temporary)
                self.feature_dir = (
                    self.root / "docs" / "Features" / "template" / "sample-feature"
                )
                self.feature_dir.mkdir(parents=True)
                self.prd = self.feature_dir / "product-requirements.md"
                self.spec = self.feature_dir / "technical-specification.md"
                self.prd.write_text(PRD, encoding="utf-8")
                try:
                    ready = self.make_ready()
                    runtime = self.bind_retired_schema10_v2(ready)
                    mutate(runtime)
                    self.assert_v2_reopen_rejected(
                        "ambiguous|invalid|different project|exact project|complete proven|lineage"
                    )
                finally:
                    self.root, self.temp, self.feature_dir, self.prd, self.spec = (
                        prior_root, prior_temp, prior_feature, prior_prd, prior_spec
                    )

    @staticmethod
    def _rewrite_runtime(runtime: Path, mutate: object) -> None:
        value = json.loads(runtime.read_text(encoding="utf-8"))
        mutate(value)
        runtime.write_text(json.dumps(value), encoding="utf-8")

    def test_v2_reopen_rejects_authority_and_quiescence_mismatches(self) -> None:
        cases = {
            "requirements path": lambda value: value["authority"]["items"][
                "requirements"
            ].update({"path": "docs/foreign-product-requirements.md"}),
            "requirements SHA": lambda value: value["authority"]["items"][
                "requirements"
            ].update({"sha256": "b" * 64}),
            "specification path": lambda value: value["authority"]["items"][
                "specification"
            ].update({"path": "docs/foreign-technical-specification.md"}),
            "prior specification SHA": lambda value: value["authority"]["items"][
                "specification"
            ].update({"sha256": "c" * 64}),
            "open gate": lambda value: value.update({
                "gates": {
                    "blocked": {"status": "open", "phase": "plan", "kind": "test"}
                }
            }),
            "open question": lambda value: value.update({
                "questions": {
                    "question": {
                        "status": "open",
                        "phase": "plan",
                        "prompt": "resolve authority",
                    }
                }
            }),
        }
        for label, mutate in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                prior_root, prior_temp, prior_feature, prior_prd, prior_spec = (
                    self.root, self.temp, self.feature_dir, self.prd, self.spec
                )
                self.temp = None
                self.root = Path(temporary)
                self.feature_dir = (
                    self.root / "docs" / "Features" / "template" / "sample-feature"
                )
                self.feature_dir.mkdir(parents=True)
                self.prd = self.feature_dir / "product-requirements.md"
                self.spec = self.feature_dir / "technical-specification.md"
                self.prd.write_text(PRD, encoding="utf-8")
                try:
                    ready = self.make_ready()
                    runtime = self.bind_retired_schema10_v2(ready)

                    def bound_mutation(value: dict) -> None:
                        mutate(value)
                        value["authority"]["digest"] = self.canonical_digest(
                            value["authority"]["items"]
                        )

                    self._rewrite_runtime(runtime, bound_mutation)
                    self.assert_v2_reopen_rejected("exact project|quiescent")
                finally:
                    self.root, self.temp, self.feature_dir, self.prd, self.spec = (
                        prior_root, prior_temp, prior_feature, prior_prd, prior_spec
                    )

    def test_v2_specification_only_reopen_rejects_active_terminal_drift_and_token(self) -> None:
        ready = self.make_ready()
        runtime = self.bind_retired_schema10_v2(ready)
        runtime_controller = controller._pipeline_v2_runner.Controller(
            controller._pipeline_v2_transaction.StateStore(runtime)
        )
        action = runtime_controller.status()["next_action"]
        runtime_controller.next(
            command_id=action["command_id"],
            assignment=action["assignment"],
            expected_generation=15,
        )
        self.assert_v2_reopen_rejected("quiescent")

        runtime.unlink()
        runtime = self.bind_retired_schema10_v2(ready)
        with mock.patch.object(
            controller._pipeline_v2_runner.Controller,
            "status",
            return_value={
                "next_action": {
                    "kind": "terminal",
                    "result": "checkout_recovery_required",
                }
            },
        ):
            self.assert_v2_reopen_rejected("terminal|checkout recovery")

        state_before = (self.root / controller.STATE_RELATIVE_PATH).read_bytes()
        spec_before = self.spec.read_bytes()
        with self.assertRaisesRegex(controller.SpecificationStateError, "tokenless"):
            controller.command_revise_ready(
                self.args(
                    reason="bounded v2 specification correction",
                    architect_id="architect-2",
                    recovery_token="ARH-FOREIGN",
                    specification_only=True,
                )
            )
        self.assertEqual(state_before, (self.root / controller.STATE_RELATIVE_PATH).read_bytes())
        self.assertEqual(spec_before, self.spec.read_bytes())

    def test_prd_revision_rewinds_active_v2_plan_and_reconverges(self) -> None:
        ready = self.make_ready()
        runtime = self.bind_direct_v2(ready)
        runtime_controller = controller._pipeline_v2_runner.Controller(
            controller._pipeline_v2_transaction.StateStore(runtime)
        )
        action = runtime_controller.status()["next_action"]
        runtime_controller.next(
            command_id=action["command_id"],
            assignment=action["assignment"],
            expected_generation=action["expected_generation"],
        )
        self.assertIsNotNone(runtime_controller.status()["active_assignment"])
        runtime_before = runtime.read_bytes()
        prior_prd = dict(ready["prd"])
        prior_specification = {
            "path": ready["specification"]["path"],
            "sha256": ready["ready"]["spec_sha256"],
        }

        self.write_full_approved_prd(4, "2099-08-11T00:00:00Z")
        rewind_action = runtime_controller.status()["next_action"]
        self.assertEqual("command", rewind_action["kind"])
        self.assertEqual("init", rewind_action["command"])
        self.assertFalse(rewind_action["user_input_required"])
        arguments = self.args(
            reason="approved product authority changed during active planning",
            architect_id="architect-2",
            recovery_token=None,
            specification_only=False,
        )
        reopened = controller.command_revise_ready(arguments)

        self.assertEqual("awaiting_accept", reopened["status"])
        self.assertEqual("prd_revision", reopened["history"][-1]["revision_kind"])
        self.assertEqual("4", reopened["prd"]["revision"])
        authorization = reopened["recovery_authorization"]
        self.assertEqual(2, authorization["schema"])
        self.assertEqual("prd_revision", authorization["revision_kind"])
        self.assertEqual(
            {"path": prior_prd["path"], "sha256": prior_prd["sha256"]},
            authorization["prior_requirements"],
        )
        self.assertEqual(prior_specification, authorization["prior_specification"])
        self.assertEqual(
            hashlib.sha256(runtime_before).hexdigest(),
            authorization["runtime_state_sha256"],
        )
        self.assertEqual(runtime_before, runtime.read_bytes())

        self.assert_committed_ready_replay_byte_noop(arguments, runtime)
        final = self.complete_fresh_v2_reopen("prd-rewind-proofread.md")
        self.assertEqual("spec_ready", final["status"])
        self.assertEqual("4", final["prd"]["revision"])
        self.assertEqual(runtime_before, runtime.read_bytes())

    def test_prd_revision_allows_stale_open_v2_lifecycle_evidence_at_init_boundary(self) -> None:
        ready = self.make_ready()
        runtime = self.bind_direct_v2(ready)
        runtime_before = runtime.read_bytes()
        self.write_full_approved_prd(4, "2099-08-11T00:00:00Z")
        with mock.patch.object(
            controller._pipeline_v2_runner.Controller,
            "status",
            return_value={
                "active_assignment": {"id": "stale-plan-assignment"},
                "open_gates": ["stale-gate"],
                "open_questions": ["stale-question"],
                "next_action": {
                    "kind": "command",
                    "command": "init",
                    "user_input_required": False,
                },
            },
        ):
            reopened = controller.command_revise_ready(
                self.args(
                    reason="approved PRD supersedes stale runtime lifecycle evidence",
                    architect_id="architect-2",
                    recovery_token=None,
                    specification_only=False,
                )
            )
        self.assertEqual("awaiting_accept", reopened["status"])
        self.assertEqual("prd_revision", reopened["recovery_authorization"]["revision_kind"])
        self.assertEqual(runtime_before, runtime.read_bytes())

    def test_prd_revision_rejects_non_init_recovery_unknown_and_token_without_mutation(self) -> None:
        self.make_ready()
        runtime = self.bind_direct_v2(controller.load_state(self.root))
        self.write_full_approved_prd(4, "2099-08-11T00:00:00Z")
        state_path = self.root / controller.STATE_RELATIVE_PATH
        cases = {
            "non-init": {
                "active_assignment": None,
                "open_gates": [],
                "open_questions": [],
                "next_action": {
                    "kind": "command",
                    "command": "next",
                    "user_input_required": False,
                },
            },
            "user-input": {
                "active_assignment": None,
                "open_gates": [],
                "open_questions": [],
                "next_action": {
                    "kind": "command",
                    "command": "init",
                    "user_input_required": True,
                },
            },
            "recovery": {
                "active_assignment": None,
                "open_gates": [],
                "open_questions": [],
                "next_action": {
                    "kind": "terminal",
                    "result": "checkout_recovery_required",
                },
            },
            "unknown": {
                "active_assignment": None,
                "open_gates": [],
                "open_questions": [],
                "next_action": {"kind": "unknown-effect"},
            },
        }
        for label, public_status in cases.items():
            with self.subTest(label=label), mock.patch.object(
                controller._pipeline_v2_runner.Controller,
                "status",
                return_value=public_status,
            ):
                state_before = state_path.read_bytes()
                spec_before = self.spec.read_bytes()
                runtime_before = runtime.read_bytes()
                with self.assertRaisesRegex(
                    controller.SpecificationStateError,
                    "init|terminal|checkout recovery|unknown|safe",
                ):
                    controller.command_revise_ready(
                        self.args(
                            reason="reject unsafe PRD rewind boundary",
                            architect_id="architect-2",
                            recovery_token=None,
                            specification_only=False,
                        )
                    )
                self.assertEqual(state_before, state_path.read_bytes())
                self.assertEqual(spec_before, self.spec.read_bytes())
                self.assertEqual(runtime_before, runtime.read_bytes())

        state_before = state_path.read_bytes()
        spec_before = self.spec.read_bytes()
        runtime_before = runtime.read_bytes()
        with self.assertRaisesRegex(controller.SpecificationStateError, "tokenless"):
            controller.command_revise_ready(
                self.args(
                    reason="reject token on PRD rewind",
                    architect_id="architect-2",
                    recovery_token="ARH-FOREIGN",
                    specification_only=False,
                )
            )
        self.assertEqual(state_before, state_path.read_bytes())
        self.assertEqual(spec_before, self.spec.read_bytes())
        self.assertEqual(runtime_before, runtime.read_bytes())

    def test_prd_revision_revalidates_prior_v2_runtime_cas_on_continuation(self) -> None:
        ready = self.make_ready()
        runtime = self.bind_direct_v2(ready)
        runtime_before = runtime.read_bytes()
        self.write_full_approved_prd(4, "2099-08-11T00:00:00Z")
        controller.command_revise_ready(
            self.args(
                reason="CAS-bound PRD rewind",
                architect_id="architect-2",
                recovery_token=None,
                specification_only=False,
            )
        )
        self.spec.write_text(
            self.spec.read_text(encoding="utf-8").replace(
                "status: draft", "status: approved", 1
            ),
            encoding="utf-8",
        )
        runtime.write_text(json.dumps(json.loads(runtime_before), indent=2), encoding="utf-8")
        state_path = self.root / controller.STATE_RELATIVE_PATH
        state_before = state_path.read_bytes()
        spec_before = self.spec.read_bytes()
        with self.assertRaisesRegex(controller.SpecificationStateError, "authorization changed"):
            controller.command_accept_spec(self.args())
        self.assertEqual(state_before, state_path.read_bytes())
        self.assertEqual(spec_before, self.spec.read_bytes())

    def test_v2_reopen_rejects_unknown_public_status_effect(self) -> None:
        ready = self.make_ready()
        self.bind_retired_schema10_v2(ready)
        with mock.patch.object(
            controller._pipeline_v2_runner.Controller,
            "status",
            return_value={
                "active_assignment": None,
                "open_gates": [],
                "open_questions": [],
                "next_action": {"kind": "unknown-effect"},
            },
        ):
            self.assert_v2_reopen_rejected("terminal|checkout recovery|safe")

    def test_v2_reopen_revalidates_runtime_cas_at_every_continuation(self) -> None:
        ready = self.make_ready()
        runtime = self.bind_retired_schema10_v2(ready)
        original_runtime = runtime.read_bytes()
        reopened = controller.command_revise_ready(
            self.args(
                reason="CAS-bound v2 specification correction",
                architect_id="architect-2",
                recovery_token=None,
                specification_only=True,
            )
        )
        self.assertEqual("awaiting_accept", reopened["status"])
        self.spec.write_text(
            self.spec.read_text(encoding="utf-8").replace(
                "status: draft", "status: approved", 1
            ),
            encoding="utf-8",
        )

        def change_runtime_bytes() -> None:
            runtime.write_text(
                json.dumps(json.loads(original_runtime), indent=2), encoding="utf-8"
            )

        change_runtime_bytes()
        state_before = (self.root / controller.STATE_RELATIVE_PATH).read_bytes()
        with self.assertRaisesRegex(controller.SpecificationStateError, "authorization changed"):
            controller.command_accept_spec(self.args())
        self.assertEqual(state_before, (self.root / controller.STATE_RELATIVE_PATH).read_bytes())
        runtime.write_bytes(original_runtime)
        controller.command_accept_spec(self.args())
        controller.command_start_cycle(
            self.args(architect_id="architect-2", proofreader_id="proofreader-2")
        )

        proofread_args = self.args(
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
            report_path="cas-proofread.md",
            finding_id=[],
            question_id=[],
        )
        change_runtime_bytes()
        state_before = (self.root / controller.STATE_RELATIVE_PATH).read_bytes()
        with self.assertRaisesRegex(controller.SpecificationStateError, "authorization changed"):
            controller.command_record_proofread(proofread_args)
        self.assertEqual(state_before, (self.root / controller.STATE_RELATIVE_PATH).read_bytes())
        runtime.write_bytes(original_runtime)
        controller.command_record_proofread(proofread_args)

        change_runtime_bytes()
        state_before = (self.root / controller.STATE_RELATIVE_PATH).read_bytes()
        with self.assertRaisesRegex(controller.SpecificationStateError, "authorization changed"):
            controller.command_confirm_ready(
                self.args(architect_id="architect-2", confirmation="exact SHA confirmed")
            )
        self.assertEqual(state_before, (self.root / controller.STATE_RELATIVE_PATH).read_bytes())

    def test_pending_v2_reopen_replays_exactly_and_rejects_runtime_change(self) -> None:
        ready = self.make_ready()
        runtime = self.bind_retired_schema10_v2(ready)
        args = self.args(
            reason="replay-bound v2 specification correction",
            architect_id="architect-2",
            recovery_token=None,
            specification_only=True,
        )
        with mock.patch.object(
            controller, "write_bytes_atomically", side_effect=OSError("lost response")
        ):
            with self.assertRaisesRegex(OSError, "lost response"):
                controller.command_revise_ready(args)
        pending = controller.load_state(self.root)
        self.assertEqual("ready_revision_pending", pending["status"])
        runtime.write_text(
            json.dumps(json.loads(runtime.read_text(encoding="utf-8")), indent=2),
            encoding="utf-8",
        )
        state_before = (self.root / controller.STATE_RELATIVE_PATH).read_bytes()
        spec_before = self.spec.read_bytes()
        with self.assertRaisesRegex(controller.SpecificationStateError, "authorization changed"):
            controller.command_revise_ready(args)
        self.assertEqual(state_before, (self.root / controller.STATE_RELATIVE_PATH).read_bytes())
        self.assertEqual(spec_before, self.spec.read_bytes())

    def test_pending_v2_reopen_rejects_changed_inputs_then_replays_exactly(self) -> None:
        ready = self.make_ready()
        self.bind_retired_schema10_v2(ready)
        args = self.args(
            reason="exact replay inputs",
            architect_id="architect-2",
            recovery_token=None,
            specification_only=True,
        )
        with mock.patch.object(
            controller, "write_bytes_atomically", side_effect=OSError("lost response")
        ):
            with self.assertRaisesRegex(OSError, "lost response"):
                controller.command_revise_ready(args)
        state_path = self.root / controller.STATE_RELATIVE_PATH
        for label, changed in {
            "reason": self.args(
                reason="different reason",
                architect_id="architect-2",
                recovery_token=None,
                specification_only=True,
            ),
            "actor": self.args(
                reason="exact replay inputs",
                architect_id="architect-3",
                recovery_token=None,
                specification_only=True,
            ),
            "mode": self.args(
                reason="exact replay inputs",
                architect_id="architect-2",
                recovery_token=None,
                specification_only=False,
            ),
        }.items():
            with self.subTest(label=label):
                state_before = state_path.read_bytes()
                spec_before = self.spec.read_bytes()
                with self.assertRaisesRegex(
                    controller.SpecificationStateError, "exact original inputs"
                ):
                    controller.command_revise_ready(changed)
                self.assertEqual(state_before, state_path.read_bytes())
                self.assertEqual(spec_before, self.spec.read_bytes())
        reopened = controller.command_revise_ready(args)
        self.assertEqual("awaiting_accept", reopened["status"])
        self.assertIn("revision: 2", self.spec.read_text(encoding="utf-8"))

    def test_released_v2_schema1_pending_before_spec_write_resumes_without_rewrite(self) -> None:
        ready = self.make_ready()
        runtime = self.bind_direct_v2(ready)
        arguments = self.args(
            reason="released schema-1 pending before specification write",
            architect_id="architect-2",
            recovery_token=None,
            specification_only=True,
        )
        with mock.patch.object(
            controller, "write_bytes_atomically", side_effect=OSError("lost response")
        ):
            with self.assertRaisesRegex(OSError, "lost response"):
                controller.command_revise_ready(arguments)
        self.assertIn("status: approved", self.spec.read_text(encoding="utf-8"))
        legacy = self.persist_released_v2_schema1_authorization()
        state_path = self.root / controller.STATE_RELATIVE_PATH
        stored_before_load = state_path.read_bytes()
        controller.load_state(self.root)
        self.assertEqual(stored_before_load, state_path.read_bytes())

        reopened = controller.command_revise_ready(arguments)

        self.assertEqual("awaiting_accept", reopened["status"])
        self.assertEqual(legacy, reopened["recovery_authorization"])
        self.assertEqual(legacy, reopened["history"][-1]["recovery_authorization"])
        self.assertIn("status: draft", self.spec.read_text(encoding="utf-8"))
        self.assertEqual(2, reopened["schema_version"])
        self.assertEqual(
            hashlib.sha256(runtime.read_bytes()).hexdigest(),
            legacy["runtime_state_sha256"],
        )

    def test_released_v2_schema1_pending_after_spec_write_resumes_without_rewrite(self) -> None:
        ready = self.make_ready()
        self.bind_direct_v2(ready)
        arguments = self.args(
            reason="released schema-1 pending after specification write",
            architect_id="architect-2",
            recovery_token=None,
            specification_only=True,
        )
        real_write = controller.write_bytes_atomically

        def write_then_lose_response(path: Path, value: bytes) -> None:
            real_write(path, value)
            raise OSError("lost response after specification write")

        with mock.patch.object(
            controller, "write_bytes_atomically", side_effect=write_then_lose_response
        ):
            with self.assertRaisesRegex(OSError, "after specification write"):
                controller.command_revise_ready(arguments)
        self.assertIn("status: draft", self.spec.read_text(encoding="utf-8"))
        legacy = self.persist_released_v2_schema1_authorization()

        reopened = controller.command_revise_ready(arguments)

        self.assertEqual("awaiting_accept", reopened["status"])
        self.assertEqual(legacy, reopened["recovery_authorization"])
        self.assertEqual(legacy, reopened["history"][-1]["recovery_authorization"])

    def test_released_v2_schema1_committed_replay_and_full_convergence(self) -> None:
        ready = self.make_ready()
        runtime = self.bind_direct_v2(ready)
        arguments = self.args(
            reason="continue released schema-1 committed specification reopen",
            architect_id="architect-2",
            recovery_token=None,
            specification_only=True,
        )
        controller.command_revise_ready(arguments)
        legacy = self.persist_released_v2_schema1_authorization()

        self.assert_committed_ready_replay_byte_noop(arguments, runtime)
        final = self.complete_fresh_v2_reopen("released-schema1-proofread.md")

        self.assertEqual("spec_ready", final["status"])
        self.assertEqual(legacy, final["recovery_authorization"])
        receipt = next(
            event
            for event in reversed(final["history"])
            if event.get("event") == "ready_specification_revision_opened"
        )
        self.assertEqual(legacy, receipt["recovery_authorization"])
        self.assertNotIn("revision_kind", legacy)
        self.assertEqual(2, final["schema_version"])

    def test_released_v2_schema1_rejects_malformed_history_runtime_and_source_byte_noop(self) -> None:
        ready = self.make_ready()
        runtime = self.bind_direct_v2(ready)
        arguments = self.args(
            reason="reject tampered released schema-1 authorization",
            architect_id="architect-2",
            recovery_token=None,
            specification_only=True,
        )
        controller.command_revise_ready(arguments)
        self.persist_released_v2_schema1_authorization()
        state_path = self.root / controller.STATE_RELATIVE_PATH
        original_state = state_path.read_bytes()

        for label in ("extra", "missing", "mixed", "history-mismatch", "archive"):
            with self.subTest(label=label):
                poisoned = json.loads(original_state)
                receipt = poisoned["history"][-1]
                receipt_authorization = receipt["recovery_authorization"]
                state_authorization = poisoned["recovery_authorization"]
                if label == "extra":
                    receipt_authorization["extra"] = "forbidden"
                    state_authorization["extra"] = "forbidden"
                elif label == "missing":
                    receipt_authorization.pop("prior_spec_sha256")
                    state_authorization.pop("prior_spec_sha256")
                elif label == "mixed":
                    receipt_authorization["revision_kind"] = "specification_only"
                    state_authorization["revision_kind"] = "specification_only"
                elif label == "history-mismatch":
                    state_authorization["reason"] = "different live authorization"
                else:
                    receipt["prior_ready"]["spec_sha256"] = "b" * 64
                    receipt["prior_ready_sha256"] = "b" * 64
                    receipt["prior_specification"]["sha256"] = "b" * 64
                    receipt_authorization["prior_spec_sha256"] = "b" * 64
                    poisoned["recovery_authorization"]["prior_spec_sha256"] = "b" * 64
                controller.write_state_file(state_path, poisoned)
                self.assert_committed_ready_replay_rejected_without_mutation(
                    arguments, "authorization|archive|history|released|receipt", runtime
                )
                state_path.write_bytes(original_state)

        poisoned = json.loads(original_state)
        receipt = poisoned["history"][-1]
        receipt["specification_only"] = False
        receipt["revision_kind"] = "prd_revision"
        receipt["spec_ready_disposition"] = "revoked_by_prd_revision"
        controller.write_state_file(state_path, poisoned)
        self.assert_committed_ready_replay_rejected_without_mutation(
            self.args(
                reason=arguments.reason,
                architect_id="architect-2",
                recovery_token=None,
                specification_only=False,
            ),
            "schema-1|archive|specification-only",
            runtime,
        )
        state_path.write_bytes(original_state)

        ambiguous_runtime = runtime.with_name("ambiguous-released-schema1.json")
        ambiguous_runtime.write_bytes(runtime.read_bytes())
        self.assert_committed_ready_replay_rejected_without_mutation(
            arguments, "multiple v2|ambiguous", runtime, ambiguous_runtime
        )
        ambiguous_runtime.unlink()

        runtime_before = runtime.read_bytes()
        runtime.write_text(json.dumps(json.loads(runtime_before), indent=2), encoding="utf-8")
        self.assert_committed_ready_replay_rejected_without_mutation(
            arguments, "authorization changed", runtime
        )
        runtime.write_bytes(runtime_before)

        self.spec.write_bytes(self.spec.read_bytes() + b"tampered source\n")
        self.assert_committed_ready_replay_rejected_without_mutation(
            arguments, "draft bytes changed", runtime
        )

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
        self.assertIn("v2 revisions", help_result.stdout)
        self.assertIn("user_input_required=false", help_result.stdout)
        self.assertIn("tokenless", help_result.stdout)
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

    def test_skill_contract_records_the_bounded_v2_reopen_route(self) -> None:
        skill_root = Path(__file__).resolve().parents[1]
        skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        contract_text = (
            skill_root / "references" / "specification-contract.md"
        ).read_text(encoding="utf-8")
        for text in (skill_text, contract_text):
            self.assertIn("retired schema-10", text)
            self.assertIn("direct v2", text)
            self.assertIn("legacy residue", text)
            self.assertIn("revise-ready", text)
            self.assertIn("--specification-only", text)
            self.assertIn("token", text)
            self.assertIn("checkout recovery", text)
            self.assertIn("user_input_required: false", text)
            self.assertIn("prior runtime requirements", text)
            self.assertIn("active assignment", text)
        self.assertIn("exact v2 state SHA", skill_text)
        self.assertIn("normalized in memory and never rewritten", skill_text)
        self.assertIn("Multiple, malformed, foreign, mixed, or unproven", contract_text)
        self.assertIn("New tokenless v2 `recovery_authorization` receipts use nested schema 2", contract_text)
        self.assertIn("mixed, missing, extra, PRD-mode, ambiguous, or tampered", contract_text)


if __name__ == "__main__":
    unittest.main()
