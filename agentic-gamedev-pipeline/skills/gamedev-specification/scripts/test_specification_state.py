#!/usr/bin/env python3
"""Tests for the bounded specification convergence controller."""

from __future__ import annotations

import sys
import json
import hashlib
import importlib
import importlib.util
import re
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
pipeline_checkout = importlib.import_module("pipeline_v2.checkout")


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
        self.preaccept_receipt = (
            self.root / ".agentic-pipeline" / "evidence" / "architect-preaccept.json"
        )
        self.helper_receipt_counter = 0
        self.prd.write_text(PRD, encoding="utf-8")
        self.initialize_git_fixture()

    def initialize_git_fixture(self) -> None:
        (self.root / ".gitignore").write_text(
            "/.agentic-pipeline/\n/.agentic-pipeline-v2/\n/.codegraph/\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(
            ["git", "-C", str(self.root), "config", "user.name", "Specification Tests"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.root), "config", "user.email", "spec-tests@example.invalid"],
            check=True,
        )
        self.commit_fixture("initial fixture")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def commit_fixture(self, message: str) -> None:
        subprocess.run(["git", "-C", str(self.root), "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", str(self.root), "commit", "--allow-empty", "-qm", message],
            check=True,
        )

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

## Goal

Implement the exact approved behavior.
{suffix}
""",
            encoding="utf-8",
        )

    def write_preaccept_receipt(self, **overrides: object) -> Path:
        self.preaccept_receipt = (
            self.root / ".agentic-pipeline" / "evidence" / "architect-preaccept.json"
        )
        self.preaccept_receipt.parent.mkdir(parents=True, exist_ok=True)
        inventory = [
            {
                "locator": locator,
                "disposition": "retain",
                "authority_or_rationale": "PRD-REQ-001 requires this authored structure.",
            }
            for locator in controller.specification_inventory_locators(self.spec)
        ]
        payload: dict[str, object] = {
            "schema": controller.PREACCEPT_RECEIPT_SCHEMA,
            "architect_id": controller.load_state(self.root)["active_architect_id"],
            "prd_sha256": controller.sha256(self.prd),
            "assessed_spec_sha256": controller.sha256(self.spec),
            "semantic_assessment": "accept",
            "section_applicability_inventory": inventory,
        }
        payload.update(overrides)
        self.preaccept_receipt.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return self.preaccept_receipt

    def prepare_helper(
        self,
        operation: str,
        correction_ids: list[str] | None = None,
    ) -> dict:
        return controller.command_prepare_helper(
            self.args(
                operation=operation,
                correction_id=(
                    correction_ids
                    if correction_ids is not None
                    else (["CORR-001"] if operation == "correction" else [])
                ),
            )
        )

    def write_fake_helper_result(self, **overrides: object) -> Path:
        state = controller.load_state(self.root)
        request_record = state["active_helper_request"]
        self.assertIsNotNone(request_record)
        request = request_record["summary"]
        artifacts = request["artifacts"]
        report = self.root / artifacts["helper_report_path"]
        coverage = self.root / artifacts["coverage_path"]
        result = self.root / artifacts["result_path"]
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            "Fake external adapter report for controller unit tests.\n",
            encoding="utf-8",
        )
        coverage.write_text(
            json.dumps(
                {
                    "owned_by": "$skill-specification-pipeline",
                    "request_id": request["request_id"],
                    "coverage": "complete",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        payload: dict[str, object] = {
            "schema": controller.HELPER_RESULT_SCHEMA,
            "request": {
                "id": request["request_id"],
                "sha256": request_record["sha256"],
            },
            "operation": request["operation"],
            "route": request["route"],
            "output_specification": {
                "path": request["specification"]["path"],
                "sha256": controller.sha256(self.spec),
            },
            "outcome": "PASS",
            "write_paths": request["allowed_write_paths"],
            "artifacts": [
                {
                    "kind": "helper_report",
                    "path": artifacts["helper_report_path"],
                    "sha256": controller.sha256(report),
                },
                {
                    "kind": "coverage",
                    "path": artifacts["coverage_path"],
                    "sha256": controller.sha256(coverage),
                },
            ],
            "helper_identity": request["helper_identity"],
        }
        payload.update(overrides)
        result.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return result

    def consume_fake_helper_result(self, **overrides: object) -> dict:
        self.write_fake_helper_result(**overrides)
        return controller.command_record_helper_result(self.args())

    def write_actual_helper_artifacts(self) -> tuple[Path, Path]:
        state = controller.load_state(self.root)
        request = state["active_helper_request"]["summary"]
        report = self.root / request["artifacts"]["helper_report_path"]
        coverage = self.root / request["artifacts"]["coverage_path"]
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("Actual emitter integration report.\n", encoding="utf-8")
        coverage.write_text(
            json.dumps({"coverage": "complete"}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return report, coverage

    def accept_spec(
        self,
        receipt: Path | None = None,
    ) -> dict:
        state = controller.load_state(self.root)
        if state.get("active_helper_request") is not None:
            self.consume_fake_helper_result()
        receipt = receipt or self.write_preaccept_receipt()
        return controller.command_accept_spec(
            self.args(
                preaccept_receipt=receipt.relative_to(self.root).as_posix(),
            )
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
        self.initialize(with_spec=False)
        self.write_spec(status="approved")
        self.accept_spec()
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
        self.commit_fixture("direct v2 fixture")
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
            base_tree_oid=pipeline_checkout.require_clean_head(self.root),
            pipeline_runtime_digest=pipeline_checkout.pipeline_runtime_digest(),
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

    def bind_schema10_residue(self, ready: dict) -> Path:
        runtime_path = self.bind_direct_v2(ready)
        state_dir = self.root / ".agentic-pipeline"
        (state_dir / "state.json").write_text(
            json.dumps({"schema_version": 10}), encoding="utf-8",
        )
        (state_dir / "findings.json").write_text(
            json.dumps({"schema_version": 10, "items": []}), encoding="utf-8",
        )
        return runtime_path
    def complete_fresh_v2_reopen(self, report_path: str) -> dict:
        self.prepare_helper("correction")
        self.spec.write_text(
            self.spec.read_text(encoding="utf-8").replace(
                "status: draft", "status: approved", 1
            ),
            encoding="utf-8",
        )
        self.accept_spec()
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
        if state["status"] == "needs_generation":
            state = self.prepare_helper("generation")
        if with_spec:
            state = self.accept_spec()
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
            self.accept_spec()
        self.assertEqual(before, state_path.read_bytes())

        cli = self.cli(
            "accept-spec", "--preaccept-receipt", "missing-preaccept.json"
        )
        self.assertEqual(2, cli.returncode)
        self.assertIn("full approved requirements contract", cli.stderr)
        self.assertEqual(before, state_path.read_bytes())

    def test_accept_spec_requires_exact_current_prd_trace(self) -> None:
        self.initialize(with_spec=False)
        self.write_spec()
        state = self.accept_spec()
        self.assertEqual(state["status"], "reviewing")
        self.assertEqual(state["specification"]["sha256"], controller.sha256(self.spec))

    def test_needs_generation_rejects_local_draft_preaccept_only_as_byte_noop(
        self,
    ) -> None:
        controller.command_init(
            self.args(
                feature="sample-feature",
                prd=self.prd.relative_to(self.root).as_posix(),
                spec=self.spec.relative_to(self.root).as_posix(),
                architect_id="architect-1",
            )
        )
        self.write_spec()
        preaccept = self.write_preaccept_receipt()
        state_path = self.root / controller.STATE_RELATIVE_PATH
        state_before = state_path.read_bytes()
        spec_before = self.spec.read_bytes()

        with self.assertRaisesRegex(
            controller.SpecificationStateError,
            "helper evidence does not end at the exact current specification SHA",
        ):
            controller.command_accept_spec(
                self.args(
                    preaccept_receipt=preaccept.relative_to(self.root).as_posix(),
                )
            )

        self.assertEqual(state_before, state_path.read_bytes())
        self.assertEqual(spec_before, self.spec.read_bytes())
        self.assertIsNone(controller.load_state(self.root)["acceptance"])

    def test_valid_generation_result_is_consumed_and_revalidated(self) -> None:
        self.initialize(with_spec=False)
        self.write_spec()
        consumed = self.consume_fake_helper_result()
        accepted = self.accept_spec()

        evidence = accepted["acceptance"]["helper_evidence"]
        self.assertEqual(
            controller.sha256(self.spec),
            evidence["results"][0]["result"]["summary"]
            ["output_specification"]["sha256"],
        )
        self.assertIsNone(evidence["source_spec_sha256"])
        self.assertIsNone(consumed["active_helper_request"])
        self.assertEqual(1, len(consumed["helper_history"]))
        report_path = self.root / (
            evidence["results"][0]["result"]["summary"]["artifacts"][0]["path"]
        )
        report_before = report_path.read_bytes()
        report_path.write_bytes(report_before + b"drift")
        state_path = self.root / controller.STATE_RELATIVE_PATH
        state_before = state_path.read_bytes()
        with self.assertRaisesRegex(
            controller.SpecificationStateError, "artifact SHA is stale or invalid"
        ):
            controller.command_start_cycle(
                self.args(
                    architect_id="architect-1",
                    proofreader_id="proofreader-helper-drift",
                )
            )
        self.assertEqual(state_before, state_path.read_bytes())
        report_path.write_bytes(report_before)
        started = controller.command_start_cycle(
            self.args(architect_id="architect-1", proofreader_id="proofreader-helper")
        )
        self.assertEqual(
            controller.sha256(self.spec), started["active_wave"]["spec_sha256"]
        )

    def test_helper_output_preflight_is_exact_read_only_and_shared_with_record(
        self,
    ) -> None:
        self.initialize(with_spec=False)
        self.write_spec()
        state = controller.load_state(self.root)
        request_path = self.root / state["active_helper_request"]["path"]
        self.assertEqual(
            controller.specification_controller_identity(),
            state["active_helper_request"]["summary"]["controller"],
        )
        state_path = self.root / controller.STATE_RELATIVE_PATH
        state_before = state_path.read_bytes()
        request_before = request_path.read_bytes()
        spec_before = self.spec.read_bytes()

        envelope = controller.command_preflight_helper_output(
            self.args(request=str(request_path))
        )
        self.assertEqual(
            {"schema", "controller", "request", "output_specification"},
            set(envelope),
        )
        self.assertEqual({"path", "sha256"}, set(envelope["controller"]))
        self.assertEqual({"id", "sha256"}, set(envelope["request"]))
        self.assertEqual(
            {"path", "sha256"}, set(envelope["output_specification"])
        )
        self.assertEqual(controller.HELPER_PREFLIGHT_SCHEMA, envelope["schema"])
        self.assertEqual(str(Path(controller.__file__).resolve()), envelope["controller"]["path"])
        self.assertEqual(
            controller.sha256(Path(controller.__file__).resolve()),
            envelope["controller"]["sha256"],
        )
        self.assertEqual("HREQ-000001", envelope["request"]["id"])
        self.assertEqual(
            state["active_helper_request"]["sha256"], envelope["request"]["sha256"]
        )
        self.assertEqual(
            self.spec.relative_to(self.root).as_posix(),
            envelope["output_specification"]["path"],
        )
        self.assertEqual(controller.sha256(self.spec), envelope["output_specification"]["sha256"])
        self.assertEqual(state_before, state_path.read_bytes())
        self.assertEqual(request_before, request_path.read_bytes())
        self.assertEqual(spec_before, self.spec.read_bytes())

        cli = self.cli("preflight-helper-output", "--request", str(request_path))
        self.assertEqual(0, cli.returncode, cli.stderr)
        self.assertEqual(envelope, json.loads(cli.stdout))
        self.assertEqual(state_before, state_path.read_bytes())

        self.spec.write_text(
            self.spec.read_text(encoding="utf-8").replace(
                controller.sha256(self.prd), "0" * 64, 1
            ),
            encoding="utf-8",
        )
        self.write_fake_helper_result()
        state_before = state_path.read_bytes()
        with self.assertRaisesRegex(
            controller.HelperOutputPreflightError, "canonical specification preflight"
        ):
            controller.command_preflight_helper_output(
                self.args(request=str(request_path))
            )
        with self.assertRaisesRegex(
            controller.HelperOutputPreflightError, "canonical specification preflight"
        ):
            controller.command_record_helper_result(self.args())
        self.assertEqual(state_before, state_path.read_bytes())

    def test_helper_output_preflight_requires_metadata_and_accepts_flat_trace(
        self,
    ) -> None:
        self.initialize(with_spec=False)
        self.write_spec(nested_trace=False)
        valid = self.spec.read_text(encoding="utf-8")
        state = controller.load_state(self.root)
        request_path = self.root / state["active_helper_request"]["path"]
        state_path = self.root / controller.STATE_RELATIVE_PATH
        mutations = {
            "missing status": valid.replace("status: draft\n", "", 1),
            "invalid status": valid.replace("status: draft", "status: ready", 1),
            "missing revision": valid.replace("revision: 1\n", "", 1),
            "zero revision": valid.replace("revision: 1", "revision: 0", 1),
            "quoted revision": valid.replace("revision: 1", "revision: '1'", 1),
            "missing language": valid.replace("language: English\n", "", 1),
            "mismatched language": valid.replace(
                "language: English", "language: Russian", 1
            ),
        }
        for label, candidate in mutations.items():
            with self.subTest(label=label):
                self.spec.write_text(candidate, encoding="utf-8")
                self.write_fake_helper_result()
                state_before = state_path.read_bytes()
                with self.assertRaisesRegex(
                    controller.HelperOutputPreflightError,
                    "canonical specification preflight",
                ):
                    controller.command_preflight_helper_output(
                        self.args(request=str(request_path))
                    )
                with self.assertRaisesRegex(
                    controller.HelperOutputPreflightError,
                    "canonical specification preflight",
                ):
                    controller.command_record_helper_result(self.args())
                self.assertEqual(state_before, state_path.read_bytes())

        self.spec.write_text(valid, encoding="utf-8")
        self.write_fake_helper_result()
        controller.command_preflight_helper_output(
            self.args(request=str(request_path))
        )
        consumed = controller.command_record_helper_result(self.args())
        self.assertIsNone(consumed["active_helper_request"])

    def test_reject_invalid_initial_generation_recovers_once_and_routes_hreq2(
        self,
    ) -> None:
        self.initialize(with_spec=False)
        initial = controller.load_state(self.root)
        request_path = self.root / initial["active_helper_request"]["path"]
        legacy_request = json.loads(request_path.read_text(encoding="utf-8"))
        legacy_request.pop("controller")
        request_path.write_text(
            json.dumps(legacy_request, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        initial["active_helper_request"] = controller.validate_helper_request(
            self.root,
            initial,
            str(request_path),
            require_current_identity=False,
        )
        controller.save_state(self.root, initial)
        self.spec.write_text(
            "# Headerless helper output\n\n## Goal\n\nImplement the behavior.\n",
            encoding="utf-8",
        )
        result_path = self.write_fake_helper_result()
        state_path = self.root / controller.STATE_RELATIVE_PATH
        initial = controller.load_state(self.root)
        artifact_paths = [
            request_path,
            result_path,
            self.spec,
            self.root
            / initial["active_helper_request"]["summary"]["artifacts"]
            ["helper_report_path"],
            self.root
            / initial["active_helper_request"]["summary"]["artifacts"]
            ["coverage_path"],
        ]
        artifact_bytes = {path: path.read_bytes() for path in artifact_paths}
        reason = "canonical output preflight rejected stale PRD authority"

        state_before = state_path.read_bytes()
        with self.assertRaisesRegex(
            controller.SpecificationStateError, "exact initial generation request"
        ):
            controller.command_reject_helper_result(
                self.args(request_id="HREQ-999999", reason=reason)
            )
        self.assertEqual(state_before, state_path.read_bytes())

        drifted_identity = dict(
            initial["active_helper_request"]["summary"]["helper_identity"]
        )
        drifted_identity["result_emitter_sha256"] = "f" * 64
        with mock.patch.object(
            controller, "external_helper_identity", return_value=drifted_identity
        ):
            state_before = state_path.read_bytes()
            with self.assertRaisesRegex(
                controller.SpecificationStateError, "controller binding is missing"
            ):
                controller.command_record_helper_result(self.args())
            self.assertEqual(state_before, state_path.read_bytes())
            recovered = controller.command_reject_helper_result(
                self.args(request_id="HREQ-000001", reason=reason)
            )

        output_sha = controller.sha256(self.spec)
        self.assertEqual("needs_generation", recovered["status"])
        self.assertIsNone(recovered["active_helper_request"])
        self.assertEqual([], recovered["helper_history"])
        self.assertEqual(
            {"source_spec_sha256": output_sha, "results": []},
            recovered["helper_evidence"],
        )
        self.assertIsNone(recovered["specification"]["sha256"])
        self.assertEqual(
            output_sha, recovered["specification"]["generation_input_sha256"]
        )
        self.assertTrue(recovered["specification"]["trace_errors"])
        self.assertEqual(1, len(recovered["history"]))
        self.assertEqual(
            controller.HELPER_REJECTION_EVENT,
            recovered["history"][-1]["event"],
        )
        for path, before in artifact_bytes.items():
            self.assertEqual(before, path.read_bytes(), path)

        replay_before = state_path.read_bytes()
        replayed = controller.command_reject_helper_result(
            self.args(request_id="HREQ-000001", reason=reason)
        )
        self.assertEqual(recovered, replayed)
        self.assertEqual(replay_before, state_path.read_bytes())

        report_path = artifact_paths[-2]
        report_before = report_path.read_bytes()
        report_path.write_bytes(report_before + b"drift")
        state_before = state_path.read_bytes()
        with self.assertRaisesRegex(controller.SpecificationStateError, "artifact SHA"):
            controller.command_reject_helper_result(
                self.args(request_id="HREQ-000001", reason=reason)
            )
        self.assertEqual(state_before, state_path.read_bytes())
        report_path.write_bytes(report_before)

        state_before = state_path.read_bytes()
        with self.assertRaisesRegex(
            controller.SpecificationStateError, "initial generation must be consumed"
        ):
            self.prepare_helper("correction", ["CORR-FORBIDDEN"])
        self.assertEqual(state_before, state_path.read_bytes())

        prepared = self.prepare_helper("generation")
        hreq2 = prepared["active_helper_request"]["summary"]
        self.assertEqual("HREQ-000002", hreq2["request_id"])
        self.assertEqual(
            controller.specification_controller_identity(), hreq2["controller"]
        )
        self.assertEqual("continue", hreq2["route"]["target_operation"])
        self.assertEqual(
            {"kind": "sha256", "sha256": output_sha},
            hreq2["specification"]["input"],
        )
        state_before = state_path.read_bytes()
        with self.assertRaisesRegex(
            controller.SpecificationStateError, "before further progress"
        ):
            controller.command_reject_helper_result(
                self.args(request_id="HREQ-000001", reason=reason)
            )
        self.assertEqual(state_before, state_path.read_bytes())

    def test_reject_helper_result_refuses_valid_output_as_byte_noop(self) -> None:
        self.initialize(with_spec=False)
        self.write_spec()
        self.write_fake_helper_result()
        state_path = self.root / controller.STATE_RELATIVE_PATH
        state_before = state_path.read_bytes()
        spec_before = self.spec.read_bytes()
        with self.assertRaisesRegex(
            controller.SpecificationStateError, "valid helper output cannot be rejected"
        ):
            controller.command_reject_helper_result(
                self.args(
                    request_id="HREQ-000001",
                    reason="attempt to reject a valid output",
                )
            )
        self.assertEqual(state_before, state_path.read_bytes())
        self.assertEqual(spec_before, self.spec.read_bytes())

    def test_helper_request_and_result_binding_failures_are_byte_noops(self) -> None:
        self.initialize(with_spec=False)
        self.write_spec()
        state_path = self.root / controller.STATE_RELATIVE_PATH
        state = controller.load_state(self.root)
        request_path = self.root / state["active_helper_request"]["path"]
        request_before = request_path.read_bytes()
        spec_before = self.spec.read_bytes()

        state_before = state_path.read_bytes()
        with self.assertRaisesRegex(
            controller.SpecificationStateError, "helper request is active"
        ):
            self.prepare_helper("generation")
        self.assertEqual(state_before, state_path.read_bytes())
        self.assertEqual(request_before, request_path.read_bytes())

        request = json.loads(request_before)
        request["expected_user_language"] = "Russian"
        request_path.write_text(
            json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        state_before = state_path.read_bytes()
        with self.assertRaisesRegex(
            controller.SpecificationStateError, "request.*changed|language binding"
        ):
            controller.command_record_helper_result(self.args())
        self.assertEqual(state_before, state_path.read_bytes())
        self.assertEqual(spec_before, self.spec.read_bytes())
        request_path.write_bytes(request_before)

        result_path = self.write_fake_helper_result()
        base = json.loads(result_path.read_text(encoding="utf-8"))
        mutations = {
            "missing field": lambda value: value.pop("operation"),
            "request SHA": lambda value: value["request"].update(
                {"sha256": "0" * 64}
            ),
            "operation": lambda value: value.update({"operation": "correction"}),
            "mode": lambda value: value["route"].update(
                {"mode": "spec-assistant"}
            ),
            "output SHA": lambda value: value["output_specification"].update(
                {"sha256": "0" * 64}
            ),
            "outcome": lambda value: value.update({"outcome": "FAIL"}),
            "write set": lambda value: value["write_paths"].append("docs/another.md"),
            "identity": lambda value: value["helper_identity"].update(
                {"entrypoint_sha256": "0" * 64}
            ),
            "artifact SHA": lambda value: value["artifacts"][0].update(
                {"sha256": "0" * 64}
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                candidate = json.loads(json.dumps(base))
                mutate(candidate)
                result_path.write_text(
                    json.dumps(candidate, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                state_before = state_path.read_bytes()
                with self.assertRaises(controller.SpecificationStateError):
                    controller.command_record_helper_result(self.args())
                self.assertEqual(state_before, state_path.read_bytes())
                self.assertEqual(spec_before, self.spec.read_bytes())

        result_path.write_text(
            json.dumps(base, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        controller.command_record_helper_result(self.args())
        state_before = state_path.read_bytes()
        with self.assertRaisesRegex(
            controller.SpecificationStateError, "no active.*request"
        ):
            controller.command_record_helper_result(self.args())
        self.assertEqual(state_before, state_path.read_bytes())

    def test_record_helper_result_requires_current_helper_fingerprint(self) -> None:
        self.initialize(with_spec=False)
        self.write_spec()
        self.write_fake_helper_result()
        state_path = self.root / controller.STATE_RELATIVE_PATH
        state = controller.load_state(self.root)
        drifted_identity = dict(
            state["active_helper_request"]["summary"]["helper_identity"]
        )
        drifted_identity["result_emitter_sha256"] = "f" * 64
        state_before = state_path.read_bytes()
        with mock.patch.object(
            controller, "external_helper_identity", return_value=drifted_identity
        ):
            with self.assertRaisesRegex(
                controller.SpecificationStateError, "fingerprint changed"
            ):
                controller.command_record_helper_result(self.args())
        self.assertEqual(state_before, state_path.read_bytes())

    def test_actual_external_emitter_creates_one_immutable_result(self) -> None:
        self.initialize(with_spec=False)
        self.write_spec()
        self.write_actual_helper_artifacts()
        state = controller.load_state(self.root)
        request = self.root / state["active_helper_request"]["path"]
        emitter = Path(
            state["active_helper_request"]["summary"]["helper_identity"]
            ["result_emitter_path"]
        )

        emitted = subprocess.run(
            [
                sys.executable,
                "-B",
                str(emitter),
                "--controller",
                str(Path(controller.__file__).resolve()),
                "--request",
                str(request),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, emitted.returncode, emitted.stderr)
        result_path = self.root / (
            state["active_helper_request"]["summary"]["artifacts"]["result_path"]
        )
        result_before = result_path.read_bytes()

        consumed = controller.command_record_helper_result(self.args())
        self.assertIsNone(consumed["active_helper_request"])
        accepted = self.accept_spec()
        self.assertEqual("reviewing", accepted["status"])

        replay = subprocess.run(
            [
                sys.executable,
                "-B",
                str(emitter),
                "--controller",
                str(Path(controller.__file__).resolve()),
                "--request",
                str(request),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(2, replay.returncode)
        self.assertIn("already exists", replay.stderr)
        self.assertEqual(result_before, result_path.read_bytes())

    def test_actual_external_emitter_rejects_foreign_controller_before_launch(
        self,
    ) -> None:
        self.initialize(with_spec=False)
        self.write_spec()
        self.write_actual_helper_artifacts()
        state = controller.load_state(self.root)
        request = self.root / state["active_helper_request"]["path"]
        result_path = self.root / (
            state["active_helper_request"]["summary"]["artifacts"]["result_path"]
        )
        emitter = Path(
            state["active_helper_request"]["summary"]["helper_identity"]
            ["result_emitter_path"]
        )
        foreign = self.root / "foreign-compatible-controller.py"
        marker = self.root / "foreign-controller-ran.txt"
        foreign.write_text(
            f"""import argparse
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--project-root", required=True)
parser.add_argument("command")
parser.add_argument("--request", required=True)
args = parser.parse_args()
request_path = Path(args.request).resolve()
request_bytes = request_path.read_bytes()
request = json.loads(request_bytes.decode("utf-8"))
root = Path(request["project_root"]).resolve()
specification = root / request["specification"]["path"]
current = Path(__file__).resolve()
Path({json.dumps(str(marker))}).write_text("ran", encoding="utf-8")
print(json.dumps({{
    "schema": 1,
    "controller": {{
        "path": str(current),
        "sha256": hashlib.sha256(current.read_bytes()).hexdigest(),
    }},
    "request": {{
        "id": request["request_id"],
        "sha256": hashlib.sha256(request_bytes).hexdigest(),
    }},
    "output_specification": {{
        "path": request["specification"]["path"],
        "sha256": hashlib.sha256(specification.read_bytes()).hexdigest(),
    }},
}}))
""",
            encoding="utf-8",
        )

        rejected = subprocess.run(
            [
                sys.executable,
                "-B",
                str(emitter),
                "--controller",
                str(foreign),
                "--request",
                str(request),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(2, rejected.returncode)
        self.assertIn("does not match the helper request binding", rejected.stderr)
        self.assertFalse(marker.exists())
        self.assertFalse(result_path.exists())

        emitted = subprocess.run(
            [
                sys.executable,
                "-B",
                str(emitter),
                "--controller",
                str(Path(controller.__file__).resolve()),
                "--request",
                str(request),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, emitted.returncode, emitted.stderr)
        self.assertTrue(result_path.is_file())

    def test_actual_external_emitter_preflight_rejects_headerless_output(self) -> None:
        self.initialize(with_spec=False)
        self.spec.write_text(
            "# Headerless helper output\n\n## Goal\n\nImplement the behavior.\n",
            encoding="utf-8",
        )
        report, coverage = self.write_actual_helper_artifacts()
        state = controller.load_state(self.root)
        state_path = self.root / controller.STATE_RELATIVE_PATH
        request = self.root / state["active_helper_request"]["path"]
        result_path = self.root / (
            state["active_helper_request"]["summary"]["artifacts"]["result_path"]
        )
        emitter = Path(
            state["active_helper_request"]["summary"]["helper_identity"]
            ["result_emitter_path"]
        )
        state_before = state_path.read_bytes()
        immutable_before = {
            path: path.read_bytes()
            for path in (request, self.spec, report, coverage)
        }

        emitted = subprocess.run(
            [
                sys.executable,
                "-B",
                str(emitter),
                "--controller",
                str(Path(controller.__file__).resolve()),
                "--request",
                str(request),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(2, emitted.returncode)
        self.assertIn("preflight", emitted.stderr.casefold())
        self.assertFalse(result_path.exists())
        self.assertEqual(state_before, state_path.read_bytes())
        for path, before in immutable_before.items():
            self.assertEqual(before, path.read_bytes(), path)

    def test_actual_external_emitter_preflight_rejects_missing_metadata(self) -> None:
        self.initialize(with_spec=False)
        self.write_spec()
        self.spec.write_text(
            self.spec.read_text(encoding="utf-8").replace(
                "language: English\n", "", 1
            ),
            encoding="utf-8",
        )
        report, coverage = self.write_actual_helper_artifacts()
        state = controller.load_state(self.root)
        state_path = self.root / controller.STATE_RELATIVE_PATH
        request = self.root / state["active_helper_request"]["path"]
        result_path = self.root / (
            state["active_helper_request"]["summary"]["artifacts"]["result_path"]
        )
        emitter = Path(
            state["active_helper_request"]["summary"]["helper_identity"]
            ["result_emitter_path"]
        )
        state_before = state_path.read_bytes()
        immutable_before = {
            path: path.read_bytes()
            for path in (request, self.spec, report, coverage)
        }

        emitted = subprocess.run(
            [
                sys.executable,
                "-B",
                str(emitter),
                "--controller",
                str(Path(controller.__file__).resolve()),
                "--request",
                str(request),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(2, emitted.returncode)
        self.assertIn("preflight", emitted.stderr.casefold())
        self.assertFalse(result_path.exists())
        self.assertEqual(state_before, state_path.read_bytes())
        for path, before in immutable_before.items():
            self.assertEqual(before, path.read_bytes(), path)

    def test_accept_spec_preaccept_receipt_failures_are_byte_noops(self) -> None:
        self.initialize(with_spec=False)
        self.write_spec()
        self.consume_fake_helper_result()
        state_path = self.root / controller.STATE_RELATIVE_PATH
        spec_before = self.spec.read_bytes()

        def assert_rejected(receipt: Path | None, pattern: str = "pre-accept") -> None:
            state_before = state_path.read_bytes()
            arguments = self.args(
                **(
                    {"preaccept_receipt": receipt.relative_to(self.root).as_posix()}
                    if receipt is not None
                    else {}
                )
            )
            with self.assertRaisesRegex(controller.SpecificationStateError, pattern):
                controller.command_accept_spec(arguments)
            self.assertEqual(state_before, state_path.read_bytes())
            self.assertEqual(spec_before, self.spec.read_bytes())

        assert_rejected(None, "requires --preaccept-receipt")

        self.preaccept_receipt.parent.mkdir(parents=True, exist_ok=True)
        self.preaccept_receipt.write_text("{", encoding="utf-8")
        assert_rejected(self.preaccept_receipt, "valid UTF-8 JSON")

        base_path = self.write_preaccept_receipt()
        base = json.loads(base_path.read_text(encoding="utf-8"))
        mutations = {
            "malformed schema": lambda value: value.update({"schema": 2}),
            "stale SHA": lambda value: value.update(
                {"assessed_spec_sha256": "0" * 64}
            ),
            "blank rationale": lambda value: value[
                "section_applicability_inventory"
            ][0].update({"authority_or_rationale": " "}),
            "duplicate locator": lambda value: value[
                "section_applicability_inventory"
            ].append(dict(value["section_applicability_inventory"][0])),
            "reject assessment": lambda value: value.update(
                {"semantic_assessment": "reject"}
            ),
            "remove disposition": lambda value: value[
                "section_applicability_inventory"
            ][0].update({"disposition": "remove"}),
            "merge disposition": lambda value: value[
                "section_applicability_inventory"
            ][0].update({"disposition": "merge"}),
            "defer disposition": lambda value: value[
                "section_applicability_inventory"
            ][0].update({"disposition": "defer"}),
            "identity mismatch": lambda value: value.update(
                {"architect_id": "different-architect"}
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                candidate = json.loads(json.dumps(base))
                mutate(candidate)
                base_path.write_text(
                    json.dumps(candidate, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                assert_rejected(base_path)

    def test_formatter_counterexample_requires_correction_helper_result(self) -> None:
        self.initialize(with_spec=False)
        trace = controller.sha256(self.prd)
        self.spec.write_text(
            f"""---
document_type: technical-specification
status: draft
revision: 1
language: English
source_prd_path: docs/Features/template/sample-feature/product-requirements.md
source_prd_revision: 3
source_prd_sha256: {trace}
---
# RoundTimeFormatter Technical Specification

## Goal

Format supported seconds as M:SS for PRD-REQ-001.

## Data Models

No structured model is introduced.

| Contract value | Type |
|---|---|
| totalSeconds | number |

## System Diagram

```text
seconds -> formatter -> M:SS
```

## Behavior

The pure formatter returns the exact PRD-AC-001 output.

## Open Questions

None.

## Source Coverage Manifest

| Source ID | Address |
|---|---|
| PRD-REQ-001 | Goal and Behavior |

No assumptions or risks are introduced.
""",
            encoding="utf-8",
        )
        old_sha = controller.sha256(self.spec)
        self.consume_fake_helper_result()
        inventory = []
        for locator in controller.specification_inventory_locators(self.spec):
            remove = any(
                token in locator
                for token in (
                    "Data Models",
                    "System Diagram",
                    "Open Questions",
                    "diagram:",
                    "footer:",
                )
            )
            if locator.startswith("table:") and not any(
                row["locator"].startswith("table:") for row in inventory
            ):
                remove = True
            inventory.append(
                {
                    "locator": locator,
                    "disposition": "remove" if remove else "retain",
                    "authority_or_rationale": (
                        "CORR-001 removes formatter boilerplate."
                        if remove
                        else "PRD-REQ-001 requires this distinct content."
                    ),
                }
            )
        rejected_receipt = self.write_preaccept_receipt(
            semantic_assessment="reject",
            section_applicability_inventory=inventory,
        )
        state_path = self.root / controller.STATE_RELATIVE_PATH
        state_before = state_path.read_bytes()
        with self.assertRaisesRegex(
            controller.SpecificationStateError, "semantic assessment must be accept"
        ):
            controller.command_accept_spec(
                self.args(
                    preaccept_receipt=rejected_receipt.relative_to(self.root).as_posix()
                )
            )
        self.assertEqual(state_before, state_path.read_bytes())
        self.assertEqual(old_sha, controller.sha256(self.spec))

        self.prepare_helper("correction", ["CORR-001"])
        corrected = self.spec.read_text(encoding="utf-8")
        corrected = corrected.replace(
            """## Data Models

No structured model is introduced.

| Contract value | Type |
|---|---|
| totalSeconds | number |

""",
            "",
        ).replace(
            """## System Diagram

```text
seconds -> formatter -> M:SS
```

""",
            "",
        ).replace(
            """## Open Questions

None.

""",
            "",
        ).replace("\nNo assumptions or risks are introduced.\n", "\n")
        self.spec.write_text(corrected, encoding="utf-8")
        new_sha = controller.sha256(self.spec)
        self.assertNotEqual(old_sha, new_sha)

        accepted = self.accept_spec()
        summary = accepted["acceptance"]["preaccept_receipt"]["summary"]
        self.assertEqual("reviewing", accepted["status"])
        self.assertEqual(new_sha, summary["assessed_spec_sha256"])
        self.assertTrue(summary["required_locators"])
        self.assertFalse(
            any(
                token in locator
                for locator in summary["required_locators"]
                for token in ("Data Models", "System Diagram", "Open Questions", "footer:")
            )
        )

    def test_active_wave_rejects_late_accept_spec_as_byte_noop(self) -> None:
        self.initialize()
        controller.command_start_cycle(
            self.args(architect_id="architect-1", proofreader_id="proofreader-late")
        )
        receipt = self.write_preaccept_receipt()
        state_path = self.root / controller.STATE_RELATIVE_PATH
        state_before = state_path.read_bytes()
        spec_before = self.spec.read_bytes()
        with self.assertRaisesRegex(
            controller.SpecificationStateError, "forbidden while a Proofreader wave is active"
        ):
            controller.command_accept_spec(
                self.args(preaccept_receipt=receipt.relative_to(self.root).as_posix())
            )
        self.assertEqual(state_before, state_path.read_bytes())
        self.assertEqual(spec_before, self.spec.read_bytes())

    def test_active_wave_legacy_acceptance_cannot_create_review_credit(self) -> None:
        self.initialize()
        controller.command_start_cycle(
            self.args(architect_id="architect-1", proofreader_id="proofreader-legacy")
        )
        state_path = self.root / controller.STATE_RELATIVE_PATH
        legacy = controller.load_state(self.root)
        legacy["acceptance"].pop("preaccept_receipt")
        controller.save_state(self.root, legacy)
        spec_before = self.spec.read_bytes()

        record_args = self.args(
            proofreader_id="proofreader-legacy",
            critical=0,
            major=0,
            minor=0,
            product_questions=0,
            scope_questions=0,
            boundary_questions=0,
            ownership_questions=0,
            public_contract_questions=0,
            minors_engineer_resolvable=True,
            coverage_complete=True,
            report_path="legacy-proofread.json",
            finding_id=[],
            question_id=[],
        )
        state_before = state_path.read_bytes()
        with self.assertRaisesRegex(
            controller.SpecificationStateError, "exact Architect pre-accept receipt"
        ):
            controller.command_record_proofread(record_args)
        self.assertEqual(state_before, state_path.read_bytes())
        self.assertEqual(spec_before, self.spec.read_bytes())

        legacy = controller.load_state(self.root)
        legacy["active_wave"]["proofread"] = {
            "critical": 0,
            "major": 0,
            "minor": 0,
            "questions": {
                "product": 0,
                "scope": 0,
                "boundary": 0,
                "ownership": 0,
                "public_contract": 0,
            },
            "minors_engineer_resolvable": True,
            "coverage_complete": True,
            "report_path": "legacy-proofread.json",
            "finding_ids": [],
            "question_ids": [],
            "recorded_at": "2026-08-29T00:00:00+00:00",
        }
        controller.save_state(self.root, legacy)
        for label, action in (
            (
                "complete",
                lambda: controller.command_complete_cycle(
                    self.args(
                        architect_id="architect-1",
                        resolution_note="must not create legacy credit",
                        user_decision_note=None,
                    )
                ),
            ),
            (
                "confirm",
                lambda: controller.command_confirm_ready(
                    self.args(
                        architect_id="architect-1",
                        confirmation="must not create legacy readiness",
                    )
                ),
            ),
        ):
            with self.subTest(label=label):
                state_before = state_path.read_bytes()
                with self.assertRaisesRegex(
                    controller.SpecificationStateError,
                    "exact Architect pre-accept receipt",
                ):
                    action()
                self.assertEqual(state_before, state_path.read_bytes())
                self.assertEqual(spec_before, self.spec.read_bytes())

    def test_active_wave_requires_acceptance_not_later_than_wave_start(self) -> None:
        self.initialize()
        controller.command_start_cycle(
            self.args(architect_id="architect-1", proofreader_id="proofreader-time")
        )
        state_path = self.root / controller.STATE_RELATIVE_PATH
        state = controller.load_state(self.root)
        state["acceptance"]["accepted_at"] = "2099-08-29T00:00:00+00:00"
        controller.save_state(self.root, state)
        before = state_path.read_bytes()
        with self.assertRaisesRegex(
            controller.SpecificationStateError, "predates the current specification acceptance"
        ):
            controller.command_record_proofread(
                self.args(
                    proofreader_id="proofreader-time",
                    critical=0,
                    major=0,
                    minor=0,
                    product_questions=0,
                    scope_questions=0,
                    boundary_questions=0,
                    ownership_questions=0,
                    public_contract_questions=0,
                    minors_engineer_resolvable=True,
                    coverage_complete=True,
                    report_path="time-proofread.json",
                    finding_id=[],
                    question_id=[],
                )
            )
        self.assertEqual(before, state_path.read_bytes())

    def test_nested_hierarchy_and_standalone_footer_can_be_retained(self) -> None:
        self.initialize(with_spec=False)
        self.write_spec(
            suffix="""

## Component Ownership

- Formatter feature
  - Shared formatter module
  - Focused verification runner

## Flat Constraints

- Keep the utility pure.
- Keep the runner focused.

## Coverage

PRD-REQ-001 is covered by the formatter and runner.

No assumptions, source conflicts, unresolved risks, or additional product obligations are introduced.
"""
        )
        locators = controller.specification_inventory_locators(self.spec)
        hierarchy = [item for item in locators if item.startswith("hierarchy:")]
        footer = [item for item in locators if item.startswith("footer:")]
        self.assertEqual(1, len(hierarchy))
        self.assertEqual(1, len(footer))
        self.assertFalse(any("Flat Constraints" in item and item.startswith("hierarchy:") for item in locators))
        accepted = self.accept_spec()
        summary = accepted["acceptance"]["preaccept_receipt"]["summary"]
        self.assertIn(hierarchy[0], summary["required_locators"])
        self.assertIn(footer[0], summary["required_locators"])

    def test_nested_hierarchy_and_footer_remove_require_corrected_new_sha(self) -> None:
        self.initialize(with_spec=False)
        self.write_spec(
            suffix="""

## Duplicate Hierarchy

- Formatter feature
  - Formatter module
  - Formatter runner

## Coverage

PRD-REQ-001 is already covered here.

No additional assumptions or risks exist.
"""
        )
        old_sha = controller.sha256(self.spec)
        self.consume_fake_helper_result()
        inventory = []
        for locator in controller.specification_inventory_locators(self.spec):
            remove = locator.startswith(("hierarchy:", "footer:")) or "Duplicate Hierarchy" in locator
            inventory.append(
                {
                    "locator": locator,
                    "disposition": "remove" if remove else "retain",
                    "authority_or_rationale": (
                        "CORR-HIER-001 removes duplicate structure."
                        if remove
                        else "PRD-REQ-001 requires this distinct content."
                    ),
                }
            )
        receipt = self.write_preaccept_receipt(
            section_applicability_inventory=inventory
        )
        state_path = self.root / controller.STATE_RELATIVE_PATH
        before = state_path.read_bytes()
        with self.assertRaisesRegex(
            controller.SpecificationStateError, "disposition must be retain"
        ):
            controller.command_accept_spec(
                self.args(preaccept_receipt=receipt.relative_to(self.root).as_posix())
            )
        self.assertEqual(before, state_path.read_bytes())

        self.prepare_helper("correction", ["CORR-HIER-001"])
        corrected = self.spec.read_text(encoding="utf-8").replace(
            """## Duplicate Hierarchy

- Formatter feature
  - Formatter module
  - Formatter runner

""",
            "",
        ).replace("\nNo additional assumptions or risks exist.\n", "\n")
        self.spec.write_text(corrected, encoding="utf-8")
        new_sha = controller.sha256(self.spec)
        self.assertNotEqual(old_sha, new_sha)
        accepted = self.accept_spec()
        summary = accepted["acceptance"]["preaccept_receipt"]["summary"]
        self.assertEqual(new_sha, summary["assessed_spec_sha256"])
        self.assertFalse(
            any(
                locator.startswith(("hierarchy:", "footer:"))
                for locator in summary["required_locators"]
            )
        )

    def test_final_section_ordinary_paragraphs_are_not_footer_structure(self) -> None:
        self.initialize(with_spec=False)
        self.write_spec(
            suffix="""

## Verification

The focused runner validates PRD-AC-001 across the supported input boundary.

The integration runner validates the same output at the current call site.
"""
        )
        locators = controller.specification_inventory_locators(self.spec)
        self.assertFalse(any(item.startswith("footer:") for item in locators))

    def test_exact_and_normalized_no_content_registers_are_footer_structure(self) -> None:
        self.initialize(with_spec=False)
        exact_footer = (
            "No assumptions, source conflicts, unresolved risks, or additional "
            "product obligations are introduced."
        )
        self.write_spec(
            suffix=f"""

## Coverage

PRD-REQ-001 is covered by the formatter and runner.

{exact_footer}
"""
        )
        exact_locators = controller.specification_inventory_locators(self.spec)
        self.assertEqual(
            1, len([item for item in exact_locators if item.startswith("footer:")])
        )

        normalized_footer = """NO   ASSUMPTIONS, source conflicts,
unresolved risks, OR additional product obligations are introduced !"""
        self.write_spec(
            suffix=f"""

## Coverage

PRD-REQ-001 is covered by the formatter and runner.

{normalized_footer}
"""
        )
        normalized_locators = controller.specification_inventory_locators(self.spec)
        self.assertEqual(
            1,
            len(
                [item for item in normalized_locators if item.startswith("footer:")]
            ),
        )

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
        self.initialize(with_spec=False)
        self.write_spec(status="approved")
        self.accept_spec()
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
        self.initialize(with_spec=False)
        self.write_spec(status="approved")
        self.accept_spec()
        self.start_and_record(1, major=0, coverage_complete=True)
        self.spec.write_text(self.spec.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
        with self.assertRaisesRegex(
            controller.SpecificationStateError,
            "pre-accept receipt specification SHA|same specification SHA",
        ):
            controller.command_confirm_ready(
                self.args(architect_id="architect-1", confirmation="confirm")
            )

    def test_edit_before_record_proofread_remains_rejected(self) -> None:
        self.initialize()
        controller.command_start_cycle(
            self.args(architect_id="architect-1", proofreader_id="proofreader-early-edit")
        )
        self.spec.write_text(
            self.spec.read_text(encoding="utf-8") + "\nUnreviewed edit.\n",
            encoding="utf-8",
        )
        state_path = self.root / controller.STATE_RELATIVE_PATH
        state_before = state_path.read_bytes()
        with self.assertRaisesRegex(
            controller.SpecificationStateError,
            "changed during read-only proofreading",
        ):
            controller.command_record_proofread(
                self.args(
                    proofreader_id="proofreader-early-edit",
                    critical=0,
                    major=0,
                    minor=0,
                    product_questions=0,
                    scope_questions=0,
                    boundary_questions=0,
                    ownership_questions=0,
                    public_contract_questions=0,
                    minors_engineer_resolvable=True,
                    coverage_complete=True,
                    report_path="early-edit.md",
                    finding_id=[],
                    question_id=[],
                )
            )
        self.assertEqual(state_before, state_path.read_bytes())

    def test_no_edit_complete_cycle_preserves_acceptance_and_reviewing(self) -> None:
        self.initialize()
        self.start_and_record(1, major=1, coverage_complete=True)
        before = controller.load_state(self.root)
        completed = controller.command_complete_cycle(
            self.args(
                architect_id="architect-1",
                resolution_note="No admissible specification edit is required.",
                user_decision_note=None,
            )
        )
        self.assertEqual("reviewing", completed["status"])
        self.assertEqual(before["acceptance"], completed["acceptance"])
        self.assertEqual(
            completed["waves"][-1]["spec_sha256"],
            completed["waves"][-1]["result_spec_sha256"],
        )

    def test_major_helper_correction_closes_wave_then_reaccepts_to_spec_ready(
        self,
    ) -> None:
        self.initialize()
        self.start_and_record(1, major=1, coverage_complete=True)
        wave_input_sha256 = controller.sha256(self.spec)
        self.prepare_helper("correction", ["SPEC-FINDING-1"])
        self.spec.write_text(
            self.spec.read_text(encoding="utf-8")
            .replace("status: draft", "status: approved", 1)
            + "\nPRD-REQ-001 correction applied.\n",
            encoding="utf-8",
        )
        corrected_sha256 = controller.sha256(self.spec)
        result_path = self.write_fake_helper_result()
        base = json.loads(result_path.read_text(encoding="utf-8"))
        state_path = self.root / controller.STATE_RELATIVE_PATH
        spec_before = self.spec.read_bytes()
        mutations = {
            "request": lambda value: value["request"].update(
                {"sha256": "0" * 64}
            ),
            "route": lambda value: value["route"].update(
                {"submode": "review-light"}
            ),
            "output": lambda value: value["output_specification"].update(
                {"sha256": "0" * 64}
            ),
            "outcome": lambda value: value.update({"outcome": "FAIL"}),
            "write set": lambda value: value["write_paths"].append("docs/another.md"),
            "artifact": lambda value: value["artifacts"][0].update(
                {"sha256": "0" * 64}
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                candidate = json.loads(json.dumps(base))
                mutate(candidate)
                result_path.write_text(
                    json.dumps(candidate, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                state_before = state_path.read_bytes()
                with self.assertRaises(controller.SpecificationStateError):
                    controller.command_record_helper_result(self.args())
                self.assertEqual(state_before, state_path.read_bytes())
                self.assertEqual(spec_before, self.spec.read_bytes())
        result_path.write_text(
            json.dumps(base, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        recorded = controller.command_record_helper_result(self.args())
        self.assertIsNone(recorded["active_helper_request"])

        completed = controller.command_complete_cycle(
            self.args(
                architect_id="architect-1",
                resolution_note="Apply the recorded Major correction.",
                user_decision_note=None,
            )
        )
        self.assertEqual("awaiting_accept", completed["status"])
        self.assertIsNone(completed["acceptance"])
        self.assertEqual(
            corrected_sha256, completed["waves"][-1]["result_spec_sha256"]
        )
        self.assertEqual(
            corrected_sha256,
            completed["waves"][-1]["helper_correction_results"][-1]
            ["result"]["summary"]["output_specification"]["sha256"],
        )
        with self.assertRaisesRegex(controller.SpecificationStateError, "awaiting_accept"):
            controller.command_start_cycle(
                self.args(architect_id="architect-1", proofreader_id="proofreader-2")
            )

        accepted = self.accept_spec()
        self.assertEqual("reviewing", accepted["status"])
        self.assertEqual(
            corrected_sha256, accepted["acceptance"]["specification_sha256"]
        )
        self.start_and_record(2, major=0, coverage_complete=True)
        ready = controller.command_confirm_ready(
            self.args(
                architect_id="architect-1",
                confirmation="Fresh Proofreader confirms the corrected exact SHA.",
            )
        )
        self.assertEqual("spec_ready", ready["status"])
        self.assertEqual(corrected_sha256, ready["ready"]["spec_sha256"])

    def test_ready_rejects_unresolved_product_question(self) -> None:
        self.initialize(with_spec=False)
        self.write_spec(status="approved")
        self.accept_spec()
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

        self.prepare_helper("correction")
        self.spec.write_text(
            spec_text.replace("status: draft", "status: approved", 1),
            encoding="utf-8",
        )
        self.accept_spec()
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

    def test_schema10_residue_requires_archive_and_fresh_plan_init(self) -> None:
        ready = self.make_ready()
        runtime = self.bind_schema10_residue(ready)
        state_path = self.root / controller.STATE_RELATIVE_PATH
        before = {
            path: path.read_bytes()
            for path in (state_path, self.prd, self.spec, runtime)
        }

        with self.assertRaisesRegex(
            controller.SpecificationStateError,
            re.escape(plan_controller.SCHEMA10_UNSUPPORTED_MESSAGE),
        ):
            controller.command_revise_ready(
                self.args(
                    reason="schema-10 cannot be bridged",
                    architect_id="architect-2",
                    recovery_token=None,
                    specification_only=True,
                )
            )

        self.assertEqual(before, {path: path.read_bytes() for path in before})
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
        self.initialize(with_spec=False)
        self.write_spec(status="approved")
        self.accept_spec()
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
        self.prepare_helper("correction")
        self.spec.write_text(
            self.spec.read_text(encoding="utf-8").replace(
                "status: draft", "status: approved", 1
            ),
            encoding="utf-8",
        )
        self.accept_spec()
        self.assert_committed_ready_replay_rejected_without_mutation(
            arguments, "requires exact spec_ready state", runtime
        )

    def test_v2_reopen_custom_state_path_revalidates_through_fresh_convergence(self) -> None:
        ready = self.make_ready()
        default_runtime = self.bind_direct_v2(ready)
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
        self.prepare_helper("correction")
        self.spec.write_text(
            self.spec.read_text(encoding="utf-8").replace(
                "status: draft", "status: approved", 1
            ),
            encoding="utf-8",
        )
        self.accept_spec()
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
        runtime = self.bind_direct_v2(ready)

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

    def test_v2_reopen_rejects_ambiguous_malformed_and_foreign_binding(self) -> None:
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
                self.initialize_git_fixture()
                try:
                    ready = self.make_ready()
                    runtime = self.bind_direct_v2(ready)
                    mutate(runtime)
                    self.assert_v2_reopen_rejected(
                        "ambiguous|invalid|different project|exact project"
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
                self.initialize_git_fixture()
                try:
                    ready = self.make_ready()
                    runtime = self.bind_direct_v2(ready)

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
        self.assert_v2_reopen_rejected("quiescent")

        runtime.unlink()
        runtime = self.bind_direct_v2(ready)
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
            self.accept_spec()
        self.assertEqual(state_before, state_path.read_bytes())
        self.assertEqual(spec_before, self.spec.read_bytes())

    def test_v2_reopen_rejects_unknown_public_status_effect(self) -> None:
        ready = self.make_ready()
        self.bind_direct_v2(ready)
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
        runtime = self.bind_direct_v2(ready)
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
        self.prepare_helper("correction")
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
            self.accept_spec()
        self.assertEqual(state_before, (self.root / controller.STATE_RELATIVE_PATH).read_bytes())
        runtime.write_bytes(original_runtime)
        self.accept_spec()
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
        runtime = self.bind_direct_v2(ready)
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
        self.bind_direct_v2(ready)
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
            self.assertIn("Schema-10 migration is unsupported", text)
            self.assertIn("direct v2", text)
            self.assertIn("legacy state/findings residue", text)
            self.assertIn("revise-ready", text)
            self.assertIn("--specification-only", text)
            self.assertIn("token", text)
            self.assertIn("checkout recovery", text)
            self.assertIn("user_input_required: false", text)
            self.assertIn("prior runtime requirements", text)
            self.assertIn("active assignment", text)
        self.assertIn("exact v2 state SHA", skill_text)
        self.assertIn("normalized in memory and never rewritten", skill_text)
        self.assertIn("Multiple, malformed, foreign, or mixed", contract_text)
        self.assertIn("New tokenless v2 `recovery_authorization` receipts use nested schema 2", contract_text)
        self.assertIn("mixed, missing, extra, PRD-mode, ambiguous, or tampered", contract_text)

    def test_skill_contract_enforces_one_bounded_scope_and_sufficiency_invariant(self) -> None:
        skill_root = Path(__file__).resolve().parents[1]
        skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        contract_text = (
            skill_root / "references" / "specification-contract.md"
        ).read_text(encoding="utf-8")
        openai_yaml = (skill_root / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        )

        self.assertEqual(1, contract_text.count("## Scope and sufficiency invariant"))
        for role in ("Director", "Generator", "Technical Spec Architect", "Proofreader"):
            self.assertIn(role, contract_text)
        for required_rule in (
            "exact approved PRD is the complete product scope",
            "concrete current-project evidence",
            "smallest required resolution",
            "Theoretical, unlikely, low-probability, or rare risks",
            "current supported path",
            "Apply KISS and YAGNI in both directions",
            "Stop and pass as soon as every mandatory PRD behavior",
            "no blocking admissible finding remains",
            "Return no optional suggestions or backlog",
            "Any missing mandatory behavior or design text is Major",
        ):
            self.assertIn(required_rule, contract_text)

        self.assertIn("scope and sufficiency invariant", skill_text)
        self.assertIn("includes this invariant in every internal worker packet", skill_text)
        self.assertIn("does not judge its semantic satisfaction", skill_text)
        self.assertIn("route it without judging semantic sufficiency", contract_text)
        self.assertNotIn("reject worker output that violates it", contract_text)
        self.assertIn("Apply KISS/YAGNI", openai_yaml)
        self.assertIn("stop when mandatory coverage", openai_yaml)
        self.assertIn("minimal sufficient design", openai_yaml)
        self.assertIn("theoretical or optional improvements", openai_yaml)

    def test_generator_requires_specification_pipeline_with_exact_bindings(self) -> None:
        skill_root = Path(__file__).resolve().parents[1]
        skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        contract_text = (
            skill_root / "references" / "specification-contract.md"
        ).read_text(encoding="utf-8")
        openai_yaml = (skill_root / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        )

        for text in (skill_text, contract_text):
            self.assertIn("$skill-specification-pipeline", text)
            self.assertIn("prepare-helper --operation generation", text)
            self.assertIn("GAMEDEV_HELPER_REQUEST_PATH", text)
            self.assertIn("GAMEDEV_SPECIFICATION_CONTROLLER_PATH", text)
            self.assertIn("path and SHA-256", text)
            for binding in (
                "`TARGET_OPERATION`",
                "`SPECIFICATION_PATH`",
            ):
                self.assertIn(binding, text)
            self.assertIn("approved PRD", text)
            self.assertIn("PRD-language", text)
            self.assertIn("external", text)
            self.assertIn("local", text)
            self.assertIn("fallback", text)

        for required_prompt_fragment in (
            "actual external $skill-specification-pipeline",
            "prepare-helper --operation generation",
            "GAMEDEV_HELPER_REQUEST_PATH",
            "request-bound resolved GAMEDEV_SPECIFICATION_CONTROLLER_PATH/SHA",
            "TARGET_OPERATION, SPECIFICATION_PATH",
            "approved PRD path/revision/SHA",
            "PRD-language USER_REQUEST",
            "MUST NOT bypass or locally replace it",
        ):
            self.assertIn(required_prompt_fragment, openai_yaml)

        banned_wording = (
            "Do not invoke " + "`$skill-specification-pipeline`",
            "Never invoke " + "$skill-specification-pipeline",
            "bounded local Generator as the only generation path",
            "mandatory generic passes cannot be constrained",
            "may optionally use " + "`$skill-specification-pipeline`",
        )
        for text in (skill_text, contract_text, openai_yaml):
            for banned in banned_wording:
                self.assertNotIn(banned, text)

    def test_generator_integration_contract_rejects_weakening_mutations(self) -> None:
        skill_root = Path(__file__).resolve().parents[1]
        contract_text = (
            skill_root / "references" / "specification-contract.md"
        ).read_text(encoding="utf-8")

        strict_clauses = (
            "The Generator MUST invoke `$skill-specification-pipeline` in `spec-generator` mode as the mandatory and only generation engine and MUST NOT bypass it.",
            "prepare-helper --operation generation",
            "`GAMEDEV_HELPER_REQUEST_PATH`",
            "The external helper retains sole ownership of its mandatory stages, passes, mode routing, and global not-applicable policy",
            "MUST NOT skip, duplicate, parse, normalize, or locally reimplement that topology",
            "`USER_REQUEST`: a complete generation request that must be authored entirely in the approved PRD language",
            "the helper-derived `USER_LANGUAGE` must exactly match the approved PRD language",
            "the exact resolved absolute current GameDev controller path and SHA-256",
            "one exact positive integer revision",
            "`status: draft|approved`",
            "language equal to the request-bound approved PRD language",
            "Director runs `record-helper-result`",
            "The Director does not author the result, parse detailed stage/pass topology or coverage content",
            "The same persistent Technical Spec Architect then performs the read-only pre-accept semantic assessment",
            "prepare-helper --operation correction",
            "same external `$skill-specification-pipeline`",
            "`TARGET_OPERATION=continue`",
            "PRD-language explicit write/apply request authorizing only those corrections",
            "`spec-assistant -> fragment-capture`",
            "runs `record-helper-result` before returning the new SHA to the same persistent Architect",
            "Any SHA drift fails closed: do not apply the packet, rebind the current SHA, and require the same Architect to reassess before issuing a replacement packet.",
            "No Proofreader credit exists before acceptance.",
            "no local fallback or Director-authored helper result is allowed",
        )

        def is_strict(text: str) -> bool:
            return all(clause in text for clause in strict_clauses)

        for clause in strict_clauses:
            self.assertIn(clause, contract_text, clause)
        weakening_mutations = {
            "must-to-may": contract_text.replace(
                "The Generator MUST invoke", "The Generator may invoke", 1
            ),
            "mandatory-to-optional": contract_text.replace(
                "the mandatory and only generation engine",
                "an optional generation helper",
                1,
            ),
            "request-bypass": contract_text.replace(
                "prepare-helper --operation generation",
                "generate without controller request",
            ),
            "wrapper-owns-topology": contract_text.replace(
                "MUST NOT skip, duplicate, parse, normalize, or locally reimplement that topology",
                "may locally normalize helper passes",
                1,
            ),
            "director-authors-result": contract_text.replace(
                "The Director does not author the result, parse detailed stage/pass topology or coverage content",
                "The Director authors and parses the result",
                1,
            ),
            "language-is-optional": contract_text.replace(
                "must be authored entirely in the approved PRD language",
                "may be authored in any language",
                1,
            ),
            "architect-is-bypassed": contract_text.replace(
                "The same persistent Technical Spec Architect then performs the read-only pre-accept semantic assessment",
                "A temporary reviewer may perform the semantic assessment",
                1,
            ),
            "correction-regenerates": contract_text.replace(
                "`TARGET_OPERATION=continue`",
                "`TARGET_OPERATION=new`",
                1,
            ),
            "correction-route-bypass": contract_text.replace(
                "`spec-assistant -> fragment-capture`",
                "The helper may repeat `spec-generator`.",
            ),
            "correction-without-write-verb": contract_text.replace(
                "PRD-language explicit write/apply request authorizing only those corrections",
                "contain a review-only request",
                1,
            ),
            "correction-without-sha-evidence": contract_text.replace(
                "runs `record-helper-result` before returning the new SHA to the same persistent Architect",
                "It returns a completion summary.",
                1,
            ),
            "sha-drift-is-ignored": contract_text.replace(
                "Any SHA drift fails closed: do not apply the packet, rebind the current SHA, and require the same Architect to reassess before issuing a replacement packet.",
                "SHA drift may be ignored for a small correction.",
                1,
            ),
            "local-fallback": contract_text.replace(
                "no local fallback or Director-authored helper result is allowed",
                "The Generator may use a local generation fallback.",
                1,
            ),
        }
        for mutation_name, mutated_text in weakening_mutations.items():
            self.assertFalse(is_strict(mutated_text), mutation_name)

    def test_external_helper_solely_owns_pass_topology_and_na_policy(self) -> None:
        skill_root = Path(__file__).resolve().parents[1]
        skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        contract_text = (
            skill_root / "references" / "specification-contract.md"
        ).read_text(encoding="utf-8")
        openai_yaml = (skill_root / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        )

        for text in (skill_text, contract_text, openai_yaml):
            self.assertIn("external", text.casefold())
            self.assertIn("stage", text.casefold())
            self.assertIn("pass", text.casefold())
            self.assertIn("not-applicable", text.casefold())
        self.assertIn("sole ownership", skill_text)
        self.assertIn("sole ownership", contract_text)
        self.assertIn("MUST NOT skip, duplicate, parse, normalize", skill_text)
        self.assertIn("MUST NOT skip, duplicate, parse, normalize", contract_text)
        self.assertIn("MUST NOT author the helper result", openai_yaml)
        self.assertIn("MUST NOT author the helper result", openai_yaml)
        for forbidden in (
            "GENERATOR_STAGES",
            "GENERATOR_PASSES",
            "FRAGMENT_PASSES",
            "PASS-003",
            "PASS-011",
            "PASS-006",
        ):
            self.assertNotIn(forbidden, skill_text)
            self.assertNotIn(forbidden, contract_text)
            self.assertNotIn(forbidden, openai_yaml)

    def test_director_architect_preaccept_ownership_and_output_validation(self) -> None:
        skill_root = Path(__file__).resolve().parents[1]
        skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        contract_text = (
            skill_root / "references" / "specification-contract.md"
        ).read_text(encoding="utf-8")
        openai_yaml = (skill_root / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        )

        for text in (skill_text, contract_text):
            for mechanical_check in (
                "prepare-helper --operation generation",
                "GAMEDEV_HELPER_REQUEST_PATH",
                "record-helper-result",
                "output SHA",
                "helper fingerprints",
                "--preaccept-receipt",
                "controller",
            ):
                self.assertIn(mechanical_check, text)
            self.assertIn("Director", text)
            self.assertIn("author the result", text)
            self.assertIn("same persistent", text)
            self.assertIn("pre-accept semantic assessment", text)
            for rejection in (
                "exact enumerated correction packet",
                "external `$skill-specification-pipeline`",
                "specification-helper integration error",
            ):
                self.assertIn(rejection, text)
            self.assertIn("local", text)
            self.assertIn("fallback", text)
            self.assertIn("Proofreader credit", text)
            self.assertIn("Proofreader credit exists", text)
        for rejection in (
            "unsupported obligation/system",
            "output scaffolding",
            "boilerplate",
            "speculative OQ/risk",
            "missing semantic coverage",
            "non-minimal design",
        ):
            self.assertIn(rejection, contract_text)
        self.assertIn(
            "request/result/output SHAs",
            openai_yaml,
        )
        self.assertIn("persistent Architect performs pre-accept semantic assessment", openai_yaml)
        self.assertIn("No Proofreader credit exists before acceptance", openai_yaml)

    def test_preaccept_section_inventory_gate_rejects_weakening_mutations(self) -> None:
        skill_root = Path(__file__).resolve().parents[1]
        skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        contract_text = (
            skill_root / "references" / "specification-contract.md"
        ).read_text(encoding="utf-8")
        openai_yaml = (skill_root / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        )

        strict_clauses = (
            "`accept-spec --preaccept-receipt <in-project-json>`",
            "exact UTF-8 JSON object with `schema: 1`",
            "Architect identity must equal the controller's persistent Architect",
            "PRD/spec hashes must match current immutable bytes",
            "`semantic_assessment` must be exact `accept`",
            "controller mechanically derives locators",
            "inventory must cover that exact locator set once",
            "Every row has exactly non-blank `locator`, exact `disposition: retain`, and non-blank `authority_or_rationale`",
            "`reject`, `remove`, `merge`, `defer`",
            "fails closed without controller-state mutation",
            "stores Architect receipt path, exact-byte SHA, and normalized inventory summary",
            "revalidates them with the helper chain before later transitions",
            "new Architect receipt bound to the resulting SHA",
        )

        def is_strict(text: str) -> bool:
            return all(clause in text for clause in strict_clauses)

        self.assertTrue(is_strict(contract_text))
        weakening_mutations = {
            "must-to-may": contract_text.replace(
                "`semantic_assessment` must be exact `accept`",
                "`semantic_assessment` may be `accept`",
                1,
            ),
            "inventory-omitted": contract_text.replace(
                "inventory must cover that exact locator set once",
                "inventory may cover some locators",
                1,
            ),
            "stale-sha-allowed": contract_text.replace(
                "PRD/spec hashes must match current immutable bytes",
                "PRD/spec hashes may be stale",
                1,
            ),
            "blank-inventory-allowed": contract_text.replace(
                "`reject`, `remove`, `merge`, `defer`",
                "Only `reject` blocks",
                1,
            ),
            "blank-row-allowed": contract_text.replace(
                "Every row has exactly non-blank `locator`, exact `disposition: retain`, and non-blank `authority_or_rationale`",
                "Every row may omit `authority_or_rationale`",
                1,
            ),
            "rejection-can-accept": contract_text.replace(
                "new Architect receipt bound to the resulting SHA",
                "old Architect receipt may be reused",
                1,
            ),
        }
        for mutation_name, mutated_text in weakening_mutations.items():
            self.assertFalse(is_strict(mutated_text), mutation_name)

        for prompt_rule in (
            "exact-SHA non-empty section-applicability/minimality inventory",
            "covering every top-level section plus standalone diagram, table, hierarchy description, and footer block",
            "accept-spec takes only --preaccept-receipt",
            "requires the consumed helper chain to end at the current SHA",
        ):
            self.assertIn(prompt_rule, openai_yaml)
        self.assertIn("section-applicability/minimality inventory", skill_text)
        self.assertIn("mechanically rejects a missing, stale-SHA, or blank inventory", skill_text)

    def test_preaccept_minimality_inventory_covers_formatter_counterexample_and_valid_sections(
        self,
    ) -> None:
        skill_root = Path(__file__).resolve().parents[1]
        contract_text = (
            skill_root / "references" / "specification-contract.md"
        ).read_text(encoding="utf-8")

        formatter_style_counterexample = {
            "Data Models": (
                "No structured model, configuration, persisted state, or runtime state "
                "is introduced; table lists scalar totalSeconds and return value."
            ),
            "System Diagram": (
                "supported totalSeconds -> RoundTimeFormatter.format -> M:SS repeats "
                "the decomposition and formatting flow."
            ),
            "Open Questions": "None.",
            "Footer": "No assumptions, source conflicts, unresolved risks, or additional obligations.",
        }
        expected_disposition = {name: "reject" for name in formatter_style_counterexample}
        self.assertEqual(
            {
                "Data Models": "reject",
                "System Diagram": "reject",
                "Open Questions": "reject",
                "Footer": "reject",
            },
            expected_disposition,
        )
        for required_counterexample_rule in (
            "Formatter-style counterexamples",
            "an absent-topic section whose only substance is `none`, `not applicable`, `no data`, or equivalent",
            "component hierarchy or diagram that duplicates another prose or diagram description without conveying distinct PRD-backed behavior",
            "an empty Open Questions, Assumptions, or Risks section, including a footer carrying only the empty declaration",
            'a generic scalar "data model" table when the approved PRD requires no data, configuration, or persistence model',
            "MUST use `reject` and an enumerated remove-or-merge correction",
        ):
            self.assertIn(required_counterexample_rule, contract_text)

        valid_prd_backed_sections = {
            "Data Models": "defines a PRD-required persisted schema",
            "Open Questions or Risks": "concrete unresolved blocker on a named PRD path",
            "Hierarchy or Diagram": (
                "exposes distinct PRD-required interaction or ownership behavior"
            ),
        }
        for distinct_authority in valid_prd_backed_sections.values():
            self.assertIn(distinct_authority, contract_text)
        self.assertIn(
            "These section kinds are not categorically forbidden.", contract_text
        )
        self.assertIn(
            "completion of a pass never requires the assembled specification to retain an empty or generic section",
            contract_text,
        )

    def test_architect_correction_loop_uses_fragment_capture_with_sha_guard(self) -> None:
        skill_root = Path(__file__).resolve().parents[1]
        skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        contract_text = (
            skill_root / "references" / "specification-contract.md"
        ).read_text(encoding="utf-8")
        openai_yaml = (skill_root / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        )

        for text in (skill_text, contract_text):
            for correction_rule in (
                "exact enumerated correction packet",
                "through the Director",
                "$skill-specification-pipeline",
                "prepare-helper --operation correction",
                "GAMEDEV_HELPER_REQUEST_PATH",
                "`TARGET_OPERATION=continue`",
                "same exact `SPECIFICATION_PATH`",
                "SHA",
                "PRD-language",
                "explicit write/apply",
                "`spec-assistant -> fragment-capture`",
                "record-helper-result",
                "same persistent Architect",
                "SHA drift",
                "fail closed",
            ):
                self.assertIn(correction_rule, text)

        for prompt_rule in (
            "prepare-helper --operation correction",
            "every correction ID",
            "same external skill through spec-assistant -> fragment-capture",
            "exact current/prewrite SHA",
            "record-helper-result",
            "Any drift",
        ):
            self.assertIn(prompt_rule, openai_yaml)

    def test_engineer_resolvable_minor_contract_matches_controller_readiness(self) -> None:
        skill_root = Path(__file__).resolve().parents[1]
        skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        contract_text = (
            skill_root / "references" / "specification-contract.md"
        ).read_text(encoding="utf-8")
        openai_yaml = (skill_root / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        )

        for required_rule in (
            "concrete, non-blocking local implementation detail",
            "already inside the approved design",
            "without changing specification bytes",
            "product meaning, system or public boundaries, or design complexity",
            "not a specification omission, improvement, suggestion, or backlog item",
            "requires Architect revision before readiness",
        ):
            self.assertIn(required_rule, contract_text)
        self.assertIn("no blocking admissible finding remains", skill_text)
        self.assertIn("Engineer-resolvable Minor", skill_text)
        self.assertIn("No Proofreader credit exists before acceptance", openai_yaml)


if __name__ == "__main__":
    unittest.main()
