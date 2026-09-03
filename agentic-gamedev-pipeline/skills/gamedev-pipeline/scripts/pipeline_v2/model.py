"""State schema and deterministic helpers for pipeline v2."""

from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = 3
CHECKOUT_MODEL = "git-tree-v1"
PHASES = ("plan", "slice", "engineering", "review", "qa", "docs", "ready")
NEXT_PHASE = dict(zip(PHASES, PHASES[1:]))
AUTHORITY_KEYS = {"requirements", "specification", "plan"}
CANDIDATE_FIELDS = {
    "base_tree_oid", "candidate_tree_oid", "changed_paths", "authority_digest",
    "pipeline_runtime_digest", "generation",
}
ROLES = {
    "plan": "planner",
    "slice": "slicer",
    "engineering": "engineer",
    "review": "reviewer",
    "qa": "qa",
    "docs": "documentation_finisher",
}
_ARTIFACT_SHAPES = {
    "plan": (
        ("outcome", "summary", "questions", "blocker", "required_action"),
        ("outcome", "summary"),
        {
            "summary": "non-empty string", "questions[]": "non-empty string",
            "blocker": "non-empty string only and always when blocked",
            "required_action": "non-empty string only and always when blocked",
        },
    ),
    "slice": (
        ("outcome", "summary", "slices", "questions", "blocker", "required_action"),
        ("outcome", "summary"),
        {
            "summary": "non-empty string",
            "slices[]": "optional ordered {id,allowed_paths,planned_commands} records",
            "questions[]": "non-empty string",
            "blocker": "non-empty string only and always when blocked",
            "required_action": "non-empty string only and always when blocked",
        },
    ),
    "engineering": (
        ("outcome", "summary", "questions", "assumptions", "blocker", "required_action"),
        ("outcome", "summary"),
        {
            "summary": "non-empty string", "questions[]": "non-empty string",
            "assumptions[]": "non-empty string",
            "blocker": "non-empty string only and always when blocked",
            "required_action": "non-empty string only and always when blocked",
        },
    ),
    "review": (
        ("outcome", "findings", "questions", "blocker", "required_action"),
        ("outcome", "findings"),
        {
            "findings[]": {
                "allowed_keys": ["text", "severity", "kind"],
                "required_keys": ["text", "severity", "kind"],
                "values": "non-empty strings",
            },
            "findings": "empty on pass; non-empty on fail",
            "questions[]": "non-empty string",
            "blocker": "non-empty string only and always when blocked",
            "required_action": "non-empty string only and always when blocked",
        },
    ),
    "qa": (
        ("outcome", "checks", "blocker", "required_action", "questions"),
        ("outcome", "checks"),
        {
            "checks[]": "non-empty string; at least one unless blocked",
            "blocker": "non-empty string only and always when blocked",
            "required_action": "non-empty string only and always when blocked",
            "questions[]": "non-empty string",
        },
    ),
    "docs": (
        ("outcome", "summary", "questions", "blocker", "required_action"),
        ("outcome", "summary"),
        {
            "summary": "non-empty string", "questions[]": "non-empty string",
            "blocker": "non-empty string only and always when blocked",
            "required_action": "non-empty string only and always when blocked",
        },
    ),
}
STATE_FIELDS = {
    "schema", "run_id", "generation", "project_root", "authority", "phase",
    "active_assignment", "slices", "artifacts", "questions", "history",
    "checkout_model", "base_tree_oid", "pipeline_runtime_digest",
}
HEX64 = set("0123456789abcdef")
ASSIGNMENT_OUTPUT_DIR = ".agentic-pipeline/outputs"
SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,62}[A-Za-z0-9])?\Z")


class PipelineError(ValueError):
    """A deterministic contract or transition failure."""


class ConflictError(PipelineError):
    """The caller attempted a stale compare-and-swap."""


def canonical_command(value: Any) -> dict[str, Any]:
    """Snapshot one command as an exact, plain JSON-semantic object."""
    if type(value) is not dict:
        raise PipelineError("command must be a plain JSON object")
    active: set[int] = set()

    def clone(item: Any) -> Any:
        if type(item) is dict:
            marker = id(item)
            if marker in active:
                raise PipelineError("command must contain only plain JSON values")
            active.add(marker)
            try:
                if any(type(key) is not str for key in item):
                    raise PipelineError("command must contain only plain JSON values")
                return {key: clone(child) for key, child in item.items()}
            finally:
                active.remove(marker)
        if type(item) is list:
            marker = id(item)
            if marker in active:
                raise PipelineError("command must contain only plain JSON values")
            active.add(marker)
            try:
                return [clone(child) for child in item]
            finally:
                active.remove(marker)
        if item is None or type(item) in {bool, int, str}:
            return item
        if type(item) is float and math.isfinite(item):
            return item
        raise PipelineError("command must contain only plain JSON values")

    return clone(value)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def is_digest(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX64


def is_git_oid(value: Any) -> bool:
    return (
        isinstance(value, str) and len(value) in {40, 64}
        and set(value) <= HEX64
    )


def is_strict_integer(value: Any) -> bool:
    """Accept JSON integers without treating booleans as numbers."""
    return type(value) is int


def is_generation(value: Any) -> bool:
    return is_strict_integer(value) and value >= 0


def candidate_record_valid(
    value: Any, authority_digest: Any, pipeline_runtime_digest: Any,
) -> bool:
    """Validate one exact candidate bound to the current authority epoch."""
    return (
        isinstance(value, dict)
        and set(value) == CANDIDATE_FIELDS
        and is_git_oid(value.get("base_tree_oid"))
        and is_git_oid(value.get("candidate_tree_oid"))
        and literal_paths_valid(value.get("changed_paths"))
        and is_digest(value.get("authority_digest"))
        and value.get("authority_digest") == authority_digest
        and is_digest(value.get("pipeline_runtime_digest"))
        and value.get("pipeline_runtime_digest") == pipeline_runtime_digest
        and is_generation(value.get("generation"))
    )


def safe_identifier(value: Any, label: str = "run_id") -> str:
    if not isinstance(value, str) or SAFE_IDENTIFIER.fullmatch(value) is None:
        raise PipelineError(
            f"{label} must be a compact safe identifier using ASCII letters, digits, '.', '_', or '-'"
        )
    return value


def assignment_output_path(assignment: dict[str, Any] | str) -> str:
    """Derive one collision-resistant, project-relative artifact path."""
    assignment_id = assignment.get("id") if isinstance(assignment, dict) else assignment
    if not isinstance(assignment_id, str) or not assignment_id:
        raise PipelineError("assignment id is required for its output path")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", assignment_id).strip(".-")
    reserved = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
    unsafe_reserved = bool(safe) and safe.split(".", 1)[0].casefold() in reserved
    if not safe or safe != assignment_id or len(safe) > 96 or unsafe_reserved:
        prefix = (safe[:64].rstrip(".-") or "assignment")
        if prefix.split(".", 1)[0].casefold() in reserved:
            prefix = f"assignment-{prefix}"
        safe = f"{prefix}-{hashlib.sha256(assignment_id.encode()).hexdigest()[:12]}"
    return f"{ASSIGNMENT_OUTPUT_DIR}/{safe}.json"


def artifact_schema(phase: str, role: str | None = None) -> dict[str, Any]:
    """Return the small worker-owned artifact contract for one assignment."""
    if phase not in _ARTIFACT_SHAPES or (role is not None and role != ROLES[phase]):
        raise PipelineError("artifact schema requires a known phase/role")
    allowed, required, shapes = _ARTIFACT_SHAPES[phase]
    return {
        "allowed_keys": list(allowed),
        "required_keys": list(required),
        "outcome_enum": ["pass", "fail", "blocked"],
        "item_shapes": deepcopy(shapes),
    }


_CONTEXT_ITEM_LIMIT = 4
_CONTEXT_TEXT_BYTES = 256


def _bounded_context_value(value: Any) -> Any:
    if isinstance(value, str):
        encoded = value.encode("utf-8")
        if len(encoded) <= _CONTEXT_TEXT_BYTES:
            return value
        marker = f"…[sha256={digest(value)}]…"
        budget = _CONTEXT_TEXT_BYTES - len(marker.encode("utf-8"))
        front = budget // 2
        return (
            encoded[:front].decode("utf-8", errors="ignore")
            + marker
            + encoded[-(budget - front):].decode("utf-8", errors="ignore")
        )
    if isinstance(value, list):
        included = [_bounded_context_value(item) for item in value[:_CONTEXT_ITEM_LIMIT]]
        if len(value) > _CONTEXT_ITEM_LIMIT:
            included.append({
                "omitted_count": len(value) - _CONTEXT_ITEM_LIMIT,
                "omitted_sha256": digest(value[_CONTEXT_ITEM_LIMIT:]),
            })
        return included
    if isinstance(value, dict):
        return {key: _bounded_context_value(child) for key, child in value.items()}
    return deepcopy(value)


def _bounded_context_records(
    records: list[dict[str, Any]], prior_summary: Any = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    included = records[-_CONTEXT_ITEM_LIMIT:]
    projected = [_bounded_context_value(item) for item in included]
    if isinstance(prior_summary, dict) and isinstance(prior_summary.get("total"), int):
        summary = deepcopy(prior_summary)
        summary["included"] = len(projected)
        return projected, summary
    omitted = records[:-_CONTEXT_ITEM_LIMIT] if len(records) > _CONTEXT_ITEM_LIMIT else []
    summary = {"total": len(records), "included": len(projected), "omitted": len(omitted)}
    if omitted:
        summary["omitted_sha256"] = digest(omitted)
    return projected, summary


def compact_assignment_context(source: dict[str, Any], bound_candidate: Any) -> dict[str, Any]:
    """Keep worker context semantic, deterministic, and bounded."""
    context: dict[str, Any] = {}
    if isinstance(source.get("current_slice"), dict):
        context["current_slice"] = deepcopy(source["current_slice"])
    if isinstance(source.get("review_target"), dict):
        context["review_target"] = deepcopy(source["review_target"])

    failure = source.get("verification_failure")
    if isinstance(failure, dict) and failure.get("candidate") == bound_candidate:
        context["verification_failure"] = _bounded_context_value(failure)

    decision_source = source.get("decisions", [])
    if not isinstance(decision_source, list):
        decision_source = []
    decisions, decision_history = _bounded_context_records(
        decision_source, source.get("decision_history"),
    )
    if decisions:
        context["decisions"] = decisions
        context["decision_history"] = decision_history
    return context


def normalize_rule(value: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise PipelineError("path rules must be non-empty strings")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise PipelineError("path rules cannot contain control characters")
    rule = value.replace("\\", "/")
    if len(rule) >= 2 and rule[0].isalpha() and rule[1] == ":":
        raise PipelineError(f"unsafe project-relative path rule: {value!r}")
    path = PurePosixPath(rule)
    if path.is_absolute() or ".." in path.parts or rule.startswith("/"):
        raise PipelineError(f"unsafe project-relative path rule: {value!r}")
    if rule == "**":
        return rule
    prefix = rule[:-3] if rule.endswith("/**") else None
    wildcard_source = prefix if prefix is not None else rule
    if any(char in wildcard_source for char in "*?") or (prefix is not None and not prefix.rstrip("/")):
        raise PipelineError("path rules allow only exact paths, '**', or 'dir/**'")
    if path.as_posix() != rule or rule in {".", ""}:
        raise PipelineError(f"invalid project-relative path rule: {value!r}")
    return path.as_posix()


def normalize_literal_path(value: str) -> str:
    """Normalize one Git-reported project-relative path without glob semantics."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise PipelineError("literal paths must be non-empty strings")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise PipelineError("literal paths cannot contain control characters")
    normalized = value.replace("\\", "/")
    if len(normalized) >= 2 and normalized[0].isalpha() and normalized[1] == ":":
        raise PipelineError(f"unsafe project-relative literal path: {value!r}")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts or normalized.startswith("/"):
        raise PipelineError(f"unsafe project-relative literal path: {value!r}")
    if path.as_posix() != normalized or normalized in {".", ""}:
        raise PipelineError(f"invalid project-relative literal path: {value!r}")
    return path.as_posix()


def literal_paths_valid(value: Any) -> bool:
    if not isinstance(value, list) or value != sorted(dict.fromkeys(value)):
        return False
    try:
        return all(normalize_literal_path(path) == path for path in value)
    except PipelineError:
        return False


def normalize_read_rule(value: str) -> str:
    """Validate a controller-sealed exact or terminal-directory read rule."""
    rule = normalize_rule(value)
    if rule != value or rule == "**":
        raise PipelineError(
            "slice read_paths allow only canonical exact paths or terminal dir/** rules"
        )
    return rule


def command_intent_digest(command: dict[str, Any]) -> str:
    """Hash caller intent, excluding CAS and controller-derived observations."""
    intent = {
        key: value for key, value in command.items()
        if key not in {"expected_generation", "controller", "controller_base", "controller_interrupt"}
    }
    return digest(intent)


def authority_record(items: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(items, dict) or set(items) != AUTHORITY_KEYS:
        raise PipelineError("authority requires exactly requirements, specification, and plan")
    clean: dict[str, dict[str, str]] = {}
    for name, item in sorted(items.items()):
        if not isinstance(name, str) or not name or not isinstance(item, dict):
            raise PipelineError("authority items must be a named object")
        path, sha = item.get("path"), item.get("sha256")
        if not isinstance(path, str) or not is_digest(sha):
            raise PipelineError(f"invalid authority item {name!r}")
        clean[name] = {"path": normalize_literal_path(path), "sha256": sha}
    return {"items": clean, "digest": digest(clean)}


def slice_records(value: Any, *, sealed: bool | None = None) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise PipelineError("at least one slice record is required")
    clean = []
    seen = set()
    for item in value:
        keys = set(item) if isinstance(item, dict) else set()
        legacy_keys = {"id", "allowed_paths", "planned_commands"}
        sealed_keys = legacy_keys | {"read_paths"}
        if (
            not isinstance(item, dict)
            or frozenset(keys) not in {frozenset(legacy_keys), frozenset(sealed_keys)}
            or sealed is True and keys != sealed_keys
            or sealed is False and keys != legacy_keys
        ):
            expectation = (
                "id, allowed_paths, planned_commands, and controller-sealed read_paths"
                if sealed is True else "id, allowed_paths, and planned_commands"
                if sealed is False else
                "id, allowed_paths, planned_commands, and optional controller-sealed read_paths"
            )
            raise PipelineError(f"each slice requires exactly {expectation}")
        slice_id = item["id"]
        normalized_id = slice_id.strip() if isinstance(slice_id, str) else ""
        if not normalized_id or normalized_id in seen:
            raise PipelineError("slice IDs must be non-empty and unique")
        paths = item["allowed_paths"]
        if not isinstance(paths, list) or not paths:
            raise PipelineError("slice allowed_paths must be a non-empty list")
        paths = [normalize_rule(path) for path in paths]
        if "**" in paths:
            raise PipelineError("slice allowed_paths cannot grant whole-project '**' access")
        read_paths = item.get("read_paths")
        if read_paths is not None:
            if not isinstance(read_paths, list) or not read_paths:
                raise PipelineError("slice read_paths must be a non-empty list")
            read_paths = [normalize_read_rule(path) for path in read_paths]
            if "**" in read_paths or len(read_paths) != len(set(read_paths)):
                raise PipelineError(
                    "slice read_paths must be duplicate-free and cannot grant whole-project '**' access"
                )
        commands = item["planned_commands"]
        if (
            not isinstance(commands, list) or not commands
            or any(
                not isinstance(argv, list) or not argv
                or any(not isinstance(part, str) or not part for part in argv)
                for argv in commands
            )
        ):
            raise PipelineError("slice planned_commands must contain non-empty argv lists")
        seen.add(normalized_id)
        record = {
            "id": normalized_id, "allowed_paths": paths,
            "planned_commands": deepcopy(commands),
        }
        if read_paths is not None:
            record["read_paths"] = read_paths
        clean.append(record)
    return clean


def slices_are_read_sealed(state: dict[str, Any]) -> bool:
    return bool(state.get("slices")) and all(
        isinstance(item, dict) and "read_paths" in item
        for item in state["slices"]
    )


def completed_slice_ids(state: dict[str, Any]) -> list[str]:
    """Return the accepted slice prefix in the current authority/scope epoch."""
    history = state.get("history", [])
    start = 0
    for index, item in enumerate(history):
        if item.get("command") == "init" and item.get("result") == "authority_scope_reconfigured":
            start = index + 1
    return [
        item["completed_slice_id"] for item in history[start:]
        if isinstance(item.get("completed_slice_id"), str)
    ]


def current_slice(state: dict[str, Any]) -> dict[str, Any]:
    """Return the next unverified slice, or the final slice after all are verified."""
    completed = completed_slice_ids(state)
    return deepcopy(state["slices"][min(len(completed), len(state["slices"]) - 1)])


def _integrated_slice_paths(state: dict[str, Any]) -> list[str]:
    """Return the deterministic completed-plus-current slice read boundary."""
    last_index = min(len(completed_slice_ids(state)), len(state["slices"]) - 1)
    return list(dict.fromkeys(
        path
        for item in state["slices"][:last_index + 1]
        for path in item["allowed_paths"] + item.get("read_paths", [])
    ))


def review_target(
    state: dict[str, Any], *,
    selected: dict[str, Any] | None = None,
    candidate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the small controller-derived target for one Review assignment."""
    def changed_paths(record: Any) -> list[str]:
        controller = record.get("controller") if isinstance(record, dict) else None
        changes = controller.get("changed_paths") if isinstance(controller, dict) else None
        if not literal_paths_valid(changes):
            return []
        return deepcopy(changes)

    selected = current_slice(state) if selected is None else deepcopy(selected)
    candidate = current_candidate(state) if candidate is None else deepcopy(candidate)
    docs = state.get("artifacts", {}).get("docs")
    if (
        state.get("phase") == "review"
        and isinstance(docs, dict)
        and docs.get("candidate") == candidate
    ):
        paths = changed_paths(docs)
        if paths:
            return {
                "kind": "documentation_changes",
                "required_scope": "candidate_changes",
                "candidate_changes": paths,
            }
    engineering = state.get("artifacts", {}).get("engineering")
    return {
        "kind": "current_slice_implementation",
        "slice_id": selected["id"],
        "required_scope": deepcopy(selected["allowed_paths"]),
        "candidate_changes": (
            changed_paths(engineering)
            if isinstance(engineering, dict) and engineering.get("candidate") == candidate
            else []
        ),
    }


def all_slices_completed(state: dict[str, Any]) -> bool:
    expected = [item["id"] for item in state.get("slices", [])]
    completed = completed_slice_ids(state)
    if completed == expected:
        return True
    # Schema-2 states sealed before multi-slice support have no marker. Preserve
    # their valid single-slice terminal record without weakening new transitions.
    return not completed and len(expected) == 1 and isinstance(state.get("artifacts", {}).get("ready"), dict)


def new_state(
    *, run_id: str, project_root: str, authority: dict[str, Any],
    slices: list[dict[str, Any]], base_tree_oid: str,
    pipeline_runtime_digest: str,
) -> dict[str, Any]:
    run_id = safe_identifier(run_id)
    if not isinstance(project_root, str) or not project_root:
        raise PipelineError("project_root is required")
    state = {
        "schema": SCHEMA,
        "checkout_model": CHECKOUT_MODEL,
        "base_tree_oid": base_tree_oid,
        "pipeline_runtime_digest": pipeline_runtime_digest,
        "run_id": run_id,
        "generation": 0,
        "project_root": project_root,
        "authority": authority_record(authority.get("items", authority)),
        "phase": "plan",
        "active_assignment": None,
        "slices": slice_records(slices),
        "artifacts": {},
        "questions": {},
        "history": [],
    }
    validate_state(state)
    return state


def current_candidate(state: dict[str, Any]) -> dict[str, Any] | None:
    candidates = []
    artifacts = state.get("artifacts", {})
    if not isinstance(artifacts, dict):
        return None
    epoch_generation = max(
        (
            item.get("generation", -1) for item in state.get("history", [])
            if item.get("command") == "init"
            and item.get("result") == "authority_scope_reconfigured"
            and is_generation(item.get("generation"))
        ),
        default=-1,
    )
    for phase in ("engineering", "docs"):
        item = artifacts.get(phase)
        worker = item.get("worker") if isinstance(item, dict) else None
        controller = item.get("controller") if isinstance(item, dict) else None
        candidate = item.get("candidate") if isinstance(item, dict) else None
        assignment_generation = max(
            (
                event.get("generation", -1) for event in state.get("history", [])
                if isinstance(item, dict)
                and event.get("assignment_id") == item.get("assignment_id")
                and is_generation(event.get("generation"))
            ),
            default=-1,
        )
        if (
            candidate_record_valid(
                candidate, state.get("authority", {}).get("digest"),
                state.get("pipeline_runtime_digest"),
            )
            and isinstance(worker, dict) and worker.get("outcome") == "pass"
            and isinstance(controller, dict)
            and all(
                isinstance(result, dict) and result.get("returncode") == 0
                for result in controller.get("commands", [])
            )
            and assignment_generation > epoch_generation
        ):
            candidates.append((candidate["generation"], phase == "docs", candidate))
    return deepcopy(max(candidates, default=(0, False, None))[-1])


def pending(mapping: dict[str, Any]) -> list[str]:
    return sorted(
        key for key, value in mapping.items()
        if isinstance(value, dict) and value.get("status") == "open"
    )


def passing_artifact(state: dict[str, Any], phase: str) -> dict[str, Any] | None:
    """Return live semantic credit, excluding evidence retained across a boundary."""
    record = state.get("artifacts", {}).get(phase)
    worker = record.get("worker") if isinstance(record, dict) else None
    if (
        not isinstance(worker, dict) or worker.get("outcome") != "pass"
        or worker.get("questions")
    ):
        return None
    assignment_generation = max(
        (
            item.get("generation", -1) for item in state.get("history", [])
            if item.get("assignment_id") == record.get("assignment_id")
            and is_generation(item.get("generation"))
        ),
        default=-1,
    )
    epoch_generation = max(
        (
            item.get("generation", -1) for item in state.get("history", [])
            if item.get("command") == "init"
            and item.get("result") == "authority_scope_reconfigured"
            and is_generation(item.get("generation"))
        ),
        default=-1,
    )
    controller = record.get("controller")
    if (
        assignment_generation <= epoch_generation
        or not isinstance(controller, dict)
        or controller.get("authority_digest") != state.get("authority", {}).get("digest")
        or any(
            isinstance(item, dict) and item.get("returncode") != 0
            for item in controller.get("commands", [])
        )
    ):
        return None
    if phase == "engineering":
        candidate = record.get("candidate")
        accepted_generation = max(
            (
                item.get("generation", -1) for item in state.get("history", [])
                if isinstance(item.get("completed_slice_id"), str)
                and is_generation(item.get("generation"))
            ),
            default=-1,
        )
        if (
            not candidate_record_valid(
                candidate, state.get("authority", {}).get("digest"),
                state.get("pipeline_runtime_digest"),
            )
            or candidate["generation"] <= accepted_generation
        ):
            return None
    return record


def production_ready(state: dict[str, Any]) -> bool:
    """Derive readiness from the exact controller-sealed terminal record."""
    if not isinstance(state, dict) or state.get("phase") != "ready" or state.get("active_assignment") is not None:
        return False
    artifacts = state.get("artifacts")
    if not isinstance(artifacts, dict):
        return False
    record = artifacts.get("ready")
    candidate = current_candidate(state)
    controller = record.get("controller") if isinstance(record, dict) else None
    return (
        isinstance(record, dict) and set(record) == {"candidate", "authority_digest", "controller"}
        and candidate is not None and record["candidate"] == candidate
        and record["authority_digest"] == state.get("authority", {}).get("digest")
        and candidate.get("authority_digest") == record["authority_digest"]
        and isinstance(controller, dict)
        and set(controller) == {"candidate_tree_oid", "pipeline_runtime_digest"}
        and controller["candidate_tree_oid"] == candidate.get("candidate_tree_oid")
        and controller["pipeline_runtime_digest"] == state.get("pipeline_runtime_digest")
        and all_slices_completed(state)
        and not pending(state.get("questions", {}))
    )


_PHASE_TASKS = {
    "plan": "Confirm the approved authority and identify only unresolved product decisions.",
    "slice": "Confirm a bounded implementation slice from the approved plan.",
    "engineering": "Implement the current approved slice and report the semantic outcome.",
    "review": "Independently review the current candidate and report actionable findings.",
    "qa": "Independently verify the current candidate against the approved acceptance boundary.",
    "docs": "Bring supporting documentation in sync with the verified candidate.",
}


def _action_id(state: dict[str, Any], verb: str) -> str:
    suffix = digest([state["run_id"], state["generation"], state["phase"], verb])[:10]
    return f"{verb}-{state['phase']}-g{state['generation']}-{suffix}"


def reconfiguration_action(
    state: dict[str, Any], authority_items: dict[str, dict[str, Any]],
    slices: list[dict[str, Any]] | None = None,
    *, candidate_tree_oid: str,
) -> dict[str, Any]:
    """Bind the public init capability to the exact controller observation."""
    if not is_git_oid(candidate_tree_oid):
        raise PipelineError("reconfiguration Git candidate tree is malformed")
    authority = authority_record(authority_items)
    proposed_slices = slice_records(state["slices"] if slices is None else slices)
    token = digest([
        state["run_id"], state["generation"], authority["digest"],
        digest(proposed_slices), candidate_tree_oid,
    ])[:10]
    return {
        "kind": "command", "command": "init",
        "command_id": f"reconfigure-g{state['generation']}-{token}",
        "expected_generation": state["generation"],
        "run_id": state["run_id"], "project_root": state["project_root"],
        "authority": {
            name: item["path"] for name, item in authority["items"].items()
        },
        "slices": proposed_slices,
        "reason": "approved authority or scope binding changed; restart at plan and re-slice",
        "user_input_required": False,
    }


def assignment_identity(run_id: str, generation: int, phase: str) -> dict[str, str]:
    """Derive replay-stable assignment identity without consulting current phase state."""
    if phase == "ready":
        raise PipelineError("ready has no worker assignment")
    role = ROLES[phase]
    token = digest([run_id, generation, phase, role])[:12]
    return {
        "id": f"{phase}-g{generation}-{token}",
        "worker_id": f"{role}-session-g{generation}-{token}",
        "task": _PHASE_TASKS[phase],
    }


def _documentation_authority(state: dict[str, Any]) -> tuple[bool, list[str]]:
    """Derive Docs write authority from exact approved-plan declarations."""
    plan_item = state.get("authority", {}).get("items", {}).get("plan")
    if not isinstance(plan_item, dict) or not isinstance(plan_item.get("path"), str):
        raise PipelineError("Docs requires an approved plan authority path")
    try:
        text = (Path(state["project_root"]) / plan_item["path"]).read_text(encoding="utf-8")
    except (KeyError, OSError, UnicodeError):
        raise PipelineError("Docs cannot read its approved plan authority")

    frontmatter = re.match(r"\A---\n(.*?)\n---(?:\n|\Z)", text, re.S)
    statuses = (
        re.findall(r"(?m)^status:\s*(\S+)\s*$", frontmatter.group(1))
        if frontmatter is not None
        else []
    )
    if statuses != ["approved"]:
        raise PipelineError("Docs requires an exact approved development plan")

    global_matches = list(re.finditer(
        r"(?ms)^## Documentation Strategy\s*$\n(.*?)(?=^## |\Z)", text,
    ))
    slice_matches = list(re.finditer(
        r"(?ms)^## Slice ([A-Za-z0-9][A-Za-z0-9._-]*)\s*$\n(.*?)(?=^## |\Z)",
        text,
    ))
    if len(global_matches) != 1 or not slice_matches:
        raise PipelineError(
            "Docs requires exactly one Documentation Strategy and at least one slice"
        )

    def rows(
        section: str, *, required: set[str], optional: set[str], label: str,
    ) -> dict[str, str]:
        result: dict[str, str] = {}
        for raw in section.splitlines():
            if not raw.strip():
                continue
            match = re.fullmatch(r"\s*-\s*([a-z_]+):\s*(\S(?:.*\S)?)\s*", raw)
            if match is None:
                raise PipelineError(f"{label} contains a non-schema row")
            key, value = match.groups()
            if key not in required | optional or key in result:
                raise PipelineError(f"{label} contains an unsupported or repeated field")
            result[key] = value
        if set(result) - optional != required:
            raise PipelineError(f"{label} is missing or malformed")
        return result

    strategy = rows(
        global_matches[0].group(1),
        required={"normative_pre_review", "derived_post_qa"},
        optional={"source_rule"},
        label="Documentation Strategy",
    )
    declarations: dict[str, list[str]] = {
        "normative": [strategy["normative_pre_review"]],
        "derived": [strategy["derived_post_qa"]],
    }
    for match in slice_matches:
        contracts = list(re.finditer(
            r"(?ms)^### Documentation Contract\s*$\n(.*?)(?=^#{2,3} |\Z)",
            match.group(2),
        ))
        if len(contracts) != 1:
            raise PipelineError(
                f"Docs requires exactly one Documentation Contract for {match.group(1)}"
            )
        contract = rows(
            contracts[0].group(1),
            required={
                "normative_pre_review_paths", "derived_post_qa_paths",
                "decision_ids", "evidence_sources",
            },
            optional=set(),
            label=f"{match.group(1)} Documentation Contract",
        )
        declarations["normative"].append(contract["normative_pre_review_paths"])
        declarations["derived"].append(contract["derived_post_qa_paths"])

    paths: list[str] = []
    all_not_required = True
    for kind, values in declarations.items():
        parsed: list[tuple[str, str | list[str]]] = []
        for value in values:
            policy = re.fullmatch(
                r"not_required \| policy=([A-Za-z0-9][A-Za-z0-9._:/-]*)", value,
            )
            if policy is not None:
                parsed.append(("policy", policy.group(1)))
                continue
            if value.startswith("not_required"):
                raise PipelineError(
                    f"Docs {kind} declaration must use exact not_required policy syntax"
                )
            items = [item.strip() for item in value.split(",")]
            if any(not item for item in items) or len(items) != len(set(items)):
                raise PipelineError(
                    f"Docs {kind} paths must be a duplicate-free comma-separated list"
                )
            normalized = [normalize_rule(item.replace("\\", "/")) for item in items]
            if "**" in normalized:
                raise PipelineError("Docs declarations cannot grant whole-project write access")
            parsed.append(("paths", normalized))

        global_kind, global_value = parsed[0]
        if global_kind == "policy":
            if any(
                item_kind != "policy" or item_value != global_value
                for item_kind, item_value in parsed[1:]
            ):
                raise PipelineError(
                    f"Docs {kind} slice declarations must repeat the plan-wide policy"
                )
            continue

        all_not_required = False
        required_slices = [
            item_value
            for item_kind, item_value in parsed[1:]
            if item_kind == "paths"
        ]
        if not required_slices:
            raise PipelineError(
                f"Docs {kind} plan-wide paths require at least one slice path declaration"
            )
        global_paths = set(global_value)
        invented = sorted({
            path
            for slice_paths in required_slices
            for path in slice_paths
            if path not in global_paths
        })
        if invented:
            raise PipelineError(
                f"Docs {kind} slice paths are absent from the plan-wide declaration: "
                + ", ".join(invented)
            )
        for path in global_value:
            if path not in paths:
                paths.append(path)

    if all_not_required:
        return True, []
    return False, paths


def default_assignment(state: dict[str, Any]) -> dict[str, Any]:
    """Derive the complete technical assignment; callers supply no IDs or path rules."""
    phase = state["phase"]
    identity = assignment_identity(state["run_id"], state["generation"], phase)
    assignment_id = identity["id"]
    authority_paths = [item["path"] for item in state["authority"]["items"].values()]
    selected = current_slice(state)
    slice_read = (
        _integrated_slice_paths(state)
        if phase in {"engineering", "review", "qa"}
        else selected["allowed_paths"]
    )
    read = list(dict.fromkeys(authority_paths + slice_read))
    target = review_target(state) if phase == "review" else None
    if target is not None and target["kind"] == "documentation_changes":
        read = list(dict.fromkeys(read + target["candidate_changes"]))
    write: list[str] = []
    checks: list[list[str]] = []
    if phase == "engineering":
        write = deepcopy(selected["allowed_paths"])
        checks = deepcopy(selected["planned_commands"])
    elif phase == "qa":
        checks = deepcopy(selected["planned_commands"])
    elif phase == "docs":
        no_documentation, write = _documentation_authority(state)
        read = (
            list(authority_paths)
            if no_documentation
            else list(dict.fromkeys(read + write))
        )
    assignment = {
        "id": assignment_id,
        "worker_id": identity["worker_id"],
        "task": identity["task"],
        "access": {"read": read, "write": write},
        "checks": checks,
        "output_path": assignment_output_path(assignment_id),
    }
    if target is not None:
        assignment["context"] = {"review_target": target}
    return assignment


def next_action(state: dict[str, Any]) -> dict[str, Any]:
    """Return one deterministic controller route with no caller-authored bookkeeping."""
    generation = state["generation"]
    active = state["active_assignment"]
    if active is not None:
        return {
            "kind": "command", "command": "complete",
            "command_id": _action_id(state, "complete"),
            "expected_generation": generation,
            "assignment_id": active["id"],
            "artifact_path": assignment_output_path(active),
        }
    record = state.get("artifacts", {}).get(state.get("phase"))
    worker = record.get("worker") if isinstance(record, dict) else None
    if (
        isinstance(worker, dict) and worker.get("outcome") == "blocked"
        and record.get("assignment_id") != "controller-checkout-baseline"
    ):
        return {
            "kind": "terminal", "result": "user_input_required",
            "phase": state["phase"], "user_input_required": True,
            "blocker": worker["blocker"], "required_action": worker["required_action"],
            "recovery": "Archive this terminal run and perform a fresh init after the prerequisite changes.",
        }
    open_questions = pending(state["questions"])
    if open_questions:
        question_id = open_questions[0]
        prompt = state["questions"][question_id]["prompt"]
        return {
            "kind": "controller_decision", "route": "controller_decision",
            "command": "answer", "command_id": _action_id(state, "answer"),
            "expected_generation": generation, "question_id": question_id,
            "prompt": prompt, "user_input_required": False,
            "decision_policy": "Choose the safest reversible interpretation consistent with approved authority.",
        }
    if production_ready(state):
        return {"kind": "terminal", "result": "production_ready_candidate"}
    phase = state["phase"]
    if passing_artifact(state, phase) is not None:
        return {
            "kind": "command", "command": "accept",
            "command_id": _action_id(state, "accept"),
            "expected_generation": generation,
        }
    if phase == "ready":
        return {
            "kind": "command", "command": "ready",
            "command_id": _action_id(state, "ready"),
            "expected_generation": generation,
        }
    return {
        "kind": "command", "command": "next",
        "command_id": _action_id(state, "next"),
        "expected_generation": generation,
        "assignment": default_assignment(state),
    }


def validate_state(state: dict[str, Any]) -> None:
    if (
        isinstance(state, dict) and state.get("schema") == SCHEMA
        and state.get("checkout_model") != CHECKOUT_MODEL
    ):
        raise PipelineError(
            "legacy filesystem-inventory state is unsupported; "
            "remove the old state and run a fresh init"
        )
    if not isinstance(state, dict) or set(state) != STATE_FIELDS:
        extra = sorted(set(state) - STATE_FIELDS) if isinstance(state, dict) else []
        missing = sorted(STATE_FIELDS - set(state)) if isinstance(state, dict) else sorted(STATE_FIELDS)
        raise PipelineError(f"invalid state fields; missing={missing}, extra={extra}")
    if len(state) != 14 or state["schema"] != SCHEMA:
        raise PipelineError("state must use the compact schema-3 shape")
    if state["checkout_model"] != CHECKOUT_MODEL:
        raise PipelineError("state must use the git-tree-v1 checkout model")
    if not is_git_oid(state["base_tree_oid"]):
        raise PipelineError("state base_tree_oid is malformed")
    if not is_digest(state["pipeline_runtime_digest"]):
        raise PipelineError("state pipeline_runtime_digest is malformed")
    safe_identifier(state["run_id"])
    if not isinstance(state["project_root"], str) or not state["project_root"]:
        raise PipelineError("project_root is required")
    if not is_generation(state["generation"]):
        raise PipelineError("generation must be a non-negative integer")
    if state["phase"] not in PHASES:
        raise PipelineError("unknown phase")
    authority = state["authority"]
    if not isinstance(authority, dict) or set(authority) != {"items", "digest"}:
        raise PipelineError("authority has an invalid shape")
    if authority_record(authority.get("items", {})) != authority:
        raise PipelineError("authority digest does not match its items")
    for key in ("artifacts", "questions"):
        if not isinstance(state[key], dict):
            raise PipelineError(f"{key} must be an object")
    for phase, item in state["artifacts"].items():
        if phase not in PHASES or not isinstance(item, dict):
            raise PipelineError("artifact has an invalid shape")
        if phase == "ready":
            if not production_ready(state):
                raise PipelineError("ready artifact is not current controller evidence")
            continue
        worker = item.get("worker")
        if not isinstance(worker, dict) or worker.get("outcome") not in {"pass", "fail", "blocked"}:
            raise PipelineError("phase artifact has an invalid worker outcome")
        candidate = item.get("candidate")
        if candidate is not None and not candidate_record_valid(
            candidate, authority["digest"], state["pipeline_runtime_digest"],
        ):
            raise PipelineError("artifact candidate is malformed")
        failure = item.get("controller_failure")
        if failure is not None:
            core_fields = {
                "command_index", "returncode", "stdout_sha256", "stderr_sha256",
                "unexecuted_count",
            }
            excerpt_fields = {
                "stderr_excerpt", "stderr_excerpt_truncated", "stderr_excerpt_redacted",
            }
            if (
                not isinstance(failure, dict)
                or frozenset(failure) not in {
                    frozenset(core_fields), frozenset(core_fields | excerpt_fields),
                }
                or not is_strict_integer(failure.get("command_index"))
                or failure["command_index"] < 1
                or type(failure.get("returncode")) is not int
                or failure["returncode"] == 0
                or not is_digest(failure.get("stdout_sha256"))
                or not is_digest(failure.get("stderr_sha256"))
                or not is_strict_integer(failure.get("unexecuted_count"))
                or failure["unexecuted_count"] < 0
                or (
                    excerpt_fields <= set(failure)
                    and (
                        not isinstance(failure["stderr_excerpt"], str)
                        or len(failure["stderr_excerpt"].encode("utf-8")) > 4096
                        or type(failure["stderr_excerpt_truncated"]) is not bool
                        or type(failure["stderr_excerpt_redacted"]) is not bool
                    )
                )
            ):
                raise PipelineError("controller failure capsule is malformed")
    if slice_records(state["slices"]) != state["slices"] or not isinstance(state["history"], list):
        raise PipelineError("slices and history are malformed")
    for name, item in state["questions"].items():
        if (
            not isinstance(name, str) or not isinstance(item, dict)
            or item.get("status") not in {"open", "answered"}
            or item.get("phase") not in PHASES[:-1]
            or not isinstance(item.get("prompt"), str)
            or (item.get("status") == "answered" and not isinstance(item.get("answer"), str))
        ):
            raise PipelineError("question has an invalid shape")
    for item in state["history"]:
        if (
            not isinstance(item, dict) or not isinstance(item.get("id"), str)
            or not isinstance(item.get("command"), str)
            or not is_digest(item.get("command_digest"))
        ):
            raise PipelineError("history has an invalid shape")
        if not is_generation(item.get("generation")):
            raise PipelineError("history generation must be a non-negative integer")
        if "actor_id" in item and (
            not isinstance(item["actor_id"], str) or not item["actor_id"]
            or item.get("phase") not in PHASES[:-1]
            or not isinstance(item.get("assignment_id"), str)
        ):
            raise PipelineError("completed actor history is malformed")
        if "completed_slice_id" in item and not isinstance(item["completed_slice_id"], str):
            raise PipelineError("completed slice history is malformed")
    completed = completed_slice_ids(state)
    expected = [item["id"] for item in state["slices"]]
    if completed != expected[:len(completed)]:
        raise PipelineError("completed slice history must be the approved slice prefix")
    active = state["active_assignment"]
    if active is not None:
        required = {"id", "phase", "role", "worker_id", "task", "access", "capsule", "base", "commands", "status"}
        optional = {"output_path", "artifact_schema"}
        if not isinstance(active, dict) or not required <= set(active) or not set(active) - required <= optional or active["status"] != "active":
            raise PipelineError("active_assignment has an invalid shape")
        if active["phase"] != state["phase"] or active["role"] != ROLES.get(state["phase"]):
            raise PipelineError("active assignment is not bound to the current phase/role")
        if not all(isinstance(active[key], str) and active[key] for key in ("id", "role", "worker_id", "task", "status")):
            raise PipelineError("active_assignment text fields are invalid")
        if "output_path" in active and active["output_path"] != assignment_output_path(active):
            raise PipelineError("active_assignment output path is not controller-derived")
        if "artifact_schema" in active and active["artifact_schema"] != artifact_schema(active["phase"], active["role"]):
            raise PipelineError("active_assignment artifact schema is not controller-derived")
        access = active["access"]
        if not isinstance(access, dict) or set(access) != {"read", "write"}:
            raise PipelineError("assignment requires explicit read/write access")
        for mode in ("read", "write"):
            if not isinstance(access[mode], list):
                raise PipelineError(f"assignment {mode} access must be a list")
            [normalize_rule(rule) for rule in access[mode]]
        capsule = active["capsule"]
        base = active["base"]
        commands = active["commands"]
        if (
            not isinstance(capsule, dict) or capsule.get("authority_digest") != authority["digest"]
            or not isinstance(capsule.get("context"), dict)
        ):
            raise PipelineError("assignment authority is stale")
        if (
            not isinstance(base, dict) or set(base) != {"candidate_tree_oid"}
            or not is_git_oid(base["candidate_tree_oid"])
        ):
            raise PipelineError("assignment Git candidate base is malformed")
        if (
            not isinstance(commands, list)
            or any(not isinstance(argv, list) or not argv or any(not isinstance(x, str) or not x for x in argv) for argv in commands)
        ):
            raise PipelineError("assignment commands are malformed")


def _active_assignment_view(
    state: dict[str, Any], active: dict[str, Any],
) -> dict[str, Any]:
    """Project the recoverable worker packet without controller bookkeeping."""
    source = active["capsule"]["context"]
    bound_candidate = active["capsule"].get("candidate")
    context = compact_assignment_context(source, bound_candidate)
    selected = context.get("current_slice")
    if (
        active["phase"] == "review"
        and "review_target" not in context
        and isinstance(selected, dict)
        and isinstance(bound_candidate, dict)
    ):
        context["review_target"] = review_target(
            state, selected=selected, candidate=bound_candidate,
        )

    return {
        "id": active["id"],
        "role": active["role"],
        "worker_id": active["worker_id"],
        "task": active["task"],
        "access": deepcopy(active["access"]),
        "checks": deepcopy(active["commands"]),
        "context": context,
        "output_path": assignment_output_path(active),
        "artifact_schema": artifact_schema(active["phase"], active["role"]),
    }


def status_view(state: dict[str, Any]) -> dict[str, Any]:
    validate_state(state)
    active = state["active_assignment"]
    return {
        "run_id": state["run_id"],
        "generation": state["generation"],
        "phase": state["phase"],
        "active_assignment": _active_assignment_view(state, active) if active else None,
        "candidate": current_candidate(state),
        "open_questions": pending(state["questions"]),
        "ready": production_ready(state),
        "next_action": next_action(state),
    }
