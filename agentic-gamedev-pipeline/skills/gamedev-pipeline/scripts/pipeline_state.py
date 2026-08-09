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

try:
    from deferred_findings import (
        BACKLOG_PATH as DEFERRED_BACKLOG_PATH,
        BacklogError,
        candidate_requires_current_scope,
        deferred_id_from_reference,
        require_pipeline_backlog_scope,
    )
except ImportError:  # pragma: no cover - package-style imports used by some test runners
    from .deferred_findings import (
        BACKLOG_PATH as DEFERRED_BACKLOG_PATH,
        BacklogError,
        candidate_requires_current_scope,
        deferred_id_from_reference,
        require_pipeline_backlog_scope,
    )


STATE_DIR = ".agentic-pipeline"
SCHEMA_VERSION = 8
CONTRACT_VERSION = "2026-08-09-bounded-review-qa-v1"
DEVELOPMENT_PLAN_STATE = Path(STATE_DIR) / "development-plan-state.json"
FINDING_KINDS = {"product", "evidence", "support", "hardening"}
BLOCKING_SCOPE_RELATIONS = {
    "candidate_introduced",
    "current_feature_path",
    "required_shared_contract",
}
SCOPE_RELATIONS = BLOCKING_SCOPE_RELATIONS | {
    "preexisting_adjacent",
    "out_of_scope",
}
BLOCKING_REACHABILITY = {"normal", "supported_failure_path"}
PRODUCTION_REACHABILITY = BLOCKING_REACHABILITY | {
    "theoretical",
    "unsupported_configuration",
    "unknown",
}
PASSED_REVIEW_STATUSES = {"passed", "passed_targeted", "passed_recovery"}
DEFAULT_MAX_CONSECUTIVE_PRODUCT_CHANGES = 2
DEFAULT_REQUIRED_CONVERGENCE_AUDITS = 3
DEFAULT_MAX_CONVERGENCE_WAVES = 2
DEFAULT_MAX_WORKERS = 14
DEFAULT_MAX_FULL_REVIEW_WAVES = 2
DEFAULT_MAX_FULL_CONVERGENCE_WAVES_PER_SLICE = 2
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
RESEARCH_TERMINAL_STATUSES = {"complete", "not_required"}
FULL_WAVE_TRIGGERS = {
    "architecture",
    "lifecycle",
    "ownership",
    "public_contract",
    "expanded_shared_touchpoint",
    "high_risk_surface",
}
QA_CAPABILITY_NAMES = {
    "studio-editor-sync",
    "single-play",
    "test-server-two-clients",
    "window-control-path",
    "logging-screenshots",
    "persistence-datastore",
    "publication-place-topology",
    "config-credentials",
}
QA_CAPABILITY_BLOCKING_STATUSES = {
    "blocked_user",
    "blocked_environment",
    "error_test",
}


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


def section_content(text: str, heading: str, level: int = 3) -> str:
    prefix = "#" * level
    match = re.search(
        rf"(?ms)^{re.escape(prefix)} {re.escape(heading)}\r?\n(.*?)(?=^{re.escape(prefix)} |\Z)",
        text,
    )
    return match.group(1).strip() if match else ""


def comma_values(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def scope_path(value: str, label: str) -> str:
    normalized = value.replace("\\", "/").strip()
    if (
        not normalized
        or normalized.startswith("/")
        or re.match(r"^[A-Za-z]:", normalized)
        or ".." in Path(normalized).parts
        or ("*" in normalized and not normalized.endswith("/**"))
    ):
        raise PipelineError(f"Invalid {label} repository-relative path: {value!r}")
    return normalized


def parse_slice_scope(slice_id: str, content: str) -> dict[str, Any]:
    scope = section_content(content, "Scope Contract")
    scalar: dict[str, str] = {}
    for key, value in re.findall(r"(?m)^\s*-\s*([a-z_]+):\s*(.+?)\s*$", scope):
        if key != "shared_touchpoint":
            scalar[key] = value.strip()
    required = {
        "acceptance_ids",
        "editable_paths",
        "excluded_components",
        "excluded_paths",
        "max_product_files",
        "max_product_lines_changed",
        "verification_scope",
        "scope_baseline_revision",
    }
    missing = sorted(key for key in required if not scalar.get(key))
    if missing:
        raise PipelineError(f"{slice_id} Scope Contract lacks: {', '.join(missing)}")
    acceptance_ids = comma_values(scalar["acceptance_ids"])
    if not acceptance_ids or any(
        not re.fullmatch(r"PRD-AC-[A-Za-z0-9-]+", item) for item in acceptance_ids
    ):
        raise PipelineError(f"{slice_id} acceptance_ids must contain only PRD-AC-* IDs")
    editable_paths = [
        scope_path(item, "editable") for item in comma_values(scalar["editable_paths"])
    ]
    excluded_paths = [
        scope_path(item, "excluded") for item in comma_values(scalar["excluded_paths"])
    ]
    touchpoints: list[dict[str, Any]] = []
    seen_touchpoints: set[str] = set()
    seen_touchpoint_paths: set[str] = set()
    for touchpoint_id, fields_text in re.findall(
        r"(?m)^\s*-\s*shared_touchpoint:\s*(TP-\d{3})\s*\|\s*(.+)$", scope
    ):
        if touchpoint_id in seen_touchpoints:
            raise PipelineError(f"{slice_id} has duplicate touchpoint {touchpoint_id}")
        seen_touchpoints.add(touchpoint_id)
        fields = {
            part.split("=", 1)[0].strip(): part.split("=", 1)[1].strip()
            for part in fields_text.split("|")
            if "=" in part
        }
        missing_fields = sorted(
            key
            for key in {"path", "symbols", "allowed_change", "forbidden_change"}
            if not fields.get(key)
        )
        if missing_fields:
            raise PipelineError(
                f"{slice_id} {touchpoint_id} lacks: {', '.join(missing_fields)}"
            )
        touchpoint_path = scope_path(fields["path"], "shared touchpoint")
        if touchpoint_path in seen_touchpoint_paths:
            raise PipelineError(
                f"{slice_id} has multiple shared_touchpoint rows for {touchpoint_path}; "
                "use one row with the complete symbol allowlist"
            )
        seen_touchpoint_paths.add(touchpoint_path)
        touchpoints.append(
            {
                "id": touchpoint_id,
                "path": touchpoint_path,
                "symbols": comma_values(fields["symbols"]),
                "allowed_change": fields["allowed_change"],
                "forbidden_change": fields["forbidden_change"],
            }
        )
    if not touchpoints:
        raise PipelineError(f"{slice_id} requires a structured shared_touchpoint")
    try:
        max_files = int(scalar["max_product_files"])
        max_lines = int(scalar["max_product_lines_changed"])
    except ValueError as exc:
        raise PipelineError(f"{slice_id} scope budgets must be integers") from exc
    if max_files < 1 or max_lines < 1:
        raise PipelineError(f"{slice_id} scope budgets must be positive")
    return {
        "acceptance_ids": acceptance_ids,
        "editable_paths": editable_paths,
        "shared_touchpoints": touchpoints,
        "excluded_components": comma_values(scalar["excluded_components"]),
        "excluded_paths": excluded_paths,
        "max_product_files": max_files,
        "max_product_lines_changed": max_lines,
        "verification_scope": scalar["verification_scope"],
        "scope_baseline_revision": scalar["scope_baseline_revision"],
    }


def plan_slice_blocks(text: str) -> list[dict[str, Any]]:
    parts = text.split("---", 2)
    body = parts[2] if len(parts) == 3 else text
    pattern = re.compile(r"(?ms)^## Slice (SLICE-\d{3})\r?\n(.*?)(?=^## |\Z)")
    slices: list[dict[str, Any]] = []
    for slice_id, content in pattern.findall(body):
        dependency_match = re.search(
            r"(?ms)^### Dependencies\r?\n(.*?)(?=^### |\Z)", content
        )
        dependencies = re.findall(
            r"\bSLICE-\d{3}\b", dependency_match.group(1) if dependency_match else ""
        )
        requirements = section_content(content, "Requirements")
        requirement_ids = sorted(set(re.findall(r"\bPRD-REQ-[A-Za-z0-9-]+\b", requirements)))
        declared_acceptance_ids = set(
            re.findall(r"\bPRD-AC-[A-Za-z0-9-]+\b", requirements)
        )
        scope_contract = parse_slice_scope(slice_id, content)
        if not set(scope_contract["acceptance_ids"]).issubset(declared_acceptance_ids):
            raise PipelineError(
                f"{slice_id} scope acceptance_ids must also appear in its Requirements section"
            )
        slices.append(
            {
                "id": slice_id,
                "dependencies": sorted(set(dependencies)),
                "requirement_ids": requirement_ids,
                "scope_contract": scope_contract,
            }
        )
    return slices


def require_development_plan(
    root: Path,
    feature: str,
    requirements: Path,
    spec: Path,
    supplied_plan: str | None,
    supplied_sha256: str | None,
) -> dict[str, Any]:
    canonical = (root / "docs" / "features" / feature / "development-plan.md").resolve()
    plan = resolve_project_file(
        root,
        supplied_plan or canonical.relative_to(root).as_posix(),
        "Approved development plan",
    )
    if plan != canonical:
        raise PipelineError(f"Approved development plan must be stored at {canonical}")
    plan_meta = parse_frontmatter(plan, "Development plan")
    if plan_meta.get("document_type") != "development-plan":
        raise PipelineError("development-plan.md document_type must be development-plan")
    if plan_meta.get("status") != "approved":
        raise PipelineError("development-plan.md must have status: approved")
    if plan_meta.get("feature") != feature:
        raise PipelineError("development-plan.md feature does not match the pipeline feature")
    if plan_meta.get("writer_strategy") != "sequential":
        raise PipelineError("development-plan.md must declare writer_strategy: sequential")
    mode = plan_meta.get("mode")
    if mode not in {"single_owner", "sequential_slices"}:
        raise PipelineError("development-plan.md mode must be single_owner or sequential_slices")
    expected_trace = {
        "source_prd_path": requirements.relative_to(root).as_posix(),
        "source_prd_revision": parse_frontmatter(requirements, "Product requirements")["revision"],
        "source_prd_sha256": file_sha256(requirements),
        "source_spec_path": spec.relative_to(root).as_posix(),
        "source_spec_revision": parse_frontmatter(spec, "Technical specification").get("revision"),
        "source_spec_sha256": file_sha256(spec),
    }
    for field, expected in expected_trace.items():
        if plan_meta.get(field) != expected:
            raise PipelineError(
                f"development-plan.md has stale {field}: expected {expected!r}, "
                f"got {plan_meta.get(field)!r}"
            )
    approved_hash = file_sha256(plan)
    if supplied_sha256 and supplied_sha256 != approved_hash:
        raise PipelineError("Supplied development-plan SHA does not match current plan bytes")
    planning_state = read_json(root / DEVELOPMENT_PLAN_STATE)
    approval = planning_state.get("approval") or {}
    if (
        planning_state.get("schema_version") != 1
        or planning_state.get("feature") != feature
        or planning_state.get("status") != "approved"
        or planning_state.get("plan_path") != plan.relative_to(root).as_posix()
        or approval.get("approved_sha256") != approved_hash
        or planning_state.get("prd", {}).get("sha256") != file_sha256(requirements)
        or planning_state.get("specification", {}).get("sha256") != file_sha256(spec)
    ):
        raise PipelineError(
            "development-plan-state.json does not prove approval of the exact current plan/PRD/spec"
        )
    slices = plan_slice_blocks(plan.read_text(encoding="utf-8"))
    slice_ids = [item["id"] for item in slices]
    if mode == "single_owner" and len(slices) != 1:
        raise PipelineError("single_owner development plan must contain exactly one slice")
    if mode == "sequential_slices" and len(slices) < 2:
        raise PipelineError("sequential_slices development plan must contain at least two slices")
    expected_ids = [f"SLICE-{index:03d}" for index in range(1, len(slices) + 1)]
    if slice_ids != expected_ids:
        raise PipelineError("development plan slice IDs must be ordered and contiguous")
    for index, item in enumerate(slices):
        invalid = set(item["dependencies"]) - set(slice_ids[:index])
        if invalid:
            raise PipelineError(
                f"{item['id']} contains non-earlier dependencies: {', '.join(sorted(invalid))}"
            )
    return {
        "path": str(plan),
        "sha256": approved_hash,
        "mode": mode,
        "slices": slices,
        "approval": approval,
    }


def ensure_test_artifact_layout(root: Path, feature: str) -> Path:
    tests_root = (root / "tests" / feature).resolve()
    for child in ("research", "verification", "reviews", "qa"):
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
    plan_path = Path(state.get("development_plan_path", ""))
    if not plan_path.is_file():
        drift.append("development plan file is missing")
    elif file_sha256(plan_path) != state.get("development_plan_sha256"):
        drift.append("development plan file changed after pipeline initialization")
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


def empty_scope_churn() -> dict[str, Any]:
    return {
        "passes": 0,
        "product_files_changed": 0,
        "product_lines_changed": 0,
        "unique_product_files": [],
        "touchpoint_ids": [],
    }


def new_slice_state(
    slice_id: str,
    dependencies: list[str],
    requirement_ids: list[str] | None = None,
    scope_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": slice_id,
        "dependencies": dependencies,
        "status": "pending",
        "base_revision": None,
        "base_product_revision": None,
        "base_support_revision": None,
        "base_evidence_revision": None,
        "result_revision": None,
        "result_product_revision": None,
        "result_support_revision": None,
        "result_evidence_revision": None,
        "owner_id": None,
        "remediation_returns_by_owner": {},
        "handoff_manifests": [],
        "requirement_ids": requirement_ids or [],
        "scope_contract": scope_contract,
        "scope_churn": empty_scope_churn(),
        "scope_history": [],
        "scope_pre_edit_check": None,
        "full_convergence_waves": 0,
        "max_full_convergence_waves": DEFAULT_MAX_FULL_CONVERGENCE_WAVES_PER_SLICE,
        "research": {
            "status": "pending",
            "base_revision": None,
            "bundles": [],
            "reason": None,
            "completed_at": None,
        },
        "sealed_at": None,
    }


def active_slice_state(state: dict[str, Any]) -> dict[str, Any] | None:
    slice_id = state.get("active_slice")
    if not slice_id:
        return None
    return state.get("slices", {}).get(slice_id)


def set_active_slice(
    state: dict[str, Any],
    slice_id: str,
    *,
    base_revision: str,
    base_product_revision: str,
    base_support_revision: str,
    base_evidence_revision: str,
) -> None:
    item = state["slices"][slice_id]
    item["status"] = "active"
    item["base_revision"] = base_revision
    item["base_product_revision"] = base_product_revision
    item["base_support_revision"] = base_support_revision
    item["base_evidence_revision"] = base_evidence_revision
    research = item.setdefault(
        "research",
        {"status": "pending", "bundles": [], "reason": None, "completed_at": None},
    )
    research["base_revision"] = base_revision
    state["active_slice"] = slice_id
    state["slice_id"] = slice_id
    owner = state.get("owner_by_slice", {}).get(slice_id)
    state["engineering_owner_id"] = owner


def all_slices_sealed(state: dict[str, Any]) -> bool:
    return bool(state.get("ordered_slices")) and all(
        state["slices"][slice_id].get("status") == "sealed"
        for slice_id in state["ordered_slices"]
    )


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
    state.setdefault("development_plan_path", None)
    state.setdefault("development_plan_sha256", None)
    state.setdefault("development_mode", "single_owner")
    state.setdefault("ordered_slices", [state.get("slice_id", "SLICE-001")])
    state.setdefault("active_slice", state.get("slice_id"))
    state.setdefault("owner_by_slice", {})
    state.setdefault("integration_owner", state.get("engineering_owner_id"))
    state.setdefault("handoff_manifests", [])
    state.setdefault("remediation_queue", [])
    state.setdefault("active_remediation_batch", None)
    state.setdefault("execution_stage", "feature_validation")
    scope_guard = state.setdefault(
        "scope_guard",
        {
            "status": "pending",
            "hold": None,
            "history": [],
            "scope_churn": empty_scope_churn(),
            "rebaseline_history": [],
        },
    )
    scope_guard.setdefault("status", "pending")
    scope_guard.setdefault("hold", None)
    scope_guard.setdefault("history", [])
    scope_guard.setdefault("scope_churn", empty_scope_churn())
    scope_guard.setdefault("rebaseline_history", [])
    if "slices" not in state:
        legacy_slice = state.get("slice_id", "SLICE-001")
        state["slices"] = {legacy_slice: new_slice_state(legacy_slice, [])}
    for slice_item in state["slices"].values():
        slice_item.setdefault("requirement_ids", [])
        slice_item.setdefault("scope_contract", None)
        slice_item.setdefault("scope_churn", empty_scope_churn())
        slice_item.setdefault("scope_history", [])
        slice_item.setdefault("scope_pre_edit_check", None)
        slice_item.setdefault("full_convergence_waves", 0)
        slice_item.setdefault(
            "max_full_convergence_waves",
            DEFAULT_MAX_FULL_CONVERGENCE_WAVES_PER_SLICE,
        )
        slice_item.setdefault(
            "research",
            {
                "status": "pending",
                "base_revision": slice_item.get("base_revision"),
                "bundles": [],
                "reason": None,
                "completed_at": None,
            },
        )
    state.setdefault("product_revalidation", None)
    state.setdefault("preflight", empty_preflight_state())
    state.setdefault(
        "convergence",
        empty_convergence_state(
            state.get("required_convergence_audits", DEFAULT_REQUIRED_CONVERGENCE_AUDITS)
        ),
    )
    state.setdefault("closure_review", None)
    state.setdefault("component_review_credits", [])
    state.setdefault("qa_capability", empty_qa_capability_state())
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
        item.setdefault("finding_kind", "product")
        item.setdefault("origin_slice", state.get("active_slice"))
        item.setdefault("remediation_route", item.get("origin_slice"))
    state.setdefault("finding_triage", None)


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
        if item["status"] == "open" and item.get("blocking") is True
    ]


def parse_explicit_bool(value: str, label: str) -> bool:
    if value not in {"true", "false"}:
        raise PipelineError(f"{label} must be true or false")
    return value == "true"


def planned_acceptance_ids(state: dict[str, Any]) -> set[str]:
    return {
        acceptance_id
        for slice_item in state.get("slices", {}).values()
        for acceptance_id in (slice_item.get("scope_contract") or {}).get(
            "acceptance_ids", []
        )
    }


def finding_is_blocking(item: dict[str, Any]) -> bool:
    return (
        item.get("scope_relation") in BLOCKING_SCOPE_RELATIONS
        and item.get("production_reachability") in BLOCKING_REACHABILITY
        and (
            bool(item.get("blocks_acceptance_ids"))
            or item.get("violates_required_invariant") is True
        )
    )


def validate_finding_dimensions(state: dict[str, Any], item: dict[str, Any]) -> None:
    acceptance_ids = item["blocks_acceptance_ids"]
    unknown_acceptance = sorted(set(acceptance_ids) - planned_acceptance_ids(state))
    if unknown_acceptance:
        raise PipelineError(
            "Finding blocks acceptance IDs outside the approved plan: "
            + ", ".join(unknown_acceptance)
        )
    if item["scope_relation"] == "candidate_introduced" and not item[
        "introduced_by_candidate"
    ]:
        raise PipelineError(
            "scope_relation candidate_introduced requires introduced_by_candidate=true"
        )
    if item["scope_relation"] == "preexisting_adjacent" and item[
        "introduced_by_candidate"
    ]:
        raise PipelineError(
            "A preexisting_adjacent finding cannot be introduced_by_candidate"
        )
    invariant_evidence = item.get("required_invariant_evidence")
    if item["violates_required_invariant"] and not invariant_evidence:
        raise PipelineError(
            "violates_required_invariant=true requires --required-invariant-evidence"
        )
    if not item["violates_required_invariant"] and invariant_evidence:
        raise PipelineError(
            "--required-invariant-evidence requires violates_required_invariant=true"
        )
    if item["severity"] == "critical" and not (
        acceptance_ids or item["violates_required_invariant"]
    ):
        raise PipelineError(
            "Critical findings require a blocked approved acceptance ID or required invariant evidence"
        )
    if item["severity"] == "minor" and (
        acceptance_ids or item["violates_required_invariant"]
    ):
        raise PipelineError(
            "Minor findings cannot claim a blocked acceptance criterion or required invariant; "
            "classify the impact accurately before controller blocking is derived"
        )
    if item["finding_kind"] in {"support", "hardening"} and (
        acceptance_ids or item["violates_required_invariant"]
    ):
        raise PipelineError(
            "Support and hardening findings cannot claim a blocked acceptance criterion or required invariant"
        )
    evidence_major_proof = (
        item.get("mandatory_core_acceptance_evidence_missing") is True
        and item.get("test_can_miss_product_defect") is True
        and bool(acceptance_ids)
    )
    if item["finding_kind"] == "evidence" and item["severity"] == "major":
        if not evidence_major_proof:
            raise PipelineError(
                "Evidence Major requires a blocked core acceptance ID, no other mandatory proof, "
                "and evidence that the current test can miss a real product defect"
            )
    elif item.get("mandatory_core_acceptance_evidence_missing") or item.get(
        "test_can_miss_product_defect"
    ):
        raise PipelineError(
            "Evidence-Major proof flags are valid only for an evidence Major finding"
        )
    if item["finding_kind"] == "evidence" and item["severity"] == "critical":
        raise PipelineError(
            "Missing evidence is not Critical by itself; record the evidenced product or invariant defect"
        )
    item["blocking"] = finding_is_blocking(item)
    deferred_reference = item.get("deferred_reference")
    if deferred_reference:
        if item["blocking"] or item["production_reachability"] == "unknown":
            raise PipelineError(
                "deferred_pending is valid only for a classified nonblocking finding"
            )
        if item["scope_relation"] not in {"preexisting_adjacent", "out_of_scope"}:
            raise PipelineError(
                "--deferred-reference requires preexisting_adjacent or out_of_scope scope_relation"
            )
        if deferred_id_from_reference(deferred_reference) is None:
            raise PipelineError(
                "--deferred-reference must be a DEF-* ID or "
                "docs/engineering/deferred-findings.json#DEF-* reference"
            )
        if candidate_requires_current_scope(item):
            raise PipelineError(
                "A candidate that was introduced/worsened by this change, is reached by the "
                "feature path or changed contract, blocks an acceptance criterion/invariant, "
                "or has a safety impact must return to current scope"
            )
        item["disposition"] = "deferred_pending"
    elif item["production_reachability"] == "unknown":
        item["disposition"] = "triage_required"
    else:
        item["disposition"] = "active"


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
    slice_ids: list[str] | None = None,
    trigger: str = "initial_implementation",
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
        "slice_ids": list(slice_ids or []),
        "trigger": trigger,
    }


def require_full_convergence_budget(
    state: dict[str, Any], slice_ids: list[str]
) -> None:
    exhausted = [
        slice_id
        for slice_id in slice_ids
        if state["slices"][slice_id].get("full_convergence_waves", 0)
        >= state["slices"][slice_id].get(
            "max_full_convergence_waves",
            DEFAULT_MAX_FULL_CONVERGENCE_WAVES_PER_SLICE,
        )
    ]
    if exhausted:
        raise PipelineError(
            "Full convergence limit exhausted for "
            + ", ".join(exhausted)
            + "; use targeted closure, defer a nonblocking issue, or obtain a "
            "user-approved replan/scope rebaseline"
        )


def count_full_convergence_wave(state: dict[str, Any]) -> None:
    convergence = state["convergence"]
    if convergence.get("counted"):
        return
    slice_ids = convergence.get("slice_ids") or list(state.get("ordered_slices", []))
    require_full_convergence_budget(state, slice_ids)
    for slice_id in slice_ids:
        state["slices"][slice_id]["full_convergence_waves"] = (
            state["slices"][slice_id].get("full_convergence_waves", 0) + 1
        )
    convergence["counted"] = True


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
        "capability_probe_id": None,
        "minimum_resume_actions": {},
    }


def empty_qa_capability_state() -> dict[str, Any]:
    return {
        "status": "pending",
        "revision": None,
        "probe_id": None,
        "capabilities": {},
        "minimum_resume_actions": {},
        "report": None,
        "probes": [],
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
    state["qa_capability"] = empty_qa_capability_state()
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


def review_credit_id(
    component: str,
    product_hash: str,
    contract_hash: str,
    lenses: list[str],
    revision: str,
) -> str:
    payload = "\n".join(
        (component, product_hash, contract_hash, ",".join(sorted(lenses)), revision)
    )
    return "RC-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16].upper()


def resolve_review_credit_manifest(
    root: Path,
    state: dict[str, Any],
    supplied: str,
    *,
    reviewer_id: str,
    review_mode: str,
    expected_lens: str | None = None,
    require_composition_audit: bool = False,
) -> tuple[str, list[str]]:
    path = resolve_report(root, state, supplied, "Component Review credit manifest")
    manifest = read_json(Path(path))
    for field, expected in {
        "schema_version": 1,
        "revision": state.get("revision"),
        "reviewer_id": reviewer_id,
        "review_mode": review_mode,
    }.items():
        if manifest.get(field) != expected:
            raise PipelineError(
                f"Review credit manifest {field} mismatch: expected {expected!r}, "
                f"got {manifest.get(field)!r}"
            )
    if require_composition_audit:
        if manifest.get("composition_audit") is not True:
            raise PipelineError(
                "Final whole-feature Review must audit cross-slice composition"
            )
        if not isinstance(manifest.get("new_boundaries_audited"), list):
            raise PipelineError(
                "Final Review credit manifest must record new_boundaries_audited"
            )
    components = manifest.get("components")
    if not isinstance(components, list) or not components:
        raise PipelineError("Review credit manifest must contain component credits")
    existing = state.setdefault("component_review_credits", [])
    planned: list[dict[str, Any]] = []
    ids: list[str] = []
    seen_keys: set[tuple[str, str, str, tuple[str, ...]]] = set()
    for item in components:
        if not isinstance(item, dict):
            raise PipelineError("Every component Review credit must be an object")
        component = str(item.get("component", "")).strip()
        product_hash = str(item.get("product_hash", "")).strip()
        contract_hash = str(item.get("contract_hash", "")).strip()
        lenses = require_string_list(
            item.get("lenses"), "Component Review credit lenses", allow_empty=False
        )
        lenses = sorted(set(lenses))
        if not component or not product_hash or not contract_hash:
            raise PipelineError(
                "Component Review credit requires component, product_hash, and contract_hash"
            )
        if expected_lens and expected_lens not in lenses:
            raise PipelineError(
                f"Convergence credit for {component} must include lens {expected_lens}"
            )
        key = (component, product_hash, contract_hash, tuple(lenses))
        if key in seen_keys:
            raise PipelineError(f"Duplicate component Review credit: {component}")
        seen_keys.add(key)
        mode = item.get("mode")
        equivalent = next(
            (
                credit
                for credit in reversed(existing)
                if credit.get("valid") is True
                and credit.get("component") == component
                and credit.get("product_hash") == product_hash
                and credit.get("contract_hash") == contract_hash
                and credit.get("lenses") == lenses
            ),
            None,
        )
        if mode == "fresh":
            if equivalent:
                raise PipelineError(
                    f"Unchanged component {component} already has valid Review credit "
                    f"{equivalent['id']}; reuse it instead of fully rereading"
                )
        elif mode == "reused":
            source_id = item.get("source_credit_id")
            if not equivalent or equivalent.get("id") != source_id:
                raise PipelineError(
                    f"Reused Review credit for {component} does not match a valid exact "
                    "component product/contract/lens credit"
                )
            ids.append(equivalent["id"])
            continue
        else:
            raise PipelineError("Component Review credit mode must be fresh or reused")
        credit_id = review_credit_id(
            component, product_hash, contract_hash, lenses, state["revision"]
        )
        planned.append(
            {
                "id": credit_id,
                "component": component,
                "product_hash": product_hash,
                "contract_hash": contract_hash,
                "lenses": lenses,
                "review_revision": state["revision"],
                "reviewer_id": reviewer_id,
                "review_mode": review_mode,
                "source_credit_id": None,
                "valid": True,
                "manifest": path,
                "recorded_at": utc_now(),
            }
        )
        ids.append(credit_id)
    for new_credit in planned:
        for old_credit in existing:
            if (
                old_credit.get("valid") is True
                and old_credit.get("component") == new_credit["component"]
                and old_credit.get("lenses") == new_credit["lenses"]
                and (
                    old_credit.get("product_hash") != new_credit["product_hash"]
                    or old_credit.get("contract_hash") != new_credit["contract_hash"]
                )
            ):
                old_credit["valid"] = False
                old_credit["invalidated_at"] = utc_now()
                old_credit["invalidation_reason"] = (
                    "component_product_hash_drift"
                    if old_credit.get("product_hash") != new_credit["product_hash"]
                    else "component_contract_hash_drift"
                )
        existing.append(new_credit)
    return path, ids


def canonical_json_sha256(value: dict[str, Any]) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def require_string_list(value: Any, label: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise PipelineError(f"{label} must be a list of non-empty strings")
    if not allow_empty and not value:
        raise PipelineError(f"{label} must not be empty")
    return value


def normalize_research_path(value: str, label: str) -> str:
    normalized = value.replace("\\", "/").strip()
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        raise PipelineError(f"{label} must be a safe repo-relative path")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if (
        not normalized
        or ".." in normalized.split("/")
    ):
        raise PipelineError(f"{label} must be a safe repo-relative path")
    return normalized.rstrip("/")


def research_path_is_allowed(path: str, allowed_paths: list[str]) -> bool:
    normalized = normalize_research_path(path, "Research path")
    return any(
        normalized == allowed or normalized.startswith(allowed + "/")
        for allowed in allowed_paths
    )


def resolve_research_bundle(
    root: Path,
    state: dict[str, Any],
    supplied: str,
    *,
    slice_id: str,
    base_revision: str,
) -> dict[str, Any]:
    bundle_path = Path(resolve_report(root, state, supplied, "Research bundle"))
    research_root = (Path(state["tests_path"]) / "research").resolve()
    try:
        bundle_path.relative_to(research_root)
    except ValueError as exc:
        raise PipelineError(
            f"Research bundle must be stored under {research_root}"
        ) from exc
    bundle = read_json(bundle_path)
    if bundle.get("schema_version") != 1:
        raise PipelineError("Research bundle must use schema_version 1")
    brief = bundle.get("brief")
    result = bundle.get("result")
    if not isinstance(brief, dict) or not isinstance(result, dict):
        raise PipelineError("Research bundle must contain brief and result objects")

    required_brief_strings = (
        "brief_id",
        "question",
        "slice_id",
        "base_revision",
        "stop_condition",
        "output_path",
    )
    for field in required_brief_strings:
        if not isinstance(brief.get(field), str) or not brief[field].strip():
            raise PipelineError(f"Research brief {field} must be a non-empty string")
    if brief["slice_id"] != slice_id:
        raise PipelineError("Research brief slice_id does not match the active slice")
    if brief["base_revision"] != base_revision:
        raise PipelineError("Research brief base_revision does not match the active slice")
    requirement_ids = require_string_list(
        brief.get("requirement_ids"), "Research brief requirement_ids", allow_empty=False
    )
    if any(not re.fullmatch(r"(?:REQ|AC)-[A-Za-z0-9._-]+", item) for item in requirement_ids):
        raise PipelineError("Research brief requirement_ids must contain only REQ-* or AC-* IDs")
    seed_paths = require_string_list(
        brief.get("seed_paths"), "Research brief seed_paths", allow_empty=False
    )
    allowed_paths = require_string_list(
        brief.get("allowed_paths"), "Research brief allowed_paths", allow_empty=False
    )
    allowed_symbols = require_string_list(
        brief.get("allowed_symbols"),
        "Research brief allowed_symbols",
        allow_empty=False,
    )
    require_string_list(brief.get("exclusions"), "Research brief exclusions", allow_empty=False)
    require_string_list(
        brief.get("requested_evidence"),
        "Research brief requested_evidence",
        allow_empty=False,
    )
    normalized_allowed_paths = [
        normalize_research_path(item, "Research brief allowed_paths")
        for item in allowed_paths
    ]
    for seed in seed_paths:
        if not research_path_is_allowed(seed, normalized_allowed_paths):
            raise PipelineError("Every research seed_path must stay within allowed_paths")
    max_files = brief.get("max_files")
    if not isinstance(max_files, int) or isinstance(max_files, bool) or max_files < 1:
        raise PipelineError("Research brief max_files must be a positive integer")
    output_path = Path(brief["output_path"])
    if not output_path.is_absolute():
        output_path = root / output_path
    if output_path.resolve() != bundle_path:
        raise PipelineError("Research brief output_path must identify its bundle file")

    required_result_strings = (
        "brief_id",
        "researcher_id",
        "base_revision",
        "brief_sha256",
        "status",
    )
    for field in required_result_strings:
        if not isinstance(result.get(field), str) or not result[field].strip():
            raise PipelineError(f"Research result {field} must be a non-empty string")
    if result["status"] not in {"complete", "limit_reached"}:
        raise PipelineError("Research result status must be complete or limit_reached")
    if result["brief_id"] != brief["brief_id"]:
        raise PipelineError("Research result brief_id does not match its brief")
    if result["base_revision"] != base_revision:
        raise PipelineError("Research result base_revision does not match the active slice")
    if result["brief_sha256"] != canonical_json_sha256(brief):
        raise PipelineError("Research result brief_sha256 does not match canonical brief bytes")
    inspected_paths = require_string_list(
        result.get("inspected_paths"), "Research result inspected_paths"
    )
    inspected_symbols = require_string_list(
        result.get("inspected_symbols"), "Research result inspected_symbols"
    )
    if any(symbol not in allowed_symbols for symbol in inspected_symbols):
        raise PipelineError("Research result inspected a symbol outside allowed_symbols")
    for field in (
        "owners_contracts_precedents",
        "lifecycle_integration_risks",
        "minimal_edit_reuse_points",
        "unresolved_questions",
        "out_of_brief_pointers",
    ):
        require_string_list(result.get(field), f"Research result {field}")
    if len(set(inspected_paths)) > max_files:
        raise PipelineError("Research result exceeds brief max_files")
    for inspected in inspected_paths:
        if not research_path_is_allowed(inspected, normalized_allowed_paths):
            raise PipelineError("Research result inspected a path outside allowed_paths")
    if any(key in result for key in ("raw", "raw_dump", "raw_logs", "source_dump")):
        raise PipelineError("Research result must not contain raw dumps or logs")
    return {
        "brief_id": brief["brief_id"],
        "researcher_id": result["researcher_id"],
        "status": result["status"],
        "base_revision": base_revision,
        "brief_sha256": result["brief_sha256"],
        "bundle_sha256": file_sha256(bundle_path),
        "path": str(bundle_path),
        "seed_paths": seed_paths,
    }


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


def resolve_handoff_manifest(
    root: Path,
    state: dict[str, Any],
    supplied: str,
    *,
    slice_id: str,
    owner_id: str,
    base_revision: str,
    result_revision: str,
    expected_change_manifest: list[dict[str, Any]] | None = None,
    label: str = "Slice handoff manifest",
) -> str:
    manifest_path = resolve_report(root, state, supplied, label)
    manifest = read_json(Path(manifest_path))
    expected = {
        "schema_version": 1,
        "status": "sealed",
        "slice_id": slice_id,
        "owner_id": owner_id,
        "base_revision": base_revision,
        "result_revision": result_revision,
    }
    for field, value in expected.items():
        if manifest.get(field) != value:
            raise PipelineError(
                f"{label} {field} mismatch: expected {value!r}, got {manifest.get(field)!r}"
            )
    if not manifest.get("checks") or not manifest.get("coverage_manifest"):
        raise PipelineError(f"{label} must record checks and coverage_manifest")
    if not isinstance(manifest.get("change_manifest"), list):
        raise PipelineError(f"{label} must embed the verified change_manifest list")
    if expected_change_manifest is not None and manifest["change_manifest"] != expected_change_manifest:
        raise PipelineError(f"{label} embedded change_manifest does not match the verified manifest")
    return manifest_path


def path_matches_scope(path: str, rule: str) -> bool:
    if rule.endswith("/**"):
        prefix = rule[:-3].rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    return path == rule


def scope_slice_for_pass(state: dict[str, Any], requested_slice: str | None) -> dict[str, Any]:
    route = (state.get("active_remediation_batch") or {}).get("route")
    slice_id = requested_slice or state.get("active_slice") or route or state.get("slice_id")
    if route == "integration":
        slice_id = requested_slice or state.get("ordered_slices", [])[-1]
    if slice_id not in state.get("slices", {}):
        raise PipelineError("Scope guard requires an approved implementation slice")
    if route and route != "integration" and route != slice_id:
        raise PipelineError("--slice-id does not match the active remediation route")
    return state["slices"][slice_id]


def resolve_scope_artifact(
    root: Path, state: dict[str, Any], supplied: str, label: str
) -> tuple[str, dict[str, Any]]:
    path = resolve_report(root, state, supplied, label)
    value = read_json(Path(path))
    if value.get("schema_version") != 1:
        raise PipelineError(f"{label} must use schema_version 1")
    return path, value


def validate_change_manifest(
    manifest: dict[str, Any],
    *,
    slice_item: dict[str, Any],
    owner_id: str,
    base_revision: str,
    result_revision: str,
) -> list[dict[str, Any]]:
    expected = {
        "slice_id": slice_item["id"],
        "owner_id": owner_id,
        "base_revision": base_revision,
        "result_revision": result_revision,
    }
    for field, value in expected.items():
        if manifest.get(field) != value:
            raise PipelineError(
                f"Change manifest {field} mismatch: expected {value!r}, got {manifest.get(field)!r}"
            )
    changes = manifest.get("change_manifest")
    if not isinstance(changes, list):
        raise PipelineError("Change manifest must contain a change_manifest list")
    seen_paths: set[str] = set()
    for entry in changes:
        required = {
            "path",
            "symbols",
            "slice_id",
            "requirement_ids",
            "acceptance_ids",
            "reason",
            "change_kind",
        }
        if not isinstance(entry, dict) or any(key not in entry for key in required):
            raise PipelineError("Every change_manifest entry must contain the required mapping fields")
        path = scope_path(str(entry["path"]), "changed product")
        if path in seen_paths:
            raise PipelineError(f"Duplicate change_manifest product path: {path}")
        seen_paths.add(path)
        entry["path"] = path
        if entry.get("slice_id") != slice_item["id"]:
            raise PipelineError(f"Change manifest path {path} maps to the wrong slice")
        if not isinstance(entry.get("reason"), str) or not entry["reason"].strip():
            raise PipelineError(f"Change manifest path {path} requires a reason")
        require_string_list(
            entry.get("symbols"),
            f"Change manifest path {path} symbols",
            allow_empty=False,
        )
        requirement_ids = set(
            require_string_list(
                entry.get("requirement_ids"),
                f"Change manifest path {path} requirement_ids",
                allow_empty=False,
            )
        )
        allowed_requirements = set(slice_item.get("requirement_ids", []))
        if not requirement_ids.issubset(allowed_requirements):
            raise PipelineError(
                f"Change manifest path {path} contains PRD-REQ IDs outside its approved slice"
            )
        acceptance_ids = set(
            require_string_list(
                entry.get("acceptance_ids"),
                f"Change manifest path {path} acceptance_ids",
                allow_empty=False,
            )
        )
        allowed_acceptance = set(slice_item["scope_contract"]["acceptance_ids"])
        if not acceptance_ids.issubset(allowed_acceptance):
            raise PipelineError(
                f"Change manifest path {path} contains PRD-AC IDs outside its approved slice"
            )
        if not isinstance(entry.get("change_kind"), str) or not entry["change_kind"].strip():
            raise PipelineError(f"Change manifest path {path} requires a change_kind")
    return changes


def validate_diff_summary(
    summary: dict[str, Any],
    *,
    slice_item: dict[str, Any],
    base_revision: str,
    result_revision: str,
) -> list[dict[str, Any]]:
    for field, expected in {
        "slice_id": slice_item["id"],
        "base_revision": base_revision,
        "result_revision": result_revision,
    }.items():
        if summary.get(field) != expected:
            raise PipelineError(
                f"Diff summary {field} mismatch: expected {expected!r}, got {summary.get(field)!r}"
            )
    files = summary.get("product_files")
    if not isinstance(files, list):
        raise PipelineError("Diff summary product_files must be a list")
    seen: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict):
            raise PipelineError("Every diff summary product file must be an object")
        path = scope_path(str(entry.get("path", "")), "diff product")
        if path in seen:
            raise PipelineError(f"Duplicate diff summary product path: {path}")
        seen.add(path)
        entry["path"] = path
        if not isinstance(entry.get("lines_changed"), int) or entry["lines_changed"] < 0:
            raise PipelineError(f"Diff summary path {path} lines_changed must be non-negative")
        require_string_list(
            entry.get("symbols"),
            f"Diff summary path {path} symbols",
            allow_empty=False,
        )
        for flag in ("lifecycle_change", "ownership_change", "public_contract_change"):
            if not isinstance(entry.get(flag), bool):
                raise PipelineError(f"Diff summary path {path} {flag} must be boolean")
        if not entry.get("change_kind"):
            raise PipelineError(f"Diff summary path {path} requires change_kind")
    return files


def scope_violations(
    slice_item: dict[str, Any],
    changes: list[dict[str, Any]],
    diff_files: list[dict[str, Any]],
    *,
    material_change_approved: bool = False,
) -> list[str]:
    scope = slice_item["scope_contract"]
    manifest_by_path = {entry["path"]: entry for entry in changes}
    diff_by_path = {entry["path"]: entry for entry in diff_files}
    violations: list[str] = []
    if set(manifest_by_path) != set(diff_by_path):
        missing = sorted(set(diff_by_path) - set(manifest_by_path))
        extra = sorted(set(manifest_by_path) - set(diff_by_path))
        if missing:
            violations.append("unmapped product files: " + ", ".join(missing))
        if extra:
            violations.append("manifest files absent from diff: " + ", ".join(extra))
    if len(diff_files) > scope["max_product_files"]:
        violations.append(
            f"product file budget breached: {len(diff_files)} > {scope['max_product_files']}"
        )
    line_count = sum(entry["lines_changed"] for entry in diff_files)
    if line_count > scope["max_product_lines_changed"]:
        violations.append(
            f"product line budget breached: {line_count} > {scope['max_product_lines_changed']}"
        )
    touchpoint_by_path = {item["path"]: item for item in scope["shared_touchpoints"]}
    excluded_components = {item.casefold() for item in scope["excluded_components"]}
    for path, diff in diff_by_path.items():
        mapped = manifest_by_path.get(path, {})
        if any(path_matches_scope(path, rule) for rule in scope["excluded_paths"]):
            violations.append(f"forbidden excluded path changed: {path}")
        component = str(diff.get("component", "")).strip()
        if component and component.casefold() in excluded_components:
            violations.append(f"forbidden component changed: {component} ({path})")
        if diff["change_kind"].casefold() in {"cleanup", "refactor", "drive-by cleanup", "drive-by refactor"} or diff.get("drive_by") is True:
            violations.append(f"drive-by cleanup/refactor is forbidden: {path}")
        material_flags = [
            name
            for name in ("lifecycle_change", "ownership_change", "public_contract_change")
            if diff[name]
        ]
        if material_flags and not material_change_approved:
            violations.append(f"material boundary change in {path}: {', '.join(material_flags)}")
        owned = any(path_matches_scope(path, rule) for rule in scope["editable_paths"])
        touchpoint = touchpoint_by_path.get(path)
        if not owned and not touchpoint:
            violations.append(f"unapproved product path: {path}")
            continue
        if touchpoint and not owned:
            if mapped.get("touchpoint_id") != touchpoint["id"]:
                violations.append(f"unapproved shared touchpoint mapping: {path}")
            changed_symbols = set(diff["symbols"])
            mapped_symbols = set(mapped.get("symbols", []))
            allowed_symbols = set(touchpoint["symbols"])
            if not changed_symbols or changed_symbols != mapped_symbols:
                violations.append(f"unmapped shared symbols: {path}")
            if not changed_symbols.issubset(allowed_symbols):
                violations.append(f"forbidden shared symbol changed: {path}")
            if mapped.get("change_kind") != diff.get("change_kind"):
                violations.append(f"shared touchpoint change kind mismatch: {path}")
            if diff.get("change_kind") != touchpoint["allowed_change"]:
                violations.append(f"shared touchpoint change is not approved: {path}")
    return sorted(set(violations))


def record_scope_churn(
    state: dict[str, Any], slice_item: dict[str, Any], diff_files: list[dict[str, Any]]
) -> None:
    for churn in (state["scope_guard"]["scope_churn"], slice_item["scope_churn"]):
        churn["passes"] += 1
        churn["product_files_changed"] += len(diff_files)
        churn["product_lines_changed"] += sum(item["lines_changed"] for item in diff_files)
        churn["unique_product_files"] = sorted(
            set(churn["unique_product_files"]) | {item["path"] for item in diff_files}
        )
        touchpoints = {
            item.get("touchpoint_id")
            for item in diff_files
            if item.get("touchpoint_id")
        }
        churn["touchpoint_ids"] = sorted(set(churn["touchpoint_ids"]) | touchpoints)


def resolve_owner_handoff_manifest(
    root: Path,
    state: dict[str, Any],
    supplied: str,
    *,
    route: str,
    from_owner: str,
    to_owner: str,
    reason: str,
    expected_finding_ids: list[str] | None = None,
) -> str:
    manifest_path = resolve_report(root, state, supplied, "Engineering owner handoff manifest")
    manifest = read_json(Path(manifest_path))
    expected = {
        "schema_version": 1,
        "status": "sealed",
        "route": route,
        "from_owner": from_owner,
        "to_owner": to_owner,
        "revision": state.get("revision"),
        "reason": reason,
    }
    for field, value in expected.items():
        if manifest.get(field) != value:
            raise PipelineError(
                "Engineering owner handoff manifest "
                f"{field} mismatch: expected {value!r}, got {manifest.get(field)!r}"
            )
    finding_ids = manifest.get("finding_ids")
    if not isinstance(finding_ids, list) or not finding_ids or not manifest.get(
        "verification_state"
    ):
        raise PipelineError(
            "Engineering owner handoff manifest must record finding_ids and verification_state"
        )
    if expected_finding_ids is not None and sorted(set(finding_ids)) != sorted(
        set(expected_finding_ids)
    ):
        raise PipelineError(
            "Engineering owner handoff manifest must contain the exact active remediation batch"
        )
    return manifest_path


def route_for_finding(state: dict[str, Any], item: dict[str, Any]) -> str:
    route = item.get("remediation_route") or item.get("origin_slice")
    if route == "integration":
        return "integration"
    if route not in state.get("ordered_slices", []):
        if state.get("development_mode") == "single_owner":
            return state["ordered_slices"][0]
        raise PipelineError(f"Finding {item['id']} has no valid origin_slice routing")
    return route


def build_remediation_queue(
    state: dict[str, Any], findings: dict[str, Any], finding_ids: list[str]
) -> None:
    selected = [item for item in findings["items"] if item["id"] in set(finding_ids)]
    grouped: dict[str, list[str]] = {}
    for item in selected:
        route = route_for_finding(state, item)
        grouped.setdefault(route, []).append(item["id"])
    order = list(state["ordered_slices"]) + ["integration"]
    state["remediation_queue"] = [
        {
            "route": route,
            "finding_ids": sorted(grouped[route]),
            "status": "pending",
            "owner_id": None,
            "returns_for_owner": None,
        }
        for route in order
        if route in grouped
    ]
    state["active_remediation_batch"] = None
    activate_next_remediation_batch(state)


def activate_next_remediation_batch(state: dict[str, Any]) -> None:
    batch = next(
        (item for item in state.get("remediation_queue", []) if item["status"] == "pending"),
        None,
    )
    if batch is None:
        state["active_remediation_batch"] = None
        return
    route = batch["route"]
    owner_id = (
        state.get("integration_owner")
        if route == "integration"
        else state.get("owner_by_slice", {}).get(route)
    )
    if not owner_id:
        raise PipelineError(f"No engineering owner is recorded for remediation route {route}")
    returns = (
        state.setdefault("integration_remediation_returns_by_owner", {}).get(owner_id, 0)
        if route == "integration"
        else state["slices"][route].setdefault("remediation_returns_by_owner", {}).get(owner_id, 0)
    )
    batch["owner_id"] = owner_id
    batch["returns_for_owner"] = returns
    batch["status"] = "active"
    state["active_remediation_batch"] = batch
    state["active_slice"] = None if route == "integration" else route
    state["slice_id"] = route
    state["engineering_owner_id"] = owner_id
    state["phase"] = "owner_handoff_hold" if returns >= 3 else "engineering"


def complete_remediation_batch(state: dict[str, Any], owner_id: str) -> bool:
    active = state.get("active_remediation_batch")
    if not active:
        return False
    batch = next(
        (
            item
            for item in state.get("remediation_queue", [])
            if item.get("status") == "active" and item.get("route") == active.get("route")
        ),
        active,
    )
    route = batch["route"]
    if route == "integration":
        counters = state.setdefault("integration_remediation_returns_by_owner", {})
    else:
        counters = state["slices"][route].setdefault("remediation_returns_by_owner", {})
    counters[owner_id] = counters.get(owner_id, 0) + 1
    batch["returns_for_owner"] = counters[owner_id]
    batch["status"] = "completed"
    batch["completed_at"] = utc_now()
    batch["result_revision"] = state.get("revision")
    state["active_remediation_batch"] = None
    activate_next_remediation_batch(state)
    return state.get("active_remediation_batch") is not None


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
            if relative == DEFERRED_BACKLOG_PATH.as_posix():
                raise PipelineError(
                    "docs/engineering/deferred-findings.json is controller-managed project "
                    "backlog state and must not enter product, support, evidence, or composite revisions"
                )
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
        if phase == "scope_expansion_hold":
            return {
                "action": "approve_updated_plan_and_rebaseline_scope",
                "owner": "user",
                "user_input_required": True,
                "hold": state.get("scope_guard", {}).get("hold"),
            }
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
    if phase == "scope_expansion_hold":
        return {
            "action": "approve_updated_plan_and_rebaseline_scope",
            "owner": "user",
            "user_input_required": True,
            "hold": state.get("scope_guard", {}).get("hold"),
        }
    if phase == "finding_triage":
        triage = state.get("finding_triage") or {}
        return {
            "action": "complete_bounded_finding_triage",
            "owner": "technical_director",
            "user_input_required": False,
            "finding_id": triage.get("finding_id"),
            "resume_phase": triage.get("resume_phase"),
        }
    if phase == "slice_research":
        active = active_slice_state(state)
        return {
            "action": (
                "resume_engineering_owner_for_research"
                if state.get("engineering_owner_id")
                else "spawn_engineering_owner_for_research"
            ),
            "owner": "technical_director",
            "user_input_required": False,
            "engineering_owner_id": state.get("engineering_owner_id"),
            "active_slice": state.get("active_slice"),
            "base_revision": (active or {}).get("base_revision"),
            "required_bundle_count": "1-3",
        }
    if phase == "slice_engineering":
        return {
            "action": (
                "resume_engineering_owner"
                if state.get("engineering_owner_id")
                else "spawn_implementation_owner"
            ),
            "owner": "technical_director",
            "user_input_required": False,
            "engineering_owner_id": state.get("engineering_owner_id"),
            "active_slice": state.get("active_slice"),
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
            "active_slice": state.get("active_slice"),
            "remediation_batch": state.get("active_remediation_batch"),
        }
    if phase == "owner_handoff_hold":
        return {
            "action": "handoff_to_fresh_engineer",
            "owner": "technical_director",
            "user_input_required": False,
            "route": (state.get("active_remediation_batch") or {}).get("route"),
            "engineering_owner_id": state.get("engineering_owner_id"),
            "reason": "The assigned Engineer has completed three remediation returns",
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
        qa_capability = state.get("qa_capability", {})
        if (
            qa_capability.get("status") != "ready"
            or qa_capability.get("revision") != state.get("revision")
        ):
            blocked = {
                name: status
                for name, status in qa_capability.get("capabilities", {}).items()
                if status in QA_CAPABILITY_BLOCKING_STATUSES
            }
            user_gate = any(status == "blocked_user" for status in blocked.values())
            return {
                "action": (
                    "resolve_qa_capability_probe"
                    if blocked
                    else "run_exact_revision_qa_capability_probe"
                ),
                "owner": "user" if user_gate else "technical_director",
                "user_input_required": user_gate,
                "probe_id": qa_capability.get("probe_id"),
                "capabilities": blocked,
                "minimum_resume_actions": qa_capability.get(
                    "minimum_resume_actions", {}
                ),
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
    if args.max_convergence_waves != DEFAULT_MAX_CONVERGENCE_WAVES:
        raise PipelineError("max-convergence-waves is a fixed hard maximum of 2")
    if args.max_workers < 1:
        raise PipelineError("max-workers must be positive")
    if args.max_full_review_waves < 1:
        raise PipelineError("max-full-review-waves must be positive")

    requirements = resolve_project_file(root, args.requirements, "Approved product requirements")
    spec = resolve_project_file(root, args.spec, "Approved technical specification")
    requirements_meta, _ = require_feature_documents(root, feature, requirements, spec)
    plan = require_development_plan(
        root, feature, requirements, spec, args.plan, args.plan_sha256
    )
    if args.slice and args.slice not in {plan["slices"][0]["id"], "slice-1"}:
        raise PipelineError(
            "--slice is a compatibility alias and must identify the first approved plan slice"
        )
    if not args.base_revision.strip():
        raise PipelineError("--base-revision must identify the exact implementation base")
    baseline_mismatches = [
        item["id"]
        for item in plan["slices"]
        if item["scope_contract"]["scope_baseline_revision"] != args.base_revision
    ]
    if baseline_mismatches:
        raise PipelineError(
            "Every approved slice scope_baseline_revision must match --base-revision; "
            "mismatch: " + ", ".join(baseline_mismatches)
        )
    tests_root = ensure_test_artifact_layout(root, feature)

    now = utc_now()
    state = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "project_root": str(root),
        "feature": feature,
        "slice_id": plan["slices"][0]["id"],
        "development_plan_path": plan["path"],
        "development_plan_sha256": plan["sha256"],
        "development_mode": plan["mode"],
        "ordered_slices": [item["id"] for item in plan["slices"]],
        "active_slice": plan["slices"][0]["id"],
        "slices": {
            item["id"]: new_slice_state(
                item["id"],
                item["dependencies"],
                item["requirement_ids"],
                item["scope_contract"],
            )
            for item in plan["slices"]
        },
        "owner_by_slice": {},
        "integration_owner": args.integration_owner,
        "handoff_manifests": [],
        "remediation_queue": [],
        "active_remediation_batch": None,
        "execution_stage": "implementation",
        "scope_guard": {
            "status": "pending",
            "hold": None,
            "history": [],
            "scope_churn": empty_scope_churn(),
            "rebaseline_history": [],
        },
        "finding_triage": None,
        "requirements_path": str(requirements),
        "requirements_revision": requirements_meta["revision"],
        "requirements_sha256": file_sha256(requirements),
        "spec_path": str(spec),
        "spec_sha256": file_sha256(spec),
        "tests_path": str(tests_root),
        "phase": "preflight",
        "revision": args.base_revision,
        "product_revision": args.base_revision,
        "support_revision": args.base_revision,
        "evidence_revision": args.base_revision,
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
        "component_review_credits": [],
        "product_revalidation": None,
        "closure_review": None,
        "qa": empty_qa_state(),
        "qa_capability": empty_qa_capability_state(),
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
    set_active_slice(
        state,
        plan["slices"][0]["id"],
        base_revision=args.base_revision,
        base_product_revision=args.base_revision,
        base_support_revision=args.base_revision,
        base_evidence_revision=args.base_revision,
    )
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
    if state["phase"] not in {"preflight", "qa"}:
        raise PipelineError("Preflight can complete only during preflight or the QA prerequisite gate")
    entry_phase = state["phase"]
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
    if entry_phase == "preflight":
        state["phase"] = (
            "preflight" if args.resource_budget_check == "fail" else "slice_research"
        )
    else:
        state["phase"] = "qa"
    save_runtime(state_path, findings_path, state, findings)
    return cmd_status(args)


def cmd_status(args: argparse.Namespace) -> int:
    _, _, _, state, findings = load_runtime(args.project_root)
    counts = {"critical": 0, "major": 0, "minor": 0}
    for item in findings["items"]:
        if item["status"] == "open":
            counts[item["severity"]] += 1
    counts["blocking"] = len(open_blocking(findings))
    gate_counts = {status: 0 for status in sorted(QA_GATE_STATUSES)}
    for gate in state.get("gates", []):
        if gate.get("status") == "open":
            gate_counts[gate["category"]] += 1
    result = {
        "feature": state["feature"],
        "slice": state["slice_id"],
        "development_plan": {
            "path": state["development_plan_path"],
            "sha256": state["development_plan_sha256"],
            "mode": state["development_mode"],
        },
        "ordered_slices": state["ordered_slices"],
        "active_slice": state["active_slice"],
        "slices": state["slices"],
        "owner_by_slice": state["owner_by_slice"],
        "integration_owner": state["integration_owner"],
        "handoff_manifests": state["handoff_manifests"],
        "remediation_queue": state["remediation_queue"],
        "active_remediation_batch": state["active_remediation_batch"],
        "execution_stage": state["execution_stage"],
        "scope_guard": state["scope_guard"],
        "finding_triage": state.get("finding_triage"),
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
        "component_review_credits": state["component_review_credits"],
        "qa": state["qa"],
        "qa_capability": state["qa_capability"],
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


def cmd_slice_research_complete(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    if state.get("phase") != "slice_research":
        raise PipelineError("Slice research can complete only in the slice_research phase")
    active = active_slice_state(state)
    if active is None or args.slice_id != state.get("active_slice"):
        raise PipelineError("Research slice_id must match the active implementation slice")
    if args.base_revision != active.get("base_revision") or args.base_revision != state.get("revision"):
        raise PipelineError("Research base revision must match the exact active slice revision")
    require_worker_budget(state, args.owner_id)
    assigned_owner = state.get("owner_by_slice", {}).get(args.slice_id)
    if assigned_owner and assigned_owner != args.owner_id:
        raise PipelineError("Only the assigned slice Engineer may close its research gate")
    bundle_paths = args.bundle or []
    if not 1 <= len(bundle_paths) <= 3:
        raise PipelineError("Slice research requires one to three result bundles")
    records = [
        resolve_research_bundle(
            root,
            state,
            supplied,
            slice_id=args.slice_id,
            base_revision=args.base_revision,
        )
        for supplied in bundle_paths
    ]
    brief_ids = [item["brief_id"] for item in records]
    researcher_ids = [item["researcher_id"] for item in records]
    if len(set(brief_ids)) != len(brief_ids):
        raise PipelineError("Research brief IDs must be unique within a slice")
    if len(set(researcher_ids)) != len(researcher_ids):
        raise PipelineError("Every research brief requires a fresh distinct researcher")
    prior_workers = set(state.get("worker_budget", {}).get("worker_ids", []))
    reused = sorted(prior_workers.intersection(researcher_ids))
    if reused:
        raise PipelineError(
            "Slice research requires fresh researcher identities: " + ", ".join(reused)
        )
    if any(item["status"] != "complete" for item in records):
        raise PipelineError("Every required research bundle must have status complete")
    for researcher_id in researcher_ids:
        require_worker_budget(state, researcher_id)
        record_worker(state, "bounded_researcher", researcher_id)
    active["research"] = {
        "status": "complete",
        "base_revision": args.base_revision,
        "bundles": records,
        "reason": None,
        "completed_at": utc_now(),
    }
    state["engineering_owner_id"] = args.owner_id
    state["owner_by_slice"][args.slice_id] = args.owner_id
    active["owner_id"] = args.owner_id
    if state.get("integration_owner") is None:
        state["integration_owner"] = args.owner_id
    state["phase"] = "slice_engineering"
    save_runtime(state_path, findings_path, state, findings)
    return cmd_status(args)


def parse_resume_actions(values: list[str] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values or []:
        if "=" not in value:
            raise PipelineError(
                "Minimum resume actions must use <capability>=<minimum action>"
            )
        name, action = value.split("=", 1)
        name = name.strip()
        action = action.strip()
        if name not in QA_CAPABILITY_NAMES or not action:
            raise PipelineError(f"Invalid minimum resume action: {value!r}")
        result[name] = action
    return result


def cmd_qa_capability_probe(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    require_current_revision(state, args.revision)
    if state["phase"] != "qa":
        raise PipelineError("QA capability probe is valid only immediately before or during QA")
    report = resolve_report(root, state, args.report, "QA capability probe report")
    capabilities = parse_capabilities(args.capability)
    missing = sorted(QA_CAPABILITY_NAMES - set(capabilities))
    extra = sorted(set(capabilities) - QA_CAPABILITY_NAMES)
    if missing or extra:
        details = []
        if missing:
            details.append("missing: " + ", ".join(missing))
        if extra:
            details.append("unexpected: " + ", ".join(extra))
        raise PipelineError(
            "QA capability probe must record the complete exact capability matrix ("
            + "; ".join(details)
            + ")"
        )
    resume_actions = parse_resume_actions(args.minimum_resume_action)
    blocked = {
        name: status
        for name, status in capabilities.items()
        if status in QA_CAPABILITY_BLOCKING_STATUSES
    }
    missing_actions = sorted(set(blocked) - set(resume_actions))
    if missing_actions:
        raise PipelineError(
            "Every failed QA capability probe requires a minimum resume action: "
            + ", ".join(missing_actions)
        )
    capability_state = state["qa_capability"]
    if any(probe["probe_id"] == args.probe_id for probe in capability_state["probes"]):
        raise PipelineError(f"QA capability probe ID already recorded: {args.probe_id}")
    probe = {
        "probe_id": args.probe_id,
        "revision": args.revision,
        "capabilities": capabilities,
        "minimum_resume_actions": resume_actions,
        "report": report,
        "status": "blocked" if blocked else "ready",
        "recorded_at": utc_now(),
    }
    capability_state["probes"].append(probe)
    capability_state.update(
        {
            "status": probe["status"],
            "revision": args.revision,
            "probe_id": args.probe_id,
            "capabilities": capabilities,
            "minimum_resume_actions": resume_actions,
            "report": report,
        }
    )
    for gate in state.get("gates", []):
        if gate.get("status") == "open" and gate.get("origin") == "qa_capability_probe":
            gate["status"] = "resolved"
            gate["resolved_at"] = utc_now()
            gate["resolution"] = "Superseded by exact-revision capability probe"
    if blocked:
        priority = (
            "blocked_user"
            if "blocked_user" in blocked.values()
            else "blocked_environment"
            if "blocked_environment" in blocked.values()
            else "error_test"
        )
        state["qa"] = {
            **empty_qa_state(),
            "status": priority,
            "revision": args.revision,
            "reason": "; ".join(f"{name}={status}" for name, status in sorted(blocked.items())),
            "capability_probe_id": args.probe_id,
            "minimum_resume_actions": resume_actions,
        }
        for name, status in blocked.items():
            state["gates"].append(
                {
                    "id": f"qa-capability:{args.probe_id}:{name}",
                    "phase": "qa",
                    "category": status,
                    "origin": "qa_capability_probe",
                    "revision": args.revision,
                    "reason": f"Capability probe failed: {name}={status}",
                    "minimum_resume_action": resume_actions[name],
                    "pending_scenarios": [name],
                    "report": report,
                    "status": "open",
                    "created_at": utc_now(),
                }
            )
    else:
        state["qa"] = empty_qa_state()
    save_runtime(state_path, findings_path, state, findings)
    return cmd_status(args)


def cmd_slice_research_not_required(args: argparse.Namespace) -> int:
    _, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    if state.get("phase") != "slice_research":
        raise PipelineError(
            "research_not_required can be recorded only in the slice_research phase"
        )
    active = active_slice_state(state)
    if active is None or args.slice_id != state.get("active_slice"):
        raise PipelineError("Research slice_id must match the active implementation slice")
    if args.base_revision != active.get("base_revision") or args.base_revision != state.get("revision"):
        raise PipelineError("Research base revision must match the exact active slice revision")
    require_worker_budget(state, args.owner_id)
    assigned_owner = state.get("owner_by_slice", {}).get(args.slice_id)
    if assigned_owner and assigned_owner != args.owner_id:
        raise PipelineError("Only the assigned slice Engineer may close its research gate")
    if not args.reason.strip():
        raise PipelineError("research_not_required requires an explicit reason")
    active["research"] = {
        "status": "not_required",
        "base_revision": args.base_revision,
        "bundles": [],
        "reason": args.reason.strip(),
        "completed_at": utc_now(),
    }
    state["engineering_owner_id"] = args.owner_id
    state["owner_by_slice"][args.slice_id] = args.owner_id
    active["owner_id"] = args.owner_id
    if state.get("integration_owner") is None:
        state["integration_owner"] = args.owner_id
    state["phase"] = "slice_engineering"
    save_runtime(state_path, findings_path, state, findings)
    return cmd_status(args)


def cmd_slice_scope_check(args: argparse.Namespace) -> int:
    _, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    if state.get("phase") not in {"slice_engineering", "engineering"}:
        raise PipelineError("slice-scope-check is valid only immediately before an Engineer edit pass")
    if state.get("scope_guard", {}).get("status") == "scope_expansion_hold":
        raise PipelineError("scope_expansion_hold requires user-approved plan rebaseline")
    slice_item = scope_slice_for_pass(state, args.slice_id)
    if args.base_revision != state.get("revision"):
        raise PipelineError("slice-scope-check base revision must match current pipeline revision")
    active_owner = state.get("engineering_owner_id") or slice_item.get("owner_id")
    if active_owner and active_owner != args.owner_id:
        raise PipelineError("slice-scope-check owner does not match the assigned Engineer")
    check = {
        "slice_id": slice_item["id"],
        "owner_id": args.owner_id,
        "base_revision": args.base_revision,
        "development_plan_sha256": state["development_plan_sha256"],
        "scope_contract": slice_item["scope_contract"],
        "status": "passed",
        "recorded_at": utc_now(),
    }
    slice_item["scope_pre_edit_check"] = check
    slice_item["scope_history"].append({"event": "pre_edit_check", **check})
    state["scope_guard"]["status"] = "edit_authorized"
    state["scope_guard"]["history"].append({"event": "pre_edit_check", **check})
    save_runtime(state_path, findings_path, state, findings)
    return cmd_status(args)


def open_scope_expansion_hold(
    state: dict[str, Any], slice_item: dict[str, Any], violations: list[str]
) -> None:
    previous_phase = state["phase"]
    hold = {
        "slice_id": slice_item["id"],
        "base_revision": state.get("revision"),
        "development_plan_sha256": state.get("development_plan_sha256"),
        "violations": violations,
        "resume_phase": previous_phase,
        "opened_at": utc_now(),
    }
    state["phase"] = "scope_expansion_hold"
    state["scope_guard"]["status"] = "scope_expansion_hold"
    state["scope_guard"]["hold"] = hold
    state["scope_guard"]["history"].append({"event": "scope_expansion_hold", **hold})
    slice_item["scope_history"].append({"event": "scope_expansion_hold", **hold})


def cmd_rebaseline_scope(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    if state.get("phase") != "scope_expansion_hold":
        raise PipelineError("rebaseline-scope requires an open scope_expansion_hold")
    if not args.user_scope_approval.strip():
        raise PipelineError("rebaseline-scope requires explicit user scope approval evidence")
    requirements = resolve_project_file(root, state["requirements_path"], "Approved product requirements")
    spec = resolve_project_file(root, state["spec_path"], "Approved technical specification")
    plan = require_development_plan(
        root,
        state["feature"],
        requirements,
        spec,
        state["development_plan_path"],
        args.plan_sha256,
    )
    if [item["id"] for item in plan["slices"]] != state["ordered_slices"]:
        raise PipelineError("Scope rebaseline cannot change approved slice ordering in-place")
    hold = state["scope_guard"]["hold"]
    active_id = hold["slice_id"]
    replacement = next(item for item in plan["slices"] if item["id"] == active_id)
    if replacement["scope_contract"]["scope_baseline_revision"] != state.get("revision"):
        raise PipelineError(
            "Updated active slice scope_baseline_revision must equal the current exact pipeline revision"
        )
    for item in plan["slices"]:
        prior = state["slices"][item["id"]]
        if prior.get("status") == "sealed" and (
            prior.get("scope_contract") != item["scope_contract"]
            or prior.get("requirement_ids") != item["requirement_ids"]
        ):
            raise PipelineError(
                f"Updated plan cannot rewrite the sealed scope contract for {item['id']}"
            )
    for item in plan["slices"]:
        state["slices"][item["id"]]["scope_contract"] = item["scope_contract"]
        state["slices"][item["id"]]["requirement_ids"] = item["requirement_ids"]
        state["slices"][item["id"]]["scope_pre_edit_check"] = None
    state["development_plan_sha256"] = plan["sha256"]
    event = {
        "event": "scope_rebaseline",
        "slice_id": active_id,
        "prior_plan_sha256": hold["development_plan_sha256"],
        "approved_plan_sha256": plan["sha256"],
        "baseline_revision": state.get("revision"),
        "user_scope_approval": args.user_scope_approval,
        "recorded_at": utc_now(),
    }
    state["scope_guard"]["history"].append(event)
    state["scope_guard"]["rebaseline_history"].append(event)
    state["scope_guard"]["hold"] = None
    state["scope_guard"]["status"] = "pending"
    state["phase"] = hold["resume_phase"]
    save_runtime(state_path, findings_path, state, findings)
    return cmd_status(args)


def cmd_engineer_complete(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    require_worker_budget(state, args.owner_id)
    if state["phase"] not in {"slice_engineering", "engineering"}:
        raise PipelineError(
            "Full Engineer completion is valid only after slice research or in remediation engineering"
        )
    if state["phase"] == "slice_engineering":
        active_research = (active_slice_state(state) or {}).get("research", {})
        if active_research.get("status") not in RESEARCH_TERMINAL_STATUSES:
            raise PipelineError("Production edits require the slice research gate to be closed")
        if active_research.get("base_revision") != state.get("revision"):
            raise PipelineError("Slice research evidence is stale for the current revision")
    slice_execution = (
        state.get("development_mode") == "sequential_slices"
        and state.get("execution_stage") == "implementation"
    )
    active_slice = active_slice_state(state)
    if slice_execution:
        if active_slice is None:
            raise PipelineError("Sequential implementation requires one active slice")
        if args.slice_id != state.get("active_slice"):
            raise PipelineError(
                f"Engineer must identify active slice {state.get('active_slice')} with --slice-id"
            )
        if args.base_revision != active_slice.get("base_revision"):
            raise PipelineError(
                "Slice Engineer base revision does not match the exact sealed predecessor revision"
            )
        if args.base_revision != state.get("revision"):
            raise PipelineError("Slice base revision is not the current pipeline revision")
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
    if active_slice is not None:
        assigned = state["owner_by_slice"].get(active_slice["id"])
        if assigned and assigned != args.owner_id:
            raise PipelineError("Only the recorded owner may write the active slice")
        state["owner_by_slice"][active_slice["id"]] = args.owner_id
        active_slice["owner_id"] = args.owner_id
    if state.get("integration_owner") is None:
        state["integration_owner"] = args.owner_id
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
    if not args.change_manifest or not args.diff_summary:
        raise PipelineError(
            "Engineer completion requires --change-manifest and --diff-summary after slice-scope-check"
        )
    slice_item = scope_slice_for_pass(state, args.slice_id)
    pre_edit = slice_item.get("scope_pre_edit_check") or {}
    if (
        pre_edit.get("status") != "passed"
        or pre_edit.get("owner_id") != args.owner_id
        or pre_edit.get("base_revision") != input_revision
        or pre_edit.get("development_plan_sha256") != state.get("development_plan_sha256")
    ):
        raise PipelineError(
            "Engineer edits require a current slice-scope-check by the assigned owner before editing"
        )
    change_manifest_path, change_manifest_value = resolve_scope_artifact(
        root, state, args.change_manifest, "Engineer change manifest"
    )
    diff_summary_path, diff_summary_value = resolve_scope_artifact(
        root, state, args.diff_summary, "Engineer product diff summary"
    )
    changes = validate_change_manifest(
        change_manifest_value,
        slice_item=slice_item,
        owner_id=args.owner_id,
        base_revision=input_revision,
        result_revision=args.revision,
    )
    diff_files = validate_diff_summary(
        diff_summary_value,
        slice_item=slice_item,
        base_revision=input_revision,
        result_revision=args.revision,
    )
    matching_rebaseline = next(
        (
            event
            for event in reversed(state["scope_guard"].get("rebaseline_history", []))
            if event.get("slice_id") == slice_item["id"]
            and event.get("baseline_revision") == input_revision
            and event.get("approved_plan_sha256") == state.get("development_plan_sha256")
        ),
        None,
    )
    material_change_approved = bool(
        matching_rebaseline
        and args.scope_approval
        and args.scope_approval == matching_rebaseline.get("user_scope_approval")
    )
    violations = scope_violations(
        slice_item,
        changes,
        diff_files,
        material_change_approved=material_change_approved,
    )
    if args.scope_approval and not material_change_approved:
        violations.append(
            "scope approval does not match the exact current-slice rebaseline event"
        )
    if args.production_change_scope == "architectural" and not material_change_approved:
        violations.append(
            "architectural scope classification requires an updated approved plan and rebaseline"
        )
    if bool(diff_files) != product_changed:
        violations.append(
            "product revision change classification does not match diff summary product_files"
        )
    computed_files_changed = len(diff_files)
    computed_lines_changed = sum(item["lines_changed"] for item in diff_files)
    if args.production_files_changed is not None and args.production_files_changed != computed_files_changed:
        violations.append("reported production file count does not match diff summary")
    if args.production_lines_changed is not None and args.production_lines_changed != computed_lines_changed:
        violations.append("reported production line count does not match diff summary")
    if violations:
        open_scope_expansion_hold(state, slice_item, sorted(set(violations)))
        save_runtime(state_path, findings_path, state, findings)
        raise PipelineError(
            "scope_expansion_hold: " + "; ".join(sorted(set(violations)))
        )
    record_scope_churn(state, slice_item, diff_files)
    scope_event = {
        "event": "scope_pass",
        "slice_id": slice_item["id"],
        "owner_id": args.owner_id,
        "base_revision": input_revision,
        "result_revision": args.revision,
        "change_manifest": change_manifest_path,
        "diff_summary": diff_summary_path,
        "product_files_changed": computed_files_changed,
        "product_lines_changed": computed_lines_changed,
        "recorded_at": utc_now(),
    }
    state["scope_guard"]["status"] = "passed"
    state["scope_guard"]["history"].append(scope_event)
    slice_item["scope_history"].append(scope_event)
    slice_item["scope_pre_edit_check"] = None
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
    coverage_manifest = resolve_coverage_manifest(
        root,
        state,
        args.coverage_manifest,
        product_revision,
        support_revision,
        evidence_revision,
    )
    resolved_ids = set(args.resolved_finding or [])
    active_batch = state.get("active_remediation_batch")
    if active_batch and resolved_ids != set(active_batch["finding_ids"]):
        raise PipelineError(
            "A remediation return must resolve the complete active origin-routed finding batch"
        )
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

    handoff_manifest = None
    if slice_execution:
        if args.machine_checks != "pass" or open_blocking(findings):
            raise PipelineError(
                "A sequential slice cannot be sealed until checks pass and blocking findings close"
            )
        if not args.handoff_manifest:
            raise PipelineError("Sequential slice completion requires --handoff-manifest")
        handoff_manifest = resolve_handoff_manifest(
            root,
            state,
            args.handoff_manifest,
            slice_id=active_slice["id"],
            owner_id=args.owner_id,
            base_revision=active_slice["base_revision"],
            result_revision=args.revision,
            expected_change_manifest=changes,
        )
        active_slice["status"] = "sealed"
        active_slice["result_revision"] = args.revision
        active_slice["result_product_revision"] = product_revision
        active_slice["result_support_revision"] = support_revision
        active_slice["result_evidence_revision"] = evidence_revision
        active_slice["handoff_manifests"].append(handoff_manifest)
        active_slice["sealed_at"] = utc_now()
        state["handoff_manifests"].append(
            {
                "kind": "slice_seal",
                "slice_id": active_slice["id"],
                "owner_id": args.owner_id,
                "base_revision": active_slice["base_revision"],
                "result_revision": args.revision,
                "manifest": handoff_manifest,
                "recorded_at": utc_now(),
            }
        )
        current_index = state["ordered_slices"].index(active_slice["id"])
        if current_index + 1 < len(state["ordered_slices"]):
            next_slice = state["ordered_slices"][current_index + 1]
            set_active_slice(
                state,
                next_slice,
                base_revision=args.revision,
                base_product_revision=product_revision,
                base_support_revision=support_revision,
                base_evidence_revision=evidence_revision,
            )
            outcome = "slice_sealed"
            state["phase"] = "slice_research"
        else:
            state["active_slice"] = None
            state["execution_stage"] = "feature_validation"
            state["engineering_owner_id"] = state.get("integration_owner")
            next_wave = state.get("convergence", {}).get("wave", 0) + 1
            state["convergence"] = empty_convergence_state(
                state["required_convergence_audits"],
                args.revision,
                product_revision,
                support_revision,
                evidence_revision,
                next_wave,
                list(state["ordered_slices"]),
                "initial_implementation",
            )
            outcome = "changed" if product_changed else "clean"
            state["phase"] = "convergence"
    elif product_changed:
        outcome = "changed"
        iteration = state["iteration_control"]
        iteration["consecutive_product_changes"] += 1
        has_next_batch = False
        if active_batch and resolved_ids == set(active_batch["finding_ids"]):
            has_next_batch = complete_remediation_batch(state, args.owner_id)
        revalidation = state.get("product_revalidation")
        if has_next_batch:
            state["iteration_control"]["resume_phase"] = None
        elif revalidation and revalidation.get("mode") == "targeted":
            state["closure_review"] = {
                "status": "pending",
                "mode": "targeted_product_closure",
                "source": revalidation.get("source"),
                "return_phase": (
                    "review" if revalidation.get("source") == "convergence" else "qa"
                ),
                "revision": state["revision"],
                "product_revision": state["product_revision"],
                "support_revision": state["support_revision"],
                "evidence_revision": state["evidence_revision"],
                "base_review_runs": revalidation.get("base_review_runs", []),
                "base_convergence_runs": revalidation.get(
                    "base_convergence_runs", []
                ),
                "finding_ids": revalidation["finding_ids"],
                "changed_impact_surface": {
                    "paths": sorted(item["path"] for item in diff_files),
                    "symbols": sorted(
                        {
                            symbol
                            for item in diff_files
                            for symbol in item.get("symbols", [])
                        }
                    ),
                },
                "run": None,
            }
            iteration["status"] = "running"
            iteration["reason"] = None
            iteration["resume_phase"] = None
            state["phase"] = "closure_review"
        else:
            slice_ids = (
                list(revalidation.get("slice_ids", []))
                if revalidation
                else list(state.get("ordered_slices", []))
            )
            trigger = (
                revalidation.get("full_wave_trigger")
                if revalidation
                else "initial_implementation"
            )
            require_full_convergence_budget(state, slice_ids)
            next_wave = state.get("convergence", {}).get("wave", 0) + 1
            state["convergence"] = empty_convergence_state(
                state["required_convergence_audits"],
                args.revision,
                product_revision,
                support_revision,
                evidence_revision,
                next_wave,
                slice_ids,
                trigger,
            )
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
            "production_files_changed": computed_files_changed,
            "production_lines_changed": computed_lines_changed,
            "scope_approval": args.scope_approval,
            "resolved_findings": sorted(resolved_ids),
            "slice_id": args.slice_id or state.get("slice_id"),
            "base_revision": args.base_revision or input_revision,
            "handoff_manifest": handoff_manifest,
            "change_manifest": change_manifest_path,
            "diff_summary": diff_summary_path,
            "audit_complete": True,
            "recorded_at": utc_now(),
        }
    )
    record_worker(state, "engineer", args.owner_id)
    save_runtime(state_path, findings_path, state, findings)
    return cmd_status(args)


def cmd_transfer_engineering_owner(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    if state["phase"] not in {"engineering", "owner_handoff_hold"}:
        raise PipelineError("Engineering ownership can transfer only before a remediation pass")
    if state.get("engineering_owner_id") != args.from_owner:
        raise PipelineError("from-owner does not match the assigned engineering owner")
    if args.from_owner == args.to_owner:
        raise PipelineError("Engineering ownership transfer requires a different owner")
    active_batch = state.get("active_remediation_batch")
    route = (active_batch or {}).get("route") or args.slice_id or state.get("active_slice")
    if args.slice_id and args.slice_id != route:
        raise PipelineError("--slice-id does not match the active engineering route")
    if args.to_owner in state.get("worker_budget", {}).get("worker_ids", []):
        raise PipelineError("Engineering ownership handoff requires a fresh Engineer identity")
    if not args.handoff_manifest:
        raise PipelineError("Engineering ownership handoff requires --handoff-manifest")
    manifest_path = resolve_owner_handoff_manifest(
        root,
        state,
        args.handoff_manifest,
        route=route,
        from_owner=args.from_owner,
        to_owner=args.to_owner,
        reason=args.reason,
        expected_finding_ids=(active_batch or {}).get("finding_ids"),
    )
    state["engineering_owner_id"] = args.to_owner
    if route == "integration":
        state["integration_owner"] = args.to_owner
    elif route in state.get("owner_by_slice", {}):
        state["owner_by_slice"][route] = args.to_owner
        state["slices"][route]["owner_id"] = args.to_owner
    if active_batch:
        active_batch["owner_id"] = args.to_owner
        active_batch["returns_for_owner"] = 0
        for queued in state.get("remediation_queue", []):
            if queued.get("status") == "active" and queued.get("route") == route:
                queued["owner_id"] = args.to_owner
                queued["returns_for_owner"] = 0
    if state["phase"] == "owner_handoff_hold":
        state["phase"] = "engineering"
    state.setdefault("owner_transfers", []).append(
        {
            "from": args.from_owner,
            "to": args.to_owner,
            "reason": args.reason,
            "route": route,
            "manifest": manifest_path,
            "recorded_at": utc_now(),
        }
    )
    state["handoff_manifests"].append(
        {
            "kind": "owner_transfer",
            "route": route,
            "from_owner": args.from_owner,
            "to_owner": args.to_owner,
            "revision": state.get("revision"),
            "manifest": manifest_path,
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
    credit_manifest, credit_ids = resolve_review_credit_manifest(
        root,
        state,
        args.credit_manifest,
        reviewer_id=args.reviewer_id,
        review_mode="full_convergence",
        expected_lens=args.lens,
    )
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
        "credit_manifest": credit_manifest,
        "component_credit_ids": credit_ids,
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
    current_blocking = [item for item in current_findings if item.get("blocking")]
    audit_failed = any(run["status"] == "fail" for run in convergence["runs"])
    count_full_convergence_wave(state)
    convergence["decision"] = args.decision
    convergence["decision_report"] = report
    convergence["decided_at"] = utc_now()

    if args.decision == "pass":
        if current_blocking or audit_failed:
            raise PipelineError(
                "Convergence cannot pass while an audit failed or current blocking findings remain open"
            )
        try:
            require_pipeline_backlog_scope(
                root,
                findings,
                revision=args.revision,
                sources={"engineer", "convergence", "review", "qa"},
            )
        except BacklogError as exc:
            raise PipelineError(str(exc)) from exc
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
            state["product_revalidation"] = None
            state["phase"] = "review"
    else:
        if not current_blocking:
            raise PipelineError("Convergence rework requires registered current blocking findings")
        if args.revalidation == "full" and args.full_wave_trigger not in FULL_WAVE_TRIGGERS:
            raise PipelineError(
                "A new full convergence wave requires an actual architecture/lifecycle/"
                "ownership/public-contract/expanded-touchpoint/high-risk trigger"
            )
        if args.revalidation == "targeted" and args.full_wave_trigger:
            raise PipelineError("Targeted closure must not declare a full-wave trigger")
        if args.revalidation == "full":
            require_full_convergence_budget(
                state,
                list(convergence.get("slice_ids") or state["ordered_slices"]),
            )
        convergence["status"] = "failed"
        state["product_revalidation"] = {
            "mode": args.revalidation,
            "source": "convergence",
            "base_revision": state["revision"],
            "base_product_revision": state["product_revision"],
            "base_support_revision": state["support_revision"],
            "base_evidence_revision": state["evidence_revision"],
            "base_convergence_runs": list(convergence["runs"]),
            "base_review_runs": [],
            "finding_ids": [item["id"] for item in current_blocking],
            "slice_ids": list(convergence.get("slice_ids") or state["ordered_slices"]),
            "full_wave_trigger": args.full_wave_trigger,
        }
        build_remediation_queue(
            state, findings, [item["id"] for item in current_blocking]
        )
        if state.get("phase") != "owner_handoff_hold":
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
    credit_manifest, credit_ids = resolve_review_credit_manifest(
        root,
        state,
        args.credit_manifest,
        reviewer_id=args.reviewer_id,
        review_mode="final_whole_feature_review",
        require_composition_audit=True,
    )

    run = {
        "run_id": args.run_id,
        "reviewer_id": args.reviewer_id,
        "revision": args.revision,
        "product_revision": state["product_revision"],
        "support_revision": state["support_revision"],
        "evidence_revision": state["evidence_revision"],
        "status": args.status,
        "report": report,
        "credit_manifest": credit_manifest,
        "component_credit_ids": credit_ids,
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
    review_blocking = [item for item in review_findings if item.get("blocking")]

    if args.decision == "pass":
        if review_blocking or reviewer_failed:
            raise PipelineError(
                "Cannot pass immutable final Review while a reviewer failed or blocking Review findings remain open"
            )
        try:
            require_pipeline_backlog_scope(
                root,
                findings,
                revision=args.revision,
                sources={"engineer", "convergence", "review", "qa"},
            )
        except BacklogError as exc:
            raise PipelineError(str(exc)) from exc
        review["status"] = "passed"
        state["product_revalidation"] = None
        state["phase"] = "qa"
    else:
        if not review_blocking:
            raise PipelineError(
                "Rework decision requires at least one registered blocking Review finding"
            )
        review["status"] = "failed"
        state["qa"] = empty_qa_state()
        if args.rework_scope in {"evidence", "support", "recovery"}:
            if any(item.get("finding_kind") == "product" for item in review_blocking):
                raise PipelineError(
                    "Non-product recovery cannot contain a product finding"
                )
            state["recovery"] = {
                "status": "awaiting_remediation",
                "base_revision": state["revision"],
                "base_product_revision": state["product_revision"],
                "base_support_revision": state["support_revision"],
                "base_evidence_revision": state["evidence_revision"],
                "finding_ids": [item["id"] for item in review_blocking],
                "base_review_runs": list(review["runs"]),
                "remediation_owner_id": None,
                "remediation_runs": [],
                "verification_runs": [],
                "cycles": 0,
                "reason": args.reason,
            }
            state["phase"] = "evidence_recovery"
        else:
            if args.revalidation == "full" and args.full_wave_trigger not in FULL_WAVE_TRIGGERS:
                raise PipelineError(
                    "A new full convergence wave requires an actual architecture/lifecycle/"
                    "ownership/public-contract/expanded-touchpoint/high-risk trigger"
                )
            if args.revalidation == "targeted" and args.full_wave_trigger:
                raise PipelineError("Targeted closure must not declare a full-wave trigger")
            affected_slice_ids = sorted(
                {
                    route_for_finding(state, item)
                    for item in review_blocking
                    if route_for_finding(state, item) != "integration"
                }
            ) or list(state["ordered_slices"])
            if args.revalidation == "full":
                require_full_convergence_budget(state, affected_slice_ids)
            state["recovery"] = None
            state["product_revalidation"] = {
                "mode": args.revalidation,
                "source": "final_review",
                "base_revision": state["revision"],
                "base_product_revision": state["product_revision"],
                "base_support_revision": state["support_revision"],
                "base_evidence_revision": state["evidence_revision"],
                "base_review_runs": list(review["runs"]),
                "finding_ids": [item["id"] for item in review_blocking],
                "reason": args.reason,
                "slice_ids": affected_slice_ids,
                "full_wave_trigger": args.full_wave_trigger,
            }
            build_remediation_queue(
                state, findings, [item["id"] for item in review_blocking]
            )
            if state.get("phase") != "owner_handoff_hold":
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
    prior_reviewers.update(
        run["reviewer_id"] for run in closure.get("base_convergence_runs", [])
    )
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
    credit_manifest, credit_ids = resolve_review_credit_manifest(
        root,
        state,
        args.credit_manifest,
        reviewer_id=args.reviewer_id,
        review_mode="targeted_closure",
    )
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
        "credit_manifest": credit_manifest,
        "component_credit_ids": credit_ids,
        "frozen_finding_ids": list(closure.get("finding_ids", [])),
        "changed_impact_surface": closure.get("changed_impact_surface", {}),
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
    current_review_blocking = [
        item for item in current_review_findings if item.get("blocking")
    ]
    if args.status == "pass":
        if current_review_blocking or open_blocking(findings):
            raise PipelineError(
                "Targeted closure cannot pass while current or blocking findings remain open"
            )
        closure["status"] = "passed"
        if closure.get("return_phase") == "review":
            state["engineer_clean"] = {
                "source": "targeted_convergence_closure",
                "run_ids": [run["run_id"]],
                "revision": state["revision"],
                "product_revision": state["product_revision"],
                "support_revision": state["support_revision"],
                "evidence_revision": state["evidence_revision"],
                "audit_complete": True,
                "report": report,
                "coverage_manifest": state["coverage_manifest"],
                "recorded_at": utc_now(),
            }
            state["review"] = empty_review_state(
                state["required_reviews"],
                state["revision"],
                state["product_revision"],
                state["support_revision"],
                state["evidence_revision"],
            )
            state["product_revalidation"] = None
            state["phase"] = "review"
        else:
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
            state["phase"] = "qa"
        state["product_revalidation"] = None
        state["qa"] = empty_qa_state()
        state["qa_capability"] = empty_qa_capability_state()
    else:
        if not current_review_blocking:
            raise PipelineError(
                "A failed targeted closure Review must register at least one current blocking finding"
            )
        closure["status"] = "failed"
        if any(
            item.get("finding_kind") == "product"
            for item in current_review_blocking
        ):
            state["product_revalidation"] = {
                "mode": "targeted",
                "source": closure.get("source"),
                "base_revision": state["revision"],
                "base_product_revision": state["product_revision"],
                "base_support_revision": state["support_revision"],
                "base_evidence_revision": state["evidence_revision"],
                "base_review_runs": list(closure.get("base_review_runs", [])),
                "base_convergence_runs": list(
                    closure.get("base_convergence_runs", [])
                ),
                "finding_ids": [item["id"] for item in current_review_blocking],
                "slice_ids": list(
                    (state.get("product_revalidation") or {}).get(
                        "slice_ids", state["ordered_slices"]
                    )
                ),
                "full_wave_trigger": None,
            }
            build_remediation_queue(
                state,
                findings,
                [item["id"] for item in current_review_blocking],
            )
            if state.get("phase") != "owner_handoff_hold":
                state["phase"] = "engineering"
        else:
            state["recovery"] = {
                "status": "awaiting_remediation",
                "base_revision": state["revision"],
                "base_product_revision": state["product_revision"],
                "base_support_revision": state["support_revision"],
                "base_evidence_revision": state["evidence_revision"],
                "finding_ids": [item["id"] for item in current_review_blocking],
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
        "engineer": {"slice_engineering", "engineering"},
        "convergence": {"convergence"},
        "review": {"review", "recovery_review", "closure_review"},
        "qa": {"qa"},
    }
    if state["phase"] not in valid_phases[args.source]:
        raise PipelineError(
            f"{args.source} findings cannot be registered during phase {state['phase']}"
        )
    if args.source == "qa" and args.finding_kind != "product":
        raise PipelineError("QA may register only product findings")
    if args.cross_slice_root_cause and args.origin_slice:
        raise PipelineError(
            "Use either --origin-slice or --cross-slice-root-cause, not both"
        )
    if args.cross_slice_root_cause:
        origin_slice = None
        remediation_route = "integration"
    else:
        origin_slice = args.origin_slice or state.get("active_slice")
        if origin_slice is None and state.get("development_mode") == "single_owner":
            origin_slice = state["ordered_slices"][0]
        if origin_slice not in state.get("ordered_slices", []):
            raise PipelineError(
                "Finding requires a valid --origin-slice or --cross-slice-root-cause"
            )
        remediation_route = origin_slice
    item = {
        "id": args.id,
        "source": args.source,
        "finding_kind": args.finding_kind,
        "severity": args.severity,
        "scope_relation": args.scope_relation,
        "introduced_by_candidate": parse_explicit_bool(
            args.introduced_by_candidate, "introduced_by_candidate"
        ),
        "production_reachability": args.production_reachability,
        "blocks_acceptance_ids": sorted(set(args.blocks_acceptance_id or [])),
        "violates_required_invariant": parse_explicit_bool(
            args.violates_required_invariant, "violates_required_invariant"
        ),
        "required_invariant_evidence": args.required_invariant_evidence,
        "mandatory_core_acceptance_evidence_missing": parse_explicit_bool(
            args.mandatory_core_acceptance_evidence_missing,
            "mandatory_core_acceptance_evidence_missing",
        ),
        "test_can_miss_product_defect": parse_explicit_bool(
            args.test_can_miss_product_defect, "test_can_miss_product_defect"
        ),
        "deferred_reference": args.deferred_reference,
        "title": args.title,
        "evidence": args.evidence,
        "revision": args.revision,
        "origin_slice": origin_slice,
        "remediation_route": remediation_route,
        "status": "open",
        "created_at": utc_now(),
        "resolved_revision": None,
    }
    validate_finding_dimensions(state, item)
    findings["items"].append(item)
    deferred_director_decision = (
        (
            args.source == "review"
            and state["phase"] in {"review", "recovery_review", "closure_review"}
        )
        or (args.source == "convergence" and state["phase"] == "convergence")
        or (args.source == "qa" and state["phase"] == "qa")
    )
    if item["production_reachability"] == "unknown":
        state["finding_triage"] = {
            "finding_id": item["id"],
            "resume_phase": state["phase"],
            "started_at": utc_now(),
        }
        state["phase"] = "finding_triage"
    elif item["blocking"] and not deferred_director_decision:
        state["phase"] = "engineering"
    save_runtime(state_path, findings_path, state, findings)
    print(json.dumps({"added": args.id}, ensure_ascii=False))
    return 0


def cmd_triage_finding(args: argparse.Namespace) -> int:
    _, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    triage = state.get("finding_triage")
    if state.get("phase") != "finding_triage" or not triage:
        raise PipelineError("No bounded finding triage is pending")
    if triage.get("finding_id") != args.id:
        raise PipelineError(
            f"Finding triage is pending for {triage.get('finding_id')}, not {args.id}"
        )
    target = next((item for item in findings["items"] if item["id"] == args.id), None)
    if target is None or target.get("status") != "open":
        raise PipelineError(f"Open finding does not exist: {args.id}")
    if target.get("production_reachability") != "unknown":
        raise PipelineError("Only reachability=unknown may enter bounded finding triage")
    target["production_reachability"] = args.production_reachability
    target["triage_evidence"] = args.evidence
    target["triaged_at"] = utc_now()
    target["deferred_reference"] = args.deferred_reference
    validate_finding_dimensions(state, target)
    resume_phase = triage["resume_phase"]
    state["finding_triage"] = None
    state["phase"] = resume_phase
    deferred_director_decision = (
        target["source"] in {"convergence", "review", "qa"}
        and resume_phase in {"convergence", "review", "recovery_review", "closure_review", "qa"}
    )
    if target["blocking"] and not deferred_director_decision:
        state["phase"] = "engineering"
    save_runtime(state_path, findings_path, state, findings)
    print(
        json.dumps(
            {
                "triaged": args.id,
                "blocking": target["blocking"],
                "phase": state["phase"],
            },
            ensure_ascii=False,
        )
    )
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
    active_ids = set((state.get("active_remediation_batch") or {}).get("finding_ids", []))
    if args.id in active_ids:
        raise PipelineError(
            "An active remediation finding can be resolved only atomically by its owner completion"
        )
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
        if item["status"] == "open"
        and item["source"] == "review"
        and item.get("blocking") is True
    ]
    if not selected or selected != {item["id"] for item in open_review}:
        raise PipelineError(
            "Supply every and only open Review finding with --finding-id"
        )
    if any(item.get("finding_kind") not in {"evidence", "support"} for item in open_review):
        raise PipelineError(
            "Legacy recovery cannot infer finding_kind; selected findings must already be "
            "normalized as evidence or support under schema 8"
        )
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
        item.get("status") != "open" or item.get("finding_kind") == "product"
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
            if item.get("finding_kind") == "product"
        ]
        if open_product:
            recovery["status"] = "product_defect"
            state["recovery"] = recovery
            build_remediation_queue(
                state, findings, [item["id"] for item in open_product]
            )
            if state.get("phase") != "owner_handoff_hold":
                state["phase"] = "engineering"
            save_runtime(state_path, findings_path, state, findings)
            return cmd_status(args)
        open_evidence = [
            item
            for item in findings["items"]
            if item.get("status") == "open"
            and item.get("finding_kind") in {"support", "evidence"}
            and item.get("blocking") is True
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
    qa_capability = state.get("qa_capability", {})
    capability_exact = qa_capability.get("revision") == args.revision
    if args.status in QA_GATE_STATUSES:
        failed_statuses = set(qa_capability.get("capabilities", {}).values())
        if (
            not capability_exact
            or qa_capability.get("status") != "blocked"
            or args.status not in failed_statuses
            or not qa_capability.get("minimum_resume_actions")
        ):
            raise PipelineError(
                "BLOCKED_USER/BLOCKED_ENVIRONMENT/ERROR_TEST requires a recorded failed "
                "capability probe on the exact revision and a minimum resume action"
            )
    elif not capability_exact or qa_capability.get("status") != "ready":
        raise PipelineError(
            "QA must not spawn before the complete exact-revision capability probe passes"
        )
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
        and item.get("finding_kind") == "product"
        and item.get("blocking") is True
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
        "capability_probe_id": qa_capability.get("probe_id"),
        "minimum_resume_actions": qa_capability.get("minimum_resume_actions", {}),
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
        "capability_probe_id": qa_capability.get("probe_id"),
        "minimum_resume_actions": qa_capability.get("minimum_resume_actions", {}),
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
        build_remediation_queue(
            state, findings, [item["id"] for item in qa_product_findings]
        )
        if state.get("phase") != "owner_handoff_hold":
            state["phase"] = "engineering"
    else:
        matching_probe_gate = next(
            (
                gate
                for gate in state.get("gates", [])
                if gate.get("status") == "open"
                and gate.get("origin") == "qa_capability_probe"
                and gate.get("category") == effective_status
                and gate.get("revision") == args.revision
            ),
            None,
        )
        gate_record = {
                "id": f"qa:{args.run_id}",
                "phase": "qa",
                "category": effective_status,
                "revision": args.revision,
                "reason": args.reason,
                "pending_scenarios": pending,
                "report": report,
                "capability_probe_id": qa_capability.get("probe_id"),
                "minimum_resume_actions": qa_capability.get(
                    "minimum_resume_actions", {}
                ),
                "status": "open",
                "created_at": utc_now(),
            }
        if matching_probe_gate:
            matching_probe_gate["qa_run_id"] = args.run_id
            matching_probe_gate["qa_report"] = report
        else:
            state["gates"].append(gate_record)
        state["phase"] = "qa"

    record_worker(state, "runtime_qa", args.worker_id)
    if state["phase"] == "ready":
        state["worker_budget"]["status"] = "running"
        state["worker_budget"]["reason"] = None
    save_runtime(state_path, findings_path, state, findings)
    return cmd_status(args)


def readiness_reasons(state: dict[str, Any], findings: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if source_drift(state):
        reasons.append("approved PRD/spec/development plan bytes changed")
    if state.get("development_mode") == "sequential_slices" and not all_slices_sealed(state):
        reasons.append("not every approved development-plan slice has a sealed exact-revision handoff")
    if state.get("remediation_queue") and any(
        item.get("status") != "completed" for item in state["remediation_queue"]
    ):
        reasons.append("origin-routed remediation batches remain incomplete")
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
        reasons.append("controller-classified blocking findings remain unresolved")
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
    qa_capability = state.get("qa_capability", {})
    if (
        qa_capability.get("status") != "ready"
        or qa_capability.get("revision") != revision
    ):
        reasons.append("exact-revision QA capability probe has not passed")
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
    init.add_argument("--plan", required=True)
    init.add_argument("--plan-sha256", required=True)
    init.add_argument("--base-revision", required=True)
    init.add_argument("--integration-owner")
    init.add_argument("--slice")
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
        "--max-convergence-waves",
        type=int,
        choices=(DEFAULT_MAX_CONVERGENCE_WAVES,),
        default=DEFAULT_MAX_CONVERGENCE_WAVES,
        help="Compatibility option; the full convergence hard maximum is fixed at 2",
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

    research = commands.add_parser("slice-research-complete")
    add_common_project_root(research)
    research.add_argument("--slice-id", required=True)
    research.add_argument("--base-revision", required=True)
    research.add_argument("--owner-id", required=True)
    research.add_argument("--bundle", action="append", required=True)
    research.set_defaults(handler=cmd_slice_research_complete)

    research_not_required = commands.add_parser("slice-research-not-required")
    add_common_project_root(research_not_required)
    research_not_required.add_argument("--slice-id", required=True)
    research_not_required.add_argument("--base-revision", required=True)
    research_not_required.add_argument("--owner-id", required=True)
    research_not_required.add_argument("--reason", required=True)
    research_not_required.set_defaults(handler=cmd_slice_research_not_required)

    scope_check = commands.add_parser("slice-scope-check")
    add_common_project_root(scope_check)
    scope_check.add_argument("--slice-id", required=True)
    scope_check.add_argument("--base-revision", required=True)
    scope_check.add_argument("--owner-id", required=True)
    scope_check.set_defaults(handler=cmd_slice_scope_check)

    rebaseline_scope = commands.add_parser("rebaseline-scope")
    add_common_project_root(rebaseline_scope)
    rebaseline_scope.add_argument("--plan-sha256", required=True)
    rebaseline_scope.add_argument("--user-scope-approval", required=True)
    rebaseline_scope.set_defaults(handler=cmd_rebaseline_scope)

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
    engineer.add_argument("--slice-id")
    engineer.add_argument("--base-revision")
    engineer.add_argument("--handoff-manifest")
    engineer.add_argument("--change-manifest")
    engineer.add_argument("--diff-summary")
    engineer.add_argument("--machine-checks", choices=("pass", "fail"), required=True)
    engineer.add_argument("--report", required=True)
    engineer.add_argument("--coverage-manifest", required=True)
    engineer.add_argument(
        "--production-change-scope",
        choices=("none", "local", "architectural"),
        required=True,
    )
    engineer.add_argument("--production-files-changed", type=int)
    engineer.add_argument("--production-lines-changed", type=int)
    engineer.add_argument("--scope-approval")
    engineer.add_argument("--resolved-finding", action="append")
    engineer.add_argument(
        "--audit-complete",
        action="store_true",
        required=True,
        help="Assert that delegated bounded research, batch remediation, checks, and scope resweep finished",
    )
    engineer.set_defaults(handler=cmd_engineer_complete)

    transfer_owner = commands.add_parser("transfer-engineering-owner")
    add_common_project_root(transfer_owner)
    transfer_owner.add_argument("--from-owner", required=True)
    transfer_owner.add_argument("--to-owner", required=True)
    transfer_owner.add_argument("--reason", required=True)
    transfer_owner.add_argument("--slice-id")
    transfer_owner.add_argument("--handoff-manifest", required=True)
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
    convergence_audit.add_argument("--credit-manifest", required=True)
    convergence_audit.set_defaults(handler=cmd_convergence_audit_complete)

    convergence_finalize = commands.add_parser("convergence-finalize")
    add_common_project_root(convergence_finalize)
    convergence_finalize.add_argument("--revision", required=True)
    convergence_finalize.add_argument("--decision", choices=("pass", "rework"), required=True)
    convergence_finalize.add_argument("--report", required=True)
    convergence_finalize.add_argument(
        "--revalidation", choices=("targeted", "full"), default="targeted"
    )
    convergence_finalize.add_argument(
        "--full-wave-trigger", choices=tuple(sorted(FULL_WAVE_TRIGGERS))
    )
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
    review.add_argument("--credit-manifest", required=True)
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
    review_finalize.add_argument(
        "--full-wave-trigger", choices=tuple(sorted(FULL_WAVE_TRIGGERS))
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
    closure_review.add_argument("--credit-manifest", required=True)
    closure_review.set_defaults(handler=cmd_closure_review_complete)

    add_finding = commands.add_parser("add-finding")
    add_common_project_root(add_finding)
    add_finding.add_argument("--id", required=True)
    add_finding.add_argument(
        "--source", choices=("engineer", "convergence", "review", "qa"), required=True
    )
    add_finding.add_argument(
        "--finding-kind",
        "--kind",
        dest="finding_kind",
        choices=tuple(sorted(FINDING_KINDS)),
        required=True,
    )
    add_finding.add_argument("--severity", choices=("critical", "major", "minor"), required=True)
    add_finding.add_argument(
        "--scope-relation", choices=tuple(sorted(SCOPE_RELATIONS)), required=True
    )
    add_finding.add_argument(
        "--introduced-by-candidate", choices=("true", "false"), required=True
    )
    add_finding.add_argument(
        "--production-reachability",
        choices=tuple(sorted(PRODUCTION_REACHABILITY)),
        required=True,
    )
    add_finding.add_argument("--blocks-acceptance-id", action="append", default=[])
    add_finding.add_argument(
        "--violates-required-invariant", choices=("true", "false"), required=True
    )
    add_finding.add_argument("--required-invariant-evidence")
    add_finding.add_argument(
        "--mandatory-core-acceptance-evidence-missing",
        choices=("true", "false"),
        required=True,
    )
    add_finding.add_argument(
        "--test-can-miss-product-defect", choices=("true", "false"), required=True
    )
    add_finding.add_argument("--deferred-reference")
    add_finding.add_argument("--title", required=True)
    add_finding.add_argument("--evidence", required=True)
    add_finding.add_argument("--revision", required=True)
    add_finding.add_argument("--origin-slice")
    add_finding.add_argument("--cross-slice-root-cause", action="store_true")
    add_finding.set_defaults(handler=cmd_add_finding)

    triage_finding = commands.add_parser("triage-finding")
    add_common_project_root(triage_finding)
    triage_finding.add_argument("--id", required=True)
    triage_finding.add_argument(
        "--production-reachability",
        choices=tuple(sorted(PRODUCTION_REACHABILITY - {"unknown"})),
        required=True,
    )
    triage_finding.add_argument("--evidence", required=True)
    triage_finding.add_argument("--deferred-reference")
    triage_finding.set_defaults(handler=cmd_triage_finding)

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

    qa_probe = commands.add_parser("qa-capability-probe")
    add_common_project_root(qa_probe)
    qa_probe.add_argument("--revision", required=True)
    qa_probe.add_argument("--probe-id", required=True)
    qa_probe.add_argument("--capability", action="append", required=True)
    qa_probe.add_argument("--minimum-resume-action", action="append")
    qa_probe.add_argument("--report", required=True)
    qa_probe.set_defaults(handler=cmd_qa_capability_probe)

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
