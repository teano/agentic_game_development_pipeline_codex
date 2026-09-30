"""Thin CLI commands for the v2 reducer and bounded delivery."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

from .checkout import safe_path
from .delivery import (assemble_delivery_pages, director_brief, execute_step, export_assignment,
                       read_delivery, read_file, read_delivery_unit, share_work_evidence, _semantic_page, _pointer_value, host_read_command)
from .legacy_gen53 import load_schema10
from .model import (
    PIPELINE_STATE_FILENAME,
    PipelineError,
    digest,
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


class _SingleIdentity(argparse.Action):
    def __call__(self, parser, namespace, value, option_string=None):
        if getattr(namespace, self.dest, None) is not None:
            parser.error(f"{option_string} may be supplied only once")
        setattr(namespace, self.dest, value)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        prog="pipeline-v2",
        description="Run the replay-safe seven-phase GameDev pipeline controller.",
    )
    value.add_argument("--root", type=Path, required=True)
    projection = value.add_mutually_exclusive_group()
    projection.add_argument("--brief", action="store_true", help="Compact control response (the default); place before the subcommand.")
    projection.add_argument("--full", action="store_true", help="Explicit full control/debug view, including worker bodies; ordinary agent work uses compact responses.")
    value.add_argument(
        "--feature", required=True, type=feature_slug,
        help="lowercase feature slug selecting .agentic-pipeline/Workflows/<feature>",
    )
    commands = value.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Initialize or reconfigure approved authority and slices.",
        epilog='File request: {"id":"exact-command-id","run_id":"run","authority_paths":{"requirements":"path","specification":"path","plan":"path"},"slices":[{"id":"slice","allowed_paths":["path"],"planned_commands":[["executable","argument"]]}],"verification_path":".agentic-pipeline/Workflows/FEATURE/verification.json","qa_contract_path":".agentic-pipeline/Workflows/FEATURE/qa.json"}. Optional inline verification and qa_contract are JSON OBJECTS, not path strings; each is mutually exclusive with its *_path field. All paths resolve from --root; *_path files must belong to this feature workflow. Other optional fields: expected_generation (integer or null), recovery, maintenance, product_failure (objects). Values are exact approved/native fields, not new authority.')
    init.add_argument("--request", type=Path, help="UTF-8 JSON object inside --root (normally this feature workflow); mutually exclusive with other init inputs. Inline verification/qa_contract must be objects; use *_path for workflow JSON files.")
    init.add_argument("--id")
    init.add_argument("--run-id", help="Compact safe run identifier (letters, digits, dot, underscore, or hyphen).")
    init.add_argument("--authority", action="append", default=[], help="Exact requirements=PATH, specification=PATH and plan=PATH; repeat all three.")
    init.add_argument("--qa-contract", type=Path, help="Workflow-local QA methods and assertion contract from approved sources.")
    init.add_argument("--verification", type=Path, help="Workflow-local exact runnable verification manifest.")
    init.add_argument("--slice", action="append"); init.add_argument("--expected-generation", type=int)
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
    answer.add_argument("--id", required=True); answer.add_argument("--expected-generation", type=int, required=True); answer.add_argument("--question-id", required=True)
    answer_input = answer.add_mutually_exclusive_group(required=True)
    answer_input.add_argument("--text", help="Answer an ordinary open clarification.")
    answer_input.add_argument("--resolution", type=Path, help="Workflow-local JSON resolution for a bound no-progress hold.")
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
    unit = commands.add_parser("assignment-read", help="Read direct assignment fields and typed child selectors, following validated references.")
    unit.add_argument("--digest", required=True, help="Full target packet digest; not a delta digest used as a retained baseline.")
    unit.add_argument("--pointer", help="Logical RFC6901 selector; default /assignment, or /assignment/context/required_finding_conditions for work.")
    unit.add_argument("--view", choices=("index", "unit", "value", "work", "bootstrap", "work-index", "work-item", "qa-index", "qa-assertion", "check-result", "check-context", "section"), default="unit",
                      help="Legacy unit/index/value/work stay available; bootstrap groups startup metadata; work-index selects exact required pairs; work-item, check-result and section support lossless text continuation.")
    unit.add_argument("--finding-id", help="Exact required finding identity for work-item.")
    unit.add_argument("--condition-id", help="Optional exact role-required condition within the selected finding.")
    unit_selection = unit.add_mutually_exclusive_group()
    unit_selection.add_argument("--assertion-id", action="append", default=[], help="qa-assertion only: exact approved assertion ID; repeat for an actual subset. Cannot combine with identity-id.")
    unit_selection.add_argument("--identity-id", action=_SingleIdentity, help="qa-assertion only: expand one exact approved identity to its complete ordered assertions. Navigation, not a required assessment batch.")
    unit.add_argument("--baseline", help="work-item only: fully consumed and still retained same-owner packet; omit after lost context.")
    unit.add_argument("--continuation", help="Exact returned page token; keep the same packet/view/selection/baseline.")
    unit.add_argument("--limit", type=int, default=8192, help="Unicode characters per transport page, never a limit on required work.")
    unit.add_argument("--format", choices=("text", "json"), default="text", help="Decoded readable output by default; json is the machine envelope.")
    unit.add_argument("--assemble", action="store_true", help="Reconstruct only this exact paged selection with the shared digest-checking reader; returns decoded value. Cannot combine with --continuation.")
    unit.add_argument("--output", type=Path, help="With --assemble, save the complete JSON result under this workflow's ReadOutputs and return compact metadata. Does not grant reading or acceptance credit.")
    delivery = commands.add_parser("delivery-read", help="Read one bounded page of an immutable delivery artifact.")
    delivery.add_argument("--digest", required=True)
    delivery.add_argument("--pointer", help="Optional exact JSON pointer selecting a full semantic section before pagination.")
    file_read = commands.add_parser("file-read", help="Read exact bounded source text within assigned read access, or explicitly linked current-bundle instructions before init.")
    file_read.add_argument("--path", help="Exact assigned project-relative source; in instruction mode, absolute bundle path or path relative to that instruction entry.")
    file_read.add_argument("--instruction", help="Current bundle role (director/engineer/qa/...) or exact gamedev-* skill. Defaults to its entry; only explicitly linked bundle Markdown is readable. Grants no project read access.")
    file_read.add_argument("--version", help="Previous page or selected-input SHA-256; required for continuation.")
    source_selection = file_read.add_mutually_exclusive_group()
    source_selection.add_argument("--section", help="Exact unique ATX Markdown heading text, optionally prefixed with #; includes children until next same/higher heading. Duplicates require --lines.")
    source_selection.add_argument("--lines", help="Inclusive one-based FIRST:LAST within the source; no silent range clipping.")
    file_read.add_argument("--continuation", help="Exact shared-reader continuation for the same source version and selection.")
    file_read.add_argument("--format", choices=("text", "json"), default="json", help="JSON envelope for scripts; text prints bounded source plainly with its metadata header.")
    file_read.add_argument("--assemble", action="store_true")
    file_read.add_argument("--output", type=Path, help="With --assemble, preserve selected text under workflow/ReadOutputs and return a compact receipt.")
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
            operation.add_argument("--with-delivery", action="store_true", help="After the normal committed check, return compact result/binding and exact read-only JSON reader argv; no inline semantic body and no repeat check on transport failure.")
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
    for name in ("artifact-validate", "artifact-write"):
        artifact = commands.add_parser(name, help="Validate existing issued schema without product tests; artifact-write also writes the exact issued output as UTF-8 JSON.")
        artifact.add_argument("--source", type=Path, required=True)
        artifact.add_argument("--assignment-id", required=name == "artifact-write", help="Exact current assignment ID; required for writes so a stale owner cannot write a newer assignment's output.")
    begin = commands.add_parser("evidence-begin", help="Capture current candidate/input binding before an authorized external execution; creates no execution or semantic credit.")
    begin.add_argument("--request", type=Path, required=True,
        help="JSON request: record_id, assignment_id (exact active assignment), invocation (including actual channel), environment (stable binding/prerequisites), input_paths. Recipe preflight instead supplies preflight=true, project_root, feature, authority_paths before init and forbids assignment_id; no native assignment or QA credit is invented.")
    record = commands.add_parser("evidence-record", help="Preserve the actual external response and post-execution binding outside the candidate; never executes the tool.")
    record.add_argument("--record-id", required=True)
    record.add_argument("--result", type=Path, required=True, help="File containing the actual raw response bytes.")
    record.add_argument("--environment", type=Path, required=True, help="JSON object reporting actual post-execution environment.")
    evidence = commands.add_parser("evidence-read", help="Read one immutable execution record and exact raw-response locator without rerunning it.")
    evidence.add_argument("--record-id", required=True)
    evidence.add_argument("--raw-file", help="Exact recorded raw/stream filename. Verify original bytes, then read JSON values or exact UTF-8 text; never rewrite provenance.")
    evidence.add_argument("--pointer", help="Select an exact JSON pointer before serialization; raw-file values are under /value.")
    evidence.add_argument("--continuation")
    evidence.add_argument("--limit", type=int, default=8192)
    evidence.add_argument("--format", choices=("text", "json"), default="json")
    evidence.add_argument("--assemble", action="store_true")
    evidence.add_argument("--output", type=Path)
    for name in ("qa-draft", "qa-read"):
        qa = commands.add_parser(name, help="Create/resume or read the current bound QA working artifact; default output is counts/revision, never unassessed not_run rows.")
        qa.add_argument("--assignment-id", required=True)
        selection = qa.add_mutually_exclusive_group()
        selection.add_argument("--identity-id", help="Read only this identity's stored assessments and pending IDs.")
        selection.add_argument("--assertion-id", help="Read only this assertion's stored assessment or pending status.")
        qa.add_argument("--pointer", help="Select an exact field within this draft response before pagination; identity/assertion selection remains in force.")
        qa.add_argument("--continuation")
        qa.add_argument("--limit", type=int, default=8192)
        qa.add_argument("--format", choices=("text", "json"), default="text")
        qa.add_argument("--assemble", action="store_true")
        qa.add_argument("--output", type=Path, help="With --assemble, save the exact selection under workflow/ReadOutputs and return a compact receipt.")
    prepare = commands.add_parser("qa-prepare", help="Read complete selected obligations and save a bound editable request under ReadOutputs; preserve unsaved edits on retry. Never assess or execute a probe.")
    prepare.add_argument("--assignment-id", required=True)
    prepare_selection = prepare.add_mutually_exclusive_group(required=True)
    prepare_selection.add_argument("--assertion-id", action="append", default=[], help="Repeat exact selected assertion IDs for an actual scenario subset. Cannot combine with identity-id.")
    prepare_selection.add_argument("--identity-id", action=_SingleIdentity, help="Expand one exact approved identity to its complete ordered assertions; does not require assessing them as one group.")
    prepare.add_argument("--method-id", help="Optional approved semantic ID or reference. Omit to read all alternatives before selecting; a unique method is filled mechanically, never assessed.")
    prepare.add_argument("--pointer", help="Select prepared context or /record_request before serialization.")
    prepare.add_argument("--continuation")
    prepare.add_argument("--limit", type=int, default=8192)
    prepare.add_argument("--format", choices=("text", "json"), default="json")
    prepare.add_argument("--assemble", action="store_true")
    prepare.add_argument("--output", type=Path, help="Optional explicit ReadOutputs destination; normally the request-bound path is generated. Return complete selected context in this same call. Cannot combine with pointer/continuation.")
    record = commands.add_parser("qa-record", help="Atomically persist completed assertion assessments in the same QA draft; unresolved work remains pending.")
    record.add_argument("--assignment-id", required=True)
    record.add_argument("--source", type=Path, required=True, help="JSON object: expected_revision integer and assessments array of terminal-shaped completed rows.")
    finalize = commands.add_parser("qa-finalize", help="Mechanically derive the terminal QA artifact after all assertions are assessed; pending QA stays with QA.")
    finalize.add_argument("--assignment-id", required=True)
    finalize.add_argument("--expected-revision", type=int, required=True)
    return value


def _json_object(root: Path, source: Path, label: str, *, workflow: str | None = None) -> dict[str, Any]:
    from .artifact_io import read_json
    path = safe_path(root, source, label, strict=True)
    if workflow is not None and not path.is_relative_to(root / workflow):
        raise PipelineError(f"{label} must be inside the selected workflow {workflow}; paths resolve from --root")
    value = read_json(path)
    if not isinstance(value, dict):
        raise PipelineError(f"{label} must be a JSON object")
    return value


def _init_request(root: Path, workflow: str, source: Path) -> dict[str, Any]:
    request = _json_object(root, source, "init request (a project-contained UTF-8 JSON file)")
    required = {"id", "run_id", "authority_paths", "slices"}
    allowed = required | {"expected_generation", "verification", "verification_path", "qa_contract", "qa_contract_path", "recovery", "maintenance", "product_failure"}
    if not required <= request.keys() or request.keys() - allowed:
        raise PipelineError("init request requires id, run_id, authority_paths and slices; unknown fields are not allowed")
    for key in ("id", "run_id"):
        if not isinstance(request[key], str) or not request[key].strip():
            raise PipelineError(f"init request {key} must be a non-empty string")
    if not isinstance(request["authority_paths"], dict):
        raise PipelineError("init request authority_paths must be an object mapping requirements, specification and plan to exact paths")
    if not isinstance(request["slices"], list) or any(not isinstance(item, dict) for item in request["slices"]):
        raise PipelineError("init request slices must be an array of slice objects")
    if request.get("expected_generation") is not None and type(request["expected_generation"]) is not int:
        raise PipelineError("init request expected_generation must be an integer or null")
    for field in ("verification", "qa_contract", "recovery", "maintenance", "product_failure"):
        path_key = field + "_path"
        if field in request and path_key in request:
            raise PipelineError(f"init request {field} and {path_key} are mutually exclusive")
        if field in request and not isinstance(request[field], dict):
            hint = f"; use {path_key} for a workflow JSON file" if field in {"verification", "qa_contract"} else ""
            raise PipelineError(f"init request {field} must be an inline JSON object, not a string/path{hint}")
        if path_key in request:
            value = request.pop(path_key)
            if not isinstance(value, str) or not value.strip():
                raise PipelineError(f"init request {path_key} must be a non-empty path string")
            request[field] = _json_object(root, Path(value), f"init request {path_key}", workflow=workflow)
    return request


def _deliver_selection(root, workflow, args, read_page):
    if args.output is not None and not args.assemble:
        raise PipelineError(f"{args.command} --output requires --assemble")
    if args.assemble and args.continuation is not None:
        raise PipelineError(f"{args.command} --assemble starts the exact selection; do not supply --continuation")
    result = assemble_delivery_pages(read_page) if args.assemble else read_page(args.continuation)
    if args.output is not None:
        from .artifact_io import write_read_output
        saved = write_read_output(root, root / workflow, args.output, result)
        return {key: value for key, value in result.items() if key != "value"} | {
            "saved_output": saved, "content_included": False, "unit_complete": False,
            "delivery_complete": False, "read_credit": False}
    return result


def _focused_result(root, workflow, args, result):
    pointer = args.pointer or ""
    try:
        body = _pointer_value(result, pointer)
    except PipelineError as exc:
        exc.path = pointer
        raise
    metadata = {"format": "pipeline-source-page-v1", "version": digest(body), "pointer": pointer,
                "view": args.command, "binding": result.get("binding"), "revision": result.get("revision"),
                "record_digest": result.get("record_digest", result.get("record", {}).get("digest")),
                "record_id": result.get("record_id"), "ref": result.get("ref"), "record_path": result.get("path"), "raw": result.get("raw"),
                "provenance": result.get("provenance", result.get("record", {}).get("provenance")),
                "assignment_id": getattr(args, "assignment_id", None),
                "selection": {key: getattr(args, key) for key in ("assertion_id", "identity_id", "method_id", "raw_file") if hasattr(args, key)}}
    return _deliver_selection(root, workflow, args,
        lambda continuation: _semantic_page(body, metadata, continuation, args.limit))


def _prepared_request_output(root, workflow, request, destination):
    """Keep edited default scaffolds; their content earns no validation credit."""
    from .artifact_io import contained_path, write_read_output
    generated = destination is None
    if generated:
        destination = root / workflow / "ReadOutputs" / ("qa-request-" + digest(request) + ".json")
        path = contained_path(root / workflow / "ReadOutputs", destination)
        if path.exists():
            raw = path.read_bytes()
            template = (json.dumps(request, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
            if raw != template:
                return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}, "preserved_edited_request"
    return write_read_output(root, root / workflow, destination, request), "prepared_request"


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
        if args.request is not None:
            if (args.id is not None or args.run_id is not None or args.authority or args.slice
                    or args.expected_generation is not None or args.verification is not None
                    or args.qa_contract is not None or recovery):
                raise PipelineError("init --request cannot be combined with other init inputs")
            request = _init_request(root, workflow, args.request)
            state = Controller(store).reconfigure({**request, "name": "init", "feature": args.feature,
                "workflow_path": workflow, "project_root": str(root)})
            return status_view(state)
        if args.id is None or args.run_id is None or not args.authority or not args.slice:
            raise PipelineError("init requires --request or --id, --run-id, --authority and --slice")
        for field in ("verification", "qa_contract"):
            manifest = getattr(args, field)
            if manifest is None:
                continue
            recovery[field] = _json_object(root, manifest, field + " manifest", workflow=workflow)
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
        payload = {"answer": args.text}
        if args.resolution is not None:
            source = safe_path(root, args.resolution, "no-progress resolution packet", strict=True)
            if not source.is_relative_to(root / workflow):
                raise PipelineError("no-progress resolution packet must be workflow-local")
            try:
                payload = {"resolution": json.loads(source.read_text(encoding="utf-8"))}
            except (OSError, json.JSONDecodeError) as exc:
                raise PipelineError(f"cannot read no-progress resolution packet: {exc}") from exc
        state = Controller(store).transition({"name": "answer", "id": args.id, "expected_generation": args.expected_generation, "question_id": args.question_id, **payload})
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
    elif args.command == "assignment-read":
        def read_page(continuation):
            return read_delivery_unit(root, workflow, args.digest, args.pointer, args.view,
                                      finding_id=args.finding_id, condition_id=args.condition_id, baseline=args.baseline,
                                      assertion_ids=args.assertion_id, identity_id=args.identity_id, continuation=continuation, limit=args.limit)
        return _deliver_selection(root, workflow, args, read_page)
    elif args.command == "delivery-read":
        return read_delivery(root, workflow, args.digest, args.offset, args.limit, args.pointer)
    elif args.command == "file-read":
        if args.path is None and args.instruction is None:
            raise PipelineError("file-read requires --path or an exact --instruction entry")
        if args.assemble and args.offset:
            raise PipelineError("file-read --assemble starts the complete selection; numeric --offset is not allowed")
        lines = None
        if args.lines is not None:
            try:
                first, last = args.lines.split(":")
                lines = (int(first), int(last))
            except (ValueError, TypeError) as exc:
                raise PipelineError("file-read --lines must be inclusive FIRST:LAST integers") from exc
        view = None if args.instruction else Controller(store).read_status()
        return _deliver_selection(root, workflow, args, lambda continuation: read_file(
            root, view, args.path, version=args.version, offset=args.offset, limit=args.limit,
            continuation=continuation, section=args.section, lines=lines, instruction=args.instruction, feature=args.feature))
    elif args.command == "step":
        return execute_step(Controller(store), root, args.expected_generation, args.action_id,
                            through_handoff=args.through_handoff)
    elif args.command == "pin-runtime":
        from .runtime_pin import pin_runtime
        return pin_runtime(args.destination)
    elif args.command == "artifact-validate":
        return Controller(store).artifact_validate(args.source if args.source.is_absolute() else root / args.source,
                                                  assignment_id=args.assignment_id)
    elif args.command == "artifact-write":
        return Controller(store).artifact_write(args.source if args.source.is_absolute() else root / args.source,
                                               assignment_id=args.assignment_id)
    elif args.command == "evidence-begin":
        return Controller(store).evidence_begin(_json_object(root, args.request, "execution evidence request"))
    elif args.command == "evidence-record":
        return Controller(store).evidence_record(args.record_id, args.result if args.result.is_absolute() else root / args.result,
            _json_object(root, args.environment, "execution environment"))
    elif args.command == "evidence-read":
        result = Controller(store).evidence_read(args.record_id, **({"raw_file": args.raw_file} if args.raw_file else {}))
        if args.pointer is None and not (args.raw_file or args.continuation or args.assemble or args.output):
            return result
        return _focused_result(root, workflow, args, result)
    elif args.command == "qa-prepare":
        result = Controller(store).qa_prepare(args.assignment_id, args.assertion_id, args.method_id, identity_id=args.identity_id)
        if args.output is not None or (args.pointer is None and args.continuation is None):
            if args.pointer is not None or args.continuation is not None:
                raise PipelineError("qa-prepare --output saves the editable record input and returns complete context; do not select pointer/continuation")
            saved, request_status = _prepared_request_output(root, workflow, result["record_request"], args.output)
            context = {key: value for key, value in result.items() if key != "record_request"}
            context["saved_record_request"] = saved
            context["request_status"] = request_status
            if request_status == "preserved_edited_request":
                context["required_action"] += " Existing unsaved request bytes were preserved. Read that exact file before editing or recording; its content has not been validated or assessed."
            selected = argparse.Namespace(**vars(args))
            selected.output, selected.assemble = None, True
            return _focused_result(root, workflow, selected, context)
        return _focused_result(root, workflow, args, result)
    elif args.command in {"qa-draft", "qa-read"}:
        selected = args.identity_id or args.assertion_id
        if not selected and args.pointer is None and (args.continuation or args.assemble or args.output):
            raise PipelineError("QA draft paging requires --identity-id or --assertion-id; the default response is compact progress")
        method = Controller(store).qa_draft if args.command == "qa-draft" else Controller(store).qa_read
        result = method(args.assignment_id, identity_id=args.identity_id, assertion_id=args.assertion_id)
        if args.pointer is not None:
            return _focused_result(root, workflow, args, result)
        if not selected:
            return result
        version = digest(result)
        metadata = {"format": "pipeline-source-page-v1", "version": version,
                    "view": "qa-draft-selection", "pointer": "/", "assignment_id": args.assignment_id,
                    "working_path": result.get("working_path"), "revision": result.get("revision"),
                    "identity_id": args.identity_id, "assertion_id": args.assertion_id}
        return _deliver_selection(root, workflow, args,
            lambda continuation: _semantic_page(result, metadata, continuation, args.limit))
    elif args.command == "qa-record":
        return Controller(store).qa_record(args.assignment_id, _json_object(root, args.source, "QA assessment group"))
    elif args.command == "qa-finalize":
        return Controller(store).qa_finalize(args.assignment_id, args.expected_revision)
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
        if args.command == "check" and args.with_delivery:
            return _check_delivery(root, state, args)
    else:  # pragma: no cover
        raise AssertionError(args.command)
    view = status_view(state)
    return view


def run(args: argparse.Namespace) -> dict[str, Any]:
    result = _run(args)
    return result if getattr(args, "full", False) else director_brief(result)


def _work_text_presentation(value: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Share only exact evidence strings already present in this response body."""
    return share_work_evidence(value)


def _render_assignment_unit(result: dict[str, Any]) -> str:
    """Human output decodes the value once; it is never a JSON-text-in-JSON page."""
    if result.get("format") in {"pipeline-delivery-page-v1", "pipeline-source-page-v1"}:
        return json.dumps({key: value for key, value in result.items() if key != "text"},
                          ensure_ascii=False, separators=(",", ":")) + "\n" + result["text"]
    metadata = {key: value for key, value in result.items() if key not in {"value", "children"}}
    body = result["value"] if "value" in result else result.get("children", [])
    if result.get("view") == "work":
        body, shared = _work_text_presentation(body)
        if shared:
            metadata["text_rendering"] = (
                "Evidence objects with same_exact_text_as reuse the exact string at that RFC6901 fragment "
                "in this response body; no additional read is required."
            )
    return (json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
            + "\n" + (body if isinstance(body, str) else json.dumps(body, ensure_ascii=False, indent=2)))


def _check_delivery(root: Path, state: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    """Compose transport only after native commit; no transport failure retries mutation."""
    record = next(item for item in state["history"] if item.get("id") == args.id)
    prefix = [sys.executable, str(Path(__file__).resolve().parents[1] / "pipeline_state.py"),
              "--root", str(root), "--feature", args.feature]
    response = {"format": "pipeline-check-delivery-v1", "committed": True,
                "command": "check", "command_id": args.id, "assignment_id": args.assignment_id,
                "expected_generation": args.expected_generation, "committed_generation": record["generation"],
                "generation": state["generation"], "transport": {"status": "pending"},
                "recovery": {"status_argv": [*prefix, "status"],
                             "export_argv": [*prefix, "assignment-export"],
                             "rule": "Check is committed. Recover transport read-only; never issue a new check for export/read/render failure. An uncertain original call is retried with the same ID and arguments."}}
    try:
        view = status_view(state)
        response["next_action"] = director_brief(view)["next_action"]
        if state["generation"] != record["generation"]:
            response["transport"] = {"status": "cursor_advanced", "reason": "This check is recorded; current assignment input belongs to a later cursor. Inspect current status."}
            return response
        assignment = view.get("active_assignment") or {}
        context = assignment.get("context", {})
        diagnostic, machine = context.get("diagnostic_checks", {}), context.get("machine_checks", {})
        response["binding"] = {"run_id": view.get("run_id"), "feature": args.feature,
            "assignment_id": args.assignment_id, "worker_id": assignment.get("worker_id"),
            "generation": state["generation"], **{key: machine[key] for key in
                ("candidate_tree_oid", "authority_digest", "pipeline_runtime_digest") if key in machine}}
        response["result"] = {
            "checks": [{key: item[key] for key in ("check_id", "returncode", "duration_ms", "execution_evidence", "execution_record_digest") if key in item}
                       for item in diagnostic.get("results", [])],
            "receipts": [{key: item[key] for key in ("id", "outcome", "receipt_id", "receipt_sha256", "execution_evidence", "execution_record_digest", "source_locator") if key in item}
                         for item in machine.get("checks", [])],
            "pending_check_ids": deepcopy(machine.get("pending_check_ids", [])),
            "grants_semantic_credit": False, "grants_manual_acceptance": False,
        }
        for receipt in [*response["result"]["checks"], *response["result"]["receipts"]]:
            reference = receipt.get("execution_evidence")
            if isinstance(reference, str) and reference.startswith("execution-evidence:"):
                receipt["read_argv"] = [*prefix, "evidence-read", "--record-id", reference.partition(":")[2].split("#", 1)[0],
                                        "--format", "text", "--assemble"]
                receipt["read"] = {"exec_command": host_read_command(receipt["read_argv"], root)}
        exported = export_assignment(root, view)
        reader = [*prefix, "assignment-read", "--digest", exported["packet_digest"], "--format", "text"]
        read_argv = [*reader, "--view", "check-context", "--assemble"]
        response["assignment_delivery"] = {key: exported[key] for key in
                                           ("packet_digest", "generation", "assignment_id", "worker_id", "mode")}
        response["recovery"]["read_argv"] = read_argv
        response["recovery"]["read"] = {"exec_command": host_read_command(read_argv, root)}
        response["recovery"]["save_usage"] = "Append --output <workflow/ReadOutputs/file.json> to save the complete selection and return compact metadata."
        response["recovery"]["bootstrap_argv"] = [*reader, "--view", "bootstrap", "--assemble"]
        response["recovery"]["bootstrap"] = {"exec_command": host_read_command(response["recovery"]["bootstrap_argv"], root)}
        response["recovery"]["selectors"] = {
            "diagnostic_checks": "/check_context/diagnostic_checks",
            "machine_checks": "/check_context/machine_checks",
            "assignment": "/assignment", "generation": "/generation",
        }
        response["transport"] = {"status": "delivered", "content_included": False,
                                 "selection_complete": False}
    except Exception as exc:
        response["transport"] = {"status": "failed", "error": str(exc), "error_type": type(exc).__name__}
    return response


def main(argv: list[str] | None = None) -> int:
    # Machine envelopes are UTF-8 irrespective of the launching shell's locale.
    # Content newlines remain escaped JSON data, separate from stdout framing.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", newline="")
    try:
        args = parser().parse_args(argv)
        result = run(args)
    except PipelineError as exc:
        from .execution import classify_error
        error = classify_error(exc)
        if hasattr(exc, "path"):
            error["path"] = exc.path
        print(json.dumps(error, ensure_ascii=False), file=sys.stderr)
        return 2
    if (args.command in {"assignment-read", "file-read", "qa-draft", "qa-read", "qa-prepare", "evidence-read"} and args.format == "text"
            and result.get("format") in {"pipeline-delivery-page-v1", "pipeline-delivery-unit-v1", "pipeline-source-page-v1", "pipeline-source-unit-v1"}):
        print(_render_assignment_unit(result))
    else:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 2 if args.command in {"artifact-validate", "artifact-write", "qa-record", "qa-finalize"} and result.get("valid") is False else 0


if __name__ == "__main__":
    raise SystemExit(main())
