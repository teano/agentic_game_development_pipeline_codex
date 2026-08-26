"""State schema and deterministic helpers for pipeline v2."""

from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from pathlib import PurePosixPath
from typing import Any

SCHEMA = 2
PHASES = ("plan", "slice", "engineering", "review", "qa", "docs", "ready")
NEXT_PHASE = dict(zip(PHASES, PHASES[1:]))
AUTHORITY_KEYS = {"requirements", "specification", "plan"}
CANDIDATE_FIELDS = {
    "checkout_sha256", "diff_sha256", "authority_digest", "generation",
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
        ("outcome", "summary", "questions"), ("outcome", "summary"),
        {"summary": "non-empty string", "questions[]": "non-empty string"},
    ),
    "slice": (
        ("outcome", "summary", "slices", "questions"), ("outcome", "summary"),
        {
            "summary": "non-empty string",
            "slices[]": "optional ordered {id,allowed_paths,planned_commands} records",
            "questions[]": "non-empty string",
        },
    ),
    "engineering": (
        ("outcome", "summary", "questions", "assumptions"), ("outcome", "summary"),
        {
            "summary": "non-empty string", "questions[]": "non-empty string",
            "assumptions[]": "non-empty string",
        },
    ),
    "review": (
        ("outcome", "findings", "questions"), ("outcome", "findings"),
        {
            "findings[]": {
                "allowed_keys": ["text", "severity", "kind"],
                "required_keys": ["text", "severity", "kind"],
                "values": "non-empty strings",
            },
            "findings": "empty on pass; non-empty on fail",
            "questions[]": "non-empty string",
        },
    ),
    "qa": (
        ("outcome", "checks", "blocker", "questions"), ("outcome", "checks"),
        {
            "checks[]": "non-empty string; at least one unless blocked",
            "blocker": "non-empty string only and always when blocked",
            "questions[]": "non-empty string",
        },
    ),
    "docs": (
        ("outcome", "summary", "questions"), ("outcome", "summary"),
        {"summary": "non-empty string", "questions[]": "non-empty string"},
    ),
}
STATE_FIELDS = {
    "schema", "run_id", "generation", "project_root", "authority", "phase",
    "active_assignment", "slices", "artifacts", "questions", "gates", "history",
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


def is_strict_integer(value: Any) -> bool:
    """Accept JSON integers without treating booleans as numbers."""
    return type(value) is int


def is_generation(value: Any) -> bool:
    return is_strict_integer(value) and value >= 0


def candidate_record_valid(value: Any, authority_digest: Any) -> bool:
    """Validate one exact candidate bound to the current authority epoch."""
    return (
        isinstance(value, dict)
        and set(value) == CANDIDATE_FIELDS
        and is_digest(value.get("checkout_sha256"))
        and is_digest(value.get("diff_sha256"))
        and is_digest(value.get("authority_digest"))
        and value.get("authority_digest") == authority_digest
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
    """Keep worker context semantic, deterministic, and bounded across retries."""
    context: dict[str, Any] = {}
    if isinstance(source.get("current_slice"), dict):
        context["current_slice"] = deepcopy(source["current_slice"])

    remediation_source = source.get("remediation", [])
    if not isinstance(remediation_source, list):
        remediation_source = []
    if "remediation_history" not in source:
        remediation_source = [
            {
                key: deepcopy(item[key])
                for key in ("gate_id", "phase", "reason", "slice_id", "worker_artifact", "resolution")
                if key in item
            }
            for item in remediation_source
            if isinstance(item, dict) and item.get("candidate_base") == bound_candidate
        ]
    remediation, remediation_history = _bounded_context_records(
        remediation_source, source.get("remediation_history"),
    )
    if remediation:
        context["remediation"] = remediation
        context["remediation_history"] = remediation_history

    migration_source = source.get("migration_audit", [])
    if not isinstance(migration_source, list):
        migration_source = []
    if "migration_history" not in source:
        projected_migration = []
        for item in migration_source:
            if not isinstance(item, dict):
                continue
            projected = {
                key: deepcopy(item[key])
                for key in ("gate_id", "phase", "reason", "resolution", "migration")
                if key in item
            }
            legacy = item.get("legacy_context")
            if isinstance(legacy, dict) and isinstance(legacy.get("migration"), dict):
                projected["migration"] = deepcopy(legacy["migration"])
            projected_migration.append(projected)
        migration_source = projected_migration
    migration, migration_history = _bounded_context_records(
        migration_source, source.get("migration_history"),
    )
    if migration:
        context["migration_audit"] = migration
        context["migration_history"] = migration_history

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
    if any(char in wildcard_source for char in "*?[") or (prefix is not None and not prefix.rstrip("/")):
        raise PipelineError("path rules allow only exact paths, '**', or 'dir/**'")
    if path.as_posix() != rule or rule in {".", ""}:
        raise PipelineError(f"invalid project-relative path rule: {value!r}")
    return path.as_posix()


def normalize_read_rule(value: str) -> str:
    """Validate a controller-sealed exact or terminal-directory read rule."""
    rule = normalize_rule(value)
    wildcard_source = rule[:-3] if rule.endswith("/**") else rule
    if rule != value or rule == "**" or "]" in wildcard_source:
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
        clean[name] = {"path": normalize_rule(path), "sha256": sha}
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


def all_slices_completed(state: dict[str, Any]) -> bool:
    expected = [item["id"] for item in state.get("slices", [])]
    completed = completed_slice_ids(state)
    if completed == expected:
        return True
    # Schema-2 states sealed before multi-slice support have no marker. Preserve
    # their valid single-slice terminal record without weakening new transitions.
    return not completed and len(expected) == 1 and isinstance(state.get("artifacts", {}).get("ready"), dict)


def new_state(*, run_id: str, project_root: str, authority: dict[str, Any], slices: list[dict[str, Any]]) -> dict[str, Any]:
    run_id = safe_identifier(run_id)
    if not isinstance(project_root, str) or not project_root:
        raise PipelineError("project_root is required")
    state = {
        "schema": SCHEMA,
        "run_id": run_id,
        "generation": 0,
        "project_root": project_root,
        "authority": authority_record(authority.get("items", authority)),
        "phase": "plan",
        "active_assignment": None,
        "slices": slice_records(slices),
        "artifacts": {},
        "questions": {},
        "gates": {},
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
            )
            or candidate["generation"] <= accepted_generation
            or any(
                gate.get("status") == "closed"
                and gate.get("kind") == "worker_result"
                and gate.get("reason") == "fail"
                and gate.get("phase") in {"review", "qa"}
                and gate.get("candidate_base") == candidate
                for gate in state.get("gates", {}).values()
                if isinstance(gate, dict)
            )
        ):
            return None
    return record


def _inventory_valid(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    try:
        return all(
            isinstance(path, str) and normalize_rule(path) == path
            and isinstance(item, dict) and set(item) == {"kind", "sha256", "size"}
            and item["kind"] in {"file", "legacy"} and is_digest(item["sha256"])
            and (item["size"] is None or type(item["size"]) is int and item["size"] >= 0)
            for path, item in value.items()
        )
    except PipelineError:
        return False


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
        and isinstance(controller, dict) and set(controller) == {"inventory", "checkout_sha256"}
        and _inventory_valid(controller["inventory"])
        and controller["checkout_sha256"] == digest(controller["inventory"])
        and controller["checkout_sha256"] == candidate.get("checkout_sha256")
        and all_slices_completed(state)
        and not pending(state.get("questions", {})) and not pending(state.get("gates", {}))
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
    *, checkout_sha256: str,
) -> dict[str, Any]:
    """Bind the public init capability to the exact controller observation."""
    if not is_digest(checkout_sha256):
        raise PipelineError("reconfiguration checkout digest is malformed")
    authority = authority_record(authority_items)
    proposed_slices = slice_records(state["slices"] if slices is None else slices)
    token = digest([
        state["run_id"], state["generation"], authority["digest"],
        digest(proposed_slices), checkout_sha256,
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


def _latest_inventory(state: dict[str, Any]) -> dict[str, Any]:
    for phase in ("qa", "review", "docs", "engineering", "slice", "plan"):
        record = state["artifacts"].get(phase)
        controller = record.get("controller") if isinstance(record, dict) else None
        inventory = controller.get("inventory") if isinstance(controller, dict) else None
        if _inventory_valid(inventory):
            return inventory
    ready = state["artifacts"].get("ready")
    controller = ready.get("controller") if isinstance(ready, dict) else None
    inventory = controller.get("inventory") if isinstance(controller, dict) else None
    return inventory if _inventory_valid(inventory) else {}


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
    write: list[str] = []
    checks: list[list[str]] = []
    if phase == "engineering":
        write = deepcopy(selected["allowed_paths"])
        checks = deepcopy(selected["planned_commands"])
    elif phase == "qa":
        checks = deepcopy(selected["planned_commands"])
    elif phase == "docs":
        authority_set = set(authority_paths)
        write = [
            path for path in sorted(_latest_inventory(state))
            if path.startswith("docs/") and path not in authority_set
            and path.lower().endswith((".md", ".json", ".jsonl"))
        ]
        if not write:
            write = [f"docs/{state['run_id']}-verification.md"]
        read = list(dict.fromkeys(read + write))
    return {
        "id": assignment_id,
        "worker_id": identity["worker_id"],
        "task": identity["task"],
        "access": {"read": read, "write": write},
        "checks": checks,
        "output_path": assignment_output_path(assignment_id),
    }


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
    open_gates = pending(state["gates"])
    if open_gates:
        gate_id = open_gates[0]
        gate = state["gates"][gate_id]
        reason = gate.get("reason", "blocked")
        return {
            "kind": "command", "command": "resume",
            "command_id": _action_id(state, "resume"),
            "expected_generation": generation, "gate_id": gate_id,
            "resume_reason": f"Controller revalidated {gate['phase']} gate: {reason}.",
            "user_input_required": False,
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
    if not isinstance(state, dict) or set(state) != STATE_FIELDS:
        extra = sorted(set(state) - STATE_FIELDS) if isinstance(state, dict) else []
        missing = sorted(STATE_FIELDS - set(state)) if isinstance(state, dict) else sorted(STATE_FIELDS)
        raise PipelineError(f"invalid state fields; missing={missing}, extra={extra}")
    if len(state) > 12 or state["schema"] != SCHEMA:
        raise PipelineError("state must use the compact schema-2 shape")
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
    for key in ("artifacts", "questions", "gates"):
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
            candidate, authority["digest"],
        ):
            raise PipelineError("artifact candidate is malformed")
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
    for name, item in state["gates"].items():
        candidate_base = item.get("candidate_base") if isinstance(item, dict) else None
        if (
            not isinstance(name, str) or not isinstance(item, dict)
            or item.get("status") not in {"open", "closed"}
            or item.get("phase") not in PHASES[:-1]
            or not isinstance(item.get("kind"), str)
        ):
            raise PipelineError("gate has an invalid shape")
        if candidate_base is not None and not candidate_record_valid(
            candidate_base, authority["digest"],
        ):
            raise PipelineError("gate candidate_base is malformed")
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
            not isinstance(base, dict) or set(base) != {"inventory", "checkout_sha256"}
            or not isinstance(base["inventory"], dict) or not is_digest(base["checkout_sha256"])
        ):
            raise PipelineError("assignment checkout base is malformed")
        if not _inventory_valid(base["inventory"]):
            raise PipelineError("assignment checkout inventory is malformed")
        if (
            not isinstance(commands, list)
            or any(not isinstance(argv, list) or not argv or any(not isinstance(x, str) or not x for x in argv) for argv in commands)
        ):
            raise PipelineError("assignment commands are malformed")


def _active_assignment_view(active: dict[str, Any]) -> dict[str, Any]:
    """Project the recoverable worker packet without controller bookkeeping."""
    source = active["capsule"]["context"]
    bound_candidate = active["capsule"].get("candidate")
    context = compact_assignment_context(source, bound_candidate)

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
        "active_assignment": _active_assignment_view(active) if active else None,
        "candidate": current_candidate(state),
        "open_questions": pending(state["questions"]),
        "open_gates": pending(state["gates"]),
        "ready": production_ready(state),
        "next_action": next_action(state),
    }
