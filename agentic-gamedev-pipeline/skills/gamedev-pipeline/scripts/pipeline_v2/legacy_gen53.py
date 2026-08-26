"""One-way, fail-closed importer from generic schema-10 runtime state."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .checkout import canonical_project_root
from .model import (
    PipelineError,
    authority_record,
    digest,
    is_digest,
    normalize_rule,
    slice_records,
    validate_state,
)


def _relative(root: str, supplied: str) -> str:
    windows = bool(re.match(r"^[A-Za-z]:[\\/]", root))
    path_type = PureWindowsPath if windows else PurePosixPath
    root_path, path = path_type(root), path_type(supplied)
    if not root_path.is_absolute():
        raise PipelineError("legacy project_root must be absolute")
    if not path.is_absolute():
        path = root_path / path
    try:
        relative = path.relative_to(root_path)
    except ValueError as exc:
        raise PipelineError(f"legacy authority path escapes project root: {supplied}") from exc
    value = relative.as_posix()
    if not value or ".." in relative.parts:
        raise PipelineError(f"invalid legacy authority path: {supplied}")
    return value


def _authority(legacy: dict[str, Any], root: str) -> dict[str, Any]:
    candidates = {
        "requirements": (legacy.get("requirements_path"), legacy.get("requirements_sha256")),
        "specification": (legacy.get("spec_path"), legacy.get("spec_sha256")),
        "plan": (legacy.get("development_plan_path"), legacy.get("development_plan_sha256")),
    }
    items = {
        name: {"path": _relative(root, path), "sha256": sha}
        for name, (path, sha) in candidates.items()
        if isinstance(path, str) and is_digest(sha)
    }
    return authority_record(items)


def _legacy_candidate(legacy: dict[str, Any], authority_digest: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    lease = legacy.get("active_write_lease")
    if not isinstance(lease, dict) or lease.get("role") != "engineer":
        return None, {}
    lease_id = lease.get("lease_id")
    worker_id = lease.get("worker_id")
    if (
        not isinstance(lease_id, str) or not lease_id.strip()
        or not isinstance(worker_id, str) or not worker_id.strip()
    ):
        return None, {}
    snapshots = legacy.get("lease_snapshots")
    snapshot = snapshots.get(lease_id) if isinstance(snapshots, dict) else None
    if not isinstance(snapshot, dict):
        return None, {}
    rebaseline = (legacy.get("scope_guard") or {}).get("rebaseline_candidate")
    candidate_checkout = rebaseline.get("candidate_checkout") if isinstance(rebaseline, dict) else None
    if not isinstance(candidate_checkout, dict):
        candidate_checkout = snapshot.get("candidate_checkout")
    if not isinstance(candidate_checkout, dict):
        candidate_checkout = snapshot.get("checkout")
    if (
        not isinstance(candidate_checkout, dict) or not candidate_checkout
        or any(not isinstance(path, str) or not is_digest(sha) for path, sha in candidate_checkout.items())
    ):
        return None, {}
    inventory = {
        path.replace("\\", "/"): {"kind": "legacy", "sha256": sha, "size": None}
        for path, sha in sorted(candidate_checkout.items())
    }
    candidate = {
        "checkout_sha256": digest(inventory),
        "diff_sha256": digest(rebaseline.get("changes", []) if isinstance(rebaseline, dict) else []),
        "authority_digest": authority_digest,
        "generation": legacy.get("generation", 0) if isinstance(legacy.get("generation", 0), int) else 0,
    }
    preserved = {
        "assignment_id": str(lease_id or "legacy-engineer"),
        "worker": {"outcome": "blocked", "summary": "Legacy dirty candidate preserved for fresh v2 ownership"},
        "controller": {"inventory": inventory},
        "candidate_binding": None,
        "candidate": candidate,
        "migration": {
            "legacy_lease_id": lease_id,
            "legacy_worker_id": worker_id,
            "legacy_capsule_id": lease.get("capsule_id"),
            "fresh_owner_required": True,
        },
    }
    return candidate, preserved


def _same_paths(value: Any, expected: list[str]) -> bool:
    if not isinstance(value, list) or len(value) != len(expected):
        return False
    try:
        normalized = [normalize_rule(path) for path in value]
    except PipelineError:
        return False
    return len(set(normalized)) == len(normalized) and set(normalized) == set(expected)


def _resumes_first_slice_engineering(
    legacy: dict[str, Any], slices: list[dict[str, Any]], authority: dict[str, Any],
) -> bool:
    """Recognize the exact safe schema-10 hold that already passed Plan/Slice."""
    selected = slices[0]
    slice_ids = [item["id"] for item in slices]
    lease = legacy.get("active_write_lease")
    guard = legacy.get("scope_guard")
    hold = guard.get("hold") if isinstance(guard, dict) else None
    legacy_slices = legacy.get("slices")
    if not all(isinstance(value, dict) for value in (lease, guard, hold, legacy_slices)):
        return False
    legacy_selected = legacy_slices.get(selected["id"])
    scope = legacy_selected.get("scope_contract") if isinstance(legacy_selected, dict) else None
    pre_edit = legacy_selected.get("scope_pre_edit_check") if isinstance(legacy_selected, dict) else None
    pre_edit_scope = pre_edit.get("scope_contract") if isinstance(pre_edit, dict) else None
    if not all(isinstance(value, dict) for value in (scope, pre_edit, pre_edit_scope)):
        return False
    slice_states_match = (
        set(legacy_slices) == set(slice_ids)
        and all(
            isinstance(legacy_slices.get(slice_id), dict)
            and legacy_slices[slice_id].get("id") == slice_id
            and legacy_slices[slice_id].get("status") == ("active" if index == 0 else "pending")
            and isinstance(legacy_slices[slice_id].get("scope_contract"), dict)
            and _same_paths(
                legacy_slices[slice_id]["scope_contract"].get("editable_paths"),
                slices[index]["allowed_paths"],
            )
            for index, slice_id in enumerate(slice_ids)
        )
    )
    exact_paths = selected["allowed_paths"]
    plan_sha = authority["items"]["plan"]["sha256"]
    return bool(
        legacy.get("phase") == "scope_expansion_hold"
        and legacy.get("execution_stage") == "implementation"
        and legacy.get("active_slice") == selected["id"]
        and legacy.get("slice_id") == selected["id"]
        and legacy.get("ordered_slices") == slice_ids
        and legacy.get("engineer_runs") == []
        and legacy.get("pending_engineer_completion") is None
        and legacy.get("last_engineer_run_id") is None
        and legacy.get("last_engineer_outcome") is None
        and slice_states_match
        and pre_edit.get("status") == "passed"
        and pre_edit.get("slice_id") == selected["id"]
        and pre_edit.get("owner_id") == lease.get("worker_id")
        and pre_edit.get("development_plan_sha256") == plan_sha
        and _same_paths(pre_edit_scope.get("editable_paths"), exact_paths)
        and guard.get("status") == "scope_expansion_hold"
        and hold.get("slice_id") == selected["id"]
        and hold.get("resume_phase") == "slice_engineering"
        and hold.get("lease_id") == lease.get("lease_id")
        and hold.get("development_plan_sha256") == plan_sha
        and legacy.get("development_plan_sha256") == plan_sha
        and lease.get("role") == "engineer"
        and lease.get("phase") == "slice_engineering"
        and lease.get("write_scope") == selected["id"]
        and lease.get("status") == "active"
        and lease.get("rebaseline_carried") is False
        and _same_paths(scope.get("editable_paths"), exact_paths)
        and _same_paths(lease.get("allowed_paths"), exact_paths)
        and _same_paths(hold.get("candidate_paths"), exact_paths)
    )


def import_schema10(legacy: dict[str, Any], slices: list[dict[str, Any]]) -> dict[str, Any]:
    """Project schema-10 data into v2 without invoking any legacy handler."""
    if not isinstance(legacy, dict) or legacy.get("schema_version") != 10:
        raise PipelineError("only schema_version 10 can be imported")
    source_digest = digest(legacy)
    supplied_root = legacy.get("project_root")
    if not isinstance(supplied_root, str) or not supplied_root:
        raise PipelineError("legacy project_root is required")
    if not (PureWindowsPath(supplied_root).is_absolute() if re.match(r"^[A-Za-z]:[\\/]", supplied_root) else PurePosixPath(supplied_root).is_absolute()):
        raise PipelineError("legacy project_root must be absolute")
    root = str(canonical_project_root(supplied_root))
    feature = legacy.get("feature") if isinstance(legacy.get("feature"), str) else "project"
    authority = _authority(legacy, root)
    approved_slices = slice_records(slices)
    candidate, preserved = _legacy_candidate(legacy, authority["digest"])
    resume_engineering = candidate is not None and _resumes_first_slice_engineering(
        legacy, approved_slices, authority,
    )
    generation = legacy.get("generation", 0)
    generation = generation if isinstance(generation, int) and generation >= 0 else 0
    state = {
        "schema": 2,
        "run_id": f"migrated-{feature}-{source_digest[:12]}",
        "generation": generation,
        "project_root": root,
        "authority": authority,
        "phase": "engineering" if resume_engineering else "plan",
        "active_assignment": None,
        "slices": approved_slices,
        "artifacts": {},
        "questions": {},
        "gates": ({
            "migration-audit": {
                "status": "closed", "phase": "engineering" if resume_engineering else "plan",
                "kind": "migration_audit", "reason": "schema10_cutover",
                "resolution": (
                    "resume_first_slice_engineering"
                    if resume_engineering else "rerun_all_v2_phases"
                ),
                "candidate_base": candidate, "legacy_context": preserved,
            }
        } if candidate else {}),
        "history": [{
            "id": f"legacy-{source_digest[:16]}", "command": "schema10_import",
            "command_digest": source_digest, "generation": generation,
            "result": (
                "resumed_at_first_slice_engineering"
                if resume_engineering else "audit_preserved" if candidate else "projected_to_plan"
            ),
        }],
    }
    validate_state(state)
    return state


def load_schema10(path: Path, slices: list[dict[str, Any]]) -> dict[str, Any]:
    import json

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"cannot read legacy state: {exc}") from exc
    return import_schema10(value, slices)
