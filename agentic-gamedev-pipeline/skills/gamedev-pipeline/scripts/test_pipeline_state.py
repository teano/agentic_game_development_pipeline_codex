#!/usr/bin/env python3
"""Schema-10 controller tests with exact role artifacts and verification boundaries."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path


SCRIPT = Path(__file__).with_name("pipeline_state.py")
FEATURE = "teleport-module"
sys.path.insert(0, str(SCRIPT.parent))
MODULE_SPEC = importlib.util.spec_from_file_location("pipeline_state_tested", SCRIPT)
assert MODULE_SPEC and MODULE_SPEC.loader
runtime_controller = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(runtime_controller)


class PipelineSchema9Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.docs = self.root / "docs" / "features" / FEATURE
        self.docs.mkdir(parents=True)
        self.prd = self.docs / "product-requirements.md"
        self.spec = self.docs / "technical-specification.md"
        self.plan = self.docs / "development-plan.md"
        self.ledger = self.docs / "decision-ledger.jsonl"
        self.src = self.root / "src" / "feature.py"
        self.test_source = self.root / "project_tests" / "test_feature.py"
        self.src.parent.mkdir(parents=True)
        self.test_source.parent.mkdir(parents=True)
        self.src.write_text("VALUE = 0\n", encoding="utf-8")
        self.test_source.write_text("def test_feature(): assert True\n", encoding="utf-8")
        self.optional_manual_identities: list[dict] = []
        self.prd.write_text(
            "---\n"
            "document_type: product-requirements\n"
            "status: approved\n"
            "revision: 1\n"
            "language: English\n"
            "approved_at: 2026-08-11T00:00:00+00:00\n"
            "---\n"
            "# Product Requirements\n\n"
            "## Product Outcome\n\nPlayable teleport outcome.\n\n"
            "## Target Audience\n\nFeature players.\n\n"
            "## Core Gameplay Loop\n\nStart, teleport, and observe the result.\n\n"
            "## Release Target\n\nOne production-ready vertical slice.\n\n"
            "## Scope\n\n### In Scope\n\nThe approved teleport feature.\n\n"
            "### Out of Scope\n\nUnrelated systems.\n\n"
            "## Functional Requirements\n\n- PRD-REQ-001: The feature teleports.\n\n"
            "## Quality Requirements\n\n- PRD-NFR-001: Verification is deterministic.\n\n"
            "## Acceptance Criteria\n\n"
            "- PRD-AC-001: approved criterion\n"
            "\n## Assumptions\n\nThe project baseline is available.\n\n"
            "## Open Questions\n\nNone.\n\n"
            "## Risks\n\nShared integration drift.\n",
            encoding="utf-8",
        )
        self.spec.write_text(
            "---\n"
            "document_type: technical-specification\n"
            "status: approved\n"
            "revision: 1\n"
            "product_authority:\n"
            f"  path: {self.rel(self.prd)}\n"
            "  revision: 1\n"
            f"  sha256: {self.sha(self.prd)}\n"
            "---\n"
            "# Specification\n\nPRD-REQ-001\nPRD-AC-001\n",
            encoding="utf-8",
        )
        self.write_plan()
        self.write_planning_state()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    @staticmethod
    def sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def write_plan(self) -> None:
        self.plan.write_text(
            "---\n"
            "document_type: development-plan\n"
            "status: approved\n"
            "revision: 1\n"
            f"feature: {FEATURE}\n"
            "mode: single_owner\n"
            "writer_strategy: sequential\n"
            "planning_analyst_id: analyst-1\n"
            "product_authority:\n"
            f"  path: {self.rel(self.prd)}\n"
            "  revision: 1\n"
            f"  sha256: {self.sha(self.prd)}\n"
            "specification_authority:\n"
            f"  path: {self.rel(self.spec)}\n"
            "  revision: 1\n"
            f"  sha256: {self.sha(self.spec)}\n"
            f"decision_ledger_path: {self.rel(self.ledger)}\n"
            "slice_count: 1\n"
            "approved_by: user\n"
            "approved_at: 2026-08-11T00:00:00+00:00\n"
            "---\n\n"
            "# Development Plan\n\n"
            "## Decision\n\n"
            "Writer sequencing: one-at-a-time\n"
            "Ownership meaning: phase-scoped write lease\n\n"
            "## Planning Analysis\n\n"
            "One bounded implementation slice covers the approved vertical behavior.\n\n"
            "## Scope Boundaries\n\n"
            "Only PRD-REQ-001, PRD-AC-001, and the declared paths are approved.\n\n"
            "## Decision Ledger\n\n"
            f"- path: {self.rel(self.ledger)}\n"
            "- active_ids: none\n"
            "- route: Decision Recorder\n\n"
            "## Coverage Strategy\n\n"
            f"- manifest_path: tests/{FEATURE}/verification/coverage-schema2.json\n"
            "- automated_identity_namespace: AUTO-*\n"
            "- manual_identity_namespace: MANUAL-*\n"
            "- mandatory_rule: PRD-AC-001 and both declared identities\n"
            "- automation_feasibility: deterministic logic automated; runtime topology manual\n"
            "- capability_prerequisites: test-server-two-clients\n"
            "- gates: plan-before-engineering, finalize-after-code-freeze, qa-updated\n\n"
            "## Documentation Strategy\n\n"
            "- normative_pre_review: not_required | policy=POLICY-DOC-NONE\n"
            "- derived_post_qa: not_required | policy=POLICY-DOC-NONE\n"
            "- source_rule: active decisions and exact verified evidence only\n\n"
            "## Context Budget\n\n"
            "- max_authority_files: 5\n"
            "- max_evidence_files: 12\n"
            "- max_total_files: 20\n"
            "- max_payload_bytes: 500000\n"
            "- max_estimated_tokens: 200000\n"
            "- metric_scope: capsule_plus_referenced_files\n"
            "- estimation_recipe: exact UTF-8 bytes divided by four\n\n"
            "## Integration Milestones\n\n"
            "- MILESTONE-001: exact slice implementation and evidence closure.\n\n"
            "## Slice SLICE-001\n\n"
            "### Vertical Outcome\n\nEnd-to-end: yes\nObservable result: approved feature behavior is verified.\n\n"
            "### Requirements\n\n- PRD-REQ-001\n- PRD-AC-001\n\n"
            "### Dependencies\n\n- none\n\n"
            "### Base Contract\n\nExact controller revision and approved authority hashes.\n\n"
            "### Handoff Contract\n\n"
            "Controller schema-2 decision_ids coverage_state documentation_state open_assumptions.\n\n"
            "### Owned Paths\n\n- src/feature.py\n\n"
            "### Expected Paths\n\n- project_tests/test_feature.py\n\n"
            "### Forbidden Scope\n\n- src/commerce/**\n\n"
            "### Scope Contract\n\n"
            "- acceptance_ids: PRD-AC-001\n"
            "- editable_paths: src/feature.py\n"
            "- shared_touchpoints: see rows\n"
            "- shared_touchpoint: TP-001 | path=src/contracts.py | symbols=FeatureContract | allowed_change=additive contract | forbidden_change=lifecycle, ownership, removals\n"
            "- excluded_components: commerce\n"
            "- excluded_paths: src/commerce/**\n"
            "- max_product_files: 4\n"
            "- max_product_lines_changed: 200\n"
            "- verification_scope: project_tests/test_feature.py and runtime identity\n"
            "\n"
            "### Research Briefs\n\n"
            "- RESEARCH-001 | question=confirm exact edit surface | paths=src/feature.py | exclusions=src/commerce/** | evidence=approved spec | stop=scope is exact\n\n"
            "### Coverage Contract\n\n"
            "- acceptance_ids: PRD-AC-001\n"
            "- automated_identity_namespace: AUTO-SLICE-001-*\n"
            "- manual_identity_namespace: MANUAL-SLICE-001-*\n"
            "- mandatory_identity_ids: AUTO-SLICE-001-CORE, MANUAL-SLICE-001-RUNTIME\n"
            "- automation_feasibility: automated core plus manual runtime topology\n"
            "- capability_prerequisites: test-server-two-clients\n"
            f"- planned_manifest: tests/{FEATURE}/verification/coverage-planned.json\n"
            f"- finalized_manifest: tests/{FEATURE}/verification/coverage-final.json\n"
            "- amendment_authorities: accepted DEC-* only\n\n"
            "### Documentation Contract\n\n"
            "- normative_pre_review_paths: not_required | policy=POLICY-DOC-NONE\n"
            "- derived_post_qa_paths: not_required | policy=POLICY-DOC-NONE\n"
            "- decision_ids: none\n"
            "- evidence_sources: exact controller and QA artifacts\n\n"
            "### Context Capsule Budget\n\n"
            "- max_authority_files: 5\n"
            "- max_evidence_files: 12\n"
            "- max_total_files: 20\n"
            "- max_payload_bytes: 500000\n"
            "- max_estimated_tokens: 200000\n"
            "- metric_scope: capsule_plus_referenced_files\n"
            "- authority_paths: docs/features/**\n"
            f"- evidence_paths: tests/{FEATURE}/**\n\n"
            "### Verification and Exit Criteria\n\nExact schema-2 equality and mandatory automated PASS.\n\n"
            "### Rollback and Recovery\n\nRestore the exact controller base revision.\n\n"
            "### Downstream Consumers\n\nFinal Review, QA, and documentation closure.\n",
            encoding="utf-8",
        )

    def refresh_spec_plan_and_state_for_current_prd(self) -> None:
        self.spec.write_text(
            "---\n"
            "document_type: technical-specification\n"
            "status: approved\n"
            "revision: 1\n"
            "product_authority:\n"
            f"  path: {self.rel(self.prd)}\n"
            "  revision: 1\n"
            f"  sha256: {self.sha(self.prd)}\n"
            "---\n"
            "# Specification\n\nPRD-REQ-001\nPRD-AC-001\n",
            encoding="utf-8",
        )
        self.write_plan()
        self.write_planning_state()

    def write_planning_state(self) -> None:
        state_root = self.root / ".agentic-pipeline"
        state_root.mkdir(parents=True, exist_ok=True)
        (state_root / "specification-state.json").write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "feature": FEATURE,
                    "status": "spec_ready",
                    "prd": {"path": self.rel(self.prd)},
                    "specification": {"path": self.rel(self.spec)},
                    "ready": {
                        "prd_sha256": self.sha(self.prd),
                        "spec_sha256": self.sha(self.spec),
                    },
                }
            ),
            encoding="utf-8",
        )
        path = state_root / "development-plan-state.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "feature": FEATURE,
                    "status": "approved",
                    "analyst_id": "analyst-1",
                    "plan_path": self.rel(self.plan),
                    "decision_ledger_path": self.rel(self.ledger),
                    "prd": {
                        "path": self.rel(self.prd),
                        "revision": "1",
                        "sha256": self.sha(self.prd),
                    },
                    "specification": {
                        "path": self.rel(self.spec),
                        "revision": "1",
                        "sha256": self.sha(self.spec),
                    },
                    "analysis": {"mode": "single_owner"},
                    "approval": {"approved_sha256": self.sha(self.plan)},
                }
            ),
            encoding="utf-8",
        )

    def cli(self, *args: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *args, "--project-root", str(self.root)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(expected, result.returncode, result.stderr or result.stdout)
        return result

    def state(self) -> dict:
        return json.loads(
            (self.root / ".agentic-pipeline" / "state.json").read_text(encoding="utf-8")
        )

    def inject_canonical_finding(self, finding: dict) -> tuple[Path, dict]:
        _, state_path, findings_path, state, findings = runtime_controller.load_runtime(
            str(self.root)
        )
        findings["items"].append(finding)
        runtime_controller.save_runtime(state_path, findings_path, state, findings)
        return findings_path, findings

    def full_status(self) -> dict:
        return json.loads(self.cli("status", "--full").stdout)

    def artifact(self, area: str, name: str, value: dict | None = None) -> str:
        path = self.root / "tests" / FEATURE / area / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        if value is None and name.endswith("engineer-report"):
            value = {"name": name, **self.dirty_candidate_report()}
        path.write_text(json.dumps(value or {"name": name}), encoding="utf-8")
        return self.rel(path)

    def dirty_candidate_report(self) -> dict:
        state = self.state()
        lease = state["active_write_lease"]
        candidate = runtime_controller.checkout_snapshot(self.root, FEATURE, state)
        digest = runtime_controller.checkout_snapshot_sha256(candidate)
        return {
            "dirty_candidate_gate": {
                "schema": 1,
                "lease_id": lease["lease_id"],
                "base_revision": lease["base_revision"],
                "candidate_before_sha256": digest,
                "candidate_after_sha256": digest,
                "outcome": "pass",
                "tool": "project-test-runner",
            }
        }

    def research_bundle(self, name: str = "research-valid", **brief_updates) -> str:
        relative = f"tests/{FEATURE}/research/{name}.json"
        brief = {
            "brief_id": "RESEARCH-001",
            "question": "confirm exact edit surface",
            "slice_id": "SLICE-001",
            "base_revision": self.state()["revision"],
            "requirement_ids": ["PRD-REQ-001", "PRD-AC-001"],
            "seed_paths": ["src/feature.py"],
            "allowed_paths": ["src"],
            "allowed_symbols": ["VALUE"],
            "exclusions": ["src/commerce/**"],
            "requested_evidence": ["approved spec"],
            "max_files": 1,
            "stop_condition": "scope is exact",
            "output_path": relative,
        }
        brief.update(brief_updates)
        result = {
            "brief_id": brief["brief_id"],
            "researcher_id": "researcher-1",
            "base_revision": brief["base_revision"],
            "brief_sha256": runtime_controller.canonical_json_sha256(brief),
            "status": "complete",
            "inspected_paths": ["src/feature.py"],
            "inspected_symbols": ["VALUE"],
            "owners_contracts_precedents": ["Feature module owns VALUE."],
            "lifecycle_integration_risks": [],
            "minimal_edit_reuse_points": ["Reuse VALUE."],
            "unresolved_questions": [],
            "out_of_brief_pointers": [],
        }
        return self.artifact("research", name, {"schema_version": 1, "brief": brief, "result": result})

    def initialize(self, *, research: bool = True, base_revision: str = "base-0") -> dict:
        if research:
            required = "- RESEARCH-001 | question=confirm exact edit surface | paths=src/feature.py | exclusions=src/commerce/** | evidence=approved spec | stop=scope is exact"
            sentinel = "- research_not_required | reason=Exact authority and edit files answer the bounded question"
            text = self.plan.read_text(encoding="utf-8")
            if required in text:
                self.plan.write_text(text.replace(required, sentinel), encoding="utf-8")
                self.write_planning_state()
        self.cli(
            "init",
            "--feature",
            FEATURE,
            "--requirements",
            self.rel(self.prd),
            "--spec",
            self.rel(self.spec),
            "--plan",
            self.rel(self.plan),
            "--plan-sha256",
            self.sha(self.plan),
            "--base-revision",
            base_revision,
            "--decision-ledger",
            self.rel(self.ledger),
            "--integration-owner",
            "engineer-1",
        )
        self.complete_preflight("preflight-1")
        if research:
            state = self.state()
            self.cli(
                "slice-research-not-required",
                "--slice-id",
                "SLICE-001",
                "--base-revision",
                state["revision"],
                "--reason",
                "Exact authority and edit files answer the bounded question",
            )
        return self.state()

    def test_research_bundle_direct_validator_binds_ids_and_path_types(self) -> None:
        state = self.initialize(research=False)
        valid = self.research_bundle()
        record = runtime_controller.resolve_research_bundle(
            self.root, state, valid, slice_id="SLICE-001", base_revision=state["revision"]
        )
        self.assertEqual("RESEARCH-001", record["brief_id"])

        invalid = self.research_bundle(
            "research-invalid-id", requirement_ids=["REQ-001", "AC-001"]
        )
        with self.assertRaisesRegex(runtime_controller.PipelineError, "PRD-REQ/PRD-AC subset"):
            runtime_controller.resolve_research_bundle(
                self.root, state, invalid, slice_id="SLICE-001", base_revision=state["revision"]
            )

        invalid_path = self.research_bundle(
            "research-invalid-path", seed_paths=["src"]
        )
        with self.assertRaisesRegex(runtime_controller.PipelineError, "seed_path.*file"):
            runtime_controller.resolve_research_bundle(
                self.root, state, invalid_path, slice_id="SLICE-001", base_revision=state["revision"]
            )

    def test_research_bundle_cli_accepts_exact_active_slice_contract(self) -> None:
        state = self.initialize(research=False)
        research_contract = state["plan_contracts"]["slices"]["SLICE-001"]["research"]
        self.assertEqual("required", research_contract["mode"])
        self.assertEqual(
            ["RESEARCH-001"],
            [item["brief_id"] for item in research_contract["briefs"]],
        )
        blocked = self.cli(
            "slice-research-not-required", "--slice-id", "SLICE-001",
            "--base-revision", state["revision"],
            "--reason", "Exact authority and edit files answer the bounded question",
            expected=2,
        )
        self.assertIn("requires exact Research Brief", blocked.stderr)
        bundle = self.research_bundle("research-cli")
        result = self.cli(
            "slice-research-complete", "--slice-id", "SLICE-001",
            "--base-revision", state["revision"], "--owner-id", "engineer-1",
            "--bundle", bundle,
        )
        self.assertIn('"phase": "slice_coverage_planning"', result.stdout)

    def test_research_bundle_rejects_unapproved_plan_selector(self) -> None:
        state = self.initialize(research=False)
        bundle = self.research_bundle("research-unapproved", brief_id="RESEARCH-002")
        result = self.cli(
            "slice-research-complete", "--slice-id", "SLICE-001",
            "--base-revision", state["revision"], "--owner-id", "engineer-1",
            "--bundle", bundle, expected=2,
        )
        self.assertIn("not approved by the exact development plan", result.stderr)

    def test_research_not_required_reason_is_copied_from_plan(self) -> None:
        state = self.initialize()
        research_contract = state["plan_contracts"]["slices"]["SLICE-001"]["research"]
        self.assertEqual(
            {
                "mode": "not_required",
                "reason": "Exact authority and edit files answer the bounded question",
            },
            research_contract,
        )
        self.assertEqual(
            research_contract["reason"],
            state["slices"]["SLICE-001"]["research"]["reason"],
        )

    def test_engineer_capsule_binds_accepted_research_bundle_and_selector(self) -> None:
        state = self.initialize(research=False)
        bundle = self.research_bundle("research-capsule")
        self.cli(
            "slice-research-complete", "--slice-id", "SLICE-001",
            "--base-revision", state["revision"], "--owner-id", "engineer-1",
            "--bundle", bundle,
        )
        self.plan_coverage()
        state = self.state()
        capsule_path = self.capsule(
            "engineer", "slice_engineering", "engineer-research",
            allowed=(self.rel(self.src),),
        )
        capsule = json.loads((self.root / capsule_path).read_text(encoding="utf-8"))
        research_ref = next(
            item for item in capsule["evidence"] if item["path"] == bundle
        )
        self.assertEqual(self.sha(self.root / bundle), research_ref["sha256"])
        self.assertEqual(["RESEARCH-001"], research_ref["ids"])

        research_ref["ids"] = []
        capsule["metrics"] = runtime_controller.capsule_metrics(capsule, self.root)
        capsule["capsule_sha256"] = runtime_controller.capsule_digest(capsule)
        with self.assertRaisesRegex(runtime_controller.PipelineError, "evidence selectors"):
            runtime_controller.validate_capsule_value(self.root, state, capsule)

    def complete_preflight(self, run_id: str) -> dict:
        preflight_args = [
            "preflight-complete",
            "--run-id",
            run_id,
            "--resource-budget-check",
            "pass",
            "--report",
            self.artifact("verification", run_id),
        ]
        for name in sorted(
            runtime_controller.required_preflight_capabilities(self.state())
        ):
            preflight_args.extend(("--capability", f"{name}=available"))
        self.cli(*preflight_args)
        return self.state()

    def downgrade_active_snapshot_to_schema9(
        self, lease_id: str, checkout_text: dict | None = None
    ) -> None:
        state_path = self.root / ".agentic-pipeline" / "state.json"
        findings_path = self.root / ".agentic-pipeline" / "findings.json"
        state = self.state()
        snapshot = state["lease_snapshots"][lease_id]
        snapshot["checkout_text"] = checkout_text or {
            relative: (self.root / relative).read_text(encoding="utf-8")
            for relative in snapshot["checkout"]
            if (self.root / relative).is_file()
        }
        snapshot.pop("line_proofs", None)
        snapshot["snapshot_schema"] = 2
        snapshot["snapshot_format"] = "sha256-raw-bytes-v1"
        state["schema_version"] = 9
        state["contract_version"] = runtime_controller.LEGACY_CONTRACT_VERSION
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        findings["schema_version"] = 9
        state_path.write_text(json.dumps(state), encoding="utf-8")
        findings_path.write_text(json.dumps(findings), encoding="utf-8")

    def prepare_authority_recovery(self) -> tuple[dict, str]:
        state = self.state()
        return state, runtime_controller.authority_rebaseline_token(
            state,
            "confirmed pre-engineering authority defect",
            "technical-director-1",
        )

    def freshly_approve_plan_revision(self) -> str:
        plan_text = self.plan.read_text(encoding="utf-8")
        self.plan.write_text(
            plan_text.replace("revision: 1\n", "revision: 2\n", 1).replace(
                "approved_at: 2026-08-11T00:00:00+00:00",
                "approved_at: 2099-08-13T00:00:00+00:00",
            )
            + "\n<!-- approved authority recovery correction -->\n",
            encoding="utf-8",
        )
        planning_path = self.root / ".agentic-pipeline" / "development-plan-state.json"
        planning = json.loads(planning_path.read_text(encoding="utf-8"))
        planning["approval"] = {
            "approved_by": "user",
            "approved_at": "2099-08-13T00:00:00+00:00",
            "approval_note": "fresh exact SHA authority recovery approval",
            "approved_sha256": self.sha(self.plan),
        }
        planning_path.write_text(json.dumps(planning), encoding="utf-8")
        return self.sha(self.plan)

    def test_authority_recovery_plan_metadata_change_preserves_semantic_evidence(self) -> None:
        before = self.initialize()
        before = self.state()
        recovery_state, token = self.prepare_authority_recovery()
        self.assertEqual("slice_coverage_planning", recovery_state["phase"])
        self.assertEqual("not_required", recovery_state["slices"]["SLICE-001"]["research"]["status"])
        new_plan_sha = self.freshly_approve_plan_revision()
        self.cli(
            "rebaseline-authority",
            "--recovery-token",
            token,
            "--reason",
            "confirmed pre-engineering authority defect",
            "--authorized-by",
            "technical-director-1",
            "--requirements",
            self.rel(self.prd),
            "--spec",
            self.rel(self.spec),
            "--plan",
            self.rel(self.plan),
            "--plan-sha256",
            new_plan_sha,
            "--plan-approval-reference",
            "user exact SHA approval in planning controller",
        )
        after = self.state()
        self.assertEqual("slice_coverage_planning", after["phase"])
        self.assertEqual(new_plan_sha, after["development_plan_sha256"])
        self.assertEqual("not_required", after["slices"]["SLICE-001"]["research"]["status"])
        self.assertEqual("complete", after["preflight"]["status"])
        self.assertEqual(before["coverage"]["SLICE-001"], after["coverage"]["SLICE-001"])
        self.assertNotEqual(before["revision"], after["revision"])
        self.assertEqual("authority_rebaseline", after["authority_recovery_history"][-1]["event"])
        self.assertTrue(after["authority_recovery_history"][-1]["semantic_equivalent"])
        active = after["slices"]["SLICE-001"]
        self.assertEqual(after["revision"], active["base_revision"])
        self.assertEqual(after["product_revision"], active["base_product_revision"])
        self.assertEqual(after["support_revision"], active["base_support_revision"])
        self.assertEqual(after["evidence_revision"], active["base_evidence_revision"])

    def test_atomic_authority_recovery_rejects_wrong_token_without_mutation(self) -> None:
        self.initialize()
        _, token = self.prepare_authority_recovery()
        new_plan_sha = self.freshly_approve_plan_revision()
        state_path = self.root / ".agentic-pipeline" / "state.json"
        before_failed_recovery = state_path.read_bytes()
        blocked = self.cli(
            "rebaseline-authority",
            "--recovery-token",
            "ARH-WRONG",
            "--reason",
            "confirmed pre-engineering authority defect",
            "--authorized-by",
            "technical-director-1",
            "--requirements",
            self.rel(self.prd),
            "--spec",
            self.rel(self.spec),
            "--plan",
            self.rel(self.plan),
            "--plan-sha256",
            new_plan_sha,
            "--plan-approval-reference",
            "fresh approval",
            expected=2,
        )
        self.assertIn("does not match", blocked.stderr)
        self.assertEqual(before_failed_recovery, state_path.read_bytes())

    def test_authority_recovery_scope_contract_change_invalidates_only_research(self) -> None:
        self.initialize()
        before = self.state()
        _, token = self.prepare_authority_recovery()
        self.freshly_approve_plan_revision()
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8").replace(
                "- max_product_files: 4", "- max_product_files: 5"
            ),
            encoding="utf-8",
        )
        planning_path = self.root / ".agentic-pipeline" / "development-plan-state.json"
        planning = json.loads(planning_path.read_text(encoding="utf-8"))
        planning["approval"]["approved_sha256"] = self.sha(self.plan)
        planning_path.write_text(json.dumps(planning), encoding="utf-8")
        self.cli(
            "rebaseline-authority",
            "--recovery-token", token,
            "--reason", "confirmed pre-engineering authority defect",
            "--authorized-by", "technical-director-1",
            "--requirements", self.rel(self.prd),
            "--spec", self.rel(self.spec),
            "--plan", self.rel(self.plan),
            "--plan-sha256", self.sha(self.plan),
            "--plan-approval-reference", "user approved exact scope budget",
        )
        after = self.state()
        self.assertEqual("slice_research", after["phase"])
        self.assertEqual("complete", after["preflight"]["status"])
        self.assertEqual("pending", after["slices"]["SLICE-001"]["research"]["status"])
        self.assertEqual(before["coverage"]["SLICE-001"], after["coverage"]["SLICE-001"])

    def test_atomic_authority_recovery_rejects_engineering_phase(self) -> None:
        self.initialize()
        state = self.state()
        token = runtime_controller.authority_rebaseline_token(state, "too late", "director")
        state["phase"] = "slice_engineering"
        (self.root / ".agentic-pipeline" / "state.json").write_text(
            json.dumps(state), encoding="utf-8"
        )
        blocked = self.cli(
            "rebaseline-authority",
            "--recovery-token",
            token,
            "--reason",
            "too late",
            "--authorized-by",
            "director",
            "--requirements",
            self.rel(self.prd),
            "--spec",
            self.rel(self.spec),
            "--plan",
            self.rel(self.plan),
            "--plan-sha256",
            self.sha(self.plan),
            expected=2,
        )
        self.assertIn("legal only", blocked.stderr)

    def test_authority_recovery_same_capability_set_preserves_preflight(self) -> None:
        self.initialize()
        _, token = self.prepare_authority_recovery()
        old_prd_sha = self.sha(self.prd)
        old_spec_sha = self.sha(self.spec)
        self.prd.write_text(
            self.prd.read_text(encoding="utf-8")
            .replace("revision: 1", "revision: 2", 1)
            .replace(
                "approved_at: 2026-08-11T00:00:00+00:00",
                "approved_at: 2099-08-13T00:00:00+00:00",
                1,
            )
            + "\n<!-- approved removal of obsolete device-only authority -->\n",
            encoding="utf-8",
        )
        self.spec.write_text(
            self.spec.read_text(encoding="utf-8")
            .replace("revision: 1", "revision: 2")
            .replace(old_prd_sha, self.sha(self.prd))
            + "\n<!-- exact simulation-based authority reconvergence -->\n",
            encoding="utf-8",
        )
        ready_path = self.root / ".agentic-pipeline" / "specification-state.json"
        ready = json.loads(ready_path.read_text(encoding="utf-8"))
        ready["ready"] = {
            "prd_sha256": self.sha(self.prd),
            "spec_sha256": self.sha(self.spec),
            "confirmed_at": "2099-08-13T00:00:00+00:00",
        }
        ready_path.write_text(json.dumps(ready), encoding="utf-8")
        plan_text = self.plan.read_text(encoding="utf-8")
        self.plan.write_text(
            plan_text.replace("revision: 1", "revision: 2")
            .replace(old_prd_sha, self.sha(self.prd))
            .replace(old_spec_sha, self.sha(self.spec))
            .replace(
                "approved_at: 2026-08-11T00:00:00+00:00",
                "approved_at: 2099-08-13T00:00:00+00:00",
            ),
            encoding="utf-8",
        )
        planning_path = self.root / ".agentic-pipeline" / "development-plan-state.json"
        planning = json.loads(planning_path.read_text(encoding="utf-8"))
        planning["prd"].update(revision="2", sha256=self.sha(self.prd))
        planning["specification"].update(revision="2", sha256=self.sha(self.spec))
        planning["approval"] = {
            "approved_by": "user",
            "approved_at": "2099-08-13T00:00:00+00:00",
            "approval_note": "fresh exact SHA chain approval",
            "approved_sha256": self.sha(self.plan),
        }
        planning_path.write_text(json.dumps(planning), encoding="utf-8")
        self.cli(
            "rebaseline-authority",
            "--recovery-token",
            token,
            "--reason",
            "confirmed pre-engineering authority defect",
            "--authorized-by",
            "technical-director-1",
            "--requirements",
            self.rel(self.prd),
            "--spec",
            self.rel(self.spec),
            "--plan",
            self.rel(self.plan),
            "--plan-sha256",
            self.sha(self.plan),
            "--prd-approval-reference",
            "user approved PRD revision 2",
            "--spec-approval-reference",
            "SPEC_READY exact revision 2",
            "--plan-approval-reference",
            "user approved exact plan SHA",
        )
        state = self.state()
        self.assertEqual("2", state["requirements_revision"])
        self.assertEqual("slice_research", state["phase"])
        self.assertEqual("complete", state["preflight"]["status"])
        event = state["authority_recovery_history"][-1]
        self.assertNotEqual(
            event["old_authority"]["requirements_sha256"],
            event["new_authority"]["requirements_sha256"],
        )
        active = state["slices"]["SLICE-001"]
        self.assertEqual(state["revision"], active["base_revision"])
        self.assertEqual(state["product_revision"], active["base_product_revision"])
        current = self.state()
        self.cli(
            "slice-research-not-required",
            "--slice-id",
            "SLICE-001",
            "--base-revision",
            current["revision"],
            "--reason",
            "Exact authority and edit files answer the bounded question",
        )

    def test_atomic_authority_recovery_from_incomplete_preflight(self) -> None:
        self.cli(
            "init",
            "--feature",
            FEATURE,
            "--requirements",
            self.rel(self.prd),
            "--spec",
            self.rel(self.spec),
            "--plan",
            self.rel(self.plan),
            "--plan-sha256",
            self.sha(self.plan),
            "--base-revision",
            "base-0",
            "--decision-ledger",
            self.rel(self.ledger),
        )
        _, token = self.prepare_authority_recovery()
        status = json.loads(self.cli("status").stdout)
        self.assertEqual("preflight", status["phase"])
        new_plan_sha = self.freshly_approve_plan_revision()
        self.cli(
            "rebaseline-authority",
            "--recovery-token",
            token,
            "--reason",
            "confirmed pre-engineering authority defect",
            "--authorized-by",
            "technical-director-1",
            "--requirements",
            self.rel(self.prd),
            "--spec",
            self.rel(self.spec),
            "--plan",
            self.rel(self.plan),
            "--plan-sha256",
            new_plan_sha,
            "--plan-approval-reference",
            "fresh exact approval from incomplete preflight",
        )
        self.assertEqual("preflight", self.state()["phase"])

    def test_atomic_authority_recovery_rejects_active_writer(self) -> None:
        self.initialize()
        state = self.state()
        token = runtime_controller.authority_rebaseline_token(
            state, "unsafe writer", "director"
        )
        state["active_write_lease"] = {"status": "active", "lease_id": "LEASE-UNSAFE"}
        (self.root / ".agentic-pipeline" / "state.json").write_text(
            json.dumps(state), encoding="utf-8"
        )
        blocked = self.cli(
            "rebaseline-authority",
            "--recovery-token",
            token,
            "--reason",
            "unsafe writer",
            "--authorized-by",
            "director",
            "--requirements",
            self.rel(self.prd),
            "--spec",
            self.rel(self.spec),
            "--plan",
            self.rel(self.plan),
            "--plan-sha256",
            self.sha(self.plan),
            expected=2,
        )
        self.assertIn("write lease is active", blocked.stderr)

    def capsule(
        self,
        role: str,
        phase: str,
        worker: str,
        *,
        allowed: tuple[str, ...] = (),
        evidence: tuple[Path, ...] = (),
        authorities: tuple[str, ...] = (),
        outputs: tuple[str, ...] = (),
        symbols: tuple[str, ...] = (),
        exclusions: tuple[str, ...] = (),
        max_payload: int = 500000,
    ) -> str:
        state = self.state()
        path = f"tests/{FEATURE}/verification/{worker}-{phase}-capsule.json"
        scope_ids = sorted(runtime_controller.capsule_scope_ids(state, phase))
        args = [
            "context-capsule-create",
            "--role",
            role,
            "--phase",
            phase,
            "--worker-id",
            worker,
            "--plan-sha256",
            state["development_plan_sha256"],
            "--revision",
            state["revision"],
            "--stop-condition",
            "Return the assigned schema and stop",
            "--max-authority-files",
            "5",
            "--max-evidence-files",
            "12",
            "--max-total-files",
            "20",
            "--max-payload-bytes",
            str(max_payload),
            "--max-estimated-tokens",
            "200000",
            "--output",
            path,
        ]
        exact_authority = runtime_controller.capsule_exact_authority(
            self.root, state
        )
        requirements_relative = self.rel(self.prd)
        ledger_relative = self.rel(self.ledger)
        for authority_path, authority_sha in sorted(exact_authority.items()):
            ids = (
                []
                if role == "decision_recorder"
                else scope_ids
                if authority_path == requirements_relative
                else state["decision_ledger"]["active_decision_ids"]
                if authority_path == ledger_relative
                else []
            )
            suffix = ":" + ",".join(ids) if ids else ""
            args.extend(
                ("--authority", f"{authority_path}={authority_sha}{suffix}")
            )
        for decision_id in state["decision_ledger"]["active_decision_ids"]:
            args.extend(("--decision-id", decision_id))
        for finding_id in sorted(
            runtime_controller.capsule_expected_finding_ids(
                self.root, state, role, phase
            )
        ):
            args.extend(("--finding-id", finding_id))
        _, coverage_ids = runtime_controller.capsule_manifest_contract(
            self.root, state, phase
        )
        for identity_id in sorted(coverage_ids):
            args.extend(("--coverage-identity-id", identity_id))
        exact_evidence_ids = runtime_controller.capsule_exact_evidence_ids(
            self.root, state, role, phase
        )
        for evidence_path, evidence_sha in sorted(
            runtime_controller.capsule_exact_evidence(
                self.root, state, role, phase
            ).items()
        ):
            ids = exact_evidence_ids[evidence_path]
            suffix = ":" + ",".join(ids) if ids else ""
            args.extend(("--evidence", f"{evidence_path}={evidence_sha}{suffix}"))
        for item in authorities:
            args.extend(("--authority", item))
        for item in outputs or (f"tests/{FEATURE}/verification/{worker}-output.json",):
            args.extend(("--output-path", item))
        for item in allowed:
            args.extend(("--allowed-path", item))
        for item in symbols:
            args.extend(("--allowed-symbol", item))
        for item in exclusions:
            args.extend(("--exclusion", item))
        for item in evidence:
            args.extend(("--evidence", f"{self.rel(item)}={self.sha(item)}"))
        self.cli(*args)
        return path

    def coverage_manifest(self, name: str, mode: str, *, mismatch: bool = False) -> str:
        state = self.state()
        evidence_log = self.root / "tests" / FEATURE / "verification" / f"{name}.log"
        evidence_log.parent.mkdir(parents=True, exist_ok=True)
        evidence_log.write_text("pass\n", encoding="utf-8")
        automated = {
            "identity_id": "AUTO-SLICE-001-CORE",
            "kind": "automated",
            "mandatory": True,
            "slice_id": "SLICE-001",
            "requirement_ids": ["PRD-REQ-001"],
            "acceptance_ids": ["PRD-AC-001"],
            "coordinates": {
                "file": "project_tests/test_feature.py",
                "suite": "FeatureTests",
                "symbol": "test_feature",
                "case": "core",
            },
            "planned_assertion_or_observation": "feature value changes deterministically",
            "capability_prerequisites": [],
        }
        manual = {
            "identity_id": "MANUAL-SLICE-001-RUNTIME",
            "kind": "manual",
            "mandatory": True,
            "slice_id": "SLICE-001",
            "requirement_ids": ["PRD-REQ-001"],
            "acceptance_ids": ["PRD-AC-001"],
            "coordinates": {
                "scenario_id": "MANUAL-SLICE-001-RUNTIME",
                "topology": "server plus two clients",
                "setup": "load exact candidate",
                "action": "exercise feature",
                "observation": "both clients observe the accepted result",
                "evidence_kind": "log and screenshot",
            },
            "planned_assertion_or_observation": "runtime topology matches PRD-AC-001",
            "capability_prerequisites": ["test-server-two-clients"],
        }
        expected = [automated, manual] + json.loads(
            json.dumps(self.optional_manual_identities)
        )
        actual = [] if mode == "planned" else [automated] if mismatch else list(expected)
        mandatory_actual = [item["identity_id"] for item in actual if item["mandatory"]]
        automated_execution = []
        manual_execution = []
        if mode == "finalized":
            automated_execution = [
                {
                    "identity_id": automated["identity_id"],
                    "executed": True,
                    "passed": True,
                    "command": "python -m unittest project_tests.test_feature",
                    "evidence_path": self.rel(evidence_log),
                    "evidence_sha256": self.sha(evidence_log),
                }
            ]
            if not mismatch:
                manual_execution = [
                    {
                        "identity_id": identity["identity_id"],
                        "executed": False,
                        "passed": None,
                        "deferred": False,
                        "blocked_by_finding": None,
                        "qa_evidence": None,
                        "gate": None,
                        "minimum_resume_action": None,
                    }
                    for identity in expected
                    if identity["kind"] == "manual"
                ]
        registration = mode == "finalized" and not mismatch
        summary = {
            "ac_mapped": True,
            "identities_registered": "complete" if registration else "mismatch",
            "expected_count": len(expected),
            "actual_count": len(actual),
            "mandatory_expected_count": 2,
            "mandatory_actual_count": len(mandatory_actual),
            "automated": "passed" if mode == "finalized" else "pending",
            "manual": "pending",
            "implementation_eligible": registration,
            "feature_verification_eligible": False,
        }
        value = {
            "schema": 2,
            "feature": FEATURE,
            "slice_id": "SLICE-001",
            "mode": mode,
            "authority": {
                "plan_path": self.rel(self.plan),
                "plan_sha256": state["development_plan_sha256"],
                "prd_path": self.rel(self.prd),
                "prd_sha256": self.sha(self.prd),
                "spec_path": self.rel(self.spec),
                "spec_sha256": self.sha(self.spec),
            },
            "revisions": {
                "revision": state["revision"],
                "product_revision": state["product_revision"],
                "support_revision": state["support_revision"],
                "evidence_revision": state["evidence_revision"],
            },
            "ac_mappings": [
                {
                    "acceptance_id": "PRD-AC-001",
                    "status": "mapped",
                    "identity_ids": [item["identity_id"] for item in expected],
                    "authority_id": None,
                }
            ],
            "expected_identities": expected,
            "actual_identities": actual,
            "mandatory_expected_identity_ids": [automated["identity_id"], manual["identity_id"]],
            "mandatory_actual_identity_ids": mandatory_actual,
            "automated_execution": automated_execution,
            "manual_execution": manual_execution,
            "amendments": [],
            "gaps": [],
            "summary": summary,
        }
        return self.artifact("verification", name, value)

    def plan_coverage(self) -> None:
        self.cli(
            "coverage-plan-complete",
            "--slice-id",
            "SLICE-001",
            "--coverage-manifest",
            self.coverage_manifest("coverage-planned", "planned"),
            "--report",
            self.artifact("verification", "coverage-plan-report"),
        )

    def engineer(self, *, forbidden_path: bool = False) -> dict:
        self.plan_coverage()
        allowed = ("src/feature.py", "src/commerce/driveby.py") if forbidden_path else ("src/feature.py",)
        capsule = self.capsule(
            "engineer", "slice_engineering", "engineer-1", allowed=allowed
        )
        state = self.state()
        self.cli(
            "slice-scope-check",
            "--slice-id",
            "SLICE-001",
            "--base-revision",
            state["revision"],
            "--owner-id",
            "engineer-1",
        )
        self.cli(
            "acquire-write-lease",
            "--role",
            "engineer",
            "--phase",
            "slice_engineering",
            "--write-scope",
            "SLICE-001",
            "--worker-id",
            "engineer-1",
            "--capsule",
            capsule,
        )
        changed_path = self.src
        if forbidden_path:
            changed_path = self.root / "src" / "commerce" / "driveby.py"
            changed_path.parent.mkdir(parents=True, exist_ok=True)
            changed_path.write_text("DRIVEBY = True\n", encoding="utf-8")
        else:
            self.src.write_text("VALUE = 1\n", encoding="utf-8")
        inventory_product = [
            self.rel(self.prd),
            self.rel(self.spec),
            self.rel(self.plan),
            self.rel(self.ledger),
            self.rel(self.src),
        ]
        if forbidden_path:
            inventory_product.append(self.rel(changed_path))
        semantic = {
            "schema": 1,
            "inventory_complete": True,
            "domain_inventory": {
                "product": sorted(inventory_product),
                "support": [],
                "evidence": [self.rel(self.test_source)],
            },
            "changes": [
                {
                    "path": self.rel(changed_path),
                    "domain": "product",
                    "symbols": ["VALUE"],
                    "reason": "assigned_goal_effect: PRD-REQ-001, PRD-AC-001 | implement the assigned feature behavior",
                    "change_kind": "modify",
                    "component": "feature",
                    "lifecycle_change": False,
                    "ownership_change": False,
                    "public_contract_change": False,
                    "requirement_ids": ["PRD-REQ-001"],
                    "acceptance_ids": ["PRD-AC-001"],
                    "decision_ids": [],
                    "touchpoint_id": None,
                }
            ],
            "open_assumptions": [],
        }
        semantic_path = self.artifact("verification", "engineer-semantic", semantic)
        lease_id = self.state()["active_write_lease"]["lease_id"]
        result = self.cli(
            "engineer-complete",
            "--run-id",
            "engineer-run-1",
            "--owner-id",
            "engineer-1",
            "--lease-id",
            lease_id,
            "--capsule",
            capsule,
            "--slice-id",
            "SLICE-001",
            "--machine-checks",
            "pass",
            "--diff-inspection",
            "pass",
            "--semantic-handoff",
            semantic_path,
            "--report",
            self.artifact("verification", "engineer-report"),
            expected=2 if forbidden_path else 0,
        )
        return self.full_status()

    def finalize_coverage(self, *, mismatch: bool = False, expected: int = 0) -> dict:
        result = self.cli(
            "coverage-finalize",
            "--scope-id",
            "SLICE-001",
            "--coverage-manifest",
            self.coverage_manifest("coverage-final", "finalized", mismatch=mismatch),
            "--expected-actual-equality",
            "pass" if not mismatch else "fail",
            "--mandatory-registration",
            "pass" if not mismatch else "fail",
            "--automated-execution",
            "pass",
            "--report",
            self.artifact("verification", "coverage-final-report"),
            expected=expected,
        )
        return self.full_status()

    def implementation_complete(self) -> dict:
        self.initialize()
        self.engineer()
        return self.finalize_coverage()

    def qa_manual_artifact(self, *, gate: str | None = None) -> str:
        state = self.state()
        passed = gate is None
        evidence = self.root / "tests" / FEATURE / "qa" / "runtime-evidence.json"
        if passed:
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_text('{"runtime":"pass"}\n', encoding="utf-8")
        value = {
            "schema": 2,
            "revision": state["revision"],
            "product_revision": state["product_revision"],
            "support_revision": state["support_revision"],
            "evidence_revision": state["evidence_revision"],
            "manual_execution": [
                {
                    "identity_id": "MANUAL-SLICE-001-RUNTIME",
                    "executed": passed,
                    "passed": True if passed else None,
                    "deferred": not passed,
                    "blocked_by_finding": None,
                    "qa_evidence": (
                        {"path": self.rel(evidence), "sha256": self.sha(evidence)}
                        if passed
                        else None
                    ),
                    "gate": gate,
                    "minimum_resume_action": None if passed else "provide operator authorization",
                }
            ],
        }
        return self.artifact("qa", "manual-execution", value)

    def optional_manual_identity(
        self, identity_id: str, *, capability_prerequisites: tuple[str, ...] = ()
    ) -> dict:
        return {
            "identity_id": identity_id,
            "kind": "manual",
            "mandatory": False,
            "slice_id": "SLICE-001",
            "requirement_ids": ["PRD-REQ-001"],
            "acceptance_ids": ["PRD-AC-001"],
            "coordinates": {
                "scenario_id": identity_id,
                "topology": "single optional client",
                "setup": "load exact candidate",
                "action": "exercise optional observation",
                "observation": "record optional telemetry",
                "evidence_kind": "log",
            },
            "planned_assertion_or_observation": "optional observation is recorded",
            "capability_prerequisites": list(capability_prerequisites),
        }

    def qa_manual_rows_artifact(self, rows: list[dict], name: str) -> str:
        state = self.state()
        return self.artifact(
            "qa",
            name,
            {
                "schema": 2,
                "revision": state["revision"],
                "product_revision": state["product_revision"],
                "support_revision": state["support_revision"],
                "evidence_revision": state["evidence_revision"],
                "manual_execution": rows,
            },
        )

    def passed_manual_row(self, identity_id: str, name: str) -> dict:
        evidence = self.root / "tests" / FEATURE / "qa" / f"{name}.json"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text('{"runtime":"observed"}\n', encoding="utf-8")
        return {
            "identity_id": identity_id,
            "executed": True,
            "passed": True,
            "deferred": False,
            "blocked_by_finding": None,
            "qa_evidence": {"path": self.rel(evidence), "sha256": self.sha(evidence)},
            "gate": None,
            "minimum_resume_action": None,
        }

    def prepare_qa_state(self) -> None:
        state_path = self.root / ".agentic-pipeline" / "state.json"
        state = self.state()
        state["phase"] = "qa"
        runs = []
        for index in (1,):
            report_relative = self.artifact("reviews", f"prepared-review-{index}")
            credit_relative = self.artifact("reviews", f"prepared-credit-{index}")
            report = self.root / report_relative
            credit = self.root / credit_relative
            runs.append(
                {
                    "run_id": f"prepared-review-{index}",
                    "reviewer_id": f"r{index}",
                    "revision": state["revision"],
                    "product_revision": state["product_revision"],
                    "support_revision": state["support_revision"],
                    "evidence_revision": state["evidence_revision"],
                    "status": "pass",
                    "report": str(report),
                    "report_sha256": self.sha(report),
                    "credit_manifest": str(credit),
                    "credit_manifest_sha256": self.sha(credit),
                    "component_credit_ids": [],
                }
            )
        state["review"] = {
            "status": "passed",
            "revision": state["revision"],
            "product_revision": state["product_revision"],
            "support_revision": state["support_revision"],
            "evidence_revision": state["evidence_revision"],
            "required": 1,
            "runs": runs,
            "recovery_run": None,
        }
        state["review_runs"] = list(runs)
        state_path.write_text(json.dumps(state), encoding="utf-8")

    def write_state(self, state: dict) -> None:
        (self.root / ".agentic-pipeline" / "state.json").write_text(
            json.dumps(state), encoding="utf-8"
        )

    def lifecycle_dashboard_text(
        self,
        updated_date: str,
        *,
        title: str = "Deterministic Feature Dashboard Validation",
        status: str = "🟨 В работе",
        link: str = "./deterministic-feature-dashboard-validation/",
    ) -> str:
        return (
            "# Фичи шаблона\n\n"
            "Этот dashboard генерируется из\n"
            "`docs/Features/template/*/feature.json`. Манифесты —\n"
            "единственный источник состояния; generated-блок не редактируется вручную.\n\n"
            "<!-- feature-index:begin -->\n\n"
            "Всего: 1 | Готово: 0 | В работе: 1 | В плане: 0 | С блокерами: 0\n\n"
            "| ID | Фича | Состояние | Активность | Ветка | Базовый commit | Worklog | Блокеры | Обновлено |\n"
            "|---|---|---|---|---|---|---|---|---|\n"
            f"| TF-0008 | [{title}]({link}) | {status} | Активна | "
            "`template-feature/tf-0008-deterministic-feature-dashboard-validation` | "
            "`765fd71b` | [Открыть](./deterministic-feature-dashboard-validation/worklog.md) | "
            f"— | {updated_date} |\n\n"
            "<!-- feature-index:end -->\n"
        )

    def write_lifecycle_manifest(self, updated_at: str) -> Path:
        path = (
            self.root
            / "docs"
            / "Features"
            / "template"
            / "deterministic-feature-dashboard-validation"
            / "feature.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schemaVersion": 2,
                    "id": "TF-0008",
                    "slug": "deterministic-feature-dashboard-validation",
                    "title": "Deterministic Feature Dashboard Validation",
                    "status": "in_progress",
                    "activity": "active",
                    "branch": "template-feature/tf-0008-deterministic-feature-dashboard-validation",
                    "baseCommit": "765fd71b755f2f0878a0c9c8761b887600590cdf",
                    "startedAt": "2026-08-11T13:03:12.7309279+00:00",
                    "completedAt": None,
                    "updatedAt": updated_at,
                    "blockers": [],
                    "artifacts": [
                        "product-requirements.md",
                        "technical-specification.md",
                        "development-plan.md",
                    ],
                    "verification": None,
                    "recoveryLog": [],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def prepare_lifecycle_projection_recovery(self) -> dict:
        self.initialize(research=False)
        state = self.state()
        state["feature"] = "deterministic-feature-dashboard-validation"
        state["phase"] = "engineering"
        state["engineering_owner_id"] = "engineer-1"
        state["owner_by_slice"]["SLICE-001"] = "engineer-1"
        state["active_slice"] = "SLICE-001"
        state["slice_id"] = "SLICE-001"
        state["pending_engineer_completion"] = None

        dashboard = self.root / "docs" / "Features" / "template" / "README.md"
        dashboard.parent.mkdir(parents=True, exist_ok=True)
        dashboard.write_text(
            self.lifecycle_dashboard_text("2026-08-11"), encoding="utf-8"
        )
        manifest = self.write_lifecycle_manifest("2026-08-11T23:59:00+00:00")
        support = self.root / "pipeline-support.txt"
        support.write_text("support-v1\n", encoding="utf-8")
        dashboard_relative = self.rel(dashboard)
        manifest_relative = self.rel(manifest)
        support_relative = self.rel(support)
        state["revision_inventory"]["product"] = sorted(
            set(state["revision_inventory"]["product"])
            | {dashboard_relative, self.rel(self.src)}
        )
        state["revision_inventory"]["support"] = [support_relative]
        state["revision_inventory"]["evidence"] = [self.rel(self.test_source)]

        coverage = self.root / "tests" / FEATURE / "verification" / "lifecycle-coverage.json"
        coverage.write_text(
            json.dumps({"expected_identities": []}) + "\n", encoding="utf-8"
        )
        state["coverage"]["SLICE-001"]["planned_manifest"] = {
            "path": self.rel(coverage),
            "sha256": self.sha(coverage),
        }

        finding_ids = [f"TF0008-CONV-{index:03d}" for index in range(1, 5)]
        batch = {
            "batch_id": "REMEDIATION-0008",
            "route": "SLICE-001",
            "finding_ids": finding_ids,
            "status": "active",
            "owner_id": "engineer-1",
            "returns_for_owner": 0,
        }
        state["active_remediation_batch"] = batch
        state["remediation_queue"] = [dict(batch)]
        state["product_revalidation"] = {
            "mode": "targeted",
            "source": "convergence",
            "base_revision": "frozen-convergence-revision",
            "base_product_revision": "frozen-convergence-product",
            "base_support_revision": "frozen-convergence-support",
            "base_evidence_revision": "frozen-convergence-evidence",
            "base_convergence_runs": [{"run_id": "convergence-history-1"}],
            "base_review_runs": [],
            "finding_ids": list(finding_ids),
            "slice_ids": ["SLICE-001"],
            "full_wave_trigger": None,
        }
        state["convergence"]["runs"] = [{"run_id": "convergence-history-1"}]
        state["convergence"]["history_marker"] = "preserve-me"
        state["lifecycle_projection_reconciliations"] = []

        revisions = runtime_controller.compute_inventory_revisions(self.root, state)
        for key in (
            "revision",
            "product_revision",
            "support_revision",
            "evidence_revision",
        ):
            state[key] = revisions[key]
        state["revision_records"] = revisions["records"]
        state["lifecycle_projection_guard"] = {
            "schema": 1,
            "feature_id": "TF-0008",
            "feature_slug": "deterministic-feature-dashboard-validation",
            "dashboard_path": dashboard_relative,
            "manifest_path": manifest_relative,
            "dashboard_sha256": self.sha(dashboard),
            "manifest_sha256": self.sha(manifest),
            "updated_date": "2026-08-11",
        }
        dashboard_hash = runtime_controller.exact_inventory_digest(
            self.root, [dashboard_relative], "lifecycle dashboard credit"
        )
        state["component_review_credits"] = [
            {
                "id": "RC-TF0008-DASHBOARD-OLD",
                "component": "feature-dashboard",
                "product_hash": dashboard_hash,
                "contract_hash": dashboard_hash,
                "product_paths": [dashboard_relative],
                "contract_paths": [dashboard_relative],
                "lenses": ["persistence-lifecycle"],
                "review_revision": state["revision"],
                "reviewer_id": "reviewer-old",
                "review_mode": "convergence",
                "source_credit_id": None,
                "valid": True,
                "manifest": "tests/teleport-module/reviews/old-credit.json",
                "recorded_at": "2026-08-11T23:59:00+00:00",
            }
        ]
        findings = {
            "schema_version": runtime_controller.SCHEMA_VERSION,
            "items": [
                {
                    "id": finding_id,
                    "status": "open",
                    "severity": "major",
                    "source": "convergence",
                    "revision": state["revision"],
                    "finding_kind": "product",
                    "origin_slice": "SLICE-001",
                    "remediation_route": "SLICE-001",
                    "blocking": True,
                    "remediation_required": True,
                }
                for finding_id in finding_ids
            ],
        }
        state_path = self.root / ".agentic-pipeline" / "state.json"
        findings_path = self.root / ".agentic-pipeline" / "findings.json"
        runtime_controller.save_runtime(state_path, findings_path, state, findings)
        return {
            "state": json.loads(json.dumps(state)),
            "findings": findings,
            "dashboard": dashboard,
            "manifest": manifest,
            "support": support,
            "finding_ids": finding_ids,
        }

    def apply_lifecycle_projection_drift(
        self,
        fixture: dict,
        *,
        dashboard_date: str = "2026-08-12",
        manifest_updated_at: str = "2026-08-12T05:02:23.8245721+00:00",
        title: str = "Deterministic Feature Dashboard Validation",
        status: str = "🟨 В работе",
        link: str = "./deterministic-feature-dashboard-validation/",
    ) -> None:
        fixture["dashboard"].write_text(
            self.lifecycle_dashboard_text(
                dashboard_date, title=title, status=status, link=link
            ),
            encoding="utf-8",
        )
        self.write_lifecycle_manifest(manifest_updated_at)

    def ready_for_qa(self) -> dict:
        self.implementation_complete()
        state = self.state()
        self.cli(
            "documentation-not-required",
            "--mode",
            "normative_pre_review",
            "--plan-sha256",
            state["development_plan_sha256"],
            "--policy-evidence",
            "POLICY-DOC-NONE",
        )
        self.prepare_qa_state()
        self.qa_probe()
        return self.state()

    def prepare_targeted_qa_closure_ready_state(
        self, *, remove_clean: bool = False, legacy_without_base_clean: bool = False,
        prior_clean_source: str = "parallel_read_only_convergence",
    ) -> dict:
        """Build the exact Final-Review remediation -> closure -> QA -> ready chain."""
        self.implementation_complete()
        state = self.state()
        self.cli(
            "documentation-not-required", "--mode", "normative_pre_review",
            "--plan-sha256", state["development_plan_sha256"],
            "--policy-evidence", "POLICY-DOC-NONE",
        )
        state = self.state()
        convergence_run_ids = ["base-convergence-current-1", "base-convergence-current-2"]
        convergence_runs = []
        for run_id in convergence_run_ids:
            convergence_report = self.artifact("reviews", f"{run_id}-report")
            convergence_credit = self.artifact("reviews", f"{run_id}-credit")
            convergence_runs.append(
                {
                    "run_id": run_id,
                    "reviewer_id": f"{run_id}-reviewer",
                    "status": "pass",
                    "revision": state["revision"],
                    "product_revision": state["product_revision"],
                    "support_revision": state["support_revision"],
                    "evidence_revision": state["evidence_revision"],
                    "report": convergence_report,
                    "report_sha256": self.sha(self.root / convergence_report),
                    "credit_manifest": convergence_credit,
                    "credit_manifest_sha256": self.sha(self.root / convergence_credit),
                }
            )
        prior_clean_run_ids = (
            ["prior-targeted-convergence"]
            if prior_clean_source == "targeted_convergence_closure"
            else convergence_run_ids
        )
        prior_clean = {
            "source": prior_clean_source,
            "run_ids": prior_clean_run_ids,
            "revision": state["revision"],
            "product_revision": state["product_revision"],
            "support_revision": state["support_revision"],
            "evidence_revision": state["evidence_revision"],
            "audit_complete": True,
            "report": self.artifact("reviews", "base-convergence-current"),
            "coverage_manifest": state["coverage_manifest"],
            "recorded_at": "2026-08-11T23:00:00+00:00",
        }
        state["phase"] = "review"
        state["engineer_clean"] = prior_clean
        state["convergence"]["runs"] = convergence_runs
        if prior_clean_source == "targeted_convergence_closure":
            state["review_runs"].append(
                {
                    "run_id": prior_clean_run_ids[0],
                    "reviewer_id": "prior-targeted-convergence-reviewer",
                    "mode": "targeted_product_closure",
                    "status": "pass",
                    "revision": state["revision"],
                    "product_revision": state["product_revision"],
                    "support_revision": state["support_revision"],
                    "evidence_revision": state["evidence_revision"],
                }
            )
        state["review"] = runtime_controller.empty_review_state(
            state["required_reviews"],
            state["revision"],
            state["product_revision"],
            state["support_revision"],
            state["evidence_revision"],
        )
        self.write_state(state)

        finding_id = "F-FINAL-PRODUCT-001"
        self.cli(
            "add-finding", "--id", finding_id, "--source", "review",
            "--finding-kind", "product", "--severity", "major",
            "--scope-relation", "current_feature_path",
            "--introduced-by-candidate", "true",
            "--production-reachability", "normal",
            "--blocks-acceptance-id", "PRD-AC-001",
            "--violates-required-invariant", "false",
            "--mandatory-core-acceptance-evidence-missing", "false",
            "--test-can-miss-product-defect", "false",
            "--title", "Final Review product defect",
            "--evidence",
            "assigned_acceptance_evidence: PRD-AC-001 | exact Final Review component evidence",
            "--revision", state["revision"],
        )
        for index in (1,):
            reviewer = f"base-final-reviewer-{index}"
            capsule_path = self.capsule("reviewer", "review", reviewer)
            report_relative = self.artifact("reviews", f"base-final-review-{index}")
            credit_relative = self.review_credit_manifest(
                f"base-final-review-credit-{index}",
                reviewer,
                "final_whole_feature_review",
            )
            credit_path = self.root / credit_relative
            credit = json.loads(credit_path.read_text(encoding="utf-8"))
            credit["composition_audit"] = True
            credit["new_boundaries_audited"] = []
            credit_path.write_text(json.dumps(credit), encoding="utf-8")
            self.cli(
                "review-complete", "--revision", state["revision"],
                "--product-revision", state["product_revision"],
                "--support-revision", state["support_revision"],
                "--evidence-revision", state["evidence_revision"],
                "--run-id", f"base-final-review-{index}",
                "--reviewer-id", reviewer, "--capsule", capsule_path,
                "--status", "fail", "--report", report_relative,
                "--credit-manifest", credit_relative,
            )
        state = self.state()
        base_review_runs = list(state["review"]["runs"])
        self.cli(
            "review-finalize", "--revision", state["revision"],
            "--decision", "rework", "--rework-scope", "product",
            "--revalidation", "targeted",
            "--reason", "repair exact Final Review product finding",
            "--report", self.artifact("reviews", "base-final-review-decision"),
        )
        revalidation = json.loads(json.dumps(self.state()["product_revalidation"]))

        state = self.state()
        state["iteration_control"]["max_consecutive_product_changes"] = 10
        self.write_state(state)
        capsule = self.capsule(
            "engineer", "engineering", "engineer-1", allowed=(self.rel(self.src),)
        )
        self.cli(
            "slice-scope-check", "--slice-id", "SLICE-001",
            "--base-revision", state["revision"], "--owner-id", "engineer-1",
        )
        self.cli(
            "acquire-write-lease", "--role", "engineer", "--phase", "engineering",
            "--write-scope", "SLICE-001", "--worker-id", "engineer-1",
            "--capsule", capsule,
        )
        self.src.write_text("VALUE = 2\n", encoding="utf-8")
        semantic = self.semantic_packet_for_change(
            self.src, domain="product", symbols=["VALUE"]
        )
        lease_id = self.state()["active_write_lease"]["lease_id"]
        self.cli(
            "engineer-complete", "--run-id", "engineer-remediation-final-review",
            "--owner-id", "engineer-1", "--lease-id", lease_id,
            "--capsule", capsule, "--slice-id", "SLICE-001",
            "--machine-checks", "pass",
            "--diff-inspection", "pass", "--semantic-handoff", semantic,
            "--report", self.artifact(
                "verification", "engineer-remediation-engineer-report"
            ),
            "--resolved-finding", finding_id,
        )
        state = self.state()
        prior_feature_coverage = Path(
            state["coverage"]["feature"]["finalized_manifest"]["path"]
        )
        remediation_coverage = json.loads(
            prior_feature_coverage.read_text(encoding="utf-8")
        )
        remediation_coverage["revisions"] = {
            key: state[key]
            for key in (
                "revision", "product_revision", "support_revision", "evidence_revision"
            )
        }
        remediation_coverage_path = self.artifact(
            "verification", "coverage-remediation-final", remediation_coverage
        )
        self.cli(
            "coverage-finalize", "--scope-id", "feature",
            "--coverage-manifest", remediation_coverage_path,
            "--expected-actual-equality", "pass", "--mandatory-registration", "pass",
            "--automated-execution", "pass",
            "--report", self.artifact("verification", "coverage-remediation-report"),
        )
        closure_before_review = json.loads(json.dumps(self.state()["closure_review"]))
        closure_capsule = self.capsule(
            "reviewer", "closure_review", "base-final-reviewer-1"
        )
        closure_credit = self.review_credit_manifest(
            "targeted-qa-closure-credit",
            "base-final-reviewer-1",
            "targeted_closure",
        )
        state = self.state()
        self.cli(
            "closure-review-complete",
            "--revision", state["revision"],
            "--product-revision", state["product_revision"],
            "--support-revision", state["support_revision"],
            "--evidence-revision", state["evidence_revision"],
            "--run-id", "targeted-qa-closure-pass",
            "--reviewer-id", "base-final-reviewer-1",
            "--capsule", closure_capsule,
            "--status", "pass",
            "--report", self.artifact("reviews", "targeted-qa-closure-report"),
            "--credit-manifest", closure_credit,
        )
        self.qa_probe()
        qa_capsule = self.capsule("reviewer", "qa", "base-final-reviewer-1")
        state = self.state()
        self.cli(
            "qa-complete",
            "--revision", state["revision"],
            "--product-revision", state["product_revision"],
            "--support-revision", state["support_revision"],
            "--evidence-revision", state["evidence_revision"],
            "--run-id", "qa-after-targeted-closure",
            "--worker-id", "base-final-reviewer-1",
            "--capsule", qa_capsule,
            "--status", "pass",
            "--manual-execution", self.qa_manual_artifact(),
            "--report", self.artifact("qa", "qa-after-targeted-closure-report"),
        )
        state = self.state()
        self.cli(
            "documentation-not-required",
            "--mode", "derived_post_qa",
            "--plan-sha256", state["development_plan_sha256"],
            "--policy-evidence", "POLICY-DOC-NONE",
        )
        if remove_clean or legacy_without_base_clean:
            state = self.state()
            state["engineer_clean"] = None
            state["ready_targeted_closure_clean_recoveries"] = []
            if legacy_without_base_clean:
                state["closure_review"].pop("base_engineer_clean", None)
            self.write_state(state)
        return {
            "state": self.state(),
            "finding_id": finding_id,
            "prior_clean": prior_clean,
            "base_review_runs": base_review_runs,
            "revalidation": revalidation,
            "closure_before_review": closure_before_review,
        }

    @staticmethod
    def user_authority_digest(
        authority_id: str, approval_reference: str, statement: str
    ) -> str:
        return hashlib.sha256(
            json.dumps(
                {
                    "kind": "user",
                    "authority_id": authority_id,
                    "approval_reference": approval_reference,
                    "statement": statement,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    def decision_packet(self, decision_id: str = "DEC-001") -> tuple[dict, str, str]:
        statement = "Use the approved deterministic feature path"
        authority_id = f"AUTH-{decision_id}"
        approval_reference = f"USER-APPROVAL-{decision_id}"
        digest = self.user_authority_digest(authority_id, approval_reference, statement)
        packet = {
            "schema": 1,
            "items": [
                {
                    "schema": 1,
                    "decision_id": decision_id,
                    "status": "accepted",
                    "statement": statement,
                    "rationale": "The accepted authority resolves the bounded implementation choice",
                    "consequences": [],
                    "scope_ids": ["PRD-AC-001", "SLICE-001"],
                    "authority": {
                        "kind": "user",
                        "reference": approval_reference,
                        "path": "not_applicable",
                        "sha256": digest,
                        "section_or_id": authority_id,
                    },
                    "supersedes": [],
                }
            ],
        }
        return packet, authority_id, digest

    def accept_user_authority(self, packet: dict) -> dict:
        item = packet["items"][0]
        authority = item["authority"]
        result = self.cli(
            "user-authority-accept",
            "--authority-id",
            authority["section_or_id"],
            "--approval-reference",
            authority["reference"],
            "--statement",
            item["statement"],
        )
        return json.loads(result.stdout)

    def accept_scope_authority(self, authority_id: str) -> dict:
        state = self.state()
        statement = runtime_controller.scope_rebaseline_authority_statement(
            state["scope_guard"]["hold"], self.sha(self.plan)
        )
        result = self.cli(
            "user-authority-accept",
            "--authority-id",
            authority_id,
            "--approval-reference",
            f"USER-APPROVAL-{authority_id}",
            "--statement",
            statement,
        )
        return json.loads(result.stdout)

    def review_credit_manifest(
        self, name: str, reviewer_id: str, review_mode: str
    ) -> str:
        state = self.state()
        product_paths = list(state["revision_inventory"]["product"])
        contract_paths = [self.rel(self.prd)]
        return self.artifact(
            "reviews",
            name,
            {
                "schema_version": 1,
                "revision": state["revision"],
                "reviewer_id": reviewer_id,
                "review_mode": review_mode,
                "components": [
                    {
                        "component": "feature",
                        "product_paths": product_paths,
                        "contract_paths": contract_paths,
                        "product_hash": runtime_controller.exact_inventory_digest(
                            self.root, product_paths, "review product"
                        ),
                        "contract_hash": runtime_controller.exact_inventory_digest(
                            self.root, contract_paths, "review contract"
                        ),
                        "lenses": ["persistence-lifecycle"],
                        "mode": "fresh",
                        "source_credit_id": None,
                    }
                ],
            },
        )

    def documentation_closure_report(
        self,
        name: str,
        *,
        run_id: str,
        reviewer_id: str,
        status: str = "pass",
        source_gaps: list[str] | None = None,
    ) -> str:
        state = self.state()
        derived = state["documentation"]["derived"]
        source_map = json.loads(
            (self.root / derived["source_map_path"]).read_text(encoding="utf-8")
        )
        return self.artifact(
            "reviews",
            name,
            {
                "schema": 1,
                "review_mode": "documentation_closure",
                "run_id": run_id,
                "reviewer_id": reviewer_id,
                "revision": state["revision"],
                "product_revision": state["product_revision"],
                "support_revision": state["support_revision"],
                "evidence_revision": state["evidence_revision"],
                "status": status,
                "changed_support_paths": sorted(derived["paths"]),
                "statement_source_map_path": derived["source_map_path"],
                "statement_source_map_sha256": derived["source_map_sha256"],
                "inspected_statement_ids": sorted(
                    {row["statement_id"] for row in source_map["statements"]}
                ),
                "source_gaps": source_gaps or [],
            },
        )

    def begin_engineer_lease(
        self,
        *,
        allowed: tuple[str, ...],
        symbols: tuple[str, ...] = (),
        exclusions: tuple[str, ...] = (),
        worker: str = "engineer-1",
    ) -> str:
        self.plan_coverage()
        capsule = self.capsule(
            "engineer",
            "slice_engineering",
            worker,
            allowed=allowed,
            symbols=symbols,
            exclusions=exclusions,
        )
        state = self.state()
        self.cli(
            "slice-scope-check",
            "--slice-id",
            "SLICE-001",
            "--base-revision",
            state["revision"],
            "--owner-id",
            worker,
        )
        self.cli(
            "acquire-write-lease",
            "--role",
            "engineer",
            "--phase",
            "slice_engineering",
            "--write-scope",
            "SLICE-001",
            "--worker-id",
            worker,
            "--capsule",
            capsule,
        )
        return capsule
    # Pre-schema-10 lease recovery helpers were removed; migration is tested at the schema-9 boundary.
    def semantic_packet_for_change(
        self,
        path: Path,
        *,
        domain: str = "product",
        symbols: list[str] | None = None,
        requirement_ids: list[str] | None = None,
        acceptance_ids: list[str] | None = None,
    ) -> str:
        state = self.state()
        inventory = {
            key: list(value) for key, value in state["revision_inventory"].items()
        }
        relative = self.rel(path)
        if relative not in inventory[domain]:
            inventory[domain].append(relative)
        for value in inventory.values():
            value.sort()
        return self.artifact(
            "verification",
            "negative-semantic",
            {
                "schema": 1,
                "inventory_complete": True,
                "domain_inventory": inventory,
                "changes": [
                    {
                        "path": relative,
                        "domain": domain,
                        "symbols": symbols if symbols is not None else ["VALUE"],
                        "reason": "assigned_goal_effect: PRD-REQ-001, PRD-AC-001 | bounded assigned implementation",
                        "change_kind": "modify",
                        "component": "feature",
                        "lifecycle_change": False,
                        "ownership_change": False,
                        "public_contract_change": False,
                        "requirement_ids": (
                            requirement_ids if requirement_ids is not None else ["PRD-REQ-001"]
                        ),
                        "acceptance_ids": (
                            acceptance_ids if acceptance_ids is not None else ["PRD-AC-001"]
                        ),
                        "decision_ids": [],
                        "touchpoint_id": None,
                    }
                ],
                "open_assumptions": [],
            },
        )

    def fail_engineer_completion(self, capsule: str, semantic: str, worker: str = "engineer-1") -> subprocess.CompletedProcess[str]:
        state = self.state()
        return self.cli(
            "engineer-complete",
            "--run-id",
            "negative-engineer-run",
            "--owner-id",
            worker,
            "--lease-id",
            state["active_write_lease"]["lease_id"],
            "--capsule",
            capsule,
            "--slice-id",
            "SLICE-001",
            "--machine-checks",
            "pass",
            "--diff-inspection",
            "pass",
            "--semantic-handoff",
            semantic,
            "--report",
            self.artifact("verification", "negative-engineer-report"),
            expected=2,
        )

    def qa_probe(self, *, blocked: bool = False) -> None:
        state = self.state()
        statuses = {
            name: (
                "blocked_user"
                if blocked and name == "test-server-two-clients"
                else "available"
            )
            for name in runtime_controller.required_qa_capabilities(self.root, state)
        }
        args = [
            "qa-capability-probe",
            "--revision",
            state["revision"],
            "--probe-id",
            "probe-1",
            "--report",
            self.artifact("qa", "probe"),
        ]
        for name, status in statuses.items():
            args.extend(("--capability", f"{name}={status}"))
        if blocked:
            args.extend((
                "--minimum-resume-action",
                "test-server-two-clients=user|true|authorize exact QA operator",
            ))
        self.cli(*args)

    def test_init_creates_exact_schema10_and_zero_entry_ledger(self) -> None:
        state = self.initialize(research=False)
        self.assertEqual(10, state["schema_version"])
        self.assertGreaterEqual(state["generation"], 2)
        self.assertEqual(0, state["decision_ledger"]["entry_count"])
        self.assertTrue(self.ledger.is_file())
        for field in (
            "implementation_state",
            "feature_verification_state",
            "active_write_lease",
            "write_lease_history",
            "coverage",
            "documentation",
            "context_capsules",
            "handoffs",
        ):
            self.assertIn(field, state)

    def test_semantic_packet_rejects_allowed_path_without_exact_assigned_goal_effect(self) -> None:
        self.initialize()
        state = self.state()
        inventory = json.loads(json.dumps(state["revision_inventory"]))
        inventory["product"] = sorted(set(inventory["product"] + [self.rel(self.src)]))
        packet = {
            "schema": 1,
            "inventory_complete": True,
            "domain_inventory": inventory,
            "changes": [{
                "path": self.rel(self.src), "domain": "product", "symbols": ["VALUE"],
                "reason": "cleanup on an allowed path", "change_kind": "modify",
                "component": "feature", "lifecycle_change": False,
                "ownership_change": False, "public_contract_change": False,
                "requirement_ids": ["PRD-REQ-001"], "acceptance_ids": ["PRD-AC-001"],
                "decision_ids": [], "touchpoint_id": None,
            }],
            "open_assumptions": [],
        }
        with self.assertRaisesRegex(runtime_controller.PipelineError, "assigned-ID effect"):
            runtime_controller.validate_semantic_write_packet(
                self.root,
                state,
                {"role": "engineer", "phase": "slice_engineering", "lease_id": "LEASE-TEST"},
                packet,
                slice_item=state["slices"]["SLICE-001"],
            )

    def test_review_side_issue_cannot_become_current_remediation_without_goal_binding(self) -> None:
        self.initialize()
        item = {
            "source": "review", "finding_kind": "product", "severity": "major",
            "scope_relation": "current_feature_path", "introduced_by_candidate": False,
            "production_reachability": "normal", "blocks_acceptance_ids": [],
            "violates_required_invariant": False, "required_invariant_evidence": None,
            "blocks_required_support_contract": False,
            "required_support_contract_evidence": None,
            "mandatory_core_acceptance_evidence_missing": False,
            "test_can_miss_product_defect": False, "deferred_reference": None,
            "coverage_identity_ids": [], "evidence": "reviewer preference",
        }
        with self.assertRaisesRegex(runtime_controller.PipelineError, "deferred backlog"):
            runtime_controller.validate_finding_dimensions(self.state(), item)

    def test_review_incomplete_is_input_gap_and_never_mutates_runtime(self) -> None:
        self.initialize()
        state_path = self.root / ".agentic-pipeline" / "state.json"
        findings_path = self.root / ".agentic-pipeline" / "findings.json"
        before_state = state_path.read_bytes()
        before_findings = findings_path.read_bytes()
        rejected = self.cli(
            "review-complete", "--revision", self.state()["revision"],
            "--run-id", "review-incomplete", "--reviewer-id", "reviewer-1",
            "--capsule", "missing-capsule.json", "--status", "incomplete",
            "--report", "missing-report.json", "--credit-manifest", "missing-credit.json",
            expected=2,
        )
        self.assertIn("invalid choice", rejected.stderr)
        self.assertEqual(before_state, state_path.read_bytes())
        self.assertEqual(before_findings, findings_path.read_bytes())

    def test_init_keeps_technical_base_controller_owned_without_plan_reapproval(self) -> None:
        approved_plan_sha = self.sha(self.plan)
        state = self.initialize(
            research=False, base_revision="technical-base-digest-v2"
        )
        self.assertEqual("technical-base-digest-v2", state["revision_base_revision"])
        self.assertEqual(approved_plan_sha, state["development_plan_sha256"])
        self.assertEqual(approved_plan_sha, self.sha(self.plan))
        self.assertNotIn(
            "scope_baseline_revision",
            state["slices"]["SLICE-001"]["scope_contract"],
        )

    def test_schema8_is_rejected_without_guessing_migration_facts(self) -> None:
        self.initialize(research=False)
        for name in ("state.json", "findings.json"):
            path = self.root / ".agentic-pipeline" / name
            value = json.loads(path.read_text(encoding="utf-8"))
            value["schema_version"] = 8
            path.write_text(json.dumps(value), encoding="utf-8")
        result = self.cli("status", expected=2)
        self.assertIn("Unsupported pipeline state", result.stderr)

    def test_context_capsule_records_exact_metrics_and_detects_staleness(self) -> None:
        self.initialize(research=False)
        result = self.cli(
            "context-capsule-create", "--role", "researcher",
            "--phase", "slice_research", expected=2,
        )
        self.assertIn("invalid choice", result.stderr)

    def test_context_capsule_fails_closed_over_numeric_budget(self) -> None:
        self.initialize(research=False)
        result = self.cli(
            "context-capsule-create",
            "--role",
            "researcher",
            "--phase",
            "slice_research",
            "--worker-id",
            "small-budget",
            "--plan-sha256",
            self.state()["development_plan_sha256"],
            "--revision",
            self.state()["revision"],
            "--authority",
            f"{self.rel(self.prd)}={self.sha(self.prd)}:PRD-AC-001",
            "--output-path",
            f"tests/{FEATURE}/verification/out.json",
            "--stop-condition",
            "stop",
            "--max-authority-files",
            "6",
            "--max-evidence-files",
            "5",
            "--max-total-files",
            "10",
            "--max-payload-bytes",
            "500000",
            "--max-estimated-tokens",
            "200000",
            "--output",
            f"tests/{FEATURE}/verification/tiny.json",
            expected=2,
        )
        self.assertIn("invalid choice", result.stderr)

    def test_exclusive_lease_and_drift_safe_release(self) -> None:
        self.initialize()
        self.plan_coverage()
        capsule = self.capsule("engineer", "slice_engineering", "engineer-1", allowed=("src/feature.py",))
        state = self.state()
        self.cli(
            "slice-scope-check", "--slice-id", "SLICE-001",
            "--base-revision", state["revision"], "--owner-id", "engineer-1",
        )
        self.cli(
            "acquire-write-lease",
            "--role", "engineer", "--phase", "slice_engineering", "--write-scope", "SLICE-001",
            "--worker-id", "engineer-1", "--capsule", capsule,
        )
        self.cli(
            "acquire-write-lease",
            "--role", "engineer", "--phase", "slice_engineering", "--write-scope", "SLICE-001",
            "--worker-id", "engineer-2", "--capsule", capsule, expected=2,
        )
        self.src.write_text("VALUE = 99\n", encoding="utf-8")
        lease = self.state()["active_write_lease"]["lease_id"]
        self.cli(
            "release-write-lease", "--lease-id", lease, "--result", "blocked",
            "--reason", "blocked after edit", expected=2,
        )
        self.assertEqual(lease, self.state()["active_write_lease"]["lease_id"])

    def test_release_lease_lost_response_replay_is_exact(self) -> None:
        self.initialize()
        capsule = self.begin_engineer_lease(allowed=("src/feature.py",))
        lease = self.state()["active_write_lease"]["lease_id"]
        command = (
            "release-write-lease", "--lease-id", lease,
            "--result", "blocked", "--reason", "external dependency",
        )
        self.cli(*command)
        state_path = self.root / ".agentic-pipeline" / "state.json"
        after_first = state_path.read_bytes()
        self.cli(*command)
        self.assertEqual(after_first, state_path.read_bytes())
        mismatch = self.cli(
            "release-write-lease", "--lease-id", lease,
            "--result", "blocked", "--reason", "different dependency",
            expected=2,
        )
        self.assertIn("lost-response replay mismatch", mismatch.stderr)

    def test_missing_scope_receipt_routes_to_scope_check_and_blocks_engineer_lease(self) -> None:
        self.initialize()
        self.plan_coverage()
        capsule = self.capsule(
            "engineer", "slice_engineering", "engineer-1",
            allowed=("src/feature.py",),
        )

        status = self.full_status()
        self.assertEqual("run_slice_scope_check", status["next_action"]["action"])
        self.assertEqual("SLICE-001", status["next_action"]["active_slice"])
        result = self.cli(
            "acquire-write-lease", "--role", "engineer", "--phase", "slice_engineering",
            "--write-scope", "SLICE-001", "--worker-id", "engineer-1",
            "--capsule", capsule, expected=2,
        )
        self.assertIn("slice-scope-check", result.stderr)
        self.assertIsNone(self.state()["active_write_lease"])

    def test_stale_scope_receipt_routes_to_scope_check(self) -> None:
        self.initialize()
        self.plan_coverage()
        state = self.state()
        self.cli(
            "slice-scope-check", "--slice-id", "SLICE-001",
            "--base-revision", state["revision"], "--owner-id", "engineer-1",
        )
        state = self.state()
        state["slices"]["SLICE-001"]["scope_pre_edit_check"]["base_revision"] = "0" * 64
        self.write_state(state)

        status = self.full_status()
        self.assertEqual("run_slice_scope_check", status["next_action"]["action"])
        self.assertEqual(state["revision"], status["next_action"]["base_revision"])

    def test_scope_route_does_not_bypass_full_review_budget_checkpoint(self) -> None:
        self.initialize()
        self.plan_coverage()
        state = self.state()
        state["phase"] = "engineering"
        state["worker_budget"]["status"] = "checkpoint_required"
        state["worker_budget"]["checkpoint_causes"] = ["full_review_waves"]
        state["worker_budget"]["reason"] = "full review wave limit reached"
        self.write_state(state)

        route = self.full_status()["next_action"]
        self.assertEqual("director_budget_checkpoint", route["action"])
        self.assertEqual("technical_director", route["owner"])

    def test_current_exact_scope_receipt_permits_engineer_lease(self) -> None:
        self.initialize()
        self.plan_coverage()
        capsule = self.capsule(
            "engineer", "slice_engineering", "engineer-1",
            allowed=("src/feature.py",),
        )
        state = self.state()
        self.cli(
            "slice-scope-check", "--slice-id", "SLICE-001",
            "--base-revision", state["revision"], "--owner-id", "engineer-1",
        )

        lease = json.loads(self.cli(
            "acquire-write-lease", "--role", "engineer", "--phase", "slice_engineering",
            "--write-scope", "SLICE-001", "--worker-id", "engineer-1",
            "--capsule", capsule,
        ).stdout)
        self.assertEqual("active", lease["status"])
        self.assertEqual(state["revision"], lease["base_revision"])

    def test_checkout_drift_after_scope_check_cannot_be_blessed_by_lease(self) -> None:
        self.initialize()
        self.plan_coverage()
        capsule = self.capsule(
            "engineer", "slice_engineering", "engineer-1",
            allowed=("src/feature.py",),
        )
        state = self.state()
        self.cli(
            "slice-scope-check", "--slice-id", "SLICE-001",
            "--base-revision", state["revision"], "--owner-id", "engineer-1",
        )
        receipt = self.state()["slices"]["SLICE-001"]["scope_pre_edit_check"]
        self.src.write_bytes(b"VALUE = 7\r\n")

        result = self.cli(
            "acquire-write-lease", "--role", "engineer", "--phase", "slice_engineering",
            "--write-scope", "SLICE-001", "--worker-id", "engineer-1",
            "--capsule", capsule, expected=2,
        )
        self.assertIn("checkout", result.stderr.lower())
        self.assertIsNone(self.state()["active_write_lease"])
        self.assertEqual(
            receipt,
            self.state()["slices"]["SLICE-001"]["scope_pre_edit_check"],
        )

    def test_scope_check_is_forbidden_after_engineer_lease(self) -> None:
        self.initialize()
        self.plan_coverage()
        capsule = self.capsule(
            "engineer", "slice_engineering", "engineer-1",
            allowed=("src/feature.py",),
        )
        state = self.state()
        self.cli(
            "slice-scope-check", "--slice-id", "SLICE-001",
            "--base-revision", state["revision"], "--owner-id", "engineer-1",
        )
        self.cli(
            "acquire-write-lease", "--role", "engineer", "--phase", "slice_engineering",
            "--write-scope", "SLICE-001", "--worker-id", "engineer-1", "--capsule", capsule,
        )
        result = self.cli(
            "slice-scope-check", "--slice-id", "SLICE-001",
            "--base-revision", state["revision"], "--owner-id", "engineer-1", expected=2,
        )
        self.assertIn("precede", result.stderr.lower())

    def test_new_lease_binds_scope_receipt_and_preserves_byte_exact_base(self) -> None:
        mixed = b"VALUE = 0\r\n# lf\n# crlf\r\n"
        self.src.write_bytes(mixed)
        generated = self.root / "node_modules" / "generated-cache"
        generated.mkdir(parents=True)
        for index in range(1200):
            (generated / f"asset-{index:04d}.js").write_text("generated\n", encoding="utf-8")
        secret = self.root / "private" / "credentials.env"
        secret.parent.mkdir(parents=True)
        secret.write_text("token=must-not-enter-runtime\n", encoding="utf-8")
        self.initialize()
        self.plan_coverage()
        capsule = self.capsule(
            "engineer", "slice_engineering", "engineer-1",
            allowed=("src/feature.py",),
        )
        state = self.state()
        self.cli(
            "slice-scope-check", "--slice-id", "SLICE-001",
            "--base-revision", state["revision"], "--owner-id", "engineer-1",
        )
        receipt = self.state()["slices"]["SLICE-001"]["scope_pre_edit_check"]
        lease = json.loads(self.cli(
            "acquire-write-lease", "--role", "engineer", "--phase", "slice_engineering",
            "--write-scope", "SLICE-001", "--worker-id", "engineer-1", "--capsule", capsule,
        ).stdout)
        state = self.state()
        snapshot = state["lease_snapshots"][lease["lease_id"]]

        self.assertEqual(4, snapshot["snapshot_schema"])
        self.assertEqual("sha256-digest-lines-v1", snapshot["snapshot_format"])
        self.assertNotIn("checkout_text", snapshot)
        self.assertNotIn(self.rel(secret), snapshot["checkout"])
        self.assertFalse(any(path.startswith("node_modules/") for path in snapshot["checkout"]))
        self.assertNotIn("must-not-enter-runtime", json.dumps(state))
        self.assertEqual(
            [hashlib.sha256(line).hexdigest() for line in mixed.splitlines()],
            snapshot["line_proofs"]["src/feature.py"]["line_hashes"],
        )
        self.assertEqual(
            receipt["checkout_snapshot_sha256"],
            lease["scope_authorization"]["checkout_snapshot_sha256"],
        )
        self.assertEqual(
            receipt["checkout_snapshot_sha256"],
            snapshot["scope_authorization"]["checkout_snapshot_sha256"],
        )
        self.assertEqual(self.sha(self.src), snapshot["checkout"]["src/feature.py"])
        self.assertEqual(hashlib.sha256(mixed).hexdigest(), snapshot["checkout"]["src/feature.py"])
        self.assertNotIn("byte_preimage_manifest", snapshot)

    def test_engineer_completion_rejects_tampered_authorized_checkout_snapshot(self) -> None:
        self.initialize()
        capsule = self.begin_engineer_lease(allowed=("src/feature.py",))
        state = self.state()
        lease_id = state["active_write_lease"]["lease_id"]
        state["lease_snapshots"][lease_id]["checkout"]["src/feature.py"] = "0" * 64
        self.write_state(state)
        self.src.write_text("VALUE = 1\n", encoding="utf-8")

        result = self.cli(
            "engineer-complete", "--run-id", "tampered-snapshot-run",
            "--owner-id", "engineer-1", "--lease-id", lease_id,
            "--capsule", capsule, "--slice-id", "SLICE-001",
            "--machine-checks", "pass",
            "--diff-inspection", "pass",
            "--semantic-handoff", self.semantic_packet_for_change(self.src),
            "--report", self.artifact("verification", "tampered-snapshot-report"),
            expected=2,
        )
        self.assertIn("binding", result.stderr.lower())
        self.assertEqual(lease_id, self.state()["active_write_lease"]["lease_id"])

    def test_schema9_raw_snapshot_migrates_automatically_without_status_leak(self) -> None:
        mixed = b"VALUE = 0\r\n# lf\n# crlf\r\n"
        self.src.write_bytes(mixed)
        self.initialize()
        self.begin_engineer_lease(allowed=("src/feature.py",))
        lease_id = self.state()["active_write_lease"]["lease_id"]
        self.downgrade_active_snapshot_to_schema9(
            lease_id, {"src/feature.py": self.src.read_text(encoding="utf-8")}
        )

        state_path = self.root / ".agentic-pipeline" / "state.json"
        findings_path = self.root / ".agentic-pipeline" / "findings.json"
        ledger_path = self.root / ".agentic-pipeline" / "decision-ledger.jsonl"
        before = {
            path: path.read_bytes() if path.exists() else None
            for path in (state_path, findings_path, ledger_path)
        }
        status = self.cli("status", "--section", "leases")
        self.assertNotIn("VALUE = 0", status.stdout)
        self.assertEqual(
            before,
            {
                path: path.read_bytes() if path.exists() else None
                for path in (state_path, findings_path, ledger_path)
            },
        )
        migrated = runtime_controller.load_runtime(str(self.root))[3]
        result = migrated["lease_snapshot_sanitizations"][-1]
        migrated_snapshot = migrated["lease_snapshots"][lease_id]
        self.assertEqual("continued", result["outcome"])
        self.assertEqual(10, migrated["schema_version"])
        self.assertEqual(4, migrated_snapshot["snapshot_schema"])
        self.assertNotIn("checkout_text", migrated_snapshot)
        self.assertEqual(
            [hashlib.sha256(line).hexdigest() for line in mixed.splitlines()],
            migrated_snapshot["line_proofs"]["src/feature.py"]["line_hashes"],
        )
        self.assertEqual("slice_engineering", migrated["phase"])

    def test_schema9_automatic_migration_is_role_agnostic(self) -> None:
        self.initialize(research=False)
        state_path = self.root / ".agentic-pipeline" / "state.json"
        state = self.state()
        lease_id = "LEASE-0001"
        checkout = runtime_controller.checkout_snapshot(self.root, FEATURE, state)
        lease = {
            "lease_id": lease_id,
            "phase": "derived_documentation",
            "write_scope": "support-docs",
            "role": "documentation_finisher",
            "worker_id": "doc-1",
            "base_revision": state["revision"],
            "allowed_paths": [self.rel(self.prd)],
            "allowed_symbols": [],
            "exclusions": [],
            "status": "active",
            "rebaseline_carried": False,
            "scope_authorization": None,
        }
        state["phase"] = "derived_documentation"
        state["active_write_lease"] = lease
        state["lease_snapshots"][lease_id] = {
            "capsule_path": "tests/doc-capsule.json",
            "capsule_sha256": "a" * 64,
            "checkout": checkout,
            "authorization_checkout": checkout,
            "checkout_text": {self.rel(self.prd): self.prd.read_text(encoding="utf-8")},
            "snapshot_schema": 2,
            "snapshot_format": "sha256-raw-bytes-v1",
            "rebaseline_carried": False,
            "scope_authorization": None,
            "created_at": "2026-08-13T00:00:00+00:00",
        }
        state_path.write_text(json.dumps(state), encoding="utf-8")
        self.downgrade_active_snapshot_to_schema9(
            lease_id, {self.rel(self.prd): self.prd.read_text(encoding="utf-8")}
        )

        state_bytes = state_path.read_bytes()
        migrated = runtime_controller.load_runtime(str(self.root))[3]
        self.assertEqual(state_bytes, state_path.read_bytes())
        result = migrated["lease_snapshot_sanitizations"][-1]
        self.assertEqual("continued", result["outcome"])
        self.assertEqual("derived_documentation", migrated["phase"])
        self.assertEqual("documentation_finisher", migrated["active_write_lease"]["role"])
        self.assertEqual(4, migrated["lease_snapshots"][lease_id]["snapshot_schema"])

    def test_schema9_changed_binary_is_audited_revoked_without_candidate_loss(self) -> None:
        base = b"\x00\xfflegacy-base"
        candidate = b"\x00\xffcandidate-change"
        self.src.write_bytes(base)
        self.initialize()
        self.begin_engineer_lease(allowed=("src/feature.py",))
        lease_id = self.state()["active_write_lease"]["lease_id"]
        self.downgrade_active_snapshot_to_schema9(lease_id, {"src/feature.py": ""})
        self.src.write_bytes(candidate)

        state_path = self.root / ".agentic-pipeline" / "state.json"
        findings_path = self.root / ".agentic-pipeline" / "findings.json"
        ledger_path = self.root / ".agentic-pipeline" / "decision-ledger.jsonl"
        before = {
            path: path.read_bytes() if path.exists() else None
            for path in (state_path, findings_path, ledger_path)
        }
        status = json.loads(self.cli("status", "--section", "leases").stdout)["data"]
        self.assertEqual(
            before,
            {
                path: path.read_bytes() if path.exists() else None
                for path in (state_path, findings_path, ledger_path)
            },
        )
        migrated = runtime_controller.load_runtime(str(self.root))[3]
        result = migrated["lease_snapshot_sanitizations"][-1]
        self.assertEqual("candidate_handoff_required", result["outcome"])
        self.assertTrue(result["files_untouched"])
        self.assertEqual(candidate, self.src.read_bytes())
        self.assertIsNone(migrated["active_write_lease"])
        self.assertNotIn(lease_id, migrated["lease_snapshots"])
        self.assertEqual("owner_handoff_hold", migrated["phase"])
        self.assertTrue(migrated["scope_guard"]["rebaseline_candidate"]["fresh_owner_required"])
        self.assertEqual("migration_unverifiable", migrated["write_lease_history"][-1]["result"])
        self.assertEqual(
            "candidate_handoff_required",
            status["last_snapshot_sanitization"]["outcome"],
        )

    def test_schema9_legacy_text_binary_zero_xml_and_symlink_matrix(self) -> None:
        variants = {
            "text": b"VALUE = 0\ntext\n",
            "binary": b"\x00\xff\x10binary",
            "zero": b"",
            "xml": b'<?xml version="1.0"?><root value="1"/>\n',
        }
        for name, raw in variants.items():
            with self.subTest(name=name):
                self.tearDown()
                self.setUp()
                self.src.write_bytes(raw)
                self.initialize()
                self.begin_engineer_lease(allowed=("src/feature.py",))
                lease_id = self.state()["active_write_lease"]["lease_id"]
                self.downgrade_active_snapshot_to_schema9(lease_id, {"src/feature.py": "legacy"})
                before = self.src.read_bytes()
                migrated = runtime_controller.load_runtime(str(self.root))[3]
                self.assertEqual("continued", migrated["lease_snapshot_sanitizations"][-1]["outcome"])
                self.assertTrue(migrated["lease_snapshot_sanitizations"][-1]["files_untouched"])
                self.assertEqual(before, self.src.read_bytes())

        self.tearDown()
        self.setUp()
        target = self.root / "src" / "target.py"
        target.write_text("TARGET = 1\n", encoding="utf-8")
        try:
            self.src.unlink()
            self.src.symlink_to(target)
        except OSError as exc:
            self.skipTest(f"file symlink creation unavailable: {exc}")
        self.initialize()
        self.begin_engineer_lease(allowed=("src/feature.py", "src/target.py"))
        lease_id = self.state()["active_write_lease"]["lease_id"]
        self.downgrade_active_snapshot_to_schema9(lease_id, {"src/feature.py": "legacy"})
        link_target = os.readlink(self.src)
        migrated = runtime_controller.load_runtime(str(self.root))[3]
        self.assertEqual("continued", migrated["lease_snapshot_sanitizations"][-1]["outcome"])
        self.assertTrue(self.src.is_symlink())
        self.assertEqual(link_target, os.readlink(self.src))

    def test_schema9_legacy_tampered_digest_holds_and_keeps_bytes(self) -> None:
        raw = b"candidate-bytes\x00"
        self.src.write_bytes(raw)
        self.initialize()
        self.begin_engineer_lease(allowed=("src/feature.py",))
        lease_id = self.state()["active_write_lease"]["lease_id"]
        self.downgrade_active_snapshot_to_schema9(lease_id, {"src/feature.py": "legacy"})
        state_path = self.root / ".agentic-pipeline" / "state.json"
        state = self.state()
        state["lease_snapshots"][lease_id]["checkout"]["src/feature.py"] = "0" * 64
        state_path.write_text(json.dumps(state), encoding="utf-8")
        migrated = runtime_controller.load_runtime(str(self.root))[3]
        event = migrated["lease_snapshot_sanitizations"][-1]
        self.assertEqual("candidate_handoff_required", event["outcome"])
        self.assertTrue(event["files_untouched"])
        self.assertFalse(event["continuity_preserved"])
        self.assertEqual("owner_handoff_hold", migrated["phase"])
        self.assertEqual(raw, self.src.read_bytes())

    def test_generated_output_policy_positive_negative_malformed_meta_and_tamper(self) -> None:
        policy_path = self.root / runtime_controller.GENERATED_OUTPUT_POLICY_PATH
        positive = ["Library/**", "Artifacts/**", "obj/**", "*.csproj", "*.sln"]
        policy_path.write_text(
            json.dumps({"schema_version": 1, "generated_paths": positive}),
            encoding="utf-8",
        )
        policy = runtime_controller.load_generated_output_policy(self.root)
        for relative in (
            "Library/cache.bin", "Artifacts/build.dat", "obj/x.tmp",
            "Game.csproj", "Game.sln",
        ):
            with self.subTest(relative=relative):
                self.assertTrue(runtime_controller.excluded_source_path(relative, FEATURE, positive))
        for relative in ("src/Game.cs", "ProjectSettings/ProjectSettings.asset", "Library/kept.meta"):
            with self.subTest(legitimate=relative):
                self.assertFalse(runtime_controller.excluded_source_path(relative, FEATURE, positive))
        self.assertEqual(positive, policy["generated_paths"])

        for invalid in ("../Library/**", "*.*", "*.meta", "Library/*.tmp", ""):
            with self.subTest(invalid=invalid):
                policy_path.write_text(
                    json.dumps({"schema_version": 1, "generated_paths": [invalid]}),
                    encoding="utf-8",
                )
                with self.assertRaises(runtime_controller.PipelineError):
                    runtime_controller.load_generated_output_policy(self.root)

        policy_path.write_text(
            json.dumps({"schema_version": 1, "generated_paths": positive}),
            encoding="utf-8",
        )
        self.initialize(research=False)
        policy_path.write_text(
            json.dumps({"schema_version": 1, "generated_paths": positive[:-1]}),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(runtime_controller.PipelineError, "policy drifted"):
            runtime_controller.checkout_snapshot(self.root, FEATURE, self.state())

    def test_dirty_candidate_gate_success_and_invalid_evidence_matrix(self) -> None:
        self.initialize()
        self.begin_engineer_lease(allowed=("src/feature.py",))
        self.src.write_text("VALUE = 1\n", encoding="utf-8")
        state = self.state()
        lease = state["active_write_lease"]
        candidate = runtime_controller.checkout_snapshot(self.root, FEATURE, state)
        digest = runtime_controller.checkout_snapshot_sha256(candidate)
        valid_gate = {
            "schema": 1,
            "lease_id": lease["lease_id"],
            "base_revision": lease["base_revision"],
            "candidate_before_sha256": digest,
            "candidate_after_sha256": digest,
            "outcome": "pass",
            "tool": "project-test-runner",
        }
        report = self.root / "tests" / FEATURE / "verification" / "dirty-matrix.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        invalid = {
            "missing_before": lambda row: row.pop("candidate_before_sha256"),
            "bad_before": lambda row: row.update(candidate_before_sha256="0" * 64),
            "bad_after": lambda row: row.update(candidate_after_sha256="0" * 64),
            "missing_tool": lambda row: row.update(tool=""),
            "bad_outcome": lambda row: row.update(outcome="fail"),
            "wrong_lease": lambda row: row.update(lease_id="LEASE-WRONG"),
            "wrong_base": lambda row: row.update(base_revision="0" * 64),
        }
        for name, mutate in invalid.items():
            with self.subTest(name=name):
                row = dict(valid_gate)
                mutate(row)
                report.write_text(json.dumps({"dirty_candidate_gate": row}), encoding="utf-8")
                with self.assertRaisesRegex(runtime_controller.PipelineError, "unchanged exact candidate"):
                    runtime_controller.write_dirty_candidate_gate_receipt(
                        self.root, state, run_id=name, lease=lease, report=str(report)
                    )

        report.write_text(json.dumps({"dirty_candidate_gate": valid_gate}), encoding="utf-8")
        record = runtime_controller.write_dirty_candidate_gate_receipt(
            self.root, state, run_id="dirty-success", lease=lease, report=str(report)
        )
        pending = {
            "lease_id": lease["lease_id"],
            "base_revisions": {"revision": lease["base_revision"]},
            "dirty_candidate_gate": record,
        }
        runtime_controller.validate_dirty_candidate_gate(self.root, pending)
        wrong = json.loads(json.dumps(pending))
        wrong["lease_id"] = "LEASE-WRONG"
        with self.assertRaisesRegex(runtime_controller.PipelineError, "binding"):
            runtime_controller.validate_dirty_candidate_gate(self.root, wrong)
        wrong = json.loads(json.dumps(pending))
        wrong["base_revisions"]["revision"] = "0" * 64
        with self.assertRaisesRegex(runtime_controller.PipelineError, "binding"):
            runtime_controller.validate_dirty_candidate_gate(self.root, wrong)
        receipt_path = self.root / record["path"]
        receipt_path.write_bytes(receipt_path.read_bytes() + b" ")
        with self.assertRaisesRegex(runtime_controller.PipelineError, "tampered"):
            runtime_controller.validate_dirty_candidate_gate(self.root, pending)

    def test_post_engineer_completion_product_mutation_is_rejected(self) -> None:
        self.initialize()
        self.engineer()
        self.src.write_text("VALUE = 2\n", encoding="utf-8")
        result = self.cli(
            "coverage-finalize", "--scope-id", "SLICE-001",
            "--coverage-manifest", self.coverage_manifest("post-completion", "finalized"),
            "--expected-actual-equality", "pass", "--mandatory-registration", "pass",
            "--automated-execution", "pass",
            "--report", self.artifact("verification", "post-completion-report"),
            expected=2,
        )
        self.assertIn("drift", result.stderr.lower())

    def test_coverage_defer_product_failure_and_authority_matrix(self) -> None:
        self.initialize(research=False)
        state = self.state()
        base = json.loads(
            (self.root / self.coverage_manifest("defer-matrix", "finalized")).read_text(
                encoding="utf-8"
            )
        )
        automated_id = base["automated_execution"][0]["identity_id"]
        manual_id = base["manual_execution"][0]["identity_id"]

        def validate(value: dict) -> dict:
            return runtime_controller.validate_coverage_manifest(
                self.root, state, value, scope_id="SLICE-001", require_finalized=True
            )

        product_failed = json.loads(json.dumps(base))
        product_failed["automated_execution"][0].update(
            outcome="product_failed", authority=None, executed=True, passed=False
        )
        product_failed["summary"].update(
            automated="pending", implementation_eligible=False,
            feature_verification_eligible=False,
        )
        failed = validate(product_failed)
        self.assertEqual([automated_id], failed["product_failed_identity_ids"])
        self.assertEqual([], failed["untested_identity_ids"])

        def deferred(outcome: str, authority: dict) -> dict:
            value = json.loads(json.dumps(base))
            value["automated_execution"][0] = {
                "identity_id": automated_id,
                "executed": False,
                "passed": None,
                "command": "",
                "evidence_path": None,
                "evidence_sha256": None,
                "outcome": outcome,
                "authority": authority,
            }
            value["summary"].update(
                automated="deferred", implementation_eligible=True,
                feature_verification_eligible=False,
                untested_identity_ids=[automated_id],
            )
            return value

        manual_identity = next(
            item for item in base["actual_identities"] if item["identity_id"] == manual_id
        )
        manual_authority = {
            "kind": "manual",
            "authority_id": manual_id,
            "reference": runtime_controller.canonical_json_sha256(manual_identity),
        }
        for outcome in ("infra_unavailable", "manual_required"):
            with self.subTest(outcome=outcome):
                result = validate(deferred(outcome, manual_authority))
                self.assertEqual([automated_id], result["untested_identity_ids"])
                self.assertEqual([], result["product_failed_identity_ids"])

        state["user_authorities"].append({"authority_id": "AUTH-DEFER-1"})
        user_authority = {
            "kind": "user", "authority_id": "AUTH-DEFER-1", "reference": "user-receipt"
        }
        self.assertEqual(
            [automated_id],
            validate(deferred("infra_unavailable", user_authority))["untested_identity_ids"],
        )
        unknown = dict(user_authority, authority_id="AUTH-UNKNOWN")
        with self.assertRaisesRegex(runtime_controller.PipelineError, "unknown user authority"):
            validate(deferred("infra_unavailable", unknown))
        forged = dict(manual_authority, reference="0" * 64)
        with self.assertRaisesRegex(runtime_controller.PipelineError, "exact registered manual"):
            validate(deferred("manual_required", forged))

        manual_deferred = json.loads(json.dumps(base))
        manual_deferred["manual_execution"][0].update(
            executed=False, passed=None, deferred=True, blocked_by_finding=None,
            qa_evidence=None, gate="blocked_user", minimum_resume_action="run exact manual probe",
        )
        manual_deferred["summary"].update(
            manual="deferred", feature_verification_eligible=False,
        )
        result = validate(manual_deferred)
        self.assertFalse(result["manual_ok"])
        self.assertEqual([], result["untested_identity_ids"])

        impossible_summary = json.loads(json.dumps(base))
        impossible_summary["summary"]["automated"] = "blocked"
        with self.assertRaisesRegex(
            runtime_controller.PipelineError, "summary does not match"
        ):
            validate(impossible_summary)

    def test_pf0001_five_file_material_contract_exact_and_mismatch_holds_without_churn(self) -> None:
        paths = [f"src/material-{index}.py" for index in range(1, 6)]
        permissions = [
            {
                "permission_id": "PF-0001",
                "change_type": "lifecycle_change",
                "target_kind": "editable_path",
                "target": paths[0],
                "rationale": "approved lifecycle boundary",
                "decision_authority": "DEC-MATERIAL",
            },
            {
                "permission_id": "PF-0002",
                "change_type": "ownership_change",
                "target_kind": "editable_path",
                "target": paths[1],
                "rationale": "approved ownership boundary",
                "decision_authority": "DEC-MATERIAL",
            },
            {
                "permission_id": "PF-0003",
                "change_type": "public_contract_change",
                "target_kind": "editable_path",
                "target": paths[2],
                "rationale": "approved public contract boundary",
                "decision_authority": "DEC-MATERIAL",
            },
        ]
        slice_item = {
            "scope_contract": {
                "editable_paths": paths,
                "shared_touchpoints": [],
                "excluded_paths": [],
                "excluded_components": [],
                "max_product_files": 5,
                "max_product_lines_changed": 50,
                "planned_material_permissions": permissions,
            }
        }
        changes = [
            {"path": path, "change_kind": "modify", "touchpoint_id": None}
            for path in paths
        ]
        diffs = [
            {
                "path": path,
                "symbols": ["VALUE"],
                "lines_changed": 1,
                "component": "feature",
                "change_kind": "modify",
                "drive_by": False,
                "lifecycle_change": index == 0,
                "ownership_change": index == 1,
                "public_contract_change": index == 2,
            }
            for index, path in enumerate(paths)
        ]
        frozen = json.dumps(slice_item, sort_keys=True)
        self.assertEqual(
            [],
            runtime_controller.scope_violations(
                slice_item, changes, diffs,
                active_decision_ids={"DEC-MATERIAL"},
            ),
        )
        self.assertEqual(frozen, json.dumps(slice_item, sort_keys=True))

        for name, altered, decisions in (
            ("missing_authority", slice_item, set()),
            (
                "wrong_target",
                {"scope_contract": {**slice_item["scope_contract"],
                    "planned_material_permissions": [
                        {**permissions[0], "target": paths[4]}, *permissions[1:]
                    ]}},
                {"DEC-MATERIAL"},
            ),
            (
                "wrong_type",
                {"scope_contract": {**slice_item["scope_contract"],
                    "planned_material_permissions": [
                        {**permissions[0], "change_type": "ownership_change"}, *permissions[1:]
                    ]}},
                {"DEC-MATERIAL"},
            ),
            (
                "missing_permission",
                {"scope_contract": {**slice_item["scope_contract"],
                    "planned_material_permissions": permissions[1:]
                }},
                {"DEC-MATERIAL"},
            ),
        ):
            with self.subTest(name=name):
                violations = runtime_controller.scope_violations(
                    altered, changes, diffs, active_decision_ids=decisions
                )
                self.assertTrue(any("unapproved" in item for item in violations), violations)
                self.assertEqual(frozen, json.dumps(slice_item, sort_keys=True))

        state = self.initialize()
        self.begin_engineer_lease(allowed=("src/feature.py",))
        state = self.state()
        plan_before = self.plan.read_bytes()
        plan_sha_before = state["development_plan_sha256"]
        active_slice = state["slices"]["SLICE-001"]
        active_slice["scope_contract"] = slice_item["scope_contract"]
        violations = runtime_controller.scope_violations(
            slice_item, changes, diffs, active_decision_ids=set()
        )
        runtime_controller.open_scope_expansion_hold(
            state, active_slice, violations,
            lease=state["active_write_lease"],
            inventory={"product": paths, "support": [], "evidence": []},
            changes=changes, diff_files=diffs,
            semantic_report="tests/semantic.json", engineer_report="tests/report.json",
            run_id="pf0001-mismatch",
        )
        self.assertEqual("scope_expansion_hold", state["phase"])
        self.assertEqual(plan_sha_before, state["development_plan_sha256"])
        self.assertEqual(plan_before, self.plan.read_bytes())

    def test_runtime_generation_cas_and_snapshot_file_guard(self) -> None:
        self.initialize(research=False)
        loaded_a = runtime_controller.load_runtime(str(self.root))
        loaded_b = runtime_controller.load_runtime(str(self.root))
        _, state_path, findings_path, state_a, findings_a = loaded_a
        _, _, _, state_b, findings_b = loaded_b
        state_a.setdefault("authority_recovery_history", []).append(
            {"event": "cas-fixture-a"}
        )
        runtime_controller.save_runtime(state_path, findings_path, state_a, findings_a)
        with self.assertRaisesRegex(runtime_controller.PipelineError, "Concurrent runtime update"):
            runtime_controller.save_runtime(state_path, findings_path, state_b, findings_b)

        current = self.state()
        original_limit = runtime_controller.MAX_SOURCE_SNAPSHOT_FILES
        runtime_controller.MAX_SOURCE_SNAPSHOT_FILES = 1
        try:
            with self.assertRaisesRegex(runtime_controller.PipelineError, "file limit"):
                runtime_controller.checkout_snapshot(self.root, FEATURE, current)
        finally:
            runtime_controller.MAX_SOURCE_SNAPSHOT_FILES = original_limit
        original_size_limit = runtime_controller.MAX_LEASE_SNAPSHOT_BYTES
        runtime_controller.MAX_LEASE_SNAPSHOT_BYTES = 1
        try:
            with self.assertRaisesRegex(runtime_controller.PipelineError, "serialized size limit"):
                runtime_controller.build_lease_snapshot(
                    self.root,
                    current,
                    capsule_path="tests/capsule.json",
                    capsule_sha256="a" * 64,
                    allowed_paths=["src/feature.py"],
                )
        finally:
            runtime_controller.MAX_LEASE_SNAPSHOT_BYTES = original_size_limit

    def test_crash_after_canonical_state_before_findings_projection_recovers(self) -> None:
        self.initialize(research=False)
        root, state_path, findings_path, state, findings = runtime_controller.load_runtime(
            str(self.root)
        )
        prior_generation = state["generation"]
        findings["fault_injection_marker"] = "new-findings-generation"
        original_write = runtime_controller.write_json

        def fail_after_canonical_state(path: Path, value: dict) -> None:
            if path == findings_path:
                raise runtime_controller.PipelineError("injected findings projection failure")
            original_write(path, value)

        runtime_controller.write_json = fail_after_canonical_state
        try:
            with self.assertRaisesRegex(
                runtime_controller.PipelineError, "injected findings projection failure"
            ):
                runtime_controller.save_runtime(
                    state_path, findings_path, state, findings
                )
        finally:
            runtime_controller.write_json = original_write

        disk_state = json.loads(state_path.read_text(encoding="utf-8"))
        compatibility_findings = json.loads(findings_path.read_text(encoding="utf-8"))
        self.assertEqual(prior_generation + 1, disk_state["generation"])
        self.assertEqual(
            "new-findings-generation",
            disk_state["canonical_findings"]["fault_injection_marker"],
        )
        self.assertNotIn("fault_injection_marker", compatibility_findings)
        _, _, _, recovered_state, recovered_findings = runtime_controller.load_runtime(
            str(root)
        )
        self.assertEqual(prior_generation + 1, recovered_state["generation"])
        self.assertEqual("new-findings-generation", recovered_findings["fault_injection_marker"])
        runtime_controller.save_runtime(
            state_path, findings_path, recovered_state, recovered_findings
        )
        self.assertEqual(
            "new-findings-generation",
            json.loads(findings_path.read_text(encoding="utf-8"))["fault_injection_marker"],
        )
        tampered = json.loads(state_path.read_text(encoding="utf-8"))
        tampered["canonical_findings"]["tampered"] = True
        state_path.write_text(json.dumps(tampered), encoding="utf-8")
        with self.assertRaisesRegex(
            runtime_controller.PipelineError, "generation/digest is inconsistent"
        ):
            runtime_controller.load_runtime(str(root))

    def test_git_projection_keeps_tracked_ignored_and_drops_untracked_ignored(self) -> None:
        self.initialize(research=False)
        tracked = self.root / "src" / "tracked.ignored"
        untracked = self.root / "src" / "untracked.ignored"
        tracked.write_text("tracked\n", encoding="utf-8")
        untracked.write_text("untracked\n", encoding="utf-8")
        (self.root / ".gitignore").write_text("src/*.ignored\n", encoding="utf-8")
        subprocess.run(
            ["git", "init", "-q"], cwd=self.root, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "add", "-f", self.rel(tracked)],
            cwd=self.root,
            check=True,
            capture_output=True,
        )
        snapshot = runtime_controller.checkout_snapshot(
            self.root, FEATURE, self.state()
        )
        self.assertIn(self.rel(tracked), snapshot)
        self.assertNotIn(self.rel(untracked), snapshot)

    def test_gitlink_in_source_projection_fails_closed_direct_and_cli(self) -> None:
        self.initialize()
        self.plan_coverage()
        module = self.root / "external-module"
        module.mkdir()
        module_file = module / "inside.cs"
        module_file.write_text("v1\n", encoding="utf-8")
        for repository in (module, self.root):
            subprocess.run(
                ["git", "init", "-q"], cwd=repository, check=True, capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.email", "test@example.invalid"],
                cwd=repository,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Pipeline Test"],
                cwd=repository,
                check=True,
                capture_output=True,
            )
        subprocess.run(
            ["git", "add", "inside.cs"], cwd=module, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-qm", "module"],
            cwd=module,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "git",
                "-c",
                "protocol.file.allow=always",
                "submodule",
                "add",
                "-q",
                str(module),
                "src/sharedlib",
            ],
            cwd=self.root,
            check=True,
            capture_output=True,
        )

        with self.assertRaisesRegex(runtime_controller.PipelineError, "gitlink/submodule"):
            runtime_controller.checkout_snapshot(self.root, FEATURE, self.state())
        state = self.state()
        blocked = self.cli(
            "slice-scope-check",
            "--slice-id",
            "SLICE-001",
            "--base-revision",
            state["revision"],
            "--owner-id",
            "engineer-1",
            expected=2,
        )
        self.assertIn("gitlink/submodule", blocked.stderr)

    def test_schema9_direct_load_migrates_before_writer_release(self) -> None:
        self.initialize()
        self.begin_engineer_lease(allowed=("src/feature.py",))
        lease_id = self.state()["active_write_lease"]["lease_id"]
        self.downgrade_active_snapshot_to_schema9(
            lease_id, {"src/feature.py": self.src.read_text(encoding="utf-8")}
        )
        _, _, _, migrated, _ = runtime_controller.load_runtime(str(self.root))
        self.assertEqual(10, migrated["schema_version"])
        self.assertEqual(
            4, migrated["lease_snapshots"][lease_id]["snapshot_schema"]
        )
        self.assertEqual(9, self.state()["schema_version"])
        self.cli(
            "release-write-lease",
            "--lease-id",
            lease_id,
            "--result",
            "blocked",
            "--reason",
            "migration completed before release",
        )
        self.assertIsNone(self.state()["active_write_lease"])
        self.assertEqual(10, self.state()["schema_version"])

    def test_runtime_control_directory_rejects_symlink_or_reparse_point(self) -> None:
        project = tempfile.TemporaryDirectory()
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(project.cleanup)
        self.addCleanup(outside.cleanup)
        project_root = Path(project.name)
        control = project_root / runtime_controller.STATE_DIR
        junction_created = False
        try:
            control.symlink_to(Path(outside.name), target_is_directory=True)
        except OSError as exc:
            if os.name != "nt":
                self.skipTest(f"directory symlink/reparse creation unavailable: {exc}")
            junction = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(control), outside.name],
                capture_output=True,
                text=True,
                check=False,
            )
            if junction.returncode != 0:
                self.skipTest(
                    "directory symlink/junction creation unavailable: "
                    + (junction.stderr or junction.stdout).strip()
                )
            junction_created = True
        try:
            with self.assertRaisesRegex(
                runtime_controller.PipelineError, "symlink/junction/reparse|escapes"
            ):
                runtime_controller.runtime_paths(str(project_root))
            cli = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "status",
                    "--project-root",
                    str(project_root),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(2, cli.returncode, cli.stderr or cli.stdout)
            self.assertRegex(cli.stderr, "symlink/junction/reparse|escapes")
        finally:
            if junction_created:
                os.rmdir(control)

    # Legacy in-schema scope recovery tests were superseded by the fail-closed schema-9 migration hold.
    def test_prepare_engineer_continuation_creates_exact_bound_handoff(self) -> None:
        self.initialize()
        self.plan_coverage()
        before = self.state()

        prepared = json.loads(self.cli("prepare-engineer-continuation").stdout)

        self.assertEqual("prepared", prepared["status"])
        self.assertEqual("slice_engineering", prepared["phase"])
        self.assertEqual("engineer-1", prepared["owner_id"])
        self.assertEqual("SLICE-001", prepared["slice_id"])
        self.assertEqual(before["revision"], prepared["revision"])
        state = self.state()
        receipt = state["slices"]["SLICE-001"]["scope_pre_edit_check"]
        lease = state["active_write_lease"]
        capsule_path = self.root / prepared["capsule"]["path"]
        capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["checkout_snapshot_sha256"], prepared["scope_receipt"]["checkout_snapshot_sha256"])
        self.assertEqual(receipt["checkout_snapshot_sha256"], lease["scope_authorization"]["checkout_snapshot_sha256"])
        self.assertEqual(lease["lease_id"], prepared["lease"]["id"])
        self.assertEqual(capsule["capsule_id"], prepared["capsule"]["id"])
        self.assertEqual(capsule["capsule_sha256"], prepared["capsule"]["capsule_sha256"])
        self.assertEqual(self.sha(capsule_path), prepared["capsule"]["sha256"])
        self.assertEqual(before["revision"], capsule["revisions"]["revision"])
        self.assertEqual(before["product_revision"], capsule["revisions"]["product_revision"])
        self.assertEqual(before["support_revision"], capsule["revisions"]["support_revision"])
        self.assertEqual(before["evidence_revision"], capsule["revisions"]["evidence_revision"])
        self.assertEqual([], capsule["finding_ids"])
        self.assertEqual(
            ["src/contracts.py", "src/feature.py"], sorted(capsule["allowed_paths"])
        )
        self.assertIn("src/commerce/**", capsule["exclusions"])
        self.assertIn("commerce", capsule["exclusions"])
        for output in capsule["output_paths"]:
            self.assertFalse(Path(output).is_absolute())
            self.assertTrue(output.startswith(f"tests/{FEATURE}/verification/controller/"))
        self.assertEqual(
            {
                "action": "dispatch_engineer",
                "role": "engineer",
                "worker_id": "engineer-1",
                "phase": "slice_engineering",
                "slice_id": "SLICE-001",
                "capsule_path": prepared["capsule"]["path"],
                "lease_id": lease["lease_id"],
                "stop_condition": capsule["stop_condition"],
            },
            prepared["handoff"],
        )

    def test_prepare_engineer_continuation_is_idempotent_without_duplicate_artifacts(self) -> None:
        self.initialize()
        self.plan_coverage()
        first = json.loads(self.cli("prepare-engineer-continuation").stdout)
        state_bytes = (self.root / ".agentic-pipeline" / "state.json").read_bytes()
        findings_bytes = (self.root / ".agentic-pipeline" / "findings.json").read_bytes()
        artifacts = {
            self.rel(path): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file()
        }

        second = json.loads(self.cli("prepare-engineer-continuation").stdout)

        self.assertEqual("already_prepared", second["status"])
        for key in ("phase", "owner_id", "slice_id", "revision", "scope_receipt", "capsule", "lease", "handoff"):
            self.assertEqual(first[key], second[key])
        self.assertEqual(state_bytes, (self.root / ".agentic-pipeline" / "state.json").read_bytes())
        self.assertEqual(findings_bytes, (self.root / ".agentic-pipeline" / "findings.json").read_bytes())
        self.assertEqual(
            artifacts,
            {
                self.rel(path): path.read_bytes()
                for path in self.root.rglob("*")
                if path.is_file()
            },
        )

    def test_prepare_engineer_continuation_refreshes_stale_capsule_after_reconciliation(self) -> None:
        fixture = self.prepare_lifecycle_projection_recovery()
        state = self.state()
        state["tests_path"] = str(
            self.root / "tests" / "deterministic-feature-dashboard-validation"
        )
        self.write_state(state)
        stale_path = self.capsule(
            "engineer", "engineering", "engineer-1", allowed=("src/feature.py",)
        )
        stale_value = json.loads((self.root / stale_path).read_text(encoding="utf-8"))
        self.apply_lifecycle_projection_drift(fixture)

        prepared = json.loads(self.cli("prepare-engineer-continuation").stdout)

        state = self.state()
        stale_record = next(
            item for item in state["context_capsules"] if item["capsule_id"] == stale_value["capsule_id"]
        )
        self.assertEqual("stale", stale_record["status"])
        self.assertNotEqual(stale_path, prepared["capsule"]["path"])
        fresh = json.loads((self.root / prepared["capsule"]["path"]).read_text(encoding="utf-8"))
        self.assertEqual(state["revision"], fresh["revisions"]["revision"])
        self.assertEqual(fixture["finding_ids"], fresh["finding_ids"])
        reconciliation = state["lifecycle_projection_reconciliations"][-1]
        self.assertTrue((self.root / reconciliation["path"]).is_file())
        self.assertIn(reconciliation["path"], {item["path"] for item in fresh["evidence"]})
    # Continuation never consumes a pre-schema-10 snapshot directly.
    def test_prepare_engineer_continuation_binds_remediation_findings_owner_slice_and_evidence(self) -> None:
        fixture = self.prepare_lifecycle_projection_recovery()
        state = self.state()
        state["tests_path"] = str(
            self.root / "tests" / "deterministic-feature-dashboard-validation"
        )
        self.write_state(state)

        prepared = json.loads(self.cli("prepare-engineer-continuation").stdout)

        state = self.state()
        capsule = json.loads(
            (self.root / prepared["capsule"]["path"]).read_text(encoding="utf-8")
        )
        self.assertEqual(fixture["finding_ids"], capsule["finding_ids"])
        self.assertEqual(state["engineering_owner_id"], capsule["worker_id"])
        self.assertEqual("SLICE-001", prepared["slice_id"])
        self.assertEqual(state["revision"], prepared["revision"])
        expected_evidence = {
            item["path"]: item["sha256"] for item in capsule["evidence"]
        }
        planned = state["coverage"]["SLICE-001"]["planned_manifest"]
        self.assertEqual(planned["sha256"], expected_evidence[planned["path"]])
        lease = state["active_write_lease"]
        snapshot = state["lease_snapshots"][lease["lease_id"]]
        self.assertEqual(capsule["capsule_sha256"], snapshot["capsule_sha256"])
        self.assertEqual(capsule["allowed_paths"], lease["allowed_paths"])
        self.assertEqual(capsule["exclusions"], lease["exclusions"])

    def test_prepare_engineer_continuation_touchpoint_symbols_do_not_restrict_owned_path(self) -> None:
        self.initialize()
        self.plan_coverage()
        prepared = json.loads(self.cli("prepare-engineer-continuation").stdout)
        capsule_path = prepared["capsule"]["path"]
        capsule = json.loads((self.root / capsule_path).read_text(encoding="utf-8"))
        # Touchpoint symbols are enforced by the slice scope contract. They must
        # not become a lease-global restriction on the separately owned file.
        self.assertEqual([], capsule["allowed_symbols"])
        self.src.write_text("VALUE = 1\n", encoding="utf-8")
        state = self.state()
        semantic_output, report_output = capsule["output_paths"]
        semantic_value = json.loads(
            (self.root / self.semantic_packet_for_change(self.src)).read_text(
                encoding="utf-8"
            )
        )
        semantic_path = self.root / semantic_output
        semantic_path.parent.mkdir(parents=True, exist_ok=True)
        semantic_path.write_text(json.dumps(semantic_value), encoding="utf-8")
        report_path = self.root / report_output
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(self.dirty_candidate_report()), encoding="utf-8")

        completed = json.loads(
            self.cli(
                "engineer-complete",
                "--run-id",
                "one-command-owned-path-run",
                "--owner-id",
                "engineer-1",
                "--lease-id",
                state["active_write_lease"]["lease_id"],
                "--capsule",
                capsule_path,
                "--slice-id",
                "SLICE-001",
                "--machine-checks",
                "pass",
                "--diff-inspection",
                "pass",
                "--semantic-handoff",
                semantic_output,
                "--report",
                report_output,
            ).stdout
        )
        self.assertEqual("slice_coverage_finalization", completed["phase"])

    def test_prepare_engineer_continuation_respects_higher_priority_checkpoint(self) -> None:
        self.initialize()
        self.plan_coverage()
        state = self.state()
        state["worker_budget"]["status"] = "checkpoint_required"
        state["worker_budget"]["checkpoint_causes"] = ["full_review_waves"]
        state["worker_budget"]["reason"] = "full review wave limit reached"
        self.write_state(state)
        before = (self.root / ".agentic-pipeline" / "state.json").read_bytes()

        result = self.cli("prepare-engineer-continuation", expected=2)

        self.assertIn("budget checkpoint", result.stderr.lower())
        self.assertEqual(before, (self.root / ".agentic-pipeline" / "state.json").read_bytes())
        self.assertIsNone(self.state()["active_write_lease"])

    def test_prepare_engineer_continuation_allows_assigned_owner_past_worker_count_checkpoint(self) -> None:
        self.initialize()
        self.plan_coverage()
        state = self.state()
        state["phase"] = "engineering"
        state["worker_budget"]["status"] = "checkpoint_required"
        state["worker_budget"]["checkpoint_causes"] = ["workers"]
        state["worker_budget"]["reason"] = "new worker budget reached"
        self.write_state(state)
        route = self.full_status()["next_action"]
        self.assertEqual("run_slice_scope_check", route["action"])

        prepared = json.loads(self.cli("prepare-engineer-continuation").stdout)

        self.assertEqual("prepared", prepared["status"])
        self.assertEqual("engineer-1", prepared["owner_id"])

    def test_prepare_engineer_continuation_stops_at_user_gate(self) -> None:
        self.initialize()
        self.plan_coverage()
        state = self.state()
        state["phase"] = "scope_expansion_hold"
        state["scope_guard"]["hold"] = {
            "reason": "product scope approval required",
            "requested_paths": ["src/new-product-area.py"],
        }
        self.write_state(state)
        before = (self.root / ".agentic-pipeline" / "state.json").read_bytes()

        result = self.cli("prepare-engineer-continuation", expected=2)

        self.assertIn("slice_engineering or engineering", result.stderr)
        self.assertEqual(before, (self.root / ".agentic-pipeline" / "state.json").read_bytes())
        self.assertIsNone(self.state()["active_write_lease"])

    def test_prepare_engineer_continuation_rejects_tampered_prepared_capsule(self) -> None:
        self.initialize()
        self.plan_coverage()
        prepared = json.loads(self.cli("prepare-engineer-continuation").stdout)
        capsule_path = self.root / prepared["capsule"]["path"]
        capsule_path.write_bytes(capsule_path.read_bytes() + b" ")
        frozen = (self.root / ".agentic-pipeline" / "state.json").read_bytes()

        result = self.cli("prepare-engineer-continuation", expected=2)

        self.assertIn("capsule", result.stderr.lower())
        self.assertEqual(frozen, (self.root / ".agentic-pipeline" / "state.json").read_bytes())
        self.assertEqual(prepared["lease"]["id"], self.state()["active_write_lease"]["lease_id"])

    def test_prepare_engineer_continuation_rejects_tampered_prepared_scope_binding(self) -> None:
        self.initialize()
        self.plan_coverage()
        prepared = json.loads(self.cli("prepare-engineer-continuation").stdout)
        state = self.state()
        state["slices"]["SLICE-001"]["scope_pre_edit_check"][
            "checkout_snapshot_sha256"
        ] = "0" * 64
        self.write_state(state)
        frozen = (self.root / ".agentic-pipeline" / "state.json").read_bytes()

        result = self.cli("prepare-engineer-continuation", expected=2)

        self.assertIn("scope", result.stderr.lower())
        self.assertEqual(frozen, (self.root / ".agentic-pipeline" / "state.json").read_bytes())
        self.assertEqual(prepared["lease"]["id"], self.state()["active_write_lease"]["lease_id"])

    def test_prepare_engineer_continuation_rejects_partial_direct_capsule_binding(self) -> None:
        for missing in ("capsule_id", "capsule_path", "capsule_sha256"):
            with self.subTest(missing=missing):
                self.tearDown()
                self.setUp()
                self.initialize()
                self.plan_coverage()
                self.cli("prepare-engineer-continuation")
                state = self.state()
                state["active_write_lease"].pop(missing)
                self.write_state(state)
                frozen = (self.root / ".agentic-pipeline" / "state.json").read_bytes()

                result = self.cli("prepare-engineer-continuation", expected=2)

                self.assertIn("capsule", result.stderr.lower())
                self.assertEqual(
                    frozen,
                    (self.root / ".agentic-pipeline" / "state.json").read_bytes(),
                )

    def test_engineer_complete_rejects_partial_auto_prepared_capsule_binding(self) -> None:
        for missing in ("capsule_id", "capsule_path", "capsule_sha256"):
            with self.subTest(missing=missing):
                self.tearDown()
                self.setUp()
                self.initialize()
                self.plan_coverage()
                prepared = json.loads(
                    self.cli("prepare-engineer-continuation").stdout
                )
                capsule_relative = prepared["capsule"]["path"]
                capsule = json.loads(
                    (self.root / capsule_relative).read_text(encoding="utf-8")
                )
                self.src.write_text("VALUE = 1\n", encoding="utf-8")
                semantic_output, report_output = capsule["output_paths"]
                semantic_value = json.loads(
                    (
                        self.root / self.semantic_packet_for_change(self.src)
                    ).read_text(encoding="utf-8")
                )
                semantic_path = self.root / semantic_output
                semantic_path.parent.mkdir(parents=True, exist_ok=True)
                semantic_path.write_text(
                    json.dumps(semantic_value), encoding="utf-8"
                )
                report_path = self.root / report_output
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(
                    json.dumps(self.dirty_candidate_report()), encoding="utf-8"
                )
                state = self.state()
                lease_id = state["active_write_lease"]["lease_id"]
                state["active_write_lease"].pop(missing)
                self.write_state(state)

                result = self.cli(
                    "engineer-complete",
                    "--run-id",
                    f"partial-direct-binding-{missing}",
                    "--owner-id",
                    "engineer-1",
                    "--lease-id",
                    lease_id,
                    "--capsule",
                    capsule_relative,
                    "--slice-id",
                    "SLICE-001",
                    "--machine-checks",
                    "pass",
                    "--diff-inspection",
                    "pass",
                    "--semantic-handoff",
                    semantic_output,
                    "--report",
                    report_output,
                    expected=2,
                )

                self.assertIn("direct capsule binding is incomplete", result.stderr)
                self.assertEqual(
                    lease_id, self.state()["active_write_lease"]["lease_id"]
                )

    def test_prepare_engineer_continuation_repeated_drift_failure_is_bounded_and_nonmutating(self) -> None:
        self.initialize()
        self.plan_coverage()
        self.prd.write_text(self.prd.read_text(encoding="utf-8") + "\nsource drift\n", encoding="utf-8")
        before = {
            self.rel(path): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file()
        }

        first = self.cli("prepare-engineer-continuation", expected=2)
        second = self.cli("prepare-engineer-continuation", expected=2)

        self.assertEqual(first.stderr, second.stderr)
        self.assertIn("drift", first.stderr.lower())
        self.assertEqual(
            before,
            {
                self.rel(path): path.read_bytes()
                for path in self.root.rglob("*")
                if path.is_file()
            },
        )

    def test_prepare_engineer_continuation_reprepares_after_clean_incomplete_release(self) -> None:
        self.initialize()
        self.plan_coverage()
        first = json.loads(self.cli("prepare-engineer-continuation").stdout)
        self.cli(
            "release-write-lease",
            "--lease-id",
            first["lease"]["id"],
            "--result",
            "incomplete",
            "--reason",
            "worker stopped before editing",
        )
        self.assertIsNone(self.state()["active_write_lease"])

        second = json.loads(self.cli("prepare-engineer-continuation").stdout)

        self.assertEqual("prepared", second["status"])
        self.assertNotEqual(first["lease"]["id"], second["lease"]["id"])
        self.assertNotEqual(first["capsule"]["id"], second["capsule"]["id"])
        self.assertNotEqual(first["capsule"]["path"], second["capsule"]["path"])
        self.assertTrue((self.root / first["capsule"]["path"]).is_file())
        self.assertTrue((self.root / second["capsule"]["path"]).is_file())
        second_capsule = json.loads(
            (self.root / second["capsule"]["path"]).read_text(encoding="utf-8")
        )
        self.assertEqual(self.state()["revision"], second_capsule["revisions"]["revision"])
        self.assertEqual("dispatch_engineer", second["handoff"]["action"])
        self.assertEqual(
            second["lease"]["id"], self.state()["active_write_lease"]["lease_id"]
        )

    # Schema-2/3 sanitizer cases were replaced by the schema-9 -> hold -> schema-4 regression.
    def test_prepare_engineer_continuation_rejects_controller_artifact_root_symlink(self) -> None:
        self.initialize()
        self.plan_coverage()
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        outside_root = Path(outside.name)
        controller_root = (
            self.root / "tests" / FEATURE / "verification" / "controller"
        )
        controller_root.parent.mkdir(parents=True, exist_ok=True)
        try:
            controller_root.symlink_to(outside_root, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"directory symlink creation unavailable: {exc}")
        frozen = (self.root / ".agentic-pipeline" / "state.json").read_bytes()

        result = self.cli("prepare-engineer-continuation", expected=2)

        self.assertTrue(
            "inside the project root" in result.stderr.lower()
            or "escapes" in result.stderr.lower()
        )
        self.assertEqual(frozen, (self.root / ".agentic-pipeline" / "state.json").read_bytes())
        self.assertEqual([], list(outside_root.iterdir()))

    def test_prepare_engineer_continuation_adopts_exact_orphan_capsule_after_save_crash(self) -> None:
        self.initialize()
        self.plan_coverage()
        before = (self.root / ".agentic-pipeline" / "state.json").read_bytes()
        original_save = runtime_controller.save_runtime

        def fail_after_capsule(*_args, **_kwargs):
            raise runtime_controller.PipelineError("simulated continuation save crash")

        runtime_controller.save_runtime = fail_after_capsule
        try:
            args = type("Args", (), {"project_root": str(self.root)})()
            with self.assertRaisesRegex(
                runtime_controller.PipelineError, "simulated continuation save crash"
            ):
                runtime_controller.cmd_prepare_engineer_continuation(args)
        finally:
            runtime_controller.save_runtime = original_save

        self.assertEqual(before, (self.root / ".agentic-pipeline" / "state.json").read_bytes())
        orphan_paths = list(
            (self.root / "tests" / FEATURE / "verification" / "controller").glob(
                "engineer-continuation-*.json"
            )
        )
        self.assertEqual(1, len(orphan_paths))
        orphan_bytes = orphan_paths[0].read_bytes()

        prepared = json.loads(self.cli("prepare-engineer-continuation").stdout)

        self.assertEqual("prepared", prepared["status"])
        self.assertEqual(orphan_paths[0], self.root / prepared["capsule"]["path"])
        self.assertEqual(orphan_bytes, orphan_paths[0].read_bytes())
        self.assertEqual(1, len(self.state()["context_capsules"]))

    def test_prepare_engineer_continuation_rejects_tampered_orphan_capsule(self) -> None:
        self.initialize()
        self.plan_coverage()
        original_save = runtime_controller.save_runtime

        def fail_after_capsule(*_args, **_kwargs):
            raise runtime_controller.PipelineError("simulated continuation save crash")

        runtime_controller.save_runtime = fail_after_capsule
        try:
            args = type("Args", (), {"project_root": str(self.root)})()
            with self.assertRaises(runtime_controller.PipelineError):
                runtime_controller.cmd_prepare_engineer_continuation(args)
        finally:
            runtime_controller.save_runtime = original_save
        orphan_path = next(
            (self.root / "tests" / FEATURE / "verification" / "controller").glob(
                "engineer-continuation-*.json"
            )
        )
        orphan = json.loads(orphan_path.read_text(encoding="utf-8"))
        orphan["stop_condition"] = "tampered orphan"
        orphan_path.write_text(json.dumps(orphan), encoding="utf-8")
        frozen = (self.root / ".agentic-pipeline" / "state.json").read_bytes()

        result = self.cli("prepare-engineer-continuation", expected=2)

        self.assertIn("capsule", result.stderr.lower())
        self.assertEqual(frozen, (self.root / ".agentic-pipeline" / "state.json").read_bytes())
        self.assertIsNone(self.state()["active_write_lease"])

    def test_prepare_engineer_continuation_preserves_rebaseline_candidate_parity(self) -> None:
        self.initialize()
        self.engineer(forbidden_path=True)
        text = self.plan.read_text(encoding="utf-8")
        text = text.replace(
            "- editable_paths: src/feature.py",
            "- editable_paths: src/feature.py, src/commerce/driveby.py",
        )
        text = text.replace("- excluded_components: commerce", "- excluded_components: payments")
        text = text.replace("- excluded_paths: src/commerce/**", "- excluded_paths: src/payments/**")
        self.plan.write_text(text, encoding="utf-8")
        planning_path = self.root / ".agentic-pipeline" / "development-plan-state.json"
        planning = json.loads(planning_path.read_text(encoding="utf-8"))
        planning["approval"]["approved_sha256"] = self.sha(self.plan)
        planning_path.write_text(json.dumps(planning), encoding="utf-8")
        self.accept_scope_authority("USER-SCOPE-APPROVAL-CONTINUE")
        self.cli(
            "rebaseline-scope",
            "--plan-sha256",
            self.sha(self.plan),
            "--user-scope-approval",
            "USER-SCOPE-APPROVAL-CONTINUE",
        )
        before = self.state()["scope_guard"]["rebaseline_candidate"]
        before_bytes = self.src.read_bytes()

        prepared = json.loads(self.cli("prepare-engineer-continuation").stdout)

        state = self.state()
        carried = state["scope_guard"]["rebaseline_candidate"]
        self.assertEqual(before, carried)
        self.assertEqual(before_bytes, self.src.read_bytes())
        lease = state["active_write_lease"]
        snapshot = state["lease_snapshots"][lease["lease_id"]]
        self.assertTrue(lease["rebaseline_carried"])
        self.assertTrue(snapshot["rebaseline_carried"])
        self.assertEqual(carried["snapshot"]["checkout"], snapshot["checkout"])
        self.assertEqual(carried["snapshot"]["line_proofs"], snapshot["line_proofs"])
        self.assertNotIn("checkout_text", snapshot)
        self.assertNotIn(prepared["capsule"]["path"], snapshot["checkout"])
        self.assertEqual(lease["lease_id"], prepared["lease"]["id"])
        self.assertEqual("dispatch_engineer", prepared["next_action"]["action"])

    def test_engineering_pass_releases_lease_but_manual_qa_remains_pending(self) -> None:
        self.initialize()
        result = self.engineer()
        self.assertEqual("slice_coverage_finalization", result["phase"])
        self.assertEqual("engineering_pass", result["last_engineer_outcome"])
        self.assertIsNone(result["active_write_lease"])
        self.assertEqual("complete", result["write_lease_history"][-1]["result"])
        self.assertNotEqual("pass", result["feature_verification_state"]["status"])

    def test_coverage_finalization_separates_implementation_from_manual_verification(self) -> None:
        result = self.implementation_complete()
        self.assertEqual("implementation_complete", result["phase"])
        self.assertEqual("pass", result["implementation_state"]["status"])
        self.assertEqual("pending", result["coverage"]["SLICE-001"]["state"]["manual"])
        self.assertFalse(result["coverage"]["SLICE-001"]["state"]["feature_verification_eligible"])
        handoff = json.loads((self.root / result["handoffs"][-1]["path"]).read_text(encoding="utf-8"))
        self.assertEqual(2, handoff["schema"])
        for field in ("decision_ids", "coverage_state", "documentation_state", "open_assumptions"):
            self.assertIn(field, handoff)

    def test_coverage_plan_lost_response_replay_is_exact_and_idempotent(self) -> None:
        self.initialize()
        manifest = self.coverage_manifest("coverage-replay-plan", "planned")
        report = self.artifact("verification", "coverage-replay-report")
        command = (
            "coverage-plan-complete", "--slice-id", "SLICE-001",
            "--coverage-manifest", manifest, "--report", report,
        )
        self.cli(*command)
        state_path = self.root / ".agentic-pipeline" / "state.json"
        after_first = state_path.read_bytes()
        self.cli(*command)
        self.assertEqual(after_first, state_path.read_bytes())
        mismatch = self.cli(
            "coverage-plan-complete", "--slice-id", "SLICE-001",
            "--coverage-manifest", manifest,
            "--report", self.artifact("verification", "coverage-replay-other"),
            expected=2,
        )
        self.assertIn("lost-response replay mismatch", mismatch.stderr)

    def test_coverage_finalize_lost_response_replay_is_exact(self) -> None:
        self.initialize()
        self.engineer()
        manifest = self.coverage_manifest("coverage-replay-final", "finalized")
        report = self.artifact("verification", "coverage-replay-final-report")
        command = (
            "coverage-finalize", "--scope-id", "SLICE-001",
            "--coverage-manifest", manifest,
            "--expected-actual-equality", "pass",
            "--mandatory-registration", "pass",
            "--automated-execution", "pass", "--report", report,
        )
        self.cli(*command)
        state_path = self.root / ".agentic-pipeline" / "state.json"
        after_first = state_path.read_bytes()
        self.cli(*command)
        self.assertEqual(after_first, state_path.read_bytes())
        mismatch = self.cli(
            "coverage-finalize", "--scope-id", "SLICE-001",
            "--coverage-manifest", manifest,
            "--expected-actual-equality", "pass",
            "--mandatory-registration", "pass",
            "--automated-execution", "pass", "--report",
            self.artifact("verification", "coverage-replay-final-other"),
            expected=2,
        )
        self.assertIn("lost-response replay mismatch", mismatch.stderr)

        state = self.state()
        state["coverage"]["SLICE-001"]["finalized_manifest"]["revision"] = "0" * 64
        state["phase"] = "slice_coverage_finalization"
        self.write_state(state)
        prior_revision = self.cli(
            "coverage-finalize", "--scope-id", "SLICE-001",
            "--coverage-manifest", manifest,
            "--expected-actual-equality", "pass",
            "--mandatory-registration", "pass",
            "--automated-execution", "pass", "--report",
            self.artifact("verification", "coverage-replay-prior-revision"),
            expected=2,
        )
        self.assertNotIn("lost-response replay mismatch", prior_revision.stderr)
        self.assertIn("controller-owned Engineer mechanics", prior_revision.stderr)

    def test_documentation_not_required_lost_response_replay_is_exact(self) -> None:
        state = self.implementation_complete()
        command = (
            "documentation-not-required", "--mode", "normative_pre_review",
            "--plan-sha256", state["development_plan"]["sha256"],
            "--policy-evidence", "POLICY-DOC-NONE",
        )
        self.cli(*command)
        state_path = self.root / ".agentic-pipeline" / "state.json"
        after_first = state_path.read_bytes()
        self.cli(*command)
        self.assertEqual(after_first, state_path.read_bytes())
        mismatch = self.cli(
            "documentation-not-required", "--mode", "normative_pre_review",
            "--plan-sha256", state["development_plan"]["sha256"],
            "--policy-evidence", "POLICY-OTHER", expected=2,
        )
        self.assertIn("lost-response replay mismatch", mismatch.stderr)

    def test_exact_identity_and_mandatory_set_mismatch_is_evidence_contract_violation(self) -> None:
        self.initialize()
        self.engineer()
        result = self.finalize_coverage(mismatch=True, expected=2)
        coverage = result["coverage"]["SLICE-001"]["state"]
        self.assertEqual("EVIDENCE_CONTRACT_VIOLATION", coverage["readiness_class"])
        self.assertEqual("invalidated", result["implementation_state"]["status"])
        findings = json.loads((self.root / ".agentic-pipeline" / "findings.json").read_text(encoding="utf-8"))
        self.assertEqual([], findings["items"])

    def test_scope_violation_opens_persistent_hold(self) -> None:
        self.initialize()
        result = self.engineer(forbidden_path=True)
        self.assertEqual("scope_expansion_hold", result["phase"])
        self.assertIsNotNone(result["active_write_lease"])
        self.assertTrue(result["scope_guard"]["hold"]["violations"])

    def test_decision_append_is_controller_ordered_and_lease_atomic(self) -> None:
        self.initialize()
        packet, authority_id, authority_digest = self.decision_packet()
        self.accept_user_authority(packet)
        capsule = self.capsule(
            "decision_recorder",
            "decision_recording",
            "recorder-1",
            allowed=(self.rel(self.ledger),),
            authorities=(f"not_applicable={authority_digest}:{authority_id}",),
            outputs=(self.rel(self.ledger),),
        )
        self.cli(
            "acquire-write-lease", "--role", "decision_recorder", "--phase", "decision_recording",
            "--write-scope", "decision-ledger", "--worker-id", "recorder-1", "--capsule", capsule,
        )
        semantic = self.artifact("verification", "decision-packet", packet)
        state = self.state()
        validated_items = runtime_controller.validate_decision_semantic_packet(
            self.root,
            state,
            packet,
            runtime_controller.read_json(self.root / capsule),
        )
        self.assertEqual(["DEC-001"], [item["decision_id"] for item in validated_items])
        report = self.artifact("verification", "decision-report")
        command = (
            "decision-record-complete", "--recorder-id", "recorder-1", "--lease-id",
            state["active_write_lease"]["lease_id"], "--capsule", capsule,
            "--semantic-packet", semantic, "--report", report,
        )
        self.cli(*command)
        ledger_after_first = self.ledger.read_bytes()
        self.cli(*command)
        self.assertEqual(ledger_after_first, self.ledger.read_bytes())
        mismatch = self.cli(
            "decision-record-complete", "--recorder-id", "recorder-1", "--lease-id",
            state["active_write_lease"]["lease_id"], "--capsule", capsule,
            "--semantic-packet", semantic, "--report",
            self.artifact("verification", "decision-other-report"), expected=2,
        )
        self.assertIn("lost-response replay mismatch", mismatch.stderr)
        result = self.full_status()
        self.assertEqual(["DEC-001"], result["decision_ledger"]["active_decision_ids"])
        entry = json.loads(self.ledger.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(1, entry["sequence"])
        self.assertIn("prior_ledger_sha256", entry)
        self.assertEqual(
            str(self.root / report),
            result["decision_ledger"]["projection"]["report_path"],
        )
        self.assertEqual(
            [],
            list(
                (self.root / "tests" / FEATURE / "verification" / "controller").glob(
                    "decision-*-append-receipt.json"
                )
            ),
        )
        self.assertIsNone(result["active_write_lease"])

    def test_qa_gate_preserves_implementation_and_uses_pending_exact_identities(self) -> None:
        state = self.implementation_complete()
        self.cli(
            "documentation-not-required", "--mode", "normative_pre_review", "--plan-sha256",
            state["development_plan"]["sha256"], "--policy-evidence", "POLICY-DOC-NONE",
        )
        self.prepare_qa_state()
        self.qa_probe(blocked=True)
        capsule = self.capsule("reviewer", "qa", "qa-1")
        state = self.state()
        result = json.loads(
            self.cli(
                "qa-complete", "--revision", state["revision"], "--product-revision", state["product_revision"],
                "--support-revision", state["support_revision"], "--evidence-revision", state["evidence_revision"],
                "--run-id", "qa-gated", "--worker-id", "qa-1", "--capsule", capsule,
                "--status", "blocked_user", "--manual-execution", self.qa_manual_artifact(gate="blocked_user"),
                "--pending-identity", "MANUAL-SLICE-001-RUNTIME", "--reason", "operator authorization required",
                "--report", self.artifact("qa", "qa-gated-report"),
            ).stdout
        )
        self.assertEqual("qa", result["phase"])
        self.assertEqual("pass", result["implementation_state"]["status"])
        self.assertEqual("pending", result["feature_verification_state"]["status"])

    def test_qa_pass_then_derived_not_required_sets_feature_verification(self) -> None:
        state = self.implementation_complete()
        self.cli(
            "documentation-not-required", "--mode", "normative_pre_review", "--plan-sha256",
            state["development_plan"]["sha256"], "--policy-evidence", "POLICY-DOC-NONE",
        )
        self.prepare_qa_state()
        self.qa_probe()
        capsule = self.capsule("reviewer", "qa", "qa-1")
        state = self.state()
        passed = json.loads(
            self.cli(
                "qa-complete", "--revision", state["revision"], "--product-revision", state["product_revision"],
                "--support-revision", state["support_revision"], "--evidence-revision", state["evidence_revision"],
                "--run-id", "qa-pass", "--worker-id", "qa-1", "--capsule", capsule,
                "--status", "pass", "--manual-execution", self.qa_manual_artifact(),
                "--report", self.artifact("qa", "qa-pass-report"),
            ).stdout
        )
        self.assertEqual("derived_documentation", passed["phase"])
        ready = json.loads(
            self.cli(
                "documentation-not-required", "--mode", "derived_post_qa", "--plan-sha256",
                state["development_plan_sha256"], "--policy-evidence", "POLICY-DOC-NONE",
            ).stdout
        )
        self.assertEqual("ready", ready["phase"])
        self.assertEqual("pass", ready["feature_verification_state"]["status"])

    def test_derived_support_change_preserves_qa_only_after_fresh_closure(self) -> None:
        state = self.implementation_complete()
        self.cli(
            "documentation-not-required", "--mode", "normative_pre_review", "--plan-sha256",
            state["development_plan"]["sha256"], "--policy-evidence", "POLICY-DOC-NONE",
        )
        self.prepare_qa_state()
        self.qa_probe()
        qa_capsule = self.capsule("reviewer", "qa", "qa-derived")
        state = self.state()
        self.cli(
            "qa-complete", "--revision", state["revision"], "--product-revision", state["product_revision"],
            "--support-revision", state["support_revision"], "--evidence-revision", state["evidence_revision"],
            "--run-id", "qa-derived-pass", "--worker-id", "qa-derived", "--capsule", qa_capsule,
            "--status", "pass", "--manual-execution", self.qa_manual_artifact(),
            "--report", self.artifact("qa", "qa-derived-report"),
        )
        support = self.root / "docs" / "operator.md"
        support.write_text("old operator handoff\n", encoding="utf-8")
        docs_capsule = self.capsule(
            "documentation_finisher", "derived_documentation", "docs-derived",
            allowed=(self.rel(support),),
        )
        self.cli(
            "acquire-write-lease", "--role", "documentation_finisher", "--phase", "derived_documentation",
            "--write-scope", "derived-support", "--worker-id", "docs-derived", "--capsule", docs_capsule,
        )
        support.write_text("operator handoff proven by QA scenario\n", encoding="utf-8")
        state = self.state()
        inventory = {key: list(value) for key, value in state["revision_inventory"].items()}
        inventory["support"] = [self.rel(support)]
        semantic_packet = {
            "schema": 1,
            "inventory_complete": True,
            "domain_inventory": inventory,
            "changes": [
                {
                    "path": self.rel(support), "domain": "support",
                    "change_id": "DOC-CHG-OPERATOR-HANDOFF",
                    "symbols": ["operator-handoff"],
                    "reason": "assigned_goal_effect: PRD-REQ-001, PRD-AC-001 | synchronize the QA-observed operator path", "change_kind": "modify",
                    "component": "operator-docs", "lifecycle_change": False, "ownership_change": False,
                    "public_contract_change": False, "requirement_ids": ["PRD-REQ-001"],
                    "acceptance_ids": ["PRD-AC-001"], "decision_ids": [], "touchpoint_id": None,
                }
            ],
            "open_assumptions": [],
        }
        semantic_path = self.artifact(
            "verification", "derived-semantic-packet", semantic_packet
        )
        qa_manual_relative = state["qa"]["manual_execution"]
        qa_manual = self.root / qa_manual_relative
        source_path = self.artifact(
            "verification",
            "derived-source-map",
            {
                "schema": 1,
                "mode": "derived_post_qa",
                "statements": [
                    {
                        "statement_id": "DOC-CHG-OPERATOR-HANDOFF",
                        "path": self.rel(support),
                        "source_kind": "qa",
                        "source_id": state["qa"]["run_id"],
                        "source_path": qa_manual_relative,
                        "source_sha256": self.sha(qa_manual),
                        "target_sha256": self.sha(support),
                    }
                ],
            },
        )
        state = self.state()
        bad_source_map = json.loads((self.root / source_path).read_text(encoding="utf-8"))
        bad_source_map["statements"][0]["source_sha256"] = "0" * 64
        bad_source_path = self.artifact("verification", "derived-source-map-stale", bad_source_map)
        before_rejection = (
            self.root / ".agentic-pipeline" / "state.json"
        ).read_bytes()
        rejected = self.cli(
            "documentation-complete", "--mode", "derived_post_qa", "--worker-id", "docs-derived",
            "--lease-id", state["active_write_lease"]["lease_id"], "--capsule", docs_capsule,
            "--semantic-packet", semantic_path, "--source-map", bad_source_path,
            "--report", self.artifact("verification", "derived-docs-rejected-report"), expected=2,
        )
        self.assertIn("source SHA is stale", rejected.stderr)
        self.assertEqual(
            before_rejection,
            (self.root / ".agentic-pipeline" / "state.json").read_bytes(),
        )
        for name, opaque_path in (
            ("qa-report", state["qa"]["report"]),
            ("capability-probe", state["qa_capability"]["report"]),
        ):
            opaque_map = json.loads(
                (self.root / source_path).read_text(encoding="utf-8")
            )
            opaque_map["statements"][0]["source_path"] = self.rel(Path(opaque_path))
            opaque_map["statements"][0]["source_sha256"] = self.sha(Path(opaque_path))
            opaque_source_path = self.artifact(
                "verification", f"derived-source-map-{name}", opaque_map
            )
            rejected = self.cli(
                "documentation-complete", "--mode", "derived_post_qa",
                "--worker-id", "docs-derived", "--lease-id",
                state["active_write_lease"]["lease_id"], "--capsule", docs_capsule,
                "--semantic-packet", semantic_path, "--source-map", opaque_source_path,
                "--report", self.artifact(
                    "verification", f"derived-docs-{name}-rejected-report"
                ), expected=2,
            )
            self.assertIn("controller-verified evidence", rejected.stderr)
            self.assertEqual(
                before_rejection,
                (self.root / ".agentic-pipeline" / "state.json").read_bytes(),
            )
        completed = json.loads(
            self.cli(
                "documentation-complete", "--mode", "derived_post_qa", "--worker-id", "docs-derived",
                "--lease-id", state["active_write_lease"]["lease_id"], "--capsule", docs_capsule,
                "--semantic-packet", semantic_path, "--source-map", source_path,
                "--report", self.artifact("verification", "derived-docs-report"),
            ).stdout
        )
        self.assertEqual("documentation_review", completed["phase"])
        self.assertEqual("pass", completed["qa"]["status"])
        reviewer_id = "qa-derived"
        review_capsule = self.capsule("reviewer", "documentation_review", reviewer_id)
        state = self.state()
        run_id = "docs-closure-1"
        report = self.documentation_closure_report(
            "docs-closure-report", run_id=run_id, reviewer_id=reviewer_id
        )
        credit = self.review_credit_manifest(
            "docs-closure-credit", reviewer_id, "documentation_closure"
        )
        self.assertEqual(
            str(self.root / report),
            runtime_controller.resolve_documentation_closure_report(
                self.root,
                state,
                report,
                run_id=run_id,
                reviewer_id=reviewer_id,
                status="pass",
            ),
        )
        runtime_controller.resolve_review_credit_manifest(
            self.root,
            state,
            credit,
            reviewer_id=reviewer_id,
            review_mode="documentation_closure",
        )
        before_rejection = (
            self.root / ".agentic-pipeline" / "state.json"
        ).read_bytes()
        rejected = self.cli(
            "documentation-review-complete", "--revision", state["revision"],
            "--product-revision", state["product_revision"], "--support-revision", state["support_revision"],
            "--evidence-revision", state["evidence_revision"], "--run-id", run_id,
            "--reviewer-id", reviewer_id, "--capsule", review_capsule, "--status", "pass",
            "--report", self.artifact("reviews", "docs-closure-invalid"),
            "--credit-manifest", credit, expected=2,
        )
        self.assertIn("exact schema-1 envelope", rejected.stderr)
        self.assertEqual(
            before_rejection,
            (self.root / ".agentic-pipeline" / "state.json").read_bytes(),
        )
        finding_id = "F-DOC-CLOSURE-PRODUCT-001"
        self.cli(
            "add-finding", "--id", finding_id, "--source", "review",
            "--finding-kind", "product", "--severity", "major",
            "--scope-relation", "current_feature_path",
            "--introduced-by-candidate", "false",
            "--production-reachability", "normal",
            "--blocks-acceptance-id", "PRD-AC-001",
            "--violates-required-invariant", "false",
            "--blocks-required-support-contract", "false",
            "--mandatory-core-acceptance-evidence-missing", "false",
            "--test-can-miss-product-defect", "false",
            "--title", "Documentation closure exposed a product mismatch",
            "--evidence",
            "assigned_acceptance_evidence: PRD-AC-001 | exact documentation closure component evidence",
            "--revision", state["revision"],
        )
        self.assertEqual("documentation_review", self.state()["phase"])
        blocked = self.cli(
            "documentation-review-complete", "--revision", state["revision"],
            "--product-revision", state["product_revision"],
            "--support-revision", state["support_revision"],
            "--evidence-revision", state["evidence_revision"], "--run-id", run_id,
            "--reviewer-id", reviewer_id, "--capsule", review_capsule, "--status", "pass",
            "--report", report, "--credit-manifest", credit, expected=2,
        )
        self.assertIn("remediation-required findings remain open", blocked.stderr)
        _, state_path, findings_path, persisted, findings = (
            runtime_controller.load_runtime(str(self.root))
        )
        finding = next(item for item in findings["items"] if item["id"] == finding_id)
        finding["status"] = "resolved"
        finding["resolved_revision"] = persisted["revision"]
        runtime_controller.save_runtime(state_path, findings_path, persisted, findings)
        closed = json.loads(
            self.cli(
                "documentation-review-complete", "--revision", state["revision"],
                "--product-revision", state["product_revision"], "--support-revision", state["support_revision"],
                "--evidence-revision", state["evidence_revision"], "--run-id", run_id,
                "--reviewer-id", reviewer_id, "--capsule", review_capsule, "--status", "pass",
                "--report", report, "--credit-manifest", credit,
            ).stdout
        )
        self.assertEqual("ready", closed["phase"])
        self.assertEqual("pass", closed["feature_verification_state"]["status"])
        replay = json.loads(
            self.cli(
                "documentation-review-complete", "--revision", state["revision"],
                "--product-revision", state["product_revision"], "--support-revision", state["support_revision"],
                "--evidence-revision", state["evidence_revision"], "--run-id", run_id,
                "--reviewer-id", reviewer_id, "--capsule", review_capsule, "--status", "pass",
                "--report", report, "--credit-manifest", credit,
            ).stdout
        )
        self.assertEqual("ready", replay["phase"])
        self.assertEqual(1, len(self.state()["documentation_review_runs"]))
        terminal = json.loads(self.cli("ready", expected=1).stdout)
        self.assertNotIn(
            "documentation closure report/credit receipt is stale or incomplete",
            terminal["reasons"],
        )
        (self.root / report).write_text("{}", encoding="utf-8")
        rejected_ready = json.loads(self.cli("ready", expected=1).stdout)
        self.assertIn(
            "documentation closure report/credit receipt is stale or incomplete",
            rejected_ready["reasons"],
        )

    def test_coverage_mapping_duplicate_acceptance_is_rejected(self) -> None:
        self.initialize()
        path = self.coverage_manifest("duplicate-ac", "planned")
        value = json.loads((self.root / path).read_text(encoding="utf-8"))
        value["ac_mappings"].append(dict(value["ac_mappings"][0]))
        (self.root / path).write_text(json.dumps(value), encoding="utf-8")
        self.cli(
            "coverage-plan-complete", "--slice-id", "SLICE-001", "--coverage-manifest", path,
            "--report", self.artifact("verification", "duplicate-report"), expected=2,
        )

    def test_feature_coverage_aggregate_unions_shared_ac_and_gap_wins(self) -> None:
        state = self.initialize()
        first_path = self.root / self.coverage_manifest(
            "shared-ac-slice-1", "finalized"
        )
        second_manifest = json.loads(first_path.read_text(encoding="utf-8"))
        second_manifest["slice_id"] = "SLICE-002"
        for group in ("expected_identities", "actual_identities"):
            for identity in second_manifest[group]:
                identity["identity_id"] = identity["identity_id"].replace(
                    "SLICE-001", "SLICE-002"
                )
                identity["slice_id"] = "SLICE-002"
        for mapping in second_manifest["ac_mappings"]:
            mapping["identity_ids"] = [
                identity_id.replace("SLICE-001", "SLICE-002")
                for identity_id in mapping["identity_ids"]
            ]
        for field in (
            "mandatory_expected_identity_ids",
            "mandatory_actual_identity_ids",
        ):
            second_manifest[field] = [
                identity_id.replace("SLICE-001", "SLICE-002")
                for identity_id in second_manifest[field]
            ]
        for group in ("automated_execution", "manual_execution"):
            for row in second_manifest[group]:
                row["identity_id"] = row["identity_id"].replace(
                    "SLICE-001", "SLICE-002"
                )
        second_manifest["summary"] = runtime_controller.coverage_summary_for_manifest(
            second_manifest
        )
        second_path = self.root / self.artifact(
            "verification", "shared-ac-slice-2", second_manifest
        )

        second_slice = json.loads(json.dumps(state["slices"]["SLICE-001"]))
        second_slice["id"] = "SLICE-002"
        state["slices"]["SLICE-002"] = second_slice
        state["ordered_slices"] = ["SLICE-001", "SLICE-002"]
        state["coverage"]["SLICE-002"] = runtime_controller.empty_coverage_scope()
        for scope_id, path in (
            ("SLICE-001", first_path),
            ("SLICE-002", second_path),
        ):
            state["coverage"][scope_id]["finalized_manifest"] = {
                "path": str(path),
                "sha256": self.sha(path),
            }

        _, mapped, _ = runtime_controller.write_feature_coverage_aggregate(
            self.root, state, suffix="shared-ac-mapped"
        )
        self.assertEqual(1, len(mapped["ac_mappings"]))
        self.assertEqual("mapped", mapped["ac_mappings"][0]["status"])
        self.assertEqual(
            [
                "AUTO-SLICE-001-CORE",
                "AUTO-SLICE-002-CORE",
                "MANUAL-SLICE-001-RUNTIME",
                "MANUAL-SLICE-002-RUNTIME",
            ],
            mapped["ac_mappings"][0]["identity_ids"],
        )

        second_manifest["ac_mappings"][0]["status"] = "gap"
        second_manifest["gaps"] = ["PRD-AC-001"]
        second_manifest["summary"] = runtime_controller.coverage_summary_for_manifest(
            second_manifest
        )
        second_path.write_text(json.dumps(second_manifest), encoding="utf-8")
        state["coverage"]["SLICE-002"]["finalized_manifest"]["sha256"] = self.sha(
            second_path
        )
        _, gap, _ = runtime_controller.write_feature_coverage_aggregate(
            self.root, state, suffix="shared-ac-gap"
        )
        self.assertEqual("gap", gap["ac_mappings"][0]["status"])

        second_manifest["ac_mappings"][0].update(
            {"status": "not_applicable", "identity_ids": [], "authority_id": "DEC-001"}
        )
        second_path.write_text(json.dumps(second_manifest), encoding="utf-8")
        state["coverage"]["SLICE-002"]["finalized_manifest"]["sha256"] = self.sha(
            second_path
        )
        with self.assertRaisesRegex(
            runtime_controller.PipelineError, "mixes not_applicable"
        ):
            runtime_controller.write_feature_coverage_aggregate(
                self.root, state, suffix="shared-ac-mixed-authority"
            )

    def test_not_applicable_coverage_requires_active_decision_authority(self) -> None:
        self.initialize()
        path = self.coverage_manifest("not-applicable", "planned")
        value = json.loads((self.root / path).read_text(encoding="utf-8"))
        value["ac_mappings"] = [
            {
                "acceptance_id": "PRD-AC-001",
                "status": "not_applicable",
                "identity_ids": [],
                "authority_id": "DEC-404",
            }
        ]
        (self.root / path).write_text(json.dumps(value), encoding="utf-8")
        result = self.cli(
            "coverage-plan-complete", "--slice-id", "SLICE-001", "--coverage-manifest", path,
            "--report", self.artifact("verification", "not-applicable-report"), expected=2,
        )
        self.assertIn("active accepted decision", result.stderr)

    def test_status_rehashes_inventory_and_rejects_unleased_product_drift(self) -> None:
        self.initialize(research=False)
        self.plan.write_text(self.plan.read_text(encoding="utf-8") + "\nplan drift\n", encoding="utf-8")
        result = self.cli("status", expected=2)
        self.assertIn("revision inventory drifted", result.stderr)

    def test_mutation_renders_validated_state_without_runtime_reload(self) -> None:
        required = "- RESEARCH-001 | question=confirm exact edit surface | paths=src/feature.py | exclusions=src/commerce/** | evidence=approved spec | stop=scope is exact"
        sentinel = "- research_not_required | reason=Exact authority and edit files answer the bounded question"
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8").replace(required, sentinel),
            encoding="utf-8",
        )
        self.write_planning_state()
        state = self.initialize(research=False)
        calls = 0
        original = runtime_controller.load_runtime

        def counted(*args, **kwargs):
            nonlocal calls
            calls += 1
            return original(*args, **kwargs)

        output = io.StringIO()
        with mock.patch.object(runtime_controller, "load_runtime", counted):
            with contextlib.redirect_stdout(output):
                result = runtime_controller.main(
                    [
                        "slice-research-not-required",
                        "--slice-id",
                        "SLICE-001",
                        "--base-revision",
                        state["revision"],
                        "--reason",
                        "Exact authority and edit files answer the bounded question",
                        "--project-root",
                        str(self.root),
                    ]
                )
        self.assertEqual(0, result)
        self.assertEqual(1, calls)
        self.assertEqual("slice_coverage_planning", json.loads(output.getvalue())["phase"])

    def test_command_inventory_is_cached_but_boundary_hashes_remain_live(self) -> None:
        state = self.initialize(research=False)
        calls = 0
        original = runtime_controller.subprocess.run

        def counted(*args, **kwargs):
            nonlocal calls
            if "ls-files" in args[0]:
                calls += 1
            return original(*args, **kwargs)

        runtime_controller._COMMAND_SOURCE_INVENTORY = {}
        try:
            with mock.patch.object(runtime_controller.subprocess, "run", counted):
                before = runtime_controller.checkout_snapshot(self.root, FEATURE, state)
                self.src.write_text("VALUE = 1\n", encoding="utf-8")
                after = runtime_controller.checkout_snapshot(self.root, FEATURE, state)
        finally:
            runtime_controller._COMMAND_SOURCE_INVENTORY = None
        self.assertEqual(1, calls)
        self.assertNotEqual(before[self.rel(self.src)], after[self.rel(self.src)])

    def test_status_reconciles_exact_lifecycle_dashboard_date_and_preserves_remediation(self) -> None:
        fixture = self.prepare_lifecycle_projection_recovery()
        before = fixture["state"]
        old_capsule = self.capsule(
            "engineer",
            "engineering",
            "engineer-before-lifecycle-refresh",
            allowed=(self.rel(fixture["dashboard"]),),
        )
        state = self.state()
        self.cli(
            "slice-scope-check", "--slice-id", "SLICE-001",
            "--base-revision", state["revision"], "--owner-id", "engineer-1",
        )
        before = self.state()
        preserved = {
            "phase": before["phase"],
            "active_remediation_batch": before["active_remediation_batch"],
            "remediation_queue": before["remediation_queue"],
            "engineering_owner_id": before["engineering_owner_id"],
            "owner_by_slice": before["owner_by_slice"],
            "product_revalidation": before["product_revalidation"],
            "convergence": before["convergence"],
        }
        self.apply_lifecycle_projection_drift(fixture)

        state_path = self.root / ".agentic-pipeline" / "state.json"
        findings_path = self.root / ".agentic-pipeline" / "findings.json"
        ledger_path = self.root / ".agentic-pipeline" / "decision-ledger.jsonl"
        disk_before_status = {
            path: path.read_bytes() if path.exists() else None
            for path in (state_path, findings_path, ledger_path)
        }
        status = json.loads(self.cli("status").stdout)
        self.assertEqual(
            disk_before_status,
            {
                path: path.read_bytes() if path.exists() else None
                for path in (state_path, findings_path, ledger_path)
            },
        )
        after_status = self.state()
        self.assertEqual("engineering", status["phase"])
        self.assertEqual("run_slice_scope_check", status["next_action"]["action"])
        self.assertEqual("SLICE-001", status["next_action"]["active_slice"])
        self.assertEqual(status["revision"], status["next_action"]["base_revision"])
        self.assertFalse(status["next_action"]["user_input_required"])
        for field, expected in preserved.items():
            self.assertEqual(expected, after_status[field], field)
        self.assertEqual(fixture["finding_ids"], status["active_ids"]["remediation_finding_ids"]["ids"])
        self.assertEqual(before["revision"], after_status["revision"])
        self.assertNotEqual(before["revision"], status["revision"])
        self.assertNotEqual(before["product_revision"], status["product_revision"])
        self.assertEqual(before["support_revision"], status["support_revision"])
        self.assertEqual(before["evidence_revision"], status["evidence_revision"])
        self.assertEqual([], after_status["lifecycle_projection_reconciliations"])

        self.cli(
            "slice-scope-check",
            "--slice-id",
            "SLICE-001",
            "--base-revision",
            status["revision"],
            "--owner-id",
            "engineer-1",
        )
        after = self.state()
        self.assertEqual(status["revision"], after["revision"])
        for field, expected in preserved.items():
            self.assertEqual(expected, after[field], field)

        reconciliations = after["lifecycle_projection_reconciliations"]
        self.assertEqual(1, len(reconciliations))
        receipt = reconciliations[0]
        self.assertEqual("LPR-0001", receipt["receipt_id"])
        self.assertEqual("lifecycle_generated_dashboard_date", receipt["kind"])
        self.assertEqual("2026-08-11", receipt["before_date"])
        self.assertEqual("2026-08-12", receipt["after_date"])
        self.assertEqual(fixture["finding_ids"], receipt["finding_ids"])
        self.assertTrue(receipt["invalidated_scope_pre_edit_check"])
        receipt_path = self.root / receipt["path"]
        self.assertTrue(receipt_path.is_file())
        self.assertEqual(receipt["sha256"], self.sha(receipt_path))
        receipt_value = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(before["revision"], receipt_value["before_revisions"]["revision"])
        self.assertEqual(after["revision"], receipt_value["after_revisions"]["revision"])

        old_record = next(
            item
            for item in after["context_capsules"]
            if item["path"] == old_capsule
        )
        self.assertEqual("stale", old_record["status"])
        self.assertIn("revision", self.cli("context-capsule-check", "--capsule", old_capsule, expected=2).stderr)
        old_credit = after["component_review_credits"][0]
        self.assertFalse(old_credit["valid"])
        self.assertEqual(
            "lifecycle_projection_product_hash_drift",
            old_credit["invalidation_reason"],
        )

        fresh_capsule = self.capsule(
            "engineer",
            "engineering",
            "engineer-after-lifecycle-refresh",
            allowed=(self.rel(fixture["dashboard"]),),
        )
        capsule_value = json.loads((self.root / fresh_capsule).read_text(encoding="utf-8"))
        self.assertEqual(fixture["finding_ids"], capsule_value["finding_ids"])
        evidence = {item["path"]: item["sha256"] for item in capsule_value["evidence"]}
        self.assertEqual(receipt["sha256"], evidence[receipt["path"]])

        first_state = self.state()
        self.cli("status")
        second_state = self.state()
        self.assertEqual(
            first_state["lifecycle_projection_reconciliations"],
            second_state["lifecycle_projection_reconciliations"],
        )
        self.assertEqual(first_state["revision"], second_state["revision"])

    def assert_lifecycle_projection_drift_rejected(
        self, fixture: dict, expected_message: str = "revision inventory drifted"
    ) -> None:
        frozen = self.state()
        result = self.cli("status", expected=2)
        self.assertIn(expected_message, result.stderr)
        after = self.state()
        self.assertEqual(frozen["revision"], after["revision"])
        self.assertEqual(
            frozen.get("lifecycle_projection_reconciliations", []),
            after.get("lifecycle_projection_reconciliations", []),
        )

    def test_lifecycle_reconciliation_rejects_second_product_path_drift(self) -> None:
        fixture = self.prepare_lifecycle_projection_recovery()
        self.apply_lifecycle_projection_drift(fixture)
        self.src.write_text("VALUE = 404\n", encoding="utf-8")
        self.assert_lifecycle_projection_drift_rejected(fixture)

    def test_lifecycle_reconciliation_rejects_dashboard_title_edit(self) -> None:
        fixture = self.prepare_lifecycle_projection_recovery()
        self.apply_lifecycle_projection_drift(fixture, title="Manually Edited Title")
        self.assert_lifecycle_projection_drift_rejected(fixture)

    def test_lifecycle_reconciliation_rejects_dashboard_status_edit(self) -> None:
        fixture = self.prepare_lifecycle_projection_recovery()
        self.apply_lifecycle_projection_drift(fixture, status="🟩 Готова")
        self.assert_lifecycle_projection_drift_rejected(fixture)

    def test_lifecycle_reconciliation_rejects_dashboard_link_edit(self) -> None:
        fixture = self.prepare_lifecycle_projection_recovery()
        self.apply_lifecycle_projection_drift(fixture, link="./wrong-feature/")
        self.assert_lifecycle_projection_drift_rejected(fixture)

    def test_lifecycle_reconciliation_rejects_manifest_date_mismatch(self) -> None:
        fixture = self.prepare_lifecycle_projection_recovery()
        self.apply_lifecycle_projection_drift(
            fixture, manifest_updated_at="2026-08-13T05:02:23+00:00"
        )
        self.assert_lifecycle_projection_drift_rejected(fixture)

    def test_lifecycle_reconciliation_rejects_support_drift(self) -> None:
        fixture = self.prepare_lifecycle_projection_recovery()
        self.apply_lifecycle_projection_drift(fixture)
        fixture["support"].write_text("support-v2\n", encoding="utf-8")
        self.assert_lifecycle_projection_drift_rejected(fixture)

    def test_lifecycle_reconciliation_rejects_evidence_drift(self) -> None:
        fixture = self.prepare_lifecycle_projection_recovery()
        self.apply_lifecycle_projection_drift(fixture)
        self.test_source.write_text("def test_feature(): assert False\n", encoding="utf-8")
        self.assert_lifecycle_projection_drift_rejected(fixture)

    def test_lifecycle_reconciliation_rejects_active_lease(self) -> None:
        fixture = self.prepare_lifecycle_projection_recovery()
        state = self.state()
        state["active_write_lease"] = {"status": "active", "lease_id": "LEASE-BUSY"}
        self.write_state(state)
        self.apply_lifecycle_projection_drift(fixture)
        self.assert_lifecycle_projection_drift_rejected(fixture)

    def test_lifecycle_reconciliation_rejects_pending_engineer_completion(self) -> None:
        fixture = self.prepare_lifecycle_projection_recovery()
        state = self.state()
        state["pending_engineer_completion"] = {"run_id": "RUN-PENDING"}
        self.write_state(state)
        self.apply_lifecycle_projection_drift(fixture)
        self.assert_lifecycle_projection_drift_rejected(fixture)

    def test_lifecycle_reconciliation_rejects_non_engineering_phase(self) -> None:
        fixture = self.prepare_lifecycle_projection_recovery()
        state = self.state()
        state["phase"] = "convergence"
        self.write_state(state)
        self.apply_lifecycle_projection_drift(fixture)
        self.assert_lifecycle_projection_drift_rejected(fixture)

    def test_lifecycle_reconciliation_rejects_mismatched_remediation_queue(self) -> None:
        fixture = self.prepare_lifecycle_projection_recovery()
        state = self.state()
        state["remediation_queue"][0]["finding_ids"] = ["TF0008-CONV-001"]
        self.write_state(state)
        self.apply_lifecycle_projection_drift(fixture)
        self.assert_lifecycle_projection_drift_rejected(fixture)

    def test_lifecycle_reconciliation_rejects_incomplete_open_finding_batch(self) -> None:
        fixture = self.prepare_lifecycle_projection_recovery()
        self.inject_canonical_finding(
            {
                "id": "TF0008-CONV-005",
                "status": "open",
                "severity": "major",
                "source": "convergence",
                "revision": self.state()["revision"],
                "finding_kind": "product",
                "origin_slice": "SLICE-001",
                "remediation_route": "SLICE-001",
                "blocking": True,
                "remediation_required": True,
            }
        )
        self.apply_lifecycle_projection_drift(fixture)
        self.assert_lifecycle_projection_drift_rejected(fixture)

    def test_lifecycle_reconciliation_rejects_multiple_active_feature_manifests(self) -> None:
        fixture = self.prepare_lifecycle_projection_recovery()
        second = (
            fixture["dashboard"].parent / "another-active-feature" / "feature.json"
        )
        second.parent.mkdir(parents=True, exist_ok=True)
        second.write_text(
            json.dumps(
                {
                    "schemaVersion": 2,
                    "id": "TF-9999",
                    "slug": "another-active-feature",
                    "activity": "active",
                    "startedAt": "2026-08-12T00:00:00+00:00",
                    "updatedAt": "2026-08-12T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )
        self.apply_lifecycle_projection_drift(fixture)
        self.assert_lifecycle_projection_drift_rejected(fixture)

    def test_lifecycle_reconciliation_recovers_exact_orphan_receipt_after_crash(self) -> None:
        fixture = self.prepare_lifecycle_projection_recovery()
        self.apply_lifecycle_projection_drift(fixture)
        original = self.state()
        findings = json.loads(
            (self.root / ".agentic-pipeline" / "findings.json").read_text(encoding="utf-8")
        )
        in_memory = json.loads(json.dumps(original))
        computed = runtime_controller.compute_inventory_revisions(self.root, in_memory)
        self.assertTrue(
            runtime_controller.try_reconcile_lifecycle_projection_drift(
                self.root, in_memory, findings, computed
            )
        )
        self.assertEqual([], self.state()["lifecycle_projection_reconciliations"])
        receipt_path = (
            self.root
            / "tests"
            / FEATURE
            / "verification"
            / "controller"
            / "lifecycle-projection-reconciliation-0001.json"
        )
        pending_receipt = in_memory["pending_lifecycle_projection_receipt"]
        self.assertEqual(self.rel(receipt_path), pending_receipt["path"])
        runtime_controller.write_json(receipt_path, pending_receipt["value"])
        self.assertTrue(receipt_path.is_file())

        self.cli("status")
        self.assertEqual(0, len(self.state()["lifecycle_projection_reconciliations"]))
        self.cli(
            "slice-scope-check", "--slice-id", "SLICE-001",
            "--base-revision", in_memory["revision"],
            "--owner-id", original["engineering_owner_id"],
        )
        recovered = self.state()
        self.assertEqual(1, len(recovered["lifecycle_projection_reconciliations"]))
        self.assertEqual("LPR-0001", recovered["lifecycle_projection_reconciliations"][0]["receipt_id"])
        self.cli("status")
        self.assertEqual(
            1, len(self.state()["lifecycle_projection_reconciliations"])
        )

    def test_lifecycle_reconciliation_rejects_tampered_orphan_receipt_replay(self) -> None:
        fixture = self.prepare_lifecycle_projection_recovery()
        self.apply_lifecycle_projection_drift(fixture)
        original = self.state()
        findings = json.loads(
            (self.root / ".agentic-pipeline" / "findings.json").read_text(encoding="utf-8")
        )
        in_memory = json.loads(json.dumps(original))
        computed = runtime_controller.compute_inventory_revisions(self.root, in_memory)
        self.assertTrue(
            runtime_controller.try_reconcile_lifecycle_projection_drift(
                self.root, in_memory, findings, computed
            )
        )
        receipt_path = (
            self.root
            / "tests"
            / FEATURE
            / "verification"
            / "controller"
            / "lifecycle-projection-reconciliation-0001.json"
        )
        pending_receipt = in_memory["pending_lifecycle_projection_receipt"]
        self.assertEqual(self.rel(receipt_path), pending_receipt["path"])
        runtime_controller.write_json(receipt_path, pending_receipt["value"])
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["finding_ids"] = ["REPLAYED-DIFFERENT-BATCH"]
        receipt_path.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        self.assert_lifecycle_projection_drift_rejected(fixture)

    def test_legacy_lifecycle_reconciliation_accepts_bounded_unique_candidate(self) -> None:
        fixture = self.prepare_lifecycle_projection_recovery()
        state = self.state()
        state["revision_records"] = None
        state["lifecycle_projection_guard"] = None
        self.write_state(state)
        self.apply_lifecycle_projection_drift(fixture)
        self.cli("status")
        self.assertEqual(0, len(self.state()["lifecycle_projection_reconciliations"]))

    def test_legacy_lifecycle_reconciliation_rejects_excessive_date_candidates(self) -> None:
        fixture = self.prepare_lifecycle_projection_recovery()
        state = self.state()
        state["revision_records"] = None
        state["lifecycle_projection_guard"] = None
        self.write_state(state)
        manifest = json.loads(fixture["manifest"].read_text(encoding="utf-8"))
        manifest["startedAt"] = "1900-01-01T00:00:00+00:00"
        manifest["updatedAt"] = "2026-08-12T05:02:23+00:00"
        fixture["manifest"].write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        fixture["dashboard"].write_text(
            self.lifecycle_dashboard_text("2026-08-12"), encoding="utf-8"
        )
        self.assert_lifecycle_projection_drift_rejected(fixture)

    def test_ready_rehashes_inventory_before_considering_phase(self) -> None:
        self.initialize(research=False)
        self.plan.write_text(self.plan.read_text(encoding="utf-8") + "\nplan drift\n", encoding="utf-8")
        result = self.cli("ready", expected=2)
        self.assertIn("revision inventory drifted", result.stderr)

    def test_context_gate_rehashes_inventory_before_capsule_validation(self) -> None:
        self.initialize(research=False)
        self.plan.write_text(self.plan.read_text(encoding="utf-8") + "\nplan drift\n", encoding="utf-8")
        result = self.cli("context-capsule-check", "--capsule", "missing.json", expected=2)
        self.assertIn("revision inventory drifted", result.stderr)

    def test_state_revision_tampering_cannot_hide_current_inventory(self) -> None:
        self.initialize(research=False)
        state = self.state()
        state["revision"] = "0" * 64
        self.write_state(state)
        result = self.cli("status", expected=2)
        self.assertIn("revision inventory drifted", result.stderr)

    def test_ledger_semantics_are_revalidated_even_when_recorded_hash_is_rewritten(self) -> None:
        self.initialize()
        packet, reference, digest = self.decision_packet()
        self.accept_user_authority(packet)
        capsule = self.capsule(
            "decision_recorder",
            "decision_recording",
            "recorder-ledger",
            allowed=(self.rel(self.ledger),),
            authorities=(f"not_applicable={digest}:{reference}",),
            outputs=(self.rel(self.ledger),),
        )
        self.cli(
            "acquire-write-lease", "--role", "decision_recorder", "--phase", "decision_recording",
            "--write-scope", "ledger", "--worker-id", "recorder-ledger", "--capsule", capsule,
        )
        state = self.state()
        self.cli(
            "decision-record-complete", "--recorder-id", "recorder-ledger", "--lease-id",
            state["active_write_lease"]["lease_id"], "--capsule", capsule,
            "--semantic-packet", self.artifact("verification", "ledger-semantic", packet),
            "--report", self.artifact("verification", "ledger-report"),
        )
        entry = json.loads(self.ledger.read_text(encoding="utf-8"))
        entry["authority"]["sha256"] = "f" * 64
        tampered_raw = (
            json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n"
        )
        self.ledger.write_text(tampered_raw, encoding="utf-8")
        state = self.state()
        state["decision_ledger"]["sha256"] = self.sha(self.ledger)
        projection = state["decision_ledger"]["projection"]
        projection["append_jsonl"] = tampered_raw
        projection["append_sha256"] = hashlib.sha256(
            tampered_raw.encode("utf-8")
        ).hexdigest()
        projection["target_sha256"] = state["decision_ledger"]["sha256"]
        self.write_state(state)
        result = self.cli("status", expected=2)
        self.assertIn("acceptance receipt", result.stderr)

    def test_scope_rebaseline_revokes_old_lease_and_requires_fresh_capsule(self) -> None:
        self.initialize()
        self.engineer(forbidden_path=True)
        held = self.state()
        old_lease = held["active_write_lease"]["lease_id"]
        old_capsule = held["lease_snapshots"][old_lease]["capsule_path"]
        text = self.plan.read_text(encoding="utf-8")
        text = text.replace("- editable_paths: src/feature.py", "- editable_paths: src/feature.py, src/commerce/driveby.py")
        text = text.replace("- excluded_components: commerce", "- excluded_components: payments")
        text = text.replace("- excluded_paths: src/commerce/**", "- excluded_paths: src/payments/**")
        self.plan.write_text(text, encoding="utf-8")
        planning = json.loads((self.root / ".agentic-pipeline" / "development-plan-state.json").read_text(encoding="utf-8"))
        planning["approval"]["approved_sha256"] = self.sha(self.plan)
        (self.root / ".agentic-pipeline" / "development-plan-state.json").write_text(json.dumps(planning), encoding="utf-8")
        frozen = (self.root / ".agentic-pipeline" / "state.json").read_bytes()
        rejected = self.cli(
            "rebaseline-scope", "--plan-sha256", self.sha(self.plan),
            "--user-scope-approval", "FREE-FORM-TOKEN", expected=2,
        )
        self.assertIn("immutable user authority receipt", rejected.stderr)
        self.assertEqual(frozen, (self.root / ".agentic-pipeline" / "state.json").read_bytes())
        self.accept_scope_authority("USER-SCOPE-APPROVAL-1")
        result = json.loads(self.cli(
            "rebaseline-scope", "--plan-sha256", self.sha(self.plan),
            "--user-scope-approval", "USER-SCOPE-APPROVAL-1",
        ).stdout)
        history_count = len(self.state()["scope_guard"]["rebaseline_history"])
        replay = json.loads(self.cli(
            "rebaseline-scope", "--plan-sha256", self.sha(self.plan),
            "--user-scope-approval", "USER-SCOPE-APPROVAL-1",
        ).stdout)
        self.assertEqual(result["phase"], replay["phase"])
        self.assertEqual(
            history_count, len(self.state()["scope_guard"]["rebaseline_history"])
        )
        result = self.full_status()
        self.assertIsNone(result["active_write_lease"])
        self.assertEqual("revoked", result["write_lease_history"][-1]["status"])
        self.assertIsNotNone(result["scope_guard"]["rebaseline_candidate"])
        self.cli("context-capsule-check", "--capsule", old_capsule, expected=2)
        fresh_capsule = self.capsule(
            "engineer", "slice_engineering", "engineer-1",
            allowed=(
                "src/feature.py",
                "src/commerce/driveby.py",
            ),
        )
        state = self.state()
        self.cli(
            "slice-scope-check", "--slice-id", "SLICE-001", "--base-revision", state["revision"],
            "--owner-id", "engineer-1",
        )
        self.cli(
            "acquire-write-lease", "--role", "engineer", "--phase", "slice_engineering",
            "--write-scope", "SLICE-001", "--worker-id", "engineer-1", "--capsule", fresh_capsule,
        )
        carried = self.state()["scope_guard"]["rebaseline_candidate"]
        (self.root / carried["engineer_report"]).write_text(
            json.dumps(self.dirty_candidate_report()), encoding="utf-8"
        )
        completed = json.loads(self.cli(
            "engineer-complete", "--run-id", carried["run_id"], "--owner-id", "engineer-1",
            "--lease-id", self.state()["active_write_lease"]["lease_id"], "--capsule", fresh_capsule,
            "--slice-id", "SLICE-001", "--machine-checks", "pass",
            "--diff-inspection", "pass", "--semantic-handoff", carried["semantic_report"],
            "--report", carried["engineer_report"], "--scope-approval", "USER-SCOPE-APPROVAL-1",
        ).stdout)
        self.assertEqual("slice_coverage_finalization", completed["phase"])
        self.assertIsNone(completed["active_write_lease"])

    def test_scope_rebaseline_rejects_checkout_that_is_neither_candidate_nor_rollback(self) -> None:
        self.initialize()
        self.engineer(forbidden_path=True)
        unrelated = self.root / "src" / "unexpected.py"
        unrelated.write_text("UNEXPECTED = True\n", encoding="utf-8")
        self.accept_scope_authority("USER-SCOPE-APPROVAL-2")
        result = self.cli(
            "rebaseline-scope", "--plan-sha256", self.sha(self.plan),
            "--user-scope-approval", "USER-SCOPE-APPROVAL-2", expected=2,
        )
        self.assertIn("either the preserved candidate or a recoverable rollback", result.stderr)

    def test_product_completion_increments_consecutive_change_circuit(self) -> None:
        self.initialize()
        result = self.engineer()
        self.assertEqual(1, result["iteration_control"]["consecutive_product_changes"])

    def test_product_completion_initializes_validation_on_exact_new_identities(self) -> None:
        self.initialize()
        before = self.state()["revision"]
        result = self.engineer()
        self.assertNotEqual(before, result["revision"])
        for key in ("revision", "product_revision", "support_revision", "evidence_revision"):
            self.assertEqual(result[key], result["machine_checks"][key])

    def test_finalized_coverage_cannot_change_planned_body_without_amendment(self) -> None:
        self.initialize()
        self.engineer()
        path = self.coverage_manifest("coverage-body-change", "finalized")
        value = json.loads((self.root / path).read_text(encoding="utf-8"))
        value["expected_identities"][0]["planned_assertion_or_observation"] = "changed after planning"
        value["actual_identities"][0]["planned_assertion_or_observation"] = "changed after planning"
        (self.root / path).write_text(json.dumps(value), encoding="utf-8")
        result = self.cli(
            "coverage-finalize", "--scope-id", "SLICE-001", "--coverage-manifest", path, "--expected-actual-equality", "pass",
            "--mandatory-registration", "pass", "--automated-execution", "pass",
            "--report", self.artifact("verification", "coverage-body-change-report"), expected=2,
        )
        self.assertIn("without an authorized", result.stderr)

    def test_coverage_rejects_one_way_acceptance_mapping(self) -> None:
        self.initialize()
        path = self.coverage_manifest("coverage-reverse", "planned")
        value = json.loads((self.root / path).read_text(encoding="utf-8"))
        value["ac_mappings"][0]["identity_ids"].remove("MANUAL-SLICE-001-RUNTIME")
        (self.root / path).write_text(json.dumps(value), encoding="utf-8")
        result = self.cli(
            "coverage-plan-complete", "--slice-id", "SLICE-001", "--coverage-manifest", path,
            "--report", self.artifact("verification", "coverage-reverse-report"), expected=2,
        )
        self.assertIn("reverse AC mapping", result.stderr)

    def test_coverage_rejects_identity_with_wrong_slice_coordinate(self) -> None:
        self.initialize()
        path = self.coverage_manifest("coverage-wrong-slice", "planned")
        value = json.loads((self.root / path).read_text(encoding="utf-8"))
        value["expected_identities"][0]["slice_id"] = "SLICE-999"
        (self.root / path).write_text(json.dumps(value), encoding="utf-8")
        result = self.cli(
            "coverage-plan-complete", "--slice-id", "SLICE-001", "--coverage-manifest", path,
            "--report", self.artifact("verification", "coverage-slice-report"), expected=2,
        )
        self.assertIn("slice_id", result.stderr)

    def test_coverage_rejects_empty_automated_command(self) -> None:
        self.initialize()
        self.engineer()
        path = self.coverage_manifest("coverage-command", "finalized")
        value = json.loads((self.root / path).read_text(encoding="utf-8"))
        value["automated_execution"][0]["command"] = ""
        (self.root / path).write_text(json.dumps(value), encoding="utf-8")
        result = self.cli(
            "coverage-finalize", "--scope-id", "SLICE-001", "--coverage-manifest", path, "--expected-actual-equality", "pass",
            "--mandatory-registration", "pass", "--automated-execution", "pass",
            "--report", self.artifact("verification", "coverage-command-report"), expected=2,
        )
        self.assertIn("non-empty command", result.stderr)

    def test_coverage_rejects_stale_automated_evidence_sha(self) -> None:
        self.initialize()
        self.engineer()
        path = self.coverage_manifest("coverage-evidence", "finalized")
        value = json.loads((self.root / path).read_text(encoding="utf-8"))
        value["automated_execution"][0]["evidence_sha256"] = "0" * 64
        (self.root / path).write_text(json.dumps(value), encoding="utf-8")
        result = self.cli(
            "coverage-finalize", "--scope-id", "SLICE-001", "--coverage-manifest", path, "--expected-actual-equality", "pass",
            "--mandatory-registration", "pass", "--automated-execution", "pass",
            "--report", self.artifact("verification", "coverage-evidence-report"), expected=2,
        )
        self.assertIn("evidence SHA mismatch", result.stderr)

    def test_decision_rejects_user_digest_that_does_not_bind_statement(self) -> None:
        self.initialize()
        packet, reference, digest = self.decision_packet()
        self.accept_user_authority(packet)
        packet["items"][0]["authority"]["sha256"] = "a" * 64
        capsule = self.capsule(
            "decision_recorder", "decision_recording", "recorder-digest",
            allowed=(self.rel(self.ledger),), authorities=(f"not_applicable={digest}:{reference}",),
            outputs=(self.rel(self.ledger),),
        )
        self.cli(
            "acquire-write-lease", "--role", "decision_recorder", "--phase", "decision_recording",
            "--write-scope", "ledger", "--worker-id", "recorder-digest", "--capsule", capsule,
        )
        state = self.state()
        result = self.cli(
            "decision-record-complete", "--recorder-id", "recorder-digest", "--lease-id",
            state["active_write_lease"]["lease_id"], "--capsule", capsule,
            "--semantic-packet", self.artifact("verification", "bad-digest-packet", packet),
            "--report", self.artifact("verification", "bad-digest-report"), expected=2,
        )
        self.assertIn("acceptance receipt", result.stderr)

    def test_decision_requires_exact_authority_assignment_in_capsule(self) -> None:
        self.initialize()
        packet, _, _ = self.decision_packet()
        self.accept_user_authority(packet)
        state = self.state()
        result = self.cli(
            "context-capsule-create", "--role", "decision_recorder",
            "--phase", "decision_recording", "--worker-id", "recorder-assignment",
            "--plan-sha256", state["development_plan_sha256"],
            "--revision", state["revision"], "--authority",
            f"{self.rel(self.prd)}={self.sha(self.prd)}:PRD-REQ-001,PRD-AC-001",
            "--allowed-path", self.rel(self.ledger), "--output-path", self.rel(self.ledger),
            "--stop-condition", "record only assigned decisions",
            "--max-authority-files", "5", "--max-evidence-files", "5",
            "--max-total-files", "10", "--max-payload-bytes", "500000",
            "--max-estimated-tokens", "200000", "--output",
            f"tests/{FEATURE}/verification/unassigned-decision-capsule.json", expected=2,
        )
        self.assertIn("exactly one assigned authority selector", result.stderr)

    def test_decision_specification_authority_selector_is_reachable(self) -> None:
        self.initialize()
        state = self.state()
        selector = "document_type: technical-specification"
        output = f"tests/{FEATURE}/verification/spec-authority-capsule.json"
        args = [
            "context-capsule-create", "--role", "decision_recorder",
            "--phase", "decision_recording", "--worker-id", "recorder-spec",
            "--plan-sha256", state["development_plan_sha256"],
            "--revision", state["revision"], "--allowed-path", self.rel(self.ledger),
            "--output-path", self.rel(self.ledger),
            "--stop-condition", "record only the assigned specification decision",
            "--max-authority-files", "5", "--max-evidence-files", "5",
            "--max-total-files", "10", "--max-payload-bytes", "500000",
            "--max-estimated-tokens", "200000", "--output", output,
        ]
        for path, digest in sorted(
            runtime_controller.capsule_exact_authority(self.root, state).items()
        ):
            suffix = f":{selector}" if path == self.rel(self.spec) else ""
            args.extend(("--authority", f"{path}={digest}{suffix}"))
        self.cli(*args)
        capsule = json.loads((self.root / output).read_text(encoding="utf-8"))
        packet = {
            "schema": 1,
            "items": [{
                "schema": 1,
                "decision_id": "DEC-SPEC-001",
                "status": "accepted",
                "statement": "Use the specification-defined boundary.",
                "rationale": "The approved specification is exact authority.",
                "consequences": [],
                "scope_ids": ["PRD-AC-001", "SLICE-001"],
                "authority": {
                    "kind": "specification",
                    "reference": "approved specification frontmatter",
                    "path": self.rel(self.spec),
                    "sha256": self.sha(self.spec),
                    "section_or_id": selector,
                },
                "supersedes": [],
            }],
        }
        items = runtime_controller.validate_decision_semantic_packet(
            self.root, state, packet, capsule
        )
        self.assertEqual("DEC-SPEC-001", items[0]["decision_id"])

    def test_decision_ledger_append_requires_capsule_output_authority(self) -> None:
        self.initialize()
        packet, reference, digest = self.decision_packet()
        self.accept_user_authority(packet)
        capsule = self.capsule(
            "decision_recorder", "decision_recording", "recorder-output",
            allowed=(self.rel(self.ledger),), authorities=(f"not_applicable={digest}:{reference}",),
        )
        self.cli(
            "acquire-write-lease", "--role", "decision_recorder", "--phase", "decision_recording",
            "--write-scope", "ledger", "--worker-id", "recorder-output", "--capsule", capsule,
        )
        state = self.state()
        result = self.cli(
            "decision-record-complete", "--recorder-id", "recorder-output", "--lease-id",
            state["active_write_lease"]["lease_id"], "--capsule", capsule,
            "--semantic-packet", self.artifact("verification", "output-packet", packet),
            "--report", self.artifact("verification", "output-report"), expected=2,
        )
        self.assertIn("ledger append is outside", result.stderr)

    def test_decision_adr_is_confined_to_documentation_paths(self) -> None:
        self.initialize()
        packet, reference, digest = self.decision_packet()
        self.accept_user_authority(packet)
        bad_adr = "src/adr.md"
        capsule = self.capsule(
            "decision_recorder", "decision_recording", "recorder-adr",
            allowed=(self.rel(self.ledger), bad_adr),
            authorities=(f"not_applicable={digest}:{reference}",),
            outputs=(self.rel(self.ledger), bad_adr),
        )
        self.cli(
            "acquire-write-lease", "--role", "decision_recorder", "--phase", "decision_recording",
            "--write-scope", "ledger", "--worker-id", "recorder-adr", "--capsule", capsule,
        )
        adr_path = self.root / bad_adr
        adr_path.write_text("# ADR\n", encoding="utf-8")
        state = self.state()
        result = self.cli(
            "decision-record-complete", "--recorder-id", "recorder-adr", "--lease-id",
            state["active_write_lease"]["lease_id"], "--capsule", capsule,
            "--semantic-packet", self.artifact("verification", "adr-packet", packet),
            "--adr-path", bad_adr, "--report", self.artifact("verification", "adr-report"), expected=2,
        )
        self.assertIn("confined to repository documentation", result.stderr)

    def test_engineer_rejects_product_path_outside_lease_allowlist(self) -> None:
        self.initialize()
        capsule = self.begin_engineer_lease(allowed=("src/feature.py",))
        path = self.root / "src" / "unauthorized.py"
        path.write_text("VALUE = 1\n", encoding="utf-8")
        result = self.fail_engineer_completion(capsule, self.semantic_packet_for_change(path))
        self.assertIn("outside the active lease allowlist", result.stderr)

    def test_engineer_rejects_symbol_outside_lease_allowlist(self) -> None:
        self.initialize()
        capsule = self.begin_engineer_lease(allowed=("src/feature.py",), symbols=("SAFE",))
        self.src.write_text("VALUE = 2\n", encoding="utf-8")
        result = self.fail_engineer_completion(capsule, self.semantic_packet_for_change(self.src))
        self.assertIn("symbols are outside", result.stderr)

    def test_engineer_rejects_path_named_by_lease_exclusion(self) -> None:
        self.initialize()
        capsule = self.begin_engineer_lease(
            allowed=("src/feature.py",), exclusions=("src/feature.py",)
        )
        self.src.write_text("VALUE = 3\n", encoding="utf-8")
        result = self.fail_engineer_completion(capsule, self.semantic_packet_for_change(self.src))
        self.assertIn("violates active lease exclusion", result.stderr)

    def test_engineer_rejects_change_without_approved_requirement_mapping(self) -> None:
        self.initialize()
        capsule = self.begin_engineer_lease(allowed=("src/feature.py",))
        self.src.write_text("VALUE = 4\n", encoding="utf-8")
        semantic = self.semantic_packet_for_change(self.src, requirement_ids=[])
        result = self.fail_engineer_completion(capsule, semantic)
        self.assertIn("approved PRD-REQ subset", result.stderr)

    def test_engineer_role_cannot_write_derived_support_domain(self) -> None:
        self.initialize()
        support = self.root / "docs" / "operator.md"
        capsule = self.begin_engineer_lease(allowed=(self.rel(support),))
        support.write_text("operator text\n", encoding="utf-8")
        semantic = self.semantic_packet_for_change(support, domain="support")
        result = self.fail_engineer_completion(capsule, semantic)
        self.assertIn("cannot change the support domain", result.stderr)

    def test_qa_worker_identity_must_be_independent_from_engineering(self) -> None:
        state = self.ready_for_qa()
        capsule = self.capsule("reviewer", "qa", "engineer-1")
        result = self.cli(
            "qa-complete", "--revision", state["revision"], "--product-revision", state["product_revision"],
            "--support-revision", state["support_revision"], "--evidence-revision", state["evidence_revision"],
            "--run-id", "qa-reused", "--worker-id", "engineer-1", "--capsule", capsule,
            "--status", "pass", "--manual-execution", self.qa_manual_artifact(),
            "--report", self.artifact("qa", "qa-reused-report"), expected=2,
        )
        self.assertIn("independent of every writer", result.stderr)

    def test_ambiguous_verifier_history_fails_closed(self) -> None:
        state = {
            "worker_budget": {
                "records": [
                    {"role": "convergence_audit", "worker_id": "verifier-a"},
                    {"role": "full_review", "worker_id": "verifier-b"},
                ]
            }
        }
        with self.assertRaisesRegex(
            runtime_controller.PipelineError, "Verifier assignment history"
        ):
            runtime_controller.require_verifier_assignment(state, "verifier-c")

    def test_one_sequential_verifier_can_complete_convergence_review_and_qa(self) -> None:
        self.implementation_complete()
        state = self.state()
        self.cli(
            "documentation-not-required", "--mode", "normative_pre_review",
            "--plan-sha256", state["development_plan_sha256"],
            "--policy-evidence", "POLICY-DOC-NONE",
        )
        state = self.state()
        verifier = "verifier-1"
        convergence_capsule = self.capsule(
            "reviewer", "convergence", verifier
        )
        convergence_report = self.artifact("reviews", "convergence-verifier-report")
        convergence_credit = self.review_credit_manifest(
            "convergence-verifier-credit", verifier, "full_convergence"
        )
        direct_state = json.loads(json.dumps(state))
        runtime_controller.resolve_review_credit_manifest(
            self.root,
            direct_state,
            convergence_credit,
            reviewer_id=verifier,
            review_mode="full_convergence",
            expected_lens="persistence-lifecycle",
        )
        old_literal = json.loads(
            (self.root / convergence_credit).read_text(encoding="utf-8")
        )
        old_literal["review_mode"] = "convergence"
        old_literal_path = self.artifact(
            "reviews", "convergence-old-literal-credit", old_literal
        )
        with self.assertRaisesRegex(runtime_controller.PipelineError, "review_mode mismatch"):
            runtime_controller.resolve_review_credit_manifest(
                self.root,
                json.loads(json.dumps(state)),
                old_literal_path,
                reviewer_id=verifier,
                review_mode="full_convergence",
                expected_lens="persistence-lifecycle",
            )
        convergence_command = (
            "convergence-audit-complete", "--revision", state["revision"],
            "--product-revision", state["product_revision"],
            "--support-revision", state["support_revision"],
            "--evidence-revision", state["evidence_revision"],
            "--run-id", "convergence-verifier-1", "--reviewer-id", verifier,
            "--capsule", convergence_capsule, "--lens", "persistence-lifecycle",
            "--status", "pass",
            "--report", convergence_report,
            "--credit-manifest", convergence_credit,
        )
        self.cli(*convergence_command)
        self.cli(*convergence_command)
        convergence_decision_report = self.artifact(
            "reviews", "convergence-verifier-decision"
        )
        convergence_finalize_command = (
            "convergence-finalize", "--revision", state["revision"],
            "--decision", "pass",
            "--report", convergence_decision_report,
        )
        self.cli(*convergence_finalize_command)
        self.cli(*convergence_finalize_command)

        state = self.state()
        review_capsule = self.capsule("reviewer", "review", verifier)
        review_credit = self.review_credit_manifest(
            "final-verifier-credit", verifier, "final_whole_feature_review"
        )
        review_credit_path = self.root / review_credit
        credit = json.loads(review_credit_path.read_text(encoding="utf-8"))
        credit["composition_audit"] = True
        credit["new_boundaries_audited"] = []
        credit["components"][0]["mode"] = "reused"
        credit["components"][0]["source_credit_id"] = state[
            "component_review_credits"
        ][-1]["id"]
        review_credit_path.write_text(json.dumps(credit), encoding="utf-8")
        review_report = self.artifact("reviews", "final-verifier-report")
        review_command = (
            "review-complete", "--revision", state["revision"],
            "--product-revision", state["product_revision"],
            "--support-revision", state["support_revision"],
            "--evidence-revision", state["evidence_revision"],
            "--run-id", "final-verifier-1", "--reviewer-id", verifier,
            "--capsule", review_capsule, "--status", "pass",
            "--report", review_report,
            "--credit-manifest", review_credit,
        )
        self.cli(*review_command)
        self.cli(*review_command)
        review_decision_report = self.artifact("reviews", "final-verifier-decision")
        review_finalize_command = (
            "review-finalize", "--revision", state["revision"],
            "--decision", "pass",
            "--report", review_decision_report,
        )
        self.cli(*review_finalize_command)
        self.cli(*review_finalize_command)

        self.qa_probe()
        state = self.state()
        qa_capsule = self.capsule("reviewer", "qa", verifier)
        manual_execution = self.qa_manual_artifact()
        qa_report = self.artifact("qa", "qa-verifier-report")
        qa_command = (
            "qa-complete", "--revision", state["revision"],
            "--product-revision", state["product_revision"],
            "--support-revision", state["support_revision"],
            "--evidence-revision", state["evidence_revision"],
            "--run-id", "qa-verifier-1", "--worker-id", verifier,
            "--capsule", qa_capsule, "--status", "pass",
            "--manual-execution", manual_execution,
            "--report", qa_report,
        )
        result = json.loads(self.cli(*qa_command).stdout)
        self.cli(*qa_command)
        self.assertEqual("derived_documentation", result["phase"])
        self.assertEqual(
            [verifier, verifier, verifier],
            [
                self.state()["convergence"]["runs"][0]["reviewer_id"],
                self.state()["review"]["runs"][0]["reviewer_id"],
                self.state()["qa"]["worker_id"],
            ],
        )
        self.assertEqual(3, len({
            self.state()["convergence"]["runs"][0]["capsule_id"],
            self.state()["review"]["runs"][0]["capsule_id"],
            self.state()["qa"]["capsule_id"],
        }))
        ready_state = json.loads(
            self.cli(
                "documentation-not-required",
                "--mode", "derived_post_qa",
                "--plan-sha256", self.state()["development_plan_sha256"],
                "--policy-evidence", "POLICY-DOC-NONE",
            ).stdout
        )
        self.assertEqual("ready", ready_state["phase"])
        terminal = json.loads(self.cli("ready").stdout)
        self.assertTrue(terminal["ready"])
        self.assertEqual([], terminal["reasons"])

    def test_qa_rejects_stale_review_chain_identity(self) -> None:
        state = self.ready_for_qa()
        state["review"]["evidence_revision"] = "0" * 64
        self.write_state(state)
        capsule = self.capsule("reviewer", "qa", "qa-stale-review")
        state = self.state()
        result = self.cli(
            "qa-complete", "--revision", state["revision"], "--product-revision", state["product_revision"],
            "--support-revision", state["support_revision"], "--evidence-revision", state["evidence_revision"],
            "--run-id", "qa-stale-review", "--worker-id", "qa-stale-review", "--capsule", capsule,
            "--status", "pass", "--manual-execution", self.qa_manual_artifact(),
            "--report", self.artifact("qa", "qa-stale-review-report"), expected=2,
        )
        self.assertIn("exact-current immutable Review chain", result.stderr)

    def test_qa_rejects_executed_identity_with_stale_evidence_sha(self) -> None:
        state = self.ready_for_qa()
        capsule = self.capsule("reviewer", "qa", "qa-bad-evidence")
        manual = self.qa_manual_artifact()
        value = json.loads((self.root / manual).read_text(encoding="utf-8"))
        value["manual_execution"][0]["qa_evidence"]["sha256"] = "0" * 64
        (self.root / manual).write_text(json.dumps(value), encoding="utf-8")
        result = self.cli(
            "qa-complete", "--revision", state["revision"], "--product-revision", state["product_revision"],
            "--support-revision", state["support_revision"], "--evidence-revision", state["evidence_revision"],
            "--run-id", "qa-bad-evidence", "--worker-id", "qa-bad-evidence", "--capsule", capsule,
            "--status", "pass", "--manual-execution", manual,
            "--report", self.artifact("qa", "qa-bad-evidence-report"), expected=2,
        )
        self.assertIn("evidence SHA", result.stderr)

    def test_qa_rejects_executed_identity_without_evidence_object(self) -> None:
        state = self.ready_for_qa()
        capsule = self.capsule("reviewer", "qa", "qa-no-evidence")
        manual = self.qa_manual_artifact()
        value = json.loads((self.root / manual).read_text(encoding="utf-8"))
        value["manual_execution"][0]["qa_evidence"] = None
        (self.root / manual).write_text(json.dumps(value), encoding="utf-8")
        result = self.cli(
            "qa-complete", "--revision", state["revision"], "--product-revision", state["product_revision"],
            "--support-revision", state["support_revision"], "--evidence-revision", state["evidence_revision"],
            "--run-id", "qa-no-evidence", "--worker-id", "qa-no-evidence", "--capsule", capsule,
            "--status", "pass", "--manual-execution", manual,
            "--report", self.artifact("qa", "qa-no-evidence-report"), expected=2,
        )
        self.assertIn("requires immutable QA evidence", result.stderr)

    def test_qa_manual_rows_reject_silent_outcome_and_stray_resume_action(self) -> None:
        self.ready_for_qa()
        state = self.state()
        manual = self.qa_manual_artifact()
        value = json.loads((self.root / manual).read_text(encoding="utf-8"))
        row = value["manual_execution"][0]
        row.update(
            executed=False,
            passed=None,
            deferred=False,
            blocked_by_finding=None,
            qa_evidence=None,
            gate=None,
            minimum_resume_action=None,
        )
        silent = self.artifact("qa", "qa-silent-outcome", value)
        with self.assertRaisesRegex(runtime_controller.PipelineError, "deferred or bound"):
            runtime_controller.validate_manual_execution_artifact(
                self.root, state, silent
            )

        value = json.loads((self.root / self.qa_manual_artifact()).read_text(encoding="utf-8"))
        value["manual_execution"][0]["minimum_resume_action"] = "unexpected retry"
        stray = self.artifact("qa", "qa-stray-resume", value)
        with self.assertRaisesRegex(runtime_controller.PipelineError, "cannot carry a resume"):
            runtime_controller.validate_manual_execution_artifact(
                self.root, state, stray
            )

    def test_qa_obeys_worker_budget_checkpoint(self) -> None:
        state = self.ready_for_qa()
        state["worker_budget"]["status"] = "checkpoint_required"
        self.write_state(state)
        capsule = self.capsule("reviewer", "qa", "qa-over-budget")
        state = self.state()
        result = self.cli(
            "qa-complete", "--revision", state["revision"], "--product-revision", state["product_revision"],
            "--support-revision", state["support_revision"], "--evidence-revision", state["evidence_revision"],
            "--run-id", "qa-over-budget", "--worker-id", "qa-over-budget", "--capsule", capsule,
            "--status", "pass", "--manual-execution", self.qa_manual_artifact(),
            "--report", self.artifact("qa", "qa-over-budget-report"), expected=2,
        )
        self.assertIn("Worker budget checkpoint", result.stderr)

    def test_qa_run_id_is_unique_across_gated_resumes(self) -> None:
        state = self.ready_for_qa()
        self.cli(
            "qa-capability-probe", "--revision", state["revision"],
            "--probe-id", "probe-gated-unique",
            "--capability", "test-server-two-clients=blocked_user",
            "--minimum-resume-action",
            "test-server-two-clients=user|true|authorize exact QA topology",
            "--report", self.artifact("qa", "probe-gated-unique"),
        )
        capsule = self.capsule("reviewer", "qa", "qa-unique")
        state = self.state()
        common = (
            "qa-complete", "--revision", state["revision"], "--product-revision", state["product_revision"],
            "--support-revision", state["support_revision"], "--evidence-revision", state["evidence_revision"],
            "--run-id", "qa-gated-unique", "--worker-id", "qa-unique", "--capsule", capsule,
            "--status", "blocked_user", "--manual-execution", self.qa_manual_artifact(gate="blocked_user"),
            "--pending-identity", "MANUAL-SLICE-001-RUNTIME", "--reason", "operator authorization",
            "--report", self.artifact("qa", "qa-unique-report"),
        )
        self.cli(*common)
        state_path = self.root / ".agentic-pipeline" / "state.json"
        after_first = state_path.read_bytes()
        self.cli(*common)
        self.assertEqual(after_first, state_path.read_bytes())
        changed = list(common)
        changed[changed.index("operator authorization")] = "different authorization"
        result = self.cli(*changed, expected=2)
        self.assertIn("qa-complete lost-response replay mismatch", result.stderr)

    def test_documentation_not_required_rejects_caller_invented_policy(self) -> None:
        self.implementation_complete()
        state = self.state()
        result = self.cli(
            "documentation-not-required", "--mode", "normative_pre_review", "--plan-sha256",
            state["development_plan_sha256"], "--policy-evidence", "INVENTED-POLICY", expected=2,
        )
        self.assertIn("exact approved-plan policy evidence", result.stderr)

    def test_runtime_state_stores_exact_plan_context_and_documentation_contracts(self) -> None:
        state = self.initialize(research=False)
        self.assertEqual(5, state["plan_contracts"]["context_budget"]["max_authority_files"])
        self.assertEqual(
            "capsule_plus_referenced_files",
            state["plan_contracts"]["context_metric_scope"],
        )
        self.assertEqual(
            "capsule_plus_referenced_files",
            state["plan_contracts"]["slices"]["SLICE-001"]["context_metric_scope"],
        )
        self.assertEqual(
            "not_required | policy=POLICY-DOC-NONE",
            state["plan_contracts"]["documentation_strategy"]["derived_post_qa"],
        )

    def test_qa_updates_terminal_feature_coverage_to_current_identity(self) -> None:
        state = self.ready_for_qa()
        capsule = self.capsule("reviewer", "qa", "qa-aggregate")
        result = json.loads(self.cli(
            "qa-complete", "--revision", state["revision"], "--product-revision", state["product_revision"],
            "--support-revision", state["support_revision"], "--evidence-revision", state["evidence_revision"],
            "--run-id", "qa-aggregate", "--worker-id", "qa-aggregate", "--capsule", capsule,
            "--status", "pass", "--manual-execution", self.qa_manual_artifact(),
            "--report", self.artifact("qa", "qa-aggregate-report"),
        ).stdout)
        result = self.full_status()
        feature = result["coverage"]["feature"]
        manifest = json.loads(Path(feature["finalized_manifest"]["path"]).read_text(encoding="utf-8"))
        self.assertEqual(result["revision"], manifest["revisions"]["revision"])
        self.assertTrue(manifest["summary"]["feature_verification_eligible"])

    def test_ready_revalidates_immutable_manual_qa_evidence_bytes(self) -> None:
        state = self.ready_for_qa()
        capsule = self.capsule("reviewer", "qa", "qa-evidence-drift")
        self.cli(
            "qa-complete", "--revision", state["revision"], "--product-revision", state["product_revision"],
            "--support-revision", state["support_revision"], "--evidence-revision", state["evidence_revision"],
            "--run-id", "qa-evidence-drift", "--worker-id", "qa-evidence-drift", "--capsule", capsule,
            "--status", "pass", "--manual-execution", self.qa_manual_artifact(),
            "--report", self.artifact("qa", "qa-evidence-drift-report"),
        )
        state = self.state()
        self.cli(
            "documentation-not-required", "--mode", "derived_post_qa", "--plan-sha256",
            state["development_plan_sha256"], "--policy-evidence", "POLICY-DOC-NONE",
        )
        feature = self.state()["coverage"]["feature"]
        manifest = json.loads(Path(feature["finalized_manifest"]["path"]).read_text(encoding="utf-8"))
        evidence_path = self.root / manifest["manual_execution"][0]["qa_evidence"]["path"]
        evidence_path.write_text('{"runtime":"drifted"}\n', encoding="utf-8")
        result = self.cli("ready", expected=1)
        self.assertIn("terminal feature coverage aggregate is stale", result.stdout)

    def test_evidence_recovery_rebinds_coverage_review_then_requires_fresh_qa_to_ready(self) -> None:
        state = self.ready_for_qa()
        state["phase"] = "evidence_recovery"
        state["review"]["status"] = "failed"
        state["engineer_clean"] = {
            "revision": state["revision"],
            "product_revision": state["product_revision"],
            "support_revision": state["support_revision"],
            "evidence_revision": state["evidence_revision"],
        }
        state["recovery"] = {
            "status": "awaiting_remediation",
            "base_revision": state["revision"],
            "base_product_revision": state["product_revision"],
            "base_support_revision": state["support_revision"],
            "base_evidence_revision": state["evidence_revision"],
            "finding_ids": ["F-EVIDENCE-1"],
            "base_review_runs": list(state["review"]["runs"]),
            "remediation_owner_id": None,
            "remediation_runs": [],
            "verification_runs": [],
            "cycles": 0,
            "reason": "repair exact automated evidence",
        }
        self.write_state(state)
        findings_path = self.root / ".agentic-pipeline" / "findings.json"
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        findings["items"].append(
            {
                "id": "F-EVIDENCE-1", "status": "open", "finding_kind": "evidence",
                "severity": "major", "blocking": True, "source": "review",
            }
        )
        findings_path.write_text(json.dumps(findings), encoding="utf-8")
        capsule = self.capsule(
            "recovery_remediator", "evidence_recovery", "recovery-worker",
            allowed=(self.rel(self.test_source),),
        )
        self.cli(
            "acquire-write-lease", "--role", "recovery_remediator", "--phase", "evidence_recovery",
            "--write-scope", "feature-evidence", "--worker-id", "recovery-worker", "--capsule", capsule,
        )
        self.test_source.write_text("def test_feature(): assert 1 == 1\n", encoding="utf-8")
        semantic = self.semantic_packet_for_change(self.test_source, domain="evidence", symbols=["test_feature"])
        active = self.state()
        current = runtime_controller.compute_inventory_revisions(self.root, active)
        prior_coverage_path = Path(active["coverage"]["feature"]["finalized_manifest"]["path"])
        recovery_coverage = json.loads(prior_coverage_path.read_text(encoding="utf-8"))
        recovery_coverage["revisions"] = {
            key: current[key]
            for key in ("revision", "product_revision", "support_revision", "evidence_revision")
        }
        coverage_path = self.artifact("verification", "recovery-coverage", recovery_coverage)
        recovered = json.loads(self.cli(
            "recovery-remediation-complete", "--run-id", "recovery-run-1", "--worker-id", "recovery-worker",
            "--lease-id", active["active_write_lease"]["lease_id"], "--capsule", capsule,
            "--machine-checks", "pass", "--semantic-report", semantic,
            "--coverage-manifest", coverage_path, "--report", self.artifact("verification", "recovery-report"),
            "--resolved-finding", "F-EVIDENCE-1",
        ).stdout)
        recovered = self.full_status()
        self.assertEqual("recovery_review", recovered["phase"])
        self.assertEqual(recovered["revision"], recovered["machine_checks"]["revision"])
        self.assertEqual(recovered["revision"], recovered["coverage"]["feature"]["state"]["revision"])
        self.assertEqual(recovered["revision"], recovered["implementation_state"]["revision"])
        state = self.state()
        recovery_review_capsule = self.capsule(
            "reviewer", "recovery_review", "recovery-reviewer"
        )
        recovery_credit = self.review_credit_manifest(
            "recovery-review-credit", "recovery-reviewer", "recovery_verification"
        )
        state = self.state()
        reviewed = json.loads(self.cli(
            "recovery-review-complete", "--revision", state["revision"],
            "--product-revision", state["product_revision"], "--support-revision", state["support_revision"],
            "--evidence-revision", state["evidence_revision"], "--run-id", "recovery-review-1",
            "--reviewer-id", "recovery-reviewer", "--capsule", recovery_review_capsule,
            "--status", "pass", "--credit-manifest", recovery_credit,
            "--report", self.artifact("reviews", "recovery-review-report"),
        ).stdout)
        self.assertEqual("qa", reviewed["phase"])
        self.qa_probe()
        qa_capsule = self.capsule("reviewer", "qa", "qa-after-recovery")
        state = self.state()
        qa = json.loads(self.cli(
            "qa-complete", "--revision", state["revision"], "--product-revision", state["product_revision"],
            "--support-revision", state["support_revision"], "--evidence-revision", state["evidence_revision"],
            "--run-id", "qa-after-recovery", "--worker-id", "qa-after-recovery", "--capsule", qa_capsule,
            "--status", "pass", "--manual-execution", self.qa_manual_artifact(),
            "--report", self.artifact("qa", "qa-after-recovery-report"),
        ).stdout)
        self.assertEqual("derived_documentation", qa["phase"])
        state = self.state()
        terminal = json.loads(self.cli(
            "documentation-not-required", "--mode", "derived_post_qa", "--plan-sha256",
            state["development_plan_sha256"], "--policy-evidence", "POLICY-DOC-NONE",
        ).stdout)
        self.assertEqual("ready", terminal["phase"])
        self.assertEqual(0, self.cli("ready").returncode)

    def test_component_credit_rejects_controller_unverified_hash(self) -> None:
        self.initialize(research=False)
        state = self.state()
        paths = list(state["revision_inventory"]["product"])
        manifest = {
            "schema_version": 1, "revision": state["revision"], "reviewer_id": "reviewer-credit",
            "review_mode": "convergence", "components": [{
                "component": "feature", "product_paths": paths, "contract_paths": [self.rel(self.prd)],
                "product_hash": "0" * 64, "contract_hash": "0" * 64,
                "lenses": ["persistence-lifecycle"], "mode": "fresh", "source_credit_id": None,
            }],
        }
        path = self.artifact("reviews", "bad-credit", manifest)
        with self.assertRaisesRegex(runtime_controller.PipelineError, "product_hash is stale"):
            runtime_controller.resolve_review_credit_manifest(
                self.root, state, path, reviewer_id="reviewer-credit", review_mode="convergence"
            )

    def test_component_credit_rejects_unsupported_lens(self) -> None:
        self.initialize(research=False)
        state = self.state()
        paths = list(state["revision_inventory"]["product"])
        product_hash = runtime_controller.exact_inventory_digest(self.root, paths, "test product")
        contract_hash = runtime_controller.exact_inventory_digest(self.root, [self.rel(self.prd)], "test contract")
        manifest = {
            "schema_version": 1, "revision": state["revision"], "reviewer_id": "reviewer-lens",
            "review_mode": "convergence", "components": [{
                "component": "feature", "product_paths": paths, "contract_paths": [self.rel(self.prd)],
                "product_hash": product_hash, "contract_hash": contract_hash,
                "lenses": ["invented-lens"], "mode": "fresh", "source_credit_id": None,
            }],
        }
        path = self.artifact("reviews", "bad-lens", manifest)
        with self.assertRaisesRegex(runtime_controller.PipelineError, "unsupported lens"):
            runtime_controller.resolve_review_credit_manifest(
                self.root, state, path, reviewer_id="reviewer-lens", review_mode="convergence"
            )

    def test_component_credit_requires_exact_product_inventory_coverage(self) -> None:
        self.initialize(research=False)
        state = self.state()
        paths = [self.rel(self.prd)]
        digest = runtime_controller.exact_inventory_digest(self.root, paths, "test subset")
        manifest = {
            "schema_version": 1, "revision": state["revision"], "reviewer_id": "reviewer-inventory",
            "review_mode": "convergence", "components": [{
                "component": "partial", "product_paths": paths, "contract_paths": paths,
                "product_hash": digest, "contract_hash": digest,
                "lenses": ["persistence-lifecycle"], "mode": "fresh", "source_credit_id": None,
            }],
        }
        path = self.artifact("reviews", "partial-credit", manifest)
        with self.assertRaisesRegex(runtime_controller.PipelineError, "exact current product inventory"):
            runtime_controller.resolve_review_credit_manifest(
                self.root, state, path, reviewer_id="reviewer-inventory", review_mode="convergence"
            )

    def test_exact_component_credit_is_reused_instead_of_reread(self) -> None:
        self.initialize(research=False)
        state = self.state()
        paths = list(state["revision_inventory"]["product"])
        product_hash = runtime_controller.exact_inventory_digest(self.root, paths, "test product")
        contract_paths = [self.rel(self.prd)]
        contract_hash = runtime_controller.exact_inventory_digest(self.root, contract_paths, "test contract")
        component = {
            "component": "feature", "product_paths": paths, "contract_paths": contract_paths,
            "product_hash": product_hash, "contract_hash": contract_hash,
            "lenses": ["persistence-lifecycle"], "mode": "fresh", "source_credit_id": None,
        }
        manifest = {
            "schema_version": 1, "revision": state["revision"], "reviewer_id": "reviewer-reuse",
            "review_mode": "convergence", "components": [component],
        }
        path = self.artifact("reviews", "fresh-credit", manifest)
        _, ids = runtime_controller.resolve_review_credit_manifest(
            self.root, state, path, reviewer_id="reviewer-reuse", review_mode="convergence"
        )
        reused = dict(component)
        reused["mode"] = "reused"
        reused["source_credit_id"] = ids[0]
        manifest["components"] = [reused]
        reused_path = self.artifact("reviews", "reused-credit", manifest)
        _, reused_ids = runtime_controller.resolve_review_credit_manifest(
            self.root, state, reused_path, reviewer_id="reviewer-reuse", review_mode="convergence"
        )
        self.assertEqual(ids, reused_ids)

    def test_write_lease_rejects_empty_path_authority(self) -> None:
        self.initialize()
        self.plan_coverage()
        result = self.cli(
            "context-capsule-create", "--role", "engineer", "--phase", "slice_engineering",
            "--worker-id", "engineer-empty",
            "--plan-sha256", self.state()["development_plan_sha256"],
            "--revision", self.state()["revision"],
            "--authority",
            f"{self.rel(self.prd)}={self.sha(self.prd)}:PRD-REQ-001,PRD-AC-001",
            "--output-path", f"tests/{FEATURE}/verification/engineer-empty-output.json",
            "--stop-condition", "stop before writing", "--max-authority-files", "5",
            "--max-evidence-files", "5", "--max-total-files", "10",
            "--max-payload-bytes", "500000", "--max-estimated-tokens", "200000",
            "--output", f"tests/{FEATURE}/verification/engineer-empty-capsule.json",
            expected=2,
        )
        self.assertIn("semantic allowed_paths", result.stderr)

    def test_owner_transfer_revokes_lease_without_resetting_revision_or_coverage(self) -> None:
        self.initialize()
        self.begin_engineer_lease(allowed=("src/feature.py",))
        before = self.state()
        before["phase"] = "engineering"
        self.write_state(before)
        result = json.loads(self.cli(
            "transfer-engineering-owner", "--from-owner", "engineer-1", "--to-owner", "engineer-2",
            "--reason", "structured ownership handoff", "--slice-id", "SLICE-001",
        ).stdout)
        result = self.full_status()
        self.assertEqual(before["revision"], result["revision"])
        self.assertEqual("engineer-2", result["owner_by_slice"]["SLICE-001"])
        self.assertIsNone(result["active_write_lease"])
        self.assertEqual("revoked", result["write_lease_history"][-1]["status"])
        self.assertIsNotNone(result["coverage"]["SLICE-001"]["planned_manifest"])

    def test_context_exhausted_release_requires_fresh_engineer_and_carries_candidate(self) -> None:
        self.initialize()
        self.begin_engineer_lease(allowed=("src/feature.py",))
        lease_id = self.state()["active_write_lease"]["lease_id"]
        self.src.write_text("VALUE = 1\n", encoding="utf-8")

        self.cli(
            "release-write-lease", "--lease-id", lease_id,
            "--result", "revoked", "--reason", "context_exhausted",
        )
        released = self.state()
        self.assertEqual("owner_handoff_hold", released["phase"])
        self.assertIn("engineer-1", released["exhausted_worker_ids"])
        carried = released["scope_guard"]["rebaseline_candidate"]
        self.assertTrue(carried["fresh_owner_required"])
        self.assertEqual(["src/feature.py"], [item["path"] for item in carried["changes"]])
        rejected = self.cli(
            "transfer-engineering-owner", "--from-owner", "engineer-1",
            "--to-owner", "engineer-1", "--reason", "context rotation",
            "--slice-id", "SLICE-001", expected=2,
        )
        self.assertIn("fresh distinct Engineer", rejected.stderr)

        self.cli(
            "transfer-engineering-owner", "--from-owner", "engineer-1",
            "--to-owner", "engineer-2", "--reason", "context rotation",
            "--slice-id", "SLICE-001",
        )
        prepared = json.loads(self.cli("prepare-engineer-continuation").stdout)
        self.assertEqual("engineer-2", prepared["owner_id"])
        self.assertTrue(self.state()["active_write_lease"]["rebaseline_carried"])
        self.assertEqual("VALUE = 1\n", self.src.read_text(encoding="utf-8"))

    def test_consecutive_product_change_checkpoint_survives_status_load(self) -> None:
        self.initialize(research=False)
        state = self.state()
        state["phase"] = "convergence_hold"
        state["iteration_control"].update(
            {
                "consecutive_product_changes": state["iteration_control"]["max_consecutive_product_changes"],
                "status": "checkpoint_required",
                "reason": "Consecutive product-change circuit breaker reached",
            }
        )
        self.write_state(state)
        result = json.loads(self.cli("status").stdout)
        self.assertEqual("convergence_hold", result["phase"])
        self.assertEqual("checkpoint_required", result["iteration_control"]["status"])

    def test_review_routes_are_sequential_and_hold_packet_is_executable(self) -> None:
        state = self.initialize(research=False)
        state["phase"] = "convergence"
        state["convergence"]["status"] = "running"
        route = runtime_controller.next_action(state)
        self.assertEqual("complete_read_only_convergence_audits", route["action"])
        self.assertNotIn("parallel", route["action"])

        state["phase"] = "review"
        state["review"]["status"] = "running"
        route = runtime_controller.next_action(state)
        self.assertEqual("complete_final_review", route["action"])

        state["phase"] = "convergence_hold"
        state["iteration_control"].update(
            reason="iteration checkpoint", resume_phase="engineering"
        )
        self.assertEqual(
            {
                "action": "authorize_iteration",
                "owner": "technical_director",
                "user_input_required": False,
                "command": "authorize-iteration",
                "hold_phase": "convergence_hold",
                "resume_phase": "engineering",
                "reason": "iteration checkpoint",
                "required_argument": "reason",
            },
            runtime_controller.next_action(state),
        )

    def test_status_defaults_compact_with_allowlisted_diagnostics(self) -> None:
        self.initialize(research=False)
        compact = json.loads(self.cli("status").stdout)
        self.assertEqual(1, compact["status_schema"])
        self.assertEqual("compact", compact["mode"])
        self.assertIn("coverage_revision", compact)
        self.assertIn("changed_ids", compact)
        self.assertIn("active_ids", compact)
        self.assertIn("next_action", compact)
        self.assertNotIn("slices", compact)
        section = json.loads(self.cli("status", "--section", "leases").stdout)
        self.assertEqual("section", section["mode"])
        self.assertEqual("leases", section["section"])
        self.assertIn("history", section["data"])
        full = json.loads(self.cli("status", "--full").stdout)
        self.assertIn("slices", full)
        self.assertIn("write_lease_history", full)
        self.assertNotIn("status_schema", full)

    def test_long_state_compact_status_has_bounded_output(self) -> None:
        self.initialize(research=False)
        state = self.state()
        findings = json.loads(
            (self.root / ".agentic-pipeline" / "findings.json").read_text(
                encoding="utf-8"
            )
        )
        for index in range(100):
            payload = "x" * 512
            state["write_lease_history"].append(
                {"lease_id": f"LEASE-{index:04d}", "status": "complete", "detail": payload}
            )
            state["context_capsules"].append(
                {"capsule_id": f"CAPSULE-{index:04d}", "detail": payload}
            )
            state["handoffs"].append(
                {"handoff_id": f"HANDOFF-{index:04d}", "detail": payload}
            )
            state["component_review_credits"].append(
                {"credit_id": f"CREDIT-{index:04d}", "detail": payload}
            )
            state["gates"].append(
                {
                    "id": f"GATE-{index:04d}",
                    "category": "blocked_environment",
                    "status": "open",
                    "detail": payload,
                }
            )
            findings["items"].append(
                {
                    "id": f"F-LONG-{index:04d}",
                    "severity": "minor",
                    "status": "open",
                    "blocking": False,
                    "detail": payload,
                }
            )
        args = runtime_controller.build_parser().parse_args(
            ["status", "--project-root", str(self.root)]
        )
        full = runtime_controller.full_status_payload(state, findings)
        compact = runtime_controller.compact_status_payload(state, findings, args)
        full_bytes = len(json.dumps(full, ensure_ascii=False, indent=2).encode("utf-8"))
        compact_bytes = len(
            json.dumps(compact, ensure_ascii=False, indent=2).encode("utf-8")
        )
        self.assertGreater(full_bytes, 200_000)
        self.assertLessEqual(compact_bytes, 8_192)
        self.assertLess(compact_bytes, full_bytes // 10)
        self.assertTrue(compact["active_ids"]["open_gate_ids"]["truncated"])
        self.assertEqual(100, compact["active_ids"]["open_gate_ids"]["total"])

    def test_open_minor_residual_risk_blocks_readiness_until_explicit_acceptance(self) -> None:
        self.initialize(research=False)
        revision = self.state()["revision"]
        findings_path, findings = self.inject_canonical_finding(
            {
                "id": "F-MINOR-1",
                "status": "open",
                "severity": "minor",
                "blocking": False,
                "revision": revision,
            }
        )
        reasons = runtime_controller.readiness_reasons(self.state(), findings)
        self.assertIn("minor findings require resolution or explicit acceptance", reasons)
        reason = "bounded cosmetic residual"
        authority_id = "AUTH-RISK-1"
        approval_reference = "USER-RISK-1"
        statement = (
            f"Accept residual risk for finding F-MINOR-1 at revision {revision}: {reason}"
        )
        self.cli(
            "user-authority-accept",
            "--authority-id",
            authority_id,
            "--approval-reference",
            approval_reference,
            "--statement",
            statement,
        )
        self.cli(
            "accept-finding", "--id", "F-MINOR-1", "--reason", reason,
            "--revision", revision, "--authority-id", authority_id,
            "--approval-reference", approval_reference,
        )
        accepted = json.loads(findings_path.read_text(encoding="utf-8"))
        self.assertEqual("accepted", accepted["items"][0]["status"])

    def test_compute_revisions_remains_deterministic_and_rejects_overlap(self) -> None:
        self.initialize(research=False)
        first = json.loads(
            self.cli(
                "compute-revisions", "--base-revision", "base", "--product-file", self.rel(self.src),
                "--evidence-file", self.rel(self.test_source),
            ).stdout
        )
        second = json.loads(
            self.cli(
                "compute-revisions", "--base-revision", "base", "--evidence-file", self.rel(self.test_source),
                "--product-file", self.rel(self.src),
            ).stdout
        )
        self.assertEqual(first["revision"], second["revision"])
        self.cli(
            "compute-revisions", "--base-revision", "base", "--product-file", self.rel(self.src),
            "--evidence-file", self.rel(self.src), expected=2,
        )

    def test_user_authority_cannot_be_self_issued_by_capsule_or_recorder(self) -> None:
        self.initialize()
        packet, authority_id, digest = self.decision_packet()
        before = (self.root / ".agentic-pipeline" / "state.json").read_bytes()
        result = self.cli(
            "context-capsule-create",
            "--role", "decision_recorder",
            "--phase", "decision_recording",
            "--worker-id", "recorder-unaccepted",
            "--plan-sha256", self.state()["development_plan_sha256"],
            "--revision", self.state()["revision"],
            "--authority", f"not_applicable={digest}:{authority_id}",
            "--allowed-path", self.rel(self.ledger),
            "--output-path", self.rel(self.ledger),
            "--stop-condition", "Record only the accepted decision",
            "--max-authority-files", "5",
            "--max-evidence-files", "5",
            "--max-total-files", "10",
            "--max-payload-bytes", "500000",
            "--max-estimated-tokens", "200000",
            "--output", f"tests/{FEATURE}/verification/unaccepted-capsule.json",
            expected=2,
        )
        self.assertIn("prior controller-registered user authority", result.stderr)
        self.assertEqual(before, (self.root / ".agentic-pipeline" / "state.json").read_bytes())
        self.assertEqual("AUTH-DEC-001", packet["items"][0]["authority"]["section_or_id"])

    def test_user_authority_receipt_is_append_only_and_revalidated_on_load(self) -> None:
        self.initialize()
        packet, _, _ = self.decision_packet()
        receipt = self.accept_user_authority(packet)
        self.assertEqual(packet["items"][0]["authority"]["sha256"], receipt["sha256"])
        duplicate = self.cli(
            "user-authority-accept",
            "--authority-id", receipt["authority_id"],
            "--approval-reference", receipt["approval_reference"],
            "--statement", receipt["statement"],
            expected=2,
        )
        self.assertIn("append-only", duplicate.stderr)
        receipt_path = self.root / receipt["receipt_path"]
        receipt_path.write_text(receipt_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
        drift = self.cli("status", expected=2)
        self.assertIn("receipt bytes drifted", drift.stderr)

    def test_user_authority_adopts_exact_orphan_receipt_after_save_crash(self) -> None:
        self.initialize()
        packet, authority_id, _ = self.decision_packet()
        item = packet["items"][0]
        args = argparse.Namespace(
            project_root=str(self.root),
            authority_id=authority_id,
            approval_reference=item["authority"]["reference"],
            statement=item["statement"],
        )
        with mock.patch.object(runtime_controller, "save_runtime", side_effect=RuntimeError("crash")):
            with self.assertRaisesRegex(RuntimeError, "crash"):
                runtime_controller.cmd_user_authority_accept(args)
        self.assertEqual([], self.state()["user_authorities"])
        with contextlib.redirect_stdout(io.StringIO()):
            runtime_controller.cmd_user_authority_accept(args)
        authorities = self.state()["user_authorities"]
        self.assertEqual([authority_id], [entry["authority_id"] for entry in authorities])

    def test_late_decision_from_implementation_complete_is_rejected_without_state_mutation(self) -> None:
        self.implementation_complete()
        packet, authority_id, authority_digest = self.decision_packet()
        self.accept_user_authority(packet)
        state_path = self.root / ".agentic-pipeline" / "state.json"
        before = state_path.read_bytes()
        result = self.cli(
            "context-capsule-create", "--role", "decision_recorder",
            "--phase", "decision_recording", "--worker-id", "recorder-late",
            "--plan-sha256", self.state()["development_plan_sha256"],
            "--revision", self.state()["revision"],
            "--authority", f"not_applicable={authority_digest}:{authority_id}",
            "--allowed-path", self.rel(self.ledger),
            "--output-path", self.rel(self.ledger),
            "--stop-condition", "Record only the accepted decision",
            "--max-authority-files", "5", "--max-evidence-files", "5",
            "--max-total-files", "10", "--max-payload-bytes", "500000",
            "--max-estimated-tokens", "200000", "--output",
            f"tests/{FEATURE}/verification/late-decision-capsule.json", expected=2,
        )
        self.assertIn("Context capsule activation is off-phase", result.stderr)
        self.assertEqual(before, state_path.read_bytes())
        self.assertFalse(
            (self.root / f"tests/{FEATURE}/verification/late-decision-capsule.json").exists()
        )
        self.assertEqual("pass", self.state()["implementation_state"]["status"])

    def test_removed_legacy_recovery_command_cannot_persist_caller_hashes(self) -> None:
        self.initialize(research=False)
        state_path = self.root / ".agentic-pipeline" / "state.json"
        before = state_path.read_bytes()
        result = self.cli(
            "start-evidence-recovery", "--revision", "f" * 64,
            "--product-revision", "f" * 64, "--support-revision", "f" * 64,
            "--evidence-revision", "f" * 64, "--finding-id", "F-EVIDENCE",
            "--reason", "caller supplied identities", expected=2,
        )
        self.assertIn("invalid choice", result.stderr)
        self.assertEqual(before, state_path.read_bytes())

    def test_review_evidence_finding_cannot_be_misrouted_as_product(self) -> None:
        state = self.initialize(research=False)
        state["phase"] = "review"
        state["review"] = {
            "status": "awaiting_decision",
            "runs": [
                {"reviewer_id": "reviewer-1", "status": "fail"},
            ],
        }
        self.write_state(state)
        findings_path, _ = self.inject_canonical_finding(
            {
                "id": "F-REVIEW-EVIDENCE",
                "status": "open",
                "source": "review",
                "revision": state["revision"],
                "finding_kind": "evidence",
                "blocking": True,
                "remediation_required": True,
            }
        )
        report = self.artifact("reviews", "misroute-review")
        state_path = self.root / ".agentic-pipeline" / "state.json"
        before_state = state_path.read_bytes()
        before_findings = findings_path.read_bytes()
        result = self.cli(
            "review-finalize", "--revision", state["revision"],
            "--decision", "rework", "--rework-scope", "product",
            "--revalidation", "targeted", "--reason", "repair evidence",
            "--report", report, expected=2,
        )
        self.assertIn("controller-derived", result.stderr)
        self.assertEqual(before_state, state_path.read_bytes())
        self.assertEqual(before_findings, findings_path.read_bytes())

    def test_coverage_amendments_match_exact_semantic_ac_diff_and_validate_prefix(self) -> None:
        state = self.initialize()
        state["slices"]["SLICE-001"]["scope_contract"]["acceptance_ids"].append("PRD-AC-002")
        findings_path = self.root / ".agentic-pipeline" / "findings.json"
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        canonical_findings = json.loads(json.dumps(state["canonical_findings"]))
        amendment_finding = {
                "id": "F-AMEND-001",
                "source": "review",
                "finding_kind": "product",
                "severity": "major",
                "scope_relation": "candidate_introduced",
                "introduced_by_candidate": True,
                "production_reachability": "normal",
                "blocks_acceptance_ids": ["PRD-AC-001", "PRD-AC-002"],
                "violates_required_invariant": False,
                "required_invariant_evidence": None,
                "mandatory_core_acceptance_evidence_missing": False,
                "test_can_miss_product_defect": False,
                "deferred_reference": None,
                "title": "Coverage expectation changed",
                "evidence": "assigned_acceptance_evidence: PRD-AC-001, PRD-AC-002 | exact accepted component evidence",
                "revision": state["revision"],
                "origin_slice": "SLICE-001",
                "remediation_route": "SLICE-001",
                "status": "open",
                "created_at": "2026-08-11T00:00:00+00:00",
                "resolved_revision": None,
                "blocking": True,
            }
        findings["items"].append(amendment_finding)
        findings_path.write_text(json.dumps(findings), encoding="utf-8")
        planned = {
            "ac_mappings": [
                {"acceptance_id": "PRD-AC-001", "identity_ids": ["AUTO-1"]},
                {"acceptance_id": "PRD-AC-002", "identity_ids": ["AUTO-2"]},
            ],
            "expected_identities": [
                {"identity_id": "AUTO-1", "acceptance_ids": ["PRD-AC-001"], "assertion": "old"},
                {"identity_id": "AUTO-2", "acceptance_ids": ["PRD-AC-002"], "assertion": "old"},
            ],
            "mandatory_expected_identity_ids": ["AUTO-1", "AUTO-2"],
            "amendments": [],
        }
        finalized = json.loads(json.dumps(planned))
        for identity in finalized["expected_identities"]:
            identity["assertion"] = "new"
        finalized["amendments"] = [
            {
                "amendment_id": "COV-AMEND-001",
                "authority_id": "F-AMEND-001",
                "before_digest": runtime_controller.coverage_plan_body_digest(planned),
                "after_digest": runtime_controller.coverage_plan_body_digest(finalized),
                "affected_acceptance_ids": ["PRD-AC-001"],
                "reason": "Update both exact acceptance observations",
            }
        ]
        with self.assertRaisesRegex(runtime_controller.PipelineError, "not controller-registered"):
            runtime_controller.validate_coverage_continuity(
                state, canonical_findings, planned, finalized
            )
        canonical_findings["items"].append(amendment_finding)
        with self.assertRaisesRegex(runtime_controller.PipelineError, "exactly equal"):
            runtime_controller.validate_coverage_continuity(
                state, canonical_findings, planned, finalized
            )
        finalized["amendments"][0]["affected_acceptance_ids"] = [
            "PRD-AC-001", "PRD-AC-002"
        ]
        self.assertEqual(
            runtime_controller.coverage_plan_body_digest(finalized),
            runtime_controller.validate_coverage_continuity(
                state, canonical_findings, planned, finalized
            ),
        )
        planned_with_bad_prefix = json.loads(json.dumps(planned))
        body_digest = runtime_controller.coverage_plan_body_digest(planned_with_bad_prefix)
        planned_with_bad_prefix["amendments"] = [
            {
                "amendment_id": "COV-AMEND-DUP",
                "authority_id": "F-AMEND-001",
                "before_digest": "0" * 64,
                "after_digest": "1" * 64,
                "affected_acceptance_ids": ["PRD-AC-001"],
                "reason": "historical authorized change",
            },
            {
                "amendment_id": "COV-AMEND-DUP",
                "authority_id": "F-AMEND-001",
                "before_digest": "1" * 64,
                "after_digest": body_digest,
                "affected_acceptance_ids": ["PRD-AC-001"],
                "reason": "duplicate historical ID",
            },
        ]
        with self.assertRaisesRegex(runtime_controller.PipelineError, "identity/hash chain"):
            runtime_controller.validate_coverage_continuity(
                state,
                canonical_findings,
                planned_with_bad_prefix,
                json.loads(json.dumps(planned_with_bad_prefix)),
            )

    def test_positive_shared_touchpoint_path_preserves_exact_mapping(self) -> None:
        self.initialize()
        capsule = self.begin_engineer_lease(
            allowed=("src/contracts.py",), symbols=("FeatureContract",)
        )
        shared = self.root / "src" / "contracts.py"
        shared.write_text("class FeatureContract: pass\n", encoding="utf-8")
        state = self.state()
        inventory = {key: list(value) for key, value in state["revision_inventory"].items()}
        inventory["product"].append(self.rel(shared))
        inventory["product"].sort()
        semantic = self.artifact(
            "verification", "shared-touchpoint-positive",
            {
                "schema": 1,
                "inventory_complete": True,
                "domain_inventory": inventory,
                "changes": [{
                    "path": self.rel(shared), "domain": "product",
                    "symbols": ["FeatureContract"], "reason": "assigned_goal_effect: PRD-REQ-001, PRD-AC-001 | add the approved feature contract",
                    "change_kind": "add", "component": "feature",
                    "lifecycle_change": False, "ownership_change": False,
                    "public_contract_change": False, "requirement_ids": ["PRD-REQ-001"],
                    "acceptance_ids": ["PRD-AC-001"], "decision_ids": [],
                    "touchpoint_id": "TP-001",
                }],
                "open_assumptions": [],
            },
        )
        active = self.state()
        result = json.loads(self.cli(
            "engineer-complete", "--run-id", "shared-touchpoint-run",
            "--owner-id", "engineer-1", "--lease-id", active["active_write_lease"]["lease_id"],
            "--capsule", capsule, "--slice-id", "SLICE-001",
            "--machine-checks", "pass",
            "--diff-inspection", "pass", "--semantic-handoff", semantic,
            "--report", self.artifact(
                "verification", "shared-touchpoint-engineer-report"
            ),
        ).stdout)
        self.assertEqual("slice_coverage_finalization", result["phase"])
        self.assertIsNone(result["active_write_lease"])

    def test_finding_blocking_classification_combination_matrix(self) -> None:
        cases = [
            ("candidate_introduced", "normal", ["PRD-AC-001"], False, True),
            ("required_shared_contract", "supported_failure_path", [], True, True),
            ("preexisting_adjacent", "normal", ["PRD-AC-001"], False, False),
            ("current_feature_path", "theoretical", ["PRD-AC-001"], False, False),
            ("current_feature_path", "unknown", ["PRD-AC-001"], False, False),
            ("out_of_scope", "normal", [], False, False),
        ]
        for scope_relation, reachability, acceptance_ids, invariant, expected in cases:
            with self.subTest(scope_relation=scope_relation, reachability=reachability):
                self.assertEqual(
                    expected,
                    runtime_controller.finding_is_blocking(
                        {
                            "scope_relation": scope_relation,
                            "production_reachability": reachability,
                            "blocks_acceptance_ids": acceptance_ids,
                            "violates_required_invariant": invariant,
                        }
                    ),
                )

    def test_sequential_slice_sealing_and_whole_feature_composition_audit(self) -> None:
        state = self.initialize(research=False)
        second = json.loads(json.dumps(state["slices"]["SLICE-001"]))
        second["id"] = "SLICE-002"
        state["slices"]["SLICE-001"]["status"] = "sealed"
        second["status"] = "sealed"
        state["slices"]["SLICE-002"] = second
        state["ordered_slices"] = ["SLICE-001", "SLICE-002"]
        state["development_mode"] = "sequential_slices"
        self.assertTrue(runtime_controller.all_slices_sealed(state))
        paths = list(state["revision_inventory"]["product"])
        contract_paths = [self.rel(self.prd)]
        manifest = {
            "schema_version": 1,
            "revision": state["revision"],
            "reviewer_id": "reviewer-composition",
            "review_mode": "final",
            "composition_audit": True,
            "new_boundaries_audited": ["SLICE-001->SLICE-002"],
            "components": [{
                "component": "whole-feature",
                "product_paths": paths,
                "contract_paths": contract_paths,
                "product_hash": runtime_controller.exact_inventory_digest(
                    self.root, paths, "composition product"
                ),
                "contract_hash": runtime_controller.exact_inventory_digest(
                    self.root, contract_paths, "composition contract"
                ),
                "lenses": ["persistence-lifecycle"],
                "mode": "fresh",
                "source_credit_id": None,
            }],
        }
        manifest_path = self.artifact("reviews", "composition-credit", manifest)
        _, credits = runtime_controller.resolve_review_credit_manifest(
            self.root,
            state,
            manifest_path,
            reviewer_id="reviewer-composition",
            review_mode="final",
            require_composition_audit=True,
        )
        self.assertEqual(1, len(credits))
        state["slices"]["SLICE-002"]["status"] = "engineering_complete"
        self.assertFalse(runtime_controller.all_slices_sealed(state))
        self.assertIn(
            "not every approved development-plan slice has a sealed exact-revision handoff",
            runtime_controller.readiness_reasons(
                state,
                json.loads(
                    (self.root / ".agentic-pipeline" / "findings.json").read_text(encoding="utf-8")
                ),
            ),
        )

    def test_owner_transfer_does_not_reset_full_convergence_wave_limit(self) -> None:
        state = self.initialize(research=False)
        state["phase"] = "engineering"
        state["engineering_owner_id"] = "engineer-1"
        state["owner_by_slice"]["SLICE-001"] = "engineer-1"
        state["slices"]["SLICE-001"]["owner_id"] = "engineer-1"
        state["slices"]["SLICE-001"]["full_convergence_waves"] = 1
        state["slices"]["SLICE-001"]["max_full_convergence_waves"] = 1
        self.write_state(state)
        transferred = json.loads(self.cli(
            "transfer-engineering-owner", "--from-owner", "engineer-1",
            "--to-owner", "engineer-2", "--slice-id", "SLICE-001",
            "--reason", "explicit ownership handoff",
        ).stdout)
        transferred = self.full_status()
        self.assertEqual(1, transferred["slices"]["SLICE-001"]["full_convergence_waves"])
        with self.assertRaisesRegex(runtime_controller.PipelineError, "limit exhausted"):
            runtime_controller.require_full_convergence_budget(transferred, ["SLICE-001"])

    def test_first_local_qa_fix_routes_to_engineering_then_threshold_holds(self) -> None:
        state = self.initialize(research=False)
        state["owner_by_slice"]["SLICE-001"] = "engineer-1"
        state["slices"]["SLICE-001"]["owner_id"] = "engineer-1"
        state["remediation_queue"] = [{
            "route": "SLICE-001", "finding_ids": ["F-QA-1"], "status": "pending",
            "owner_id": None, "returns_for_owner": None,
        }]
        runtime_controller.activate_next_remediation_batch(state)
        self.assertEqual("engineering", state["phase"])
        self.assertEqual(0, state["active_remediation_batch"]["returns_for_owner"])
        held = json.loads(json.dumps(state))
        held["remediation_queue"][0]["status"] = "pending"
        held["active_remediation_batch"] = None
        held["slices"]["SLICE-001"]["remediation_returns_by_owner"] = {"engineer-1": 3}
        runtime_controller.activate_next_remediation_batch(held)
        self.assertEqual("owner_handoff_hold", held["phase"])

    def test_recovery_cycle_authorization_resets_only_recovery_circuit(self) -> None:
        state = self.initialize(research=False)
        state["phase"] = "recovery_hold"
        state["recovery"] = {"cycles": 2, "status": "awaiting_remediation"}
        state["iteration_control"]["status"] = "checkpoint_required"
        state["iteration_control"]["consecutive_product_changes"] = 1
        self.write_state(state)
        resumed = json.loads(self.cli(
            "authorize-iteration", "--reason", "director approved one recovery retry"
        ).stdout)
        resumed = self.full_status()
        self.assertEqual("evidence_recovery", resumed["phase"])
        self.assertEqual(0, resumed["recovery"]["cycles"])
        self.assertEqual(1, resumed["iteration_control"]["consecutive_product_changes"])

    def test_full_review_budget_extension_requires_and_records_wave_capacity(self) -> None:
        state = self.initialize(research=False)
        state["worker_budget"].update(
            {
                "status": "checkpoint_required",
                "checkpoint_causes": ["full_review_waves"],
                "max_full_review_waves": 1,
                "full_review_waves": 1,
            }
        )
        self.write_state(state)
        rejected = self.cli(
            "authorize-budget", "--additional-workers", "1",
            "--additional-full-review-waves", "0", "--reason", "review retry",
            expected=2,
        )
        self.assertIn("authorize at least one additional wave", rejected.stderr)
        extended = json.loads(self.cli(
            "authorize-budget", "--additional-workers", "1",
            "--additional-full-review-waves", "2", "--reason", "approved full review extension",
        ).stdout)
        extended = self.full_status()
        self.assertEqual(3, extended["worker_budget"]["max_full_review_waves"])
        self.assertEqual([], extended["worker_budget"]["checkpoint_causes"])

    def test_ready_requires_terminal_handoff_coverage_exactly_equal_current_aggregate(self) -> None:
        state = self.ready_for_qa()
        capsule = self.capsule("reviewer", "qa", "qa-terminal-equality")
        self.cli(
            "qa-complete", "--revision", state["revision"],
            "--product-revision", state["product_revision"],
            "--support-revision", state["support_revision"],
            "--evidence-revision", state["evidence_revision"],
            "--run-id", "qa-terminal-equality", "--worker-id", "qa-terminal-equality",
            "--capsule", capsule, "--status", "pass",
            "--manual-execution", self.qa_manual_artifact(),
            "--report", self.artifact("qa", "qa-terminal-equality-report"),
        )
        state = self.state()
        self.cli(
            "documentation-not-required", "--mode", "derived_post_qa",
            "--plan-sha256", state["development_plan_sha256"],
            "--policy-evidence", "POLICY-DOC-NONE",
        )
        state = self.state()
        terminal_record = state["handoffs"][-1]
        terminal_path = self.root / terminal_record["path"]
        terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
        terminal["coverage_state"]["manual"] = "pending"
        terminal["handoff_sha256"] = runtime_controller.canonical_json_sha256(
            {key: value for key, value in terminal.items() if key != "handoff_sha256"}
        )
        terminal_path.write_text(json.dumps(terminal), encoding="utf-8")
        terminal_record["sha256"] = self.sha(terminal_path)
        terminal_record["handoff_sha256"] = terminal["handoff_sha256"]
        self.write_state(state)
        result = self.cli("ready", expected=1)
        self.assertIn("schema-2 terminal handoff is stale or incomplete", result.stdout)

        terminal["coverage_state"]["manual"] = state["coverage"]["feature"]["state"]["manual"]
        terminal["open_assumptions"] = [{
            "assumption_id": "ASSUME-READY-001",
            "statement": "An unresolved premise remains.",
            "owner": "engineer-1",
            "validation_point": "before readiness",
            "impact_if_false": "accepted behavior is not established",
        }]
        terminal["handoff_sha256"] = runtime_controller.canonical_json_sha256(
            {key: value for key, value in terminal.items() if key != "handoff_sha256"}
        )
        terminal_path.write_text(json.dumps(terminal), encoding="utf-8")
        terminal_record["sha256"] = self.sha(terminal_path)
        terminal_record["handoff_sha256"] = terminal["handoff_sha256"]
        self.write_state(state)
        result = self.cli("ready", expected=1)
        self.assertIn("schema-2 terminal handoff is stale or incomplete", result.stdout)

    def test_final_review_targeted_qa_closure_preserves_clean_through_ready(self) -> None:
        fixture = self.prepare_targeted_qa_closure_ready_state()
        state = self.state()
        clean = state["engineer_clean"]
        closure = state["closure_review"]

        self.assertEqual("ready", state["phase"])
        self.assertEqual("targeted_final_review_closure_chain", clean["source"])
        self.assertEqual([closure["run"]["run_id"]], clean["run_ids"])
        for key in (
            "revision", "product_revision", "support_revision", "evidence_revision"
        ):
            self.assertEqual(state[key], clean[key])
        self.assertEqual(fixture["prior_clean"], clean["base_engineer_clean"])
        self.assertEqual(
            [run["run_id"] for run in fixture["base_review_runs"]],
            clean["base_review_run_ids"],
        )
        self.assertEqual(closure["run"]["run_id"], clean["closure_run_id"])
        self.assertTrue(clean["audit_complete"])
        ready = json.loads(self.cli("ready").stdout)
        self.assertTrue(ready["ready"])
        self.assertEqual([], ready["reasons"])

    def test_review_finalize_preserves_exact_clean_and_review_lineage_for_targeted_closure(self) -> None:
        fixture = self.prepare_targeted_qa_closure_ready_state()
        revalidation = fixture["revalidation"]
        closure = fixture["closure_before_review"]

        self.assertEqual("final_review", revalidation["source"])
        self.assertEqual(fixture["prior_clean"], revalidation["base_engineer_clean"])
        self.assertEqual(fixture["base_review_runs"], revalidation["base_review_runs"])
        self.assertEqual(revalidation["base_engineer_clean"], closure["base_engineer_clean"])
        self.assertEqual(revalidation["base_review_runs"], closure["base_review_runs"])
        self.assertEqual("qa", closure["return_phase"])

    def test_targeted_convergence_clean_lineage_is_accepted_and_source_tamper_rejected(self) -> None:
        self.prepare_targeted_qa_closure_ready_state(
            prior_clean_source="targeted_convergence_closure"
        )
        state = self.state()
        self.assertEqual(
            "targeted_convergence_closure",
            state["engineer_clean"]["base_engineer_clean"]["source"],
        )
        closure = json.loads(json.dumps(state["closure_review"]))
        closure["base_engineer_clean"]["source"] = "untrusted_synthetic_clean"
        with self.assertRaisesRegex(
            runtime_controller.PipelineError, "prior convergence proof"
        ):
            runtime_controller.targeted_closure_engineer_clean_proof(
                self.root, state, closure, closure["run"]
            )

    def test_failed_or_stale_targeted_qa_closure_never_credits_clean(self) -> None:
        fixture = self.prepare_targeted_qa_closure_ready_state()
        state = self.state()
        clean = dict(state["engineer_clean"])
        closure = state["closure_review"]
        closure["status"] = "failed"
        with self.assertRaisesRegex(runtime_controller.PipelineError, "exact-current|complete"):
            runtime_controller.targeted_closure_engineer_clean_proof(
                self.root, state, closure, closure["run"]
            )
        closure["status"] = "passed"
        closure["run"]["revision"] = "0" * 64
        with self.assertRaisesRegex(runtime_controller.PipelineError, "exact-current|complete"):
            runtime_controller.targeted_closure_engineer_clean_proof(
                self.root, state, closure, closure["run"]
            )
        self.assertEqual(clean, self.state()["engineer_clean"])

    def test_targeted_qa_closure_rejects_substituted_base_lineage(self) -> None:
        fixture = self.prepare_targeted_qa_closure_ready_state()
        state = self.state()
        state["product_revalidation"] = fixture["revalidation"]
        original = state["closure_review"]
        mutations = {
            "different_clean_same_revision": lambda closure: closure[
                "base_engineer_clean"
            ].update(run_ids=["different-clean-run"]),
            "different_base_tuple": lambda closure: closure.update(
                base_revision="0" * 64
            ),
            "inconsistent_review_status": lambda closure: closure[
                "base_review_runs"
            ][0].update(status="pass"),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                closure = json.loads(json.dumps(original))
                mutate(closure)
                with self.assertRaises(runtime_controller.PipelineError):
                    runtime_controller.targeted_closure_engineer_clean_proof(
                        self.root, state, closure, closure["run"]
                    )

    def test_targeted_qa_closure_rejects_unrelated_current_engineer_run(self) -> None:
        fixture = self.prepare_targeted_qa_closure_ready_state()
        state = self.state()
        state["product_revalidation"] = fixture["revalidation"]
        closure = state["closure_review"]
        frozen = list(closure["finding_ids"])
        for engineer in state["engineer_runs"]:
            if engineer.get("result_revisions") == {
                key: state[key]
                for key in (
                    "revision", "product_revision", "support_revision", "evidence_revision"
                )
            }:
                engineer["resolved_findings"] = []
        unrelated = json.loads(json.dumps(state["engineer_runs"][-1]))
        unrelated["run_id"] = "unrelated-exact-current-engineer"
        unrelated["resolved_findings"] = ["F-UNRELATED"]
        state["engineer_runs"].append(unrelated)

        with self.assertRaisesRegex(
            runtime_controller.PipelineError, "Engineer completion"
        ):
            runtime_controller.targeted_closure_engineer_clean_proof(
                self.root, state, closure, closure["run"]
            )
        self.assertNotEqual(frozen, unrelated["resolved_findings"])

    def test_ready_rejects_off_phase_review_and_convergence_capsules_without_mutation(self) -> None:
        self.prepare_targeted_qa_closure_ready_state()
        state_path = self.root / ".agentic-pipeline" / "state.json"
        findings_path = self.root / ".agentic-pipeline" / "findings.json"
        for role, phase in (("reviewer", "review"), ("reviewer", "convergence")):
            with self.subTest(phase=phase):
                output = f"tests/{FEATURE}/verification/off-phase-{phase}.json"
                before_state = state_path.read_bytes()
                before_findings = findings_path.read_bytes()
                before_artifacts = {
                    self.rel(path): path.read_bytes()
                    for path in self.root.rglob("*") if path.is_file()
                }
                state = self.state()
                result = self.cli(
                    "context-capsule-create",
                    "--role", role,
                    "--phase", phase,
                    "--worker-id", f"off-phase-{phase}",
                    "--plan-sha256", state["development_plan_sha256"],
                    "--revision", state["revision"],
                    "--authority", f"{self.rel(self.prd)}={self.sha(self.prd)}:PRD-AC-001",
                    "--output-path", f"tests/{FEATURE}/reviews/off-phase-{phase}.json",
                    "--stop-condition", "stop",
                    "--max-authority-files", "5",
                    "--max-evidence-files", "12",
                    "--max-total-files", "20",
                    "--max-payload-bytes", "500000",
                    "--max-estimated-tokens", "200000",
                    "--output", output,
                    expected=2,
                )
                self.assertIn("Context capsule activation is off-phase", result.stderr)
                self.assertIn('"current_phase": "ready"', result.stderr)
                self.assertIn('"next_action": "run_ready"', result.stderr)
                self.assertEqual(before_state, state_path.read_bytes())
                self.assertEqual(before_findings, findings_path.read_bytes())
                self.assertEqual(
                    before_artifacts,
                    {
                        self.rel(path): path.read_bytes()
                        for path in self.root.rglob("*") if path.is_file()
                    },
                )
                self.assertFalse((self.root / output).exists())

    def test_documented_cross_phase_capsule_activations_remain_allowed(self) -> None:
        state = self.initialize(research=False)
        state["phase"] = "implementation_complete"
        self.write_state(state)
        normative = self.capsule(
            "documentation_finisher", "normative_documentation", "docs-cross-phase",
            allowed=(self.rel(self.src),),
        )
        self.assertTrue((self.root / normative).is_file())
        state = self.state()
        state["phase"] = "preflight"
        self.write_state(state)
        packet, _, _ = self.decision_packet()
        self.accept_user_authority(packet)
        decision = self.capsule(
            "decision_recorder", "decision_recording", "decision-cross-phase",
            allowed=(self.rel(self.ledger),), outputs=(self.rel(self.ledger),),
            authorities=(
                f"not_applicable={packet['items'][0]['authority']['sha256']}:{packet['items'][0]['authority']['section_or_id']}",
            ),
        )
        self.assertTrue((self.root / decision).is_file())

    def test_ready_targeted_closure_clean_recovery_is_exact_and_idempotent(self) -> None:
        self.prepare_targeted_qa_closure_ready_state(legacy_without_base_clean=True)
        before = self.state()
        before_identities = {
            key: before[key]
            for key in (
                "revision", "product_revision", "support_revision", "evidence_revision"
            )
        }
        before_inventory = json.loads(json.dumps(before["revision_inventory"]))
        before_records = json.loads(json.dumps(before["revision_records"]))

        recovered = json.loads(
            self.cli("recover-ready-targeted-closure-clean").stdout
        )

        self.assertEqual("recovered", recovered["status"])
        self.assertEqual("ready", recovered["phase"])
        self.assertEqual("run_ready", recovered["next_action"]["action"])
        self.assertEqual("RTC-0001", recovered["receipt"]["id"])
        state = self.state()
        self.assertEqual(before_identities, {key: state[key] for key in before_identities})
        self.assertEqual(before_inventory, state["revision_inventory"])
        self.assertEqual(before_records, state["revision_records"])
        self.assertEqual("targeted_final_review_closure_chain", state["engineer_clean"]["source"])
        receipt_path = self.root / recovered["receipt"]["path"]
        self.assertEqual(recovered["receipt"]["sha256"], self.sha(receipt_path))
        first_state = (self.root / ".agentic-pipeline" / "state.json").read_bytes()
        first_receipt = receipt_path.read_bytes()

        again = json.loads(
            self.cli("recover-ready-targeted-closure-clean").stdout
        )
        self.assertEqual("already_recovered", again["status"])
        self.assertEqual(recovered["receipt"], again["receipt"])
        self.assertEqual(first_state, (self.root / ".agentic-pipeline" / "state.json").read_bytes())
        self.assertEqual(first_receipt, receipt_path.read_bytes())
        self.assertTrue(json.loads(self.cli("ready").stdout)["ready"])

    def test_ready_targeted_closure_clean_recovery_rejects_broken_chain(self) -> None:
        mutations = {
            "revision": lambda state, findings: state["closure_review"]["run"].update(
                revision="0" * 64
            ),
            "closure_run": lambda state, findings: state["closure_review"].update(
                run={**state["closure_review"]["run"], "run_id": "different-run"}
            ),
            "credit": lambda state, findings: state["closure_review"]["run"].update(
                credit_manifest_sha256="0" * 64
            ),
            "base_review_missing": lambda state, findings: state["closure_review"].update(
                base_review_runs=[]
            ),
            "qa": lambda state, findings: state["qa"].update(report_sha256="0" * 64),
            "coverage": lambda state, findings: state["coverage"]["feature"][
                "finalized_manifest"
            ].update(sha256="0" * 64),
            "handoff": lambda state, findings: state["handoffs"][-1].update(
                sha256="0" * 64
            ),
            "lease": lambda state, findings: state.update(
                active_write_lease={"lease_id": "LEASE-BUSY", "status": "active"}
            ),
            "pending": lambda state, findings: state.update(
                pending_engineer_completion={"run_id": "PENDING"}
            ),
            "open_finding": lambda state, findings: findings["items"].append(
                {
                    "id": "F-OPEN", "status": "open", "severity": "major",
                    "blocking": True, "remediation_required": True,
                }
            ),
        }
        self.prepare_targeted_qa_closure_ready_state(
            legacy_without_base_clean=True
        )
        state_path = self.root / ".agentic-pipeline" / "state.json"
        findings_path = self.root / ".agentic-pipeline" / "findings.json"
        baseline_state = state_path.read_bytes()
        baseline_findings = findings_path.read_bytes()
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                state_path.write_bytes(baseline_state)
                findings_path.write_bytes(baseline_findings)
                state = self.state()
                findings = json.loads(findings_path.read_text(encoding="utf-8"))
                mutate(state, findings)
                if name == "open_finding":
                    state["canonical_findings"] = json.loads(json.dumps(findings))
                    state["findings_sha256"] = runtime_controller.canonical_json_sha256(
                        findings
                    )
                self.write_state(state)
                findings_path.write_text(json.dumps(findings), encoding="utf-8")
                before_state = state_path.read_bytes()
                before_findings = findings_path.read_bytes()

                result = self.cli(
                    "recover-ready-targeted-closure-clean", expected=2
                )

                self.assertTrue(result.stderr.strip())
                self.assertEqual(before_state, state_path.read_bytes())
                self.assertEqual(before_findings, findings_path.read_bytes())
                self.assertIsNone(self.state()["engineer_clean"])

    def test_ready_targeted_closure_clean_recovery_rejects_product_drift(self) -> None:
        self.prepare_targeted_qa_closure_ready_state(legacy_without_base_clean=True)
        self.src.write_text("VALUE = 999\n", encoding="utf-8")
        before = (self.root / ".agentic-pipeline" / "state.json").read_bytes()
        result = self.cli("recover-ready-targeted-closure-clean", expected=2)
        self.assertIn("drift", result.stderr.lower())
        self.assertEqual(before, (self.root / ".agentic-pipeline" / "state.json").read_bytes())

    def test_ready_targeted_closure_clean_recovery_rejects_existing_unproven_clean(self) -> None:
        self.prepare_targeted_qa_closure_ready_state()
        before = (self.root / ".agentic-pipeline" / "state.json").read_bytes()
        result = self.cli("recover-ready-targeted-closure-clean", expected=2)
        self.assertIn("already", result.stderr.lower())
        self.assertEqual(before, (self.root / ".agentic-pipeline" / "state.json").read_bytes())

    def test_ready_targeted_closure_recovery_crash_adopts_exact_orphan(self) -> None:
        self.prepare_targeted_qa_closure_ready_state(legacy_without_base_clean=True)
        state_path = self.root / ".agentic-pipeline" / "state.json"
        before = state_path.read_bytes()
        original_save = runtime_controller.save_runtime

        def fail_after_receipt(*_args, **_kwargs):
            raise runtime_controller.PipelineError("simulated ready recovery save crash")

        runtime_controller.save_runtime = fail_after_receipt
        try:
            args = type("Args", (), {"project_root": str(self.root)})()
            with self.assertRaisesRegex(
                runtime_controller.PipelineError, "simulated ready recovery save crash"
            ):
                runtime_controller.cmd_recover_ready_targeted_closure_clean(args)
        finally:
            runtime_controller.save_runtime = original_save
        receipt_path = (
            self.root / "tests" / FEATURE / "verification" / "controller"
            / "ready-targeted-closure-clean-recovery-0001.json"
        )
        orphan = receipt_path.read_bytes()
        self.assertEqual(before, state_path.read_bytes())

        recovered = json.loads(
            self.cli("recover-ready-targeted-closure-clean").stdout
        )
        self.assertEqual("recovered", recovered["status"])
        self.assertEqual(orphan, receipt_path.read_bytes())

    def test_ready_targeted_closure_recovery_adopts_exact_temporary_orphan(self) -> None:
        self.prepare_targeted_qa_closure_ready_state(legacy_without_base_clean=True)
        state_path = self.root / ".agentic-pipeline" / "state.json"
        before = state_path.read_bytes()
        original_save = runtime_controller.save_runtime

        def fail_after_receipt(*_args, **_kwargs):
            raise runtime_controller.PipelineError("simulated pre-replace crash")

        runtime_controller.save_runtime = fail_after_receipt
        try:
            args = type("Args", (), {"project_root": str(self.root)})()
            with self.assertRaisesRegex(runtime_controller.PipelineError, "pre-replace"):
                runtime_controller.cmd_recover_ready_targeted_closure_clean(args)
        finally:
            runtime_controller.save_runtime = original_save
        receipt_path = (
            self.root / "tests" / FEATURE / "verification" / "controller"
            / "ready-targeted-closure-clean-recovery-0001.json"
        )
        temporary = receipt_path.with_suffix(receipt_path.suffix + ".tmp")
        exact = receipt_path.read_bytes()
        receipt_path.rename(temporary)
        self.assertEqual(before, state_path.read_bytes())

        recovered = json.loads(self.cli("recover-ready-targeted-closure-clean").stdout)

        self.assertEqual("recovered", recovered["status"])
        self.assertFalse(temporary.exists())
        self.assertEqual(exact, receipt_path.read_bytes())

    def test_ready_targeted_closure_recovery_rejects_tampered_temporary_orphan(self) -> None:
        self.prepare_targeted_qa_closure_ready_state(legacy_without_base_clean=True)
        state_path = self.root / ".agentic-pipeline" / "state.json"
        original_save = runtime_controller.save_runtime

        def fail_after_receipt(*_args, **_kwargs):
            raise runtime_controller.PipelineError("simulated pre-replace crash")

        runtime_controller.save_runtime = fail_after_receipt
        try:
            args = type("Args", (), {"project_root": str(self.root)})()
            with self.assertRaisesRegex(runtime_controller.PipelineError, "pre-replace"):
                runtime_controller.cmd_recover_ready_targeted_closure_clean(args)
        finally:
            runtime_controller.save_runtime = original_save
        receipt_path = (
            self.root / "tests" / FEATURE / "verification" / "controller"
            / "ready-targeted-closure-clean-recovery-0001.json"
        )
        temporary = receipt_path.with_suffix(receipt_path.suffix + ".tmp")
        receipt_path.rename(temporary)
        tampered = json.loads(temporary.read_text(encoding="utf-8"))
        tampered["closure_run_id"] = "tampered-run"
        temporary.write_text(json.dumps(tampered), encoding="utf-8")
        before_state = state_path.read_bytes()
        before_temporary = temporary.read_bytes()

        result = self.cli("recover-ready-targeted-closure-clean", expected=2)

        self.assertIn("temporary path contains unrelated bytes", result.stderr)
        self.assertEqual(before_state, state_path.read_bytes())
        self.assertEqual(before_temporary, temporary.read_bytes())
        self.assertFalse(receipt_path.exists())

    def test_ready_targeted_closure_recovery_rejects_malformed_history_without_mutation(self) -> None:
        self.prepare_targeted_qa_closure_ready_state(legacy_without_base_clean=True)
        state = self.state()
        state["ready_targeted_closure_clean_recoveries"] = [{}, {}]
        self.write_state(state)
        state_path = self.root / ".agentic-pipeline" / "state.json"
        findings_path = self.root / ".agentic-pipeline" / "findings.json"
        before_state = state_path.read_bytes()
        before_findings = findings_path.read_bytes()
        before_artifacts = {
            self.rel(path): path.read_bytes()
            for path in self.root.rglob("*") if path.is_file()
        }

        result = self.cli("recover-ready-targeted-closure-clean", expected=2)

        self.assertIn("history is malformed", result.stderr)
        self.assertEqual(before_state, state_path.read_bytes())
        self.assertEqual(before_findings, findings_path.read_bytes())
        self.assertEqual(
            before_artifacts,
            {self.rel(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()},
        )

    def test_ready_targeted_closure_recovery_idempotency_revalidates_all_artifacts(self) -> None:
        mutations = {
            "qa_report": lambda state: Path(state["qa"]["report"]).write_text(
                "tampered\n", encoding="utf-8"
            ),
            "closure_credit": lambda state: Path(
                state["closure_review"]["run"]["credit_manifest"]
            ).write_text("tampered\n", encoding="utf-8"),
            "base_review_credit": lambda state: Path(
                state["closure_review"]["base_review_runs"][0]["credit_manifest"]
            ).write_text("tampered\n", encoding="utf-8"),
            "handoff_artifact": lambda state: (self.root / state["engineer_clean"]["handoff_path"]).write_text(
                "tampered\n", encoding="utf-8"
            ),
            "handoff_record": lambda state: state["handoffs"][-2].update(sha256="0" * 64),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                self.tearDown()
                self.setUp()
                self.prepare_targeted_qa_closure_ready_state(
                    legacy_without_base_clean=True
                )
                self.cli("recover-ready-targeted-closure-clean")
                state = self.state()
                mutate(state)
                if name == "handoff_record":
                    self.write_state(state)
                before = (self.root / ".agentic-pipeline" / "state.json").read_bytes()

                result = self.cli(
                    "recover-ready-targeted-closure-clean", expected=2
                )

                self.assertTrue(result.stderr.strip())
                self.assertEqual(
                    before,
                    (self.root / ".agentic-pipeline" / "state.json").read_bytes(),
                )

    def test_ready_targeted_closure_recovery_rejects_controller_root_symlink_in_project(self) -> None:
        self.prepare_targeted_qa_closure_ready_state(legacy_without_base_clean=True)
        controller_root = self.root / "tests" / FEATURE / "verification" / "controller"
        relocated = controller_root.with_name("controller-relocated")
        controller_root.rename(relocated)
        try:
            controller_root.symlink_to(relocated, target_is_directory=True)
        except OSError as exc:
            relocated.rename(controller_root)
            self.skipTest(f"directory symlink creation unavailable: {exc}")
        state_path = self.root / ".agentic-pipeline" / "state.json"
        before = state_path.read_bytes()

        result = self.cli("recover-ready-targeted-closure-clean", expected=2)

        self.assertIn("symlink", result.stderr.lower())
        self.assertEqual(before, state_path.read_bytes())
        self.assertFalse(
            (relocated / "ready-targeted-closure-clean-recovery-0001.json").exists()
        )

    def test_ready_targeted_closure_recovery_rejects_occupied_temporary_symlink(self) -> None:
        self.prepare_targeted_qa_closure_ready_state(legacy_without_base_clean=True)
        controller_root = self.root / "tests" / FEATURE / "verification" / "controller"
        temporary = controller_root / "ready-targeted-closure-clean-recovery-0001.json.tmp"
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        outside_target = Path(outside.name) / "outside.json"
        sentinel = b'{"outside":"unchanged"}\n'
        outside_target.write_bytes(sentinel)
        try:
            temporary.symlink_to(outside_target)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        state_path = self.root / ".agentic-pipeline" / "state.json"
        before = state_path.read_bytes()

        result = self.cli("recover-ready-targeted-closure-clean", expected=2)

        self.assertIn("temporary path is already occupied", result.stderr)
        self.assertEqual(before, state_path.read_bytes())
        self.assertEqual(sentinel, outside_target.read_bytes())

    def test_preflight_requires_complete_exact_capability_contract(self) -> None:
        self.initialize(research=False)
        state = self.state()
        state["phase"] = "preflight"
        self.write_state(state)
        args = [
            "preflight-complete", "--run-id", "preflight-incomplete",
            "--resource-budget-check", "pass",
            "--report", self.artifact("verification", "preflight-incomplete"),
        ]
        for name in sorted(runtime_controller.required_preflight_capabilities(state) - {"test-server-two-clients"}):
            args.extend(("--capability", f"{name}=available"))
        result = self.cli(*args, expected=2)
        self.assertIn("test-server-two-clients", result.stderr)
        self.assertEqual("preflight", self.state()["phase"])

    def test_all_controller_review_completions_require_capsules_and_recovery_credit(self) -> None:
        parser = runtime_controller.build_parser()
        commands = parser._subparsers._group_actions[0].choices
        for command in (
            "convergence-audit-complete",
            "review-complete",
            "closure-review-complete",
            "recovery-review-complete",
        ):
            actions = {action.dest: action for action in commands[command]._actions}
            self.assertTrue(actions["capsule"].required, command)
        recovery_actions = {
            action.dest: action
            for action in commands["recovery-review-complete"]._actions
        }
        self.assertTrue(recovery_actions["credit_manifest"].required)

    def test_capsule_budget_may_be_below_but_not_above_plan_ceiling(self) -> None:
        state = self.implementation_complete()
        self.cli(
            "documentation-not-required", "--mode", "normative_pre_review",
            "--plan-sha256", state["development_plan"]["sha256"],
            "--policy-evidence", "POLICY-DOC-NONE",
        )
        state = self.state()
        output = f"tests/{FEATURE}/verification/smaller-capsule.json"
        args = [
            "context-capsule-create", "--role", "reviewer",
            "--phase", "convergence",
            "--worker-id", "smaller-verifier", "--plan-sha256", state["development_plan_sha256"],
            "--revision", state["revision"],
            "--authority",
            f"{self.rel(self.prd)}={self.sha(self.prd)}:PRD-REQ-001,PRD-AC-001",
            "--authority", f"{self.rel(self.spec)}={self.sha(self.spec)}",
            "--authority", f"{self.rel(self.plan)}={self.sha(self.plan)}",
            "--output-path", f"tests/{FEATURE}/reviews/smaller.json",
            "--stop-condition", "review assigned evidence and stop",
            "--max-authority-files", "3", "--max-evidence-files", "2",
            "--max-total-files", "5", "--max-payload-bytes", "100000",
            "--max-estimated-tokens", "50000", "--output", output,
        ]
        _, coverage_ids = runtime_controller.capsule_manifest_contract(
            self.root, state, "convergence"
        )
        for identity_id in sorted(coverage_ids):
            args.extend(("--coverage-identity-id", identity_id))
        for evidence_path, evidence_sha in sorted(
            runtime_controller.capsule_exact_evidence(
                self.root, state, "reviewer", "convergence"
            ).items()
        ):
            args.extend(("--evidence", f"{evidence_path}={evidence_sha}"))
        result = json.loads(self.cli(*args).stdout)
        self.assertEqual(3, result["budget"]["max_authority_files"])
        self.assertLess(result["budget"]["max_payload_bytes"], 500000)

    def test_generic_resolve_finding_command_is_removed(self) -> None:
        parser = runtime_controller.build_parser()
        command_action = next(
            action for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        self.assertNotIn("resolve-finding", command_action.choices)

    def test_completion_proof_flags_expose_only_pass(self) -> None:
        commands = runtime_controller.build_parser()._subparsers._group_actions[0].choices
        expected = {
            "engineer-complete": {"machine_checks", "diff_inspection"},
            "coverage-finalize": {
                "expected_actual_equality",
                "mandatory_registration",
                "automated_execution",
            },
            "recovery-remediation-complete": {"machine_checks"},
        }
        for command, destinations in expected.items():
            actions = {action.dest: action for action in commands[command]._actions}
            for destination in destinations:
                self.assertEqual(("pass",), actions[destination].choices)

    def test_accept_finding_rejects_generic_user_receipt(self) -> None:
        self.initialize(research=False)
        revision = self.state()["revision"]
        findings_path, _ = self.inject_canonical_finding(
            {"id": "F-RISK-BAD", "status": "open", "severity": "minor", "blocking": False,
             "revision": revision}
        )
        self.cli(
            "user-authority-accept", "--authority-id", "AUTH-RISK-BAD",
            "--approval-reference", "USER-RISK-BAD", "--statement", "Accept generic risk",
        )
        before = findings_path.read_bytes()
        result = self.cli(
            "accept-finding", "--id", "F-RISK-BAD", "--reason", "bounded risk",
            "--revision", revision, "--authority-id", "AUTH-RISK-BAD", expected=2,
        )
        self.assertIn("exact finding, revision, and reason", result.stderr)
        self.assertEqual(before, findings_path.read_bytes())

    def test_required_support_contract_routes_review_rework_without_product_blocking(self) -> None:
        self.initialize(research=False)
        state = self.state()
        state["plan_contracts"]["slices"]["SLICE-001"]["documentation"][
            "derived_post_qa_paths"
        ] = "docs/operator.md"
        state["phase"] = "review"
        state["review"].update(
            {
                "status": "awaiting_decision",
                "revision": state["revision"],
                "product_revision": state["product_revision"],
                "support_revision": state["support_revision"],
                "evidence_revision": state["evidence_revision"],
                "runs": [
                    {"reviewer_id": "r-support-1", "status": "fail"},
                ],
            }
        )
        self.write_state(state)
        self.cli(
            "add-finding", "--id", "F-SUPPORT-1", "--source", "review",
            "--finding-kind", "support", "--severity", "major",
            "--scope-relation", "current_feature_path", "--introduced-by-candidate", "false",
            "--production-reachability", "normal", "--violates-required-invariant", "false",
            "--blocks-required-support-contract", "true",
            "--required-support-contract-evidence", "docs/operator.md",
            "--mandatory-core-acceptance-evidence-missing", "false",
            "--test-can-miss-product-defect", "false", "--title", "Operator handoff missing",
            "--evidence", "review report statement", "--revision", state["revision"],
        )
        finding = json.loads(
            (self.root / ".agentic-pipeline" / "findings.json").read_text(encoding="utf-8")
        )["items"][0]
        self.assertFalse(finding["blocking"])
        self.assertTrue(finding["remediation_required"])
        routed = json.loads(self.cli(
            "review-finalize", "--revision", state["revision"], "--decision", "rework",
            "--rework-scope", "support", "--report", self.artifact("reviews", "support-rework"),
        ).stdout)
        routed = self.full_status()
        self.assertEqual("evidence_recovery", routed["phase"])
        self.assertEqual(["F-SUPPORT-1"], routed["recovery"]["finding_ids"])

    def test_qa_mixed_external_gates_have_deterministic_overall_status(self) -> None:
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8").replace(
                "- capability_prerequisites: test-server-two-clients",
                "- capability_prerequisites: test-server-two-clients, "
                "config-credentials, persistence-datastore",
            ),
            encoding="utf-8",
        )
        self.write_planning_state()
        self.optional_manual_identities = [
            self.optional_manual_identity(
                "MANUAL-SLICE-001-OPTIONAL-USER",
                capability_prerequisites=("config-credentials",),
            ),
            self.optional_manual_identity(
                "MANUAL-SLICE-001-OPTIONAL-ENV",
                capability_prerequisites=("persistence-datastore",),
            ),
        ]
        state = self.ready_for_qa()
        statuses = {
            name: "available"
            for name in runtime_controller.required_qa_capabilities(self.root, state)
        }
        statuses["config-credentials"] = "blocked_user"
        statuses["persistence-datastore"] = "blocked_environment"
        probe_args = [
            "qa-capability-probe", "--revision", state["revision"], "--probe-id", "probe-mixed",
            "--report", self.artifact("qa", "probe-mixed"),
            "--minimum-resume-action", "config-credentials=user|true|authorize credentials",
            "--minimum-resume-action",
            "persistence-datastore=technical_director|false|provide datastore",
        ]
        for name, status in statuses.items():
            probe_args.extend(("--capability", f"{name}={status}"))
        self.cli(*probe_args)
        mandatory = self.passed_manual_row("MANUAL-SLICE-001-RUNTIME", "mixed-mandatory")
        rows = [mandatory]
        for identity_id, gate in (
            ("MANUAL-SLICE-001-OPTIONAL-USER", "blocked_user"),
            ("MANUAL-SLICE-001-OPTIONAL-ENV", "blocked_environment"),
        ):
            rows.append(
                {"identity_id": identity_id, "executed": False, "passed": None,
                 "deferred": True, "blocked_by_finding": None, "qa_evidence": None,
                 "gate": gate, "minimum_resume_action": f"resume {identity_id}"}
            )
        capsule = self.capsule("reviewer", "qa", "qa-mixed")
        state = self.state()
        result = json.loads(self.cli(
            "qa-complete", "--revision", state["revision"],
            "--product-revision", state["product_revision"],
            "--support-revision", state["support_revision"],
            "--evidence-revision", state["evidence_revision"],
            "--run-id", "qa-mixed", "--worker-id", "qa-mixed", "--capsule", capsule,
            "--status", "blocked_user", "--manual-execution",
            self.qa_manual_rows_artifact(rows, "mixed-manual"),
            "--pending-identity", "MANUAL-SLICE-001-OPTIONAL-USER",
            "--pending-identity", "MANUAL-SLICE-001-OPTIONAL-ENV",
            "--reason", "two independent external gates",
            "--report", self.artifact("qa", "qa-mixed-report"),
        ).stdout)
        self.assertEqual("blocked_user", result["qa"]["status"])
        self.assertEqual(
            2, result["active_ids"]["pending_qa_identity_ids"]["total"]
        )
        manual_gate_categories = {
            gate["category"]
            for gate in self.state()["gates"]
            if gate["id"].startswith("qa:qa-mixed:")
        }
        self.assertEqual({"blocked_user", "blocked_environment"}, manual_gate_categories)

    def test_qa_optional_failure_passes_only_with_exact_accepted_finding(self) -> None:
        optional_id = "MANUAL-SLICE-001-OPTIONAL"
        self.optional_manual_identities = [self.optional_manual_identity(optional_id)]
        state = self.ready_for_qa()
        self.cli(
            "add-finding", "--id", "F-QA-OPTIONAL", "--source", "qa",
            "--finding-kind", "product", "--severity", "minor",
            "--scope-relation", "current_feature_path", "--introduced-by-candidate", "false",
            "--production-reachability", "normal", "--violates-required-invariant", "false",
            "--mandatory-core-acceptance-evidence-missing", "false",
            "--test-can-miss-product-defect", "false", "--coverage-identity-id", optional_id,
            "--title", "Optional telemetry differs", "--evidence", "exact optional observation",
            "--revision", state["revision"],
        )
        reason = "optional telemetry is nonblocking"
        authority_id = "AUTH-QA-OPTIONAL"
        self.cli(
            "user-authority-accept", "--authority-id", authority_id,
            "--approval-reference", "USER-QA-OPTIONAL",
            "--statement",
            f"Accept residual risk for finding F-QA-OPTIONAL at revision {state['revision']}: {reason}",
        )
        self.cli(
            "accept-finding", "--id", "F-QA-OPTIONAL", "--reason", reason,
            "--revision", state["revision"], "--authority-id", authority_id,
        )
        optional_row = self.passed_manual_row(optional_id, "optional-failed")
        optional_row["passed"] = False
        rows = [
            self.passed_manual_row("MANUAL-SLICE-001-RUNTIME", "optional-mandatory"),
            optional_row,
        ]
        capsule = self.capsule("reviewer", "qa", "qa-optional")
        state = self.state()
        result = json.loads(self.cli(
            "qa-complete", "--revision", state["revision"],
            "--product-revision", state["product_revision"],
            "--support-revision", state["support_revision"],
            "--evidence-revision", state["evidence_revision"],
            "--run-id", "qa-optional", "--worker-id", "qa-optional", "--capsule", capsule,
            "--status", "pass", "--manual-execution",
            self.qa_manual_rows_artifact(rows, "optional-manual"),
            "--report", self.artifact("qa", "qa-optional-report"),
        ).stdout)
        self.assertEqual("pass", result["qa"]["status"])
        self.assertEqual("derived_documentation", result["phase"])

    def test_runtime_init_rejects_prose_plan_capability_id(self) -> None:
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8").replace(
                "- capability_prerequisites: test-server-two-clients",
                "- capability_prerequisites: server plus two clients",
            ),
            encoding="utf-8",
        )
        self.write_planning_state()
        result = self.cli(
            "init", "--feature", FEATURE, "--requirements", self.rel(self.prd),
            "--spec", self.rel(self.spec), "--plan", self.rel(self.plan),
            "--plan-sha256", self.sha(self.plan), "--base-revision", "base-0",
            "--decision-ledger", self.rel(self.ledger), expected=2,
        )
        self.assertIn("capability ID", result.stderr)

    def test_runtime_init_rejects_acceptance_range_shorthand(self) -> None:
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8").replace(
                "- acceptance_ids: PRD-AC-001",
                "- acceptance_ids: PRD-AC-001..003",
            ),
            encoding="utf-8",
        )
        self.write_planning_state()
        result = self.cli(
            "init", "--feature", FEATURE, "--requirements", self.rel(self.prd),
            "--spec", self.rel(self.spec), "--plan", self.rel(self.plan),
            "--plan-sha256", self.sha(self.plan), "--base-revision", "base-0",
            "--decision-ledger", self.rel(self.ledger), expected=2,
        )
        self.assertIn("non-literal acceptance ID", result.stderr)

    def test_runtime_init_rejects_pending_plan_revision_transition(self) -> None:
        self.write_planning_state()
        planning_path = self.root / ".agentic-pipeline" / "development-plan-state.json"
        planning = json.loads(planning_path.read_text(encoding="utf-8"))
        planning["status"] = "revision_reopen_pending"
        planning["revision_reopen"] = {
            "prior_approved_sha256": self.sha(self.plan),
            "draft_sha256": "0" * 64,
        }
        planning_path.write_text(json.dumps(planning), encoding="utf-8")

        result = self.cli(
            "init", "--feature", FEATURE, "--requirements", self.rel(self.prd),
            "--spec", self.rel(self.spec), "--plan", self.rel(self.plan),
            "--plan-sha256", self.sha(self.plan), "--base-revision", "base-0",
            "--decision-ledger", self.rel(self.ledger), expected=2,
        )

        self.assertIn("does not prove approval", result.stderr)
        self.assertFalse((self.root / ".agentic-pipeline" / "state.json").exists())

    def test_runtime_init_rejects_unknown_only_acceptance_id(self) -> None:
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8").replace(
                "PRD-AC-001", "PRD-AC-unknown-only"
            ),
            encoding="utf-8",
        )
        self.write_planning_state()
        result = self.cli(
            "init", "--feature", FEATURE, "--requirements", self.rel(self.prd),
            "--spec", self.rel(self.spec), "--plan", self.rel(self.plan),
            "--plan-sha256", self.sha(self.plan), "--base-revision", "base-0",
            "--decision-ledger", self.rel(self.ledger), expected=2,
        )
        self.assertIn("absent from the approved PRD inventory", result.stderr)
        self.assertIn("unknown-only", result.stderr)

    def test_runtime_init_rejects_mixed_valid_and_unknown_acceptance_ids(self) -> None:
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
        self.write_planning_state()
        result = self.cli(
            "init", "--feature", FEATURE, "--requirements", self.rel(self.prd),
            "--spec", self.rel(self.spec), "--plan", self.rel(self.plan),
            "--plan-sha256", self.sha(self.plan), "--base-revision", "base-0",
            "--decision-ledger", self.rel(self.ledger), expected=2,
        )
        self.assertIn("absent from the approved PRD inventory", result.stderr)
        self.assertIn("unknown-mixed", result.stderr)

    def test_runtime_parser_defense_rejects_unknown_only_and_mixed_ids(self) -> None:
        approved_inventory = frozenset({"PRD-AC-001"})
        original = self.plan.read_text(encoding="utf-8")
        candidates = (
            original.replace("PRD-AC-001", "PRD-AC-unknown-only"),
            original
            .replace(
                "### Requirements\n\n- PRD-REQ-001\n- PRD-AC-001",
                "### Requirements\n\n- PRD-REQ-001\n- PRD-AC-001\n- PRD-AC-unknown-mixed",
            )
            .replace(
                "- acceptance_ids: PRD-AC-001",
                "- acceptance_ids: PRD-AC-001, PRD-AC-unknown-mixed",
            ),
        )
        for candidate in candidates:
            with self.subTest(candidate="mixed" if "unknown-mixed" in candidate else "only"):
                with self.assertRaisesRegex(
                    runtime_controller.PipelineError, "absent from the approved PRD"
                ):
                    runtime_controller.plan_slice_blocks(candidate, approved_inventory)

        coverage_unknown = original.replace(
            "### Coverage Contract\n\n- acceptance_ids: PRD-AC-001",
            "### Coverage Contract\n\n- acceptance_ids: PRD-AC-unknown-coverage",
        )
        valid_slices = runtime_controller.plan_slice_blocks(original, approved_inventory)
        with self.assertRaisesRegex(
            runtime_controller.PipelineError, "absent from the approved PRD"
        ):
            runtime_controller.runtime_plan_contracts(
                coverage_unknown, valid_slices, approved_inventory
            )

    def test_runtime_direct_and_cli_ignore_incidental_acceptance_ids(self) -> None:
        self.prd.write_text(
            self.prd.read_text(encoding="utf-8").replace(
                "The project baseline is available.",
                "The project baseline is available.\n\nExample only: PRD-AC-incidental.",
            ),
            encoding="utf-8",
        )
        self.refresh_spec_plan_and_state_for_current_prd()
        inventory = runtime_controller.derive_prd_acceptance_inventory(
            self.prd.read_text(encoding="utf-8"), label="approved PRD"
        )
        self.assertNotIn("PRD-AC-incidental", inventory)
        candidate = self.plan.read_text(encoding="utf-8").replace(
            "PRD-AC-001", "PRD-AC-incidental"
        )
        with self.assertRaisesRegex(
            runtime_controller.PipelineError, "absent from the approved PRD"
        ):
            runtime_controller.plan_slice_blocks(candidate, inventory)
        self.plan.write_text(candidate, encoding="utf-8")
        self.write_planning_state()
        result = self.cli(
            "init", "--feature", FEATURE, "--requirements", self.rel(self.prd),
            "--spec", self.rel(self.spec), "--plan", self.rel(self.plan),
            "--plan-sha256", self.sha(self.plan), "--base-revision", "base-0",
            "--decision-ledger", self.rel(self.ledger), expected=2,
        )
        self.assertIn("absent from the approved PRD inventory", result.stderr)

    def test_runtime_direct_and_cli_reject_unicode_text_ranges_and_duplicate_criteria(self) -> None:
        invalid_declarations = (
            "- PRD-AC-001",
            "- PRD-AC-001:",
            "- PRD-AC-001_invalid: adjacent invalid token",
            "- PRD-AC-001…003 — Unicode range",
            "- PRD-AC-001 to PRD-AC-003 — textual range",
            "- PRD-AC-001\n  ..\n  003: multiline range",
            "- PRD-AC-001 to\n  PRD-AC-003: multiline textual range",
            "- PRD-AC-001: first\n- PRD-AC-001: duplicate",
        )
        for invalid in invalid_declarations:
            with self.subTest(invalid=invalid):
                text = self.prd.read_text(encoding="utf-8")
                text = text.replace("- PRD-AC-001: approved criterion", invalid)
                self.prd.write_text(text, encoding="utf-8")
                self.refresh_spec_plan_and_state_for_current_prd()
                with self.assertRaises(ValueError):
                    runtime_controller.derive_prd_acceptance_inventory(
                        text, label="approved PRD"
                    )
                result = self.cli(
                    "init", "--feature", FEATURE,
                    "--requirements", self.rel(self.prd), "--spec", self.rel(self.spec),
                    "--plan", self.rel(self.plan), "--plan-sha256", self.sha(self.plan),
                    "--base-revision", "base-0", "--decision-ledger", self.rel(self.ledger),
                    expected=2,
                )
                self.assertRegex(
                    result.stderr,
                    "must use exact|range shorthand|repeats criterion|semantic",
                )
                self.temporary.cleanup()
                self.setUp()

    def test_runtime_direct_and_cli_use_markdown_structural_prd_authority(self) -> None:
        examples = (
            "```md\n## Acceptance Criteria\n- PRD-AC-fenced: no\n```",
            "~~~~ markdown\n## Acceptance Criteria\n- PRD-AC-fenced: no\n~~~~",
            "    ## Acceptance Criteria\n    - PRD-AC-indented: no",
            "> ## Acceptance Criteria\n> - PRD-AC-quoted: no",
        )
        for example in examples:
            with self.subTest(example=example):
                self.prd.write_text(
                    self.prd.read_text(encoding="utf-8").replace(
                        "## Acceptance Criteria\n",
                        "## Acceptance Criteria\n\n" + example + "\n",
                    ),
                    encoding="utf-8",
                )
                self.refresh_spec_plan_and_state_for_current_prd()
                inventory = runtime_controller.derive_prd_acceptance_inventory(
                    self.prd.read_text(encoding="utf-8"), label="approved PRD"
                )
                self.assertEqual(frozenset({"PRD-AC-001"}), inventory)
                self.initialize(research=False)
                self.temporary.cleanup()
                self.setUp()

    def test_runtime_direct_and_cli_accept_public_alnum_hyphen_id(self) -> None:
        self.prd.write_text(
            self.prd.read_text(encoding="utf-8").replace("PRD-AC-001", "PRD-AC-save-v2"),
            encoding="utf-8",
        )
        self.refresh_spec_plan_and_state_for_current_prd()
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8").replace("PRD-AC-001", "PRD-AC-save-v2"),
            encoding="utf-8",
        )
        self.write_planning_state()
        inventory = runtime_controller.derive_prd_acceptance_inventory(
            self.prd.read_text(encoding="utf-8"), label="approved PRD"
        )
        runtime_controller.plan_slice_blocks(self.plan.read_text(encoding="utf-8"), inventory)
        self.initialize(research=False)

    def test_runtime_direct_and_cli_reject_fenced_only_or_near_prd_heading(self) -> None:
        replacements = (
            "```\n## Acceptance Criteria\n- PRD-AC-001: hidden\n```",
            "    ## Acceptance Criteria\n    - PRD-AC-001: hidden",
            "> ## Acceptance Criteria\n> - PRD-AC-001: hidden",
            "### Acceptance Criteria\n- PRD-AC-001: near",
        )
        canonical = "## Acceptance Criteria\n\n- PRD-AC-001: approved criterion"
        for replacement in replacements:
            with self.subTest(replacement=replacement):
                text = self.prd.read_text(encoding="utf-8").replace(canonical, replacement)
                self.prd.write_text(text, encoding="utf-8")
                self.refresh_spec_plan_and_state_for_current_prd()
                with self.assertRaisesRegex(ValueError, "exactly one exact top-level"):
                    runtime_controller.derive_prd_acceptance_inventory(
                        text, label="approved PRD"
                    )
                result = self.cli(
                    "init", "--feature", FEATURE,
                    "--requirements", self.rel(self.prd), "--spec", self.rel(self.spec),
                    "--plan", self.rel(self.plan), "--plan-sha256", self.sha(self.plan),
                    "--base-revision", "base-0", "--decision-ledger", self.rel(self.ledger),
                    expected=2,
                )
                self.assertIn("exactly one exact top-level", result.stderr)
                self.temporary.cleanup()
                self.setUp()

    def test_runtime_requirements_reject_shared_full_and_short_range_matrix(self) -> None:
        inventory = runtime_controller.derive_prd_acceptance_inventory(
            self.prd.read_text(encoding="utf-8"), label="approved PRD"
        )
        ranges = (
            "PRD-AC-001.002",
            "PRD-AC-001 .. PRD-AC-002",
            "PRD-AC-001…002",
            "PRD-AC-001 – PRD-AC-002",
            "PRD-AC-001—002",
            "PRD-AC-001 to PRD-AC-002",
            "PRD-AC-save-v1 TO save-v2",
            "PRD-AC-001\n  ..\n  PRD-AC-002",
            "PRD-AC-001 to\n  002",
            "PRD-AC-001\n  — 002",
        )
        for acceptance_range in ranges:
            with self.subTest(acceptance_range=acceptance_range):
                candidate = self.plan.read_text(encoding="utf-8").replace(
                    "- PRD-AC-001\n", f"- {acceptance_range}\n"
                )
                with self.assertRaisesRegex(runtime_controller.PipelineError, "range shorthand"):
                    runtime_controller.plan_slice_blocks(candidate, inventory)
                self.plan.write_text(candidate, encoding="utf-8")
                self.write_planning_state()
                result = self.cli(
                    "init", "--feature", FEATURE,
                    "--requirements", self.rel(self.prd), "--spec", self.rel(self.spec),
                    "--plan", self.rel(self.plan), "--plan-sha256", self.sha(self.plan),
                    "--base-revision", "base-0", "--decision-ledger", self.rel(self.ledger),
                    expected=2,
                )
                self.assertIn("range shorthand", result.stderr)
                self.temporary.cleanup()
                self.setUp()

    def test_runtime_requirements_reject_adjacent_invalid_id_direct_and_cli(self) -> None:
        inventory = runtime_controller.derive_prd_acceptance_inventory(
            self.prd.read_text(encoding="utf-8"), label="approved PRD"
        )
        candidate = self.plan.read_text(encoding="utf-8").replace(
            "- PRD-AC-001\n", "- PRD-AC-001_invalid\n"
        )
        with self.assertRaises(runtime_controller.PipelineError):
            runtime_controller.plan_slice_blocks(candidate, inventory)
        self.plan.write_text(candidate, encoding="utf-8")
        self.write_planning_state()
        result = self.cli(
            "init", "--feature", FEATURE,
            "--requirements", self.rel(self.prd), "--spec", self.rel(self.spec),
            "--plan", self.rel(self.plan), "--plan-sha256", self.sha(self.plan),
            "--base-revision", "base-0", "--decision-ledger", self.rel(self.ledger),
            expected=2,
        )
        self.assertTrue(result.stderr)

    def test_runtime_structural_html_rendering_and_nested_range_direct_cli(self) -> None:
        hidden = "<pre>\n## Acceptance Criteria\n- PRD-AC-hidden: no\n</pre>"
        self.prd.write_text(
            self.prd.read_text(encoding="utf-8").replace(
                "- PRD-AC-001: approved criterion",
                "- PRD-AC-001: approved criterion\n" + hidden,
            ),
            encoding="utf-8",
        )
        self.refresh_spec_plan_and_state_for_current_prd()
        inventory = runtime_controller.derive_prd_acceptance_inventory(
            self.prd.read_text(encoding="utf-8"), label="approved PRD"
        )
        self.assertEqual(frozenset({"PRD-AC-001"}), inventory)
        self.initialize(research=False)

        self.temporary.cleanup()
        self.setUp()
        inventory = runtime_controller.derive_prd_acceptance_inventory(
            self.prd.read_text(encoding="utf-8"), label="approved PRD"
        )
        candidate = self.plan.read_text(encoding="utf-8").replace(
            "- PRD-AC-001\n", "- outer\n  - PRD-AC-001…002\n"
        )
        with self.assertRaisesRegex(runtime_controller.PipelineError, "range shorthand"):
            runtime_controller.plan_slice_blocks(candidate, inventory)
        self.plan.write_text(candidate, encoding="utf-8")
        self.write_planning_state()
        result = self.cli(
            "init", "--feature", FEATURE,
            "--requirements", self.rel(self.prd), "--spec", self.rel(self.spec),
            "--plan", self.rel(self.plan), "--plan-sha256", self.sha(self.plan),
            "--base-revision", "base-0", "--decision-ledger", self.rel(self.ledger),
            expected=2,
        )
        self.assertIn("range shorthand", result.stderr)

    def test_runtime_rejects_hidden_rendering_and_unicode_boundary_direct_cli(self) -> None:
        canonical = "- PRD-AC-001: approved criterion"
        for invalid in (
            "- PRD-AC-001: <!-- hidden -->",
            "- PRD-AC-001: <br>",
            "- PRD-AC-001: [](url)",
            "- PRD-AC-001\u203f: invalid boundary",
        ):
            with self.subTest(invalid=invalid):
                text = self.prd.read_text(encoding="utf-8").replace(canonical, invalid)
                self.prd.write_text(text, encoding="utf-8")
                self.refresh_spec_plan_and_state_for_current_prd()
                with self.assertRaises(ValueError):
                    runtime_controller.derive_prd_acceptance_inventory(text, label="approved PRD")
                result = self.cli(
                    "init", "--feature", FEATURE,
                    "--requirements", self.rel(self.prd), "--spec", self.rel(self.spec),
                    "--plan", self.rel(self.plan), "--plan-sha256", self.sha(self.plan),
                    "--base-revision", "base-0", "--decision-ledger", self.rel(self.ledger),
                    expected=2,
                )
                self.assertTrue(result.stderr)
                self.temporary.cleanup()
                self.setUp()

    def test_runtime_commonmark_sixth_audit_matrix_direct_and_cli(self) -> None:
        canonical = "- PRD-AC-001: approved criterion"
        hidden = (
            "<textarea>\n## Acceptance Criteria\n- PRD-AC-hidden: no\n</textarea>",
            "<?pi\n## Acceptance Criteria\n?>",
            "<![CDATA[\n## Acceptance Criteria\n]]>",
            "<custom-tag>\n## Acceptance Criteria\n- PRD-AC-hidden: no\n\n",
        )
        for block in hidden:
            with self.subTest(block=block):
                self.prd.write_text(
                    self.prd.read_text(encoding="utf-8").replace(canonical, canonical + "\n" + block),
                    encoding="utf-8",
                )
                self.refresh_spec_plan_and_state_for_current_prd()
                inventory = runtime_controller.derive_prd_acceptance_inventory(
                    self.prd.read_text(encoding="utf-8"), label="approved PRD"
                )
                self.assertEqual(frozenset({"PRD-AC-001"}), inventory)
                self.initialize(research=False)
                self.temporary.cleanup()
                self.setUp()
        invalid = (
            "- PRD-AC-001: <template>hidden</template>",
            "- PRD-AC-001: ``unmatched `",
            "- PRD-AC-001\u202e: boundary",
            "- PRD-AC-001 **..** `002`: rendered range",
        )
        for declaration in invalid:
            with self.subTest(declaration=declaration):
                text = self.prd.read_text(encoding="utf-8").replace(canonical, declaration)
                self.prd.write_text(text, encoding="utf-8")
                self.refresh_spec_plan_and_state_for_current_prd()
                with self.assertRaises(ValueError):
                    runtime_controller.derive_prd_acceptance_inventory(text, label="approved PRD")
                result = self.cli(
                    "init", "--feature", FEATURE,
                    "--requirements", self.rel(self.prd), "--spec", self.rel(self.spec),
                    "--plan", self.rel(self.plan), "--plan-sha256", self.sha(self.plan),
                    "--base-revision", "base-0", "--decision-ledger", self.rel(self.ledger),
                    expected=2,
                )
                self.assertTrue(result.stderr)
                self.temporary.cleanup()
                self.setUp()

        inventory = runtime_controller.derive_prd_acceptance_inventory(
            self.prd.read_text(encoding="utf-8"), label="approved PRD"
        )
        candidate = self.plan.read_text(encoding="utf-8").replace(
            "- PRD-AC-001\n", "- PRD-AC-001 &hellip; [002](trace)\n"
        )
        with self.assertRaisesRegex(runtime_controller.PipelineError, "literal acceptance ID"):
            runtime_controller.plan_slice_blocks(candidate, inventory)
        self.plan.write_text(candidate, encoding="utf-8")
        self.write_planning_state()
        result = self.cli(
            "init", "--feature", FEATURE,
            "--requirements", self.rel(self.prd), "--spec", self.rel(self.spec),
            "--plan", self.rel(self.plan), "--plan-sha256", self.sha(self.plan),
            "--base-revision", "base-0", "--decision-ledger", self.rel(self.ledger),
            expected=2,
        )
        self.assertIn("literal acceptance ID", result.stderr)

    def test_qa_probe_excludes_plan_capability_unused_by_manual_identities(self) -> None:
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8").replace(
                "- capability_prerequisites: test-server-two-clients",
                "- capability_prerequisites: test-server-two-clients, custom-runtime-probe",
            ),
            encoding="utf-8",
        )
        self.write_planning_state()
        self.initialize()
        state = self.state()
        self.assertEqual(
            "available", state["preflight"]["capabilities"]["custom-runtime-probe"]
        )
        self.engineer()
        self.finalize_coverage()
        state = self.state()
        state["phase"] = "qa"
        self.write_state(state)
        statuses = {
            name: "available"
            for name in runtime_controller.required_qa_capabilities(self.root, state)
        }
        self.assertNotIn("custom-runtime-probe", statuses)
        args = [
            "qa-capability-probe", "--revision", state["revision"],
            "--probe-id", "probe-custom", "--report", self.artifact("qa", "probe-custom"),
        ]
        for name, status in statuses.items():
            args.extend(("--capability", f"{name}={status}"))
        rejected = self.cli(
            *args,
            "--capability", "custom-runtime-probe=available",
            expected=2,
        )
        self.assertIn("complete exact capability matrix", rejected.stderr)
        self.cli(*args)
        self.assertEqual("ready", self.state()["qa_capability"]["status"])

    def test_blocked_preflight_persists_exact_resume_contract_and_routes_next_action(self) -> None:
        self.initialize(research=False)
        state = self.state()
        state["phase"] = "preflight"
        state["plan_contracts"]["coverage_strategy"][
            "capability_prerequisites"
        ] = "config-credentials, persistence-datastore"
        self.write_state(state)
        args = [
            "preflight-complete", "--run-id", "preflight-blocked-user",
            "--resource-budget-check", "pass",
            "--minimum-resume-action",
            "config-credentials=user|true|authorize exact credentials",
            "--minimum-resume-action",
            "persistence-datastore=technical_director|false|start local datastore",
            "--report", self.artifact("verification", "preflight-blocked-user"),
        ]
        for name in sorted(runtime_controller.required_preflight_capabilities(state)):
            status = {
                "config-credentials": "blocked_user",
                "persistence-datastore": "blocked_environment",
            }.get(name, "available")
            args.extend(("--capability", f"{name}={status}"))
        result = json.loads(self.cli(*args).stdout)
        self.assertEqual("preflight", result["phase"])
        self.assertEqual("authorize exact credentials", result["next_action"]["action"])
        self.assertEqual("user", result["next_action"]["owner"])
        self.assertTrue(result["next_action"]["user_input_required"])
        full = self.full_status()
        self.assertEqual(
            "authorize exact credentials",
            full["preflight"]["minimum_resume_actions"]["config-credentials"]["action"],
        )
        self.assertEqual(
            "start local datastore",
            full["preflight"]["minimum_resume_actions"]["persistence-datastore"]["action"],
        )

    def test_blocked_preflight_environment_route_uses_saved_non_user_action(self) -> None:
        self.initialize(research=False)
        state = self.state()
        state["phase"] = "preflight"
        state["plan_contracts"]["coverage_strategy"][
            "capability_prerequisites"
        ] = "window-control-path"
        self.write_state(state)
        args = [
            "preflight-complete", "--run-id", "preflight-blocked-environment",
            "--resource-budget-check", "pass", "--minimum-resume-action",
            "window-control-path=technical_director|false|repair window automation",
            "--report", self.artifact("verification", "preflight-blocked-environment"),
        ]
        for name in sorted(runtime_controller.required_preflight_capabilities(state)):
            status = "error_test" if name == "window-control-path" else "available"
            args.extend(("--capability", f"{name}={status}"))
        compact = json.loads(self.cli(*args).stdout)
        self.assertEqual("preflight", compact["phase"])
        self.assertEqual("repair window automation", compact["next_action"]["action"])
        self.assertEqual("technical_director", compact["next_action"]["owner"])
        self.assertFalse(compact["next_action"]["user_input_required"])

    def test_documentation_source_map_rejects_changed_path_self_authority(self) -> None:
        self.initialize(research=False)
        state = self.state()
        relative = self.rel(self.src)
        state["active_write_lease"] = {"lease_id": "LEASE-DOC-SELF"}
        state["lease_snapshots"]["LEASE-DOC-SELF"] = {
            "checkout": {relative: self.sha(self.src)}
        }
        source_map = self.artifact(
            "verification", "self-source-map",
            {
                "schema": 1,
                "mode": "normative_pre_review",
                "statements": [{
                    "statement_id": "DOC-CHG-SELF", "path": relative,
                    "source_kind": "public_contract", "source_id": relative,
                    "source_path": relative, "source_sha256": self.sha(self.src),
                    "target_sha256": self.sha(self.src),
                }],
            },
        )
        with self.assertRaisesRegex(runtime_controller.PipelineError, "changed path"):
            runtime_controller.validate_documentation_source_map(
                self.root, state, source_map,
                mode="normative_pre_review",
                semantic_changes=[{
                    "change_id": "DOC-CHG-SELF", "path": relative,
                    "change_kind": "modify",
                }],
            )

    def test_documentation_source_map_rejects_cross_citation_between_changed_paths(self) -> None:
        self.initialize(research=False)
        state = self.state()
        first = self.rel(self.src)
        second = self.rel(self.spec)
        state["active_write_lease"] = {"lease_id": "LEASE-DOC-CROSS"}
        state["lease_snapshots"]["LEASE-DOC-CROSS"] = {
            "checkout": {first: self.sha(self.src), second: self.sha(self.spec)}
        }
        source_map = self.artifact(
            "verification", "cross-source-map",
            {
                "schema": 1,
                "mode": "normative_pre_review",
                "statements": [{
                    "statement_id": "DOC-CHG-CROSS-FIRST", "path": first,
                    "source_kind": "public_contract", "source_id": second,
                    "source_path": second, "source_sha256": self.sha(self.spec),
                    "target_sha256": self.sha(self.src),
                }],
            },
        )
        with self.assertRaisesRegex(runtime_controller.PipelineError, "changed path"):
            runtime_controller.validate_documentation_source_map(
                self.root, state, source_map,
                mode="normative_pre_review",
                semantic_changes=[
                    {"change_id": "DOC-CHG-CROSS-FIRST", "path": first, "change_kind": "modify"},
                    {"change_id": "DOC-CHG-CROSS-SECOND", "path": second, "change_kind": "modify"},
                ],
            )

    def test_documentation_source_map_accepts_immutable_authoritative_review_credit(self) -> None:
        self.initialize(research=False)
        state = self.state()
        state["decision_ledger"]["active_decision_ids"] = ["DEC-SOURCE-001"]
        review_relative = self.artifact("reviews", "immutable-review-source")
        review_report = self.root / review_relative
        review_credit_relative = self.review_credit_manifest(
            "immutable-review-credit", "review-source-worker", "full_convergence"
        )
        review_credit = self.root / review_credit_relative
        state["review_runs"].append(
            {
                "run_id": "review-source-1",
                "report": str(review_report),
                "report_sha256": self.sha(review_report),
                "credit_manifest": str(review_credit),
                "credit_manifest_sha256": self.sha(review_credit),
            }
        )
        normative_target = "docs/generated-contract.md"
        normative_target_path = self.root / normative_target
        normative_target_path.parent.mkdir(parents=True, exist_ok=True)
        normative_target_path.write_text("generated contract\n", encoding="utf-8")
        normative_map = self.artifact(
            "verification", "immutable-normative-map",
            {
                "schema": 1,
                "mode": "normative_pre_review",
                "statements": [
                    {
                        "statement_id": "DOC-CHG-NORMATIVE", "path": normative_target,
                        "source_kind": "requirement", "source_id": "PRD-REQ-001",
                        "source_path": self.rel(self.prd), "source_sha256": self.sha(self.prd),
                        "target_sha256": self.sha(normative_target_path),
                    },
                    {
                        "statement_id": "DOC-CHG-NORMATIVE", "path": normative_target,
                        "source_kind": "specification", "source_id": "approved-specification",
                        "source_path": self.rel(self.spec), "source_sha256": self.sha(self.spec),
                        "target_sha256": self.sha(normative_target_path),
                    },
                    {
                        "statement_id": "DOC-CHG-NORMATIVE", "path": normative_target,
                        "source_kind": "decision", "source_id": "DEC-SOURCE-001",
                        "source_path": self.rel(self.ledger), "source_sha256": self.sha(self.ledger),
                        "target_sha256": self.sha(normative_target_path),
                    },
                ],
            },
        )
        _, normative_ids = runtime_controller.validate_documentation_source_map(
            self.root, state, normative_map,
            mode="normative_pre_review", semantic_changes=[{
                "change_id": "DOC-CHG-NORMATIVE", "path": normative_target,
                "change_kind": "modify",
            }],
        )
        self.assertEqual(
            ["decision:DEC-SOURCE-001", "requirement:PRD-REQ-001", "specification:approved-specification"],
            normative_ids,
        )
        tampered_target = json.loads(
            (self.root / normative_map).read_text(encoding="utf-8")
        )
        tampered_target["statements"][0]["target_sha256"] = "0" * 64
        tampered_target_path = self.artifact(
            "verification", "immutable-normative-target-tampered", tampered_target
        )
        with self.assertRaisesRegex(runtime_controller.PipelineError, "target SHA"):
            runtime_controller.validate_documentation_source_map(
                self.root, state, tampered_target_path,
                mode="normative_pre_review", semantic_changes=[{
                    "change_id": "DOC-CHG-NORMATIVE", "path": normative_target,
                    "change_kind": "modify",
                }],
            )
        omitted_path = self.artifact(
            "verification", "immutable-normative-omitted",
            {"schema": 1, "mode": "normative_pre_review", "statements": []},
        )
        with self.assertRaisesRegex(runtime_controller.PipelineError, "omits semantic"):
            runtime_controller.validate_documentation_source_map(
                self.root, state, omitted_path,
                mode="normative_pre_review", semantic_changes=[{
                    "change_id": "DOC-CHG-NORMATIVE", "path": normative_target,
                    "change_kind": "modify",
                }],
            )
        derived_target = "docs/generated-support.md"
        derived_target_path = self.root / derived_target
        derived_target_path.write_text("generated support\n", encoding="utf-8")
        derived_map = self.artifact(
            "verification", "immutable-derived-map",
            {
                "schema": 1,
                "mode": "derived_post_qa",
                "statements": [
                    {
                        "statement_id": "DOC-CHG-DERIVED", "path": derived_target,
                        "source_kind": "decision", "source_id": "DEC-SOURCE-001",
                        "source_path": self.rel(self.ledger), "source_sha256": self.sha(self.ledger),
                        "target_sha256": self.sha(derived_target_path),
                    },
                    {
                        "statement_id": "DOC-CHG-DERIVED", "path": derived_target,
                        "source_kind": "review", "source_id": "review-source-1",
                        "source_path": self.rel(review_credit),
                        "source_sha256": self.sha(review_credit),
                        "target_sha256": self.sha(derived_target_path),
                    },
                ],
            },
        )
        _, derived_ids = runtime_controller.validate_documentation_source_map(
            self.root, state, derived_map,
            mode="derived_post_qa", semantic_changes=[{
                "change_id": "DOC-CHG-DERIVED", "path": derived_target,
                "change_kind": "modify",
            }],
        )
        self.assertEqual(
            ["decision:DEC-SOURCE-001", "review:review-source-1"], derived_ids
        )
        report_map = json.loads((self.root / derived_map).read_text(encoding="utf-8"))
        report_map["statements"][1]["source_path"] = self.rel(review_report)
        report_map["statements"][1]["source_sha256"] = self.sha(review_report)
        report_map_path = self.artifact(
            "verification", "non-authoritative-review-report-map", report_map
        )
        with self.assertRaisesRegex(
            runtime_controller.PipelineError, "controller-verified evidence"
        ):
            runtime_controller.validate_documentation_source_map(
                self.root,
                state,
                report_map_path,
                mode="derived_post_qa",
                semantic_changes=[{
                    "change_id": "DOC-CHG-DERIVED", "path": derived_target,
                    "change_kind": "modify",
                }],
            )

    def test_reviewer_capsule_rejects_semantically_empty_assignment(self) -> None:
        self.initialize(research=False)
        state = self.state()
        state["phase"] = "review"
        self.write_state(state)
        result = self.cli(
            "context-capsule-create", "--role", "reviewer", "--phase", "review",
            "--worker-id", "empty-reviewer", "--plan-sha256", state["development_plan_sha256"],
            "--revision", state["revision"],
            "--authority", f"{self.rel(self.prd)}={self.sha(self.prd)}:PRD-AC-001",
            "--output-path", f"tests/{FEATURE}/reviews/empty-review.json",
            "--stop-condition", "review and stop", "--max-authority-files", "5",
            "--max-evidence-files", "5", "--max-total-files", "10",
            "--max-payload-bytes", "500000", "--max-estimated-tokens", "200000",
            "--output", f"tests/{FEATURE}/verification/empty-review-capsule.json",
            expected=2,
        )
        self.assertIn("semantic", result.stderr)

    def test_engineer_capsule_rejects_missing_controller_coverage_evidence(self) -> None:
        self.initialize()
        self.plan_coverage()
        capsule_path = self.capsule(
            "engineer", "slice_engineering", "engineer-semantic-negative",
            allowed=("src/feature.py",),
        )
        value = json.loads((self.root / capsule_path).read_text(encoding="utf-8"))
        value["evidence"] = []
        value["metrics"] = runtime_controller.capsule_metrics(value, self.root)
        value["capsule_sha256"] = runtime_controller.capsule_digest(value)
        with self.assertRaisesRegex(
            runtime_controller.PipelineError, "exact role/phase packet|coverage evidence"
        ):
            runtime_controller.validate_capsule_value(self.root, self.state(), value)

    def test_qa_capsule_rejects_unknown_coverage_identity(self) -> None:
        self.ready_for_qa()
        capsule_path = self.capsule("reviewer", "qa", "qa-semantic-negative")
        value = json.loads((self.root / capsule_path).read_text(encoding="utf-8"))
        value["coverage_identity_ids"].append("UNKNOWN-QA-IDENTITY")
        value["metrics"] = runtime_controller.capsule_metrics(value, self.root)
        value["capsule_sha256"] = runtime_controller.capsule_digest(value)
        with self.assertRaisesRegex(runtime_controller.PipelineError, "coverage_identity_ids"):
            runtime_controller.validate_capsule_value(self.root, self.state(), value)

    def test_recovery_capsule_rejects_missing_assigned_finding(self) -> None:
        self.implementation_complete()
        state = self.state()
        state["phase"] = "evidence_recovery"
        state["recovery"] = {
            "status": "awaiting_remediation",
            "finding_ids": ["F-RECOVERY-CAPSULE"],
        }
        self.write_state(state)
        capsule_path = self.capsule(
            "recovery_remediator", "evidence_recovery", "recovery-semantic-negative",
            allowed=(self.rel(self.test_source),),
        )
        value = json.loads((self.root / capsule_path).read_text(encoding="utf-8"))
        value["finding_ids"] = []
        value["metrics"] = runtime_controller.capsule_metrics(value, self.root)
        value["capsule_sha256"] = runtime_controller.capsule_digest(value)
        with self.assertRaisesRegex(runtime_controller.PipelineError, "finding_ids"):
            runtime_controller.validate_capsule_value(self.root, self.state(), value)

    def test_engineer_capsule_receives_active_slice_remediation_findings(self) -> None:
        state = self.initialize(research=False)
        state["active_remediation_batch"] = {
            "route": "SLICE-001",
            "finding_ids": ["F-SLICE-REMEDIATION"],
            "status": "active",
        }
        self.assertEqual(
            {"F-SLICE-REMEDIATION"},
            runtime_controller.capsule_expected_finding_ids(
                self.root, state, "engineer", "engineering"
            ),
        )

    def test_runtime_mutation_writes_hash_bound_director_checkpoint(self) -> None:
        state = self.initialize(research=False)
        checkpoint_path = self.root / runtime_controller.DIRECTOR_CHECKPOINT
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        self.assertEqual(1, checkpoint["schema"])
        self.assertEqual(state["phase"], checkpoint["phase"])
        self.assertEqual(runtime_controller.file_sha256(self.root / ".agentic-pipeline" / "state.json"), checkpoint["state_sha256"])
        self.assertEqual(runtime_controller.file_sha256(self.root / ".agentic-pipeline" / "findings.json"), checkpoint["findings_sha256"])
        self.assertEqual(state["revision"], checkpoint["revisions"]["revision"])
        self.assertIn("next_action", checkpoint)

    def test_engineer_capsule_receives_active_integration_remediation_findings(self) -> None:
        state = self.initialize(research=False)
        state["active_remediation_batch"] = {
            "route": "integration",
            "finding_ids": ["F-INTEGRATION-REMEDIATION"],
            "status": "active",
        }
        self.assertEqual(
            {"F-INTEGRATION-REMEDIATION"},
            runtime_controller.capsule_expected_finding_ids(
                self.root, state, "engineer", "engineering"
            ),
        )

    def test_engineer_capsule_rejects_invalid_active_remediation_route(self) -> None:
        state = self.initialize(research=False)
        state["active_remediation_batch"] = {
            "route": "engineer",
            "finding_ids": ["F-INVALID-ROUTE"],
            "status": "active",
        }
        with self.assertRaisesRegex(runtime_controller.PipelineError, "invalid controller route"):
            runtime_controller.capsule_expected_finding_ids(
                self.root, state, "engineer", "engineering"
            )

    def test_slice_remediation_capsule_contains_exact_assigned_findings(self) -> None:
        self.implementation_complete()
        state = self.state()
        state["phase"] = "engineering"
        state["active_slice"] = "SLICE-001"
        state["active_remediation_batch"] = {
            "route": "SLICE-001",
            "finding_ids": ["F-SLICE-CAPSULE"],
            "status": "active",
        }
        self.write_state(state)
        capsule_path = self.capsule(
            "engineer",
            "engineering",
            "engineer-slice-remediation",
            allowed=("src/feature.py",),
        )
        capsule = json.loads((self.root / capsule_path).read_text(encoding="utf-8"))
        self.assertEqual(["F-SLICE-CAPSULE"], capsule["finding_ids"])

    def test_integration_remediation_capsule_uses_feature_coverage_and_findings(self) -> None:
        self.implementation_complete()
        state = self.state()
        state["phase"] = "engineering"
        state["active_slice"] = None
        state["active_remediation_batch"] = {
            "route": "integration",
            "finding_ids": ["F-INTEGRATION-CAPSULE"],
            "status": "active",
        }
        self.write_state(state)
        coverage_path, coverage_ids = runtime_controller.capsule_manifest_contract(
            self.root, state, "engineering"
        )
        finalized = state["coverage"]["feature"]["finalized_manifest"]
        self.assertEqual(self.rel(Path(finalized["path"])), coverage_path)
        self.assertTrue(coverage_ids)
        capsule_path = self.capsule(
            "engineer",
            "engineering",
            "engineer-integration-remediation",
            allowed=("src/feature.py",),
        )
        capsule = json.loads((self.root / capsule_path).read_text(encoding="utf-8"))
        self.assertEqual(["F-INTEGRATION-CAPSULE"], capsule["finding_ids"])

    def test_targeted_closure_capsule_contains_frozen_findings(self) -> None:
        self.implementation_complete()
        state = self.state()
        state["phase"] = "closure_review"
        state["closure_review"] = {
            "finding_ids": ["F-CLOSURE-CAPSULE"],
            "base_review_runs": [],
            "base_convergence_runs": [],
        }
        self.write_state(state)
        capsule_path = self.capsule(
            "reviewer", "closure_review", "reviewer-targeted-closure"
        )
        capsule = json.loads((self.root / capsule_path).read_text(encoding="utf-8"))
        self.assertEqual(["F-CLOSURE-CAPSULE"], capsule["finding_ids"])

    def test_legacy_schema9_complete_empty_preflight_enters_migration_hold(self) -> None:
        self.initialize(research=False)
        state = self.state()
        state["phase"] = "slice_research"
        state["preflight"].update(
            {
                "status": "complete",
                "resource_budget_check": "pass",
                "capabilities": {},
                "minimum_resume_actions": {},
            }
        )
        for field in (
            "proof_version",
            "required_capability_ids",
            "required_capability_digest",
            "resume_contract_complete",
        ):
            state["preflight"].pop(field, None)
        self.write_state(state)
        compact = json.loads(self.cli("status").stdout)
        self.assertEqual("preflight_migration_hold", compact["phase"])
        self.assertEqual("reinitialize_preflight", compact["next_action"]["action"])
        blocked = self.cli(
            "slice-research-not-required", "--slice-id", "SLICE-001",
            "--base-revision", state["revision"],
            "--reason", "legacy state must not activate a worker", expected=2,
        )
        self.assertIn("slice_research phase", blocked.stderr)
        reset = json.loads(
            self.cli(
                "reinitialize-preflight", "--reason",
                "migrate legacy schema-9 state to proof version 1",
            ).stdout
        )
        self.assertEqual("preflight", reset["phase"])
        state = self.state()
        rerun = [
            "preflight-complete", "--run-id", "preflight-migration-1",
            "--resource-budget-check", "pass", "--report",
            self.artifact("verification", "preflight-migration"),
        ]
        for name in sorted(runtime_controller.required_preflight_capabilities(state)):
            rerun.extend(("--capability", f"{name}=available"))
        migrated = json.loads(self.cli(*rerun).stdout)
        self.assertEqual("slice_research", migrated["phase"])
        self.assertEqual(1, self.state()["preflight"]["proof_version"])

    def test_legacy_schema9_partial_preflight_set_enters_migration_hold(self) -> None:
        self.initialize(research=False)
        state = self.state()
        state["phase"] = "slice_research"
        self.assertEqual(1, len(runtime_controller.required_preflight_capabilities(state)))
        state["preflight"]["capabilities"] = {}
        self.write_state(state)
        compact = json.loads(self.cli("status").stdout)
        self.assertEqual("preflight_migration_hold", compact["phase"])
        self.assertEqual("reinitialize_preflight", compact["next_action"]["action"])

    def test_fresh_preflight_persists_current_exact_proof(self) -> None:
        state = self.initialize(research=False)
        required = sorted(runtime_controller.required_preflight_capabilities(state))
        self.assertEqual(1, state["preflight"]["proof_version"])
        self.assertEqual(required, state["preflight"]["required_capability_ids"])
        self.assertTrue(state["preflight"]["resume_contract_complete"])
        self.assertEqual("slice_research", state["phase"])

    def test_capability_sets_are_plan_derived_and_qa_identity_scoped(self) -> None:
        state = self.initialize()
        self.assertEqual(
            {"test-server-two-clients"},
            runtime_controller.required_preflight_capabilities(state),
        )
        self.engineer()
        self.finalize_coverage()
        state = self.state()
        self.assertEqual(
            {"test-server-two-clients"},
            runtime_controller.required_qa_capabilities(self.root, state),
        )
        self.assertNotIn("studio-editor-sync", state["preflight"]["capabilities"])

    def test_capsule_roles_exclude_dead_researcher_and_separate_qa_role(self) -> None:
        self.assertEqual(
            {
                "decision_recorder",
                "engineer",
                "documentation_finisher",
                "recovery_remediator",
                "reviewer",
            },
            runtime_controller.CAPSULE_ROLES,
        )
        self.assertNotIn("researcher", runtime_controller.CAPSULE_PHASES)
        self.assertIn("qa", runtime_controller.CAPSULE_PHASES["reviewer"])

    def test_qa_capsule_is_exact_review_probe_coverage_handoff_packet(self) -> None:
        self.ready_for_qa()
        state = self.state()
        runs = []
        for index in (1,):
            report_rel = self.artifact("reviews", f"qa-packet-review-{index}")
            credit_rel = self.artifact("reviews", f"qa-packet-credit-{index}")
            report = self.root / report_rel
            credit = self.root / credit_rel
            runs.append(
                {
                    "run_id": f"review-packet-{index}",
                    "reviewer_id": f"reviewer-packet-{index}",
                    "report": str(report),
                    "report_sha256": self.sha(report),
                    "credit_manifest": str(credit),
                    "credit_manifest_sha256": self.sha(credit),
                }
            )
        state["review"]["runs"] = runs
        state["review_runs"] = list(runs)
        self.write_state(state)
        capsule_path = self.capsule("reviewer", "qa", "qa-exact-packet")
        value = json.loads((self.root / capsule_path).read_text(encoding="utf-8"))
        expected_evidence = {
            self.rel(Path(state["coverage"]["feature"]["finalized_manifest"]["path"])),
            state["handoffs"][-1]["path"],
            self.rel(Path(state["qa_capability"]["report"])),
            *{
                self.rel(Path(run[field]))
                for run in runs
                for field in ("credit_manifest",)
            },
        }
        self.assertEqual(expected_evidence, {item["path"] for item in value["evidence"]})
        self.assertEqual(
            {self.rel(self.prd), self.rel(self.spec), self.rel(self.plan)},
            {item["path"] for item in value["authority"]},
        )

    def test_qa_capsule_rejects_extra_controller_known_evidence_and_authority(self) -> None:
        self.ready_for_qa()
        capsule_path = self.capsule("reviewer", "qa", "qa-extra-packet")
        state = self.state()
        value = json.loads((self.root / capsule_path).read_text(encoding="utf-8"))
        planned = state["coverage"]["SLICE-001"]["planned_manifest"]
        planned_path = Path(planned["path"])
        value["evidence"].append(
            {
                "path": self.rel(planned_path),
                "sha256": planned["sha256"],
                "ids": [],
            }
        )
        value["authority"].append(
            {"path": self.rel(self.src), "sha256": self.sha(self.src), "ids": []}
        )
        value["metrics"] = runtime_controller.capsule_metrics(value, self.root)
        value["capsule_sha256"] = runtime_controller.capsule_digest(value)
        with self.assertRaisesRegex(runtime_controller.PipelineError, "exact|unexpected"):
            runtime_controller.validate_capsule_value(self.root, state, value)

    def test_reviewer_capsule_requires_exact_convergence_component_packet(self) -> None:
        self.implementation_complete()
        state = self.state()
        self.cli(
            "documentation-not-required", "--mode", "normative_pre_review",
            "--plan-sha256", state["development_plan_sha256"],
            "--policy-evidence", "POLICY-DOC-NONE",
        )
        state = self.state()
        convergence_runs = []
        for index in (1,):
            report_rel = self.artifact("reviews", f"convergence-packet-{index}")
            credit_rel = self.artifact("reviews", f"convergence-credit-{index}")
            report = self.root / report_rel
            credit = self.root / credit_rel
            convergence_runs.append(
                {
                    "run_id": f"convergence-packet-{index}",
                    "report": str(report),
                    "report_sha256": self.sha(report),
                    "credit_manifest": str(credit),
                    "credit_manifest_sha256": self.sha(credit),
                }
            )
        state["convergence"]["runs"] = convergence_runs
        state["phase"] = "review"
        self.write_state(state)
        capsule_path = self.capsule("reviewer", "review", "reviewer-exact-packet")
        value = json.loads((self.root / capsule_path).read_text(encoding="utf-8"))
        expected_evidence = {
            self.rel(Path(state["coverage"]["feature"]["finalized_manifest"]["path"])),
            state["handoffs"][-1]["path"],
            *{
                self.rel(Path(run[field]))
                for run in convergence_runs
                for field in ("credit_manifest",)
            },
        }
        self.assertEqual(expected_evidence, {item["path"] for item in value["evidence"]})
        removed = value["evidence"].pop()
        value["metrics"] = runtime_controller.capsule_metrics(value, self.root)
        value["capsule_sha256"] = runtime_controller.capsule_digest(value)
        with self.assertRaisesRegex(runtime_controller.PipelineError, "evidence"):
            runtime_controller.validate_capsule_value(self.root, self.state(), value)
        self.assertTrue(removed["path"])

    def test_compact_blocked_preflight_is_bounded_with_500_blockers(self) -> None:
        self.initialize(research=False)
        state = self.state()
        base_required = runtime_controller.required_preflight_capabilities(state)
        custom_count = 500 - len(base_required)
        self.assertGreater(custom_count, 0)
        custom = [f"bulk-blocker-{index:03d}" for index in range(custom_count)]
        state["plan_contracts"]["coverage_strategy"][
            "capability_prerequisites"
        ] = ", ".join(custom)
        required = sorted(runtime_controller.required_preflight_capabilities(state))
        capabilities = {name: "blocked_environment" for name in required}
        resume = {
            name: {
                "owner": "technical_director",
                "action": f"repair {name}",
                "user_input_required": False,
            }
            for name in required
        }
        state["phase"] = "preflight"
        state["preflight"].update(
            {
                "status": "capability_blocked",
                "resource_budget_check": "pass",
                "capabilities": capabilities,
                "minimum_resume_actions": resume,
                "proof_version": 1,
                "required_capability_ids": required,
                "required_capability_digest": runtime_controller.canonical_json_sha256(
                    {"proof_version": 1, "required_capability_ids": required}
                ),
                "resume_contract_complete": True,
            }
        )
        self.write_state(state)
        compact_result = self.cli("status")
        compact = json.loads(compact_result.stdout)
        self.assertLessEqual(len(compact_result.stdout.encode("utf-8")), 8192)
        self.assertEqual("bulk-blocker-000", compact["next_action"]["capability_id"])
        self.assertEqual("repair bulk-blocker-000", compact["next_action"]["action"])
        self.assertEqual(500, compact["next_action"]["capability_summary"]["total"])
        self.assertTrue(compact["next_action"]["capability_summary"]["truncated"])
        section = json.loads(self.cli("status", "--section", "preflight").stdout)
        self.assertEqual(500, len(section["data"]["capabilities"]))

    def test_compact_blocked_qa_is_bounded_with_500_blockers(self) -> None:
        self.initialize(research=False)
        state = self.state()
        base_required = runtime_controller.required_preflight_capabilities(state)
        custom_count = 500 - len(base_required)
        self.assertGreater(custom_count, 0)
        custom = [f"qa-bulk-blocker-{index:03d}" for index in range(custom_count)]
        state["plan_contracts"]["coverage_strategy"][
            "capability_prerequisites"
        ] = ", ".join(custom)
        required = sorted(runtime_controller.required_preflight_capabilities(state))
        self.assertEqual(500, len(required))
        state["preflight"].update(
            {
                "status": "complete",
                "resource_budget_check": "pass",
                "capabilities": {name: "available" for name in required},
                "minimum_resume_actions": {},
                "proof_version": runtime_controller.PREFLIGHT_PROOF_VERSION,
                "required_capability_ids": required,
                "required_capability_digest": runtime_controller.required_capability_proof_digest(
                    required
                ),
                "resume_contract_complete": True,
            }
        )
        selected = "qa-bulk-blocker-000"
        self.assertIn(selected, required)
        blocked = {
            name: (
                "blocked_user"
                if name == selected
                else "blocked_environment"
                if index % 2 == 0
                else "error_test"
            )
            for index, name in enumerate(required)
        }
        resume_actions = {
            name: {
                "owner": "user" if status == "blocked_user" else "technical_director",
                "action": (
                    "authorize selected QA capability"
                    if name == selected
                    else f"repair {name}"
                ),
                "user_input_required": status == "blocked_user",
            }
            for name, status in blocked.items()
        }
        state["phase"] = "qa"
        state["qa_capability"].update(
            {
                "status": "blocked",
                "revision": state["revision"],
                "probe_id": "probe-500-blockers",
                "capabilities": blocked,
                "minimum_resume_actions": resume_actions,
            }
        )
        state["qa"].update(
            {
                "status": "blocked_user",
                "revision": state["revision"],
                "capability_probe_id": "probe-500-blockers",
                "minimum_resume_actions": resume_actions,
            }
        )
        state["gates"] = [
            {
                "id": f"qa-capability:probe-500-blockers:{name}",
                "phase": "qa",
                "category": status,
                "origin": "qa_capability_probe",
                "revision": state["revision"],
                "minimum_resume_action": resume_actions[name],
                "status": "open",
            }
            for name, status in blocked.items()
        ]
        self.write_state(state)
        compact_result = self.cli("status")
        compact = json.loads(compact_result.stdout)
        self.assertLessEqual(len(compact_result.stdout.encode("utf-8")), 8192)
        route = compact["next_action"]
        self.assertEqual(selected, route["capability_id"])
        self.assertEqual("authorize selected QA capability", route["action"])
        self.assertEqual("user", route["owner"])
        self.assertTrue(route["user_input_required"])
        self.assertEqual(500, route["capability_summary"]["total"])
        self.assertTrue(route["capability_summary"]["truncated"])
        self.assertEqual(500, sum(route["capability_summary"]["by_status"].values()))
        self.assertNotIn("capabilities", route)
        self.assertNotIn("minimum_resume_actions", route)
        section = json.loads(self.cli("status", "--section", "qa").stdout)
        self.assertEqual(500, len(section["data"]["capability"]["capabilities"]))
        self.assertEqual(
            500,
            len(section["data"]["capability"]["minimum_resume_actions"]),
        )


class RuntimeProgressResult(unittest.TextTestResult):
    """Emit immediate per-test progress and duration for the large runtime suite."""

    def startTest(self, test: unittest.TestCase) -> None:
        self._runtime_started_at = time.perf_counter()
        self.stream.writeln(f"[runtime-test:start] {test.id()}")
        self.stream.flush()
        super().startTest(test)

    def stopTest(self, test: unittest.TestCase) -> None:
        elapsed = time.perf_counter() - self._runtime_started_at
        super().stopTest(test)
        self.stream.writeln(f"[runtime-test:done] {test.id()} {elapsed:.3f}s")
        self.stream.flush()


class RuntimeProgressRunner(unittest.TextTestRunner):
    resultclass = RuntimeProgressResult


if __name__ == "__main__":
    unittest.main(testRunner=RuntimeProgressRunner, verbosity=2)
