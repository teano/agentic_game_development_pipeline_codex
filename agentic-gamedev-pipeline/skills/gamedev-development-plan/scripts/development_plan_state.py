#!/usr/bin/env python3
"""Deterministic controller and validator for development-plan approval."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import importlib.util
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
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

_acceptance_path = Path(__file__).resolve().parents[3] / "scripts" / "acceptance_contract.py"
_acceptance_spec = importlib.util.spec_from_file_location(
    "gamedev_acceptance_contract", _acceptance_path
)
if _acceptance_spec is None or _acceptance_spec.loader is None:
    raise RuntimeError("Cannot load the canonical acceptance contract")
_acceptance_module = importlib.util.module_from_spec(_acceptance_spec)
_acceptance_spec.loader.exec_module(_acceptance_module)
extract_literal_acceptance_ids = _acceptance_module.extract_literal_acceptance_ids
parse_acceptance_ids = _acceptance_module.parse_acceptance_ids
derive_prd_acceptance_inventory = _acceptance_module.derive_prd_acceptance_inventory
require_known_acceptance_ids = _acceptance_module.require_known_acceptance_ids
require_complete_acceptance_coverage = (
    _acceptance_module.require_complete_acceptance_coverage
)

_requirements_validator_spec = importlib.util.spec_from_file_location(
    "gamedev_requirements_validator_for_planning",
    Path(__file__).resolve().parents[2]
    / "gamedev-requirements"
    / "scripts"
    / "validate_product_requirements.py",
)
if _requirements_validator_spec is None or _requirements_validator_spec.loader is None:
    raise RuntimeError("Cannot load the approved PRD validator")
_requirements_validator = importlib.util.module_from_spec(_requirements_validator_spec)
_requirements_validator_spec.loader.exec_module(_requirements_validator)

_plan_contract_path = Path(__file__).resolve().parents[3] / "scripts" / "development_plan_contract.py"
_plan_contract_spec = importlib.util.spec_from_file_location(
    "gamedev_development_plan_contract", _plan_contract_path
)
if _plan_contract_spec is None or _plan_contract_spec.loader is None:
    raise RuntimeError("Cannot load the shared development-plan contract")
_plan_contract = importlib.util.module_from_spec(_plan_contract_spec)
_plan_contract_spec.loader.exec_module(_plan_contract)

_pipeline_v2_model_path = (
    Path(__file__).resolve().parents[2]
    / "gamedev-pipeline"
    / "scripts"
    / "pipeline_v2"
    / "model.py"
)
_pipeline_v2_model_spec = importlib.util.spec_from_file_location(
    "gamedev_pipeline_v2_model_for_planning", _pipeline_v2_model_path
)
if _pipeline_v2_model_spec is None or _pipeline_v2_model_spec.loader is None:
    raise RuntimeError("Cannot load the canonical pipeline-v2 state model")
_pipeline_v2_model = importlib.util.module_from_spec(_pipeline_v2_model_spec)
_pipeline_v2_model_spec.loader.exec_module(_pipeline_v2_model)

_pipeline_v2_package_root = _pipeline_v2_model_path.parent.parent
_pipeline_v2_package_root_text = str(_pipeline_v2_package_root)
_pipeline_v2_path_added = _pipeline_v2_package_root_text not in sys.path
if _pipeline_v2_path_added:
    sys.path.insert(0, _pipeline_v2_package_root_text)
try:
    _pipeline_v2_legacy = importlib.import_module("pipeline_v2.legacy_gen53")
finally:
    if _pipeline_v2_path_added:
        sys.path.remove(_pipeline_v2_package_root_text)
if Path(_pipeline_v2_legacy.__file__).resolve() != (
    _pipeline_v2_model_path.parent / "legacy_gen53.py"
).resolve():
    raise RuntimeError("Cannot load the canonical pipeline-v2 schema-10 importer")


SCHEMA_VERSION = 1
SPECIFICATION_STATE_SCHEMA_VERSION = 2
STATE_RELATIVE_PATH = Path(".agentic-pipeline/development-plan-state.json")
SPEC_STATE_RELATIVE_PATH = Path(".agentic-pipeline/specification-state.json")
RUNTIME_STATE_RELATIVE_PATH = Path(".agentic-pipeline/state.json")
RUNTIME_FINDINGS_RELATIVE_PATH = Path(".agentic-pipeline/findings.json")
V2_RUNTIME_STATE_RELATIVE_PATH = Path(".agentic-pipeline-v2/state.json")
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
APPROVAL_WAITING_STATES = {"awaiting_approval", "awaiting_user_approval"}
APPROVAL_ACTOR_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


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


def exact_top_level_frontmatter_value(text: str, key: str, *, label: str) -> str:
    parts = text.split("---", 2)
    if len(parts) != 3 or parts[0] != "":
        raise DevelopmentPlanError(f"{label} must contain terminated YAML frontmatter")
    values = [
        match.group(1).strip()
        for line in parts[1].splitlines()
        if (match := re.match(rf"^{re.escape(key)}\s*:\s*(.*?)\s*$", line))
    ]
    if len(values) != 1:
        raise DevelopmentPlanError(
            f"{label} must contain exactly one top-level {key}: field"
        )
    return values[0]


def exact_positive_plan_revision(text: str, *, label: str) -> int:
    value = exact_top_level_frontmatter_value(text, "revision", label=label)
    if not re.fullmatch(r"[1-9][0-9]*", value):
        raise DevelopmentPlanError(
            f"{label} top-level revision must be one positive integer"
        )
    return int(value)


def normalized_actor_id(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def require_approval_actor(value: Any) -> str:
    if not isinstance(value, str) or APPROVAL_ACTOR_PATTERN.fullmatch(value) is None:
        raise DevelopmentPlanError(
            "approval actor must be one safe 1-64 character identity"
        )
    return value


def normalized_planning_analyst_identities(value: Any) -> set[str]:
    """Collect every stored Planning Analyst identity across current/history shapes."""
    result: set[str] = set()

    def visit(item: Any, key: str | None = None) -> None:
        if isinstance(item, dict):
            for child_key, child in item.items():
                visit(child, child_key)
        elif isinstance(item, list):
            for child in item:
                visit(child, key)
        elif (
            isinstance(item, str)
            and key is not None
            and (key == "analyst_id" or key.endswith("_analyst_id"))
        ):
            result.add(normalized_actor_id(item))

    visit(value)
    return result


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


def load_valid_v2_runtime(path: Path) -> dict[str, Any]:
    try:
        runtime = load_json(path, "v2 runtime state")
        _pipeline_v2_model.validate_state(runtime)
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        _pipeline_v2_model.PipelineError,
    ) as error:
        raise DevelopmentPlanError(f"v2 runtime state is invalid: {error}") from error
    return runtime


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
    prd_validation = _requirements_validator.validate(prd, True)
    if not prd_validation.get("valid"):
        raise DevelopmentPlanError(
            "PRD does not pass the full approved requirements contract; perform a "
            "controlled PRD revision and specification reconvergence: "
            + "; ".join(prd_validation.get("errors") or [])
        )
    prd_revision = str(prd_validation["revision"])

    spec_meta, _ = parse_frontmatter(spec, "specification")
    if spec_meta.get("document_type") != "technical-specification":
        raise DevelopmentPlanError("specification document_type must be technical-specification")
    if spec_meta.get("status") != "approved" or not spec_meta.get("revision"):
        raise DevelopmentPlanError("specification must have approved status and a revision")

    prd_hash = prd_validation["sha256"]
    spec_hash = sha256(spec)
    expected_prd_path = prd.relative_to(root).as_posix()
    spec_product_trace = authority_trace(
        spec_meta, "source_prd", ("product_authority",)
    )
    if spec_product_trace != {
        "path": expected_prd_path,
        "revision": prd_revision,
        "sha256": prd_hash,
    }:
        raise DevelopmentPlanError("specification does not trace the exact current approved PRD")

    specification_state = load_json(root / SPEC_STATE_RELATIVE_PATH, "specification state")
    if specification_state.get("schema_version") != SPECIFICATION_STATE_SCHEMA_VERSION:
        raise DevelopmentPlanError(
            "specification state must use the current schema; reconverge specification "
            "authority before planning"
        )
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
            "revision": prd_revision,
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
        if state.get("status") not in {"approval_pending", "revision_reopen_pending"}:
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
    try:
        meta, body = _plan_contract.parse_development_plan_frontmatter(
            plan.read_text(encoding="utf-8"), label="development plan"
        )
    except _plan_contract.PlanContractError as exc:
        raise DevelopmentPlanError(str(exc)) from exc
    errors: list[str] = []
    try:
        exact_positive_plan_revision(
            plan.read_text(encoding="utf-8"), label="development plan"
        )
    except DevelopmentPlanError as exc:
        errors.append(str(exc))
    try:
        prd_acceptance_inventory = derive_prd_acceptance_inventory(
            (root / state["prd"]["path"]).read_text(encoding="utf-8"),
            label="approved PRD",
        )
    except ValueError as exc:
        errors.append(str(exc))
        prd_acceptance_inventory = frozenset()
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
    if meta.get("mode") not in MODES:
        errors.append("frontmatter mode is invalid")
    if required_status == "draft" and ("approved_by" in meta or "approved_at" in meta):
        errors.append("draft frontmatter cannot contain approval metadata")
    if required_status == "approved":
        approval_record = state.get("approval_transition") or state.get("approval") or {}
        expected_actor = approval_record.get("approved_by")
        try:
            require_approval_actor(expected_actor)
        except DevelopmentPlanError as exc:
            errors.append(str(exc))
        if meta.get("approved_by") != expected_actor:
            errors.append(
                "approved frontmatter must record the controller-bound approval actor"
            )
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
    if "planning controller internal" not in ledger_section.lower():
        errors.append("Decision Ledger must state the planning controller internal route")

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
    try:
        _plan_contract.parse_coverage_strategy(coverage_strategy)
    except _plan_contract.PlanContractError as exc:
        errors.append(str(exc))
    documentation_strategy = global_sections.get("Documentation Strategy", "")
    try:
        _plan_contract.parse_exact_contract_rows(
            documentation_strategy,
            label="Documentation Strategy",
            scalar_keys={"normative_pre_review", "derived_post_qa"},
            optional_keys={"source_rule"},
            path_or_policy_keys={"normative_pre_review", "derived_post_qa"},
        )
    except _plan_contract.PlanContractError as exc:
        errors.append(str(exc))

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

    slice_acceptance_by_id: dict[str, set[str]] = {}
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
        try:
            requirement_acceptance_ids = set(
                extract_literal_acceptance_ids(
                    requirements, label=f"{slice_id} Requirements"
                )
            )
        except ValueError as exc:
            errors.append(str(exc))
            requirement_acceptance_ids = set()
        if not requirement_acceptance_ids:
            errors.append(f"{slice_id} must map at least one literal PRD-AC")
        try:
            require_known_acceptance_ids(
                requirement_acceptance_ids,
                prd_acceptance_inventory,
                label=f"{slice_id} Requirements",
            )
        except ValueError as exc:
            errors.append(str(exc))

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
        scope_acceptance_values = [
            value
            for key, value in re.findall(
                r"(?m)^\s*-\s*([a-z_]+):\s*(.+?)\s*$", scope
            )
            if key == "acceptance_ids"
        ]
        if len(scope_acceptance_values) != 1:
            errors.append(
                f"{slice_id} Scope Contract requires exactly one acceptance_ids field"
            )
        scope_acceptance_value = (
            scope_acceptance_values[0] if len(scope_acceptance_values) == 1 else ""
        )
        try:
            scope_acceptance = set(
                parse_acceptance_ids(
                    scope_acceptance_value,
                    label=f"{slice_id} Scope Contract acceptance_ids",
                )
            )
        except ValueError as exc:
            errors.append(str(exc))
            scope_acceptance = set()
        slice_acceptance_by_id[slice_id] = scope_acceptance
        try:
            require_known_acceptance_ids(
                scope_acceptance,
                prd_acceptance_inventory,
                label=f"{slice_id} Scope Contract acceptance_ids",
            )
        except ValueError as exc:
            errors.append(str(exc))
        if not scope_acceptance.issubset(requirement_acceptance_ids):
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
        try:
            editable_values = re.findall(
                r"(?m)^\s*-\s*editable_paths:\s*(.+?)\s*$", scope
            )
            editable_paths = (
                [item.strip().replace("\\", "/") for item in editable_values[0].split(",")]
                if len(editable_values) == 1
                else []
            )
            parsed_touchpoints = [
                {
                    "id": touchpoint_id,
                    "path": next(
                        (
                            part.split("=", 1)[1].strip().replace("\\", "/")
                            for part in fields_text.split("|")
                            if "=" in part and part.split("=", 1)[0].strip() == "path"
                        ),
                        "",
                    ),
                }
                for touchpoint_id, fields_text in touchpoints
            ]
            _plan_contract.parse_planned_material_permissions(
                scope,
                label=f"{slice_id} Scope Contract",
                editable_paths=editable_paths,
                shared_touchpoints=parsed_touchpoints,
            )
        except _plan_contract.PlanContractError as exc:
            errors.append(str(exc))
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
        elif len(research_rows) > 3:
            errors.append(f"{slice_id} permits at most three Research Briefs")
        research_ids = [research_id for research_id, _ in research_rows]
        if len(research_ids) != len(set(research_ids)):
            errors.append(f"{slice_id} Research Brief IDs must be unique")
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
        try:
            parsed_coverage_contract = _plan_contract.parse_slice_coverage_contract(
                coverage, label=f"{slice_id} Coverage Contract"
            )
        except _plan_contract.PlanContractError as exc:
            errors.append(str(exc))
            parsed_coverage_contract = {}
        coverage_acceptance_values = re.findall(
            r"(?m)^\s*-\s*acceptance_ids:\s*(\S(?:.*\S)?)\s*$", coverage
        )
        if len(coverage_acceptance_values) != 1:
            errors.append(
                f"{slice_id} Coverage Contract requires exactly one acceptance_ids field"
            )
        else:
            try:
                coverage_acceptance = set(
                    parse_acceptance_ids(
                        coverage_acceptance_values[0],
                        label=f"{slice_id} Coverage Contract acceptance_ids",
                    )
                )
                require_known_acceptance_ids(
                    coverage_acceptance,
                    prd_acceptance_inventory,
                    label=f"{slice_id} Coverage Contract acceptance_ids",
                )
                if coverage_acceptance != scope_acceptance:
                    errors.append(
                        f"{slice_id} Coverage Contract acceptance_ids must exactly equal "
                        "Scope Contract acceptance_ids"
                    )
            except ValueError as exc:
                errors.append(str(exc))
        documentation = sections.get("Documentation Contract", "")
        try:
            _plan_contract.parse_exact_contract_rows(
                documentation,
                label=f"{slice_id} Documentation Contract",
                scalar_keys={
                    "normative_pre_review_paths", "derived_post_qa_paths",
                    "decision_ids", "evidence_sources",
                },
                path_or_policy_keys={
                    "normative_pre_review_paths", "derived_post_qa_paths"
                },
            )
        except _plan_contract.PlanContractError as exc:
            errors.append(str(exc))
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

    try:
        require_complete_acceptance_coverage(
            slice_acceptance_by_id,
            prd_acceptance_inventory,
            label="Development plan slice acceptance_ids",
        )
    except ValueError as exc:
        errors.append(str(exc))

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
            if state["status"] not in {
                "approval_pending",
                "revision_reopen_pending",
            }:
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
    if state.get("revision_reopen"):
        raise DevelopmentPlanError(
            "cannot reinitialize while an approved-plan revision transition is pending"
        )
    pending_transition = state.get("approval_transition")
    pending_recovery = (
        pending_transition is not None or state.get("status") == "approval_pending"
    )
    pending_drift: list[str] = []
    pending_draft_bytes: bytes | None = None
    pending_resulting_draft_sha256: str | None = None
    pending_event: dict[str, Any] | None = None
    if pending_recovery:
        if state.get("status") != "approval_pending" or not isinstance(
            pending_transition, dict
        ):
            raise DevelopmentPlanError(
                "pending plan approval state and transition are inconsistent"
            )
        required_transition_fields = {
            "approved_by",
            "approval_note",
            "submitted_sha256",
            "approved_sha256",
            "approved_at",
        }
        if (
            set(pending_transition) != required_transition_fields
            or not isinstance(pending_transition.get("approved_by"), str)
            or APPROVAL_ACTOR_PATTERN.fullmatch(pending_transition["approved_by"])
            is None
            or not isinstance(pending_transition.get("approval_note"), str)
            or not pending_transition["approval_note"].strip()
            or not isinstance(pending_transition.get("approved_at"), str)
            or not pending_transition["approved_at"].strip()
            or any(
                not isinstance(pending_transition.get(field), str)
                or re.fullmatch(r"[0-9a-f]{64}", pending_transition[field]) is None
                for field in ("submitted_sha256", "approved_sha256")
            )
        ):
            raise DevelopmentPlanError("pending plan approval transition is malformed")
        pending_drift = source_drift(root, state)
        if not pending_drift:
            raise DevelopmentPlanError(
                "cannot reinitialize an unchanged pending approval; resume approve with "
                "the exact original approval inputs"
            )
        pending_plan = resolve_project_path(
            root, state["plan_path"], "pending development plan"
        )
        current_sha = sha256(pending_plan)
        submitted_sha = pending_transition["submitted_sha256"]
        approved_sha = pending_transition["approved_sha256"]
        if current_sha == approved_sha:
            pending_draft_bytes = recovered_submitted_plan_bytes(pending_plan)
            pending_resulting_draft_sha256 = hashlib.sha256(
                pending_draft_bytes
            ).hexdigest()
        elif current_sha == submitted_sha:
            pending_resulting_draft_sha256 = submitted_sha
        else:
            reproduced_approved = promoted_plan_bytes(
                pending_plan,
                pending_transition["approved_by"],
                pending_transition["approved_at"],
            )
            deterministic_recovery = recovered_submitted_plan_bytes(
                reproduced_approved
            )
            if (
                hashlib.sha256(reproduced_approved).hexdigest() != approved_sha
                or pending_plan.read_bytes() != deterministic_recovery
            ):
                raise DevelopmentPlanError(
                    "pending plan approval found unexpected development-plan bytes"
                )
            pending_resulting_draft_sha256 = current_sha
    elif state["status"] != "stale":
        raise DevelopmentPlanError("reinitialize is allowed only from stale state")
    if (
        not args.analyst_id.strip()
        or normalized_actor_id(args.analyst_id)
        in normalized_planning_analyst_identities(state)
    ):
        raise DevelopmentPlanError(
            "reinitialize requires a Planning Analyst identity fresh across all planning history"
        )
    prior_approval = state.get("approval") or {}
    prior_plan_sha256 = prior_approval.get("approved_sha256")
    authorization = require_runtime_unbound(
        root,
        recovery_token=getattr(args, "recovery_token", None),
        reason=getattr(args, "reason", None),
        prior_plan_sha256=prior_plan_sha256,
        prior_plan_path=state["plan_path"],
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
    if pending_recovery:
        superseded_at = utc_now()
        pending_event = copy.deepcopy(pending_transition)
        pending_event.update(
            {
                "event": "plan_approval_superseded_by_reinitialize",
                "superseded_at": superseded_at,
                "source_drift": pending_drift,
                "resulting_draft_sha256": pending_resulting_draft_sha256,
                "reinitialized_by_analyst_id": args.analyst_id,
            }
        )
        history.append(pending_event)
        if pending_draft_bytes is not None:
            write_bytes_atomically(
                resolve_project_path(
                    root, state["plan_path"], "pending development plan"
                ),
                pending_draft_bytes,
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
    if authorization:
        renewed["recovery_authorization"] = authorization
    save_state(root, renewed)
    return renewed


def command_accept_analysis(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root).resolve()
    state = load_state(root)
    require_bound_recovery_continuation(root, state)
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
    require_bound_recovery_continuation(root, state)
    if not state.get("analysis"):
        raise DevelopmentPlanError("Planning Analyst decision has not been accepted")
    required_status = "approved" if state["status"] == "approved" else "draft"
    result = validate_plan(root, state, required_status)
    if state["status"] == "approved":
        approval = state.get("approval") or {}
        if result["sha256"] != approval.get("approved_sha256"):
            raise DevelopmentPlanError("approved plan changed after recorded approval")
    return result


def command_submit(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root).resolve()
    state = load_state(root)
    require_bound_recovery_continuation(root, state)
    if state["status"] != "drafting" and state["status"] not in APPROVAL_WAITING_STATES:
        raise DevelopmentPlanError(f"cannot submit plan in {state['status']}")
    result = validate_plan(root, state, "draft")
    recorded_submission = state.get("submission")
    if (
        state["status"] in APPROVAL_WAITING_STATES
        and isinstance(recorded_submission, dict)
        and set(recorded_submission) == set(result) | {"submitted_at"}
        and isinstance(recorded_submission.get("submitted_at"), str)
        and bool(recorded_submission["submitted_at"])
        and all(recorded_submission.get(key) == value for key, value in result.items())
        and state.get("approval") is None
        and "approval_transition" not in state
    ):
        return state
    state["submission"] = {**result, "submitted_at": utc_now()}
    state["approval"] = None
    state["status"] = "awaiting_approval"
    state["updated_at"] = utc_now()
    save_state(root, state)
    return state


def promoted_plan_bytes(plan: Path, approved_by: str, approved_at: str) -> bytes:
    approved_by = require_approval_actor(approved_by)
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
    return new_text.encode("utf-8")


def recovered_submitted_plan_bytes(plan: Path | bytes) -> bytes:
    """Reproduce submitted draft bytes from an interrupted deterministic promotion."""
    raw = plan.read_bytes() if isinstance(plan, Path) else plan
    text = raw.decode("utf-8")
    parts = text.split("---", 2)
    if len(parts) != 3:
        raise DevelopmentPlanError("pending development plan lacks YAML frontmatter")
    lines = parts[1].splitlines()
    if sum(bool(re.match(r"^status\s*:", line)) for line in lines) != 1:
        raise DevelopmentPlanError("pending development plan must contain exactly one status")
    updated: list[str] = []
    for line in lines:
        if re.match(r"^(approved_by|approved_at)\s*:", line):
            continue
        if re.match(r"^status\s*:", line):
            updated.append("status: draft")
        else:
            updated.append(line)
    return (
        "---\n" + "\n".join(updated).strip() + "\n---\n" + parts[2].lstrip("\r\n")
    ).encode("utf-8")


def reopened_plan_bytes(plan: Path, analyst_id: str) -> tuple[bytes, int, int]:
    """Build the controller-owned mechanical reopening of exact approved bytes."""
    text = plan.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) != 3:
        raise DevelopmentPlanError("approved development plan lacks YAML frontmatter")
    lines = parts[1].splitlines()
    prior_revision = exact_positive_plan_revision(
        text, label="approved development plan"
    )
    next_revision = prior_revision + 1
    analyst_fields = sum(
        bool(re.match(r"^planning_analyst_id\s*:", line)) for line in lines
    )
    status_fields = sum(bool(re.match(r"^status\s*:", line)) for line in lines)
    if analyst_fields != 1 or status_fields != 1:
        raise DevelopmentPlanError(
            "approved development plan must contain one status and planning_analyst_id field"
        )
    updated: list[str] = []
    for line in lines:
        if re.match(r"^(approved_by|approved_at)\s*:", line):
            continue
        if re.match(r"^status\s*:", line):
            updated.append("status: draft")
        elif re.match(r"^revision\s*:", line):
            updated.append(f"revision: {next_revision}")
        elif re.match(r"^planning_analyst_id\s*:", line):
            updated.append(f"planning_analyst_id: {analyst_id}")
        else:
            updated.append(line)
    new_text = "---\n" + "\n".join(updated).strip() + "\n---\n" + parts[2].lstrip("\r\n")
    return new_text.encode("utf-8"), prior_revision, next_revision


def write_bytes_atomically(path: Path, value: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(value)
    os.replace(temporary, path)


def canonical_json_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and set(value) <= set("0123456789abcdef")
    )


def runtime_path_exists(path: Path) -> bool:
    return os.path.lexists(path)


def require_canonical_runtime_file(root: Path, relative: Path, label: str) -> Path:
    directory = root / relative.parent
    path = root / relative
    try:
        directory_stat = directory.lstat()
        path_stat = path.lstat()
    except OSError as error:
        raise DevelopmentPlanError(
            f"retired schema-10 lineage requires the complete canonical legacy pair: {error}"
        ) from error
    if (
        not directory.is_dir()
        or directory.is_symlink()
        or bool(getattr(directory_stat, "st_file_attributes", 0) & 0x400)
        or not path.is_file()
        or path.is_symlink()
        or bool(getattr(path_stat, "st_file_attributes", 0) & 0x400)
    ):
        raise DevelopmentPlanError(
            f"retired schema-10 lineage requires a canonical regular {label} file"
        )
    return path


def legacy_relative_path(legacy_root: str, supplied: Any, label: str) -> str:
    if not isinstance(supplied, str) or not supplied:
        raise DevelopmentPlanError(
            f"retired schema-10 lineage has an invalid {label} path"
        )
    windows = bool(re.match(r"^[A-Za-z]:[\\/]", legacy_root))
    path_type = PureWindowsPath if windows else PurePosixPath
    base = path_type(legacy_root)
    path = path_type(supplied)
    if not base.is_absolute():
        raise DevelopmentPlanError(
            "retired schema-10 lineage project root must be absolute"
        )
    if not path.is_absolute():
        path = base / path
    try:
        relative = path.relative_to(base)
    except ValueError as error:
        raise DevelopmentPlanError(
            f"retired schema-10 lineage {label} path escapes the project root"
        ) from error
    value = relative.as_posix()
    if (
        not value
        or value == "."
        or ".." in relative.parts
        or any(character in value for character in "*?[")
    ):
        raise DevelopmentPlanError(
            f"retired schema-10 lineage has an invalid {label} path"
        )
    return value


def derived_schema10_authority(root: Path, legacy: dict[str, Any]) -> dict[str, Any]:
    legacy_root = legacy.get("project_root")
    if (
        not isinstance(legacy_root, str)
        or not legacy_root
        or Path(legacy_root).resolve() != root
    ):
        raise DevelopmentPlanError(
            "retired schema-10 lineage belongs to a different project root"
        )
    candidates = {
        "requirements": (
            legacy.get("requirements_path"), legacy.get("requirements_sha256")
        ),
        "specification": (legacy.get("spec_path"), legacy.get("spec_sha256")),
        "plan": (
            legacy.get("development_plan_path"),
            legacy.get("development_plan_sha256"),
        ),
    }
    items: dict[str, dict[str, str]] = {}
    for name, (path, digest) in candidates.items():
        if not is_sha256(digest):
            raise DevelopmentPlanError(
                f"retired schema-10 lineage has an invalid {name} authority digest"
            )
        items[name] = {
            "path": legacy_relative_path(legacy_root, path, name),
            "sha256": digest,
        }
    return {"items": items, "digest": canonical_json_digest(items)}


def require_retired_schema10_history(
    runtime: dict[str, Any], legacy_generation: int,
) -> list[dict[str, Any]]:
    runtime_generation = runtime.get("generation")
    history = runtime.get("history")
    if (
        type(runtime_generation) is not int
        or runtime_generation < legacy_generation
        or not isinstance(history, list)
        or len(history) < 2
    ):
        raise DevelopmentPlanError(
            "retired schema-10 lineage has an invalid runtime generation or history"
        )
    seen_ids: set[str] = set()
    for index, item in enumerate(history):
        expected_generation = (
            legacy_generation if index < 2 else legacy_generation + index - 1
        )
        record_id = item.get("id") if isinstance(item, dict) else None
        if (
            not isinstance(item, dict)
            or type(item.get("generation")) is not int
            or item["generation"] < 0
            or item["generation"] != expected_generation
            or not isinstance(record_id, str)
            or not record_id.strip()
            or record_id in seen_ids
            or any(
                not isinstance(item.get(field), str) or not item[field].strip()
                for field in ("command", "result")
            )
        ):
            raise DevelopmentPlanError(
                "retired schema-10 lineage has invalid public history sequencing"
            )
        seen_ids.add(record_id)
    if history[-1]["generation"] != runtime_generation:
        raise DevelopmentPlanError(
            "retired schema-10 lineage history does not reach the runtime generation"
        )
    return history


def reconstruct_retired_schema10_import(
    legacy: dict[str, Any], runtime: dict[str, Any],
    first: dict[str, Any], migrate: dict[str, Any], *, evolved: bool,
) -> dict[str, Any]:
    runtime_slices = runtime.get("slices")
    legacy_slice_fields = ("id", "allowed_paths", "planned_commands")
    if not isinstance(runtime_slices, list):
        raise DevelopmentPlanError(
            "retired schema-10 lineage has invalid imported slice records"
        )
    if evolved:
        slices = [
            {field: copy.deepcopy(item[field]) for field in legacy_slice_fields}
            for item in runtime_slices
            if isinstance(item, dict)
            and all(field in item for field in legacy_slice_fields)
        ]
        if len(slices) != len(runtime_slices):
            raise DevelopmentPlanError(
                "retired schema-10 lineage has invalid imported slice records"
            )
    else:
        slices = runtime_slices
    try:
        slices = _pipeline_v2_model.slice_records(slices, sealed=False)
        imported = _pipeline_v2_legacy.import_schema10(legacy, slices)
    except (
        _pipeline_v2_model.PipelineError,
        _pipeline_v2_legacy.PipelineError,
        KeyError,
    ) as error:
        raise DevelopmentPlanError(
            f"retired schema-10 lineage import snapshot is invalid: {error}"
        ) from error
    if imported.get("history") != [first]:
        raise DevelopmentPlanError(
            "retired schema-10 lineage import snapshot does not match its public record"
        )
    expected_migrate_digest = canonical_json_digest(
        {"name": "migrate", "id": migrate["id"], "imported": imported}
    )
    if migrate.get("command_digest") != expected_migrate_digest:
        raise DevelopmentPlanError(
            "retired schema-10 lineage public migrate digest is invalid"
        )
    return imported


def require_retired_schema10_lineage(
    root: Path, runtime: dict[str, Any]
) -> None:
    legacy_state_path = require_canonical_runtime_file(
        root, RUNTIME_STATE_RELATIVE_PATH, "legacy state"
    )
    legacy_findings_path = require_canonical_runtime_file(
        root, RUNTIME_FINDINGS_RELATIVE_PATH, "legacy findings"
    )
    try:
        legacy = json.loads(legacy_state_path.read_text(encoding="utf-8"))
        findings = json.loads(legacy_findings_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DevelopmentPlanError(
            f"retired schema-10 lineage evidence is unreadable: {error}"
        ) from error
    if not isinstance(legacy, dict) or legacy.get("schema_version") != 10:
        raise DevelopmentPlanError(
            "retired schema-10 lineage requires an exact schema-10 legacy state"
        )
    generation = legacy.get("generation")
    if type(generation) is not int or generation < 0:
        raise DevelopmentPlanError(
            "retired schema-10 lineage has an invalid legacy generation"
        )
    if (
        not isinstance(findings, dict)
        or set(findings) != {"schema_version", "items", "generation"}
        or findings.get("schema_version") != 10
        or type(findings.get("generation")) is not int
        or findings.get("generation") != generation
        or findings.get("items") != []
    ):
        raise DevelopmentPlanError(
            "retired schema-10 lineage requires empty same-generation schema-10 findings"
        )

    authority = derived_schema10_authority(root, legacy)
    source_digest = canonical_json_digest(legacy)
    feature = legacy.get("feature")
    if not isinstance(feature, str) or not feature:
        raise DevelopmentPlanError(
            "retired schema-10 lineage requires a non-empty legacy feature"
        )
    expected_run_id = f"migrated-{feature}-{source_digest[:12]}"
    if runtime.get("run_id") != expected_run_id:
        raise DevelopmentPlanError(
            "retired schema-10 lineage has a mismatched deterministic v2 run ID"
        )
    history = require_retired_schema10_history(runtime, generation)
    first, migrate = history[0], history[1]
    first_result_phases = {
        "resumed_at_first_slice_engineering": "engineering",
        "audit_preserved": "plan",
        "projected_to_plan": "plan",
    }
    if (
        not isinstance(first, dict)
        or set(first) != {"id", "command", "command_digest", "generation", "result"}
        or first.get("id") != f"legacy-{source_digest[:16]}"
        or first.get("command") != "schema10_import"
        or first.get("command_digest") != source_digest
        or first.get("generation") != generation
        or first.get("result") not in first_result_phases
        or sum(
            isinstance(item, dict) and item.get("command") == "schema10_import"
            for item in history
        )
        != 1
    ):
        raise DevelopmentPlanError(
            "retired schema-10 lineage does not match the immutable import record"
        )
    if (
        not isinstance(migrate, dict)
        or set(migrate) != {"id", "command", "command_digest", "generation", "result"}
        or not isinstance(migrate.get("id"), str)
        or not migrate["id"].strip()
        or migrate.get("command") != "migrate"
        or not is_sha256(migrate.get("command_digest"))
        or migrate.get("generation") != generation
        or migrate.get("result") != "migrated"
        or sum(
            isinstance(item, dict) and item.get("command") == "migrate"
            for item in history
        )
        != 1
    ):
        raise DevelopmentPlanError(
            "retired schema-10 lineage is missing the following public migrate record"
        )

    bridge_candidates = [
        (index, item)
        for index, item in enumerate(history[2:], 2)
        if isinstance(item, dict)
        and item.get("result") == "authority_scope_reconfigured"
    ]
    imported = reconstruct_retired_schema10_import(
        legacy, runtime, first, migrate, evolved=bool(bridge_candidates)
    )
    if bridge_candidates:
        bridge_index, bridge = bridge_candidates[0]
        bridge_generation = bridge.get("generation")
        prior = bridge.get("prior")
        prior_fields = {
            "phase", "authority_digest", "slices_digest", "candidate",
            "artifact_phases", "question_ids", "gate_ids",
        }
        prior_lists = (
            prior.get("artifact_phases"), prior.get("question_ids"),
            prior.get("gate_ids"),
        ) if isinstance(prior, dict) else (None, None, None)
        valid_prior_lists = all(
            isinstance(value, list)
            and all(isinstance(item, str) and item for item in value)
            and value == sorted(set(value))
            for value in prior_lists
        )
        migration_audit_required = first["result"] != "projected_to_plan"
        duplicate_legacy_bridge = sum(
            isinstance(item.get("prior"), dict)
            and item["prior"].get("authority_digest") == authority["digest"]
            for _, item in bridge_candidates
        ) > 1
        if (
            set(bridge) != {
                "id", "command", "command_digest", "generation", "result", "prior",
            }
            or not isinstance(bridge.get("id"), str)
            or not bridge["id"].strip()
            or bridge.get("command") != "init"
            or not is_sha256(bridge.get("command_digest"))
            or bridge.get("result") != "authority_scope_reconfigured"
            or type(bridge_generation) is not int
            or bridge_generation <= generation
            or not isinstance(prior, dict)
            or not prior_fields <= set(prior)
            or prior.get("authority_digest") != authority["digest"]
            or prior.get("slices_digest") != canonical_json_digest(imported["slices"])
            or prior.get("phase") not in _pipeline_v2_model.PHASES
            or not valid_prior_lists
            or (
                migration_audit_required
                and "migration-audit" not in prior["gate_ids"]
            )
            or duplicate_legacy_bridge
        ):
            raise DevelopmentPlanError(
                "retired schema-10 lineage has an invalid public reconfiguration bridge"
            )
        return

    if runtime.get("authority") != authority:
        raise DevelopmentPlanError(
            "retired schema-10 lineage authority does not match the v2 authority"
        )
    expected_audit = imported["gates"].get("migration-audit")
    runtime_gates = runtime.get("gates")
    if expected_audit is not None and (
        not isinstance(runtime_gates, dict)
        or runtime_gates.get("migration-audit") != expected_audit
    ):
        raise DevelopmentPlanError(
            "retired schema-10 lineage has invalid migration audit evidence"
        )


def discover_v2_runtime_states(root: Path) -> list[Path]:
    """Find direct schema-2 runtime states without treating other JSON as state."""
    directory = root / V2_RUNTIME_STATE_RELATIVE_PATH.parent
    if not directory.exists():
        return []
    try:
        stat = directory.lstat()
    except OSError as error:
        raise DevelopmentPlanError(f"cannot inspect v2 runtime directory: {error}") from error
    if (
        not directory.is_dir() or directory.is_symlink()
        or bool(getattr(stat, "st_file_attributes", 0) & 0x400)
    ):
        raise DevelopmentPlanError("v2 runtime directory must be a canonical confined directory")
    candidates = []
    for path in sorted(directory.glob("*.json"), key=lambda item: item.name):
        try:
            child_stat = path.lstat()
        except OSError as error:
            raise DevelopmentPlanError(f"cannot inspect v2 runtime JSON: {error}") from error
        if (
            not path.is_file() or path.is_symlink()
            or bool(getattr(child_stat, "st_file_attributes", 0) & 0x400)
        ):
            raise DevelopmentPlanError("v2 runtime JSON must be a canonical confined file")
        if path.name == V2_RUNTIME_STATE_RELATIVE_PATH.name:
            candidates.append(path)
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if (
            isinstance(value, dict) and value.get("schema") == 2
            and "project_root" in value and "authority" in value
        ):
            candidates.append(path)
    return candidates


def require_v2_runtime_binding(
    root: Path,
    v2_path: Path,
    *,
    prior_plan_sha256: str | None,
    prior_plan_path: str | None,
) -> dict[str, Any]:
    runtime = load_valid_v2_runtime(v2_path)
    authority = runtime.get("authority")
    items = authority.get("items") if isinstance(authority, dict) else None
    expected_digest = canonical_json_digest(items) if isinstance(items, dict) else None
    if (
        runtime.get("schema") != 2
        or Path(str(runtime.get("project_root", ""))).resolve() != root
        or not isinstance(authority, dict)
        or set(authority) != {"items", "digest"}
        or set(items or {}) != {"requirements", "specification", "plan"}
        or authority.get("digest") != expected_digest
    ):
        raise DevelopmentPlanError("v2 runtime binding is malformed and fails closed")
    plan_binding = items.get("plan")
    if not isinstance(plan_binding, dict) or set(plan_binding) != {"path", "sha256"}:
        raise DevelopmentPlanError("v2 runtime plan binding is malformed")
    if plan_binding.get("path") != prior_plan_path:
        raise DevelopmentPlanError(
            "v2 runtime bound plan path does not match the canonical plan being reopened"
        )
    if plan_binding.get("sha256") != prior_plan_sha256:
        raise DevelopmentPlanError(
            "v2 runtime bound plan SHA does not match the approved plan being reopened"
        )
    return runtime


def runtime_recovery_authorization(
    root: Path,
    *,
    recovery_token: str | None,
    reason: str | None,
    prior_plan_sha256: str | None,
    prior_plan_path: str | None,
) -> dict[str, Any] | None:
    v2_paths = discover_v2_runtime_states(root)
    legacy_presence = [
        runtime_path_exists(root / path)
        for path in (RUNTIME_STATE_RELATIVE_PATH, RUNTIME_FINDINGS_RELATIVE_PATH)
    ]
    if v2_paths:
        if len(v2_paths) != 1:
            raise DevelopmentPlanError(
                "multiple v2 runtime state candidates exist; retired schema-10 lineage "
                "cannot be proven and the ambiguous binding fails closed"
            )
        try:
            runtime = require_v2_runtime_binding(
                root,
                v2_paths[0],
                prior_plan_sha256=prior_plan_sha256,
                prior_plan_path=prior_plan_path,
            )
        except DevelopmentPlanError as error:
            if any(legacy_presence):
                raise DevelopmentPlanError(
                    "retired schema-10 lineage cannot use an invalid v2 binding: "
                    f"{error}"
                ) from error
            raise
        if recovery_token:
            raise DevelopmentPlanError(
                "v2 runtime reconfiguration uses public status -> init, not a recovery token"
            )
        if any(legacy_presence):
            if not all(legacy_presence):
                raise DevelopmentPlanError(
                    "retired schema-10 lineage requires the complete legacy state/findings pair"
                )
            require_retired_schema10_lineage(root, runtime)
        return None
    legacy_bound = [
        path
        for path, present in zip(
            (RUNTIME_STATE_RELATIVE_PATH, RUNTIME_FINDINGS_RELATIVE_PATH),
            legacy_presence,
            strict=True,
        )
        if present
    ]
    if not legacy_bound:
        if recovery_token:
            raise DevelopmentPlanError(
                "--recovery-token is valid only for an open bound runtime recovery hold"
            )
        return None
    if len(legacy_bound) != 2:
        raise DevelopmentPlanError(
            "runtime pipeline state binding is incomplete and cannot authorize plan recovery"
        )
    legacy_state_path = require_canonical_runtime_file(
        root, RUNTIME_STATE_RELATIVE_PATH, "legacy state"
    )
    require_canonical_runtime_file(
        root, RUNTIME_FINDINGS_RELATIVE_PATH, "legacy findings"
    )
    runtime = load_json(legacy_state_path, "runtime state")
    hold = runtime.get("authority_recovery_hold") or {}
    token_payload = {
        "feature": hold.get("feature"),
        "opened_at": hold.get("opened_at"),
        "authorized_by": hold.get("authorized_by"),
        "reason": hold.get("reason"),
        "requirements_sha256": (hold.get("requirements") or {}).get("sha256"),
        "spec_sha256": (hold.get("specification") or {}).get("sha256"),
        "plan_sha256": (hold.get("development_plan") or {}).get("sha256"),
        "revision": hold.get("revision"),
    }
    expected_token = "ARH-" + hashlib.sha256(
        json.dumps(
            token_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()[:32].upper()
    if (
        runtime.get("phase") != "authority_recovery_hold"
        or hold.get("status") != "open"
        or hold.get("token") != expected_token
        or not recovery_token
        or recovery_token != hold.get("token")
        or reason != hold.get("reason")
        or prior_plan_sha256 != (hold.get("development_plan") or {}).get("sha256")
    ):
        raise DevelopmentPlanError(
            "bound plan recovery requires the exact open authority_recovery_hold token, "
            "reason, and prior approved plan SHA"
        )
    return {
        "schema": 1,
        "token": recovery_token,
        "reason": reason,
        "runtime_state_path": RUNTIME_STATE_RELATIVE_PATH.as_posix(),
        "hold_opened_at": hold.get("opened_at"),
        "prior_plan_sha256": prior_plan_sha256,
    }


def require_runtime_unbound(
    root: Path,
    *,
    recovery_token: str | None = None,
    reason: str | None = None,
    prior_plan_sha256: str | None = None,
    prior_plan_path: str | None = None,
) -> dict[str, Any] | None:
    return runtime_recovery_authorization(
        root,
        recovery_token=recovery_token,
        reason=reason,
        prior_plan_sha256=prior_plan_sha256,
        prior_plan_path=prior_plan_path,
    )


def require_bound_recovery_continuation(root: Path, state: dict[str, Any]) -> None:
    authorization = state.get("recovery_authorization") or {}
    prior_plan_sha256 = authorization.get("prior_plan_sha256")
    if not is_sha256(prior_plan_sha256):
        for item in reversed(state.get("history", [])):
            if not isinstance(item, dict):
                continue
            if item.get("status") == "stale":
                archived_approval = item.get("approval")
                if (
                    item.get("plan_path") != state.get("plan_path")
                    or not isinstance(archived_approval, dict)
                    or not is_sha256(archived_approval.get("approved_sha256"))
                ):
                    raise DevelopmentPlanError(
                        "reinitialized plan authority history is malformed"
                    )
                prior_plan_sha256 = archived_approval["approved_sha256"]
                break
            if (
                item.get("event") == "approved_plan_revision_opened"
                and item.get("plan_path") == state.get("plan_path")
                and item.get("new_analyst_id") == state.get("analyst_id")
                and is_sha256(item.get("prior_approved_sha256"))
            ):
                prior_plan_sha256 = item["prior_approved_sha256"]
                break
    if not is_sha256(prior_plan_sha256) and state.get("status") == "approved":
        approval = state.get("approval") or {}
        approved_sha256 = approval.get("approved_sha256")
        if is_sha256(approved_sha256):
            prior_plan_sha256 = approved_sha256
    runtime_recovery_authorization(
        root,
        recovery_token=authorization.get("token"),
        reason=authorization.get("reason"),
        prior_plan_sha256=prior_plan_sha256,
        prior_plan_path=state.get("plan_path"),
    )


def finalize_approved_revision_reopen(
    root: Path, state: dict[str, Any], args: argparse.Namespace
) -> dict[str, Any]:
    transition = state.get("revision_reopen") or {}
    exact_args = {
        "opened_by": args.reopened_by,
        "reason": args.reason,
        "new_analyst_id": args.analyst_id,
        "recovery_token": getattr(args, "recovery_token", None),
    }
    if any(transition.get(key) != value for key, value in exact_args.items()):
        raise DevelopmentPlanError(
            "pending approved-plan revision must resume with the exact original identities and reason"
        )
    authorization = require_runtime_unbound(
        root,
        recovery_token=getattr(args, "recovery_token", None),
        reason=args.reason,
        prior_plan_sha256=transition["prior_approved_sha256"],
        prior_plan_path=transition["plan_path"],
    )
    drift = source_drift(root, state)
    if drift:
        raise DevelopmentPlanError(
            "pending approved-plan revision has source-authority drift: "
            + "; ".join(drift)
        )
    plan = root / state["plan_path"]
    current_sha256 = sha256(plan)
    if current_sha256 == transition["prior_approved_sha256"]:
        draft_bytes, prior_revision, next_revision = reopened_plan_bytes(
            plan, transition["new_analyst_id"]
        )
        if (
            prior_revision != transition["prior_revision"]
            or next_revision != transition["next_revision"]
            or hashlib.sha256(draft_bytes).hexdigest() != transition["draft_sha256"]
        ):
            raise DevelopmentPlanError(
                "pending approved-plan revision no longer reproduces its audited draft"
            )
        write_bytes_atomically(plan, draft_bytes)
    elif current_sha256 != transition["draft_sha256"]:
        raise DevelopmentPlanError(
            "pending approved-plan revision found unexpected plan bytes"
        )

    event = copy.deepcopy(transition)
    event["event"] = "approved_plan_revision_opened"
    state.setdefault("history", []).append(event)
    state["status"] = "analyzing"
    state["analyst_id"] = transition["new_analyst_id"]
    state["analysis"] = None
    state["submission"] = None
    state["approval"] = None
    state["drift"] = []
    if authorization:
        state["recovery_authorization"] = authorization
    state["updated_at"] = transition["opened_at"]
    state.pop("revision_reopen", None)
    save_state(root, state)
    return state


def command_revise_approved(args: argparse.Namespace) -> dict[str, Any]:
    """Open exact approved bytes as a new draft without carrying approval forward."""
    root = Path(args.project_root).resolve()
    state = load_state(root)
    if state["status"] == "revision_reopen_pending":
        return finalize_approved_revision_reopen(root, state, args)
    if state["status"] != "approved":
        raise DevelopmentPlanError(
            f"revise-approved requires approved state, got {state['status']}"
        )
    if not args.reason.strip() or not args.reopened_by.strip() or not args.analyst_id.strip():
        raise DevelopmentPlanError(
            "revision reason, reopened-by identity, and fresh analyst identity are required"
        )
    if normalized_actor_id(args.analyst_id) == normalized_actor_id(args.reopened_by):
        raise DevelopmentPlanError(
            "revise-approved requires distinct Director and Planning Analyst identities"
        )
    if normalized_actor_id(args.analyst_id) in normalized_planning_analyst_identities(state):
        raise DevelopmentPlanError(
            "revise-approved requires a Planning Analyst identity fresh across all planning history"
        )
    require_current_sources(root, state)
    plan = root / state["plan_path"]
    approval = state.get("approval") or {}
    prior_sha256 = sha256(plan)
    if approval.get("approved_sha256") != prior_sha256:
        raise DevelopmentPlanError(
            "approved plan bytes do not match the controller-recorded approval SHA"
        )
    authorization = require_runtime_unbound(
        root,
        recovery_token=getattr(args, "recovery_token", None),
        reason=args.reason,
        prior_plan_sha256=prior_sha256,
        prior_plan_path=state["plan_path"],
    )
    meta, _ = parse_frontmatter(plan, "approved development plan")
    approval_actor = approval.get("approved_by")
    if (
        meta.get("document_type") != "development-plan"
        or meta.get("status") != "approved"
        or meta.get("feature") != state["feature"]
        or require_approval_actor(approval_actor) != meta.get("approved_by")
    ):
        raise DevelopmentPlanError(
            "approved plan frontmatter does not match the recorded approved authority"
        )
    opened_at = utc_now()
    draft_bytes, prior_revision, next_revision = reopened_plan_bytes(
        plan, args.analyst_id
    )
    state["status"] = "revision_reopen_pending"
    state["revision_reopen"] = {
        "opened_at": opened_at,
        "opened_by": args.reopened_by,
        "reason": args.reason,
        "new_analyst_id": args.analyst_id,
        "plan_path": state["plan_path"],
        "prior_revision": prior_revision,
        "next_revision": next_revision,
        "prior_approved_sha256": prior_sha256,
        "prior_approval_disposition": "revoked_by_plan_revision",
        "approval_revoked_at": opened_at,
        "draft_sha256": hashlib.sha256(draft_bytes).hexdigest(),
        "prior_submission": copy.deepcopy(state.get("submission")),
        "prior_approval": copy.deepcopy(approval),
        "prd": copy.deepcopy(state["prd"]),
        "specification": copy.deepcopy(state["specification"]),
        "analyst_id": state["analyst_id"],
        "recovery_token": getattr(args, "recovery_token", None),
        "recovery_authorization": copy.deepcopy(authorization),
    }
    state["updated_at"] = opened_at
    save_state(root, state)
    return finalize_approved_revision_reopen(root, state, args)


def finalize_plan_approval(
    root: Path, state: dict[str, Any], args: argparse.Namespace
) -> dict[str, Any]:
    transition = state.get("approval_transition") or {}
    transition_actor = require_approval_actor(transition.get("approved_by"))
    if (
        transition_actor != args.approved_by
        or transition.get("approval_note") != args.approval_note
    ):
        raise DevelopmentPlanError(
            "pending plan approval must resume with the exact original approval inputs"
        )
    require_current_sources(root, state)
    plan = root / state["plan_path"]
    current_sha = sha256(plan)
    if current_sha == transition.get("submitted_sha256"):
        approved_bytes = promoted_plan_bytes(
            plan, transition["approved_by"], transition["approved_at"]
        )
        if hashlib.sha256(approved_bytes).hexdigest() != transition.get(
            "approved_sha256"
        ):
            raise DevelopmentPlanError(
                "pending plan approval no longer reproduces its audited approved bytes"
            )
        write_bytes_atomically(plan, approved_bytes)
    elif current_sha != transition.get("approved_sha256"):
        reproduced_approved = promoted_plan_bytes(
            plan, transition["approved_by"], transition["approved_at"]
        )
        deterministic_recovery = recovered_submitted_plan_bytes(
            reproduced_approved
        )
        if (
            hashlib.sha256(reproduced_approved).hexdigest()
            != transition.get("approved_sha256")
            or plan.read_bytes() != deterministic_recovery
        ):
            raise DevelopmentPlanError(
                "pending plan approval found unexpected development-plan bytes"
            )
        write_bytes_atomically(plan, reproduced_approved)

    result = validate_plan(root, state, "approved")
    if result["sha256"] != transition["approved_sha256"]:
        raise DevelopmentPlanError("approved development-plan SHA is inconsistent")
    state["approval"] = {
        "approved_by": transition["approved_by"],
        "approval_note": transition["approval_note"],
        "submitted_sha256": transition["submitted_sha256"],
        "approved_sha256": transition["approved_sha256"],
        "approved_at": transition["approved_at"],
    }
    state["status"] = "approved"
    state["drift"] = []
    state["updated_at"] = utc_now()
    state.pop("approval_transition", None)
    save_state(root, state)
    return state


def command_approve(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root).resolve()
    state = load_state(root)
    approval_actor = require_approval_actor(args.approved_by)
    if state["status"] == "approved":
        approval = state.get("approval") or {}
        if (
            approval.get("approved_by") == args.approved_by
            and approval.get("approval_note") == args.approval_note
            and sha256(root / state["plan_path"]) == approval.get("approved_sha256")
        ):
            require_current_sources(root, state)
            return state
        raise DevelopmentPlanError("development plan is already approved with different inputs")
    require_bound_recovery_continuation(root, state)
    if state["status"] == "approval_pending":
        return finalize_plan_approval(root, state, args)
    if state["status"] not in APPROVAL_WAITING_STATES or not state.get("submission"):
        raise DevelopmentPlanError("approval requires a submitted draft")
    require_current_sources(root, state)
    if not args.approval_note.strip():
        raise DevelopmentPlanError("approval note is required")
    plan = root / state["plan_path"]
    if sha256(plan) != state["submission"]["sha256"]:
        raise DevelopmentPlanError("draft changed after submission; resubmit before approval")
    approved_at = utc_now()
    approved_bytes = promoted_plan_bytes(plan, approval_actor, approved_at)
    state["approval_transition"] = {
        "approved_by": approval_actor,
        "approval_note": args.approval_note,
        "submitted_sha256": state["submission"]["sha256"],
        "approved_sha256": hashlib.sha256(approved_bytes).hexdigest(),
        "approved_at": approved_at,
    }
    state["status"] = "approval_pending"
    state["updated_at"] = utc_now()
    save_state(root, state)
    return finalize_plan_approval(root, state, args)


def command_status(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root).resolve()
    state = load_state(root)
    drift = source_drift(root, state)
    if drift and state["status"] in {"approval_pending", "revision_reopen_pending"}:
        state["drift"] = drift
        state["updated_at"] = utc_now()
        save_state(root, state)
    elif drift and state["status"] != "stale":
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
    reinitialize.add_argument("--recovery-token")
    reinitialize.add_argument("--reason")
    reinitialize.set_defaults(handler=command_reinitialize)

    revise = commands.add_parser(
        "revise-approved",
        help=(
            "revoke exact approved bytes and open a resumable new draft revision; "
            "v2 continues through public status -> init; legacy binding requires its token"
        ),
        description=(
            "Reopen approved plan bytes. A bound v2 runtime fails closed until its public "
            "status -> init reconfiguration; --recovery-token is legacy-only."
        ),
    )
    revise.add_argument("--reason", required=True, help="exact audited revision reason")
    revise.add_argument(
        "--reopened-by", required=True, help="Development Plan Director identity"
    )
    revise.add_argument(
        "--analyst-id",
        required=True,
        help="Planning Analyst identity unused across all planning history",
    )
    revise.add_argument(
        "--recovery-token",
        help="legacy-only exact token from a controller-owned authority_recovery_hold",
    )
    revise.set_defaults(handler=command_revise_approved)

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
