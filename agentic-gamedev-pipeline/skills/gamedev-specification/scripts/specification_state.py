#!/usr/bin/env python3
"""Deterministic controller for bounded technical-specification convergence."""

from __future__ import annotations

import argparse
import copy
import hashlib
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
STATE_RELATIVE_PATH = Path(".agentic-pipeline/specification-state.json")
RUNTIME_STATE_RELATIVE_PATH = Path(".agentic-pipeline/state.json")
RUNTIME_FINDINGS_RELATIVE_PATH = Path(".agentic-pipeline/findings.json")
MAX_CYCLES_PER_ARCHITECT = 5


class SpecificationStateError(RuntimeError):
    pass


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
        raise SpecificationStateError("ready specification lacks YAML frontmatter")
    prior_revision = exact_positive_revision(spec, "ready specification")
    next_revision = prior_revision + 1
    lines = parts[1].splitlines()
    if sum(bool(re.match(r"^status\s*:", line)) for line in lines) != 1:
        raise SpecificationStateError("ready specification must contain exactly one status")
    flat = any(re.match(r"^source_prd_(?:path|revision|sha256)\s*:", line) for line in lines)
    nested = any(re.match(r"^product_authority\s*:\s*$", line) for line in lines)
    if flat == nested:
        raise SpecificationStateError("ready specification has ambiguous product authority trace")
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


def load_state(root: Path) -> dict[str, Any]:
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
) -> dict[str, Any] | None:
    bound = [
        path
        for path in (RUNTIME_STATE_RELATIVE_PATH, RUNTIME_FINDINGS_RELATIVE_PATH)
        if (root / path).exists()
    ]
    if not bound:
        if recovery_token:
            raise SpecificationStateError(
                "--recovery-token is valid only for an open bound runtime recovery hold"
            )
        return None
    if len(bound) != 2:
        raise SpecificationStateError("runtime binding is incomplete and fails closed")
    runtime = json.loads((root / RUNTIME_STATE_RELATIVE_PATH).read_text(encoding="utf-8"))
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
    expected_token = "ARH-" + canonical_json_sha256(token_payload)[:32].upper()
    if (
        runtime.get("phase") != "authority_recovery_hold"
        or hold.get("status") != "open"
        or hold.get("token") != expected_token
        or not recovery_token
        or recovery_token != hold.get("token")
        or reason != hold.get("reason")
        or prior_spec_sha256 != (hold.get("specification") or {}).get("sha256")
    ):
        raise SpecificationStateError(
            "bound specification revision requires the exact authority_recovery_hold "
            "token, reason, and prior specification SHA"
        )
    require_runtime_preengineering_gate(runtime)
    return {
        "schema": 1,
        "token": recovery_token,
        "reason": reason,
        "runtime_state_path": RUNTIME_STATE_RELATIVE_PATH.as_posix(),
        "hold_opened_at": hold.get("opened_at"),
        "prior_spec_sha256": prior_spec_sha256,
    }


def require_bound_recovery_continuation(root: Path, state: dict[str, Any]) -> None:
    if not any(
        (root / path).exists()
        for path in (RUNTIME_STATE_RELATIVE_PATH, RUNTIME_FINDINGS_RELATIVE_PATH)
    ):
        return
    authorization = state.get("recovery_authorization") or {}
    runtime_recovery_authorization(
        root,
        recovery_token=authorization.get("token"),
        reason=authorization.get("reason"),
        prior_spec_sha256=authorization.get("prior_spec_sha256"),
    )


def active_architect(state: dict[str, Any]) -> dict[str, Any]:
    architect_id = state["active_architect_id"]
    for architect in state["architects"]:
        if architect["id"] == architect_id:
            return architect
    raise SpecificationStateError("active Architect is missing from history")


def require_source_unchanged(root: Path, state: dict[str, Any]) -> tuple[Path, Path]:
    prd = root / state["prd"]["path"]
    spec = root / state["specification"]["path"]
    require_approved_prd(prd)
    current_prd_hash = sha256(prd)
    if current_prd_hash != state["prd"]["sha256"]:
        raise SpecificationStateError(
            "PRD bytes changed; reinitialize specification work from the new approved PRD"
        )
    _, drift = specification_trace(root, prd, spec)
    if drift:
        raise SpecificationStateError("stale specification trace: " + "; ".join(drift))
    return prd, spec


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
    runtime_recovery_authorization(
        root,
        recovery_token=getattr(args, "recovery_token", None),
        reason=args.reason,
        prior_spec_sha256=transition["prior_ready_sha256"],
    )
    prd = root / transition["new_prd"]["path"]
    if sha256(prd) != transition["new_prd"]["sha256"]:
        raise SpecificationStateError("pending ready revision found changed PRD bytes")
    validate_approved_prd_contract(
        prd,
        label=(
            "unchanged specification-only PRD"
            if transition.get("specification_only")
            else "new PRD"
        ),
    )
    spec = root / transition["specification_path"]
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
    if transition.get("recovery_authorization"):
        state["recovery_authorization"] = copy.deepcopy(
            transition["recovery_authorization"]
        )
    state.pop("ready_revision", None)
    state["updated_at"] = now
    save_state(root, state)
    return state


def command_revise_ready(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root).resolve()
    state = load_state(root)
    if state.get("status") == "ready_revision_pending":
        return finalize_ready_revision(root, state, args)
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
    )
    if (
        authorization
        and prd_approved_at is not None
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
            copy.deepcopy(state["prd"])
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
        existing = load_state(root)
        if existing["feature"] != feature:
            raise SpecificationStateError(
                "specification state already exists for another feature"
            )
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
        "history": [],
        "identity_history": [],
        "created_at": now,
        "updated_at": now,
    }
    if spec_meta and not drift:
        state["specification"]["status"] = spec_meta.get("status")
    save_state(root, state)
    return state


def command_accept_spec(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root).resolve()
    state = load_state(root)
    require_bound_recovery_continuation(root, state)
    if state["status"] not in {"needs_generation", "reviewing", "awaiting_accept"}:
        raise SpecificationStateError(f"cannot accept specification in {state['status']}")
    prd = root / state["prd"]["path"]
    spec = root / state["specification"]["path"]
    validate_approved_prd_contract(prd)
    if sha256(prd) != state["prd"]["sha256"]:
        raise SpecificationStateError("PRD changed after initialization")
    meta, drift = specification_trace(root, prd, spec)
    if drift:
        raise SpecificationStateError("cannot accept stale specification: " + "; ".join(drift))
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
    if state["status"] != "reviewing":
        raise SpecificationStateError(f"cannot start cycle in {state['status']}")
    if state["active_wave"] is not None:
        raise SpecificationStateError("a Proofreader wave is already active")
    prd = root / state["prd"]["path"]
    spec = root / state["specification"]["path"]
    acceptance = state.get("acceptance") or {}
    expected_acceptance = {
        "prd_path": state["prd"]["path"],
        "prd_revision": state["prd"]["revision"],
        "prd_sha256": sha256(prd),
        "specification_path": state["specification"]["path"],
        "specification_revision": exact_positive_revision(
            spec, "current specification"
        ),
        "specification_sha256": sha256(spec),
        "accepted_by": state["active_architect_id"],
        "recovery_token": (state.get("recovery_authorization") or {}).get("token"),
    }
    if (
        not acceptance.get("accepted_at")
        or any(acceptance.get(key) != value for key, value in expected_acceptance.items())
    ):
        raise SpecificationStateError(
            "start-cycle requires a fresh accept-spec receipt for the exact current "
            "PRD/spec/revision/recovery authorization"
        )
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
    _, spec = require_source_unchanged(root, state)
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
    require_bound_recovery_continuation(root, state)
    wave = state.get("active_wave")
    if not wave or wave["proofread"] is not None:
        raise SpecificationStateError("no wave is awaiting a Proofreader result")
    if not same_actor(wave["proofreader_id"], args.proofreader_id):
        raise SpecificationStateError("unexpected Proofreader identity")
    _, spec = require_source_unchanged(root, state)
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
    _, spec = require_source_unchanged(root, state)
    wave["architect_response"] = args.resolution_note
    wave["user_decision"] = args.user_decision_note
    close_active_wave(state, "revised", sha256(spec))
    state["specification"]["sha256"] = sha256(spec)
    state["specification"]["status"] = parse_frontmatter(spec, "Specification").get("status")
    state["status"] = "reviewing"
    state["updated_at"] = utc_now()
    save_state(root, state)
    return state


def command_confirm_ready(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root).resolve()
    state = load_state(root)
    require_bound_recovery_continuation(root, state)
    wave = state.get("active_wave")
    if not wave or wave["proofread"] is None:
        raise SpecificationStateError("readiness requires a fresh Proofreader result")
    if not same_actor(args.architect_id, state["active_architect_id"]):
        raise SpecificationStateError("only the active Architect may confirm readiness")
    if not args.confirmation.strip():
        raise SpecificationStateError("Architect readiness confirmation is required")
    _, spec = require_source_unchanged(root, state)
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

    accept = commands.add_parser("accept-spec")
    accept.set_defaults(handler=command_accept_spec)

    revise_ready = commands.add_parser(
        "revise-ready",
        aliases=["reopen-ready"],
        help=(
            "revoke exact SPEC_READY bytes for a sanctioned specification revision or "
            "a newly approved PRD revision; "
            "a bound runtime requires an exact authority_recovery_hold token"
        ),
    )
    revise_ready.add_argument("--reason", required=True)
    revise_ready.add_argument("--architect-id", required=True)
    revise_ready.add_argument("--recovery-token")
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
