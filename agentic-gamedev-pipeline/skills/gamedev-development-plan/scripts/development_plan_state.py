#!/usr/bin/env python3
"""Deterministic controller and validator for development-plan approval."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from capability_contract import parse_capability_ids
except ImportError:  # pragma: no cover - importlib loading from the pipeline controller
    _capability_path = Path(__file__).with_name("capability_contract.py")
    _capability_spec = importlib.util.spec_from_file_location(
        "gamedev_capability_contract", _capability_path
    )
    if _capability_spec is None or _capability_spec.loader is None:
        raise
    _capability_module = importlib.util.module_from_spec(
        _capability_spec
    )
    _capability_spec.loader.exec_module(_capability_module)
    parse_capability_ids = _capability_module.parse_capability_ids


SCHEMA_VERSION = 1
STATE_RELATIVE_PATH = Path(".agentic-pipeline/development-plan-state.json")
SPEC_STATE_RELATIVE_PATH = Path(".agentic-pipeline/specification-state.json")
MODES = {"single_owner", "sequential_slices"}
REQUIRED_GLOBAL_SECTIONS = {
    "Decision",
    "Planning Analysis",
    "Scope Boundaries",
    "Decision Ledger",
    "Coverage Strategy",
    "Documentation Strategy",
    "Context Budget",
}
REQUIRED_SLICE_SECTIONS = {
    "Vertical Outcome",
    "Requirements",
    "Dependencies",
    "Base Contract",
    "Handoff Contract",
    "Owned Paths",
    "Expected Paths",
    "Forbidden Scope",
    "Scope Contract",
    "Research Briefs",
    "Coverage Contract",
    "Documentation Contract",
    "Context Capsule Budget",
    "Verification and Exit Criteria",
    "Rollback and Recovery",
    "Downstream Consumers",
}
REQUIRED_SCOPE_FIELDS = {
    "acceptance_ids",
    "editable_paths",
    "shared_touchpoints",
    "excluded_components",
    "excluded_paths",
    "max_product_files",
    "max_product_lines_changed",
    "verification_scope",
    "scope_baseline_revision",
}
REQUIRED_RESEARCH_FIELDS = {"question", "paths", "exclusions", "evidence", "stop"}
CONTEXT_LIMITS = {
    "max_authority_files",
    "max_evidence_files",
    "max_total_files",
    "max_payload_bytes",
    "max_estimated_tokens",
}
CONTEXT_METRIC_SCOPE = "capsule_plus_referenced_files"


class DevelopmentPlanError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_slug(feature: str) -> str:
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", feature):
        raise DevelopmentPlanError("feature must be a lowercase hyphen slug")
    return feature


def parse_frontmatter(path: Path, label: str) -> tuple[dict[str, str], str]:
    if not path.is_file():
        raise DevelopmentPlanError(f"{label} does not exist: {path}")
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise DevelopmentPlanError(f"{label} must start with YAML frontmatter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise DevelopmentPlanError(f"{label} has unterminated frontmatter")
    fields: dict[str, str] = {}
    parent: str | None = None
    for line in parts[1].splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        indentation = len(line) - len(line.lstrip())
        key, value = line.strip().split(":", 1)
        value = value.strip().strip("\"'")
        if indentation == 0:
            parent = key if not value else None
            if value:
                fields[key] = value
        elif parent and value:
            fields[f"{parent}.{key}"] = value
    return fields, parts[2].lstrip("\r\n")


def resolve_project_path(root: Path, supplied: str, label: str) -> Path:
    path = Path(supplied)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise DevelopmentPlanError(
            f"{label} must stay inside the project root: {path}"
        ) from error
    return path


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


def state_path(root: Path) -> Path:
    return root / STATE_RELATIVE_PATH


def load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise DevelopmentPlanError(f"{label} does not exist: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise DevelopmentPlanError(f"{label} must contain a JSON object")
    return data


def load_state(root: Path) -> dict[str, Any]:
    state = load_json(state_path(root), "development-plan state")
    if state.get("schema_version") != SCHEMA_VERSION:
        raise DevelopmentPlanError("unsupported development-plan state schema")
    return state


def save_state(root: Path, state: dict[str, Any]) -> None:
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def require_sources(
    root: Path,
    feature: str,
    prd_path: str,
    spec_path: str,
    plan_path: str,
    decision_ledger_path: str,
) -> dict[str, Any]:
    prd = resolve_project_path(root, prd_path, "PRD")
    spec = resolve_project_path(root, spec_path, "specification")
    plan = resolve_project_path(root, plan_path, "development plan")
    decision_ledger = resolve_project_path(
        root, decision_ledger_path, "decision ledger"
    )
    if decision_ledger.exists() and not decision_ledger.is_file():
        raise DevelopmentPlanError("decision ledger path must be a file or a creatable file path")
    prd_meta, _ = parse_frontmatter(prd, "PRD")
    if prd_meta.get("document_type") != "product-requirements":
        raise DevelopmentPlanError("PRD document_type must be product-requirements")
    if prd_meta.get("status") != "approved" or not prd_meta.get("revision"):
        raise DevelopmentPlanError("PRD must have approved status and a revision")

    spec_meta, _ = parse_frontmatter(spec, "specification")
    if spec_meta.get("document_type") != "technical-specification":
        raise DevelopmentPlanError("specification document_type must be technical-specification")
    if spec_meta.get("status") != "approved" or not spec_meta.get("revision"):
        raise DevelopmentPlanError("specification must have approved status and a revision")

    prd_hash = sha256(prd)
    spec_hash = sha256(spec)
    expected_prd_path = prd.relative_to(root).as_posix()
    spec_product_trace = authority_trace(
        spec_meta, "source_prd", ("product_authority",)
    )
    if spec_product_trace != {
        "path": expected_prd_path,
        "revision": prd_meta["revision"],
        "sha256": prd_hash,
    }:
        raise DevelopmentPlanError("specification does not trace the exact current approved PRD")

    specification_state = load_json(root / SPEC_STATE_RELATIVE_PATH, "specification state")
    ready = specification_state.get("ready") or {}
    if specification_state.get("feature") != feature or specification_state.get("status") != "spec_ready":
        raise DevelopmentPlanError("specification state is not SPEC_READY for this feature")
    if (
        specification_state.get("prd", {}).get("path") != expected_prd_path
        or specification_state.get("specification", {}).get("path")
        != spec.relative_to(root).as_posix()
    ):
        raise DevelopmentPlanError(
            "SPEC_READY evidence refers to different repository-owned artifact paths"
        )
    if ready.get("prd_sha256") != prd_hash or ready.get("spec_sha256") != spec_hash:
        raise DevelopmentPlanError("SPEC_READY evidence does not match current PRD/specification bytes")

    return {
        "prd": {
            "path": expected_prd_path,
            "revision": prd_meta["revision"],
            "sha256": prd_hash,
        },
        "specification": {
            "path": spec.relative_to(root).as_posix(),
            "revision": spec_meta["revision"],
            "sha256": spec_hash,
        },
        "plan_path": plan.relative_to(root).as_posix(),
        "decision_ledger_path": decision_ledger.relative_to(root).as_posix(),
    }


def source_drift(root: Path, state: dict[str, Any]) -> list[str]:
    try:
        current = require_sources(
            root,
            state["feature"],
            state["prd"]["path"],
            state["specification"]["path"],
            state["plan_path"],
            state["decision_ledger_path"],
        )
    except (OSError, ValueError, json.JSONDecodeError, DevelopmentPlanError) as error:
        return [str(error)]
    drift: list[str] = []
    for key in ("prd", "specification"):
        for field in ("path", "revision", "sha256"):
            if current[key][field] != state[key][field]:
                drift.append(
                    f"{key}.{field}: expected {state[key][field]!r}, got {current[key][field]!r}"
                )
    return drift


def require_current_sources(root: Path, state: dict[str, Any]) -> None:
    drift = source_drift(root, state)
    if drift:
        state["status"] = "stale"
        state["drift"] = drift
        state["updated_at"] = utc_now()
        save_state(root, state)
        raise DevelopmentPlanError("development plan is stale: " + "; ".join(drift))


def section_map(body: str, level: int) -> dict[str, str]:
    prefix = "#" * level
    pattern = re.compile(
        rf"(?ms)^{re.escape(prefix)} ([^\r\n]+)\r?\n(.*?)(?=^{re.escape(prefix)} |\Z)"
    )
    return {name.strip(): content.strip() for name, content in pattern.findall(body)}


def slice_blocks(body: str) -> list[tuple[str, str]]:
    pattern = re.compile(r"(?ms)^## Slice (SLICE-\d{3})\r?\n(.*?)(?=^## |\Z)")
    return [(slice_id, content.strip()) for slice_id, content in pattern.findall(body)]


def require_nonempty(section: str, slice_id: str, errors: list[str]) -> None:
    if not section or not re.search(r"[A-Za-zА-Яа-я0-9]", section):
        errors.append(f"{slice_id} has an empty required section")


def validate_plan(root: Path, state: dict[str, Any], required_status: str = "draft") -> dict[str, Any]:
    require_current_sources(root, state)
    plan = root / state["plan_path"]
    meta, body = parse_frontmatter(plan, "development plan")
    errors: list[str] = []
    expected_meta = {
        "document_type": "development-plan",
        "status": required_status,
        "feature": state["feature"],
        "mode": state.get("analysis", {}).get("mode"),
        "writer_strategy": "sequential",
        "planning_analyst_id": state["analyst_id"],
    }
    for key, value in expected_meta.items():
        if meta.get(key) != value:
            errors.append(f"frontmatter {key}: expected {value!r}, got {meta.get(key)!r}")
    product_trace = authority_trace(meta, "source_prd", ("product_authority",))
    specification_trace = authority_trace(
        meta,
        "source_spec",
        ("specification_authority", "technical_authority"),
    )
    for label, actual, expected in (
        (
            "product authority",
            product_trace,
            {
                "path": state["prd"]["path"],
                "revision": state["prd"]["revision"],
                "sha256": state["prd"]["sha256"],
            },
        ),
        (
            "specification authority",
            specification_trace,
            {
                "path": state["specification"]["path"],
                "revision": state["specification"]["revision"],
                "sha256": state["specification"]["sha256"],
            },
        ),
    ):
        for field, expected_value in expected.items():
            if actual.get(field) != expected_value:
                errors.append(
                    f"frontmatter {label} {field}: expected {expected_value!r}, "
                    f"got {actual.get(field)!r}"
                )
    if not re.fullmatch(r"[1-9][0-9]*", meta.get("revision", "")):
        errors.append("frontmatter revision must be a positive integer")
    if meta.get("mode") not in MODES:
        errors.append("frontmatter mode is invalid")
    if required_status == "draft" and ("approved_by" in meta or "approved_at" in meta):
        errors.append("draft frontmatter cannot contain approval metadata")
    if required_status == "approved":
        if meta.get("approved_by") != "user":
            errors.append("approved frontmatter must record approved_by: user")
        if not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00", meta.get("approved_at", "")
        ):
            errors.append("approved_at must be a UTC controller timestamp")

    global_sections = section_map(body, 2)
    for name in sorted(REQUIRED_GLOBAL_SECTIONS):
        if not global_sections.get(name):
            errors.append(f"missing or empty global section: {name}")
    if not re.search(
        r"(?im)^Writer sequencing:\s*one-at-a-time\s*$",
        global_sections.get("Decision", ""),
    ):
        errors.append("Decision must declare Writer sequencing: one-at-a-time")
    if not re.search(
        r"(?im)^Ownership meaning:\s*phase-scoped write lease\s*$",
        global_sections.get("Decision", ""),
    ):
        errors.append("Decision must declare Ownership meaning: phase-scoped write lease")

    ledger_path = meta.get("decision_ledger_path")
    if ledger_path != state.get("decision_ledger_path"):
        errors.append(
            "frontmatter decision_ledger_path must equal the resolved repository-owned ledger path"
        )
    ledger_section = global_sections.get("Decision Ledger", "")
    if state.get("decision_ledger_path") not in ledger_section:
        errors.append("Decision Ledger must name the exact resolved ledger path")
    if not re.search(r"\bDEC-[A-Za-z0-9-]+\b|\bnone\b", ledger_section, re.I):
        errors.append("Decision Ledger must list active DEC-* IDs or none")
    if "Decision Recorder" not in ledger_section:
        errors.append("Decision Ledger must state the Decision Recorder route")

    def validate_context_budget(section: str, label: str) -> dict[str, int]:
        found: dict[str, int] = {}
        seen: set[str] = set()
        for key, raw in re.findall(r"(?m)^\s*-\s*([a-z_]+):\s*([0-9]+)\s*$", section):
            if key.startswith("max_") and key not in CONTEXT_LIMITS:
                errors.append(f"{label} contains unsupported numeric limit: {key}")
            if key in CONTEXT_LIMITS:
                if key in seen:
                    errors.append(f"{label} repeats numeric limit: {key}")
                seen.add(key)
                found[key] = int(raw)
        missing = sorted(CONTEXT_LIMITS - set(found))
        if missing:
            errors.append(f"{label} lacks numeric limits: {', '.join(missing)}")
        nonpositive = sorted(key for key, value in found.items() if value < 1)
        if nonpositive:
            errors.append(f"{label} limits must be positive: {', '.join(nonpositive)}")
        if found.get("max_total_files", 0) < max(
            found.get("max_authority_files", 0), found.get("max_evidence_files", 0)
        ):
            errors.append(f"{label} max_total_files cannot be smaller than a component file limit")
        metric_scopes = re.findall(
            r"(?m)^\s*-\s*metric_scope:\s*(\S(?:.*\S)?)\s*$", section
        )
        if len(metric_scopes) != 1:
            errors.append(f"{label} requires exactly one metric_scope")
        elif metric_scopes[0] != CONTEXT_METRIC_SCOPE:
            errors.append(
                f"{label} metric_scope must be {CONTEXT_METRIC_SCOPE}"
            )
        return found

    global_context_budget = validate_context_budget(
        global_sections.get("Context Budget", ""), "Context Budget"
    )
    coverage_strategy = global_sections.get("Coverage Strategy", "")
    for required_text in (
        "manifest_path",
        "automated_identity_namespace",
        "manual_identity_namespace",
        "mandatory_rule",
        "capability_prerequisites",
        "plan-before-engineering",
        "finalize-after-code-freeze",
    ):
        if required_text not in coverage_strategy:
            errors.append(f"Coverage Strategy must contain {required_text}")
    global_capability_values = re.findall(
        r"(?m)^\s*-\s*capability_prerequisites:\s*(\S(?:.*\S)?)\s*$",
        coverage_strategy,
    )
    if len(global_capability_values) != 1:
        errors.append("Coverage Strategy requires exactly one capability_prerequisites field")
    else:
        try:
            parse_capability_ids(
                global_capability_values[0],
                label="Coverage Strategy capability_prerequisites",
            )
        except ValueError as exc:
            errors.append(str(exc))
    documentation_strategy = global_sections.get("Documentation Strategy", "")
    for required_text in ("normative_pre_review", "derived_post_qa"):
        if required_text not in documentation_strategy:
            errors.append(f"Documentation Strategy must contain {required_text}")

    slices = slice_blocks(body)
    slice_ids = [item[0] for item in slices]
    expected_ids = [f"SLICE-{number:03d}" for number in range(1, len(slices) + 1)]
    if slice_ids != expected_ids:
        errors.append("slice IDs must be unique, contiguous, and ordered from SLICE-001")
    try:
        declared_count = int(meta.get("slice_count", ""))
    except ValueError:
        declared_count = -1
    if declared_count != len(slices):
        errors.append("frontmatter slice_count must equal the number of slices")
    mode = meta.get("mode")
    if mode == "single_owner" and len(slices) != 1:
        errors.append("single_owner requires exactly one slice")
    if mode == "sequential_slices" and len(slices) < 2:
        errors.append("sequential_slices requires at least two slices")
    if mode == "single_owner":
        milestones = global_sections.get("Integration Milestones", "")
        if not re.search(r"(?m)^\s*-\s*MILESTONE-\d{3}\b", milestones):
            errors.append("single_owner requires at least one Integration Milestones entry")

    for index, (slice_id, content) in enumerate(slices):
        sections = section_map(content, 3)
        for name in sorted(REQUIRED_SLICE_SECTIONS):
            if name not in sections:
                errors.append(f"{slice_id} is missing section: {name}")
            else:
                require_nonempty(sections[name], slice_id, errors)
        outcome = sections.get("Vertical Outcome", "")
        if not re.search(r"(?im)^End-to-end:\s*yes\s*$", outcome):
            errors.append(f"{slice_id} must declare End-to-end: yes")
        if not re.search(r"(?im)^Observable result:\s*\S", outcome):
            errors.append(f"{slice_id} must state an Observable result")
        requirements = sections.get("Requirements", "")
        if not re.search(r"\bPRD-REQ-[A-Za-z0-9-]+\b", requirements):
            errors.append(f"{slice_id} must map at least one PRD-REQ")
        if not re.search(r"\bPRD-AC-[A-Za-z0-9-]+\b", requirements):
            errors.append(f"{slice_id} must map at least one PRD-AC")

        dependency_ids = re.findall(r"\bSLICE-\d{3}\b", sections.get("Dependencies", ""))
        allowed_dependencies = set(slice_ids[:index])
        if index == 0 and dependency_ids:
            errors.append(f"{slice_id} cannot depend on another slice")
        if index > 0 and not dependency_ids:
            errors.append(f"{slice_id} must depend on at least one earlier slice")
        invalid_dependencies = sorted(set(dependency_ids) - allowed_dependencies)
        if invalid_dependencies:
            errors.append(f"{slice_id} has non-earlier dependencies: {', '.join(invalid_dependencies)}")

        scope = sections.get("Scope Contract", "")
        found_scope_fields = set(re.findall(r"(?m)^\s*-\s*([a-z_]+):\s*\S", scope))
        missing_scope = sorted(REQUIRED_SCOPE_FIELDS - found_scope_fields)
        if missing_scope:
            errors.append(f"{slice_id} scope contract lacks: {', '.join(missing_scope)}")
        if not re.search(
            r"(?m)^\s*-\s*acceptance_ids:\s*.*\bPRD-AC-[A-Za-z0-9-]+\b", scope
        ):
            errors.append(f"{slice_id} acceptance_ids must contain at least one PRD-AC")
        scope_acceptance = set(
            re.findall(
                r"\bPRD-AC-[A-Za-z0-9-]+\b",
                next(
                    (
                        value
                        for key, value in re.findall(
                            r"(?m)^\s*-\s*([a-z_]+):\s*(.+?)\s*$", scope
                        )
                        if key == "acceptance_ids"
                    ),
                    "",
                ),
            )
        )
        requirement_acceptance = set(
            re.findall(r"\bPRD-AC-[A-Za-z0-9-]+\b", requirements)
        )
        if not scope_acceptance.issubset(requirement_acceptance):
            errors.append(f"{slice_id} scope acceptance_ids must appear in Requirements")
        touchpoints = re.findall(
            r"(?m)^\s*-\s*shared_touchpoint:\s*(TP-\d{3})\s*\|\s*(.+)$", scope
        )
        if not touchpoints:
            errors.append(f"{slice_id} requires at least one structured shared_touchpoint")
        seen_touchpoint_ids: set[str] = set()
        seen_touchpoint_paths: set[str] = set()
        for touchpoint_id, fields_text in touchpoints:
            fields = {
                part.split("=", 1)[0].strip(): part.split("=", 1)[1].strip()
                for part in fields_text.split("|")
                if "=" in part and part.split("=", 1)[1].strip()
            }
            missing = sorted(
                {"path", "symbols", "allowed_change", "forbidden_change"} - fields.keys()
            )
            if missing:
                errors.append(
                    f"{slice_id} {touchpoint_id} lacks: {', '.join(missing)}"
                )
            if touchpoint_id in seen_touchpoint_ids:
                errors.append(f"{slice_id} repeats shared touchpoint ID {touchpoint_id}")
            seen_touchpoint_ids.add(touchpoint_id)
            touchpoint_path = fields.get("path")
            if touchpoint_path in seen_touchpoint_paths:
                errors.append(
                    f"{slice_id} repeats shared touchpoint path {touchpoint_path}"
                )
            if touchpoint_path:
                seen_touchpoint_paths.add(touchpoint_path)
        for budget in ("max_product_files", "max_product_lines_changed"):
            match = re.search(rf"(?m)^\s*-\s*{budget}:\s*([0-9]+)\s*$", scope)
            if not match or int(match.group(1)) < 1:
                errors.append(f"{slice_id} {budget} must be a positive integer")

        research_section = sections.get("Research Briefs", "")
        research_rows = re.findall(
            r"(?m)^\s*-\s*(RESEARCH-\d{3})\s*\|\s*(.+)$",
            research_section,
        )
        research_not_required = re.findall(
            r"(?m)^\s*-\s*research_not_required\s*\|\s*reason=(\S.*?)\s*$",
            research_section,
        )
        if research_rows and research_not_required:
            errors.append(
                f"{slice_id} Research Briefs must choose briefs or research_not_required, not both"
            )
        elif not research_rows and len(research_not_required) != 1:
            errors.append(
                f"{slice_id} requires structured research briefs or one exact "
                "research_not_required | reason=<source-backed reason> sentinel"
            )
        elif research_not_required and research_not_required[0] in {
            "EXACT_SOURCE_BACKED_REASON",
            "placeholder",
            "none",
        }:
            errors.append(f"{slice_id} research_not_required requires a concrete reason")
        for research_id, fields_text in research_rows:
            found = {
                part.split("=", 1)[0].strip()
                for part in fields_text.split("|")
                if "=" in part and part.split("=", 1)[1].strip()
            }
            missing = sorted(REQUIRED_RESEARCH_FIELDS - found)
            if missing:
                errors.append(f"{slice_id} {research_id} lacks: {', '.join(missing)}")

        coverage = sections.get("Coverage Contract", "")
        for required_text in (
            "acceptance_ids",
            "automated_identity_namespace",
            "manual_identity_namespace",
            "mandatory_identity_ids",
            "automation_feasibility",
            "capability_prerequisites",
            "planned_manifest",
            "finalized_manifest",
            "amendment_authorities",
        ):
            if required_text not in coverage:
                errors.append(f"{slice_id} Coverage Contract must contain {required_text}")
        slice_capability_values = re.findall(
            r"(?m)^\s*-\s*capability_prerequisites:\s*(\S(?:.*\S)?)\s*$",
            coverage,
        )
        if len(slice_capability_values) != 1:
            errors.append(
                f"{slice_id} Coverage Contract requires exactly one capability_prerequisites field"
            )
        else:
            try:
                parse_capability_ids(
                    slice_capability_values[0],
                    label=f"{slice_id} Coverage Contract capability_prerequisites",
                )
            except ValueError as exc:
                errors.append(str(exc))
        documentation = sections.get("Documentation Contract", "")
        for required_text in (
            "normative_pre_review_paths",
            "derived_post_qa_paths",
            "decision_ids",
            "evidence_sources",
        ):
            if required_text not in documentation:
                errors.append(f"{slice_id} Documentation Contract must contain {required_text}")
        capsule_budget = sections.get("Context Capsule Budget", "")
        slice_context_budget = validate_context_budget(
            capsule_budget, f"{slice_id} Context Capsule Budget"
        )
        exceeded = sorted(
            key
            for key, value in slice_context_budget.items()
            if key in global_context_budget and value > global_context_budget[key]
        )
        if exceeded:
            errors.append(
                f"{slice_id} Context Capsule Budget exceeds global limits: "
                + ", ".join(exceeded)
            )
        if "authority_paths" not in capsule_budget or "evidence_paths" not in capsule_budget:
            errors.append(
                f"{slice_id} Context Capsule Budget must bound authority_paths and evidence_paths"
            )
        handoff = sections.get("Handoff Contract", "")
        for required_text in (
            "schema-2",
            "decision_ids",
            "coverage_state",
            "documentation_state",
            "open_assumptions",
        ):
            if required_text not in handoff:
                errors.append(f"{slice_id} Handoff Contract must contain {required_text}")

    if errors:
        raise DevelopmentPlanError("invalid development plan: " + "; ".join(errors))
    return {
        "path": plan.relative_to(root).as_posix(),
        "sha256": sha256(plan),
        "status": meta["status"],
        "mode": meta["mode"],
        "slice_ids": slice_ids,
    }


def command_init(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root).resolve()
    feature = require_slug(args.feature)
    requested_paths = (
        resolve_project_path(root, args.prd, "PRD").relative_to(root).as_posix(),
        resolve_project_path(root, args.spec, "specification").relative_to(root).as_posix(),
        resolve_project_path(root, args.plan, "development plan").relative_to(root).as_posix(),
        resolve_project_path(root, args.decision_ledger, "decision ledger")
        .relative_to(root)
        .as_posix(),
    )
    if state_path(root).is_file():
        state = load_state(root)
        if state["feature"] != feature:
            raise DevelopmentPlanError("development-plan state already belongs to another feature")
        recorded_paths = (
            state["prd"]["path"],
            state["specification"]["path"],
            state["plan_path"],
            state["decision_ledger_path"],
        )
        if requested_paths != recorded_paths:
            raise DevelopmentPlanError(
                "development-plan state already exists with different repository-owned paths"
            )
        drift = source_drift(root, state)
        if drift:
            state["status"] = "stale"
            state["drift"] = drift
            state["updated_at"] = utc_now()
            save_state(root, state)
        return state
    if not args.analyst_id.strip():
        raise DevelopmentPlanError("a fresh Planning Analyst identity is required")
    sources = require_sources(root, feature, *requested_paths)
    now = utc_now()
    state = {
        "schema_version": SCHEMA_VERSION,
        "feature": feature,
        "status": "analyzing",
        "analyst_id": args.analyst_id,
        "prd": sources["prd"],
        "specification": sources["specification"],
        "plan_path": sources["plan_path"],
        "decision_ledger_path": sources["decision_ledger_path"],
        "analysis": None,
        "submission": None,
        "approval": None,
        "drift": [],
        "history": [],
        "created_at": now,
        "updated_at": now,
    }
    save_state(root, state)
    return state


def command_reinitialize(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root).resolve()
    state = load_state(root)
    if state["status"] != "stale":
        raise DevelopmentPlanError("reinitialize is allowed only from stale state")
    prior_analyst_ids = {state["analyst_id"]} | {
        item.get("analyst_id")
        for item in state.get("history", [])
        if item.get("analyst_id")
    }
    if not args.analyst_id.strip() or args.analyst_id in prior_analyst_ids:
        raise DevelopmentPlanError(
            "reinitialize requires a Planning Analyst identity fresh across all planning history"
        )
    sources = require_sources(
        root,
        state["feature"],
        getattr(args, "prd", None) or state["prd"]["path"],
        getattr(args, "spec", None) or state["specification"]["path"],
        getattr(args, "plan", None) or state["plan_path"],
        getattr(args, "decision_ledger", None) or state["decision_ledger_path"],
    )
    now = utc_now()
    history = list(state.get("history", []))
    history.append(
        {
            key: value
            for key, value in state.items()
            if key not in {"schema_version", "feature", "history"}
        }
    )
    renewed = {
        "schema_version": SCHEMA_VERSION,
        "feature": state["feature"],
        "status": "analyzing",
        "analyst_id": args.analyst_id,
        "prd": sources["prd"],
        "specification": sources["specification"],
        "plan_path": sources["plan_path"],
        "decision_ledger_path": sources["decision_ledger_path"],
        "analysis": None,
        "submission": None,
        "approval": None,
        "drift": [],
        "history": history,
        "created_at": now,
        "updated_at": now,
    }
    save_state(root, renewed)
    return renewed


def command_accept_analysis(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root).resolve()
    state = load_state(root)
    if state["status"] != "analyzing":
        raise DevelopmentPlanError(f"cannot accept analysis in {state['status']}")
    require_current_sources(root, state)
    if args.analyst_id != state["analyst_id"]:
        raise DevelopmentPlanError("analysis must come from the assigned fresh Planning Analyst")
    if args.mode not in MODES:
        raise DevelopmentPlanError("mode must be single_owner or sequential_slices")
    for label, value in (
        ("rationale", args.rationale),
        ("working-set estimate", args.working_set),
        ("seams assessment", args.seams_assessment),
    ):
        if not value.strip():
            raise DevelopmentPlanError(f"{label} is required")
    state["analysis"] = {
        "mode": args.mode,
        "rationale": args.rationale,
        "working_set": args.working_set,
        "seams_assessment": args.seams_assessment,
        "recorded_at": utc_now(),
    }
    state["status"] = "drafting"
    state["updated_at"] = utc_now()
    save_state(root, state)
    return state


def command_validate(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root).resolve()
    state = load_state(root)
    if not state.get("analysis"):
        raise DevelopmentPlanError("Planning Analyst decision has not been accepted")
    required_status = "approved" if state["status"] == "approved" else "draft"
    result = validate_plan(root, state, required_status)
    if state["status"] == "approved":
        approval = state.get("approval") or {}
        if result["sha256"] != approval.get("approved_sha256"):
            raise DevelopmentPlanError("approved plan changed after user approval")
    return result


def command_submit(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root).resolve()
    state = load_state(root)
    if state["status"] not in {"drafting", "awaiting_user_approval"}:
        raise DevelopmentPlanError(f"cannot submit plan in {state['status']}")
    result = validate_plan(root, state, "draft")
    state["submission"] = {**result, "submitted_at": utc_now()}
    state["approval"] = None
    state["status"] = "awaiting_user_approval"
    state["updated_at"] = utc_now()
    save_state(root, state)
    return state


def promote_plan(plan: Path, approved_by: str, approved_at: str) -> None:
    text = plan.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    lines = parts[1].splitlines()
    updated: list[str] = []
    for line in lines:
        if re.match(r"^(approved_by|approved_at)\s*:", line):
            continue
        if re.match(r"^status\s*:", line):
            updated.append("status: approved")
        else:
            updated.append(line)
    updated.extend([f"approved_by: {approved_by}", f"approved_at: {approved_at}"])
    new_text = "---\n" + "\n".join(updated).strip() + "\n---\n" + parts[2].lstrip("\r\n")
    temporary = plan.with_suffix(".tmp")
    temporary.write_text(new_text, encoding="utf-8")
    os.replace(temporary, plan)


def command_approve(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root).resolve()
    state = load_state(root)
    if state["status"] != "awaiting_user_approval" or not state.get("submission"):
        raise DevelopmentPlanError("approval requires a submitted draft")
    require_current_sources(root, state)
    if args.approved_by != "user":
        raise DevelopmentPlanError("only explicit user approval may promote the plan")
    if not args.approval_note.strip():
        raise DevelopmentPlanError("approval note is required")
    plan = root / state["plan_path"]
    if sha256(plan) != state["submission"]["sha256"]:
        raise DevelopmentPlanError("draft changed after submission; resubmit before approval")
    approved_at = utc_now()
    promote_plan(plan, args.approved_by, approved_at)
    result = validate_plan(root, state, "approved")
    state["approval"] = {
        "approved_by": args.approved_by,
        "approval_note": args.approval_note,
        "submitted_sha256": state["submission"]["sha256"],
        "approved_sha256": result["sha256"],
        "approved_at": approved_at,
    }
    state["status"] = "approved"
    state["updated_at"] = utc_now()
    save_state(root, state)
    return state


def command_status(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root).resolve()
    state = load_state(root)
    drift = source_drift(root, state)
    if drift and state["status"] != "stale":
        state["status"] = "stale"
        state["drift"] = drift
        state["updated_at"] = utc_now()
        save_state(root, state)
    return state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init")
    init.add_argument("--feature", required=True)
    init.add_argument("--prd", required=True)
    init.add_argument("--spec", required=True)
    init.add_argument("--plan", required=True)
    init.add_argument("--decision-ledger", required=True)
    init.add_argument("--analyst-id", required=True)
    init.set_defaults(handler=command_init)

    reinitialize = commands.add_parser("reinitialize")
    reinitialize.add_argument("--analyst-id", required=True)
    reinitialize.add_argument("--prd")
    reinitialize.add_argument("--spec")
    reinitialize.add_argument("--plan")
    reinitialize.add_argument("--decision-ledger")
    reinitialize.set_defaults(handler=command_reinitialize)

    analysis = commands.add_parser("accept-analysis")
    analysis.add_argument("--analyst-id", required=True)
    analysis.add_argument("--mode", required=True, choices=sorted(MODES))
    analysis.add_argument("--rationale", required=True)
    analysis.add_argument("--working-set", required=True)
    analysis.add_argument("--seams-assessment", required=True)
    analysis.set_defaults(handler=command_accept_analysis)

    validate = commands.add_parser("validate-plan")
    validate.set_defaults(handler=command_validate)

    submit = commands.add_parser("submit")
    submit.set_defaults(handler=command_submit)

    approve = commands.add_parser("approve")
    approve.add_argument("--approved-by", required=True)
    approve.add_argument("--approval-note", required=True)
    approve.set_defaults(handler=command_approve)

    status = commands.add_parser("status")
    status.set_defaults(handler=command_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.handler(args)
    except (OSError, ValueError, json.JSONDecodeError, DevelopmentPlanError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
