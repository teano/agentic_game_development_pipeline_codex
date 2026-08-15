#!/usr/bin/env python3
"""Deterministic state controller for the agentic GameDev pipeline."""

from __future__ import annotations

import argparse
import contextlib
import copy
import difflib
import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_capability_contract_path = (
    Path(__file__).resolve().parents[2]
    / "gamedev-development-plan"
    / "scripts"
    / "capability_contract.py"
)
_capability_contract_spec = importlib.util.spec_from_file_location(
    "gamedev_capability_contract", _capability_contract_path
)
if _capability_contract_spec is None or _capability_contract_spec.loader is None:
    raise RuntimeError("Cannot load the canonical capability contract")
_capability_contract = importlib.util.module_from_spec(_capability_contract_spec)
_capability_contract_spec.loader.exec_module(_capability_contract)
CAPABILITY_ID_PATTERN = _capability_contract.CAPABILITY_ID_PATTERN
parse_capability_ids = _capability_contract.parse_capability_ids

_acceptance_contract_path = (
    Path(__file__).resolve().parents[3] / "scripts" / "acceptance_contract.py"
)
_acceptance_contract_spec = importlib.util.spec_from_file_location(
    "gamedev_acceptance_contract", _acceptance_contract_path
)
if _acceptance_contract_spec is None or _acceptance_contract_spec.loader is None:
    raise RuntimeError("Cannot load the canonical acceptance contract")
_acceptance_contract = importlib.util.module_from_spec(_acceptance_contract_spec)
_acceptance_contract_spec.loader.exec_module(_acceptance_contract)
parse_acceptance_ids = _acceptance_contract.parse_acceptance_ids
extract_literal_acceptance_ids = _acceptance_contract.extract_literal_acceptance_ids
derive_prd_acceptance_inventory = _acceptance_contract.derive_prd_acceptance_inventory
require_known_acceptance_ids = _acceptance_contract.require_known_acceptance_ids

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
DIRECTOR_CHECKPOINT = Path(STATE_DIR) / "director-checkpoint.json"
SCHEMA_VERSION = 10
LEGACY_SCHEMA_VERSION = 9
CONTRACT_VERSION = "2026-08-14-scoped-digest-snapshots-v1"
LEGACY_CONTRACT_VERSION = "2026-08-11-role-artifacts-coverage-docs-v2"
PREFLIGHT_PROOF_VERSION = 1
ASSIGNED_GOAL_EFFECT_PREFIX = "assigned_goal_effect:"
ASSIGNED_ACCEPTANCE_EVIDENCE_PREFIX = "assigned_acceptance_evidence:"
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
DEFAULT_REQUIRED_CONVERGENCE_AUDITS = 1
DEFAULT_MAX_CONVERGENCE_WAVES = 2
DEFAULT_MAX_WORKERS = 14
DEFAULT_MAX_FULL_REVIEW_WAVES = 2
DEFAULT_MAX_FULL_CONVERGENCE_WAVES_PER_SLICE = 2
CONVERGENCE_LENSES = {
    "persistence-lifecycle",
    "config-security-capacity",
    "integration-runtime-docs",
}
REVIEW_FINDING_PHASES = {"review", "recovery_review", "closure_review", "documentation_review"}
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
FULL_WAVE_TRIGGERS = {
    "architecture",
    "lifecycle",
    "ownership",
    "public_contract",
    "expanded_shared_touchpoint",
    "high_risk_surface",
}
# There is no engine/tool capability that every supported project universally
# needs.  Runtime requirements are approved explicitly by the plan and, at QA,
# narrowed further to the registered manual identities.
UNIVERSAL_CAPABILITY_NAMES: frozenset[str] = frozenset()
QA_CAPABILITY_BLOCKING_STATUSES = {
    "blocked_user",
    "blocked_environment",
    "error_test",
}
WRITE_ROLES = {
    "decision_recorder",
    "engineer",
    "documentation_finisher",
    "recovery_remediator",
}
CAPSULE_ROLES = WRITE_ROLES | {
    "reviewer",
}
LEASE_PHASES = {
    "decision_recorder": {"decision_recording"},
    "engineer": {"slice_engineering", "engineering"},
    "documentation_finisher": {"normative_documentation", "derived_documentation"},
    "recovery_remediator": {"evidence_recovery"},
}
CAPSULE_PHASES = {
    "decision_recorder": {"decision_recording"},
    "engineer": {"slice_engineering", "engineering"},
    "documentation_finisher": {
        "normative_documentation",
        "derived_documentation",
    },
    "reviewer": {
        "convergence",
        "review",
        "closure_review",
        "recovery_review",
        "documentation_review",
        "qa",
    },
    "recovery_remediator": {"evidence_recovery"},
}
CAPSULE_ACTIVATION_PHASES = {
    "decision_recording": {
        "decision_recording",
        "preflight",
        "slice_research",
        "slice_coverage_planning",
    },
    "normative_documentation": {
        "normative_documentation",
        "implementation_complete",
    },
}
CONTEXT_LIMIT_NAMES = (
    "max_authority_files",
    "max_evidence_files",
    "max_total_files",
    "max_payload_bytes",
    "max_estimated_tokens",
)
CONTEXT_METRIC_SCOPE = "capsule_plus_referenced_files"
LEASE_SNAPSHOT_SCHEMA = 4
LEASE_SNAPSHOT_FORMAT = "sha256-digest-lines-v1"
MAX_SOURCE_SNAPSHOT_FILES = 12_000
MAX_SOURCE_FILE_BYTES = 64 * 1024 * 1024
MAX_LINE_PROOF_FILES = 256
MAX_LINE_PROOF_LINES = 100_000
MAX_LEASE_SNAPSHOT_BYTES = 12 * 1024 * 1024
GENERATED_OUTPUT_POLICY_PATH = ".agentic-generated-output-policy.json"
_COMMAND_SOURCE_INVENTORY: dict[Path, list[tuple[str, bool]]] | None = None


class PipelineError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def path_is_reparse_point(path: Path) -> bool:
    try:
        stat = path.lstat()
    except FileNotFoundError:
        return False
    return path.is_symlink() or bool(
        getattr(stat, "st_file_attributes", 0) & 0x400  # FILE_ATTRIBUTE_REPARSE_POINT
    )


def resolve_runtime_control_path(root: Path, relative: str) -> Path:
    """Resolve a controller path without crossing symlink/junction/reparse components."""
    logical = Path(relative)
    if logical.is_absolute() or ".." in logical.parts:
        raise PipelineError(f"Unsafe runtime controller path: {relative}")
    candidate = root / logical
    try:
        candidate.resolve(strict=False).relative_to(root)
    except (OSError, ValueError) as exc:
        raise PipelineError(
            f"Runtime controller path escapes the project root: {relative}"
        ) from exc
    current = root
    for part in logical.parts:
        current = current / part
        if current.exists() or current.is_symlink():
            if path_is_reparse_point(current):
                raise PipelineError(
                    "Runtime controller path crosses a symlink/junction/reparse point: "
                    + current.relative_to(root).as_posix()
                )
    return candidate


def runtime_paths(project_root: str) -> tuple[Path, Path, Path]:
    root = Path(project_root).resolve()
    if not root.is_dir():
        raise PipelineError(f"Project root does not exist: {root}")
    state_path = resolve_runtime_control_path(root, f"{STATE_DIR}/state.json")
    findings_path = resolve_runtime_control_path(root, f"{STATE_DIR}/findings.json")
    resolve_runtime_control_path(root, f"{STATE_DIR}/runtime.lock")
    return root, state_path, findings_path


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
    parent: str | None = None
    for raw_line in parts[1].splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#") or ":" not in raw_line:
            continue
        indentation = len(raw_line) - len(raw_line.lstrip())
        key, value = raw_line.strip().split(":", 1)
        value = value.strip().strip('"\'')
        if indentation == 0:
            parent = key if not value else None
            if value:
                result[key] = value
        elif parent and value:
            result[f"{parent}.{key}"] = value
    return result


_PLAN_CONTRACT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "development_plan_contract.py"
_PLAN_CONTRACT_SPEC = importlib.util.spec_from_file_location(
    "gamedev_runtime_development_plan_contract", _PLAN_CONTRACT_PATH
)
if _PLAN_CONTRACT_SPEC is None or _PLAN_CONTRACT_SPEC.loader is None:
    raise RuntimeError("Cannot load the shared development-plan contract")
_PLAN_CONTRACT = importlib.util.module_from_spec(_PLAN_CONTRACT_SPEC)
_PLAN_CONTRACT_SPEC.loader.exec_module(_PLAN_CONTRACT)


def authority_trace(
    meta: dict[str, str], flat_prefix: str, nested_names: tuple[str, ...]
) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for field in ("path", "revision", "sha256"):
        value = meta.get(f"{flat_prefix}_{field}")
        for nested_name in nested_names:
            value = value or meta.get(f"{nested_name}.{field}")
        result[field] = value
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
    try:
        path.relative_to(root)
    except ValueError as error:
        raise PipelineError(f"{label} must stay inside the project root: {path}") from error
    if not path.is_file():
        raise PipelineError(f"{label} does not exist: {path}")
    return path


def require_feature_documents(
    root: Path, feature: str, requirements: Path, spec: Path
) -> tuple[dict[str, str], dict[str, str], frozenset[str]]:
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
        "path": relative_requirements,
        "revision": requirements_meta["revision"],
        "sha256": file_sha256(requirements),
    }
    actual_trace = authority_trace(spec_meta, "source_prd", ("product_authority",))
    for field, expected in expected_trace.items():
        if actual_trace.get(field) != expected:
            raise PipelineError(
                f"technical-specification.md has stale product authority {field}: "
                f"expected {expected!r}, got {actual_trace.get(field)!r}"
            )
    try:
        acceptance_inventory = derive_prd_acceptance_inventory(
            requirements.read_text(encoding="utf-8"), label="approved PRD"
        )
    except ValueError as exc:
        raise PipelineError(str(exc)) from exc
    return requirements_meta, spec_meta, acceptance_inventory


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
            if key in scalar:
                raise PipelineError(f"{slice_id} Scope Contract repeats field: {key}")
            scalar[key] = value.strip()
    required = {
        "acceptance_ids",
        "editable_paths",
        "excluded_components",
        "excluded_paths",
        "max_product_files",
        "max_product_lines_changed",
        "verification_scope",
    }
    missing = sorted(key for key in required if not scalar.get(key))
    if missing:
        raise PipelineError(f"{slice_id} Scope Contract lacks: {', '.join(missing)}")
    try:
        acceptance_ids = parse_acceptance_ids(
            scalar["acceptance_ids"],
            label=f"{slice_id} Scope Contract acceptance_ids",
        )
    except ValueError as exc:
        raise PipelineError(str(exc)) from exc
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
    try:
        material_permissions = _PLAN_CONTRACT.parse_planned_material_permissions(
            scope,
            label=f"{slice_id} Scope Contract",
            editable_paths=editable_paths,
            shared_touchpoints=touchpoints,
        )
    except _PLAN_CONTRACT.PlanContractError as exc:
        raise PipelineError(str(exc)) from exc
    result = {
        "acceptance_ids": acceptance_ids,
        "editable_paths": editable_paths,
        "shared_touchpoints": touchpoints,
        "planned_material_permissions": material_permissions,
        "excluded_components": comma_values(scalar["excluded_components"]),
        "excluded_paths": excluded_paths,
        "max_product_files": max_files,
        "max_product_lines_changed": max_lines,
        "verification_scope": scalar["verification_scope"],
    }
    return result


def plan_slice_blocks(
    text: str, prd_acceptance_inventory: frozenset[str]
) -> list[dict[str, Any]]:
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
        try:
            declared_acceptance_ids = set(
                extract_literal_acceptance_ids(
                    requirements, label=f"{slice_id} Requirements"
                )
            )
        except ValueError as exc:
            raise PipelineError(str(exc)) from exc
        if not declared_acceptance_ids:
            raise PipelineError(
                f"{slice_id} Requirements must contain at least one literal PRD-AC-* ID"
            )
        try:
            require_known_acceptance_ids(
                declared_acceptance_ids,
                prd_acceptance_inventory,
                label=f"{slice_id} Requirements",
            )
        except ValueError as exc:
            raise PipelineError(str(exc)) from exc
        scope_contract = parse_slice_scope(slice_id, content)
        try:
            require_known_acceptance_ids(
                set(scope_contract["acceptance_ids"]),
                prd_acceptance_inventory,
                label=f"{slice_id} Scope Contract acceptance_ids",
            )
        except ValueError as exc:
            raise PipelineError(str(exc)) from exc
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


def markdown_sections(text: str, level: int) -> dict[str, str]:
    marker = "#" * level
    pattern = re.compile(
        rf"(?ms)^{re.escape(marker)} ([^\r\n]+)\r?\n(.*?)(?=^{re.escape(marker)} |\Z)"
    )
    result: dict[str, str] = {}
    for name, content in pattern.findall(text):
        if name in result:
            raise PipelineError(f"Development plan repeats section: {name}")
        result[name] = content.strip()
    return result


def contract_scalars(section: str, label: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in re.findall(r"(?m)^\s*-\s*([a-z_]+):\s*(.+?)\s*$", section):
        if key in result:
            raise PipelineError(f"{label} repeats field: {key}")
        result[key] = value.strip()
    return result


def parse_runtime_research_contract(section: str, label: str) -> dict[str, Any]:
    rows = re.findall(
        r"(?m)^\s*-\s*(RESEARCH-\d{3})\s*\|\s*(.+)$",
        section,
    )
    not_required = re.findall(
        r"(?m)^\s*-\s*research_not_required\s*\|\s*reason=(\S.*?)\s*$",
        section,
    )
    if rows and not_required:
        raise PipelineError(
            f"{label} must choose approved briefs or research_not_required, not both"
        )
    if not_required:
        if len(not_required) != 1:
            raise PipelineError(f"{label} must contain exactly one research_not_required row")
        return {"mode": "not_required", "reason": not_required[0]}
    if not 1 <= len(rows) <= 3:
        raise PipelineError(f"{label} must contain one to three approved Research Briefs")
    briefs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for brief_id, fields_text in rows:
        if brief_id in seen:
            raise PipelineError(f"{label} repeats Research Brief ID {brief_id}")
        seen.add(brief_id)
        fields = {
            part.split("=", 1)[0].strip(): part.split("=", 1)[1].strip()
            for part in fields_text.split("|")
            if "=" in part
        }
        required = {"question", "paths", "exclusions", "evidence", "stop"}
        if set(fields) != required or any(not fields[key] for key in required):
            raise PipelineError(
                f"{label} {brief_id} must contain exactly question, paths, exclusions, evidence, and stop"
            )
        briefs.append(
            {
                "brief_id": brief_id,
                "question": fields["question"],
                "seed_paths": comma_values(fields["paths"]),
                "exclusions": comma_values(fields["exclusions"]),
                "requested_evidence": comma_values(fields["evidence"]),
                "stop_condition": fields["stop"],
            }
        )
    return {"mode": "required", "briefs": briefs}


def runtime_plan_contracts(
    text: str,
    slices: list[dict[str, Any]],
    prd_acceptance_inventory: frozenset[str],
) -> dict[str, Any]:
    body = text.split("---", 2)[2] if text.startswith("---") else text
    global_sections = markdown_sections(body, 2)
    global_budget_raw = contract_scalars(global_sections["Context Budget"], "Context Budget")
    global_budget = {key: int(global_budget_raw[key]) for key in CONTEXT_LIMIT_NAMES}
    if global_budget_raw.get("metric_scope") != CONTEXT_METRIC_SCOPE:
        raise PipelineError(
            f"Context Budget metric_scope must be {CONTEXT_METRIC_SCOPE}"
        )
    slice_sections = {
        slice_id: markdown_sections(content, 3)
        for slice_id, content in re.findall(
            r"(?ms)^## Slice (SLICE-\d{3})\r?\n(.*?)(?=^## |\Z)", body
        )
    }
    per_slice: dict[str, Any] = {}
    for item in slices:
        slice_id = item["id"]
        sections = slice_sections[slice_id]
        budget_raw = contract_scalars(
            sections["Context Capsule Budget"], f"{slice_id} Context Capsule Budget"
        )
        if budget_raw.get("metric_scope") != CONTEXT_METRIC_SCOPE:
            raise PipelineError(
                f"{slice_id} Context Capsule Budget metric_scope must be "
                f"{CONTEXT_METRIC_SCOPE}"
            )
        per_slice[slice_id] = {
            "context_budget": {key: int(budget_raw[key]) for key in CONTEXT_LIMIT_NAMES},
            "context_metric_scope": budget_raw["metric_scope"],
            "coverage": _PLAN_CONTRACT.parse_slice_coverage_contract(
                sections["Coverage Contract"], label=f"{slice_id} Coverage Contract"
            ),
            "documentation": _PLAN_CONTRACT.parse_exact_contract_rows(
                sections["Documentation Contract"],
                label=f"{slice_id} Documentation Contract",
                scalar_keys={
                    "normative_pre_review_paths", "derived_post_qa_paths",
                    "decision_ids", "evidence_sources",
                },
                path_or_policy_keys={
                    "normative_pre_review_paths", "derived_post_qa_paths"
                },
            ),
            "research": parse_runtime_research_contract(
                sections["Research Briefs"], f"{slice_id} Research Briefs"
            ),
        }
        coverage_acceptance = per_slice[slice_id]["coverage"].get("acceptance_ids", "")
        try:
            parsed_coverage_acceptance = parse_acceptance_ids(
                coverage_acceptance,
                label=f"{slice_id} Coverage Contract acceptance_ids",
            )
        except ValueError as exc:
            raise PipelineError(str(exc)) from exc
        try:
            require_known_acceptance_ids(
                set(parsed_coverage_acceptance),
                prd_acceptance_inventory,
                label=f"{slice_id} Coverage Contract acceptance_ids",
            )
        except ValueError as exc:
            raise PipelineError(str(exc)) from exc
        if set(parsed_coverage_acceptance) != set(item["scope_contract"]["acceptance_ids"]):
            raise PipelineError(
                f"{slice_id} Coverage Contract acceptance_ids must exactly equal "
                "Scope Contract acceptance_ids"
            )
    return {
        "context_budget": global_budget,
        "context_metric_scope": global_budget_raw["metric_scope"],
        "coverage_strategy": _PLAN_CONTRACT.parse_coverage_strategy(
            global_sections["Coverage Strategy"]
        ),
        "documentation_strategy": _PLAN_CONTRACT.parse_exact_contract_rows(
            global_sections["Documentation Strategy"],
            label="Documentation Strategy",
            scalar_keys={"normative_pre_review", "derived_post_qa"},
            optional_keys={"source_rule"},
            path_or_policy_keys={"normative_pre_review", "derived_post_qa"},
        ),
        "slices": per_slice,
    }


def documentation_policy_reference(state: dict[str, Any], lane: str) -> str:
    global_key = "normative_pre_review" if lane == "normative" else "derived_post_qa"
    slice_key = (
        "normative_pre_review_paths"
        if lane == "normative"
        else "derived_post_qa_paths"
    )
    values = [state["plan_contracts"]["documentation_strategy"].get(global_key, "")]
    values.extend(
        contract["documentation"].get(slice_key, "")
        for contract in state["plan_contracts"]["slices"].values()
    )
    references: list[str] = []
    for value in values:
        match = re.fullmatch(r"not_required\s*\|\s*policy=(\S(?:.*\S)?)", value)
        if not match:
            raise PipelineError(
                f"Approved plan does not authorize {lane} documentation as not_required"
            )
        references.append(match.group(1))
    if len(set(references)) != 1:
        raise PipelineError(
            f"Approved plan has inconsistent {lane} documentation policy authorities"
        )
    return references[0]


def validate_plan_with_shared_planner(root: Path, planning_state: dict[str, Any]) -> None:
    module_path = (
        Path(__file__).resolve().parents[2]
        / "gamedev-development-plan"
        / "scripts"
        / "development_plan_state.py"
    )
    spec = importlib.util.spec_from_file_location("gamedev_development_plan_state", module_path)
    if spec is None or spec.loader is None:
        raise PipelineError("Cannot load the development-plan validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        module.validate_plan(root, planning_state, required_status="approved")
    except module.DevelopmentPlanError as exc:
        raise PipelineError(str(exc)) from exc


def require_development_plan(
    root: Path,
    feature: str,
    requirements: Path,
    spec: Path,
    supplied_plan: str | None,
    supplied_sha256: str | None,
    prd_acceptance_inventory: frozenset[str],
) -> dict[str, Any]:
    if not supplied_plan:
        raise PipelineError("Approved development plan path is required")
    plan = resolve_project_file(root, supplied_plan, "Approved development plan")
    try:
        plan_meta, _ = _PLAN_CONTRACT.parse_development_plan_frontmatter(
            plan.read_text(encoding="utf-8"), label="development-plan.md"
        )
    except _PLAN_CONTRACT.PlanContractError as exc:
        raise PipelineError(str(exc)) from exc
    if plan_meta["status"] != "approved":
        raise PipelineError("development-plan.md must have status: approved")
    if plan_meta.get("feature") != feature:
        raise PipelineError("development-plan.md feature does not match the pipeline feature")
    if plan_meta.get("writer_strategy") != "sequential":
        raise PipelineError("development-plan.md must declare writer_strategy: sequential")
    decision_ledger_path = plan_meta.get("decision_ledger_path")
    if not decision_ledger_path:
        raise PipelineError("development-plan.md must declare decision_ledger_path")
    decision_ledger_path = scope_path(decision_ledger_path, "decision ledger")
    mode = plan_meta.get("mode")
    if mode not in {"single_owner", "sequential_slices"}:
        raise PipelineError("development-plan.md mode must be single_owner or sequential_slices")
    trace_checks = (
        (
            "product authority",
            authority_trace(plan_meta, "source_prd", ("product_authority",)),
            {
                "path": requirements.relative_to(root).as_posix(),
                "revision": parse_frontmatter(requirements, "Product requirements")["revision"],
                "sha256": file_sha256(requirements),
            },
        ),
        (
            "specification authority",
            authority_trace(
                plan_meta,
                "source_spec",
                ("specification_authority", "technical_authority"),
            ),
            {
                "path": spec.relative_to(root).as_posix(),
                "revision": parse_frontmatter(spec, "Technical specification").get("revision"),
                "sha256": file_sha256(spec),
            },
        ),
    )
    for label, actual, expected_trace in trace_checks:
        for field, expected in expected_trace.items():
            if actual.get(field) != expected:
                raise PipelineError(
                    f"development-plan.md has stale {label} {field}: "
                    f"expected {expected!r}, got {actual.get(field)!r}"
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
        or (
            planning_state.get("prd", {}).get("path") is not None
            and planning_state.get("prd", {}).get("path")
            != requirements.relative_to(root).as_posix()
        )
        or planning_state.get("prd", {}).get("sha256") != file_sha256(requirements)
        or (
            planning_state.get("specification", {}).get("path") is not None
            and planning_state.get("specification", {}).get("path")
            != spec.relative_to(root).as_posix()
        )
        or planning_state.get("specification", {}).get("sha256") != file_sha256(spec)
        or planning_state.get("decision_ledger_path") != decision_ledger_path
    ):
        raise PipelineError(
            "development-plan-state.json does not prove approval of the exact current plan/PRD/spec"
        )
    validate_plan_with_shared_planner(root, planning_state)
    plan_text = plan.read_text(encoding="utf-8")
    slices = plan_slice_blocks(plan_text, prd_acceptance_inventory)
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
    try:
        contracts = runtime_plan_contracts(plan_text, slices, prd_acceptance_inventory)
    except _PLAN_CONTRACT.PlanContractError as exc:
        raise PipelineError(str(exc)) from exc
    return {
        "path": str(plan),
        "sha256": approved_hash,
        "mode": mode,
        "slices": slices,
        "decision_ledger_path": decision_ledger_path,
        "contracts": contracts,
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
    policy = state.get("generated_output_policy")
    if isinstance(policy, dict):
        policy_path = Path(state["project_root"]) / policy["path"]
        if not policy_path.is_file():
            drift.append("generated-output policy file is missing")
        elif file_sha256(policy_path) != policy["sha256"]:
            drift.append("generated-output policy changed after pipeline initialization")
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
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    )
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def serialized_json_sha256(value: dict[str, Any]) -> str:
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@contextmanager
def runtime_write_lock(path: Path, timeout_seconds: float = 5.0):
    """Serialize runtime commits; the OS releases the lock after a crashed process."""
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("a+b")
    stream.seek(0, os.SEEK_END)
    if stream.tell() == 0:
        stream.write(b"\0")
        stream.flush()
    deadline = time.monotonic() + timeout_seconds
    locked = False
    try:
        while not locked:
            try:
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:  # pragma: no cover - exercised by non-Windows CI
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise PipelineError(
                        f"Timed out waiting for runtime controller lock: {path}"
                    ) from exc
                time.sleep(0.05)
        yield
    finally:
        if locked:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:  # pragma: no cover - exercised by non-Windows CI
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()


def resolve_project_output(root: Path, supplied: str, label: str) -> tuple[Path, str]:
    path = Path(supplied)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise PipelineError(f"{label} must stay inside the project root: {path}") from exc
    if relative == STATE_DIR or relative.startswith(f"{STATE_DIR}/"):
        raise PipelineError(f"{label} must not overwrite controller state")
    return path, relative


def parse_decision_ledger_raw(
    raw: bytes, *, label: str = "Decision ledger"
) -> list[dict[str, Any]]:
    if not raw:
        return []
    entries: list[dict[str, Any]] = []
    prefix = b""
    active: set[str] = set()
    semantic_fields = {
        "schema",
        "decision_id",
        "status",
        "statement",
        "rationale",
        "consequences",
        "scope_ids",
        "authority",
        "supersedes",
    }
    mechanical_fields = {
        "sequence",
        "recorded_at",
        "recorder_id",
        "prior_ledger_sha256",
        "input_product_revision",
    }
    for index, line in enumerate(raw.splitlines(keepends=True), start=1):
        if not line.strip():
            raise PipelineError(f"{label} cannot contain blank JSONL records")
        try:
            item = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PipelineError(f"{label} line {index} is invalid JSON") from exc
        if not isinstance(item, dict) or set(item) != semantic_fields | mechanical_fields:
            raise PipelineError(
                f"{label} line {index} does not use the exact schema-1 entry fields"
            )
        decision_id = item.get("decision_id")
        if (
            item.get("schema") != 1
            or item.get("sequence") != index
            or item.get("status") != "accepted"
            or not isinstance(decision_id, str)
            or not re.fullmatch(r"DEC-[A-Za-z0-9-]+", decision_id)
            or decision_id in {entry["decision_id"] for entry in entries}
        ):
            raise PipelineError(f"{label} line {index} has invalid identity/order/status")
        if item.get("prior_ledger_sha256") != hashlib.sha256(prefix).hexdigest():
            raise PipelineError(f"{label} line {index} breaks append-only hash history")
        supersedes = require_string_list(
            item.get("supersedes"), f"Decision ledger line {index} supersedes"
        )
        if any(target not in active for target in supersedes):
            raise PipelineError(
                f"{label} line {index} supersedes an absent or inactive decision"
            )
        active.difference_update(supersedes)
        active.add(decision_id)
        entries.append(item)
        prefix += line
    return entries


def read_decision_ledger(path: Path) -> tuple[list[dict[str, Any]], bytes]:
    if not path.is_file():
        raise PipelineError(f"Decision ledger does not exist: {path}")
    raw = path.read_bytes()
    return parse_decision_ledger_raw(raw), raw


def decision_ledger_state_from_raw(raw: bytes, relative: str) -> dict[str, Any]:
    entries = parse_decision_ledger_raw(raw)
    superseded = sorted(
        {decision_id for item in entries for decision_id in item.get("supersedes", [])}
    )
    active = sorted({item["decision_id"] for item in entries} - set(superseded))
    return {
        "path": relative,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "entry_count": len(entries),
        "active_decision_ids": active,
        "superseded_decision_ids": superseded,
    }


def decision_ledger_state(path: Path, relative: str) -> dict[str, Any]:
    _, raw = read_decision_ledger(path)
    return decision_ledger_state_from_raw(raw, relative)


DECISION_PROJECTION_FIELDS = {
    "schema",
    "operation_id",
    "prior_sha256",
    "prior_entry_count",
    "append_jsonl",
    "append_sha256",
    "target_sha256",
    "target_entry_count",
    "decision_ids",
    "recorder_id",
    "lease_id",
    "capsule_path",
    "capsule_sha256",
    "semantic_packet_path",
    "semantic_packet_sha256",
    "report_path",
    "report_sha256",
    "adr_paths",
    "committed_at",
}


def canonical_decision_ledger(
    root: Path, state: dict[str, Any]
) -> tuple[list[dict[str, Any]], bytes, str]:
    """Read the canonical ledger transaction without mutating its JSONL projection."""
    ledger = state.get("decision_ledger")
    if not isinstance(ledger, dict):
        raise PipelineError("Canonical decision ledger state is missing")
    relative = ledger.get("path")
    if not isinstance(relative, str):
        raise PipelineError("Canonical decision ledger path is malformed")
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise PipelineError("Canonical decision ledger path escapes the project root") from exc
    physical_entries, physical_raw = read_decision_ledger(path)
    projection = ledger.get("projection")
    target_core = {key: ledger.get(key) for key in (
        "path",
        "sha256",
        "entry_count",
        "active_decision_ids",
        "superseded_decision_ids",
    )}
    if projection is None:
        if decision_ledger_state_from_raw(physical_raw, relative) != target_core:
            raise PipelineError(
                "Decision ledger bytes/history drifted outside the controller; reinitialize or "
                "record a controller-authorized append"
            )
        return physical_entries, physical_raw, "projected"
    if not isinstance(projection, dict) or set(projection) != DECISION_PROJECTION_FIELDS:
        raise PipelineError("Canonical decision ledger projection record is malformed")
    append_text = projection.get("append_jsonl")
    if not isinstance(append_text, str):
        raise PipelineError("Canonical decision ledger projection bytes are malformed")
    append_raw = append_text.encode("utf-8")
    decision_ids = projection.get("decision_ids")
    if (
        projection.get("schema") != 1
        or not isinstance(projection.get("operation_id"), str)
        or not isinstance(projection.get("prior_entry_count"), int)
        or not isinstance(projection.get("target_entry_count"), int)
        or not isinstance(decision_ids, list)
        or any(not isinstance(item, str) for item in decision_ids)
        or hashlib.sha256(append_raw).hexdigest() != projection.get("append_sha256")
        or projection.get("target_sha256") != ledger.get("sha256")
        or projection.get("target_entry_count") != ledger.get("entry_count")
    ):
        raise PipelineError("Canonical decision ledger projection binding is inconsistent")
    physical_sha = hashlib.sha256(physical_raw).hexdigest()
    if physical_sha == projection.get("prior_sha256"):
        if len(physical_entries) != projection.get("prior_entry_count"):
            raise PipelineError("Decision ledger pre-projection entry count is inconsistent")
        target_raw = physical_raw + append_raw
        status = "pending_projection"
    elif physical_sha == projection.get("target_sha256"):
        target_raw = physical_raw
        status = "projected"
    else:
        raise PipelineError(
            "Decision ledger projection is neither the exact committed prefix nor target; "
            "possible tampering detected"
        )
    if hashlib.sha256(target_raw).hexdigest() != projection.get("target_sha256"):
        raise PipelineError("Decision ledger committed projection target digest is inconsistent")
    entries = parse_decision_ledger_raw(target_raw, label="Canonical decision ledger")
    if decision_ledger_state_from_raw(target_raw, relative) != target_core:
        raise PipelineError("Canonical decision ledger state does not match its exact projection")
    if [item["decision_id"] for item in entries[-len(decision_ids):]] != decision_ids:
        raise PipelineError("Decision ledger projection decision IDs are inconsistent")
    return entries, target_raw, status


def project_canonical_decision_ledger(root: Path, state: dict[str, Any]) -> str:
    """Materialize an exact state-authorized JSONL projection after state commit."""
    _, target_raw, status = canonical_decision_ledger(root, state)
    if status == "projected":
        return status
    ledger_path = root / state["decision_ledger"]["path"]
    temporary = ledger_path.with_name(
        f".{ledger_path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    )
    try:
        with temporary.open("wb") as stream:
            stream.write(target_raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, ledger_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    canonical_decision_ledger(root, state)
    return "projected"


def user_authority_digest(authority_id: str, approval_reference: str, statement: str) -> str:
    return canonical_json_sha256(
        {
            "kind": "user",
            "authority_id": authority_id,
            "approval_reference": approval_reference,
            "statement": statement,
        }
    )


def scope_hold_sha256(hold: dict[str, Any]) -> str:
    """Fingerprint the exact immutable hold the user is being asked to approve."""
    if not isinstance(hold, dict) or not hold:
        raise PipelineError("Scope rebaseline authority requires an exact open hold")
    return canonical_json_sha256(hold)


def scope_rebaseline_authority_statement(
    hold: dict[str, Any], approved_plan_sha256: str
) -> str:
    if re.fullmatch(r"[0-9a-f]{64}", approved_plan_sha256) is None:
        raise PipelineError("Scope rebaseline authority requires an exact plan SHA-256")
    return (
        "Approve scope rebaseline "
        f"hold_sha256={scope_hold_sha256(hold)} "
        f"plan_sha256={approved_plan_sha256}"
    )


def validate_user_authority_registry(root: Path, state: dict[str, Any]) -> None:
    registry = state.get("user_authorities")
    if not isinstance(registry, list):
        raise PipelineError("Schema 9 state lacks the append-only user authority registry")
    seen: set[str] = set()
    exact = {
        "authority_id",
        "approval_reference",
        "statement",
        "sha256",
        "receipt_path",
        "receipt_sha256",
        "recorded_at",
    }
    for record in registry:
        if not isinstance(record, dict) or set(record) != exact:
            raise PipelineError("User authority registry record is malformed")
        authority_id = record["authority_id"]
        if (
            not isinstance(authority_id, str)
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9._:-]*", authority_id)
            or authority_id in seen
        ):
            raise PipelineError("User authority IDs are unique append-only identifiers")
        seen.add(authority_id)
        expected_digest = user_authority_digest(
            authority_id, record["approval_reference"], record["statement"]
        )
        if record["sha256"] != expected_digest:
            raise PipelineError("User authority registry digest does not bind its exact checkpoint")
        receipt_path = resolve_project_file(root, record["receipt_path"], "User authority receipt")
        if file_sha256(receipt_path) != record["receipt_sha256"]:
            raise PipelineError("User authority receipt bytes drifted outside the controller")
        receipt = read_json(receipt_path)
        if receipt != {
            "schema": 1,
            "authority_id": authority_id,
            "approval_reference": record["approval_reference"],
            "statement": record["statement"],
            "sha256": record["sha256"],
            "recorded_at": record["recorded_at"],
        }:
            raise PipelineError("User authority receipt does not match its immutable registry record")


def empty_documentation_state() -> dict[str, Any]:
    return {
        "normative": {
            "status": "pending",
            "product_revision": None,
            "paths": [],
            "decision_ids": [],
            "report_path": None,
            "report_sha256": None,
        },
        "derived": {
            "status": "pending",
            "support_revision": None,
            "paths": [],
            "source_evidence_ids": [],
            "report_path": None,
            "report_sha256": None,
            "closure_review_id": "pending",
        },
    }


def empty_coverage_scope() -> dict[str, Any]:
    return {
        "planned_manifest": None,
        "finalized_manifest": None,
        "state": {
            "status": "pending",
            "ac_mapped": False,
            "identities_registered": "pending",
            "mandatory_registration": "pending",
            "automated": "pending",
            "manual": "pending",
            "implementation_eligible": False,
            "feature_verification_eligible": False,
            "readiness_class": None,
            "gaps": [],
        },
    }


def revision_records(root: Path, paths: list[str], label: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for relative in sorted(paths):
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise PipelineError(f"{label} inventory escapes the project root: {relative}") from exc
        if not path.is_file():
            raise PipelineError(f"{label} inventory path is missing: {relative}")
        records.append({"path": relative, "sha256": file_sha256(path)})
    return records


def compute_inventory_revisions(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    inventory = state.get("revision_inventory")
    if not isinstance(inventory, dict):
        raise PipelineError("Schema 9 state lacks the controller revision inventory")
    assigned: set[str] = set()
    domains: dict[str, list[dict[str, str]]] = {}
    for domain in ("product", "support", "evidence"):
        values = inventory.get(domain)
        if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
            raise PipelineError(f"revision_inventory.{domain} must be a path list")
        duplicate = assigned.intersection(values)
        if duplicate:
            raise PipelineError(
                "Revision inventory assigns paths to multiple domains: "
                + ", ".join(sorted(duplicate))
            )
        assigned.update(values)
        domains[domain] = revision_records(root, values, domain)
    ledger = state.get("decision_ledger")
    if isinstance(ledger, dict) and ledger.get("projection") is not None:
        # The atomically committed state is authoritative while its JSONL file is
        # still either the exact prior prefix or exact target projection.
        canonical_decision_ledger(root, state)
        ledger_path = ledger.get("path")
        for records in domains.values():
            for record in records:
                if record["path"] == ledger_path:
                    record["sha256"] = ledger["sha256"]
    base = state["revision_base_revision"]
    product_revision = revision_for_domain(base, domains["product"])
    support_revision = revision_for_domain(base, domains["support"])
    evidence_revision = revision_for_domain(base, domains["evidence"])
    revision = hashlib.sha256(
        (
            f"product:{product_revision}\n"
            f"support:{support_revision}\n"
            f"evidence:{evidence_revision}\n"
        ).encode("utf-8")
    ).hexdigest()
    return {
        "revision": revision,
        "product_revision": product_revision,
        "support_revision": support_revision,
        "evidence_revision": evidence_revision,
        "records": domains,
    }


def aggregate_revision(
    product_revision: str, support_revision: str, evidence_revision: str
) -> str:
    return hashlib.sha256(
        (
            f"product:{product_revision}\n"
            f"support:{support_revision}\n"
            f"evidence:{evidence_revision}\n"
        ).encode("utf-8")
    ).hexdigest()


def parse_rfc3339_utc_day(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise PipelineError(f"{label} must be an RFC3339 UTC timestamp")
    match = re.fullmatch(
        r"(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]00:00)",
        value,
    )
    if not match:
        raise PipelineError(f"{label} must be an RFC3339 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(f"{match.group(1)}T{match.group(2)}+00:00")
    except ValueError as exc:
        raise PipelineError(f"{label} must be an RFC3339 UTC timestamp") from exc
    return parsed


def remediation_batch_is_exact(state: dict[str, Any], findings: dict[str, Any]) -> bool:
    batch = state.get("active_remediation_batch")
    if not isinstance(batch, dict) or batch.get("status") != "active":
        return False
    finding_ids = batch.get("finding_ids")
    if (
        not isinstance(finding_ids, list)
        or not finding_ids
        or len(finding_ids) != len(set(finding_ids))
        or any(not isinstance(value, str) or not value for value in finding_ids)
    ):
        return False
    required = open_remediation_required(findings)
    if set(finding_ids) != {item.get("id") for item in required}:
        return False
    route = batch.get("route")
    try:
        if any(route_for_finding(state, item) != route for item in required):
            return False
    except PipelineError:
        return False
    if batch.get("owner_id") != state.get("engineering_owner_id"):
        return False
    active_queue = [
        item
        for item in state.get("remediation_queue", [])
        if isinstance(item, dict) and item.get("status") == "active"
    ]
    return len(active_queue) == 1 and all(
        active_queue[0].get(key) == batch.get(key)
        for key in ("route", "finding_ids", "status", "owner_id", "returns_for_owner")
    )


def lifecycle_dashboard_candidate(
    root: Path,
    state: dict[str, Any],
    dashboard_relative: str,
) -> dict[str, Any] | None:
    feature_slug = state.get("feature")
    if not isinstance(feature_slug, str) or not feature_slug:
        return None
    dashboard = (root / dashboard_relative).resolve()
    try:
        dashboard.relative_to(root)
    except ValueError:
        return None
    manifest = (dashboard.parent / feature_slug / "feature.json").resolve()
    try:
        manifest.relative_to(root)
    except ValueError:
        return None
    if not dashboard.is_file() or not manifest.is_file():
        return None
    try:
        manifest_value = read_json(manifest)
        feature_id = manifest_value.get("id")
        if (
            not isinstance(feature_id, str)
            or not feature_id
            or manifest_value.get("activity") != "active"
        ):
            return None
        updated = parse_rfc3339_utc_day(
            manifest_value.get("updatedAt"), "Active feature manifest updatedAt"
        )
        started = parse_rfc3339_utc_day(
            manifest_value.get("startedAt"), "Active feature manifest startedAt"
        )
        if started > updated:
            return None
        active_manifests: list[Path] = []
        for sibling in dashboard.parent.glob("*/feature.json"):
            sibling_value = read_json(sibling)
            if sibling_value.get("activity") == "active":
                active_manifests.append(sibling.resolve())
        if active_manifests != [manifest.resolve()]:
            return None
        text = dashboard.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError, PipelineError):
        return None
    row_pattern = re.compile(
        rf"(?m)^\|\s*{re.escape(feature_id)}\s*\|[^\r\n]*\|\s*(\d{{4}}-\d{{2}}-\d{{2}})\s*\|\s*$"
    )
    rows = list(row_pattern.finditer(text))
    if len(rows) != 1 or f"./{feature_slug}/" not in rows[0].group(0):
        return None
    current_date = rows[0].group(1)
    if current_date != updated.date().isoformat():
        return None
    return {
        "feature_id": feature_id,
        "feature_slug": feature_slug,
        "dashboard_path": dashboard_relative,
        "dashboard": dashboard,
        "dashboard_text": text,
        "date_span": rows[0].span(1),
        "current_date": current_date,
        "manifest_path": manifest.relative_to(root).as_posix(),
        "manifest": manifest,
        "started": started,
        "updated": updated,
    }


def reverse_lifecycle_dashboard_candidates(
    state: dict[str, Any],
    computed: dict[str, Any],
    candidate: dict[str, Any],
) -> list[dict[str, Any]]:
    dashboard_path = candidate["dashboard_path"]
    current_records = computed["records"]["product"]
    old_guard = state.get("lifecycle_projection_guard")
    guarded_date = (
        old_guard.get("updated_date")
        if isinstance(old_guard, dict)
        and old_guard.get("dashboard_path") == dashboard_path
        and old_guard.get("feature_id") == candidate["feature_id"]
        else None
    )
    dates: list[str] = []
    if isinstance(guarded_date, str):
        dates.append(guarded_date)
    if (candidate["updated"].date() - candidate["started"].date()).days > 3660:
        return []
    day = candidate["started"]
    while day.date() <= candidate["updated"].date():
        value = day.date().isoformat()
        if value not in dates:
            dates.append(value)
        day += timedelta(days=1)
    before, after = candidate["date_span"]
    matches: list[dict[str, Any]] = []
    for old_date in dates:
        if old_date == candidate["current_date"]:
            continue
        prior_text = (
            candidate["dashboard_text"][:before]
            + old_date
            + candidate["dashboard_text"][after:]
        )
        prior_sha = hashlib.sha256(prior_text.encode("utf-8")).hexdigest()
        prior_records = [dict(record) for record in current_records]
        dashboard_records = [
            record for record in prior_records if record["path"] == dashboard_path
        ]
        if len(dashboard_records) != 1:
            return []
        dashboard_records[0]["sha256"] = prior_sha
        product_revision = revision_for_domain(
            state["revision_base_revision"], prior_records
        )
        revision = aggregate_revision(
            product_revision,
            computed["support_revision"],
            computed["evidence_revision"],
        )
        if (
            product_revision == state.get("product_revision")
            and revision == state.get("revision")
        ):
            matches.append(
                {
                    "before_date": old_date,
                    "before_dashboard_sha256": prior_sha,
                }
            )
    return matches


def stale_unused_engineer_capsules(state: dict[str, Any], old_revision: str) -> list[str]:
    used = {
        item.get("capsule_id")
        for item in state.get("write_lease_history", [])
        if isinstance(item, dict)
    }
    active = state.get("active_write_lease")
    if isinstance(active, dict):
        used.add(active.get("capsule_id"))
    stale: list[str] = []
    for item in state.get("context_capsules", []):
        if (
            isinstance(item, dict)
            and item.get("role") == "engineer"
            and item.get("revision") == old_revision
            and item.get("capsule_id") not in used
            and item.get("status") != "stale"
        ):
            item["status"] = "stale"
            item["stale_reason"] = "lifecycle_projection_reconciled"
            stale.append(str(item.get("capsule_id")))
    return stale


def try_reconcile_lifecycle_projection_drift(
    root: Path,
    state: dict[str, Any],
    findings: dict[str, Any],
    computed: dict[str, Any],
) -> bool:
    if (
        state.get("phase") != "engineering"
        or state.get("active_write_lease") is not None
        or state.get("pending_engineer_completion") is not None
        or computed["support_revision"] != state.get("support_revision")
        or computed["evidence_revision"] != state.get("evidence_revision")
        or computed["product_revision"] == state.get("product_revision")
        or computed["revision"] == state.get("revision")
        or not remediation_batch_is_exact(state, findings)
    ):
        return False
    stored_records = state.get("revision_records")
    if isinstance(stored_records, dict):
        if set(stored_records) != {"product", "support", "evidence"}:
            return False
        stored_product = stored_records.get("product")
        if not isinstance(stored_product, list):
            return False
        old_by_path = {
            item.get("path"): item.get("sha256")
            for item in stored_product
            if isinstance(item, dict)
        }
        current_by_path = {
            item["path"]: item["sha256"] for item in computed["records"]["product"]
        }
        changed_paths = {
            path
            for path in set(old_by_path) | set(current_by_path)
            if old_by_path.get(path) != current_by_path.get(path)
        }
        if len(changed_paths) != 1:
            return False
        dashboard_paths = list(changed_paths)
    else:
        dashboard_paths = [
            value
            for value in state["revision_inventory"]["product"]
            if isinstance(value, str) and Path(value).name.lower() == "readme.md"
        ]
    proven: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for dashboard_path in dashboard_paths:
        candidate = lifecycle_dashboard_candidate(root, state, dashboard_path)
        if candidate is None:
            continue
        reverse = reverse_lifecycle_dashboard_candidates(state, computed, candidate)
        if len(reverse) == 1:
            proven.append((candidate, reverse[0]))
    if len(proven) != 1:
        return False
    candidate, reverse = proven[0]
    if isinstance(stored_records, dict):
        expected_old_sha = next(
            (
                item.get("sha256")
                for item in stored_records["product"]
                if item.get("path") == candidate["dashboard_path"]
            ),
            None,
        )
        if expected_old_sha != reverse["before_dashboard_sha256"]:
            return False

    before_revisions = {
        key: state[key]
        for key in ("revision", "product_revision", "support_revision", "evidence_revision")
    }
    after_revisions = {
        key: computed[key]
        for key in ("revision", "product_revision", "support_revision", "evidence_revision")
    }
    history = state.setdefault("lifecycle_projection_reconciliations", [])
    if not isinstance(history, list):
        return False
    receipt_id = f"LPR-{len(history) + 1:04d}"
    controller_root = (
        Path(state.get("tests_path", "")) / "verification" / "controller"
    ).resolve()
    try:
        controller_root.relative_to(root)
    except ValueError:
        return False
    receipt_path = controller_root / f"lifecycle-projection-reconciliation-{len(history) + 1:04d}.json"
    orphan_receipt: dict[str, Any] | None = None
    if receipt_path.exists():
        try:
            orphan_receipt = read_json(receipt_path)
        except PipelineError:
            return False
    working = copy.deepcopy(state)
    working_history = working["lifecycle_projection_reconciliations"]
    stale_capsules = stale_unused_engineer_capsules(
        working, before_revisions["revision"]
    )
    invalidated_credit_ids: list[str] = []
    for credit in working.get("component_review_credits", []):
        if (
            isinstance(credit, dict)
            and credit.get("valid") is True
            and candidate["dashboard_path"]
            in set(credit.get("product_paths") or [])
            | set(credit.get("contract_paths") or [])
        ):
            credit["valid"] = False
            credit["invalidated_at"] = utc_now()
            credit["invalidation_reason"] = "lifecycle_projection_product_hash_drift"
            invalidated_credit_ids.append(str(credit.get("id")))
    invalidated_pre_edit = False
    active_slice = active_slice_state(working)
    if isinstance(active_slice, dict):
        pre_edit = active_slice.get("scope_pre_edit_check")
        if isinstance(pre_edit, dict) and before_revisions["revision"] in pre_edit.values():
            active_slice["scope_pre_edit_check"] = None
            invalidated_pre_edit = True
    recorded_at = (
        orphan_receipt.get("recorded_at")
        if isinstance(orphan_receipt, dict)
        else utc_now()
    )
    if not isinstance(recorded_at, str) or not recorded_at:
        return False
    receipt = {
        "schema": 1,
        "receipt_id": receipt_id,
        "kind": "lifecycle_generated_dashboard_date",
        "feature_id": candidate["feature_id"],
        "feature_slug": candidate["feature_slug"],
        "dashboard_path": candidate["dashboard_path"],
        "manifest_path": candidate["manifest_path"],
        "before_date": reverse["before_date"],
        "after_date": candidate["current_date"],
        "before_dashboard_sha256": reverse["before_dashboard_sha256"],
        "after_dashboard_sha256": file_sha256(candidate["dashboard"]),
        "manifest_sha256": file_sha256(candidate["manifest"]),
        "before_revisions": before_revisions,
        "after_revisions": after_revisions,
        "remediation_route": working["active_remediation_batch"]["route"],
        "finding_ids": sorted(working["active_remediation_batch"]["finding_ids"]),
        "stale_capsule_ids": stale_capsules,
        "invalidated_component_review_credit_ids": invalidated_credit_ids,
        "invalidated_scope_pre_edit_check": invalidated_pre_edit,
        "recorded_at": recorded_at,
    }
    receipt_relative = receipt_path.relative_to(root).as_posix()
    receipt_sha = serialized_json_sha256(receipt)
    if orphan_receipt is not None:
        if orphan_receipt != receipt:
            return False
    else:
        working["pending_lifecycle_projection_receipt"] = {
            "path": receipt_relative,
            "value": receipt,
            "sha256": receipt_sha,
        }
    summary = dict(receipt)
    summary.pop("schema")
    summary["path"] = receipt_relative
    summary["sha256"] = receipt_sha
    working_history.append(summary)
    working.update(after_revisions)
    working["revision_records"] = computed["records"]
    working["lifecycle_projection_guard"] = {
        "schema": 1,
        "feature_id": candidate["feature_id"],
        "feature_slug": candidate["feature_slug"],
        "dashboard_path": candidate["dashboard_path"],
        "manifest_path": candidate["manifest_path"],
        "dashboard_sha256": receipt["after_dashboard_sha256"],
        "manifest_sha256": receipt["manifest_sha256"],
        "updated_date": candidate["current_date"],
    }
    state.clear()
    state.update(working)
    return True


def source_projection_rules(
    state: dict[str, Any], extra_rules: list[str] | None = None
) -> list[str]:
    """Return the controller-owned source projection, never the whole checkout."""
    exact: set[str] = set()
    source_roots: set[str] = set()

    def add_exact(value: Any) -> None:
        if not isinstance(value, str):
            return
        value = value.replace("\\", "/").strip("/")
        if value and not Path(value).is_absolute() and ".." not in Path(value).parts:
            exact.add(value)

    def add_source(value: Any) -> None:
        if not isinstance(value, str):
            return
        value = value.replace("\\", "/").strip("/")
        if not value or Path(value).is_absolute() or ".." in Path(value).parts:
            return
        prefix = value[:-3].rstrip("/") if value.endswith("/**") else value
        parts = Path(prefix).parts
        if len(parts) > 1:
            source_roots.add(parts[0].replace("\\", "/") + "/**")
        else:
            exact.add(value)

    for key in ("requirements_path", "spec_path", "development_plan_path"):
        add_exact(state.get(key))
    ledger = state.get("decision_ledger") or {}
    add_exact(ledger.get("path"))
    for paths in (state.get("revision_inventory") or {}).values():
        if isinstance(paths, list):
            for relative in paths:
                add_exact(relative)
    for authority in state.get("user_authorities") or []:
        if isinstance(authority, dict):
            add_exact(authority.get("path"))
    for slice_item in (state.get("slices") or {}).values():
        if not isinstance(slice_item, dict):
            continue
        scope = slice_item.get("scope_contract") or {}
        for relative in scope.get("editable_paths") or []:
            add_source(relative)
        for touchpoint in scope.get("shared_touchpoints") or []:
            if isinstance(touchpoint, dict):
                add_source(touchpoint.get("path"))
    for relative in extra_rules or []:
        add_source(relative)
    rules = sorted(exact | source_roots)
    if not rules:
        raise PipelineError("Controller source projection is empty")
    return rules


def load_generated_output_policy(root: Path) -> dict[str, Any] | None:
    path = root / GENERATED_OUTPUT_POLICY_PATH
    if not path.exists():
        return None
    value = read_json(path)
    if set(value) != {"schema_version", "generated_paths"} or value.get("schema_version") != 1:
        raise PipelineError(
            "Generated-output policy must use exact schema_version=1 and generated_paths"
        )
    patterns = require_string_list(
        value.get("generated_paths"), "Generated-output policy generated_paths"
    )
    normalized: list[str] = []
    for pattern in patterns:
        pattern = pattern.replace("\\", "/").strip("/")
        valid = (
            bool(pattern)
            and ".." not in Path(pattern).parts
            and not Path(pattern).is_absolute()
            and (
                "*" not in pattern
                or pattern.endswith("/**")
                or (pattern.startswith("*.") and pattern.count("*") == 1 and "/" not in pattern)
            )
        )
        if not valid:
            raise PipelineError(f"Invalid generated-output policy path: {pattern!r}")
        if pattern.casefold().endswith(".meta") or pattern == "*.*":
            raise PipelineError("Generated-output policy cannot classify project-owned .meta files")
        normalized.append(pattern)
    if len(normalized) != len(set(normalized)):
        raise PipelineError("Generated-output policy paths must be duplicate-free")
    return {
        "path": GENERATED_OUTPUT_POLICY_PATH,
        "sha256": file_sha256(path),
        "schema_version": 1,
        "generated_paths": normalized,
    }


def generated_output_path(relative: str, patterns: list[str]) -> bool:
    normalized = relative.replace("\\", "/").strip("/")
    if normalized.casefold().endswith(".meta"):
        return False
    for pattern in patterns:
        if pattern.endswith("/**") and path_matches_scope(normalized, pattern):
            return True
        if pattern.startswith("*.") and Path(normalized).name.endswith(pattern[1:]):
            return True
        if normalized == pattern:
            return True
    return False


def excluded_source_path(
    relative: str, feature: str, generated_paths: list[str] | None = None
) -> bool:
    parts = tuple(part.casefold() for part in Path(relative).parts)
    ignored_feature = f"tests/{feature}".casefold()
    normalized = relative.casefold().strip("/")
    return (
        not relative
        or relative.startswith("/")
        or ".." in Path(relative).parts
        or normalized == ignored_feature
        or normalized.startswith(ignored_feature + "/")
        or any(part in {".git", STATE_DIR.casefold()} for part in parts)
        or generated_output_path(relative, generated_paths or [])
        or relative.endswith((".pyc", ".pyo", ".tmp"))
    )


def source_projection_candidates(root: Path, rules: list[str], feature: str) -> list[str]:
    """Enumerate tracked/unignored projected sources with a bounded safe fallback."""
    candidates: set[str] = set()
    policy = load_generated_output_policy(root)
    generated_paths = policy["generated_paths"] if policy else []
    cache_key = root.resolve()
    cached = (
        _COMMAND_SOURCE_INVENTORY.get(cache_key)
        if _COMMAND_SOURCE_INVENTORY is not None
        else None
    )
    if cached is None:
        try:
            inventory = subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "ls-files",
                    "--stage",
                    "--others",
                    "--exclude-standard",
                    "-z",
                ],
                check=True,
                capture_output=True,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            cached = []
        else:
            cached = []
            for item in inventory.stdout.split(b"\0"):
                if not item:
                    continue
                metadata, separator, encoded_path = item.partition(b"\t")
                if separator:
                    fields = metadata.split()
                    if len(fields) != 3:
                        raise PipelineError("git ls-files --stage returned a malformed record")
                    relative = encoded_path.decode(
                        "utf-8", errors="surrogateescape"
                    ).replace("\\", "/")
                    cached.append((relative, fields[0] == b"160000"))
                else:
                    relative = item.decode(
                        "utf-8", errors="surrogateescape"
                    ).replace("\\", "/")
                    cached.append((relative, False))
        if _COMMAND_SOURCE_INVENTORY is not None:
            _COMMAND_SOURCE_INVENTORY[cache_key] = cached
    candidates.update(relative for relative, _ in cached)
    unsupported = sorted(
        relative
        for relative, is_gitlink in cached
        if is_gitlink
        and not excluded_source_path(relative, feature, generated_paths)
        and any(path_matches_scope(relative, rule) for rule in rules)
    )
    if unsupported:
        raise PipelineError(
            "Controller source projection crosses unsupported Git gitlink/submodule: "
            + ", ".join(unsupported)
        )

    if not candidates:
        roots: set[Path] = set()
        for rule in rules:
            prefix = rule[:-3].rstrip("/") if rule.endswith("/**") else rule
            candidate = root / prefix
            roots.add(candidate if candidate.is_dir() else candidate.parent)
        for projection_root in sorted(roots):
            if not projection_root.exists() or projection_root.is_symlink():
                continue
            for directory, directories, files in os.walk(projection_root):
                directory_path = Path(directory)
                directories[:] = [
                    name
                    for name in directories
                    if not excluded_source_path(
                        (directory_path / name).relative_to(root).as_posix(), feature,
                        generated_paths,
                    )
                    and not (directory_path / name).is_symlink()
                ]
                candidates.update(
                    (directory_path / name).relative_to(root).as_posix() for name in files
                )

    selected = sorted(
        relative
        for relative in candidates
        if not excluded_source_path(relative, feature, generated_paths)
        and any(path_matches_scope(relative, rule) for rule in rules)
    )
    if len(selected) > MAX_SOURCE_SNAPSHOT_FILES:
        raise PipelineError(
            "Controller source projection exceeds the lease snapshot file limit: "
            f"{len(selected)} > {MAX_SOURCE_SNAPSHOT_FILES}"
        )
    return selected


def snapshot_file_sha256(path: Path) -> str:
    if path.is_symlink():
        return hashlib.sha256(
            ("symlink:\0" + os.readlink(path)).encode("utf-8", errors="surrogateescape")
        ).hexdigest()
    size = path.stat().st_size
    if size > MAX_SOURCE_FILE_BYTES:
        raise PipelineError(
            f"Projected source exceeds the per-file snapshot limit: {path} ({size} bytes)"
        )
    return file_sha256(path)


def checkout_snapshot(
    root: Path,
    feature: str,
    state: dict[str, Any] | None = None,
    extra_rules: list[str] | None = None,
) -> dict[str, str]:
    if state is None:
        state_path = root / STATE_DIR / "state.json"
        state = read_json(state_path) if state_path.is_file() else {}
    policy = load_generated_output_policy(root)
    recorded_policy = state.get("generated_output_policy")
    if recorded_policy is not None and policy != recorded_policy:
        raise PipelineError("Generated-output policy drifted from the initialized contract")
    rules = source_projection_rules(state, extra_rules)
    result: dict[str, str] = {}
    for relative in source_projection_candidates(root, rules, feature):
        path = root / relative
        if path.is_file() or path.is_symlink():
            result[relative] = snapshot_file_sha256(path)
    return result


def changed_checkout_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(
        path
        for path in set(before) | set(after)
        if before.get(path) != after.get(path)
    )


def line_hashes(raw: bytes) -> list[str] | None:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return [
        hashlib.sha256(line.encode("utf-8")).hexdigest() for line in text.splitlines()
    ]


def line_proof_snapshot(
    root: Path, checkout: dict[str, str], allowed_paths: list[str]
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    total_lines = 0
    for relative in sorted(checkout):
        if not any(path_matches_scope(relative, rule) for rule in allowed_paths):
            continue
        if len(result) >= MAX_LINE_PROOF_FILES:
            raise PipelineError(
                "Lease line-proof projection exceeds the file limit: "
                f"{len(result) + 1} > {MAX_LINE_PROOF_FILES}"
            )
        path = root / relative
        if path.is_symlink():
            hashes = None
            byte_count = len(os.readlink(path).encode("utf-8", errors="surrogateescape"))
        else:
            size = path.stat().st_size
            if size > MAX_SOURCE_FILE_BYTES:
                raise PipelineError(
                    f"Projected source exceeds the per-file snapshot limit: {relative}"
                )
            raw = path.read_bytes()
            hashes = line_hashes(raw)
            byte_count = len(raw)
        if hashes is not None:
            total_lines += len(hashes)
            if total_lines > MAX_LINE_PROOF_LINES:
                raise PipelineError(
                    "Lease line-proof projection exceeds the line limit: "
                    f"{total_lines} > {MAX_LINE_PROOF_LINES}"
                )
        result[relative] = {
            "sha256": checkout[relative],
            "byte_count": byte_count,
            "line_count": len(hashes) if hashes is not None else None,
            "line_hashes": hashes,
        }
    return result


def build_lease_snapshot(
    root: Path,
    state: dict[str, Any],
    *,
    capsule_path: str,
    capsule_sha256: str,
    allowed_paths: list[str],
    authorization_checkout: dict[str, str] | None = None,
    checkout: dict[str, str] | None = None,
    inherited_line_proofs: dict[str, dict[str, Any]] | None = None,
    rebaseline_carried: bool = False,
    scope_authorization: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    current = checkout_snapshot(
        root, state["feature"], state, extra_rules=allowed_paths
    )
    if authorization_checkout is not None and current != authorization_checkout:
        raise PipelineError("Checkout changed while capturing the lease snapshot")
    base = copy.deepcopy(checkout if checkout is not None else current)
    snapshot = {
        "capsule_path": capsule_path,
        "capsule_sha256": capsule_sha256,
        "checkout": base,
        "authorization_checkout": copy.deepcopy(
            authorization_checkout if authorization_checkout is not None else current
        ),
        "line_proofs": copy.deepcopy(
            inherited_line_proofs
            if inherited_line_proofs is not None
            else line_proof_snapshot(root, base, allowed_paths)
        ),
        "snapshot_schema": LEASE_SNAPSHOT_SCHEMA,
        "snapshot_format": LEASE_SNAPSHOT_FORMAT,
        "source_projection_rules": source_projection_rules(state, allowed_paths),
        "rebaseline_carried": rebaseline_carried,
        "scope_authorization": scope_authorization,
        "created_at": created_at or utc_now(),
    }
    encoded_size = len(
        json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    )
    if encoded_size > MAX_LEASE_SNAPSHOT_BYTES:
        raise PipelineError(
            "Lease snapshot exceeds the serialized size limit: "
            f"{encoded_size} > {MAX_LEASE_SNAPSHOT_BYTES}"
        )
    return snapshot


def snapshot_line_count(base: Any, current: Path) -> int:
    if base is None:
        if not current.is_file():
            return 0
        current_hashes = line_hashes(current.read_bytes())
        return len(current_hashes) if current_hashes is not None else 1
    if not isinstance(base, dict) or set(base) != {
        "sha256",
        "byte_count",
        "line_count",
        "line_hashes",
    }:
        raise PipelineError("Lease line proof is missing or malformed")
    if current.is_file() and file_sha256(current) == base.get("sha256"):
        return 0
    prior_hashes = base.get("line_hashes")
    current_hashes = line_hashes(current.read_bytes()) if current.is_file() else []
    if not isinstance(prior_hashes, list) or current_hashes is None:
        prior_lines = base.get("line_count")
        return max(
            1,
            (prior_lines if isinstance(prior_lines, int) else 0)
            + (len(current_hashes) if isinstance(current_hashes, list) else 0),
        )
    count = 0
    for tag, before_start, before_end, after_start, after_end in difflib.SequenceMatcher(
        a=prior_hashes, b=current_hashes, autojunk=False
    ).get_opcodes():
        if tag != "equal":
            count += (before_end - before_start) + (after_end - after_start)
    return count


def checkout_snapshot_sha256(snapshot: dict[str, str]) -> str:
    """Bind an authorization receipt to the exact byte hashes visible at a boundary."""
    return canonical_json_sha256(snapshot)


def snapshot_revisions(
    state: dict[str, Any], snapshot: dict[str, str]
) -> dict[str, str]:
    """Rebuild the frozen revisions from an immutable lease checkout snapshot."""
    domains: dict[str, list[dict[str, str]]] = {}
    for domain in ("product", "support", "evidence"):
        records: list[dict[str, str]] = []
        for relative in state["revision_inventory"][domain]:
            sha = snapshot.get(relative)
            if not isinstance(sha, str) or not sha:
                raise PipelineError(
                    f"Lease snapshot lacks revision input {domain}:{relative}"
                )
            records.append({"path": relative, "sha256": sha})
        domains[domain] = records
    base = state["revision_base_revision"]
    product = revision_for_domain(base, domains["product"])
    support = revision_for_domain(base, domains["support"])
    evidence = revision_for_domain(base, domains["evidence"])
    return {
        "revision": aggregate_revision(product, support, evidence),
        "product_revision": product,
        "support_revision": support,
        "evidence_revision": evidence,
    }


def validate_schema10_runtime(state: dict[str, Any], findings: dict[str, Any]) -> None:
    required = {
        "implementation_state",
        "feature_verification_state",
        "active_write_lease",
        "write_lease_history",
        "decision_ledger",
        "coverage",
        "documentation",
        "context_capsules",
        "handoffs",
        "lease_snapshots",
        "revision_inventory",
        "revision_base_revision",
        "plan_contracts",
        "user_authorities",
    }
    missing = sorted(required - set(state))
    if missing:
        raise PipelineError(
            "Schema 10 state is incomplete and cannot be inferred; reinitialize explicitly: "
            + ", ".join(missing)
        )
    if not isinstance(state["write_lease_history"], list) or not isinstance(
        state["context_capsules"], list
    ) or not isinstance(state["handoffs"], list):
        raise PipelineError("Schema 10 append-only histories must be arrays")
    if state["active_write_lease"] is not None and not isinstance(
        state["active_write_lease"], dict
    ):
        raise PipelineError("active_write_lease must be null or a schema-1 lease")
    if findings.get("schema_version") != SCHEMA_VERSION:
        raise PipelineError("Findings schema does not match the schema-10 runtime")
    for lease_id, snapshot in state.get("lease_snapshots", {}).items():
        if not isinstance(snapshot, dict):
            raise PipelineError(f"Lease snapshot {lease_id} is malformed")
        if (
            snapshot.get("snapshot_schema") != LEASE_SNAPSHOT_SCHEMA
            or snapshot.get("snapshot_format") != LEASE_SNAPSHOT_FORMAT
            or "checkout_text" in snapshot
        ):
            raise PipelineError(
                f"Lease snapshot {lease_id} was not automatically migrated to schema 4"
            )


def migrate_active_legacy_snapshot(
    root: Path,
    state: dict[str, Any],
    lease_id: str,
    migrated_at: str,
) -> dict[str, Any]:
    """Sanitize a verifiable legacy snapshot or audit-revoke it without touching files."""
    lease = state.get("active_write_lease")
    snapshot = (state.get("lease_snapshots") or {}).get(lease_id)
    role = lease.get("role") if isinstance(lease, dict) else None
    expected_phase = lease.get("phase") if isinstance(lease, dict) else state.get("phase")
    verification_errors: list[str] = []
    if (
        not isinstance(lease, dict)
        or lease.get("status") != "active"
        or lease.get("lease_id") != lease_id
        or role not in WRITE_ROLES
        or expected_phase not in LEASE_PHASES.get(role, set())
        or state.get("phase") != expected_phase
    ):
        verification_errors.append("active writer lease metadata is inconsistent")
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("checkout"), dict):
        verification_errors.append("active lease snapshot is missing or malformed")

    legacy_checkout_value = snapshot.get("checkout") if isinstance(snapshot, dict) else None
    legacy_checkout = legacy_checkout_value if isinstance(legacy_checkout_value, dict) else {}
    invalid_checkout = sorted(
        str(relative)
        for relative, digest in legacy_checkout.items()
        if not isinstance(relative, str)
        or not isinstance(digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
    )
    if invalid_checkout:
        verification_errors.append(
            "legacy checkout lacks immutable lowercase SHA-256 metadata"
        )

    allowed_paths = list(lease.get("allowed_paths") or []) if isinstance(lease, dict) else []
    rules = source_projection_rules(state, allowed_paths)
    projected_checkout = {
        relative: digest
        for relative, digest in legacy_checkout.items()
        if isinstance(relative, str)
        and isinstance(digest, str)
        and re.fullmatch(r"[0-9a-f]{64}", digest) is not None
        and not excluded_source_path(
            relative,
            state["feature"],
            (load_generated_output_policy(root) or {}).get("generated_paths", []),
        )
        and any(path_matches_scope(relative, rule) for rule in rules)
    }
    if len(projected_checkout) > MAX_SOURCE_SNAPSHOT_FILES:
        verification_errors.append("legacy source projection exceeds the file limit")
    missing_revision_inputs = sorted(
        relative
        for paths in state["revision_inventory"].values()
        for relative in paths
        if relative not in projected_checkout
    )
    if missing_revision_inputs:
        verification_errors.append("legacy snapshot cannot reproduce revision inputs")

    current_checkout: dict[str, str] = {}
    try:
        current_checkout = checkout_snapshot(
            root,
            state["feature"],
            state,
            extra_rules=allowed_paths,
        )
    except PipelineError as exc:
        verification_errors.append(str(exc))
    changed_paths = (
        changed_checkout_paths(projected_checkout, current_checkout)
        if current_checkout
        else []
    )
    if changed_paths:
        verification_errors.append("candidate bytes differ from immutable checkout digests")

    legacy_text = snapshot.get("checkout_text") if isinstance(snapshot, dict) else None
    event = {
        "event": "legacy_lease_snapshot_migrated",
        "lease_id": lease_id,
        "role": role,
        "from_schema": snapshot.get("snapshot_schema") if isinstance(snapshot, dict) else None,
        "to_schema": LEASE_SNAPSHOT_SCHEMA,
        "legacy_checkout_text_sha256": canonical_json_sha256(legacy_text),
        "base_checkout_sha256": canonical_json_sha256(legacy_checkout),
        "current_checkout_sha256": (
            checkout_snapshot_sha256(current_checkout) if current_checkout else None
        ),
        "changed_path_count": len(changed_paths),
        "changed_paths_sha256": canonical_json_sha256(changed_paths),
        "changed_paths": changed_paths[:STATUS_ID_LIMIT],
        "changed_paths_truncated": len(changed_paths) > STATUS_ID_LIMIT,
        "projected_file_count": len(projected_checkout),
        "resume_phase": expected_phase,
        "recorded_at": migrated_at,
    }

    legacy_authorization = (
        snapshot.get("authorization_checkout") if isinstance(snapshot, dict) else None
    )
    projected_authorization = {
        relative: digest
        for relative, digest in (
            legacy_authorization if isinstance(legacy_authorization, dict) else {}
        ).items()
        if relative in projected_checkout
    }
    if not projected_authorization:
        projected_authorization = copy.deepcopy(projected_checkout)
    authorization = copy.deepcopy(
        lease.get("scope_authorization") if isinstance(lease, dict) else None
    )
    if isinstance(authorization, dict):
        authorization["checkout_snapshot_sha256"] = checkout_snapshot_sha256(
            projected_authorization
        )
        authorization["diff_base_checkout_sha256"] = checkout_snapshot_sha256(
            projected_checkout
        )

    proofs: dict[str, dict[str, Any]] = {}
    candidate_snapshot: dict[str, Any] | None = None
    if not verification_errors:
        try:
            proofs = line_proof_snapshot(root, projected_checkout, allowed_paths)
            candidate_snapshot = {
                "capsule_path": snapshot.get("capsule_path") or lease.get("capsule_path") or "",
                "capsule_sha256": snapshot.get("capsule_sha256") or lease.get("capsule_sha256") or "",
                "checkout": projected_checkout,
                "authorization_checkout": projected_authorization,
                "line_proofs": proofs,
                "snapshot_schema": LEASE_SNAPSHOT_SCHEMA,
                "snapshot_format": LEASE_SNAPSHOT_FORMAT,
                "source_projection_rules": rules,
                "rebaseline_carried": bool(lease.get("rebaseline_carried")),
                "scope_authorization": authorization,
                "created_at": snapshot.get("created_at") or migrated_at,
                "migration": copy.deepcopy(event),
            }
            encoded_size = len(
                json.dumps(
                    candidate_snapshot,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            if encoded_size > MAX_LEASE_SNAPSHOT_BYTES:
                verification_errors.append("migrated snapshot exceeds the serialized size limit")
                candidate_snapshot = None
        except (OSError, PipelineError) as exc:
            verification_errors.append(str(exc))
            candidate_snapshot = None

    if candidate_snapshot is not None and not verification_errors:
        lease["scope_authorization"] = authorization
        state["lease_snapshots"][lease_id] = candidate_snapshot
        event.update(
            {
                "outcome": "continued",
                "files_untouched": True,
                "line_proof_file_count": len(proofs),
                "result_phase": expected_phase,
            }
        )
    else:
        result_phase = state.get("phase")
        if expected_phase == "decision_recording":
            result_phase = (state.get("decision_recording") or {}).get("resume_phase") or "preflight"
            state["decision_recording"] = None
        released = dict(lease) if isinstance(lease, dict) else {"lease_id": lease_id}
        released.update(
            {
                "status": "revoked",
                "result": "migration_unverifiable",
                "reason": "legacy snapshot could not be verified from immutable digests",
                "released_at": migrated_at,
            }
        )
        state.setdefault("write_lease_history", []).append(released)
        state["active_write_lease"] = None
        state.setdefault("lease_snapshots", {}).pop(lease_id, None)
        if role == "engineer":
            prior_owner_id = lease.get("worker_id") if isinstance(lease, dict) else None
            if prior_owner_id and prior_owner_id not in state.setdefault(
                "exhausted_worker_ids", []
            ):
                state["exhausted_worker_ids"].append(prior_owner_id)
            base_proofs = {
                relative: {
                    "sha256": digest,
                    "byte_count": None,
                    "line_count": None,
                    "line_hashes": None,
                }
                for relative, digest in projected_checkout.items()
            }
            changes = [
                {
                    "path": relative,
                    "base_sha256": projected_checkout.get(relative),
                    "candidate_sha256": current_checkout.get(relative),
                    "change_kind": (
                        "add" if relative not in projected_checkout
                        else "delete" if relative not in current_checkout
                        else "modify"
                    ),
                }
                for relative in changed_checkout_paths(projected_checkout, current_checkout)
            ]
            slice_id = (
                lease.get("write_scope")
                if isinstance(lease, dict) and lease.get("write_scope") in state.get("slices", {})
                else state.get("active_slice") or state.get("slice_id")
            )
            recovery = {
                "schema": 1,
                "kind": "legacy_unverifiable_candidate",
                "prior_lease_id": lease_id,
                "prior_owner_id": prior_owner_id,
                "base_checkout_sha256": checkout_snapshot_sha256(projected_checkout),
                "candidate_checkout_sha256": checkout_snapshot_sha256(current_checkout),
                "changes_sha256": canonical_json_sha256(changes),
                "changes": changes,
                "recorded_at": migrated_at,
            }
            state["scope_guard"]["rebaseline_candidate"] = {
                "slice_id": slice_id,
                "prior_lease_id": lease_id,
                "prior_owner_id": recovery["prior_owner_id"],
                "fresh_owner_required": True,
                "resume_phase": result_phase,
                "snapshot": {
                    "capsule_path": snapshot.get("capsule_path", "") if isinstance(snapshot, dict) else "",
                    "capsule_sha256": snapshot.get("capsule_sha256", "") if isinstance(snapshot, dict) else "",
                    "checkout": projected_checkout,
                    "authorization_checkout": current_checkout,
                    "line_proofs": base_proofs,
                    "snapshot_schema": LEASE_SNAPSHOT_SCHEMA,
                    "snapshot_format": LEASE_SNAPSHOT_FORMAT,
                    "source_projection_rules": rules,
                    "rebaseline_carried": True,
                    "scope_authorization": None,
                    "created_at": migrated_at,
                },
                "changes": changes,
                "base_revisions": {
                    key: state.get(key) for key in (
                        "revision", "product_revision", "support_revision", "evidence_revision"
                    )
                },
                "candidate_checkout": current_checkout,
                "recovery": recovery,
            }
            state["phase"] = "owner_handoff_hold"
            event["candidate_recovery_sha256"] = canonical_json_sha256(recovery)
        else:
            state["phase"] = result_phase
        event.update(
            {
                "outcome": (
                    "candidate_handoff_required" if role == "engineer"
                    else "revoked_unverifiable"
                ),
                "files_untouched": True,
                "continuity_preserved": False,
                "line_proof_file_count": 0,
                "result_phase": state["phase"],
                "verification_error_sha256": canonical_json_sha256(verification_errors),
            }
        )
    state.setdefault("lease_snapshot_sanitizations", []).append(event)
    return event


def migrate_schema9_runtime(
    root: Path, state: dict[str, Any], findings: dict[str, Any]
) -> bool:
    if (
        state.get("schema_version") != LEGACY_SCHEMA_VERSION
        or findings.get("schema_version") != LEGACY_SCHEMA_VERSION
        or state.get("contract_version") != LEGACY_CONTRACT_VERSION
    ):
        return False
    migrated_at = utc_now()
    active = state.get("active_write_lease")
    active_id = active.get("lease_id") if isinstance(active, dict) else None
    legacy_ids = [
        lease_id
        for lease_id, snapshot in (state.get("lease_snapshots") or {}).items()
        if not isinstance(snapshot, dict)
        or snapshot.get("snapshot_schema") != LEASE_SNAPSHOT_SCHEMA
        or snapshot.get("snapshot_format") != LEASE_SNAPSHOT_FORMAT
        or "checkout_text" in snapshot
    ]
    orphaned = sorted(set(legacy_ids) - ({active_id} if active_id else set()))
    for lease_id in orphaned:
        state["lease_snapshots"].pop(lease_id, None)
    state.setdefault("lease_snapshot_sanitizations", [])
    active_migration = None
    if active_id in legacy_ids:
        active_migration = migrate_active_legacy_snapshot(
            root, state, active_id, migrated_at
        )
    state["schema_version"] = SCHEMA_VERSION
    state["contract_version"] = CONTRACT_VERSION
    state.pop("findings_sha256", None)
    state.pop("canonical_findings", None)
    findings["schema_version"] = SCHEMA_VERSION
    event = {
        "event": "schema9_to_schema10_migration",
        "from_schema": LEGACY_SCHEMA_VERSION,
        "to_schema": SCHEMA_VERSION,
        "legacy_active_lease_id": active_id if active_id in legacy_ids else None,
        "discarded_orphan_snapshot_ids": orphaned,
        "active_snapshot_outcome": (
            active_migration.get("outcome") if active_migration else None
        ),
        "migrated_at": migrated_at,
    }
    state.setdefault("schema_migrations", []).append(event)
    return True


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
    state.setdefault("generation", 0)
    state.setdefault("schema_migrations", [])
    state.setdefault("exhausted_worker_ids", [])
    state.setdefault("lease_snapshot_sanitizations", [])
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
    state["required_reviews"] = 1
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
    state.setdefault("revision_records", None)
    state.setdefault("lifecycle_projection_guard", None)
    state.setdefault("lifecycle_projection_reconciliations", [])
    state.setdefault("legacy_scope_recoveries", [])
    state.setdefault("authority_recovery_history", [])
    active_lease = state.get("active_write_lease")
    if (
        isinstance(active_lease, dict)
        and active_lease.get("role") == "engineer"
        and not active_lease.get("scope_authorization")
    ):
        legacy_snapshot = state.get("lease_snapshots", {}).get(
            active_lease.get("lease_id")
        )
        if isinstance(legacy_snapshot, dict) and "snapshot_schema" not in legacy_snapshot:
            legacy_snapshot["_legacy_scope_snapshot_eligible"] = True
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
    state.setdefault("ready_targeted_closure_clean_recoveries", [])
    state.setdefault("preflight", empty_preflight_state())
    preflight = state["preflight"]
    preflight.setdefault("minimum_resume_actions", {})
    preflight.setdefault("proof_version", None)
    preflight.setdefault("required_capability_ids", [])
    preflight.setdefault("required_capability_digest", None)
    preflight.setdefault("resume_contract_complete", False)
    preflight.setdefault("migration_resume_phase", None)
    state.setdefault("preflight_migration_hold", None)
    state.setdefault("preflight_migration_history", [])
    phase = state.get("phase")
    if phase not in {
        "preflight",
        "preflight_migration_hold",
    }:
        proof_error = preflight_proof_error(state)
        if proof_error:
            state["preflight_migration_hold"] = {
                "resume_phase": phase,
                "reason": proof_error,
                "required_capability_ids": sorted(
                    required_preflight_capabilities(state)
                ),
            }
            state["phase"] = "preflight_migration_hold"
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
        item.setdefault("blocks_required_support_contract", False)
        item.setdefault("required_support_contract_evidence", None)
        item.setdefault("coverage_identity_ids", [])
        item.setdefault("remediation_required", finding_requires_remediation(item))
    state.setdefault("finding_triage", None)


def require_revision_inventory_current(
    root: Path, state: dict[str, Any], findings: dict[str, Any]
) -> bool:
    computed = compute_inventory_revisions(root, state)
    stale = [
        key
        for key in ("revision", "product_revision", "support_revision", "evidence_revision")
        if computed[key] != state.get(key)
    ]
    if stale:
        carried = state.get("scope_guard", {}).get("rebaseline_candidate")
        if isinstance(carried, dict) and carried.get("fresh_owner_required") is True:
            expected = carried.get("candidate_checkout")
            snapshot = carried.get("snapshot") or {}
            if (
                isinstance(expected, dict)
                and checkout_snapshot(
                    root,
                    state["feature"],
                    state,
                    extra_rules=snapshot.get("source_projection_rules") or [],
                ) == expected
                and checkout_snapshot_sha256(expected)
                == (carried.get("recovery") or {}).get("candidate_checkout_sha256")
            ):
                return False
            raise PipelineError("Preserved Engineer candidate bytes changed after recovery")
        if try_reconcile_lifecycle_projection_drift(root, state, findings, computed):
            return True
        raise PipelineError(
            "Controller revision inventory drifted outside an active writer completion: "
            + ", ".join(stale)
        )
    return False


def commit_runtime_generation(
    state_path: Path,
    findings_path: Path,
    state: dict[str, Any],
    findings: dict[str, Any],
) -> None:
    """Commit one canonical state document; findings.json is a compatibility projection."""
    root, expected_state, expected_findings = runtime_paths(
        str(state_path.parent.parent)
    )
    if state_path.absolute() != expected_state.absolute() or findings_path.absolute() != expected_findings.absolute():
        raise PipelineError("Runtime persistence paths do not match the safe controller root")
    lock_path = resolve_runtime_control_path(root, f"{STATE_DIR}/runtime.lock")
    with runtime_write_lock(lock_path):
        disk_generation = 0
        if state_path.is_file():
            disk_state = read_json(state_path)
            disk_generation = disk_state.get("generation", 0)
        expected_generation = state.get("generation", 0)
        if (
            not isinstance(disk_generation, int)
            or isinstance(disk_generation, bool)
            or not isinstance(expected_generation, int)
            or isinstance(expected_generation, bool)
            or expected_generation != disk_generation
        ):
            raise PipelineError(
                "Concurrent runtime update detected; reload state before retrying "
                f"(expected generation {expected_generation}, current {disk_generation})"
            )
        new_generation = expected_generation + 1
        findings["generation"] = new_generation
        state["generation"] = new_generation
        state["findings_sha256"] = canonical_json_sha256(findings)
        state["canonical_findings"] = copy.deepcopy(findings)
        # State is the canonical transaction and embeds findings. Compatibility
        # findings and the ledger are projections repaired from this commit.
        write_json(state_path, state)
        write_json(findings_path, findings)


def load_canonical_findings(
    state: dict[str, Any], findings_path: Path
) -> dict[str, Any]:
    if state.get("schema_version") == LEGACY_SCHEMA_VERSION:
        return read_json(findings_path)
    embedded = state.get("canonical_findings")
    if embedded is None:
        compatibility = read_json(findings_path)
        if (
            compatibility.get("generation") != state.get("generation")
            or canonical_json_sha256(compatibility) != state.get("findings_sha256")
        ):
            raise PipelineError(
                "Legacy split runtime findings do not match the state generation/digest"
            )
        return compatibility
    if not isinstance(embedded, dict):
        raise PipelineError("Canonical runtime findings are malformed")
    digest = state.get("findings_sha256")
    if (
        not isinstance(digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        or canonical_json_sha256(embedded) != digest
        or embedded.get("generation") != state.get("generation")
    ):
        raise PipelineError("Canonical runtime findings generation/digest is inconsistent")
    return copy.deepcopy(embedded)


def load_runtime(
    project_root: str,
    *,
    allow_active_writer_completion_drift: bool = False,
) -> tuple[Path, Path, Path, dict[str, Any], dict[str, Any]]:
    root, state_path, findings_path = runtime_paths(project_root)
    state = read_json(state_path)
    findings = load_canonical_findings(state, findings_path)
    migrated = migrate_schema9_runtime(root, state, findings)
    if state.get("schema_version") != SCHEMA_VERSION or findings.get("schema_version") != SCHEMA_VERSION:
        raise PipelineError(
            "Unsupported pipeline state; only the exact schema-9 contract has a safe "
            "schema-10 migration. Older or unknown states must be reinitialized "
            "explicitly because leases, decisions, coverage, documentation, capsules, and "
            "handoffs cannot be inferred safely"
        )
    if state.get("contract_version") != CONTRACT_VERSION:
        raise PipelineError("Pipeline contract changed after initialization; reinitialize explicitly")
    normalize_runtime(state, findings)
    validate_schema10_runtime(state, findings)
    entries, _, _ = canonical_decision_ledger(root, state)
    validate_user_authority_registry(root, state)
    for entry in entries:
        authority = entry.get("authority")
        if not isinstance(authority, dict) or set(authority) != {
            "kind",
            "reference",
            "path",
            "sha256",
            "section_or_id",
        }:
            raise PipelineError(
                f"Decision ledger entry {entry.get('decision_id')} has malformed authority"
            )
        validate_decision_authority(root, state, authority, entry["statement"], None)
    if allow_active_writer_completion_drift:
        lease = state.get("active_write_lease")
        if not isinstance(lease, dict) or lease.get("status") != "active":
            raise PipelineError(
                "Revision-drift bypass is valid only inside an exact active writer completion"
            )
    elif not migrated:
        reconciled = require_revision_inventory_current(root, state, findings)
    return root, state_path, findings_path, state, findings


def materialize_pending_lifecycle_projection_receipt(
    root: Path, state: dict[str, Any]
) -> None:
    pending_receipt = state.get("pending_lifecycle_projection_receipt")
    if not isinstance(pending_receipt, dict):
        return
    receipt_path = resolve_runtime_control_path(root, pending_receipt["path"])
    if receipt_path.exists():
        if (
            read_json(receipt_path) != pending_receipt.get("value")
            or file_sha256(receipt_path) != pending_receipt.get("sha256")
        ):
            raise PipelineError("Lifecycle reconciliation orphan receipt conflicts")
    else:
        write_json(receipt_path, pending_receipt["value"])
    if file_sha256(receipt_path) != pending_receipt.get("sha256"):
        raise PipelineError("Lifecycle reconciliation receipt digest is inconsistent")


def save_runtime(
    state_path: Path,
    findings_path: Path,
    state: dict[str, Any],
    findings: dict[str, Any],
) -> None:
    pending_receipt = state.get("pending_lifecycle_projection_receipt")
    if isinstance(pending_receipt, dict):
        materialize_pending_lifecycle_projection_receipt(
            state_path.parent.parent, state
        )
        state.pop("pending_lifecycle_projection_receipt", None)
    computed = compute_inventory_revisions(state_path.parent.parent, state)
    if all(
        computed[key] == state.get(key)
        for key in ("revision", "product_revision", "support_revision", "evidence_revision")
    ):
        state["revision_records"] = computed["records"]
        guards = [
            candidate
            for relative in state.get("revision_inventory", {}).get("product", [])
            if isinstance(relative, str) and Path(relative).name.lower() == "readme.md"
            for candidate in [lifecycle_dashboard_candidate(
                state_path.parent.parent, state, relative
            )]
            if candidate is not None
        ]
        if len(guards) == 1:
            candidate = guards[0]
            state["lifecycle_projection_guard"] = {
                "schema": 1,
                "feature_id": candidate["feature_id"],
                "feature_slug": candidate["feature_slug"],
                "dashboard_path": candidate["dashboard_path"],
                "manifest_path": candidate["manifest_path"],
                "dashboard_sha256": file_sha256(candidate["dashboard"]),
                "manifest_sha256": file_sha256(candidate["manifest"]),
                "updated_date": candidate["current_date"],
            }
    state["updated_at"] = utc_now()
    commit_runtime_generation(state_path, findings_path, state, findings)
    # JSONL is a projection of the already-committed canonical ledger
    # transaction. Exact retry is safe before or after this materialization.
    project_canonical_decision_ledger(state_path.parent.parent, state)
    latest_capsule = (state.get("context_capsules") or [None])[-1]
    latest_handoff = (state.get("handoffs") or [None])[-1]

    def artifact_reference(record: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(record, dict):
            return None
        return {
            key: record.get(key)
            for key in (
                "capsule_id",
                "handoff_id",
                "path",
                "sha256",
                "capsule_sha256",
                "handoff_sha256",
                "role",
                "phase",
                "worker_id",
            )
            if record.get(key) is not None
        }

    route = next_action(state, findings)
    checkpoint = {
        "schema": 1,
        "feature": state.get("feature"),
        "phase": state.get("phase"),
        "next_action": route,
        "user_input_required": bool(route.get("user_input_required")),
        "revisions": {
            key: state.get(key)
            for key in (
                "revision",
                "product_revision",
                "support_revision",
                "evidence_revision",
            )
        },
        "active_slice": state.get("active_slice"),
        "active_write_lease": compact_write_lease(state.get("active_write_lease")),
        "active_remediation_batch": state.get("active_remediation_batch"),
        "latest_capsule": artifact_reference(latest_capsule),
        "latest_handoff": artifact_reference(latest_handoff),
        "iteration_control": state.get("iteration_control"),
        "worker_budget": {
            key: state.get("worker_budget", {}).get(key)
            for key in (
                "status",
                "workers_used",
                "max_workers",
                "full_review_waves",
                "max_full_review_waves",
                "checkpoint_causes",
            )
            if key in state.get("worker_budget", {})
        },
        "state_sha256": file_sha256(state_path),
        "findings_sha256": file_sha256(findings_path),
        "generated_at": utc_now(),
    }
    write_json(state_path.parent / DIRECTOR_CHECKPOINT.name, checkpoint)


def open_blocking(findings: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in findings["items"]
        if item["status"] == "open" and item.get("blocking") is True
    ]


def finding_requires_remediation(item: dict[str, Any]) -> bool:
    return item.get("blocking") is True or (
        item.get("finding_kind") == "support"
        and item.get("blocks_required_support_contract") is True
    )


def open_remediation_required(findings: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in findings["items"]
        if item["status"] == "open" and finding_requires_remediation(item)
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


def required_support_contract_paths(state: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    for contract in (state.get("plan_contracts", {}).get("slices") or {}).values():
        value = (contract.get("documentation") or {}).get(
            "derived_post_qa_paths", ""
        )
        if value.startswith("not_required"):
            continue
        paths.update(scope_path(item, "required support contract") for item in comma_values(value))
    return paths


def assigned_acceptance_evidence_prefix(acceptance_ids: list[str]) -> str:
    return (
        f"{ASSIGNED_ACCEPTANCE_EVIDENCE_PREFIX} "
        f"{', '.join(sorted(set(acceptance_ids)))} |"
    )


def validate_finding_dimensions(state: dict[str, Any], item: dict[str, Any]) -> None:
    acceptance_ids = item["blocks_acceptance_ids"]
    unknown_acceptance = sorted(set(acceptance_ids) - planned_acceptance_ids(state))
    if unknown_acceptance:
        raise PipelineError(
            "Finding blocks acceptance IDs outside the approved plan: "
            + ", ".join(unknown_acceptance)
        )
    if acceptance_ids:
        evidence_prefix = assigned_acceptance_evidence_prefix(acceptance_ids)
        evidence = item.get("evidence")
        if (
            not isinstance(evidence, str)
            or not evidence.startswith(evidence_prefix)
            or not evidence[len(evidence_prefix) :].strip()
        ):
            raise PipelineError(
                "A finding that blocks assigned acceptance must cite the exact IDs as "
                f"'{evidence_prefix} <component/path/receipt evidence>'"
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
    support_contract_evidence = item.get("required_support_contract_evidence")
    if item.get("blocks_required_support_contract") is True:
        if item["finding_kind"] != "support":
            raise PipelineError(
                "Only a support finding may block an explicit required-support contract"
            )
        if support_contract_evidence not in required_support_contract_paths(state):
            raise PipelineError(
                "Required-support remediation needs an exact path from the approved "
                "derived_post_qa_paths contract"
            )
    elif support_contract_evidence:
        raise PipelineError(
            "--required-support-contract-evidence requires "
            "--blocks-required-support-contract=true"
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
    direct_assigned_binding = bool(
        acceptance_ids
        or item["violates_required_invariant"]
        or item.get("blocks_required_support_contract") is True
        or (item.get("source") == "qa" and item.get("coverage_identity_ids"))
    )
    if (
        item.get("source") in {"review", "qa"}
        and item["scope_relation"] in BLOCKING_SCOPE_RELATIONS
        and not direct_assigned_binding
    ):
        raise PipelineError(
            "Review/QA current-scope findings require an exact assigned acceptance, "
            "required invariant/support contract, or finalized QA identity binding; "
            "record unrelated side issues in the deferred backlog"
        )
    item["blocking"] = finding_is_blocking(item)
    item["remediation_required"] = finding_requires_remediation(item)
    deferred_reference = item.get("deferred_reference")
    if (
        item["scope_relation"] in {"preexisting_adjacent", "out_of_scope"}
        and item["production_reachability"] != "unknown"
        and not deferred_reference
    ):
        raise PipelineError(
            "A classified side finding requires a canonical deferred backlog reference"
        )
    if (
        item["scope_relation"] in {"preexisting_adjacent", "out_of_scope"}
        and candidate_requires_current_scope(item)
    ):
        raise PipelineError(
            "A candidate introduced/worsened by this change, reached by the feature path "
            "or changed contract, blocking assigned acceptance/invariant, or carrying a "
            "safety impact cannot be classified as a deferred side issue"
        )
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
        "minimum_resume_actions": {},
        "proof_version": None,
        "required_capability_ids": [],
        "required_capability_digest": None,
        "resume_contract_complete": False,
        "migration_resume_phase": None,
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


def worker_is_writer(state: dict[str, Any], worker_id: str) -> bool:
    if worker_id == state.get("engineering_owner_id"):
        return True
    leases = list(state.get("write_lease_history", []))
    if state.get("active_write_lease"):
        leases.append(state["active_write_lease"])
    return any(
        lease.get("worker_id") == worker_id and lease.get("role") in WRITE_ROLES
        for lease in leases
    )


def require_verifier_assignment(state: dict[str, Any], worker_id: str) -> None:
    verifier_roles = {"convergence_audit", "full_review", "runtime_qa"}
    identities = {
        record.get("worker_id")
        for record in (state.get("worker_budget") or {}).get("records", [])
        if record.get("role") in verifier_roles and record.get("worker_id")
    }
    if identities and identities != {worker_id}:
        raise PipelineError(
            f"Verifier assignment history is {', '.join(sorted(identities))}; "
            "convergence, Final Review, and QA "
            "must reuse the same independent worker identity"
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


def command_request_sha256(
    root: Path,
    command: str,
    fields: dict[str, Any],
    artifacts: dict[str, str] | None = None,
) -> str:
    """Bind a completion request to current artifact bytes without a retry registry."""
    bound: dict[str, dict[str, str]] = {}
    for label, supplied in sorted((artifacts or {}).items()):
        path = Path(supplied)
        if not path.is_absolute():
            path = root / path
        path = path.resolve()
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError as exc:
            raise PipelineError(f"{label} replay artifact escapes project root") from exc
        if not path.is_file():
            raise PipelineError(f"{label} replay artifact is missing: {relative}")
        bound[label] = {"path": relative, "sha256": file_sha256(path)}
    return canonical_json_sha256(
        {"command": command, "fields": fields, "artifacts": bound}
    )


def exact_lost_response_replay(
    record: dict[str, Any] | None, request_sha256: str, label: str
) -> bool:
    if record is None:
        return False
    if record.get("request_sha256") == request_sha256:
        return True
    raise PipelineError(f"{label} lost-response replay mismatch; refusing duplicate mutation")


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


def exact_inventory_digest(root: Path, paths: list[str], label: str) -> str:
    if not paths:
        raise PipelineError(f"{label} must name at least one repository file")
    normalized = [scope_path(item, label) for item in paths]
    if len(normalized) != len(set(normalized)):
        raise PipelineError(f"{label} repeats a path")
    rows: list[str] = []
    for relative in sorted(normalized):
        path = resolve_project_file(root, relative, label)
        rows.append(f"{relative}\0{file_sha256(path)}\n")
    return hashlib.sha256("".join(rows).encode("utf-8")).hexdigest()


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
    exact_envelope = {
        "schema_version",
        "revision",
        "reviewer_id",
        "review_mode",
        "components",
    }
    if require_composition_audit:
        exact_envelope.update({"composition_audit", "new_boundaries_audited"})
    if set(manifest) != exact_envelope:
        raise PipelineError(
            "Review credit manifest must use the exact command-specific schema-1 envelope"
        )
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
    represented_product_paths: set[str] = set()
    for item in components:
        if not isinstance(item, dict) or set(item) != {
            "component",
            "product_paths",
            "contract_paths",
            "product_hash",
            "contract_hash",
            "lenses",
            "mode",
            "source_credit_id",
        }:
            raise PipelineError(
                "Every component Review credit must use the exact inventory-backed fields"
            )
        component = str(item.get("component", "")).strip()
        product_hash = str(item.get("product_hash", "")).strip()
        contract_hash = str(item.get("contract_hash", "")).strip()
        product_paths = require_string_list(
            item.get("product_paths"),
            f"Component {component or '<unknown>'} product_paths",
            allow_empty=False,
        )
        contract_paths = require_string_list(
            item.get("contract_paths"),
            f"Component {component or '<unknown>'} contract_paths",
            allow_empty=False,
        )
        normalized_product_paths = [scope_path(path, "Component product path") for path in product_paths]
        normalized_contract_paths = [scope_path(path, "Component contract path") for path in contract_paths]
        current_inventory = set(state["revision_inventory"]["product"])
        if not set(normalized_product_paths).issubset(current_inventory) or not set(
            normalized_contract_paths
        ).issubset(current_inventory):
            raise PipelineError("Component Review paths must come from current product inventory")
        if product_hash != exact_inventory_digest(root, normalized_product_paths, "Component product inventory"):
            raise PipelineError(f"Component Review product_hash is stale for {component}")
        if contract_hash != exact_inventory_digest(root, normalized_contract_paths, "Component contract inventory"):
            raise PipelineError(f"Component Review contract_hash is stale for {component}")
        represented_product_paths.update(normalized_product_paths)
        lenses = require_string_list(
            item.get("lenses"), "Component Review credit lenses", allow_empty=False
        )
        lenses = sorted(set(lenses))
        if any(lens not in CONVERGENCE_LENSES for lens in lenses):
            raise PipelineError(f"Component Review credit has an unsupported lens: {component}")
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
            if item.get("source_credit_id") is not None:
                raise PipelineError(
                    f"Fresh Review credit for {component} must use source_credit_id=null"
                )
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
                "product_paths": sorted(normalized_product_paths),
                "contract_paths": sorted(normalized_contract_paths),
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
    if represented_product_paths != set(state["revision_inventory"]["product"]):
        missing = sorted(set(state["revision_inventory"]["product"]) - represented_product_paths)
        extra = sorted(represented_product_paths - set(state["revision_inventory"]["product"]))
        raise PipelineError(
            "Component Review manifest must cover exact current product inventory; missing="
            + ",".join(missing)
            + " extra="
            + ",".join(extra)
        )
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
    if set(bundle) != {"schema_version", "brief", "result"} or bundle.get("schema_version") != 1:
        raise PipelineError("Research bundle must use schema_version 1")
    brief = bundle.get("brief")
    result = bundle.get("result")
    if not isinstance(brief, dict) or not isinstance(result, dict):
        raise PipelineError("Research bundle must contain brief and result objects")

    exact_brief_fields = {
        "brief_id", "question", "slice_id", "base_revision", "requirement_ids",
        "seed_paths", "allowed_paths", "allowed_symbols", "exclusions",
        "requested_evidence", "max_files", "stop_condition", "output_path",
    }
    exact_result_fields = {
        "brief_id", "researcher_id", "base_revision", "brief_sha256", "status",
        "inspected_paths", "inspected_symbols", "owners_contracts_precedents",
        "lifecycle_integration_risks", "minimal_edit_reuse_points",
        "unresolved_questions", "out_of_brief_pointers",
    }
    if set(brief) != exact_brief_fields:
        raise PipelineError("Research brief must use the exact schema-1 fields")
    if set(result) != exact_result_fields:
        raise PipelineError("Research result must use the exact schema-1 fields")

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
    active_slice = state.get("slices", {}).get(slice_id)
    if not isinstance(active_slice, dict):
        raise PipelineError("Research bundle cannot resolve the active approved slice")
    approved_requirement_ids = set(active_slice.get("requirement_ids", []))
    approved_acceptance_ids = set(
        active_slice.get("scope_contract", {}).get("acceptance_ids", [])
    )
    supplied_requirements = {item for item in requirement_ids if item.startswith("PRD-REQ-")}
    supplied_acceptance = {item for item in requirement_ids if item.startswith("PRD-AC-")}
    if (
        len(requirement_ids) != len(set(requirement_ids))
        or supplied_requirements | supplied_acceptance != set(requirement_ids)
        or not supplied_requirements
        or not supplied_acceptance
        or not supplied_requirements.issubset(approved_requirement_ids)
        or not supplied_acceptance.issubset(approved_acceptance_ids)
    ):
        raise PipelineError(
            "Research brief requirement_ids must be a duplicate-free non-empty PRD-REQ/PRD-AC subset of the active slice"
        )
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
    if len(normalized_allowed_paths) != len(set(normalized_allowed_paths)):
        raise PipelineError("Research brief allowed_paths repeats a path")
    for allowed in normalized_allowed_paths:
        allowed_path = (root / allowed).resolve()
        if not allowed_path.exists() or not (allowed_path.is_file() or allowed_path.is_dir()):
            raise PipelineError("Every research allowed_path must exist as a file or directory")
    for seed in seed_paths:
        if not research_path_is_allowed(seed, normalized_allowed_paths):
            raise PipelineError("Every research seed_path must stay within allowed_paths")
        seed_path = (root / normalize_research_path(seed, "Research brief seed_paths")).resolve()
        if not seed_path.is_file():
            raise PipelineError("Every research seed_path must exist and be a file")
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
    research_contract = (
        state.get("plan_contracts", {}).get("slices", {}).get(slice_id, {}).get("research")
    )
    if not isinstance(research_contract, dict) or research_contract.get("mode") != "required":
        raise PipelineError("Approved plan does not authorize a Research bundle for this slice")
    approved_briefs = {
        item.get("brief_id"): item
        for item in research_contract.get("briefs", [])
        if isinstance(item, dict)
    }
    approved = approved_briefs.get(brief["brief_id"])
    if approved is None:
        raise PipelineError("Research bundle brief_id is not approved by the exact development plan")
    selector_fields = (
        "question",
        "seed_paths",
        "exclusions",
        "requested_evidence",
        "stop_condition",
    )
    if any(brief.get(field) != approved.get(field) for field in selector_fields):
        raise PipelineError(
            "Research bundle content selectors differ from the exact approved plan brief"
        )
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
        inspected_path = (
            root / normalize_research_path(inspected, "Research result inspected_paths")
        ).resolve()
        if not inspected_path.is_file():
            raise PipelineError("Every research inspected_path must exist and be a file")
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


def validate_identity_coordinates(identity: dict[str, Any], label: str) -> None:
    required = {
        "identity_id",
        "kind",
        "mandatory",
        "slice_id",
        "requirement_ids",
        "acceptance_ids",
        "coordinates",
        "planned_assertion_or_observation",
        "capability_prerequisites",
    }
    if not isinstance(identity, dict) or set(identity) != required:
        raise PipelineError(f"{label} must use the exact schema-2 identity fields")
    if not isinstance(identity["identity_id"], str) or not identity["identity_id"]:
        raise PipelineError(f"{label} identity_id is required")
    if identity["kind"] not in {"automated", "manual"} or not isinstance(
        identity["mandatory"], bool
    ):
        raise PipelineError(f"{label} kind/mandatory is invalid")
    for field in ("requirement_ids", "acceptance_ids", "capability_prerequisites"):
        require_string_list(identity[field], f"{label} {field}")
    try:
        parsed_capabilities = [
            _capability_contract.require_capability_id(
                item, label=f"{label} capability prerequisite"
            )
            for item in identity["capability_prerequisites"]
        ]
    except ValueError as exc:
        raise PipelineError(str(exc)) from exc
    if len(parsed_capabilities) != len(set(parsed_capabilities)):
        raise PipelineError(f"{label} repeats a capability prerequisite")
    coordinates = identity["coordinates"]
    if not isinstance(coordinates, dict):
        raise PipelineError(f"{label} coordinates must be an object")
    required_coordinates = (
        {"file", "suite", "symbol", "case"}
        if identity["kind"] == "automated"
        else {"scenario_id", "topology", "setup", "action", "observation", "evidence_kind"}
    )
    if set(coordinates) != required_coordinates or any(
        not isinstance(coordinates[field], str) or not coordinates[field].strip()
        for field in required_coordinates
    ):
        raise PipelineError(f"{label} has incomplete exact coordinates")
    if not isinstance(identity["planned_assertion_or_observation"], str) or not identity[
        "planned_assertion_or_observation"
    ].strip():
        raise PipelineError(f"{label} planned assertion/observation is required")


def coverage_plan_body_digest(manifest: dict[str, Any]) -> str:
    return canonical_json_sha256(
        {
            "ac_mappings": manifest["ac_mappings"],
            "expected_identities": manifest["expected_identities"],
            "mandatory_expected_identity_ids": manifest[
                "mandatory_expected_identity_ids"
            ],
        }
    )


def coverage_semantic_projection(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mappings = {
        item["acceptance_id"]: item
        for item in manifest.get("ac_mappings", [])
        if isinstance(item, dict) and isinstance(item.get("acceptance_id"), str)
    }
    identities = {
        item["identity_id"]: item
        for item in manifest.get("expected_identities", [])
        if isinstance(item, dict) and isinstance(item.get("identity_id"), str)
    }
    mandatory = set(manifest.get("mandatory_expected_identity_ids", []))
    acceptance_ids = set(mappings)
    for identity in identities.values():
        acceptance_ids.update(identity.get("acceptance_ids", []))
    projection: dict[str, dict[str, Any]] = {}
    for acceptance_id in acceptance_ids:
        mapping = mappings.get(acceptance_id)
        related_ids = {
            identity_id
            for identity_id, identity in identities.items()
            if acceptance_id in identity.get("acceptance_ids", [])
            or (mapping and identity_id in mapping.get("identity_ids", []))
        }
        projection[acceptance_id] = {
            "mapping": mapping,
            "expected_identities": [identities[item] for item in sorted(related_ids)],
            "mandatory_expected_identity_ids": sorted(related_ids.intersection(mandatory)),
        }
    return projection


def validate_coverage_amendment_authority(
    state: dict[str, Any],
    findings: dict[str, Any],
    authority_id: str,
    affected: set[str],
    *,
    appended: bool,
) -> None:
    root = Path(state["project_root"])
    ledger_entries, _ = read_decision_ledger(root / state["decision_ledger"]["path"])
    decisions = {entry["decision_id"]: entry for entry in ledger_entries}
    decision = decisions.get(authority_id)
    if decision is not None:
        if appended and authority_id not in state["decision_ledger"]["active_decision_ids"]:
            raise PipelineError("New coverage amendment requires an active accepted decision")
        if not affected.issubset(set(decision["scope_ids"])):
            raise PipelineError(
                "Coverage amendment decision must explicitly scope every affected acceptance ID"
            )
        return

    finding = next(
        (item for item in findings.get("items", []) if item.get("id") == authority_id), None
    )
    if finding is not None:
        normalized_fields = {
            "id", "source", "finding_kind", "severity", "scope_relation",
            "introduced_by_candidate", "production_reachability",
            "blocks_acceptance_ids", "violates_required_invariant",
            "required_invariant_evidence", "mandatory_core_acceptance_evidence_missing",
            "test_can_miss_product_defect", "deferred_reference", "title", "evidence",
            "revision", "origin_slice", "remediation_route", "status", "created_at",
            "resolved_revision", "blocking",
        }
        if not normalized_fields.issubset(finding):
            raise PipelineError("Coverage amendment finding authority is not normalized")
        normalized = dict(finding)
        recorded_blocking = normalized.get("blocking")
        validate_finding_dimensions(state, normalized)
        if normalized.get("blocking") != recorded_blocking:
            raise PipelineError("Coverage amendment finding classification is stale")
        if not affected.issubset(set(finding.get("blocks_acceptance_ids", []))):
            raise PipelineError(
                "Coverage amendment finding must block every affected acceptance ID"
            )
        return

    for event in state.get("scope_guard", {}).get("rebaseline_history", []):
        if authority_id not in {
            event.get("user_scope_approval"),
            event.get("approved_plan_sha256"),
        }:
            continue
        slice_item = state.get("slices", {}).get(event.get("slice_id"), {})
        approved_acceptance = set(
            (slice_item.get("scope_contract") or {}).get("acceptance_ids", [])
        )
        if not affected.issubset(approved_acceptance):
            raise PipelineError(
                "Coverage amendment rebaseline authority does not cover every affected acceptance ID"
            )
        return
    raise PipelineError("Coverage amendment authority is not controller-registered")


def validate_coverage_continuity(
    state: dict[str, Any],
    findings: dict[str, Any],
    planned: dict[str, Any],
    finalized: dict[str, Any],
) -> str:
    planned_amendments = planned.get("amendments", [])
    finalized_amendments = finalized.get("amendments", [])
    if not isinstance(planned_amendments, list) or not isinstance(finalized_amendments, list):
        raise PipelineError("Coverage amendments must be append-only lists")
    if finalized_amendments[: len(planned_amendments)] != planned_amendments:
        raise PipelineError("Coverage amendments must preserve the planned append-only prefix")
    before = coverage_plan_body_digest(planned)
    after = coverage_plan_body_digest(finalized)
    appended = finalized_amendments[len(planned_amendments) :]
    if before == after and appended:
        raise PipelineError("Coverage amendment cannot be appended without a plan-body change")
    if before != after and not appended:
        raise PipelineError(
            "Finalized coverage changed its planned body without an authorized append-only amendment"
        )
    exact = {
        "amendment_id",
        "authority_id",
        "before_digest",
        "after_digest",
        "affected_acceptance_ids",
        "reason",
    }
    seen_amendment_ids: set[str] = set()
    previous_prefix_after: str | None = None
    for amendment_index, item in enumerate(finalized_amendments):
        if not isinstance(item, dict) or set(item) != exact:
            raise PipelineError("Coverage amendment must use the exact append-only schema")
        if (
            not re.fullmatch(r"COV-AMEND-[A-Za-z0-9-]+", str(item["amendment_id"]))
            or item["amendment_id"] in seen_amendment_ids
            or not re.fullmatch(r"[0-9a-f]{64}", str(item["before_digest"]))
            or not re.fullmatch(r"[0-9a-f]{64}", str(item["after_digest"]))
            or not isinstance(item["reason"], str)
            or not item["reason"].strip()
        ):
            raise PipelineError("Coverage amendment identity/hash chain is invalid")
        seen_amendment_ids.add(item["amendment_id"])
        if previous_prefix_after is not None and item["before_digest"] != previous_prefix_after:
            raise PipelineError("Coverage amendment append-only hash chain is discontinuous")
        affected = set(
            require_string_list(
                item["affected_acceptance_ids"],
                "Coverage amendment affected_acceptance_ids",
                allow_empty=False,
            )
        )
        if len(affected) != len(item["affected_acceptance_ids"]):
            raise PipelineError("Coverage amendment affected acceptance IDs must be distinct")
        if not affected.issubset(planned_acceptance_ids(state)):
            raise PipelineError("Coverage amendment names acceptance IDs outside the approved plan")
        is_appended = amendment_index >= len(planned_amendments)
        validate_coverage_amendment_authority(
            state, findings, item["authority_id"], affected, appended=is_appended
        )
        previous_prefix_after = item["after_digest"]

    if planned_amendments and planned_amendments[-1]["after_digest"] != before:
        raise PipelineError("Planned coverage amendment prefix does not end at its body digest")

    previous = before
    affected_union: set[str] = set()
    for item in appended:
        if item["before_digest"] != previous:
            raise PipelineError("Coverage amendment authority/hash chain is invalid")
        affected = set(
            require_string_list(
                item["affected_acceptance_ids"],
                "Coverage amendment affected_acceptance_ids",
                allow_empty=False,
            )
        )
        affected_union.update(affected)
        previous = item["after_digest"]
    if previous != after:
        raise PipelineError("Coverage amendment chain does not end at the finalized plan body")
    planned_projection = coverage_semantic_projection(planned)
    finalized_projection = coverage_semantic_projection(finalized)
    semantically_changed = {
        acceptance_id
        for acceptance_id in set(planned_projection).union(finalized_projection)
        if planned_projection.get(acceptance_id) != finalized_projection.get(acceptance_id)
    }
    if affected_union != semantically_changed:
        raise PipelineError(
            "Coverage amendment affected_acceptance_ids must exactly equal the controller-derived "
            "planned-to-final semantic AC change set"
        )
    return after


def validate_coverage_manifest(
    root: Path,
    state: dict[str, Any],
    manifest: dict[str, Any],
    *,
    scope_id: str | None = None,
    require_finalized: bool = False,
    expected_product_revision: str | None = None,
    expected_support_revision: str | None = None,
    expected_evidence_revision: str | None = None,
    expected_revision: str | None = None,
) -> dict[str, Any]:
    exact_fields = {
        "schema",
        "feature",
        "slice_id",
        "mode",
        "authority",
        "revisions",
        "ac_mappings",
        "expected_identities",
        "actual_identities",
        "mandatory_expected_identity_ids",
        "mandatory_actual_identity_ids",
        "automated_execution",
        "manual_execution",
        "amendments",
        "gaps",
        "summary",
    }
    if set(manifest) != exact_fields or manifest.get("schema") != 2:
        raise PipelineError("Coverage manifest must use the exact schema 2 shape")
    if manifest.get("feature") != state["feature"]:
        raise PipelineError("Coverage manifest feature mismatch")
    if manifest.get("mode") not in {"planned", "finalized", "qa_updated"}:
        raise PipelineError("Coverage manifest mode is invalid")
    if require_finalized and manifest.get("mode") not in {"finalized", "qa_updated"}:
        raise PipelineError("A finalized schema-2 coverage manifest is required")
    if scope_id and manifest.get("slice_id") != scope_id:
        raise PipelineError("Coverage manifest scope identity mismatch")
    authority = manifest.get("authority")
    if not isinstance(authority, dict) or set(authority) != {
        "plan_path",
        "plan_sha256",
        "prd_path",
        "prd_sha256",
        "spec_path",
        "spec_sha256",
    }:
        raise PipelineError("Coverage authority must use exact plan/PRD/spec path and SHA fields")
    expected_authority = {
        "plan_path": Path(state["development_plan_path"]).resolve().relative_to(root).as_posix(),
        "plan_sha256": state["development_plan_sha256"],
        "prd_path": Path(state["requirements_path"]).resolve().relative_to(root).as_posix(),
        "prd_sha256": state["requirements_sha256"],
        "spec_path": Path(state["spec_path"]).resolve().relative_to(root).as_posix(),
        "spec_sha256": state["spec_sha256"],
    }
    if authority != expected_authority:
        raise PipelineError("Coverage manifest authority is stale or points elsewhere")
    revisions = manifest.get("revisions")
    if not isinstance(revisions, dict) or set(revisions) != {
        "revision",
        "product_revision",
        "support_revision",
        "evidence_revision",
    }:
        raise PipelineError("Coverage revisions must use all four exact identities")
    expected = {
        "revision": expected_revision or state["revision"],
        "product_revision": expected_product_revision or state["product_revision"],
        "support_revision": expected_support_revision or state["support_revision"],
        "evidence_revision": expected_evidence_revision or state["evidence_revision"],
    }
    if revisions != expected:
        raise PipelineError("Coverage manifest revision identities do not match current state")
    assigned_acceptance = (
        planned_acceptance_ids(state)
        if manifest["slice_id"] == "feature"
        else set(
            (state.get("slices", {}).get(manifest["slice_id"], {}).get("scope_contract") or {}).get(
                "acceptance_ids", []
            )
        )
    )
    mappings = manifest.get("ac_mappings")
    if not isinstance(mappings, list):
        raise PipelineError("Coverage ac_mappings must be a list")
    mapping_ids = [item.get("acceptance_id") for item in mappings if isinstance(item, dict)]
    if len(mapping_ids) != len(mappings) or len(set(mapping_ids)) != len(mapping_ids):
        raise PipelineError("Coverage acceptance mappings must be distinct")
    if set(mapping_ids) != assigned_acceptance:
        raise PipelineError("Coverage acceptance mappings must equal the approved scope set")
    ledger_entries, _ = read_decision_ledger(root / state["decision_ledger"]["path"])
    decisions = {item["decision_id"]: item for item in ledger_entries}
    mapping_gaps: list[str] = []
    for item in mappings:
        if set(item) != {"acceptance_id", "status", "identity_ids", "authority_id"}:
            raise PipelineError("Every acceptance mapping must use exact schema-2 fields")
        ids = require_string_list(item["identity_ids"], "Coverage mapping identity_ids")
        if item["status"] not in {"mapped", "gap", "not_applicable"}:
            raise PipelineError("Coverage acceptance mapping status is invalid")
        if item["status"] == "mapped" and not ids:
            raise PipelineError("A mapped acceptance criterion requires an identity")
        if item["status"] in {"mapped", "gap"} and item["authority_id"] is not None:
            raise PipelineError("mapped/gap coverage must use authority_id=null")
        if item["status"] == "not_applicable":
            if ids:
                raise PipelineError("not_applicable coverage must not register identity_ids")
            if item["authority_id"] not in state["decision_ledger"]["active_decision_ids"]:
                raise PipelineError("not_applicable coverage requires an active accepted decision")
            if item["acceptance_id"] not in decisions[item["authority_id"]]["scope_ids"]:
                raise PipelineError(
                    "not_applicable decision authority must explicitly scope the concrete acceptance ID"
                )
        if item["status"] == "gap":
            mapping_gaps.append(item["acceptance_id"])
    identities: dict[str, dict[str, Any]] = {}
    expected_identities: dict[str, dict[str, Any]] = {}
    identity_sets: dict[str, list[str]] = {}
    for group in ("expected_identities", "actual_identities"):
        values = manifest.get(group)
        if not isinstance(values, list):
            raise PipelineError(f"Coverage {group} must be a list")
        ids: list[str] = []
        for index, identity in enumerate(values):
            validate_identity_coordinates(identity, f"Coverage {group}[{index}]")
            identity_id = identity["identity_id"]
            if identity_id in ids:
                raise PipelineError(f"Coverage {group} contains duplicate identity {identity_id}")
            ids.append(identity_id)
            if group == "actual_identities":
                identities[identity_id] = identity
            else:
                expected_identities[identity_id] = identity
            if manifest["slice_id"] == "feature":
                if identity["slice_id"] not in state["ordered_slices"]:
                    raise PipelineError("Feature coverage identity names an unknown owning slice")
                owning_slice = state["slices"][identity["slice_id"]]
            else:
                if identity["slice_id"] != manifest["slice_id"]:
                    raise PipelineError("Coverage identity slice_id must equal its manifest scope")
                owning_slice = state["slices"].get(identity["slice_id"])
            if not owning_slice:
                raise PipelineError("Coverage identity names an unknown slice")
            if not set(identity["requirement_ids"]).issubset(
                set(owning_slice["requirement_ids"])
            ) or not set(identity["acceptance_ids"]).issubset(
                set(owning_slice["scope_contract"]["acceptance_ids"])
            ):
                raise PipelineError("Coverage identity coordinates map outside its approved slice")
        identity_sets[group] = ids
    expected_ids = set(identity_sets["expected_identities"])
    actual_ids = set(identity_sets["actual_identities"])
    for item in mappings:
        if not set(item["identity_ids"]).issubset(expected_ids):
            raise PipelineError("Acceptance mapping cites an unregistered expected identity")
    mandatory_expected = require_string_list(
        manifest.get("mandatory_expected_identity_ids"), "mandatory expected identities"
    )
    mandatory_actual = require_string_list(
        manifest.get("mandatory_actual_identity_ids"), "mandatory actual identities"
    )
    if len(set(mandatory_expected)) != len(mandatory_expected) or len(set(mandatory_actual)) != len(
        mandatory_actual
    ):
        raise PipelineError("Coverage mandatory identity sets reject duplicates")
    explicit_expected = {
        item["identity_id"] for item in manifest["expected_identities"] if item["mandatory"]
    }
    explicit_actual = {
        item["identity_id"] for item in manifest["actual_identities"] if item["mandatory"]
    }
    mandatory_registration_ok = (
        set(mandatory_expected) == explicit_expected
        and set(mandatory_actual) == explicit_actual
        and set(mandatory_expected) == set(mandatory_actual)
    )
    registration_ok = expected_ids == actual_ids
    if registration_ok and any(
        expected_identities[identity_id] != identities[identity_id]
        for identity_id in expected_ids
    ):
        raise PipelineError("Expected and actual coverage identity bodies must match exactly")
    mapping_by_acceptance = {item["acceptance_id"]: item for item in mappings}
    for acceptance_id, mapping in mapping_by_acceptance.items():
        for identity_id in mapping["identity_ids"]:
            if acceptance_id not in expected_identities[identity_id]["acceptance_ids"]:
                raise PipelineError("Coverage AC mapping is not reflected by its expected identity")
    for identity_id, identity in expected_identities.items():
        for acceptance_id in identity["acceptance_ids"]:
            if identity_id not in mapping_by_acceptance[acceptance_id]["identity_ids"]:
                raise PipelineError("Expected coverage identity is missing its reverse AC mapping")
    automated_rows = manifest.get("automated_execution")
    manual_rows = manifest.get("manual_execution")
    if not isinstance(automated_rows, list) or not isinstance(manual_rows, list):
        raise PipelineError("Coverage execution dimensions must be lists")
    auto_by_id: dict[str, dict[str, Any]] = {}
    deferred_automated: list[str] = []
    product_failed_automated: list[str] = []
    for row in automated_rows:
        legacy_fields = {
            "identity_id",
            "executed",
            "passed",
            "command",
            "evidence_path",
            "evidence_sha256",
        }
        deferred_fields = legacy_fields | {"outcome", "authority"}
        if not isinstance(row, dict) or frozenset(row) not in {
            frozenset(legacy_fields),
            frozenset(deferred_fields),
        }:
            raise PipelineError("Automated execution row has invalid schema")
        identity_id = row["identity_id"]
        if identity_id in auto_by_id or identities.get(identity_id, {}).get("kind") != "automated":
            raise PipelineError("Automated execution must name each actual automated identity once")
        if not isinstance(row["executed"], bool) or row["passed"] not in {True, False, None}:
            raise PipelineError("Automated executed/passed dimensions are invalid")
        if row["passed"] is True and row["executed"] is not True:
            raise PipelineError("Automated passed=true requires executed=true")
        if row["executed"] and (
            not isinstance(row["command"], str)
            or not row["command"].strip()
            or not row["evidence_path"]
            or not re.fullmatch(r"[0-9a-f]{64}", str(row["evidence_sha256"]))
        ):
            raise PipelineError(
                "Executed automated identity requires a non-empty command and exact evidence path/SHA"
            )
        if row["evidence_path"]:
            evidence_path = resolve_project_file(root, row["evidence_path"], "Automated evidence")
            if file_sha256(evidence_path) != row["evidence_sha256"]:
                raise PipelineError("Automated execution evidence SHA mismatch")
        outcome = row.get("outcome")
        if outcome is not None:
            if outcome not in {"pass", "product_failed", "infra_unavailable", "manual_required"}:
                raise PipelineError("Automated execution outcome is invalid")
            if outcome == "pass" and not (row["executed"] is True and row["passed"] is True):
                raise PipelineError("Automated outcome pass requires executed=true and passed=true")
            if outcome == "product_failed":
                if not (row["executed"] is True and row["passed"] is False):
                    raise PipelineError(
                        "Automated product_failed requires executed=true and passed=false"
                    )
                if row["authority"] is not None:
                    raise PipelineError("Automated product_failed cannot use deferral authority")
                product_failed_automated.append(identity_id)
            elif outcome in {"infra_unavailable", "manual_required"}:
                authority = row["authority"]
                if row["executed"] or row["passed"] is not None or row["command"] or row["evidence_path"] or row["evidence_sha256"]:
                    raise PipelineError(
                        "Deferred automated identity must remain visibly unexecuted without evidence"
                    )
                if (
                    not isinstance(authority, dict)
                    or set(authority) != {"kind", "authority_id", "reference"}
                    or authority.get("kind") not in {"user", "manual"}
                    or not all(isinstance(authority.get(key), str) and authority[key].strip() for key in ("authority_id", "reference"))
                ):
                    raise PipelineError(
                        "Deferred automated identity requires exact user/manual authority"
                    )
                if authority["kind"] == "user" and authority["authority_id"] not in {
                    item["authority_id"] for item in state.get("user_authorities", [])
                }:
                    raise PipelineError("Deferred automated identity cites unknown user authority")
                if authority["kind"] == "manual":
                    manual_identity = identities.get(authority["authority_id"])
                    if (
                        not manual_identity
                        or manual_identity.get("kind") != "manual"
                        or authority["reference"]
                        != canonical_json_sha256(manual_identity)
                    ):
                        raise PipelineError(
                            "Deferred automated identity manual authority must bind an exact "
                            "registered manual identity body"
                        )
                deferred_automated.append(identity_id)
            elif row["authority"] is not None:
                raise PipelineError("Automated pass cannot use deferral authority")
        auto_by_id[identity_id] = row
    manual_by_id: dict[str, dict[str, Any]] = {}
    for row in manual_rows:
        if not isinstance(row, dict) or set(row) != {
            "identity_id",
            "executed",
            "passed",
            "deferred",
            "blocked_by_finding",
            "qa_evidence",
            "gate",
            "minimum_resume_action",
        }:
            raise PipelineError("Manual execution row has invalid schema")
        identity_id = row["identity_id"]
        if identity_id in manual_by_id or identities.get(identity_id, {}).get("kind") != "manual":
            raise PipelineError("Manual execution must name an actual manual identity")
        if not isinstance(row["executed"], bool) or row["passed"] not in {True, False, None} or not isinstance(
            row["deferred"], bool
        ):
            raise PipelineError("Manual executed/passed/deferred dimensions are invalid")
        if row["passed"] is True and not row["executed"]:
            raise PipelineError("Manual passed=true requires executed=true")
        if row["deferred"]:
            if row["executed"] or row["passed"] is not None or row["gate"] not in QA_GATE_STATUSES or not row[
                "minimum_resume_action"
            ]:
                raise PipelineError("Deferred manual identity requires a gate and resume action")
        if row["blocked_by_finding"] and row["deferred"]:
            raise PipelineError("blocked_by_finding is not a deferred user/environment/test gate")
        if row["executed"]:
            evidence = row["qa_evidence"]
            if not isinstance(evidence, dict) or set(evidence) != {"path", "sha256"}:
                raise PipelineError(
                    "Executed manual coverage identity requires immutable QA evidence path/SHA"
                )
            evidence_path = resolve_project_file(root, evidence["path"], "Manual QA evidence")
            try:
                evidence_path.relative_to(Path(state["tests_path"]).resolve())
            except ValueError as exc:
                raise PipelineError(
                    "Manual QA evidence must stay under feature test artifacts"
                ) from exc
            if (
                not re.fullmatch(r"[0-9a-f]{64}", str(evidence["sha256"]))
                or file_sha256(evidence_path) != evidence["sha256"]
            ):
                raise PipelineError("Manual QA evidence SHA does not match immutable bytes")
        elif row["qa_evidence"] is not None:
            raise PipelineError("Unexecuted manual coverage identity cannot claim QA evidence")
        manual_by_id[identity_id] = row
    mandatory_auto = {
        identity_id
        for identity_id in mandatory_actual
        if identities.get(identity_id, {}).get("kind") == "automated"
    }
    automated_ok = all(
        (
            auto_by_id.get(identity_id, {}).get("executed") is True
            and auto_by_id.get(identity_id, {}).get("passed") is True
        )
        or auto_by_id.get(identity_id, {}).get("outcome")
        in {"infra_unavailable", "manual_required"}
        for identity_id in mandatory_auto
    ) and not product_failed_automated
    mandatory_manual = {
        identity_id
        for identity_id in mandatory_actual
        if identities.get(identity_id, {}).get("kind") == "manual"
    }
    manual_ok = all(
        manual_by_id.get(identity_id, {}).get("executed") is True
        and manual_by_id.get(identity_id, {}).get("passed") is True
        and manual_by_id.get(identity_id, {}).get("deferred") is False
        and not manual_by_id.get(identity_id, {}).get("blocked_by_finding")
        for identity_id in mandatory_manual
    )
    if manifest["mode"] == "planned":
        automated_ok = False
        manual_ok = False
    declared_gaps = require_string_list(manifest.get("gaps"), "Coverage gaps")
    all_mapped = not mapping_gaps and all(item["status"] != "gap" for item in mappings)
    implementation_eligible = (
        all_mapped
        and registration_ok
        and mandatory_registration_ok
        and not declared_gaps
        and automated_ok
    )
    feature_eligible = implementation_eligible and manual_ok
    derived_summary = {
        "ac_mapped": all_mapped,
        "identities_registered": "complete" if registration_ok else "mismatch",
        "expected_count": len(expected_ids),
        "actual_count": len(actual_ids),
        "mandatory_expected_count": len(mandatory_expected),
        "mandatory_actual_count": len(mandatory_actual),
        "automated": (
            "deferred" if deferred_automated and automated_ok
            else "passed" if automated_ok
            else "pending"
        ),
        "manual": "passed" if manual_ok else (
            "deferred" if any(row["deferred"] for row in manual_rows) else "pending"
        ),
        "implementation_eligible": implementation_eligible,
        "feature_verification_eligible": feature_eligible,
    }
    if deferred_automated:
        derived_summary["untested_identity_ids"] = sorted(deferred_automated)
    if manifest.get("summary") != derived_summary:
        raise PipelineError("Coverage summary does not match controller-derived dimensions")
    return {
        "summary": derived_summary,
        "registration_ok": registration_ok,
        "mandatory_registration_ok": mandatory_registration_ok,
        "automated_ok": automated_ok,
        "manual_ok": manual_ok,
        "gaps": sorted(set(declared_gaps + mapping_gaps)),
        "expected_ids": sorted(expected_ids),
        "actual_ids": sorted(actual_ids),
        "mandatory_expected_ids": sorted(mandatory_expected),
        "mandatory_actual_ids": sorted(mandatory_actual),
        "manual_by_id": manual_by_id,
        "actual_identities": identities,
        "untested_identity_ids": sorted(deferred_automated),
        "product_failed_identity_ids": sorted(product_failed_automated),
    }


def path_matches_scope(path: str, rule: str) -> bool:
    if rule.endswith("/**"):
        prefix = rule[:-3].rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    return path == rule


def path_matches_touchpoint(path: str, touchpoint_path: str) -> bool:
    prefix = touchpoint_path.rstrip("/")
    return path == prefix or path.startswith(prefix + "/")


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


def exact_scope_precheck(
    state: dict[str, Any], slice_item: dict[str, Any], owner_id: str
) -> dict[str, Any] | None:
    check = slice_item.get("scope_pre_edit_check")
    if not isinstance(check, dict):
        return None
    if (
        check.get("status") != "passed"
        or check.get("slice_id") != slice_item.get("id")
        or check.get("owner_id") != owner_id
        or check.get("base_revision") != state.get("revision")
        or check.get("development_plan_sha256")
        != state.get("development_plan_sha256")
        or check.get("scope_contract") != slice_item.get("scope_contract")
        or not isinstance(check.get("checkout_snapshot_sha256"), str)
    ):
        return None
    return check


def engineer_scope_route(state: dict[str, Any]) -> dict[str, Any] | None:
    """Return a mandatory scope authorization route before Engineer execution."""
    if state.get("phase") not in {"slice_engineering", "engineering"}:
        return None
    try:
        slice_item = scope_slice_for_pass(state, None)
    except PipelineError:
        return None
    lease = state.get("active_write_lease")
    owner_id = (
        state.get("engineering_owner_id")
        or slice_item.get("owner_id")
        or state.get("owner_by_slice", {}).get(slice_item["id"])
        or (
            lease.get("worker_id")
            if isinstance(lease, dict) and lease.get("role") == "engineer"
            else None
        )
        or state.get("integration_owner")
    )
    if not owner_id:
        return None
    check = exact_scope_precheck(state, slice_item, owner_id)
    if isinstance(lease, dict) and lease.get("role") == "engineer":
        authorization = lease.get("scope_authorization")
        if not isinstance(authorization, dict) or not authorization.get("receipt_sha256"):
            return {
                "action": "recover_legacy_engineer_scope_authorization",
                "owner": "technical_director",
                "user_input_required": False,
                "lease_id": lease.get("lease_id"),
                "engineering_owner_id": owner_id,
                "active_slice": slice_item.get("id"),
                "reason": "active_legacy_lease_missing_exact_base_scope_authorization",
            }
        return None
    if check is None:
        return {
            "action": "run_slice_scope_check",
            "owner": "technical_director",
            "user_input_required": False,
            "engineering_owner_id": owner_id,
            "active_slice": slice_item.get("id"),
            "base_revision": state.get("revision"),
            "reason": "missing_or_stale_exact_base_scope_precheck",
        }
    return None


def scope_violations(
    slice_item: dict[str, Any],
    changes: list[dict[str, Any]],
    diff_files: list[dict[str, Any]],
    *,
    material_change_approved: bool = False,
    active_decision_ids: set[str] | None = None,
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
    touchpoints = list(scope["shared_touchpoints"])
    permissions = list(scope.get("planned_material_permissions") or [])
    active_decisions = active_decision_ids or set()
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
        owned = any(path_matches_scope(path, rule) for rule in scope["editable_paths"])
        matching_touchpoints = [
            item
            for item in touchpoints
            if path_matches_touchpoint(path, item["path"])
        ]
        touchpoint = matching_touchpoints[0] if len(matching_touchpoints) == 1 else None
        for change_type in material_flags:
            exact_permission = next(
                (
                    permission
                    for permission in permissions
                    if permission["change_type"] == change_type
                    and permission["decision_authority"] in active_decisions
                    and (
                        (
                            permission["target_kind"] == "editable_path"
                            and permission["target"] == path
                        )
                        or (
                            permission["target_kind"] == "shared_touchpoint"
                            and touchpoint is not None
                            and permission["target"] == touchpoint["id"]
                        )
                    )
                ),
                None,
            )
            if exact_permission is None and not material_change_approved:
                violations.append(f"unapproved {change_type} in {path}")
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
    if phase == "preflight_migration_hold":
        hold = state.get("preflight_migration_hold") or {}
        return {
            "action": "reinitialize_preflight",
            "owner": "technical_director",
            "user_input_required": False,
            "resume_phase": hold.get("resume_phase"),
            "reason": hold.get("reason", "current versioned preflight proof is absent"),
        }
    if source_drift(state):
        if phase == "scope_expansion_hold":
            hold = state.get("scope_guard", {}).get("hold") or {}
            return {
                "action": "approve_updated_plan_and_rebaseline_scope",
                "owner": "user",
                "user_input_required": True,
                "hold": hold,
                "hold_sha256": scope_hold_sha256(hold),
                "authority_statement_template": (
                    "Approve scope rebaseline "
                    f"hold_sha256={scope_hold_sha256(hold)} "
                    "plan_sha256=<approved-plan-sha256>"
                ),
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
        phase in {"slice_engineering", "engineering"}
        and bool(
            state.get("engineering_owner_id")
            or state.get("integration_owner")
            or state.get("owner_by_slice", {}).get(
                state.get("active_slice") or state.get("slice_id")
            )
            or (
                state.get("active_write_lease") or {}
            ).get("worker_id")
        )
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
    scope_route = engineer_scope_route(state)
    if scope_route is not None:
        return scope_route
    if phase == "preflight":
        blocked = blocked_preflight_capabilities(state)
        if blocked:
            priority = qa_gate_priority(set(blocked.values()))
            capability_id = sorted(
                name for name, status in blocked.items() if status == priority
            )[0]
            contract = state.get("preflight", {}).get(
                "minimum_resume_actions", {}
            ).get(capability_id)
            if not isinstance(contract, dict):
                return {
                    "action": "record_missing_preflight_resume_contract",
                    "owner": "technical_director",
                    "user_input_required": False,
                    "capability_id": capability_id,
                    "capability_summary": blocked_capability_summary(blocked),
                }
            return {
                "action": contract["action"],
                "owner": contract["owner"],
                "user_input_required": contract["user_input_required"],
                "capability_id": capability_id,
                "capability_summary": blocked_capability_summary(blocked),
            }
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
        hold = state.get("scope_guard", {}).get("hold") or {}
        return {
            "action": "approve_updated_plan_and_rebaseline_scope",
            "owner": "user",
            "user_input_required": True,
            "hold": hold,
            "hold_sha256": scope_hold_sha256(hold),
            "authority_statement_template": (
                "Approve scope rebaseline "
                f"hold_sha256={scope_hold_sha256(hold)} "
                "plan_sha256=<approved-plan-sha256>"
            ),
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
        research_contract = (
            state.get("plan_contracts", {})
            .get("slices", {})
            .get(state.get("active_slice"), {})
            .get("research", {})
        )
        return {
            "action": "complete_or_waive_slice_research",
            "owner": "technical_director",
            "user_input_required": False,
            "active_slice": state.get("active_slice"),
            "base_revision": (active or {}).get("base_revision"),
            "required_bundle_count": len(research_contract.get("briefs", [])),
        }
    if phase == "slice_coverage_planning":
        return {
            "action": "record_pre_engineering_coverage",
            "owner": "technical_director",
            "user_input_required": False,
            "active_slice": state.get("active_slice"),
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
    if phase == "slice_coverage_finalization":
        return {
            "action": "run_slice_coverage_finalization",
            "owner": "technical_director",
            "user_input_required": False,
            "active_slice": state.get("active_slice"),
        }
    if phase == "implementation_complete":
        return {
            "action": "finish_normative_documentation",
            "owner": "technical_director",
            "user_input_required": False,
        }
    if phase == "normative_documentation":
        return {
            "action": "complete_normative_documentation",
            "owner": "technical_director",
            "user_input_required": False,
        }
    if phase == "coverage_finalization":
        return {
            "action": "run_feature_coverage_finalization",
            "owner": "technical_director",
            "user_input_required": False,
        }
    if phase == "decision_recording":
        return {
            "action": "complete_accepted_decision_recording",
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
                else "complete_read_only_convergence_audits"
            ),
            "owner": "technical_director",
            "user_input_required": False,
            "required": convergence.get("required"),
            "completed": len(convergence.get("runs", [])),
        }
    if phase in {"convergence_hold", "recovery_hold"}:
        iteration = state.get("iteration_control") or {}
        return {
            "action": "authorize_iteration",
            "owner": "technical_director",
            "user_input_required": False,
            "command": "authorize-iteration",
            "hold_phase": phase,
            "resume_phase": (
                iteration.get("resume_phase")
                if phase == "convergence_hold"
                else "evidence_recovery"
            ),
            "reason": iteration.get("reason"),
            "required_argument": "reason",
        }
    if phase == "review":
        action = (
            "finalize_review"
            if state.get("review", {}).get("status") == "awaiting_decision"
            else "complete_final_review"
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
            return blocked_capability_next_action(
                blocked_capabilities,
                state.get("preflight", {}).get("minimum_resume_actions", {}),
                probe_id="preflight",
                missing_action="record_missing_preflight_resume_contract",
            )
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
            if blocked:
                return blocked_capability_next_action(
                    blocked,
                    qa_capability.get("minimum_resume_actions", {}),
                    probe_id=qa_capability.get("probe_id"),
                    missing_action="record_missing_qa_resume_contract",
                )
            return {
                "action": "run_exact_revision_qa_capability_probe",
                "owner": "technical_director",
                "user_input_required": False,
                "capability_id": None,
                "probe_id": qa_capability.get("probe_id"),
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
    if phase == "derived_documentation":
        return {
            "action": "finish_derived_post_qa_documentation",
            "owner": "technical_director",
            "user_input_required": False,
        }
    if phase == "documentation_review":
        return {
            "action": "run_documentation_closure_review",
            "owner": "technical_director",
            "user_input_required": False,
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
    if args.max_consecutive_product_changes < 1:
        raise PipelineError("max-consecutive-product-changes must be positive")
    if args.max_workers < 1:
        raise PipelineError("max-workers must be positive")
    if args.max_full_review_waves < 1:
        raise PipelineError("max-full-review-waves must be positive")

    requirements = resolve_project_file(root, args.requirements, "Approved product requirements")
    spec = resolve_project_file(root, args.spec, "Approved technical specification")
    requirements_meta, _, prd_acceptance_inventory = require_feature_documents(
        root, feature, requirements, spec
    )
    plan = require_development_plan(
        root,
        feature,
        requirements,
        spec,
        args.plan,
        args.plan_sha256,
        prd_acceptance_inventory,
    )
    supplied_ledger = args.decision_ledger or plan["decision_ledger_path"]
    supplied_ledger = scope_path(supplied_ledger, "decision ledger")
    if supplied_ledger != plan["decision_ledger_path"]:
        raise PipelineError(
            "--decision-ledger must equal the exact path approved in development-plan.md"
        )
    ledger_path = (root / supplied_ledger).resolve()
    try:
        ledger_path.relative_to(root)
    except ValueError as exc:
        raise PipelineError("Decision ledger must stay inside the project root") from exc
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    if not ledger_path.exists():
        temporary_ledger = ledger_path.with_suffix(ledger_path.suffix + ".tmp")
        temporary_ledger.write_bytes(b"")
        os.replace(temporary_ledger, ledger_path)
    ledger_state = decision_ledger_state(ledger_path, supplied_ledger)
    if not args.base_revision.strip():
        raise PipelineError("--base-revision must identify the exact implementation base")
    tests_root = ensure_test_artifact_layout(root, feature)
    generated_output_policy = load_generated_output_policy(root)

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
        "plan_contracts": plan["contracts"],
        "generated_output_policy": generated_output_policy,
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
        "revision_base_revision": args.base_revision,
        "revision_inventory": {
            "product": sorted(
                {
                    requirements.relative_to(root).as_posix(),
                    spec.relative_to(root).as_posix(),
                    Path(plan["path"]).resolve().relative_to(root).as_posix(),
                    supplied_ledger,
                }
            ),
            "support": [],
            "evidence": [],
        },
        "revision": None,
        "product_revision": None,
        "support_revision": None,
        "evidence_revision": None,
        "implementation_state": {
            "status": "pending",
            "revision": None,
            "coverage_manifest": None,
        },
        "feature_verification_state": {
            "status": "pending",
            "product_revision": None,
            "support_revision": None,
            "evidence_revision": None,
        },
        "active_write_lease": None,
        "write_lease_history": [],
        "lease_snapshots": {},
        "legacy_scope_recoveries": [],
        "decision_ledger": ledger_state,
        "user_authorities": [],
        "coverage": {
            item["id"]: empty_coverage_scope() for item in plan["slices"]
        },
        "documentation": empty_documentation_state(),
        "context_capsules": [],
        "handoffs": [],
        "decision_recording": None,
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
        "required_convergence_audits": DEFAULT_REQUIRED_CONVERGENCE_AUDITS,
        "max_convergence_waves": DEFAULT_MAX_CONVERGENCE_WAVES,
        "convergence": empty_convergence_state(DEFAULT_REQUIRED_CONVERGENCE_AUDITS),
        "required_reviews": 1,
        "review": empty_review_state(1),
        "review_runs": [],
        "component_review_credits": [],
        "product_revalidation": None,
        "ready_targeted_closure_clean_recoveries": [],
        "closure_review": None,
        "qa": empty_qa_state(),
        "qa_capability": empty_qa_capability_state(),
        "qa_runs": [],
        "gates": [],
        "preflight": empty_preflight_state(),
        "preflight_migration_hold": None,
        "preflight_migration_history": [],
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
    initial_revisions = compute_inventory_revisions(root, state)
    for key in ("revision", "product_revision", "support_revision", "evidence_revision"):
        state[key] = initial_revisions[key]
    findings = {"schema_version": SCHEMA_VERSION, "items": []}
    set_active_slice(
        state,
        plan["slices"][0]["id"],
        base_revision=state["revision"],
        base_product_revision=state["product_revision"],
        base_support_revision=state["support_revision"],
        base_evidence_revision=state["evidence_revision"],
    )
    save_runtime(state_path, findings_path, state, findings)
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
        if not re.fullmatch(CAPABILITY_ID_PATTERN, name):
            raise PipelineError(f"Invalid capability name: {name!r}")
        if status not in PREFLIGHT_CAPABILITY_STATUSES:
            raise PipelineError(f"Invalid capability status for {name}: {status!r}")
        if name in result:
            raise PipelineError(f"Duplicate capability: {name}")
        result[name] = status
    return result


def required_preflight_capabilities(state: dict[str, Any]) -> set[str]:
    """Return the approved capability contract plus the truly universal minimum."""
    required = set(UNIVERSAL_CAPABILITY_NAMES)
    contracts = state.get("plan_contracts") or {}
    coverage_values = [
        (contracts.get("coverage_strategy") or {}).get("capability_prerequisites", "")
    ]
    coverage_values.extend(
        (item.get("coverage") or {}).get("capability_prerequisites", "")
        for item in (contracts.get("slices") or {}).values()
    )
    for value in coverage_values:
        try:
            required.update(
                parse_capability_ids(value, label="approved capability_prerequisites")
            )
        except ValueError as exc:
            raise PipelineError(str(exc)) from exc
    return required


def required_qa_capabilities(root: Path, state: dict[str, Any]) -> set[str]:
    """Narrow QA probing to capabilities used by registered manual identities."""
    required = set(UNIVERSAL_CAPABILITY_NAMES)
    record = (state.get("coverage", {}).get("feature") or {}).get(
        "finalized_manifest"
    )
    if not record:
        raise PipelineError("QA capability probe requires finalized feature coverage")
    path = resolve_project_file(root, record.get("path", ""), "QA coverage manifest")
    if file_sha256(path) != record.get("sha256"):
        raise PipelineError("QA coverage manifest drifted before capability probing")
    manifest = read_json(path)
    for identity in manifest.get("actual_identities", []):
        if isinstance(identity, dict) and identity.get("kind") == "manual":
            try:
                required.update(
                    _capability_contract.require_capability_id(
                        item, label="QA identity capability prerequisite"
                    )
                    for item in identity.get("capability_prerequisites", [])
                )
            except ValueError as exc:
                raise PipelineError(str(exc)) from exc
    undeclared = required - required_preflight_capabilities(state)
    if undeclared:
        raise PipelineError(
            "QA identities require capabilities absent from the approved plan: "
            + ", ".join(sorted(undeclared))
        )
    return required


def required_capability_proof_digest(required_ids: list[str]) -> str:
    return canonical_json_sha256(
        {
            "proof_version": PREFLIGHT_PROOF_VERSION,
            "required_capability_ids": required_ids,
        }
    )


def resume_contract_is_valid(status: str, contract: Any) -> bool:
    if not isinstance(contract, dict) or set(contract) != {
        "owner",
        "user_input_required",
        "action",
    }:
        return False
    if not isinstance(contract.get("action"), str) or not contract["action"].strip():
        return False
    if not isinstance(contract.get("user_input_required"), bool):
        return False
    if status == "blocked_user":
        return contract["owner"] == "user" and contract["user_input_required"] is True
    if status in {"blocked_environment", "error_test"}:
        return (
            contract["owner"] == "technical_director"
            and contract["user_input_required"] is False
        )
    return False


def preflight_proof_error(state: dict[str, Any]) -> str | None:
    preflight = state.get("preflight")
    if not isinstance(preflight, dict):
        return "missing preflight state"
    required_ids = sorted(required_preflight_capabilities(state))
    if preflight.get("proof_version") != PREFLIGHT_PROOF_VERSION:
        return "missing or unsupported proof_version"
    if preflight.get("required_capability_ids") != required_ids:
        return "required capability IDs do not match the current approved plan"
    if preflight.get("required_capability_digest") != required_capability_proof_digest(
        required_ids
    ):
        return "required capability digest is invalid"
    capabilities = preflight.get("capabilities")
    if not isinstance(capabilities, dict) or set(capabilities) != set(required_ids):
        return "capability proof is incomplete or contains unexpected IDs"
    if any(status not in PREFLIGHT_CAPABILITY_STATUSES for status in capabilities.values()):
        return "capability proof contains an unsupported status"
    blocked = {
        name: status
        for name, status in capabilities.items()
        if status in QA_CAPABILITY_BLOCKING_STATUSES
    }
    resume_actions = preflight.get("minimum_resume_actions")
    if not isinstance(resume_actions, dict) or set(resume_actions) != set(blocked):
        return "minimum resume contracts do not exactly match blocked capabilities"
    if any(
        not resume_contract_is_valid(blocked[name], resume_actions[name])
        for name in blocked
    ):
        return "minimum resume contract authority is invalid"
    if preflight.get("resume_contract_complete") is not True:
        return "resume contract completeness proof is absent"
    resource_status = preflight.get("resource_budget_check")
    expected_status = (
        "complete"
        if resource_status == "pass" and not blocked
        else "capability_blocked"
        if blocked
        else "budget_failed"
        if resource_status == "fail"
        else None
    )
    if expected_status is None or preflight.get("status") != expected_status:
        return "preflight aggregate status is inconsistent with its exact proof"
    return None


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
    required_capabilities = required_preflight_capabilities(state)
    supplied_capabilities = set(capabilities)
    missing = sorted(required_capabilities - supplied_capabilities)
    unexpected = sorted(supplied_capabilities - required_capabilities)
    if missing or unexpected:
        details: list[str] = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if unexpected:
            details.append("unexpected=" + ",".join(unexpected))
        raise PipelineError(
            "Preflight capability proof must exactly cover the approved capability set: "
            + "; ".join(details)
        )
    blocked = sorted(
        name
        for name, status in capabilities.items()
        if status in QA_CAPABILITY_BLOCKING_STATUSES
    )
    resume_actions = parse_resume_actions(args.minimum_resume_action, capabilities)
    missing_actions = sorted(set(blocked) - set(resume_actions))
    extra_actions = sorted(set(resume_actions) - set(blocked))
    if missing_actions or extra_actions:
        raise PipelineError(
            "Preflight minimum resume actions must exactly match blocked capabilities: "
            + "; ".join(
                part
                for part in (
                    "missing=" + ",".join(missing_actions) if missing_actions else "",
                    "unexpected=" + ",".join(extra_actions) if extra_actions else "",
                )
                if part
            )
        )
    preflight["resource_budget_check"] = args.resource_budget_check
    preflight["capabilities"] = dict(sorted(capabilities.items()))
    preflight["minimum_resume_actions"] = resume_actions
    required_ids = sorted(required_capabilities)
    preflight["proof_version"] = PREFLIGHT_PROOF_VERSION
    preflight["required_capability_ids"] = required_ids
    preflight["required_capability_digest"] = required_capability_proof_digest(
        required_ids
    )
    preflight["resume_contract_complete"] = True
    preflight["status"] = (
        "complete"
        if args.resource_budget_check == "pass" and not blocked
        else "capability_blocked"
        if blocked
        else "budget_failed"
    )
    preflight["runs"].append(
        {
            "run_id": args.run_id,
            "resource_budget_check": args.resource_budget_check,
            "capabilities": capabilities,
            "proof_version": PREFLIGHT_PROOF_VERSION,
            "required_capability_ids": required_ids,
            "required_capability_digest": preflight["required_capability_digest"],
            "resume_contract_complete": True,
            "report": report,
            "report_sha256": file_sha256(Path(report)),
            "recorded_at": utc_now(),
        }
    )
    if entry_phase == "preflight":
        if preflight["status"] == "complete":
            state["phase"] = preflight.get("migration_resume_phase") or "slice_research"
            preflight["migration_resume_phase"] = None
        else:
            state["phase"] = "preflight"
    else:
        state["phase"] = "qa"
    save_runtime(state_path, findings_path, state, findings)
    return render_status(args, state, findings)


def cmd_reinitialize_preflight(args: argparse.Namespace) -> int:
    _, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    hold = state.get("preflight_migration_hold")
    if state.get("phase") != "preflight_migration_hold" or not isinstance(hold, dict):
        raise PipelineError("reinitialize-preflight requires an explicit preflight migration hold")
    if state.get("active_write_lease") is not None:
        raise PipelineError("Preflight migration cannot begin while a write lease is active")
    old = state.get("preflight") or {}
    state["preflight_migration_history"].append(
        {
            "resume_phase": hold.get("resume_phase"),
            "reason": args.reason,
            "detected_error": hold.get("reason"),
            "prior_proof_version": old.get("proof_version"),
            "prior_capability_count": len(old.get("capabilities") or {}),
            "reinitialized_at": utc_now(),
        }
    )
    fresh = empty_preflight_state()
    fresh["migration_resume_phase"] = hold.get("resume_phase") or "slice_research"
    state["preflight"] = fresh
    state["preflight_migration_hold"] = None
    state["phase"] = "preflight"
    save_runtime(state_path, findings_path, state, findings)
    return render_status(args, state, findings)


STATUS_SCHEMA_VERSION = 1
STATUS_ID_LIMIT = 20
STATUS_SECTIONS = (
    "capsules",
    "coverage",
    "decisions",
    "documentation",
    "findings",
    "gates",
    "handoffs",
    "leases",
    "plan",
    "preflight",
    "qa",
    "recovery",
    "reviews",
    "revisions",
    "scope",
    "workers",
)


def status_counts(
    state: dict[str, Any], findings: dict[str, Any]
) -> tuple[dict[str, int], dict[str, int]]:
    counts = {"critical": 0, "major": 0, "minor": 0}
    for item in findings["items"]:
        if item["status"] == "open":
            counts[item["severity"]] += 1
    counts["blocking"] = len(open_blocking(findings))
    counts["remediation_required"] = len(open_remediation_required(findings))
    gate_counts = {status: 0 for status in sorted(QA_GATE_STATUSES)}
    for gate in state.get("gates", []):
        if gate.get("status") == "open":
            gate_counts[gate["category"]] += 1
    return counts, gate_counts


def full_status_payload(
    state: dict[str, Any], findings: dict[str, Any]
) -> dict[str, Any]:
    counts, gate_counts = status_counts(state, findings)
    return {
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
        "implementation_state": state["implementation_state"],
        "feature_verification_state": state["feature_verification_state"],
        "active_write_lease": state["active_write_lease"],
        "write_lease_history": state["write_lease_history"],
        "decision_ledger": state["decision_ledger"],
        "user_authorities": state["user_authorities"],
        "coverage": state["coverage"],
        "documentation": state["documentation"],
        "plan_contracts": state["plan_contracts"],
        "context_capsules": state["context_capsules"],
        "handoffs": state["handoffs"],
        "phase": state["phase"],
        "last_engineer_outcome": state["last_engineer_outcome"],
        "machine_checks": state["machine_checks"],
        "engineer_clean": state["engineer_clean"],
        "engineering_owner_id": state["engineering_owner_id"],
        "preflight": state["preflight"],
        "convergence": state["convergence"],
        "review": state["review"],
        "product_revalidation": state["product_revalidation"],
        "ready_targeted_closure_clean_recoveries": state.get(
            "ready_targeted_closure_clean_recoveries", []
        ),
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


def bounded_ids(values: list[str]) -> dict[str, Any]:
    unique = sorted({value for value in values if value})
    return {
        "ids": unique[:STATUS_ID_LIMIT],
        "total": len(unique),
        "truncated": len(unique) > STATUS_ID_LIMIT,
    }


def blocked_capability_summary(blocked: dict[str, str]) -> dict[str, Any]:
    summary = bounded_ids(list(blocked))
    summary["by_status"] = {
        status: sum(1 for value in blocked.values() if value == status)
        for status in ("blocked_user", "blocked_environment", "error_test")
        if status in set(blocked.values())
    }
    return summary


def blocked_capability_next_action(
    blocked: dict[str, str],
    resume_actions: dict[str, Any],
    *,
    probe_id: str | None,
    missing_action: str,
) -> dict[str, Any]:
    priority = qa_gate_priority(set(blocked.values()))
    capability_id = (
        sorted(name for name, status in blocked.items() if status == priority)[0]
        if priority
        else None
    )
    resume_contract = resume_actions.get(capability_id)
    valid_contract = bool(
        capability_id
        and resume_contract_is_valid(blocked[capability_id], resume_contract)
    )
    return {
        "action": resume_contract["action"] if valid_contract else missing_action,
        "owner": resume_contract["owner"] if valid_contract else "technical_director",
        "user_input_required": (
            resume_contract["user_input_required"] if valid_contract else False
        ),
        "capability_id": capability_id,
        "probe_id": probe_id,
        "capability_summary": blocked_capability_summary(blocked),
    }


def coverage_revision_summary(state: dict[str, Any]) -> dict[str, Any]:
    coverage = state.get("coverage", {})
    scope_id = "feature" if coverage.get("feature") else state.get("active_slice")
    scope = coverage.get(scope_id, {}) if scope_id else {}
    record = scope.get("finalized_manifest") or scope.get("planned_manifest") or {}
    coverage_state = scope.get("state", {})
    return {
        "scope_id": scope_id,
        "revision": record.get("revision"),
        "status": coverage_state.get("status", "pending"),
        "manifest_path": record.get("path"),
        "manifest_sha256": record.get("sha256"),
    }


def compact_write_lease(lease: dict[str, Any] | None) -> dict[str, Any] | None:
    if not lease:
        return None
    return {
        key: lease.get(key)
        for key in ("lease_id", "role", "phase", "write_scope", "worker_id", "status")
        if key in lease
    }


def transition_changed_ids(args: argparse.Namespace) -> dict[str, Any]:
    changed: dict[str, Any] = {}
    for attribute in (
        "id",
        "run_id",
        "worker_id",
        "owner_id",
        "reviewer_id",
        "recorder_id",
        "lease_id",
        "authority_id",
        "probe_id",
        "scope_id",
        "slice_id",
    ):
        value = getattr(args, attribute, None)
        if value:
            changed[attribute] = value
    resolved = getattr(args, "resolved_finding", None)
    if resolved:
        changed["resolved_finding_ids"] = sorted(set(resolved))
    return changed


def compact_status_payload(
    state: dict[str, Any], findings: dict[str, Any], args: argparse.Namespace
) -> dict[str, Any]:
    finding_counts, gate_counts = status_counts(state, findings)
    open_findings = [
        item for item in findings.get("items", []) if item.get("status") == "open"
    ]
    open_gates = [gate for gate in state.get("gates", []) if gate.get("status") == "open"]
    active_batch = state.get("active_remediation_batch") or {}
    triage = state.get("finding_triage") or {}
    active_decisions = state.get("decision_ledger", {}).get("active_decision_ids", [])
    pending_identities = [
        str(value)
        for value in state.get("qa", {}).get("pending_identities", [])
    ]
    return {
        "status_schema": STATUS_SCHEMA_VERSION,
        "mode": "compact",
        "transition": getattr(args, "command", "status"),
        "feature": state.get("feature"),
        "phase": state.get("phase"),
        "revision": state.get("revision"),
        "product_revision": state.get("product_revision"),
        "support_revision": state.get("support_revision"),
        "evidence_revision": state.get("evidence_revision"),
        "coverage_revision": coverage_revision_summary(state),
        "active_slice": state.get("active_slice"),
        "active_write_lease": compact_write_lease(state.get("active_write_lease")),
        "active_remediation_batch": {
            key: active_batch.get(key)
            for key in ("batch_id", "route", "owner_id", "status")
            if key in active_batch
        } or None,
        "execution_stage": state.get("execution_stage"),
        "implementation_state": {
            key: state.get("implementation_state", {}).get(key)
            for key in ("status", "revision")
        },
        "feature_verification_state": {
            key: state.get("feature_verification_state", {}).get(key)
            for key in (
                "status",
                "product_revision",
                "support_revision",
                "evidence_revision",
            )
        },
        "documentation": {
            kind: (state.get("documentation", {}).get(kind) or {}).get("status")
            for kind in ("normative", "derived")
        },
        "qa": {
            key: state.get("qa", {}).get(key)
            for key in ("status", "revision", "run_id", "worker_id")
            if key in state.get("qa", {})
        },
        "iteration_control": {
            key: state.get("iteration_control", {}).get(key)
            for key in (
                "status",
                "consecutive_product_changes",
                "max_consecutive_product_changes",
                "reason",
            )
        },
        "last_engineer_outcome": state.get("last_engineer_outcome"),
        "changed_ids": transition_changed_ids(args),
        "active_ids": {
            "finding_triage_id": triage.get("finding_id"),
            "remediation_finding_ids": bounded_ids(
                [str(value) for value in active_batch.get("finding_ids", [])]
            ),
            "open_finding_ids": bounded_ids(
                [str(item.get("id")) for item in open_findings if item.get("id")]
            ),
            "open_gate_ids": bounded_ids(
                [str(gate.get("id")) for gate in open_gates if gate.get("id")]
            ),
            "decision_ids": bounded_ids([str(value) for value in active_decisions]),
            "pending_qa_identity_ids": bounded_ids(pending_identities),
        },
        "open_findings": finding_counts,
        "open_gates": gate_counts,
        "source_drift": source_drift(state),
        "next_action": next_action(state, findings),
    }


def status_section_payload(
    section: str, state: dict[str, Any], findings: dict[str, Any]
) -> dict[str, Any]:
    finding_counts, gate_counts = status_counts(state, findings)
    snapshot_status = {
        lease_id: {
            "snapshot_schema": snapshot.get("snapshot_schema"),
            "snapshot_format": snapshot.get("snapshot_format"),
            "checkout_snapshot_sha256": (
                checkout_snapshot_sha256(snapshot.get("checkout"))
                if isinstance(snapshot, dict) and isinstance(snapshot.get("checkout"), dict)
                else None
            ),
            "projected_file_count": (
                len(snapshot.get("checkout", {})) if isinstance(snapshot, dict) else 0
            ),
            "line_proof_file_count": (
                len(snapshot.get("line_proofs", {}))
                if isinstance(snapshot, dict)
                and isinstance(snapshot.get("line_proofs"), dict)
                else 0
            ),
            "migration_required": isinstance(snapshot, dict)
            and (
                "checkout_text" in snapshot
                or snapshot.get("snapshot_schema") != LEASE_SNAPSHOT_SCHEMA
            ),
        }
        for lease_id, snapshot in state.get("lease_snapshots", {}).items()
    }
    sections: dict[str, Any] = {
        "capsules": state.get("context_capsules", []),
        "coverage": state.get("coverage", {}),
        "decisions": {
            "decision_ledger": state.get("decision_ledger", {}),
            "user_authorities": state.get("user_authorities", []),
            "decision_recording": state.get("decision_recording"),
        },
        "documentation": {
            "documentation": state.get("documentation", {}),
            "plan_contracts": state.get("plan_contracts", {}),
        },
        "findings": {"counts": finding_counts, "items": findings.get("items", [])},
        "gates": {"counts": gate_counts, "items": state.get("gates", [])},
        "handoffs": {
            "handoffs": state.get("handoffs", []),
            "manifests": state.get("handoff_manifests", []),
        },
        "leases": {
            "active": state.get("active_write_lease"),
            "history": state.get("write_lease_history", []),
            "snapshots": snapshot_status,
            "last_snapshot_sanitization": (
                (state.get("lease_snapshot_sanitizations") or [None])[-1]
            ),
        },
        "plan": {
            "development_plan": {
                "path": state.get("development_plan_path"),
                "sha256": state.get("development_plan_sha256"),
                "mode": state.get("development_mode"),
            },
            "ordered_slices": state.get("ordered_slices", []),
            "slices": state.get("slices", {}),
        },
        "preflight": state.get("preflight", {}),
        "qa": {
            "qa": state.get("qa", {}),
            "capability": state.get("qa_capability", {}),
            "gates": state.get("gates", []),
        },
        "recovery": {
            "recovery": state.get("recovery"),
            "remediation_queue": state.get("remediation_queue", []),
            "active_remediation_batch": state.get("active_remediation_batch"),
        },
        "reviews": {
            "convergence": state.get("convergence", {}),
            "review": state.get("review", {}),
            "product_revalidation": state.get("product_revalidation"),
            "closure_review": state.get("closure_review"),
            "component_review_credits": state.get("component_review_credits", []),
        },
        "revisions": {
            "revision": state.get("revision"),
            "product_revision": state.get("product_revision"),
            "support_revision": state.get("support_revision"),
            "evidence_revision": state.get("evidence_revision"),
            "coverage_revision": coverage_revision_summary(state),
            "implementation_state": state.get("implementation_state", {}),
            "feature_verification_state": state.get("feature_verification_state", {}),
        },
        "scope": {
            "active_slice": state.get("active_slice"),
            "execution_stage": state.get("execution_stage"),
            "scope_guard": state.get("scope_guard", {}),
            "finding_triage": state.get("finding_triage"),
        },
        "workers": {
            "worker_budget": state.get("worker_budget", {}),
            "owner_by_slice": state.get("owner_by_slice", {}),
            "integration_owner": state.get("integration_owner"),
            "engineering_owner_id": state.get("engineering_owner_id"),
        },
    }
    return {
        "status_schema": STATUS_SCHEMA_VERSION,
        "mode": "section",
        "section": section,
        "feature": state.get("feature"),
        "phase": state.get("phase"),
        "data": sections[section],
        "next_action": next_action(state, findings),
    }


def cmd_status(args: argparse.Namespace) -> int:
    _, _, _, state, findings = load_runtime(args.project_root)
    return render_status(args, state, findings)


def render_status(
    args: argparse.Namespace, state: dict[str, Any], findings: dict[str, Any]
) -> int:
    """Render already-validated in-memory state without reopening the runtime."""
    if getattr(args, "full", False):
        result = full_status_payload(state, findings)
    elif getattr(args, "section", None):
        result = status_section_payload(args.section, state, findings)
    else:
        result = compact_status_payload(state, findings, args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def require_preengineering_authority_recovery_gate(state: dict[str, Any]) -> None:
    """Fail closed unless the runtime has never crossed the engineering boundary."""
    if state.get("active_write_lease") is not None:
        raise PipelineError("authority recovery is forbidden while a write lease is active")
    if state.get("write_lease_history"):
        raise PipelineError("authority recovery is forbidden after any writer lease")
    if (
        state.get("engineer_runs")
        or state.get("engineer_clean") is not None
        or state.get("last_engineer_run_id") is not None
        or state.get("last_engineer_outcome") is not None
        or state.get("pending_engineer_completion") is not None
    ):
        raise PipelineError("authority recovery is forbidden after Engineer evidence")
    if (state.get("implementation_state") or {}).get("status") not in {
        "pending",
        "in_progress",
    }:
        raise PipelineError("authority recovery is forbidden after product implementation evidence")
    if (state.get("feature_verification_state") or {}).get("status") != "pending":
        raise PipelineError("authority recovery is forbidden after feature verification evidence")
    for slice_id in state.get("ordered_slices", []):
        item = (state.get("slices") or {}).get(slice_id) or {}
        if (
            item.get("sealed_at") is not None
            or item.get("status") not in {"pending", "active"}
            or item.get("result_revision") is not None
            or item.get("scope_pre_edit_check") is not None
        ):
            raise PipelineError(
                f"authority recovery is forbidden after engineering/sealing evidence for {slice_id}"
            )


def authority_rebaseline_token(
    state: dict[str, Any], reason: str, authorized_by: str
) -> str:
    """Bind one external recovery authorization to the exact pre-engineering state."""
    reason = reason.strip()
    authorized_by = authorized_by.strip()
    if not reason or not authorized_by:
        raise PipelineError("authority recovery requires a reason and authorizing identity")
    return "ARR-" + canonical_json_sha256(
        {
            "schema": 1,
            "operation": "rebaseline_authority",
            "feature": state.get("feature"),
            "reason": reason,
            "authorized_by": authorized_by,
            "revision": state.get("revision"),
            "requirements": {
                "path": state.get("requirements_path"),
                "revision": state.get("requirements_revision"),
                "sha256": state.get("requirements_sha256"),
            },
            "specification": {
                "path": state.get("spec_path"),
                "sha256": state.get("spec_sha256"),
            },
            "development_plan": {
                "path": state.get("development_plan_path"),
                "sha256": state.get("development_plan_sha256"),
            },
            "ordered_slices": state.get("ordered_slices"),
        }
    )[:32].upper()


def load_authority_rebaseline_runtime(
    project_root: str,
) -> tuple[Path, Path, Path, dict[str, Any], dict[str, Any]]:
    """Load pre-engineering state without reconciling expected authority drift."""
    root, state_path, findings_path = runtime_paths(project_root)
    state = read_json(state_path)
    findings = load_canonical_findings(state, findings_path)
    if (
        state.get("schema_version") != SCHEMA_VERSION
        or state.get("contract_version") != CONTRACT_VERSION
        or findings.get("schema_version") != SCHEMA_VERSION
    ):
        raise PipelineError("authority recovery requires the current exact runtime schema")
    normalize_runtime(state, findings)
    validate_schema10_runtime(state, findings)
    if state.get("phase") not in {
        "preflight",
        "slice_research",
        "slice_coverage_planning",
    }:
        raise PipelineError(
            "rebaseline-authority is legal only before Engineer evidence"
        )
    try:
        canonical_decision_ledger(root, state)
    except PipelineError as exc:
        raise PipelineError("decision ledger changed during authority recovery") from exc
    require_preengineering_authority_recovery_gate(state)
    return root, state_path, findings_path, state, findings


def require_exact_specification_ready(
    root: Path, requirements: Path, spec: Path
) -> dict[str, Any]:
    proof = read_json(root / Path(STATE_DIR) / "specification-state.json")
    ready = proof.get("ready") or {}
    if (
        proof.get("status") != "spec_ready"
        or (proof.get("prd") or {}).get("path") != requirements.relative_to(root).as_posix()
        or (proof.get("specification") or {}).get("path") != spec.relative_to(root).as_posix()
        or ready.get("prd_sha256") != file_sha256(requirements)
        or ready.get("spec_sha256") != file_sha256(spec)
    ):
        raise PipelineError(
            "specification-state.json does not prove SPEC_READY for the exact fresh PRD/spec"
        )
    return proof


def authority_contract_projection_from_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": state.get("development_mode"),
        "ordered_slices": list(state.get("ordered_slices", [])),
        "contracts": copy.deepcopy(state.get("plan_contracts", {})),
        "slices": {
            slice_id: {
                "dependencies": copy.deepcopy(item.get("dependencies", [])),
                "requirement_ids": copy.deepcopy(item.get("requirement_ids", [])),
                "scope_contract": copy.deepcopy(item.get("scope_contract")),
            }
            for slice_id, item in (state.get("slices") or {}).items()
        },
    }


def authority_contract_projection_from_plan(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": plan["mode"],
        "ordered_slices": [item["id"] for item in plan["slices"]],
        "contracts": copy.deepcopy(plan["contracts"]),
        "slices": {
            item["id"]: {
                "dependencies": copy.deepcopy(item["dependencies"]),
                "requirement_ids": copy.deepcopy(item["requirement_ids"]),
                "scope_contract": copy.deepcopy(item["scope_contract"]),
            }
            for item in plan["slices"]
        },
    }


def cmd_rebaseline_authority(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_authority_rebaseline_runtime(
        args.project_root
    )
    reason = args.reason.strip()
    authorized_by = args.authorized_by.strip()
    expected_token = authority_rebaseline_token(state, reason, authorized_by)
    if args.recovery_token != expected_token:
        raise PipelineError("recovery token does not match the exact pre-engineering authority")
    requirements = resolve_project_file(root, args.requirements, "Approved product requirements")
    spec = resolve_project_file(root, args.spec, "Approved technical specification")
    if (
        str(requirements) != state["requirements_path"]
        or str(spec) != state["spec_path"]
    ):
        raise PipelineError("authority recovery cannot change canonical PRD/spec paths in-place")
    requirements_meta, spec_meta, acceptance_inventory = require_feature_documents(
        root, state["feature"], requirements, spec
    )
    specification_ready = require_exact_specification_ready(root, requirements, spec)
    plan = require_development_plan(
        root,
        state["feature"],
        requirements,
        spec,
        args.plan,
        args.plan_sha256,
        acceptance_inventory,
    )
    if plan["path"] != state["development_plan_path"]:
        raise PipelineError("authority recovery cannot change the canonical plan path in-place")
    new_order = [item["id"] for item in plan["slices"]]
    if new_order != state["ordered_slices"]:
        raise PipelineError("authority recovery cannot change slice IDs or ordering in-place")
    old_hashes = {
        "requirements_sha256": state["requirements_sha256"],
        "spec_sha256": state["spec_sha256"],
        "plan_sha256": state["development_plan_sha256"],
    }
    new_hashes = {
        "requirements_sha256": file_sha256(requirements),
        "spec_sha256": file_sha256(spec),
        "plan_sha256": plan["sha256"],
    }
    changed = {key for key in new_hashes if new_hashes[key] != old_hashes[key]}
    if not changed:
        raise PipelineError("authority recovery requires at least one freshly approved authority")
    authority_text_changed = bool(
        changed.intersection({"requirements_sha256", "spec_sha256"})
    )
    if "requirements_sha256" in changed:
        if (
            requirements_meta.get("revision") == state.get("requirements_revision")
            or not requirements_meta.get("approved_at")
            or requirements_meta.get("approved_at") == "null"
            or not (args.prd_approval_reference or "").strip()
        ):
            raise PipelineError(
                "changed PRD requires a new revision, approved_at, and fresh approval reference"
            )
    if "spec_sha256" in changed:
        confirmed_at = (specification_ready.get("ready") or {}).get("confirmed_at")
        if (
            not confirmed_at
            or not (args.spec_approval_reference or "").strip()
        ):
            raise PipelineError(
                "changed specification requires exact SPEC_READY and an approval reference"
            )
    approval = plan.get("approval") or {}
    if (
        new_hashes["plan_sha256"] != old_hashes["plan_sha256"]
        and (
            approval.get("approved_by") != "user"
            or not approval.get("approved_at")
            or not (args.plan_approval_reference or "").strip()
        )
    ):
        raise PipelineError(
            "changed plan requires controller-recorded explicit user approval and a reference"
        )
    prior_phase = state["phase"]
    prior_projection = authority_contract_projection_from_state(state)
    next_projection = authority_contract_projection_from_plan(plan)
    prior_capabilities = required_preflight_capabilities(state)
    changed_research: list[str] = []
    changed_coverage: list[str] = []
    for slice_id in state["ordered_slices"]:
        old_slice = prior_projection["slices"][slice_id]
        new_slice = next_projection["slices"][slice_id]
        if old_slice != new_slice:
            changed_research.append(slice_id)
        old_contract = prior_projection["contracts"]["slices"][slice_id]["coverage"]
        new_contract = next_projection["contracts"]["slices"][slice_id]["coverage"]
        if old_slice["scope_contract"]["acceptance_ids"] != new_slice["scope_contract"][
            "acceptance_ids"
        ] or old_contract != new_contract:
            changed_coverage.append(slice_id)
    if (
        prior_projection["contracts"].get("coverage_strategy")
        != next_projection["contracts"].get("coverage_strategy")
    ):
        changed_coverage = list(state["ordered_slices"])
    documentation_changed = (
        prior_projection["contracts"].get("documentation_strategy")
        != next_projection["contracts"].get("documentation_strategy")
        or any(
            prior_projection["contracts"]["slices"][slice_id].get("documentation")
            != next_projection["contracts"]["slices"][slice_id].get("documentation")
            for slice_id in state["ordered_slices"]
        )
    )
    state["requirements_revision"] = requirements_meta["revision"]
    state["requirements_sha256"] = new_hashes["requirements_sha256"]
    state["spec_sha256"] = new_hashes["spec_sha256"]
    state["development_plan_sha256"] = new_hashes["plan_sha256"]
    state["development_mode"] = plan["mode"]
    state["plan_contracts"] = plan["contracts"]
    for item in plan["slices"]:
        target = state["slices"][item["id"]]
        target["dependencies"] = item["dependencies"]
        target["requirement_ids"] = item["requirement_ids"]
        target["scope_contract"] = item["scope_contract"]
        target["scope_pre_edit_check"] = None
    new_capabilities = required_preflight_capabilities(state)
    capabilities_changed = prior_capabilities != new_capabilities
    if authority_text_changed:
        changed_research = list(state["ordered_slices"])
        changed_coverage = list(state["ordered_slices"])
        documentation_changed = True
    for slice_id in changed_coverage:
        state["coverage"][slice_id] = empty_coverage_scope()
    for slice_id in changed_research:
        state["slices"][slice_id]["research"] = {
            "status": "pending",
            "base_revision": None,
            "bundles": [],
            "reason": None,
            "completed_at": None,
        }
    if changed_coverage:
        state["coverage"].pop("feature", None)
        state["coverage_manifest"] = None
        state["implementation_state"] = {
            "status": "pending",
            "revision": None,
            "coverage_manifest": None,
        }
    if documentation_changed:
        state["documentation"] = empty_documentation_state()
    stale_capsules: list[str] = []
    for capsule in state.get("context_capsules", []):
        if isinstance(capsule, dict) and capsule.get("status") != "stale":
            capsule["status"] = "stale"
            capsule["stale_reason"] = "authority_rebaseline"
            stale_capsules.append(str(capsule.get("capsule_id")))
    if capabilities_changed:
        state["preflight"] = empty_preflight_state()
    active_id = state.get("active_slice")
    if capabilities_changed:
        next_phase = "preflight"
        state["preflight"]["migration_resume_phase"] = (
            "slice_research" if active_id in changed_research else prior_phase
        )
    elif active_id in changed_research:
        next_phase = "slice_research"
    elif active_id in changed_coverage:
        next_phase = "slice_coverage_planning"
    else:
        next_phase = prior_phase
    computed = compute_inventory_revisions(root, state)
    for key in ("revision", "product_revision", "support_revision", "evidence_revision"):
        state[key] = computed[key]
    active_slice = state["slices"][state["active_slice"]]
    active_slice.update(
        {
            "base_revision": state["revision"],
            "base_product_revision": state["product_revision"],
            "base_support_revision": state["support_revision"],
            "base_evidence_revision": state["evidence_revision"],
        }
    )
    for slice_id in changed_research:
        state["slices"][slice_id]["research"]["base_revision"] = (
            state["revision"] if slice_id == state.get("active_slice") else None
        )
    semantic_equivalent = (
        not authority_text_changed and prior_projection == next_projection
    )
    event = {
        "event": "authority_rebaseline",
        "token": expected_token,
        "reason": reason,
        "authorized_by": authorized_by,
        "old_authority": old_hashes,
        "new_authority": new_hashes,
        "approval_references": {
            "prd": args.prd_approval_reference,
            "specification": args.spec_approval_reference,
            "plan": args.plan_approval_reference,
        },
        "semantic_equivalent": semantic_equivalent,
        "prior_contract_sha256": canonical_json_sha256(prior_projection),
        "new_contract_sha256": canonical_json_sha256(next_projection),
        "invalidated_preflight": capabilities_changed,
        "invalidated_research_slice_ids": changed_research,
        "invalidated_coverage_scope_ids": changed_coverage,
        "invalidated_documentation": documentation_changed,
        "stale_capsules": stale_capsules,
        "capabilities_changed": capabilities_changed,
        "next_phase": next_phase,
        "recorded_at": utc_now(),
    }
    state.setdefault("authority_recovery_history", []).append(event)
    state["phase"] = next_phase
    save_runtime(state_path, findings_path, state, findings)
    print(json.dumps({"rebaselined": True, "phase": next_phase, **new_hashes}, ensure_ascii=False))
    return 0


def parse_capsule_reference(root: Path, value: str, label: str) -> dict[str, Any]:
    if "=" not in value:
        raise PipelineError(f"{label} must use path=sha256:ID,ID")
    supplied_path, digest_and_ids = value.split("=", 1)
    digest, separator, ids_text = digest_and_ids.partition(":")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise PipelineError(f"{label} must contain a lowercase SHA-256")
    ids = [item.strip() for item in ids_text.split(",") if item.strip()] if separator else []
    if len(ids) != len(set(ids)):
        raise PipelineError(f"{label} contains duplicate IDs")
    if supplied_path == "not_applicable":
        if "authority" not in label.casefold() or not ids:
            raise PipelineError(
                "not_applicable is valid only for an ID-bound capsule authority digest"
            )
        return {"path": "not_applicable", "sha256": digest, "ids": ids}
    path = resolve_project_file(root, supplied_path, label)
    relative = path.relative_to(root).as_posix()
    if file_sha256(path) != digest:
        raise PipelineError(f"{label} SHA-256 does not match current bytes: {relative}")
    if ids:
        text_value = path.read_text(encoding="utf-8", errors="replace")
        missing = [item for item in ids if item not in text_value]
        if missing:
            raise PipelineError(
                f"{label} IDs are absent from {relative}: " + ", ".join(missing)
            )
    return {"path": relative, "sha256": digest, "ids": ids}


def capsule_digest(value: dict[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "capsule_sha256"}
    return canonical_json_sha256(payload)


def capsule_metrics(
    value: dict[str, Any], root: Path
) -> dict[str, int]:
    payload = {
        key: item
        for key, item in value.items()
        if key not in {"metrics", "capsule_sha256"}
    }
    referenced = {
        item["path"]
        for field in ("authority", "evidence")
        for item in value[field]
        if item["path"] != "not_applicable"
    }
    payload_bytes = len(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ) + sum((root / path).stat().st_size for path in referenced)
    return {
        "authority_files": len(
            {item["path"] for item in value["authority"] if item["path"] != "not_applicable"}
        ),
        "evidence_files": len({item["path"] for item in value["evidence"]}),
        "total_files": len(referenced),
        "payload_bytes": payload_bytes,
        "estimated_tokens": (payload_bytes + 3) // 4,
    }


def approved_capsule_budget(state: dict[str, Any], phase: str) -> dict[str, int]:
    slice_scoped = {
        "slice_research",
        "slice_coverage_planning",
        "slice_engineering",
        "slice_coverage_finalization",
    }
    active_slice = state.get("active_slice")
    if phase in slice_scoped and active_slice:
        return dict(state["plan_contracts"]["slices"][active_slice]["context_budget"])
    return dict(state["plan_contracts"]["context_budget"])


def validate_capsule_budget_ceiling(
    state: dict[str, Any], phase: str, budget: dict[str, int]
) -> None:
    approved = approved_capsule_budget(state, phase)
    exceeded = [
        name for name in CONTEXT_LIMIT_NAMES if budget[name] > approved[name]
    ]
    if exceeded:
        raise PipelineError(
            "Context capsule limits exceed approved development-plan ceilings: "
            + ", ".join(exceeded)
        )
    if budget["max_total_files"] < max(
        budget["max_authority_files"], budget["max_evidence_files"]
    ):
        raise PipelineError(
            "Context capsule max_total_files must cover each authority/evidence file ceiling"
        )


def capsule_scope_ids(state: dict[str, Any], phase: str) -> set[str]:
    if phase.startswith("slice_") and state.get("active_slice"):
        scope_ids = [state["active_slice"]]
    else:
        scope_ids = list(state.get("ordered_slices", []))
    result: set[str] = set()
    for scope_id in scope_ids:
        item = state.get("slices", {}).get(scope_id, {})
        result.update(str(value) for value in item.get("requirement_ids", []))
        result.update(
            str(value)
            for value in (item.get("scope_contract") or {}).get("acceptance_ids", [])
        )
    return result


def capsule_manifest_contract(
    root: Path, state: dict[str, Any], phase: str
) -> tuple[str | None, set[str]]:
    active_slice = state.get("active_slice")
    record: dict[str, Any] | None = None
    identity_field = "actual_identities"
    if phase in {"slice_engineering", "engineering", "slice_coverage_finalization"}:
        active_batch = state.get("active_remediation_batch") or {}
        if (
            phase == "engineering"
            and active_batch.get("status") == "active"
            and active_batch.get("route") == "integration"
        ):
            record = state.get("coverage", {}).get("feature", {}).get(
                "finalized_manifest"
            )
        else:
            record = (
                state.get("coverage", {}).get(active_slice, {}).get("planned_manifest")
                if active_slice
                else None
            )
            identity_field = "expected_identities"
    elif phase in {
        "convergence",
        "review",
        "closure_review",
        "recovery_review",
        "documentation_review",
        "qa",
        "evidence_recovery",
        "derived_documentation",
    }:
        record = state.get("coverage", {}).get("feature", {}).get("finalized_manifest")
    if not record:
        return None, set()
    supplied_path = record.get("path")
    expected_sha = record.get("sha256")
    if not supplied_path or not expected_sha:
        raise PipelineError("Controller coverage evidence record is incomplete")
    path = resolve_project_file(root, supplied_path, "Capsule coverage evidence")
    if file_sha256(path) != expected_sha:
        raise PipelineError("Controller coverage evidence record is stale")
    manifest = read_json(path)
    identities = manifest.get(identity_field)
    if not isinstance(identities, list):
        raise PipelineError(
            f"Capsule coverage evidence lacks controller-required {identity_field}"
        )
    identity_ids = {
        str(item.get("identity_id"))
        for item in identities
        if isinstance(item, dict) and item.get("identity_id")
    }
    if len(identity_ids) != len(identities):
        raise PipelineError("Capsule coverage evidence contains malformed identity records")
    return path.relative_to(root).as_posix(), identity_ids


def capsule_expected_finding_ids(
    root: Path, state: dict[str, Any], role: str, phase: str
) -> set[str]:
    expected: set[str] = set()
    if role == "engineer":
        batch = state.get("active_remediation_batch") or {}
        if batch.get("status") == "active":
            route = batch.get("route")
            valid_routes = set(state.get("ordered_slices", [])) | {"integration"}
            if route not in valid_routes:
                raise PipelineError(
                    "Active Engineer remediation batch has an invalid controller route"
                )
            expected.update(str(value) for value in batch.get("finding_ids", []))
    if role == "reviewer" and phase == "closure_review":
        closure = state.get("closure_review") or {}
        expected.update(str(value) for value in closure.get("finding_ids", []))
    if role == "recovery_remediator" or phase == "recovery_review":
        recovery = state.get("recovery") or {}
        expected.update(str(value) for value in recovery.get("finding_ids", []))
    return expected


def capsule_exact_authority(root: Path, state: dict[str, Any]) -> dict[str, str]:
    records: dict[str, str] = {}

    def add(value: str, expected_sha256: str) -> None:
        records[
            controller_relative_path(root, value, "Capsule controller authority")
        ] = expected_sha256

    add(state["requirements_path"], state["requirements_sha256"])
    add(state["spec_path"], state["spec_sha256"])
    add(state["development_plan_path"], state["development_plan_sha256"])
    if state["decision_ledger"]["active_decision_ids"]:
        add(state["decision_ledger"]["path"], state["decision_ledger"]["sha256"])
    return records


def capsule_exact_evidence(
    root: Path, state: dict[str, Any], role: str, phase: str
) -> dict[str, str]:
    records: dict[str, str] = {}

    def add(value: str | None, expected_sha256: str | None, label: str) -> None:
        if not value or not expected_sha256:
            raise PipelineError(f"Exact {label} evidence is missing from controller state")
        relative = controller_relative_path(root, value, f"Capsule {label} evidence")
        path = resolve_project_file(root, relative, f"Capsule {label} evidence")
        if file_sha256(path) != expected_sha256:
            raise PipelineError(f"Exact {label} evidence drifted after controller recording")
        records[relative] = expected_sha256

    coverage_path, _ = capsule_manifest_contract(root, state, phase)
    if coverage_path:
        coverage_record = None
        for scope in state.get("coverage", {}).values():
            for name in ("planned_manifest", "finalized_manifest"):
                candidate = scope.get(name) or {}
                if candidate.get("path") and controller_relative_path(
                    root, candidate["path"], "Capsule coverage lookup"
                ) == coverage_path:
                    coverage_record = candidate
                    break
            if coverage_record:
                break
        if not coverage_record:
            raise PipelineError("Exact capsule coverage evidence is absent")
        add(coverage_record["path"], coverage_record["sha256"], "coverage")

    def add_handoff() -> None:
        handoffs = state.get("handoffs") or []
        if not handoffs:
            raise PipelineError("Exact current controller handoff is missing")
        handoff = handoffs[-1]
        add(handoff.get("path"), handoff.get("sha256"), "handoff")

    def add_review_runs(runs: list[dict[str, Any]], label: str) -> None:
        for run in runs:
            add(
                run.get("credit_manifest"),
                run.get("credit_manifest_sha256"),
                f"{label} credit manifest",
            )

    if role == "reviewer":
        add_handoff()
        if phase == "review":
            add_review_runs(
                list((state.get("convergence") or {}).get("runs", [])),
                "convergence",
            )
        elif phase == "closure_review":
            add_review_runs(
                list((state.get("closure_review") or {}).get("base_review_runs", [])),
                "base Review",
            )
        elif phase == "recovery_review":
            add_review_runs(
                list((state.get("recovery") or {}).get("base_review_runs", [])),
                "base Review",
            )
        elif phase == "qa":
            review = state.get("review") or {}
            review_runs = list(review.get("runs", []))
            if review.get("recovery_run"):
                review_runs.append(review["recovery_run"])
            add_review_runs(review_runs, "current Review")
            capability = state.get("qa_capability") or {}
            add(
                capability.get("report"),
                capability.get("report_sha256"),
                "QA capability probe",
            )
            prior_qa = state.get("qa") or {}
            if prior_qa.get("manual_execution"):
                add(
                    prior_qa.get("manual_execution"),
                    prior_qa.get("manual_execution_sha256"),
                    "prior QA manual execution",
                )
        elif phase == "documentation_review":
            review = state.get("review") or {}
            review_runs = list(review.get("runs", []))
            if review.get("recovery_run"):
                review_runs.append(review["recovery_run"])
            add_review_runs(review_runs, "current Review")
            qa = state.get("qa") or {}
            add(
                qa.get("manual_execution"),
                qa.get("manual_execution_sha256"),
                "QA manual execution",
            )
            derived = (state.get("documentation") or {}).get("derived") or {}
            add(
                derived.get("source_map_path"),
                derived.get("source_map_sha256"),
                "documentation source map",
            )
    elif role == "recovery_remediator":
        add_review_runs(
            list((state.get("recovery") or {}).get("base_review_runs", [])),
            "recovery source Review",
        )
    elif role == "documentation_finisher" and phase == "derived_documentation":
        add_handoff()
        review = state.get("review") or {}
        review_runs = list(review.get("runs", []))
        if review.get("recovery_run"):
            review_runs.append(review["recovery_run"])
        add_review_runs(review_runs, "current Review")
        qa = state.get("qa") or {}
        add(
            qa.get("manual_execution"),
            qa.get("manual_execution_sha256"),
            "QA manual execution",
        )

    if role == "engineer" and phase in {"slice_engineering", "engineering"}:
        active = active_slice_state(state)
        research = (active or {}).get("research") or {}
        if research.get("status") == "complete":
            for bundle in research.get("bundles") or []:
                add(
                    bundle.get("path"),
                    bundle.get("bundle_sha256"),
                    f"research bundle {bundle.get('brief_id') or 'unknown'}",
                )
        reconciliations = state.get("lifecycle_projection_reconciliations") or []
        if reconciliations:
            latest = reconciliations[-1]
            after_revisions = latest.get("after_revisions") or {}
            if after_revisions.get("revision") == state.get("revision"):
                add(
                    latest.get("path"),
                    latest.get("sha256"),
                    "lifecycle projection reconciliation",
                )

    return records


def capsule_exact_evidence_ids(
    root: Path, state: dict[str, Any], role: str, phase: str
) -> dict[str, list[str]]:
    """Return the exact selectors assigned to each already hash-bound evidence ref."""
    selectors = {
        path: [] for path in capsule_exact_evidence(root, state, role, phase)
    }
    if role == "engineer" and phase in {"slice_engineering", "engineering"}:
        active = active_slice_state(state)
        research = (active or {}).get("research") or {}
        if research.get("status") == "complete":
            for bundle in research.get("bundles") or []:
                relative = controller_relative_path(
                    root, bundle.get("path", ""), "Capsule research selector"
                )
                brief_id = bundle.get("brief_id")
                if not isinstance(brief_id, str) or not brief_id:
                    raise PipelineError("Controller research evidence lacks an exact brief ID")
                selectors[relative] = [brief_id]
    return selectors


def validate_capsule_semantics(
    root: Path, state: dict[str, Any], value: dict[str, Any]
) -> None:
    role = value["role"]
    phase = value["phase"]
    if phase not in CAPSULE_PHASES[role]:
        raise PipelineError("Context capsule role/phase semantic assignment is invalid")
    if role in WRITE_ROLES and not value["allowed_paths"]:
        raise PipelineError("Write-capable context capsule requires semantic allowed_paths")
    if role not in WRITE_ROLES and (
        value["allowed_paths"] or value["allowed_symbols"] or value["exclusions"]
    ):
        raise PipelineError(
            "Read-only context capsule cannot include write paths, symbols, or exclusions"
        )

    cited_authority_ids = {
        str(authority_id)
        for item in value["authority"]
        for authority_id in item["ids"]
    }
    if role == "decision_recorder":
        user_ids = {item["authority_id"] for item in state.get("user_authorities", [])}
        non_file_authority = [
            item for item in value["authority"] if item["path"] == "not_applicable"
        ]
        file_selectors = [
            (item, selector)
            for item in value["authority"]
            if item["path"] != "not_applicable"
            for selector in item["ids"]
        ]
        user_selectors = [
            selector for item in non_file_authority for selector in item["ids"]
        ]
        if len(file_selectors) + len(user_selectors) != 1:
            raise PipelineError(
                "Decision Recorder capsule requires exactly one assigned authority selector"
            )
        if user_selectors:
            if (
                len(non_file_authority) != 1
                or user_selectors[0] not in user_ids
                or file_selectors
            ):
                raise PipelineError(
                    "Decision Recorder user authority must be one prior accepted receipt"
                )
        else:
            if non_file_authority:
                raise PipelineError(
                    "Decision Recorder file authority cannot include a non-file receipt"
                )
            item, selector = file_selectors[0]
            authority_file = resolve_project_file(
                root, item["path"], "Decision Recorder assigned authority"
            )
            if selector not in authority_file.read_text(
                encoding="utf-8", errors="replace"
            ):
                raise PipelineError(
                    "Decision Recorder assigned authority selector is absent from its exact file"
                )
    else:
        known_authority_ids = capsule_scope_ids(state, phase)
        known_authority_ids.update(state["decision_ledger"]["active_decision_ids"])
        unknown_authority_ids = cited_authority_ids - known_authority_ids
        if unknown_authority_ids:
            raise PipelineError(
                "Context capsule cites authority IDs outside controller state: "
                + ", ".join(sorted(unknown_authority_ids))
            )
        if any(item["path"] == "not_applicable" for item in value["authority"]):
            raise PipelineError(
                "Only Decision Recorder capsules may contain non-file user authority"
            )
        missing_authority = capsule_scope_ids(state, phase) - cited_authority_ids
        if missing_authority:
            raise PipelineError(
                "Context capsule semantic authority omits required controller IDs: "
                + ", ".join(sorted(missing_authority))
            )
    expected_authority = capsule_exact_authority(root, state)
    file_authority = {
        item["path"]: item for item in value["authority"] if item["path"] != "not_applicable"
    }
    if set(file_authority) != set(expected_authority):
        missing = sorted(set(expected_authority) - set(file_authority))
        extra = sorted(set(file_authority) - set(expected_authority))
        raise PipelineError(
            "Context capsule semantic authority paths must equal the exact role packet; "
            + " ".join(
                part
                for part in (
                    "missing=" + ",".join(missing) if missing else "",
                    "unexpected=" + ",".join(extra) if extra else "",
                )
                if part
            )
        )
    stale_authority = sorted(
        path
        for path, item in file_authority.items()
        if item["sha256"] != expected_authority[path]
    )
    if stale_authority:
        raise PipelineError(
            "Context capsule authority SHA differs from controller state: "
            + ", ".join(stale_authority)
        )
    requirements_relative = controller_relative_path(
        root, state["requirements_path"], "Capsule PRD authority"
    )
    if role != "decision_recorder":
        if set(file_authority[requirements_relative]["ids"]) != capsule_scope_ids(state, phase):
            raise PipelineError("Context capsule PRD authority IDs must equal the phase scope")
        for path, item in file_authority.items():
            if path == requirements_relative:
                continue
            expected_ids = (
                set(state["decision_ledger"]["active_decision_ids"])
                if path
                == controller_relative_path(
                    root, state["decision_ledger"]["path"], "Capsule decision authority"
                )
                else set()
            )
            if set(item["ids"]) != expected_ids:
                raise PipelineError(
                    f"Context capsule authority IDs are unnecessary or incomplete for {path}"
                )

    expected_decisions = set(state["decision_ledger"]["active_decision_ids"])
    if set(value["decision_ids"]) != expected_decisions:
        raise PipelineError(
            "Context capsule decision_ids must equal the active controller decision set"
        )
    expected_findings = capsule_expected_finding_ids(root, state, role, phase)
    if set(value["finding_ids"]) != expected_findings:
        raise PipelineError(
            "Context capsule finding_ids must equal the assigned controller finding set"
        )

    required_evidence, expected_coverage = capsule_manifest_contract(root, state, phase)
    evidence_required_phases = {
        "slice_engineering",
        "engineering",
        "slice_coverage_finalization",
        "convergence",
        "review",
        "closure_review",
        "recovery_review",
        "documentation_review",
        "qa",
        "evidence_recovery",
        "derived_documentation",
    }
    if phase in evidence_required_phases and not required_evidence:
        raise PipelineError(
            "Context capsule semantic assignment lacks controller-produced phase evidence"
        )
    if set(value["coverage_identity_ids"]) != expected_coverage:
        raise PipelineError(
            "Context capsule coverage_identity_ids must equal the controller coverage set"
        )
    evidence_paths = {item["path"] for item in value["evidence"]}
    exact_evidence = capsule_exact_evidence(root, state, role, phase)
    if evidence_paths != set(exact_evidence):
        missing = sorted(set(exact_evidence) - evidence_paths)
        extra = sorted(evidence_paths - set(exact_evidence))
        raise PipelineError(
            "Context capsule evidence paths must equal the exact role/phase packet; "
            + " ".join(
                part
                for part in (
                    "missing=" + ",".join(missing) if missing else "",
                    "unexpected=" + ",".join(extra) if extra else "",
                )
                if part
            )
        )
    stale_evidence = sorted(
        item["path"]
        for item in value["evidence"]
        if exact_evidence.get(item["path"]) != item["sha256"]
    )
    if stale_evidence:
        raise PipelineError(
            "Context capsule evidence SHA differs from controller state: "
            + ", ".join(stale_evidence)
        )
    exact_evidence_ids = capsule_exact_evidence_ids(root, state, role, phase)
    selector_mismatches = sorted(
        item["path"]
        for item in value["evidence"]
        if item["ids"] != exact_evidence_ids[item["path"]]
    )
    if selector_mismatches:
        raise PipelineError(
            "Context capsule evidence selectors differ from the exact role/phase packet: "
            + ", ".join(selector_mismatches)
        )
    if role in {"decision_recorder", "documentation_finisher"} and value["commands"]:
        raise PipelineError("Context capsule includes unnecessary commands for this role")


def validate_capsule_value(
    root: Path, state: dict[str, Any], value: dict[str, Any]
) -> None:
    required = {
        "schema",
        "capsule_id",
        "role",
        "phase",
        "worker_id",
        "plan_sha256",
        "revisions",
        "authority",
        "decision_ids",
        "finding_ids",
        "coverage_identity_ids",
        "evidence",
        "allowed_paths",
        "allowed_symbols",
        "exclusions",
        "commands",
        "output_paths",
        "stop_condition",
        "budget",
        "metrics",
        "capsule_sha256",
    }
    if set(value) != required or value.get("schema") != 1:
        raise PipelineError("Context capsule must use the exact schema-1 fields")
    if value.get("role") not in CAPSULE_ROLES:
        raise PipelineError("Context capsule role is invalid")
    if not value.get("worker_id") or not value.get("phase") or not value.get("stop_condition"):
        raise PipelineError("Context capsule worker, phase, and stop condition are required")
    if value.get("plan_sha256") != state.get("development_plan_sha256"):
        raise PipelineError("Context capsule approved-plan SHA is stale")
    revisions = value.get("revisions")
    expected_revisions = {
        "revision": state.get("revision"),
        "product_revision": state.get("product_revision"),
        "support_revision": state.get("support_revision"),
        "evidence_revision": state.get("evidence_revision"),
    }
    if revisions != expected_revisions:
        raise PipelineError("Context capsule revision identities are stale")
    for field in ("authority", "evidence"):
        if not isinstance(value.get(field), list):
            raise PipelineError(f"Context capsule {field} must be a list")
        seen: set[str] = set()
        for item in value[field]:
            if not isinstance(item, dict) or set(item) != {"path", "sha256", "ids"}:
                raise PipelineError(f"Context capsule {field} entry is malformed")
            if item["path"] == "not_applicable":
                if field != "authority" or not item["ids"] or not re.fullmatch(
                    r"[0-9a-f]{64}", str(item["sha256"])
                ):
                    raise PipelineError("Capsule non-file authority digest is malformed")
                if len(item["ids"]) != 1 or not any(
                    record["authority_id"] == item["ids"][0]
                    and record["sha256"] == item["sha256"]
                    for record in state["user_authorities"]
                ):
                    raise PipelineError(
                        "Capsule non-file authority must cite one prior controller-registered user authority"
                    )
            else:
                path = resolve_project_file(root, item["path"], f"Capsule {field}")
                if file_sha256(path) != item["sha256"]:
                    raise PipelineError(f"Context capsule {field} reference is stale: {item['path']}")
            if item["path"] in seen:
                raise PipelineError(f"Context capsule repeats {field} path: {item['path']}")
            seen.add(item["path"])
    for field in (
        "decision_ids",
        "finding_ids",
        "coverage_identity_ids",
        "allowed_paths",
        "allowed_symbols",
        "exclusions",
        "commands",
        "output_paths",
    ):
        require_string_list(value.get(field), f"Context capsule {field}")
    unknown_decisions = sorted(
        set(value["decision_ids"]) - set(state["decision_ledger"]["active_decision_ids"])
    )
    if unknown_decisions:
        raise PipelineError(
            "Context capsule cites inactive decision IDs: " + ", ".join(unknown_decisions)
        )
    validate_capsule_semantics(root, state, value)
    budget = value.get("budget")
    if not isinstance(budget, dict) or set(budget) != set(CONTEXT_LIMIT_NAMES):
        raise PipelineError("Context capsule budget must contain all five exact limits")
    if any(not isinstance(budget[name], int) or budget[name] < 1 for name in CONTEXT_LIMIT_NAMES):
        raise PipelineError("Every context capsule limit must be a positive integer")
    validate_capsule_budget_ceiling(state, value["phase"], budget)
    metrics = capsule_metrics(value, root)
    if value.get("metrics") != metrics:
        raise PipelineError("Context capsule metrics do not match controller calculation")
    limits = {
        "authority_files": budget["max_authority_files"],
        "evidence_files": budget["max_evidence_files"],
        "total_files": budget["max_total_files"],
        "payload_bytes": budget["max_payload_bytes"],
        "estimated_tokens": budget["max_estimated_tokens"],
    }
    exceeded = [name for name, actual in metrics.items() if actual > limits[name]]
    if exceeded:
        raise PipelineError("Context capsule exceeds its declared limits: " + ", ".join(exceeded))
    if value.get("capsule_sha256") != capsule_digest(value):
        raise PipelineError("Context capsule digest is invalid")


def resolve_validated_capsule(
    root: Path,
    state: dict[str, Any],
    supplied: str,
    *,
    role: str | None = None,
    worker_id: str | None = None,
    phase: str | None = None,
) -> tuple[str, dict[str, Any]]:
    path = resolve_project_file(root, supplied, "Context capsule")
    relative = path.relative_to(root).as_posix()
    value = read_json(path)
    validate_capsule_value(root, state, value)
    if role and value["role"] != role:
        raise PipelineError(f"Context capsule role must be {role}")
    if worker_id and value["worker_id"] != worker_id:
        raise PipelineError("Context capsule worker identity mismatch")
    if phase and value["phase"] != phase:
        raise PipelineError("Context capsule phase mismatch")
    recorded = next(
        (
            item
            for item in state["context_capsules"]
            if item.get("capsule_id") == value["capsule_id"]
        ),
        None,
    )
    if isinstance(recorded, dict) and recorded.get("status") == "stale":
        raise PipelineError("Context capsule was made stale by controller reconciliation")
    if (
        not recorded
        or recorded.get("path") != relative
        or recorded.get("sha256") != file_sha256(path)
        or recorded.get("capsule_sha256") != value["capsule_sha256"]
    ):
        raise PipelineError("Context capsule was not created and preserved by this controller")
    return relative, value


def cmd_context_capsule_create(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    require_current_revision(state, args.revision)
    if args.role not in CAPSULE_ROLES:
        raise PipelineError("Unsupported context capsule role")
    if args.phase not in CAPSULE_PHASES[args.role]:
        raise PipelineError("Context capsule role/phase semantic assignment is invalid")
    allowed_current_phases = CAPSULE_ACTIVATION_PHASES.get(
        args.phase, {args.phase}
    )
    if state.get("phase") not in allowed_current_phases:
        route = next_action(state, findings)
        detail = {
            "requested_role": args.role,
            "requested_phase": args.phase,
            "current_phase": state.get("phase"),
            "next_action": route.get("action"),
        }
        raise PipelineError(
            "Context capsule activation is off-phase: "
            + json.dumps(detail, ensure_ascii=False, sort_keys=True)
        )
    supplied_budget = {name: getattr(args, name) for name in CONTEXT_LIMIT_NAMES}
    if any(
        not isinstance(supplied_budget[name], int) or supplied_budget[name] < 1
        for name in CONTEXT_LIMIT_NAMES
    ):
        raise PipelineError("Every context capsule CLI limit must be a positive integer")
    validate_capsule_budget_ceiling(state, args.phase, supplied_budget)
    authority = [
        parse_capsule_reference(root, value, "Capsule authority")
        for value in (args.authority or [])
    ]
    evidence = [
        parse_capsule_reference(root, value, "Capsule evidence")
        for value in (args.evidence or [])
    ]
    output_path, output_relative = resolve_project_output(root, args.output, "Capsule output")
    for target in args.output_path or []:
        resolve_project_output(root, target, "Capsule delegated output")
    capsule_id = f"CAP-{len(state['context_capsules']) + 1:04d}"
    value: dict[str, Any] = {
        "schema": 1,
        "capsule_id": capsule_id,
        "role": args.role,
        "phase": args.phase,
        "worker_id": args.worker_id,
        "plan_sha256": args.plan_sha256,
        "revisions": {
            "revision": state["revision"],
            "product_revision": state["product_revision"],
            "support_revision": state["support_revision"],
            "evidence_revision": state["evidence_revision"],
        },
        "authority": authority,
        "decision_ids": sorted(set(args.decision_id or [])),
        "finding_ids": sorted(set(args.finding_id or [])),
        "coverage_identity_ids": sorted(set(args.coverage_identity_id or [])),
        "evidence": evidence,
        "allowed_paths": [scope_path(item, "capsule allowed") for item in (args.allowed_path or [])],
        "allowed_symbols": sorted(set(args.allowed_symbol or [])),
        "exclusions": sorted(set(args.exclusion or [])),
        "commands": list(args.command or []),
        "output_paths": [
            resolve_project_output(root, target, "Capsule delegated output")[1]
            for target in (args.output_path or [])
        ],
        "stop_condition": args.stop_condition,
        "budget": supplied_budget,
        "metrics": {},
        "capsule_sha256": "",
    }
    value["metrics"] = capsule_metrics(value, root)
    value["capsule_sha256"] = capsule_digest(value)
    validate_capsule_value(root, state, value)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(output_path, value)
    state["context_capsules"].append(
        {
            "capsule_id": capsule_id,
            "path": output_relative,
            "sha256": file_sha256(output_path),
            "capsule_sha256": value["capsule_sha256"],
            "role": args.role,
            "phase": args.phase,
            "worker_id": args.worker_id,
            "revision": state["revision"],
            "metrics": value["metrics"],
            "created_at": utc_now(),
        }
    )
    save_runtime(state_path, findings_path, state, findings)
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0


def cmd_context_capsule_check(args: argparse.Namespace) -> int:
    root, _, _, state, _ = load_runtime(args.project_root)
    relative, value = resolve_validated_capsule(root, state, args.capsule)
    print(
        json.dumps(
            {
                "valid": True,
                "path": relative,
                "capsule_id": value["capsule_id"],
                "metrics": value["metrics"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def release_active_lease(
    state: dict[str, Any], *, result: str, reason: str
) -> dict[str, Any]:
    lease = state.get("active_write_lease")
    if not lease:
        raise PipelineError("No active write lease")
    released = dict(lease)
    released["status"] = "revoked" if result == "revoked" else "released"
    released["result"] = result
    released["reason"] = reason
    released["released_at"] = utc_now()
    state["write_lease_history"].append(released)
    state["active_write_lease"] = None
    state["lease_snapshots"].pop(lease["lease_id"], None)
    return released


def cmd_acquire_write_lease(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    if args.role not in WRITE_ROLES or args.phase not in LEASE_PHASES[args.role]:
        raise PipelineError("Write lease role/phase combination is invalid")
    if state.get("active_write_lease") is not None:
        raise PipelineError("A write-capable lease is already active in this checkout")
    current_phase = state["phase"]
    if args.phase == "normative_documentation" and current_phase == "implementation_complete":
        state["phase"] = "normative_documentation"
    elif args.phase == "decision_recording":
        safe_decision_boundaries = {
            "preflight",
            "slice_research",
            "slice_coverage_planning",
        }
        if current_phase not in safe_decision_boundaries:
            raise PipelineError(
                "Decision recording is allowed only before implementation begins; late decisions require replan/reinitialization"
            )
        state["decision_recording"] = {"resume_phase": current_phase}
        state["phase"] = "decision_recording"
    elif current_phase != args.phase:
        raise PipelineError(
            f"Write lease phase {args.phase} does not match controller phase {current_phase}"
        )
    if args.role == "engineer" and args.phase == "slice_engineering":
        active_scope = state["coverage"].get(state.get("active_slice"), {})
        if not active_scope.get("planned_manifest"):
            raise PipelineError("Engineer lease requires accepted schema-2 coverage planning")
    capsule_path, capsule = resolve_validated_capsule(
        root,
        state,
        args.capsule,
        role=args.role,
        worker_id=args.worker_id,
        phase=args.phase,
    )
    if not args.write_scope.strip():
        raise PipelineError("Write lease requires an exact non-empty write scope")
    if not capsule["allowed_paths"]:
        raise PipelineError("Write-capable context capsule requires a non-empty allowed_paths scope")
    scope_authorization: dict[str, Any] | None = None
    current_checkout = checkout_snapshot(
        root, state["feature"], state, extra_rules=capsule["allowed_paths"]
    )
    if args.role == "engineer" and args.phase in {"slice_engineering", "engineering"}:
        slice_item = scope_slice_for_pass(state, args.write_scope)
        active_owner = state.get("engineering_owner_id") or slice_item.get("owner_id")
        if active_owner and active_owner != args.worker_id:
            raise PipelineError("Engineer lease owner does not match the assigned Engineer")
        pre_edit = exact_scope_precheck(state, slice_item, args.worker_id)
        if pre_edit is None:
            raise PipelineError(
                "Engineer write lease requires a current exact-base slice-scope-check"
            )
        current_checkout_sha = checkout_snapshot_sha256(current_checkout)
        if pre_edit["checkout_snapshot_sha256"] != current_checkout_sha:
            raise PipelineError(
                "Checkout changed after slice-scope-check and before Engineer lease acquisition"
            )
        scope_authorization = {
            "kind": "pre_edit_check",
            "receipt_sha256": canonical_json_sha256(pre_edit),
            "slice_id": slice_item["id"],
            "owner_id": args.worker_id,
            "base_revision": state["revision"],
            "checkout_snapshot_sha256": current_checkout_sha,
        }
    lease_id = f"LEASE-{len(state['write_lease_history']) + 1:04d}"
    carried = state.get("scope_guard", {}).get("rebaseline_candidate")
    if carried and (
        args.role != "engineer"
        or args.write_scope != carried["slice_id"]
        or args.phase != state["phase"]
    ):
        raise PipelineError(
            "A rebaselined candidate requires the next fresh lease for its exact Engineer scope"
        )
    lease = {
        "lease_id": lease_id,
        "phase": args.phase,
        "write_scope": args.write_scope,
        "role": args.role,
        "worker_id": args.worker_id,
        "base_revision": (
            carried["base_revisions"]["revision"] if carried else state["revision"]
        ),
        "allowed_paths": capsule["allowed_paths"],
        "allowed_symbols": capsule["allowed_symbols"],
        "exclusions": capsule["exclusions"],
        "status": "active",
        "rebaseline_carried": bool(carried),
        "scope_authorization": scope_authorization,
    }
    lease_checkout = (
        carried["snapshot"]["checkout"] if carried else current_checkout
    )
    if scope_authorization is not None:
        scope_authorization["diff_base_checkout_sha256"] = checkout_snapshot_sha256(
            lease_checkout
        )
    if not carried and checkout_snapshot(
        root, state["feature"], state, extra_rules=capsule["allowed_paths"]
    ) != lease_checkout:
        raise PipelineError(
            "Checkout changed while capturing the Engineer lease snapshot"
        )
    state["active_write_lease"] = lease
    state["lease_snapshots"][lease_id] = build_lease_snapshot(
        root,
        state,
        capsule_path=capsule_path,
        capsule_sha256=capsule["capsule_sha256"],
        allowed_paths=capsule["allowed_paths"],
        authorization_checkout=current_checkout,
        checkout=lease_checkout,
        inherited_line_proofs=(
            carried["snapshot"].get("line_proofs") if carried else None
        ),
        rebaseline_carried=bool(carried),
        scope_authorization=scope_authorization,
    )
    save_runtime(state_path, findings_path, state, findings)
    print(json.dumps(lease, ensure_ascii=False, indent=2))
    return 0


def cmd_release_write_lease(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    request_sha256 = command_request_sha256(
        root,
        "release-write-lease",
        {"lease_id": args.lease_id, "result": args.result, "reason": args.reason},
    )
    lease = state.get("active_write_lease")
    if not lease or lease.get("lease_id") != args.lease_id:
        prior = next(
            (
                item
                for item in reversed(state.get("write_lease_history", []))
                if item.get("lease_id") == args.lease_id
            ),
            None,
        )
        if exact_lost_response_replay(prior, request_sha256, "release-write-lease"):
            print(json.dumps(prior, ensure_ascii=False, indent=2))
            return 0
        raise PipelineError("release-write-lease does not match the active lease")
    snapshot_record = state["lease_snapshots"].get(args.lease_id, {})
    snapshot = snapshot_record.get("checkout", {})
    current_checkout = checkout_snapshot(root, state["feature"], state)
    changed = changed_checkout_paths(snapshot, current_checkout)
    exhausted_engineer = (
        args.reason == "context_exhausted"
        and args.result == "revoked"
        and lease.get("role") == "engineer"
        and lease.get("phase") in {"slice_engineering", "engineering"}
    )
    if exhausted_engineer:
        owner_id = lease.get("worker_id")
        if owner_id not in state.setdefault("exhausted_worker_ids", []):
            state["exhausted_worker_ids"].append(owner_id)
        state["phase"] = "owner_handoff_hold"
    if changed:
        if not exhausted_engineer:
            raise PipelineError(
                "Dirty lease release requires Engineer result=revoked and exact "
                "reason=context_exhausted: " + ", ".join(changed)
            )
        changes = [
            {
                "path": relative,
                "base_sha256": snapshot.get(relative),
                "candidate_sha256": current_checkout.get(relative),
                "change_kind": (
                    "add" if relative not in snapshot
                    else "delete" if relative not in current_checkout
                    else "modify"
                ),
            }
            for relative in changed
        ]
        recovery = {
            "schema": 1,
            "kind": "context_exhausted_candidate",
            "prior_lease_id": lease["lease_id"],
            "prior_owner_id": owner_id,
            "base_checkout_sha256": checkout_snapshot_sha256(snapshot),
            "candidate_checkout_sha256": checkout_snapshot_sha256(current_checkout),
            "changes_sha256": canonical_json_sha256(changes),
            "changes": changes,
            "recorded_at": utc_now(),
        }
        slice_id = lease.get("write_scope")
        if slice_id not in state.get("slices", {}):
            slice_id = state.get("active_slice") or state.get("slice_id")
        state["scope_guard"]["rebaseline_candidate"] = {
            "slice_id": slice_id,
            "prior_lease_id": lease["lease_id"],
            "prior_owner_id": owner_id,
            "fresh_owner_required": True,
            "resume_phase": lease["phase"],
            "snapshot": {
                **copy.deepcopy(snapshot_record),
                "checkout": copy.deepcopy(snapshot),
                "authorization_checkout": copy.deepcopy(current_checkout),
                "rebaseline_carried": True,
            },
            "changes": changes,
            "base_revisions": {
                key: state.get(key) for key in (
                    "revision", "product_revision", "support_revision", "evidence_revision"
                )
            },
            "candidate_checkout": copy.deepcopy(current_checkout),
            "recovery": recovery,
        }
        state["phase"] = "owner_handoff_hold"
    released = release_active_lease(state, result=args.result, reason=args.reason)
    released["request_sha256"] = request_sha256
    if lease["phase"] == "decision_recording" and state.get("decision_recording"):
        state["phase"] = state["decision_recording"]["resume_phase"]
        state["decision_recording"] = None
    save_runtime(state_path, findings_path, state, findings)
    print(json.dumps(released, ensure_ascii=False, indent=2))
    return 0


def cmd_recover_legacy_engineer_scope(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(
        args.project_root, allow_active_writer_completion_drift=True
    )
    require_sources_current(state)
    history = state.setdefault("legacy_scope_recoveries", [])
    prior = next(
        (
            item
            for item in history
            if isinstance(item, dict) and item.get("lease_id") == args.lease_id
        ),
        None,
    )
    if prior is not None:
        raise PipelineError("Legacy scope recovery is one-shot and cannot be replayed")
    lease = state.get("active_write_lease")
    if (
        state.get("phase") not in {"slice_engineering", "engineering"}
        or not isinstance(lease, dict)
        or lease.get("lease_id") != args.lease_id
        or lease.get("role") != "engineer"
        or lease.get("worker_id") != args.owner_id
        or lease.get("phase") != state.get("phase")
    ):
        raise PipelineError("Legacy scope recovery requires the exact active Engineer lease")
    if lease.get("scope_authorization"):
        raise PipelineError("Legacy scope recovery is one-shot and the lease is already authorized")
    if lease.get("rebaseline_carried") is True:
        raise PipelineError("Legacy scope recovery cannot infer authority across a rebaseline")
    slice_item = scope_slice_for_pass(state, args.slice_id)
    if slice_item.get("scope_pre_edit_check") is not None:
        raise PipelineError("Legacy scope recovery requires a missing pre-edit check")
    if lease.get("base_revision") != state.get("revision"):
        raise PipelineError("Legacy lease base revision is not the current exact revision")
    snapshot = state.get("lease_snapshots", {}).get(args.lease_id)
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("checkout"), dict):
        raise PipelineError("Legacy scope recovery requires an immutable lease snapshot")
    migrated_legacy_lease = any(
        isinstance(event, dict)
        and event.get("event") == "schema9_to_schema10_migration"
        and event.get("legacy_active_lease_id") == args.lease_id
        for event in state.get("schema_migrations", [])
    )
    if snapshot.get("_legacy_scope_snapshot_eligible") is not True and not migrated_legacy_lease:
        raise PipelineError("Active lease is not an eligible legacy scope-gate lease")
    checkout = snapshot["checkout"]
    frozen = snapshot_revisions(state, checkout)
    for key in ("revision", "product_revision", "support_revision", "evidence_revision"):
        if frozen[key] != state.get(key):
            raise PipelineError(
                "Legacy lease snapshot does not reproduce the frozen pipeline revisions"
            )
    capsule_path, capsule = resolve_validated_capsule(
        root,
        state,
        snapshot.get("capsule_path", ""),
        role="engineer",
        worker_id=args.owner_id,
        phase=state["phase"],
    )
    if (
        capsule["capsule_sha256"] != snapshot.get("capsule_sha256")
        or capsule["allowed_paths"] != lease.get("allowed_paths")
        or capsule["allowed_symbols"] != lease.get("allowed_symbols")
        or capsule["exclusions"] != lease.get("exclusions")
    ):
        raise PipelineError("Legacy lease capsule binding is missing or changed")
    observed = changed_checkout_paths(
        checkout, checkout_snapshot(root, state["feature"], state)
    )
    scope = slice_item.get("scope_contract") or {}
    scope_paths = list(scope.get("editable_paths") or []) + [
        item["path"]
        for item in scope.get("shared_touchpoints") or []
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    ]
    for relative in observed:
        if not any(path_matches_scope(relative, rule) for rule in lease["allowed_paths"]):
            raise PipelineError(
                f"Legacy scope recovery observed path outside capsule authority: {relative}"
            )
        if any(
            path_matches_scope(relative, rule)
            for rule in list(lease.get("exclusions") or [])
            + list(scope.get("excluded_paths") or [])
            if "/" in rule
        ):
            raise PipelineError(
                f"Legacy scope recovery observed excluded path: {relative}"
            )
        if not any(path_matches_scope(relative, rule) for rule in scope_paths):
            raise PipelineError(
                f"Legacy scope recovery observed path outside the approved slice: {relative}"
            )
    checkout_sha = checkout_snapshot_sha256(checkout)
    recovery_id = f"LSR-{len(history) + 1:04d}"
    pre_edit = {
        "slice_id": slice_item["id"],
        "owner_id": args.owner_id,
        "base_revision": state["revision"],
        "development_plan_sha256": state["development_plan_sha256"],
        "scope_contract": slice_item["scope_contract"],
        "checkout_snapshot_sha256": checkout_sha,
        "status": "passed",
        "recorded_at": snapshot.get("created_at"),
        "recovered_at": utc_now(),
        "recovery_receipt_id": recovery_id,
    }
    if not isinstance(pre_edit["recorded_at"], str) or not pre_edit["recorded_at"]:
        raise PipelineError("Legacy lease snapshot lacks its controller-recorded creation time")
    logical_controller_root = Path(state["tests_path"]) / "verification" / "controller"
    controller_root = logical_controller_root.resolve()
    try:
        controller_relative = controller_root.relative_to(root)
    except ValueError as exc:
        raise PipelineError("Legacy scope recovery receipt root escapes project root") from exc
    boundary = root
    for part in controller_relative.parts:
        boundary = boundary / part
        if boundary.is_symlink():
            raise PipelineError(
                "Legacy scope recovery receipt path crosses a symlink boundary"
            )
    receipt_path = controller_root / f"legacy-scope-recovery-{len(history) + 1:04d}.json"
    if receipt_path.is_symlink():
        raise PipelineError("Legacy scope recovery receipt cannot be a symlink")
    orphan_receipt = read_json(receipt_path) if receipt_path.exists() else None
    recovery_recorded_at = (
        orphan_receipt.get("recorded_at")
        if isinstance(orphan_receipt, dict)
        else utc_now()
    )
    if not isinstance(recovery_recorded_at, str) or not recovery_recorded_at:
        raise PipelineError("Legacy scope recovery orphan receipt lacks recorded_at")
    pre_edit["recovered_at"] = recovery_recorded_at
    receipt = {
        "schema": 1,
        "receipt_id": recovery_id,
        "kind": "legacy_engineer_scope_authorization",
        "lease_id": args.lease_id,
        "slice_id": slice_item["id"],
        "owner_id": args.owner_id,
        "base_revision": state["revision"],
        "development_plan_sha256": state["development_plan_sha256"],
        "capsule_path": capsule_path,
        "capsule_sha256": capsule["capsule_sha256"],
        "checkout_snapshot_sha256": checkout_sha,
        "observed_changed_paths": observed,
        "recorded_at": recovery_recorded_at,
    }
    if receipt_path.exists():
        if orphan_receipt != receipt:
            raise PipelineError("Legacy scope recovery receipt path is already occupied")
    else:
        write_json(receipt_path, receipt)
    receipt_relative = receipt_path.relative_to(root).as_posix()
    receipt_file_sha = file_sha256(receipt_path)
    authorization = {
        "kind": "legacy_recovery",
        "receipt_sha256": canonical_json_sha256(pre_edit),
        "recovery_receipt_id": recovery_id,
        "recovery_receipt_sha256": receipt_file_sha,
        "slice_id": slice_item["id"],
        "owner_id": args.owner_id,
        "base_revision": state["revision"],
        "checkout_snapshot_sha256": checkout_sha,
        "diff_base_checkout_sha256": checkout_sha,
    }
    slice_item["scope_pre_edit_check"] = pre_edit
    slice_item["scope_history"].append({"event": "legacy_pre_edit_recovery", **pre_edit})
    state["scope_guard"]["status"] = "edit_authorized"
    state["scope_guard"]["history"].append(
        {"event": "legacy_pre_edit_recovery", **pre_edit}
    )
    lease["scope_authorization"] = authorization
    snapshot.pop("_legacy_scope_snapshot_eligible", None)
    snapshot["snapshot_schema"] = LEASE_SNAPSHOT_SCHEMA
    snapshot["snapshot_format"] = LEASE_SNAPSHOT_FORMAT
    snapshot["provenance"] = "legacy_pre_scope_gate"
    snapshot["scope_authorization"] = authorization
    snapshot["authorization_checkout"] = copy.deepcopy(checkout)
    history.append(
        {
            "receipt_id": recovery_id,
            "lease_id": args.lease_id,
            "slice_id": slice_item["id"],
            "owner_id": args.owner_id,
            "path": receipt_relative,
            "sha256": receipt_file_sha,
            "observed_changed_paths": observed,
            "recorded_at": receipt["recorded_at"],
        }
    )
    save_runtime(state_path, findings_path, state, findings)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


def engineer_continuation_artifact(
    root: Path,
    state: dict[str, Any],
    slice_item: dict[str, Any],
    owner_id: str,
) -> tuple[Path, str, dict[str, Any]]:
    """Derive the exact controller-owned Engineer capsule without role judgment."""
    phase = state["phase"]
    scope = slice_item.get("scope_contract") or {}
    allowed_paths = sorted(
        {
            scope_path(value, "Engineer continuation allowed")
            for value in list(scope.get("editable_paths") or [])
            + [
                item["path"]
                for item in scope.get("shared_touchpoints") or []
                if isinstance(item, dict) and isinstance(item.get("path"), str)
            ]
        }
    )
    exclusions = sorted(
        {
            str(value)
            for value in list(scope.get("excluded_paths") or [])
            + list(scope.get("excluded_components") or [])
            if str(value).strip()
        }
    )
    if not allowed_paths:
        raise PipelineError("Engineer continuation scope has no controller-approved editable paths")

    authority_ids = capsule_scope_ids(state, phase)
    requirements_relative = controller_relative_path(
        root, state["requirements_path"], "Engineer continuation PRD authority"
    )
    ledger_relative = controller_relative_path(
        root, state["decision_ledger"]["path"], "Engineer continuation decision authority"
    )
    authority = []
    for relative, digest in sorted(capsule_exact_authority(root, state).items()):
        ids = (
            sorted(authority_ids)
            if relative == requirements_relative
            else sorted(state["decision_ledger"]["active_decision_ids"])
            if relative == ledger_relative
            else []
        )
        authority.append({"path": relative, "sha256": digest, "ids": ids})
    exact_evidence = capsule_exact_evidence(root, state, "engineer", phase)
    exact_evidence_ids = capsule_exact_evidence_ids(root, state, "engineer", phase)
    evidence = [
        {
            "path": relative,
            "sha256": digest,
            "ids": exact_evidence_ids[relative],
        }
        for relative, digest in sorted(exact_evidence.items())
    ]
    _, coverage_ids = capsule_manifest_contract(root, state, phase)
    safe_owner = re.sub(r"[^A-Za-z0-9_.-]+", "-", owner_id).strip("-.") or "engineer"
    tests_relative = controller_relative_path(
        root, state["tests_path"], "Engineer continuation tests root"
    )
    artifact_root = Path(tests_relative) / "verification" / "controller"
    boundary = root
    for part in artifact_root.parts:
        boundary = boundary / part
        if boundary.is_symlink():
            raise PipelineError(
                "Engineer continuation controller artifact path crosses a symlink boundary"
            )
    capsule_id = f"CAP-{len(state['context_capsules']) + 1:04d}"
    capsule_relative = (
        artifact_root
        / f"engineer-continuation-{capsule_id.lower()}-{state['revision'][:12]}-{safe_owner}.json"
    ).as_posix()
    capsule_path, capsule_relative = resolve_project_output(
        root, capsule_relative, "Engineer continuation capsule"
    )
    output_paths = [
        (artifact_root / f"{capsule_id.lower()}-{safe_owner}-{phase}-semantic-handoff.json").as_posix(),
        (artifact_root / f"{capsule_id.lower()}-{safe_owner}-{phase}-report.json").as_posix(),
    ]
    for relative in output_paths:
        resolve_project_output(root, relative, "Engineer continuation delegated output")
    budget = approved_capsule_budget(state, phase)
    value: dict[str, Any] = {
        "schema": 1,
        "capsule_id": capsule_id,
        "role": "engineer",
        "phase": phase,
        "worker_id": owner_id,
        "plan_sha256": state["development_plan_sha256"],
        "revisions": {
            key: state[key]
            for key in (
                "revision",
                "product_revision",
                "support_revision",
                "evidence_revision",
            )
        },
        "authority": authority,
        "decision_ids": sorted(state["decision_ledger"]["active_decision_ids"]),
        "finding_ids": sorted(
            capsule_expected_finding_ids(root, state, "engineer", phase)
        ),
        "coverage_identity_ids": sorted(coverage_ids),
        "evidence": evidence,
        "allowed_paths": allowed_paths,
        "allowed_symbols": [],
        "exclusions": exclusions,
        "commands": [],
        "output_paths": output_paths,
        "stop_condition": (
            "Return the bounded Engineer result through engineer-complete and stop; "
            "do not perform another pipeline role"
        ),
        "budget": budget,
        "metrics": {},
        "capsule_sha256": "",
    }
    value["metrics"] = capsule_metrics(value, root)
    value["capsule_sha256"] = capsule_digest(value)
    validate_capsule_value(root, state, value)
    return capsule_path, capsule_relative, value


def validated_engineer_continuation_payload(
    root: Path,
    state: dict[str, Any],
    slice_item: dict[str, Any],
    owner_id: str,
    *,
    status: str,
) -> dict[str, Any]:
    """Validate every persisted binding before returning a subagent handoff."""
    lease = state.get("active_write_lease")
    if (
        not isinstance(lease, dict)
        or lease.get("status") != "active"
        or lease.get("role") != "engineer"
        or lease.get("phase") != state.get("phase")
        or lease.get("worker_id") != owner_id
        or lease.get("write_scope") != slice_item.get("id")
    ):
        raise PipelineError("Engineer continuation lacks the exact active Engineer lease")
    snapshot = state.get("lease_snapshots", {}).get(lease["lease_id"])
    if not isinstance(snapshot, dict):
        raise PipelineError("Engineer continuation lease snapshot is missing")
    capsule_path, capsule = resolve_validated_capsule(
        root,
        state,
        snapshot.get("capsule_path", ""),
        role="engineer",
        worker_id=owner_id,
        phase=state["phase"],
    )
    direct_capsule_binding = {
        "capsule_id": capsule["capsule_id"],
        "capsule_path": capsule_path,
        "capsule_sha256": capsule["capsule_sha256"],
    }
    present_direct_fields = {key for key in direct_capsule_binding if key in lease}
    direct_binding_present = len(present_direct_fields) == len(direct_capsule_binding)
    proven_legacy_binding = (
        not present_direct_fields
        and snapshot.get("snapshot_schema") == LEASE_SNAPSHOT_SCHEMA
        and snapshot.get("provenance") == "legacy_pre_scope_gate"
        and (lease.get("scope_authorization") or {}).get("kind") == "legacy_recovery"
    )
    if (
        capsule.get("capsule_sha256") != snapshot.get("capsule_sha256")
        or (not direct_binding_present and not proven_legacy_binding)
        or any(
            lease.get(key) != expected
            for key, expected in direct_capsule_binding.items()
            if direct_binding_present
        )
        or capsule.get("allowed_paths") != lease.get("allowed_paths")
        or capsule.get("allowed_symbols") != lease.get("allowed_symbols")
        or capsule.get("exclusions") != lease.get("exclusions")
    ):
        raise PipelineError("Engineer continuation capsule/lease binding is missing or changed")
    pre_edit = exact_scope_precheck(state, slice_item, owner_id)
    authorization = lease.get("scope_authorization")
    snapshot_authorization = snapshot.get("scope_authorization")
    if (
        pre_edit is None
        or not isinstance(authorization, dict)
        or authorization != snapshot_authorization
        or authorization.get("receipt_sha256") != canonical_json_sha256(pre_edit)
        or authorization.get("slice_id") != slice_item.get("id")
        or authorization.get("owner_id") != owner_id
        or authorization.get("base_revision") != state.get("revision")
        or not isinstance(snapshot.get("checkout"), dict)
        or authorization.get("diff_base_checkout_sha256")
        != checkout_snapshot_sha256(snapshot["checkout"])
        or not isinstance(snapshot.get("authorization_checkout"), dict)
        or authorization.get("checkout_snapshot_sha256")
        != checkout_snapshot_sha256(snapshot["authorization_checkout"])
    ):
        raise PipelineError("Engineer continuation scope receipt/lease binding is missing or changed")
    receipt: dict[str, Any] = {
        "kind": authorization.get("kind"),
        "id": authorization.get("recovery_receipt_id"),
        "path": None,
        "sha256": authorization.get("receipt_sha256"),
        "checkout_snapshot_sha256": authorization.get("checkout_snapshot_sha256"),
    }
    if authorization.get("kind") == "legacy_recovery":
        recovery = next(
            (
                item
                for item in state.get("legacy_scope_recoveries", [])
                if item.get("receipt_id") == authorization.get("recovery_receipt_id")
            ),
            None,
        )
        if (
            not isinstance(recovery, dict)
            or recovery.get("lease_id") != lease["lease_id"]
            or recovery.get("sha256") != authorization.get("recovery_receipt_sha256")
        ):
            raise PipelineError("Engineer continuation legacy recovery receipt is missing or changed")
        receipt.update(
            {"path": recovery.get("path"), "file_sha256": recovery.get("sha256")}
        )
    handoff = {
        "action": "dispatch_engineer",
        "role": "engineer",
        "worker_id": owner_id,
        "phase": state["phase"],
        "slice_id": slice_item["id"],
        "capsule_path": capsule_path,
        "lease_id": lease["lease_id"],
        "stop_condition": capsule["stop_condition"],
    }
    return {
        "status": status,
        "phase": state["phase"],
        "owner_id": owner_id,
        "slice_id": slice_item["id"],
        "revision": state["revision"],
        "scope_receipt": receipt,
        "capsule": {
            "id": capsule["capsule_id"],
            "path": capsule_path,
            "sha256": file_sha256(root / capsule_path),
            "capsule_sha256": capsule["capsule_sha256"],
        },
        "lease": {
            "id": lease["lease_id"],
            "path": None,
            "sha256": canonical_json_sha256(lease),
            "status": lease["status"],
        },
        "next_action": handoff,
        "handoff": handoff,
    }


def cmd_prepare_engineer_continuation(args: argparse.Namespace) -> int:
    """Prepare the exact Engineer boundary as one controller-owned operation."""
    root, state_path, findings_path = runtime_paths(args.project_root)
    raw_state = read_json(state_path)
    raw_lease = raw_state.get("active_write_lease")
    allow_candidate = isinstance(raw_lease, dict) and raw_lease.get("role") == "engineer"
    root, state_path, findings_path, state, findings = load_runtime(
        args.project_root,
        allow_active_writer_completion_drift=allow_candidate,
    )
    require_sources_current(state)
    if state.get("phase") not in {"slice_engineering", "engineering"}:
        raise PipelineError(
            "prepare-engineer-continuation requires slice_engineering or engineering"
        )
    if state.get("pending_engineer_completion") is not None:
        raise PipelineError("Engineer continuation is blocked by pending Engineer completion")
    if state.get("iteration_control", {}).get("status") == "checkpoint_required":
        raise PipelineError("Engineer continuation is blocked by the iteration checkpoint")
    slice_item = scope_slice_for_pass(state, None)
    lease = state.get("active_write_lease")
    lease_owner = (
        lease.get("worker_id")
        if isinstance(lease, dict) and lease.get("role") == "engineer"
        else None
    )
    owner_id = (
        state.get("engineering_owner_id")
        or slice_item.get("owner_id")
        or state.get("owner_by_slice", {}).get(slice_item["id"])
        or lease_owner
        or state.get("integration_owner")
    )
    if not isinstance(owner_id, str) or not owner_id:
        raise PipelineError(
            "Engineer continuation requires an existing Engineer/integration owner identity"
        )
    if owner_id in state.get("exhausted_worker_ids", []):
        raise PipelineError(
            "Engineer continuation requires transfer to a fresh non-exhausted identity"
        )
    state["engineering_owner_id"] = owner_id
    state["owner_by_slice"][slice_item["id"]] = owner_id
    slice_item["owner_id"] = owner_id
    if state.get("integration_owner") is None:
        state["integration_owner"] = owner_id
    materialize_pending_lifecycle_projection_receipt(root, state)
    route = next_action(state, findings)
    allowed_routes = {
        "run_slice_scope_check",
        "resume_engineering_owner",
        "recover_legacy_engineer_scope_authorization",
    }
    if route.get("action") not in allowed_routes or route.get("user_input_required"):
        label = (
            "budget checkpoint"
            if route.get("action") == "director_budget_checkpoint"
            else str(route.get("action"))
        )
        raise PipelineError(
            "Engineer continuation is blocked by higher-priority next_action: "
            + label
        )
    if isinstance(lease, dict):
        authorization = lease.get("scope_authorization")
        if not isinstance(authorization, dict) or not authorization.get("receipt_sha256"):
            recovery_args = argparse.Namespace(
                project_root=args.project_root,
                lease_id=lease.get("lease_id"),
                owner_id=owner_id,
                slice_id=slice_item["id"],
            )
            with contextlib.redirect_stdout(io.StringIO()):
                cmd_recover_legacy_engineer_scope(recovery_args)
            root, _, _, state, findings = load_runtime(
                args.project_root, allow_active_writer_completion_drift=True
            )
            slice_item = scope_slice_for_pass(state, None)
        payload = validated_engineer_continuation_payload(
            root, state, slice_item, owner_id, status="already_prepared"
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    current_checkout = checkout_snapshot(root, state["feature"], state)
    current_checkout_sha = checkout_snapshot_sha256(current_checkout)
    carried = state.get("scope_guard", {}).get("rebaseline_candidate")
    if carried and (
        carried.get("slice_id") != slice_item["id"]
        or state.get("phase") not in {"slice_engineering", "engineering"}
        or not isinstance(carried.get("base_revisions"), dict)
        or not isinstance(carried.get("snapshot"), dict)
        or not isinstance(carried["snapshot"].get("checkout"), dict)
        or not isinstance(carried["snapshot"].get("line_proofs"), dict)
        or carried["snapshot"].get("snapshot_schema") != LEASE_SNAPSHOT_SCHEMA
    ):
        raise PipelineError(
            "A rebaselined candidate requires the next fresh lease for its exact Engineer scope"
        )
    pre_edit = exact_scope_precheck(state, slice_item, owner_id)
    if pre_edit is None or pre_edit.get("checkout_snapshot_sha256") != current_checkout_sha:
        pre_edit = {
            "slice_id": slice_item["id"],
            "owner_id": owner_id,
            "base_revision": state["revision"],
            "development_plan_sha256": state["development_plan_sha256"],
            "scope_contract": slice_item["scope_contract"],
            "checkout_snapshot_sha256": current_checkout_sha,
            "status": "passed",
            "recorded_at": utc_now(),
        }

    capsule_path, capsule_relative, capsule = engineer_continuation_artifact(
        root, state, slice_item, owner_id
    )
    recorded = next(
        (
            item
            for item in state["context_capsules"]
            if item.get("path") == capsule_relative
        ),
        None,
    )
    capsule_record: dict[str, Any]
    if recorded is not None:
        if not capsule_path.exists():
            raise PipelineError("Recorded Engineer continuation capsule artifact is missing")
        existing = read_json(capsule_path)
        validate_capsule_value(root, state, existing)
        if (
            existing != capsule
            or recorded.get("sha256") != file_sha256(capsule_path)
            or recorded.get("capsule_sha256") != existing.get("capsule_sha256")
        ):
            raise PipelineError("Recorded Engineer continuation capsule is stale or changed")
        capsule = existing
        capsule_record = recorded
    else:
        if capsule_path.exists():
            orphan = read_json(capsule_path)
            if orphan != capsule:
                raise PipelineError("Engineer continuation capsule path is already occupied")
        capsule_record = {
            "capsule_id": capsule["capsule_id"],
            "path": capsule_relative,
            "sha256": "",
            "capsule_sha256": capsule["capsule_sha256"],
            "role": "engineer",
            "phase": state["phase"],
            "worker_id": owner_id,
            "revision": state["revision"],
            "metrics": capsule["metrics"],
            "created_at": utc_now(),
        }
        state["context_capsules"].append(capsule_record)

    slice_item["scope_pre_edit_check"] = pre_edit
    slice_item["scope_history"].append({"event": "pre_edit_check", **pre_edit})
    state["scope_guard"]["status"] = "edit_authorized"
    state["scope_guard"]["history"].append({"event": "pre_edit_check", **pre_edit})
    lease_checkout = carried["snapshot"]["checkout"] if carried else current_checkout
    scope_authorization = {
        "kind": "pre_edit_check",
        "receipt_sha256": canonical_json_sha256(pre_edit),
        "slice_id": slice_item["id"],
        "owner_id": owner_id,
        "base_revision": state["revision"],
        "checkout_snapshot_sha256": current_checkout_sha,
        "diff_base_checkout_sha256": checkout_snapshot_sha256(lease_checkout),
    }
    lease_id = f"LEASE-{len(state['write_lease_history']) + 1:04d}"
    lease = {
        "lease_id": lease_id,
        "phase": state["phase"],
        "write_scope": slice_item["id"],
        "role": "engineer",
        "worker_id": owner_id,
        "base_revision": (
            carried["base_revisions"]["revision"] if carried else state["revision"]
        ),
        "allowed_paths": capsule["allowed_paths"],
        "allowed_symbols": capsule["allowed_symbols"],
        "exclusions": capsule["exclusions"],
        "status": "active",
        "rebaseline_carried": bool(carried),
        "scope_authorization": scope_authorization,
        "capsule_id": capsule["capsule_id"],
        "capsule_path": capsule_relative,
        "capsule_sha256": capsule["capsule_sha256"],
    }
    state["active_write_lease"] = lease
    capsule_path.parent.mkdir(parents=True, exist_ok=True)
    if not capsule_path.exists():
        write_json(capsule_path, capsule)
    capsule_file_sha = file_sha256(capsule_path)
    capsule_record["sha256"] = capsule_file_sha
    # The artifact is outside the source projection. Re-capture the exact edit
    # boundary after its write and bind digest-only line proofs for allowed sources.
    lease_snapshot = build_lease_snapshot(
        root,
        state,
        capsule_path=capsule_relative,
        capsule_sha256=capsule["capsule_sha256"],
        allowed_paths=capsule["allowed_paths"],
        authorization_checkout=current_checkout,
        checkout=lease_checkout,
        inherited_line_proofs=(
            carried["snapshot"].get("line_proofs") if carried else None
        ),
        rebaseline_carried=bool(carried),
        scope_authorization=scope_authorization,
    )
    state["lease_snapshots"][lease_id] = lease_snapshot
    final_checkout = checkout_snapshot(root, state["feature"], state)
    boundary_changes = changed_checkout_paths(current_checkout, final_checkout)
    if boundary_changes:
        raise PipelineError(
            "Checkout changed while preparing Engineer continuation: "
            + ", ".join(boundary_changes)
        )
    computed = snapshot_revisions(state, final_checkout)
    stale = [
        key
        for key in ("revision", "product_revision", "support_revision", "evidence_revision")
        if computed[key] != state.get(key)
    ]
    if stale:
        raise PipelineError(
            "Controller revision inventory changed while preparing Engineer continuation: "
            + ", ".join(stale)
        )
    save_runtime(state_path, findings_path, state, findings)
    payload = validated_engineer_continuation_payload(
        root, state, slice_item, owner_id, status="prepared"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
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
    research_contract = state["plan_contracts"]["slices"][args.slice_id]["research"]
    if research_contract.get("mode") != "required":
        raise PipelineError("Approved plan marks this slice research_not_required")
    expected_brief_ids = [item["brief_id"] for item in research_contract["briefs"]]
    if len(bundle_paths) != len(expected_brief_ids):
        raise PipelineError(
            "Slice research bundle count must equal the exact approved Research Brief set"
        )
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
    if set(brief_ids) != set(expected_brief_ids):
        raise PipelineError("Research bundle IDs must equal the exact approved Research Brief set")
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
    state["phase"] = "slice_coverage_planning"
    save_runtime(state_path, findings_path, state, findings)
    return render_status(args, state, findings)


def parse_resume_actions(
    values: list[str] | None, capabilities: dict[str, str]
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for value in values or []:
        if "=" not in value:
            raise PipelineError(
                "Minimum resume actions must use "
                "<capability>=<owner>|<user_input_required>|<action>"
            )
        name, contract = value.split("=", 1)
        name = name.strip()
        try:
            parsed_name = _capability_contract.require_capability_id(
                name, label="minimum resume capability"
            )
        except ValueError as exc:
            raise PipelineError(str(exc)) from exc
        if parsed_name not in capabilities or parsed_name in result:
            raise PipelineError(f"Invalid minimum resume action: {value!r}")
        parts = [item.strip() for item in contract.split("|", 2)]
        if len(parts) != 3 or parts[0] not in {"user", "technical_director"}:
            raise PipelineError(
                "Minimum resume action owner must be user or technical_director"
            )
        if parts[1] not in {"true", "false"} or not parts[2]:
            raise PipelineError(
                "Minimum resume action requires exact boolean and non-empty action"
            )
        user_input_required = parts[1] == "true"
        status = capabilities[parsed_name]
        expected_owner = "user" if status == "blocked_user" else "technical_director"
        expected_user_input = status == "blocked_user"
        if status not in QA_CAPABILITY_BLOCKING_STATUSES:
            raise PipelineError(
                f"Minimum resume action is valid only for a blocked capability: {parsed_name}"
            )
        if parts[0] != expected_owner or user_input_required != expected_user_input:
            raise PipelineError(
                f"Minimum resume action authority conflicts with {parsed_name}={status}"
            )
        result[parsed_name] = {
            "owner": parts[0],
            "user_input_required": user_input_required,
            "action": parts[2],
        }
    return result


def cmd_qa_capability_probe(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    require_current_revision(state, args.revision)
    if state["phase"] != "qa":
        raise PipelineError("QA capability probe is valid only immediately before or during QA")
    report = resolve_report(root, state, args.report, "QA capability probe report")
    capabilities = parse_capabilities(args.capability)
    required_capabilities = required_qa_capabilities(root, state)
    missing = sorted(required_capabilities - set(capabilities))
    extra = sorted(set(capabilities) - required_capabilities)
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
    resume_actions = parse_resume_actions(args.minimum_resume_action, capabilities)
    blocked = {
        name: status
        for name, status in capabilities.items()
        if status in QA_CAPABILITY_BLOCKING_STATUSES
    }
    missing_actions = sorted(set(blocked) - set(resume_actions))
    extra_actions = sorted(set(resume_actions) - set(blocked))
    if missing_actions or extra_actions:
        raise PipelineError(
            "QA minimum resume actions must exactly match blocked capabilities: "
            + "; ".join(
                part
                for part in (
                    "missing=" + ",".join(missing_actions) if missing_actions else "",
                    "unexpected=" + ",".join(extra_actions) if extra_actions else "",
                )
                if part
            )
        )
    capability_state = state["qa_capability"]
    if any(probe["probe_id"] == args.probe_id for probe in capability_state["probes"]):
        raise PipelineError(f"QA capability probe ID already recorded: {args.probe_id}")
    probe = {
        "probe_id": args.probe_id,
        "revision": args.revision,
        "capabilities": capabilities,
        "capability_dimensions": {
            name: (
                "authorization"
                if status == "blocked_user"
                else "environment"
                if status == "blocked_environment"
                else "operator"
                if status == "planned_manual"
                else "executed"
                if status == "available"
                else "not_required"
                if status == "not_required"
                else "test_execution"
            )
            for name, status in capabilities.items()
        },
        "minimum_resume_actions": resume_actions,
        "report": report,
        "report_sha256": file_sha256(root / report),
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
            "capability_dimensions": probe["capability_dimensions"],
            "minimum_resume_actions": resume_actions,
            "report": report,
            "report_sha256": probe["report_sha256"],
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
    return render_status(args, state, findings)


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
    research_contract = state["plan_contracts"]["slices"][args.slice_id]["research"]
    if research_contract.get("mode") != "not_required":
        raise PipelineError("Approved plan requires exact Research Brief completion")
    if args.reason != research_contract.get("reason"):
        raise PipelineError(
            "research_not_required reason must equal the exact approved plan reason"
        )
    active["research"] = {
        "status": "not_required",
        "base_revision": args.base_revision,
        "bundles": [],
        "reason": args.reason,
        "completed_at": utc_now(),
    }
    state["phase"] = "slice_coverage_planning"
    save_runtime(state_path, findings_path, state, findings)
    return render_status(args, state, findings)


def coverage_state_from_validation(
    manifest_path: str, manifest: dict[str, Any], validation: dict[str, Any]
) -> dict[str, Any]:
    result = {
        "status": "finalized" if manifest["mode"] in {"finalized", "qa_updated"} else "planned",
        "manifest_path": manifest_path,
        "manifest_sha256": file_sha256(Path(manifest_path)),
        "ac_mapped": validation["summary"]["ac_mapped"],
        "identities_registered": validation["summary"]["identities_registered"],
        "mandatory_registration": (
            "complete" if validation["mandatory_registration_ok"] else "mismatch"
        ),
        "automated": validation["summary"]["automated"],
        "manual": validation["summary"]["manual"],
        "implementation_eligible": validation["summary"]["implementation_eligible"],
        "feature_verification_eligible": validation["summary"]["feature_verification_eligible"],
        "readiness_class": (
            None if validation["summary"]["implementation_eligible"] else "EVIDENCE_CONTRACT_VIOLATION"
        ),
        "gaps": validation["gaps"],
        "expected_identity_ids": validation["expected_ids"],
        "actual_identity_ids": validation["actual_ids"],
        "mandatory_expected_identity_ids": validation["mandatory_expected_ids"],
        "mandatory_actual_identity_ids": validation["mandatory_actual_ids"],
    }
    if validation.get("untested_identity_ids"):
        result["untested_identity_ids"] = validation["untested_identity_ids"]
    return result


def cmd_coverage_plan_complete(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    report = resolve_report(root, state, args.report, "Coverage planning report")
    manifest_path = resolve_report(
        root, state, args.coverage_manifest, "Coverage planned manifest"
    )
    request_sha256 = command_request_sha256(
        root,
        "coverage-plan-complete",
        {"slice_id": args.slice_id},
        {"coverage_manifest": manifest_path, "report": report},
    )
    prior = (state.get("coverage", {}).get(args.slice_id) or {}).get(
        "planned_manifest"
    )
    if prior and exact_lost_response_replay(
        prior, request_sha256, "coverage-plan-complete"
    ):
        return render_status(args, state, findings)
    if state.get("phase") != "slice_coverage_planning":
        raise PipelineError("coverage-plan-complete requires slice_coverage_planning")
    if args.slice_id != state.get("active_slice"):
        raise PipelineError("Coverage planning must target the active slice")
    manifest = read_json(Path(manifest_path))
    if manifest.get("mode") != "planned":
        raise PipelineError("coverage-plan-complete requires mode planned")
    validation = validate_coverage_manifest(
        root, state, manifest, scope_id=args.slice_id, require_finalized=False
    )
    scope = state["coverage"][args.slice_id]
    scope["planned_manifest"] = {
        "path": manifest_path,
        "sha256": file_sha256(Path(manifest_path)),
        "revision": state["revision"],
        "plan_body_digest": coverage_plan_body_digest(manifest),
        "amendments": list(manifest["amendments"]),
        "report": report,
        "report_sha256": file_sha256(Path(report)),
        "request_sha256": request_sha256,
    }
    scope["state"] = coverage_state_from_validation(manifest_path, manifest, validation)
    state["implementation_state"]["status"] = "in_progress"
    state["phase"] = "slice_engineering"
    save_runtime(state_path, findings_path, state, findings)
    return render_status(args, state, findings)


def generate_schema2_handoff(
    root: Path,
    state: dict[str, Any],
    pending: dict[str, Any],
    coverage_record: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    index = len(state["handoffs"]) + 1
    handoff_id = f"HANDOFF-{index:04d}"
    output = root / "tests" / state["feature"] / "verification" / "controller" / f"{handoff_id}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    assumptions = pending.get("open_assumptions", [])
    for item in assumptions:
        if not isinstance(item, dict) or set(item) != {
            "assumption_id",
            "statement",
            "owner",
            "validation_point",
            "impact_if_false",
        } or any(not item[field] for field in item):
            raise PipelineError("Semantic handoff open_assumptions must use the exact schema")
    value: dict[str, Any] = {
        "schema": 2,
        "handoff_id": handoff_id,
        "phase": pending["phase"],
        "writer_role": pending["writer_role"],
        "writer_id": pending["writer_id"],
        "lease_id": pending["lease_id"],
        "slice_id": pending["slice_id"],
        "base_revisions": pending["base_revisions"],
        "result_revisions": pending["result_revisions"],
        "change_manifest_path": pending["change_manifest"],
        "diff_summary_path": pending["diff_summary"],
        "semantic_report_path": pending["semantic_report"],
        "decision_ids": list(state["decision_ledger"]["active_decision_ids"]),
        "coverage_state": {
            "manifest_path": coverage_record["manifest_path"],
            "manifest_sha256": coverage_record["manifest_sha256"],
            "ac_mapped": coverage_record["ac_mapped"],
            "identities_registered": coverage_record["identities_registered"],
            "automated": coverage_record["automated"],
            "manual": coverage_record["manual"],
        },
        "documentation_state": {
            "normative": state["documentation"]["normative"]["status"],
            "derived": state["documentation"]["derived"]["status"],
        },
        "open_assumptions": assumptions,
        "generated_at": utc_now(),
        "handoff_sha256": "",
    }
    value["handoff_sha256"] = canonical_json_sha256(
        {key: item for key, item in value.items() if key != "handoff_sha256"}
    )
    write_json(output, value)
    return output.relative_to(root).as_posix(), value


def coverage_summary_for_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    expected = {item["identity_id"]: item for item in manifest["expected_identities"]}
    actual = {item["identity_id"]: item for item in manifest["actual_identities"]}
    mandatory_expected = set(manifest["mandatory_expected_identity_ids"])
    mandatory_actual = set(manifest["mandatory_actual_identity_ids"])
    auto = {item["identity_id"]: item for item in manifest["automated_execution"]}
    manual = {item["identity_id"]: item for item in manifest["manual_execution"]}
    deferred_automated = sorted(
        identity_id
        for identity_id, row in auto.items()
        if row.get("outcome") in {"infra_unavailable", "manual_required"}
    )
    product_failed_automated = {
        identity_id
        for identity_id, row in auto.items()
        if row.get("outcome") == "product_failed"
    }
    automated_ok = all(
        (
            auto.get(identity_id, {}).get("executed") is True
            and auto.get(identity_id, {}).get("passed") is True
        )
        or auto.get(identity_id, {}).get("outcome")
        in {"infra_unavailable", "manual_required"}
        for identity_id in mandatory_actual
        if actual.get(identity_id, {}).get("kind") == "automated"
    ) and not product_failed_automated
    mandatory_manual = {
        identity_id
        for identity_id in mandatory_actual
        if actual.get(identity_id, {}).get("kind") == "manual"
    }
    manual_ok = all(
        manual.get(identity_id, {}).get("executed") is True
        and manual.get(identity_id, {}).get("passed") is True
        and manual.get(identity_id, {}).get("deferred") is False
        and not manual.get(identity_id, {}).get("blocked_by_finding")
        for identity_id in mandatory_manual
    )
    mapped = all(item["status"] != "gap" for item in manifest["ac_mappings"])
    registration = set(expected) == set(actual) and all(
        expected[key] == actual[key] for key in expected.keys() & actual.keys()
    )
    mandatory_registration = (
        mandatory_expected == mandatory_actual
        == {key for key, item in actual.items() if item["mandatory"]}
        == {key for key, item in expected.items() if item["mandatory"]}
    )
    implementation = (
        mapped
        and registration
        and mandatory_registration
        and not manifest["gaps"]
        and automated_ok
    )
    result = {
        "ac_mapped": mapped,
        "identities_registered": "complete" if registration else "mismatch",
        "expected_count": len(expected),
        "actual_count": len(actual),
        "mandatory_expected_count": len(mandatory_expected),
        "mandatory_actual_count": len(mandatory_actual),
        "automated": (
            "deferred" if deferred_automated and automated_ok
            else "passed" if automated_ok
            else "pending"
        ),
        "manual": "passed" if manual_ok else (
            "deferred" if any(item["deferred"] for item in manual.values()) else "pending"
        ),
        "implementation_eligible": implementation,
        "feature_verification_eligible": implementation and manual_ok,
    }
    if deferred_automated:
        result["untested_identity_ids"] = deferred_automated
    return result


def write_feature_coverage_aggregate(
    root: Path,
    state: dict[str, Any],
    *,
    mode: str = "finalized",
    manual_execution: list[dict[str, Any]] | None = None,
    suffix: str = "finalized",
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    feature_record = state.get("coverage", {}).get("feature", {}).get("finalized_manifest")
    if mode == "qa_updated" and feature_record:
        path = Path(feature_record["path"])
        if not path.is_file() or file_sha256(path) != feature_record["sha256"]:
            raise PipelineError("Finalized feature coverage drifted before QA aggregation")
        manifests.append(read_json(path))
    else:
        for scope_id in state["ordered_slices"]:
            record = state["coverage"][scope_id].get("finalized_manifest")
            if not record:
                raise PipelineError(f"Feature coverage aggregate lacks finalized scope {scope_id}")
            path = Path(record["path"])
            if not path.is_file() or file_sha256(path) != record["sha256"]:
                raise PipelineError(f"Finalized slice coverage drifted for {scope_id}")
            manifests.append(read_json(path))
    merged: dict[str, list[Any]] = {
        key: []
        for key in (
            "ac_mappings",
            "expected_identities",
            "actual_identities",
            "mandatory_expected_identity_ids",
            "mandatory_actual_identity_ids",
            "automated_execution",
            "manual_execution",
            "amendments",
            "gaps",
        )
    }
    mappings_by_acceptance: dict[str, list[dict[str, Any]]] = {}
    for manifest in manifests:
        for mapping in manifest["ac_mappings"]:
            mappings_by_acceptance.setdefault(mapping["acceptance_id"], []).append(mapping)
        for key in merged:
            if key != "ac_mappings":
                merged[key].extend(manifest[key])
    for acceptance_id, mappings in sorted(mappings_by_acceptance.items()):
        statuses = {item["status"] for item in mappings}
        authorities = {item["authority_id"] for item in mappings}
        if statuses == {"not_applicable"}:
            if len(authorities) != 1:
                raise PipelineError(
                    f"Feature coverage not_applicable authority disagrees for {acceptance_id}"
                )
            status = "not_applicable"
            authority_id = next(iter(authorities))
        elif "not_applicable" in statuses:
            raise PipelineError(
                f"Feature coverage mixes not_applicable with mapped/gap for {acceptance_id}"
            )
        else:
            status = "gap" if "gap" in statuses else "mapped"
            authority_id = None
        merged["ac_mappings"].append(
            {
                "acceptance_id": acceptance_id,
                "status": status,
                "identity_ids": sorted(
                    {
                        identity_id
                        for mapping in mappings
                        for identity_id in mapping["identity_ids"]
                    }
                ),
                "authority_id": authority_id,
            }
        )
    if manual_execution is not None:
        merged["manual_execution"] = manual_execution
    value = {
        "schema": 2,
        "feature": state["feature"],
        "slice_id": "feature",
        "mode": mode,
        "authority": {
            "plan_path": Path(state["development_plan_path"])
            .resolve()
            .relative_to(root)
            .as_posix(),
            "plan_sha256": state["development_plan_sha256"],
            "prd_path": Path(state["requirements_path"]).resolve().relative_to(root).as_posix(),
            "prd_sha256": state["requirements_sha256"],
            "spec_path": Path(state["spec_path"]).resolve().relative_to(root).as_posix(),
            "spec_sha256": state["spec_sha256"],
        },
        "revisions": {
            key: state[key]
            for key in ("revision", "product_revision", "support_revision", "evidence_revision")
        },
        **merged,
        "summary": {},
    }
    value["summary"] = coverage_summary_for_manifest(value)
    controller_root = root / "tests" / state["feature"] / "verification" / "controller"
    controller_root.mkdir(parents=True, exist_ok=True)
    controller_root.mkdir(parents=True, exist_ok=True)
    path = controller_root / f"coverage-feature-{suffix}.json"
    write_json(path, value)
    validation = validate_coverage_manifest(
        root, state, value, scope_id="feature", require_finalized=True
    )
    relative = path.relative_to(root).as_posix()
    coverage_state = coverage_state_from_validation(str(path), value, validation)
    coverage_state.update(
        {
            "revision": state["revision"],
            "product_revision": state["product_revision"],
            "support_revision": state["support_revision"],
            "evidence_revision": state["evidence_revision"],
        }
    )
    return relative, value, coverage_state


def cmd_coverage_finalize(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    report = resolve_report(root, state, args.report, "Coverage finalization report")
    manifest_path = resolve_report(
        root, state, args.coverage_manifest, "Coverage finalized manifest"
    )
    request_sha256 = command_request_sha256(
        root,
        "coverage-finalize",
        {
            "scope_id": args.scope_id,
            "expected_actual_equality": args.expected_actual_equality,
            "mandatory_registration": args.mandatory_registration,
            "automated_execution": args.automated_execution,
        },
        {"coverage_manifest": manifest_path, "report": report},
    )
    prior_finalized = (state.get("coverage", {}).get(args.scope_id) or {}).get(
        "finalized_manifest"
    )
    if (
        prior_finalized
        and prior_finalized.get("revision") == state.get("revision")
        and exact_lost_response_replay(
            prior_finalized, request_sha256, "coverage-finalize"
        )
    ):
        return render_status(args, state, findings)
    expected_phase = (
        "slice_coverage_finalization" if args.scope_id != "feature" else "coverage_finalization"
    )
    if state.get("phase") != expected_phase:
        raise PipelineError(f"coverage-finalize requires {expected_phase}")
    manifest = read_json(Path(manifest_path))
    if manifest.get("mode") != "finalized":
        raise PipelineError("coverage-finalize requires mode finalized")
    validation = validate_coverage_manifest(
        root, state, manifest, scope_id=args.scope_id, require_finalized=True
    )
    scope = state["coverage"].setdefault(args.scope_id, empty_coverage_scope())
    planned_record = scope.get("planned_manifest") or (
        scope.get("finalized_manifest") if args.scope_id == "feature" else None
    )
    if not planned_record:
        raise PipelineError("Coverage finalization requires its controller-recorded planned manifest")
    planned_path = Path(planned_record["path"])
    if not planned_path.is_file() or file_sha256(planned_path) != planned_record["sha256"]:
        raise PipelineError("Planned coverage manifest drifted before finalization")
    planned_manifest = read_json(planned_path)
    final_plan_digest = validate_coverage_continuity(
        state,
        findings,
        planned_manifest,
        manifest,
    )
    record = coverage_state_from_validation(manifest_path, manifest, validation)
    record.update(
        {
            "report": report,
            "plan_body_digest": final_plan_digest,
            "revision": state["revision"],
            "product_revision": state["product_revision"],
            "support_revision": state["support_revision"],
            "evidence_revision": state["evidence_revision"],
        }
    )
    scope["finalized_manifest"] = {
        "path": manifest_path,
        "sha256": file_sha256(Path(manifest_path)),
        "revision": state["revision"],
        "report": report,
        "report_sha256": file_sha256(Path(report)),
        "request_sha256": request_sha256,
    }
    scope["state"] = record
    controller_assertions = (
        args.expected_actual_equality == "pass"
        and args.mandatory_registration == "pass"
        and (
            args.automated_execution == "pass"
            or (
                bool(validation.get("untested_identity_ids"))
                and not validation.get("product_failed_identity_ids")
            )
        )
    )
    eligible = validation["summary"]["implementation_eligible"] and controller_assertions
    if not eligible:
        record["readiness_class"] = "EVIDENCE_CONTRACT_VIOLATION"
        record["gaps"] = sorted(
            set(record["gaps"] + ["schema-2 registration/mapping/automated execution gate failed"])
        )
        state["implementation_state"]["status"] = "invalidated"
        save_runtime(state_path, findings_path, state, findings)
        raise PipelineError(
            "EVIDENCE_CONTRACT_VIOLATION: coverage does not satisfy exact AC, identity, "
            "mandatory-set, gap-free, and automated-pass requirements; no product finding was created"
        )
    pending = state.get("pending_engineer_completion")
    if not pending:
        raise PipelineError("Coverage finalization lacks controller-owned Engineer mechanics")
    validate_dirty_candidate_gate(root, pending)
    handoff_path, handoff = generate_schema2_handoff(root, state, pending, record)
    state["handoffs"].append(
        {
            "handoff_id": handoff["handoff_id"],
            "path": handoff_path,
            "sha256": file_sha256(root / handoff_path),
            "handoff_sha256": handoff["handoff_sha256"],
            "schema": 2,
            "recorded_at": utc_now(),
        }
    )
    state["handoff_manifests"].append(
        {
            "kind": "schema2_sealed",
            "slice_id": pending["slice_id"],
            "manifest": handoff_path,
            "recorded_at": utc_now(),
        }
    )
    if args.scope_id == "feature":
        state["implementation_state"] = {
            "status": "pass",
            "revision": state["revision"],
            "coverage_manifest": manifest_path,
        }
        state["phase"] = pending.get("post_coverage_phase", "convergence")
    else:
        slice_item = state["slices"][args.scope_id]
        slice_item["status"] = "sealed"
        slice_item["result_revision"] = state["revision"]
        slice_item["result_product_revision"] = state["product_revision"]
        slice_item["result_support_revision"] = state["support_revision"]
        slice_item["result_evidence_revision"] = state["evidence_revision"]
        slice_item["handoff_manifests"].append(handoff_path)
        slice_item["sealed_at"] = utc_now()
        current_index = state["ordered_slices"].index(args.scope_id)
        if current_index + 1 < len(state["ordered_slices"]):
            next_slice = state["ordered_slices"][current_index + 1]
            set_active_slice(
                state,
                next_slice,
                base_revision=state["revision"],
                base_product_revision=state["product_revision"],
                base_support_revision=state["support_revision"],
                base_evidence_revision=state["evidence_revision"],
            )
            state["phase"] = "slice_research"
        else:
            state["active_slice"] = None
            state["execution_stage"] = "feature_validation"
            aggregate_path, _, aggregate_state = write_feature_coverage_aggregate(
                root, state, suffix=f"implementation-{len(state['handoffs']) + 1:04d}"
            )
            aggregate_absolute = str(root / aggregate_path)
            state["coverage"]["feature"] = {
                "planned_manifest": None,
                "finalized_manifest": {
                    "path": aggregate_absolute,
                    "sha256": file_sha256(root / aggregate_path),
                    "revision": state["revision"],
                    "report": "controller:feature-coverage-aggregate",
                    "steward_id": "controller-aggregate",
                },
                "state": aggregate_state,
            }
            state["implementation_state"] = {
                "status": "pass",
                "revision": state["revision"],
                "coverage_manifest": aggregate_absolute,
            }
            state["phase"] = "implementation_complete"
    state["coverage_manifest"] = (
        state["coverage"].get("feature", {}).get("finalized_manifest", {}).get("path")
        or manifest_path
    )
    state["pending_engineer_completion"] = None
    save_runtime(state_path, findings_path, state, findings)
    return render_status(args, state, findings)


def cmd_slice_scope_check(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    if state.get("phase") not in {"slice_engineering", "engineering"}:
        raise PipelineError("slice-scope-check is valid only immediately before an Engineer edit pass")
    if state.get("scope_guard", {}).get("status") == "scope_expansion_hold":
        raise PipelineError("scope_expansion_hold requires user-approved plan rebaseline")
    if state.get("active_write_lease") is not None:
        raise PipelineError(
            "slice-scope-check must precede Engineer write lease acquisition"
        )
    slice_item = scope_slice_for_pass(state, args.slice_id)
    if args.base_revision != state.get("revision"):
        raise PipelineError("slice-scope-check base revision must match current pipeline revision")
    active_owner = state.get("engineering_owner_id") or slice_item.get("owner_id")
    if active_owner and active_owner != args.owner_id:
        raise PipelineError("slice-scope-check owner does not match the assigned Engineer")
    state["engineering_owner_id"] = args.owner_id
    state["owner_by_slice"][slice_item["id"]] = args.owner_id
    slice_item["owner_id"] = args.owner_id
    if state.get("integration_owner") is None:
        state["integration_owner"] = args.owner_id
    check = {
        "slice_id": slice_item["id"],
        "owner_id": args.owner_id,
        "base_revision": args.base_revision,
        "development_plan_sha256": state["development_plan_sha256"],
        "scope_contract": slice_item["scope_contract"],
        "checkout_snapshot_sha256": checkout_snapshot_sha256(
            checkout_snapshot(root, state["feature"], state)
        ),
        "status": "passed",
        "recorded_at": utc_now(),
    }
    slice_item["scope_pre_edit_check"] = check
    slice_item["scope_history"].append({"event": "pre_edit_check", **check})
    state["scope_guard"]["status"] = "edit_authorized"
    state["scope_guard"]["history"].append({"event": "pre_edit_check", **check})
    save_runtime(state_path, findings_path, state, findings)
    return render_status(args, state, findings)


def open_scope_expansion_hold(
    state: dict[str, Any],
    slice_item: dict[str, Any],
    violations: list[str],
    *,
    lease: dict[str, Any],
    inventory: dict[str, list[str]],
    changes: list[dict[str, Any]],
    diff_files: list[dict[str, Any]],
    semantic_report: str,
    engineer_report: str,
    run_id: str,
) -> None:
    previous_phase = state["phase"]
    hold = {
        "slice_id": slice_item["id"],
        "base_revision": state.get("revision"),
        "development_plan_sha256": state.get("development_plan_sha256"),
        "violations": violations,
        "resume_phase": previous_phase,
        "lease_id": lease["lease_id"],
        "candidate_paths": sorted(item["path"] for item in changes),
        "candidate_inventory": inventory,
        "candidate_changes": changes,
        "candidate_diff_files": diff_files,
        "semantic_report": semantic_report,
        "engineer_report": engineer_report,
        "run_id": run_id,
        "base_revisions": {
            "revision": state["revision"],
            "product_revision": state["product_revision"],
            "support_revision": state["support_revision"],
            "evidence_revision": state["evidence_revision"],
        },
        "snapshot_sha256": canonical_json_sha256(
            state["lease_snapshots"][lease["lease_id"]]["checkout"]
        ),
        "opened_at": utc_now(),
    }
    state["phase"] = "scope_expansion_hold"
    state["scope_guard"]["status"] = "scope_expansion_hold"
    state["scope_guard"]["hold"] = hold
    state["scope_guard"]["history"].append({"event": "scope_expansion_hold", **hold})
    slice_item["scope_history"].append({"event": "scope_expansion_hold", **hold})


def cmd_rebaseline_scope(args: argparse.Namespace) -> int:
    _, raw_state_path, _ = runtime_paths(args.project_root)
    raw_phase = read_json(raw_state_path).get("phase")
    root, state_path, findings_path, state, findings = load_runtime(
        args.project_root,
        allow_active_writer_completion_drift=(raw_phase == "scope_expansion_hold"),
    )
    request_sha256 = command_request_sha256(
        root,
        "rebaseline-scope",
        {
            "plan_sha256": args.plan_sha256,
            "user_scope_approval": args.user_scope_approval,
        },
        {"plan": state["development_plan_path"]},
    )
    if state.get("phase") != "scope_expansion_hold":
        prior = next(
            iter(reversed(state.get("scope_guard", {}).get("rebaseline_history", []))),
            None,
        )
        if exact_lost_response_replay(prior, request_sha256, "scope rebaseline"):
            return render_status(args, state, findings)
        raise PipelineError("rebaseline-scope requires an open scope_expansion_hold")
    hold = state["scope_guard"]["hold"]
    lease = state.get("active_write_lease")
    if not lease or lease.get("lease_id") != hold.get("lease_id"):
        raise PipelineError("Scope hold lost its exact active writer lease")
    requirements = resolve_project_file(root, state["requirements_path"], "Approved product requirements")
    spec = resolve_project_file(root, state["spec_path"], "Approved technical specification")
    _, _, prd_acceptance_inventory = require_feature_documents(
        root, state["feature"], requirements, spec
    )
    plan = require_development_plan(
        root,
        state["feature"],
        requirements,
        spec,
        state["development_plan_path"],
        args.plan_sha256,
        prd_acceptance_inventory,
    )
    if [item["id"] for item in plan["slices"]] != state["ordered_slices"]:
        raise PipelineError("Scope rebaseline cannot change approved slice ordering in-place")
    authority = next(
        (
            record
            for record in state["user_authorities"]
            if record["authority_id"] == args.user_scope_approval
        ),
        None,
    )
    expected_statement = scope_rebaseline_authority_statement(hold, plan["sha256"])
    if authority is None or authority["statement"] != expected_statement:
        raise PipelineError(
            "--user-scope-approval must name an immutable user authority receipt "
            "binding the exact hold fingerprint and approved plan SHA-256"
        )
    snapshot = state["lease_snapshots"].get(lease["lease_id"])
    if not snapshot or canonical_json_sha256(snapshot["checkout"]) != hold.get("snapshot_sha256"):
        raise PipelineError("Scope hold lease snapshot is missing or changed")
    current_paths = changed_checkout_paths(
        snapshot["checkout"], checkout_snapshot(root, state["feature"], state)
    )
    plan_relative = Path(state["development_plan_path"]).resolve().relative_to(root).as_posix()
    authority_receipt_relative = authority["receipt_path"]
    candidate_checkout_paths = sorted(
        path
        for path in current_paths
        if path not in {plan_relative, authority_receipt_relative}
    )
    if candidate_checkout_paths not in ([], hold["candidate_paths"]):
        raise PipelineError(
            "Scope hold checkout no longer matches either the preserved candidate or a recoverable rollback"
        )
    active_id = hold["slice_id"]
    replacement = next(item for item in plan["slices"] if item["id"] == active_id)
    for item in plan["slices"]:
        prior = state["slices"][item["id"]]
        if prior.get("status") == "sealed" and (
            prior.get("scope_contract") != item["scope_contract"]
            or prior.get("requirement_ids") != item["requirement_ids"]
        ):
            raise PipelineError(
                f"Updated plan cannot rewrite the sealed scope contract for {item['id']}"
            )
    if candidate_checkout_paths:
        remaining = scope_violations(
            replacement,
            hold["candidate_changes"],
            hold["candidate_diff_files"],
            material_change_approved=True,
        )
        if remaining:
            raise PipelineError(
                "Updated plan still does not authorize the preserved candidate: "
                + "; ".join(remaining)
            )
    for item in plan["slices"]:
        state["slices"][item["id"]]["scope_contract"] = item["scope_contract"]
        state["slices"][item["id"]]["requirement_ids"] = item["requirement_ids"]
        state["slices"][item["id"]]["scope_pre_edit_check"] = None
    state["development_plan_sha256"] = plan["sha256"]
    state["plan_contracts"] = plan["contracts"]
    candidate: dict[str, Any] | None = None
    if candidate_checkout_paths:
        state["revision_inventory"] = hold["candidate_inventory"]
        computed = compute_inventory_revisions(root, state)
        candidate = {
            "slice_id": active_id,
            "prior_lease_id": lease["lease_id"],
            "snapshot": snapshot,
            "changes": hold["candidate_changes"],
            "diff_files": hold["candidate_diff_files"],
            "inventory": hold["candidate_inventory"],
            "base_revisions": hold["base_revisions"],
            "result_revisions": {
                key: computed[key]
                for key in ("revision", "product_revision", "support_revision", "evidence_revision")
            },
            "semantic_report": hold["semantic_report"],
            "engineer_report": hold["engineer_report"],
            "run_id": hold["run_id"],
        }
        for key in candidate["result_revisions"]:
            state[key] = candidate["result_revisions"][key]
        state["implementation_state"]["status"] = "invalidated"
        state["feature_verification_state"]["status"] = "invalidated"
    else:
        computed = compute_inventory_revisions(root, state)
        for key in ("revision", "product_revision", "support_revision", "evidence_revision"):
            state[key] = computed[key]
        state["implementation_state"]["status"] = "invalidated"
        state["feature_verification_state"]["status"] = "invalidated"
    release_active_lease(state, result="revoked", reason="approved_scope_rebaseline")
    event = {
        "event": "scope_rebaseline",
        "slice_id": active_id,
        "prior_plan_sha256": hold["development_plan_sha256"],
        "approved_plan_sha256": plan["sha256"],
        "baseline_revision": (
            candidate["base_revisions"]["revision"] if candidate else state.get("revision")
        ),
        "result_revision": state.get("revision"),
        "user_scope_approval": args.user_scope_approval,
        "user_scope_approval_sha256": authority["sha256"],
        "user_scope_approval_receipt": authority["receipt_path"],
        "user_scope_approval_receipt_sha256": authority["receipt_sha256"],
        "hold_sha256": scope_hold_sha256(hold),
        "request_sha256": request_sha256,
        "recorded_at": utc_now(),
    }
    state["scope_guard"]["history"].append(event)
    state["scope_guard"]["rebaseline_history"].append(event)
    state["scope_guard"]["hold"] = None
    state["scope_guard"]["status"] = "pending"
    state["scope_guard"]["rebaseline_candidate"] = candidate
    state["phase"] = hold["resume_phase"]
    save_runtime(state_path, findings_path, state, findings)
    return render_status(args, state, findings)


def assigned_goal_effect_reason_prefix(
    requirement_ids: set[str], acceptance_ids: set[str]
) -> str:
    assigned_ids = sorted(requirement_ids) + sorted(acceptance_ids)
    return f"{ASSIGNED_GOAL_EFFECT_PREFIX} {', '.join(assigned_ids)} |"




def validate_semantic_write_packet(
    root: Path,
    state: dict[str, Any],
    lease: dict[str, Any],
    packet: dict[str, Any],
    *,
    slice_item: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, list[str]], list[str]]:
    exact_fields = {"schema", "inventory_complete", "domain_inventory", "changes", "open_assumptions"}
    if set(packet) != exact_fields or packet.get("schema") != 1 or packet.get("inventory_complete") is not True:
        raise PipelineError(
            "Semantic write packet must use schema 1 and attest inventory_complete=true; "
            "the controller fails closed rather than guessing a partial domain inventory"
        )
    forbidden_mechanics = {
        "revision",
        "product_revision",
        "support_revision",
        "evidence_revision",
        "change_count",
        "line_count",
        "handoff_sha256",
    }
    if forbidden_mechanics.intersection(packet):
        raise PipelineError("Workers cannot supply controller-owned revision/change/handoff mechanics")
    inventory = packet.get("domain_inventory")
    if not isinstance(inventory, dict) or set(inventory) != {"product", "support", "evidence"}:
        raise PipelineError("Semantic packet domain_inventory must list product/support/evidence")
    normalized_inventory: dict[str, list[str]] = {}
    assigned: set[str] = set()
    for domain in ("product", "support", "evidence"):
        paths = require_string_list(inventory[domain], f"Semantic {domain} inventory")
        normalized = [scope_path(path, f"semantic {domain} inventory") for path in paths]
        if len(set(normalized)) != len(normalized):
            raise PipelineError(f"Semantic {domain} inventory contains duplicates")
        overlap = assigned.intersection(normalized)
        if overlap:
            raise PipelineError("Semantic domain inventory overlaps: " + ", ".join(sorted(overlap)))
        assigned.update(normalized)
        normalized_inventory[domain] = sorted(normalized)
    changes = packet.get("changes")
    if not isinstance(changes, list):
        raise PipelineError("Semantic packet changes must be a list")
    expected_change_fields = {
        "path",
        "domain",
        "symbols",
        "reason",
        "change_kind",
        "component",
        "lifecycle_change",
        "ownership_change",
        "public_contract_change",
        "requirement_ids",
        "acceptance_ids",
        "decision_ids",
        "touchpoint_id",
    }
    documentation_change_fields = expected_change_fields | {"change_id"}
    normalized_changes: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_change_ids: set[str] = set()
    role_domains = {
        "engineer": {"product", "evidence"},
        "documentation_finisher": (
            {"product"} if lease.get("phase") == "normative_documentation" else {"support"}
        ),
        "recovery_remediator": {"support", "evidence"},
    }
    allowed_domains = role_domains.get(lease.get("role"))
    if allowed_domains is None:
        raise PipelineError("The active lease role cannot submit a semantic write packet")
    approved_requirements = set(slice_item.get("requirement_ids", []))
    approved_acceptance = set(slice_item.get("scope_contract", {}).get("acceptance_ids", []))
    for change in changes:
        required_change_fields = (
            documentation_change_fields
            if lease.get("role") == "documentation_finisher"
            else expected_change_fields
        )
        if not isinstance(change, dict) or set(change) != required_change_fields:
            raise PipelineError("Every semantic change must use the exact controller annotation fields")
        item = dict(change)
        path = scope_path(item["path"], "semantic changed")
        if path in seen:
            raise PipelineError(f"Semantic packet repeats changed path: {path}")
        seen.add(path)
        item["path"] = path
        if lease.get("role") == "documentation_finisher":
            change_id = item.get("change_id")
            if (
                not isinstance(change_id, str)
                or re.fullmatch(r"DOC-CHG-[A-Za-z0-9._-]+", change_id) is None
                or change_id in seen_change_ids
            ):
                raise PipelineError(
                    "Documentation semantic changes require unique DOC-CHG-* change_id values"
                )
            seen_change_ids.add(change_id)
        if item["domain"] not in {"product", "support", "evidence"}:
            raise PipelineError(f"Semantic change {path} has invalid domain")
        if item["domain"] not in allowed_domains:
            raise PipelineError(
                f"{lease['role']} lease cannot change the {item['domain']} domain: {path}"
            )
        if item["change_kind"] == "delete":
            if path in normalized_inventory[item["domain"]]:
                raise PipelineError(f"Deleted path remains in {item['domain']} inventory: {path}")
        elif path not in normalized_inventory[item["domain"]]:
            raise PipelineError(f"Changed path is absent from {item['domain']} inventory: {path}")
        for field in ("symbols", "requirement_ids", "acceptance_ids", "decision_ids"):
            require_string_list(item[field], f"Semantic change {path} {field}")
        requirement_ids = set(item["requirement_ids"])
        acceptance_ids = set(item["acceptance_ids"])
        if not requirement_ids or not requirement_ids.issubset(approved_requirements):
            raise PipelineError(
                f"Semantic change {path} must map to an approved PRD-REQ subset for {slice_item['id']}"
            )
        if not acceptance_ids or not acceptance_ids.issubset(approved_acceptance):
            raise PipelineError(
                f"Semantic change {path} must map to an approved PRD-AC subset for {slice_item['id']}"
            )
        expected_reason_prefix = assigned_goal_effect_reason_prefix(
            requirement_ids, acceptance_ids
        )
        if (
            not isinstance(item["reason"], str)
            or not item["reason"].startswith(expected_reason_prefix)
            or not item["reason"][len(expected_reason_prefix) :].strip()
            or item["change_kind"] not in {"add", "modify", "delete"}
            or not isinstance(item["component"], str)
            or not item["component"].strip()
        ):
            raise PipelineError(
                f"Semantic change {path} must attest its assigned-ID effect as "
                f"'{expected_reason_prefix} <direct effect>' and supply change_kind/component; "
                "allowed paths alone do not authorize drive-by semantic changes"
            )
        if item["touchpoint_id"] is not None and (
            not isinstance(item["touchpoint_id"], str)
            or re.fullmatch(r"TP-\d{3}", item["touchpoint_id"]) is None
        ):
            raise PipelineError(f"Semantic change {path} touchpoint_id must be TP-NNN or null")
        for flag in ("lifecycle_change", "ownership_change", "public_contract_change"):
            if not isinstance(item[flag], bool):
                raise PipelineError(f"Semantic change {path} {flag} must be boolean")
        inactive = sorted(set(item["decision_ids"]) - set(state["decision_ledger"]["active_decision_ids"]))
        if inactive:
            raise PipelineError(f"Semantic change {path} cites inactive decisions: {', '.join(inactive)}")
        normalized_changes.append(item)
    snapshot_record = state["lease_snapshots"].get(lease["lease_id"], {})
    snapshot = snapshot_record.get("checkout")
    if not isinstance(snapshot, dict):
        raise PipelineError("Active lease snapshot is missing")
    if lease.get("rebaseline_carried") is True and state.get("scope_guard", {}).get(
        "rebaseline_candidate"
    ):
        authorization_checkout = snapshot_record.get("authorization_checkout")
        if not isinstance(authorization_checkout, dict):
            raise PipelineError("Carried rebaseline authorization checkout is missing")
        candidate_paths = {
            item["path"]
            for item in state["scope_guard"]["rebaseline_candidate"]["changes"]
        }
        snapshot = {
            **{
                path: digest
                for path, digest in authorization_checkout.items()
                if path not in candidate_paths
            },
            **snapshot,
        }
    actual_changed = changed_checkout_paths(
        snapshot, checkout_snapshot(root, state["feature"], state)
    )
    if lease.get("rebaseline_carried") is True and state.get("scope_guard", {}).get(
        "rebaseline_candidate"
    ):
        approved_plan_path = (
            Path(state["development_plan_path"]).resolve().relative_to(root).as_posix()
        )
        actual_changed = [path for path in actual_changed if path != approved_plan_path]
    if set(actual_changed) != seen:
        raise PipelineError(
            "Controller-observed checkout diff does not equal semantic changed paths; observed="
            + ",".join(actual_changed)
            + " semantic="
            + ",".join(sorted(seen))
        )
    prior_inventory = state["revision_inventory"]
    for domain in ("product", "support", "evidence"):
        deleted = {
            item["path"]
            for item in normalized_changes
            if item["domain"] == domain and item["change_kind"] == "delete"
        }
        missing_prior = set(prior_inventory[domain]) - deleted - set(normalized_inventory[domain])
        if missing_prior:
            raise PipelineError(
                f"Semantic {domain} inventory silently drops prior inputs: "
                + ", ".join(sorted(missing_prior))
            )
    for path in assigned:
        if path == DEFERRED_BACKLOG_PATH.as_posix() or path.startswith(f"tests/{state['feature']}/"):
            raise PipelineError(f"Controller evidence/backlog path cannot enter revision inventory: {path}")
        if not (root / path).is_file():
            raise PipelineError(f"Semantic revision inventory path is missing: {path}")
    allowed = lease["allowed_paths"]
    allowed_symbols = set(lease["allowed_symbols"])
    exclusions = lease["exclusions"]
    for item in normalized_changes:
        path = item["path"]
        lease_path_authorized = any(
            path_matches_scope(path, rule) for rule in allowed
        )
        if allowed and not lease_path_authorized:
            raise PipelineError(f"Changed path is outside the active lease allowlist: {path}")
        if allowed_symbols and not set(item["symbols"]).issubset(allowed_symbols):
            raise PipelineError(f"Changed symbols are outside the active lease allowlist: {path}")
        if any(path_matches_scope(path, rule) for rule in exclusions if "/" in rule):
            raise PipelineError(f"Changed path violates active lease exclusion: {path}")
        if str(item["component"]).casefold() in {
            value.casefold() for value in exclusions if "/" not in value
        }:
            raise PipelineError(f"Changed component violates active lease exclusion: {path}")
    assumptions = packet.get("open_assumptions")
    if not isinstance(assumptions, list):
        raise PipelineError("Semantic open_assumptions must be a list")
    return normalized_changes, normalized_inventory, actual_changed


def write_controller_mechanics(
    root: Path,
    state: dict[str, Any],
    *,
    run_id: str,
    lease: dict[str, Any],
    slice_item: dict[str, Any],
    changes: list[dict[str, Any]],
    base_revisions: dict[str, str],
    result_revisions: dict[str, str],
) -> tuple[str, str, str, list[dict[str, Any]]]:
    controller_root = root / "tests" / state["feature"] / "verification" / "controller"
    controller_root.mkdir(parents=True, exist_ok=True)
    safe_run = re.sub(r"[^A-Za-z0-9._-]+", "-", run_id)
    change_path = controller_root / f"{safe_run}-change-manifest.json"
    diff_path = controller_root / f"{safe_run}-diff-summary.json"
    revision_path = controller_root / f"{safe_run}-revisions.json"
    product_changes = [item for item in changes if item["domain"] == "product"]
    change_rows = [
        {
            "path": item["path"],
            "domain": item["domain"],
            "symbols": item["symbols"],
            "slice_id": slice_item["id"],
            "scope_id": lease["write_scope"],
            "requirement_ids": item["requirement_ids"],
            "acceptance_ids": item["acceptance_ids"],
            "decision_ids": item["decision_ids"],
            "reason": item["reason"],
            "change_kind": item["change_kind"],
            "touchpoint_id": item["touchpoint_id"],
        }
        for item in changes
    ]
    change_manifest = {
        "schema": 2,
        "phase": lease["phase"],
        "scope_id": lease["write_scope"],
        "slice_id": slice_item["id"],
        "role": lease["role"],
        "worker_id": lease["worker_id"],
        "lease_id": lease["lease_id"],
        "base_revisions": base_revisions,
        "result_revisions": result_revisions,
        "change_manifest": change_rows,
    }
    line_proofs = state["lease_snapshots"].get(lease["lease_id"], {}).get("line_proofs", {})
    diff_rows = [
        {
            "path": item["path"],
            "symbols": item["symbols"],
            "lines_changed": snapshot_line_count(
                line_proofs.get(item["path"]), root / item["path"]
            ),
            "component": item["component"],
            "change_kind": item["change_kind"],
            "lifecycle_change": item["lifecycle_change"],
            "ownership_change": item["ownership_change"],
            "public_contract_change": item["public_contract_change"],
            "touchpoint_id": item["touchpoint_id"],
        }
        for item in product_changes
    ]
    diff_summary = {
        "schema": 2,
        "phase": lease["phase"],
        "base_revisions": base_revisions,
        "result_revisions": result_revisions,
        "product_files": diff_rows,
        "support_paths": sorted(item["path"] for item in changes if item["domain"] == "support"),
        "evidence_paths": sorted(item["path"] for item in changes if item["domain"] == "evidence"),
    }
    revision_manifest = {
        "schema": 2,
        "base_revision": state["revision_base_revision"],
        "inventory": state["revision_inventory"],
        **result_revisions,
    }
    write_json(change_path, change_manifest)
    write_json(diff_path, diff_summary)
    write_json(revision_path, revision_manifest)
    return (
        change_path.relative_to(root).as_posix(),
        diff_path.relative_to(root).as_posix(),
        revision_path.relative_to(root).as_posix(),
        diff_rows,
    )


def write_dirty_candidate_gate_receipt(
    root: Path,
    state: dict[str, Any],
    *,
    run_id: str,
    lease: dict[str, Any],
    report: str,
) -> dict[str, Any]:
    """Bind project-owned verification evidence to an exact leased dirty candidate."""
    snapshot = state["lease_snapshots"][lease["lease_id"]]
    implementation_base = snapshot["checkout"]
    candidate = checkout_snapshot(root, state["feature"], state)
    candidate_digest = checkout_snapshot_sha256(candidate)
    changed = changed_checkout_paths(implementation_base, candidate)
    report_value = read_json(Path(report))
    gate = report_value.get("dirty_candidate_gate")
    if (
        not isinstance(gate, dict)
        or set(gate) != {
            "schema",
            "lease_id",
            "base_revision",
            "candidate_before_sha256",
            "candidate_after_sha256",
            "outcome",
            "tool",
        }
        or gate.get("schema") != 1
        or gate.get("lease_id") != lease["lease_id"]
        or gate.get("base_revision") != lease["base_revision"]
        or gate.get("candidate_before_sha256") != candidate_digest
        or gate.get("candidate_after_sha256") != candidate_digest
        or gate.get("outcome") != "pass"
        or not isinstance(gate.get("tool"), str)
        or not gate["tool"].strip()
    ):
        raise PipelineError(
            "Engineer report dirty_candidate_gate must prove an unchanged exact candidate, "
            "pass outcome, tool, lease, and base revision"
        )
    proof = [
        {
            "path": path,
            "before_sha256": implementation_base.get(path),
            "after_sha256": candidate.get(path),
        }
        for path in changed
    ]
    value = {
        "schema": 1,
        "kind": "dirty_candidate_gate",
        "lease_id": lease["lease_id"],
        "worker_id": lease["worker_id"],
        "write_scope": lease["write_scope"],
        "base_revision": lease["base_revision"],
        "implementation_base_checkout_sha256": checkout_snapshot_sha256(
            implementation_base
        ),
        "candidate_before_sha256": candidate_digest,
        "candidate_after_sha256": candidate_digest,
        "candidate_checkout_sha256": candidate_digest,
        "changed_paths": proof,
        "verification": {
            "machine_checks": "pass",
            "diff_inspection": "pass",
            "project_tool_report": report,
            "project_tool_report_sha256": file_sha256(root / report),
            "tool": gate["tool"],
        },
        "recorded_at": utc_now(),
    }
    controller_root = root / "tests" / state["feature"] / "verification" / "controller"
    safe_run = re.sub(r"[^A-Za-z0-9._-]+", "-", run_id)
    path = controller_root / f"{safe_run}-dirty-candidate-gate.json"
    write_json(path, value)
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": file_sha256(path),
        "lease_id": lease["lease_id"],
        "base_revision": lease["base_revision"],
        "candidate_checkout_sha256": value["candidate_checkout_sha256"],
    }


def validate_dirty_candidate_gate(root: Path, pending: dict[str, Any]) -> None:
    record = pending.get("dirty_candidate_gate")
    if not isinstance(record, dict):
        raise PipelineError("Engineer completion lacks the dirty candidate gate receipt")
    path = resolve_project_file(root, record.get("path", ""), "Dirty candidate gate receipt")
    if file_sha256(path) != record.get("sha256"):
        raise PipelineError("Dirty candidate gate receipt was tampered")
    value = read_json(path)
    if (
        value.get("kind") != "dirty_candidate_gate"
        or value.get("lease_id") != pending.get("lease_id")
        or value.get("base_revision") != pending.get("base_revisions", {}).get("revision")
        or value.get("candidate_checkout_sha256") != record.get("candidate_checkout_sha256")
        or value.get("verification", {}).get("machine_checks") != "pass"
        or value.get("verification", {}).get("diff_inspection") != "pass"
    ):
        raise PipelineError("Dirty candidate gate receipt binding is inconsistent")


def cmd_engineer_complete(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(
        args.project_root, allow_active_writer_completion_drift=True
    )
    require_sources_current(state)
    if state["phase"] not in {"slice_engineering", "engineering"}:
        raise PipelineError("engineer-complete requires slice_engineering or engineering")
    if args.machine_checks != "pass" or args.diff_inspection != "pass":
        raise PipelineError(
            "ENGINEERING_PASS requires completed production work, targeted checks, and final diff inspection; "
            "manual QA/DataStore/operator work is not part of this gate"
        )
    lease = state.get("active_write_lease")
    carried = state.get("scope_guard", {}).get("rebaseline_candidate")
    if (
        not lease
        or lease.get("lease_id") != args.lease_id
        or lease.get("role") != "engineer"
        or lease.get("worker_id") != args.owner_id
        or lease.get("phase") != state["phase"]
        or (
            lease.get("base_revision") != state["revision"]
            and not (
                lease.get("rebaseline_carried") is True
                and carried
                and lease.get("base_revision") == carried["base_revisions"]["revision"]
            )
        )
    ):
        raise PipelineError("engineer-complete requires the exact active Engineer lease/base revision")
    _, capsule = resolve_validated_capsule(
        root,
        state,
        args.capsule,
        role="engineer",
        worker_id=args.owner_id,
        phase=state["phase"],
    )
    snapshot_capsule = state["lease_snapshots"].get(lease["lease_id"], {}).get("capsule_sha256")
    if capsule["capsule_sha256"] != snapshot_capsule:
        raise PipelineError("Engineer capsule differs from the capsule that authorized the lease")
    slice_item = scope_slice_for_pass(state, args.slice_id)
    pre_edit = slice_item.get("scope_pre_edit_check") or {}
    if (
        pre_edit.get("status") != "passed"
        or pre_edit.get("owner_id") != args.owner_id
        or pre_edit.get("base_revision") != state["revision"]
    ):
        raise PipelineError("Engineer edits require a current exact-base slice-scope-check")
    authorization = lease.get("scope_authorization") or {}
    lease_snapshot = state["lease_snapshots"].get(lease["lease_id"], {})
    snapshot_authorization = lease_snapshot.get("scope_authorization") or {}
    authorization_checkout = lease_snapshot.get("authorization_checkout")
    diff_base_checkout = lease_snapshot.get("checkout")
    if (
        authorization != snapshot_authorization
        or authorization.get("receipt_sha256") != canonical_json_sha256(pre_edit)
        or authorization.get("slice_id") != slice_item["id"]
        or authorization.get("owner_id") != args.owner_id
        or not isinstance(authorization_checkout, dict)
        or authorization.get("checkout_snapshot_sha256")
        != checkout_snapshot_sha256(authorization_checkout)
        or not isinstance(diff_base_checkout, dict)
        or authorization.get("diff_base_checkout_sha256")
        != checkout_snapshot_sha256(diff_base_checkout)
    ):
        raise PipelineError("Engineer lease scope authorization binding is missing or changed")
    semantic_path = resolve_project_file(root, args.semantic_handoff, "Engineer semantic handoff")
    semantic = read_json(semantic_path)
    changes, inventory, _ = validate_semantic_write_packet(
        root, state, lease, semantic, slice_item=slice_item
    )
    report = resolve_report(root, state, args.report, "Engineer report")
    dirty_candidate_gate = write_dirty_candidate_gate_receipt(
        root,
        state,
        run_id=args.run_id,
        lease=lease,
        report=report,
    )
    direct_fields = {"capsule_id", "capsule_path", "capsule_sha256"}
    present_direct_fields = direct_fields & set(lease)
    if present_direct_fields and present_direct_fields != direct_fields:
        raise PipelineError("Engineer lease direct capsule binding is incomplete")
    if present_direct_fields == direct_fields:
        if (
            lease["capsule_id"] != capsule["capsule_id"]
            or lease["capsule_sha256"] != capsule["capsule_sha256"]
            or lease["capsule_path"]
            != controller_relative_path(root, args.capsule, "Engineer lease capsule")
        ):
            raise PipelineError("Engineer lease direct capsule binding is missing or changed")
        delegated_outputs = [
            semantic_path.relative_to(root).as_posix(),
            Path(report).relative_to(root).as_posix(),
        ]
        if capsule["output_paths"] != delegated_outputs:
            raise PipelineError(
                "Controller-prepared Engineer outputs must equal the semantic handoff/report pair"
            )
    product_changes = [item for item in changes if item["domain"] == "product"]
    if any(item["domain"] == "support" for item in changes):
        raise PipelineError("Engineer cannot write derived support documentation")
    mechanical_changes = [
        {
            "path": item["path"],
            "symbols": item["symbols"],
            "slice_id": slice_item["id"],
            "requirement_ids": item["requirement_ids"],
            "acceptance_ids": item["acceptance_ids"],
            "decision_ids": item["decision_ids"],
            "reason": item["reason"],
            "change_kind": item["change_kind"],
            "touchpoint_id": item["touchpoint_id"],
        }
        for item in product_changes
    ]
    line_proofs = state["lease_snapshots"].get(lease["lease_id"], {}).get("line_proofs", {})
    diff_files = [
        {
            "path": item["path"],
            "symbols": item["symbols"],
            "lines_changed": snapshot_line_count(
                line_proofs.get(item["path"]), root / item["path"]
            ),
            "component": item["component"],
            "change_kind": item["change_kind"],
            "lifecycle_change": item["lifecycle_change"],
            "ownership_change": item["ownership_change"],
            "public_contract_change": item["public_contract_change"],
            "touchpoint_id": item["touchpoint_id"],
        }
        for item in product_changes
    ]
    matching_rebaseline = next(
        (
            event
            for event in reversed(state["scope_guard"].get("rebaseline_history", []))
            if event.get("slice_id") == slice_item["id"]
            and event.get("baseline_revision") == lease["base_revision"]
            and event.get("approved_plan_sha256") == state["development_plan_sha256"]
        ),
        None,
    )
    material_approved = bool(
        matching_rebaseline
        and args.scope_approval
        and args.scope_approval == matching_rebaseline.get("user_scope_approval")
    )
    violations = scope_violations(
        slice_item,
        mechanical_changes,
        diff_files,
        material_change_approved=material_approved,
        active_decision_ids=set(state["decision_ledger"]["active_decision_ids"]),
    )
    if violations:
        open_scope_expansion_hold(
            state,
            slice_item,
            violations,
            lease=lease,
            inventory=inventory,
            changes=changes,
            diff_files=diff_files,
            semantic_report=semantic_path.relative_to(root).as_posix(),
            engineer_report=report,
            run_id=args.run_id,
        )
        save_runtime(state_path, findings_path, state, findings)
        raise PipelineError("scope_expansion_hold: " + "; ".join(violations))
    base_revisions = (
        dict(carried["base_revisions"])
        if carried and lease.get("rebaseline_carried") is True
        else {
            "revision": state["revision"],
            "product_revision": state["product_revision"],
            "support_revision": state["support_revision"],
            "evidence_revision": state["evidence_revision"],
        }
    )
    state["revision_inventory"] = inventory
    result = compute_inventory_revisions(root, state)
    result_revisions = {key: result[key] for key in base_revisions}
    product_changed = result["product_revision"] != base_revisions["product_revision"]
    if product_changes and not product_changed:
        raise PipelineError("Controller product diff did not change the product identity")
    if product_changed:
        state["iteration_control"]["consecutive_product_changes"] += 1
        reset_validation(
            state,
            result["revision"],
            result["product_revision"],
            result["support_revision"],
            result["evidence_revision"],
        )
        state["implementation_state"]["status"] = "invalidated"
        state["feature_verification_state"]["status"] = "invalidated"
    for key in base_revisions:
        state[key] = result[key]
    change_path, diff_path, revision_path, _ = write_controller_mechanics(
        root,
        state,
        run_id=args.run_id,
        lease=lease,
        slice_item=slice_item,
        changes=changes,
        base_revisions=base_revisions,
        result_revisions=result_revisions,
    )
    resolved_ids = set(args.resolved_finding or [])
    active_batch = state.get("active_remediation_batch")
    if active_batch and resolved_ids != set(active_batch["finding_ids"]):
        raise PipelineError("Engineer remediation must close the exact frozen product batch")
    if resolved_ids and not product_changed:
        raise PipelineError("Resolving product findings requires changed product identity")
    resolve_product_findings(
        findings,
        resolved_ids,
        result["revision"],
        result["product_revision"],
        result["evidence_revision"],
    )
    post_coverage_phase = "convergence"
    if active_batch and resolved_ids:
        has_next = complete_remediation_batch(state, args.owner_id)
        if has_next:
            post_coverage_phase = "engineering"
        else:
            revalidation = state.get("product_revalidation") or {}
            if revalidation.get("mode") == "targeted":
                post_coverage_phase = "closure_review"
                state["closure_review"] = {
                    "status": "pending",
                    "mode": "targeted_product_closure",
                    "source": revalidation.get("source"),
                    "return_phase": (
                        "review" if revalidation.get("source") == "convergence" else "qa"
                    ),
                    **result_revisions,
                    "base_review_runs": list(revalidation.get("base_review_runs", [])),
                    "base_convergence_runs": list(
                        revalidation.get("base_convergence_runs", [])
                    ),
                    "base_engineer_clean": copy.deepcopy(
                        revalidation.get("base_engineer_clean")
                    ),
                    "base_revision": revalidation.get("base_revision"),
                    "base_product_revision": revalidation.get("base_product_revision"),
                    "base_support_revision": revalidation.get("base_support_revision"),
                    "base_evidence_revision": revalidation.get("base_evidence_revision"),
                    "base_review_decision": copy.deepcopy(
                        revalidation.get("base_review_decision")
                    ),
                    "finding_ids": list(revalidation.get("finding_ids", [])),
                    "changed_impact_surface": {
                        "paths": sorted(item["path"] for item in diff_files),
                        "symbols": sorted(
                            {symbol for item in diff_files for symbol in item["symbols"]}
                        ),
                    },
                    "run": None,
                }
            else:
                post_coverage_phase = "convergence"
                slice_ids = list(revalidation.get("slice_ids") or state["ordered_slices"])
                require_full_convergence_budget(state, slice_ids)
                state["convergence"] = empty_convergence_state(
                    state["required_convergence_audits"],
                    result["revision"],
                    result["product_revision"],
                    result["support_revision"],
                    result["evidence_revision"],
                    state.get("convergence", {}).get("wave", 0) + 1,
                    slice_ids,
                    revalidation.get("full_wave_trigger") or "product_remediation",
                )
            iteration = state["iteration_control"]
            if (
                product_changed
                and iteration["consecutive_product_changes"]
                >= iteration["max_consecutive_product_changes"]
            ):
                iteration["status"] = "checkpoint_required"
                iteration["reason"] = "Consecutive product-change circuit breaker reached"
                iteration["resume_phase"] = post_coverage_phase
                post_coverage_phase = "convergence_hold"
    state["pending_engineer_completion"] = {
        "phase": lease["phase"],
        "writer_role": "engineer",
        "writer_id": args.owner_id,
        "lease_id": lease["lease_id"],
        "slice_id": slice_item["id"],
        "base_revisions": base_revisions,
        "result_revisions": result_revisions,
        "change_manifest": change_path,
        "diff_summary": diff_path,
        "revision_manifest": revision_path,
        "semantic_report": semantic_path.relative_to(root).as_posix(),
        "dirty_candidate_gate": dirty_candidate_gate,
        "open_assumptions": semantic["open_assumptions"],
        "post_coverage_phase": post_coverage_phase,
    }
    record_scope_churn(state, slice_item, diff_files)
    slice_item["scope_pre_edit_check"] = None
    slice_item["status"] = "engineering_complete"
    state["machine_checks"] = {
        "status": "pass",
        **result_revisions,
        "report": report,
        "diff_inspection": "pass",
    }
    state["last_engineer_run_id"] = args.run_id
    state["last_engineer_outcome"] = "engineering_pass"
    state["engineer_runs"].append(
        {
            "run_id": args.run_id,
            "owner_id": args.owner_id,
            "outcome": "engineering_pass",
            "base_revisions": base_revisions,
            "result_revisions": result_revisions,
            "report": report,
            "semantic_handoff": semantic_path.relative_to(root).as_posix(),
            "change_manifest": change_path,
            "diff_summary": diff_path,
            "revision_manifest": revision_path,
            "dirty_candidate_gate": dirty_candidate_gate,
            "resolved_findings": sorted(resolved_ids),
            "recorded_at": utc_now(),
        }
    )
    release_active_lease(state, result="complete", reason="ENGINEERING_PASS")
    state["scope_guard"]["rebaseline_candidate"] = None
    state["phase"] = (
        "slice_coverage_finalization" if lease["phase"] == "slice_engineering" else "coverage_finalization"
    )
    record_worker(state, "engineer", args.owner_id)
    save_runtime(state_path, findings_path, state, findings)
    return render_status(args, state, findings)




def cmd_transfer_engineering_owner(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    if state["phase"] not in {"engineering", "owner_handoff_hold"}:
        raise PipelineError("Engineering owner transfer is valid only at a remediation boundary")
    lease = state.get("active_write_lease")
    if lease:
        if lease.get("role") != "engineer" or lease.get("worker_id") != args.from_owner:
            raise PipelineError("Active lease does not belong to from-owner")
        snapshot = state["lease_snapshots"].get(lease["lease_id"], {}).get("checkout", {})
        changed = changed_checkout_paths(snapshot, checkout_snapshot(root, state["feature"], state))
        if changed:
            raise PipelineError("Cannot transfer ownership with unaccepted checkout drift")
        lease_id = lease["lease_id"]
        release_active_lease(state, result="revoked", reason=args.reason)
    else:
        lease_id = "no_write"
    if state.get("engineering_owner_id") != args.from_owner:
        raise PipelineError("from-owner does not match the current route owner")
    if (
        args.from_owner == args.to_owner
        or args.to_owner in state["worker_budget"].get("worker_ids", [])
        or args.to_owner in state.get("exhausted_worker_ids", [])
    ):
        raise PipelineError("Ownership transfer requires a fresh distinct Engineer")
    route = (state.get("active_remediation_batch") or {}).get("route") or args.slice_id
    if not route:
        raise PipelineError("Ownership transfer requires an exact route/slice")
    controller_root = root / "tests" / state["feature"] / "verification" / "controller"
    controller_root.mkdir(parents=True, exist_ok=True)
    empty_change = controller_root / f"transfer-{len(state['handoffs']) + 1:04d}-change.json"
    empty_diff = controller_root / f"transfer-{len(state['handoffs']) + 1:04d}-diff.json"
    write_json(empty_change, {"schema": 2, "change_manifest": [], "revision": state["revision"]})
    write_json(empty_diff, {"schema": 2, "product_files": [], "support_paths": [], "evidence_paths": []})
    coverage_record = state["coverage"].get(route) or state["coverage"].get("feature") or empty_coverage_scope()
    coverage_state = coverage_record.get("state", {})
    pending = {
        "phase": state["phase"],
        "writer_role": "engineer",
        "writer_id": args.from_owner,
        "lease_id": lease_id,
        "slice_id": route if route in state["slices"] else state["ordered_slices"][-1],
        "base_revisions": {
            "revision": state["revision"],
            "product_revision": state["product_revision"],
            "support_revision": state["support_revision"],
            "evidence_revision": state["evidence_revision"],
        },
        "result_revisions": {
            "revision": state["revision"],
            "product_revision": state["product_revision"],
            "support_revision": state["support_revision"],
            "evidence_revision": state["evidence_revision"],
        },
        "change_manifest": empty_change.relative_to(root).as_posix(),
        "diff_summary": empty_diff.relative_to(root).as_posix(),
        "semantic_report": "controller:owner-transfer:" + args.reason,
        "open_assumptions": [],
    }
    normalized_coverage = {
        "manifest_path": coverage_state.get("manifest_path"),
        "manifest_sha256": coverage_state.get("manifest_sha256"),
        "ac_mapped": coverage_state.get("ac_mapped", False),
        "identities_registered": coverage_state.get("identities_registered", "pending"),
        "automated": coverage_state.get("automated", "pending"),
        "manual": coverage_state.get("manual", "pending"),
    }
    handoff_path, handoff = generate_schema2_handoff(root, state, pending, normalized_coverage)
    state["handoffs"].append(
        {
            "handoff_id": handoff["handoff_id"],
            "path": handoff_path,
            "sha256": file_sha256(root / handoff_path),
            "handoff_sha256": handoff["handoff_sha256"],
            "schema": 2,
            "recorded_at": utc_now(),
        }
    )
    state["engineering_owner_id"] = args.to_owner
    if route == "integration":
        state["integration_owner"] = args.to_owner
    elif route in state["slices"]:
        state["owner_by_slice"][route] = args.to_owner
        state["slices"][route]["owner_id"] = args.to_owner
    if state.get("active_remediation_batch"):
        state["active_remediation_batch"]["owner_id"] = args.to_owner
        state["active_remediation_batch"]["returns_for_owner"] = 0
    if state["phase"] == "owner_handoff_hold":
        state["phase"] = "engineering"
    state.setdefault("owner_transfers", []).append(
        {
            "from": args.from_owner,
            "to": args.to_owner,
            "reason": args.reason,
            "route": route,
            "handoff": handoff_path,
            "recorded_at": utc_now(),
        }
    )
    save_runtime(state_path, findings_path, state, findings)
    return render_status(args, state, findings)


def cmd_user_authority_accept(args: argparse.Namespace) -> int:
    _, raw_state_path, _ = runtime_paths(args.project_root)
    raw_phase = read_json(raw_state_path).get("phase")
    root, state_path, findings_path, state, findings = load_runtime(
        args.project_root,
        allow_active_writer_completion_drift=(raw_phase == "scope_expansion_hold"),
    )
    scope_hold = (
        state.get("scope_guard", {}).get("hold")
        if state.get("phase") == "scope_expansion_hold"
        else None
    )
    if scope_hold is None:
        require_sources_current(state)
        if state.get("active_write_lease") is not None or state.get("phase") == "decision_recording":
            raise PipelineError("User authority acceptance requires a separate lease-free checkpoint")
    else:
        lease = state.get("active_write_lease") or {}
        if lease.get("lease_id") != scope_hold.get("lease_id"):
            raise PipelineError("Scope authority acceptance requires the exact retained hold lease")
        plan_path = resolve_project_file(
            root, state["development_plan_path"], "Updated development plan"
        )
        expected = scope_rebaseline_authority_statement(
            scope_hold, file_sha256(plan_path)
        )
        if args.statement != expected:
            raise PipelineError(
                "Scope authority statement must deterministically bind the exact "
                "hold fingerprint and updated plan SHA-256"
            )
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9._:-]*", args.authority_id):
        raise PipelineError("User authority ID must be a stable machine-addressable identifier")
    if not args.approval_reference.strip() or not args.statement.strip():
        raise PipelineError("User authority acceptance requires exact approval reference and statement")
    if any(
        record["authority_id"] == args.authority_id
        for record in state["user_authorities"]
    ):
        raise PipelineError("User authority IDs are append-only and cannot be reissued")
    digest = user_authority_digest(
        args.authority_id, args.approval_reference, args.statement
    )
    controller_root = root / "tests" / state["feature"] / "verification" / "controller"
    controller_root.mkdir(parents=True, exist_ok=True)
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "-", args.authority_id)
    receipt_path = controller_root / f"user-authority-{safe_id}.json"
    if receipt_path.exists():
        receipt = read_json(receipt_path)
        recorded_at = receipt.get("recorded_at")
        if receipt != {
            "schema": 1,
            "authority_id": args.authority_id,
            "approval_reference": args.approval_reference,
            "statement": args.statement,
            "sha256": digest,
            "recorded_at": recorded_at,
        } or not isinstance(recorded_at, str):
            raise PipelineError("User authority receipt path collides with different evidence")
    else:
        recorded_at = utc_now()
        receipt = {
            "schema": 1,
            "authority_id": args.authority_id,
            "approval_reference": args.approval_reference,
            "statement": args.statement,
            "sha256": digest,
            "recorded_at": recorded_at,
        }
        write_json(receipt_path, receipt)
    record = {
        "authority_id": args.authority_id,
        "approval_reference": args.approval_reference,
        "statement": args.statement,
        "sha256": digest,
        "receipt_path": receipt_path.relative_to(root).as_posix(),
        "receipt_sha256": file_sha256(receipt_path),
        "recorded_at": recorded_at,
    }
    state["user_authorities"].append(record)
    save_runtime(state_path, findings_path, state, findings)
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


def validate_decision_authority(
    root: Path,
    state: dict[str, Any],
    authority: dict[str, Any],
    statement: str,
    capsule: dict[str, Any] | None,
) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", str(authority["sha256"])):
        raise PipelineError("Decision authority SHA must be 64 lowercase hexadecimal characters")
    kind = authority["kind"]
    if kind == "user":
        record = next(
            (
                item
                for item in state["user_authorities"]
                if item["authority_id"] == authority["section_or_id"]
            ),
            None,
        )
        if (
            authority["path"] != "not_applicable"
            or not record
            or record["approval_reference"] != authority["reference"]
            or record["statement"] != statement
            or record["sha256"] != authority["sha256"]
        ):
            raise PipelineError(
                "User decision authority must match a prior immutable controller acceptance receipt"
            )
    else:
        expected_paths = {
            "prd": Path(state["requirements_path"]).resolve().relative_to(root).as_posix(),
            "specification": Path(state["spec_path"]).resolve().relative_to(root).as_posix(),
            "development_plan": Path(state["development_plan_path"])
            .resolve()
            .relative_to(root)
            .as_posix(),
        }
        relative = scope_path(authority["path"], "Decision authority")
        if kind in expected_paths and relative != expected_paths[kind]:
            raise PipelineError(f"Decision {kind} authority points outside its canonical artifact")
        path = resolve_project_file(root, relative, "Decision authority")
        if file_sha256(path) != authority["sha256"]:
            raise PipelineError("Decision authority SHA does not match exact current bytes")
        if authority["section_or_id"] not in path.read_text(
            encoding="utf-8", errors="replace"
        ):
            raise PipelineError("Decision authority section/ID is absent from its exact artifact")
    if capsule is not None and not any(
        entry["path"] == authority["path"]
        and entry["sha256"] == authority["sha256"]
        and authority["section_or_id"] in entry["ids"]
        for entry in capsule["authority"]
    ):
        raise PipelineError("Decision authority was not assigned by the exact context capsule")


def validate_decision_semantic_packet(
    root: Path,
    state: dict[str, Any],
    packet: dict[str, Any],
    capsule: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if set(packet) != {"schema", "items"} or packet.get("schema") != 1 or not isinstance(
        packet.get("items"), list
    ) or not packet["items"]:
        raise PipelineError("Decision semantic packet must be schema 1 with non-empty items")
    exact = {
        "schema",
        "decision_id",
        "status",
        "statement",
        "rationale",
        "consequences",
        "scope_ids",
        "authority",
        "supersedes",
    }
    existing = set(state["decision_ledger"]["active_decision_ids"]) | set(
        state["decision_ledger"]["superseded_decision_ids"]
    )
    active = set(state["decision_ledger"]["active_decision_ids"])
    seen: set[str] = set()
    for item in packet["items"]:
        if not isinstance(item, dict) or set(item) != exact or item.get("schema") != 1:
            raise PipelineError("Every decision item must use the exact schema-1 semantic fields")
        decision_id = item.get("decision_id")
        if not isinstance(decision_id, str) or not re.fullmatch(r"DEC-[A-Za-z0-9-]+", decision_id):
            raise PipelineError("Decision ID must use DEC-*")
        if decision_id in existing or decision_id in seen:
            raise PipelineError("Decision IDs are append-only and cannot be duplicated or mutated")
        seen.add(decision_id)
        if (
            item.get("status") != "accepted"
            or not item.get("statement")
            or not isinstance(item.get("rationale"), str)
            or not item["rationale"].strip()
        ):
            raise PipelineError("Decision Recorder may append accepted non-empty decisions only")
        require_string_list(item.get("consequences"), f"Decision {decision_id} consequences")
        scope_ids = set(
            require_string_list(
                item.get("scope_ids"), f"Decision {decision_id} scope_ids", allow_empty=False
            )
        )
        approved_scope_ids = set(state["ordered_slices"]) | planned_acceptance_ids(state) | {
            requirement
            for slice_item in state["slices"].values()
            for requirement in slice_item["requirement_ids"]
        }
        if not scope_ids.issubset(approved_scope_ids):
            raise PipelineError("Decision scope_ids must be an approved PRD/slice subset")
        supersedes = require_string_list(item.get("supersedes"), f"Decision {decision_id} supersedes")
        if any(target not in active for target in supersedes):
            raise PipelineError("Decision supersedes only currently active ledger entries")
        authority = item.get("authority")
        if not isinstance(authority, dict) or set(authority) != {
            "kind",
            "reference",
            "path",
            "sha256",
            "section_or_id",
        } or authority.get("kind") not in {
            "user",
            "prd",
            "specification",
            "development_plan",
            "controller_resolution",
        } or any(not authority.get(field) for field in authority):
            raise PipelineError("Decision authority must be exact, accepted, and complete")
        validate_decision_authority(root, state, authority, item["statement"], capsule)
        active.difference_update(supersedes)
        active.add(decision_id)
    return packet["items"]


def decision_projection_replay_matches(
    root: Path, state: dict[str, Any], args: argparse.Namespace
) -> bool:
    projection = (state.get("decision_ledger") or {}).get("projection")
    if not isinstance(projection, dict):
        return False
    try:
        capsule_path = resolve_project_file(root, args.capsule, "Decision Recorder capsule")
        packet_path = resolve_project_file(
            root, args.semantic_packet, "Decision semantic packet"
        )
        report_path = Path(resolve_report(root, state, args.report, "Decision Recorder report"))
        adr_paths = sorted(scope_path(path, "ADR") for path in (args.adr_path or []))
    except PipelineError:
        return False
    expected = {
        "recorder_id": args.recorder_id,
        "lease_id": args.lease_id,
        "capsule_path": capsule_path.relative_to(root).as_posix(),
        "capsule_sha256": file_sha256(capsule_path),
        "semantic_packet_path": packet_path.relative_to(root).as_posix(),
        "semantic_packet_sha256": file_sha256(packet_path),
        "report_path": str(report_path),
        "report_sha256": file_sha256(report_path),
        "adr_paths": adr_paths,
    }
    return all(projection.get(key) == value for key, value in expected.items())


def cmd_decision_record_complete(args: argparse.Namespace) -> int:
    _, raw_state_path, _ = runtime_paths(args.project_root)
    raw_state = read_json(raw_state_path)
    replay_candidate = isinstance(
        (raw_state.get("decision_ledger") or {}).get("projection"), dict
    )
    root, state_path, findings_path, state, findings = load_runtime(
        args.project_root,
        allow_active_writer_completion_drift=not replay_candidate,
    )
    projection = (state.get("decision_ledger") or {}).get("projection")
    if isinstance(projection, dict):
        if not decision_projection_replay_matches(root, state, args):
            raise PipelineError(
                "decision-record-complete lost-response replay mismatch; "
                "refusing duplicate mutation"
            )
        project_canonical_decision_ledger(root, state)
        return render_status(args, state, findings)
    lease = state.get("active_write_lease")
    if (
        state["phase"] != "decision_recording"
        or not lease
        or lease.get("lease_id") != args.lease_id
        or lease.get("role") != "decision_recorder"
        or lease.get("worker_id") != args.recorder_id
    ):
        raise PipelineError("decision-record-complete requires the exact active recorder lease")
    capsule_path, capsule = resolve_validated_capsule(
        root,
        state,
        args.capsule,
        role="decision_recorder",
        worker_id=args.recorder_id,
        phase="decision_recording",
    )
    packet_path = resolve_project_file(root, args.semantic_packet, "Decision semantic packet")
    items = validate_decision_semantic_packet(
        root, state, read_json(packet_path), capsule
    )
    report = resolve_report(root, state, args.report, "Decision Recorder report")
    snapshot = state["lease_snapshots"][lease["lease_id"]]["checkout"]
    before = checkout_snapshot(root, state["feature"], state)
    preexisting_drift = changed_checkout_paths(snapshot, before)
    allowed_adr = sorted(scope_path(path, "ADR") for path in (args.adr_path or []))
    if len(allowed_adr) != len(set(allowed_adr)):
        raise PipelineError("Decision recording repeats an ADR path")
    ledger_relative = state["decision_ledger"]["path"]
    assigned_outputs = set(capsule["output_paths"])
    assigned_paths = set(lease["allowed_paths"])
    for adr in allowed_adr:
        if not adr.startswith("docs/") or Path(adr).suffix.casefold() not in {".md", ".mdx"}:
            raise PipelineError("ADR synchronization is confined to repository documentation paths")
        if adr not in assigned_outputs or not any(
            path_matches_scope(adr, rule) for rule in assigned_paths
        ):
            raise PipelineError("ADR path is outside exact capsule/lease output authority")
        if not (root / adr).is_file():
            raise PipelineError(f"Assigned ADR output does not exist: {adr}")
    if ledger_relative not in assigned_outputs or not any(
        path_matches_scope(ledger_relative, rule) for rule in assigned_paths
    ):
        raise PipelineError("Decision ledger append is outside exact capsule/lease output authority")
    if set(preexisting_drift) != set(allowed_adr):
        raise PipelineError(
            "Decision recording checkout drift must equal the exact explicitly assigned ADR set"
        )
    _, prior_raw, projection_status = canonical_decision_ledger(root, state)
    if projection_status != "projected":
        raise PipelineError(
            "Complete the exact prior decision ledger projection replay before appending"
        )
    prefix = prior_raw
    sequence = state["decision_ledger"]["entry_count"]
    lines: list[bytes] = []
    recorded_at = utc_now()
    for semantic in items:
        sequence += 1
        entry = {
            **semantic,
            "sequence": sequence,
            "recorded_at": recorded_at,
            "recorder_id": args.recorder_id,
            "prior_ledger_sha256": hashlib.sha256(prefix + b"".join(lines)).hexdigest(),
            "input_product_revision": state["product_revision"],
        }
        lines.append(
            json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            + b"\n"
        )
    append_raw = b"".join(lines)
    target_raw = prefix + append_raw
    target_ledger = decision_ledger_state_from_raw(target_raw, ledger_relative)
    projection_binding = {
        "recorder_id": args.recorder_id,
        "lease_id": args.lease_id,
        "capsule_path": capsule_path,
        "capsule_sha256": file_sha256(root / capsule_path),
        "semantic_packet_path": packet_path.relative_to(root).as_posix(),
        "semantic_packet_sha256": file_sha256(packet_path),
        "report_path": report,
        "report_sha256": file_sha256(Path(report)),
        "adr_paths": allowed_adr,
    }
    operation_id = "DLP-" + canonical_json_sha256(
        {
            **projection_binding,
            "prior_sha256": hashlib.sha256(prior_raw).hexdigest(),
            "append_sha256": hashlib.sha256(append_raw).hexdigest(),
            "target_sha256": target_ledger["sha256"],
        }
    )[:32].upper()
    target_ledger["projection"] = {
        "schema": 1,
        "operation_id": operation_id,
        "prior_sha256": hashlib.sha256(prior_raw).hexdigest(),
        "prior_entry_count": len(parse_decision_ledger_raw(prior_raw)),
        "append_jsonl": append_raw.decode("utf-8"),
        "append_sha256": hashlib.sha256(append_raw).hexdigest(),
        "target_sha256": target_ledger["sha256"],
        "target_entry_count": target_ledger["entry_count"],
        "decision_ids": [item["decision_id"] for item in items],
        **projection_binding,
        "committed_at": recorded_at,
    }
    state["decision_ledger"] = target_ledger
    for adr in allowed_adr:
        if adr not in state["revision_inventory"]["product"]:
            state["revision_inventory"]["product"].append(adr)
    state["revision_inventory"]["product"] = sorted(state["revision_inventory"]["product"])
    base = {
        "revision": state["revision"],
        "product_revision": state["product_revision"],
        "support_revision": state["support_revision"],
        "evidence_revision": state["evidence_revision"],
    }
    current = compute_inventory_revisions(root, state)
    for key in base:
        state[key] = current[key]
    controller_root = root / "tests" / state["feature"] / "verification" / "controller"
    controller_root.mkdir(parents=True, exist_ok=True)
    change_path = controller_root / f"decision-{sequence:04d}-change-manifest.json"
    diff_path = controller_root / f"decision-{sequence:04d}-diff-summary.json"
    decision_paths = [state["decision_ledger"]["path"], *allowed_adr]
    write_json(
        change_path,
        {
            "schema": 2,
            "phase": "decision_recording",
            "role": "decision_recorder",
            "worker_id": args.recorder_id,
            "lease_id": lease["lease_id"],
            "base_revisions": base,
            "result_revisions": {key: current[key] for key in base},
            "change_manifest": [
                {
                    "path": path,
                    "domain": "product",
                    "decision_ids": [item["decision_id"] for item in items],
                    "reason": "accepted decision ledger append or assigned ADR synchronization",
                    "change_kind": "append" if path == state["decision_ledger"]["path"] else "adr_sync",
                }
                for path in decision_paths
            ],
        },
    )
    write_json(
        diff_path,
        {
            "schema": 2,
            "phase": "decision_recording",
            "base_revisions": base,
            "result_revisions": {key: current[key] for key in base},
            "product_files": decision_paths,
            "support_paths": [],
            "evidence_paths": [],
        },
    )
    scope_id = state.get("active_slice") or state["ordered_slices"][-1]
    coverage_record = state["coverage"].get(scope_id, empty_coverage_scope())["state"]
    coverage_for_handoff = {
        "manifest_path": coverage_record.get("manifest_path"),
        "manifest_sha256": coverage_record.get("manifest_sha256"),
        "ac_mapped": coverage_record.get("ac_mapped", False),
        "identities_registered": coverage_record.get("identities_registered", "pending"),
        "automated": coverage_record.get("automated", "pending"),
        "manual": coverage_record.get("manual", "pending"),
    }
    pending = {
        "phase": "decision_recording",
        "writer_role": "decision_recorder",
        "writer_id": args.recorder_id,
        "lease_id": lease["lease_id"],
        "slice_id": scope_id,
        "base_revisions": base,
        "result_revisions": {key: current[key] for key in base},
        "change_manifest": change_path.relative_to(root).as_posix(),
        "diff_summary": diff_path.relative_to(root).as_posix(),
        "semantic_report": packet_path.relative_to(root).as_posix(),
        "open_assumptions": [],
    }
    handoff_path, handoff = generate_schema2_handoff(
        root, state, pending, coverage_for_handoff
    )
    state["handoffs"].append(
        {
            "handoff_id": handoff["handoff_id"],
            "path": handoff_path,
            "sha256": file_sha256(root / handoff_path),
            "handoff_sha256": handoff["handoff_sha256"],
            "schema": 2,
            "recorded_at": utc_now(),
        }
    )
    release_active_lease(state, result="complete", reason="DECISION_RECORDING_COMPLETE")
    resume = (state.get("decision_recording") or {}).get("resume_phase")
    state["decision_recording"] = None
    if resume == "preflight":
        state["phase"] = "preflight"
    else:
        active = state.get("active_slice")
        if not active:
            raise PipelineError("Early decision recording lost its active slice route")
        slice_item = state["slices"][active]
        slice_item["base_revision"] = state["revision"]
        slice_item["base_product_revision"] = state["product_revision"]
        slice_item["base_support_revision"] = state["support_revision"]
        slice_item["base_evidence_revision"] = state["evidence_revision"]
        slice_item["scope_pre_edit_check"] = None
        slice_item["research"] = {
            "status": "pending",
            "base_revision": state["revision"],
            "bundles": [],
            "reason": None,
            "completed_at": None,
        }
        state["coverage"][active] = empty_coverage_scope()
        state["pending_engineer_completion"] = None
        state["phase"] = "slice_research"
    state["implementation_state"] = {
        "status": "pending",
        "revision": None,
        "coverage_manifest": None,
    }
    state["feature_verification_state"] = {
        "status": "pending",
        "product_revision": None,
        "support_revision": None,
        "evidence_revision": None,
    }
    save_runtime(state_path, findings_path, state, findings)
    return render_status(args, state, findings)


def controller_relative_path(root: Path, value: str, label: str) -> str:
    candidate = Path(value)
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(root).as_posix()
        except ValueError as exc:
            raise PipelineError(f"{label} escapes the project root") from exc
    return scope_path(value, label)


def documentation_source_authorities(
    root: Path, state: dict[str, Any], mode: str
) -> dict[tuple[str, str], dict[str, str]]:
    """Return controller-recorded immutable source bytes, never post-write bytes."""
    authorities: dict[tuple[str, str], dict[str, str]] = {}

    def add(
        kind: str,
        source_id: str | None,
        path: str | None,
        expected_sha256: str | None,
    ) -> None:
        if not source_id or not path or path == "not_applicable" or not expected_sha256:
            return
        if not re.fullmatch(r"[0-9a-f]{64}", str(expected_sha256)):
            raise PipelineError(f"Controller {kind} source SHA is malformed")
        normalized = controller_relative_path(root, path, f"{kind} source")
        authorities.setdefault((kind, source_id), {})[normalized] = expected_sha256

    requirement_ids = sorted(
        {
            requirement_id
            for item in state.get("slices", {}).values()
            for requirement_id in item.get("requirement_ids", [])
        }
    )
    acceptance_ids = sorted(planned_acceptance_ids(state))
    for source_id in requirement_ids + acceptance_ids:
        add(
            "requirement",
            source_id,
            state["requirements_path"],
            state["requirements_sha256"],
        )
    add(
        "specification",
        "approved-specification",
        state["spec_path"],
        state["spec_sha256"],
    )
    for decision_id in state["decision_ledger"]["active_decision_ids"]:
        add(
            "decision",
            decision_id,
            state["decision_ledger"]["path"],
            state["decision_ledger"]["sha256"],
        )
    if mode == "normative_pre_review":
        lease = state.get("active_write_lease") or {}
        snapshot = state.get("lease_snapshots", {}).get(lease.get("lease_id"), {})
        checkout = snapshot.get("checkout") or {}
        for path in state["revision_inventory"]["product"]:
            add("public_contract", path, path, checkout.get(path))
        return authorities

    qa = state.get("qa") or {}
    add(
        "qa",
        qa.get("run_id"),
        qa.get("manual_execution"),
        qa.get("manual_execution_sha256"),
    )
    for run in state.get("review_runs", []):
        add(
            "review",
            run.get("run_id"),
            run.get("credit_manifest"),
            run.get("credit_manifest_sha256"),
        )
    for handoff in state.get("handoffs", []):
        add(
            "controller_handoff",
            handoff.get("handoff_id"),
            handoff.get("path"),
            handoff.get("sha256"),
        )
    return authorities


def validate_documentation_source_map(
    root: Path,
    state: dict[str, Any],
    supplied: str,
    *,
    mode: str,
    semantic_changes: list[dict[str, Any]],
) -> tuple[str, list[str]]:
    path = resolve_project_file(root, supplied, "Documentation statement source map")
    value = read_json(path)
    if set(value) != {"schema", "mode", "statements"} or value.get("schema") != 1:
        raise PipelineError("Documentation source map must use the exact statement-map schema 1")
    if value.get("mode") != mode or not isinstance(value.get("statements"), list):
        raise PipelineError("Documentation source map mode/statements are invalid")
    exact = {
        "statement_id",
        "path",
        "source_kind",
        "source_id",
        "source_path",
        "source_sha256",
        "target_sha256",
    }
    allowed_kinds = (
        {"decision", "requirement", "specification", "public_contract"}
        if mode == "normative_pre_review"
        else {"decision", "qa", "review", "controller_handoff"}
    )
    change_by_id = {
        item["change_id"]: item
        for item in semantic_changes
        if isinstance(item, dict) and isinstance(item.get("change_id"), str)
    }
    if len(change_by_id) != len(semantic_changes):
        raise PipelineError(
            "Documentation source-map validation requires every semantic change_id exactly once"
        )
    changed_paths = sorted(item["path"] for item in semantic_changes)
    authorities = documentation_source_authorities(root, state, mode)
    seen_statements: set[str] = set()
    seen_mappings: set[tuple[str, str, str, str]] = set()
    evidence_ids: set[str] = set()
    for row in value["statements"]:
        if not isinstance(row, dict) or set(row) != exact:
            raise PipelineError("Every documentation statement mapping must use exact schema-1 fields")
        if (
            not isinstance(row["statement_id"], str)
            or re.fullmatch(r"DOC-CHG-[A-Za-z0-9._-]+", row["statement_id"]) is None
        ):
            raise PipelineError("Documentation statement IDs must use DOC-CHG-* change IDs")
        mapping_identity = (
            row["statement_id"],
            str(row["source_kind"]),
            str(row["source_id"]),
            str(row["source_path"]),
        )
        if mapping_identity in seen_mappings:
            raise PipelineError("Documentation statement source mappings must be unique")
        seen_mappings.add(mapping_identity)
        seen_statements.add(row["statement_id"])
        change = change_by_id.get(row["statement_id"])
        if change is None or row["path"] != change["path"]:
            raise PipelineError(
                "Documentation statement map must bind its exact semantic change_id and path"
            )
        expected_target_sha256 = (
            None
            if change.get("change_kind") == "delete"
            else file_sha256(
                resolve_project_file(
                    root, row["path"], "Documentation statement target"
                )
            )
        )
        if row["target_sha256"] != expected_target_sha256:
            raise PipelineError(
                "Documentation statement map target SHA does not match the exact changed artifact"
            )
        if row["source_kind"] not in allowed_kinds:
            raise PipelineError("Documentation statement map uses a source kind invalid for its lane")
        source_key = (row["source_kind"], row["source_id"])
        source_relative = controller_relative_path(
            root, row["source_path"], "documentation statement source"
        )
        if source_relative in set(changed_paths):
            raise PipelineError(
                "Documentation statement source must be immutable pre-write authority, "
                "not a changed path in the semantic packet"
            )
        expected_sha256 = authorities.get(source_key, {}).get(source_relative)
        if not expected_sha256:
            raise PipelineError(
                "Documentation statement source is not controller-verified evidence for "
                f"{row['source_kind']}:{row['source_id']}"
            )
        source_file = resolve_project_file(
            root, source_relative, "Documentation statement source"
        )
        if (
            not re.fullmatch(r"[0-9a-f]{64}", str(row["source_sha256"]))
            or row["source_sha256"] != expected_sha256
            or file_sha256(source_file) != row["source_sha256"]
        ):
            raise PipelineError(
                "Documentation statement source SHA is stale or not the controller-recorded immutable baseline"
            )
        evidence_ids.add(f"{row['source_kind']}:{row['source_id']}")
    missing_change_ids = sorted(set(change_by_id) - seen_statements)
    if missing_change_ids:
        raise PipelineError(
            "Documentation source map omits semantic change IDs: "
            + ", ".join(missing_change_ids)
        )
    return path.relative_to(root).as_posix(), sorted(evidence_ids)


def resolve_documentation_closure_report(
    root: Path,
    state: dict[str, Any],
    supplied: str,
    *,
    run_id: str,
    reviewer_id: str,
    status: str,
) -> str:
    report = resolve_report(root, state, supplied, "Documentation closure report")
    value = read_json(Path(report))
    exact = {
        "schema",
        "review_mode",
        "run_id",
        "reviewer_id",
        "revision",
        "product_revision",
        "support_revision",
        "evidence_revision",
        "status",
        "changed_support_paths",
        "statement_source_map_path",
        "statement_source_map_sha256",
        "inspected_statement_ids",
        "source_gaps",
    }
    if not isinstance(value, dict) or set(value) != exact or value.get("schema") != 1:
        raise PipelineError(
            "Documentation closure report must use the exact schema-1 envelope"
        )
    for field, expected in {
        "review_mode": "documentation_closure",
        "run_id": run_id,
        "reviewer_id": reviewer_id,
        "revision": state["revision"],
        "product_revision": state["product_revision"],
        "support_revision": state["support_revision"],
        "evidence_revision": state["evidence_revision"],
        "status": status,
    }.items():
        if value.get(field) != expected:
            raise PipelineError(
                f"Documentation closure report {field} mismatch: expected "
                f"{expected!r}, got {value.get(field)!r}"
            )
    derived = state["documentation"]["derived"]
    source_map_path = derived.get("source_map_path")
    source_map_sha256 = derived.get("source_map_sha256")
    if value.get("changed_support_paths") != sorted(derived.get("paths") or []):
        raise PipelineError(
            "Documentation closure report must cover the exact changed support paths"
        )
    if (
        value.get("statement_source_map_path") != source_map_path
        or value.get("statement_source_map_sha256") != source_map_sha256
    ):
        raise PipelineError(
            "Documentation closure report must bind the exact current statement source map"
        )
    source_map = read_json(
        resolve_project_file(root, source_map_path, "Documentation statement source map")
    )
    statement_ids = sorted(
        {row["statement_id"] for row in source_map["statements"]}
    )
    if value.get("inspected_statement_ids") != statement_ids:
        raise PipelineError(
            "Documentation closure report must inspect every mapped statement exactly once"
        )
    source_gaps = value.get("source_gaps")
    if (
        not isinstance(source_gaps, list)
        or any(not isinstance(item, str) or not item.strip() for item in source_gaps)
        or len(source_gaps) != len(set(source_gaps))
    ):
        raise PipelineError(
            "Documentation closure report source_gaps must be unique non-empty strings"
        )
    if (status == "pass" and source_gaps) or (status == "fail" and not source_gaps):
        raise PipelineError(
            "Documentation closure pass requires no source gaps and fail requires at least one"
        )
    return report


def cmd_documentation_complete(args: argparse.Namespace) -> int:
    lane = "normative" if args.mode == "normative_pre_review" else "derived"
    _, raw_state_path, _ = runtime_paths(args.project_root)
    raw_state = read_json(raw_state_path)
    replay_candidate = isinstance(
        ((raw_state.get("documentation") or {}).get(lane) or {}).get(
            "request_sha256"
        ),
        str,
    )
    root, state_path, findings_path, state, findings = load_runtime(
        args.project_root,
        allow_active_writer_completion_drift=not replay_candidate,
    )
    phase = "normative_documentation" if args.mode == "normative_pre_review" else "derived_documentation"
    request_sha256 = command_request_sha256(
        root,
        "documentation-complete",
        {
            "mode": args.mode,
            "worker_id": args.worker_id,
            "lease_id": args.lease_id,
        },
        {
            "capsule": args.capsule,
            "semantic_packet": args.semantic_packet,
            "source_map": args.source_map,
            "report": args.report,
        },
    )
    prior_documentation = state.get("documentation", {}).get(lane)
    if prior_documentation and prior_documentation.get("request_sha256") is not None:
        if exact_lost_response_replay(
            prior_documentation, request_sha256, "documentation-complete"
        ):
            return render_status(args, state, findings)
    lease = state.get("active_write_lease")
    if (
        state["phase"] != phase
        or not lease
        or lease.get("lease_id") != args.lease_id
        or lease.get("role") != "documentation_finisher"
        or lease.get("worker_id") != args.worker_id
    ):
        raise PipelineError("documentation-complete requires the exact active Finisher lease/lane")
    resolve_validated_capsule(
        root,
        state,
        args.capsule,
        role="documentation_finisher",
        worker_id=args.worker_id,
        phase=phase,
    )
    semantic_path = resolve_project_file(
        root, args.semantic_packet, "Documentation semantic write packet"
    )
    packet = read_json(semantic_path)
    slice_item = state["slices"][state.get("active_slice") or state["ordered_slices"][-1]]
    changes, inventory, _ = validate_semantic_write_packet(
        root, state, lease, packet, slice_item=slice_item
    )
    expected_domain = "product" if lane == "normative" else "support"
    if not changes or any(item["domain"] != expected_domain for item in changes):
        raise PipelineError(
            f"{args.mode} may change only non-empty {expected_domain}-domain assigned outputs"
        )
    if lane == "derived":
        qa = state["qa"]
        if (
            qa.get("status") != "pass"
            or qa.get("product_revision") != state["product_revision"]
            or qa.get("evidence_revision") != state["evidence_revision"]
        ):
            raise PipelineError("Derived documentation requires unchanged passed-QA product/evidence")
    changed_paths = sorted(item["path"] for item in changes)
    source_map_path, source_evidence_ids = validate_documentation_source_map(
        root,
        state,
        args.source_map,
        mode=args.mode,
        semantic_changes=changes,
    )
    report = resolve_report(root, state, args.report, "Documentation Finisher report")
    base = {
        "revision": state["revision"],
        "product_revision": state["product_revision"],
        "support_revision": state["support_revision"],
        "evidence_revision": state["evidence_revision"],
    }
    state["revision_inventory"] = inventory
    current = compute_inventory_revisions(root, state)
    for key in base:
        state[key] = current[key]
    if lane == "derived":
        aggregate_path, _, aggregate_state = write_feature_coverage_aggregate(
            root,
            state,
            mode="qa_updated",
            suffix=f"docs-{args.worker_id}-{len(state['handoffs']) + 1:04d}",
        )
        aggregate_absolute = str(root / aggregate_path)
        state["coverage"]["feature"]["finalized_manifest"] = {
            "path": aggregate_absolute,
            "sha256": file_sha256(root / aggregate_path),
            "revision": state["revision"],
            "report": "controller:derived-documentation-coverage-rebind",
            "steward_id": "controller-aggregate",
        }
        state["coverage"]["feature"]["state"] = aggregate_state
        state["coverage_manifest"] = aggregate_absolute
    change_path, diff_path, revision_path, _ = write_controller_mechanics(
        root,
        state,
        run_id=f"docs-{args.worker_id}-{len(state['handoffs']) + 1}",
        lease=lease,
        slice_item=slice_item,
        changes=changes,
        base_revisions=base,
        result_revisions={key: current[key] for key in base},
    )
    decision_ids = sorted({decision for item in changes for decision in item["decision_ids"]})
    documentation = state["documentation"][lane]
    documentation.update(
        {
            "status": "required_complete",
            "paths": changed_paths,
            "report_path": report,
            "report_sha256": file_sha256(root / report),
            "source_map_path": source_map_path,
            "source_map_sha256": file_sha256(root / source_map_path),
            "lease_id": args.lease_id,
            "request_sha256": request_sha256,
        }
    )
    if lane == "normative":
        documentation["product_revision"] = state["product_revision"]
        documentation["decision_ids"] = decision_ids
        state["implementation_state"]["revision"] = state["revision"]
        state["feature_verification_state"]["status"] = "invalidated"
        next_wave = state.get("convergence", {}).get("wave", 0) + 1
        state["convergence"] = empty_convergence_state(
            state["required_convergence_audits"],
            state["revision"],
            state["product_revision"],
            state["support_revision"],
            state["evidence_revision"],
            next_wave,
            list(state["ordered_slices"]),
            "initial_implementation",
        )
        state["phase"] = "convergence"
    else:
        documentation["support_revision"] = state["support_revision"]
        documentation["source_evidence_ids"] = source_evidence_ids
        documentation["closure_review_id"] = "pending"
        state["phase"] = "documentation_review"
    pending = {
        "phase": phase,
        "writer_role": "documentation_finisher",
        "writer_id": args.worker_id,
        "lease_id": lease["lease_id"],
        "slice_id": slice_item["id"],
        "base_revisions": base,
        "result_revisions": {key: current[key] for key in base},
        "change_manifest": change_path,
        "diff_summary": diff_path,
        "semantic_report": semantic_path.relative_to(root).as_posix(),
        "open_assumptions": packet["open_assumptions"],
    }
    coverage_record = state["coverage"].get("feature") or state["coverage"].get(slice_item["id"])
    coverage_state = (coverage_record or empty_coverage_scope())["state"]
    normalized_coverage = {
        "manifest_path": coverage_state.get("manifest_path"),
        "manifest_sha256": coverage_state.get("manifest_sha256"),
        "ac_mapped": coverage_state.get("ac_mapped", False),
        "identities_registered": coverage_state.get("identities_registered", "pending"),
        "automated": coverage_state.get("automated", "pending"),
        "manual": coverage_state.get("manual", "pending"),
    }
    handoff_path, handoff = generate_schema2_handoff(root, state, pending, normalized_coverage)
    state["handoffs"].append(
        {
            "handoff_id": handoff["handoff_id"],
            "path": handoff_path,
            "sha256": file_sha256(root / handoff_path),
            "handoff_sha256": handoff["handoff_sha256"],
            "schema": 2,
            "recorded_at": utc_now(),
        }
    )
    release_active_lease(state, result="complete", reason="DOCUMENTATION_COMPLETE")
    record_worker(state, f"documentation_finisher_{lane}", args.worker_id)
    save_runtime(state_path, findings_path, state, findings)
    return render_status(args, state, findings)


def cmd_documentation_not_required(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    lane = "normative" if args.mode == "normative_pre_review" else "derived"
    request_sha256 = command_request_sha256(
        root,
        "documentation-not-required",
        {
            "mode": args.mode,
            "plan_sha256": args.plan_sha256,
            "policy_evidence": args.policy_evidence,
        },
    )
    prior_documentation = state.get("documentation", {}).get(lane)
    if prior_documentation and prior_documentation.get("request_sha256") is not None:
        if exact_lost_response_replay(
            prior_documentation, request_sha256, "documentation-not-required"
        ):
            return render_status(args, state, findings)
    if (
        args.plan_sha256 != state["development_plan_sha256"]
        or args.policy_evidence != documentation_policy_reference(state, lane)
    ):
        raise PipelineError("documentation-not-required requires exact approved-plan policy evidence")
    expected = {"normative": {"implementation_complete", "normative_documentation"}, "derived": {"derived_documentation"}}
    if state["phase"] not in expected[lane]:
        raise PipelineError("documentation-not-required is invalid in the current phase")
    state["documentation"][lane].update(
        {
            "status": "not_required",
            "paths": [],
            "report_path": args.policy_evidence,
            "report_sha256": None,
            "request_sha256": request_sha256,
        }
    )
    if lane == "normative":
        state["documentation"][lane]["product_revision"] = state["product_revision"]
        next_wave = state.get("convergence", {}).get("wave", 0) + 1
        state["convergence"] = empty_convergence_state(
            state["required_convergence_audits"],
            state["revision"],
            state["product_revision"],
            state["support_revision"],
            state["evidence_revision"],
            next_wave,
            list(state["ordered_slices"]),
            "initial_implementation",
        )
        state["phase"] = "convergence"
    else:
        state["documentation"][lane]["support_revision"] = state["support_revision"]
        state["documentation"][lane]["closure_review_id"] = "not_required"
        qa = state["qa"]
        if (
            qa.get("status") != "pass"
            or qa.get("product_revision") != state["product_revision"]
            or qa.get("evidence_revision") != state["evidence_revision"]
        ):
            raise PipelineError("Derived not-required closure requires unchanged passed-QA identities")
        state["feature_verification_state"] = {
            "status": "pass",
            "product_revision": state["product_revision"],
            "support_revision": state["support_revision"],
            "evidence_revision": state["evidence_revision"],
        }
        controller_root = Path(state["tests_path"]) / "verification" / "controller"
        controller_root.mkdir(parents=True, exist_ok=True)
        change_path = controller_root / "derived-not-required-change.json"
        diff_path = controller_root / "derived-not-required-diff.json"
        write_json(change_path, {"schema": 2, "change_manifest": [], "policy_evidence": args.policy_evidence})
        write_json(diff_path, {"schema": 2, "product_files": [], "support_paths": [], "evidence_paths": []})
        scope_id = state["ordered_slices"][-1]
        coverage_record = state["coverage"].get("feature") or state["coverage"][scope_id]
        coverage_state = coverage_record["state"]
        identities = {
            "revision": state["revision"],
            "product_revision": state["product_revision"],
            "support_revision": state["support_revision"],
            "evidence_revision": state["evidence_revision"],
        }
        pending = {
            "phase": "derived_documentation",
            "writer_role": "documentation_finisher",
            "writer_id": "controller-not-required",
            "lease_id": "no_write",
            "slice_id": scope_id,
            "base_revisions": identities,
            "result_revisions": identities,
            "change_manifest": change_path.relative_to(Path(state["project_root"])).as_posix(),
            "diff_summary": diff_path.relative_to(Path(state["project_root"])).as_posix(),
            "semantic_report": args.policy_evidence,
            "open_assumptions": [],
        }
        coverage_for_handoff = {
            "manifest_path": coverage_state.get("manifest_path"),
            "manifest_sha256": coverage_state.get("manifest_sha256"),
            "ac_mapped": coverage_state.get("ac_mapped", False),
            "identities_registered": coverage_state.get("identities_registered", "pending"),
            "automated": coverage_state.get("automated", "pending"),
            "manual": coverage_state.get("manual", "pending"),
        }
        root = Path(state["project_root"])
        handoff_path, handoff = generate_schema2_handoff(root, state, pending, coverage_for_handoff)
        state["handoffs"].append(
            {
                "handoff_id": handoff["handoff_id"],
                "path": handoff_path,
                "sha256": file_sha256(root / handoff_path),
                "handoff_sha256": handoff["handoff_sha256"],
                "schema": 2,
                "recorded_at": utc_now(),
            }
        )
        state["phase"] = "ready"
    save_runtime(state_path, findings_path, state, findings)
    return render_status(args, state, findings)


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
    request_sha256 = command_request_sha256(
        root,
        "convergence-audit-complete",
        {
            "revision": args.revision,
            "product_revision": args.product_revision,
            "support_revision": args.support_revision,
            "evidence_revision": args.evidence_revision,
            "run_id": args.run_id,
            "reviewer_id": args.reviewer_id,
            "lens": args.lens,
            "status": args.status,
        },
        {
            "capsule": args.capsule,
            "report": args.report,
            "credit_manifest": args.credit_manifest,
        },
    )
    prior_run = next(
        (
            run
            for run in (state.get("convergence") or {}).get("runs", [])
            if run.get("run_id") == args.run_id
        ),
        None,
    )
    if prior_run and exact_lost_response_replay(
        prior_run, request_sha256, "convergence-audit-complete"
    ):
        return render_status(args, state, findings)
    if state["phase"] != "convergence":
        raise PipelineError("Convergence audits can complete only in convergence phase")
    convergence = state["convergence"]
    if convergence.get("status") == "awaiting_decision":
        raise PipelineError("The current convergence wave already has all required reports")
    if any(run["run_id"] == args.run_id for run in convergence["runs"]):
        raise PipelineError(f"Convergence run ID already recorded: {args.run_id}")
    if any(run["reviewer_id"] == args.reviewer_id for run in convergence["runs"]):
        raise PipelineError(f"Convergence reviewer already recorded: {args.reviewer_id}")
    if worker_is_writer(state, args.reviewer_id):
        raise PipelineError("Convergence audits must be independent of the writing owner")
    require_verifier_assignment(state, args.reviewer_id)
    if any(run["lens"] == args.lens for run in convergence["runs"]):
        raise PipelineError(f"Convergence lens already covered: {args.lens}")
    capsule_path, capsule = resolve_validated_capsule(
        root,
        state,
        args.capsule,
        role="reviewer",
        worker_id=args.reviewer_id,
        phase="convergence",
    )
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
        "report_sha256": file_sha256(root / report),
        "capsule": capsule_path,
        "capsule_id": capsule["capsule_id"],
        "credit_manifest": credit_manifest,
        "credit_manifest_sha256": file_sha256(Path(credit_manifest)),
        "component_credit_ids": credit_ids,
        "request_sha256": request_sha256,
        "recorded_at": utc_now(),
    }
    convergence["runs"].append(run)
    convergence["status"] = "running"
    if len(convergence["runs"]) == convergence["required"]:
        convergence["status"] = "awaiting_decision"
    record_worker(state, "convergence_audit", args.reviewer_id)
    save_runtime(state_path, findings_path, state, findings)
    return render_status(args, state, findings)


def cmd_convergence_finalize(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    require_current_revision(state, args.revision)
    convergence = state.get("convergence", {})
    report = resolve_report(root, state, args.report, "Convergence decision report")
    request_sha256 = command_request_sha256(
        root,
        "convergence-finalize",
        {
            "revision": args.revision,
            "decision": args.decision,
            "revalidation": args.revalidation,
            "full_wave_trigger": args.full_wave_trigger,
        },
        {"report": report},
    )
    if convergence.get("decision") is not None and exact_lost_response_replay(
        convergence, request_sha256, "convergence-finalize"
    ):
        return render_status(args, state, findings)
    if state["phase"] != "convergence" or convergence.get("status") != "awaiting_decision":
        raise PipelineError("Convergence decision requires the complete configured audit wave")
    if len(convergence.get("runs", [])) != convergence.get("required"):
        raise PipelineError("Convergence decision requires every configured audit lens")
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
    convergence["decision_report_sha256"] = file_sha256(Path(report))
    convergence["request_sha256"] = request_sha256
    convergence["decided_at"] = utc_now()

    if args.decision == "pass":
        if state["implementation_state"].get("status") != "pass":
            raise PipelineError("Convergence PASS requires independent implementation_state=pass")
        if state["documentation"]["normative"].get("status") not in {
            "required_complete",
            "not_required",
        }:
            raise PipelineError("Convergence PASS requires normative documentation closure")
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
    return render_status(args, state, findings)


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
    request_sha256 = command_request_sha256(
        root,
        "review-complete",
        {
            "revision": args.revision,
            "product_revision": args.product_revision,
            "support_revision": args.support_revision,
            "evidence_revision": args.evidence_revision,
            "run_id": args.run_id,
            "reviewer_id": args.reviewer_id,
            "status": args.status,
        },
        {
            "capsule": args.capsule,
            "report": args.report,
            "credit_manifest": args.credit_manifest,
        },
    )
    prior_run = next(
        (
            run
            for run in state.get("review_runs", [])
            if run.get("run_id") == args.run_id
        ),
        None,
    )
    if prior_run and exact_lost_response_replay(
        prior_run, request_sha256, "review-complete"
    ):
        return render_status(args, state, findings)
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
    if worker_is_writer(state, args.reviewer_id):
        raise PipelineError("Final Review must be independent of every writer")
    require_verifier_assignment(state, args.reviewer_id)
    capsule_path, capsule = resolve_validated_capsule(
        root,
        state,
        args.capsule,
        role="reviewer",
        worker_id=args.reviewer_id,
        phase="review",
    )
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
        "report_sha256": file_sha256(root / report),
        "capsule": capsule_path,
        "capsule_id": capsule["capsule_id"],
        "credit_manifest": credit_manifest,
        "credit_manifest_sha256": file_sha256(Path(credit_manifest)),
        "component_credit_ids": credit_ids,
        "request_sha256": request_sha256,
        "recorded_at": utc_now(),
    }
    current_runs.append(run)
    state["review_runs"].append(run)
    state["review"]["status"] = "running"

    if len(current_runs) >= state["required_reviews"]:
        state["review"]["status"] = "awaiting_decision"

    record_worker(state, "full_review", args.reviewer_id)
    save_runtime(state_path, findings_path, state, findings)
    return render_status(args, state, findings)


def cmd_review_finalize(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    require_current_revision(state, args.revision)
    review = state.get("review", {})
    report = resolve_report(root, state, args.report, "Aggregated Review decision report")
    request_sha256 = command_request_sha256(
        root,
        "review-finalize",
        {
            "revision": args.revision,
            "decision": args.decision,
            "reason": args.reason,
            "rework_scope": args.rework_scope,
            "revalidation": args.revalidation,
            "full_wave_trigger": args.full_wave_trigger,
        },
        {"report": report},
    )
    if review.get("decision") is not None and exact_lost_response_replay(
        review, request_sha256, "review-finalize"
    ):
        return render_status(args, state, findings)
    review["required"] = 1
    if state["phase"] != "review" or review.get("status") != "awaiting_decision":
        raise PipelineError("Review decision requires the configured final Review reports")
    if len(review.get("runs", [])) != state["required_reviews"]:
        raise PipelineError("Review decision requires every configured Review report")
    if args.decision == "pass":
        coverage_gaps = [
            scope_id
            for scope_id, record in state.get("coverage", {}).items()
            if record.get("state", {}).get("readiness_class") == "EVIDENCE_CONTRACT_VIOLATION"
            or record.get("state", {}).get("gaps")
            or (
                record.get("finalized_manifest")
                and not record.get("state", {}).get("implementation_eligible")
            )
        ]
        if coverage_gaps:
            raise PipelineError(
                "Final Review PASS is forbidden by EVIDENCE_CONTRACT_VIOLATION in: "
                + ", ".join(sorted(coverage_gaps))
            )
    reviewer_failed = any(run["status"] == "fail" for run in review["runs"])
    review_findings = [
        item
        for item in findings["items"]
        if item["status"] == "open"
        and item["source"] == "review"
        and item["revision"] == args.revision
    ]
    review_actionable = [
        item for item in review_findings if finding_requires_remediation(item)
    ]

    derived_rework_scope: str | None = None
    if args.decision == "rework":
        if not review_actionable:
            raise PipelineError(
                "Rework decision requires at least one registered remediation-required Review finding"
            )
        blocking_kinds = {item.get("finding_kind") for item in review_actionable}
        if blocking_kinds == {"product"}:
            derived_rework_scope = "product"
        elif blocking_kinds.issubset({"evidence", "support"}):
            derived_rework_scope = "recovery"
        else:
            raise PipelineError(
                "Blocking Review findings do not form one normalized product or evidence/support batch"
            )
        requested_family = (
            "product" if args.rework_scope == "product" else "recovery"
        )
        if requested_family != derived_rework_scope:
            raise PipelineError(
                "Review rework scope conflicts with the controller-derived blocking finding_kind route"
            )

    budget = state["worker_budget"]
    budget["full_review_waves"] += 1

    if args.decision == "pass":
        if review_actionable or reviewer_failed:
            raise PipelineError(
                "Cannot pass immutable final Review while a reviewer failed or remediation-required findings remain open"
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
        review["decision"] = "pass"
        review["decision_report"] = report
        review["decision_report_sha256"] = file_sha256(Path(report))
        review["request_sha256"] = request_sha256
        state["product_revalidation"] = None
        state["phase"] = "qa"
    else:
        review["status"] = "failed"
        review["decision"] = "rework"
        review["decision_report"] = report
        review["decision_report_sha256"] = file_sha256(Path(report))
        review["request_sha256"] = request_sha256
        state["qa"] = empty_qa_state()
        if derived_rework_scope == "recovery":
            state["recovery"] = {
                "status": "awaiting_remediation",
                "base_revision": state["revision"],
                "base_product_revision": state["product_revision"],
                "base_support_revision": state["support_revision"],
                "base_evidence_revision": state["evidence_revision"],
                "finding_ids": [item["id"] for item in review_actionable],
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
                    for item in review_actionable
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
                "base_engineer_clean": copy.deepcopy(state.get("engineer_clean")),
                "base_review_runs": list(review["runs"]),
                "base_review_decision": {
                    "decision": "rework",
                    "rework_scope": "product",
                    "revalidation": args.revalidation,
                    "decision_report": report,
                },
                "finding_ids": [item["id"] for item in review_actionable],
                "reason": args.reason,
                "slice_ids": affected_slice_ids,
                "full_wave_trigger": args.full_wave_trigger,
            }
            build_remediation_queue(
                state, findings, [item["id"] for item in review_actionable]
            )
            if state.get("phase") != "owner_handoff_hold":
                state["phase"] = "engineering"

    review["decision"] = args.decision
    review["decision_report"] = report
    review["decision_reason"] = args.reason
    review["decided_at"] = utc_now()
    if (
        args.decision == "rework"
        and derived_rework_scope == "product"
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
    return render_status(args, state, findings)


def targeted_closure_engineer_clean_proof(
    root: Path,
    state: dict[str, Any],
    closure: dict[str, Any],
    run: dict[str, Any],
    *,
    findings: dict[str, Any] | None = None,
    legacy_inference: bool = False,
    recorded_at: str | None = None,
) -> dict[str, Any]:
    """Bind current clean credit to prior convergence, full Review, and closure."""
    if findings is None:
        findings = read_json(root / STATE_DIR / "findings.json")
    identities = (
        "revision",
        "product_revision",
        "support_revision",
        "evidence_revision",
    )
    if (
        closure.get("mode") != "targeted_product_closure"
        or closure.get("source") != "final_review"
        or closure.get("return_phase") != "qa"
        or closure.get("status") != "passed"
        or closure.get("run") != run
        or run.get("mode") != "targeted_product_closure"
        or run.get("status") != "pass"
        or any(closure.get(key) != state.get(key) for key in identities)
        or any(run.get(key) != state.get(key) for key in identities)
        or not isinstance(run.get("run_id"), str)
        or not run.get("run_id")
        or not isinstance(run.get("report"), str)
        or not isinstance(run.get("report_sha256"), str)
        or not isinstance(run.get("credit_manifest"), str)
        or not isinstance(run.get("credit_manifest_sha256"), str)
        or not run.get("component_credit_ids")
    ):
        raise PipelineError("Targeted closure clean proof is not exact-current or complete")
    report_path = resolve_project_file(root, run["report"], "Targeted closure clean report")
    credit_path = resolve_project_file(
        root, run["credit_manifest"], "Targeted closure clean credit manifest"
    )
    if (
        file_sha256(report_path) != run["report_sha256"]
        or file_sha256(credit_path) != run["credit_manifest_sha256"]
    ):
        raise PipelineError("Targeted closure clean proof artifacts are stale")
    base_clean = closure.get("base_engineer_clean")
    base_runs = closure.get("base_review_runs")
    base_identities = {
        key: closure.get(f"base_{key}")
        for key in identities
    }
    # Legacy in-memory callers may already carry the exact base tuple in the proof.
    if all(value is None for value in base_identities.values()) and isinstance(base_clean, dict):
        base_identities = {key: base_clean.get(key) for key in identities}
    if not isinstance(base_clean, dict) or not isinstance(base_runs, list):
        raise PipelineError("Targeted closure lacks exact prior convergence/full Review lineage")
    allowed_clean_sources = (
        {"legacy_controller_accepted_final_review_gate"}
        if legacy_inference
        else {"parallel_read_only_convergence", "targeted_convergence_closure"}
    )
    if (
        base_clean.get("source") not in allowed_clean_sources
        or base_clean.get("audit_complete") is not True
        or any(base_clean.get(key) != base_identities[key] for key in identities)
    ):
        raise PipelineError("Targeted closure prior convergence proof is stale or incomplete")
    if not legacy_inference:
        clean_run_ids = base_clean.get("run_ids")
        if not isinstance(clean_run_ids, list) or not clean_run_ids:
            raise PipelineError("Targeted closure prior clean run lineage is missing")
        if base_clean["source"] == "parallel_read_only_convergence":
            convergence_runs = list((state.get("convergence") or {}).get("runs", []))
            by_id = {item.get("run_id"): item for item in convergence_runs}
            if any(
                run_id not in by_id
                or by_id[run_id].get("status") != "pass"
                or any(by_id[run_id].get(key) != base_identities[key] for key in identities)
                for run_id in clean_run_ids
            ):
                raise PipelineError("Targeted closure prior convergence lineage is invalid")
        else:
            by_id = {item.get("run_id"): item for item in state.get("review_runs", [])}
            if any(
                run_id not in by_id
                or by_id[run_id].get("mode") != "targeted_product_closure"
                or by_id[run_id].get("status") != "pass"
                or any(by_id[run_id].get(key) != base_identities[key] for key in identities)
                for run_id in clean_run_ids
            ):
                raise PipelineError("Targeted closure prior targeted convergence lineage is invalid")
        resolve_project_file(root, base_clean.get("report", ""), "Prior convergence decision report")
        resolve_project_file(root, base_clean.get("coverage_manifest", ""), "Prior convergence coverage")
    if (
        len(base_runs) != state.get("required_reviews")
        or any(item.get("status") not in {"pass", "fail"} for item in base_runs)
        or any(any(item.get(key) != base_identities[key] for key in identities) for item in base_runs)
    ):
        raise PipelineError(
            "Targeted closure lacks exact prior convergence/full Review lineage: "
            + json.dumps({
                "required": state.get("required_reviews"),
                "count": len(base_runs),
                "reviewers": [item.get("reviewer_id") for item in base_runs],
                "statuses": [item.get("status") for item in base_runs],
                "base_identities": base_identities,
                "run_identities": [{key: item.get(key) for key in identities} for item in base_runs],
            }, sort_keys=True)
        )
    if not legacy_inference:
        revalidation = state.get("product_revalidation") or {}
        decision = closure.get("base_review_decision")
        if (
            not isinstance(decision, dict)
            or decision.get("decision") != "rework"
            or decision.get("rework_scope") != "product"
            or decision.get("revalidation") != "targeted"
            or not decision.get("decision_report")
            or revalidation.get("mode") != "targeted"
            or revalidation.get("source") != "final_review"
            or revalidation.get("base_engineer_clean") != base_clean
            or revalidation.get("base_review_runs") != base_runs
            or revalidation.get("base_review_decision") != decision
            or any(
                revalidation.get(f"base_{key}") != closure.get(f"base_{key}")
                for key in identities
            )
            or sorted(revalidation.get("finding_ids") or [])
            != sorted(closure.get("finding_ids") or [])
        ):
            raise PipelineError("Targeted closure lacks its controller-accepted Final Review rework gate")
    recorded_runs = {item.get("run_id"): item for item in state.get("review_runs", [])}
    capsule_records = {
        item.get("capsule_id"): item for item in state.get("context_capsules", [])
    }
    credit_records = {
        item.get("id"): item for item in state.get("component_review_credits", [])
    }
    for item in base_runs:
        if recorded_runs.get(item.get("run_id")) != item:
            raise PipelineError("Targeted closure base Review is not controller-recorded")
        for field, sha_field, label in (
            ("report", "report_sha256", "base Review report"),
            ("credit_manifest", "credit_manifest_sha256", "base Review credit"),
        ):
            artifact = resolve_project_file(root, item.get(field, ""), label)
            if file_sha256(artifact) != item.get(sha_field):
                raise PipelineError(f"Targeted closure {label} drifted")
        capsule_record = capsule_records.get(item.get("capsule_id"))
        capsule_path = resolve_project_file(root, item.get("capsule", ""), "base Review capsule")
        if (
            not capsule_record
            or capsule_record.get("path") != item.get("capsule")
            or capsule_record.get("sha256") != file_sha256(capsule_path)
        ):
            raise PipelineError("Targeted closure base Review capsule is missing or changed")
        credit_ids = item.get("component_credit_ids")
        if (
            not isinstance(credit_ids, list)
            or not credit_ids
            or any(credit_id not in credit_records for credit_id in credit_ids)
        ):
            raise PipelineError("Targeted closure base Review component credit lineage is missing")
    frozen = sorted(set(closure.get("finding_ids") or []))
    resolved = {
        item.get("id"): item
        for item in findings.get("items", [])
        if item.get("id") in frozen and item.get("status") == "resolved"
    }
    if (
        not frozen
        or sorted(run.get("frozen_finding_ids") or []) != frozen
        or sorted(resolved) != frozen
        or any(item.get("resolved_product_revision") != state["product_revision"] for item in resolved.values())
    ):
        raise PipelineError("Targeted closure frozen findings are not exactly resolved on current product")
    engineer = next(
        (
            item for item in reversed(state.get("engineer_runs", []))
            if item.get("outcome") == "engineering_pass"
            and item.get("result_revisions") == {key: state[key] for key in identities}
            and sorted(item.get("resolved_findings") or []) == frozen
        ),
        None,
    )
    if not engineer:
        raise PipelineError("Targeted closure lacks current controller-recorded Engineer completion")
    for field, label in (
        ("report", "Engineer report"),
        ("semantic_handoff", "Engineer semantic handoff"),
        ("change_manifest", "Engineer change manifest"),
        ("diff_summary", "Engineer diff summary"),
        ("revision_manifest", "Engineer revision manifest"),
    ):
        resolve_project_file(root, engineer.get(field, ""), label)
    coverage_path = resolve_project_file(
        root, state.get("coverage_manifest", ""), "Targeted closure clean coverage"
    )
    finalized = state.get("coverage", {}).get("feature", {}).get(
        "finalized_manifest"
    ) or {}
    if (
        finalized.get("path") != str(coverage_path)
        or finalized.get("sha256") != file_sha256(coverage_path)
        or finalized.get("revision") != state["revision"]
    ):
        raise PipelineError("Targeted closure clean proof lacks current finalized coverage")
    handoff: dict[str, Any] | None = None
    handoff_path: Path | None = None
    handoff_value: dict[str, Any] | None = None
    for candidate in reversed(state.get("handoffs") or []):
        if not isinstance(candidate, dict) or candidate.get("schema") != 2:
            continue
        candidate_path = resolve_project_file(
            root, candidate.get("path", ""), "Targeted closure Engineer handoff"
        )
        candidate_value = read_json(candidate_path)
        if (
            candidate_value.get("result_revisions") == {key: state[key] for key in identities}
            and candidate_value.get("writer_id") == engineer.get("owner_id")
            and candidate_value.get("semantic_report_path") == engineer.get("semantic_handoff")
            and candidate_value.get("change_manifest_path") == engineer.get("change_manifest")
            and candidate_value.get("diff_summary_path") == engineer.get("diff_summary")
        ):
            handoff = candidate
            handoff_path = candidate_path
            handoff_value = candidate_value
            break
    if handoff is None or handoff_path is None or handoff_value is None:
        raise PipelineError("Targeted closure clean proof lacks current sealed handoff")
    if (
        file_sha256(handoff_path) != handoff.get("sha256")
        or handoff_value.get("schema") != 2
        or handoff_value.get("handoff_id") != handoff.get("handoff_id")
        or handoff_value.get("result_revisions")
        != {key: state[key] for key in identities}
        or handoff_value.get("handoff_sha256") != handoff.get("handoff_sha256")
        or handoff_value.get("handoff_sha256")
        != canonical_json_sha256(
            {key: value for key, value in handoff_value.items() if key != "handoff_sha256"}
        )
    ):
        raise PipelineError("Targeted closure current handoff drifted")
    return {
        "source": "targeted_final_review_closure_chain",
        "run_ids": [run["run_id"]],
        "revision": state["revision"],
        "product_revision": state["product_revision"],
        "support_revision": state["support_revision"],
        "evidence_revision": state["evidence_revision"],
        "audit_complete": True,
        "report": run["report"],
        "report_sha256": run["report_sha256"],
        "credit_manifest": run["credit_manifest"],
        "credit_manifest_sha256": run["credit_manifest_sha256"],
        "component_credit_ids": list(run["component_credit_ids"]),
        "base_engineer_clean": copy.deepcopy(base_clean),
        "base_review_runs": copy.deepcopy(base_runs),
        "base_review_run_ids": [item["run_id"] for item in base_runs],
        "targeted_closure_run": copy.deepcopy(run),
        "closure_run_id": run["run_id"],
        "engineer_run_id": engineer["run_id"],
        "coverage_manifest": str(coverage_path),
        "coverage_manifest_sha256": file_sha256(coverage_path),
        "handoff_id": handoff.get("handoff_id"),
        "handoff_path": handoff["path"],
        "handoff_sha256": handoff["sha256"],
        "recorded_at": recorded_at or utc_now(),
    }


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
    if worker_is_writer(state, args.reviewer_id):
        raise PipelineError("Targeted closure reviewer must be independent of every writer")
    if any(run["run_id"] == args.run_id for run in state["review_runs"]):
        raise PipelineError(f"Review run ID already recorded: {args.run_id}")
    capsule_path, capsule = resolve_validated_capsule(
        root,
        state,
        args.capsule,
        role="reviewer",
        worker_id=args.reviewer_id,
        phase="closure_review",
    )
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
        "report_sha256": file_sha256(root / report),
        "capsule": capsule_path,
        "capsule_id": capsule["capsule_id"],
        "credit_manifest": credit_manifest,
        "credit_manifest_sha256": file_sha256(Path(credit_manifest)),
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
    current_review_actionable = [
        item for item in current_review_findings if finding_requires_remediation(item)
    ]
    if args.status == "pass":
        if current_review_actionable or open_remediation_required(findings):
            raise PipelineError(
                "Targeted closure cannot pass while remediation-required findings remain open"
            )
        closure["status"] = "passed"
        closure["run"] = run
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
            state["engineer_clean"] = targeted_closure_engineer_clean_proof(
                root, state, closure, run, findings=findings
            )
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
                    "The independent Verifier checked the frozen local product batch, "
                    "changed impact surface, and preserved complementary Review evidence"
                ),
            }
            state["phase"] = "qa"
        state["product_revalidation"] = None
        state["qa"] = empty_qa_state()
        state["qa_capability"] = empty_qa_capability_state()
    else:
        if not current_review_actionable:
            raise PipelineError(
                "A failed targeted closure Review must register at least one current remediation-required finding"
            )
        closure["status"] = "failed"
        if any(
            item.get("finding_kind") == "product"
            for item in current_review_actionable
        ):
            state["product_revalidation"] = {
                "mode": "targeted",
                "source": closure.get("source"),
                "base_review_runs": list(closure.get("base_review_runs", [])),
                "base_convergence_runs": list(
                    closure.get("base_convergence_runs", [])
                ),
                "base_engineer_clean": copy.deepcopy(
                    closure.get("base_engineer_clean")
                ),
                "base_revision": closure.get("base_revision"),
                "base_product_revision": closure.get("base_product_revision"),
                "base_support_revision": closure.get("base_support_revision"),
                "base_evidence_revision": closure.get("base_evidence_revision"),
                "base_review_decision": copy.deepcopy(
                    closure.get("base_review_decision")
                ),
                "finding_ids": [item["id"] for item in current_review_actionable],
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
                [item["id"] for item in current_review_actionable],
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
                "finding_ids": [item["id"] for item in current_review_actionable],
                "base_review_runs": list(closure["base_review_runs"]),
                "remediation_owner_id": None,
                "remediation_runs": [],
                "verification_runs": [],
                "cycles": 0,
                "reason": "Targeted product closure found only support/evidence gaps",
            }
            state["phase"] = "evidence_recovery"
    save_runtime(state_path, findings_path, state, findings)
    return render_status(args, state, findings)


def cmd_add_finding(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    require_current_revision(state, args.revision)
    if any(item["id"] == args.id for item in findings["items"]):
        raise PipelineError(f"Finding ID already exists: {args.id}")
    valid_phases = {
        "engineer": {"slice_engineering", "engineering"},
        "convergence": {"convergence"},
        "review": REVIEW_FINDING_PHASES,
        "qa": {"qa"},
    }
    if state["phase"] not in valid_phases[args.source]:
        raise PipelineError(
            f"{args.source} findings cannot be registered during phase {state['phase']}"
        )
    if args.source == "qa" and args.finding_kind != "product":
        raise PipelineError("QA may register only product findings")
    coverage_identity_ids = sorted(set(args.coverage_identity_id or []))
    if coverage_identity_ids and args.source != "qa":
        raise PipelineError("Coverage identity binding is valid only for QA findings")
    if coverage_identity_ids:
        catalog, _ = finalized_manual_identity_catalog(root, state)
        unknown_identities = sorted(set(coverage_identity_ids) - set(catalog))
        if unknown_identities:
            raise PipelineError(
                "QA finding cites unknown finalized manual identities: "
                + ", ".join(unknown_identities)
            )
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
        "blocks_required_support_contract": parse_explicit_bool(
            args.blocks_required_support_contract,
            "blocks_required_support_contract",
        ),
        "required_support_contract_evidence": args.required_support_contract_evidence,
        "mandatory_core_acceptance_evidence_missing": parse_explicit_bool(
            args.mandatory_core_acceptance_evidence_missing,
            "mandatory_core_acceptance_evidence_missing",
        ),
        "test_can_miss_product_defect": parse_explicit_bool(
            args.test_can_miss_product_defect, "test_can_miss_product_defect"
        ),
        "deferred_reference": args.deferred_reference,
        "coverage_identity_ids": coverage_identity_ids,
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
            and state["phase"] in REVIEW_FINDING_PHASES
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
    elif item["remediation_required"] and not deferred_director_decision:
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
        and resume_phase in REVIEW_FINDING_PHASES | {"convergence", "qa"}
    )
    if target["remediation_required"] and not deferred_director_decision:
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
    if target.get("blocking") is not False or finding_requires_remediation(target):
        raise PipelineError("A blocking or remediation-required finding cannot be accepted")
    require_current_revision(state, args.revision)
    if target.get("revision") != args.revision:
        raise PipelineError(
            "Residual-risk acceptance must bind the finding's exact current revision"
        )
    expected_statement = (
        f"Accept residual risk for finding {args.id} at revision {args.revision}: "
        f"{args.reason}"
    )
    receipt = next(
        (
            item
            for item in state["user_authorities"]
            if item.get("authority_id") == args.authority_id
        ),
        None,
    )
    if receipt is None or receipt.get("statement") != expected_statement:
        raise PipelineError(
            "accept-finding requires a prior immutable user-authority receipt bound to "
            "the exact finding, revision, and reason"
        )
    if args.approval_reference and (
        args.approval_reference != receipt.get("approval_reference")
    ):
        raise PipelineError("Approval reference does not match the immutable authority receipt")
    target["status"] = "accepted"
    target["accepted_reason"] = args.reason
    target["accepted_revision"] = args.revision
    target["authority_id"] = receipt["authority_id"]
    target["approval_reference"] = receipt["approval_reference"]
    target["authority_receipt_path"] = receipt["receipt_path"]
    target["authority_receipt_sha256"] = receipt["receipt_sha256"]
    target["accepted_at"] = utc_now()
    save_runtime(state_path, findings_path, state, findings)
    print(json.dumps({"accepted": args.id}, ensure_ascii=False))
    return 0


def cmd_evidence_remediation_complete(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(
        args.project_root, allow_active_writer_completion_drift=True
    )
    recovery = state.get("recovery")
    lease = state.get("active_write_lease")
    if (
        state["phase"] != "evidence_recovery"
        or not recovery
        or not lease
        or lease.get("lease_id") != args.lease_id
        or lease.get("role") != "recovery_remediator"
        or lease.get("worker_id") != args.worker_id
    ):
        raise PipelineError("recovery-remediation-complete requires the exact active recovery lease")
    if args.machine_checks != "pass":
        raise PipelineError("Recovery remediation remains incomplete until targeted checks pass")
    require_worker_budget(state, args.worker_id)
    if any(
        run.get("run_id") == args.run_id for run in recovery.get("remediation_runs", [])
    ):
        raise PipelineError(f"Recovery remediation run ID already recorded: {args.run_id}")
    resolve_validated_capsule(
        root,
        state,
        args.capsule,
        role="recovery_remediator",
        worker_id=args.worker_id,
        phase="evidence_recovery",
    )
    semantic_path = resolve_project_file(root, args.semantic_report, "Recovery semantic report")
    packet = read_json(semantic_path)
    slice_item = state["slices"][state["ordered_slices"][-1]]
    changes, inventory, _ = validate_semantic_write_packet(
        root, state, lease, packet, slice_item=slice_item
    )
    if any(item["domain"] == "product" for item in changes):
        raise PipelineError("Product drift exits evidence recovery and requires Engineer routing")
    required_ids = set(recovery["finding_ids"])
    resolved_ids = set(args.resolved_finding or [])
    if resolved_ids != required_ids:
        raise PipelineError("Recovery remediation must resolve the exact frozen non-product batch")
    report = resolve_report(root, state, args.report, "Recovery remediation report")
    base = {
        "revision": state["revision"],
        "product_revision": state["product_revision"],
        "support_revision": state["support_revision"],
        "evidence_revision": state["evidence_revision"],
    }
    state["revision_inventory"] = inventory
    current = compute_inventory_revisions(root, state)
    if current["product_revision"] != base["product_revision"]:
        raise PipelineError("Product identity drifted during recovery")
    coverage_path = resolve_report(
        root, state, args.coverage_manifest, "Recovery finalized coverage aggregate"
    )
    coverage_manifest = read_json(Path(coverage_path))
    coverage_validation = validate_coverage_manifest(
        root,
        state,
        coverage_manifest,
        scope_id="feature",
        require_finalized=True,
        expected_revision=current["revision"],
        expected_product_revision=current["product_revision"],
        expected_support_revision=current["support_revision"],
        expected_evidence_revision=current["evidence_revision"],
    )
    prior_coverage_record = state.get("coverage", {}).get("feature", {}).get(
        "finalized_manifest"
    )
    if not prior_coverage_record:
        raise PipelineError("Recovery requires a prior finalized feature coverage aggregate")
    prior_coverage_path = Path(prior_coverage_record["path"])
    if (
        not prior_coverage_path.is_file()
        or file_sha256(prior_coverage_path) != prior_coverage_record["sha256"]
    ):
        raise PipelineError("Prior finalized feature coverage aggregate drifted")
    validate_coverage_continuity(
        state,
        findings,
        read_json(prior_coverage_path),
        coverage_manifest,
    )
    for key in base:
        state[key] = current[key]
    coverage_state = coverage_state_from_validation(
        coverage_path, coverage_manifest, coverage_validation
    )
    coverage_state.update(
        {
            "revision": state["revision"],
            "product_revision": state["product_revision"],
            "support_revision": state["support_revision"],
            "evidence_revision": state["evidence_revision"],
        }
    )
    state["coverage"]["feature"] = {
        "planned_manifest": state["coverage"]["feature"].get("planned_manifest"),
        "finalized_manifest": {
            "path": coverage_path,
            "sha256": file_sha256(Path(coverage_path)),
            "revision": state["revision"],
            "report": report,
            "steward_id": "recovery-remediator-validated",
        },
        "state": coverage_state,
    }
    state["coverage_manifest"] = coverage_path
    if (
        state.get("implementation_state", {}).get("status") == "pass"
        and coverage_state.get("implementation_eligible") is True
    ):
        state["implementation_state"] = {
            "status": "pass",
            "revision": state["revision"],
            "coverage_manifest": coverage_path,
        }
    state["machine_checks"] = {
        "status": "pass",
        "revision": state["revision"],
        "product_revision": state["product_revision"],
        "support_revision": state["support_revision"],
        "evidence_revision": state["evidence_revision"],
        "report": report,
        "coverage_manifest": coverage_path,
    }
    state["review"].update(
        {
            "status": "recovery_verification",
            "revision": state["revision"],
            "product_revision": state["product_revision"],
            "support_revision": state["support_revision"],
            "evidence_revision": state["evidence_revision"],
            "recovery_run": None,
        }
    )
    state["qa"] = empty_qa_state()
    state["qa_capability"] = empty_qa_capability_state()
    change_path, diff_path, revision_path, _ = write_controller_mechanics(
        root,
        state,
        run_id=args.run_id,
        lease=lease,
        slice_item=slice_item,
        changes=changes,
        base_revisions=base,
        result_revisions={key: current[key] for key in base},
    )
    coverage_scope = state["coverage"].get("feature") or state["coverage"].get(
        slice_item["id"], empty_coverage_scope()
    )
    coverage_value = coverage_scope.get("state", {})
    handoff_path, handoff = generate_schema2_handoff(
        root,
        state,
        {
            "phase": lease["phase"],
            "writer_role": "recovery_remediator",
            "writer_id": args.worker_id,
            "lease_id": lease["lease_id"],
            "slice_id": slice_item["id"],
            "base_revisions": base,
            "result_revisions": {key: current[key] for key in base},
            "change_manifest": change_path,
            "diff_summary": diff_path,
            "semantic_report": semantic_path.relative_to(root).as_posix(),
            "open_assumptions": packet["open_assumptions"],
        },
        {
            "manifest_path": coverage_value.get("manifest_path"),
            "manifest_sha256": coverage_value.get("manifest_sha256"),
            "ac_mapped": coverage_value.get("ac_mapped", False),
            "identities_registered": coverage_value.get(
                "identities_registered", "pending"
            ),
            "automated": coverage_value.get("automated", "pending"),
            "manual": coverage_value.get("manual", "pending"),
        },
    )
    state["handoffs"].append(
        {
            "handoff_id": handoff["handoff_id"],
            "path": handoff_path,
            "sha256": file_sha256(root / handoff_path),
            "handoff_sha256": handoff["handoff_sha256"],
            "schema": 2,
            "recorded_at": utc_now(),
        }
    )
    for item in findings["items"]:
        if item["id"] in resolved_ids:
            if item.get("finding_kind") == "product" or item.get("status") != "open":
                raise PipelineError("Recovery batch contains an invalid product/closed finding")
            item["status"] = "resolved"
            item["resolved_revision"] = state["revision"]
            item["resolved_product_revision"] = state["product_revision"]
            item["resolved_support_revision"] = state["support_revision"]
            item["resolved_evidence_revision"] = state["evidence_revision"]
            item["resolved_at"] = utc_now()
    recovery["status"] = "awaiting_verification"
    recovery["current_revision"] = state["revision"]
    recovery["current_support_revision"] = state["support_revision"]
    recovery["current_evidence_revision"] = state["evidence_revision"]
    recovery.setdefault("remediation_runs", []).append(
        {
            "run_id": args.run_id,
            "worker_id": args.worker_id,
            "resolved_findings": sorted(resolved_ids),
            "semantic_report": semantic_path.relative_to(root).as_posix(),
            "change_manifest": change_path,
            "diff_summary": diff_path,
            "revision_manifest": revision_path,
            "recorded_at": utc_now(),
        }
    )
    release_active_lease(state, result="complete", reason="RECOVERY_REMEDIATION_COMPLETE")
    state["phase"] = "recovery_review"
    state["feature_verification_state"]["status"] = "invalidated"
    record_worker(state, "nonproduct_remediation", args.worker_id)
    save_runtime(state_path, findings_path, state, findings)
    return render_status(args, state, findings)


def cmd_recover_ready_targeted_closure_clean(args: argparse.Namespace) -> int:
    """Repair only the legacy ready-state omission of the targeted closure clean link."""
    raw_root, _, _ = runtime_paths(args.project_root)
    raw_state = read_json(raw_root / STATE_DIR / "state.json")
    raw_computed = compute_inventory_revisions(raw_root, raw_state)
    identity_fields = ("revision", "product_revision", "support_revision", "evidence_revision")
    if any(raw_computed[key] != raw_state.get(key) for key in identity_fields):
        raise PipelineError("Ready targeted-closure recovery rejects checkout revision drift")
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    history = state.setdefault("ready_targeted_closure_clean_recoveries", [])
    if state.get("phase") != "ready":
        raise PipelineError("Ready targeted-closure clean recovery requires phase=ready")
    if len(history) > 1 or (history and not isinstance(history[0], dict)):
        raise PipelineError("Ready targeted-closure recovery history is malformed")
    clean = state.get("engineer_clean")
    if (
        not history
        and isinstance(clean, dict)
        and clean.get("product_revision") == state.get("product_revision")
    ):
        raise PipelineError("Ready state already has current engineer_clean; recovery is not eligible")
    if (
        state.get("active_write_lease") is not None
        or state.get("pending_engineer_completion") is not None
        or state.get("product_revalidation") is not None
        or any(item.get("status") != "completed" for item in state.get("remediation_queue", []))
        or any(item.get("status") == "open" for item in findings.get("items", []))
        or any(gate.get("status") == "open" for gate in state.get("gates", []))
    ):
        raise PipelineError("Ready targeted-closure recovery is blocked by pending work or an open hold")
    closure = copy.deepcopy(state.get("closure_review") or {})
    review = state.get("review") or {}
    qa = state.get("qa") or {}
    identities = identity_fields
    if (
        closure.get("status") != "passed"
        or closure.get("mode") != "targeted_product_closure"
        or closure.get("source") != "final_review"
        or closure.get("return_phase") != "qa"
        or review.get("status") != "passed_targeted"
        or review.get("recovery_run") != closure.get("run")
        or qa.get("status") != "pass"
        or any(closure.get(key) != state.get(key) for key in identities)
        or any(review.get(key) != state.get(key) for key in identities)
        or any(qa.get(key) != state.get(key) for key in identities)
    ):
        raise PipelineError("Ready state lacks an exact accepted targeted closure and QA chain")
    for field, sha_field, label in (
        ("report", "report_sha256", "QA report"),
        ("manual_execution", "manual_execution_sha256", "QA manual execution"),
    ):
        artifact = resolve_project_file(root, qa.get(field, ""), label)
        if file_sha256(artifact) != qa.get(sha_field):
            raise PipelineError(f"{label} is missing or changed")
    base_runs = closure.get("base_review_runs")
    if not isinstance(base_runs, list) or not base_runs:
        raise PipelineError("Legacy closure lacks controller-accepted base Review records")
    base_tuple = {key: base_runs[0].get(key) for key in identities}
    if any(any(item.get(key) != base_tuple[key] for key in identities) for item in base_runs):
        raise PipelineError("Legacy base Review identities are inconsistent")
    closure.update({f"base_{key}": value for key, value in base_tuple.items()})
    closure["base_engineer_clean"] = {
        "source": "legacy_controller_accepted_final_review_gate",
        "run_ids": [],
        **base_tuple,
        "audit_complete": True,
        "recorded_at": base_runs[0].get("recorded_at"),
        "legacy_inference": {
            "schema": 1,
            "provenance": "controller_accepted_full_review_records",
            "base_review_run_ids": [item.get("run_id") for item in base_runs],
        },
    }
    prior_record = history[-1] if history else None
    prior_receipt: dict[str, Any] | None = None
    if prior_record:
        prior_path = root / str(prior_record.get("path", ""))
        if prior_path.is_symlink():
            raise PipelineError("Ready recovery receipt cannot be a symlink")
        prior_path = resolve_project_file(root, str(prior_record.get("path", "")), "Ready recovery receipt")
        prior_receipt = read_json(prior_path)
    recovered_at = (
        prior_receipt.get("recorded_at")
        if isinstance(prior_receipt, dict)
        else utc_now()
    )
    if not isinstance(recovered_at, str) or not recovered_at:
        raise PipelineError("Ready recovery receipt lacks recorded_at")
    proof = targeted_closure_engineer_clean_proof(
        root,
        state,
        closure,
        closure["run"],
        findings=findings,
        legacy_inference=True,
        recorded_at=recovered_at,
    )
    proof["legacy_recovery"] = True
    readiness_state = copy.deepcopy(state)
    readiness_state["engineer_clean"] = proof
    reasons = readiness_reasons(readiness_state, findings)
    if reasons:
        raise PipelineError(
            "Ready targeted-closure recovery prerequisites are incomplete: "
            + "; ".join(reasons)
        )
    before = compute_inventory_revisions(root, state)
    sequence = len(history) if history else 1
    receipt_id = f"RTC-{sequence:04d}"
    logical_controller_root = Path(state["tests_path"]) / "verification" / "controller"
    try:
        logical_relative = logical_controller_root.relative_to(root)
    except ValueError as exc:
        raise PipelineError("Ready recovery receipt root escapes project root") from exc
    boundary = root
    for part in logical_relative.parts:
        boundary = boundary / part
        if boundary.is_symlink():
            raise PipelineError("Ready recovery receipt path crosses a symlink boundary")
    controller_root = logical_controller_root.resolve()
    try:
        controller_relative = controller_root.relative_to(root)
    except ValueError as exc:
        raise PipelineError("Ready recovery receipt root escapes project root") from exc
    receipt_path = controller_root / f"ready-targeted-closure-clean-recovery-{sequence:04d}.json"
    if receipt_path.is_symlink():
        raise PipelineError("Ready recovery receipt cannot be a symlink")
    receipt_temporary = receipt_path.with_suffix(receipt_path.suffix + ".tmp")
    if receipt_temporary.is_symlink():
        raise PipelineError(
            "Ready recovery receipt temporary path is already occupied by a symlink"
        )
    orphan = read_json(receipt_path) if receipt_path.exists() else None
    temporary_orphan = read_json(receipt_temporary) if receipt_temporary.exists() else None
    if orphan is not None and temporary_orphan is not None:
        raise PipelineError("Ready recovery receipt and temporary path are both occupied")
    orphan_source = orphan if orphan is not None else temporary_orphan
    if orphan_source is not None:
        recovered_at = orphan_source.get("recorded_at")
        if not isinstance(recovered_at, str) or not recovered_at:
            raise PipelineError("Ready recovery orphan receipt lacks recorded_at")
        proof["recorded_at"] = recovered_at
    receipt = {
        "schema": 1,
        "receipt_id": receipt_id,
        "kind": "ready_targeted_closure_clean_recovery",
        "identities": {key: state[key] for key in identities},
        "base_identities": base_tuple,
        "base_review_run_ids": [item["run_id"] for item in base_runs],
        "closure_run_id": closure["run"]["run_id"],
        "closure_report_sha256": closure["run"]["report_sha256"],
        "closure_credit_manifest_sha256": closure["run"]["credit_manifest_sha256"],
        "qa_run_id": qa["run_id"],
        "qa_report_sha256": qa["report_sha256"],
        "qa_manual_execution_sha256": qa["manual_execution_sha256"],
        "coverage_manifest": proof["coverage_manifest"],
        "coverage_manifest_sha256": proof["coverage_manifest_sha256"],
        "handoff_id": proof["handoff_id"],
        "handoff_sha256": proof["handoff_sha256"],
        "engineer_clean_sha256": canonical_json_sha256(proof),
        "recorded_at": recovered_at,
    }
    created = False
    if orphan is not None:
        if orphan != receipt:
            raise PipelineError("Ready recovery receipt path is occupied by unrelated bytes")
    elif temporary_orphan is not None:
        if temporary_orphan != receipt:
            raise PipelineError("Ready recovery receipt temporary path contains unrelated bytes")
        os.replace(receipt_temporary, receipt_path)
        created = True
    else:
        write_json(receipt_path, receipt)
        created = True
    if receipt_path.is_symlink() or read_json(receipt_path) != receipt:
        raise PipelineError("Ready recovery receipt write was not preserved exactly")
    after = compute_inventory_revisions(root, state)
    if any(before[key] != after[key] for key in identities):
        if created:
            receipt_path.unlink(missing_ok=True)
        raise PipelineError("Ready recovery receipt changed revision inventory identities")
    relative = receipt_path.relative_to(root).as_posix()
    receipt_sha = file_sha256(receipt_path)
    record = {
        "receipt_id": receipt_id,
        "kind": receipt["kind"],
        "path": relative,
        "sha256": receipt_sha,
        "engineer_clean_sha256": receipt["engineer_clean_sha256"],
        "recorded_at": recovered_at,
    }
    if history:
        if (
            len(history) != 1
            or prior_record != record
            or prior_receipt != receipt
            or not isinstance(clean, dict)
            or clean != proof
            or canonical_json_sha256(clean) != record["engineer_clean_sha256"]
        ):
            raise PipelineError("Recorded ready targeted-closure recovery is missing or changed")
        print(json.dumps({
            "status": "already_recovered",
            "receipt": {"id": receipt_id, "path": relative, "sha256": receipt_sha},
            "engineer_clean": clean,
            "phase": state["phase"],
            "next_action": next_action(state, findings),
        }, ensure_ascii=False, indent=2))
        return 0
    state["engineer_clean"] = proof
    history.append(record)
    save_runtime(state_path, findings_path, state, findings)
    print(json.dumps({
        "status": "recovered",
        "receipt": {"id": receipt_id, "path": relative, "sha256": receipt_sha},
        "engineer_clean": proof,
        "phase": state["phase"],
        "next_action": next_action(state, findings),
    }, ensure_ascii=False, indent=2))
    return 0


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
    if worker_is_writer(state, args.reviewer_id):
        raise PipelineError("Recovery reviewer must be independent of every writer")
    if any(run["run_id"] == args.run_id for run in state["review_runs"]):
        raise PipelineError(f"Review run ID already recorded: {args.run_id}")
    capsule_path, capsule = resolve_validated_capsule(
        root,
        state,
        args.capsule,
        role="reviewer",
        worker_id=args.reviewer_id,
        phase="recovery_review",
    )
    report = resolve_report(root, state, args.report, "Recovery Review report")
    credit_manifest, credit_ids = resolve_review_credit_manifest(
        root,
        state,
        args.credit_manifest,
        reviewer_id=args.reviewer_id,
        review_mode="recovery_verification",
    )
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
        "report_sha256": file_sha256(root / report),
        "capsule": capsule_path,
        "capsule_id": capsule["capsule_id"],
        "credit_manifest": credit_manifest,
        "credit_manifest_sha256": file_sha256(Path(credit_manifest)),
        "component_credit_ids": credit_ids,
        "recorded_at": utc_now(),
    }
    recovery["verification_runs"].append(run)
    state["review_runs"].append(run)
    state["review"]["recovery_run"] = run
    record_worker(state, "recovery_review", args.reviewer_id)
    if args.status == "pass":
        if open_remediation_required(findings):
            raise PipelineError(
                "Recovery Review cannot pass while remediation-required findings remain open"
            )
        state["review"]["status"] = "passed_recovery"
        state["review"]["decision"] = "pass"
        state["review"]["decision_reason"] = (
            "Product revision stayed unchanged; one independent verifier checked the "
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
            return render_status(args, state, findings)
        open_evidence = [
            item
            for item in findings["items"]
            if item.get("status") == "open"
            and item.get("finding_kind") in {"support", "evidence"}
            and finding_requires_remediation(item)
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
    return render_status(args, state, findings)


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
    return render_status(args, state, findings)


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
    return render_status(args, state, findings)


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


def qa_gate_priority(categories: set[str]) -> str | None:
    for category in ("blocked_user", "blocked_environment", "error_test"):
        if category in categories:
            return category
    return None




def finalized_manual_identity_catalog(
    root: Path, state: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    identities: dict[str, dict[str, Any]] = {}
    mandatory: set[str] = set()
    scopes = list(state["ordered_slices"])
    if state.get("coverage", {}).get("feature", {}).get("finalized_manifest"):
        scopes = ["feature"]
    for scope_id in scopes:
        record = state["coverage"].get(scope_id, {})
        artifact = record.get("finalized_manifest")
        if not artifact:
            raise PipelineError(f"QA requires finalized schema-2 coverage for {scope_id}")
        path = Path(artifact["path"])
        if not path.is_file() or file_sha256(path) != artifact["sha256"]:
            raise PipelineError(f"Finalized coverage artifact drifted for {scope_id}")
        manifest = read_json(path)
        actual = manifest.get("actual_identities")
        if not isinstance(actual, list):
            raise PipelineError("Finalized coverage actual identities are missing")
        for item in actual:
            identity_id = item.get("identity_id") if isinstance(item, dict) else None
            if not identity_id or identity_id in identities:
                raise PipelineError("Coverage identity IDs must be globally unique across scopes")
            if item.get("kind") == "manual":
                identities[identity_id] = item
        mandatory.update(
            identity_id
            for identity_id in manifest.get("mandatory_actual_identity_ids", [])
            if identity_id in identities
        )
    return identities, mandatory


def validate_manual_execution_artifact(
    root: Path,
    state: dict[str, Any],
    supplied: str,
) -> tuple[str, list[dict[str, Any]], dict[str, dict[str, Any]], set[str]]:
    path = resolve_project_file(root, supplied, "QA manual execution artifact")
    value = read_json(path)
    if set(value) != {
        "schema",
        "revision",
        "product_revision",
        "support_revision",
        "evidence_revision",
        "manual_execution",
    } or value.get("schema") != 2:
        raise PipelineError("Manual execution artifact must use the exact schema 2 envelope")
    for field in ("revision", "product_revision", "support_revision", "evidence_revision"):
        if value[field] != state[field]:
            raise PipelineError(f"Manual execution artifact {field} is stale")
    catalog, mandatory = finalized_manual_identity_catalog(root, state)
    rows = value["manual_execution"]
    if not isinstance(rows, list):
        raise PipelineError("Manual execution rows must be a list")
    by_id: dict[str, dict[str, Any]] = {}
    exact = {
        "identity_id",
        "executed",
        "passed",
        "deferred",
        "blocked_by_finding",
        "qa_evidence",
        "gate",
        "minimum_resume_action",
    }
    for row in rows:
        if not isinstance(row, dict) or set(row) != exact:
            raise PipelineError("Every QA manual row must use exact schema-2 execution fields")
        identity_id = row["identity_id"]
        if identity_id not in catalog or identity_id in by_id:
            raise PipelineError("QA manual row names an unknown or duplicate exact identity")
        if not isinstance(row["executed"], bool) or row["passed"] not in {True, False, None} or not isinstance(
            row["deferred"], bool
        ):
            raise PipelineError("QA manual executed/passed/deferred values are invalid")
        if row["passed"] is True and not row["executed"]:
            raise PipelineError("Manual PASS requires executed=true")
        if row["deferred"]:
            if row["executed"] or row["passed"] is not None or row["gate"] not in QA_GATE_STATUSES or not row[
                "minimum_resume_action"
            ]:
                raise PipelineError("Deferred manual identity requires a gate and resume action")
        elif row["gate"] is not None:
            raise PipelineError("Non-deferred manual identity cannot carry a gate")
        elif row["minimum_resume_action"] is not None:
            raise PipelineError("Non-deferred manual identity cannot carry a resume action")
        if row["blocked_by_finding"]:
            if not isinstance(row["blocked_by_finding"], str):
                raise PipelineError("blocked_by_finding must be a finding ID or null")
            if row["executed"] or row["deferred"] or row["passed"] is not None:
                raise PipelineError("blocked_by_finding is an unexecuted non-gate identity")
        if row["executed"]:
            if not isinstance(row["passed"], bool):
                raise PipelineError("Executed QA manual identity requires passed=true|false")
            evidence = row["qa_evidence"]
            if not isinstance(evidence, dict) or set(evidence) != {"path", "sha256"}:
                raise PipelineError(
                    "Every executed manual identity requires immutable QA evidence path/SHA"
                )
            evidence_path = resolve_project_file(root, evidence["path"], "QA identity evidence")
            try:
                evidence_path.relative_to(Path(state["tests_path"]).resolve())
            except ValueError as exc:
                raise PipelineError("QA identity evidence must stay under feature test artifacts") from exc
            if (
                not re.fullmatch(r"[0-9a-f]{64}", str(evidence["sha256"]))
                or file_sha256(evidence_path) != evidence["sha256"]
            ):
                raise PipelineError("QA identity evidence SHA does not match immutable bytes")
        elif row["qa_evidence"] is not None:
            raise PipelineError("Unexecuted manual identity cannot claim QA evidence")
        if (
            not row["executed"]
            and not row["deferred"]
            and not row["blocked_by_finding"]
        ):
            raise PipelineError(
                "Unexecuted manual identity must be deferred or bound to a product finding"
            )
        by_id[identity_id] = row
    if set(by_id) != set(catalog):
        raise PipelineError("QA must return every registered manual identity exactly once")
    return path.relative_to(root).as_posix(), rows, by_id, mandatory


def require_current_review_chain_for_qa(state: dict[str, Any]) -> None:
    review = state.get("review", {})
    exact = all(
        review.get(key) == state[key]
        for key in ("revision", "product_revision", "support_revision", "evidence_revision")
    )
    if review.get("status") not in PASSED_REVIEW_STATUSES or not exact:
        raise PipelineError("QA requires an exact-current immutable Review chain")
    if review["status"] == "passed":
        runs = review.get("runs", [])
        if len(runs) != state["required_reviews"]:
            raise PipelineError("QA requires the configured final Review report")
    elif review["status"] == "passed_recovery":
        recovery = state.get("recovery") or {}
        if (
            recovery.get("status") != "passed"
            or len(recovery.get("base_review_runs", [])) != state["required_reviews"]
            or not review.get("recovery_run")
        ):
            raise PipelineError("QA recovery Review chain is incomplete")
    else:
        closure = state.get("closure_review") or {}
        if (
            closure.get("status") != "passed"
            or len(closure.get("base_review_runs", [])) != state["required_reviews"]
            or not closure.get("run")
        ):
            raise PipelineError("QA targeted-closure Review chain is incomplete")


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
    request_sha256 = command_request_sha256(
        root,
        "qa-complete",
        {
            "revision": args.revision,
            "product_revision": args.product_revision,
            "support_revision": args.support_revision,
            "evidence_revision": args.evidence_revision,
            "run_id": args.run_id,
            "worker_id": args.worker_id,
            "status": args.status,
            "reason": args.reason,
            "pending_identity": sorted(args.pending_identity or []),
        },
        {
            "capsule": args.capsule,
            "manual_execution": args.manual_execution,
            "report": args.report,
        },
    )
    prior_run = next(
        (run for run in state.get("qa_runs", []) if run.get("run_id") == args.run_id),
        None,
    )
    if prior_run and exact_lost_response_replay(
        prior_run, request_sha256, "qa-complete"
    ):
        return render_status(args, state, findings)
    if state["phase"] != "qa":
        raise PipelineError("qa-complete requires QA phase")
    if any(run.get("run_id") == args.run_id for run in state["qa_runs"]):
        raise PipelineError(f"QA run ID already recorded: {args.run_id}")
    if worker_is_writer(state, args.worker_id):
        raise PipelineError("Runtime QA must be independent of every writer")
    require_verifier_assignment(state, args.worker_id)
    require_current_review_chain_for_qa(state)
    capsule_path, capsule = resolve_validated_capsule(
        root, state, args.capsule, role="reviewer", worker_id=args.worker_id, phase="qa"
    )
    qa_capability = state["qa_capability"]
    if qa_capability.get("revision") != state["revision"]:
        raise PipelineError("QA capability probe is stale")
    manual_path, rows, by_id, mandatory = validate_manual_execution_artifact(
        root, state, args.manual_execution
    )
    pending = sorted(args.pending_identity or [])
    if len(pending) != len(set(pending)) or any(identity_id not in by_id for identity_id in pending):
        raise PipelineError("pending-identity must name distinct registered manual identities")
    deferred = sorted(identity_id for identity_id, row in by_id.items() if row["deferred"])
    blocked_by_finding = sorted(
        identity_id for identity_id, row in by_id.items() if row["blocked_by_finding"]
    )
    failed = sorted(
        identity_id
        for identity_id, row in by_id.items()
        if row["executed"] and row["passed"] is False
    )
    mandatory_pass = all(
        by_id[identity_id]["executed"] is True
        and by_id[identity_id]["passed"] is True
        and not by_id[identity_id]["deferred"]
        and not by_id[identity_id]["blocked_by_finding"]
        for identity_id in mandatory
    )
    if pending != deferred:
        raise PipelineError("pending-identity must equal the exact deferred identity set")
    current_qa_findings = [
        item
        for item in findings["items"]
        if item.get("source") == "qa"
        and item.get("finding_kind") == "product"
        and item.get("revision") == state["revision"]
        and item.get("status") in {"open", "accepted"}
    ]
    by_finding_id = {item["id"]: item for item in current_qa_findings}
    linked_by_identity = {
        identity_id: [
            item
            for item in current_qa_findings
            if identity_id in item.get("coverage_identity_ids", [])
        ]
        for identity_id in by_id
    }
    product_failure = False
    for identity_id in failed:
        linked = linked_by_identity[identity_id]
        if not linked:
            raise PipelineError(
                f"Failed QA identity {identity_id} requires an exact QA finding binding"
            )
        if identity_id in mandatory:
            if not any(item.get("status") == "open" and item.get("blocking") for item in linked):
                raise PipelineError(
                    "A failed mandatory identity requires an open normalized blocking QA finding"
                )
            product_failure = True
        else:
            accepted_nonblocking = [
                item
                for item in linked
                if item.get("status") == "accepted"
                and item.get("severity") == "minor"
                and item.get("blocking") is False
            ]
            if not accepted_nonblocking or any(
                item.get("status") == "open" or item.get("blocking") is True
                for item in linked
            ):
                raise PipelineError(
                    "An optional failed identity may remain nonblocking only through an "
                    "accepted minor exact-revision QA finding"
                )
    for identity_id in blocked_by_finding:
        finding_id = by_id[identity_id]["blocked_by_finding"]
        item = by_finding_id.get(finding_id)
        if (
            not item
            or item.get("status") != "open"
            or item.get("blocking") is not True
            or identity_id not in item.get("coverage_identity_ids", [])
        ):
            raise PipelineError(
                "blocked_by_finding must name an open blocking QA finding bound to the identity"
            )
        product_failure = True
    unbound_blocking = [
        item["id"]
        for item in current_qa_findings
        if item.get("status") == "open"
        and item.get("blocking") is True
        and not any(
            identity_id in item.get("coverage_identity_ids", [])
            and (identity_id in failed or identity_id in blocked_by_finding)
            for identity_id in by_id
        )
    ]
    if unbound_blocking:
        raise PipelineError(
            "Open blocking QA findings are not bound to a failed/blocked identity: "
            + ", ".join(sorted(unbound_blocking))
        )
    gate_categories = {by_id[identity_id]["gate"] for identity_id in deferred}
    derived_gate = qa_gate_priority(gate_categories)
    if product_failure:
        derived_status = "fail_product"
    elif derived_gate:
        derived_status = derived_gate
    elif mandatory_pass:
        derived_status = "pass"
    else:
        raise PipelineError(
            "QA result is not closed: mandatory identities must pass, defer through an "
            "external gate, or bind to a product finding"
        )
    if args.status != derived_status:
        raise PipelineError(
            f"Supplied QA status {args.status!r} conflicts with controller-derived "
            f"status {derived_status!r}"
        )
    blocked_capability_categories = {
        status
        for status in qa_capability.get("capabilities", {}).values()
        if status in QA_GATE_STATUSES
    }
    if gate_categories:
        if qa_capability.get("status") != "blocked" or gate_categories != blocked_capability_categories:
            raise PipelineError(
                "Deferred QA gate categories must exactly match the failed capability probe"
            )
        if not args.reason:
            raise PipelineError("QA external gates require a reason")
    elif qa_capability.get("status") != "ready":
        raise PipelineError("QA execution requires a ready exact-revision capability probe")
    if derived_status == "fail_product" and not (failed or blocked_by_finding):
        raise PipelineError("FAIL_PRODUCT requires a failed or finding-blocked manual identity")
    report = resolve_report(root, state, args.report, "QA report")
    run = {
        "run_id": args.run_id,
        "worker_id": args.worker_id,
        "revision": state["revision"],
        "product_revision": state["product_revision"],
        "support_revision": state["support_revision"],
        "evidence_revision": state["evidence_revision"],
        "status": args.status,
        "manual_execution": manual_path,
        "executed_identity_ids": sorted(
            identity_id for identity_id, row in by_id.items() if row["executed"]
        ),
        "passed_identity_ids": sorted(
            identity_id for identity_id, row in by_id.items() if row["passed"] is True
        ),
        "deferred_identity_ids": deferred,
        "blocked_by_finding_identity_ids": blocked_by_finding,
        "pending_identities": pending,
        "reason": args.reason,
        "report": report,
        "report_sha256": file_sha256(root / report),
        "manual_execution_sha256": file_sha256(root / manual_path),
        "capsule": capsule_path,
        "capsule_id": capsule["capsule_id"],
        "capability_probe_id": qa_capability.get("probe_id"),
        "request_sha256": request_sha256,
        "recorded_at": utc_now(),
    }
    state["qa_runs"].append(run)
    state["qa"] = run
    aggregate_path, _, aggregate_state = write_feature_coverage_aggregate(
        root,
        state,
        mode="qa_updated",
        manual_execution=rows,
        suffix=f"qa-{args.run_id}",
    )
    aggregate_absolute = str(root / aggregate_path)
    aggregate_state["manual_execution"] = manual_path
    feature_scope = state["coverage"].setdefault("feature", empty_coverage_scope())
    feature_scope["finalized_manifest"] = {
        "path": aggregate_absolute,
        "sha256": file_sha256(root / aggregate_path),
        "revision": state["revision"],
        "report": report,
        "steward_id": "controller-qa-aggregate",
    }
    feature_scope["state"] = aggregate_state
    state["coverage_manifest"] = aggregate_absolute
    for category in sorted(gate_categories):
        category_pending = sorted(
            identity_id
            for identity_id in deferred
            if by_id[identity_id]["gate"] == category
        )
        state["gates"].append(
            {
                "id": f"qa:{args.run_id}:{category}",
                "phase": "qa",
                "category": category,
                "revision": state["revision"],
                "pending_identities": category_pending,
                "reason": args.reason,
                "minimum_resume_actions": {
                    identity_id: by_id[identity_id]["minimum_resume_action"]
                    for identity_id in category_pending
                },
                "status": "open",
                "created_at": utc_now(),
            }
        )
    if args.status == "pass":
        resolve_qa_gates(state, state["revision"], "All mandatory manual identities passed")
        state["feature_verification_state"] = {
            "status": "pending",
            "product_revision": state["product_revision"],
            "support_revision": state["support_revision"],
            "evidence_revision": state["evidence_revision"],
        }
        state["phase"] = "derived_documentation"
    elif args.status == "fail_product":
        qa_product = [
            item for item in findings["items"] if item.get("status") == "open" and item.get("source") == "qa" and item.get("blocking")
        ]
        state["feature_verification_state"]["status"] = "invalidated"
        build_remediation_queue(state, findings, [item["id"] for item in qa_product])
        if state.get("phase") != "owner_handoff_hold":
            state["phase"] = "engineering"
    else:
        state["feature_verification_state"]["status"] = "pending"
        state["phase"] = "qa"
    record_worker(state, "runtime_qa", args.worker_id)
    save_runtime(state_path, findings_path, state, findings)
    return render_status(args, state, findings)


def cmd_documentation_review_complete(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_current_identity(
        state,
        args.revision,
        args.product_revision,
        args.support_revision,
        args.evidence_revision,
    )
    request_sha256 = command_request_sha256(
        root,
        "documentation-review-complete",
        {
            "revision": args.revision,
            "product_revision": args.product_revision,
            "support_revision": args.support_revision,
            "evidence_revision": args.evidence_revision,
            "run_id": args.run_id,
            "reviewer_id": args.reviewer_id,
            "status": args.status,
        },
        {
            "capsule": args.capsule,
            "report": args.report,
            "credit_manifest": args.credit_manifest,
        },
    )
    prior_run = next(
        (
            run
            for run in state.get("documentation_review_runs", [])
            if run.get("run_id") == args.run_id
        ),
        None,
    )
    if prior_run and exact_lost_response_replay(
        prior_run, request_sha256, "documentation-review-complete"
    ):
        return render_status(args, state, findings)
    if state["phase"] != "documentation_review":
        raise PipelineError("documentation-review-complete requires documentation_review")
    if any(
        run.get("run_id") == args.run_id
        for run in state.get("documentation_review_runs", [])
    ):
        raise PipelineError(f"Documentation closure run ID already recorded: {args.run_id}")
    capsule_path, capsule = resolve_validated_capsule(
        root,
        state,
        args.capsule,
        role="reviewer",
        worker_id=args.reviewer_id,
        phase="documentation_review",
    )
    qa = state["qa"]
    if (
        qa.get("status") != "pass"
        or qa.get("product_revision") != state["product_revision"]
        or qa.get("evidence_revision") != state["evidence_revision"]
        or args.product_revision != qa.get("product_revision")
        or args.evidence_revision != qa.get("evidence_revision")
    ):
        state["feature_verification_state"]["status"] = "invalidated"
        save_runtime(state_path, findings_path, state, findings)
        raise PipelineError("Documentation closure cannot preserve QA after product/evidence drift")
    if worker_is_writer(state, args.reviewer_id):
        raise PipelineError("Documentation closure reviewer must be independent of every writer")
    if args.status == "pass" and open_remediation_required(findings):
        raise PipelineError(
            "Documentation closure cannot pass while remediation-required findings remain open"
        )
    report = resolve_documentation_closure_report(
        root,
        state,
        args.report,
        run_id=args.run_id,
        reviewer_id=args.reviewer_id,
        status=args.status,
    )
    credit_manifest, credit_ids = resolve_review_credit_manifest(
        root,
        state,
        args.credit_manifest,
        reviewer_id=args.reviewer_id,
        review_mode="documentation_closure",
    )
    if args.status == "pass":
        state["documentation"]["derived"]["closure_review_id"] = args.run_id
        state["feature_verification_state"] = {
            "status": "pass",
            "product_revision": state["product_revision"],
            "support_revision": state["support_revision"],
            "evidence_revision": state["evidence_revision"],
        }
        state["phase"] = "ready"
    else:
        state["documentation"]["derived"]["status"] = "gap"
        state["feature_verification_state"]["status"] = "invalidated"
        state["phase"] = "derived_documentation"
    state.setdefault("documentation_review_runs", []).append(
        {
            "run_id": args.run_id,
            "reviewer_id": args.reviewer_id,
            "status": args.status,
            "revision": state["revision"],
            "product_revision": state["product_revision"],
            "support_revision": state["support_revision"],
            "evidence_revision": state["evidence_revision"],
            "report": report,
            "report_sha256": file_sha256(Path(report)),
            "capsule": capsule_path,
            "capsule_id": capsule["capsule_id"],
            "credit_manifest": credit_manifest,
            "credit_manifest_sha256": file_sha256(Path(credit_manifest)),
            "component_credit_ids": credit_ids,
            "request_sha256": request_sha256,
            "recorded_at": utc_now(),
        }
    )
    record_worker(state, "documentation_closure_review", args.reviewer_id)
    save_runtime(state_path, findings_path, state, findings)
    return render_status(args, state, findings)


def readiness_reasons(state: dict[str, Any], findings: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
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
    if state.get("active_write_lease") is not None:
        reasons.append("a write-capable lease is still active")
    if any(item.get("status") not in {"released", "revoked"} for item in state.get("write_lease_history", [])):
        reasons.append("write lease history contains an unclosed entry")
    if state.get("implementation_state", {}).get("status") != "pass":
        reasons.append("implementation_state has not independently passed")
    feature_verification = state.get("feature_verification_state", {})
    if feature_verification != {
        "status": "pass",
        "product_revision": product_revision,
        "support_revision": support_revision,
        "evidence_revision": evidence_revision,
    }:
        reasons.append("feature_verification_state has not passed on current identities")
    if state.get("documentation", {}).get("normative", {}).get("status") not in {
        "required_complete",
        "not_required",
    }:
        reasons.append("normative documentation is incomplete")
    if state.get("documentation", {}).get("derived", {}).get("status") not in {
        "required_complete",
        "not_required",
    }:
        reasons.append("derived documentation is incomplete")
    derived = state.get("documentation", {}).get("derived", {})
    if derived.get("status") == "required_complete":
        closure_id = derived.get("closure_review_id")
        closure_run = next(
            (
                run
                for run in state.get("documentation_review_runs", [])
                if run.get("run_id") == closure_id
            ),
            None,
        )
        valid_credit_ids = {
            credit.get("id")
            for credit in state.get("component_review_credits", [])
            if credit.get("valid") is True
        }
        try:
            report_path = Path((closure_run or {}).get("report", ""))
            credit_path = Path((closure_run or {}).get("credit_manifest", ""))
            artifacts_current = (
                report_path.is_file()
                and file_sha256(report_path) == closure_run.get("report_sha256")
                and credit_path.is_file()
                and file_sha256(credit_path)
                == closure_run.get("credit_manifest_sha256")
            )
        except (OSError, PipelineError):
            artifacts_current = False
        if (
            not closure_run
            or closure_run.get("status") != "pass"
            or any(
                closure_run.get(field) != state.get(field)
                for field in (
                    "revision",
                    "product_revision",
                    "support_revision",
                    "evidence_revision",
                )
            )
            or not artifacts_current
            or not closure_run.get("component_credit_ids")
            or not set(closure_run["component_credit_ids"]).issubset(valid_credit_ids)
            or not isinstance(closure_run.get("request_sha256"), str)
        ):
            reasons.append(
                "documentation closure report/credit receipt is stale or incomplete"
            )
    if any(
        record.get("state", {}).get("readiness_class") == "EVIDENCE_CONTRACT_VIOLATION"
        or record.get("state", {}).get("gaps")
        for record in state.get("coverage", {}).values()
        if record.get("finalized_manifest")
    ):
        reasons.append("schema-2 coverage has an EVIDENCE_CONTRACT_VIOLATION")
    feature_coverage = state.get("coverage", {}).get("feature", {})
    feature_artifact = feature_coverage.get("finalized_manifest")
    feature_state = feature_coverage.get("state", {})
    expected_terminal_coverage_state: dict[str, Any] | None = None
    if not feature_artifact:
        reasons.append("terminal feature coverage aggregate is missing")
    else:
        feature_path = Path(feature_artifact.get("path", ""))
        try:
            feature_value = read_json(feature_path)
            validation = validate_coverage_manifest(
                Path(state["project_root"]),
                state,
                feature_value,
                scope_id="feature",
                require_finalized=True,
            )
        except PipelineError:
            validation = None
        expected_coverage_revisions = {
            key: state[key]
            for key in ("revision", "product_revision", "support_revision", "evidence_revision")
        }
        if (
            not feature_path.is_file()
            or file_sha256(feature_path) != feature_artifact.get("sha256")
            or feature_artifact.get("revision") != revision
            or not validation
            or feature_value.get("revisions") != expected_coverage_revisions
            or feature_state.get("revision") != revision
            or feature_state.get("product_revision") != product_revision
            or feature_state.get("support_revision") != support_revision
            or feature_state.get("evidence_revision") != evidence_revision
            or feature_state.get("feature_verification_eligible") is not True
        ):
            reasons.append("terminal feature coverage aggregate is stale or ineligible")
        else:
            validated_coverage_state = coverage_state_from_validation(
                str(feature_path), feature_value, validation
            )
            expected_terminal_coverage_state = {
                "manifest_path": validated_coverage_state["manifest_path"],
                "manifest_sha256": validated_coverage_state["manifest_sha256"],
                "ac_mapped": validated_coverage_state["ac_mapped"],
                "identities_registered": validated_coverage_state["identities_registered"],
                "automated": validated_coverage_state["automated"],
                "manual": validated_coverage_state["manual"],
            }
    terminal = state.get("handoffs", [])[-1] if state.get("handoffs") else None
    if not terminal:
        reasons.append("controller-generated schema-2 terminal handoff is missing")
    else:
        terminal_path = Path(state["project_root"]) / terminal.get("path", "")
        try:
            terminal_value = read_json(terminal_path)
        except PipelineError:
            terminal_value = {}
        if (
            terminal.get("schema") != 2
            or not terminal_path.is_file()
            or file_sha256(terminal_path) != terminal.get("sha256")
            or terminal_value.get("decision_ids") != state["decision_ledger"]["active_decision_ids"]
            or terminal_value.get("documentation_state")
            != {
                "normative": state["documentation"]["normative"]["status"],
                "derived": state["documentation"]["derived"]["status"],
            }
            or expected_terminal_coverage_state is None
            or terminal_value.get("coverage_state") != expected_terminal_coverage_state
            or terminal_value.get("open_assumptions") != []
        ):
            reasons.append("schema-2 terminal handoff is stale or incomplete")
    machine = state.get("machine_checks", {})
    if (
        machine.get("status") != "pass"
        or machine.get("evidence_revision") != evidence_revision
    ):
        reasons.append("machine checks have not passed on the current revision")
    if open_remediation_required(findings):
        reasons.append("controller-classified remediation-required findings remain unresolved")
    if any(
        item["status"] == "open" and item["severity"] == "minor"
        for item in findings["items"]
    ):
        reasons.append("minor findings require resolution or explicit acceptance")
    clean = state.get("engineer_clean")
    if not clean or clean.get("product_revision") != product_revision:
        reasons.append("read-only convergence has not passed on the current product revision")
    review = state.get("review", {})
    if (
        review.get("status") not in PASSED_REVIEW_STATUSES
        or review.get("product_revision") != product_revision
        or review.get("evidence_revision") != evidence_revision
    ):
        reasons.append("the required final Review has not passed on the current product/evidence identities")
    elif review.get("status") == "passed" and len(review.get("runs", [])) != state.get("required_reviews", 1):
        reasons.append("final review evidence is incomplete")
    elif review.get("status") == "passed_recovery":
        recovery = state.get("recovery") or {}
        if (
            recovery.get("status") != "passed"
            or len(recovery.get("base_review_runs", [])) != state.get("required_reviews", 1)
            or not review.get("recovery_run")
        ):
            reasons.append("evidence recovery review chain is incomplete")
    elif review.get("status") == "passed_targeted":
        closure = state.get("closure_review") or {}
        if (
            closure.get("status") != "passed"
            or not closure.get("run")
            or len(closure.get("base_review_runs", [])) != state.get("required_reviews", 1)
        ):
            reasons.append("targeted product closure review chain is incomplete")
    preflight = state.get("preflight", {})
    proof_error = preflight_proof_error(state)
    if proof_error:
        reasons.append("current versioned preflight proof is invalid: " + proof_error)
    if preflight.get("resource_budget_check") != "pass":
        reasons.append("preflight resource-budget proof has not passed")
    if blocked_preflight_capabilities(state):
        reasons.append("preflight runtime capabilities remain unavailable")
    qa = state.get("qa", {})
    qa_capability = state.get("qa_capability", {})
    if (
        qa_capability.get("status") != "ready"
        or qa_capability.get("probe_id") != qa.get("capability_probe_id")
    ):
        reasons.append("exact-revision QA capability probe has not passed")
    if (
        qa.get("status") != "pass"
        or qa.get("product_revision") != product_revision
        or qa.get("evidence_revision") != evidence_revision
    ):
        reasons.append("feature-focused runtime QA has not passed on current product/evidence")
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
    init.add_argument("--decision-ledger")
    init.add_argument("--integration-owner")
    init.add_argument(
        "--max-consecutive-product-changes",
        "--max-automatic-product-changes",
        dest="max_consecutive_product_changes",
        type=int,
        default=DEFAULT_MAX_CONSECUTIVE_PRODUCT_CHANGES,
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
    preflight.add_argument("--minimum-resume-action", action="append")
    preflight.add_argument("--report", required=True)
    preflight.set_defaults(handler=cmd_preflight_complete)

    reinitialize_preflight = commands.add_parser("reinitialize-preflight")
    add_common_project_root(reinitialize_preflight)
    reinitialize_preflight.add_argument("--reason", required=True)
    reinitialize_preflight.set_defaults(handler=cmd_reinitialize_preflight)

    status = commands.add_parser("status")
    add_common_project_root(status)
    status_mode = status.add_mutually_exclusive_group()
    status_mode.add_argument(
        "--section",
        choices=STATUS_SECTIONS,
        help="Return one bounded diagnostic section plus the deterministic next action",
    )
    status_mode.add_argument(
        "--full",
        action="store_true",
        help="Return the legacy accumulated status payload for diagnostics",
    )
    status.set_defaults(handler=cmd_status)

    authority_rebaseline = commands.add_parser(
        "rebaseline-authority",
        help="atomically bind a freshly approved PRD/spec/plan chain before engineering",
    )
    add_common_project_root(authority_rebaseline)
    authority_rebaseline.add_argument("--recovery-token", required=True)
    authority_rebaseline.add_argument("--reason", required=True)
    authority_rebaseline.add_argument("--authorized-by", required=True)
    authority_rebaseline.add_argument("--requirements", required=True)
    authority_rebaseline.add_argument("--spec", required=True)
    authority_rebaseline.add_argument("--plan", required=True)
    authority_rebaseline.add_argument("--plan-sha256", required=True)
    authority_rebaseline.add_argument("--prd-approval-reference")
    authority_rebaseline.add_argument("--spec-approval-reference")
    authority_rebaseline.add_argument("--plan-approval-reference")
    authority_rebaseline.set_defaults(handler=cmd_rebaseline_authority)

    user_authority = commands.add_parser("user-authority-accept")
    add_common_project_root(user_authority)
    user_authority.add_argument("--authority-id", required=True)
    user_authority.add_argument("--approval-reference", required=True)
    user_authority.add_argument("--statement", required=True)
    user_authority.set_defaults(handler=cmd_user_authority_accept)

    capsule_create = commands.add_parser("context-capsule-create")
    add_common_project_root(capsule_create)
    capsule_create.add_argument("--role", choices=tuple(sorted(CAPSULE_ROLES)), required=True)
    capsule_create.add_argument("--phase", required=True)
    capsule_create.add_argument("--worker-id", required=True)
    capsule_create.add_argument("--plan-sha256", required=True)
    capsule_create.add_argument("--revision", required=True)
    capsule_create.add_argument("--authority", action="append", required=True)
    capsule_create.add_argument("--evidence", action="append")
    capsule_create.add_argument("--decision-id", action="append")
    capsule_create.add_argument("--finding-id", action="append")
    capsule_create.add_argument("--coverage-identity-id", action="append")
    capsule_create.add_argument("--allowed-path", action="append")
    capsule_create.add_argument("--allowed-symbol", action="append")
    capsule_create.add_argument("--exclusion", action="append")
    capsule_create.add_argument("--command", action="append")
    capsule_create.add_argument("--output-path", action="append", required=True)
    capsule_create.add_argument("--stop-condition", required=True)
    for limit in CONTEXT_LIMIT_NAMES:
        capsule_create.add_argument("--" + limit.replace("_", "-"), dest=limit, type=int, required=True)
    capsule_create.add_argument("--output", required=True)
    capsule_create.set_defaults(handler=cmd_context_capsule_create)

    capsule_check = commands.add_parser("context-capsule-check")
    add_common_project_root(capsule_check)
    capsule_check.add_argument("--capsule", required=True)
    capsule_check.set_defaults(handler=cmd_context_capsule_check)

    acquire_lease = commands.add_parser("acquire-write-lease")
    add_common_project_root(acquire_lease)
    acquire_lease.add_argument("--role", choices=tuple(sorted(WRITE_ROLES)), required=True)
    acquire_lease.add_argument("--phase", required=True)
    acquire_lease.add_argument("--write-scope", required=True)
    acquire_lease.add_argument("--worker-id", required=True)
    acquire_lease.add_argument("--capsule", required=True)
    acquire_lease.set_defaults(handler=cmd_acquire_write_lease)

    release_lease = commands.add_parser("release-write-lease")
    add_common_project_root(release_lease)
    release_lease.add_argument("--lease-id", required=True)
    release_lease.add_argument("--result", choices=("incomplete", "blocked", "revoked"), required=True)
    release_lease.add_argument("--reason", required=True)
    release_lease.set_defaults(handler=cmd_release_write_lease)

    legacy_scope = commands.add_parser("recover-legacy-engineer-scope")
    add_common_project_root(legacy_scope)
    legacy_scope.add_argument("--lease-id", required=True)
    legacy_scope.add_argument("--owner-id", required=True)
    legacy_scope.add_argument("--slice-id", required=True)
    legacy_scope.set_defaults(handler=cmd_recover_legacy_engineer_scope)

    prepare_engineer = commands.add_parser("prepare-engineer-continuation")
    add_common_project_root(prepare_engineer)
    prepare_engineer.set_defaults(handler=cmd_prepare_engineer_continuation)

    decision_complete = commands.add_parser("decision-record-complete")
    add_common_project_root(decision_complete)
    decision_complete.add_argument("--recorder-id", required=True)
    decision_complete.add_argument("--lease-id", required=True)
    decision_complete.add_argument("--capsule", required=True)
    decision_complete.add_argument("--semantic-packet", required=True)
    decision_complete.add_argument("--adr-path", action="append")
    decision_complete.add_argument("--report", required=True)
    decision_complete.set_defaults(handler=cmd_decision_record_complete)

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
    research_not_required.add_argument("--reason", required=True)
    research_not_required.set_defaults(handler=cmd_slice_research_not_required)

    coverage_plan = commands.add_parser("coverage-plan-complete")
    add_common_project_root(coverage_plan)
    coverage_plan.add_argument("--slice-id", required=True)
    coverage_plan.add_argument("--coverage-manifest", required=True)
    coverage_plan.add_argument("--report", required=True)
    coverage_plan.set_defaults(handler=cmd_coverage_plan_complete)

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
    engineer.add_argument("--run-id", required=True)
    engineer.add_argument("--owner-id", required=True)
    engineer.add_argument("--lease-id", required=True)
    engineer.add_argument("--capsule", required=True)
    engineer.add_argument("--slice-id", required=True)
    engineer.add_argument("--machine-checks", choices=("pass",), required=True)
    engineer.add_argument("--diff-inspection", choices=("pass",), required=True)
    engineer.add_argument("--semantic-handoff", required=True)
    engineer.add_argument("--report", required=True)
    engineer.add_argument("--scope-approval")
    engineer.add_argument("--resolved-finding", action="append")
    engineer.set_defaults(handler=cmd_engineer_complete)

    coverage_finalize = commands.add_parser("coverage-finalize")
    add_common_project_root(coverage_finalize)
    coverage_finalize.add_argument("--scope-id", required=True)
    coverage_finalize.add_argument("--coverage-manifest", required=True)
    coverage_finalize.add_argument("--expected-actual-equality", choices=("pass",), required=True)
    coverage_finalize.add_argument("--mandatory-registration", choices=("pass",), required=True)
    coverage_finalize.add_argument("--automated-execution", choices=("pass",), required=True)
    coverage_finalize.add_argument("--report", required=True)
    coverage_finalize.set_defaults(handler=cmd_coverage_finalize)

    documentation_complete = commands.add_parser("documentation-complete")
    add_common_project_root(documentation_complete)
    documentation_complete.add_argument("--mode", choices=("normative_pre_review", "derived_post_qa"), required=True)
    documentation_complete.add_argument("--worker-id", required=True)
    documentation_complete.add_argument("--lease-id", required=True)
    documentation_complete.add_argument("--capsule", required=True)
    documentation_complete.add_argument("--semantic-packet", required=True)
    documentation_complete.add_argument("--source-map", required=True)
    documentation_complete.add_argument("--report", required=True)
    documentation_complete.set_defaults(handler=cmd_documentation_complete)

    documentation_not_required = commands.add_parser("documentation-not-required")
    add_common_project_root(documentation_not_required)
    documentation_not_required.add_argument("--mode", choices=("normative_pre_review", "derived_post_qa"), required=True)
    documentation_not_required.add_argument("--plan-sha256", required=True)
    documentation_not_required.add_argument("--policy-evidence", required=True)
    documentation_not_required.set_defaults(handler=cmd_documentation_not_required)

    transfer_owner = commands.add_parser("transfer-engineering-owner")
    add_common_project_root(transfer_owner)
    transfer_owner.add_argument("--from-owner", required=True)
    transfer_owner.add_argument("--to-owner", required=True)
    transfer_owner.add_argument("--reason", required=True)
    transfer_owner.add_argument("--slice-id")
    transfer_owner.set_defaults(handler=cmd_transfer_engineering_owner)

    convergence_audit = commands.add_parser("convergence-audit-complete")
    add_common_project_root(convergence_audit)
    convergence_audit.add_argument("--revision", required=True)
    convergence_audit.add_argument("--product-revision")
    convergence_audit.add_argument("--support-revision")
    convergence_audit.add_argument("--evidence-revision")
    convergence_audit.add_argument("--run-id", required=True)
    convergence_audit.add_argument("--reviewer-id", required=True)
    convergence_audit.add_argument("--capsule", required=True)
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
    review.add_argument("--capsule", required=True)
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
    closure_review.add_argument("--capsule", required=True)
    closure_review.add_argument("--status", choices=("pass", "fail"), required=True)
    closure_review.add_argument("--report", required=True)
    closure_review.add_argument("--credit-manifest", required=True)
    closure_review.set_defaults(handler=cmd_closure_review_complete)

    recover_ready_closure = commands.add_parser(
        "recover-ready-targeted-closure-clean"
    )
    add_common_project_root(recover_ready_closure)
    recover_ready_closure.set_defaults(
        handler=cmd_recover_ready_targeted_closure_clean
    )

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
        "--blocks-required-support-contract",
        choices=("true", "false"),
        default="false",
    )
    add_finding.add_argument("--required-support-contract-evidence")
    add_finding.add_argument(
        "--mandatory-core-acceptance-evidence-missing",
        choices=("true", "false"),
        required=True,
    )
    add_finding.add_argument(
        "--test-can-miss-product-defect", choices=("true", "false"), required=True
    )
    add_finding.add_argument("--deferred-reference")
    add_finding.add_argument("--coverage-identity-id", action="append", default=[])
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

    accept = commands.add_parser("accept-finding")
    add_common_project_root(accept)
    accept.add_argument("--id", required=True)
    accept.add_argument("--reason", required=True)
    accept.add_argument("--revision", required=True)
    accept.add_argument("--authority-id", required=True)
    accept.add_argument("--approval-reference")
    accept.set_defaults(handler=cmd_accept_finding)

    remediation = commands.add_parser(
        "recovery-remediation-complete",
        aliases=["evidence-remediation-complete"],
    )
    add_common_project_root(remediation)
    remediation.add_argument("--run-id", required=True)
    remediation.add_argument("--worker-id", required=True)
    remediation.add_argument("--lease-id", required=True)
    remediation.add_argument("--capsule", required=True)
    remediation.add_argument("--machine-checks", choices=("pass",), required=True)
    remediation.add_argument("--semantic-report", required=True)
    remediation.add_argument("--coverage-manifest", required=True)
    remediation.add_argument("--report", required=True)
    remediation.add_argument("--resolved-finding", action="append", required=True)
    remediation.set_defaults(handler=cmd_evidence_remediation_complete)

    recovery_review = commands.add_parser("recovery-review-complete")
    add_common_project_root(recovery_review)
    recovery_review.add_argument("--revision", required=True)
    recovery_review.add_argument("--product-revision", required=True)
    recovery_review.add_argument("--support-revision", required=True)
    recovery_review.add_argument("--evidence-revision", required=True)
    recovery_review.add_argument("--run-id", required=True)
    recovery_review.add_argument("--reviewer-id", required=True)
    recovery_review.add_argument("--capsule", required=True)
    recovery_review.add_argument("--status", choices=("pass", "fail"), required=True)
    recovery_review.add_argument("--report", required=True)
    recovery_review.add_argument("--credit-manifest", required=True)
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
    qa.add_argument("--capsule", required=True)
    qa.add_argument("--status", choices=tuple(sorted(QA_STATUSES)), required=True)
    qa.add_argument("--manual-execution", required=True)
    qa.add_argument("--report", required=True)
    qa.add_argument("--reason")
    qa.add_argument("--pending-identity", action="append")
    qa.set_defaults(handler=cmd_qa_complete)

    documentation_review = commands.add_parser("documentation-review-complete")
    add_common_project_root(documentation_review)
    documentation_review.add_argument("--revision", required=True)
    documentation_review.add_argument("--product-revision", required=True)
    documentation_review.add_argument("--support-revision", required=True)
    documentation_review.add_argument("--evidence-revision", required=True)
    documentation_review.add_argument("--run-id", required=True)
    documentation_review.add_argument("--reviewer-id", required=True)
    documentation_review.add_argument("--capsule", required=True)
    documentation_review.add_argument("--status", choices=("pass", "fail"), required=True)
    documentation_review.add_argument("--report", required=True)
    documentation_review.add_argument("--credit-manifest", required=True)
    documentation_review.set_defaults(handler=cmd_documentation_review_complete)

    ready = commands.add_parser("ready")
    add_common_project_root(ready)
    ready.set_defaults(handler=cmd_ready)
    commands.metavar = "{" + ",".join(sorted(commands.choices)) + "}"
    return parser


def main(argv: list[str] | None = None) -> int:
    global _COMMAND_SOURCE_INVENTORY
    args = build_parser().parse_args(argv)
    _COMMAND_SOURCE_INVENTORY = {}
    try:
        return args.handler(args)
    except PipelineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        _COMMAND_SOURCE_INVENTORY = None


if __name__ == "__main__":
    raise SystemExit(main())
