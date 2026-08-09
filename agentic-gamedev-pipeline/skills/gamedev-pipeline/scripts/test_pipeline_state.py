#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("pipeline_state.py")
DEFERRED_SCRIPT = Path(__file__).with_name("deferred_findings.py")
FEATURE = "teleport-module"


class PipelineStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.docs = self.root / "docs" / "features" / FEATURE
        self.docs.mkdir(parents=True)
        self.requirements = self.docs / "product-requirements.md"
        self.spec = self.docs / "technical-specification.md"
        self.requirements.write_text(
            "---\n"
            "document_type: product-requirements\n"
            "status: approved\n"
            "revision: 1\n"
            "language: Russian\n"
            "approved_at: 2026-08-03T12:00:00Z\n"
            "---\n"
            "# Product Requirements\n",
            encoding="utf-8",
        )
        self.write_spec()
        self.write_plan()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_spec(self, *, status: str = "approved", sha: str | None = None) -> None:
        requirements_sha = sha or hashlib.sha256(self.requirements.read_bytes()).hexdigest()
        self.spec.write_text(
            "---\n"
            "document_type: technical-specification\n"
            f"status: {status}\n"
            "revision: 1\n"
            "language: Russian\n"
            "approved_at: 2026-08-03T12:30:00Z\n"
            f"source_prd_path: docs/features/{FEATURE}/product-requirements.md\n"
            "source_prd_revision: 1\n"
            f"source_prd_sha256: {requirements_sha}\n"
            "---\n"
            "# Technical Specification\n",
            encoding="utf-8",
        )

    def write_plan(self, *, mode: str = "single_owner", slice_count: int = 1) -> None:
        plan = self.docs / "development-plan.md"
        slices = []
        for index in range(1, slice_count + 1):
            slice_id = f"SLICE-{index:03d}"
            dependency = "none" if index == 1 else f"SLICE-{index - 1:03d}"
            slices.append(
                f"## Slice {slice_id}\n\n"
                "### Requirements\n\n"
                f"- PRD-REQ-{index:03d}\n- PRD-AC-{index:03d}\n\n"
                "### Dependencies\n\n"
                f"- {dependency}\n\n"
                "### Scope Contract\n\n"
                f"- acceptance_ids: PRD-AC-{index:03d}\n"
                f"- editable_paths: src/feature-{index}.py\n"
                "- shared_touchpoints: see structured rows below\n"
                f"- shared_touchpoint: TP-{index:03d} | path=src/contracts.py | symbols=FeatureContract{index} | allowed_change=additive feature contract | forbidden_change=lifecycle, ownership, removals\n"
                "- excluded_components: save-system, commerce\n"
                "- excluded_paths: src/save/**, src/commerce/**\n"
                "- max_product_files: 4\n"
                "- max_product_lines_changed: 200\n"
                f"- verification_scope: tests/test_feature_{index}.py and feature smoke test\n"
                "- scope_baseline_revision: base-0\n\n"
                "### Handoff Contract\n\nExact sealed result revision and evidence.\n"
            )
        plan.write_text(
            "---\n"
            "document_type: development-plan\n"
            "status: approved\n"
            "revision: 1\n"
            f"feature: {FEATURE}\n"
            f"mode: {mode}\n"
            "writer_strategy: sequential\n"
            "planning_analyst_id: analyst-1\n"
            f"source_prd_path: docs/features/{FEATURE}/product-requirements.md\n"
            "source_prd_revision: 1\n"
            f"source_prd_sha256: {hashlib.sha256(self.requirements.read_bytes()).hexdigest()}\n"
            f"source_spec_path: docs/features/{FEATURE}/technical-specification.md\n"
            "source_spec_revision: 1\n"
            f"source_spec_sha256: {hashlib.sha256(self.spec.read_bytes()).hexdigest()}\n"
            f"slice_count: {slice_count}\n"
            "approved_by: user\n"
            "approved_at: 2026-08-03T13:00:00+00:00\n"
            "---\n\n"
            "# Development Plan\n\n"
            + "\n".join(slices),
            encoding="utf-8",
        )
        plan_sha = hashlib.sha256(plan.read_bytes()).hexdigest()
        state_path = self.root / ".agentic-pipeline" / "development-plan-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "feature": FEATURE,
                    "status": "approved",
                    "plan_path": f"docs/features/{FEATURE}/development-plan.md",
                    "prd": {"sha256": hashlib.sha256(self.requirements.read_bytes()).hexdigest()},
                    "specification": {"sha256": hashlib.sha256(self.spec.read_bytes()).hexdigest()},
                    "approval": {"approved_sha256": plan_sha},
                }
            ),
            encoding="utf-8",
        )

    def run_command(self, *arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *arguments, "--project-root", str(self.root)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(expected, result.returncode, msg=result.stderr or result.stdout)
        return result

    def defer_backlog(self, *, local_id: str, component: str = "Adjacent") -> str:
        result = subprocess.run(
            [
                sys.executable,
                str(DEFERRED_SCRIPT),
                "backlog-upsert",
                "--component",
                component,
                "--contract",
                "adjacent contract",
                "--root-cause",
                f"preexisting root cause {local_id}",
                "--failure-mode",
                "supported adjacent failure",
                "--effect",
                "nonblocking current-feature effect",
                "--title",
                "Deferred adjacent issue",
                "--problem",
                "The supported issue predates and does not block this feature",
                "--violated-invariant",
                "none in current feature",
                "--provisional-severity",
                "major",
                "--reachability",
                "normal",
                "--evidence",
                f"controller test evidence {local_id}",
                "--occurrence-id",
                f"test:{local_id}",
                "--observed-by",
                "test-director",
                "--origin-feature",
                FEATURE,
                "--current-revision",
                "base-0",
                "--scope-relation",
                "preexisting_adjacent",
                "--project-root",
                str(self.root),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, msg=result.stderr or result.stdout)
        return json.loads(result.stdout)["reference"]

    def finding_dimensions(
        self,
        *,
        finding_kind: str = "product",
        severity: str = "major",
        scope_relation: str = "current_feature_path",
        introduced_by_candidate: bool = False,
        reachability: str = "normal",
        blocks: tuple[str, ...] = ("PRD-AC-001",),
        violates_invariant: bool = False,
        invariant_evidence: str | None = None,
        deferred_reference: str | None = None,
        kind_flag: str = "--finding-kind",
    ) -> tuple[str, ...]:
        if finding_kind in {"support", "hardening"}:
            blocks = ()
        arguments = [
            kind_flag,
            finding_kind,
            "--scope-relation",
            scope_relation,
            "--introduced-by-candidate",
            "true" if introduced_by_candidate else "false",
            "--production-reachability",
            reachability,
            "--violates-required-invariant",
            "true" if violates_invariant else "false",
            "--mandatory-core-acceptance-evidence-missing",
            "true" if finding_kind == "evidence" and severity == "major" else "false",
            "--test-can-miss-product-defect",
            "true" if finding_kind == "evidence" and severity == "major" else "false",
        ]
        for acceptance_id in blocks:
            arguments.extend(("--blocks-acceptance-id", acceptance_id))
        if invariant_evidence:
            arguments.extend(("--required-invariant-evidence", invariant_evidence))
        if deferred_reference:
            arguments.extend(("--deferred-reference", deferred_reference))
        return tuple(arguments)

    def initialize(
        self,
        *,
        complete_preflight: bool = True,
        research_owner: str | None = "owner-main",
        extra: tuple[str, ...] = (),
    ) -> None:
        self.run_command(
            "init",
            "--feature",
            FEATURE,
            "--requirements",
            f"docs/features/{FEATURE}/product-requirements.md",
            "--spec",
            f"docs/features/{FEATURE}/technical-specification.md",
            "--plan",
            f"docs/features/{FEATURE}/development-plan.md",
            "--plan-sha256",
            hashlib.sha256((self.docs / "development-plan.md").read_bytes()).hexdigest(),
            "--base-revision",
            "base-0",
            "--slice",
            "slice-1",
            *extra,
        )
        if complete_preflight:
            self.preflight()
            if research_owner:
                self.research_not_required(owner_id=research_owner)

    def preflight(
        self,
        *,
        run_id: str = "preflight-1",
        budget: str = "pass",
        capabilities: tuple[str, ...] = (
            "rojo=available",
            "published-config=available",
            "datastore=available",
            "multi-place-teleport=planned_manual",
            "player-control=planned_manual",
        ),
    ) -> dict:
        arguments = [
            "preflight-complete",
            "--run-id",
            run_id,
            "--resource-budget-check",
            budget,
            "--report",
            self.report("verification", run_id),
        ]
        for capability in capabilities:
            arguments.extend(("--capability", capability))
        return json.loads(self.run_command(*arguments).stdout)

    def state(self) -> dict:
        return json.loads((self.root / ".agentic-pipeline" / "state.json").read_text(encoding="utf-8"))

    def research_not_required(
        self,
        reason: str = "Exact edit files and canonical documents are sufficient",
        *,
        owner_id: str = "owner-main",
    ) -> dict:
        state = self.state()
        slice_id = state["active_slice"]
        return json.loads(
            self.run_command(
                "slice-research-not-required",
                "--slice-id",
                slice_id,
                "--base-revision",
                state["slices"][slice_id]["base_revision"],
                "--owner-id",
                owner_id,
                "--reason",
                reason,
            ).stdout
        )

    def research_bundle(
        self,
        name: str,
        researcher_id: str,
        *,
        slice_id: str | None = None,
        base_revision: str | None = None,
        status: str = "complete",
    ) -> str:
        state = self.state()
        slice_id = slice_id or state["active_slice"]
        base_revision = base_revision or state["slices"][slice_id]["base_revision"]
        relative = f"tests/{FEATURE}/research/{name}.json"
        brief = {
            "brief_id": name,
            "question": "Where is the existing lifecycle contract implemented?",
            "slice_id": slice_id,
            "requirement_ids": ["REQ-001", "AC-001"],
            "base_revision": base_revision,
            "seed_paths": ["src/feature.py"],
            "allowed_paths": ["src"],
            "allowed_symbols": ["FeatureService"],
            "exclusions": ["unrelated persistence modules"],
            "requested_evidence": ["owner and reusable entry point"],
            "max_files": 3,
            "stop_condition": "owner and entry point are identified",
            "output_path": relative,
        }
        brief_sha = hashlib.sha256(
            json.dumps(
                brief, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        bundle = {
            "schema_version": 1,
            "brief": brief,
            "result": {
                "brief_id": name,
                "researcher_id": researcher_id,
                "base_revision": base_revision,
                "brief_sha256": brief_sha,
                "status": status,
                "inspected_paths": ["src/feature.py"],
                "inspected_symbols": ["FeatureService"],
                "owners_contracts_precedents": ["FeatureService owns the lifecycle"],
                "lifecycle_integration_risks": ["Call ordering is significant"],
                "minimal_edit_reuse_points": ["Reuse FeatureService.start"],
                "unresolved_questions": [],
                "out_of_brief_pointers": [],
            },
        }
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(bundle), encoding="utf-8")
        return relative

    def report(self, area: str, name: str) -> str:
        report = self.root / "tests" / FEATURE / area / f"{name}.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps({"name": name}), encoding="utf-8")
        return str(report.relative_to(self.root))

    def credit_manifest(
        self,
        name: str,
        reviewer_id: str,
        review_mode: str,
        lenses: tuple[str, ...],
        *,
        component: str | None = None,
        mode: str = "fresh",
        source_credit_id: str | None = None,
        composition_audit: bool = False,
    ) -> str:
        state = self.state()
        item = {
            "component": component or f"feature:{name}",
            "product_hash": state["product_revision"],
            "contract_hash": state["spec_sha256"],
            "lenses": list(lenses),
            "mode": mode,
        }
        if source_credit_id:
            item["source_credit_id"] = source_credit_id
        manifest = self.root / "tests" / FEATURE / "reviews" / f"{name}-credits.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "revision": state["revision"],
                    "reviewer_id": reviewer_id,
                    "review_mode": review_mode,
                    "composition_audit": composition_audit,
                    "new_boundaries_audited": [],
                    "components": [item],
                }
            ),
            encoding="utf-8",
        )
        return str(manifest.relative_to(self.root))

    def qa_probe(
        self,
        revision: str,
        probe_id: str,
        *,
        blocked: tuple[str, str] | None = None,
    ) -> dict:
        statuses = {
            "studio-editor-sync": "available",
            "single-play": "available",
            "test-server-two-clients": "available",
            "window-control-path": "planned_manual",
            "logging-screenshots": "available",
            "persistence-datastore": "available",
            "publication-place-topology": "available",
            "config-credentials": "available",
        }
        if blocked:
            statuses[blocked[0]] = blocked[1]
        arguments = [
            "qa-capability-probe",
            "--revision",
            revision,
            "--probe-id",
            probe_id,
            "--report",
            self.report("qa", probe_id),
        ]
        for name, status in statuses.items():
            arguments.extend(("--capability", f"{name}={status}"))
        if blocked:
            arguments.extend(
                (
                    "--minimum-resume-action",
                    f"{blocked[0]}=restore {blocked[0]} and rerun the exact probe",
                )
            )
        return json.loads(self.run_command(*arguments).stdout)

    def coverage_manifest(
        self,
        name: str,
        product_revision: str,
        evidence_revision: str,
        support_revision: str | None = None,
    ) -> str:
        support_revision = support_revision or product_revision
        manifest = self.root / "tests" / FEATURE / "verification" / f"{name}-coverage.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "product_revision": product_revision,
                    "support_revision": support_revision,
                    "evidence_revision": evidence_revision,
                    "entries": [
                        {
                            "id": "AC-001",
                            "status": "covered",
                            "implementation_evidence": ["src/feature.py:1"],
                            "tests": [
                                {
                                    "file": "tests/test_feature.py",
                                    "suite": "FeatureTests",
                                    "symbol": "test_feature",
                                    "assertions": ["result is correct"],
                                    "execution": "pass",
                                    "evidence": "verification.log:1",
                                }
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return str(manifest.relative_to(self.root))

    def handoff_manifest(
        self,
        name: str,
        slice_id: str,
        owner_id: str,
        base_revision: str,
        result_revision: str,
        changes: list[dict] | None = None,
    ) -> str:
        manifest = self.root / "tests" / FEATURE / "verification" / f"{name}-handoff.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "sealed",
                    "slice_id": slice_id,
                    "owner_id": owner_id,
                    "base_revision": base_revision,
                    "result_revision": result_revision,
                    "checks": "pass",
                    "coverage_manifest": f"{name}-coverage.json",
                    "change_manifest": changes or [],
                }
            ),
            encoding="utf-8",
        )
        return str(manifest.relative_to(self.root))

    def scope_artifacts(
        self,
        name: str,
        *,
        slice_id: str,
        owner_id: str,
        base_revision: str,
        result_revision: str,
        product_changed: bool,
        path: str | None = None,
        lines_changed: int = 20,
        change_kind: str = "feature",
        component: str = "feature",
        symbols: list[str] | None = None,
        touchpoint_id: str | None = None,
        lifecycle_change: bool = False,
        ownership_change: bool = False,
        public_contract_change: bool = False,
    ) -> tuple[str, str, list[dict]]:
        index = int(slice_id.split("-")[1])
        path = path or f"src/feature-{index}.py"
        symbols = symbols or [f"Feature{index}"]
        changes: list[dict] = []
        diff_files: list[dict] = []
        if product_changed:
            mapping = {
                "path": path,
                "symbols": symbols,
                "slice_id": slice_id,
                "requirement_ids": [f"PRD-REQ-{index:03d}"],
                "acceptance_ids": [f"PRD-AC-{index:03d}"],
                "reason": "Implement the approved vertical outcome",
                "change_kind": change_kind,
            }
            if touchpoint_id:
                mapping["touchpoint_id"] = touchpoint_id
            changes.append(mapping)
            diff_files.append(
                {
                    "path": path,
                    "symbols": symbols,
                    "lines_changed": lines_changed,
                    "change_kind": change_kind,
                    "component": component,
                    "lifecycle_change": lifecycle_change,
                    "ownership_change": ownership_change,
                    "public_contract_change": public_contract_change,
                }
            )
        verification = self.root / "tests" / FEATURE / "verification"
        verification.mkdir(parents=True, exist_ok=True)
        manifest = verification / f"{name}-changes.json"
        summary = verification / f"{name}-diff.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "slice_id": slice_id,
                    "owner_id": owner_id,
                    "base_revision": base_revision,
                    "result_revision": result_revision,
                    "change_manifest": changes,
                }
            ),
            encoding="utf-8",
        )
        summary.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "slice_id": slice_id,
                    "base_revision": base_revision,
                    "result_revision": result_revision,
                    "product_files": diff_files,
                    "smoke_tests": ["feature smoke"] if not product_changed else [],
                }
            ),
            encoding="utf-8",
        )
        return (
            str(manifest.relative_to(self.root)),
            str(summary.relative_to(self.root)),
            changes,
        )

    def owner_handoff_manifest(
        self,
        name: str,
        route: str,
        from_owner: str,
        to_owner: str,
        revision: str,
        reason: str,
        finding_ids: tuple[str, ...],
    ) -> str:
        manifest = self.root / "tests" / FEATURE / "verification" / f"{name}.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "sealed",
                    "route": route,
                    "from_owner": from_owner,
                    "to_owner": to_owner,
                    "revision": revision,
                    "reason": reason,
                    "finding_ids": list(finding_ids),
                    "verification_state": "frozen remediation batch",
                }
            ),
            encoding="utf-8",
        )
        return str(manifest.relative_to(self.root))

    def engineer(
        self,
        revision: str,
        run_id: str,
        checks: str = "pass",
        *,
        product_revision: str | None = None,
        support_revision: str | None = None,
        evidence_revision: str | None = None,
        owner_id: str = "owner-main",
        scope: str | None = None,
        scope_approval: str | None = None,
        resolved: tuple[str, ...] = (),
    ) -> dict:
        if self.state().get("phase") == "slice_research":
            self.research_not_required(owner_id=owner_id)
        product_revision = product_revision or revision
        support_revision = support_revision or product_revision
        evidence_revision = evidence_revision or revision
        if scope is None:
            state_path = self.root / ".agentic-pipeline" / "state.json"
            current_product = (
                json.loads(state_path.read_text(encoding="utf-8")).get("product_revision")
                if state_path.is_file()
                else None
            )
            scope = "local" if current_product != product_revision else "none"
        state = self.state()
        route = (state.get("active_remediation_batch") or {}).get("route")
        slice_id = state.get("active_slice") or (
            state.get("ordered_slices", [])[-1] if route == "integration" else route
        ) or state.get("slice_id")
        base_revision = state["revision"]
        self.run_command(
            "slice-scope-check",
            "--slice-id",
            slice_id,
            "--base-revision",
            base_revision,
            "--owner-id",
            owner_id,
        )
        change_manifest, diff_summary, changes = self.scope_artifacts(
            run_id,
            slice_id=slice_id,
            owner_id=owner_id,
            base_revision=base_revision,
            result_revision=revision,
            product_changed=(state["product_revision"] != product_revision),
        )
        arguments = [
            "engineer-complete",
            "--revision",
            revision,
            "--product-revision",
            product_revision,
            "--support-revision",
            support_revision,
            "--evidence-revision",
            evidence_revision,
            "--run-id",
            run_id,
            "--owner-id",
            owner_id,
            "--machine-checks",
            checks,
            "--report",
            self.report("verification", run_id),
            "--coverage-manifest",
            self.coverage_manifest(
                run_id, product_revision, evidence_revision, support_revision
            ),
            "--production-change-scope",
            scope,
            "--change-manifest",
            change_manifest,
            "--diff-summary",
            diff_summary,
            "--audit-complete",
        ]
        state = self.state()
        if state.get("development_mode") == "sequential_slices" and state.get("execution_stage") == "implementation":
            slice_id = state["active_slice"]
            base_revision = state["slices"][slice_id]["base_revision"]
            arguments.extend(
                (
                    "--slice-id",
                    slice_id,
                    "--base-revision",
                    base_revision,
                    "--handoff-manifest",
                    self.handoff_manifest(
                        run_id, slice_id, owner_id, base_revision, revision, changes
                    ),
                )
            )
        if scope_approval:
            arguments.extend(("--scope-approval", scope_approval))
        for finding_id in resolved:
            arguments.extend(("--resolved-finding", finding_id))
        result = self.run_command(
            *arguments,
        )
        return json.loads(result.stdout)

    def review(self, revision: str, run_id: str, reviewer_id: str, status: str = "pass") -> dict:
        result = self.run_command(
            "review-complete",
            "--revision",
            revision,
            "--run-id",
            run_id,
            "--reviewer-id",
            reviewer_id,
            "--status",
            status,
            "--report",
            self.report("reviews", run_id),
            "--credit-manifest",
            self.credit_manifest(
                run_id,
                reviewer_id,
                "final_whole_feature_review",
                (f"final:{reviewer_id}",),
                composition_audit=True,
            ),
        )
        return json.loads(result.stdout)

    def finalize_review(
        self,
        revision: str,
        decision: str,
        *,
        reason: str | None = None,
        rework_scope: str = "product",
        revalidation: str = "targeted",
    ) -> dict:
        arguments = [
            "review-finalize",
            "--revision",
            revision,
            "--decision",
            decision,
            "--report",
            self.report("reviews", f"decision-{decision}"),
            "--rework-scope",
            rework_scope,
            "--revalidation",
            revalidation,
        ]
        if reason:
            arguments.extend(("--reason", reason))
        if revalidation == "full":
            arguments.extend(("--full-wave-trigger", "high_risk_surface"))
        return json.loads(self.run_command(*arguments).stdout)

    def converge_to_qa(self, revision: str = "rev-a") -> None:
        self.engineer(revision, "eng-change")
        self.convergence_pass(revision)
        self.review(revision, "review-1", "reviewer-a")
        self.review(revision, "review-2", "reviewer-b")
        self.finalize_review(revision, "pass")

    def convergence_pass(self, revision: str, *, prefix: str = "conv") -> dict:
        for index, lens in enumerate(
            (
                "persistence-lifecycle",
                "config-security-capacity",
                "integration-runtime-docs",
            ),
            start=1,
        ):
            self.run_command(
                "convergence-audit-complete",
                "--revision",
                revision,
                "--run-id",
                f"{prefix}-{index}",
                "--reviewer-id",
                f"{prefix}-reviewer-{index}",
                "--lens",
                lens,
                "--status",
                "pass",
                "--report",
                self.report("verification", f"{prefix}-{index}"),
                "--credit-manifest",
                self.credit_manifest(
                    f"{prefix}-{index}",
                    f"{prefix}-reviewer-{index}",
                    "full_convergence",
                    (lens,),
                ),
            )
        return json.loads(
            self.run_command(
                "convergence-finalize",
                "--revision",
                revision,
                "--decision",
                "pass",
                "--report",
                self.report("verification", f"{prefix}-decision"),
            ).stdout
        )

    def convergence_rework(
        self,
        revision: str,
        *,
        finding_id: str = "CONV-001",
        prefix: str = "conv-fail",
        revalidation: str = "full",
    ) -> dict:
        for index, lens in enumerate(
            (
                "persistence-lifecycle",
                "config-security-capacity",
                "integration-runtime-docs",
            ),
            start=1,
        ):
            self.run_command(
                "convergence-audit-complete",
                "--revision",
                revision,
                "--run-id",
                f"{prefix}-{index}",
                "--reviewer-id",
                f"{prefix}-reviewer-{index}",
                "--lens",
                lens,
                "--status",
                "fail" if index == 1 else "pass",
                "--report",
                self.report("verification", f"{prefix}-{index}"),
                "--credit-manifest",
                self.credit_manifest(
                    f"{prefix}-{index}",
                    f"{prefix}-reviewer-{index}",
                    "full_convergence",
                    (lens,),
                ),
            )
        self.run_command(
            "add-finding",
            "--id",
            finding_id,
            "--source",
            "convergence",
            "--kind",
            "product",
            "--severity",
            "major",
            "--title",
            "Convergence defect",
            "--evidence",
            "The read-only audit reproduced the defect",
            "--revision",
            revision,
            *self.finding_dimensions(kind_flag="--kind"),
        )
        return json.loads(
            self.run_command(
                "convergence-finalize",
                "--revision",
                revision,
                "--decision",
                "rework",
                "--report",
                self.report("verification", f"{prefix}-decision"),
                "--revalidation",
                revalidation,
                *(("--full-wave-trigger", "high_risk_surface") if revalidation == "full" else ()),
            ).stdout
        )

    def convergence_rework_batch(
        self,
        revision: str,
        prefix: str,
        routed_findings: tuple[tuple[str, str], ...],
    ) -> dict:
        for index, lens in enumerate(
            (
                "persistence-lifecycle",
                "config-security-capacity",
                "integration-runtime-docs",
            ),
            start=1,
        ):
            self.run_command(
                "convergence-audit-complete",
                "--revision",
                revision,
                "--run-id",
                f"{prefix}-{index}",
                "--reviewer-id",
                f"{prefix}-reviewer-{index}",
                "--lens",
                lens,
                "--status",
                "fail" if index == 1 else "pass",
                "--report",
                self.report("verification", f"{prefix}-{index}"),
                "--credit-manifest",
                self.credit_manifest(
                    f"{prefix}-{index}",
                    f"{prefix}-reviewer-{index}",
                    "full_convergence",
                    (lens,),
                ),
            )
        for finding_id, route in routed_findings:
            arguments = [
                "add-finding",
                "--id",
                finding_id,
                "--source",
                "convergence",
                "--kind",
                "product",
                "--severity",
                "major",
                "--title",
                "Routed convergence defect",
                "--evidence",
                f"Reproduced on {revision}",
                "--revision",
                revision,
                *self.finding_dimensions(),
            ]
            if route == "integration":
                arguments.append("--cross-slice-root-cause")
            else:
                arguments.extend(("--origin-slice", route))
            self.run_command(*arguments)
        return json.loads(
            self.run_command(
                "convergence-finalize",
                "--revision",
                revision,
                "--decision",
                "rework",
                "--report",
                self.report("verification", f"{prefix}-decision"),
                "--revalidation",
                "full",
                "--full-wave-trigger",
                "high_risk_surface",
            ).stdout
        )

    def qa(
        self,
        revision: str,
        run_id: str,
        status: str,
        *,
        worker_id: str = "qa-owner",
        reason: str | None = None,
        pending: tuple[str, ...] = (),
    ) -> dict:
        capability = self.state().get("qa_capability", {})
        if status in {"blocked_user", "blocked_environment", "error_test"}:
            if (
                capability.get("status") != "blocked"
                or capability.get("revision") != revision
                or status not in set(capability.get("capabilities", {}).values())
            ):
                capability_name = (
                    "config-credentials"
                    if status == "blocked_user"
                    else "studio-editor-sync"
                    if status == "blocked_environment"
                    else "logging-screenshots"
                )
                self.qa_probe(revision, f"probe-{run_id}", blocked=(capability_name, status))
        elif capability.get("status") != "ready" or capability.get("revision") != revision:
            self.qa_probe(revision, f"probe-{run_id}")
        arguments = [
            "qa-complete",
            "--revision",
            revision,
            "--run-id",
            run_id,
            "--worker-id",
            worker_id,
            "--status",
            status,
            "--report",
            self.report("qa", run_id),
        ]
        if reason:
            arguments.extend(("--reason", reason))
        elif status != "pass":
            arguments.extend(("--reason", f"{status} test result"))
        for scenario in pending:
            arguments.extend(("--pending-scenario", scenario))
        return json.loads(self.run_command(*arguments).stdout)

    def evidence_remediation(
        self,
        revision: str,
        product_revision: str,
        evidence_revision: str,
        run_id: str,
        finding_ids: tuple[str, ...],
        support_revision: str | None = None,
        worker_id: str = "recovery-owner",
    ) -> dict:
        support_revision = support_revision or product_revision
        arguments = [
            "recovery-remediation-complete",
            "--revision",
            revision,
            "--product-revision",
            product_revision,
            "--support-revision",
            support_revision,
            "--evidence-revision",
            evidence_revision,
            "--run-id",
            run_id,
            "--worker-id",
            worker_id,
            "--machine-checks",
            "pass",
            "--report",
            self.report("verification", run_id),
            "--coverage-manifest",
            self.coverage_manifest(
                run_id, product_revision, evidence_revision, support_revision
            ),
            "--production-change-scope",
            "none",
        ]
        for finding_id in finding_ids:
            arguments.extend(("--resolved-finding", finding_id))
        return json.loads(self.run_command(*arguments).stdout)

    def recovery_review(
        self,
        revision: str,
        product_revision: str,
        evidence_revision: str,
        *,
        support_revision: str | None = None,
        status: str = "pass",
        run_id: str = "recovery-review-1",
        reviewer_id: str = "recovery-reviewer",
    ) -> dict:
        support_revision = support_revision or product_revision
        return json.loads(
            self.run_command(
                "recovery-review-complete",
                "--revision",
                revision,
                "--product-revision",
                product_revision,
                "--support-revision",
                support_revision,
                "--evidence-revision",
                evidence_revision,
                "--run-id",
                run_id,
                "--reviewer-id",
                reviewer_id,
                "--status",
                status,
                "--report",
                self.report("reviews", run_id),
            ).stdout
        )

    def test_init_enforces_feature_layout_and_gitignored_test_artifacts(self) -> None:
        self.initialize()
        self.assertEqual("/tests/\n", (self.root / ".gitignore").read_text(encoding="utf-8"))
        for child in ("research", "verification", "reviews", "qa"):
            self.assertTrue((self.root / "tests" / FEATURE / child).is_dir())
        state = self.state()
        self.assertEqual(FEATURE, state["feature"])
        self.assertEqual(8, state["schema_version"])
        self.assertEqual("slice_engineering", state["phase"])
        self.assertEqual("pass", state["preflight"]["resource_budget_check"])

    def test_init_preserves_existing_gitignore(self) -> None:
        (self.root / ".gitignore").write_text(".cache/\n", encoding="utf-8")
        self.initialize()
        self.assertEqual(".cache/\n/tests/\n", (self.root / ".gitignore").read_text(encoding="utf-8"))

    def test_preflight_requires_resource_budget_proof_and_surfaces_runtime_gates(self) -> None:
        self.initialize(complete_preflight=False)
        failed = self.preflight(
            run_id="preflight-budget-fail",
            budget="fail",
            capabilities=("player-control=blocked_user",),
        )
        self.assertEqual("preflight", failed["phase"])
        self.assertEqual("reconcile_resource_budget", failed["next_action"]["action"])

        passed = self.preflight(
            run_id="preflight-budget-pass",
            capabilities=("player-control=blocked_user", "rojo=available"),
        )
        self.assertEqual("slice_research", passed["phase"])
        self.assertEqual("blocked_user", passed["preflight"]["capabilities"]["player-control"])

    def test_slice_research_gate_blocks_engineering_until_explicitly_closed(self) -> None:
        self.initialize(complete_preflight=False)
        pending = self.preflight()
        self.assertEqual("slice_research", pending["phase"])
        blocked = self.run_command(
            "engineer-complete",
            "--revision",
            "rev-a",
            "--run-id",
            "eng-too-early",
            "--owner-id",
            "owner-main",
            "--machine-checks",
            "pass",
            "--report",
            self.report("verification", "eng-too-early"),
            "--coverage-manifest",
            self.coverage_manifest("eng-too-early", "rev-a", "rev-a"),
            "--production-change-scope",
            "local",
            "--audit-complete",
            expected=2,
        )
        self.assertIn("only after slice research", blocked.stderr)

        closed = self.research_not_required("No discovery beyond exact edit files is needed")
        self.assertEqual("slice_engineering", closed["phase"])
        self.assertEqual(
            "not_required", closed["slices"]["SLICE-001"]["research"]["status"]
        )

    def test_slice_research_accepts_one_to_three_fresh_bounded_bundles(self) -> None:
        self.initialize(complete_preflight=False)
        self.preflight()
        first = self.research_bundle("brief-a", "researcher-a")
        second = self.research_bundle("brief-b", "researcher-b")
        completed = json.loads(
            self.run_command(
                "slice-research-complete",
                "--slice-id",
                "SLICE-001",
                "--base-revision",
                "base-0",
                "--owner-id",
                "owner-main",
                "--bundle",
                first,
                "--bundle",
                second,
            ).stdout
        )
        research = completed["slices"]["SLICE-001"]["research"]
        self.assertEqual("slice_engineering", completed["phase"])
        self.assertEqual("complete", research["status"])
        self.assertEqual(2, len(research["bundles"]))
        self.assertEqual(
            ["researcher-a", "researcher-b"],
            sorted(item["researcher_id"] for item in research["bundles"]),
        )
        self.assertTrue(
            all("/tests/teleport-module/research/" in item["path"].replace("\\", "/") for item in research["bundles"])
        )

    def test_research_bundle_must_match_exact_revision_and_complete_status(self) -> None:
        self.initialize(complete_preflight=False)
        self.preflight()
        stale = self.research_bundle(
            "stale", "researcher-stale", base_revision="another-revision"
        )
        mismatch = self.run_command(
            "slice-research-complete",
            "--slice-id",
            "SLICE-001",
            "--base-revision",
            "base-0",
            "--owner-id",
            "owner-main",
            "--bundle",
            stale,
            expected=2,
        )
        self.assertIn("base_revision", mismatch.stderr)

        limited = self.research_bundle("limited", "researcher-limited", status="limit_reached")
        incomplete = self.run_command(
            "slice-research-complete",
            "--slice-id",
            "SLICE-001",
            "--base-revision",
            "base-0",
            "--owner-id",
            "owner-main",
            "--bundle",
            limited,
            expected=2,
        )
        self.assertIn("status complete", incomplete.stderr)

        outside = self.research_bundle("outside", "researcher-outside")
        outside_path = self.root / outside
        outside_data = json.loads(outside_path.read_text(encoding="utf-8"))
        outside_data["result"]["inspected_paths"] = ["unrelated/secret.py"]
        outside_path.write_text(json.dumps(outside_data), encoding="utf-8")
        expanded = self.run_command(
            "slice-research-complete",
            "--slice-id",
            "SLICE-001",
            "--base-revision",
            "base-0",
            "--owner-id",
            "owner-main",
            "--bundle",
            outside,
            expected=2,
        )
        self.assertIn("outside allowed_paths", expanded.stderr)

    def test_worker_budget_opens_a_director_checkpoint_before_another_spawn(self) -> None:
        self.initialize(extra=("--max-workers", "1"))
        changed = self.engineer("rev-a", "eng-1")
        self.assertEqual("checkpoint_required", changed["worker_budget"]["status"])
        self.assertEqual("director_budget_checkpoint", changed["next_action"]["action"])
        authorized = json.loads(
            self.run_command(
                "authorize-budget",
                "--additional-workers",
                "4",
                "--reason",
                "One bounded convergence wave remains",
            ).stdout
        )
        self.assertEqual("running", authorized["worker_budget"]["status"])
        self.assertEqual("complete_parallel_read_only_audits", authorized["next_action"]["action"])

    def test_controller_derives_blocking_from_all_required_dimensions(self) -> None:
        self.initialize()
        self.run_command(
            "add-finding",
            "--id",
            "CLASS-BLOCKING",
            "--source",
            "engineer",
            "--severity",
            "major",
            "--title",
            "Required feature transition fails",
            "--evidence",
            "The supported transition reproduces the wrong state",
            "--revision",
            "base-0",
            *self.finding_dimensions(),
        )
        finding = json.loads(
            (self.root / ".agentic-pipeline" / "findings.json").read_text(
                encoding="utf-8"
            )
        )["items"][0]
        self.assertTrue(finding["blocking"])
        self.assertEqual("product", finding["finding_kind"])
        self.assertNotIn("kind", finding)
        self.assertEqual(["PRD-AC-001"], finding["blocks_acceptance_ids"])
        self.assertEqual("engineering", self.state()["phase"])

    def test_minor_cannot_smuggle_blocking_dimensions_into_remediation(self) -> None:
        self.initialize()
        rejected = self.run_command(
            "add-finding",
            "--id",
            "CLASS-MINOR-BLOCKING",
            "--source",
            "engineer",
            "--severity",
            "minor",
            "--title",
            "Misclassified acceptance failure",
            "--evidence",
            "The candidate claims a core acceptance failure while labeled Minor",
            "--revision",
            "base-0",
            *self.finding_dimensions(severity="minor"),
            expected=2,
        )
        self.assertIn("Minor findings cannot claim", rejected.stderr)

    def test_preexisting_adjacent_major_is_nonblocking_and_deferred_pending(self) -> None:
        self.initialize()
        deferred_reference = self.defer_backlog(local_id="CLASS-DEFERRED")
        self.run_command(
            "add-finding",
            "--id",
            "CLASS-DEFERRED",
            "--source",
            "engineer",
            "--severity",
            "major",
            "--title",
            "Adjacent preexisting issue",
            "--evidence",
            "The issue predates the candidate and does not affect its acceptance path",
            "--revision",
            "base-0",
            *self.finding_dimensions(
                scope_relation="preexisting_adjacent",
                blocks=(),
                deferred_reference=deferred_reference,
            ),
        )
        finding = json.loads(
            (self.root / ".agentic-pipeline" / "findings.json").read_text(
                encoding="utf-8"
            )
        )["items"][0]
        self.assertFalse(finding["blocking"])
        self.assertEqual("deferred_pending", finding["disposition"])
        self.assertEqual("slice_engineering", self.state()["phase"])

    def test_unknown_reachability_requires_bounded_triage_before_remediation(self) -> None:
        self.initialize()
        self.run_command(
            "add-finding",
            "--id",
            "CLASS-UNKNOWN",
            "--source",
            "engineer",
            "--severity",
            "major",
            "--title",
            "Reachability not yet established",
            "--evidence",
            "A static path exists but supported execution is not established",
            "--revision",
            "base-0",
            *self.finding_dimensions(reachability="unknown"),
        )
        held = json.loads(self.run_command("status").stdout)
        self.assertEqual("finding_triage", held["phase"])
        self.assertEqual(
            "complete_bounded_finding_triage", held["next_action"]["action"]
        )
        triaged = json.loads(
            self.run_command(
                "triage-finding",
                "--id",
                "CLASS-UNKNOWN",
                "--production-reachability",
                "theoretical",
                "--evidence",
                "The only caller requires an unsupported configuration",
            ).stdout
        )
        self.assertFalse(triaged["blocking"])
        self.assertEqual("slice_engineering", triaged["phase"])

    def test_controller_rejects_invalid_classification_combinations(self) -> None:
        self.initialize()
        invalid_candidate = self.run_command(
            "add-finding",
            "--id",
            "INVALID-CANDIDATE",
            "--source",
            "engineer",
            "--finding-kind",
            "product",
            "--severity",
            "major",
            "--scope-relation",
            "candidate_introduced",
            "--introduced-by-candidate",
            "false",
            "--production-reachability",
            "normal",
            "--blocks-acceptance-id",
            "PRD-AC-001",
            "--violates-required-invariant",
            "false",
            "--mandatory-core-acceptance-evidence-missing",
            "false",
            "--test-can-miss-product-defect",
            "false",
            "--title",
            "Invalid provenance",
            "--evidence",
            "Contradictory dimensions",
            "--revision",
            "base-0",
            expected=2,
        )
        self.assertIn("requires introduced_by_candidate=true", invalid_candidate.stderr)

        invalid_evidence = self.run_command(
            "add-finding",
            "--id",
            "INVALID-EVIDENCE",
            "--source",
            "engineer",
            "--finding-kind",
            "evidence",
            "--severity",
            "major",
            "--scope-relation",
            "current_feature_path",
            "--introduced-by-candidate",
            "false",
            "--production-reachability",
            "normal",
            "--blocks-acceptance-id",
            "PRD-AC-001",
            "--violates-required-invariant",
            "false",
            "--mandatory-core-acceptance-evidence-missing",
            "false",
            "--test-can-miss-product-defect",
            "false",
            "--title",
            "Overstated evidence gap",
            "--evidence",
            "A duplicate assertion is preferred",
            "--revision",
            "base-0",
            expected=2,
        )
        self.assertIn("Evidence Major requires", invalid_evidence.stderr)

        invalid_support = self.run_command(
            "add-finding",
            "--id",
            "INVALID-SUPPORT",
            "--source",
            "engineer",
            "--finding-kind",
            "support",
            "--severity",
            "major",
            "--scope-relation",
            "current_feature_path",
            "--introduced-by-candidate",
            "false",
            "--production-reachability",
            "normal",
            "--blocks-acceptance-id",
            "PRD-AC-001",
            "--violates-required-invariant",
            "false",
            "--mandatory-core-acceptance-evidence-missing",
            "false",
            "--test-can-miss-product-defect",
            "false",
            "--title",
            "Invalid support blocker",
            "--evidence",
            "Derived metadata is stale",
            "--revision",
            "base-0",
            expected=2,
        )
        self.assertIn("Support and hardening", invalid_support.stderr)
        self.assertEqual([], json.loads(
            (self.root / ".agentic-pipeline" / "findings.json").read_text(encoding="utf-8")
        )["items"])

    def test_critical_invariant_claim_requires_and_persists_exact_evidence(self) -> None:
        self.initialize()
        missing = self.run_command(
            "add-finding",
            "--id",
            "CRITICAL-MISSING-INVARIANT",
            "--source",
            "engineer",
            "--severity",
            "critical",
            "--title",
            "Potential data loss",
            "--evidence",
            "A destructive path was observed",
            "--revision",
            "base-0",
            *self.finding_dimensions(severity="critical", blocks=()),
            expected=2,
        )
        self.assertIn("Critical findings require", missing.stderr)
        self.run_command(
            "add-finding",
            "--id",
            "CRITICAL-INVARIANT",
            "--source",
            "engineer",
            "--severity",
            "critical",
            "--title",
            "Confirmed data loss",
            "--evidence",
            "Supported retry deletes the only durable copy",
            "--revision",
            "base-0",
            *self.finding_dimensions(
                severity="critical",
                blocks=(),
                violates_invariant=True,
                invariant_evidence="INV-DURABILITY: the supported retry destroys committed data",
            ),
        )
        finding = json.loads(
            (self.root / ".agentic-pipeline" / "findings.json").read_text(
                encoding="utf-8"
            )
        )["items"][0]
        self.assertTrue(finding["blocking"])
        self.assertIn("INV-DURABILITY", finding["required_invariant_evidence"])

    def test_full_review_revalidation_requires_explicit_wave_budget_extension(self) -> None:
        self.initialize(extra=("--max-full-review-waves", "1"))
        self.engineer("rev-a", "eng-1")
        self.convergence_pass("rev-a")
        self.review("rev-a", "review-1", "reviewer-a", status="fail")
        self.review("rev-a", "review-2", "reviewer-b", status="pass")
        self.run_command(
            "add-finding",
            "--id",
            "R-BROAD-001",
            "--source",
            "review",
            "--kind",
            "product",
            "--severity",
            "major",
            "--title",
            "Architectural contract mismatch",
            "--evidence",
            "The correction changes a shared contract across the feature boundary",
            "--revision",
            "rev-a",
            *self.finding_dimensions(),
        )
        rework = self.finalize_review(
            "rev-a",
            "rework",
            reason="Broad correction requires a fresh full Review pair",
            revalidation="full",
        )
        self.assertEqual("checkpoint_required", rework["worker_budget"]["status"])
        self.assertEqual("director_budget_checkpoint", rework["next_action"]["action"])
        self.run_command(
            "authorize-budget",
            "--additional-workers",
            "4",
            "--reason",
            "Fund one bounded full Review revalidation wave",
            expected=2,
        )
        authorized = json.loads(
            self.run_command(
                "authorize-budget",
                "--additional-workers",
                "4",
                "--additional-full-review-waves",
                "1",
                "--reason",
                "Fund one bounded full Review revalidation wave",
            ).stdout
        )
        self.assertEqual("running", authorized["worker_budget"]["status"])
        self.assertEqual(2, authorized["worker_budget"]["max_full_review_waves"])
        self.assertEqual("resume_engineering_owner", authorized["next_action"]["action"])

    def test_init_rejects_noncanonical_document_paths(self) -> None:
        root_prd = self.root / "product-requirements.md"
        root_prd.write_bytes(self.requirements.read_bytes())
        self.run_command(
            "init",
            "--feature",
            FEATURE,
            "--requirements",
            "product-requirements.md",
            "--spec",
            f"docs/features/{FEATURE}/technical-specification.md",
            "--slice",
            "slice-1",
            expected=2,
        )

    def test_init_rejects_draft_or_stale_specification(self) -> None:
        self.write_spec(status="draft")
        self.run_command(
            "init",
            "--feature",
            FEATURE,
            "--requirements",
            f"docs/features/{FEATURE}/product-requirements.md",
            "--spec",
            f"docs/features/{FEATURE}/technical-specification.md",
            "--slice",
            "slice-1",
            expected=2,
        )
        self.write_spec(sha="0" * 64)
        self.run_command(
            "init",
            "--feature",
            FEATURE,
            "--requirements",
            f"docs/features/{FEATURE}/product-requirements.md",
            "--spec",
            f"docs/features/{FEATURE}/technical-specification.md",
            "--slice",
            "slice-1",
            expected=2,
        )

    def test_compute_revisions_is_deterministic_and_rejects_overlap(self) -> None:
        self.initialize()
        product_a = self.root / "src" / "a.py"
        product_b = self.root / "src" / "b.py"
        evidence = self.root / "tests" / "fixture.txt"
        support = self.root / "docs" / "handoff.md"
        product_a.parent.mkdir(parents=True)
        evidence.parent.mkdir(parents=True, exist_ok=True)
        support.parent.mkdir(parents=True, exist_ok=True)
        product_a.write_text("a\n", encoding="utf-8")
        product_b.write_text("b\n", encoding="utf-8")
        evidence.write_text("fixture\n", encoding="utf-8")
        support.write_text("handoff\n", encoding="utf-8")
        first = json.loads(
            self.run_command(
                "compute-revisions",
                "--base-revision",
                "base-1",
                "--product-file",
                "src/b.py",
                "--product-file",
                "src/a.py",
                "--evidence-file",
                "tests/fixture.txt",
                "--support-file",
                "docs/handoff.md",
                "--output",
                f"tests/{FEATURE}/verification/revisions.json",
            ).stdout
        )
        second = json.loads(
            self.run_command(
                "compute-revisions",
                "--base-revision",
                "base-1",
                "--product-file",
                "src/a.py",
                "--product-file",
                "src/b.py",
                "--evidence-file",
                "tests/fixture.txt",
                "--support-file",
                "docs/handoff.md",
            ).stdout
        )
        self.assertEqual(first["revision"], second["revision"])
        self.assertEqual(["src/a.py", "src/b.py"], [item["path"] for item in first["product_files"]])
        self.assertEqual(["docs/handoff.md"], [item["path"] for item in first["support_files"]])
        self.assertTrue(Path(first["manifest"]).is_file())
        self.run_command(
            "compute-revisions",
            "--base-revision",
            "base-1",
            "--product-file",
            "src/a.py",
            "--evidence-file",
            "src/a.py",
            expected=2,
        )
        self.defer_backlog(local_id="REVISION-EXCLUSION")
        excluded = self.run_command(
            "compute-revisions",
            "--base-revision",
            "base-1",
            "--support-file",
            "docs/engineering/deferred-findings.json",
            expected=2,
        )
        self.assertIn("must not enter product, support, evidence", excluded.stderr)

    def test_engineering_owner_is_stable_until_explicit_transfer(self) -> None:
        self.initialize()
        self.engineer("rev-a", "eng-1")
        self.convergence_rework("rev-a", finding_id="CONV-OWNER")
        self.run_command(
            "engineer-complete",
            "--revision",
            "rev-b",
            "--product-revision",
            "rev-b",
            "--support-revision",
            "rev-b",
            "--evidence-revision",
            "rev-b",
            "--run-id",
            "eng-wrong-owner",
            "--owner-id",
            "owner-other",
            "--machine-checks",
            "pass",
            "--report",
            self.report("verification", "eng-wrong-owner"),
            "--coverage-manifest",
            self.coverage_manifest("eng-wrong-owner", "rev-b", "rev-b"),
            "--production-change-scope",
            "local",
            "--resolved-finding",
            "CONV-OWNER",
            "--audit-complete",
            expected=2,
        )
        transferred = json.loads(
            self.run_command(
                "transfer-engineering-owner",
                "--from-owner",
                "owner-main",
                "--to-owner",
                "owner-other",
                "--reason",
                "Original owner is unavailable; frozen batch is unchanged",
                "--handoff-manifest",
                self.owner_handoff_manifest(
                    "owner-unavailable",
                    "SLICE-001",
                    "owner-main",
                    "owner-other",
                    "rev-a",
                    "Original owner is unavailable; frozen batch is unchanged",
                    ("CONV-OWNER",),
                ),
            ).stdout
        )
        self.assertEqual("owner-other", transferred["engineering_owner_id"])
        changed = self.engineer(
            "rev-b",
            "eng-new-owner",
            owner_id="owner-other",
            resolved=("CONV-OWNER",),
        )
        self.assertEqual("convergence", changed["phase"])
    def test_happy_path_uses_one_clean_engineer_and_two_reviews(self) -> None:
        self.initialize()
        changed = self.engineer("rev-a", "eng-1")
        self.assertEqual("changed", changed["last_engineer_outcome"])
        clean = self.convergence_pass("rev-a")
        self.assertEqual("parallel_read_only_convergence", clean["engineer_clean"]["source"])
        self.assertEqual("review", clean["phase"])

        first = self.review("rev-a", "review-1", "reviewer-a")
        self.assertEqual("running", first["review"]["status"])
        second = self.review("rev-a", "review-2", "reviewer-b")
        self.assertEqual("awaiting_decision", second["review"]["status"])
        self.assertEqual("review", second["phase"])
        finalized = self.finalize_review("rev-a", "pass")
        self.assertEqual("passed", finalized["review"]["status"])
        self.assertEqual("qa", finalized["phase"])

        final = self.qa("rev-a", "qa-1", "pass")
        self.assertEqual("ready", final["phase"])
        self.assertTrue(json.loads(self.run_command("ready").stdout)["ready"])

    def test_sequential_slices_seal_exact_handoffs_before_feature_convergence(self) -> None:
        self.write_plan(mode="sequential_slices", slice_count=2)
        self.initialize(research_owner=None)

        first = self.engineer("rev-a", "slice-1", owner_id="owner-a")
        self.assertEqual("slice_research", first["phase"])
        self.assertEqual("SLICE-002", first["active_slice"])
        self.assertEqual("sealed", first["slices"]["SLICE-001"]["status"])
        self.assertEqual("rev-a", first["slices"]["SLICE-002"]["base_revision"])
        self.assertEqual("owner-a", first["owner_by_slice"]["SLICE-001"])
        self.assertEqual(1, len(first["handoff_manifests"]))

        second = self.engineer("rev-b", "slice-2", owner_id="owner-b")
        self.assertEqual("convergence", second["phase"])
        self.assertIsNone(second["active_slice"])
        self.assertEqual("feature_validation", second["execution_stage"])
        self.assertTrue(
            all(item["status"] == "sealed" for item in second["slices"].values())
        )
        self.assertEqual("owner-b", second["owner_by_slice"]["SLICE-002"])

    def test_scope_violation_persists_hold_until_exact_user_approved_rebaseline(self) -> None:
        self.initialize()
        state = self.state()
        self.run_command(
            "slice-scope-check",
            "--slice-id",
            "SLICE-001",
            "--base-revision",
            state["revision"],
            "--owner-id",
            "owner-main",
        )
        change_manifest, diff_summary, _ = self.scope_artifacts(
            "scope-breach",
            slice_id="SLICE-001",
            owner_id="owner-main",
            base_revision="base-0",
            result_revision="rev-a",
            product_changed=True,
            path="src/unplanned.py",
        )
        blocked = self.run_command(
            "engineer-complete",
            "--revision",
            "rev-a",
            "--product-revision",
            "rev-a",
            "--support-revision",
            "rev-a",
            "--evidence-revision",
            "rev-a",
            "--run-id",
            "scope-breach",
            "--owner-id",
            "owner-main",
            "--machine-checks",
            "pass",
            "--report",
            self.report("verification", "scope-breach"),
            "--coverage-manifest",
            self.coverage_manifest("scope-breach", "rev-a", "rev-a"),
            "--production-change-scope",
            "local",
            "--change-manifest",
            change_manifest,
            "--diff-summary",
            diff_summary,
            "--audit-complete",
            expected=2,
        )
        self.assertIn("scope_expansion_hold", blocked.stderr)
        held = self.state()
        self.assertEqual("scope_expansion_hold", held["phase"])
        self.assertIn("unapproved product path", " ".join(held["scope_guard"]["hold"]["violations"]))
        self.run_command(
            "preflight-complete",
            "--run-id",
            "scope-hold-bypass",
            "--resource-budget-check",
            "fail",
            "--report",
            self.report("verification", "scope-hold-bypass"),
            expected=2,
        )
        self.assertEqual("scope_expansion_hold", self.state()["phase"])
        self.run_command(
            "authorize-iteration", "--reason", "cannot bypass scope", expected=2
        )
        self.run_command(
            "transfer-engineering-owner",
            "--from-owner",
            "owner-main",
            "--to-owner",
            "owner-fresh",
            "--reason",
            "cannot bypass scope",
            expected=2,
        )

        plan = self.docs / "development-plan.md"
        plan.write_text(
            plan.read_text(encoding="utf-8").replace(
                "editable_paths: src/feature-1.py",
                "editable_paths: src/feature-1.py, src/unplanned.py",
            ),
            encoding="utf-8",
        )
        plan_sha = hashlib.sha256(plan.read_bytes()).hexdigest()
        planning_state_path = self.root / ".agentic-pipeline" / "development-plan-state.json"
        planning_state = json.loads(planning_state_path.read_text(encoding="utf-8"))
        planning_state["approval"]["approved_sha256"] = plan_sha
        planning_state_path.write_text(json.dumps(planning_state), encoding="utf-8")
        resumed = json.loads(
            self.run_command(
                "rebaseline-scope",
                "--plan-sha256",
                plan_sha,
                "--user-scope-approval",
                "user approved the exact expanded plan SHA",
            ).stdout
        )
        self.assertEqual("slice_engineering", resumed["phase"])
        self.assertEqual("pending", resumed["scope_guard"]["status"])
        self.assertEqual(1, len(resumed["scope_guard"]["rebaseline_history"]))

        self.run_command(
            "slice-scope-check",
            "--slice-id",
            "SLICE-001",
            "--base-revision",
            "base-0",
            "--owner-id",
            "owner-main",
        )
        approved_manifest, approved_summary, _ = self.scope_artifacts(
            "approved-material-scope",
            slice_id="SLICE-001",
            owner_id="owner-main",
            base_revision="base-0",
            result_revision="rev-approved-material",
            product_changed=True,
            path="src/unplanned.py",
            lifecycle_change=True,
        )
        accepted = json.loads(
            self.run_command(
                "engineer-complete",
                "--revision",
                "rev-approved-material",
                "--product-revision",
                "rev-approved-material",
                "--support-revision",
                "rev-approved-material",
                "--evidence-revision",
                "rev-approved-material",
                "--run-id",
                "approved-material-scope",
                "--owner-id",
                "owner-main",
                "--machine-checks",
                "pass",
                "--report",
                self.report("verification", "approved-material-scope"),
                "--coverage-manifest",
                self.coverage_manifest(
                    "approved-material-scope",
                    "rev-approved-material",
                    "rev-approved-material",
                ),
                "--production-change-scope",
                "architectural",
                "--scope-approval",
                "user approved the exact expanded plan SHA",
                "--change-manifest",
                approved_manifest,
                "--diff-summary",
                approved_summary,
                "--audit-complete",
            ).stdout
        )
        self.assertEqual("convergence", accepted["phase"])

    def test_scope_guard_accepts_exact_shared_touchpoint_and_records_churn(self) -> None:
        self.initialize()
        state = self.state()
        self.run_command(
            "slice-scope-check",
            "--slice-id",
            "SLICE-001",
            "--base-revision",
            "base-0",
            "--owner-id",
            "owner-main",
        )
        manifest, summary, _ = self.scope_artifacts(
            "shared-touchpoint",
            slice_id="SLICE-001",
            owner_id="owner-main",
            base_revision="base-0",
            result_revision="rev-shared",
            product_changed=True,
            path="src/contracts.py",
            symbols=["FeatureContract1"],
            touchpoint_id="TP-001",
            change_kind="additive feature contract",
        )
        result = json.loads(
            self.run_command(
                "engineer-complete",
                "--revision",
                "rev-shared",
                "--product-revision",
                "rev-shared",
                "--support-revision",
                "rev-shared",
                "--evidence-revision",
                "rev-shared",
                "--run-id",
                "shared-touchpoint",
                "--owner-id",
                "owner-main",
                "--machine-checks",
                "pass",
                "--report",
                self.report("verification", "shared-touchpoint"),
                "--coverage-manifest",
                self.coverage_manifest("shared-touchpoint", "rev-shared", "rev-shared"),
                "--production-change-scope",
                "local",
                "--change-manifest",
                manifest,
                "--diff-summary",
                summary,
                "--audit-complete",
            ).stdout
        )
        self.assertEqual("passed", result["scope_guard"]["status"])
        self.assertEqual(1, result["scope_guard"]["scope_churn"]["product_files_changed"])
        self.assertEqual(20, result["scope_guard"]["scope_churn"]["product_lines_changed"])

    def test_remediation_batches_follow_slice_dependency_order_then_integration_owner(self) -> None:
        self.write_plan(mode="sequential_slices", slice_count=2)
        self.initialize(
            research_owner=None,
            extra=("--max-consecutive-product-changes", "10"),
        )
        self.engineer("rev-a", "slice-1", owner_id="owner-a")
        self.engineer("rev-b", "slice-2", owner_id="owner-b")
        routed = self.convergence_rework_batch(
            "rev-b",
            "routed",
            (
                ("F-SLICE-2", "SLICE-002"),
                ("F-INTEGRATION", "integration"),
                ("F-SLICE-1", "SLICE-001"),
            ),
        )
        self.assertEqual(
            ["SLICE-001", "SLICE-002", "integration"],
            [item["route"] for item in routed["remediation_queue"]],
        )
        self.assertEqual("owner-a", routed["engineering_owner_id"])

        first = self.engineer(
            "rev-c", "fix-1", owner_id="owner-a", resolved=("F-SLICE-1",)
        )
        self.assertEqual("SLICE-002", first["active_remediation_batch"]["route"])
        self.assertEqual("owner-b", first["engineering_owner_id"])
        second = self.engineer(
            "rev-d", "fix-2", owner_id="owner-b", resolved=("F-SLICE-2",)
        )
        self.assertEqual("integration", second["active_remediation_batch"]["route"])
        self.assertEqual("owner-a", second["engineering_owner_id"])
        final = self.engineer(
            "rev-e", "fix-integration", owner_id="owner-a", resolved=("F-INTEGRATION",)
        )
        self.assertEqual("convergence", final["phase"])
        self.assertTrue(all(item["status"] == "completed" for item in final["remediation_queue"]))

    def test_owner_replacement_does_not_reset_per_slice_full_wave_limit(self) -> None:
        self.initialize(extra=("--max-workers", "30"))
        self.engineer("rev-0", "eng-initial")
        self.convergence_rework("rev-0", finding_id="RETURN-1", prefix="return-1")
        self.engineer("rev-1", "eng-return-1", resolved=("RETURN-1",))
        second = self.convergence_rework(
            "rev-1",
            finding_id="RETURN-2",
            prefix="return-2",
            revalidation="targeted",
        )
        self.assertEqual(2, second["slices"]["SLICE-001"]["full_convergence_waves"])
        transferred = json.loads(
            self.run_command(
                "transfer-engineering-owner",
                "--from-owner",
                "owner-main",
                "--to-owner",
                "owner-fresh",
                "--slice-id",
                "SLICE-001",
                "--reason",
                "Fresh owner receives the same frozen batch",
                "--handoff-manifest",
                self.owner_handoff_manifest(
                    "preserve-wave-budget",
                    "SLICE-001",
                    "owner-main",
                    "owner-fresh",
                    "rev-1",
                    "Fresh owner receives the same frozen batch",
                    ("RETURN-2",),
                ),
            ).stdout
        )
        self.assertEqual(2, transferred["slices"]["SLICE-001"]["full_convergence_waves"])

    def test_changed_revision_never_receives_clean_credit(self) -> None:
        self.initialize()
        changed = self.engineer("rev-a", "eng-1")
        self.assertIsNone(changed["engineer_clean"])
        self.assertEqual("convergence", changed["phase"])

    def test_evidence_only_change_cannot_use_full_engineer_completion(self) -> None:
        self.initialize()
        self.engineer(
            "rev-a",
            "eng-1",
            product_revision="product-a",
            evidence_revision="evidence-a",
        )
        self.convergence_pass("rev-a")
        self.run_command(
            "engineer-complete",
            "--revision",
            "rev-b",
            "--product-revision",
            "product-a",
            "--support-revision",
            "product-a",
            "--evidence-revision",
            "evidence-b",
            "--run-id",
            "eng-wrong-lane",
            "--owner-id",
            "owner-main",
            "--machine-checks",
            "pass",
            "--report",
            self.report("verification", "eng-wrong-lane"),
            "--coverage-manifest",
            self.coverage_manifest("eng-wrong-lane", "product-a", "evidence-b"),
            "--audit-complete",
            expected=2,
        )
        self.assertEqual("review", self.state()["phase"])

    def test_second_full_wave_runs_without_resetting_the_per_slice_counter(self) -> None:
        self.initialize()
        self.engineer(
            "rev-a",
            "eng-1",
            product_revision="product-a",
            evidence_revision="evidence-a",
        )
        self.convergence_rework("rev-a", finding_id="CONV-FIRST")
        held = self.engineer(
            "rev-b",
            "eng-2",
            product_revision="product-b",
            evidence_revision="evidence-b",
            resolved=("CONV-FIRST",),
        )
        self.assertEqual("convergence", held["phase"])
        self.assertEqual(1, held["slices"]["SLICE-001"]["full_convergence_waves"])

    def test_clean_pass_resets_the_consecutive_change_window(self) -> None:
        self.initialize()
        self.engineer("rev-a", "eng-change-a")
        clean = self.convergence_pass("rev-a")
        self.assertEqual(0, clean["iteration_control"]["consecutive_product_changes"])
        self.review("rev-a", "review-a", "reviewer-a")
        self.review("rev-a", "review-b", "reviewer-b")
        self.run_command(
            "add-finding", "--id", "REV-REWORK", "--source", "review",
            "--kind", "product", "--severity", "major", "--title", "Review defect",
            "--evidence", "Review found a product defect", "--revision", "rev-a",
            *self.finding_dimensions(),
        )
        self.finalize_review("rev-a", "rework")
        changed = self.engineer("rev-b", "eng-change-b", resolved=("REV-REWORK",))
        self.assertEqual("closure_review", changed["phase"])
        self.assertEqual(1, changed["iteration_control"]["consecutive_product_changes"])

    def test_legacy_cumulative_counter_does_not_preserve_a_false_hold(self) -> None:
        self.initialize()
        self.engineer("rev-a", "eng-change-a")
        self.convergence_pass("rev-a")
        state = self.state()
        state["phase"] = "convergence_hold"
        state["iteration_control"] = {
            "automatic_product_changes": 6,
            "max_automatic_product_changes": 2,
            "status": "approval_required",
            "reason": "Legacy cumulative counter",
            "authorizations": [],
        }
        (self.root / ".agentic-pipeline" / "state.json").write_text(
            json.dumps(state), encoding="utf-8"
        )
        normalized = json.loads(self.run_command("status").stdout)
        self.assertEqual("engineering", normalized["phase"])
        self.assertEqual(0, normalized["iteration_control"]["consecutive_product_changes"])
        self.assertEqual("resume_engineering_owner", normalized["next_action"]["action"])

    def test_engineer_resolves_product_findings_atomically_without_losing_hold(self) -> None:
        self.initialize()
        self.engineer("rev-a", "eng-change-a")
        self.convergence_rework("rev-a", finding_id="ENG-001")
        held = self.engineer(
            "rev-b", "eng-change-b", product_revision="product-b",
            evidence_revision="evidence-b", resolved=("ENG-001",)
        )
        self.assertEqual("convergence", held["phase"])
        findings = json.loads(
            (self.root / ".agentic-pipeline" / "findings.json").read_text(encoding="utf-8")
        )
        self.assertEqual("resolved", findings["items"][0]["status"])
        self.assertEqual(["ENG-001"], self.state()["engineer_runs"][-1]["resolved_findings"])

    def test_resolve_finding_never_changes_the_pipeline_phase(self) -> None:
        self.initialize()
        self.engineer("rev-a", "eng-change-a")
        self.convergence_rework("rev-a", finding_id="MIN-001")
        self.run_command(
            "resolve-finding", "--id", "MIN-001", "--revision", "rev-a", expected=2
        )
        self.assertEqual("engineering", self.state()["phase"])
        self.engineer("rev-b", "eng-change-b", resolved=("MIN-001",))
        self.run_command(
            "resolve-finding", "--id", "MIN-001", "--revision", "rev-b", expected=2
        )
        self.assertEqual("convergence", self.state()["phase"])

    def test_architectural_change_requires_scope_approval(self) -> None:
        self.initialize()
        self.run_command(
            "engineer-complete",
            "--revision",
            "rev-a",
            "--run-id",
            "eng-architecture",
            "--owner-id",
            "owner-main",
            "--machine-checks",
            "pass",
            "--report",
            self.report("verification", "eng-architecture"),
            "--coverage-manifest",
            self.coverage_manifest("eng-architecture", "rev-a", "rev-a"),
            "--production-change-scope",
            "architectural",
            "--audit-complete",
            expected=2,
        )

    def test_engineer_completion_requires_engineering_phase_and_truthful_scope(self) -> None:
        self.initialize()
        self.run_command(
            "engineer-complete", "--revision", "rev-a", "--run-id", "eng-none-change",
            "--owner-id", "owner-main",
            "--machine-checks", "pass", "--report", self.report("verification", "eng-none-change"),
            "--coverage-manifest", self.coverage_manifest("eng-none-change", "rev-a", "rev-a"),
            "--production-change-scope", "none", "--audit-complete", expected=2,
        )
        self.engineer("rev-a", "eng-change")
        self.run_command(
            "engineer-complete", "--revision", "rev-a", "--run-id", "eng-false-local",
            "--owner-id", "owner-main",
            "--machine-checks", "pass", "--report", self.report("verification", "eng-false-local"),
            "--coverage-manifest", self.coverage_manifest("eng-false-local", "rev-a", "rev-a"),
            "--production-change-scope", "local", "--audit-complete", expected=2,
        )
        self.convergence_pass("rev-a")
        self.run_command(
            "engineer-complete", "--revision", "rev-a", "--run-id", "eng-during-review",
            "--owner-id", "owner-main",
            "--machine-checks", "pass", "--report", self.report("verification", "eng-during-review"),
            "--coverage-manifest", self.coverage_manifest("eng-during-review", "rev-a", "rev-a"),
            "--production-change-scope", "none", "--audit-complete", expected=2,
        )

    def test_evidence_recovery_preserves_clean_product_and_uses_one_fresh_reviewer(self) -> None:
        self.initialize()
        self.engineer(
            "rev-a",
            "eng-1",
            product_revision="product-a",
            evidence_revision="evidence-a",
        )
        self.convergence_pass("rev-a")
        self.review("rev-a", "review-1", "reviewer-a", status="fail")
        self.review("rev-a", "review-2", "reviewer-b", status="pass")
        self.run_command(
            "add-finding",
            "--id",
            "R-EVIDENCE-001",
            "--source",
            "review",
            "--kind",
            "evidence",
            "--severity",
            "major",
            "--title",
            "Missing exact regression",
            "--evidence",
            "The approved acceptance row has no exact executable assertion",
            "--revision",
            "rev-a",
            *self.finding_dimensions(finding_kind="evidence"),
        )
        rework = self.finalize_review(
            "rev-a",
            "rework",
            reason="Only test evidence changes are required",
            rework_scope="evidence",
        )
        self.assertEqual("evidence_recovery", rework["phase"])
        clean_before = rework["engineer_clean"]

        remediated = self.evidence_remediation(
            "rev-b",
            "product-a",
            "evidence-b",
            "evidence-fix-1",
            ("R-EVIDENCE-001",),
        )
        self.assertEqual("recovery_review", remediated["phase"])
        self.assertEqual(clean_before, remediated["engineer_clean"])
        self.assertEqual("product-a", remediated["product_revision"])

        verified = self.recovery_review("rev-b", "product-a", "evidence-b")
        self.assertEqual("passed_recovery", verified["review"]["status"])
        self.assertEqual("qa", verified["phase"])
        self.assertEqual(3, len(self.state()["review_runs"]))

    def test_preexisting_support_finding_is_deferred_without_remediation(self) -> None:
        self.initialize()
        self.engineer(
            "rev-a",
            "eng-1",
            product_revision="product-a",
            support_revision="support-a",
            evidence_revision="evidence-a",
        )
        self.convergence_pass("rev-a", prefix="support-conv")
        self.review("rev-a", "review-1", "reviewer-a", status="pass")
        self.review("rev-a", "review-2", "reviewer-b", status="pass")
        deferred_reference = self.defer_backlog(
            local_id="R-SUPPORT-001", component="Handoff"
        )
        self.run_command(
            "add-finding",
            "--id",
            "R-SUPPORT-001",
            "--source",
            "review",
            "--kind",
            "support",
            "--severity",
            "major",
            "--title",
            "Stale handoff",
            "--evidence",
            "Derived handoff points to an obsolete report",
            "--revision",
            "rev-a",
            *self.finding_dimensions(
                finding_kind="support",
                scope_relation="preexisting_adjacent",
                deferred_reference=deferred_reference,
            ),
        )
        reviewed = self.finalize_review(
            "rev-a",
            "pass",
            reason="Stale derived handoff is preexisting adjacent and deferred",
        )
        finding = json.loads(
            (self.root / ".agentic-pipeline" / "findings.json").read_text(
                encoding="utf-8"
            )
        )["items"][0]
        self.assertEqual("qa", reviewed["phase"])
        self.assertFalse(finding["blocking"])
        self.assertEqual("deferred_pending", finding["disposition"])
        rejected = self.run_command(
            "review-finalize",
            "--revision",
            "rev-a",
            "--decision",
            "rework",
            "--rework-scope",
            "support",
            "--report",
            self.report("reviews", "late-support-rework"),
            expected=2,
        )
        self.assertIn("Review decision requires", rejected.stderr)

    def test_failed_recovery_refreezes_new_evidence_and_checkpoint_resets_cycles(self) -> None:
        self.initialize()
        self.engineer("rev-a", "eng-1", product_revision="product-a", evidence_revision="evidence-a")
        self.convergence_pass("rev-a")
        self.review("rev-a", "review-1", "reviewer-a", status="fail")
        self.review("rev-a", "review-2", "reviewer-b")
        self.run_command(
            "add-finding", "--id", "R-EVIDENCE-001", "--source", "review",
            "--kind", "evidence", "--severity", "major", "--title", "Gap one",
            "--evidence", "Missing assertion", "--revision", "rev-a",
            *self.finding_dimensions(finding_kind="evidence"),
        )
        self.finalize_review(
            "rev-a", "rework", reason="Evidence only", rework_scope="evidence"
        )
        self.evidence_remediation(
            "rev-b", "product-a", "evidence-b", "evidence-fix-1", ("R-EVIDENCE-001",)
        )
        self.run_command(
            "add-finding", "--id", "R-EVIDENCE-002", "--source", "review",
            "--kind", "evidence", "--severity", "major", "--title", "Gap two",
            "--evidence", "Closure review found a missing assertion", "--revision", "rev-b",
            *self.finding_dimensions(finding_kind="evidence"),
        )
        first_fail = self.recovery_review(
            "rev-b", "product-a", "evidence-b", status="fail",
            run_id="recovery-review-1", reviewer_id="recovery-reviewer-1",
        )
        self.assertEqual("evidence_recovery", first_fail["phase"])
        self.assertEqual(["R-EVIDENCE-002"], first_fail["recovery"]["finding_ids"])
        self.evidence_remediation(
            "rev-c", "product-a", "evidence-c", "evidence-fix-2", ("R-EVIDENCE-002",)
        )
        self.run_command(
            "add-finding", "--id", "R-EVIDENCE-003", "--source", "review",
            "--kind", "evidence", "--severity", "major", "--title", "Gap three",
            "--evidence", "Second closure review found another gap", "--revision", "rev-c",
            *self.finding_dimensions(finding_kind="evidence"),
        )
        held = self.recovery_review(
            "rev-c", "product-a", "evidence-c", status="fail",
            run_id="recovery-review-2", reviewer_id="recovery-reviewer-2",
        )
        self.assertEqual("recovery_hold", held["phase"])
        authorized = json.loads(
            self.run_command(
                "authorize-iteration", "--reason", "Director refroze the remaining batch"
            ).stdout
        )
        self.assertEqual("evidence_recovery", authorized["phase"])
        self.assertEqual(0, authorized["recovery"]["cycles"])

    def test_paused_rework_enters_recovery_only_after_explicit_kind_normalization(self) -> None:
        self.initialize()
        self.engineer("rev-a", "eng-1")
        self.convergence_pass("rev-a")
        self.review("rev-a", "review-1", "reviewer-a", status="fail")
        self.review("rev-a", "review-2", "reviewer-b", status="pass")
        self.run_command(
            "add-finding",
            "--id",
            "R-LEGACY-001",
            "--source",
            "review",
            "--kind",
            "evidence",
            "--severity",
            "major",
            "--title",
            "Legacy evidence gap",
            "--evidence",
            "The old controller stored this as a generic Review finding",
            "--revision",
            "rev-a",
            *self.finding_dimensions(finding_kind="evidence"),
        )
        self.finalize_review("rev-a", "rework", reason="Paused before remediation")
        recovered = json.loads(
            self.run_command(
                "start-evidence-recovery",
                "--revision",
                "rev-a",
                "--product-revision",
                "product-a",
                "--support-revision",
                "product-a",
                "--evidence-revision",
                "evidence-a",
                "--finding-id",
                "R-LEGACY-001",
                "--reason",
                "Normalize the paused legacy Review batch",
            ).stdout
        )
        self.assertEqual("evidence_recovery", recovered["phase"])
        findings = json.loads(
            (self.root / ".agentic-pipeline" / "findings.json").read_text(encoding="utf-8")
        )
        self.assertEqual("evidence", findings["items"][0]["finding_kind"])

    def test_pre_v8_state_is_rejected_instead_of_guessing_finding_dimensions(self) -> None:
        self.initialize()
        state_path = self.root / ".agentic-pipeline" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["schema_version"] = 7
        state_path.write_text(json.dumps(state), encoding="utf-8")
        rejected = self.run_command("status", expected=2)
        self.assertIn("Unsupported pipeline state", rejected.stderr)

    def test_partial_engineer_pass_cannot_be_recorded(self) -> None:
        self.initialize()
        self.run_command(
            "engineer-complete",
            "--revision",
            "rev-a",
            "--run-id",
            "eng-partial",
            "--machine-checks",
            "pass",
            "--report",
            self.report("verification", "partial"),
            expected=2,
        )
        self.assertEqual([], self.state()["engineer_runs"])

    def test_report_must_be_inside_feature_test_artifacts(self) -> None:
        self.initialize()
        outside = self.root / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        self.run_command(
            "engineer-complete",
            "--revision",
            "rev-a",
            "--run-id",
            "eng-1",
            "--machine-checks",
            "pass",
            "--report",
            str(outside),
            "--audit-complete",
            expected=2,
        )

    def test_reviews_require_distinct_reviewers(self) -> None:
        self.initialize()
        self.engineer("rev-a", "eng-1")
        self.convergence_pass("rev-a")
        self.review("rev-a", "review-1", "reviewer-a")
        self.run_command(
            "review-complete",
            "--revision",
            "rev-a",
            "--run-id",
            "review-2",
            "--reviewer-id",
            "reviewer-a",
            "--status",
            "pass",
            "--report",
            self.report("reviews", "review-2"),
            "--credit-manifest",
            self.credit_manifest(
                "review-2-duplicate",
                "reviewer-a",
                "final_whole_feature_review",
                ("final:reviewer-a",),
                composition_audit=True,
            ),
            expected=2,
        )
        self.assertEqual(1, len(self.state()["review"]["runs"]))

    def test_unchanged_component_credit_must_be_reused_not_reread(self) -> None:
        self.initialize()
        self.engineer("rev-a", "eng-1")
        self.convergence_pass("rev-a")
        credit = self.state()["component_review_credits"][0]
        common = (
            "review-complete",
            "--revision",
            "rev-a",
            "--run-id",
            "review-credit",
            "--reviewer-id",
            "reviewer-credit",
            "--status",
            "pass",
            "--report",
            self.report("reviews", "review-credit"),
        )
        self.run_command(
            *common,
            "--credit-manifest",
            self.credit_manifest(
                "review-credit-fresh",
                "reviewer-credit",
                "final_whole_feature_review",
                tuple(credit["lenses"]),
                component=credit["component"],
                composition_audit=True,
            ),
            expected=2,
        )
        reused = json.loads(
            self.run_command(
                *common,
                "--credit-manifest",
                self.credit_manifest(
                    "review-credit-reused",
                    "reviewer-credit",
                    "final_whole_feature_review",
                    tuple(credit["lenses"]),
                    component=credit["component"],
                    mode="reused",
                    source_credit_id=credit["id"],
                    composition_audit=True,
                ),
            ).stdout
        )
        self.assertEqual(credit["id"], reused["review"]["runs"][0]["component_credit_ids"][0])
        credit_ids = [
            item["id"] for item in reused["component_review_credits"]
        ]
        self.assertEqual(len(credit_ids), len(set(credit_ids)))

    def test_failed_review_returns_to_engineering_after_both_reports(self) -> None:
        self.initialize()
        self.engineer("rev-a", "eng-1")
        self.convergence_pass("rev-a")
        first = self.review("rev-a", "review-1", "reviewer-a", status="fail")
        self.assertEqual("review", first["phase"])
        second = self.review("rev-a", "review-2", "reviewer-b", status="pass")
        self.assertEqual("awaiting_decision", second["review"]["status"])
        self.assertEqual("review", second["phase"])
        self.run_command(
            "add-finding",
            "--id",
            "R-001",
            "--source",
            "review",
            "--severity",
            "major",
            "--title",
            "Incorrect transition",
            "--evidence",
            "Both reports support the failure path",
            "--revision",
            "rev-a",
            *self.finding_dimensions(),
        )
        self.assertEqual("review", self.state()["phase"])
        finalized = self.finalize_review("rev-a", "rework")
        self.assertEqual("failed", finalized["review"]["status"])
        self.assertEqual("engineering", finalized["phase"])

    def test_director_cannot_override_immutable_reviewer_failure(self) -> None:
        self.initialize()
        self.engineer("rev-a", "eng-1")
        self.convergence_pass("rev-a")
        self.review("rev-a", "review-1", "reviewer-a", status="fail")
        self.review("rev-a", "review-2", "reviewer-b", status="pass")
        self.run_command(
            "review-finalize",
            "--revision",
            "rev-a",
            "--decision",
            "pass",
            "--report",
            self.report("reviews", "decision-without-reason"),
            expected=2,
        )
        rejected = self.run_command(
            "review-finalize",
            "--revision",
            "rev-a",
            "--decision",
            "pass",
            "--report",
            self.report("reviews", "decision-with-override-reason"),
            "--reason",
            "Director cannot rewrite an immutable reviewer result",
            expected=2,
        )
        self.assertIn("immutable final Review", rejected.stderr)
        self.assertEqual("review", self.state()["phase"])

    def test_local_product_rework_uses_one_targeted_closure_review(self) -> None:
        self.initialize()
        self.engineer("rev-a", "eng-1")
        self.convergence_pass("rev-a", prefix="initial-conv")
        self.review("rev-a", "review-1", "reviewer-a", status="fail")
        self.review("rev-a", "review-2", "reviewer-b", status="pass")
        self.run_command(
            "add-finding",
            "--id",
            "R-LOCAL-001",
            "--source",
            "review",
            "--kind",
            "product",
            "--severity",
            "major",
            "--title",
            "Local rollback defect",
            "--evidence",
            "The immutable review reproduced one bounded failure path",
            "--revision",
            "rev-a",
            *self.finding_dimensions(),
        )
        rework = self.finalize_review(
            "rev-a",
            "rework",
            reason="Bounded local correction",
        )
        self.assertEqual("targeted", rework["product_revalidation"]["mode"])
        remediated = self.engineer("rev-b", "eng-local-fix", resolved=("R-LOCAL-001",))
        self.assertEqual("closure_review", remediated["phase"])
        closed = json.loads(
            self.run_command(
                "closure-review-complete",
                "--revision",
                "rev-b",
                "--run-id",
                "closure-review-1",
                "--reviewer-id",
                "reviewer-c",
                "--status",
                "pass",
                "--report",
                self.report("reviews", "closure-review-1"),
                "--credit-manifest",
                self.credit_manifest(
                    "closure-review-1",
                    "reviewer-c",
                    "targeted_closure",
                    ("targeted-local-impact",),
                ),
            ).stdout
        )
        self.assertEqual("passed_targeted", closed["review"]["status"])
        self.assertEqual("qa", closed["phase"])
        self.assertEqual(3, len(closed["review"]["runs"]) + 1)

    def test_qa_does_not_spawn_while_preflight_capability_is_blocked(self) -> None:
        self.initialize(complete_preflight=False)
        self.preflight(capabilities=("player-control=blocked_user",))
        self.converge_to_qa()
        status = json.loads(self.run_command("status").stdout)
        self.assertEqual("prepare_qa_prerequisites", status["next_action"]["action"])
        self.assertTrue(status["next_action"]["user_input_required"])
        self.run_command(
            "qa-complete",
            "--revision",
            "rev-a",
            "--run-id",
            "qa-too-early",
            "--worker-id",
            "qa-owner",
            "--status",
            "pass",
            "--report",
            self.report("qa", "qa-too-early"),
            expected=2,
        )
        self.preflight(
            run_id="preflight-player-ready",
            capabilities=("player-control=planned_manual",),
        )
        final = self.qa("rev-a", "qa-manual-operator", "pass")
        self.assertEqual("ready", final["phase"])

    def test_blocked_user_qa_preserves_engineer_and_review_evidence(self) -> None:
        self.initialize()
        self.converge_to_qa()
        blocked = self.qa(
            "rev-a",
            "qa-blocked",
            "blocked_user",
            reason="Player must complete one movement step",
            pending=("AC-PLAYER-MOVE",),
        )
        self.assertEqual("qa", blocked["phase"])
        self.assertEqual("blocked_user", blocked["qa"]["status"])
        self.assertIsNotNone(blocked["engineer_clean"])
        self.assertEqual("passed", blocked["review"]["status"])
        self.assertEqual(1, blocked["open_gates"]["blocked_user"])
        self.assertEqual("user", blocked["next_action"]["owner"])
        self.assertTrue(blocked["next_action"]["user_input_required"])

        resumed = self.qa("rev-a", "qa-resumed", "pass")
        self.assertEqual("ready", resumed["phase"])
        self.assertEqual(0, resumed["open_gates"]["blocked_user"])

    def test_environment_and_test_errors_do_not_restart_engineering(self) -> None:
        self.initialize()
        self.converge_to_qa()
        for status in ("blocked_environment", "error_test"):
            with self.subTest(status=status):
                result = self.qa(
                    "rev-a",
                    f"qa-{status}",
                    status,
                    reason="Runtime control unavailable",
                    pending=("AC-RUNTIME",),
                )
                self.assertEqual("qa", result["phase"])
                self.assertEqual("passed", result["review"]["status"])

    def test_blocked_qa_requires_reason_and_pending_scenario(self) -> None:
        self.initialize()
        self.converge_to_qa()
        self.run_command(
            "qa-complete",
            "--revision",
            "rev-a",
            "--run-id",
            "qa-invalid",
            "--worker-id",
            "qa-owner",
            "--status",
            "blocked_user",
            "--report",
            self.report("qa", "qa-invalid"),
            expected=2,
        )

    def test_product_failure_resets_engineer_and_review_evidence(self) -> None:
        self.initialize()
        self.converge_to_qa()
        self.run_command(
            "add-finding",
            "--id",
            "QA-001",
            "--source",
            "qa",
            "--severity",
            "major",
            "--title",
            "Runtime interaction failed",
            "--evidence",
            "The exact player flow reproduced incorrect behavior",
            "--revision",
            "rev-a",
            *self.finding_dimensions(),
        )
        self.assertEqual("qa", self.state()["phase"])
        failed = self.qa("rev-a", "qa-fail", "fail_product")
        self.assertEqual("engineering", failed["phase"])
        self.assertIsNone(failed["engineer_clean"])
        self.assertEqual("pending", failed["review"]["status"])
        self.assertEqual("resume_engineering_owner", failed["next_action"]["action"])
        self.assertFalse(failed["next_action"]["user_input_required"])

    def test_product_failure_requires_a_registered_qa_finding(self) -> None:
        self.initialize()
        self.converge_to_qa()
        self.run_command(
            "qa-complete",
            "--revision",
            "rev-a",
            "--run-id",
            "qa-unregistered-failure",
            "--worker-id",
            "qa-owner",
            "--status",
            "fail_product",
            "--reason",
            "Runtime behavior failed",
            "--report",
            self.report("qa", "qa-unregistered-failure"),
            expected=2,
        )
        self.assertEqual("qa", self.state()["phase"])

    def test_first_local_qa_fix_after_clean_does_not_open_a_hold(self) -> None:
        self.initialize()
        self.converge_to_qa()
        self.run_command(
            "add-finding",
            "--id",
            "QA-LOCAL",
            "--source",
            "qa",
            "--kind",
            "product",
            "--severity",
            "major",
            "--title",
            "Local runtime defect",
            "--evidence",
            "Reproduced on rev-a",
            "--revision",
            "rev-a",
            *self.finding_dimensions(),
        )
        self.qa("rev-a", "qa-local-fail", "fail_product")
        result = self.engineer(
            "rev-b",
            "eng-qa-fix",
            product_revision="product-b",
            evidence_revision="evidence-b",
            resolved=("QA-LOCAL",),
        )
        self.assertEqual("convergence", result["phase"])
        self.assertEqual(1, result["iteration_control"]["consecutive_product_changes"])

    def test_unresolved_product_finding_prevents_clean_engineer(self) -> None:
        self.initialize()
        self.engineer("rev-a", "eng-1")
        self.convergence_rework("rev-a", finding_id="E-001")
        self.run_command(
            "slice-scope-check",
            "--slice-id",
            "SLICE-001",
            "--base-revision",
            "rev-a",
            "--owner-id",
            "owner-main",
        )
        change_manifest, diff_summary, _ = self.scope_artifacts(
            "eng-2",
            slice_id="SLICE-001",
            owner_id="owner-main",
            base_revision="rev-a",
            result_revision="rev-a",
            product_changed=False,
        )
        blocked = self.run_command(
            "engineer-complete",
            "--revision",
            "rev-a",
            "--product-revision",
            "rev-a",
            "--support-revision",
            "rev-a",
            "--evidence-revision",
            "rev-a",
            "--run-id",
            "eng-2",
            "--owner-id",
            "owner-main",
            "--machine-checks",
            "pass",
            "--report",
            self.report("verification", "eng-2"),
            "--coverage-manifest",
            self.coverage_manifest("eng-2", "rev-a", "rev-a"),
            "--production-change-scope",
            "none",
            "--change-manifest",
            change_manifest,
            "--diff-summary",
            diff_summary,
            "--audit-complete",
            expected=2,
        )
        self.assertIn("complete active origin-routed finding batch", blocked.stderr)
        self.assertEqual("engineering", self.state()["phase"])

    def test_minor_finding_requires_explicit_acceptance(self) -> None:
        self.initialize()
        self.converge_to_qa()
        self.run_command(
            "add-finding",
            "--id",
            "E-002",
            "--source",
            "qa",
            "--severity",
            "minor",
            "--title",
            "Bounded visual defect",
            "--evidence",
            "One non-core transition flickers",
            "--revision",
            "rev-a",
            *self.finding_dimensions(severity="minor", blocks=()),
        )
        self.qa("rev-a", "qa-1", "pass")
        self.run_command("ready", expected=1)
        status = json.loads(self.run_command("status").stdout)
        self.assertEqual(
            "request_residual_risk_decision", status["next_action"]["action"]
        )
        self.assertTrue(status["next_action"]["user_input_required"])
        self.assertEqual(["E-002"], status["next_action"]["finding_ids"])
        self.run_command(
            "accept-finding",
            "--id",
            "E-002",
            "--reason",
            "Accepted for this release by product owner",
            "--approval-reference",
            "user-message-42",
        )
        self.assertTrue(json.loads(self.run_command("ready").stdout)["ready"])

    def test_source_change_blocks_further_progress(self) -> None:
        self.initialize()
        self.requirements.write_text(
            self.requirements.read_text(encoding="utf-8") + "\nChanged.\n",
            encoding="utf-8",
        )
        self.run_command(
            "engineer-complete",
            "--revision",
            "rev-a",
            "--run-id",
            "eng-1",
            "--machine-checks",
            "pass",
            "--report",
            self.report("verification", "eng-1"),
            "--audit-complete",
            expected=2,
        )
        status = json.loads(self.run_command("status").stdout)
        self.assertIn("requirements file changed after pipeline initialization", status["source_drift"])


if __name__ == "__main__":
    unittest.main()
