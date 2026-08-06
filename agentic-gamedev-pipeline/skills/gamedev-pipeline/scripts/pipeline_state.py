#!/usr/bin/env python3
"""Deterministic state controller for the agentic GameDev pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATE_DIR = ".agentic-pipeline"
SCHEMA_VERSION = 4
CONTRACT_VERSION = "2026-08-05-efficient-review-v2"
BLOCKING_SEVERITIES = {"critical", "major"}
FINDING_KINDS = {"product", "support", "evidence"}
PASSED_REVIEW_STATUSES = {"passed", "passed_targeted", "passed_recovery"}
DEFAULT_MAX_CONSECUTIVE_PRODUCT_CHANGES = 2
DEFAULT_REQUIRED_CONVERGENCE_AUDITS = 3
DEFAULT_MAX_CONVERGENCE_WAVES = 2
DEFAULT_MAX_WORKERS = 14
DEFAULT_MAX_FULL_REVIEW_WAVES = 2
CONVERGENCE_LENSES = {
    "persistence-lifecycle",
    "config-security-capacity",
    "integration-runtime-docs",
}
PREFLIGHT_CAPABILITY_STATUSES = {
    "available",
    "not_required",
    "planned_manual",
    "blocked_user",
    "blocked_environment",
    "error_test",
}
QA_STATUSES = {
    "pass",
    "fail_product",
    "blocked_user",
    "blocked_environment",
    "error_test",
}
QA_GATE_STATUSES = {"blocked_user", "blocked_environment", "error_test"}


class PipelineError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def runtime_paths(project_root: str) -> tuple[Path, Path, Path]:
    root = Path(project_root).resolve()
    return root, root / STATE_DIR / "state.json", root / STATE_DIR / "findings.json"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_frontmatter(path: Path, label: str) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise PipelineError(f"{label} must contain YAML front matter: {path}")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise PipelineError(f"{label} has unterminated YAML front matter: {path}")
    result: dict[str, str] = {}
    for raw_line in parts[1].splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#") or ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        result[key.strip()] = value.strip().strip('"\'')
    return result


def require_feature_slug(feature: str) -> str:
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", feature):
        raise PipelineError(
            "feature must be a lowercase hyphen slug such as teleport-module"
        )
    return feature


def resolve_project_file(root: Path, supplied: str, label: str) -> Path:
    path = Path(supplied)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if not path.is_file():
        raise PipelineError(f"{label} does not exist: {path}")
    return path


def require_feature_documents(
    root: Path, feature: str, requirements: Path, spec: Path
) -> tuple[dict[str, str], dict[str, str]]:
    feature_dir = (root / "docs" / "features" / feature).resolve()
    expected_requirements = feature_dir / "product-requirements.md"
    expected_spec = feature_dir / "technical-specification.md"
    if requirements != expected_requirements:
        raise PipelineError(
            f"Approved product requirements must be stored at {expected_requirements}"
        )
    if spec != expected_spec:
        raise PipelineError(
            f"Approved technical specification must be stored at {expected_spec}"
        )

    requirements_meta = parse_frontmatter(requirements, "Product requirements")
    if requirements_meta.get("status") != "approved":
        raise PipelineError("product-requirements.md must have status: approved")
    if not requirements_meta.get("revision"):
        raise PipelineError("product-requirements.md must record revision")

    spec_meta = parse_frontmatter(spec, "Technical specification")
    if spec_meta.get("status") != "approved":
        raise PipelineError("technical-specification.md must have status: approved")

    relative_requirements = requirements.relative_to(root).as_posix()
    expected_trace = {
        "source_prd_path": relative_requirements,
        "source_prd_revision": requirements_meta["revision"],
        "source_prd_sha256": file_sha256(requirements),
    }
    for field, expected in expected_trace.items():
        if spec_meta.get(field) != expected:
            raise PipelineError(
                f"technical-specification.md has stale {field}: "
                f"expected {expected!r}, got {spec_meta.get(field)!r}"
            )
    return requirements_meta, spec_meta


def ensure_test_artifact_layout(root: Path, feature: str) -> Path:
    tests_root = (root / "tests" / feature).resolve()
    for child in ("verification", "reviews", "qa"):
        (tests_root / child).mkdir(parents=True, exist_ok=True)

    gitignore = root / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    active_lines = {
        line.strip()
        for line in existing.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    if "/tests/" not in active_lines:
        separator = "" if not existing or existing.endswith(("\n", "\r")) else "\n"
        gitignore.write_text(existing + separator + "/tests/\n", encoding="utf-8")
    return tests_root


def source_drift(state: dict[str, Any]) -> list[str]:
    drift: list[str] = []
    for label in ("requirements", "spec"):
        path = Path(state[f"{label}_path"])
        if not path.is_file():
            drift.append(f"{label} file is missing")
        elif file_sha256(path) != state[f"{label}_sha256"]:
            drift.append(f"{label} file changed after pipeline initialization")
    return drift


def require_sources_current(state: dict[str, Any]) -> None:
    drift = source_drift(state)
    if drift:
        raise PipelineError("; ".join(drift))


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise PipelineError(f"Missing pipeline file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"Cannot read valid JSON from {path}: {exc}") from exc


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def normalize_runtime(state: dict[str, Any], findings: dict[str, Any]) -> None:
    """Add optional fields introduced within the current controller contract."""
    state.setdefault("product_revision", state.get("revision"))
    state.setdefault("support_revision", state.get("product_revision"))
    state.setdefault("evidence_revision", state.get("revision"))
    state.setdefault("coverage_manifest", None)
    iteration = state.setdefault("iteration_control", {})
    authorizations = iteration.setdefault("authorizations", [])
    boundary_times = [
        run.get("recorded_at", "")
        for run in state.get("engineer_runs", [])
        if run.get("outcome") == "clean"
    ]
    if state.get("engineer_clean"):
        boundary_times.append(state["engineer_clean"].get("recorded_at", ""))
    boundary_times.extend(
        item.get("recorded_at", "")
        for item in authorizations
        if item.get("phase") == "convergence_hold"
    )
    boundary = max(boundary_times, default="")
    derived_changes = sum(
        1
        for run in state.get("engineer_runs", [])
        if run.get("outcome") in {"changed", "product_changed"}
        and run.get("recorded_at", "") > boundary
    )
    iteration.setdefault("consecutive_product_changes", derived_changes)
    iteration.setdefault(
        "max_consecutive_product_changes",
        iteration.get(
            "max_automatic_product_changes", DEFAULT_MAX_CONSECUTIVE_PRODUCT_CHANGES
        ),
    )
    iteration.pop("automatic_product_changes", None)
    iteration.pop("max_automatic_product_changes", None)
    if iteration.get("status") == "approval_required":
        iteration["status"] = "checkpoint_required"
    iteration.setdefault("status", "running")
    iteration.setdefault("reason", None)
    if (
        state.get("phase") == "convergence_hold"
        and iteration["consecutive_product_changes"]
        < iteration["max_consecutive_product_changes"]
    ):
        state["phase"] = "engineering"
        iteration["status"] = "running"
        iteration["reason"] = None
    state.setdefault("recovery", None)
    state.setdefault("engineering_owner_id", None)
    state.setdefault("product_revalidation", None)
    state.setdefault("preflight", empty_preflight_state())
    state.setdefault(
        "convergence",
        empty_convergence_state(
            state.get("required_convergence_audits", DEFAULT_REQUIRED_CONVERGENCE_AUDITS)
        ),
    )
    state.setdefault("closure_review", None)
    state.setdefault(
        "worker_budget",
        empty_worker_budget(DEFAULT_MAX_WORKERS, DEFAULT_MAX_FULL_REVIEW_WAVES),
    )
    state["worker_budget"].setdefault("checkpoint_causes", [])
    state["worker_budget"].setdefault(
        "worker_ids",
        sorted(
            {
                record["worker_id"]
                for record in state["worker_budget"].get("records", [])
                if record.get("worker_id")
            }
        ),
    )

    for run in state.get("engineer_runs", []):
        run.setdefault("product_revision", run.get("revision"))
        run.setdefault("support_revision", run.get("product_revision"))
        run.setdefault("evidence_revision", run.get("revision"))
        run.setdefault("change_class", "product" if run.get("outcome") == "changed" else "none")
    clean = state.get("engineer_clean")
    if clean:
        clean.setdefault("product_revision", clean.get("revision"))
        clean.setdefault("support_revision", clean.get("product_revision"))
        clean.setdefault("evidence_revision", clean.get("revision"))
    machine = state.get("machine_checks", {})
    machine.setdefault("product_revision", machine.get("revision"))
    machine.setdefault("support_revision", machine.get("product_revision"))
    machine.setdefault("evidence_revision", machine.get("revision"))
    review = state.get("review", {})
    review.setdefault("product_revision", review.get("revision"))
    review.setdefault("support_revision", review.get("product_revision"))
    review.setdefault("evidence_revision", review.get("revision"))
    review.setdefault("recovery_run", None)
    for item in findings.get("items", []):
        item.setdefault("kind", "product")


def load_runtime(project_root: str) -> tuple[Path, Path, Path, dict[str, Any], dict[str, Any]]:
    root, state_path, findings_path = runtime_paths(project_root)
    state = read_json(state_path)
    findings = read_json(findings_path)
    if state.get("schema_version") != SCHEMA_VERSION or findings.get("schema_version") != SCHEMA_VERSION:
        raise PipelineError("Unsupported pipeline state; reinitialize it for the Review workflow")
    if state.get("contract_version") != CONTRACT_VERSION:
        raise PipelineError("Pipeline contract changed after initialization; reinitialize explicitly")
    normalize_runtime(state, findings)
    return root, state_path, findings_path, state, findings


def save_runtime(
    state_path: Path,
    findings_path: Path,
    state: dict[str, Any],
    findings: dict[str, Any],
) -> None:
    state["updated_at"] = utc_now()
    write_json(state_path, state)
    write_json(findings_path, findings)


def open_blocking(findings: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in findings["items"]
        if item["status"] == "open" and item["severity"] in BLOCKING_SEVERITIES
    ]


def empty_review_state(
    required: int,
    revision: str | None = None,
    product_revision: str | None = None,
    support_revision: str | None = None,
    evidence_revision: str | None = None,
) -> dict[str, Any]:
    return {
        "status": "pending",
        "revision": revision,
        "product_revision": product_revision if product_revision is not None else revision,
        "support_revision": support_revision if support_revision is not None else revision,
        "evidence_revision": evidence_revision if evidence_revision is not None else revision,
        "required": required,
        "runs": [],
        "recovery_run": None,
        "decision": None,
        "decision_report": None,
        "decision_reason": None,
    }


def empty_preflight_state() -> dict[str, Any]:
    return {
        "status": "pending",
        "resource_budget_check": "pending",
        "capabilities": {},
        "runs": [],
    }


def empty_convergence_state(
    required: int,
    revision: str | None = None,
    product_revision: str | None = None,
    support_revision: str | None = None,
    evidence_revision: str | None = None,
    wave: int = 0,
) -> dict[str, Any]:
    return {
        "status": "pending",
        "wave": wave,
        "required": required,
        "revision": revision,
        "product_revision": product_revision,
        "support_revision": support_revision,
        "evidence_revision": evidence_revision,
        "runs": [],
        "decision": None,
        "decision_report": None,
    }


def empty_worker_budget(max_workers: int, max_full_review_waves: int) -> dict[str, Any]:
    return {
        "status": "running",
        "completed_workers": 0,
        "worker_ids": [],
        "max_workers": max_workers,
        "full_review_waves": 0,
        "max_full_review_waves": max_full_review_waves,
        "records": [],
        "reason": None,
        "checkpoint_causes": [],
        "authorizations": [],
    }


def empty_qa_state() -> dict[str, Any]:
    return {
        "status": "pending",
        "revision": None,
        "product_revision": None,
        "support_revision": None,
        "evidence_revision": None,
        "run_id": None,
        "worker_id": None,
        "report": None,
        "pending_scenarios": [],
        "reason": None,
    }


def invalidate_open_gates(state: dict[str, Any], reason: str) -> None:
    for gate in state.get("gates", []):
        if gate.get("status") == "open":
            gate["status"] = "invalidated"
            gate["resolved_at"] = utc_now()
            gate["resolution"] = reason


def reset_validation(
    state: dict[str, Any],
    revision: str | None = None,
    product_revision: str | None = None,
    support_revision: str | None = None,
    evidence_revision: str | None = None,
) -> None:
    state["engineer_clean"] = None
    state["review"] = empty_review_state(
        state["required_reviews"],
        revision,
        product_revision,
        support_revision,
        evidence_revision,
    )
    state["closure_review"] = None
    state["qa"] = empty_qa_state()
    invalidate_open_gates(state, "product revision changed")


def require_current_revision(state: dict[str, Any], revision: str) -> None:
    if not state.get("revision"):
        raise PipelineError("No Engineer revision has been recorded")
    if revision != state["revision"]:
        raise PipelineError(
            f"Revision mismatch: current={state['revision']!r}, supplied={revision!r}"
        )


def require_current_identity(
    state: dict[str, Any],
    revision: str,
    product_revision: str | None = None,
    support_revision: str | None = None,
    evidence_revision: str | None = None,
) -> None:
    require_current_revision(state, revision)
    if product_revision is not None and product_revision != state.get("product_revision"):
        raise PipelineError(
            "Product revision mismatch: "
            f"current={state.get('product_revision')!r}, supplied={product_revision!r}"
        )
    if support_revision is not None and support_revision != state.get("support_revision"):
        raise PipelineError(
            "Support revision mismatch: "
            f"current={state.get('support_revision')!r}, supplied={support_revision!r}"
        )
    if evidence_revision is not None and evidence_revision != state.get("evidence_revision"):
        raise PipelineError(
            "Evidence revision mismatch: "
            f"current={state.get('evidence_revision')!r}, supplied={evidence_revision!r}"
        )


def blocked_preflight_capabilities(state: dict[str, Any]) -> dict[str, str]:
    capabilities = state.get("preflight", {}).get("capabilities", {})
    return {
        name: status
        for name, status in capabilities.items()
        if status in QA_GATE_STATUSES
    }


def record_worker(state: dict[str, Any], role: str, worker_id: str) -> None:
    budget = state["worker_budget"]
    worker_ids = budget.setdefault("worker_ids", [])
    reused = worker_id in worker_ids
    if not reused:
        worker_ids.append(worker_id)
        budget["completed_workers"] += 1
    budget["records"].append(
        {
            "role": role,
            "worker_id": worker_id,
            "reused": reused,
            "recorded_at": utc_now(),
        }
    )
    if budget["completed_workers"] >= budget["max_workers"]:
        budget["status"] = "checkpoint_required"
        if "workers" not in budget["checkpoint_causes"]:
            budget["checkpoint_causes"].append("workers")
        budget["reason"] = (
            f"Worker budget reached {budget['completed_workers']}/"
            f"{budget['max_workers']}; consolidate the remaining scope before spawning more workers"
        )


def require_worker_budget(state: dict[str, Any], worker_id: str) -> None:
    budget = state.get("worker_budget", {})
    if (
        budget.get("status") == "checkpoint_required"
        and worker_id not in budget.get("worker_ids", [])
    ):
        raise PipelineError(
            "Worker budget checkpoint is open; run authorize-budget before recording another worker"
        )


def resolve_report(root: Path, state: dict[str, Any], supplied: str, label: str) -> str:
    report = Path(supplied)
    if not report.is_absolute():
        report = root / report
    report = report.resolve()
    tests_root = Path(state["tests_path"]).resolve()
    try:
        report.relative_to(tests_root)
    except ValueError as exc:
        raise PipelineError(f"{label} must be stored under {tests_root}") from exc
    if not report.is_file():
        raise PipelineError(f"{label} does not exist: {report}")
    return str(report)


def resolve_coverage_manifest(
    root: Path,
    state: dict[str, Any],
    supplied: str,
    product_revision: str,
    support_revision: str,
    evidence_revision: str,
) -> str:
    manifest_path = resolve_report(root, state, supplied, "Coverage manifest")
    manifest = read_json(Path(manifest_path))
    if manifest.get("schema_version") != 1:
        raise PipelineError("Coverage manifest must use schema_version 1")
    if manifest.get("product_revision") != product_revision:
        raise PipelineError("Coverage manifest product_revision does not match the pass")
    if manifest.get("support_revision") != support_revision:
        raise PipelineError("Coverage manifest support_revision does not match the pass")
    if manifest.get("evidence_revision") != evidence_revision:
        raise PipelineError("Coverage manifest evidence_revision does not match the pass")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        raise PipelineError("Coverage manifest must contain at least one requirement entry")
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise PipelineError("Every coverage entry must have a string id")
        entry_id = entry["id"]
        if entry_id in seen:
            raise PipelineError(f"Duplicate coverage entry: {entry_id}")
        seen.add(entry_id)
        status = entry.get("status")
        if status not in {"covered", "finding", "not_applicable"}:
            raise PipelineError(f"Coverage entry {entry_id} has invalid status")
        if status == "covered":
            if not entry.get("implementation_evidence"):
                raise PipelineError(
                    f"Covered entry {entry_id} must record implementation_evidence"
                )
            tests = entry.get("tests")
            if not isinstance(tests, list) or not tests:
                raise PipelineError(f"Covered entry {entry_id} must record exact tests")
            for test in tests:
                required = {"file", "suite", "symbol", "assertions", "execution", "evidence"}
                if not isinstance(test, dict) or any(not test.get(field) for field in required):
                    raise PipelineError(
                        f"Coverage entry {entry_id} has an incomplete exact-test record"
                    )
        elif status == "finding" and not entry.get("finding_ids"):
            raise PipelineError(f"Finding entry {entry_id} must record finding_ids")
        elif status == "not_applicable" and not entry.get("reason"):
            raise PipelineError(f"Not-applicable entry {entry_id} must record a reason")
    return manifest_path


def resolve_input_file(root: Path, supplied: str, label: str) -> tuple[Path, str]:
    path = Path(supplied)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise PipelineError(f"{label} must be inside {root}") from exc
    if not path.is_file():
        raise PipelineError(f"{label} does not exist: {path}")
    if relative == STATE_DIR or relative.startswith(f"{STATE_DIR}/"):
        raise PipelineError(f"{label} must not include controller state")
    return path, relative


def revision_for_domain(base_revision: str, records: list[dict[str, str]]) -> str:
    payload = f"base:{base_revision}\n" + "".join(
        f"{record['path']}\0{record['sha256']}\n"
        for record in sorted(records, key=lambda item: item["path"])
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cmd_compute_revisions(args: argparse.Namespace) -> int:
    root, _, _, state, _ = load_runtime(args.project_root)
    require_sources_current(state)
    domains: dict[str, list[dict[str, str]]] = {
        "product": [],
        "support": [],
        "evidence": [],
    }
    assigned: dict[str, str] = {}
    for domain, supplied_files in (
        ("product", args.product_file or []),
        ("support", args.support_file or []),
        ("evidence", args.evidence_file or []),
    ):
        for supplied in supplied_files:
            path, relative = resolve_input_file(root, supplied, f"{domain} file")
            if relative in assigned:
                previous = assigned[relative]
                if previous == domain:
                    raise PipelineError(
                        f"Revision input {relative} is duplicated in {domain}"
                    )
                raise PipelineError(
                    f"Revision input {relative} is assigned to both {previous} and {domain}"
                )
            assigned[relative] = domain
            domains[domain].append({"path": relative, "sha256": file_sha256(path)})

    product_revision = revision_for_domain(args.base_revision, domains["product"])
    support_revision = revision_for_domain(args.base_revision, domains["support"])
    evidence_revision = revision_for_domain(args.base_revision, domains["evidence"])
    revision = hashlib.sha256(
        (
            f"product:{product_revision}\n"
            f"support:{support_revision}\n"
            f"evidence:{evidence_revision}\n"
        ).encode("utf-8")
    ).hexdigest()
    result = {
        "schema_version": 1,
        "base_revision": args.base_revision,
        "product_files": sorted(domains["product"], key=lambda item: item["path"]),
        "support_files": sorted(domains["support"], key=lambda item: item["path"]),
        "evidence_files": sorted(domains["evidence"], key=lambda item: item["path"]),
        "product_revision": product_revision,
        "support_revision": support_revision,
        "evidence_revision": evidence_revision,
        "revision": revision,
    }
    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = root / output
        output = output.resolve()
        verification_root = Path(state["tests_path"]).resolve() / "verification"
        try:
            output_relative = output.relative_to(root).as_posix()
            output.relative_to(verification_root)
        except ValueError as exc:
            raise PipelineError(
                f"Revision manifest must be stored under {verification_root}"
            ) from exc
        if output_relative in assigned:
            raise PipelineError("Revision manifest cannot hash itself as a revision input")
        output.parent.mkdir(parents=True, exist_ok=True)
        write_json(output, result)
        result["manifest"] = str(output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def resolve_product_findings(
    findings: dict[str, Any],
    resolved_ids: set[str],
    revision: str,
    product_revision: str,
    evidence_revision: str,
) -> None:
    for finding_id in resolved_ids:
        target = next(
            (item for item in findings["items"] if item["id"] == finding_id), None
        )
        if target is None:
            raise PipelineError(f"Unknown finding ID: {finding_id}")
        if target.get("status") != "open":
            raise PipelineError(f"Finding is not open: {finding_id}")
        # A product-changing owner pass may close one normalized mixed batch;
        # keeping support/evidence findings open would force a second serial lane.
        target["status"] = "resolved"
        target["resolved_revision"] = revision
        target["resolved_product_revision"] = product_revision
        target["resolved_evidence_revision"] = evidence_revision
        target["resolved_at"] = utc_now()


def next_action(
    state: dict[str, Any], findings: dict[str, Any] | None = None
) -> dict[str, Any]:
    phase = state.get("phase")
    if source_drift(state):
        return {
            "action": "reconcile_source_drift",
            "owner": "technical_director",
            "user_input_required": False,
        }
    budget = state.get("worker_budget", {})
    technical_decision_pending = (
        phase == "convergence"
        and state.get("convergence", {}).get("status") == "awaiting_decision"
    ) or (
        phase == "review"
        and state.get("review", {}).get("status") == "awaiting_decision"
    )
    resume_identity_available = (
        phase == "engineering" and bool(state.get("engineering_owner_id"))
    ) or (
        phase == "qa" and bool(state.get("qa", {}).get("worker_id"))
    ) or (
        phase == "evidence_recovery"
        and bool((state.get("recovery") or {}).get("remediation_owner_id"))
    )
    full_review_checkpoint = "full_review_waves" in budget.get(
        "checkpoint_causes", []
    )
    if (
        budget.get("status") == "checkpoint_required"
        and not technical_decision_pending
        and (full_review_checkpoint or not resume_identity_available)
        and phase != "ready"
    ):
        return {
            "action": "director_budget_checkpoint",
            "owner": "technical_director",
            "user_input_required": False,
            "completed_workers": budget.get("completed_workers"),
            "max_workers": budget.get("max_workers"),
            "reason": budget.get("reason"),
        }
    if phase == "preflight":
        action = (
            "reconcile_resource_budget"
            if state.get("preflight", {}).get("resource_budget_check") == "fail"
            else "run_environment_preflight"
        )
        return {
            "action": action,
            "owner": "technical_director",
            "user_input_required": False,
        }
    if phase == "engineering":
        return {
            "action": (
                "resume_engineering_owner"
                if state.get("engineering_owner_id")
                else "spawn_implementation_owner"
            ),
            "owner": "technical_director",
            "user_input_required": False,
            "engineering_owner_id": state.get("engineering_owner_id"),
        }
    if phase == "convergence":
        convergence = state.get("convergence", {})
        return {
            "action": (
                "finalize_convergence_wave"
                if convergence.get("status") == "awaiting_decision"
                else "complete_parallel_read_only_audits"
            ),
            "owner": "technical_director",
            "user_input_required": False,
            "required": convergence.get("required"),
            "completed": len(convergence.get("runs", [])),
        }
    if phase in {"convergence_hold", "recovery_hold"}:
        return {
            "action": "director_checkpoint",
            "owner": "technical_director",
            "user_input_required": False,
        }
    if phase == "review":
        action = (
            "finalize_review"
            if state.get("review", {}).get("status") == "awaiting_decision"
            else "complete_parallel_reviews"
        )
        return {
            "action": action,
            "owner": "technical_director",
            "user_input_required": False,
        }
    if phase == "evidence_recovery":
        return {
            "action": (
                "resume_nonproduct_remediator"
                if (state.get("recovery") or {}).get("remediation_owner_id")
                else "run_nonproduct_remediation"
            ),
            "owner": "technical_director",
            "user_input_required": False,
            "worker_id": (state.get("recovery") or {}).get("remediation_owner_id"),
        }
    if phase == "recovery_review":
        return {
            "action": "run_recovery_review",
            "owner": "technical_director",
            "user_input_required": False,
        }
    if phase == "closure_review":
        return {
            "action": "run_targeted_closure_review",
            "owner": "technical_director",
            "user_input_required": False,
        }
    if phase == "qa":
        blocked_capabilities = blocked_preflight_capabilities(state)
        if blocked_capabilities:
            user_gate = any(
                status == "blocked_user" for status in blocked_capabilities.values()
            )
            return {
                "action": "prepare_qa_prerequisites",
                "owner": "user" if user_gate else "technical_director",
                "user_input_required": user_gate,
                "capabilities": blocked_capabilities,
            }
        gates = [
            gate for gate in state.get("gates", []) if gate.get("status") == "open"
        ]
        user_gate = any(gate.get("category") == "blocked_user" for gate in gates)
        return {
            "action": "resolve_qa_gate" if gates else "run_or_resume_qa",
            "owner": "user" if user_gate else "technical_director",
            "user_input_required": user_gate,
        }
    if phase == "ready":
        open_minor = [
            item
            for item in (findings or {}).get("items", [])
            if item.get("status") == "open" and item.get("severity") == "minor"
        ]
        if open_minor:
            return {
                "action": "request_residual_risk_decision",
                "owner": "user",
                "user_input_required": True,
                "finding_ids": sorted(item["id"] for item in open_minor),
            }
        return {
            "action": "run_ready",
            "owner": "technical_director",
            "user_input_required": False,
        }
    return {
        "action": "inspect_state",
        "owner": "technical_director",
        "user_input_required": False,
    }


def cmd_init(args: argparse.Namespace) -> int:
    root, state_path, findings_path = runtime_paths(args.project_root)
    if not root.is_dir():
        raise PipelineError(f"Project root does not exist: {root}")
    if state_path.exists() or findings_path.exists():
        raise PipelineError(f"Pipeline is already initialized under {state_path.parent}")
    feature = require_feature_slug(args.feature)
    if args.required_reviews != 2:
        raise PipelineError("required-reviews must be exactly 2")
    if args.max_consecutive_product_changes < 1:
        raise PipelineError("max-consecutive-product-changes must be positive")
    if args.required_convergence_audits not in {2, 3}:
        raise PipelineError("required-convergence-audits must be 2 or 3")
    if args.max_convergence_waves < 1:
        raise PipelineError("max-convergence-waves must be positive")
    if args.max_workers < 1:
        raise PipelineError("max-workers must be positive")
    if args.max_full_review_waves < 1:
        raise PipelineError("max-full-review-waves must be positive")

    requirements = resolve_project_file(root, args.requirements, "Approved product requirements")
    spec = resolve_project_file(root, args.spec, "Approved technical specification")
    requirements_meta, _ = require_feature_documents(root, feature, requirements, spec)
    tests_root = ensure_test_artifact_layout(root, feature)

    now = utc_now()
    state = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "project_root": str(root),
        "feature": feature,
        "slice_id": args.slice,
        "requirements_path": str(requirements),
        "requirements_revision": requirements_meta["revision"],
        "requirements_sha256": file_sha256(requirements),
        "spec_path": str(spec),
        "spec_sha256": file_sha256(spec),
        "tests_path": str(tests_root),
        "phase": "preflight",
        "revision": None,
        "product_revision": None,
        "support_revision": None,
        "evidence_revision": None,
        "coverage_manifest": None,
        "last_engineer_run_id": None,
        "last_engineer_outcome": None,
        "machine_checks": {
            "status": "pending",
            "revision": None,
            "report": None,
        },
        "engineer_clean": None,
        "engineering_owner_id": None,
        "engineer_runs": [],
        "required_convergence_audits": args.required_convergence_audits,
        "max_convergence_waves": args.max_convergence_waves,
        "convergence": empty_convergence_state(args.required_convergence_audits),
        "required_reviews": args.required_reviews,
        "review": empty_review_state(args.required_reviews),
        "review_runs": [],
        "product_revalidation": None,
        "closure_review": None,
        "qa": empty_qa_state(),
        "qa_runs": [],
        "gates": [],
        "preflight": empty_preflight_state(),
        "worker_budget": empty_worker_budget(
            args.max_workers, args.max_full_review_waves
        ),
        "iteration_control": {
            "consecutive_product_changes": 0,
            "max_consecutive_product_changes": args.max_consecutive_product_changes,
            "status": "running",
            "reason": None,
            "authorizations": [],
        },
        "recovery": None,
        "created_at": now,
        "updated_at": now,
    }
    findings = {"schema_version": SCHEMA_VERSION, "items": []}
    write_json(state_path, state)
    write_json(findings_path, findings)
    print(
        json.dumps(
            {
                "initialized": True,
                "state": str(state_path),
                "feature_docs": str(requirements.parent),
                "test_artifacts": str(tests_root),
            },
            ensure_ascii=False,
        )
    )
    return 0


def parse_capabilities(values: list[str] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values or []:
        if "=" not in value:
            raise PipelineError("Capabilities must use <name>=<status>")
        name, status = value.split("=", 1)
        name = name.strip()
        status = status.strip()
        if not re.fullmatch(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", name):
            raise PipelineError(f"Invalid capability name: {name!r}")
        if status not in PREFLIGHT_CAPABILITY_STATUSES:
            raise PipelineError(f"Invalid capability status for {name}: {status!r}")
        if name in result:
            raise PipelineError(f"Duplicate capability: {name}")
        result[name] = status
    return result


def cmd_preflight_complete(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    if state["phase"] == "ready":
        raise PipelineError("A ready pipeline does not accept preflight updates")
    preflight = state["preflight"]
    if any(run["run_id"] == args.run_id for run in preflight["runs"]):
        raise PipelineError(f"Preflight run ID already recorded: {args.run_id}")
    report = resolve_report(root, state, args.report, "Preflight report")
    capabilities = parse_capabilities(args.capability)
    preflight["resource_budget_check"] = args.resource_budget_check
    preflight["capabilities"].update(capabilities)
    preflight["status"] = (
        "complete" if args.resource_budget_check == "pass" else "budget_failed"
    )
    preflight["runs"].append(
        {
            "run_id": args.run_id,
            "resource_budget_check": args.resource_budget_check,
            "capabilities": capabilities,
            "report": report,
            "recorded_at": utc_now(),
        }
    )
    if args.resource_budget_check == "fail":
        state["phase"] = "preflight"
    elif state["phase"] == "preflight":
        state["phase"] = "engineering"
    save_runtime(state_path, findings_path, state, findings)
    return cmd_status(args)


def cmd_status(args: argparse.Namespace) -> int:
    _, _, _, state, findings = load_runtime(args.project_root)
    counts = {"critical": 0, "major": 0, "minor": 0}
    for item in findings["items"]:
        if item["status"] == "open":
            counts[item["severity"]] += 1
    gate_counts = {status: 0 for status in sorted(QA_GATE_STATUSES)}
    for gate in state.get("gates", []):
        if gate.get("status") == "open":
            gate_counts[gate["category"]] += 1
    result = {
        "feature": state["feature"],
        "slice": state["slice_id"],
        "revision": state["revision"],
        "product_revision": state["product_revision"],
        "support_revision": state["support_revision"],
        "evidence_revision": state["evidence_revision"],
        "phase": state["phase"],
        "last_engineer_outcome": state["last_engineer_outcome"],
        "machine_checks": state["machine_checks"],
        "engineer_clean": state["engineer_clean"],
        "engineering_owner_id": state["engineering_owner_id"],
        "preflight": state["preflight"],
        "convergence": state["convergence"],
        "review": state["review"],
        "product_revalidation": state["product_revalidation"],
        "closure_review": state["closure_review"],
        "qa": state["qa"],
        "iteration_control": state["iteration_control"],
        "worker_budget": state["worker_budget"],
        "recovery": state["recovery"],
        "open_findings": counts,
        "open_gates": gate_counts,
        "source_drift": source_drift(state),
        "next_action": next_action(state, findings),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_engineer_complete(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    require_worker_budget(state, args.owner_id)
    if state["phase"] != "engineering":
        raise PipelineError("Full Engineer completion is valid only in the engineering phase")
    if not args.audit_complete:
        raise PipelineError("Engineer pass cannot complete before the full audit-remediation-resweep gate")
    if any(run["run_id"] == args.run_id for run in state["engineer_runs"]):
        raise PipelineError(f"Engineer run ID already recorded: {args.run_id}")
    if state["iteration_control"].get("status") == "checkpoint_required":
        raise PipelineError(
            "Automatic convergence circuit breaker is open; run authorize-iteration first"
        )
    if state.get("engineering_owner_id") is None:
        state["engineering_owner_id"] = args.owner_id
    elif state["engineering_owner_id"] != args.owner_id:
        raise PipelineError(
            "Product remediation must resume the assigned engineering owner; "
            "use transfer-engineering-owner for an explicit handoff"
        )
    report = resolve_report(root, state, args.report, "Engineer verification report")

    input_revision = state.get("revision")
    input_product_revision = state.get("product_revision")
    input_support_revision = state.get("support_revision")
    input_evidence_revision = state.get("evidence_revision")
    product_revision = args.product_revision or args.revision
    support_revision = args.support_revision or product_revision
    evidence_revision = args.evidence_revision or args.revision
    product_changed = input_product_revision != product_revision
    support_changed = input_support_revision != support_revision
    evidence_changed = input_evidence_revision != evidence_revision
    revision_changed = input_revision != args.revision
    if not product_changed and (revision_changed or support_changed or evidence_changed):
        raise PipelineError(
            "Support/evidence-only changes must use recovery-remediation-complete; "
            "a full Engineer pass must not invalidate clean product evidence"
        )
    if product_changed and args.machine_checks != "pass":
        raise PipelineError(
            "A product-changing Engineer must resume until required checks pass"
        )
    if product_changed and args.production_change_scope == "none":
        raise PipelineError("A product change must be classified as local or architectural")
    if not product_changed and args.production_change_scope != "none":
        raise PipelineError("An unchanged product pass must use production-change-scope none")
    if args.production_change_scope == "architectural" and not args.scope_approval:
        raise PipelineError(
            "Architectural or lifecycle scope expansion requires --scope-approval"
        )
    coverage_manifest = resolve_coverage_manifest(
        root,
        state,
        args.coverage_manifest,
        product_revision,
        support_revision,
        evidence_revision,
    )
    resolved_ids = set(args.resolved_finding or [])
    if resolved_ids and not product_changed:
        raise PipelineError("Resolving product findings requires a changed product revision")
    if product_changed:
        reset_validation(
            state,
            args.revision,
            product_revision,
            support_revision,
            evidence_revision,
        )

    state["revision"] = args.revision
    state["product_revision"] = product_revision
    state["support_revision"] = support_revision
    state["evidence_revision"] = evidence_revision
    state["coverage_manifest"] = coverage_manifest
    state["last_engineer_run_id"] = args.run_id
    state["machine_checks"] = {
        "status": args.machine_checks,
        "revision": args.revision,
        "product_revision": product_revision,
        "support_revision": support_revision,
        "evidence_revision": evidence_revision,
        "report": report,
        "coverage_manifest": coverage_manifest,
    }
    resolve_product_findings(
        findings, resolved_ids, args.revision, product_revision, evidence_revision
    )

    if product_changed:
        outcome = "changed"
        iteration = state["iteration_control"]
        iteration["consecutive_product_changes"] += 1
        next_wave = state.get("convergence", {}).get("wave", 0) + 1
        state["convergence"] = empty_convergence_state(
            state["required_convergence_audits"],
            args.revision,
            product_revision,
            support_revision,
            evidence_revision,
            next_wave,
        )
        if (
            iteration["consecutive_product_changes"]
            >= iteration["max_consecutive_product_changes"]
        ):
            iteration["status"] = "checkpoint_required"
            iteration["reason"] = (
                "Two product-changing Engineer passes require a director checkpoint "
                "before another read-only convergence wave"
            )
            iteration["resume_phase"] = "convergence"
            state["phase"] = "convergence_hold"
        else:
            iteration["status"] = "running"
            iteration["reason"] = None
            iteration["resume_phase"] = None
            state["phase"] = "convergence"
    elif args.machine_checks != "pass" or open_blocking(findings):
        outcome = "blocked"
        reset_validation(
            state,
            args.revision,
            product_revision,
            support_revision,
            evidence_revision,
        )
        state["phase"] = "engineering"
    else:
        outcome = "clean"
        state["iteration_control"]["status"] = "running"
        state["iteration_control"]["reason"] = None
        state["iteration_control"]["consecutive_product_changes"] = 0
        state["engineer_clean"] = {
            "run_id": args.run_id,
            "revision": args.revision,
            "product_revision": product_revision,
            "support_revision": support_revision,
            "evidence_revision": evidence_revision,
            "audit_complete": True,
            "report": report,
            "coverage_manifest": coverage_manifest,
            "recorded_at": utc_now(),
        }
        state["review"] = empty_review_state(
            state["required_reviews"],
            args.revision,
            product_revision,
            support_revision,
            evidence_revision,
        )
        state["qa"] = empty_qa_state()
        state["phase"] = "review"

    state["last_engineer_outcome"] = outcome
    state["engineer_runs"].append(
        {
            "run_id": args.run_id,
            "owner_id": args.owner_id,
            "input_revision": input_revision,
            "input_product_revision": input_product_revision,
            "input_support_revision": input_support_revision,
            "input_evidence_revision": input_evidence_revision,
            "revision": args.revision,
            "product_revision": product_revision,
            "support_revision": support_revision,
            "evidence_revision": evidence_revision,
            "change_class": "product" if product_changed else "none",
            "outcome": outcome,
            "machine_checks": args.machine_checks,
            "report": report,
            "coverage_manifest": coverage_manifest,
            "production_change_scope": args.production_change_scope,
            "production_files_changed": args.production_files_changed,
            "production_lines_changed": args.production_lines_changed,
            "scope_approval": args.scope_approval,
            "resolved_findings": sorted(resolved_ids),
            "audit_complete": True,
            "recorded_at": utc_now(),
        }
    )
    record_worker(state, "engineer", args.owner_id)
    save_runtime(state_path, findings_path, state, findings)
    return cmd_status(args)


def cmd_transfer_engineering_owner(args: argparse.Namespace) -> int:
    _, state_path, findings_path, state, findings = load_runtime(args.project_root)
    if state["phase"] != "engineering":
        raise PipelineError("Engineering ownership can transfer only before a remediation pass")
    if state.get("engineering_owner_id") != args.from_owner:
        raise PipelineError("from-owner does not match the assigned engineering owner")
    if args.from_owner == args.to_owner:
        raise PipelineError("Engineering ownership transfer requires a different owner")
    state["engineering_owner_id"] = args.to_owner
    state.setdefault("owner_transfers", []).append(
        {
            "from": args.from_owner,
            "to": args.to_owner,
            "reason": args.reason,
            "recorded_at": utc_now(),
        }
    )
    save_runtime(state_path, findings_path, state, findings)
    return cmd_status(args)


def cmd_convergence_audit_complete(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    require_worker_budget(state, args.reviewer_id)
    require_current_identity(
        state,
        args.revision,
        args.product_revision,
        args.support_revision,
        args.evidence_revision,
    )
    if state["phase"] != "convergence":
        raise PipelineError("Convergence audits can complete only in convergence phase")
    convergence = state["convergence"]
    if convergence.get("status") == "awaiting_decision":
        raise PipelineError("The current convergence wave already has all required reports")
    if any(run["run_id"] == args.run_id for run in convergence["runs"]):
        raise PipelineError(f"Convergence run ID already recorded: {args.run_id}")
    if any(run["reviewer_id"] == args.reviewer_id for run in convergence["runs"]):
        raise PipelineError(f"Convergence reviewer already recorded: {args.reviewer_id}")
    if args.reviewer_id == state.get("engineering_owner_id"):
        raise PipelineError("Convergence audits must be independent of the writing owner")
    if args.reviewer_id in state["worker_budget"].get("worker_ids", []):
        raise PipelineError("Every convergence audit requires a fresh worker identity")
    if any(run["lens"] == args.lens for run in convergence["runs"]):
        raise PipelineError(f"Convergence lens already covered: {args.lens}")
    report = resolve_report(root, state, args.report, "Convergence audit report")
    run = {
        "run_id": args.run_id,
        "reviewer_id": args.reviewer_id,
        "lens": args.lens,
        "status": args.status,
        "revision": args.revision,
        "product_revision": state["product_revision"],
        "support_revision": state["support_revision"],
        "evidence_revision": state["evidence_revision"],
        "report": report,
        "recorded_at": utc_now(),
    }
    convergence["runs"].append(run)
    convergence["status"] = "running"
    if len(convergence["runs"]) == convergence["required"]:
        convergence["status"] = "awaiting_decision"
    record_worker(state, "convergence_audit", args.reviewer_id)
    save_runtime(state_path, findings_path, state, findings)
    return cmd_status(args)


def cmd_convergence_finalize(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    require_current_revision(state, args.revision)
    convergence = state.get("convergence", {})
    if state["phase"] != "convergence" or convergence.get("status") != "awaiting_decision":
        raise PipelineError("Convergence decision requires the complete parallel audit wave")
    if len(convergence.get("runs", [])) != convergence.get("required"):
        raise PipelineError("Convergence decision requires every configured audit lens")
    report = resolve_report(root, state, args.report, "Convergence decision report")
    current_findings = [
        item
        for item in findings["items"]
        if item["status"] == "open"
        and item["source"] == "convergence"
        and item["revision"] == args.revision
    ]
    audit_failed = any(run["status"] == "fail" for run in convergence["runs"])
    convergence["decision"] = args.decision
    convergence["decision_report"] = report
    convergence["decided_at"] = utc_now()

    if args.decision == "pass":
        if current_findings or audit_failed:
            raise PipelineError(
                "Convergence cannot pass while an audit failed or current findings remain open"
            )
        convergence["status"] = "passed"
        state["iteration_control"]["status"] = "running"
        state["iteration_control"]["reason"] = None
        state["iteration_control"]["resume_phase"] = None
        state["iteration_control"]["consecutive_product_changes"] = 0
        state["engineer_clean"] = {
            "source": "parallel_read_only_convergence",
            "run_ids": [run["run_id"] for run in convergence["runs"]],
            "revision": state["revision"],
            "product_revision": state["product_revision"],
            "support_revision": state["support_revision"],
            "evidence_revision": state["evidence_revision"],
            "audit_complete": True,
            "report": report,
            "coverage_manifest": state["coverage_manifest"],
            "recorded_at": utc_now(),
        }
        revalidation = state.get("product_revalidation")
        if revalidation and revalidation.get("mode") == "targeted":
            state["closure_review"] = {
                "status": "pending",
                "revision": state["revision"],
                "product_revision": state["product_revision"],
                "support_revision": state["support_revision"],
                "evidence_revision": state["evidence_revision"],
                "base_review_runs": revalidation["base_review_runs"],
                "finding_ids": revalidation["finding_ids"],
                "run": None,
            }
            state["review"] = empty_review_state(
                state["required_reviews"],
                state["revision"],
                state["product_revision"],
                state["support_revision"],
                state["evidence_revision"],
            )
            state["review"]["status"] = "targeted_pending"
            state["phase"] = "closure_review"
        else:
            state["review"] = empty_review_state(
                state["required_reviews"],
                state["revision"],
                state["product_revision"],
                state["support_revision"],
                state["evidence_revision"],
            )
            state["phase"] = "review"
    else:
        if not current_findings:
            raise PipelineError("Convergence rework requires registered current findings")
        convergence["status"] = "failed"
        if convergence["wave"] >= state["max_convergence_waves"]:
            state["iteration_control"]["status"] = "checkpoint_required"
            state["iteration_control"]["reason"] = (
                "Configured convergence-wave budget was exhausted; aggregate the complete "
                "remaining batch before another owner remediation"
            )
            state["iteration_control"]["resume_phase"] = "engineering"
            state["phase"] = "convergence_hold"
        else:
            state["phase"] = "engineering"
    save_runtime(state_path, findings_path, state, findings)
    return cmd_status(args)


def cmd_review_complete(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    require_worker_budget(state, args.reviewer_id)
    require_current_identity(
        state,
        args.revision,
        args.product_revision,
        args.support_revision,
        args.evidence_revision,
    )
    if state["phase"] != "review":
        raise PipelineError("Final reviews can complete only during the review phase")
    clean = state.get("engineer_clean")
    if (
        not clean
        or clean.get("revision") != state["revision"]
        or clean.get("product_revision") != state["product_revision"]
        or clean.get("support_revision") != state["support_revision"]
        or clean.get("evidence_revision") != state["evidence_revision"]
    ):
        raise PipelineError("Final reviews require passed independent convergence on the current revision")
    if any(run["run_id"] == args.run_id for run in state["review_runs"]):
        raise PipelineError(f"Review run ID already recorded: {args.run_id}")
    current_runs = state["review"]["runs"]
    if any(run["reviewer_id"] == args.reviewer_id for run in current_runs):
        raise PipelineError(f"Reviewer already recorded for this revision: {args.reviewer_id}")
    excluded_reviewers = {state.get("engineering_owner_id")}
    excluded_reviewers.update(
        run.get("reviewer_id") for run in state.get("convergence", {}).get("runs", [])
    )
    if args.reviewer_id in excluded_reviewers:
        raise PipelineError("Final Review requires a fresh identity independent of engineering and convergence")
    if args.reviewer_id in state["worker_budget"].get("worker_ids", []):
        raise PipelineError("Every full Review requires a fresh worker identity")
    report = resolve_report(root, state, args.report, "Review report")

    run = {
        "run_id": args.run_id,
        "reviewer_id": args.reviewer_id,
        "revision": args.revision,
        "product_revision": state["product_revision"],
        "support_revision": state["support_revision"],
        "evidence_revision": state["evidence_revision"],
        "status": args.status,
        "report": report,
        "recorded_at": utc_now(),
    }
    current_runs.append(run)
    state["review_runs"].append(run)
    state["review"]["status"] = "running"

    if len(current_runs) >= state["required_reviews"]:
        state["review"]["status"] = "awaiting_decision"

    record_worker(state, "full_review", args.reviewer_id)
    save_runtime(state_path, findings_path, state, findings)
    return cmd_status(args)


def cmd_review_finalize(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    require_current_revision(state, args.revision)
    review = state.get("review", {})
    if state["phase"] != "review" or review.get("status") != "awaiting_decision":
        raise PipelineError("Review decision requires both final Review reports")
    if len(review.get("runs", [])) != state["required_reviews"]:
        raise PipelineError("Review decision requires exactly two completed Review reports")
    report = resolve_report(root, state, args.report, "Aggregated Review decision report")
    budget = state["worker_budget"]
    budget["full_review_waves"] += 1
    reviewer_failed = any(run["status"] == "fail" for run in review["runs"])
    review_findings = [
        item
        for item in findings["items"]
        if item["status"] == "open"
        and item["source"] == "review"
        and item["revision"] == args.revision
    ]

    if args.decision == "pass":
        if review_findings:
            raise PipelineError("Cannot pass final Review while confirmed Review findings remain open")
        if reviewer_failed and not args.reason:
            raise PipelineError("Overriding a reviewer FAIL requires --reason")
        review["status"] = "passed"
        state["product_revalidation"] = None
        state["phase"] = "qa"
    else:
        if not review_findings:
            raise PipelineError("Rework decision requires at least one registered Review finding")
        review["status"] = "failed"
        state["qa"] = empty_qa_state()
        if args.rework_scope in {"evidence", "support", "recovery"}:
            if any(item.get("kind") == "product" for item in review_findings):
                raise PipelineError(
                    "Non-product recovery cannot contain a product finding"
                )
            state["recovery"] = {
                "status": "awaiting_remediation",
                "base_revision": state["revision"],
                "base_product_revision": state["product_revision"],
                "base_support_revision": state["support_revision"],
                "base_evidence_revision": state["evidence_revision"],
                "finding_ids": [item["id"] for item in review_findings],
                "base_review_runs": list(review["runs"]),
                "remediation_owner_id": None,
                "remediation_runs": [],
                "verification_runs": [],
                "cycles": 0,
                "reason": args.reason,
            }
            state["phase"] = "evidence_recovery"
        else:
            state["recovery"] = None
            state["product_revalidation"] = {
                "mode": args.revalidation,
                "base_revision": state["revision"],
                "base_product_revision": state["product_revision"],
                "base_support_revision": state["support_revision"],
                "base_evidence_revision": state["evidence_revision"],
                "base_review_runs": list(review["runs"]),
                "finding_ids": [item["id"] for item in review_findings],
                "reason": args.reason,
            }
            state["phase"] = "engineering"

    review["decision"] = args.decision
    review["decision_report"] = report
    review["decision_reason"] = args.reason
    review["decided_at"] = utc_now()
    if (
        args.decision == "rework"
        and args.rework_scope == "product"
        and args.revalidation == "full"
        and budget["full_review_waves"] >= budget["max_full_review_waves"]
    ):
        budget["status"] = "checkpoint_required"
        if "full_review_waves" not in budget["checkpoint_causes"]:
            budget["checkpoint_causes"].append("full_review_waves")
        budget["reason"] = (
            f"Full Review wave budget reached {budget['full_review_waves']}/"
            f"{budget['max_full_review_waves']}; use targeted closure or justify another full wave"
        )
    save_runtime(state_path, findings_path, state, findings)
    return cmd_status(args)


def cmd_closure_review_complete(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    require_worker_budget(state, args.reviewer_id)
    require_current_identity(
        state,
        args.revision,
        args.product_revision,
        args.support_revision,
        args.evidence_revision,
    )
    closure = state.get("closure_review")
    if state["phase"] != "closure_review" or not closure:
        raise PipelineError("No targeted product closure Review is pending")
    if closure.get("run"):
        raise PipelineError("The targeted closure Review is already recorded")
    prior_reviewers = {
        run["reviewer_id"] for run in closure.get("base_review_runs", [])
    }
    if args.reviewer_id in prior_reviewers:
        raise PipelineError("Targeted closure requires one fresh reviewer identity")
    if args.reviewer_id == state.get("engineering_owner_id") or any(
        run.get("reviewer_id") == args.reviewer_id
        for run in state.get("convergence", {}).get("runs", [])
    ):
        raise PipelineError("Targeted closure reviewer must be independent of the writer and convergence wave")
    if args.reviewer_id in state["worker_budget"].get("worker_ids", []):
        raise PipelineError("Targeted closure requires a fresh worker identity")
    if any(run["run_id"] == args.run_id for run in state["review_runs"]):
        raise PipelineError(f"Review run ID already recorded: {args.run_id}")
    report = resolve_report(root, state, args.report, "Targeted closure Review report")
    run = {
        "run_id": args.run_id,
        "reviewer_id": args.reviewer_id,
        "mode": "targeted_product_closure",
        "revision": args.revision,
        "product_revision": state["product_revision"],
        "support_revision": state["support_revision"],
        "evidence_revision": state["evidence_revision"],
        "status": args.status,
        "report": report,
        "recorded_at": utc_now(),
    }
    closure["run"] = run
    state["review_runs"].append(run)
    record_worker(state, "targeted_closure_review", args.reviewer_id)
    current_review_findings = [
        item
        for item in findings["items"]
        if item["status"] == "open"
        and item["source"] == "review"
        and item["revision"] == args.revision
    ]
    if args.status == "pass":
        if current_review_findings or open_blocking(findings):
            raise PipelineError(
                "Targeted closure cannot pass while current or blocking findings remain open"
            )
        closure["status"] = "passed"
        state["review"] = {
            "status": "passed_targeted",
            "revision": state["revision"],
            "product_revision": state["product_revision"],
            "support_revision": state["support_revision"],
            "evidence_revision": state["evidence_revision"],
            "required": state["required_reviews"],
            "runs": closure["base_review_runs"],
            "recovery_run": run,
            "decision": "pass",
            "decision_report": report,
            "decision_reason": (
                "One fresh closure reviewer verified the frozen local product batch, "
                "changed impact surface, and preserved complementary Review evidence"
            ),
        }
        state["product_revalidation"] = None
        state["qa"] = empty_qa_state()
        state["phase"] = "qa"
    else:
        if not current_review_findings:
            raise PipelineError(
                "A failed targeted closure Review must register at least one current finding"
            )
        closure["status"] = "failed"
        if any(item.get("kind") == "product" for item in current_review_findings):
            state["phase"] = "engineering"
        else:
            state["recovery"] = {
                "status": "awaiting_remediation",
                "base_revision": state["revision"],
                "base_product_revision": state["product_revision"],
                "base_support_revision": state["support_revision"],
                "base_evidence_revision": state["evidence_revision"],
                "finding_ids": [item["id"] for item in current_review_findings],
                "base_review_runs": list(closure["base_review_runs"]),
                "remediation_owner_id": None,
                "remediation_runs": [],
                "verification_runs": [],
                "cycles": 0,
                "reason": "Targeted product closure found only support/evidence gaps",
            }
            state["phase"] = "evidence_recovery"
    save_runtime(state_path, findings_path, state, findings)
    return cmd_status(args)


def cmd_add_finding(args: argparse.Namespace) -> int:
    _, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    require_current_revision(state, args.revision)
    if any(item["id"] == args.id for item in findings["items"]):
        raise PipelineError(f"Finding ID already exists: {args.id}")
    valid_phases = {
        "engineer": {"engineering"},
        "convergence": {"convergence"},
        "review": {"review", "recovery_review", "closure_review"},
        "qa": {"qa"},
    }
    if state["phase"] not in valid_phases[args.source]:
        raise PipelineError(
            f"{args.source} findings cannot be registered during phase {state['phase']}"
        )
    if args.source == "qa" and args.kind != "product":
        raise PipelineError("QA may register only product findings")
    findings["items"].append(
        {
            "id": args.id,
            "source": args.source,
            "kind": args.kind,
            "severity": args.severity,
            "title": args.title,
            "evidence": args.evidence,
            "revision": args.revision,
            "status": "open",
            "created_at": utc_now(),
            "resolved_revision": None,
        }
    )
    deferred_director_decision = (
        (
            args.source == "review"
            and state["phase"] in {"review", "recovery_review", "closure_review"}
        )
        or (args.source == "convergence" and state["phase"] == "convergence")
        or (args.source == "qa" and state["phase"] == "qa")
    )
    if args.severity in BLOCKING_SEVERITIES and not deferred_director_decision:
        state["phase"] = (
            "evidence_recovery" if args.kind == "evidence" else "engineering"
        )
    save_runtime(state_path, findings_path, state, findings)
    print(json.dumps({"added": args.id}, ensure_ascii=False))
    return 0


def cmd_resolve_finding(args: argparse.Namespace) -> int:
    _, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    require_current_revision(state, args.revision)
    target = next((item for item in findings["items"] if item["id"] == args.id), None)
    if target is None:
        raise PipelineError(f"Unknown finding ID: {args.id}")
    if target["status"] != "open":
        raise PipelineError(f"Finding is not open: {args.id}")
    target["status"] = "resolved"
    target["resolved_revision"] = args.revision
    target["resolved_at"] = utc_now()
    save_runtime(state_path, findings_path, state, findings)
    print(json.dumps({"resolved": args.id}, ensure_ascii=False))
    return 0


def cmd_accept_finding(args: argparse.Namespace) -> int:
    _, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    target = next((item for item in findings["items"] if item["id"] == args.id), None)
    if target is None:
        raise PipelineError(f"Unknown finding ID: {args.id}")
    if target["status"] != "open":
        raise PipelineError(f"Finding is not open: {args.id}")
    if target["severity"] != "minor":
        raise PipelineError("Only minor findings can be accepted as residual risk")
    target["status"] = "accepted"
    target["accepted_reason"] = args.reason
    target["approval_reference"] = args.approval_reference
    target["accepted_at"] = utc_now()
    save_runtime(state_path, findings_path, state, findings)
    print(json.dumps({"accepted": args.id}, ensure_ascii=False))
    return 0


def cmd_start_evidence_recovery(args: argparse.Namespace) -> int:
    """Convert a paused legacy Review rework into the non-product recovery lane."""
    _, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    require_current_revision(state, args.revision)
    review = state.get("review", {})
    if state["phase"] != "engineering" or review.get("status") != "failed":
        raise PipelineError(
            "start-evidence-recovery requires a finalized failed Review paused in engineering"
        )
    selected = set(args.finding_id or [])
    open_review = [
        item
        for item in findings["items"]
        if item["status"] == "open" and item["source"] == "review"
    ]
    if not selected or selected != {item["id"] for item in open_review}:
        raise PipelineError(
            "Supply every and only open Review finding with --finding-id"
        )
    for item in open_review:
        if item.get("kind") == "product":
            item["kind"] = "evidence"
    state["product_revision"] = args.product_revision
    state["support_revision"] = args.support_revision
    state["evidence_revision"] = args.evidence_revision
    clean = state.get("engineer_clean")
    if clean:
        clean["product_revision"] = args.product_revision
        clean["support_revision"] = args.support_revision
        clean["evidence_revision"] = args.evidence_revision
    state["machine_checks"]["product_revision"] = args.product_revision
    state["machine_checks"]["support_revision"] = args.support_revision
    state["machine_checks"]["evidence_revision"] = args.evidence_revision
    review["product_revision"] = args.product_revision
    review["support_revision"] = args.support_revision
    review["evidence_revision"] = args.evidence_revision
    state["recovery"] = {
        "status": "awaiting_remediation",
        "base_revision": state["revision"],
        "base_product_revision": args.product_revision,
        "base_support_revision": args.support_revision,
        "base_evidence_revision": args.evidence_revision,
        "finding_ids": sorted(selected),
        "base_review_runs": list(review.get("runs", [])),
        "remediation_owner_id": None,
        "remediation_runs": [],
        "verification_runs": [],
        "cycles": 0,
        "reason": args.reason,
    }
    state["phase"] = "evidence_recovery"
    save_runtime(state_path, findings_path, state, findings)
    return cmd_status(args)


def cmd_evidence_remediation_complete(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    require_worker_budget(state, args.worker_id)
    recovery = state.get("recovery")
    if state["phase"] != "evidence_recovery" or not recovery:
        raise PipelineError("No support/evidence remediation is awaiting completion")
    if args.product_revision != recovery["base_product_revision"]:
        raise PipelineError(
            "Product revision changed during evidence recovery; return to full engineering"
        )
    if recovery.get("remediation_owner_id") is None:
        recovery["remediation_owner_id"] = args.worker_id
    elif recovery["remediation_owner_id"] != args.worker_id:
        raise PipelineError(
            "Support/evidence recovery must resume the assigned remediator identity"
        )
    if args.production_change_scope != "none":
        raise PipelineError("Support/evidence recovery must not modify runtime product code")
    if args.machine_checks != "pass":
        raise PipelineError("Support/evidence recovery requires passing targeted and aggregate checks")
    if (
        args.support_revision == recovery["base_support_revision"]
        and args.evidence_revision == recovery["base_evidence_revision"]
    ):
        raise PipelineError(
            "Non-product remediation must produce a new support or evidence revision"
        )
    if any(
        run["run_id"] == args.run_id
        for run in recovery.get("remediation_runs", [])
    ):
        raise PipelineError(f"Evidence remediation run ID already recorded: {args.run_id}")

    required_ids = set(recovery["finding_ids"])
    selected_items = [
        item for item in findings["items"] if item["id"] in required_ids
    ]
    if len(selected_items) != len(required_ids) or any(
        item.get("status") != "open" or item.get("kind") == "product"
        for item in selected_items
    ):
        raise PipelineError("The frozen evidence-recovery batch is missing or no longer open")
    resolved_ids = set(args.resolved_finding or [])
    if resolved_ids != required_ids:
        raise PipelineError(
            "Evidence remediation must resolve the complete open evidence finding batch"
        )
    report = resolve_report(root, state, args.report, "Evidence remediation report")
    coverage_manifest = resolve_coverage_manifest(
        root,
        state,
        args.coverage_manifest,
        args.product_revision,
        args.support_revision,
        args.evidence_revision,
    )
    for item in findings["items"]:
        if item["id"] in resolved_ids:
            item["status"] = "resolved"
            item["resolved_revision"] = args.revision
            item["resolved_product_revision"] = args.product_revision
            item["resolved_support_revision"] = args.support_revision
            item["resolved_evidence_revision"] = args.evidence_revision
            item["resolved_at"] = utc_now()

    state["revision"] = args.revision
    state["product_revision"] = args.product_revision
    state["support_revision"] = args.support_revision
    state["evidence_revision"] = args.evidence_revision
    state["coverage_manifest"] = coverage_manifest
    state["machine_checks"] = {
        "status": "pass",
        "revision": args.revision,
        "product_revision": args.product_revision,
        "support_revision": args.support_revision,
        "evidence_revision": args.evidence_revision,
        "report": report,
        "coverage_manifest": coverage_manifest,
    }
    recovery["status"] = "awaiting_verification"
    recovery["current_revision"] = args.revision
    recovery["current_support_revision"] = args.support_revision
    recovery["current_evidence_revision"] = args.evidence_revision
    recovery["remediation_runs"].append(
        {
            "run_id": args.run_id,
            "worker_id": args.worker_id,
            "revision": args.revision,
            "product_revision": args.product_revision,
            "support_revision": args.support_revision,
            "evidence_revision": args.evidence_revision,
            "resolved_findings": sorted(resolved_ids),
            "report": report,
            "coverage_manifest": coverage_manifest,
            "recorded_at": utc_now(),
        }
    )
    review = state["review"]
    review["status"] = "recovery_verification"
    review["revision"] = args.revision
    review["product_revision"] = args.product_revision
    review["support_revision"] = args.support_revision
    review["evidence_revision"] = args.evidence_revision
    review["recovery_run"] = None
    state["qa"] = empty_qa_state()
    state["phase"] = "recovery_review"
    record_worker(state, "nonproduct_remediation", args.worker_id)
    save_runtime(state_path, findings_path, state, findings)
    return cmd_status(args)


def cmd_recovery_review_complete(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    require_worker_budget(state, args.reviewer_id)
    require_current_identity(
        state,
        args.revision,
        args.product_revision,
        args.support_revision,
        args.evidence_revision,
    )
    recovery = state.get("recovery")
    if state["phase"] != "recovery_review" or not recovery:
        raise PipelineError("No evidence recovery verification is pending")
    if any(
        run.get("reviewer_id") == args.reviewer_id
        for run in recovery.get("base_review_runs", []) + recovery.get("verification_runs", [])
    ):
        raise PipelineError("Recovery verification requires a fresh reviewer identity")
    if args.reviewer_id == state.get("engineering_owner_id"):
        raise PipelineError("Recovery reviewer must be independent of the writing owner")
    if args.reviewer_id in state["worker_budget"].get("worker_ids", []):
        raise PipelineError("Recovery verification requires a fresh worker identity")
    if any(run["run_id"] == args.run_id for run in state["review_runs"]):
        raise PipelineError(f"Review run ID already recorded: {args.run_id}")
    report = resolve_report(root, state, args.report, "Recovery Review report")
    run = {
        "run_id": args.run_id,
        "reviewer_id": args.reviewer_id,
        "revision": args.revision,
        "product_revision": args.product_revision,
        "support_revision": args.support_revision,
        "evidence_revision": args.evidence_revision,
        "status": args.status,
        "mode": "evidence_recovery",
        "report": report,
        "recorded_at": utc_now(),
    }
    recovery["verification_runs"].append(run)
    state["review_runs"].append(run)
    state["review"]["recovery_run"] = run
    record_worker(state, "recovery_review", args.reviewer_id)
    if args.status == "pass":
        if open_blocking(findings):
            raise PipelineError(
                "Recovery Review cannot pass while blocking findings remain open"
            )
        state["review"]["status"] = "passed_recovery"
        state["review"]["decision"] = "pass"
        state["review"]["decision_reason"] = (
            "Product revision stayed unchanged; one fresh reviewer verified the "
            "complete normalized support/evidence finding batch"
        )
        recovery["status"] = "passed"
        state["qa"] = empty_qa_state()
        state["phase"] = "qa"
    else:
        open_product = [
            item
            for item in open_blocking(findings)
            if item.get("kind") == "product"
        ]
        if open_product:
            recovery["status"] = "product_defect"
            state["recovery"] = recovery
            state["phase"] = "engineering"
            save_runtime(state_path, findings_path, state, findings)
            return cmd_status(args)
        open_evidence = [
            item
            for item in findings["items"]
            if item.get("status") == "open"
            and item.get("kind") in {"support", "evidence"}
            and item.get("revision") == args.revision
        ]
        if not open_evidence:
            raise PipelineError(
                "A failed recovery Review must register at least one open support/evidence finding"
            )
        recovery["finding_ids"] = sorted(item["id"] for item in open_evidence)
        recovery["cycles"] += 1
        recovery["status"] = "awaiting_remediation"
        state["review"]["status"] = "failed_recovery"
        if recovery["cycles"] >= 2:
            state["iteration_control"]["status"] = "checkpoint_required"
            state["iteration_control"]["reason"] = (
                "Two evidence-recovery cycles require a director checkpoint"
            )
            state["phase"] = "recovery_hold"
        else:
            state["phase"] = "evidence_recovery"
    save_runtime(state_path, findings_path, state, findings)
    return cmd_status(args)


def cmd_authorize_iteration(args: argparse.Namespace) -> int:
    _, state_path, findings_path, state, findings = load_runtime(args.project_root)
    if state["phase"] not in {"convergence_hold", "recovery_hold"}:
        raise PipelineError("No convergence or recovery circuit breaker is open")
    previous_phase = state["phase"]
    state["iteration_control"]["authorizations"].append(
        {
            "reason": args.reason,
            "phase": previous_phase,
            "recorded_at": utc_now(),
        }
    )
    state["iteration_control"]["status"] = "running"
    state["iteration_control"]["reason"] = args.reason
    if previous_phase == "convergence_hold":
        state["iteration_control"]["consecutive_product_changes"] = 0
        resume_phase = state["iteration_control"].get("resume_phase") or "convergence"
        state["iteration_control"]["resume_phase"] = None
    else:
        recovery = state.get("recovery")
        if recovery:
            recovery["cycles"] = 0
        resume_phase = "evidence_recovery"
    state["phase"] = resume_phase
    save_runtime(state_path, findings_path, state, findings)
    return cmd_status(args)


def cmd_authorize_budget(args: argparse.Namespace) -> int:
    _, state_path, findings_path, state, findings = load_runtime(args.project_root)
    budget = state["worker_budget"]
    if budget.get("status") != "checkpoint_required":
        raise PipelineError("No worker budget checkpoint is open")
    if args.additional_workers < 1:
        raise PipelineError("additional-workers must be positive")
    if args.additional_full_review_waves < 0:
        raise PipelineError("additional-full-review-waves cannot be negative")
    review_extension_required = "full_review_waves" in budget.get(
        "checkpoint_causes", []
    )
    if review_extension_required and args.additional_full_review_waves < 1:
        raise PipelineError(
            "The full-Review wave budget is exhausted; authorize at least one additional wave"
        )
    budget["authorizations"].append(
        {
            "reason": args.reason,
            "additional_workers": args.additional_workers,
            "additional_full_review_waves": args.additional_full_review_waves,
            "recorded_at": utc_now(),
        }
    )
    budget["max_workers"] += args.additional_workers
    budget["max_full_review_waves"] += args.additional_full_review_waves
    budget["status"] = "running"
    budget["reason"] = args.reason
    budget["checkpoint_causes"] = []
    save_runtime(state_path, findings_path, state, findings)
    return cmd_status(args)


def resolve_qa_gates(state: dict[str, Any], revision: str, resolution: str) -> None:
    for gate in state.get("gates", []):
        if (
            gate.get("status") == "open"
            and gate.get("phase") == "qa"
            and gate.get("revision") == revision
        ):
            gate["status"] = "resolved"
            gate["resolved_at"] = utc_now()
            gate["resolution"] = resolution


def cmd_qa_complete(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    require_worker_budget(state, args.worker_id)
    require_current_identity(
        state,
        args.revision,
        args.product_revision,
        args.support_revision,
        args.evidence_revision,
    )
    if state["phase"] != "qa":
        raise PipelineError("QA can complete only during the QA phase")
    blocked_capabilities = blocked_preflight_capabilities(state)
    if blocked_capabilities:
        raise PipelineError(
            "QA must not spawn before preflight capabilities are ready: "
            + ", ".join(sorted(blocked_capabilities))
        )
    non_qa_roles = {
        record["role"]
        for record in state["worker_budget"].get("records", [])
        if record.get("worker_id") == args.worker_id and record.get("role") != "runtime_qa"
    }
    if non_qa_roles:
        raise PipelineError("Runtime QA requires an identity independent of earlier pipeline roles")
    review = state.get("review", {})
    if review.get("status") not in PASSED_REVIEW_STATUSES or review.get("revision") != args.revision:
        raise PipelineError("QA requires two passed final reviews on the current revision")
    if any(run["run_id"] == args.run_id for run in state["qa_runs"]):
        raise PipelineError(f"QA run ID already recorded: {args.run_id}")
    report = resolve_report(root, state, args.report, "QA report")
    pending = args.pending_scenario or []
    if args.status != "pass" and not args.reason:
        raise PipelineError("Non-pass QA requires --reason")
    if args.status in QA_GATE_STATUSES and not pending:
        raise PipelineError(
            "Blocked or errored QA requires --reason and at least one --pending-scenario"
        )

    qa_product_findings = [
        item
        for item in findings["items"]
        if item.get("status") == "open"
        and item.get("source") == "qa"
        and item.get("kind") == "product"
        and item.get("severity") in BLOCKING_SEVERITIES
        and item.get("revision") == args.revision
    ]
    if args.status == "fail_product" and not qa_product_findings:
        raise PipelineError(
            "FAIL_PRODUCT requires an open critical or major QA product finding "
            "on this revision"
        )
    if args.status != "fail_product" and qa_product_findings:
        raise PipelineError("Open blocking QA product findings require status fail_product")
    if args.status == "pass" and pending:
        raise PipelineError("Passing QA cannot contain pending scenarios")
    effective_status = args.status
    qa_run = {
        "run_id": args.run_id,
        "worker_id": args.worker_id,
        "revision": args.revision,
        "product_revision": state["product_revision"],
        "support_revision": state["support_revision"],
        "evidence_revision": state["evidence_revision"],
        "status": effective_status,
        "report": report,
        "pending_scenarios": pending,
        "reason": args.reason,
        "recorded_at": utc_now(),
    }
    state["qa_runs"].append(qa_run)
    state["qa"] = {
        "status": effective_status,
        "revision": args.revision,
        "product_revision": state["product_revision"],
        "support_revision": state["support_revision"],
        "evidence_revision": state["evidence_revision"],
        "run_id": args.run_id,
        "worker_id": args.worker_id,
        "report": report,
        "pending_scenarios": pending,
        "reason": args.reason,
    }

    if effective_status == "pass":
        resolve_qa_gates(state, args.revision, "QA completed on the same revision")
        state["phase"] = "ready"
    elif effective_status == "fail_product":
        resolve_qa_gates(state, args.revision, "QA reproduced a product defect")
        state["engineer_clean"] = None
        state["review"] = empty_review_state(
            state["required_reviews"],
            args.revision,
            state["product_revision"],
            state["support_revision"],
            state["evidence_revision"],
        )
        state["phase"] = "engineering"
    else:
        state["gates"].append(
            {
                "id": f"qa:{args.run_id}",
                "phase": "qa",
                "category": effective_status,
                "revision": args.revision,
                "reason": args.reason,
                "pending_scenarios": pending,
                "report": report,
                "status": "open",
                "created_at": utc_now(),
            }
        )
        state["phase"] = "qa"

    record_worker(state, "runtime_qa", args.worker_id)
    if state["phase"] == "ready":
        state["worker_budget"]["status"] = "running"
        state["worker_budget"]["reason"] = None
    save_runtime(state_path, findings_path, state, findings)
    return cmd_status(args)


def readiness_reasons(state: dict[str, Any], findings: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    reasons.extend(source_drift(state))
    revision = state.get("revision")
    product_revision = state.get("product_revision")
    support_revision = state.get("support_revision")
    evidence_revision = state.get("evidence_revision")
    if not revision:
        reasons.append("no current revision")
    machine = state.get("machine_checks", {})
    if (
        machine.get("status") != "pass"
        or machine.get("revision") != revision
        or machine.get("product_revision") != product_revision
        or machine.get("support_revision") != support_revision
        or machine.get("evidence_revision") != evidence_revision
    ):
        reasons.append("machine checks have not passed on the current revision")
    if open_blocking(findings):
        reasons.append("critical or major findings remain unresolved")
    if any(
        item["status"] == "open" and item["severity"] == "minor"
        for item in findings["items"]
    ):
        reasons.append("minor findings require resolution or explicit acceptance")
    clean = state.get("engineer_clean")
    if not clean or clean.get("product_revision") != product_revision:
        reasons.append("parallel read-only convergence has not passed on the current product revision")
    review = state.get("review", {})
    if review.get("status") not in PASSED_REVIEW_STATUSES or review.get("revision") != revision:
        reasons.append("two final reviews have not passed on the current revision")
    elif review.get("status") == "passed" and len(review.get("runs", [])) != state.get("required_reviews", 2):
        reasons.append("final review evidence is incomplete")
    elif review.get("status") == "passed" and len({run["reviewer_id"] for run in review["runs"]}) != len(review["runs"]):
        reasons.append("final reviews are not from distinct reviewers")
    elif review.get("status") == "passed_recovery":
        recovery = state.get("recovery") or {}
        if (
            recovery.get("status") != "passed"
            or len(recovery.get("base_review_runs", [])) != state.get("required_reviews", 2)
            or not review.get("recovery_run")
        ):
            reasons.append("evidence recovery review chain is incomplete")
    elif review.get("status") == "passed_targeted":
        closure = state.get("closure_review") or {}
        if (
            closure.get("status") != "passed"
            or not closure.get("run")
            or len(closure.get("base_review_runs", [])) != state.get("required_reviews", 2)
        ):
            reasons.append("targeted product closure review chain is incomplete")
    preflight = state.get("preflight", {})
    if preflight.get("resource_budget_check") != "pass":
        reasons.append("preflight resource-budget proof has not passed")
    if blocked_preflight_capabilities(state):
        reasons.append("preflight runtime capabilities remain unavailable")
    qa = state.get("qa", {})
    if qa.get("status") != "pass" or qa.get("revision") != revision:
        reasons.append("feature-focused runtime QA has not passed on the current revision")
    if any(gate.get("status") == "open" for gate in state.get("gates", [])):
        reasons.append("an execution, environment, or user gate remains open")
    if state.get("phase") != "ready":
        reasons.append("pipeline phase is not ready")
    return reasons


def cmd_ready(args: argparse.Namespace) -> int:
    _, _, _, state, findings = load_runtime(args.project_root)
    reasons = readiness_reasons(state, findings)
    print(json.dumps({"ready": not reasons, "reasons": reasons}, ensure_ascii=False, indent=2))
    return 0 if not reasons else 1


def add_common_project_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-root", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init")
    add_common_project_root(init)
    init.add_argument("--feature", required=True)
    init.add_argument("--requirements", required=True)
    init.add_argument("--spec", required=True)
    init.add_argument("--slice", required=True)
    init.add_argument("--required-reviews", type=int, default=2)
    init.add_argument(
        "--max-consecutive-product-changes",
        "--max-automatic-product-changes",
        dest="max_consecutive_product_changes",
        type=int,
        default=DEFAULT_MAX_CONSECUTIVE_PRODUCT_CHANGES,
    )
    init.add_argument(
        "--required-convergence-audits",
        type=int,
        default=DEFAULT_REQUIRED_CONVERGENCE_AUDITS,
    )
    init.add_argument(
        "--max-convergence-waves", type=int, default=DEFAULT_MAX_CONVERGENCE_WAVES
    )
    init.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    init.add_argument(
        "--max-full-review-waves", type=int, default=DEFAULT_MAX_FULL_REVIEW_WAVES
    )
    init.set_defaults(handler=cmd_init)

    preflight = commands.add_parser("preflight-complete")
    add_common_project_root(preflight)
    preflight.add_argument("--run-id", required=True)
    preflight.add_argument("--resource-budget-check", choices=("pass", "fail"), required=True)
    preflight.add_argument("--capability", action="append")
    preflight.add_argument("--report", required=True)
    preflight.set_defaults(handler=cmd_preflight_complete)

    status = commands.add_parser("status")
    add_common_project_root(status)
    status.set_defaults(handler=cmd_status)

    revisions = commands.add_parser("compute-revisions")
    add_common_project_root(revisions)
    revisions.add_argument("--base-revision", required=True)
    revisions.add_argument("--product-file", action="append")
    revisions.add_argument("--support-file", action="append")
    revisions.add_argument("--evidence-file", action="append")
    revisions.add_argument("--output")
    revisions.set_defaults(handler=cmd_compute_revisions)

    engineer = commands.add_parser("engineer-complete")
    add_common_project_root(engineer)
    engineer.add_argument("--revision", required=True)
    engineer.add_argument("--product-revision")
    engineer.add_argument("--support-revision")
    engineer.add_argument("--evidence-revision")
    engineer.add_argument("--run-id", required=True)
    engineer.add_argument("--owner-id", required=True)
    engineer.add_argument("--machine-checks", choices=("pass", "fail"), required=True)
    engineer.add_argument("--report", required=True)
    engineer.add_argument("--coverage-manifest", required=True)
    engineer.add_argument(
        "--production-change-scope",
        choices=("none", "local", "architectural"),
        required=True,
    )
    engineer.add_argument("--production-files-changed", type=int, default=0)
    engineer.add_argument("--production-lines-changed", type=int, default=0)
    engineer.add_argument("--scope-approval")
    engineer.add_argument("--resolved-finding", action="append")
    engineer.add_argument(
        "--audit-complete",
        action="store_true",
        required=True,
        help="Assert that full discovery, batch remediation, checks, and scope resweep finished",
    )
    engineer.set_defaults(handler=cmd_engineer_complete)

    transfer_owner = commands.add_parser("transfer-engineering-owner")
    add_common_project_root(transfer_owner)
    transfer_owner.add_argument("--from-owner", required=True)
    transfer_owner.add_argument("--to-owner", required=True)
    transfer_owner.add_argument("--reason", required=True)
    transfer_owner.set_defaults(handler=cmd_transfer_engineering_owner)

    convergence_audit = commands.add_parser("convergence-audit-complete")
    add_common_project_root(convergence_audit)
    convergence_audit.add_argument("--revision", required=True)
    convergence_audit.add_argument("--product-revision")
    convergence_audit.add_argument("--support-revision")
    convergence_audit.add_argument("--evidence-revision")
    convergence_audit.add_argument("--run-id", required=True)
    convergence_audit.add_argument("--reviewer-id", required=True)
    convergence_audit.add_argument("--lens", choices=tuple(sorted(CONVERGENCE_LENSES)), required=True)
    convergence_audit.add_argument("--status", choices=("pass", "fail"), required=True)
    convergence_audit.add_argument("--report", required=True)
    convergence_audit.set_defaults(handler=cmd_convergence_audit_complete)

    convergence_finalize = commands.add_parser("convergence-finalize")
    add_common_project_root(convergence_finalize)
    convergence_finalize.add_argument("--revision", required=True)
    convergence_finalize.add_argument("--decision", choices=("pass", "rework"), required=True)
    convergence_finalize.add_argument("--report", required=True)
    convergence_finalize.set_defaults(handler=cmd_convergence_finalize)

    review = commands.add_parser("review-complete")
    add_common_project_root(review)
    review.add_argument("--revision", required=True)
    review.add_argument("--product-revision")
    review.add_argument("--support-revision")
    review.add_argument("--evidence-revision")
    review.add_argument("--run-id", required=True)
    review.add_argument("--reviewer-id", required=True)
    review.add_argument("--status", choices=("pass", "fail"), required=True)
    review.add_argument("--report", required=True)
    review.set_defaults(handler=cmd_review_complete)

    review_finalize = commands.add_parser("review-finalize")
    add_common_project_root(review_finalize)
    review_finalize.add_argument("--revision", required=True)
    review_finalize.add_argument("--decision", choices=("pass", "rework"), required=True)
    review_finalize.add_argument("--report", required=True)
    review_finalize.add_argument("--reason")
    review_finalize.add_argument(
        "--rework-scope",
        choices=("product", "support", "evidence", "recovery"),
        default="product",
    )
    review_finalize.add_argument(
        "--revalidation", choices=("targeted", "full"), default="targeted"
    )
    review_finalize.set_defaults(handler=cmd_review_finalize)

    closure_review = commands.add_parser("closure-review-complete")
    add_common_project_root(closure_review)
    closure_review.add_argument("--revision", required=True)
    closure_review.add_argument("--product-revision")
    closure_review.add_argument("--support-revision")
    closure_review.add_argument("--evidence-revision")
    closure_review.add_argument("--run-id", required=True)
    closure_review.add_argument("--reviewer-id", required=True)
    closure_review.add_argument("--status", choices=("pass", "fail"), required=True)
    closure_review.add_argument("--report", required=True)
    closure_review.set_defaults(handler=cmd_closure_review_complete)

    add_finding = commands.add_parser("add-finding")
    add_common_project_root(add_finding)
    add_finding.add_argument("--id", required=True)
    add_finding.add_argument(
        "--source", choices=("engineer", "convergence", "review", "qa"), required=True
    )
    add_finding.add_argument("--kind", choices=tuple(sorted(FINDING_KINDS)), default="product")
    add_finding.add_argument("--severity", choices=("critical", "major", "minor"), required=True)
    add_finding.add_argument("--title", required=True)
    add_finding.add_argument("--evidence", required=True)
    add_finding.add_argument("--revision", required=True)
    add_finding.set_defaults(handler=cmd_add_finding)

    resolve = commands.add_parser("resolve-finding")
    add_common_project_root(resolve)
    resolve.add_argument("--id", required=True)
    resolve.add_argument("--revision", required=True)
    resolve.set_defaults(handler=cmd_resolve_finding)

    accept = commands.add_parser("accept-finding")
    add_common_project_root(accept)
    accept.add_argument("--id", required=True)
    accept.add_argument("--reason", required=True)
    accept.add_argument("--approval-reference", required=True)
    accept.set_defaults(handler=cmd_accept_finding)

    recovery_start = commands.add_parser("start-evidence-recovery")
    add_common_project_root(recovery_start)
    recovery_start.add_argument("--revision", required=True)
    recovery_start.add_argument("--product-revision", required=True)
    recovery_start.add_argument("--support-revision", required=True)
    recovery_start.add_argument("--evidence-revision", required=True)
    recovery_start.add_argument("--finding-id", action="append", required=True)
    recovery_start.add_argument("--reason", required=True)
    recovery_start.set_defaults(handler=cmd_start_evidence_recovery)

    remediation = commands.add_parser(
        "recovery-remediation-complete",
        aliases=["evidence-remediation-complete"],
    )
    add_common_project_root(remediation)
    remediation.add_argument("--revision", required=True)
    remediation.add_argument("--product-revision", required=True)
    remediation.add_argument("--support-revision", required=True)
    remediation.add_argument("--evidence-revision", required=True)
    remediation.add_argument("--run-id", required=True)
    remediation.add_argument("--worker-id", required=True)
    remediation.add_argument("--machine-checks", choices=("pass", "fail"), required=True)
    remediation.add_argument("--report", required=True)
    remediation.add_argument("--coverage-manifest", required=True)
    remediation.add_argument("--resolved-finding", action="append", required=True)
    remediation.add_argument(
        "--production-change-scope",
        choices=("none", "local", "architectural"),
        default="none",
    )
    remediation.set_defaults(handler=cmd_evidence_remediation_complete)

    recovery_review = commands.add_parser("recovery-review-complete")
    add_common_project_root(recovery_review)
    recovery_review.add_argument("--revision", required=True)
    recovery_review.add_argument("--product-revision", required=True)
    recovery_review.add_argument("--support-revision", required=True)
    recovery_review.add_argument("--evidence-revision", required=True)
    recovery_review.add_argument("--run-id", required=True)
    recovery_review.add_argument("--reviewer-id", required=True)
    recovery_review.add_argument("--status", choices=("pass", "fail"), required=True)
    recovery_review.add_argument("--report", required=True)
    recovery_review.set_defaults(handler=cmd_recovery_review_complete)

    authorize = commands.add_parser("authorize-iteration")
    add_common_project_root(authorize)
    authorize.add_argument("--reason", required=True)
    authorize.set_defaults(handler=cmd_authorize_iteration)

    authorize_budget = commands.add_parser("authorize-budget")
    add_common_project_root(authorize_budget)
    authorize_budget.add_argument("--additional-workers", type=int, required=True)
    authorize_budget.add_argument("--additional-full-review-waves", type=int, default=0)
    authorize_budget.add_argument("--reason", required=True)
    authorize_budget.set_defaults(handler=cmd_authorize_budget)

    qa = commands.add_parser("qa-complete")
    add_common_project_root(qa)
    qa.add_argument("--revision", required=True)
    qa.add_argument("--product-revision")
    qa.add_argument("--support-revision")
    qa.add_argument("--evidence-revision")
    qa.add_argument("--run-id", required=True)
    qa.add_argument("--worker-id", required=True)
    qa.add_argument("--status", choices=tuple(sorted(QA_STATUSES)), required=True)
    qa.add_argument("--report", required=True)
    qa.add_argument("--reason")
    qa.add_argument("--pending-scenario", dest="pending_scenario", action="append")
    qa.set_defaults(handler=cmd_qa_complete)

    ready = commands.add_parser("ready")
    add_common_project_root(ready)
    ready.set_defaults(handler=cmd_ready)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except PipelineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
