#!/usr/bin/env python3
"""Deterministic controller for bounded technical-specification convergence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
STATE_RELATIVE_PATH = Path(".agentic-pipeline/specification-state.json")
MAX_CYCLES_PER_ARCHITECT = 5


class SpecificationStateError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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
    return meta


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
    if data.get("schema_version") != SCHEMA_VERSION:
        raise SpecificationStateError("unsupported specification state schema")
    return data


def save_state(root: Path, state: dict[str, Any]) -> None:
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


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


def command_init(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root).resolve()
    feature = require_slug(args.feature)
    prd = resolve_project_path(root, args.prd, "approved PRD")
    spec = resolve_project_path(root, args.spec, "technical specification")
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
        "active_architect_id": args.architect_id,
        "architects": [
            {
                "id": args.architect_id,
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
    if state["status"] not in {"needs_generation", "reviewing"}:
        raise SpecificationStateError(f"cannot accept specification in {state['status']}")
    prd = root / state["prd"]["path"]
    spec = root / state["specification"]["path"]
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
    state["status"] = "reviewing"
    state["updated_at"] = utc_now()
    save_state(root, state)
    return state


def command_start_cycle(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project_root).resolve()
    state = load_state(root)
    if state["status"] != "reviewing":
        raise SpecificationStateError(f"cannot start cycle in {state['status']}")
    if state["active_wave"] is not None:
        raise SpecificationStateError("a Proofreader wave is already active")
    architect = active_architect(state)
    if args.architect_id != architect["id"]:
        raise SpecificationStateError("cycle Architect does not own the specification")
    proofreader_id = args.proofreader_id.strip()
    if not proofreader_id:
        raise SpecificationStateError("a fresh Proofreader identity is required")
    prior_worker_ids = {
        item["id"] for item in state.get("architects", [])
    } | {
        item["proofreader_id"] for item in state.get("waves", [])
    }
    if proofreader_id in prior_worker_ids:
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
    wave = state.get("active_wave")
    if not wave or wave["proofread"] is not None:
        raise SpecificationStateError("no wave is awaiting a Proofreader result")
    if wave["proofreader_id"] != args.proofreader_id:
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
    wave = state.get("active_wave")
    if not wave or wave["proofread"] is None:
        raise SpecificationStateError("cycle has no recorded Proofreader result")
    if args.architect_id != state["active_architect_id"]:
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
    wave = state.get("active_wave")
    if not wave or wave["proofread"] is None:
        raise SpecificationStateError("readiness requires a fresh Proofreader result")
    if args.architect_id != state["active_architect_id"]:
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
    if state["status"] != "spec_convergence_hold":
        raise SpecificationStateError("Architect handoff is allowed only from spec_convergence_hold")
    if any(item["id"] == args.new_architect_id for item in state["architects"]):
        raise SpecificationStateError("new Architect identity must be distinct")
    if not args.new_architect_id.strip() or not args.decision_note.strip():
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
            "id": args.new_architect_id,
            "cycles_completed": 0,
            "started_at": now,
            "ended_at": None,
            "handoff_reason": None,
        }
    )
    state["active_architect_id"] = args.new_architect_id
    state["status"] = "reviewing"
    state.setdefault("hold_history", []).append(
        {
            **(state.get("hold") or {}),
            "resolved_by": "handoff-architect",
            "new_architect_id": args.new_architect_id,
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
