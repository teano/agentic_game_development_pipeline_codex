"""Nine thin CLI commands for the v2 reducer."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .checkout import safe_path
from .legacy_gen53 import load_schema10
from .model import PipelineError, status_view
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
    value.add_argument(
        "--state", type=Path, default=Path(".agentic-pipeline-v2/state.json"),
        help=(
            "Controller state path; must be a direct .json child of the project "
            "root's .agentic-pipeline-v2 directory "
            "(default: .agentic-pipeline-v2/state.json)."
        ),
    )
    commands = value.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Initialize or reconfigure approved authority and slices.")
    init.add_argument("--id", required=True); init.add_argument("--root", type=Path, required=True)
    init.add_argument("--run-id", required=True, help="Compact safe run identifier (letters, digits, dot, underscore, or hyphen).")
    init.add_argument("--authority", action="append", default=[], required=True)
    init.add_argument("--slice", action="append", required=True); init.add_argument("--expected-generation", type=int)
    commands.add_parser("status", help="Return one executable action or terminal recovery fact.")
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
    resume = commands.add_parser("resume", help="Close one gate and route to a fresh bounded assignment.")
    resume.add_argument("--id", required=True); resume.add_argument("--expected-generation", type=int, required=True); resume.add_argument("--gate-id", required=True); resume.add_argument("--resolution", required=True); resume.add_argument("--run", action="append", default=[])
    accept = commands.add_parser("accept", help="Accept current passing phase evidence and advance.")
    accept.add_argument("--id", required=True); accept.add_argument("--expected-generation", type=int, required=True)
    migrate = commands.add_parser(
        "migrate",
        help="Unsupported schema-10 tombstone; archive legacy state/findings and run fresh Plan/init.",
    )
    migrate.add_argument("--id", required=True); migrate.add_argument("--legacy-state", type=Path, required=True); migrate.add_argument("--slice", action="append", required=True)
    ready = commands.add_parser("ready", help="Seal the fully verified live candidate as production-ready.")
    ready.add_argument("--id", required=True); ready.add_argument("--expected-generation", type=int, required=True)
    return value


def run(args: argparse.Namespace) -> dict[str, Any]:
    store = StateStore(args.state)
    if args.command == "init":
        root = safe_path(args.root, None, "project root", strict=True)
        state = Controller(store).reconfigure({"name": "init", "id": args.id, "expected_generation": args.expected_generation, "run_id": args.run_id, "project_root": str(root), "authority_paths": _pairs(args.authority, "authority"), "slices": _slices(args.slice)})
    elif args.command == "status":
        return Controller(store).status()
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
    elif args.command == "resume":
        state = Controller(store).transition({"name": "resume", "id": args.id, "expected_generation": args.expected_generation, "gate_id": args.gate_id, "resolution": args.resolution, "commands": _commands(args.run)})
    elif args.command == "accept":
        state = Controller(store).transition({"name": "accept", "id": args.id, "expected_generation": args.expected_generation})
    elif args.command == "migrate":
        state = Controller(store).migrate({
            "name": "migrate", "id": args.id,
            "imported": load_schema10(args.legacy_state, _slices(args.slice)),
        })
    elif args.command == "ready":
        state = Controller(store).ready(command_id=args.id, expected_generation=args.expected_generation)
    else:  # pragma: no cover
        raise AssertionError(args.command)
    view = status_view(state)
    return view


def main(argv: list[str] | None = None) -> int:
    try:
        result = run(parser().parse_args(argv))
    except PipelineError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
