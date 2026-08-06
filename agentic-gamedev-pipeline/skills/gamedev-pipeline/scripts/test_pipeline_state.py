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

    def run_command(self, *arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *arguments, "--project-root", str(self.root)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(expected, result.returncode, msg=result.stderr or result.stdout)
        return result

    def initialize(self, *, complete_preflight: bool = True, extra: tuple[str, ...] = ()) -> None:
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
            *extra,
        )
        if complete_preflight:
            self.preflight()

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

    def report(self, area: str, name: str) -> str:
        report = self.root / "tests" / FEATURE / area / f"{name}.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps({"name": name}), encoding="utf-8")
        return str(report.relative_to(self.root))

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
            "--audit-complete",
        ]
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
        for child in ("verification", "reviews", "qa"):
            self.assertTrue((self.root / "tests" / FEATURE / child).is_dir())
        state = self.state()
        self.assertEqual(FEATURE, state["feature"])
        self.assertEqual(4, state["schema_version"])
        self.assertEqual("engineering", state["phase"])
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
        self.assertEqual("engineering", passed["phase"])
        self.assertEqual("blocked_user", passed["preflight"]["capabilities"]["player-control"])

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
            ).stdout
        )
        self.assertEqual("owner-other", transferred["engineering_owner_id"])
        changed = self.engineer(
            "rev-b",
            "eng-new-owner",
            owner_id="owner-other",
            resolved=("CONV-OWNER",),
        )
        self.assertEqual("convergence_hold", changed["phase"])
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

    def test_two_product_changes_open_the_convergence_circuit_breaker(self) -> None:
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
        self.assertEqual("convergence_hold", held["phase"])
        self.assertEqual("checkpoint_required", held["iteration_control"]["status"])
        authorized = json.loads(
            self.run_command(
                "authorize-iteration",
                "--reason",
                "Director approved one more convergence pass",
            ).stdout
        )
        self.assertEqual("convergence", authorized["phase"])
        self.assertEqual("running", authorized["iteration_control"]["status"])
        self.assertEqual(0, authorized["iteration_control"]["consecutive_product_changes"])

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
        )
        self.finalize_review("rev-a", "rework")
        changed = self.engineer("rev-b", "eng-change-b")
        self.assertEqual("convergence", changed["phase"])
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
        self.assertEqual("convergence_hold", held["phase"])
        findings = json.loads(
            (self.root / ".agentic-pipeline" / "findings.json").read_text(encoding="utf-8")
        )
        self.assertEqual("resolved", findings["items"][0]["status"])
        self.assertEqual(["ENG-001"], self.state()["engineer_runs"][-1]["resolved_findings"])

    def test_resolve_finding_never_changes_the_pipeline_phase(self) -> None:
        self.initialize()
        self.engineer("rev-a", "eng-change-a")
        self.convergence_rework("rev-a", finding_id="MIN-001")
        self.engineer("rev-b", "eng-change-b")
        self.run_command("resolve-finding", "--id", "MIN-001", "--revision", "rev-b")
        self.assertEqual("convergence_hold", self.state()["phase"])

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

    def test_support_only_rework_preserves_product_and_full_reviews(self) -> None:
        self.initialize()
        self.engineer(
            "rev-a",
            "eng-1",
            product_revision="product-a",
            support_revision="support-a",
            evidence_revision="evidence-a",
        )
        self.convergence_pass("rev-a", prefix="support-conv")
        self.review("rev-a", "review-1", "reviewer-a", status="fail")
        self.review("rev-a", "review-2", "reviewer-b", status="pass")
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
        )
        rework = self.finalize_review(
            "rev-a",
            "rework",
            reason="Only derived support documentation changes",
            rework_scope="support",
        )
        clean_before = rework["engineer_clean"]
        remediated = self.evidence_remediation(
            "rev-b",
            "product-a",
            "evidence-a",
            "support-fix-1",
            ("R-SUPPORT-001",),
            support_revision="support-b",
        )
        self.assertEqual("product-a", remediated["product_revision"])
        self.assertEqual("support-b", remediated["support_revision"])
        self.assertEqual(clean_before, remediated["engineer_clean"])
        verified = self.recovery_review(
            "rev-b",
            "product-a",
            "evidence-a",
            support_revision="support-b",
        )
        self.assertEqual("qa", verified["phase"])

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

    def test_paused_legacy_rework_can_enter_evidence_recovery_explicitly(self) -> None:
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
            "--severity",
            "major",
            "--title",
            "Legacy evidence gap",
            "--evidence",
            "The old controller stored this as a generic Review finding",
            "--revision",
            "rev-a",
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
        self.assertEqual("evidence", findings["items"][0]["kind"])

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
            expected=2,
        )
        self.assertEqual(1, len(self.state()["review"]["runs"]))

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
        )
        self.assertEqual("review", self.state()["phase"])
        finalized = self.finalize_review("rev-a", "rework")
        self.assertEqual("failed", finalized["review"]["status"])
        self.assertEqual("engineering", finalized["phase"])

    def test_parent_may_override_reviewer_failure_with_reason(self) -> None:
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
        finalized = self.finalize_review(
            "rev-a",
            "pass",
            reason="Candidate contradicted the exact verification evidence",
        )
        self.assertEqual("qa", finalized["phase"])

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
        )
        rework = self.finalize_review(
            "rev-a",
            "rework",
            reason="Bounded local correction",
        )
        self.assertEqual("targeted", rework["product_revalidation"]["mode"])
        self.engineer("rev-b", "eng-local-fix", resolved=("R-LOCAL-001",))
        converged = self.convergence_pass("rev-b", prefix="closure-conv")
        self.assertEqual("closure_review", converged["phase"])
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
        blocked = self.engineer("rev-a", "eng-2")
        self.assertEqual("blocked", blocked["last_engineer_outcome"])
        self.assertEqual("engineering", blocked["phase"])

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
