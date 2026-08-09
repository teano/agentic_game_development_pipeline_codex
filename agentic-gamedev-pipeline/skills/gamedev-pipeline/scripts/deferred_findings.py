#!/usr/bin/env python3
"""Atomic, deterministic controller for the project deferred-findings backlog."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


SCHEMA_VERSION = 1
BACKLOG_PATH = Path("docs/engineering/deferred-findings.json")
PIPELINE_FINDINGS_PATH = Path(".agentic-pipeline/findings.json")
PIPELINE_STATE_PATH = Path(".agentic-pipeline/state.json")
STATUSES = {
    "deferred_untriaged",
    "deferred_owned",
    "planned",
    "in_progress",
    "resolved",
    "reopened",
    "wont_fix",
    "duplicate",
}
SEVERITIES = {"minor": 1, "major": 2, "critical": 3}
REACHABILITY = {
    "normal",
    "supported_failure_path",
    "theoretical",
    "unsupported_configuration",
    "unknown",
}
DEFERRED_SCOPE_RELATIONS = {"preexisting_adjacent", "out_of_scope"}
TERMINAL_STATUSES = {"resolved", "wont_fix", "duplicate"}


class BacklogError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_fingerprint_part(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    return re.sub(r"\s+", " ", normalized)


def fingerprint_for(
    component: str,
    contract: str,
    root_cause: str,
    failure_mode: str,
    effect: str,
) -> str:
    # Title, revision and a specific trigger are deliberately absent.
    parts = [component, contract, root_cause, failure_mode, effect]
    payload = json.dumps(
        [normalize_fingerprint_part(part) for part in parts],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stable_id(fingerprint: str, entries: dict[str, Any]) -> str:
    for length in range(12, len(fingerprint) + 1, 4):
        candidate = f"DEF-{fingerprint[:length].upper()}"
        existing = entries.get(candidate)
        if existing is None or existing.get("fingerprint") == fingerprint:
            return candidate
    raise BacklogError("Unable to allocate a collision-free stable deferred finding ID")


def backlog_path(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / BACKLOG_PATH


def empty_backlog() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "entries": {}}


def read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise BacklogError(f"Missing {label}: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BacklogError(f"Cannot read valid {label} JSON at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BacklogError(f"{label} must be a JSON object: {path}")
    return value


def load_backlog(path: Path, *, allow_missing: bool = False) -> dict[str, Any]:
    if allow_missing and not path.exists():
        return empty_backlog()
    value = read_json(path, "deferred-findings backlog")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise BacklogError(
            f"Unsupported deferred-findings schema: {value.get('schema_version')!r}"
        )
    if not isinstance(value.get("entries"), dict):
        raise BacklogError("deferred-findings backlog requires an entries object")
    for entry_id, entry in value["entries"].items():
        if not isinstance(entry, dict) or entry.get("id") != entry_id:
            raise BacklogError(f"Malformed deferred finding entry: {entry_id}")
        if entry.get("status") not in STATUSES:
            raise BacklogError(f"Unsupported status for {entry_id}: {entry.get('status')!r}")
    return value


@contextmanager
def exclusive_lock(path: Path, timeout_seconds: float = 5.0) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_seconds
    descriptor: int | None = None
    while descriptor is None:
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, f"{os.getpid()}\n".encode("ascii"))
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise BacklogError(f"Timed out waiting for backlog controller lock: {path}")
            time.sleep(0.05)
    try:
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def unique_extend(target: list[str], additions: list[str] | None) -> list[str]:
    combined = {item.strip() for item in target if item.strip()}
    combined.update(item.strip() for item in (additions or []) if item.strip())
    return sorted(combined)


def change_status(entry: dict[str, Any], status: str, *, reason: str, actor: str) -> None:
    if status not in STATUSES:
        raise BacklogError(f"Unsupported deferred finding status: {status}")
    previous = entry["status"]
    if previous == status:
        return
    changed_at = utc_now()
    entry.setdefault("status_history", []).append(
        {
            "from": previous,
            "to": status,
            "reason": reason,
            "actor": actor,
            "changed_at": changed_at,
        }
    )
    entry["status"] = status
    entry["last_seen"] = changed_at


def occurrence_from_args(args: argparse.Namespace, now: str) -> dict[str, Any] | None:
    occurrence_id = getattr(args, "occurrence_id", None)
    if not occurrence_id:
        return None
    return {
        "occurrence_id": occurrence_id,
        "observed_at": getattr(args, "observed_at", None) or now,
        "observed_by": getattr(args, "observed_by", None),
        "origin_feature": getattr(args, "origin_feature", None),
        "current_scope": {
            "feature": getattr(args, "current_feature", None),
            "slice": getattr(args, "current_slice", None),
            "revision": getattr(args, "current_revision", None),
            "scope_relation": getattr(args, "scope_relation", None),
        },
        "evidence": sorted(set(getattr(args, "evidence", None) or [])),
    }


def append_occurrence(entry: dict[str, Any], occurrence: dict[str, Any] | None) -> bool:
    if occurrence is None:
        return False
    occurrence_id = occurrence["occurrence_id"]
    if any(item.get("occurrence_id") == occurrence_id for item in entry["occurrences"]):
        return False
    entry["occurrences"].append(occurrence)
    return True


def update_entry(entry: dict[str, Any], args: argparse.Namespace, now: str) -> None:
    prior_evidence = set(entry["evidence"])
    entry["conditions"] = unique_extend(entry["conditions"], args.condition)
    entry["impacts"] = unique_extend(entry["impacts"], args.impact)
    entry["evidence"] = unique_extend(entry["evidence"], args.evidence)
    entry["observed_by"] = unique_extend(
        entry["observed_by"], [args.observed_by] if args.observed_by else []
    )
    entry["origin_features"] = unique_extend(
        entry["origin_features"], [args.origin_feature] if args.origin_feature else []
    )
    entry["reentry_conditions"] = unique_extend(
        entry["reentry_conditions"], args.reentry_condition
    )
    new_evidence = sorted(set(entry["evidence"]) - prior_evidence)
    if SEVERITIES[args.provisional_severity] > SEVERITIES[entry["provisional_severity"]]:
        if not new_evidence:
            raise BacklogError("Severity escalation requires new evidence in the same operation")
        previous = entry["provisional_severity"]
        entry["provisional_severity"] = args.provisional_severity
        entry.setdefault("severity_history", []).append(
            {
                "from": previous,
                "to": args.provisional_severity,
                "evidence": new_evidence,
                "changed_at": now,
            }
        )
    occurrence = occurrence_from_args(args, now)
    appended = append_occurrence(entry, occurrence)
    if occurrence:
        entry["current_scope"] = occurrence["current_scope"]
    if appended or new_evidence:
        entry["last_seen"] = occurrence["observed_at"] if occurrence else now
    if entry["status"] == "resolved" and (appended or new_evidence):
        change_status(
            entry,
            "reopened",
            reason="rediscovered with an independent occurrence or new evidence",
            actor=args.observed_by,
        )


def cmd_init(args: argparse.Namespace) -> int:
    path = backlog_path(args.project_root)
    with exclusive_lock(path.with_suffix(path.suffix + ".lock")):
        if path.exists():
            backlog = load_backlog(path)
        else:
            backlog = empty_backlog()
            atomic_write_json(path, backlog)
    print(json.dumps({"path": str(path), **backlog}, ensure_ascii=False, indent=2))
    return 0


def cmd_upsert(args: argparse.Namespace) -> int:
    path = backlog_path(args.project_root)
    fingerprint = fingerprint_for(
        args.component,
        args.contract,
        args.root_cause,
        args.failure_mode,
        args.effect,
    )
    now = utc_now()
    with exclusive_lock(path.with_suffix(path.suffix + ".lock")):
        backlog = load_backlog(path, allow_missing=True)
        entries = backlog["entries"]
        matches = [
            entry for entry in entries.values() if entry.get("fingerprint") == fingerprint
        ]
        if len(matches) > 1:
            raise BacklogError("Backlog contains duplicate entries for the same fingerprint")
        if matches:
            entry = matches[0]
            update_entry(entry, args, now)
            created = False
        else:
            entry_id = stable_id(fingerprint, entries)
            status = "deferred_owned" if args.owner else "deferred_untriaged"
            occurrence = occurrence_from_args(args, now)
            entry = {
                "id": entry_id,
                "fingerprint": fingerprint,
                "status": status,
                "title": args.title,
                "component": args.component,
                "contract": args.contract,
                "root_cause": args.root_cause,
                "failure_mode": args.failure_mode,
                "effect": args.effect,
                "problem": args.problem,
                "violated_invariant": args.violated_invariant,
                "provisional_severity": args.provisional_severity,
                "reachability": args.reachability,
                "owner": args.owner,
                "conditions": unique_extend([], args.condition),
                "impacts": unique_extend([], args.impact),
                "evidence": unique_extend([], args.evidence),
                "occurrences": [occurrence] if occurrence else [],
                "first_seen": args.observed_at or now,
                "last_seen": args.observed_at or now,
                "observed_by": unique_extend([], [args.observed_by]),
                "origin_features": unique_extend([], [args.origin_feature]),
                "current_scope": occurrence["current_scope"] if occurrence else {},
                "reentry_conditions": unique_extend([], args.reentry_condition),
                "links": {"duplicate_of": None, "duplicates": [], "related": []},
                "status_history": [],
                "severity_history": [],
            }
            entries[entry_id] = entry
            created = True
        atomic_write_json(path, backlog)
    print(
        json.dumps(
            {
                "path": str(path),
                "created": created,
                "id": entry["id"],
                "fingerprint": fingerprint,
                "status": entry["status"],
                "reference": f"{BACKLOG_PATH.as_posix()}#{entry['id']}",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def require_entry(backlog: dict[str, Any], entry_id: str) -> dict[str, Any]:
    entry = backlog["entries"].get(entry_id)
    if entry is None:
        raise BacklogError(f"Unknown deferred finding ID: {entry_id}")
    return entry


def mutate_one(args: argparse.Namespace, callback: Any) -> int:
    path = backlog_path(args.project_root)
    with exclusive_lock(path.with_suffix(path.suffix + ".lock")):
        backlog = load_backlog(path)
        entry = require_entry(backlog, args.id)
        callback(backlog, entry)
        atomic_write_json(path, backlog)
    print(json.dumps({"id": args.id, "status": entry["status"]}, indent=2))
    return 0


def cmd_extend(args: argparse.Namespace) -> int:
    return mutate_one(args, lambda _backlog, entry: update_entry(entry, args, utc_now()))


def cmd_assign(args: argparse.Namespace) -> int:
    def apply(_backlog: dict[str, Any], entry: dict[str, Any]) -> None:
        entry["owner"] = args.owner
        if entry["status"] in {"deferred_untriaged", "reopened"}:
            change_status(entry, "deferred_owned", reason=args.reason, actor=args.assigned_by)

    return mutate_one(args, apply)


def cmd_reactivate(args: argparse.Namespace) -> int:
    def apply(_backlog: dict[str, Any], entry: dict[str, Any]) -> None:
        if entry["status"] == "duplicate":
            raise BacklogError("A duplicate must be unlinked before it can be reactivated")
        change_status(entry, "reopened", reason=args.reason, actor=args.reactivated_by)
        entry["evidence"] = unique_extend(entry["evidence"], args.evidence)

    return mutate_one(args, apply)


def cmd_resolve(args: argparse.Namespace) -> int:
    def apply(_backlog: dict[str, Any], entry: dict[str, Any]) -> None:
        new_evidence = sorted(set(args.evidence) - set(entry["evidence"]))
        if not new_evidence:
            raise BacklogError("Resolving a deferred finding requires new resolution evidence")
        entry["evidence"] = unique_extend(entry["evidence"], args.evidence)
        change_status(entry, "resolved", reason=args.reason, actor=args.resolved_by)

    return mutate_one(args, apply)


def cmd_link_duplicate(args: argparse.Namespace) -> int:
    path = backlog_path(args.project_root)
    with exclusive_lock(path.with_suffix(path.suffix + ".lock")):
        backlog = load_backlog(path)
        duplicate = require_entry(backlog, args.id)
        canonical = require_entry(backlog, args.canonical_id)
        if duplicate["id"] == canonical["id"]:
            raise BacklogError("A deferred finding cannot be a duplicate of itself")
        change_status(duplicate, "duplicate", reason=args.reason, actor=args.linked_by)
        duplicate["links"]["duplicate_of"] = canonical["id"]
        canonical["links"]["duplicates"] = unique_extend(
            canonical["links"]["duplicates"], [duplicate["id"]]
        )
        atomic_write_json(path, backlog)
    print(
        json.dumps(
            {"id": duplicate["id"], "status": "duplicate", "duplicate_of": canonical["id"]},
            indent=2,
        )
    )
    return 0


def deferred_id_from_reference(reference: str) -> str | None:
    prefix = f"{BACKLOG_PATH.as_posix()}#"
    normalized = reference.replace("\\", "/")
    if normalized.startswith(prefix):
        return normalized[len(prefix) :]
    if re.fullmatch(r"DEF-[A-F0-9]{12,64}", reference):
        return reference
    return None


def candidate_requires_current_scope(item: dict[str, Any]) -> bool:
    return bool(
        item.get("introduced_by_candidate")
        or item.get("worsened_by_candidate")
        or item.get("changed_contract")
        or item.get("feature_path_reaches_trigger")
        or item.get("blocks_acceptance_ids")
        or item.get("violates_required_invariant")
        or item.get("safety_impact")
    )


def backlog_scope_errors(
    root: Path,
    pipeline_findings: dict[str, Any],
    *,
    revision: str | None = None,
    sources: set[str] | None = None,
) -> list[str]:
    candidates = [
        item
        for item in pipeline_findings.get("items", [])
        if item.get("status") == "open"
        and item.get("blocking") is False
        and item.get("scope_relation") in DEFERRED_SCOPE_RELATIONS
        and item.get("production_reachability") != "unknown"
        and (revision is None or item.get("revision") == revision)
        and (sources is None or item.get("source") in sources)
    ]
    if not candidates:
        return []
    path = root / BACKLOG_PATH
    try:
        backlog = load_backlog(path)
    except BacklogError as exc:
        return [str(exc)]
    errors: list[str] = []
    for item in candidates:
        finding_id = item.get("id", "<unknown>")
        if candidate_requires_current_scope(item):
            detail = " and scope_expansion_hold is required" if item.get("material_scope_change") else ""
            errors.append(
                f"{finding_id} must return to current scope{detail}; it cannot be deferred"
            )
            continue
        reference = item.get("deferred_reference")
        entry_id = deferred_id_from_reference(reference) if reference else None
        if entry_id is None:
            errors.append(f"{finding_id} lacks a canonical deferred backlog reference")
            continue
        entry = backlog["entries"].get(entry_id)
        if entry is None:
            errors.append(f"{finding_id} references missing deferred finding {entry_id}")
        elif entry.get("status") in TERMINAL_STATUSES:
            errors.append(
                f"{finding_id} references terminal deferred finding {entry_id} ({entry.get('status')}); reactivate/upsert it"
            )
    return errors


def require_pipeline_backlog_scope(
    root: Path,
    pipeline_findings: dict[str, Any],
    *,
    revision: str,
    sources: set[str],
) -> None:
    errors = backlog_scope_errors(root, pipeline_findings, revision=revision, sources=sources)
    if errors:
        raise BacklogError("Deferred candidate gate failed: " + "; ".join(errors))


def cmd_scope_check(args: argparse.Namespace) -> int:
    root = Path(args.project_root).resolve()
    findings_path = root / (Path(args.findings_file) if args.findings_file else PIPELINE_FINDINGS_PATH)
    findings = read_json(findings_path, "pipeline findings")
    sources = set(args.source) if args.source else None
    errors = backlog_scope_errors(root, findings, revision=args.revision, sources=sources)
    result = {
        "status": "pass" if not errors else "fail",
        "backlog": str(root / BACKLOG_PATH),
        "revision": args.revision,
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


def add_project_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-root", default=".")


def add_lists(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--condition", action="append", default=[])
    parser.add_argument("--impact", action="append", default=[])
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--reentry-condition", action="append", default=[])


def add_observation(parser: argparse.ArgumentParser, *, required: bool) -> None:
    parser.add_argument("--occurrence-id", required=required)
    parser.add_argument("--observed-at")
    parser.add_argument("--observed-by", required=required)
    parser.add_argument("--origin-feature", required=required)
    parser.add_argument("--current-feature")
    parser.add_argument("--current-slice")
    parser.add_argument("--current-revision")
    parser.add_argument("--scope-relation", choices=tuple(sorted(DEFERRED_SCOPE_RELATIONS)))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init")
    add_project_root(init)
    init.set_defaults(handler=cmd_init)

    upsert = commands.add_parser("backlog-upsert", aliases=["defer"])
    add_project_root(upsert)
    upsert.add_argument("--component", required=True)
    upsert.add_argument("--contract", required=True)
    upsert.add_argument("--root-cause", required=True)
    upsert.add_argument("--failure-mode", required=True)
    upsert.add_argument("--effect", required=True)
    upsert.add_argument("--title", required=True)
    upsert.add_argument("--problem", required=True)
    upsert.add_argument("--violated-invariant", required=True)
    upsert.add_argument("--provisional-severity", choices=tuple(SEVERITIES), required=True)
    upsert.add_argument("--reachability", choices=tuple(sorted(REACHABILITY)), required=True)
    upsert.add_argument("--owner")
    add_lists(upsert)
    add_observation(upsert, required=True)
    upsert.set_defaults(handler=cmd_upsert)

    extend = commands.add_parser("extend")
    add_project_root(extend)
    extend.add_argument("--id", required=True)
    extend.add_argument("--provisional-severity", choices=tuple(SEVERITIES), required=True)
    add_lists(extend)
    add_observation(extend, required=False)
    extend.set_defaults(handler=cmd_extend)

    assign = commands.add_parser("assign")
    add_project_root(assign)
    assign.add_argument("--id", required=True)
    assign.add_argument("--owner", required=True)
    assign.add_argument("--assigned-by", required=True)
    assign.add_argument("--reason", required=True)
    assign.set_defaults(handler=cmd_assign)

    reactivate = commands.add_parser("reactivate")
    add_project_root(reactivate)
    reactivate.add_argument("--id", required=True)
    reactivate.add_argument("--reactivated-by", required=True)
    reactivate.add_argument("--reason", required=True)
    reactivate.add_argument("--evidence", action="append", required=True)
    reactivate.set_defaults(handler=cmd_reactivate)

    resolve = commands.add_parser("resolve")
    add_project_root(resolve)
    resolve.add_argument("--id", required=True)
    resolve.add_argument("--resolved-by", required=True)
    resolve.add_argument("--reason", required=True)
    resolve.add_argument("--evidence", action="append", required=True)
    resolve.set_defaults(handler=cmd_resolve)

    duplicate = commands.add_parser("link-duplicate")
    add_project_root(duplicate)
    duplicate.add_argument("--id", required=True)
    duplicate.add_argument("--canonical-id", required=True)
    duplicate.add_argument("--linked-by", required=True)
    duplicate.add_argument("--reason", required=True)
    duplicate.set_defaults(handler=cmd_link_duplicate)

    scope = commands.add_parser("backlog-scope-check")
    add_project_root(scope)
    scope.add_argument("--revision")
    scope.add_argument("--source", action="append")
    scope.add_argument("--findings-file")
    scope.set_defaults(handler=cmd_scope_check)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except BacklogError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
