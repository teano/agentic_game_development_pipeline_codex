#!/usr/bin/env python3
"""Shared exact parsing rules for the authorable development-plan contract."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable


class PlanContractError(ValueError):
    pass


BASE_SCALARS = {
    "document_type",
    "status",
    "revision",
    "feature",
    "mode",
    "writer_strategy",
    "planning_analyst_id",
    "decision_ledger_path",
    "slice_count",
}
FLAT_TRACE_SCALARS = {
    "source_prd_path",
    "source_prd_revision",
    "source_prd_sha256",
    "source_spec_path",
    "source_spec_revision",
    "source_spec_sha256",
}
NESTED_TRACES = {"product_authority", "specification_authority"}
TRACE_FIELDS = {"path", "revision", "sha256"}
APPROVAL_SCALARS = {"approved_by", "approved_at"}
MODES = {"single_owner", "sequential_slices"}
MATERIAL_CHANGE_TYPES = {
    "lifecycle_change",
    "ownership_change",
    "public_contract_change",
}


def _unquoted_scalar(raw: str, label: str) -> str:
    value = raw.strip()
    if not value or value[0] in "'\"" or value[-1:] in "'\"":
        raise PlanContractError(f"{label} must be one non-empty unquoted scalar")
    if value.startswith(("[", "{", "&", "*", "!", "|", ">")):
        raise PlanContractError(f"{label} must be a scalar, not YAML collection syntax")
    return value


def _repo_path(value: str, label: str, *, allow_glob: bool = False) -> str:
    normalized = value.replace("\\", "/").strip()
    if (
        not normalized
        or normalized.startswith("/")
        or re.match(r"^[A-Za-z]:", normalized)
        or ".." in Path(normalized).parts
        or ("*" in normalized and (not allow_glob or not normalized.endswith("/**")))
    ):
        raise PlanContractError(f"{label} must be a safe repository-relative path")
    return normalized


def parse_development_plan_frontmatter(text: str, *, label: str = "development plan") -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        raise PlanContractError(f"{label} must start with YAML frontmatter")
    parts = text.split("---", 2)
    if len(parts) != 3 or parts[0] != "":
        raise PlanContractError(f"{label} must contain terminated YAML frontmatter")
    scalars: dict[str, str] = {}
    nested: dict[str, dict[str, str]] = {}
    parent: str | None = None
    for line_number, raw in enumerate(parts[1].splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if "\t" in raw or ":" not in raw:
            raise PlanContractError(f"{label} frontmatter line {line_number} is not an exact key/value row")
        indent = len(raw) - len(raw.lstrip(" "))
        key, raw_value = raw.strip().split(":", 1)
        if not re.fullmatch(r"[a-z][a-z0-9_]*", key):
            raise PlanContractError(f"{label} has invalid frontmatter key: {key}")
        if indent == 0:
            parent = None
            if key in scalars or key in nested:
                if key == "revision":
                    raise PlanContractError(
                        f"{label} must contain exactly one top-level revision field"
                    )
                raise PlanContractError(f"{label} repeats frontmatter field: {key}")
            if raw_value.strip():
                scalars[key] = (
                    raw_value.strip()
                    if key == "revision"
                    else _unquoted_scalar(raw_value, f"{label} {key}")
                )
            else:
                if key not in NESTED_TRACES:
                    raise PlanContractError(f"{label} field {key} cannot be a mapping")
                nested[key] = {}
                parent = key
        elif indent == 2 and parent:
            if key in nested[parent]:
                raise PlanContractError(f"{label} repeats {parent}.{key}")
            nested[parent][key] = _unquoted_scalar(raw_value, f"{label} {parent}.{key}")
        else:
            raise PlanContractError(f"{label} frontmatter supports only top-level scalars and two-space authority mappings")

    allowed = BASE_SCALARS | FLAT_TRACE_SCALARS | NESTED_TRACES | APPROVAL_SCALARS
    extra = sorted((set(scalars) | set(nested)) - allowed)
    if extra:
        raise PlanContractError(f"{label} has unsupported frontmatter fields: {', '.join(extra)}")
    missing = sorted(BASE_SCALARS - set(scalars))
    if missing:
        raise PlanContractError(f"{label} lacks frontmatter fields: {', '.join(missing)}")
    uses_flat = bool(set(scalars) & FLAT_TRACE_SCALARS)
    uses_nested = bool(nested)
    if uses_flat == uses_nested:
        raise PlanContractError(f"{label} must use exactly one complete flat or nested authority trace representation")
    if uses_flat:
        missing_trace = sorted(FLAT_TRACE_SCALARS - set(scalars))
        if missing_trace:
            raise PlanContractError(f"{label} lacks flat authority fields: {', '.join(missing_trace)}")
    else:
        if set(nested) != NESTED_TRACES:
            raise PlanContractError(f"{label} requires both product_authority and specification_authority")
        for name, fields in nested.items():
            if set(fields) != TRACE_FIELDS:
                raise PlanContractError(f"{label} {name} must contain exactly path, revision, and sha256")
            scalars.update({f"{name}.{key}": value for key, value in fields.items()})

    if scalars["document_type"] != "development-plan":
        raise PlanContractError(f"{label} document_type must be development-plan")
    if scalars["status"] not in {"draft", "approved"}:
        raise PlanContractError(f"{label} status must be draft or approved")
    if scalars["mode"] not in MODES:
        raise PlanContractError(f"{label} mode must be single_owner or sequential_slices")
    if scalars["writer_strategy"] != "sequential":
        raise PlanContractError(f"{label} writer_strategy must be sequential")
    for key in ("revision", "slice_count"):
        if not re.fullmatch(r"[1-9][0-9]*", scalars[key]):
            raise PlanContractError(f"{label} {key} must be one positive integer")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", scalars["feature"]):
        raise PlanContractError(f"{label} feature must be a lowercase hyphen slug")
    for key in ("decision_ledger_path", "source_prd_path", "source_spec_path"):
        if key in scalars:
            scalars[key] = _repo_path(scalars[key], f"{label} {key}")
    for key in ("product_authority.path", "specification_authority.path"):
        if key in scalars:
            scalars[key] = _repo_path(scalars[key], f"{label} {key}")
    approval = set(scalars) & APPROVAL_SCALARS
    if scalars["status"] == "approved" and approval != APPROVAL_SCALARS:
        raise PlanContractError(f"{label} approved status requires approved_by and approved_at")
    if scalars["status"] == "draft" and approval:
        raise PlanContractError(f"{label} draft status forbids approval fields")
    return scalars, parts[2].lstrip("\r\n")


def parse_exact_contract_rows(
    section: str,
    *,
    label: str,
    scalar_keys: set[str],
    list_keys: set[str] = frozenset(),
    optional_keys: set[str] = frozenset(),
    enum_values: dict[str, set[str]] | None = None,
    path_or_policy_keys: set[str] = frozenset(),
) -> dict[str, Any]:
    """Parse exact ``- key: value`` rows and reject duplicate/unknown fields."""
    result: dict[str, Any] = {}
    for raw in section.splitlines():
        if not raw.strip():
            continue
        match = re.fullmatch(r"\s*-\s*([a-z_]+):\s*(\S(?:.*\S)?)\s*", raw)
        if not match:
            raise PlanContractError(f"{label} contains a non-schema row: {raw.strip()}")
        key, value = match.groups()
        if key not in scalar_keys | list_keys | optional_keys:
            raise PlanContractError(f"{label} contains unsupported field: {key}")
        if key in result:
            raise PlanContractError(f"{label} repeats field: {key}")
        if key in list_keys:
            items = [item.strip() for item in value.split(",")]
            if any(not item for item in items) or len(items) != len(set(items)):
                raise PlanContractError(f"{label} {key} must be a duplicate-free comma-separated list")
            result[key] = items
        else:
            result[key] = value
    missing = sorted((scalar_keys | list_keys) - set(result))
    if missing:
        raise PlanContractError(f"{label} lacks fields: {', '.join(missing)}")
    for key, choices in (enum_values or {}).items():
        if result[key] not in choices:
            raise PlanContractError(f"{label} {key} must be one of: {', '.join(sorted(choices))}")
    for key in path_or_policy_keys:
        value = result[key]
        if value.startswith("not_required"):
            if re.fullmatch(r"not_required \| policy=[A-Za-z0-9][A-Za-z0-9._:/-]*", value) is None:
                raise PlanContractError(f"{label} {key} must use not_required | policy=<exact-reference>")
        else:
            for item in [part.strip() for part in value.split(",")]:
                _repo_path(item, f"{label} {key}", allow_glob=True)
    return result


CONTEXT_CAPSULE_KEYS = {
    "max_authority_files",
    "max_evidence_files",
    "max_total_files",
    "max_payload_bytes",
    "max_estimated_tokens",
    "metric_scope",
    "authority_paths",
    "evidence_paths",
}


def _controller_read_path(value: str, label: str) -> str:
    """Validate one canonical runtime read rule from an approved plan."""
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\\" in value
        or value.startswith(("/", "//"))
        or re.match(r"^[A-Za-z]:", value)
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise PlanContractError(f"{label} must be a canonical project-relative read path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise PlanContractError(f"{label} must be a canonical project-relative read path")
    if value == "**":
        raise PlanContractError(f"{label} cannot grant whole-project '**' read access")
    wildcard = value.endswith("/**")
    source = value[:-3] if wildcard else value
    if not source or any(char in source for char in "*?[]") or (not wildcard and "*" in value):
        raise PlanContractError(
            f"{label} allows only exact paths or a terminal dir/** rule"
        )
    return value


def parse_context_capsule_read_paths(
    section: str, *, label: str
) -> list[str]:
    """Parse one scalar Context Capsule and return its sealed read scope."""
    rows = parse_exact_contract_rows(
        section,
        label=label,
        scalar_keys=CONTEXT_CAPSULE_KEYS,
    )
    combined: list[str] = []
    for key in ("authority_paths", "evidence_paths"):
        items = [item.strip() for item in rows[key].split(",")]
        if not items or any(not item for item in items):
            raise PlanContractError(
                f"{label} {key} must be a non-empty comma-separated list"
            )
        for path in items:
            canonical = _controller_read_path(path, f"{label} {key}")
            if canonical not in combined:
                combined.append(canonical)
    return combined


def _path_list(section: str, *, label: str) -> list[str]:
    """Parse one ordered, duplicate-free Markdown bullet list of path rules."""
    paths: list[str] = []
    for raw in section.splitlines():
        if not raw.strip():
            continue
        match = re.fullmatch(r"\s*-\s*(\S(?:.*\S)?)\s*", raw)
        if match is None:
            raise PlanContractError(f"{label} contains a non-path row: {raw.strip()}")
        path = _controller_read_path(match.group(1), label)
        if path in paths:
            raise PlanContractError(f"{label} repeats path: {path}")
        paths.append(path)
    if not paths:
        raise PlanContractError(f"{label} must contain at least one path")
    return paths


def _editable_paths(section: str, *, label: str) -> list[str]:
    values = re.findall(r"(?m)^\s*-\s*editable_paths:\s*(.*?)\s*$", section)
    if len(values) != 1:
        raise PlanContractError(f"{label} requires exactly one editable_paths field")
    paths = [item.strip() for item in values[0].split(",")]
    if any(not item for item in paths):
        raise PlanContractError(
            f"{label} editable_paths must be a non-empty comma-separated list"
        )
    canonical = [
        _controller_read_path(path, f"{label} editable_paths") for path in paths
    ]
    if len(canonical) != len(set(canonical)):
        raise PlanContractError(f"{label} editable_paths must be duplicate-free")
    return canonical


def _path_rule_covers(scope: str, target: str) -> bool:
    if scope == target:
        return True
    if not scope.endswith("/**"):
        return False
    root = scope[:-3].rstrip("/")
    target_root = target[:-3].rstrip("/") if target.endswith("/**") else target
    return target_root == root or target_root.startswith(root + "/")


def _path_rules_overlap(left: str, right: str) -> bool:
    return _path_rule_covers(left, right) or _path_rule_covers(right, left)


def parse_slice_path_contract(
    *,
    owned_section: str,
    expected_section: str,
    scope_section: str,
    context_section: str,
    label: str,
) -> dict[str, list[str]]:
    """Return one slice's exact approved write and read/integration surfaces."""
    write_paths = _path_list(owned_section, label=f"{label} Owned Paths")
    editable_paths = _editable_paths(scope_section, label=f"{label} Scope Contract")
    if write_paths != editable_paths:
        raise PlanContractError(
            f"{label} Owned Paths must exactly equal Scope Contract editable_paths "
            "in order"
        )
    expected_paths = _path_list(
        expected_section, label=f"{label} Expected Paths"
    )
    overlap = [
        path
        for path in expected_paths
        if any(_path_rules_overlap(path, write) for write in write_paths)
    ]
    if overlap:
        raise PlanContractError(
            f"{label} Expected Paths must be disjoint from write paths: "
            + ", ".join(overlap)
        )
    read_paths = parse_context_capsule_read_paths(
        context_section, label=f"{label} Context Capsule Budget"
    )
    missing = [
        path
        for path in expected_paths
        if not any(_path_rule_covers(scope, path) for scope in read_paths)
    ]
    if missing:
        raise PlanContractError(
            f"{label} Expected Paths must be covered by sealed Context Capsule reads: "
            + ", ".join(missing)
        )
    return {
        "write_paths": write_paths,
        "expected_paths": expected_paths,
        "read_paths": read_paths,
    }


def parse_slice_path_contracts(
    text: str, *, label: str = "approved development plan"
) -> dict[str, dict[str, list[str]]]:
    """Return exact per-slice write/read contracts from an approved plan."""
    meta, body = parse_development_plan_frontmatter(text, label=label)
    if meta["status"] != "approved":
        raise PlanContractError(f"{label} must be approved before scopes are sealed")
    matches = list(
        re.finditer(r"(?m)^## Slice ([A-Za-z0-9][A-Za-z0-9._-]*)\s*$", body)
    )
    if len(matches) != int(meta["slice_count"]):
        raise PlanContractError(f"{label} slice_count does not match its Slice sections")
    result: dict[str, dict[str, list[str]]] = {}
    required = (
        "Owned Paths",
        "Expected Paths",
        "Scope Contract",
        "Context Capsule Budget",
    )
    for index, match in enumerate(matches):
        slice_id = match.group(1)
        if slice_id in result:
            raise PlanContractError(f"{label} repeats slice ID: {slice_id}")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        block = body[match.end():end]
        headings = list(re.finditer(r"(?m)^### (\S(?:.*\S)?)\s*$", block))
        sections: dict[str, str] = {}
        for heading_index, heading in enumerate(headings):
            name = heading.group(1)
            section_end = (
                headings[heading_index + 1].start()
                if heading_index + 1 < len(headings)
                else len(block)
            )
            if name in sections:
                raise PlanContractError(
                    f"{label} {slice_id} repeats section: {name}"
                )
            sections[name] = block[heading.end():section_end]
        missing = [name for name in required if name not in sections]
        if missing:
            raise PlanContractError(
                f"{label} {slice_id} lacks path-contract sections: {', '.join(missing)}"
            )
        result[slice_id] = parse_slice_path_contract(
            owned_section=sections["Owned Paths"],
            expected_section=sections["Expected Paths"],
            scope_section=sections["Scope Contract"],
            context_section=sections["Context Capsule Budget"],
            label=f"{label} {slice_id}",
        )
    return result


def parse_slice_read_paths(
    text: str, *, label: str = "approved development plan"
) -> dict[str, list[str]]:
    """Return controller read scopes sealed from each slice Context Capsule."""
    contracts = parse_slice_path_contracts(text, label=label)
    return {
        slice_id: contract["read_paths"]
        for slice_id, contract in contracts.items()
    }


def parse_planned_material_permissions(
    section: str,
    *,
    label: str,
    editable_paths: list[str],
    shared_touchpoints: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Parse exact, pre-authorized material boundary changes from a slice scope."""
    candidate_rows = [
        raw
        for raw in section.splitlines()
        if re.match(r"\s*-\s*planned_material_permission\s*[:|]", raw)
    ]
    rows: list[tuple[str, str]] = []
    for raw in candidate_rows:
        match = re.fullmatch(
            r"\s*-\s*planned_material_permission:\s*(PF-\d{4})\s*\|\s*(\S(?:.*\S)?)\s*",
            raw,
        )
        if not match:
            raise PlanContractError(f"{label} contains malformed planned_material_permission")
        rows.append((match.group(1), match.group(2)))
    permissions: list[dict[str, str]] = []
    seen: set[str] = set()
    touchpoints = {item["id"]: item["path"] for item in shared_touchpoints}
    for permission_id, fields_text in rows:
        if permission_id in seen:
            raise PlanContractError(f"{label} repeats material permission {permission_id}")
        seen.add(permission_id)
        parts = [part.strip() for part in fields_text.split("|")]
        if any("=" not in part for part in parts):
            raise PlanContractError(f"{label} {permission_id} contains a non-schema field")
        pairs = [tuple(piece.strip() for piece in part.split("=", 1)) for part in parts]
        keys = [key for key, _ in pairs]
        if len(keys) != len(set(keys)):
            raise PlanContractError(f"{label} {permission_id} repeats a field")
        fields = dict(pairs)
        exact = {"change_type", "target_kind", "target", "rationale", "decision_authority"}
        if set(fields) != exact or any(not fields[key] for key in exact):
            raise PlanContractError(
                f"{label} {permission_id} requires exactly change_type, target_kind, "
                "target, rationale, and decision_authority"
            )
        if fields["change_type"] not in MATERIAL_CHANGE_TYPES:
            raise PlanContractError(f"{label} {permission_id} has invalid change_type")
        if fields["target_kind"] == "editable_path":
            fields["target"] = _repo_path(fields["target"], f"{label} {permission_id} target")
            if fields["target"] not in editable_paths:
                raise PlanContractError(
                    f"{label} {permission_id} target must equal one declared editable_path"
                )
        elif fields["target_kind"] == "shared_touchpoint":
            if fields["target"] not in touchpoints:
                raise PlanContractError(
                    f"{label} {permission_id} target must equal one shared touchpoint ID"
                )
        else:
            raise PlanContractError(
                f"{label} {permission_id} target_kind must be editable_path or shared_touchpoint"
            )
        if re.fullmatch(r"DEC-[A-Za-z0-9-]+", fields["decision_authority"]) is None:
            raise PlanContractError(
                f"{label} {permission_id} decision_authority must be an exact DEC-* ID"
            )
        permissions.append({"permission_id": permission_id, **fields})
    return permissions


COVERAGE_GATES = {
    "plan-before-engineering",
    "finalize-after-code-freeze",
    "qa-updated",
}
COVERAGE_STRATEGY_KEYS = {
    "automated_identity_namespace",
    "manual_identity_namespace",
    "mandatory_rule",
    "automation_feasibility",
    "capability_prerequisites",
}
SLICE_COVERAGE_KEYS = {
    "acceptance_ids",
    "automated_identity_namespace",
    "manual_identity_namespace",
    "mandatory_identity_ids",
    "automation_feasibility",
    "capability_prerequisites",
    "amendment_authorities",
}


def _capability_ids(value: str, label: str) -> list[str]:
    items = [item.strip() for item in value.split(",")]
    if (
        not items
        or any(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", item) is None for item in items)
        or len(items) != len(set(items))
    ):
        raise PlanContractError(
            f"{label} must be a duplicate-free comma-separated capability ID list"
        )
    return items


def _identity_namespace(value: str, label: str, prefix: str) -> None:
    if re.fullmatch(rf"{prefix}-(?:[A-Z0-9-]+)?\*", value) is None:
        raise PlanContractError(f"{label} must be a canonical {prefix}-...-* namespace")


def parse_coverage_strategy(section: str, *, label: str = "Coverage Strategy") -> dict[str, Any]:
    result = parse_exact_contract_rows(
        section,
        label=label,
        scalar_keys=COVERAGE_STRATEGY_KEYS,
        list_keys={"gates"},
        optional_keys={"manifest_path"},
    )
    if "manifest_path" in result:
        result["manifest_path"] = _repo_path(
            result["manifest_path"], f"{label} manifest_path"
        )
    _identity_namespace(result["automated_identity_namespace"], f"{label} automated_identity_namespace", "AUTO")
    _identity_namespace(result["manual_identity_namespace"], f"{label} manual_identity_namespace", "MANUAL")
    _capability_ids(result["capability_prerequisites"], f"{label} capability_prerequisites")
    gates = set(result["gates"])
    if not {"plan-before-engineering", "finalize-after-code-freeze"}.issubset(gates) or not gates.issubset(COVERAGE_GATES):
        raise PlanContractError(
            f"{label} gates must contain plan-before-engineering and finalize-after-code-freeze, "
            "with optional qa-updated"
        )
    return result


def parse_slice_coverage_contract(section: str, *, label: str) -> dict[str, Any]:
    result = parse_exact_contract_rows(
        section,
        label=label,
        scalar_keys=SLICE_COVERAGE_KEYS,
        optional_keys={"planned_manifest", "finalized_manifest"},
    )
    _identity_namespace(result["automated_identity_namespace"], f"{label} automated_identity_namespace", "AUTO")
    _identity_namespace(result["manual_identity_namespace"], f"{label} manual_identity_namespace", "MANUAL")
    _capability_ids(result["capability_prerequisites"], f"{label} capability_prerequisites")
    for key in ("planned_manifest", "finalized_manifest"):
        if key in result:
            result[key] = _repo_path(result[key], f"{label} {key}")
    return result
