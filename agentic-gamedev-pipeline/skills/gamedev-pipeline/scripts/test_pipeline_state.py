#!/usr/bin/env python3
"""Schema-9 controller tests with exact role artifacts and verification boundaries."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
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
        self.prd.write_text(
            "---\n"
            "document_type: product-requirements\n"
            "status: approved\n"
            "revision: 1\n"
            "---\n"
            "# PRD\n\nPRD-REQ-001\nPRD-AC-001\n",
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
            "- capability_prerequisites: test-server-two-clients\n"
            "- gates: plan-before-engineering, finalize-after-code-freeze, qa-updated\n\n"
            "## Documentation Strategy\n\n"
            "- normative_pre_review: not_required | policy=POLICY-DOC-NONE\n"
            "- derived_post_qa: not_required | policy=POLICY-DOC-NONE\n"
            "- source_rule: active decisions and exact verified evidence only\n\n"
            "## Context Budget\n\n"
            "- max_authority_files: 5\n"
            "- max_evidence_files: 5\n"
            "- max_total_files: 10\n"
            "- max_payload_bytes: 500000\n"
            "- max_estimated_tokens: 200000\n"
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
            "- scope_baseline_revision: base-0\n\n"
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
            "- max_evidence_files: 5\n"
            "- max_total_files: 10\n"
            "- max_payload_bytes: 500000\n"
            "- max_estimated_tokens: 200000\n"
            "- authority_paths: docs/features/**\n"
            f"- evidence_paths: tests/{FEATURE}/**\n\n"
            "### Verification and Exit Criteria\n\nExact schema-2 equality and mandatory automated PASS.\n\n"
            "### Rollback and Recovery\n\nRestore the exact controller base revision.\n\n"
            "### Downstream Consumers\n\nFinal Review, QA, and documentation closure.\n",
            encoding="utf-8",
        )

    def write_planning_state(self) -> None:
        state_root = self.root / ".agentic-pipeline"
        state_root.mkdir(parents=True, exist_ok=True)
        (state_root / "specification-state.json").write_text(
            json.dumps(
                {
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

    def artifact(self, area: str, name: str, value: dict | None = None) -> str:
        path = self.root / "tests" / FEATURE / area / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value or {"name": name}), encoding="utf-8")
        return self.rel(path)

    def initialize(self, *, research: bool = True) -> dict:
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
        self.cli(
            "preflight-complete",
            "--run-id",
            "preflight-1",
            "--resource-budget-check",
            "pass",
            "--capability",
            "editor=available",
            "--capability",
            "operator=planned_manual",
            "--report",
            self.artifact("verification", "preflight"),
        )
        if research:
            state = self.state()
            self.cli(
                "slice-research-not-required",
                "--slice-id",
                "SLICE-001",
                "--base-revision",
                state["revision"],
                "--owner-id",
                "engineer-1",
                "--reason",
                "Exact authority and edit files answer the bounded question",
            )
        return self.state()

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
            "--authority",
            f"{self.rel(self.prd)}={self.sha(self.prd)}:PRD-AC-001",
            "--stop-condition",
            "Return the assigned schema and stop",
            "--max-authority-files",
            "5",
            "--max-evidence-files",
            "5",
            "--max-total-files",
            "10",
            "--max-payload-bytes",
            str(max_payload),
            "--max-estimated-tokens",
            "200000",
            "--output",
            path,
        ]
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
        expected = [automated, manual]
        actual = [] if mode == "planned" else [automated] if mismatch else [automated, manual]
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
                        "identity_id": manual["identity_id"],
                        "executed": False,
                        "passed": None,
                        "deferred": False,
                        "blocked_by_finding": None,
                        "qa_evidence": None,
                        "gate": None,
                        "minimum_resume_action": None,
                    }
                ]
        registration = mode == "finalized" and not mismatch
        summary = {
            "ac_mapped": True,
            "identities_registered": "complete" if registration else "mismatch",
            "expected_count": 2,
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
                    "identity_ids": [automated["identity_id"], manual["identity_id"]],
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
        capsule = self.capsule("coverage_steward", "slice_coverage_planning", "steward-plan")
        self.cli(
            "coverage-plan-complete",
            "--slice-id",
            "SLICE-001",
            "--steward-id",
            "steward-plan",
            "--capsule",
            capsule,
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
                    "reason": "Implement PRD-AC-001",
                    "change_kind": "behavior",
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
            "--engineering-status",
            "pass",
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
        return self.state() if forbidden_path else json.loads(result.stdout)

    def finalize_coverage(self, *, mismatch: bool = False, expected: int = 0) -> dict:
        capsule = self.capsule(
            "coverage_steward", "slice_coverage_finalization", "steward-final"
        )
        result = self.cli(
            "coverage-finalize",
            "--scope-id",
            "SLICE-001",
            "--steward-id",
            "steward-final",
            "--capsule",
            capsule,
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
        return self.state() if expected else json.loads(result.stdout)

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

    def prepare_qa_state(self) -> None:
        state_path = self.root / ".agentic-pipeline" / "state.json"
        state = self.state()
        state["phase"] = "qa"
        state["review"] = {
            "status": "passed",
            "revision": state["revision"],
            "product_revision": state["product_revision"],
            "support_revision": state["support_revision"],
            "evidence_revision": state["evidence_revision"],
            "required": 2,
            "runs": [{"reviewer_id": "r1"}, {"reviewer_id": "r2"}],
            "recovery_run": None,
        }
        state_path.write_text(json.dumps(state), encoding="utf-8")

    def write_state(self, state: dict) -> None:
        (self.root / ".agentic-pipeline" / "state.json").write_text(
            json.dumps(state), encoding="utf-8"
        )

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
        return capsule

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
                        "reason": "Bounded PRD-AC-001 implementation",
                        "change_kind": "behavior",
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
            "--engineering-status",
            "pass",
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
            "studio-editor-sync": "available",
            "single-play": "available",
            "test-server-two-clients": "available",
            "window-control-path": "planned_manual",
            "logging-screenshots": "available",
            "persistence-datastore": "available",
            "publication-place-topology": "available",
            "config-credentials": "blocked_user" if blocked else "available",
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
            args.extend(("--minimum-resume-action", "config-credentials=authorize exact QA credential"))
        self.cli(*args)

    def test_init_creates_exact_schema9_and_zero_entry_ledger(self) -> None:
        state = self.initialize(research=False)
        self.assertEqual(9, state["schema_version"])
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

    def test_schema8_is_rejected_without_guessing_migration_facts(self) -> None:
        self.initialize(research=False)
        for name in ("state.json", "findings.json"):
            path = self.root / ".agentic-pipeline" / name
            value = json.loads(path.read_text(encoding="utf-8"))
            value["schema_version"] = 8
            path.write_text(json.dumps(value), encoding="utf-8")
        result = self.cli("status", expected=2)
        self.assertIn("pre-v9", result.stderr)

    def test_context_capsule_records_exact_metrics_and_detects_staleness(self) -> None:
        self.initialize()
        capsule = self.capsule("coverage_steward", "slice_coverage_planning", "steward")
        value = json.loads((self.root / capsule).read_text(encoding="utf-8"))
        self.assertGreater(value["metrics"]["payload_bytes"], self.prd.stat().st_size)
        self.assertEqual((value["metrics"]["payload_bytes"] + 3) // 4, value["metrics"]["estimated_tokens"])
        self.cli("context-capsule-check", "--capsule", capsule)
        (self.root / capsule).write_text("{}", encoding="utf-8")
        self.cli("context-capsule-check", "--capsule", capsule, expected=2)

    def test_context_capsule_fails_closed_over_numeric_budget(self) -> None:
        self.initialize()
        result = self.cli(
            "context-capsule-create",
            "--role",
            "coverage_steward",
            "--phase",
            "slice_coverage_planning",
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
            "1",
            "--max-evidence-files",
            "1",
            "--max-total-files",
            "1",
            "--max-payload-bytes",
            "1",
            "--max-estimated-tokens",
            "1",
            "--output",
            f"tests/{FEATURE}/verification/tiny.json",
            expected=2,
        )
        self.assertIn("cannot invent or override", result.stderr)

    def test_exclusive_lease_and_drift_safe_release(self) -> None:
        self.initialize()
        self.plan_coverage()
        capsule = self.capsule("engineer", "slice_engineering", "engineer-1", allowed=("src/feature.py",))
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
        result = json.loads(
            self.cli(
                "decision-record-complete", "--recorder-id", "recorder-1", "--lease-id",
                state["active_write_lease"]["lease_id"], "--capsule", capsule,
                "--semantic-packet", semantic, "--report", self.artifact("verification", "decision-report"),
            ).stdout
        )
        self.assertEqual(["DEC-001"], result["decision_ledger"]["active_decision_ids"])
        entry = json.loads(self.ledger.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(1, entry["sequence"])
        self.assertIn("prior_ledger_sha256", entry)
        self.assertIsNone(result["active_write_lease"])

    def test_qa_gate_preserves_implementation_and_uses_pending_exact_identities(self) -> None:
        state = self.implementation_complete()
        self.cli(
            "documentation-not-required", "--mode", "normative_pre_review", "--plan-sha256",
            state["development_plan"]["sha256"], "--policy-evidence", "POLICY-DOC-NONE",
        )
        self.prepare_qa_state()
        self.qa_probe(blocked=True)
        capsule = self.capsule("qa", "qa", "qa-1")
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
        capsule = self.capsule("qa", "qa", "qa-1")
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
        qa_capsule = self.capsule("qa", "qa", "qa-derived")
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
        source_map = {
            "schema": 1,
            "inventory_complete": True,
            "domain_inventory": inventory,
            "changes": [
                {
                    "path": self.rel(support), "domain": "support", "symbols": ["operator-handoff"],
                    "reason": "Synchronize immutable QA-observed operator path", "change_kind": "derived_docs",
                    "component": "operator-docs", "lifecycle_change": False, "ownership_change": False,
                    "public_contract_change": False, "requirement_ids": ["PRD-REQ-001"],
                    "acceptance_ids": ["PRD-AC-001"], "decision_ids": [], "touchpoint_id": None,
                }
            ],
            "open_assumptions": [],
        }
        source_path = self.artifact("verification", "derived-source-map", source_map)
        state = self.state()
        completed = json.loads(
            self.cli(
                "documentation-complete", "--mode", "derived_post_qa", "--worker-id", "docs-derived",
                "--lease-id", state["active_write_lease"]["lease_id"], "--capsule", docs_capsule,
                "--source-map", source_path, "--report", self.artifact("verification", "derived-docs-report"),
            ).stdout
        )
        self.assertEqual("documentation_review", completed["phase"])
        self.assertEqual("pass", completed["qa"]["status"])
        review_capsule = self.capsule("reviewer", "documentation_review", "docs-reviewer")
        state = self.state()
        closed = json.loads(
            self.cli(
                "documentation-review-complete", "--revision", state["revision"],
                "--product-revision", state["product_revision"], "--support-revision", state["support_revision"],
                "--evidence-revision", state["evidence_revision"], "--run-id", "docs-closure-1",
                "--reviewer-id", "docs-reviewer", "--capsule", review_capsule, "--status", "pass",
                "--report", self.artifact("reviews", "docs-closure-report"),
            ).stdout
        )
        self.assertEqual("ready", closed["phase"])
        self.assertEqual("pass", closed["feature_verification_state"]["status"])

    def test_coverage_mapping_duplicate_acceptance_is_rejected(self) -> None:
        self.initialize()
        capsule = self.capsule("coverage_steward", "slice_coverage_planning", "steward-plan")
        path = self.coverage_manifest("duplicate-ac", "planned")
        value = json.loads((self.root / path).read_text(encoding="utf-8"))
        value["ac_mappings"].append(dict(value["ac_mappings"][0]))
        (self.root / path).write_text(json.dumps(value), encoding="utf-8")
        self.cli(
            "coverage-plan-complete", "--slice-id", "SLICE-001", "--steward-id", "steward-plan",
            "--capsule", capsule, "--coverage-manifest", path,
            "--report", self.artifact("verification", "duplicate-report"), expected=2,
        )

    def test_not_applicable_coverage_requires_active_decision_authority(self) -> None:
        self.initialize()
        capsule = self.capsule("coverage_steward", "slice_coverage_planning", "steward-na")
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
            "coverage-plan-complete", "--slice-id", "SLICE-001", "--steward-id", "steward-na",
            "--capsule", capsule, "--coverage-manifest", path,
            "--report", self.artifact("verification", "not-applicable-report"), expected=2,
        )
        self.assertIn("active accepted decision", result.stderr)

    def test_status_rehashes_inventory_and_rejects_unleased_product_drift(self) -> None:
        self.initialize(research=False)
        self.plan.write_text(self.plan.read_text(encoding="utf-8") + "\nplan drift\n", encoding="utf-8")
        result = self.cli("status", expected=2)
        self.assertIn("revision inventory drifted", result.stderr)

    def test_ready_rehashes_inventory_before_considering_phase(self) -> None:
        self.initialize(research=False)
        self.plan.write_text(self.plan.read_text(encoding="utf-8") + "\nplan drift\n", encoding="utf-8")
        result = self.cli("ready", expected=2)
        self.assertIn("revision inventory drifted", result.stderr)

    def test_context_gate_rehashes_inventory_before_capsule_validation(self) -> None:
        self.initialize()
        capsule = self.capsule("coverage_steward", "slice_coverage_planning", "steward-drift")
        self.plan.write_text(self.plan.read_text(encoding="utf-8") + "\nplan drift\n", encoding="utf-8")
        result = self.cli("context-capsule-check", "--capsule", capsule, expected=2)
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
        self.ledger.write_text(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        state = self.state()
        state["decision_ledger"]["sha256"] = self.sha(self.ledger)
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
        text = text.replace("- scope_baseline_revision: base-0", f"- scope_baseline_revision: {held['revision']}")
        self.plan.write_text(text, encoding="utf-8")
        planning = json.loads((self.root / ".agentic-pipeline" / "development-plan-state.json").read_text(encoding="utf-8"))
        planning["approval"]["approved_sha256"] = self.sha(self.plan)
        (self.root / ".agentic-pipeline" / "development-plan-state.json").write_text(json.dumps(planning), encoding="utf-8")
        result = json.loads(self.cli(
            "rebaseline-scope", "--plan-sha256", self.sha(self.plan),
            "--user-scope-approval", "USER-SCOPE-APPROVAL-1",
        ).stdout)
        self.assertIsNone(result["active_write_lease"])
        self.assertEqual("revoked", result["write_lease_history"][-1]["status"])
        self.assertIsNotNone(result["scope_guard"]["rebaseline_candidate"])
        self.cli("context-capsule-check", "--capsule", old_capsule, expected=2)
        fresh_capsule = self.capsule(
            "engineer", "slice_engineering", "engineer-1",
            allowed=("src/feature.py", "src/commerce/driveby.py"),
        )
        self.cli(
            "acquire-write-lease", "--role", "engineer", "--phase", "slice_engineering",
            "--write-scope", "SLICE-001", "--worker-id", "engineer-1", "--capsule", fresh_capsule,
        )
        state = self.state()
        self.cli(
            "slice-scope-check", "--slice-id", "SLICE-001", "--base-revision", state["revision"],
            "--owner-id", "engineer-1",
        )
        carried = self.state()["scope_guard"]["rebaseline_candidate"]
        completed = json.loads(self.cli(
            "engineer-complete", "--run-id", carried["run_id"], "--owner-id", "engineer-1",
            "--lease-id", self.state()["active_write_lease"]["lease_id"], "--capsule", fresh_capsule,
            "--slice-id", "SLICE-001", "--engineering-status", "pass", "--machine-checks", "pass",
            "--diff-inspection", "pass", "--semantic-handoff", carried["semantic_report"],
            "--report", carried["engineer_report"], "--scope-approval", "USER-SCOPE-APPROVAL-1",
        ).stdout)
        self.assertEqual("slice_coverage_finalization", completed["phase"])
        self.assertIsNone(completed["active_write_lease"])

    def test_scope_rebaseline_rejects_checkout_that_is_neither_candidate_nor_rollback(self) -> None:
        self.initialize()
        self.engineer(forbidden_path=True)
        held = self.state()
        unrelated = self.root / "src" / "unexpected.py"
        unrelated.write_text("UNEXPECTED = True\n", encoding="utf-8")
        text = self.plan.read_text(encoding="utf-8").replace(
            "- scope_baseline_revision: base-0", f"- scope_baseline_revision: {held['revision']}"
        )
        self.plan.write_text(text, encoding="utf-8")
        planning_path = self.root / ".agentic-pipeline" / "development-plan-state.json"
        planning = json.loads(planning_path.read_text(encoding="utf-8"))
        planning["approval"]["approved_sha256"] = self.sha(self.plan)
        planning_path.write_text(json.dumps(planning), encoding="utf-8")
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
        capsule = self.capsule("coverage_steward", "slice_coverage_finalization", "steward-change")
        path = self.coverage_manifest("coverage-body-change", "finalized")
        value = json.loads((self.root / path).read_text(encoding="utf-8"))
        value["expected_identities"][0]["planned_assertion_or_observation"] = "changed after planning"
        value["actual_identities"][0]["planned_assertion_or_observation"] = "changed after planning"
        (self.root / path).write_text(json.dumps(value), encoding="utf-8")
        result = self.cli(
            "coverage-finalize", "--scope-id", "SLICE-001", "--steward-id", "steward-change",
            "--capsule", capsule, "--coverage-manifest", path, "--expected-actual-equality", "pass",
            "--mandatory-registration", "pass", "--automated-execution", "pass",
            "--report", self.artifact("verification", "coverage-body-change-report"), expected=2,
        )
        self.assertIn("without an authorized", result.stderr)

    def test_coverage_rejects_one_way_acceptance_mapping(self) -> None:
        self.initialize()
        capsule = self.capsule("coverage_steward", "slice_coverage_planning", "steward-reverse")
        path = self.coverage_manifest("coverage-reverse", "planned")
        value = json.loads((self.root / path).read_text(encoding="utf-8"))
        value["ac_mappings"][0]["identity_ids"].remove("MANUAL-SLICE-001-RUNTIME")
        (self.root / path).write_text(json.dumps(value), encoding="utf-8")
        result = self.cli(
            "coverage-plan-complete", "--slice-id", "SLICE-001", "--steward-id", "steward-reverse",
            "--capsule", capsule, "--coverage-manifest", path,
            "--report", self.artifact("verification", "coverage-reverse-report"), expected=2,
        )
        self.assertIn("reverse AC mapping", result.stderr)

    def test_coverage_rejects_identity_with_wrong_slice_coordinate(self) -> None:
        self.initialize()
        capsule = self.capsule("coverage_steward", "slice_coverage_planning", "steward-slice")
        path = self.coverage_manifest("coverage-wrong-slice", "planned")
        value = json.loads((self.root / path).read_text(encoding="utf-8"))
        value["expected_identities"][0]["slice_id"] = "SLICE-999"
        (self.root / path).write_text(json.dumps(value), encoding="utf-8")
        result = self.cli(
            "coverage-plan-complete", "--slice-id", "SLICE-001", "--steward-id", "steward-slice",
            "--capsule", capsule, "--coverage-manifest", path,
            "--report", self.artifact("verification", "coverage-slice-report"), expected=2,
        )
        self.assertIn("slice_id", result.stderr)

    def test_coverage_rejects_empty_automated_command(self) -> None:
        self.initialize()
        self.engineer()
        capsule = self.capsule("coverage_steward", "slice_coverage_finalization", "steward-command")
        path = self.coverage_manifest("coverage-command", "finalized")
        value = json.loads((self.root / path).read_text(encoding="utf-8"))
        value["automated_execution"][0]["command"] = ""
        (self.root / path).write_text(json.dumps(value), encoding="utf-8")
        result = self.cli(
            "coverage-finalize", "--scope-id", "SLICE-001", "--steward-id", "steward-command",
            "--capsule", capsule, "--coverage-manifest", path, "--expected-actual-equality", "pass",
            "--mandatory-registration", "pass", "--automated-execution", "pass",
            "--report", self.artifact("verification", "coverage-command-report"), expected=2,
        )
        self.assertIn("non-empty command", result.stderr)

    def test_coverage_rejects_stale_automated_evidence_sha(self) -> None:
        self.initialize()
        self.engineer()
        capsule = self.capsule("coverage_steward", "slice_coverage_finalization", "steward-evidence")
        path = self.coverage_manifest("coverage-evidence", "finalized")
        value = json.loads((self.root / path).read_text(encoding="utf-8"))
        value["automated_execution"][0]["evidence_sha256"] = "0" * 64
        (self.root / path).write_text(json.dumps(value), encoding="utf-8")
        result = self.cli(
            "coverage-finalize", "--scope-id", "SLICE-001", "--steward-id", "steward-evidence",
            "--capsule", capsule, "--coverage-manifest", path, "--expected-actual-equality", "pass",
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
        capsule = self.capsule(
            "decision_recorder", "decision_recording", "recorder-assignment",
            allowed=(self.rel(self.ledger),), outputs=(self.rel(self.ledger),),
        )
        self.cli(
            "acquire-write-lease", "--role", "decision_recorder", "--phase", "decision_recording",
            "--write-scope", "ledger", "--worker-id", "recorder-assignment", "--capsule", capsule,
        )
        state = self.state()
        result = self.cli(
            "decision-record-complete", "--recorder-id", "recorder-assignment", "--lease-id",
            state["active_write_lease"]["lease_id"], "--capsule", capsule,
            "--semantic-packet", self.artifact("verification", "unassigned-packet", packet),
            "--report", self.artifact("verification", "unassigned-report"), expected=2,
        )
        self.assertIn("not assigned", result.stderr)

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

    def test_qa_worker_identity_must_be_fresh_from_engineering(self) -> None:
        state = self.ready_for_qa()
        capsule = self.capsule("qa", "qa", "engineer-1")
        result = self.cli(
            "qa-complete", "--revision", state["revision"], "--product-revision", state["product_revision"],
            "--support-revision", state["support_revision"], "--evidence-revision", state["evidence_revision"],
            "--run-id", "qa-reused", "--worker-id", "engineer-1", "--capsule", capsule,
            "--status", "pass", "--manual-execution", self.qa_manual_artifact(),
            "--report", self.artifact("qa", "qa-reused-report"), expected=2,
        )
        self.assertIn("fresh from every prior non-QA role", result.stderr)

    def test_qa_rejects_stale_review_chain_identity(self) -> None:
        state = self.ready_for_qa()
        state["review"]["evidence_revision"] = "0" * 64
        self.write_state(state)
        capsule = self.capsule("qa", "qa", "qa-stale-review")
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
        capsule = self.capsule("qa", "qa", "qa-bad-evidence")
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
        capsule = self.capsule("qa", "qa", "qa-no-evidence")
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

    def test_qa_obeys_worker_budget_checkpoint(self) -> None:
        state = self.ready_for_qa()
        state["worker_budget"]["status"] = "checkpoint_required"
        self.write_state(state)
        capsule = self.capsule("qa", "qa", "qa-over-budget")
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
        state["qa_capability"]["status"] = "blocked"
        state["qa_capability"]["capabilities"]["config-credentials"] = "blocked_user"
        state["qa_capability"]["minimum_resume_actions"] = {
            "config-credentials": "authorize exact QA credential"
        }
        self.write_state(state)
        capsule = self.capsule("qa", "qa", "qa-unique")
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
        result = self.cli(*common, expected=2)
        self.assertIn("QA run ID already recorded", result.stderr)

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
            "not_required | policy=POLICY-DOC-NONE",
            state["plan_contracts"]["documentation_strategy"]["derived_post_qa"],
        )

    def test_qa_updates_terminal_feature_coverage_to_current_identity(self) -> None:
        state = self.ready_for_qa()
        capsule = self.capsule("qa", "qa", "qa-aggregate")
        result = json.loads(self.cli(
            "qa-complete", "--revision", state["revision"], "--product-revision", state["product_revision"],
            "--support-revision", state["support_revision"], "--evidence-revision", state["evidence_revision"],
            "--run-id", "qa-aggregate", "--worker-id", "qa-aggregate", "--capsule", capsule,
            "--status", "pass", "--manual-execution", self.qa_manual_artifact(),
            "--report", self.artifact("qa", "qa-aggregate-report"),
        ).stdout)
        feature = result["coverage"]["feature"]
        manifest = json.loads(Path(feature["finalized_manifest"]["path"]).read_text(encoding="utf-8"))
        self.assertEqual(result["revision"], manifest["revisions"]["revision"])
        self.assertTrue(manifest["summary"]["feature_verification_eligible"])

    def test_ready_revalidates_immutable_manual_qa_evidence_bytes(self) -> None:
        state = self.ready_for_qa()
        capsule = self.capsule("qa", "qa", "qa-evidence-drift")
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
        self.assertEqual("recovery_review", recovered["phase"])
        self.assertEqual(recovered["revision"], recovered["machine_checks"]["revision"])
        self.assertEqual(recovered["revision"], recovered["coverage"]["feature"]["state"]["revision"])
        self.assertEqual(recovered["revision"], recovered["implementation_state"]["revision"])
        state = self.state()
        reviewed = json.loads(self.cli(
            "recovery-review-complete", "--revision", state["revision"],
            "--product-revision", state["product_revision"], "--support-revision", state["support_revision"],
            "--evidence-revision", state["evidence_revision"], "--run-id", "recovery-review-1",
            "--reviewer-id", "recovery-reviewer", "--status", "pass",
            "--report", self.artifact("reviews", "recovery-review-report"),
        ).stdout)
        self.assertEqual("qa", reviewed["phase"])
        self.qa_probe()
        qa_capsule = self.capsule("qa", "qa", "qa-after-recovery")
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
        capsule = self.capsule("engineer", "slice_engineering", "engineer-empty")
        result = self.cli(
            "acquire-write-lease", "--role", "engineer", "--phase", "slice_engineering",
            "--write-scope", "SLICE-001", "--worker-id", "engineer-empty", "--capsule", capsule,
            expected=2,
        )
        self.assertIn("non-empty allowed_paths", result.stderr)

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
        self.assertEqual(before["revision"], result["revision"])
        self.assertEqual("engineer-2", result["owner_by_slice"]["SLICE-001"])
        self.assertIsNone(result["active_write_lease"])
        self.assertEqual("revoked", result["write_lease_history"][-1]["status"])
        self.assertIsNotNone(result["coverage"]["SLICE-001"]["planned_manifest"])

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

    def test_open_minor_residual_risk_blocks_readiness_until_explicit_acceptance(self) -> None:
        self.initialize(research=False)
        findings_path = self.root / ".agentic-pipeline" / "findings.json"
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        findings["items"].append(
            {"id": "F-MINOR-1", "status": "open", "severity": "minor", "blocking": False}
        )
        findings_path.write_text(json.dumps(findings), encoding="utf-8")
        reasons = runtime_controller.readiness_reasons(self.state(), findings)
        self.assertIn("minor findings require resolution or explicit acceptance", reasons)
        self.cli(
            "accept-finding", "--id", "F-MINOR-1", "--reason", "bounded cosmetic residual",
            "--approval-reference", "USER-RISK-1",
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

    def test_late_decision_from_implementation_complete_is_rejected_without_state_mutation(self) -> None:
        self.implementation_complete()
        capsule = self.capsule(
            "decision_recorder", "decision_recording", "recorder-late",
            allowed=(self.rel(self.ledger),), outputs=(self.rel(self.ledger),),
        )
        state_path = self.root / ".agentic-pipeline" / "state.json"
        before = state_path.read_bytes()
        result = self.cli(
            "acquire-write-lease", "--role", "decision_recorder",
            "--phase", "decision_recording", "--write-scope", "ledger",
            "--worker-id", "recorder-late", "--capsule", capsule, expected=2,
        )
        self.assertIn("before implementation begins", result.stderr)
        self.assertEqual(before, state_path.read_bytes())
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
                {"reviewer_id": "reviewer-2", "status": "pass"},
            ],
        }
        self.write_state(state)
        findings_path = self.root / ".agentic-pipeline" / "findings.json"
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        findings["items"].append(
            {
                "id": "F-REVIEW-EVIDENCE",
                "status": "open",
                "source": "review",
                "revision": state["revision"],
                "finding_kind": "evidence",
                "blocking": True,
            }
        )
        findings_path.write_text(json.dumps(findings), encoding="utf-8")
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
        findings["items"].append(
            {
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
                "evidence": "Exact accepted finding evidence",
                "revision": state["revision"],
                "origin_slice": "SLICE-001",
                "remediation_route": "SLICE-001",
                "status": "open",
                "created_at": "2026-08-11T00:00:00+00:00",
                "resolved_revision": None,
                "blocking": True,
            }
        )
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
        with self.assertRaisesRegex(runtime_controller.PipelineError, "exactly equal"):
            runtime_controller.validate_coverage_continuity(
                state, planned, finalized, authorized_new_ids={"F-AMEND-001"}
            )
        finalized["amendments"][0]["affected_acceptance_ids"] = [
            "PRD-AC-001", "PRD-AC-002"
        ]
        self.assertEqual(
            runtime_controller.coverage_plan_body_digest(finalized),
            runtime_controller.validate_coverage_continuity(
                state, planned, finalized, authorized_new_ids={"F-AMEND-001"}
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
                planned_with_bad_prefix,
                json.loads(json.dumps(planned_with_bad_prefix)),
                authorized_new_ids=set(),
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
                    "symbols": ["FeatureContract"], "reason": "Add approved feature contract",
                    "change_kind": "additive contract", "component": "feature",
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
            "--engineering-status", "pass", "--machine-checks", "pass",
            "--diff-inspection", "pass", "--semantic-handoff", semantic,
            "--report", self.artifact("verification", "shared-touchpoint-report"),
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
        self.assertEqual(3, extended["worker_budget"]["max_full_review_waves"])
        self.assertEqual([], extended["worker_budget"]["checkpoint_causes"])

    def test_ready_requires_terminal_handoff_coverage_exactly_equal_current_aggregate(self) -> None:
        state = self.ready_for_qa()
        capsule = self.capsule("qa", "qa", "qa-terminal-equality")
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


if __name__ == "__main__":
    unittest.main()
