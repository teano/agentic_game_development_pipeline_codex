#!/usr/bin/env python3
"""Deterministic controller for bounded technical-specification convergence."""

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
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 2
V2_RECOVERY_AUTHORIZATION_SCHEMA = 2
STATE_RELATIVE_PATH = Path(".agentic-pipeline/specification-state.json")
SPECIFICATION_ARCHIVE_ROOT_RELATIVE_PATH = Path(".agentic-pipeline/Workflows")
SPECIFICATION_ARTIFACT_DIRECTORIES = (
    "architect-receipts",
    "helper-requests",
    "helper-results",
)
NON_SPECIFICATION_PIPELINE_ARTIFACTS = {
    "development-plan-state.json",
    "findings.json",
    "state.json",
}
NON_SPECIFICATION_PIPELINE_DIRECTORIES = {"outputs"}
RUNTIME_STATE_RELATIVE_PATH = Path(".agentic-pipeline/state.json")
RUNTIME_FINDINGS_RELATIVE_PATH = Path(".agentic-pipeline/findings.json")
V2_RUNTIME_STATE_RELATIVE_PATH = Path(".agentic-pipeline-v2/state.json")
MAX_CYCLES_PER_ARCHITECT = 5
PREACCEPT_RECEIPT_SCHEMA = 1
PREACCEPT_RECEIPT_KEYS = {
    "schema",
    "architect_id",
    "prd_sha256",
    "assessed_spec_sha256",
    "semantic_assessment",
    "section_applicability_inventory",
}
PREACCEPT_INVENTORY_ROW_KEYS = {
    "locator",
    "disposition",
    "authority_or_rationale",
}
HELPER_REQUEST_SCHEMA = 1
HELPER_RESULT_SCHEMA = 1
HELPER_PREFLIGHT_SCHEMA = 1
HELPER_REJECTION_SCHEMA = 1
HELPER_REQUEST_KEYS = {
    "schema",
    "request_id",
    "operation",
    "project_root",
    "route",
    "approved_prd",
    "specification",
    "expected_user_language",
    "allowed_write_paths",
    "artifacts",
    "helper_identity",
    "controller",
    "correction_ids",
}
HELPER_LEGACY_REQUEST_KEYS = HELPER_REQUEST_KEYS - {"controller"}
HELPER_ROUTE_KEYS = {"mode", "submode", "target_operation"}
HELPER_AUTHORITY_KEYS = {"path", "revision", "sha256"}
HELPER_SPECIFICATION_KEYS = {"path", "input"}
HELPER_INPUT_ABSENT_KEYS = {"kind"}
HELPER_INPUT_SHA_KEYS = {"kind", "sha256"}
HELPER_ARTIFACT_PATH_KEYS = {
    "helper_report_path",
    "coverage_path",
    "result_path",
}
HELPER_IDENTITY_KEYS = {
    "entrypoint_path",
    "entrypoint_sha256",
    "result_emitter_path",
    "result_emitter_sha256",
}
HELPER_CONTROLLER_KEYS = {"path", "sha256"}
HELPER_RESULT_KEYS = {
    "schema",
    "request",
    "operation",
    "route",
    "output_specification",
    "outcome",
    "write_paths",
    "artifacts",
    "helper_identity",
}
HELPER_RESULT_REQUEST_KEYS = {"id", "sha256"}
HELPER_RESULT_SPECIFICATION_KEYS = {"path", "sha256"}
HELPER_RESULT_ARTIFACT_KEYS = {"kind", "path", "sha256"}
HELPER_EVIDENCE_KEYS = {"source_spec_sha256", "results"}
HELPER_PREFLIGHT_KEYS = {
    "schema",
    "controller",
    "request",
    "output_specification",
}
HELPER_PREFLIGHT_CONTROLLER_KEYS = {"path", "sha256"}
HELPER_PREFLIGHT_REQUEST_KEYS = {"id", "sha256"}
HELPER_REJECTION_EVENT = "invalid_initial_generation_helper_result_rejected"
HELPER_REJECTION_RECEIPT_KEYS = {
    "schema",
    "event",
    "rejected_at",
    "reason",
    "request_id",
    "request_sha256",
    "result_path",
    "result_sha256",
    "output_specification",
    "preserved_generation_input_sha256",
    "trace_errors",
    "history_length_after",
    "post_state_sha256",
}
_NO_CONTENT_FOOTER_ITEM = (
    r"(?:additional\s+)?assumptions?"
    r"|source\s+conflicts?"
    r"|(?:unresolved\s+)?risks?"
    r"|open\s+questions?"
    r"|additional\s+product\s+obligations?"
)
_NO_CONTENT_FOOTER_PATTERN = re.compile(
    rf"^no\s+(?:{_NO_CONTENT_FOOTER_ITEM})"
    rf"(?:(?:\s*,\s*(?:(?:and|or)\s+)?|\s+(?:and|or)\s+)"
    rf"(?:{_NO_CONTENT_FOOTER_ITEM}))*"
    r"\s+(?:exist|exists|are\s+introduced|is\s+introduced)\s*[.!]?$",
    re.IGNORECASE,
)

V2_RECOVERY_AUTHORIZATION_V1_KEYS = {
    "schema",
    "token",
    "reason",
    "runtime_state_path",
    "runtime_state_sha256",
    "prior_spec_sha256",
}
V2_RECOVERY_AUTHORIZATION_V2_KEYS = {
    "schema",
    "token",
    "reason",
    "revision_kind",
    "prior_requirements",
    "prior_specification",
    "runtime_state_path",
    "runtime_state_sha256",
}
READY_REVISION_RECEIPT_KEYS = {
    "opened_at",
    "reason",
    "new_architect_id",
    "recovery_token",
    "specification_only",
    "revision_kind",
    "recovery_authorization",
    "specification_path",
    "prior_revision",
    "next_revision",
    "prior_ready_sha256",
    "draft_sha256",
    "prior_prd",
    "new_prd",
    "prior_specification",
    "prior_ready",
    "prior_architects",
    "prior_waves",
    "prior_hold_history",
    "prior_total_cycles_completed",
    "spec_ready_disposition",
}


_DEVELOPMENT_PLAN_CONTROLLER_PATH = (
    Path(__file__).resolve().parents[2]
    / "gamedev-development-plan"
    / "scripts"
    / "development_plan_state.py"
)
_DEVELOPMENT_PLAN_CONTROLLER_SPEC = importlib.util.spec_from_file_location(
    "gamedev_development_plan_for_specification",
    _DEVELOPMENT_PLAN_CONTROLLER_PATH,
)
if (
    _DEVELOPMENT_PLAN_CONTROLLER_SPEC is None
    or _DEVELOPMENT_PLAN_CONTROLLER_SPEC.loader is None
):
    raise RuntimeError("Cannot load the canonical Development Plan runtime classifier")
_development_plan_controller = importlib.util.module_from_spec(
    _DEVELOPMENT_PLAN_CONTROLLER_SPEC
)
_DEVELOPMENT_PLAN_CONTROLLER_SPEC.loader.exec_module(_development_plan_controller)

_PIPELINE_V2_PACKAGE_ROOT = (
    Path(__file__).resolve().parents[2] / "gamedev-pipeline" / "scripts"
)
_pipeline_v2_package_root_text = str(_PIPELINE_V2_PACKAGE_ROOT)
_pipeline_v2_path_added = _pipeline_v2_package_root_text not in sys.path
if _pipeline_v2_path_added:
    sys.path.insert(0, _pipeline_v2_package_root_text)
try:
    _pipeline_v2_runner = importlib.import_module("pipeline_v2.runner")
    _pipeline_v2_transaction = importlib.import_module("pipeline_v2.transaction")
finally:
    if _pipeline_v2_path_added:
        sys.path.remove(_pipeline_v2_package_root_text)
if Path(_pipeline_v2_runner.__file__).resolve() != (
    _PIPELINE_V2_PACKAGE_ROOT / "pipeline_v2" / "runner.py"
).resolve():
    raise RuntimeError("Cannot load the canonical pipeline-v2 runner")


class SpecificationStateError(RuntimeError):
    pass


class HelperOutputPreflightError(SpecificationStateError):
    def __init__(self, trace_errors: list[str]) -> None:
        self.trace_errors = list(trace_errors)
        super().__init__(
            "external helper output fails canonical specification preflight: "
            + "; ".join(self.trace_errors)
        )


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def utc_timestamp(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise SpecificationStateError(f"{label} must be an ISO-8601 UTC timestamp") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise SpecificationStateError(f"{label} must be an ISO-8601 UTC timestamp")
    return parsed


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def external_helper_identity() -> dict[str, str]:
    codex_root = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    skill_root = (codex_root / "skills" / "skill-specification-pipeline").resolve()
    entrypoint = skill_root / "SKILL.md"
    emitter = skill_root / "scripts" / "emit_helper_result.py"
    if not entrypoint.is_file() or not emitter.is_file():
        raise SpecificationStateError(
            "external $skill-specification-pipeline entrypoint/result emitter is unavailable"
        )
    return {
        "entrypoint_path": str(entrypoint),
        "entrypoint_sha256": sha256(entrypoint),
        "result_emitter_path": str(emitter),
        "result_emitter_sha256": sha256(emitter),
    }


def specification_controller_identity() -> dict[str, str]:
    controller = Path(__file__).resolve()
    return {
        "path": str(controller),
        "sha256": sha256(controller),
    }


def parse_frontmatter(path: Path, label: str) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise SpecificationStateError(f"{label} must start with YAML frontmatter: {path}")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise SpecificationStateError(f"{label} has unterminated frontmatter: {path}")
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
    return fields


def specification_inventory_locators(path: Path) -> list[str]:
    """Return bounded mechanical locators for authored specification structure."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SpecificationStateError(
            f"Specification must start with YAML frontmatter: {path}"
        )
    try:
        body_start = next(
            index for index in range(1, len(lines)) if lines[index].strip() == "---"
        ) + 1
    except StopIteration as error:
        raise SpecificationStateError(
            f"Specification has unterminated frontmatter: {path}"
        ) from error

    locators: list[str] = []
    structural_blocks: list[tuple[int, int]] = []
    section_starts: list[int] = []
    current_section = ""
    index = body_start
    while index < len(lines):
        line = lines[index]
        heading = re.fullmatch(r"##(?!#)\s+(.+?)\s*", line)
        if heading:
            current_section = heading.group(1).strip()
            line_number = index + 1
            section_starts.append(index)
            locators.append(f"section:L{line_number}:{current_section}")
            index += 1
            continue

        fence = re.match(r"^\s*(```+|~~~+)(.*)$", line)
        if fence:
            marker = fence.group(1)
            end = index + 1
            while end < len(lines) and re.match(
                rf"^\s*{re.escape(marker[0])}{{{len(marker)},}}\s*$", lines[end]
            ) is None:
                end += 1
            if end >= len(lines):
                raise SpecificationStateError(
                    f"Specification has an unterminated fenced block at line {index + 1}"
                )
            content = "\n".join(lines[index + 1 : end])
            fence_info = fence.group(2).strip().casefold()
            section_name = current_section.casefold()
            if any(token in content for token in ("├", "└", "│", "┬", "┼")):
                kind = "hierarchy"
            elif (
                "diagram" in section_name
                or fence_info == "mermaid"
                or re.search(r"(?:-->|->|=>|\bv\b\s*$)", content, re.MULTILINE)
            ):
                kind = "diagram"
            else:
                kind = "fenced-block"
            locators.append(f"{kind}:L{index + 1}-L{end + 1}")
            structural_blocks.append((index, end))
            index = end + 1
            continue

        if (
            line.strip().startswith("|")
            and index + 1 < len(lines)
            and re.fullmatch(
                r"\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*",
                lines[index + 1],
            )
        ):
            end = index + 2
            while end < len(lines) and lines[end].strip().startswith("|"):
                end += 1
            locators.append(f"table:L{index + 1}-L{end}")
            structural_blocks.append((index, end - 1))
            index = end
            continue

        list_item = re.match(r"^(\s*)(?:[-*+]|\d+[.)])\s+\S", line)
        if list_item:
            end = index
            indentation_levels: list[int] = []
            while end < len(lines):
                nested_item = re.match(
                    r"^(\s*)(?:[-*+]|\d+[.)])\s+\S", lines[end]
                )
                if nested_item is None:
                    break
                indentation_levels.append(
                    len(nested_item.group(1).expandtabs(4))
                )
                end += 1
            if (
                len(indentation_levels) >= 2
                and max(indentation_levels) > min(indentation_levels)
            ):
                locators.append(f"hierarchy:L{index + 1}-L{end}")
                structural_blocks.append((index, end - 1))
            index = end
            continue

        if re.search(r"!\[[^\]]*\]\([^\)]+\)", line):
            locators.append(f"diagram:L{index + 1}-L{index + 1}")
            structural_blocks.append((index, index))
        index += 1

    if section_starts:
        final_section_start = section_starts[-1]
        last_nonblank = len(lines) - 1
        while last_nonblank >= body_start and not lines[last_nonblank].strip():
            last_nonblank -= 1
        if last_nonblank > final_section_start:
            paragraph_start = last_nonblank
            while (
                paragraph_start - 1 > final_section_start
                and lines[paragraph_start - 1].strip()
            ):
                paragraph_start -= 1
            paragraph = lines[paragraph_start : last_nonblank + 1]
            normalized_paragraph = re.sub(
                r"\s+", " ", " ".join(item.strip() for item in paragraph)
            ).strip()
            prior_nonblank = paragraph_start - 1
            while (
                prior_nonblank > final_section_start
                and not lines[prior_nonblank].strip()
            ):
                prior_nonblank -= 1
            if (
                paragraph_start > final_section_start + 1
                and not lines[paragraph_start - 1].strip()
                and prior_nonblank > final_section_start
                and _NO_CONTENT_FOOTER_PATTERN.fullmatch(normalized_paragraph)
            ):
                locators.append(
                    f"footer:L{paragraph_start + 1}-L{last_nonblank + 1}"
                )

    if not locators:
        raise SpecificationStateError(
            "Specification has no inventory-addressable top-level section"
        )
    if len(locators) != len(set(locators)):
        raise SpecificationStateError("Specification inventory locators are not unique")
    return locators


def _is_exact_sha256(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _read_helper_json(
    root: Path, supplied_path: str | None, label: str
) -> tuple[Path, bytes, dict[str, Any]]:
    if not isinstance(supplied_path, str) or not supplied_path.strip():
        raise SpecificationStateError(f"{label} path is required")
    artifact_path = resolve_project_path(root, supplied_path.strip(), label)
    if artifact_path.suffix.casefold() != ".json" or not artifact_path.is_file():
        raise SpecificationStateError(
            f"{label} must be one readable in-project JSON file"
        )
    artifact_bytes = artifact_path.read_bytes()
    try:
        artifact = json.loads(artifact_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SpecificationStateError(
            f"{label} must contain valid UTF-8 JSON"
        ) from error
    if not isinstance(artifact, dict):
        raise SpecificationStateError(f"{label} must contain one JSON object")
    return artifact_path, artifact_bytes, artifact


def _helper_input_sha(request: dict[str, Any]) -> str | None:
    binding = (request.get("specification") or {}).get("input")
    if not isinstance(binding, dict):
        raise SpecificationStateError("helper request specification input is malformed")
    if set(binding) == HELPER_INPUT_ABSENT_KEYS and binding.get("kind") == "absent":
        return None
    if (
        set(binding) == HELPER_INPUT_SHA_KEYS
        and binding.get("kind") == "sha256"
        and _is_exact_sha256(binding.get("sha256"))
    ):
        return binding["sha256"]
    raise SpecificationStateError("helper request specification input is malformed")


def _helper_evidence_output(evidence: dict[str, Any]) -> str | None:
    results = evidence.get("results")
    if isinstance(results, list) and results:
        return results[-1]["result"]["summary"]["output_specification"]["sha256"]
    return evidence.get("source_spec_sha256")


def ensure_helper_state(state: dict[str, Any]) -> None:
    state.setdefault("helper_sequence", 0)
    state.setdefault("active_helper_request", None)
    state.setdefault("helper_history", [])
    if (
        type(state["helper_sequence"]) is not int
        or state["helper_sequence"] < 0
        or not isinstance(state["helper_history"], list)
    ):
        raise SpecificationStateError("helper lifecycle state is malformed")
    if "helper_evidence" not in state:
        source_sha = (state.get("specification") or {}).get("sha256")
        if source_sha is not None and not _is_exact_sha256(source_sha):
            source_sha = (state.get("specification") or {}).get(
                "generation_input_sha256"
            )
        state["helper_evidence"] = {
            "source_spec_sha256": source_sha if _is_exact_sha256(source_sha) else None,
            "results": [],
        }


def require_no_active_helper_request(state: dict[str, Any]) -> None:
    ensure_helper_state(state)
    if state.get("active_helper_request") is not None:
        raise SpecificationStateError(
            "an external helper request is active; record its exact result before "
            "another specification transition"
        )


def validate_helper_request(
    root: Path,
    state: dict[str, Any],
    supplied_path: str | None,
    *,
    require_current_identity: bool,
) -> dict[str, Any]:
    label = "controller-issued helper request"
    path, request_bytes, request = _read_helper_json(root, supplied_path, label)
    request_keys = set(request)
    if (
        request_keys != HELPER_REQUEST_KEYS
        and request_keys != HELPER_LEGACY_REQUEST_KEYS
    ):
        raise SpecificationStateError("controller-issued helper request schema is invalid")
    if type(request.get("schema")) is not int or request["schema"] != HELPER_REQUEST_SCHEMA:
        raise SpecificationStateError("controller-issued helper request version is invalid")
    request_id = request.get("request_id")
    if not isinstance(request_id, str) or re.fullmatch(r"HREQ-[0-9]{6}", request_id) is None:
        raise SpecificationStateError("controller-issued helper request id is invalid")
    if path.relative_to(root).as_posix() != (
        f".agentic-pipeline/helper-requests/{request_id}.json"
    ):
        raise SpecificationStateError(
            "controller-issued helper request path is non-canonical"
        )
    if request.get("project_root") != str(root):
        raise SpecificationStateError("controller-issued helper request project is foreign")

    controller_binding = request.get("controller")
    if controller_binding is None:
        if require_current_identity:
            raise SpecificationStateError(
                "controller-issued helper request controller binding is missing"
            )
    elif (
        not isinstance(controller_binding, dict)
        or set(controller_binding) != HELPER_CONTROLLER_KEYS
        or not isinstance(controller_binding.get("path"), str)
        or not Path(controller_binding["path"]).is_absolute()
        or str(Path(controller_binding["path"]).resolve()) != controller_binding["path"]
        or not _is_exact_sha256(controller_binding.get("sha256"))
    ):
        raise SpecificationStateError(
            "controller-issued helper request controller binding is invalid"
        )
    elif require_current_identity and controller_binding != specification_controller_identity():
        raise SpecificationStateError(
            "controller-issued helper request controller binding is stale or foreign"
        )

    route = request.get("route")
    correction_ids = request.get("correction_ids")
    operation = request.get("operation")
    if not isinstance(route, dict) or set(route) != HELPER_ROUTE_KEYS:
        raise SpecificationStateError("controller-issued helper request route is invalid")
    if operation == "generation":
        route_valid = (
            route.get("mode") == "spec-generator"
            and route.get("submode") is None
            and route.get("target_operation") in {"new", "continue"}
            and correction_ids == []
        )
    elif operation == "correction":
        route_valid = (
            route
            == {
                "mode": "spec-assistant",
                "submode": "fragment-capture",
                "target_operation": "continue",
            }
            and isinstance(correction_ids, list)
            and bool(correction_ids)
            and all(isinstance(item, str) and item.strip() for item in correction_ids)
            and len(correction_ids) == len(set(correction_ids))
        )
    else:
        route_valid = False
    if not route_valid:
        raise SpecificationStateError(
            "controller-issued helper request operation/route is invalid"
        )

    expected_prd = {
        "path": state["prd"]["path"],
        "revision": state["prd"]["revision"],
        "sha256": state["prd"]["sha256"],
    }
    approved_prd = request.get("approved_prd")
    if (
        not isinstance(approved_prd, dict)
        or set(approved_prd) != HELPER_AUTHORITY_KEYS
        or approved_prd != expected_prd
    ):
        raise SpecificationStateError(
            "controller-issued helper request PRD authority is stale or foreign"
        )
    prd = resolve_project_path(root, approved_prd["path"], "helper request PRD")
    if not prd.is_file() or sha256(prd) != approved_prd["sha256"]:
        raise SpecificationStateError(
            "controller-issued helper request PRD bytes changed"
        )

    specification = request.get("specification")
    if (
        not isinstance(specification, dict)
        or set(specification) != HELPER_SPECIFICATION_KEYS
        or specification.get("path") != state["specification"]["path"]
    ):
        raise SpecificationStateError(
            "controller-issued helper request specification path is invalid"
        )
    input_sha = _helper_input_sha(request)
    if (
        input_sha is None
        and route.get("target_operation") != "new"
        or input_sha is not None
        and route.get("target_operation") != "continue"
    ):
        raise SpecificationStateError(
            "controller-issued helper request input/target operation is invalid"
        )

    language = require_approved_prd(prd).get("language")
    if (
        not isinstance(language, str)
        or not language.strip()
        or request.get("expected_user_language") != language
    ):
        raise SpecificationStateError(
            "controller-issued helper request language binding is invalid"
        )

    artifacts = request.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != HELPER_ARTIFACT_PATH_KEYS:
        raise SpecificationStateError(
            "controller-issued helper request artifact paths are invalid"
        )
    base = f".agentic-pipeline/helper-results/{request_id}"
    expected_artifacts = {
        "helper_report_path": f"{base}.report.md",
        "coverage_path": f"{base}.coverage.json",
        "result_path": f"{base}.result.json",
    }
    if artifacts != expected_artifacts:
        raise SpecificationStateError(
            "controller-issued helper request artifact paths are non-canonical"
        )
    expected_allowed = [
        state["specification"]["path"],
        expected_artifacts["helper_report_path"],
        expected_artifacts["coverage_path"],
        expected_artifacts["result_path"],
    ]
    if request.get("allowed_write_paths") != expected_allowed:
        raise SpecificationStateError(
            "controller-issued helper request write boundary is invalid"
        )
    for relative in expected_allowed:
        resolve_project_path(root, relative, "helper allowed write path")

    identity = request.get("helper_identity")
    if not isinstance(identity, dict) or set(identity) != HELPER_IDENTITY_KEYS:
        raise SpecificationStateError(
            "controller-issued helper request external identity is invalid"
        )
    if require_current_identity and identity != external_helper_identity():
        raise SpecificationStateError(
            "external $skill-specification-pipeline fingerprint changed or is foreign"
        )
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(request_bytes).hexdigest(),
        "summary": copy.deepcopy(request),
    }


def validate_helper_output_preflight(
    root: Path,
    state: dict[str, Any],
    request_record: dict[str, Any],
    *,
    require_current_identity: bool,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Validate current helper output without consuming or writing controller state."""
    if not isinstance(request_record, dict) or set(request_record) != {
        "path",
        "sha256",
        "summary",
    }:
        raise SpecificationStateError("recorded helper request is malformed")
    current_request = validate_helper_request(
        root,
        state,
        request_record.get("path"),
        require_current_identity=require_current_identity,
    )
    if current_request != request_record:
        raise SpecificationStateError(
            "controller-issued helper request changed after preparation"
        )
    request = current_request["summary"]
    prd = resolve_project_path(root, state["prd"]["path"], "canonical PRD")
    validate_approved_prd_contract(prd)
    if sha256(prd) != state["prd"]["sha256"]:
        raise SpecificationStateError("PRD changed after helper request preparation")

    spec_relative = request["specification"]["path"]
    spec = resolve_project_path(root, spec_relative, "helper output specification")
    if not spec.is_file():
        raise SpecificationStateError(
            "external helper output specification does not exist"
        )
    output_sha = sha256(spec)
    input_sha = _helper_input_sha(request)
    if input_sha is not None and output_sha == input_sha:
        raise SpecificationStateError(
            "external helper output did not change the requested specification"
        )
    try:
        meta, drift = specification_trace(root, prd, spec)
    except SpecificationStateError as error:
        raise HelperOutputPreflightError([str(error)]) from error
    metadata_errors = list(drift)
    try:
        exact_positive_revision(spec, "helper output specification")
    except SpecificationStateError as error:
        metadata_errors.append(str(error))
    if meta.get("status") not in {"draft", "approved"}:
        metadata_errors.append(
            "helper output specification status must be draft or approved"
        )
    if meta.get("language") != request["expected_user_language"]:
        metadata_errors.append(
            "helper output specification language does not match the approved PRD language"
        )
    if metadata_errors:
        raise HelperOutputPreflightError(metadata_errors)

    controller_identity = specification_controller_identity()
    envelope = {
        "schema": HELPER_PREFLIGHT_SCHEMA,
        "controller": controller_identity,
        "request": {
            "id": request["request_id"],
            "sha256": current_request["sha256"],
        },
        "output_specification": {
            "path": spec.relative_to(root).as_posix(),
            "sha256": output_sha,
        },
    }
    return envelope, meta


def validate_helper_result(
    root: Path,
    state: dict[str, Any],
    request_record: dict[str, Any],
    *,
    require_current_identity: bool,
    require_output_bytes: bool,
) -> dict[str, Any]:
    if not isinstance(request_record, dict) or set(request_record) != {
        "path",
        "sha256",
        "summary",
    }:
        raise SpecificationStateError("recorded helper request is malformed")
    current_request = validate_helper_request(
        root,
        state,
        request_record.get("path"),
        require_current_identity=require_current_identity,
    )
    if current_request != request_record:
        raise SpecificationStateError(
            "controller-issued helper request changed after preparation"
        )
    request = current_request["summary"]
    result_relative = request["artifacts"]["result_path"]
    result_path, result_bytes, result = _read_helper_json(
        root, result_relative, "external helper result"
    )
    if set(result) != HELPER_RESULT_KEYS:
        raise SpecificationStateError("external helper result schema is invalid")
    if type(result.get("schema")) is not int or result["schema"] != HELPER_RESULT_SCHEMA:
        raise SpecificationStateError("external helper result version is invalid")
    if result.get("request") != {
        "id": request["request_id"],
        "sha256": current_request["sha256"],
    }:
        raise SpecificationStateError(
            "external helper result does not bind the exact controller request"
        )
    if (
        result.get("operation") != request["operation"]
        or result.get("route") != request["route"]
        or result.get("outcome") != "PASS"
        or result.get("write_paths") != request["allowed_write_paths"]
        or result.get("helper_identity") != request["helper_identity"]
    ):
        raise SpecificationStateError(
            "external helper result route/outcome/write/identity binding is invalid"
        )

    output = result.get("output_specification")
    spec = resolve_project_path(
        root, request["specification"]["path"], "helper output specification"
    )
    if (
        not isinstance(output, dict)
        or set(output) != HELPER_RESULT_SPECIFICATION_KEYS
        or output.get("path") != request["specification"]["path"]
        or not _is_exact_sha256(output.get("sha256"))
        or require_output_bytes
        and (not spec.is_file() or sha256(spec) != output.get("sha256"))
    ):
        raise SpecificationStateError(
            "external helper result output specification SHA is stale or invalid"
        )
    input_sha = _helper_input_sha(request)
    if input_sha is not None and output["sha256"] == input_sha:
        raise SpecificationStateError(
            "external helper result did not change the requested specification"
        )

    expected_artifacts = [
        ("helper_report", request["artifacts"]["helper_report_path"]),
        ("coverage", request["artifacts"]["coverage_path"]),
    ]
    artifacts = result.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != len(expected_artifacts):
        raise SpecificationStateError(
            "external helper result artifact references are incomplete"
        )
    normalized_artifacts: list[dict[str, str]] = []
    for row, (expected_kind, expected_path) in zip(artifacts, expected_artifacts):
        artifact_path = resolve_project_path(root, expected_path, "helper result artifact")
        if (
            not isinstance(row, dict)
            or set(row) != HELPER_RESULT_ARTIFACT_KEYS
            or row.get("kind") != expected_kind
            or row.get("path") != expected_path
            or not _is_exact_sha256(row.get("sha256"))
            or not artifact_path.is_file()
            or artifact_path.stat().st_size == 0
            or sha256(artifact_path) != row.get("sha256")
        ):
            raise SpecificationStateError(
                "external helper result artifact SHA is stale or invalid"
            )
        normalized_artifacts.append(copy.deepcopy(row))
    return {
        "request": current_request,
        "result": {
            "path": result_path.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(result_bytes).hexdigest(),
            "summary": {
                "schema": HELPER_RESULT_SCHEMA,
                "request": copy.deepcopy(result["request"]),
                "operation": result["operation"],
                "route": copy.deepcopy(result["route"]),
                "output_specification": copy.deepcopy(output),
                "outcome": "PASS",
                "write_paths": list(result["write_paths"]),
                "artifacts": normalized_artifacts,
                "helper_identity": copy.deepcopy(result["helper_identity"]),
            },
        },
    }


def revalidate_helper_evidence(
    root: Path,
    state: dict[str, Any],
    prd: Path,
    evidence: Any,
    expected_output_sha256: str | None,
) -> dict[str, Any]:
    if not isinstance(evidence, dict) or set(evidence) != HELPER_EVIDENCE_KEYS:
        raise SpecificationStateError(
            "current workflow requires exact controller-consumed helper evidence"
        )
    source_sha = evidence.get("source_spec_sha256")
    if source_sha is not None and not _is_exact_sha256(source_sha):
        raise SpecificationStateError(
            "helper evidence source specification SHA is invalid"
        )
    if sha256(prd) != state["prd"]["sha256"]:
        raise SpecificationStateError("helper evidence PRD authority changed")
    results = evidence.get("results")
    if not isinstance(results, list):
        raise SpecificationStateError("helper result evidence is malformed")
    chain_sha = source_sha
    validated: list[dict[str, Any]] = []
    generation_seen = False
    for index, record in enumerate(results):
        if not isinstance(record, dict):
            raise SpecificationStateError("helper result evidence record is malformed")
        current = validate_helper_result(
            root,
            state,
            record.get("request") if isinstance(record, dict) else {},
            require_current_identity=False,
            require_output_bytes=False,
        )
        if current != record:
            raise SpecificationStateError(
                "external helper request/result/artifacts changed after consumption"
            )
        request = current["request"]["summary"]
        if _helper_input_sha(request) != chain_sha:
            raise SpecificationStateError(
                "external helper result chain does not bind its immediate input SHA"
            )
        if request["operation"] == "generation":
            if index != 0 or generation_seen:
                raise SpecificationStateError(
                    "helper evidence contains a replayed generation operation"
                )
            generation_seen = True
        elif chain_sha is None:
            raise SpecificationStateError(
                "helper correction has no exact source specification SHA"
            )
        chain_sha = current["result"]["summary"]["output_specification"]["sha256"]
        validated.append(current)
    if chain_sha != expected_output_sha256:
        raise SpecificationStateError(
            "helper evidence does not end at the exact current specification SHA"
        )
    return {"source_spec_sha256": source_sha, "results": validated}


def validate_preaccept_receipt(
    root: Path,
    state: dict[str, Any],
    prd: Path,
    spec: Path,
    supplied_path: str | None,
    expected_spec_sha256: str | None = None,
    expected_locators: list[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(supplied_path, str) or not supplied_path.strip():
        raise SpecificationStateError("accept-spec requires --preaccept-receipt")
    receipt_path = resolve_project_path(
        root, supplied_path.strip(), "Architect pre-accept receipt"
    )
    if receipt_path.suffix.casefold() != ".json" or not receipt_path.is_file():
        raise SpecificationStateError(
            "Architect pre-accept receipt must be one readable in-project JSON file"
        )
    receipt_bytes = receipt_path.read_bytes()
    try:
        receipt = json.loads(receipt_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SpecificationStateError(
            "Architect pre-accept receipt must contain valid UTF-8 JSON"
        ) from error
    if not isinstance(receipt, dict) or set(receipt) != PREACCEPT_RECEIPT_KEYS:
        raise SpecificationStateError("Architect pre-accept receipt schema is invalid")
    if type(receipt.get("schema")) is not int or receipt["schema"] != PREACCEPT_RECEIPT_SCHEMA:
        raise SpecificationStateError("Architect pre-accept receipt version is invalid")
    architect_id = receipt.get("architect_id")
    if (
        not isinstance(architect_id, str)
        or not architect_id.strip()
        or not same_actor(architect_id, state.get("active_architect_id", ""))
    ):
        raise SpecificationStateError(
            "Architect pre-accept receipt identity does not match the persistent Architect"
        )
    current_prd_sha = sha256(prd)
    current_spec_sha = expected_spec_sha256 or sha256(spec)
    if receipt.get("prd_sha256") != current_prd_sha:
        raise SpecificationStateError(
            "Architect pre-accept receipt PRD SHA does not match current immutable bytes"
        )
    if receipt.get("assessed_spec_sha256") != current_spec_sha:
        raise SpecificationStateError(
            "Architect pre-accept receipt specification SHA does not match current immutable bytes"
        )
    if receipt.get("semantic_assessment") != "accept":
        raise SpecificationStateError(
            "Architect pre-accept receipt semantic assessment must be accept"
        )
    inventory = receipt.get("section_applicability_inventory")
    if not isinstance(inventory, list) or not inventory:
        raise SpecificationStateError(
            "Architect pre-accept receipt inventory must be non-empty"
        )
    normalized_rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in inventory:
        if not isinstance(row, dict) or set(row) != PREACCEPT_INVENTORY_ROW_KEYS:
            raise SpecificationStateError(
                "Architect pre-accept inventory row schema is invalid"
            )
        locator = row.get("locator")
        disposition = row.get("disposition")
        rationale = row.get("authority_or_rationale")
        if not isinstance(locator, str) or not locator.strip():
            raise SpecificationStateError(
                "Architect pre-accept inventory locator must be non-blank"
            )
        locator = locator.strip()
        if locator in seen:
            raise SpecificationStateError(
                "Architect pre-accept inventory locators must be unique"
            )
        seen.add(locator)
        if disposition != "retain":
            raise SpecificationStateError(
                "Architect pre-accept inventory disposition must be retain before acceptance"
            )
        if not isinstance(rationale, str) or not rationale.strip():
            raise SpecificationStateError(
                "Architect pre-accept inventory rationale/evidence must be non-blank"
            )
        normalized_rows.append(
            {
                "locator": locator,
                "disposition": disposition,
                "authority_or_rationale": rationale.strip(),
            }
        )
    if expected_locators is None:
        if sha256(spec) != current_spec_sha:
            raise SpecificationStateError(
                "Architect pre-accept receipt old structure lacks accepted locator evidence"
            )
        required_locators = specification_inventory_locators(spec)
    else:
        if (
            not isinstance(expected_locators, list)
            or not expected_locators
            or any(not isinstance(item, str) or not item for item in expected_locators)
            or len(expected_locators) != len(set(expected_locators))
        ):
            raise SpecificationStateError(
                "Architect pre-accept receipt accepted locator evidence is malformed"
            )
        required_locators = expected_locators
    if seen != set(required_locators):
        missing = sorted(set(required_locators) - seen)
        extra = sorted(seen - set(required_locators))
        raise SpecificationStateError(
            "Architect pre-accept inventory does not exactly cover the specification "
            f"structure; missing={missing}; extra={extra}"
        )
    normalized_rows.sort(key=lambda row: row["locator"])
    summary = {
        "schema": PREACCEPT_RECEIPT_SCHEMA,
        "architect_id": architect_id.strip(),
        "prd_sha256": current_prd_sha,
        "assessed_spec_sha256": current_spec_sha,
        "semantic_assessment": "accept",
        "inventory_count": len(normalized_rows),
        "inventory_sha256": canonical_json_sha256(normalized_rows),
        "required_locators": required_locators,
    }
    return {
        "path": receipt_path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "summary": summary,
    }


def require_current_preaccept_acceptance(
    root: Path,
    state: dict[str, Any],
    prd: Path,
    spec: Path,
    active_wave: dict[str, Any] | None = None,
) -> dict[str, Any]:
    acceptance = state.get("acceptance") or {}
    accepted_preaccept = acceptance.get("preaccept_receipt")
    if not isinstance(accepted_preaccept, dict):
        raise SpecificationStateError(
            "current workflow requires the exact Architect pre-accept receipt"
        )
    accepted_spec_sha256 = (
        active_wave.get("spec_sha256") if active_wave is not None else sha256(spec)
    )
    accepted_summary = accepted_preaccept.get("summary") or {}
    current_preaccept = validate_preaccept_receipt(
        root,
        state,
        prd,
        spec,
        accepted_preaccept.get("path"),
        accepted_spec_sha256,
        accepted_summary.get("required_locators"),
    )
    helper_evidence = revalidate_helper_evidence(
        root,
        state,
        prd,
        acceptance.get("helper_evidence"),
        accepted_spec_sha256,
    )
    expected_acceptance = {
        "prd_path": state["prd"]["path"],
        "prd_revision": state["prd"]["revision"],
        "prd_sha256": sha256(prd),
        "specification_path": state["specification"]["path"],
        "specification_revision": exact_positive_revision(
            spec, "current specification"
        ),
        "specification_sha256": accepted_spec_sha256,
        "accepted_by": state["active_architect_id"],
        "recovery_token": (state.get("recovery_authorization") or {}).get("token"),
        "preaccept_receipt": current_preaccept,
        "helper_evidence": helper_evidence,
    }
    if (
        not acceptance.get("accepted_at")
        or any(acceptance.get(key) != value for key, value in expected_acceptance.items())
    ):
        raise SpecificationStateError(
            "current workflow requires a fresh accept-spec receipt for the exact current "
            "PRD/spec/revision/recovery/preaccept authority"
        )
    accepted_at = utc_timestamp(acceptance["accepted_at"], "specification acceptance")
    if active_wave is not None:
        started_at = utc_timestamp(
            active_wave.get("started_at"), "active Proofreader wave started_at"
        )
        if accepted_at > started_at:
            raise SpecificationStateError(
                "active Proofreader wave predates the current specification acceptance"
            )
    return acceptance


def require_slug(feature: str) -> str:
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", feature):
        raise SpecificationStateError("feature must be a lowercase hyphen slug")
    return feature


def resolve_project_path(root: Path, supplied: str, label: str) -> Path:
    path = Path(supplied)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise SpecificationStateError(
            f"{label} must stay inside the project root: {path}"
        ) from error
    return path


def product_authority_trace(meta: dict[str, str]) -> dict[str, str | None]:
    return {
        "path": meta.get("source_prd_path") or meta.get("product_authority.path"),
        "revision": meta.get("source_prd_revision")
        or meta.get("product_authority.revision"),
        "sha256": meta.get("source_prd_sha256")
        or meta.get("product_authority.sha256"),
    }


def require_approved_prd(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise SpecificationStateError(f"approved PRD does not exist: {path}")
    meta = parse_frontmatter(path, "PRD")
    if meta.get("document_type") != "product-requirements":
        raise SpecificationStateError("PRD document_type must be product-requirements")
    if meta.get("status") != "approved":
        raise SpecificationStateError("PRD status must be approved")
    if not meta.get("revision"):
        raise SpecificationStateError("PRD revision is required")
    if not meta.get("approved_at") or meta.get("approved_at") == "null":
        raise SpecificationStateError("approved PRD must record approved_at")
    return meta


def validate_approved_prd_contract(
    path: Path, *, label: str = "approved PRD"
) -> dict[str, Any]:
    validator_path = (
        Path(__file__).resolve().parents[2]
        / "gamedev-requirements"
        / "scripts"
        / "validate_product_requirements.py"
    )
    module_spec = importlib.util.spec_from_file_location(
        "gamedev_requirements_validator", validator_path
    )
    if module_spec is None or module_spec.loader is None:
        raise SpecificationStateError("cannot load the approved PRD validator")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    result = module.validate(path, True)
    if not result.get("valid"):
        raise SpecificationStateError(
            f"{label} does not pass the full approved requirements contract: "
            + "; ".join(result.get("errors") or [])
        )
    return result


def exact_positive_revision(path: Path, label: str) -> int:
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) != 3:
        raise SpecificationStateError(f"{label} lacks YAML frontmatter")
    values = re.findall(r"(?m)^revision\s*:\s*(.*?)\s*$", parts[1])
    if len(values) != 1 or not re.fullmatch(r"[1-9][0-9]*", values[0]):
        raise SpecificationStateError(
            f"{label} must contain exactly one unquoted positive integer revision"
        )
    return int(values[0])


def reopened_specification_bytes(
    spec: Path, prd_relative: str, prd_revision: str, prd_sha256: str
) -> tuple[bytes, int, int]:
    text = spec.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) != 3:
        raise SpecificationStateError("specification lacks YAML frontmatter")
    prior_revision = exact_positive_revision(spec, "specification")
    next_revision = prior_revision + 1
    lines = parts[1].splitlines()
    if sum(bool(re.match(r"^status\s*:", line)) for line in lines) != 1:
        raise SpecificationStateError("specification must contain exactly one status")
    flat = any(re.match(r"^source_prd_(?:path|revision|sha256)\s*:", line) for line in lines)
    nested = any(re.match(r"^product_authority\s*:\s*$", line) for line in lines)
    if flat == nested:
        raise SpecificationStateError("specification has ambiguous product authority trace")
    updated: list[str] = []
    parent: str | None = None
    for line in lines:
        stripped = line.strip()
        indentation = len(line) - len(line.lstrip())
        if indentation == 0:
            parent = "product_authority" if stripped == "product_authority:" else None
        if re.match(r"^status\s*:", line):
            updated.append("status: draft")
        elif re.match(r"^revision\s*:", line):
            updated.append(f"revision: {next_revision}")
        elif flat and re.match(r"^source_prd_path\s*:", line):
            updated.append(f"source_prd_path: {prd_relative}")
        elif flat and re.match(r"^source_prd_revision\s*:", line):
            updated.append(f"source_prd_revision: {prd_revision}")
        elif flat and re.match(r"^source_prd_sha256\s*:", line):
            updated.append(f"source_prd_sha256: {prd_sha256}")
        elif nested and parent == "product_authority" and re.match(r"^\s+path\s*:", line):
            updated.append(f"  path: {prd_relative}")
        elif nested and parent == "product_authority" and re.match(r"^\s+revision\s*:", line):
            updated.append(f"  revision: {prd_revision}")
        elif nested and parent == "product_authority" and re.match(r"^\s+sha256\s*:", line):
            updated.append(f"  sha256: {prd_sha256}")
        else:
            updated.append(line)
    result = "---\n" + "\n".join(updated).strip() + "\n---\n" + parts[2].lstrip("\r\n")
    return result.encode("utf-8"), prior_revision, next_revision


def write_bytes_atomically(path: Path, value: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(value)
    os.replace(temporary, path)


def write_new_bytes_atomically(path: Path, value: bytes, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.is_file() and path.read_bytes() == value:
            return
        raise SpecificationStateError(f"{label} already exists with different bytes")
    temporary = path.with_suffix(path.suffix + ".tmp")
    if temporary.exists():
        raise SpecificationStateError(f"{label} temporary path already exists")
    try:
        temporary.write_bytes(value)
        if path.exists():
            raise SpecificationStateError(f"{label} appeared during atomic creation")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def reset_helper_chain(state: dict[str, Any], source_sha256: str | None) -> None:
    ensure_helper_state(state)
    if source_sha256 is not None and not _is_exact_sha256(source_sha256):
        raise SpecificationStateError("helper chain source SHA is invalid")
    state["active_helper_request"] = None
    state["helper_evidence"] = {
        "source_spec_sha256": source_sha256,
        "results": [],
    }


def specification_trace(root: Path, prd: Path, spec: Path) -> tuple[dict[str, str], list[str]]:
    if not spec.is_file():
        return {}, ["specification is missing"]
    meta = parse_frontmatter(spec, "Specification")
    prd_meta = require_approved_prd(prd)
    trace = product_authority_trace(meta)
    expected = {
        "path": prd.relative_to(root).as_posix(),
        "revision": prd_meta["revision"],
        "sha256": sha256(prd),
    }
    drift: list[str] = []
    if meta.get("document_type") != "technical-specification":
        drift.append(
            "document_type: expected 'technical-specification', "
            f"got {meta.get('document_type')!r}"
        )
    drift.extend(
        f"product authority {key}: expected {value!r}, got {trace.get(key)!r}"
        for key, value in expected.items()
        if trace.get(key) != value
    )
    return meta, drift


def state_path(root: Path) -> Path:
    return root / STATE_RELATIVE_PATH


def load_state(root: Path, *, persist_migration: bool = True) -> dict[str, Any]:
    path = state_path(root)
    if not path.is_file():
        raise SpecificationStateError(f"state does not exist; run init first: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    migrated = False
    if data.get("schema_version") == 1:
        data["schema_version"] = SCHEMA_VERSION
        data.setdefault("identity_history", [])
        transition = data.get("ready_revision")
        if isinstance(transition, dict):
            transition.setdefault("specification_only", False)
            transition.setdefault("revision_kind", "prd_revision")
        migrated = True
    if data.get("schema_version") != SCHEMA_VERSION:
        raise SpecificationStateError("unsupported specification state schema")
    refresh_identity_history(data)
    if migrated:
        prd_entry = data.get("prd") or {}
        prd_relative = prd_entry.get("path")
        if not isinstance(prd_relative, str) or not prd_relative:
            raise SpecificationStateError(
                "legacy specification state lacks canonical PRD authority"
            )
        migrated_prd = resolve_project_path(
            root, prd_relative, "legacy state canonical PRD"
        )
        validate_approved_prd_contract(
            migrated_prd, label="legacy state approved PRD"
        )
        if persist_migration:
            write_state_file(path, data)
    return data


def write_state_file(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def save_state(root: Path, state: dict[str, Any]) -> None:
    state["schema_version"] = SCHEMA_VERSION
    refresh_identity_history(state)
    write_state_file(state_path(root), state)


def _is_link_or_junction(path: Path) -> bool:
    return path.is_symlink() or (
        hasattr(path, "is_junction") and path.is_junction()
    )


def _require_archivable_completed_state(root: Path, state: dict[str, Any]) -> str:
    feature_value = state.get("feature")
    if not isinstance(feature_value, str):
        raise SpecificationStateError("existing specification feature is invalid")
    feature = require_slug(feature_value)
    if state.get("status") != "spec_ready":
        raise SpecificationStateError(
            "another feature may be archived only from exact terminal SPEC_READY state"
        )
    for key, label in (
        ("active_helper_request", "active helper request"),
        ("active_wave", "active wave"),
        ("hold", "active hold"),
    ):
        if state.get(key) is not None:
            raise SpecificationStateError(
                f"terminal SPEC_READY archive is blocked by an {label}"
            )
    if any(
        state.get(key) is not None
        for key in ("in_progress_revision", "ready_revision")
    ):
        raise SpecificationStateError(
            "terminal SPEC_READY archive is blocked by a pending revision"
        )

    prd, spec = require_source_unchanged(root, state)
    current_prd_sha = sha256(prd)
    current_spec_sha = sha256(spec)
    specification = state.get("specification")
    ready = state.get("ready")
    acceptance = state.get("acceptance")
    waves = state.get("waves")
    if (
        not isinstance(specification, dict)
        or specification.get("sha256") != current_spec_sha
        or specification.get("status") != "approved"
        or not isinstance(ready, dict)
        or ready.get("prd_sha256") != current_prd_sha
        or ready.get("spec_sha256") != current_spec_sha
        or not isinstance(ready.get("architect_id"), str)
        or not ready["architect_id"].strip()
        or not isinstance(ready.get("proofreader_id"), str)
        or not ready["proofreader_id"].strip()
        or not isinstance(acceptance, dict)
        or acceptance.get("prd_sha256") != current_prd_sha
        or acceptance.get("specification_sha256") != current_spec_sha
        or not isinstance(waves, list)
        or not waves
        or not isinstance(waves[-1], dict)
        or waves[-1].get("outcome") != "spec_ready"
        or waves[-1].get("result_spec_sha256") != current_spec_sha
        or not same_actor(waves[-1].get("architect_id", ""), ready["architect_id"])
        or not same_actor(waves[-1].get("proofreader_id", ""), ready["proofreader_id"])
    ):
        raise SpecificationStateError(
            "another feature has incomplete or inconsistent terminal SPEC_READY evidence"
        )
    proofread = waves[-1].get("proofread")
    questions = proofread.get("questions") if isinstance(proofread, dict) else None
    if (
        not isinstance(proofread, dict)
        or not isinstance(questions, dict)
        or proofread.get("critical") != 0
        or proofread.get("major") != 0
        or not proofread.get("coverage_complete")
        or any(questions.values())
        or (
            proofread.get("minor", 0) != 0
            and proofread.get("minors_engineer_resolvable") is not True
        )
    ):
        raise SpecificationStateError(
            "another feature lacks a clean terminal SPEC_READY proofreader result"
        )
    return feature


def _specification_archive_file(
    root: Path, candidate: Path, *, required: bool = False
) -> tuple[str, bytes] | None:
    pipeline_root = root / ".agentic-pipeline"
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        relative = resolved.relative_to(pipeline_root.resolve())
    except ValueError:
        if required:
            raise SpecificationStateError(
                f"specification archive source is outside .agentic-pipeline: {candidate}"
            )
        return None
    if not relative.parts or relative.parts[0].casefold() == "workflows":
        raise SpecificationStateError(
            "specification archive source overlaps the workflow archive namespace"
        )
    relative_text = relative.as_posix()
    if (
        relative_text.casefold() in NON_SPECIFICATION_PIPELINE_ARTIFACTS
        or relative.parts[0].casefold() in NON_SPECIFICATION_PIPELINE_DIRECTORIES
    ):
        raise SpecificationStateError(
            f"specification archive cannot claim another controller artifact: {relative_text}"
        )
    if not candidate.exists():
        if required:
            raise SpecificationStateError(
                f"required specification archive source does not exist: {candidate}"
            )
        return None
    if _is_link_or_junction(candidate) or not candidate.is_file():
        raise SpecificationStateError(
            f"specification archive source must be a regular file: {candidate}"
        )
    return relative_text, candidate.read_bytes()


def _referenced_specification_artifact_paths(state: dict[str, Any]) -> list[str]:
    paths: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            report_path = value.get("report_path")
            if isinstance(report_path, str) and report_path.strip():
                paths.append(report_path.strip())
            preaccept = value.get("preaccept_receipt")
            if isinstance(preaccept, dict):
                preaccept_path = preaccept.get("path")
                if isinstance(preaccept_path, str) and preaccept_path.strip():
                    paths.append(preaccept_path.strip())
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(state)
    return paths


def _specification_archive_files(
    root: Path, state: dict[str, Any]
) -> dict[str, bytes]:
    pipeline_root = root / ".agentic-pipeline"
    if _is_link_or_junction(pipeline_root) or not pipeline_root.is_dir():
        raise SpecificationStateError(
            ".agentic-pipeline must be a regular project-owned directory"
        )
    state_file = _specification_archive_file(root, state_path(root), required=True)
    if state_file is None:
        raise SpecificationStateError("specification archive lacks its source state")
    files = {state_file[0]: state_file[1]}

    def add(candidate: Path, *, required: bool = False) -> None:
        artifact = _specification_archive_file(root, candidate, required=required)
        if artifact is None:
            return
        relative, value = artifact
        if relative in files and files[relative] != value:
            raise SpecificationStateError(
                f"specification archive source is ambiguous: {relative}"
            )
        files[relative] = value

    for directory_name in SPECIFICATION_ARTIFACT_DIRECTORIES:
        directory = pipeline_root / directory_name
        if not directory.exists():
            continue
        if _is_link_or_junction(directory) or not directory.is_dir():
            raise SpecificationStateError(
                f"specification artifact namespace must be a regular directory: {directory}"
            )
        for candidate in directory.rglob("*"):
            if candidate.is_dir():
                if _is_link_or_junction(candidate):
                    raise SpecificationStateError(
                        f"specification artifact namespace contains a link: {candidate}"
                    )
                continue
            add(candidate, required=True)
    for supplied in _referenced_specification_artifact_paths(state):
        add(Path(supplied))
    return files


def _remove_archived_specification_sources(
    root: Path, archive_root: Path, files: dict[str, bytes]
) -> None:
    pipeline_root = root / ".agentic-pipeline"
    state_relative = STATE_RELATIVE_PATH.name
    parents: set[Path] = set()
    for relative, expected_bytes in files.items():
        if relative == state_relative:
            continue
        source = pipeline_root / relative
        archived = archive_root / relative
        if not archived.is_file() or archived.read_bytes() != expected_bytes:
            raise SpecificationStateError(
                f"published specification archive cannot verify cleanup source: {relative}"
            )
        if _is_link_or_junction(source) or not source.is_file():
            raise SpecificationStateError(
                f"specification archive cleanup source is not a regular file: {source}"
            )
        if source.read_bytes() != expected_bytes:
            raise SpecificationStateError(
                f"specification artifact changed after archive publication: {relative}"
            )
        source.unlink()
        parents.add(source.parent)
    for parent in sorted(parents, key=lambda item: len(item.parts), reverse=True):
        current = parent
        while current != pipeline_root:
            if current == archive_root or current.parent == archive_root:
                break
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent

    source_state = state_path(root)
    expected_state = files[state_relative]
    if not source_state.is_file() or source_state.read_bytes() != expected_state:
        raise SpecificationStateError(
            "specification state changed after archive publication"
        )
    source_state.unlink()


def archive_completed_specification_state(
    root: Path, state: dict[str, Any]
) -> Path:
    feature = _require_archivable_completed_state(root, state)
    files = _specification_archive_files(root, state)
    workflows_root = root / SPECIFICATION_ARCHIVE_ROOT_RELATIVE_PATH
    if workflows_root.exists() and (
        _is_link_or_junction(workflows_root) or not workflows_root.is_dir()
    ):
        raise SpecificationStateError(
            "specification workflow archive root must be a regular directory"
        )
    workflows_root.mkdir(parents=True, exist_ok=True)
    archive_root = workflows_root / feature
    if archive_root.exists() and (
        _is_link_or_junction(archive_root) or not archive_root.is_dir()
    ):
        raise SpecificationStateError(
            "specification archive destination must be a regular directory"
        )

    if archive_root.exists() and any(archive_root.iterdir()):
        raise SpecificationStateError(
            "specification archive destination is non-empty and ambiguous"
        )

    staging_root = workflows_root / f".{feature}.specification-archive.tmp"
    if staging_root.exists():
        raise SpecificationStateError(
            f"incomplete specification archive staging directory requires inspection: {staging_root}"
        )
    staging_root.mkdir()
    for relative, value in sorted(files.items()):
        write_new_bytes_atomically(
            staging_root / relative,
            value,
            f"staged specification archive file {relative}",
        )
    for relative, value in files.items():
        if (staging_root / relative).read_bytes() != value:
            raise SpecificationStateError(
                f"staged specification archive bytes changed: {relative}"
            )
    if archive_root.exists():
        archive_root.rmdir()
    os.replace(staging_root, archive_root)
    for relative, value in files.items():
        if (archive_root / relative).read_bytes() != value:
            raise SpecificationStateError(
                f"published specification archive bytes changed: {relative}"
            )
    _remove_archived_specification_sources(root, archive_root, files)
    return archive_root


def canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def normalized_actor_id(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def same_actor(left: str, right: str) -> bool:
    return bool(normalized_actor_id(left)) and normalized_actor_id(left) == normalized_actor_id(
        right
    )


WORKER_IDENTITY_KEYS = {
    "active_architect_id",
    "architect_id",
    "new_architect_id",
    "proofreader_id",
    "attempted_proofreader_id",
    "accepted_by",
}


def historical_worker_ids(value: Any) -> set[str]:
    result: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "identity_history" and isinstance(item, list):
                result.update(
                    normalized_actor_id(identity)
                    for identity in item
                    if isinstance(identity, str) and normalized_actor_id(identity)
                )
                continue
            if key in WORKER_IDENTITY_KEYS and isinstance(item, str):
                result.add(normalized_actor_id(item))
            elif key == "architects" and isinstance(item, list):
                for architect in item:
                    if isinstance(architect, dict) and isinstance(architect.get("id"), str):
                        result.add(normalized_actor_id(architect["id"]))
            result.update(historical_worker_ids(item))
    elif isinstance(value, list):
        for item in value:
            result.update(historical_worker_ids(item))
    return result


def refresh_identity_history(state: dict[str, Any]) -> None:
    prior = state.get("identity_history", [])
    if not isinstance(prior, list) or any(not isinstance(item, str) for item in prior):
        raise SpecificationStateError("identity_history must be a list of normalized strings")
    normalized_prior = {
        normalized_actor_id(item) for item in prior if normalized_actor_id(item)
    }
    state["identity_history"] = sorted(normalized_prior | historical_worker_ids(state))


def require_runtime_preengineering_gate(runtime: dict[str, Any]) -> None:
    if runtime.get("active_write_lease") is not None:
        raise SpecificationStateError("authority recovery is forbidden with an active write lease")
    if any(
        isinstance(item, dict) and item.get("role") == "engineer"
        for item in runtime.get("write_lease_history", [])
    ):
        raise SpecificationStateError("authority recovery is forbidden after an Engineer lease")
    if (
        runtime.get("engineer_runs")
        or runtime.get("engineer_clean") is not None
        or runtime.get("last_engineer_run_id") is not None
        or runtime.get("last_engineer_outcome") is not None
        or runtime.get("pending_engineer_completion") is not None
        or (runtime.get("implementation_state") or {}).get("status") != "pending"
        or (runtime.get("feature_verification_state") or {}).get("status") != "pending"
    ):
        raise SpecificationStateError("authority recovery is forbidden after Engineer/product evidence")
    for slice_id in runtime.get("ordered_slices", []):
        item = (runtime.get("slices") or {}).get(slice_id) or {}
        if (
            item.get("sealed_at") is not None
            or item.get("status") not in {"pending", "active"}
            or item.get("result_revision") is not None
            or item.get("scope_pre_edit_check") is not None
        ):
            raise SpecificationStateError(
                f"authority recovery is forbidden after engineering/sealing evidence for {slice_id}"
            )


def runtime_recovery_authorization(
    root: Path,
    *,
    recovery_token: str | None,
    reason: str | None,
    prior_spec_sha256: str | None,
    requirements_path: str | None = None,
    requirements_sha256: str | None = None,
    specification_path: str | None = None,
    revision_kind: str = "prd_revision",
    expected_authorization: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    try:
        v2_paths = _development_plan_controller.discover_v2_runtime_states(root)
        legacy_presence = [
            _development_plan_controller.runtime_path_exists(root / path)
            for path in (RUNTIME_STATE_RELATIVE_PATH, RUNTIME_FINDINGS_RELATIVE_PATH)
        ]
    except _development_plan_controller.DevelopmentPlanError as error:
        raise SpecificationStateError(
            f"cannot classify the bound runtime safely: {error}"
        ) from error
    if any(legacy_presence):
        raise SpecificationStateError(
            _development_plan_controller.SCHEMA10_UNSUPPORTED_MESSAGE
        )
    if v2_paths:
        if len(v2_paths) != 1:
            raise SpecificationStateError(
                "multiple v2 runtime state candidates exist; specification authority "
                "binding is ambiguous and fails closed"
            )
        if recovery_token:
            raise SpecificationStateError(
                "v2 specification revision uses the public tokenless reopen route"
            )
        if revision_kind not in {"specification_only", "prd_revision"}:
            raise SpecificationStateError(
                "bound v2 runtime revision kind is invalid"
            )
        v2_path = v2_paths[0]
        try:
            before = v2_path.read_bytes()
            runtime = _development_plan_controller.load_valid_v2_runtime(v2_path)
        except (
            OSError,
            _development_plan_controller.DevelopmentPlanError,
        ) as error:
            raise SpecificationStateError(
                f"bound v2 specification lineage is invalid: {error}"
            ) from error
        authority = runtime.get("authority")
        items = authority.get("items") if isinstance(authority, dict) else None
        requirements = items.get("requirements") if isinstance(items, dict) else None
        specification = items.get("specification") if isinstance(items, dict) else None
        if (
            runtime.get("schema") != 2
            or Path(str(runtime.get("project_root", ""))).resolve() != root
            or not isinstance(authority, dict)
            or set(authority) != {"items", "digest"}
            or set(items or {}) != {"requirements", "specification", "plan"}
            or authority.get("digest") != canonical_json_sha256(items)
            or not isinstance(requirements, dict)
            or set(requirements) != {"path", "sha256"}
            or requirements.get("path") != requirements_path
            or requirements.get("sha256") != requirements_sha256
            or not isinstance(specification, dict)
            or set(specification) != {"path", "sha256"}
            or specification.get("path") != specification_path
            or specification.get("sha256") != prior_spec_sha256
        ):
            raise SpecificationStateError(
                "bound v2 runtime does not match the exact project, requirements, "
                "and prior specification authority"
            )
        try:
            view = _pipeline_v2_runner.Controller(
                _pipeline_v2_transaction.StateStore(v2_path)
            ).status()
            after = v2_path.read_bytes()
        except (OSError, _pipeline_v2_runner.PipelineError) as error:
            raise SpecificationStateError(
                f"bound v2 public status cannot prove a safe checkout: {error}"
            ) from error
        next_action = view.get("next_action") if isinstance(view, dict) else None
        public_status_invalid = (
            before != after
            or not isinstance(view, dict)
            or not isinstance(next_action, dict)
            or next_action.get("kind") != "command"
        )
        if revision_kind == "specification_only":
            public_status_invalid = public_status_invalid or (
                runtime.get("active_assignment") is not None
                or view.get("active_assignment") is not None
                or view.get("open_gates") != []
                or view.get("open_questions") != []
            )
        else:
            public_status_invalid = public_status_invalid or (
                next_action.get("command") != "init"
                or next_action.get("user_input_required") is not False
            )
        if public_status_invalid:
            raise SpecificationStateError(
                "bound v2 public status is not a safe specification-reopen boundary: "
                "the specification-only route is not quiescent, the PRD-change route "
                "does not expose tokenless init with user_input_required=false, status "
                "is terminal or requires checkout recovery, an effect is unknown, or "
                "the runtime changed during authorization"
            )
        authorization = {
            "schema": V2_RECOVERY_AUTHORIZATION_SCHEMA,
            "token": None,
            "reason": reason,
            "revision_kind": revision_kind,
            "prior_requirements": {
                "path": requirements_path,
                "sha256": requirements_sha256,
            },
            "prior_specification": {
                "path": specification_path,
                "sha256": prior_spec_sha256,
            },
            "runtime_state_path": v2_path.relative_to(root).as_posix(),
            "runtime_state_sha256": hashlib.sha256(before).hexdigest(),
        }
        if (
            expected_authorization is not None
            and authorization != expected_authorization
        ):
            raise SpecificationStateError(
                "bound v2 runtime authorization changed after the audited reopen boundary"
            )
        return authorization
    if expected_authorization is not None:
        raise SpecificationStateError(
            "bound runtime authorization disappeared after the audited reopen boundary"
        )
    if recovery_token:
        raise SpecificationStateError(
            "--recovery-token is invalid without a supported v2 runtime binding"
        )
    return None


def require_bound_recovery_continuation(root: Path, state: dict[str, Any]) -> None:
    raw_authorization = state.get("recovery_authorization") or {}
    authorization = (
        normalized_recovery_authorization_for_state(root, state, raw_authorization)
        if raw_authorization
        else raw_authorization
    )
    if not authorization:
        try:
            v2_paths = _development_plan_controller.discover_v2_runtime_states(root)
            legacy_presence = [
                _development_plan_controller.runtime_path_exists(root / path)
                for path in (
                    RUNTIME_STATE_RELATIVE_PATH,
                    RUNTIME_FINDINGS_RELATIVE_PATH,
                )
            ]
        except _development_plan_controller.DevelopmentPlanError as error:
            raise SpecificationStateError(
                f"cannot classify the bound runtime safely: {error}"
            ) from error
        if not v2_paths and not any(legacy_presence):
            return
    runtime_state_path = authorization.get("runtime_state_path")
    authorized_v2_path = (
        isinstance(runtime_state_path, str)
        and Path(runtime_state_path).parent
        == V2_RUNTIME_STATE_RELATIVE_PATH.parent
        and Path(runtime_state_path).suffix == ".json"
    )
    revision_kind = authorization.get("revision_kind")
    prior_requirements = authorization.get("prior_requirements")
    prior_specification = authorization.get("prior_specification")
    if authorized_v2_path and (
        revision_kind not in {"specification_only", "prd_revision"}
        or not isinstance(prior_requirements, dict)
        or set(prior_requirements) != {"path", "sha256"}
        or not isinstance(prior_specification, dict)
        or set(prior_specification) != {"path", "sha256"}
    ):
        raise SpecificationStateError(
            "bound v2 runtime authorization lacks the exact prior authority binding"
        )
    runtime_recovery_authorization(
        root,
        recovery_token=authorization.get("token"),
        reason=authorization.get("reason"),
        prior_spec_sha256=(
            prior_specification.get("sha256")
            if authorized_v2_path
            else authorization.get("prior_spec_sha256")
        ),
        requirements_path=(
            prior_requirements.get("path")
            if authorized_v2_path
            else (state.get("prd") or {}).get("path")
        ),
        requirements_sha256=(
            prior_requirements.get("sha256")
            if authorized_v2_path
            else (state.get("prd") or {}).get("sha256")
        ),
        specification_path=(
            prior_specification.get("path")
            if authorized_v2_path
            else (state.get("specification") or {}).get("path")
        ),
        revision_kind=(revision_kind if authorized_v2_path else "prd_revision"),
        expected_authorization=authorization,
    )


def active_architect(state: dict[str, Any]) -> dict[str, Any]:
    architect_id = state["active_architect_id"]
    for architect in state["architects"]:
        if architect["id"] == architect_id:
            return architect
    raise SpecificationStateError("active Architect is missing from history")


def require_no_runtime_binding(root: Path) -> None:
    if any(
        (root / path).exists()
        for path in (RUNTIME_STATE_RELATIVE_PATH, RUNTIME_FINDINGS_RELATIVE_PATH)
    ):
        raise SpecificationStateError(
            "revise-in-progress is allowed only before runtime pipeline binding"
        )


def require_source_unchanged(root: Path, state: dict[str, Any]) -> tuple[Path, Path]:
    prd = root / state["prd"]["path"]
    spec = root / state["specification"]["path"]
    require_approved_prd(prd)
    current_prd_hash = sha256(prd)
    if current_prd_hash != state["prd"]["sha256"]:
        raise SpecificationStateError(
            "PRD bytes changed; use the sanctioned PRD revision command for the current state"
        )
    _, drift = specification_trace(root, prd, spec)
    if drift:
        raise SpecificationStateError("stale specification trace: " + "; ".join(drift))
    return prd, spec


def finalize_in_progress_revision(
    root: Path, state: dict[str, Any], args: argparse.Namespace
) -> dict[str, Any]:
    transition = state.get("in_progress_revision") or {}
    if (
        transition.get("reason") != args.reason.strip()
        or not same_actor(transition.get("new_architect_id", ""), args.architect_id)
    ):
        raise SpecificationStateError(
            "pending in-progress revision must resume with exact original inputs"
        )
    require_no_runtime_binding(root)
    prd = root / transition["new_prd"]["path"]
    if sha256(prd) != transition["new_prd"]["sha256"]:
        raise SpecificationStateError("pending in-progress revision found changed PRD bytes")
    validate_approved_prd_contract(prd, label="new PRD")
    spec = root / transition["specification_path"]
    current_sha = sha256(spec)
    if current_sha == transition["prior_spec_sha256"]:
        draft_bytes, prior_revision, next_revision = reopened_specification_bytes(
            spec,
            transition["new_prd"]["path"],
            transition["new_prd"]["revision"],
            transition["new_prd"]["sha256"],
        )
        if (
            prior_revision != transition["prior_revision"]
            or next_revision != transition["next_revision"]
            or hashlib.sha256(draft_bytes).hexdigest() != transition["draft_sha256"]
        ):
            raise SpecificationStateError(
                "pending in-progress revision no longer reproduces its audited draft"
            )
        write_bytes_atomically(spec, draft_bytes)
    elif current_sha != transition["draft_sha256"]:
        raise SpecificationStateError(
            "pending in-progress revision found unexpected specification bytes"
        )
    event = copy.deepcopy(transition)
    event["event"] = "in_progress_prd_revision_opened"
    state.setdefault("history", []).append(event)
    now = transition["opened_at"]
    state["prd"] = copy.deepcopy(transition["new_prd"])
    state["specification"] = {
        "path": transition["specification_path"],
        "sha256": transition["draft_sha256"],
        "status": "draft",
        "trace_errors": [],
    }
    state["status"] = "awaiting_accept"
    state["active_architect_id"] = transition["new_architect_id"]
    state["architects"] = [
        {
            "id": transition["new_architect_id"],
            "cycles_completed": 0,
            "started_at": now,
            "ended_at": None,
            "handoff_reason": None,
        }
    ]
    state["total_cycles_completed"] = 0
    state["waves"] = []
    state["active_wave"] = None
    state["hold"] = None
    state["hold_history"] = []
    state["ready"] = None
    state["acceptance"] = None
    reset_helper_chain(state, transition["draft_sha256"])
    state.pop("in_progress_revision", None)
    state["updated_at"] = now
    save_state(root, state)
    return state


def command_revise_in_progress(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root).resolve()
    state = load_state(root)
    require_no_active_helper_request(state)
    if state.get("status") == "in_progress_revision_pending":
        return finalize_in_progress_revision(root, state, args)
    if state.get("status") == "spec_ready":
        raise SpecificationStateError("spec_ready authority must use revise-ready")
    if state.get("status") != "reviewing":
        raise SpecificationStateError("revise-in-progress requires exact reviewing state")
    if state.get("ready") is not None:
        raise SpecificationStateError("reviewing state must not retain SPEC_READY evidence")
    reason = args.reason.strip()
    architect_id = args.architect_id.strip()
    if not reason or not architect_id:
        raise SpecificationStateError("revision reason and fresh Architect identity are required")
    if normalized_actor_id(architect_id) in historical_worker_ids(state):
        raise SpecificationStateError(
            "revise-in-progress requires an Architect identity fresh across specification history"
        )
    require_no_runtime_binding(root)
    prd = resolve_project_path(root, state["prd"]["path"], "canonical PRD")
    spec = resolve_project_path(
        root, state["specification"]["path"], "canonical technical specification"
    )
    if (
        prd.relative_to(root).as_posix() != state["prd"]["path"]
        or spec.relative_to(root).as_posix() != state["specification"]["path"]
    ):
        raise SpecificationStateError("in-progress authority paths are not canonical")
    validation = validate_approved_prd_contract(prd, label="new PRD")
    if not spec.is_file():
        raise SpecificationStateError("in-progress specification does not exist")
    current_spec_sha = sha256(spec)
    if current_spec_sha != state["specification"].get("sha256"):
        raise SpecificationStateError(
            "in-progress specification bytes do not equal controller-recorded SHA"
        )
    active_wave = state.get("active_wave")
    if not isinstance(active_wave, dict) or not isinstance(
        active_wave.get("proofread"), dict
    ):
        raise SpecificationStateError(
            "revise-in-progress requires an active wave with a recorded Proofreader result"
        )
    if active_wave.get("spec_sha256") != current_spec_sha:
        raise SpecificationStateError(
            "active Proofreader wave does not reference the current specification SHA"
        )
    meta = parse_frontmatter(spec, "in-progress specification")
    prior_prd_trace = {
        key: state["prd"].get(key) for key in ("path", "revision", "sha256")
    }
    if (
        meta.get("document_type") != "technical-specification"
        or product_authority_trace(meta) != prior_prd_trace
    ):
        raise SpecificationStateError(
            "in-progress specification frontmatter does not match prior PRD authority"
        )
    acceptance = state.get("acceptance") or {}
    expected_acceptance = {
        "prd_path": state["prd"]["path"],
        "prd_revision": state["prd"]["revision"],
        "prd_sha256": state["prd"]["sha256"],
        "specification_path": state["specification"]["path"],
        "specification_revision": exact_positive_revision(
            spec, "in-progress specification"
        ),
        "specification_sha256": current_spec_sha,
        "accepted_by": state["active_architect_id"],
        "recovery_token": None,
    }
    if (
        not acceptance.get("accepted_at")
        or any(acceptance.get(key) != value for key, value in expected_acceptance.items())
    ):
        raise SpecificationStateError(
            "revise-in-progress requires the exact prior accept-spec receipt"
        )
    accepted_at = utc_timestamp(
        acceptance["accepted_at"], "in-progress acceptance"
    )
    new_prd_meta = require_approved_prd(prd)
    new_prd_sha = sha256(prd)
    try:
        old_revision = int(state["prd"]["revision"])
        new_revision = int(new_prd_meta["revision"])
    except (TypeError, ValueError) as exc:
        raise SpecificationStateError("PRD revisions must be positive integers") from exc
    if new_prd_sha == state["prd"]["sha256"] or new_revision <= old_revision:
        raise SpecificationStateError(
            "revise-in-progress requires a newly approved higher PRD revision and changed SHA"
        )
    prd_approved_at = utc_timestamp(
        new_prd_meta["approved_at"], "new PRD approved_at"
    )
    if prd_approved_at <= accepted_at:
        raise SpecificationStateError(
            "new PRD approval must be fresh after in-progress specification acceptance"
        )
    draft_bytes, prior_revision, next_revision = reopened_specification_bytes(
        spec,
        state["prd"]["path"],
        new_prd_meta["revision"],
        new_prd_sha,
    )
    opened_at = utc_now()
    state["status"] = "in_progress_revision_pending"
    state["in_progress_revision"] = {
        "opened_at": opened_at,
        "reason": reason,
        "new_architect_id": architect_id,
        "revision_kind": "prd_revision",
        "specification_path": state["specification"]["path"],
        "prior_revision": prior_revision,
        "next_revision": next_revision,
        "prior_spec_sha256": current_spec_sha,
        "draft_sha256": hashlib.sha256(draft_bytes).hexdigest(),
        "prior_status": "reviewing",
        "prior_prd": copy.deepcopy(state["prd"]),
        "new_prd": {
            "path": state["prd"]["path"],
            "revision": new_prd_meta["revision"],
            "sha256": new_prd_sha,
            "approved_at": new_prd_meta["approved_at"],
            "validation_sha256": validation["sha256"],
        },
        "prior_specification": copy.deepcopy(state["specification"]),
        "prior_acceptance": copy.deepcopy(state.get("acceptance")),
        "prior_ready": copy.deepcopy(state.get("ready")),
        "prior_architects": copy.deepcopy(state.get("architects", [])),
        "prior_waves": copy.deepcopy(state.get("waves", [])),
        "prior_active_wave": copy.deepcopy(state.get("active_wave")),
        "prior_hold": copy.deepcopy(state.get("hold")),
        "prior_hold_history": copy.deepcopy(state.get("hold_history", [])),
        "prior_total_cycles_completed": state.get("total_cycles_completed", 0),
        "in_progress_disposition": "superseded_by_prd_revision",
    }
    state["updated_at"] = opened_at
    save_state(root, state)
    return finalize_in_progress_revision(root, state, args)


def finalize_ready_revision(
    root: Path, state: dict[str, Any], args: argparse.Namespace
) -> dict[str, Any]:
    transition = state.get("ready_revision") or {}
    if (
        transition.get("reason") != args.reason
        or not same_actor(transition.get("new_architect_id", ""), args.architect_id)
        or transition.get("recovery_token")
        != getattr(args, "recovery_token", None)
        or bool(transition.get("specification_only"))
        != bool(getattr(args, "specification_only", False))
    ):
        raise SpecificationStateError(
            "pending ready-specification revision must resume with exact original inputs"
        )
    if (
        set(transition) != READY_REVISION_RECEIPT_KEYS
        or not _canonical_ready_archive(transition)
    ):
        raise SpecificationStateError("pending ready revision receipt is not canonical")
    _validated_ready_revision_prd(root, transition, label="pending ready revision PRD")
    expected_authorization = normalized_recovery_authorization_for_state(
        root, state, transition.get("recovery_authorization")
    )
    runtime_recovery_authorization(
        root,
        recovery_token=getattr(args, "recovery_token", None),
        reason=args.reason,
        prior_spec_sha256=transition["prior_ready_sha256"],
        requirements_path=transition["prior_prd"]["path"],
        requirements_sha256=transition["prior_prd"]["sha256"],
        specification_path=transition["specification_path"],
        revision_kind=transition.get("revision_kind"),
        expected_authorization=expected_authorization,
    )
    spec = resolve_project_path(
        root, transition["specification_path"], "pending ready revision specification"
    )
    if spec.relative_to(root).as_posix() != transition["specification_path"]:
        raise SpecificationStateError(
            "pending ready revision specification path is not canonical"
        )
    current_sha = sha256(spec)
    if current_sha == transition["prior_ready_sha256"]:
        draft_bytes, prior_revision, next_revision = reopened_specification_bytes(
            spec,
            transition["new_prd"]["path"],
            transition["new_prd"]["revision"],
            transition["new_prd"]["sha256"],
        )
        if (
            prior_revision != transition["prior_revision"]
            or next_revision != transition["next_revision"]
            or hashlib.sha256(draft_bytes).hexdigest() != transition["draft_sha256"]
        ):
            raise SpecificationStateError(
                "pending ready revision no longer reproduces its audited draft"
            )
        write_bytes_atomically(spec, draft_bytes)
    elif current_sha != transition["draft_sha256"]:
        raise SpecificationStateError("pending ready revision found unexpected specification bytes")
    event = copy.deepcopy(transition)
    event["event"] = "ready_specification_revision_opened"
    state.setdefault("history", []).append(event)
    now = transition["opened_at"]
    state["prd"] = copy.deepcopy(transition["new_prd"])
    state["specification"] = {
        "path": transition["specification_path"],
        "sha256": transition["draft_sha256"],
        "status": "draft",
        "trace_errors": [],
    }
    state["status"] = "awaiting_accept"
    state["active_architect_id"] = transition["new_architect_id"]
    state["architects"] = [
        {
            "id": transition["new_architect_id"],
            "cycles_completed": 0,
            "started_at": now,
            "ended_at": None,
            "handoff_reason": None,
        }
    ]
    state["total_cycles_completed"] = 0
    state["waves"] = []
    state["active_wave"] = None
    state["hold"] = None
    state["hold_history"] = []
    state["ready"] = None
    state["acceptance"] = None
    reset_helper_chain(state, transition["draft_sha256"])
    if transition.get("recovery_authorization"):
        state["recovery_authorization"] = copy.deepcopy(
            transition["recovery_authorization"]
        )
    state.pop("ready_revision", None)
    state["updated_at"] = now
    save_state(root, state)
    return state


def _is_receipt_timestamp(value: Any) -> bool:
    try:
        utc_timestamp(value, "committed replay receipt timestamp")
    except SpecificationStateError:
        return False
    return True


def _is_receipt_digest(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _is_receipt_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _normalized_receipt_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = unicodedata.normalize("NFKC", value).strip()
    return normalized or None


def _is_canonical_receipt_id_list(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    normalized = [_normalized_receipt_id(item) for item in value]
    return (
        all(item is not None for item in normalized)
        and len(normalized) == len(set(normalized))
        and value == sorted(set(value))
    )


def _is_canonical_prd_receipt(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    base_keys = {"path", "revision", "sha256"}
    extended_keys = base_keys | {"approved_at", "validation_sha256"}
    if set(value) not in (base_keys, extended_keys):
        return False
    revision = value.get("revision")
    if not (
        isinstance(value.get("path"), str)
        and bool(value["path"])
        and _is_receipt_digest(value.get("sha256"))
        and (
            isinstance(revision, str)
            and bool(re.fullmatch(r"[1-9][0-9]*", revision))
            or isinstance(revision, int)
            and not isinstance(revision, bool)
            and revision > 0
        )
    ):
        return False
    return set(value) == base_keys or (
        _is_receipt_timestamp(value.get("approved_at"))
        and _is_receipt_digest(value.get("validation_sha256"))
    )


def _canonical_ready_archive(event: dict[str, Any]) -> bool:
    prior_ready = event.get("prior_ready")
    prior_specification = event.get("prior_specification")
    prior_prd = event.get("prior_prd")
    new_prd = event.get("new_prd")
    architects = event.get("prior_architects")
    waves = event.get("prior_waves")
    holds = event.get("prior_hold_history")
    total = event.get("prior_total_cycles_completed")
    specification_only = event.get("specification_only")
    prior_revision = event.get("prior_revision")
    next_revision = event.get("next_revision")
    if (
        type(specification_only) is not bool
        or not _is_receipt_timestamp(event.get("opened_at"))
        or not isinstance(event.get("reason"), str)
        or not event["reason"].strip()
        or _normalized_receipt_id(event.get("new_architect_id")) is None
        or type(prior_revision) is not int
        or prior_revision < 1
        or type(next_revision) is not int
        or next_revision != prior_revision + 1
        or not _is_receipt_digest(event.get("prior_ready_sha256"))
        or not _is_receipt_digest(event.get("draft_sha256"))
        or not _is_canonical_prd_receipt(prior_prd)
        or not _is_canonical_prd_receipt(new_prd)
        or not isinstance(prior_ready, dict)
        or set(prior_ready)
        != {"prd_sha256", "spec_sha256", "proofreader_id", "architect_id", "confirmed_at"}
        or prior_ready.get("prd_sha256") != prior_prd.get("sha256")
        or prior_ready.get("spec_sha256") != event.get("prior_ready_sha256")
        or not all(
            _normalized_receipt_id(prior_ready.get(key)) is not None
            for key in ("proofreader_id", "architect_id")
        )
        or not _is_receipt_timestamp(prior_ready.get("confirmed_at"))
        or prior_specification
        != {
            "path": event.get("specification_path"),
            "sha256": event.get("prior_ready_sha256"),
            "status": "approved",
            "trace_errors": [],
        }
        or specification_only
        and new_prd
        != {key: prior_prd.get(key) for key in ("path", "revision", "sha256")}
        or not isinstance(architects, list)
        or not architects
        or not isinstance(waves, list)
        or not waves
        or not isinstance(holds, list)
        or not _is_receipt_count(total)
        or total != len(waves)
    ):
        return False

    architect_keys = {"id", "cycles_completed", "started_at", "ended_at", "handoff_reason"}
    architect_ids: list[str] = []
    architect_cycles: dict[str, int] = {}
    for index, architect in enumerate(architects):
        if not isinstance(architect, dict) or set(architect) != architect_keys:
            return False
        actor_id = architect.get("id")
        cycles = architect.get("cycles_completed")
        if (
            _normalized_receipt_id(actor_id) is None
            or normalized_actor_id(actor_id) in architect_ids
            or not _is_receipt_count(cycles)
            or cycles < 1
            or cycles > MAX_CYCLES_PER_ARCHITECT
            or not _is_receipt_timestamp(architect.get("started_at"))
        ):
            return False
        normalized_id = normalized_actor_id(actor_id)
        architect_ids.append(normalized_id)
        architect_cycles[normalized_id] = cycles
        if index == len(architects) - 1:
            if architect.get("ended_at") is not None or architect.get("handoff_reason") is not None:
                return False
        elif (
            cycles != MAX_CYCLES_PER_ARCHITECT
            or not _is_receipt_timestamp(architect.get("ended_at"))
            or not isinstance(architect.get("handoff_reason"), str)
            or not architect["handoff_reason"].strip()
        ):
            return False
    if (
        sum(architect_cycles.values()) != total
        or not same_actor(prior_ready["architect_id"], architects[-1]["id"])
    ):
        return False

    proofread_keys = {
        "critical",
        "major",
        "minor",
        "questions",
        "minors_engineer_resolvable",
        "coverage_complete",
        "report_path",
        "finding_ids",
        "question_ids",
        "recorded_at",
    }
    question_keys = {"product", "scope", "boundary", "ownership", "public_contract"}
    base_wave_keys = {
        "number",
        "architect_id",
        "proofreader_id",
        "spec_sha256",
        "started_at",
        "proofread",
        "outcome",
        "result_spec_sha256",
        "completed_at",
    }
    wave_counts = {actor_id: 0 for actor_id in architect_ids}
    proofreader_ids: set[str] = set()
    for index, wave in enumerate(waves):
        if not isinstance(wave, dict):
            return False
        outcome = wave.get("outcome")
        expected_wave_keys = base_wave_keys | (
            {"architect_response", "user_decision"}
            if outcome == "revised"
            else {"architect_confirmation"}
            if outcome == "spec_ready"
            else set()
        )
        wave_architect_id = wave.get("architect_id")
        wave_proofreader_id = wave.get("proofreader_id")
        if (
            _normalized_receipt_id(wave_architect_id) is None
            or _normalized_receipt_id(wave_proofreader_id) is None
        ):
            return False
        actor_id = normalized_actor_id(wave_architect_id)
        proofreader_id = normalized_actor_id(wave_proofreader_id)
        proofread = wave.get("proofread")
        if (
            set(wave) != expected_wave_keys
            or not _is_receipt_count(wave.get("number"))
            or wave["number"] != index + 1
            or actor_id not in wave_counts
            or not proofreader_id
            or proofreader_id in proofreader_ids
            or proofreader_id in architect_ids
            or not _is_receipt_digest(wave.get("spec_sha256"))
            or not _is_receipt_digest(wave.get("result_spec_sha256"))
            or not _is_receipt_timestamp(wave.get("started_at"))
            or not _is_receipt_timestamp(wave.get("completed_at"))
            or not isinstance(proofread, dict)
            or set(proofread) != proofread_keys
        ):
            return False
        wave_counts[actor_id] += 1
        proofreader_ids.add(proofreader_id)
        questions = proofread.get("questions")
        finding_ids = proofread.get("finding_ids")
        question_ids = proofread.get("question_ids")
        if (
            not all(_is_receipt_count(proofread.get(key)) for key in ("critical", "major", "minor"))
            or not isinstance(questions, dict)
            or set(questions) != question_keys
            or not all(_is_receipt_count(questions.get(key)) for key in question_keys)
            or type(proofread.get("minors_engineer_resolvable")) is not bool
            or type(proofread.get("coverage_complete")) is not bool
            or not isinstance(proofread.get("report_path"), str)
            or not proofread["report_path"].strip()
            or not _is_canonical_receipt_id_list(finding_ids)
            or len(finding_ids)
            != proofread["critical"] + proofread["major"] + proofread["minor"]
            or not _is_canonical_receipt_id_list(question_ids)
            or len(question_ids) != sum(questions.values())
            or not _is_receipt_timestamp(proofread.get("recorded_at"))
        ):
            return False
        if outcome == "revised":
            user_decision = wave.get("user_decision")
            if (
                index == len(waves) - 1
                or not isinstance(wave.get("architect_response"), str)
                or not wave["architect_response"].strip()
                or user_decision is not None
                and not isinstance(user_decision, str)
                or sum(questions.values()) > 0
                and (not isinstance(user_decision, str) or not user_decision.strip())
            ):
                return False
        elif (
            index != len(waves) - 1
            or wave.get("result_spec_sha256") != wave.get("spec_sha256")
            or not isinstance(wave.get("architect_confirmation"), str)
            or not wave["architect_confirmation"].strip()
            or proofread["critical"]
            or proofread["major"]
            or any(questions.values())
            or not proofread["coverage_complete"]
            or proofread["minor"]
            and not proofread["minors_engineer_resolvable"]
        ):
            return False
    last_wave = waves[-1]
    if (
        wave_counts != architect_cycles
        or last_wave.get("result_spec_sha256") != prior_ready.get("spec_sha256")
        or not same_actor(last_wave.get("architect_id", ""), prior_ready["architect_id"])
        or not same_actor(last_wave.get("proofreader_id", ""), prior_ready["proofreader_id"])
    ):
        return False

    open_hold_keys = {
        "reason",
        "architect_id",
        "cycles_completed",
        "attempted_proofreader_id",
        "entered_at",
        "next_actions",
    }
    resolved_hold_keys = open_hold_keys | {
        "resolved_by",
        "new_architect_id",
        "decision_note",
        "resolved_at",
    }
    if len(holds) != 2 * (len(architects) - 1):
        return False
    for index in range(len(architects) - 1):
        opened = holds[2 * index]
        resolved = holds[2 * index + 1]
        old_architect = architects[index]
        new_architect = architects[index + 1]
        opened_architect_id = opened.get("architect_id") if isinstance(opened, dict) else None
        resolved_architect_id = (
            resolved.get("new_architect_id") if isinstance(resolved, dict) else None
        )
        if (
            not isinstance(opened, dict)
            or set(opened) != open_hold_keys
            or not isinstance(resolved, dict)
            or set(resolved) != resolved_hold_keys
            or opened.get("reason") != "architect_cycle_limit"
            or _normalized_receipt_id(opened_architect_id) is None
            or not same_actor(opened_architect_id, old_architect["id"])
            or not _is_receipt_count(opened.get("cycles_completed"))
            or opened["cycles_completed"] != MAX_CYCLES_PER_ARCHITECT
            or _normalized_receipt_id(opened.get("attempted_proofreader_id")) is None
            or not _is_receipt_timestamp(opened.get("entered_at"))
            or opened.get("next_actions") != ["handoff-architect", "user-gate"]
            or any(resolved.get(key) != value for key, value in opened.items())
            or resolved.get("resolved_by") != "handoff-architect"
            or _normalized_receipt_id(resolved_architect_id) is None
            or not same_actor(resolved_architect_id, new_architect["id"])
            or resolved.get("decision_note") != old_architect["handoff_reason"]
            or resolved.get("resolved_at") != old_architect["ended_at"]
            or resolved.get("resolved_at") != new_architect["started_at"]
            or not _is_receipt_timestamp(resolved.get("resolved_at"))
        ):
            return False
    return True


def _validated_ready_revision_prd(
    root: Path, event: dict[str, Any], *, label: str
) -> Path:
    """Bind a ready-revision receipt to the freshly validated canonical live PRD."""
    new_prd = event.get("new_prd")
    prior_prd = event.get("prior_prd")
    specification_only = event.get("specification_only")
    if (
        type(specification_only) is not bool
        or not isinstance(new_prd, dict)
        or not isinstance(prior_prd, dict)
    ):
        raise SpecificationStateError(f"{label} receipt is malformed")
    try:
        prd = resolve_project_path(root, new_prd.get("path"), label)
    except (TypeError, SpecificationStateError) as error:
        raise SpecificationStateError(f"{label} path is not canonical") from error
    relative_path = prd.relative_to(root).as_posix()
    if relative_path != new_prd.get("path") or relative_path != prior_prd.get("path"):
        raise SpecificationStateError(f"{label} path changed")

    validation = validate_approved_prd_contract(prd, label=label)
    metadata = require_approved_prd(prd)
    live_digest = sha256(prd)
    if validation.get("sha256") != live_digest:
        raise SpecificationStateError(f"{label} changed during validation")
    expected = {
        "path": relative_path,
        "revision": metadata["revision"],
        "sha256": live_digest,
    }
    if not specification_only:
        expected.update(
            {
                "approved_at": metadata["approved_at"],
                "validation_sha256": validation["sha256"],
            }
        )
    if new_prd.get("sha256") != live_digest:
        raise SpecificationStateError(f"{label} found changed PRD bytes")
    if new_prd != expected:
        raise SpecificationStateError(f"{label} receipt does not match the live approved PRD")
    return prd


def _recovery_authorization_archive(
    state: dict[str, Any], authorization: dict[str, Any]
) -> dict[str, Any]:
    if state.get("status") == "ready_revision_pending":
        archive = state.get("ready_revision")
        if (
            not isinstance(archive, dict)
            or archive.get("recovery_authorization") != authorization
        ):
            raise SpecificationStateError(
                "legacy v2 recovery authorization has no exact live pending receipt"
            )
        return archive

    history = state.get("history")
    if not isinstance(history, list):
        raise SpecificationStateError(
            "legacy v2 recovery authorization has no canonical committed history"
        )
    archive = next(
        (
            event
            for event in reversed(history)
            if isinstance(event, dict)
            and event.get("event") == "ready_specification_revision_opened"
        ),
        None,
    )
    if (
        not isinstance(archive, dict)
        or archive.get("recovery_authorization") != authorization
        or state.get("recovery_authorization") != authorization
    ):
        raise SpecificationStateError(
            "legacy v2 recovery authorization does not match live committed history"
        )
    return archive


def normalized_recovery_authorization_for_state(
    root: Path,
    state: dict[str, Any],
    authorization: Any,
) -> dict[str, Any] | None:
    """Return semantic v2 authorization without rewriting its persisted receipt."""
    if authorization is None:
        return None
    if not isinstance(authorization, dict):
        raise SpecificationStateError("bound runtime authorization is malformed")
    schema = authorization.get("schema")
    if type(schema) is not int or schema not in {1, V2_RECOVERY_AUTHORIZATION_SCHEMA}:
        raise SpecificationStateError(
            "v2 recovery authorization schema must be exact integer 1 or 2"
        )

    archive = _recovery_authorization_archive(state, authorization)
    archived_authorization = archive.get("recovery_authorization")
    archived_schema = (
        archived_authorization.get("schema")
        if isinstance(archived_authorization, dict)
        else None
    )
    if (
        type(archived_schema) is not int
        or archived_schema not in {1, V2_RECOVERY_AUTHORIZATION_SCHEMA}
    ):
        raise SpecificationStateError(
            "archived v2 recovery authorization schema must be exact integer 1 or 2"
        )
    live_authorization = (
        archived_authorization
        if state.get("status") == "ready_revision_pending"
        else state.get("recovery_authorization")
    )
    live_schema = (
        live_authorization.get("schema")
        if isinstance(live_authorization, dict)
        else None
    )
    if type(live_schema) is not int or live_schema not in {
        1,
        V2_RECOVERY_AUTHORIZATION_SCHEMA,
    }:
        raise SpecificationStateError(
            "live recovery authorization schema must be exact integer 1 or 2"
        )
    if authorization.get("token") is not None:
        return copy.deepcopy(authorization)
    expected_archive_keys = READY_REVISION_RECEIPT_KEYS | (
        set() if state.get("status") == "ready_revision_pending" else {"event"}
    )
    if (
        set(archive) != expected_archive_keys
        or not _canonical_ready_archive(archive)
        or (
            archive.get("specification_only") is not True
            and authorization.get("schema") == 1
        )
        or archive.get("revision_kind")
        != ("specification_only" if archive.get("specification_only") else "prd_revision")
        or archive.get("recovery_token") is not None
        or archive.get("reason") != authorization.get("reason")
    ):
        raise SpecificationStateError(
            "v2 recovery authorization archive is not canonical for its revision mode"
        )

    prior_prd = archive.get("prior_prd")
    prior_specification = archive.get("prior_specification")
    prior_ready = archive.get("prior_ready")
    if (
        not isinstance(prior_prd, dict)
        or not isinstance(prior_specification, dict)
        or not isinstance(prior_ready, dict)
    ):
        raise SpecificationStateError(
            "v2 recovery authorization lacks canonical prior authority"
        )
    try:
        prior_prd_path = resolve_project_path(
            root, prior_prd.get("path"), "prior runtime requirements"
        )
        prior_specification_path = resolve_project_path(
            root, prior_specification.get("path"), "prior runtime specification"
        )
    except (TypeError, SpecificationStateError) as error:
        raise SpecificationStateError(
            "v2 recovery authorization prior authority paths are not canonical"
        ) from error
    if (
        prior_prd_path.relative_to(root).as_posix() != prior_prd.get("path")
        or prior_specification_path.relative_to(root).as_posix()
        != prior_specification.get("path")
    ):
        raise SpecificationStateError(
            "v2 recovery authorization prior authority paths are not canonical"
        )

    derived = {
        "schema": V2_RECOVERY_AUTHORIZATION_SCHEMA,
        "token": None,
        "reason": archive.get("reason"),
        "revision_kind": archive.get("revision_kind"),
        "prior_requirements": {
            "path": prior_prd.get("path"),
            "sha256": prior_prd.get("sha256"),
        },
        "prior_specification": {
            "path": prior_specification.get("path"),
            "sha256": prior_ready.get("spec_sha256"),
        },
        "runtime_state_path": authorization.get("runtime_state_path"),
        "runtime_state_sha256": authorization.get("runtime_state_sha256"),
    }
    if schema == 1:
        if (
            set(authorization) != V2_RECOVERY_AUTHORIZATION_V1_KEYS
            or archive.get("specification_only") is not True
            or archive.get("revision_kind") != "specification_only"
            or authorization.get("prior_spec_sha256")
            != prior_ready.get("spec_sha256")
        ):
            raise SpecificationStateError(
                "legacy v2 recovery authorization is not the exact released "
                "specification-only schema-1 form"
            )
        return derived
    if schema == V2_RECOVERY_AUTHORIZATION_SCHEMA:
        if set(authorization) != V2_RECOVERY_AUTHORIZATION_V2_KEYS:
            raise SpecificationStateError(
                "v2 recovery authorization schema-2 keyset is invalid"
            )
        if authorization != derived:
            raise SpecificationStateError(
                "v2 recovery authorization does not match its canonical authority archive"
            )
        return copy.deepcopy(authorization)
    raise SpecificationStateError("unsupported v2 recovery authorization schema")


def replay_committed_ready_revision(
    root: Path,
    state: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    history = state.get("history")
    event = history[-1] if isinstance(history, list) and history else None
    if not isinstance(event, dict) or event.get("event") != "ready_specification_revision_opened":
        raise SpecificationStateError("revise-ready requires exact spec_ready state")
    if (
        type(event.get("specification_only")) is not bool
        or not isinstance(event.get("reason"), str)
        or not event["reason"].strip()
        or _normalized_receipt_id(event.get("new_architect_id")) is None
        or event.get("recovery_token") is not None
        and (
            not isinstance(event.get("recovery_token"), str)
            or not event["recovery_token"].strip()
        )
        or not isinstance(event.get("specification_path"), str)
        or not event["specification_path"]
        or not _is_receipt_timestamp(event.get("opened_at"))
        or event.get("recovery_authorization") is not None
        and not isinstance(event.get("recovery_authorization"), dict)
    ):
        raise SpecificationStateError("committed replay receipt changed after commit")
    if (
        event.get("reason") != args.reason
        or not same_actor(event.get("new_architect_id", ""), args.architect_id)
        or event.get("recovery_token") != getattr(args, "recovery_token", None)
        or event["specification_only"] != bool(getattr(args, "specification_only", False))
    ):
        raise SpecificationStateError(
            "committed ready-specification replay requires exact original inputs"
        )

    expected_event_keys = READY_REVISION_RECEIPT_KEYS | {"event"}
    prior_ready = event.get("prior_ready")
    prior_specification = event.get("prior_specification")
    prior_prd = event.get("prior_prd")
    new_prd = event.get("new_prd")
    prior_revision = event.get("prior_revision")
    next_revision = event.get("next_revision")
    specification_only = event.get("specification_only")
    if (
        set(event) != expected_event_keys
        or not isinstance(prior_ready, dict)
        or not isinstance(prior_specification, dict)
        or not isinstance(prior_prd, dict)
        or not isinstance(new_prd, dict)
        or not isinstance(prior_revision, int)
        or isinstance(prior_revision, bool)
        or not isinstance(next_revision, int)
        or isinstance(next_revision, bool)
        or prior_revision < 1
        or next_revision != prior_revision + 1
        or not _canonical_ready_archive(event)
        or event.get("revision_kind")
        != ("specification_only" if specification_only else "prd_revision")
        or event.get("spec_ready_disposition")
        != (
            "revoked_by_specification_revision"
            if specification_only
            else "revoked_by_prd_revision"
        )
    ):
        raise SpecificationStateError("committed replay receipt changed after commit")
    expected_authorization = normalized_recovery_authorization_for_state(
        root, state, event.get("recovery_authorization")
    )
    runtime_recovery_authorization(
        root,
        recovery_token=getattr(args, "recovery_token", None),
        reason=args.reason,
        prior_spec_sha256=event["prior_ready_sha256"],
        requirements_path=prior_prd.get("path"),
        requirements_sha256=prior_prd.get("sha256"),
        specification_path=event["specification_path"],
        revision_kind=event.get("revision_kind"),
        expected_authorization=expected_authorization,
    )
    _validated_ready_revision_prd(root, event, label="committed replay PRD")

    spec = resolve_project_path(
        root, event.get("specification_path"), "committed replay specification"
    )
    if spec.relative_to(root).as_posix() != event.get("specification_path"):
        raise SpecificationStateError("committed replay specification path changed")
    if sha256(spec) != event.get("draft_sha256"):
        raise SpecificationStateError("committed replay draft bytes changed")
    meta = parse_frontmatter(spec, "committed replay specification")
    expected_trace = {
        key: new_prd.get(key) for key in ("path", "revision", "sha256")
    }
    if (
        meta.get("status") != "draft"
        or exact_positive_revision(spec, "committed replay specification")
        != next_revision
        or product_authority_trace(meta) != expected_trace
    ):
        raise SpecificationStateError("committed replay draft authority changed")

    expected_projection = {
        "status": "awaiting_accept",
        "prd": copy.deepcopy(new_prd),
        "specification": {
            "path": event["specification_path"],
            "sha256": event["draft_sha256"],
            "status": "draft",
            "trace_errors": [],
        },
        "active_architect_id": event["new_architect_id"],
        "architects": [
            {
                "id": event["new_architect_id"],
                "cycles_completed": 0,
                "started_at": event["opened_at"],
                "ended_at": None,
                "handoff_reason": None,
            }
        ],
        "total_cycles_completed": 0,
        "waves": [],
        "active_wave": None,
        "hold": None,
        "hold_history": [],
        "ready": None,
        "acceptance": None,
        "recovery_authorization": copy.deepcopy(event.get("recovery_authorization")),
        "updated_at": event["opened_at"],
    }
    if (
        "ready_revision" in state
        or normalized_actor_id(event["new_architect_id"])
        not in state.get("identity_history", [])
        or any(state.get(key) != value for key, value in expected_projection.items())
    ):
        raise SpecificationStateError("committed state projection changed after replay receipt")
    return state


def command_revise_ready(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root).resolve()
    state = load_state(root)
    require_no_active_helper_request(state)
    if state.get("status") == "ready_revision_pending":
        return finalize_ready_revision(root, state, args)
    if state.get("status") == "awaiting_accept":
        history = state.get("history")
        if (
            isinstance(history, list)
            and history
            and isinstance(history[-1], dict)
            and history[-1].get("event") == "ready_specification_revision_opened"
        ):
            return replay_committed_ready_revision(root, state, args)
    if state.get("status") != "spec_ready" or not isinstance(state.get("ready"), dict):
        raise SpecificationStateError("revise-ready requires exact spec_ready state")
    specification_only = bool(getattr(args, "specification_only", False))
    architect_id = args.architect_id.strip()
    if not args.reason.strip() or not architect_id:
        raise SpecificationStateError("revision reason and fresh Architect identity are required")
    if normalized_actor_id(architect_id) in historical_worker_ids(state):
        raise SpecificationStateError(
            "revise-ready requires an Architect identity fresh across specification history"
        )
    prd = resolve_project_path(root, state["prd"]["path"], "canonical PRD")
    spec = resolve_project_path(
        root, state["specification"]["path"], "canonical technical specification"
    )
    if (
        prd.relative_to(root).as_posix() != state["prd"]["path"]
        or spec.relative_to(root).as_posix() != state["specification"]["path"]
    ):
        raise SpecificationStateError("ready authority paths are not canonical")
    validation = validate_approved_prd_contract(
        prd,
        label=(
            "unchanged specification-only PRD"
            if specification_only
            else "new PRD"
        ),
    )
    if not spec.is_file() or sha256(spec) != state["ready"].get("spec_sha256"):
        raise SpecificationStateError(
            "ready specification bytes do not equal controller-recorded SPEC_READY SHA"
        )
    meta = parse_frontmatter(spec, "ready specification")
    prior_prd_trace = {
        key: state["prd"].get(key) for key in ("path", "revision", "sha256")
    }
    if (
        meta.get("status") != "approved"
        or product_authority_trace(meta) != prior_prd_trace
        or state["ready"].get("prd_sha256") != state["prd"].get("sha256")
    ):
        raise SpecificationStateError(
            "ready specification frontmatter does not match prior SPEC_READY authority"
        )
    new_prd_meta = require_approved_prd(prd)
    new_prd_sha = sha256(prd)
    try:
        old_revision = int(state["prd"]["revision"])
        new_revision = int(new_prd_meta["revision"])
    except (TypeError, ValueError) as exc:
        raise SpecificationStateError("PRD revisions must be positive integers") from exc
    if specification_only:
        if (
            new_prd_sha != state["prd"]["sha256"]
            or new_revision != old_revision
        ):
            raise SpecificationStateError(
                "specification-only revision requires the exact unchanged approved PRD"
            )
        prd_approved_at = None
    else:
        if new_prd_sha == state["prd"]["sha256"] or new_revision <= old_revision:
            raise SpecificationStateError(
                "revise-ready requires a newly approved higher PRD revision and changed SHA; "
                "use --specification-only when product authority is unchanged"
            )
        ready_at = utc_timestamp(
            state["ready"].get("confirmed_at") or "", "prior SPEC_READY confirmation"
        )
        prd_approved_at = utc_timestamp(
            new_prd_meta["approved_at"], "new PRD approved_at"
        )
        if prd_approved_at <= ready_at:
            raise SpecificationStateError(
                "new PRD approval must be fresh after prior SPEC_READY"
            )
    authorization = runtime_recovery_authorization(
        root,
        recovery_token=getattr(args, "recovery_token", None),
        reason=args.reason,
        prior_spec_sha256=state["ready"]["spec_sha256"],
        requirements_path=state["prd"]["path"],
        requirements_sha256=state["prd"]["sha256"],
        specification_path=state["specification"]["path"],
        revision_kind=("specification_only" if specification_only else "prd_revision"),
    )
    if (
        authorization
        and prd_approved_at is not None
        and authorization.get("hold_opened_at") is not None
        and prd_approved_at
        <= utc_timestamp(
            authorization["hold_opened_at"], "authority recovery hold opened_at"
        )
    ):
        raise SpecificationStateError("new PRD approval must be fresh after the recovery hold")
    draft_bytes, prior_revision, next_revision = reopened_specification_bytes(
        spec,
        state["prd"]["path"],
        new_prd_meta["revision"],
        new_prd_sha,
    )
    opened_at = utc_now()
    state["status"] = "ready_revision_pending"
    state["ready_revision"] = {
        "opened_at": opened_at,
        "reason": args.reason,
        "new_architect_id": architect_id,
        "recovery_token": getattr(args, "recovery_token", None),
        "specification_only": specification_only,
        "revision_kind": "specification_only" if specification_only else "prd_revision",
        "recovery_authorization": copy.deepcopy(authorization),
        "specification_path": state["specification"]["path"],
        "prior_revision": prior_revision,
        "next_revision": next_revision,
        "prior_ready_sha256": state["ready"]["spec_sha256"],
        "draft_sha256": hashlib.sha256(draft_bytes).hexdigest(),
        "prior_prd": copy.deepcopy(state["prd"]),
        "new_prd": (
            {
                "path": state["prd"]["path"],
                "revision": new_prd_meta["revision"],
                "sha256": new_prd_sha,
            }
            if specification_only
            else {
                "path": state["prd"]["path"],
                "revision": new_prd_meta["revision"],
                "sha256": new_prd_sha,
                "approved_at": new_prd_meta["approved_at"],
                "validation_sha256": validation["sha256"],
            }
        ),
        "prior_specification": copy.deepcopy(state["specification"]),
        "prior_ready": copy.deepcopy(state["ready"]),
        "prior_architects": copy.deepcopy(state.get("architects", [])),
        "prior_waves": copy.deepcopy(state.get("waves", [])),
        "prior_hold_history": copy.deepcopy(state.get("hold_history", [])),
        "prior_total_cycles_completed": state.get("total_cycles_completed", 0),
        "spec_ready_disposition": (
            "revoked_by_specification_revision"
            if specification_only
            else "revoked_by_prd_revision"
        ),
    }
    state["updated_at"] = opened_at
    save_state(root, state)
    return finalize_ready_revision(root, state, args)


def command_init(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root).resolve()
    feature = require_slug(args.feature)
    architect_id = args.architect_id.strip()
    if not architect_id:
        raise SpecificationStateError("initial Architect identity is required")
    prd = resolve_project_path(root, args.prd, "approved PRD")
    spec = resolve_project_path(root, args.spec, "technical specification")
    validate_approved_prd_contract(prd)
    if state_path(root).is_file():
        existing = load_state(root, persist_migration=False)
        if existing["feature"] != feature:
            archive_completed_specification_state(root, existing)
        else:
            existing = load_state(root)
            requested_paths = (
                prd.relative_to(root).as_posix(),
                spec.relative_to(root).as_posix(),
            )
            recorded_paths = (
                existing["prd"]["path"],
                existing["specification"]["path"],
            )
            if requested_paths != recorded_paths:
                raise SpecificationStateError(
                    "specification state already exists with different repository-owned paths"
                )
            return existing
    prd_meta = require_approved_prd(prd)
    spec_meta, drift = specification_trace(root, prd, spec)
    now = utc_now()
    state = {
        "schema_version": SCHEMA_VERSION,
        "feature": feature,
        "status": "needs_generation" if drift else "reviewing",
        "prd": {
            "path": prd.relative_to(root).as_posix(),
            "revision": prd_meta["revision"],
            "sha256": sha256(prd),
        },
        "specification": {
            "path": spec.relative_to(root).as_posix(),
            "sha256": sha256(spec) if spec.is_file() and not drift else None,
            "generation_input_sha256": sha256(spec) if spec.is_file() else None,
            "trace_errors": drift,
        },
        "active_architect_id": architect_id,
        "architects": [
            {
                "id": architect_id,
                "cycles_completed": 0,
                "started_at": now,
                "ended_at": None,
                "handoff_reason": None,
            }
        ],
        "total_cycles_completed": 0,
        "waves": [],
        "active_wave": None,
        "hold": None,
        "hold_history": [],
        "ready": None,
        "acceptance": None,
        "helper_sequence": 0,
        "active_helper_request": None,
        "helper_history": [],
        "helper_evidence": {
            "source_spec_sha256": (
                sha256(spec) if spec.is_file() else None
            ),
            "results": [],
        },
        "history": [],
        "identity_history": [],
        "created_at": now,
        "updated_at": now,
    }
    if spec_meta and not drift:
        state["specification"]["status"] = spec_meta.get("status")
    save_state(root, state)
    return state


def command_prepare_helper(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root).resolve()
    state = load_state(root)
    require_bound_recovery_continuation(root, state)
    require_no_active_helper_request(state)
    operation = args.operation
    correction_ids = [item.strip() for item in (args.correction_id or [])]
    if (
        any(not item for item in correction_ids)
        or len(correction_ids) != len(set(correction_ids))
    ):
        raise SpecificationStateError("helper correction IDs must be non-blank and distinct")

    prd = resolve_project_path(root, state["prd"]["path"], "canonical PRD")
    spec = resolve_project_path(
        root, state["specification"]["path"], "canonical technical specification"
    )
    validate_approved_prd_contract(prd)
    if sha256(prd) != state["prd"]["sha256"]:
        raise SpecificationStateError("PRD changed after initialization")
    evidence = state["helper_evidence"]
    evidence_output = _helper_evidence_output(evidence)

    if operation == "generation":
        if state["status"] != "needs_generation":
            raise SpecificationStateError(
                "generation helper request is allowed only in needs_generation"
            )
        if correction_ids:
            raise SpecificationStateError(
                "generation helper request cannot carry correction IDs"
            )
        if (evidence.get("results") or []):
            raise SpecificationStateError(
                "generation helper request was already consumed for this convergence"
            )
        revalidate_helper_evidence(root, state, prd, evidence, evidence_output)
        input_sha = evidence_output
        if input_sha is None:
            if spec.exists():
                raise SpecificationStateError(
                    "unrequested local specification bytes exist before generation prepare"
                )
            target_operation = "new"
        else:
            if not spec.is_file() or sha256(spec) != input_sha:
                raise SpecificationStateError(
                    "generation input specification bytes drifted before prepare"
                )
            target_operation = "continue"
        route = {
            "mode": "spec-generator",
            "submode": None,
            "target_operation": target_operation,
        }
    elif operation == "correction":
        if state["status"] not in {"needs_generation", "reviewing", "awaiting_accept"}:
            raise SpecificationStateError(
                f"correction helper request is forbidden in {state['status']}"
            )
        if not correction_ids:
            raise SpecificationStateError(
                "correction helper request requires one or more correction IDs"
            )
        if not spec.is_file():
            raise SpecificationStateError(
                "correction helper request requires an existing specification"
            )
        input_sha = sha256(spec)
        revalidate_helper_evidence(root, state, prd, evidence, input_sha)
        if state["status"] == "needs_generation" and not evidence["results"]:
            raise SpecificationStateError(
                "initial generation must be consumed before a correction request"
            )
        wave = state.get("active_wave")
        if wave is not None:
            if (
                state["status"] != "reviewing"
                or not isinstance(wave, dict)
                or not isinstance(wave.get("proofread"), dict)
            ):
                raise SpecificationStateError(
                    "active-wave correction requires a recorded Proofreader result"
                )
            require_current_preaccept_acceptance(root, state, prd, spec, wave)
            if wave.get("spec_sha256") != input_sha:
                raise SpecificationStateError(
                    "active-wave correction input does not match the reviewed SHA"
                )
        elif state["status"] == "reviewing" and state.get("acceptance") is not None:
            raise SpecificationStateError(
                "accepted specification corrections require a recorded Proofreader wave"
            )
        route = {
            "mode": "spec-assistant",
            "submode": "fragment-capture",
            "target_operation": "continue",
        }
    else:
        raise SpecificationStateError("helper operation must be generation or correction")

    sequence = state["helper_sequence"] + 1
    request_id = f"HREQ-{sequence:06d}"
    request_relative = f".agentic-pipeline/helper-requests/{request_id}.json"
    base = f".agentic-pipeline/helper-results/{request_id}"
    artifacts = {
        "helper_report_path": f"{base}.report.md",
        "coverage_path": f"{base}.coverage.json",
        "result_path": f"{base}.result.json",
    }
    for relative in artifacts.values():
        if resolve_project_path(root, relative, "helper output artifact").exists():
            raise SpecificationStateError(
                "helper output artifact already exists before request preparation"
            )
    request = {
        "schema": HELPER_REQUEST_SCHEMA,
        "request_id": request_id,
        "operation": operation,
        "project_root": str(root),
        "route": route,
        "approved_prd": {
            "path": state["prd"]["path"],
            "revision": state["prd"]["revision"],
            "sha256": state["prd"]["sha256"],
        },
        "specification": {
            "path": state["specification"]["path"],
            "input": (
                {"kind": "absent"}
                if input_sha is None
                else {"kind": "sha256", "sha256": input_sha}
            ),
        },
        "expected_user_language": require_approved_prd(prd)["language"],
        "allowed_write_paths": [
            state["specification"]["path"],
            artifacts["helper_report_path"],
            artifacts["coverage_path"],
            artifacts["result_path"],
        ],
        "artifacts": artifacts,
        "helper_identity": external_helper_identity(),
        "controller": specification_controller_identity(),
        "correction_ids": correction_ids,
    }
    request_path = resolve_project_path(root, request_relative, "helper request")
    request_bytes = (
        json.dumps(request, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    write_new_bytes_atomically(
        request_path, request_bytes, "controller-issued helper request"
    )
    request_record = validate_helper_request(
        root, state, request_relative, require_current_identity=True
    )
    state["helper_sequence"] = sequence
    state["active_helper_request"] = request_record
    state["updated_at"] = utc_now()
    save_state(root, state)
    return state


def command_preflight_helper_output(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root).resolve()
    state = load_state(root, persist_migration=False)
    ensure_helper_state(state)
    active = state.get("active_helper_request")
    if not isinstance(active, dict):
        raise SpecificationStateError(
            "no active controller-issued helper request is awaiting output"
        )
    request = validate_helper_request(
        root,
        state,
        args.request,
        require_current_identity=True,
    )
    if request != active:
        raise SpecificationStateError(
            "preflight request is not the exact active controller-issued request"
        )
    envelope, _ = validate_helper_output_preflight(
        root,
        state,
        request,
        require_current_identity=True,
    )
    return envelope


def _helper_rejection_state_sha256(state: dict[str, Any]) -> str:
    return canonical_json_sha256(
        {key: value for key, value in state.items() if key != "history"}
    )


def _require_initial_generation_rejection_state(state: dict[str, Any]) -> None:
    ensure_helper_state(state)
    if (
        state.get("status") != "needs_generation"
        or state.get("acceptance") is not None
        or state.get("active_wave") is not None
        or state.get("waves") != []
        or state.get("ready") is not None
        or state.get("total_cycles_completed") != 0
        or state.get("helper_sequence") != 1
        or state.get("helper_history") != []
        or state.get("history") != []
    ):
        raise SpecificationStateError(
            "helper-result rejection is limited to the initial generation before further progress"
        )
    evidence = state.get("helper_evidence")
    if (
        not isinstance(evidence, dict)
        or set(evidence) != HELPER_EVIDENCE_KEYS
        or evidence.get("results") != []
    ):
        raise SpecificationStateError(
            "initial generation helper-result rejection cannot revoke helper credit"
        )


def _validate_helper_rejection_receipt(receipt: Any) -> dict[str, Any]:
    if (
        not isinstance(receipt, dict)
        or set(receipt) != HELPER_REJECTION_RECEIPT_KEYS
        or type(receipt.get("schema")) is not int
        or receipt.get("schema") != HELPER_REJECTION_SCHEMA
        or receipt.get("event") != HELPER_REJECTION_EVENT
        or not isinstance(receipt.get("reason"), str)
        or not receipt["reason"]
        or not isinstance(receipt.get("request_id"), str)
        or re.fullmatch(r"HREQ-[0-9]{6}", receipt["request_id"]) is None
        or not _is_exact_sha256(receipt.get("request_sha256"))
        or not isinstance(receipt.get("result_path"), str)
        or not receipt["result_path"]
        or not _is_exact_sha256(receipt.get("result_sha256"))
        or not _is_exact_sha256(receipt.get("preserved_generation_input_sha256"))
        or not isinstance(receipt.get("trace_errors"), list)
        or not receipt["trace_errors"]
        or not all(isinstance(item, str) and item for item in receipt["trace_errors"])
        or type(receipt.get("history_length_after")) is not int
        or receipt["history_length_after"] < 1
        or not _is_exact_sha256(receipt.get("post_state_sha256"))
    ):
        raise SpecificationStateError("helper-result rejection receipt is malformed")
    utc_timestamp(receipt.get("rejected_at"), "helper-result rejection timestamp")
    output = receipt.get("output_specification")
    if (
        not isinstance(output, dict)
        or set(output) != HELPER_RESULT_SPECIFICATION_KEYS
        or not isinstance(output.get("path"), str)
        or not output["path"]
        or not _is_exact_sha256(output.get("sha256"))
        or receipt["preserved_generation_input_sha256"] != output["sha256"]
    ):
        raise SpecificationStateError("helper-result rejection receipt is malformed")
    return receipt


def _replay_rejected_helper_result(
    root: Path,
    state: dict[str, Any],
    request_id: str,
    reason: str,
) -> dict[str, Any]:
    history = state.get("history")
    if not isinstance(history, list) or not history:
        raise SpecificationStateError(
            "no active initial generation helper result can be rejected"
        )
    receipt = _validate_helper_rejection_receipt(history[-1])
    if receipt["request_id"] != request_id or receipt["reason"] != reason:
        raise SpecificationStateError(
            "helper-result rejection replay requires the exact original request ID and reason"
        )
    if (
        len(history) != receipt["history_length_after"]
        or state.get("updated_at") != receipt["rejected_at"]
        or _helper_rejection_state_sha256(state) != receipt["post_state_sha256"]
        or state.get("status") != "needs_generation"
        or state.get("active_helper_request") is not None
        or state.get("helper_history") != []
        or state.get("helper_evidence")
        != {
            "source_spec_sha256": receipt["preserved_generation_input_sha256"],
            "results": [],
        }
    ):
        raise SpecificationStateError(
            "helper-result rejection replay is forbidden after drift or further progress"
        )
    specification = state.get("specification")
    if (
        not isinstance(specification, dict)
        or specification.get("path") != receipt["output_specification"]["path"]
        or specification.get("sha256") is not None
        or specification.get("generation_input_sha256")
        != receipt["preserved_generation_input_sha256"]
        or specification.get("trace_errors") != receipt["trace_errors"]
    ):
        raise SpecificationStateError(
            "helper-result rejection replay is forbidden after state drift"
        )

    request_path = f".agentic-pipeline/helper-requests/{request_id}.json"
    request = validate_helper_request(
        root,
        state,
        request_path,
        require_current_identity=False,
    )
    if request["sha256"] != receipt["request_sha256"]:
        raise SpecificationStateError(
            "rejected controller-issued helper request bytes drifted"
        )
    result = validate_helper_result(
        root,
        state,
        request,
        require_current_identity=False,
        require_output_bytes=True,
    )
    result_record = result["result"]
    if (
        result_record["path"] != receipt["result_path"]
        or result_record["sha256"] != receipt["result_sha256"]
        or result_record["summary"]["output_specification"]
        != receipt["output_specification"]
    ):
        raise SpecificationStateError("rejected helper result bytes drifted")
    try:
        validate_helper_output_preflight(
            root,
            state,
            request,
            require_current_identity=False,
        )
    except HelperOutputPreflightError as error:
        if error.trace_errors != receipt["trace_errors"]:
            raise SpecificationStateError(
                "rejected helper output preflight errors drifted"
            ) from error
    else:
        raise SpecificationStateError(
            "helper-result rejection replay is forbidden for valid output"
        )
    return state


def command_reject_helper_result(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root).resolve()
    state = load_state(root, persist_migration=False)
    request_id = args.request_id
    reason = args.reason
    if (
        not isinstance(request_id, str)
        or request_id != request_id.strip()
        or re.fullmatch(r"HREQ-[0-9]{6}", request_id) is None
    ):
        raise SpecificationStateError("helper-result rejection request ID is invalid")
    if not isinstance(reason, str) or reason != reason.strip() or not reason:
        raise SpecificationStateError("helper-result rejection reason is required")

    active = state.get("active_helper_request")
    if not isinstance(active, dict):
        return _replay_rejected_helper_result(root, state, request_id, reason)
    _require_initial_generation_rejection_state(state)
    request = validate_helper_request(
        root,
        state,
        active.get("path"),
        require_current_identity=False,
    )
    if request != active:
        raise SpecificationStateError(
            "active controller-issued helper request changed after preparation"
        )
    request_summary = request["summary"]
    if (
        request_summary["request_id"] != request_id
        or request_id != "HREQ-000001"
        or request_summary["operation"] != "generation"
    ):
        raise SpecificationStateError(
            "helper-result rejection requires the exact initial generation request"
        )

    prd = resolve_project_path(root, state["prd"]["path"], "canonical PRD")
    input_sha = _helper_input_sha(request_summary)
    revalidate_helper_evidence(
        root,
        state,
        prd,
        state["helper_evidence"],
        input_sha,
    )
    result = validate_helper_result(
        root,
        state,
        request,
        require_current_identity=False,
        require_output_bytes=True,
    )
    try:
        validate_helper_output_preflight(
            root,
            state,
            request,
            require_current_identity=False,
        )
    except HelperOutputPreflightError as error:
        trace_errors = error.trace_errors
    else:
        raise SpecificationStateError(
            "valid helper output cannot be rejected through recovery"
        )

    output = copy.deepcopy(
        result["result"]["summary"]["output_specification"]
    )
    spec = resolve_project_path(
        root, output["path"], "rejected helper output specification"
    )
    confirmed_result = validate_helper_result(
        root,
        state,
        request,
        require_current_identity=False,
        require_output_bytes=True,
    )
    if confirmed_result != result or sha256(spec) != output["sha256"]:
        raise SpecificationStateError(
            "helper output or immutable result artifacts drifted during rejection"
        )
    try:
        meta = parse_frontmatter(spec, "Specification")
    except SpecificationStateError:
        meta = {}
    rejected_at = utc_now()
    reset_helper_chain(state, output["sha256"])
    state["specification"] = {
        **state["specification"],
        "path": output["path"],
        "sha256": None,
        "generation_input_sha256": output["sha256"],
        "status": meta.get("status"),
        "trace_errors": list(trace_errors),
    }
    state["status"] = "needs_generation"
    state["updated_at"] = rejected_at
    refresh_identity_history(state)
    receipt = {
        "schema": HELPER_REJECTION_SCHEMA,
        "event": HELPER_REJECTION_EVENT,
        "rejected_at": rejected_at,
        "reason": reason,
        "request_id": request_id,
        "request_sha256": request["sha256"],
        "result_path": result["result"]["path"],
        "result_sha256": result["result"]["sha256"],
        "output_specification": output,
        "preserved_generation_input_sha256": output["sha256"],
        "trace_errors": list(trace_errors),
        "history_length_after": len(state["history"]) + 1,
        "post_state_sha256": _helper_rejection_state_sha256(state),
    }
    state["history"].append(receipt)
    save_state(root, state)
    return state


def command_record_helper_result(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root).resolve()
    state = load_state(root)
    require_bound_recovery_continuation(root, state)
    ensure_helper_state(state)
    active = state.get("active_helper_request")
    if not isinstance(active, dict):
        raise SpecificationStateError(
            "no active controller-issued helper request is awaiting a result"
        )
    request = validate_helper_request(
        root,
        state,
        active.get("path"),
        require_current_identity=True,
    )
    if request != active:
        raise SpecificationStateError(
            "active controller-issued helper request changed after preparation"
        )
    preflight, meta = validate_helper_output_preflight(
        root,
        state,
        request,
        require_current_identity=True,
    )
    prd = resolve_project_path(root, state["prd"]["path"], "canonical PRD")
    result = validate_helper_result(
        root,
        state,
        request,
        require_current_identity=True,
        require_output_bytes=True,
    )
    input_sha = _helper_input_sha(request["summary"])
    evidence = revalidate_helper_evidence(
        root, state, prd, state["helper_evidence"], input_sha
    )
    updated_evidence = copy.deepcopy(evidence)
    updated_evidence["results"].append(result)
    output_sha = result["result"]["summary"]["output_specification"]["sha256"]
    if output_sha != preflight["output_specification"]["sha256"]:
        raise SpecificationStateError(
            "external helper result does not bind the canonical preflight output"
        )
    updated_evidence = revalidate_helper_evidence(
        root, state, prd, updated_evidence, output_sha
    )
    if any(
        item.get("request", {}).get("summary", {}).get("request_id")
        == request["summary"]["request_id"]
        for item in state["helper_history"]
        if isinstance(item, dict)
    ):
        raise SpecificationStateError("helper request/result replay is forbidden")

    spec = resolve_project_path(
        root, state["specification"]["path"], "helper output specification"
    )
    state["helper_evidence"] = updated_evidence
    state["helper_history"].append(copy.deepcopy(result))
    state["active_helper_request"] = None
    state["specification"] = {
        **state["specification"],
        "path": spec.relative_to(root).as_posix(),
        "sha256": output_sha,
        "status": meta.get("status"),
        "trace_errors": [],
    }
    state["updated_at"] = utc_now()
    save_state(root, state)
    return state


def helper_evidence_for_acceptance(
    root: Path,
    state: dict[str, Any],
    prd: Path,
    spec: Path,
) -> dict[str, Any]:
    require_no_active_helper_request(state)
    current_sha = sha256(spec)
    evidence = revalidate_helper_evidence(
        root, state, prd, state["helper_evidence"], current_sha
    )
    if state["status"] == "needs_generation":
        results = evidence["results"]
        if not results or results[0]["request"]["summary"]["operation"] != "generation":
            raise SpecificationStateError(
                "needs_generation accept-spec requires a consumed external generation result"
            )
    return evidence


def command_accept_spec(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root).resolve()
    state = load_state(root)
    require_bound_recovery_continuation(root, state)
    if state["status"] not in {"needs_generation", "reviewing", "awaiting_accept"}:
        raise SpecificationStateError(f"cannot accept specification in {state['status']}")
    if state.get("active_wave") is not None:
        raise SpecificationStateError(
            "accept-spec is forbidden while a Proofreader wave is active"
        )
    require_no_active_helper_request(state)
    prd = root / state["prd"]["path"]
    spec = root / state["specification"]["path"]
    validate_approved_prd_contract(prd)
    if sha256(prd) != state["prd"]["sha256"]:
        raise SpecificationStateError("PRD changed after initialization")
    meta, drift = specification_trace(root, prd, spec)
    if drift:
        raise SpecificationStateError("cannot accept stale specification: " + "; ".join(drift))
    preaccept_receipt = validate_preaccept_receipt(
        root,
        state,
        prd,
        spec,
        getattr(args, "preaccept_receipt", None),
    )
    helper_evidence = helper_evidence_for_acceptance(root, state, prd, spec)
    state["specification"] = {
        "path": spec.relative_to(root).as_posix(),
        "sha256": sha256(spec),
        "status": meta.get("status"),
        "trace_errors": [],
    }
    state["acceptance"] = {
        "prd_path": state["prd"]["path"],
        "prd_revision": state["prd"]["revision"],
        "prd_sha256": state["prd"]["sha256"],
        "specification_path": state["specification"]["path"],
        "specification_revision": exact_positive_revision(
            spec, "accepted specification"
        ),
        "specification_sha256": state["specification"]["sha256"],
        "accepted_by": state["active_architect_id"],
        "recovery_token": (state.get("recovery_authorization") or {}).get("token"),
        "preaccept_receipt": preaccept_receipt,
        "helper_evidence": helper_evidence,
        "accepted_at": utc_now(),
    }
    state["status"] = "reviewing"
    state["updated_at"] = utc_now()
    save_state(root, state)
    return state


def command_start_cycle(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root).resolve()
    state = load_state(root)
    require_bound_recovery_continuation(root, state)
    require_no_active_helper_request(state)
    if state["status"] != "reviewing":
        raise SpecificationStateError(f"cannot start cycle in {state['status']}")
    if state["active_wave"] is not None:
        raise SpecificationStateError("a Proofreader wave is already active")
    prd, spec = require_source_unchanged(root, state)
    require_current_preaccept_acceptance(root, state, prd, spec)
    architect = active_architect(state)
    if not same_actor(args.architect_id, architect["id"]):
        raise SpecificationStateError("cycle Architect does not own the specification")
    proofreader_id = args.proofreader_id.strip()
    if not proofreader_id:
        raise SpecificationStateError("a fresh Proofreader identity is required")
    prior_worker_ids = historical_worker_ids(state)
    if normalized_actor_id(proofreader_id) in prior_worker_ids:
        raise SpecificationStateError(
            "every Proofreader cycle requires a fresh identity independent of all Architects"
        )
    if architect["cycles_completed"] >= MAX_CYCLES_PER_ARCHITECT:
        state["status"] = "spec_convergence_hold"
        state["hold"] = {
            "reason": "architect_cycle_limit",
            "architect_id": architect["id"],
            "cycles_completed": architect["cycles_completed"],
            "attempted_proofreader_id": args.proofreader_id,
            "entered_at": utc_now(),
            "next_actions": ["handoff-architect", "user-gate"],
        }
        state.setdefault("hold_history", []).append(dict(state["hold"]))
        state["updated_at"] = utc_now()
        save_state(root, state)
        raise SpecificationStateError(
            "sixth cycle for this Architect is forbidden; entered spec_convergence_hold"
        )
    wave_number = len(state["waves"]) + 1
    state["active_wave"] = {
        "number": wave_number,
        "architect_id": architect["id"],
        "proofreader_id": proofreader_id,
        "spec_sha256": sha256(spec),
        "started_at": utc_now(),
        "proofread": None,
    }
    state["specification"]["sha256"] = sha256(spec)
    state["specification"]["status"] = parse_frontmatter(spec, "Specification").get(
        "status"
    )
    state["updated_at"] = utc_now()
    save_state(root, state)
    return state


def command_record_proofread(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root).resolve()
    state = load_state(root)
    if state["status"] != "reviewing":
        raise SpecificationStateError(f"cannot record Proofreader result in {state['status']}")
    require_bound_recovery_continuation(root, state)
    require_no_active_helper_request(state)
    wave = state.get("active_wave")
    if not wave or wave["proofread"] is not None:
        raise SpecificationStateError("no wave is awaiting a Proofreader result")
    if not same_actor(wave["proofreader_id"], args.proofreader_id):
        raise SpecificationStateError("unexpected Proofreader identity")
    prd, spec = require_source_unchanged(root, state)
    require_current_preaccept_acceptance(root, state, prd, spec, wave)
    current_hash = sha256(spec)
    if current_hash != wave["spec_sha256"]:
        raise SpecificationStateError("specification changed during read-only proofreading")
    if min(args.critical, args.major, args.minor) < 0:
        raise SpecificationStateError("finding counts cannot be negative")
    question_counts = {
        "product": args.product_questions,
        "scope": args.scope_questions,
        "boundary": args.boundary_questions,
        "ownership": args.ownership_questions,
        "public_contract": args.public_contract_questions,
    }
    if min(question_counts.values()) < 0:
        raise SpecificationStateError("question counts cannot be negative")
    finding_ids = sorted(set(args.finding_id))
    question_ids = sorted(set(args.question_id))
    if len(finding_ids) != args.critical + args.major + args.minor:
        raise SpecificationStateError(
            "Proofreader finding counts must match distinct --finding-id values"
        )
    if len(question_ids) != sum(question_counts.values()):
        raise SpecificationStateError(
            "Proofreader question counts must match distinct --question-id values"
        )
    if not args.report_path or not args.report_path.strip():
        raise SpecificationStateError("Proofreader result requires a report path")
    wave["proofread"] = {
        "critical": args.critical,
        "major": args.major,
        "minor": args.minor,
        "questions": question_counts,
        "minors_engineer_resolvable": args.minors_engineer_resolvable,
        "coverage_complete": args.coverage_complete,
        "report_path": args.report_path,
        "finding_ids": finding_ids,
        "question_ids": question_ids,
        "recorded_at": utc_now(),
    }
    state["updated_at"] = utc_now()
    save_state(root, state)
    return state


def close_active_wave(state: dict[str, Any], outcome: str, spec_hash: str) -> None:
    wave = state["active_wave"]
    wave["outcome"] = outcome
    wave["result_spec_sha256"] = spec_hash
    wave["completed_at"] = utc_now()
    state["waves"].append(wave)
    state["active_wave"] = None
    architect = active_architect(state)
    architect["cycles_completed"] += 1
    state["total_cycles_completed"] += 1


def command_complete_cycle(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root).resolve()
    state = load_state(root)
    if state["status"] != "reviewing":
        raise SpecificationStateError(f"cannot complete cycle in {state['status']}")
    require_bound_recovery_continuation(root, state)
    wave = state.get("active_wave")
    if not wave or wave["proofread"] is None:
        raise SpecificationStateError("cycle has no recorded Proofreader result")
    if not same_actor(args.architect_id, state["active_architect_id"]):
        raise SpecificationStateError("only the active Architect may respond")
    if not args.resolution_note.strip():
        raise SpecificationStateError("Architect resolution note is required")
    if any(wave["proofread"]["questions"].values()) and not args.user_decision_note:
        raise SpecificationStateError(
            "product/scope/boundary/ownership/contract questions require a recorded user decision"
        )
    require_no_active_helper_request(state)
    prd, spec = require_source_unchanged(root, state)
    require_current_preaccept_acceptance(root, state, prd, spec, wave)
    current_hash = sha256(spec)
    wave["architect_response"] = args.resolution_note
    wave["user_decision"] = args.user_decision_note
    if current_hash != wave["spec_sha256"]:
        accepted_evidence = revalidate_helper_evidence(
            root,
            state,
            prd,
            state["acceptance"].get("helper_evidence"),
            wave["spec_sha256"],
        )
        revised_evidence = revalidate_helper_evidence(
            root,
            state,
            prd,
            state.get("helper_evidence"),
            current_hash,
        )
        accepted_results = accepted_evidence["results"]
        revised_results = revised_evidence["results"]
        if revised_results[: len(accepted_results)] != accepted_results:
            raise SpecificationStateError(
                "active-wave helper result chain does not preserve accepted provenance"
            )
        new_results = revised_results[len(accepted_results) :]
        if not new_results or any(
            item["request"]["summary"]["operation"] != "correction"
            for item in new_results
        ):
            raise SpecificationStateError(
                "changed active-wave specification requires consumed correction results"
            )
        wave["helper_correction_results"] = copy.deepcopy(new_results)
        close_active_wave(state, "revised", current_hash)
        state["acceptance"] = None
        state["status"] = "awaiting_accept"
    else:
        current_evidence = revalidate_helper_evidence(
            root,
            state,
            prd,
            state.get("helper_evidence"),
            current_hash,
        )
        if current_evidence != state["acceptance"].get("helper_evidence"):
            raise SpecificationStateError(
                "no-edit cycle cannot consume an unrelated helper result"
            )
        close_active_wave(state, "revised", current_hash)
        state["status"] = "reviewing"
    state["specification"]["sha256"] = current_hash
    state["specification"]["status"] = parse_frontmatter(spec, "Specification").get("status")
    state["updated_at"] = utc_now()
    save_state(root, state)
    return state


def command_confirm_ready(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root).resolve()
    state = load_state(root)
    if state["status"] != "reviewing":
        raise SpecificationStateError(f"cannot confirm readiness in {state['status']}")
    require_bound_recovery_continuation(root, state)
    require_no_active_helper_request(state)
    wave = state.get("active_wave")
    if not wave or wave["proofread"] is None:
        raise SpecificationStateError("readiness requires a fresh Proofreader result")
    if not same_actor(args.architect_id, state["active_architect_id"]):
        raise SpecificationStateError("only the active Architect may confirm readiness")
    if not args.confirmation.strip():
        raise SpecificationStateError("Architect readiness confirmation is required")
    prd, spec = require_source_unchanged(root, state)
    require_current_preaccept_acceptance(root, state, prd, spec, wave)
    proofread = wave["proofread"]
    blockers: list[str] = []
    if proofread["critical"] or proofread["major"]:
        blockers.append("Critical/Major findings remain")
    if any(proofread["questions"].values()):
        blockers.append("product/scope/boundary/ownership/contract questions remain")
    if not proofread["coverage_complete"]:
        blockers.append("Proofreader coverage is incomplete")
    if proofread["minor"] and not proofread["minors_engineer_resolvable"]:
        blockers.append("remaining Minor findings are not explicitly engineer-resolvable")
    current_hash = sha256(spec)
    if current_hash != wave["spec_sha256"]:
        blockers.append("Architect and Proofreader are not confirming the same specification SHA")
    meta = parse_frontmatter(spec, "Specification")
    if meta.get("status") != "approved":
        blockers.append("specification status must be approved")
    if blockers:
        raise SpecificationStateError("SPEC_READY blocked: " + "; ".join(blockers))
    wave["architect_confirmation"] = args.confirmation
    close_active_wave(state, "spec_ready", current_hash)
    state["specification"]["sha256"] = current_hash
    state["specification"]["status"] = "approved"
    state["status"] = "spec_ready"
    state["ready"] = {
        "prd_sha256": state["prd"]["sha256"],
        "spec_sha256": current_hash,
        "proofreader_id": state["waves"][-1]["proofreader_id"],
        "architect_id": args.architect_id,
        "confirmed_at": utc_now(),
    }
    state["updated_at"] = utc_now()
    save_state(root, state)
    return state


def command_handoff(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root).resolve()
    state = load_state(root)
    require_bound_recovery_continuation(root, state)
    require_no_active_helper_request(state)
    if state["status"] != "spec_convergence_hold":
        raise SpecificationStateError("Architect handoff is allowed only from spec_convergence_hold")
    new_architect_id = args.new_architect_id.strip()
    if normalized_actor_id(new_architect_id) in historical_worker_ids(state):
        raise SpecificationStateError(
            "new Architect identity must be fresh across all Architect and Proofreader history"
        )
    if not new_architect_id or not args.decision_note.strip():
        raise SpecificationStateError(
            "Architect handoff requires a fresh identity and recorded rationale"
        )
    require_source_unchanged(root, state)
    now = utc_now()
    old = active_architect(state)
    old["ended_at"] = now
    old["handoff_reason"] = args.decision_note
    state["architects"].append(
        {
            "id": new_architect_id,
            "cycles_completed": 0,
            "started_at": now,
            "ended_at": None,
            "handoff_reason": None,
        }
    )
    state["active_architect_id"] = new_architect_id
    state["status"] = "reviewing"
    state.setdefault("hold_history", []).append(
        {
            **(state.get("hold") or {}),
            "resolved_by": "handoff-architect",
            "new_architect_id": new_architect_id,
            "decision_note": args.decision_note,
            "resolved_at": now,
        }
    )
    state["hold"] = None
    state["updated_at"] = now
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
    init.add_argument("--architect-id", required=True)
    init.set_defaults(handler=command_init)

    prepare_helper = commands.add_parser("prepare-helper")
    prepare_helper.add_argument(
        "--operation", choices=("generation", "correction"), required=True
    )
    prepare_helper.add_argument("--correction-id", action="append", default=[])
    prepare_helper.set_defaults(handler=command_prepare_helper)

    preflight_helper = commands.add_parser("preflight-helper-output")
    preflight_helper.add_argument("--request", required=True)
    preflight_helper.set_defaults(handler=command_preflight_helper_output)

    record_helper = commands.add_parser("record-helper-result")
    record_helper.set_defaults(handler=command_record_helper_result)

    reject_helper = commands.add_parser("reject-helper-result")
    reject_helper.add_argument("--request-id", required=True)
    reject_helper.add_argument("--reason", required=True)
    reject_helper.set_defaults(handler=command_reject_helper_result)

    accept = commands.add_parser("accept-spec")
    accept.add_argument("--preaccept-receipt", required=True)
    accept.set_defaults(handler=command_accept_spec)

    revise_in_progress = commands.add_parser(
        "revise-in-progress",
        help=(
            "replace stale PRD authority during an active reviewed wave before runtime "
            "binding, archive that wave, and require fresh acceptance and convergence"
        ),
    )
    revise_in_progress.add_argument("--reason", required=True)
    revise_in_progress.add_argument("--architect-id", required=True)
    revise_in_progress.set_defaults(handler=command_revise_in_progress)

    revise_ready_help = (
        "revoke exact SPEC_READY bytes for a sanctioned specification revision or "
        "a newly approved PRD revision; a legacy bound runtime requires an exact "
        "authority_recovery_hold token, while proven v2 revisions are tokenless and "
        "a PRD change requires public status to expose init with "
        "user_input_required=false"
    )
    revise_ready = commands.add_parser(
        "revise-ready",
        aliases=["reopen-ready"],
        help=revise_ready_help,
        description=revise_ready_help,
    )
    revise_ready.add_argument("--reason", required=True)
    revise_ready.add_argument("--architect-id", required=True)
    revise_ready.add_argument(
        "--recovery-token",
        help=(
            "required only for an exact legacy authority_recovery_hold; "
            "all v2 specification and PRD revisions are tokenless"
        ),
    )
    revise_ready.add_argument(
        "--specification-only",
        action="store_true",
        help="reopen exact SPEC_READY bytes while preserving the exact approved PRD",
    )
    revise_ready.set_defaults(handler=command_revise_ready)

    start = commands.add_parser("start-cycle")
    start.add_argument("--architect-id", required=True)
    start.add_argument("--proofreader-id", required=True)
    start.set_defaults(handler=command_start_cycle)

    proofread = commands.add_parser("record-proofread")
    proofread.add_argument("--proofreader-id", required=True)
    proofread.add_argument("--critical", type=int, required=True)
    proofread.add_argument("--major", type=int, required=True)
    proofread.add_argument("--minor", type=int, required=True)
    proofread.add_argument("--product-questions", type=int, default=0)
    proofread.add_argument("--scope-questions", type=int, default=0)
    proofread.add_argument("--boundary-questions", type=int, default=0)
    proofread.add_argument("--ownership-questions", type=int, default=0)
    proofread.add_argument("--public-contract-questions", type=int, default=0)
    proofread.add_argument("--minors-engineer-resolvable", action="store_true")
    proofread.add_argument("--coverage-complete", action="store_true")
    proofread.add_argument("--report-path")
    proofread.add_argument("--finding-id", action="append", default=[])
    proofread.add_argument("--question-id", action="append", default=[])
    proofread.set_defaults(handler=command_record_proofread)

    complete = commands.add_parser("complete-cycle")
    complete.add_argument("--architect-id", required=True)
    complete.add_argument("--resolution-note", required=True)
    complete.add_argument("--user-decision-note")
    complete.set_defaults(handler=command_complete_cycle)

    ready = commands.add_parser("confirm-ready")
    ready.add_argument("--architect-id", required=True)
    ready.add_argument("--confirmation", required=True)
    ready.set_defaults(handler=command_confirm_ready)

    handoff = commands.add_parser("handoff-architect")
    handoff.add_argument("--new-architect-id", required=True)
    handoff.add_argument("--decision-note", required=True)
    handoff.set_defaults(handler=command_handoff)

    status = commands.add_parser("status")
    status.set_defaults(handler=lambda args: load_state(Path(args.project_root).resolve()))
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.handler(args)
    except (OSError, ValueError, json.JSONDecodeError, SpecificationStateError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
