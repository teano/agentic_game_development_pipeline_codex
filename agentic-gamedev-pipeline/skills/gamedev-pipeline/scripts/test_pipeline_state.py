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
        self.optional_manual_identities: list[dict] = []
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

    def full_status(self) -> dict:
        return json.loads(self.cli("status", "--full").stdout)

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
        preflight_args = [
            "preflight-complete",
            "--run-id",
            "preflight-1",
            "--resource-budget-check",
            "pass",
            "--report",
            self.artifact("verification", "preflight"),
        ]
        for name in sorted(
            runtime_controller.required_preflight_capabilities(self.state())
        ):
            preflight_args.extend(("--capability", f"{name}=available"))
        self.cli(*preflight_args)
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
                scope_ids
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
        for evidence_path, evidence_sha in sorted(
            runtime_controller.capsule_exact_evidence(
                self.root, state, role, phase
            ).items()
        ):
            args.extend(("--evidence", f"{evidence_path}={evidence_sha}"))
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
        return self.full_status()

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

    def optional_manual_identity(self, identity_id: str) -> dict:
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
            "capability_prerequisites": [],
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
        for index in (1, 2):
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
            "required": 2,
            "runs": runs,
            "recovery_run": None,
        }
        state["review_runs"] = list(runs)
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
            args.extend((
                "--minimum-resume-action",
                "config-credentials=user|true|authorize exact QA credential",
            ))
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
        self.assertIn("exceed approved development-plan ceilings", result.stderr)

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
        result = self.full_status()
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
        semantic_packet = {
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
        semantic_path = self.artifact(
            "verification", "derived-semantic-packet", semantic_packet
        )
        qa_report = Path(state["qa"]["report"])
        source_path = self.artifact(
            "verification",
            "derived-source-map",
            {
                "schema": 1,
                "mode": "derived_post_qa",
                "statements": [
                    {
                        "statement_id": "DOC-STMT-001",
                        "path": self.rel(support),
                        "source_kind": "qa",
                        "source_id": state["qa"]["run_id"],
                        "source_path": self.rel(qa_report),
                        "source_sha256": self.sha(qa_report),
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
        result = self.full_status()
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
        self.assertIn("prior user receipt", result.stderr)

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
        capsule = self.capsule("qa", "qa", "qa-aggregate")
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
        findings_path = self.root / ".agentic-pipeline" / "findings.json"
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        findings["items"].append(
            {
                "id": "F-MINOR-1",
                "status": "open",
                "severity": "minor",
                "blocking": False,
                "revision": revision,
            }
        )
        findings_path.write_text(json.dumps(findings), encoding="utf-8")
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

    def test_late_decision_from_implementation_complete_is_rejected_without_state_mutation(self) -> None:
        self.implementation_complete()
        packet, authority_id, authority_digest = self.decision_packet()
        self.accept_user_authority(packet)
        capsule = self.capsule(
            "decision_recorder", "decision_recording", "recorder-late",
            allowed=(self.rel(self.ledger),), outputs=(self.rel(self.ledger),),
            authorities=(f"not_applicable={authority_digest}:{authority_id}",),
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
        for name in sorted(runtime_controller.QA_CAPABILITY_NAMES - {"config-credentials"}):
            args.extend(("--capability", f"{name}=available"))
        result = self.cli(*args, expected=2)
        self.assertIn("config-credentials", result.stderr)
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
        self.initialize(research=False)
        state = self.state()
        output = f"tests/{FEATURE}/verification/smaller-capsule.json"
        result = json.loads(self.cli(
            "context-capsule-create", "--role", "researcher",
            "--phase", "slice_research",
            "--worker-id", "smaller-researcher", "--plan-sha256", state["development_plan_sha256"],
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
        ).stdout)
        self.assertEqual(3, result["budget"]["max_authority_files"])
        self.assertLess(result["budget"]["max_payload_bytes"], 500000)

    def test_generic_resolve_finding_is_fail_closed_and_nonmutating(self) -> None:
        self.initialize(research=False)
        state = self.state()
        findings_path = self.root / ".agentic-pipeline" / "findings.json"
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        findings["items"].append(
            {"id": "F-CLOSE-1", "status": "open", "severity": "major", "blocking": True}
        )
        findings_path.write_text(json.dumps(findings), encoding="utf-8")
        before_state = (self.root / ".agentic-pipeline" / "state.json").read_bytes()
        before_findings = findings_path.read_bytes()
        result = self.cli(
            "resolve-finding", "--id", "F-CLOSE-1", "--revision", state["revision"],
            expected=2,
        )
        self.assertIn("resolve-finding is disabled", result.stderr)
        self.assertEqual(before_state, (self.root / ".agentic-pipeline" / "state.json").read_bytes())
        self.assertEqual(before_findings, findings_path.read_bytes())

    def test_accept_finding_rejects_generic_user_receipt(self) -> None:
        self.initialize(research=False)
        revision = self.state()["revision"]
        findings_path = self.root / ".agentic-pipeline" / "findings.json"
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        findings["items"].append(
            {"id": "F-RISK-BAD", "status": "open", "severity": "minor", "blocking": False,
             "revision": revision}
        )
        findings_path.write_text(json.dumps(findings), encoding="utf-8")
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
                    {"reviewer_id": "r-support-2", "status": "pass"},
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
        self.optional_manual_identities = [
            self.optional_manual_identity("MANUAL-SLICE-001-OPTIONAL-USER"),
            self.optional_manual_identity("MANUAL-SLICE-001-OPTIONAL-ENV"),
        ]
        state = self.ready_for_qa()
        statuses = {name: "available" for name in runtime_controller.QA_CAPABILITY_NAMES}
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
        capsule = self.capsule("qa", "qa", "qa-mixed")
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
        capsule = self.capsule("qa", "qa", "qa-optional")
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

    def test_custom_plan_capability_is_accepted_by_exact_qa_probe(self) -> None:
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8").replace(
                "- capability_prerequisites: test-server-two-clients",
                "- capability_prerequisites: test-server-two-clients, custom-runtime-probe",
            ),
            encoding="utf-8",
        )
        self.write_planning_state()
        self.initialize(research=False)
        state = self.state()
        self.assertEqual(
            "available", state["preflight"]["capabilities"]["custom-runtime-probe"]
        )
        state["phase"] = "qa"
        self.write_state(state)
        statuses = {name: "available" for name in runtime_controller.QA_CAPABILITY_NAMES}
        statuses["custom-runtime-probe"] = "available"
        args = [
            "qa-capability-probe", "--revision", state["revision"],
            "--probe-id", "probe-custom", "--report", self.artifact("qa", "probe-custom"),
        ]
        for name, status in statuses.items():
            args.extend(("--capability", f"{name}={status}"))
        self.cli(*args)
        self.assertEqual("ready", self.state()["qa_capability"]["status"])

    def test_blocked_preflight_persists_exact_resume_contract_and_routes_next_action(self) -> None:
        self.initialize(research=False)
        state = self.state()
        state["phase"] = "preflight"
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
        for name in sorted(runtime_controller.QA_CAPABILITY_NAMES):
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
        self.write_state(state)
        args = [
            "preflight-complete", "--run-id", "preflight-blocked-environment",
            "--resource-budget-check", "pass", "--minimum-resume-action",
            "window-control-path=technical_director|false|repair window automation",
            "--report", self.artifact("verification", "preflight-blocked-environment"),
        ]
        for name in sorted(runtime_controller.QA_CAPABILITY_NAMES):
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
                    "statement_id": "SELF-001", "path": relative,
                    "source_kind": "public_contract", "source_id": relative,
                    "source_path": relative, "source_sha256": self.sha(self.src),
                }],
            },
        )
        with self.assertRaisesRegex(runtime_controller.PipelineError, "changed path"):
            runtime_controller.validate_documentation_source_map(
                self.root, state, source_map,
                mode="normative_pre_review", changed_paths=[relative],
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
                    "statement_id": "CROSS-001", "path": first,
                    "source_kind": "public_contract", "source_id": second,
                    "source_path": second, "source_sha256": self.sha(self.spec),
                }],
            },
        )
        with self.assertRaisesRegex(runtime_controller.PipelineError, "changed path"):
            runtime_controller.validate_documentation_source_map(
                self.root, state, source_map,
                mode="normative_pre_review", changed_paths=[first, second],
            )

    def test_documentation_source_map_accepts_immutable_prd_spec_decision_and_review(self) -> None:
        self.initialize(research=False)
        state = self.state()
        state["decision_ledger"]["active_decision_ids"] = ["DEC-SOURCE-001"]
        review_relative = self.artifact("reviews", "immutable-review-source")
        review_report = self.root / review_relative
        state["review_runs"].append(
            {
                "run_id": "review-source-1",
                "report": str(review_report),
                "report_sha256": self.sha(review_report),
            }
        )
        normative_target = "docs/generated-contract.md"
        normative_map = self.artifact(
            "verification", "immutable-normative-map",
            {
                "schema": 1,
                "mode": "normative_pre_review",
                "statements": [
                    {
                        "statement_id": "REQ-001", "path": normative_target,
                        "source_kind": "requirement", "source_id": "PRD-REQ-001",
                        "source_path": self.rel(self.prd), "source_sha256": self.sha(self.prd),
                    },
                    {
                        "statement_id": "SPEC-001", "path": normative_target,
                        "source_kind": "specification", "source_id": "approved-specification",
                        "source_path": self.rel(self.spec), "source_sha256": self.sha(self.spec),
                    },
                    {
                        "statement_id": "DEC-001", "path": normative_target,
                        "source_kind": "decision", "source_id": "DEC-SOURCE-001",
                        "source_path": self.rel(self.ledger), "source_sha256": self.sha(self.ledger),
                    },
                ],
            },
        )
        _, normative_ids = runtime_controller.validate_documentation_source_map(
            self.root, state, normative_map,
            mode="normative_pre_review", changed_paths=[normative_target],
        )
        self.assertEqual(
            ["decision:DEC-SOURCE-001", "requirement:PRD-REQ-001", "specification:approved-specification"],
            normative_ids,
        )
        derived_target = "docs/generated-support.md"
        derived_map = self.artifact(
            "verification", "immutable-derived-map",
            {
                "schema": 1,
                "mode": "derived_post_qa",
                "statements": [
                    {
                        "statement_id": "DEC-002", "path": derived_target,
                        "source_kind": "decision", "source_id": "DEC-SOURCE-001",
                        "source_path": self.rel(self.ledger), "source_sha256": self.sha(self.ledger),
                    },
                    {
                        "statement_id": "REVIEW-001", "path": derived_target,
                        "source_kind": "review", "source_id": "review-source-1",
                        "source_path": self.rel(review_report),
                        "source_sha256": self.sha(review_report),
                    },
                ],
            },
        )
        _, derived_ids = runtime_controller.validate_documentation_source_map(
            self.root, state, derived_map,
            mode="derived_post_qa", changed_paths=[derived_target],
        )
        self.assertEqual(
            ["decision:DEC-SOURCE-001", "review:review-source-1"], derived_ids
        )

    def test_reviewer_capsule_rejects_semantically_empty_assignment(self) -> None:
        self.initialize(research=False)
        state = self.state()
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
        capsule_path = self.capsule("qa", "qa", "qa-semantic-negative")
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
            "--base-revision", state["revision"], "--owner-id", "engineer-1",
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
        only = sorted(runtime_controller.QA_CAPABILITY_NAMES)[0]
        state["preflight"]["capabilities"] = {only: "available"}
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

    def test_qa_capsule_is_exact_review_probe_coverage_handoff_packet(self) -> None:
        self.ready_for_qa()
        state = self.state()
        runs = []
        for index in (1, 2):
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
        capsule_path = self.capsule("qa", "qa", "qa-exact-packet")
        value = json.loads((self.root / capsule_path).read_text(encoding="utf-8"))
        expected_evidence = {
            self.rel(Path(state["coverage"]["feature"]["finalized_manifest"]["path"])),
            state["handoffs"][-1]["path"],
            self.rel(Path(state["qa_capability"]["report"])),
            *{
                self.rel(Path(run[field]))
                for run in runs
                for field in ("report", "credit_manifest")
            },
        }
        self.assertEqual(expected_evidence, {item["path"] for item in value["evidence"]})
        self.assertEqual(
            {self.rel(self.prd), self.rel(self.spec), self.rel(self.plan)},
            {item["path"] for item in value["authority"]},
        )

    def test_qa_capsule_rejects_extra_controller_known_evidence_and_authority(self) -> None:
        self.ready_for_qa()
        capsule_path = self.capsule("qa", "qa", "qa-extra-packet")
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
        for index in (1, 2):
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
                for field in ("report", "credit_manifest")
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
        custom = [f"bulk-blocker-{index:03d}" for index in range(500)]
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
        self.assertEqual(508, compact["next_action"]["capability_summary"]["total"])
        self.assertTrue(compact["next_action"]["capability_summary"]["truncated"])
        section = json.loads(self.cli("status", "--section", "preflight").stdout)
        self.assertEqual(508, len(section["data"]["capabilities"]))

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
        selected = "config-credentials"
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


if __name__ == "__main__":
    unittest.main()
