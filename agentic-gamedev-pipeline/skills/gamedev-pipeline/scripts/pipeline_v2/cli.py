"""Thin CLI commands for the v2 reducer and bounded delivery."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .checkout import safe_path
from .delivery import director_brief, execute_step, export_assignment, read_delivery, read_file
from .legacy_gen53 import load_schema10
from .model import (
    PIPELINE_STATE_FILENAME,
    PipelineError,
    feature_slug,
    status_view,
    workflow_relative_path,
)
from .runner import Controller
from .transaction import StateStore


def _pairs(values: list[str], label: str) -> dict[str, str]:
    result = {}
    for value in values:
        if "=" not in value:
            raise PipelineError(f"{label} must use NAME=PATH")
        name, path = value.split("=", 1)
        if not name or not path or name in result:
            raise PipelineError(f"invalid {label}: {value!r}")
        result[name] = path
    return result


def _commands(values: list[str]) -> list[list[str]]:
    result = []
    for value in values:
        try:
            argv = json.loads(value)
        except json.JSONDecodeError as exc:
            raise PipelineError(f"command must be a JSON argv list: {exc}") from exc
        result.append(argv)
    return result


def _slices(values: list[str]) -> list[dict[str, Any]]:
    result = []
    for value in values:
        try:
            item = json.loads(value)
        except json.JSONDecodeError as exc:
            raise PipelineError(f"slice must be a JSON object: {exc}") from exc
        result.append(item)
    return result


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        prog="pipeline-v2",
        description="Run the replay-safe seven-phase GameDev pipeline controller.",
    )
    value.add_argument("--root", type=Path, required=True)
    value.add_argument("--brief", action="store_true", help="Return Director control facts without full worker input; place before the subcommand.")
    value.add_argument(
        "--feature", required=True, type=feature_slug,
        help="lowercase feature slug selecting .agentic-pipeline/Workflows/<feature>",
    )
    commands = value.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Initialize or reconfigure approved authority and slices.")
    init.add_argument("--id", required=True)
    init.add_argument("--run-id", required=True, help="Compact safe run identifier (letters, digits, dot, underscore, or hyphen).")
    init.add_argument("--authority", action="append", default=[], required=True)
    init.add_argument("--verification", type=Path, help="Workflow-local exact runnable verification manifest.")
    init.add_argument("--slice", action="append", required=True); init.add_argument("--expected-generation", type=int)
    status = commands.add_parser("status", help="Return one executable action or terminal recovery fact.")
    status.add_argument("--recovery", type=Path)
    init.add_argument("--recovery", type=Path)
    status.add_argument("--maintenance", nargs="?", const="", type=str)
    init.add_argument("--maintenance", type=Path)
    status.add_argument("--product-failure", nargs="?", const="", type=str)
    init.add_argument("--product-failure", type=Path)
    next_cmd = commands.add_parser("next", help="Issue the controller-derived assignment for the current phase.")
    next_cmd.add_argument("--id", required=True); next_cmd.add_argument("--expected-generation", type=int)
    next_cmd.add_argument("--assignment-id", help="Optional exact status-derived assignment ID.")
    next_cmd.add_argument("--worker", help="Optional exact status-derived worker session ID.")
    next_cmd.add_argument("--task", help="Optional exact status-derived task text.")
    next_cmd.add_argument("--read", action="append", default=[]); next_cmd.add_argument("--write", action="append", default=[])
    next_cmd.add_argument("--run", action="append", default=[])
    complete = commands.add_parser("complete", help="Validate the assigned semantic artifact and controller evidence.")
    complete.add_argument("--id", required=True); complete.add_argument("--expected-generation", type=int); complete.add_argument("--artifact", type=Path)
    answer = commands.add_parser("answer", help="Record a conservative controller decision for one open question.")
    answer.add_argument("--id", required=True); answer.add_argument("--expected-generation", type=int, required=True); answer.add_argument("--question-id", required=True); answer.add_argument("--text", required=True)
    accept = commands.add_parser("accept", help="Accept current passing phase evidence and advance.")
    accept.add_argument("--id", required=True); accept.add_argument("--expected-generation", type=int, required=True)
    migrate = commands.add_parser(
        "migrate",
        help="Unsupported schema-10 tombstone; archive legacy state/findings and run fresh Plan/init.",
    )
    migrate.add_argument("--id", required=True); migrate.add_argument("--legacy-state", type=Path, required=True); migrate.add_argument("--slice", action="append", required=True)
    ready = commands.add_parser("ready", help="Seal the fully verified live candidate as production-ready.")
    ready.add_argument("--id", required=True); ready.add_argument("--expected-generation", type=int, required=True)
    observe = commands.add_parser("technical-observe", help="Capture an in-scope baseline before an Engineering editor action.")
    observe.add_argument("--id", required=True); observe.add_argument("--expected-generation", type=int, required=True)
    observe.add_argument("--action", required=True)
    decision = commands.add_parser("technical-decision", help="Record a technical decision and reconcile exact scoped paths or check order.")
    decision.add_argument("--id", required=True); decision.add_argument("--expected-generation", type=int, required=True)
    decision.add_argument("--packet", type=Path, required=True)
    export = commands.add_parser("assignment-export", help="Export the exact active assignment; optionally deliver a same-worker delta.")
    export.add_argument("--baseline", help="Digest of a fully received previous assignment packet for this worker.")
    export.add_argument("--input", action="append", default=[], help="Selected exact project-relative input; records version without loading its body.")
    delivery = commands.add_parser("delivery-read", help="Read one bounded page of an immutable delivery artifact.")
    delivery.add_argument("--digest", required=True)
    delivery.add_argument("--pointer", help="Optional exact JSON pointer selecting a full semantic section before pagination.")
    file_read = commands.add_parser("file-read", help="Read one bounded, version-checked page inside active read access.")
    file_read.add_argument("--path", required=True)
    file_read.add_argument("--version", help="Previous page or selected-input SHA-256; required for continuation.")
    for reader in (delivery, file_read):
        reader.add_argument("--offset", type=int, default=0)
        reader.add_argument("--limit", type=int, default=8192)
    step = commands.add_parser("step", help="Execute exactly one current next/complete/accept; stop at all semantic boundaries.")
    step.add_argument("--expected-generation", type=int, required=True)
    step.add_argument("--action-id", required=True, help="Exact public status.next_action.command_id; safely retries the same action.")
    step.add_argument("--through-handoff", action="store_true", help="Optionally continue a passing complete through accept and next; stop at the first new assignment or other boundary.")
    for name in ("check", "rotate-owner", "read-admit", "recover-capability", "reconcile"):
        operation = commands.add_parser(name)
        operation.add_argument("--id", required=True)
        operation.add_argument("--expected-generation", type=int, required=True)
        if name == "check":
            operation.add_argument("--assignment-id", required=True)
            operation.add_argument("--quiescence", required=True)
            operation.add_argument("--collect-independent", action="store_true")
        elif name in {"rotate-owner", "read-admit"}:
            operation.add_argument("--reason", required=True)
            if name == "read-admit":
                operation.add_argument("--path", required=True)
        elif name == "recover-capability":
            operation.add_argument("--evidence", type=Path, required=True)
        else:
            operation.add_argument("--packet", type=Path, required=True)
    pin = commands.add_parser("pin-runtime", help="Create a new verified immutable runtime bundle outside the product checkout.")
    pin.add_argument("--destination", type=Path, required=True)
    return value


def _run(args: argparse.Namespace) -> dict[str, Any]:
    root = safe_path(args.root, None, "project root", strict=True)
    workflow = workflow_relative_path(args.feature)
    store = StateStore(root / workflow / PIPELINE_STATE_FILENAME)
    recovery = {}
    if getattr(args, "recovery", None) is not None:
        packet_path = safe_path(root, args.recovery, "recovery packet", strict=True)
        try:
            recovery = {"recovery": json.loads(packet_path.read_text(encoding="utf-8"))}
        except (OSError, json.JSONDecodeError) as exc:
            raise PipelineError(f"cannot read recovery packet: {exc}") from exc
    if getattr(args, "maintenance", None) is not None:
        if args.maintenance == "":
            recovery["maintenance"] = {}
        else:
            packet_path = safe_path(root, args.maintenance, "maintenance packet", strict=True)
            try:
                recovery["maintenance"] = json.loads(packet_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise PipelineError(f"cannot read maintenance packet: {exc}") from exc
    if getattr(args, "product_failure", None) is not None:
        if args.product_failure == "":
            recovery["product_failure"] = {}
        else:
            packet_path = safe_path(root, args.product_failure, "product failure packet", strict=True)
            try:
                recovery["product_failure"] = json.loads(packet_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise PipelineError(f"cannot read product failure packet: {exc}") from exc
    if args.command == "init":
        if args.verification is not None:
            source = safe_path(root, args.verification, "verification manifest", strict=True)
            if not source.is_relative_to(root / workflow):
                raise PipelineError("verification manifest must be workflow-local")
            try:
                recovery["verification"] = json.loads(source.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise PipelineError(f"cannot read verification manifest: {exc}") from exc
        state = Controller(store).reconfigure({"name": "init", "id": args.id, "expected_generation": args.expected_generation, "run_id": args.run_id, "feature": args.feature, "workflow_path": workflow, "project_root": str(root), "authority_paths": _pairs(args.authority, "authority"), "slices": _slices(args.slice), **recovery})
    elif args.command == "status":
        return Controller(store).status(**recovery)
    elif args.command == "next":
        assignment = {
            key: value for key, value in {
                "id": args.assignment_id, "worker_id": args.worker, "task": args.task,
            }.items() if value is not None
        }
        assignment["access"] = {"read": args.read, "write": args.write}
        assignment["commands"] = _commands(args.run)
        state = Controller(store).next(command_id=args.id, assignment=assignment, expected_generation=args.expected_generation)
    elif args.command == "complete":
        state = Controller(store).complete(command_id=args.id, artifact_path=args.artifact, expected_generation=args.expected_generation)
    elif args.command == "answer":
        state = Controller(store).transition({"name": "answer", "id": args.id, "expected_generation": args.expected_generation, "question_id": args.question_id, "answer": args.text})
    elif args.command == "accept":
        state = Controller(store).transition({"name": "accept", "id": args.id, "expected_generation": args.expected_generation})
    elif args.command == "migrate":
        state = Controller(store).migrate({
            "name": "migrate", "id": args.id,
            "imported": load_schema10(args.legacy_state, _slices(args.slice)),
        })
    elif args.command == "ready":
        state = Controller(store).ready(command_id=args.id, expected_generation=args.expected_generation)
    elif args.command == "technical-observe":
        state = Controller(store).technical_action(command_id=args.id, expected_generation=args.expected_generation, action=args.action)
    elif args.command == "technical-decision":
        packet_path = safe_path(root, args.packet, "technical decision packet", strict=True)
        try:
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PipelineError(f"cannot read technical decision packet: {exc}") from exc
        state = Controller(store).technical_action(command_id=args.id, expected_generation=args.expected_generation, packet=packet)
    elif args.command == "assignment-export":
        return export_assignment(root, Controller(store).status(), args.baseline, args.input)
    elif args.command == "delivery-read":
        return read_delivery(root, workflow, args.digest, args.offset, args.limit, args.pointer)
    elif args.command == "file-read":
        return read_file(root, Controller(store).read_status(), args.path, version=args.version, offset=args.offset, limit=args.limit)
    elif args.command == "step":
        return execute_step(Controller(store), root, args.expected_generation, args.action_id,
                            through_handoff=args.through_handoff)
    elif args.command == "pin-runtime":
        from .runtime_pin import pin_runtime
        return pin_runtime(args.destination)
    elif args.command in {"check", "rotate-owner", "read-admit", "recover-capability", "reconcile"}:
        payload = {key: getattr(args, key) for key in ("assignment_id", "quiescence", "collect_independent", "reason", "path") if hasattr(args, key)}
        for key in ("evidence", "packet"):
            if hasattr(args, key):
                source = safe_path(root, getattr(args, key), key, strict=True)
                if not source.is_relative_to(root / workflow):
                    raise PipelineError(f"{key} must be workflow-local")
                try:
                    payload[key] = json.loads(source.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    raise PipelineError(f"cannot read {key}: {exc}") from exc
        state = Controller(store).control_action(args.command, command_id=args.id, expected_generation=args.expected_generation, **payload)
    else:  # pragma: no cover
        raise AssertionError(args.command)
    view = status_view(state)
    return view


def run(args: argparse.Namespace) -> dict[str, Any]:
    result = _run(args)
    return director_brief(result) if getattr(args, "brief", False) else result


def main(argv: list[str] | None = None) -> int:
    try:
        result = run(parser().parse_args(argv))
    except PipelineError as exc:
        from .execution import classify_error
        print(json.dumps(classify_error(exc), ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
