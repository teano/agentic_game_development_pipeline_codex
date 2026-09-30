"""Lossless, content-addressed delivery and one-step controller execution.

Delivery files are transport artifacts, never controller evidence or read receipts.
Offsets count Unicode code points in decoded UTF-8 text (not bytes or tokens).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shlex
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlsplit

from .checkout import matches, safe_path
from .model import ROLES, PipelineError, canonical_bytes, is_digest, normalize_literal_path, status_view


def host_read_command(argv: list[str], root: Path, *, windows: bool | None = None) -> dict[str, str]:
    """Quote an existing read invocation, never infer environment or authority."""
    windows = os.name == "nt" if windows is None else windows
    if windows:
        command = "& " + " ".join("'" + str(argument).replace("'", "''") + "'" for argument in argv)
        shell = "powershell"
    else:
        command, shell = shlex.join([str(argument) for argument in argv]), "/bin/sh"
    return {"cmd": command, "shell": shell, "workdir": str(root)}


def _read_handle(argv, root):
    return {"exec_command": host_read_command(argv, root)}


def _role_instructions(role: str | None) -> dict[str, str] | None:
    """Locate only the assigned worker's existing contract in this running bundle."""
    sources = {
        "engineer": "gamedev-engineer/SKILL.md",
        "reviewer": "gamedev-review/SKILL.md",
        "qa": "gamedev-qa/SKILL.md",
        "documentation_finisher": "gamedev-documentation-finisher/SKILL.md",
        "planner": "gamedev-pipeline/references/pipeline-protocol.md",
        "slicer": "gamedev-pipeline/references/pipeline-protocol.md",
    }
    if role not in sources:
        return None
    bundle = Path(__file__).resolve().parents[4]
    path = (bundle / "skills" / sources[role]).resolve()
    if not path.is_relative_to(bundle) or not path.is_file():
        raise PipelineError("assigned role instruction source must exist inside the running bundle")
    locator = {"role": role, "path": str(path)}
    if role in {"planner", "slicer"}:
        locator["section"] = "Runtime Plan and Slice"
    return locator


def director_brief(view: dict[str, Any]) -> dict[str, Any]:
    """Keep control facts and semantic boundaries without retransmitting worker input.

This is explicitly an observation, not an executable worker assignment. Full
status remains available; assignment-export is the lossless worker transport.
"""
    if "next_action" not in view or "active_assignment" not in view:
        return view
    result = deepcopy(view)

    def identity(assignment: dict[str, Any]) -> dict[str, Any]:
        metadata = {key: assignment[key] for key in ("id", "role", "worker_id", "output_path") if key in assignment}
        instructions = _role_instructions(assignment.get("role") or ROLES.get(view.get("phase")))
        if instructions is not None:
            metadata["role_instructions"] = instructions
        metadata["content_included"] = False
        context = assignment.get("context")
        diagnostic = context.get("diagnostic_checks") if isinstance(context, dict) else None
        if isinstance(diagnostic, dict):
            projected = {
                key: deepcopy(diagnostic[key])
                for key in ("assignment_id", "candidate_tree_oid", "grants_semantic_credit")
                if key in diagnostic
            }
            results = diagnostic.get("results")
            if isinstance(results, list):
                projected["results"] = [
                    {key: deepcopy(item[key]) for key in ("check_id", "returncode", "duration_ms") if key in item}
                    for item in results if isinstance(item, dict)
                ]
            machine = context.get("machine_checks")
            if isinstance(machine, dict):
                for key in ("pending_check_ids", "grants_manual_acceptance"):
                    if key in machine:
                        projected[key] = deepcopy(machine[key])
            metadata["diagnostic_checks"] = projected
        observation = assignment.get("technical_observation")
        if isinstance(observation, dict):
            metadata["technical_observation"] = {key: observation[key] for key in ("id", "tree", "assignment_id") if key in observation}
        return metadata

    if result["active_assignment"] is not None:
        result["active_assignment"] = identity(result["active_assignment"])
        result["assignment_delivery"] = {"command": "assignment-export", "content_included": False,
            **({"project_root": view["project_root"]} if "project_root" in view else {})}
    action = result["next_action"]
    if isinstance(action.get("assignment"), dict):
        action["assignment"] = identity(action["assignment"])
    invocation = public_action_invocation(view)
    if invocation is not None:
        action["invocation"] = invocation
    result["view"] = "director-brief"
    return result


def public_action_invocation(view: dict[str, Any]) -> dict[str, Any] | None:
    """Project the current public action into exact argv and missing input shape.

    This supplies syntax only. It neither grants recovery/semantic authority nor
    selects missing evidence, and it never infers a newer action identity.
    """
    action = view.get("next_action", {})
    root, feature = view.get("project_root"), view.get("feature")
    if not root or not feature or not action.get("command_id") or "expected_generation" not in action:
        return None
    prefix = [sys.executable, str(Path(__file__).resolve().parents[1] / "pipeline_state.py"),
              "--root", root, "--feature", feature, "--brief"]
    command = action.get("command")
    if command in {"next", "complete", "accept"}:
        return {"argv": [*prefix, "step", "--expected-generation", str(action["expected_generation"]),
                         "--action-id", action["command_id"], "--through-handoff"]}
    argv = [*prefix, command, "--id", action["command_id"],
            "--expected-generation", str(action["expected_generation"])]
    if command == "ready":
        return {"argv": argv}
    if command == "recover-capability":
        return {"argv_prefix": [*argv, "--evidence"], "input": {
            "kind": "workflow_json_file", "field_sources": {"binding": "/capability_binding"},
            "source": "current next_action; copy the complete exact field, never infer its content",
            "required_fields": {key: "non-empty factual string supplied by the responsible specialist"
                                for key in ("prerequisite", "resolution", "evidence", "unchanged_dependencies")},
            "authority": "Requires a real prerequisite change; filled binding is not evidence or permission."}}
    if command == "init":
        sources = {"id": "/command_id", "expected_generation": "/expected_generation", "run_id": "/run_id",
                   "authority_paths": "/authority", "slices": "/slices"}
        sources.update({key: "/" + key for key in ("recovery", "maintenance", "product_failure") if key in action})
        return {"argv_prefix": [*prefix, "init", "--request"], "input": {
            "kind": "workflow_json_file", "field_sources": sources, "required_fields": {},
            "source": "current next_action; copy complete exact fields, never parse plan prose or duplicate it in control responses",
            "authority": "Preserve the current action's authorization and recovery boundary; no new approval is inferred."}}
    if command == "answer":
        argv += ["--question-id", action["question_id"]]
        if "no_progress_binding" in action:
            return {"argv_prefix": [*argv, "--resolution"], "input": {
                "kind": "workflow_json_file", "field_sources": {"binding": "/no_progress_binding"},
                "schema_pointer": "/resolution_schema", "source": "current next_action",
                "authority": "Responsible specialist supplies the source-supported resolution."}}
        return {"argv_prefix": [*argv, "--text"], "input": {
            "kind": "single_argument", "authority": "Responsible specialist supplies the actual authorized answer."}}
    return None


def json_patch(before: Any, after: Any, path: str = "") -> list[dict[str, Any]]:
    """Deterministic RFC 6902 add/remove/replace subset, including list entries."""
    if canonical_bytes(before) == canonical_bytes(after):
        return []
    child = lambda key: path + "/" + str(key).replace("~", "~0").replace("/", "~1")
    if isinstance(before, dict) and isinstance(after, dict):
        result = [{"op": "remove", "path": child(key)} for key in sorted(before.keys() - after.keys())]
        for key in sorted(after):
            result.extend(json_patch(before[key], after[key], child(key)) if key in before else [
                {"op": "add", "path": child(key), "value": after[key]},
            ])
        return result
    if isinstance(before, list) and isinstance(after, list):
        common = min(len(before), len(after))
        result = [op for index in range(common) for op in json_patch(before[index], after[index], child(index))]
        result.extend({"op": "remove", "path": child(index)} for index in range(len(before) - 1, common - 1, -1))
        result.extend({"op": "add", "path": child(index), "value": after[index]} for index in range(common, len(after)))
        return result
    return [{"op": "replace", "path": path, "value": after}]


def _directory(root: Path, workflow: str) -> Path:
    return safe_path(root, f"{workflow}/Delivery", "delivery directory")


def _save(root: Path, workflow: str, value: dict[str, Any]) -> dict[str, Any]:
    payload = canonical_bytes(value)
    version = hashlib.sha256(payload).hexdigest()
    directory = _directory(root, workflow)
    temporary = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        target = safe_path(root, directory / f"{version}.json", "delivery file")
        fd, temporary = tempfile.mkstemp(prefix=".delivery-", suffix=".tmp", dir=directory)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if target.exists():
            if target.read_bytes() != payload:
                raise PipelineError("delivery digest collision or corrupt existing file")
        else:
            # Publish complete bytes; concurrent same-digest exports have identical bytes.
            os.replace(temporary, target)
            temporary = None
    except OSError as exc:
        raise PipelineError(f"cannot save delivery file: {exc}") from exc
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
    return {"digest": version, "path": target.relative_to(root).as_posix(),
            "characters": len(payload.decode("utf-8")), "bytes": len(payload)}


def _load(root: Path, workflow: str, version: str) -> tuple[dict[str, Any], str]:
    if not is_digest(version):
        raise PipelineError("delivery digest must be a SHA-256 hexadecimal digest")
    target = safe_path(root, _directory(root, workflow) / f"{version}.json", "delivery file", strict=True)
    try:
        payload = target.read_bytes()
        if hashlib.sha256(payload).hexdigest() != version:
            raise PipelineError("delivery file changed; digest does not match")
        text = payload.decode("utf-8")
        value = json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PipelineError(f"cannot read delivery file: {exc}") from exc
    if not isinstance(value, dict):
        raise PipelineError("delivery file must contain an object")
    return value, text


def _child_pointer(pointer: str, key: Any) -> str:
    return pointer + "/" + str(key).replace("~", "~0").replace("/", "~1")


def _pointer_parts(pointer: str) -> list[str]:
    if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
        raise PipelineError("section pointer must be an empty or slash-prefixed JSON pointer")
    parts = pointer[1:].split("/") if pointer else []
    if any("~" in part.replace("~1", "").replace("~0", "") for part in parts):
        raise PipelineError("section pointer contains an invalid RFC 6901 escape")
    return [part.replace("~1", "/").replace("~0", "~") for part in parts]


def _child_value(value: Any, part: str) -> Any:
    try:
        if isinstance(value, list):
            if not part.isascii() or not part.isdigit() or (len(part) > 1 and part.startswith("0")):
                raise ValueError("invalid array index")
            return value[int(part)]
        return value[part]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise PipelineError("section pointer does not identify a value") from exc


def _pointer_value(value: Any, pointer: str) -> Any:
    for part in _pointer_parts(pointer):
        value = _child_value(value, part)
    return value


def _transport_assignment(root: Path, workflow: str, packet: dict[str, Any]) -> list[dict[str, Any]]:
    """Replace exact duplicate values only; canonical controller state is untouched."""
    context = packet["assignment"].get("context")
    references: dict[str, Any] = packet["references"]
    resources = []
    if not isinstance(context, dict):
        return resources

    def reference(parent: Any, key: Any, source: str, descriptor: dict[str, Any]) -> None:
        parent[key] = {"$delivery_ref": source}
        references[source] = descriptor

    qa = context.get("qa_contract")
    if isinstance(qa, dict) and qa.get("status") == "bound" and "definition" in qa:
        if not isinstance(qa.get("binding"), dict):
            raise PipelineError("bound QA delivery requires its existing contract binding")
        resource = {"format": "pipeline-qa-definition-v1",
                    **{key: packet[key] for key in ("project_root", "run_id", "feature")},
                    "binding": deepcopy(qa["binding"]), "definition": qa["definition"]}
        saved = _save(root, workflow, resource)
        source = "/assignment/context/qa_contract/definition"
        reference(qa, "definition", source, {"kind": "resource", "digest": saved["digest"], "pointer": "/definition"})
        resources.append({**saved, "pointer": source})

    convergence = context.get("convergence")
    opened = convergence.get("open") if isinstance(convergence, dict) else None
    failure = context.get("verification_failure")
    findings = failure.get("findings") if isinstance(failure, dict) else None
    if not isinstance(opened, dict):
        return resources
    originals = {canonical_bytes(item): _child_pointer("/assignment/context/convergence/open", key)
                 for key, item in opened.items() if isinstance(item, dict)}
    if isinstance(findings, list):
        for index, finding in enumerate(findings):
            target = originals.get(canonical_bytes(finding))
            if target is not None:
                reference(findings, index, f"/assignment/context/verification_failure/findings/{index}",
                          {"kind": "local", "pointer": target})
    statuses = convergence.get("condition_status")
    if isinstance(statuses, dict):
        for identity, rows in statuses.items():
            finding = opened.get(identity)
            if not isinstance(finding, dict) or not isinstance(finding.get("text"), str) or not isinstance(rows, dict):
                continue
            target = _child_pointer("/assignment/context/convergence/open", identity) + "/text"
            for condition, row in rows.items():
                if isinstance(row, dict) and row.get("evidence") == finding["text"]:
                    source = _child_pointer(_child_pointer("/assignment/context/convergence/condition_status", identity), condition) + "/evidence"
                    reference(row, "evidence", source, {"kind": "local", "pointer": target})
    return resources


def _same_owner(previous: dict[str, Any], packet: dict[str, Any], *, legacy: bool = False) -> bool:
    return (isinstance(packet.get("project_root"), str) and isinstance(packet.get("assignment"), dict)
            and all(previous.get(key) == packet.get(key) for key in ("run_id", "feature"))
            and previous.get("project_root", packet["project_root"] if legacy else None) == packet["project_root"]
            and isinstance(previous.get("assignment"), dict)
            and all(previous["assignment"].get(key) == packet["assignment"].get(key) for key in ("role", "worker_id")))


def _baseline_order(previous: dict[str, Any], packet: dict[str, Any]) -> None:
    if (type(previous.get("generation")) is not int or type(packet.get("generation")) is not int
            or previous["generation"] > packet["generation"]):
        raise PipelineError("delivery baseline must not be newer than its target packet")


def _apply_patch(document: dict[str, Any], patch: Any) -> Any:
    """Validate/reconstruct the exported RFC 6902 subset without trusting its target digest."""
    if not isinstance(patch, list):
        raise PipelineError("delivery delta patch must be a list")
    result = deepcopy(document)
    for operation in patch:
        if not isinstance(operation, dict) or operation.get("op") not in {"add", "remove", "replace"}:
            raise PipelineError("delivery delta contains an unsupported patch operation")
        op = operation["op"]
        if set(operation) != ({"op", "path"} if op == "remove" else {"op", "path", "value"}):
            raise PipelineError("delivery delta patch operation has invalid fields")
        parts = _pointer_parts(operation["path"])
        if not parts:
            if op == "remove":
                raise PipelineError("delivery delta cannot remove its document")
            result = deepcopy(operation["value"])
            continue
        parent = result
        for part in parts[:-1]:
            parent = _child_value(parent, part)
        key = parts[-1]
        if isinstance(parent, list):
            if not key.isascii() or not key.isdigit() or (len(key) > 1 and key.startswith("0")):
                raise PipelineError("delivery delta has an invalid array index")
            key = int(key)
            if key > len(parent) or (op != "add" and key == len(parent)):
                raise PipelineError("delivery delta array index is out of range")
            if op == "add":
                parent.insert(key, deepcopy(operation["value"]))
                continue
        elif not isinstance(parent, dict):
            raise PipelineError("delivery delta target is not a container")
        if op != "add" and (key not in parent if isinstance(parent, dict) else key >= len(parent)):
            raise PipelineError("delivery delta target does not exist")
        if op == "remove":
            del parent[key]
        else:
            parent[key] = deepcopy(operation["value"])
    return result


class _DeliveryUnits:
    """Resolve registered transport references; literal JSON objects stay literal."""

    def __init__(self, root: Path, workflow: str, version: str):
        self.root, self.workflow = root, workflow
        self.packet, _ = _load(root, workflow, version)
        self.packet_digest = version
        self.provenance: list[dict[str, Any]] = []
        if self.packet.get("format") == "pipeline-assignment-delta-v2":
            delta = self.packet
            self.packet_digest = delta.get("packet_digest")
            self.packet, _ = _load(root, workflow, self.packet_digest)
            previous, _ = _load(root, workflow, delta.get("baseline_digest"))
            if (self.packet.get("format") != "pipeline-assignment-v2"
                    or previous.get("format") != "pipeline-assignment-v2"
                    or delta.get("project_root") != self.packet.get("project_root")
                    or not _same_owner(previous, self.packet)):
                raise PipelineError("delta baseline must belong to the same run, role and worker in this project_root")
            _baseline_order(previous, self.packet)
            rebuilt = _apply_patch(previous, delta.get("patch"))
            if canonical_bytes(rebuilt) != canonical_bytes(self.packet):
                raise PipelineError("delivery delta patch does not match its packet digest")
            self.provenance.append({"kind": "delta", "digest": version,
                                    "baseline_digest": delta["baseline_digest"], "packet_digest": self.packet_digest})
        if self.packet.get("format") not in {"pipeline-assignment-v1", "pipeline-assignment-v2"}:
            raise PipelineError("semantic delivery reader requires an assignment packet or a v2 delta")
        project_root = self.packet.get("project_root")
        if project_root != str(root.resolve()) and (project_root is not None or self.packet["format"] != "pipeline-assignment-v1"):
            raise PipelineError("delivery packet belongs to a different project_root")
        self.references = self.packet.get("references", {}) if self.packet["format"] == "pipeline-assignment-v2" else {}
        if not isinstance(self.references, dict):
            raise PipelineError("delivery references must be an object")
        for source, descriptor in self.references.items():
            if (not source.startswith("/assignment/") or not isinstance(descriptor, dict)
                    or _pointer_value(self.packet, source) != {"$delivery_ref": source}):
                raise PipelineError("delivery reference must identify its exact registered assignment slot")
            if descriptor.get("kind") == "local":
                if (set(descriptor) != {"kind", "pointer"} or not isinstance(descriptor["pointer"], str)
                        or not descriptor["pointer"].startswith("/assignment/")):
                    raise PipelineError("invalid packet-local delivery reference")
                _pointer_parts(descriptor["pointer"])
            elif descriptor.get("kind") == "resource":
                if (set(descriptor) != {"kind", "digest", "pointer"}
                        or source != "/assignment/context/qa_contract/definition" or descriptor["pointer"] != "/definition"
                        or not is_digest(descriptor["digest"])):
                    raise PipelineError("invalid QA resource delivery reference")
            else:
                raise PipelineError("unknown delivery reference kind")
        self.resources: dict[str, Any] = {}

    def _dereference(self, value: Any, pointer: str, stack: tuple[str, ...]) -> tuple[Any, str, bool]:
        descriptor = self.references.get(pointer)
        if descriptor is None:
            return value, pointer, False
        if pointer in stack:
            raise PipelineError("packet-local delivery reference cycle")
        provenance = {"source_pointer": pointer, **descriptor}
        if provenance not in self.provenance:
            self.provenance.append(provenance)
        if descriptor["kind"] == "local":
            return self.locate(descriptor["pointer"], stack + (pointer,))
        version = descriptor["digest"]
        if version not in self.resources:
            resource, _ = _load(self.root, self.workflow, version)
            qa = _pointer_value(self.packet, "/assignment/context/qa_contract")
            if (resource.get("format") != "pipeline-qa-definition-v1"
                    or any(resource.get(key) != self.packet.get(key) for key in ("project_root", "run_id", "feature"))
                    or qa.get("status") != "bound" or not isinstance(qa.get("binding"), dict)
                    or canonical_bytes(resource.get("binding")) != canonical_bytes(qa["binding"])
                    or "definition" not in resource):
                raise PipelineError("QA resource project/run/feature/contract binding does not match its assignment")
            self.resources[version] = resource
        return self.resources[version]["definition"], pointer, True

    def locate(self, pointer: str, stack: tuple[str, ...] = ()) -> tuple[Any, str, bool]:
        value, actual, external = self.packet, "", False
        for part in _pointer_parts(pointer):
            if not external:
                value, actual, external = self._dereference(value, actual, stack)
            value = _child_value(value, part)
            actual = _child_pointer(actual, part)
        return (value, actual, True) if external else self._dereference(value, actual, stack)

    def expand(self, value: Any, pointer: str, external: bool, stack: tuple[str, ...] = ()) -> Any:
        if external:
            return deepcopy(value)
        if pointer in self.references:
            if pointer in stack:
                raise PipelineError("packet-local delivery reference cycle")
            resolved, actual, external = self._dereference(value, pointer, stack)
            return self.expand(resolved, actual, external, stack + (pointer,))
        if isinstance(value, dict):
            return {key: self.expand(child, _child_pointer(pointer, key), False, stack) for key, child in value.items()}
        if isinstance(value, list):
            return [self.expand(child, _child_pointer(pointer, index), False, stack) for index, child in enumerate(value)]
        return deepcopy(value)


def _value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    return {dict: "object", list: "array", str: "string", int: "number", float: "number"}.get(type(value), "unknown")


_WORK_POINTER = "/assignment/context/required_finding_conditions"
_REWORK_PHASES = {"engineer": "engineering", "reviewer": "review", "documentation_finisher": "docs"}


def _required_work_roster(context: dict[str, Any], role: str) -> tuple[list[dict[str, Any]], str]:
    """Check the exact existing inventory; legacy fallback never invents evidence."""
    from .finding_contract import required_condition_roster
    phase = _REWORK_PHASES.get(role) if isinstance(role, str) else None
    if phase is None:
        raise PipelineError("work view is available only to Engineer, Review and Documentation Finisher")
    supplied = context.get("required_finding_conditions")
    convergence = context.get("convergence")
    if convergence is None:
        if "required_finding_conditions" in context and supplied == []:
            return [], "required_finding_conditions"
        raise PipelineError("complete rework is unavailable: obtain a current assignment with its required roster and convergence")
    if (not isinstance(convergence, dict) or not isinstance(convergence.get("open"), dict)
            or not isinstance(convergence.get("condition_status"), dict)):
        raise PipelineError("complete rework requires original open conditions and their independent results")
    for finding_id, finding in convergence["open"].items():
        if (not isinstance(finding, dict) or finding.get("id", finding_id) != finding_id
                or not isinstance(finding.get("conditions"), list) or not finding["conditions"]):
            raise PipelineError("complete rework cannot infer missing original finding conditions")
        statuses = convergence["condition_status"].get(finding_id)
        for condition in finding["conditions"]:
            result = statuses.get(condition.get("id")) if (isinstance(statuses, dict) and isinstance(condition, dict)
                      and isinstance(condition.get("id"), str)) else None
            if (not isinstance(result, dict) or not isinstance(result.get("status"), str)
                    or result["status"] not in {"resolved", "unresolved"}
                    or not isinstance(result.get("evidence"), str) or not result["evidence"].strip()):
                raise PipelineError("complete rework requires the latest independent status and non-empty evidence for every open finding condition")
    expected = required_condition_roster(convergence, phase)
    if "required_finding_conditions" not in context:
        return expected, "legacy_convergence"
    if canonical_bytes(supplied) != canonical_bytes(expected):
        raise PipelineError("required rework roster or pointers do not match the exact role-specific convergence inventory")
    return expected, "required_finding_conditions"


def _read_work(reader: _DeliveryUnits, version: str, pointer: str | None) -> dict[str, Any]:
    """Deliver complete current finding work, not the assignment's other obligations."""
    if pointer not in {None, _WORK_POINTER}:
        raise PipelineError("work view selects only /assignment/context/required_finding_conditions")
    assignment = reader.packet.get("assignment", {})
    context_value, actual, external = reader.locate("/assignment/context")
    if not isinstance(context_value, dict):
        raise PipelineError("complete rework requires an assignment context")
    # Resolve only finding input. QA resources and unrelated histories are not
    # needed to validate the roster or assemble the complete work presentation.
    context = {key: deepcopy(context_value[key]) for key in ("required_finding_conditions",) if key in context_value}
    if "convergence" in context_value:
        value, actual, external = reader.locate("/assignment/context/convergence")
        context["convergence"] = reader.expand(value, actual, external)
    roster, source = _required_work_roster(context, assignment.get("role"))
    findings: dict[str, dict[str, Any]] = {}
    for row in roster:
        finding_id = row["finding_id"]
        finding_pointer = _child_pointer("/assignment/context/convergence/open", finding_id)
        if finding_id not in findings:
            value, actual, external = reader.locate(finding_pointer)
            finding = reader.expand(value, actual, external)
            findings[finding_id] = {
                "finding_id": finding_id, "finding_pointer": finding_pointer,
                "finding": {key: deepcopy(item) for key, item in finding.items() if key != "conditions"},
                "conditions": [],
            }
        condition, actual, external = reader.locate(row["original_condition_pointer"])
        condition = reader.expand(condition, actual, external)
        result, actual, external = reader.locate(row["latest_independent_result_pointer"])
        result = reader.expand(result, actual, external)
        findings[finding_id]["conditions"].append({
            **deepcopy(row), "original_condition": condition, "latest_independent_result": result,
        })
    return {"format": "pipeline-delivery-unit-v1", "version": version,
            "packet_digest": reader.packet_digest, "pointer": _WORK_POINTER, "view": "work", "type": "object",
            "roster_source": source, "required_condition_count": len(roster),
            "work_complete": True, "unit_complete": False, "delivery_complete": False,
            "value": {"assignment": {key: deepcopy(assignment[key]) for key in
                ("id", "worker_id", "role", "task", "output_path") if key in assignment},
                "findings": list(findings.values())}, "provenance": reader.provenance}


_PAGED_VIEWS = {"bootstrap", "work-index", "work-item", "qa-index", "qa-assertion", "check-result", "check-context", "section"}
_QA_POINTER = "/assignment/context/qa_contract/definition"


def _qa_selection(reader: _DeliveryUnits, view: str, assertion_ids: list[str], identity_id=None) -> dict[str, Any]:
    from .qa_contract import expand_slice_contract, selected_contract, resolve_assertion_selection, QAContractError
    try:
        definition = expand_slice_contract(_expanded(reader, _QA_POINTER))
    except QAContractError as exc:
        raise PipelineError(str(exc)) from exc
    identities = definition["identities"]
    if view == "qa-index":
        prefix = [sys.executable, str(Path(__file__).resolve().parents[1] / "pipeline_state.py"),
                  "--root", str(reader.root), "--feature", reader.packet["feature"]]
        inventory = []
        for item in identities:
            entry = {"id": item["id"], "source": item["source"],
                     "assertion_ids": [row["id"] for row in item["assertions"]]}
            if reader.packet["assignment"].get("role") == "qa":
                entry["prepare"] = _read_handle([*prefix, "qa-prepare", "--assignment-id", reader.packet["assignment"]["id"],
                                                "--format", "text", "--assemble", "--identity-id", item["id"]], reader.root)
            else:
                entry["read"] = _read_handle([*prefix, "assignment-read", "--digest", reader.packet_digest,
                    "--view", "qa-assertion", "--format", "text", "--assemble", "--identity-id", item["id"]], reader.root)
            inventory.append(entry)
        return {"identities": inventory,
                "assertion_count": sum(len(item["assertions"]) for item in identities),
                "selection": "The ready handle selects its exact identity, not a required assessment batch. For a coherent subset, use repeated --assertion-id with the exact assertion_ids listed here; do not combine selectors or construct identity/assertion IDs. Every required identity remains in this index."}
    try:
        assertion_ids = resolve_assertion_selection(definition, assertion_ids, identity_id=identity_id)
    except QAContractError as exc:
        raise PipelineError(str(exc)) from exc
    return {**selected_contract(definition, assertion_ids),
            "method_id_rule": "Read each referenced full method definition in this response. Use its id for assessments and method reasons; reference keys are not semantic IDs."}


def share_work_evidence(value: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Exact text presentation only; reconstruct after collecting the entire selection."""
    shown, shared = deepcopy(value), False
    for finding_index, group in enumerate(shown["findings"]):
        finding = group["finding"]
        explanation = finding.get("text") if isinstance(finding, dict) else None
        seen = ({explanation: f"#/findings/{finding_index}/finding/text"}
                if isinstance(explanation, str) else {})
        for condition_index, row in enumerate(group["conditions"]):
            result = row["latest_independent_result"]
            evidence = result["evidence"]
            if not isinstance(evidence, str):
                continue
            if evidence in seen:
                result["evidence"] = {"same_exact_text_as": seen[evidence]}
                shared = True
            else:
                seen[evidence] = (f"#/findings/{finding_index}/conditions/{condition_index}"
                                  "/latest_independent_result/evidence")
    return shown, shared


def _expanded(reader: _DeliveryUnits, pointer: str) -> Any:
    value, actual, external = reader.locate(pointer)
    return reader.expand(value, actual, external)


def _bootstrap(reader: _DeliveryUnits) -> dict[str, Any]:
    """Group complete startup metadata; retain explicit locators for every body."""
    assignment = reader.packet["assignment"]
    body = {key: _expanded(reader, _child_pointer("/assignment", key))
            for key in assignment if key != "context"}
    context = assignment.get("context", {})
    if not isinstance(context, dict):
        raise PipelineError("assignment startup requires an object context")
    deferred = {"convergence", "technical_decisions", "verification_failure", "diagnostic_checks",
                "machine_checks", "qa_previous_observations", "required_finding_conditions"}
    metadata, sources = {}, []
    for key, value in context.items():
        pointer = _child_pointer("/assignment/context", key)
        if key == "qa_contract" and isinstance(value, dict):
            metadata[key] = {field: _expanded(reader, _child_pointer(pointer, field))
                             for field in value if field != "definition"}
            if "definition" in value:
                sources.append({"pointer": pointer + "/definition", "view": "section"})
        elif key in deferred:
            # Empty values convey their complete absence without a navigation call.
            if value in ([], {}):
                metadata[key] = deepcopy(value)
            else:
                sources.append({"pointer": pointer, "view": "section"})
            if key == "machine_checks" and isinstance(value, dict):
                metadata[key] = {field: deepcopy(item) for field, item in value.items() if field != "checks"}
        else:
            metadata[key] = _expanded(reader, pointer)
    body["context"] = metadata
    result = {"assignment": body, "sources": sources,
              "selected_inputs": deepcopy(reader.packet.get("selected_inputs", []))}
    if "role_instructions" in reader.packet:
        result["role_instructions"] = deepcopy(reader.packet["role_instructions"])
    if assignment.get("role") in _REWORK_PHASES and (
            context.get("required_finding_conditions") or context.get("convergence", {}).get("open")):
        result["required_work"] = {"view": "work-index", "pointer": _WORK_POINTER}
    return result


def _selected_work(reader: _DeliveryUnits, version: str, view: str,
                   finding_id: str | None, condition_id: str | None,
                   baseline: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
    work = _read_work(reader, version, None)
    groups = work["value"]["findings"]
    roster = [{key: row[key] for key in ("finding_id", "condition_id", "original_condition_pointer",
                                       "latest_independent_result_pointer")}
              for group in groups for row in group["conditions"]]
    details = {"roster_digest": hashlib.sha256(canonical_bytes(roster)).hexdigest(),
               "required_condition_count": len(roster), "roster_source": work["roster_source"],
               "work_complete": False}
    if view == "work-index":
        return {"assignment": work["value"]["assignment"], "roster": roster}, details
    if not isinstance(finding_id, str) or not finding_id:
        raise PipelineError("work-item requires an exact finding-id from the current work-index")
    selected = [deepcopy(group) for group in groups if group["finding_id"] == finding_id]
    if not selected:
        raise PipelineError("finding-id is not in the exact current required roster")
    group = selected[0]
    if condition_id is not None:
        group["conditions"] = [row for row in group["conditions"] if row["condition_id"] == condition_id]
        if not group["conditions"]:
            raise PipelineError("condition-id is not in the exact current role-specific required roster")
    details["selected_condition_count"] = len(group["conditions"])
    body = {"assignment": work["value"]["assignment"], "findings": selected}
    if baseline is not None:
        retained = _DeliveryUnits(reader.root, reader.workflow, baseline)
        if retained.packet_digest != baseline or not _same_owner(retained.packet, reader.packet):
            raise PipelineError("retained baseline must be a full packet of the same run, role and worker")
        _baseline_order(retained.packet, reader.packet)
        # Validate complete accessible baseline material, not just an old digest.
        _expanded(retained, "/assignment")
        prior_context = retained.packet["assignment"].get("context", {})
        current_context = reader.packet["assignment"].get("context", {})
        prior_binding = prior_context.get("qa_contract", {}).get("binding")
        current_binding = current_context.get("qa_contract", {}).get("binding")
        if canonical_bytes(prior_binding) != canonical_bytes(current_binding):
            raise PipelineError("retained baseline authority/QA binding changed; read full current originals")
        refs = []
        originals = [("/findings/0/finding", group["finding_pointer"], group["finding"], True)]
        originals.extend((f"/findings/0/conditions/{index}/original_condition", row["original_condition_pointer"],
                          row["original_condition"], False) for index, row in enumerate(group["conditions"]))
        for source, target, current, finding_metadata in originals:
            try:
                previous = _expanded(retained, target)
            except PipelineError:
                continue  # New or reindexed original: deliver current bytes in full.
            if finding_metadata and isinstance(previous, dict):
                previous = {key: value for key, value in previous.items() if key != "conditions"}
            if canonical_bytes(previous) != canonical_bytes(current):
                continue
            parts = _pointer_parts(source)
            parent = body
            for part in parts[:-1]:
                parent = _child_value(parent, part)
            parent[parts[-1]] = None
            refs.append({"source_pointer": source, "packet_digest": baseline, "pointer": target,
                         **({"omit_fields": ["conditions"]} if finding_metadata else {})})
        if refs:
            body["retained_originals"] = refs
            details["baseline_digest"] = baseline
    return body, details


def _semantic_page(body: Any, metadata: dict[str, Any], continuation: str | None, limit: int,
                   *, raw_text: bool = False, offset: int = 0) -> dict[str, Any]:
    """Page serialized text, including inside strings, with immutable reconstruction bindings."""
    text = body if raw_text else json.dumps(body, ensure_ascii=False, indent=2)
    if raw_text:
        metadata = {**metadata, "serialization_kind": "text"}
    content_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    binding = hashlib.sha256(canonical_bytes({**metadata, "content_digest": content_digest})).hexdigest()
    if continuation is not None:
        try:
            token = json.loads(base64.b64decode(continuation.encode("ascii"), altchars=b"-_", validate=True))
        except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
            raise PipelineError("invalid delivery continuation; restart this exact selection") from exc
        if (not isinstance(token, dict) or set(token) != {"binding", "offset"}
                or token["binding"] != binding or type(token["offset"]) is not int
                or not 0 < token["offset"] < len(text)):
            raise PipelineError("continuation does not match this exact packet, selection, baseline and content")
        offset = token["offset"]
    page = text_page(text, metadata["version"], offset, limit)
    next_token = None
    if page["next_offset"] is not None:
        next_token = base64.urlsafe_b64encode(canonical_bytes({"binding": binding, "offset": page["next_offset"]})).decode("ascii")
    return {**metadata, **page, "content_digest": content_digest,
            "page_digest": hashlib.sha256(page["text"].encode("utf-8")).hexdigest(),
            "continuation": next_token, "unit_complete": False, "delivery_complete": False,
            "serialization": ("Exact source text fragment" if raw_text else "JSON text fragment") +
                " in the machine envelope text field; use --format json and --assemble for exact reconstruction; complete marks selection end only"}


def assemble_delivery_pages(read_page: Callable[[str | None], dict[str, Any]]) -> dict[str, Any]:
    """Consume one exact selection, checking every fragment before decoding it.

    The callback transports decoded JSON envelopes, never human stdout. No
    stripping or newline normalization is allowed: whitespace belongs to the
    content digest. This read does not acknowledge any other selection or work.
    """
    variable = {"text", "offset", "end_offset", "complete", "next_offset", "page_digest", "continuation"}
    first, fixed, parts, tokens = None, None, [], set()
    continuation, offset = None, 0
    while True:
        try:
            page = read_page(continuation)
        except StopIteration as exc:
            raise PipelineError("assembly ended before its required continuation") from exc
        if not isinstance(page, dict) or page.get("format") not in {"pipeline-delivery-page-v1", "pipeline-source-page-v1"}:
            raise PipelineError("assembly requires a semantic JSON page envelope")
        metadata = {key: value for key, value in page.items() if key not in variable}
        if first is None:
            first, fixed = page, metadata
            digest_keys = ("content_digest", "version") + (("packet_digest",) if page["format"] == "pipeline-delivery-page-v1" else ())
            if any(not is_digest(page.get(key)) for key in digest_keys):
                raise PipelineError("assembly requires exact content and packet digests")
        elif metadata != fixed:
            raise PipelineError("assembly page binding or selection changed")
        text, end, total = page.get("text"), page.get("end_offset"), page.get("total_characters")
        if (type(page.get("offset")) is not int or page["offset"] != offset
                or type(end) is not int or type(total) is not int or total < 0
                or not isinstance(text, str) or end - offset != len(text)
                or not offset <= end <= total or (end == offset and total != 0)):
            raise PipelineError("assembly requires contiguous complete fragments with exact lengths")
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != page.get("page_digest"):
            raise PipelineError("assembly page digest does not match exact text")
        complete, token = page.get("complete"), page.get("continuation")
        if type(complete) is not bool or complete != (end == total):
            raise PipelineError("assembly completion does not match selection length")
        if complete:
            if token is not None or page.get("next_offset") is not None:
                raise PipelineError("completed assembly must not contain a continuation")
        elif (not isinstance(token, str) or not token or token in tokens
              or type(page.get("next_offset")) is not int or page["next_offset"] != end):
            raise PipelineError("assembly requires a progressing bound continuation")
        parts.append(text)
        offset = end
        if complete:
            break
        tokens.add(token)
        continuation = token
    text = "".join(parts)
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != first["content_digest"]:
        raise PipelineError("assembly content digest does not match exact selection")
    if first.get("serialization_kind") == "text":
        value = text
    else:
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise PipelineError(f"assembled selection is not valid JSON: {exc}") from exc
    return {**fixed, "format": "pipeline-source-unit-v1" if first["format"] == "pipeline-source-page-v1" else "pipeline-delivery-unit-v1", "value": value,
            "assembled_pages": len(parts), "selection_complete": True,
            "unit_complete": True, "delivery_complete": False,
            "serialization": "Decoded exact selection; no global work or delivery read credit"}


def read_delivery_unit(root: Path, workflow: str, digest: str, pointer: str | None = None,
                       view: str = "index", *, finding_id: str | None = None,
                       condition_id: str | None = None, baseline: str | None = None,
                       assertion_ids: list[str] | None = None, identity_id: str | None = None,
                       continuation: str | None = None, limit: int = 8192) -> dict[str, Any]:
    """Read one decoded logical unit. Its completeness is never a global read receipt."""
    if view not in {"index", "unit", "value", "work"} | _PAGED_VIEWS:
        raise PipelineError("unknown delivery unit view")
    if view not in _PAGED_VIEWS and (continuation is not None or limit != 8192):
        raise PipelineError("continuation and limit require a paged semantic view")
    if view != "work-item" and any(item is not None for item in (finding_id, condition_id, baseline)):
        raise PipelineError("finding-id, condition-id and retained baseline require work-item")
    if (assertion_ids or identity_id is not None) and view != "qa-assertion":
        raise PipelineError("assertion-id and identity-id require the qa-assertion view")
    reader = _DeliveryUnits(root, workflow, digest)
    if view in _PAGED_VIEWS:
        fixed_pointer = (_QA_POINTER if view in {"qa-index", "qa-assertion"} else
                         _WORK_POINTER if view in {"work-index", "work-item"} else "/assignment")
        if view != "section" and pointer not in {None, fixed_pointer}:
            raise PipelineError("semantic view has a fixed pointer; use section for an arbitrary exact pointer")
        if pointer is None:
            pointer = fixed_pointer
        details = {}
        if view in {"bootstrap", "check-result", "check-context"}:
            body = (_bootstrap(reader) if view != "check-context" else {
                "assignment": {key: deepcopy(reader.packet["assignment"][key])
                               for key in ("id", "worker_id", "role", "output_path")
                               if key in reader.packet["assignment"]},
                "generation": reader.packet["generation"],
            })
            if view in {"check-result", "check-context"}:
                context = reader.packet["assignment"].get("context", {})
                body["check_context"] = {key: _expanded(reader, _child_pointer("/assignment/context", key))
                                         for key in ("diagnostic_checks", "machine_checks") if key in context}
                if not body["check_context"]:
                    raise PipelineError("check-result/check-context requires committed diagnostic or machine check context")
        elif view in {"qa-index", "qa-assertion"}:
            body = _qa_selection(reader, view, assertion_ids or [], identity_id)
            if assertion_ids:
                details["assertion_ids"] = list(assertion_ids)
            if identity_id is not None:
                details["identity_id"] = identity_id
        elif view in {"work-index", "work-item"}:
            body, details = _selected_work(reader, digest, view, finding_id, condition_id, baseline)
            if view == "work-item":
                body, shared = share_work_evidence(body)
                if shared:
                    details["text_rendering"] = ("After concatenating all selection pages, evidence same_exact_text_as "
                        "fragments identify literal strings in that reconstructed body; expand exactly, never infer evidence")
        else:
            body = _expanded(reader, pointer)
        metadata = {"format": "pipeline-delivery-page-v1", "version": digest, "packet_digest": reader.packet_digest,
                    "view": view, "pointer": pointer, **details,
                    **({"finding_id": finding_id} if finding_id is not None else {}),
                    **({"condition_id": condition_id} if condition_id is not None else {}),
                    **({"baseline_digest": baseline} if baseline is not None else {})}
        return _semantic_page(body, metadata, continuation, limit)
    if view == "work":
        return _read_work(reader, digest, pointer)
    pointer = "/assignment" if pointer is None else pointer
    value, actual, external = reader.locate(pointer)
    response: dict[str, Any] = {"format": "pipeline-delivery-unit-v1", "version": digest,
        "packet_digest": reader.packet_digest, "pointer": pointer, "view": view, "type": _value_type(value),
        "unit_complete": view == "value", "delivery_complete": False}
    if view == "value" or (view == "unit" and not isinstance(value, (dict, list))):
        response["value"] = reader.expand(value, actual, external)
        response["unit_complete"] = True
    else:
        children = value.items() if isinstance(value, dict) else enumerate(value) if isinstance(value, list) else []
        response["children"] = []
        response["unit_complete"] = view == "unit"
        for key, child in children:
            logical = _child_pointer(pointer, key)
            resolved, _, _ = reader.locate(logical)
            item = {"selector": str(key), "pointer": logical, "type": _value_type(resolved)}
            if isinstance(resolved, dict) and isinstance(resolved.get("id"), (str, int)):
                item["id"] = resolved["id"]
            if view == "unit":
                if isinstance(resolved, dict):
                    for identity_key in ("finding_id", "condition_id"):
                        if isinstance(resolved.get(identity_key), str):
                            item[identity_key] = resolved[identity_key]
                source = _child_pointer(actual, key)
                reference = None if external else reader.references.get(source)
                if reference is not None:
                    # Keep exact duplicate text at its existing target instead of
                    # replaying it whenever a condition/status container is read.
                    item["reference"] = {"source_pointer": source, **deepcopy(reference)}
                elif not isinstance(resolved, (dict, list)):
                    item["value"] = deepcopy(resolved)
                if "value" not in item:
                    response["unit_complete"] = False
            response["children"].append(item)
    response["provenance"] = reader.provenance
    return response


def _verification_exit_criteria_locator(
    root: Path, view: dict[str, Any], assignment: dict[str, Any],
) -> dict[str, Any] | None:
    """Locate an already-bound slice section without curating its meaning."""
    try:
        workflow = normalize_literal_path(view["workflow_path"])
        state_path = safe_path(root, f"{workflow}/pipeline-state.json", "pipeline state", strict=True)
        state = json.loads(state_path.read_bytes().decode("utf-8"))
        active = state.get("active_assignment")
        assignment_context = assignment.get("context")
        active_context = active.get("capsule", {}).get("context") if isinstance(active, dict) else None
        selected = assignment_context.get("current_slice") if isinstance(assignment_context, dict) else None
        if (
            not isinstance(active, dict)
            or active.get("id") != assignment.get("id")
            or not isinstance(selected, dict)
            or canonical_bytes(selected) != canonical_bytes(active_context.get("current_slice"))
        ):
            return None
        slice_id = selected.get("id")
        plan = state.get("authority", {}).get("items", {}).get("plan")
        plan_path = normalize_literal_path(plan["path"])
        version = plan.get("sha256")
        if (
            not isinstance(slice_id, str)
            or not is_digest(version)
            or not any(matches(plan_path, rule) for rule in assignment.get("access", {}).get("read", []))
        ):
            return None
        payload = safe_path(root, plan_path, "approved plan", strict=True).read_bytes()
        if hashlib.sha256(payload).hexdigest() != version:
            return None
        text = payload.decode("utf-8")
    except (AttributeError, KeyError, OSError, TypeError, UnicodeError, json.JSONDecodeError, PipelineError):
        return None

    locator: dict[str, Any] = {
        "path": plan_path,
        "version": version,
        "total_characters": len(text),
    }
    slice_matches = list(re.finditer(rf"(?m)^## Slice {re.escape(slice_id)}\r?$", text))
    if len(slice_matches) != 1:
        return locator
    slice_end = next(
        (match.start() for match in re.compile(r"(?m)^## Slice \S").finditer(text, slice_matches[0].end())),
        len(text),
    )
    section_matches = list(re.compile(r"(?m)^### Verification and Exit Criteria\r?$").finditer(
        text, slice_matches[0].end(), slice_end,
    ))
    if len(section_matches) != 1:
        return locator
    section = section_matches[0]
    section_end = next(
        (match.start() for match in re.compile(r"(?m)^### \S").finditer(text, section.end(), slice_end)),
        slice_end,
    )
    locator["section"] = {
        "heading": "Verification and Exit Criteria",
        "start_offset": section.start(),
        "end_offset": section_end,
    }
    return locator


def _dispatch_descriptor(root: Path, view: dict[str, Any], packet: dict[str, Any],
                         saved: dict[str, Any], response: dict[str, Any],
                         mode: str, baseline: str | None) -> dict[str, Any]:
    """Forwardable routing metadata; semantic work stays in the immutable packet.

    The exact terminal output is authorized by the assignment, separately from
    product scope. This descriptor creates no host lease or controller command
    grant; physical ownership and return correlation remain caller-bound.
    """
    assignment = packet["assignment"]
    launcher = Path(__file__).resolve().parents[1] / "pipeline_state.py"
    if not launcher.is_file():
        raise PipelineError("dispatch launcher must exist inside the running bundle")
    packet_path = safe_path(root, saved["path"], "assignment packet", strict=True)
    input_path = safe_path(root, response["path"], "assignment delivery", strict=True)
    output_path = safe_path(root, assignment["output_path"], "assigned artifact")
    reference = {"packet_digest": saved["digest"]}
    reader_argv = [sys.executable, str(launcher), "--root", packet["project_root"],
                   "--feature", view["feature"], "assignment-read", "--digest", saved["digest"], "--format", "json"]
    assembled = [*reader_argv[:-1], "text", "--assemble"]
    context = assignment.get("context", {})
    roster = context.get("required_finding_conditions") if isinstance(context, dict) else None
    convergence = context.get("convergence") if isinstance(context, dict) else None
    has_rework = assignment.get("role") in _REWORK_PHASES and (
        bool(roster) or (isinstance(convergence, dict) and bool(convergence.get("open"))))
    descriptor = {
        "format": "pipeline-dispatch-v1",
        "run_id": view["run_id"], "feature": view["feature"],
        "generation": view["generation"], "assignment_id": assignment["id"],
        "worker_id": assignment["worker_id"], "role": assignment["role"],
        "project_root": packet["project_root"], "cwd": packet["project_root"],
        "launcher_argv": [sys.executable, str(launcher)],
        "controller_args": ["--root", packet["project_root"], "--feature", view["feature"], "--brief"],
        "input": {"mode": mode, "path": str(input_path), "digest": response["digest"],
                  "packet_path": str(packet_path), "packet_digest": saved["digest"],
                  **({"baseline_digest": baseline} if baseline is not None else {})},
        "reader": {"command": "assignment-read", "packet_format": packet["format"],
                   "default_view": "bootstrap",
                   "format": "text",
                   "bootstrap_argv": [*assembled, "--view", "bootstrap"],
                   "bootstrap": _read_handle([*assembled, "--view", "bootstrap"], root),
                   **({"work_index_argv": [*assembled, "--view", "work-index"],
                       "work_item_argv_prefix": [*assembled, "--view", "work-item", "--finding-id"],
                       "work_scope": "index is navigation only; consume every exact required pair through work-item, retaining original context and latest independent results"}
                      if has_rework else {}),
                   "section_argv_prefix": [*assembled, "--view", "section", "--pointer"],
                   "source_argv_prefix": [sys.executable, str(launcher), "--root", packet["project_root"],
                       "--feature", view["feature"], "file-read", "--format", "text", "--assemble", "--path"],
                   **({"qa_index_argv": [*assembled, "--view", "qa-index"],
                       "qa_index": _read_handle([*assembled, "--view", "qa-index"], root),
                       "qa_assertion_argv_prefix": [*assembled, "--view", "qa-assertion", "--assertion-id"],
                       **({"qa_prepare_argv_prefix": [sys.executable, str(launcher), "--root", packet["project_root"],
                           "--feature", view["feature"], "qa-prepare", "--assignment-id", assignment["id"],
                           "--format", "text", "--assemble", "--assertion-id"]} if assignment.get("role") == "qa" else {}),
                       "qa_navigation": "Select actual case groups. QA uses qa-prepare for complete obligations, alternatives, producers and editable input in one response; Engineer/Review read exact obligations through qa-assertion."}
                      if isinstance(context.get("qa_contract"), dict) and context["qa_contract"].get("status") == "bound" else {}),
                   "advanced": {"unit_argv_prefix": [*reader_argv, "--view", "unit", "--pointer"],
                       "index_argv": [*reader_argv, "--view", "index"],
                       "value_argv_prefix": [*reader_argv, "--view", "value", "--pointer"],
                       **({"work_argv": [*reader_argv, "--view", "work"]} if has_rework else {}),
                       "paged_argv": reader_argv,
                       "usage": "Legacy/debug readers and exact page continuation; normal semantic readers already assemble. --output saves only the selected body and grants no read credit."},
                   "selector_argument": "append one exact child pointer from a structural unit or logical index",
                   "navigation": "execute bootstrap_argv as supplied; identity/access/schema/checks/current slice are grouped; follow exact source locators and required work roster; lost retention requires full reads without --baseline",
                   "required_resources": [{"pointer": pointer, "digest": item["digest"]}
                       for pointer, item in packet.get("references", {}).items() if item["kind"] == "resource"],
                   "completeness": "full delivery requires the manifest and all referenced operative values; index, digest and unit reads are not a global read receipt",
                   "delta_rule": "apply every RFC 6902 operation including removals only to the exact retained same-worker baseline; logical reads select the full target packet"},
        "scope": {**reference, "pointer": "/assignment/access"},
        "output": {"path": str(output_path), "relative_path": assignment["output_path"],
                   "write_authority": "issued_exact_terminal_artifact",
                   **({"schema": {**reference, "pointer": "/assignment/artifact_schema"}}
                      if "artifact_schema" in assignment else {})},
        "allowed_action": "execute_issued_assignment",
        "stop_boundary": "terminal_artifact_or_required_control_pause",
        "controller_mutation_authority": "requires_separate_bounded_grant",
    }
    if "role_instructions" in packet:
        descriptor["role_instructions"] = deepcopy(packet["role_instructions"])
        descriptor["role_instructions"]["read_argv"] = [sys.executable, str(launcher), "--root", packet["project_root"],
            "--feature", view["feature"], "file-read", "--instruction", assignment["role"], "--format", "text", "--assemble",
            *(["--section", descriptor["role_instructions"]["section"]] if "section" in descriptor["role_instructions"] else [])]
        descriptor["role_instructions"]["exec_command"] = host_read_command(descriptor["role_instructions"]["read_argv"], root)
    return descriptor


def export_assignment(root: Path, view: dict[str, Any], baseline: str | None = None,
                      inputs: list[str] | None = None) -> dict[str, Any]:
    assignment = view.get("active_assignment")
    if assignment is None or view["next_action"].get("command") != "complete":
        raise PipelineError("assignment export requires a live active assignment with no recovery boundary")
    project_root = str(root.resolve())
    if "project_root" in view and (
        not Path(view["project_root"]).is_absolute()
        or Path(view["project_root"]).resolve() != root.resolve()
    ):
        raise PipelineError("delivery root must match the controller-bound project_root")
    selected = []
    for relative in dict.fromkeys(inputs or []):
        relative = normalize_literal_path(relative)
        if not any(matches(relative, rule) for rule in assignment["access"]["read"]):
            raise PipelineError("selected input is outside the active assignment read access")
        target = safe_path(root, relative, "selected input", strict=True)
        try:
            payload = target.read_bytes()
            selected.append({"path": relative, "version": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)})
        except OSError as exc:
            raise PipelineError(f"cannot inspect selected input: {exc}") from exc
    packet = {"format": "pipeline-assignment-v2", "run_id": view["run_id"], "feature": view["feature"],
              "project_root": project_root,
              "generation": view["generation"], "assignment": deepcopy(assignment), "selected_inputs": selected,
              "references": {}}
    instructions = _role_instructions(assignment.get("role"))
    if instructions is not None:
        packet["role_instructions"] = instructions
    workflow = view["workflow_path"]
    previous = None
    fallback = None
    if baseline is not None:
        previous, _ = _load(root, workflow, baseline)
        legacy = previous.get("format") == "pipeline-assignment-v1"
        if (previous.get("format") not in {"pipeline-assignment-v1", "pipeline-assignment-v2"}
                or not _same_owner(previous, packet, legacy=legacy)):
            raise PipelineError("delta baseline must belong to the same run, role and worker in this project_root")
        _baseline_order(previous, packet)
        if legacy:
            fallback = {"reason": "legacy_packet_requires_full_v2", "baseline_digest": baseline,
                        "baseline_format": previous["format"]}
        else:
            # A retained digest alone is not sufficient if its referenced material is corrupt.
            read_delivery_unit(root, workflow, baseline, "/assignment", "value")
    resources = _transport_assignment(root, workflow, packet)
    saved = _save(root, workflow, packet)
    if baseline is None or fallback is not None:
        response = saved
        mode = "full"
    else:
        response = _save(root, workflow, {"format": "pipeline-assignment-delta-v2", "baseline_digest": baseline,
            "packet_digest": saved["digest"], "project_root": project_root,
            "patch": json_patch(previous, packet)})
        mode = "delta"
    source_bytes = sum(item["bytes"] for item in selected)
    context = assignment.get("context", {})
    sections = [
        {"name": key, "pointer": _child_pointer("/assignment/context", key),
         "bytes": len(canonical_bytes(value))}
        for key, value in context.items()
    ] if isinstance(context, dict) else []
    decisions = context.get("technical_decisions", []) if isinstance(context, dict) else []
    journal_index = [
        {"id": item.get("id"), "pointer": f"/assignment/context/technical_decisions/{index}"}
        for index, item in enumerate(decisions) if isinstance(item, dict)
    ] if isinstance(decisions, list) else []
    working_set = {"packet_bytes": saved["bytes"], "transport_bytes": response["bytes"],
        "selected_source_bytes": source_bytes, "selected_source_count": len(selected),
        "required_resource_bytes": sum(item["bytes"] for item in resources),
        "required_resources": resources,
        "estimated_tokens": (saved["bytes"] + source_bytes + sum(item["bytes"] for item in resources) + 3) // 4,
        "measurement": "UTF-8 bytes/4 estimate; excludes conversation, tools and system context",
        "context_sections": sections, "technical_decision_index": journal_index}
    locator = _verification_exit_criteria_locator(root, view, assignment)
    if locator is not None:
        working_set["verification_exit_criteria"] = locator
    dispatch = _dispatch_descriptor(root, view, packet, saved, response, mode, baseline if mode == "delta" else None)
    return {"mode": mode, "packet_digest": saved["digest"], "response_digest": response["digest"],
            "path": response["path"], "characters": response["characters"], "assignment_id": assignment["id"],
            "worker_id": assignment["worker_id"], "project_root": project_root,
            **({"role_instructions": instructions} if instructions is not None else {}),
            "generation": view["generation"], "delivery_complete": False,
            **({"fallback": fallback} if fallback is not None else {}),
            "working_set": working_set, "dispatch": dispatch}


def text_page(text: str, version: str, offset: int = 0, limit: int = 8192) -> dict[str, Any]:
    if type(offset) is not int or offset < 0 or offset > len(text):
        raise PipelineError("offset must be between zero and the text length")
    if type(limit) is not int or not 1 <= limit <= 16384:
        raise PipelineError("limit must be between 1 and 16384 Unicode characters")
    end = min(offset + limit, len(text))
    return {"version": version, "offset": offset, "end_offset": end, "total_characters": len(text),
            "text": text[offset:end], "complete": end == len(text), "next_offset": None if end == len(text) else end}


def read_delivery(root: Path, workflow: str, version: str, offset: int = 0, limit: int = 8192,
                  pointer: str | None = None) -> dict[str, Any]:
    value, text = _load(root, workflow, version)
    if pointer is not None:
        if pointer and not pointer.startswith("/"):
            raise PipelineError("section pointer must be an empty or slash-prefixed JSON pointer")
        try:
            for part in pointer[1:].split("/") if pointer else []:
                # RFC 6901 escapes are exact; reject ambiguous spellings.
                if "~" in part.replace("~1", "").replace("~0", ""):
                    raise ValueError("invalid pointer escape")
                part = part.replace("~1", "/").replace("~0", "~")
                if isinstance(value, list):
                    if not part.isdigit() or (len(part) > 1 and part.startswith("0")):
                        raise ValueError("invalid array index")
                    value = value[int(part)]
                else:
                    value = value[part]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise PipelineError("section pointer does not identify a value") from exc
        text = canonical_bytes(value).decode("utf-8")
    return {"pointer": pointer, **text_page(text, version, offset, limit)}


def _instruction_path(instruction: str, relative: str | None) -> Path:
    """Read only the selected installed entry and its explicit local Markdown links."""
    bundle = Path(__file__).resolve().parents[4]
    if instruction == "director":
        entry = bundle / "skills/gamedev-pipeline/SKILL.md"
    elif instruction in ROLES.values():
        entry = Path(_role_instructions(instruction)["path"])
    elif re.fullmatch(r"gamedev-[a-z0-9-]+", instruction or ""):
        entry = bundle / "skills" / instruction / "SKILL.md"
    else:
        raise PipelineError("instruction must name an existing bundle role or exact gamedev-* skill")
    entry = safe_path(bundle, entry, "instruction entry", strict=True)
    target = entry if relative is None else safe_path(bundle,
        Path(relative) if Path(relative).is_absolute() else entry.parent / relative,
        "instruction source", strict=True)
    if target.suffix.lower() != ".md":
        raise PipelineError("instruction reading is limited to explicitly linked bundle Markdown")
    pending, visited = [entry], set()
    while pending:
        current = pending.pop()
        if current == target:
            return target
        if current in visited:
            continue
        visited.add(current)
        try:
            text = current.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise PipelineError(f"cannot read instruction link source: {exc}") from exc
        for locator in re.findall(r"\]\(([^)]+)\)", text):
            locator = locator.strip().strip("<>")
            try:
                parsed = urlsplit(locator)
            except ValueError:
                continue
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            path = (current.parent / unquote(parsed.path)).resolve()
            if not path.is_relative_to(bundle) or path.suffix.lower() != ".md" or not path.is_file():
                continue
            pending.append(safe_path(bundle, path, "linked instruction", strict=True))
    raise PipelineError("instruction source is not the selected entry or one of its explicit bundle Markdown links")


def _markdown_prose(text):
    fence = None
    for number, row in enumerate(text.splitlines(keepends=True), 1):
        marker = re.match(r"^[ \t]{0,3}(`{3,}|~{3,})([^\r\n]*)", row)
        if marker:
            token = (marker.group(1)[0], len(marker.group(1)))
            if fence is None:
                fence = token
            elif token[0] == fence[0] and token[1] >= fence[1] and not marker.group(2).strip():
                fence = None
            continue
        if fence is None:
            yield number, row


def _markdown_headings(text):
    headings = []
    for number, row in _markdown_prose(text):
        match = re.match(r"^(#{1,6})[ \t]+([^\r\n]*)", row.lstrip("\ufeff"))
        if match:
            title = re.sub(r"[ \t]+#+[ \t]*$", "", match.group(2)).strip()
            headings.append((number, len(match.group(1)), title))
    return headings


def _instruction_link_reads(root, feature, instruction, current, selected):
    """Resolve only actual selected Markdown links; no policy or instruction index."""
    prefix = [sys.executable, str(Path(__file__).resolve().parents[1] / "pipeline_state.py"),
              "--root", str(root), "--feature", feature, "file-read", "--instruction", instruction,
              "--format", "text", "--assemble"]
    reads, known = [], {}
    for _, line in _markdown_prose(selected):
        for label, href in re.findall(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)", line):
            link = {"label": label, "href": href}
            try:
                parsed = urlsplit(href.strip().strip("<>"))
                if parsed.scheme or parsed.netloc or parsed.query:
                    continue
                target = _instruction_path(instruction, str((current.parent / unquote(parsed.path)).resolve()) if parsed.path else str(current))
                raw = target.read_bytes()
                text, version = raw.decode("utf-8"), hashlib.sha256(raw).hexdigest()
                first, last = 1, max(1, len(text.splitlines()))
                if parsed.fragment:
                    # Canonical bundle ATX anchors. Ambiguity or an unsupported
                    # anchor is explicit; never fall back to the whole manual.
                    anchor = unquote(parsed.fragment)
                    headings = _markdown_headings(text)
                    matching = [row for row in headings if re.sub(r"[^\w\- ]", "", row[2].lower()).replace(" ", "-") == anchor]
                    if len(matching) != 1:
                        raise PipelineError("linked anchor must identify exactly one current heading")
                    first, level, _ = matching[0]
                    last = next((number - 1 for number, depth, _ in headings if number > first and depth <= level), last)
                key = (str(target), version, first, last)
                if key in known:
                    if link not in known[key]["links"]:
                        known[key]["links"].append(link)
                    continue
                row = {"links": [link], "source": {"path": str(target), "sha256": version, "start_line": first, "end_line": last},
                       "exec_command": host_read_command([*prefix, "--path", str(target), "--version", version,
                                                           "--lines", f"{first}:{last}"], root)}
                known[key] = row
                reads.append(row)
            except (PipelineError, OSError, UnicodeError, ValueError) as exc:
                reads.append({"links": [link], "error": str(exc)})
    return reads


def _source_selection(text: str, section: str | None, lines: tuple[int, int] | None) -> tuple[str, int, int]:
    rows = text.splitlines(keepends=True)
    if not rows:
        rows = [""]
    if section is not None and lines is not None:
        raise PipelineError("source section and line range are mutually exclusive")
    first, last = 1, len(rows)
    if lines is not None:
        first, last = lines
        if type(first) is not int or type(last) is not int or not 1 <= first <= last <= len(rows):
            raise PipelineError(f"source lines must be an inclusive range within 1:{len(rows)}")
    elif section is not None:
        wanted = re.sub(r"^#{1,6}[ \t]+", "", section).strip()
        headings = _markdown_headings(text)
        matches_found = [item for item in headings if item[2] == wanted]
        if len(matches_found) != 1:
            raise PipelineError("source heading must match exactly once; use --lines for duplicates (matching lines: " +
                                ", ".join(str(item[0]) for item in matches_found) + ")")
        first, level, _ = matches_found[0]
        last = next((number - 1 for number, depth, _ in headings if number > first and depth <= level), len(rows))
    return "".join(rows[first - 1:last]), first, last


def read_file(root: Path, view: dict[str, Any] | None, relative: str | None, *, version: str | None = None,
              offset: int = 0, limit: int = 8192, continuation: str | None = None,
              section: str | None = None, lines: tuple[int, int] | None = None,
              instruction: str | None = None, feature: str | None = None) -> dict[str, Any]:
    assignment = None
    if instruction is not None:
        target = _instruction_path(instruction, relative)
        relative = str(target)
    else:
        assignment = (view or {}).get("active_assignment")
        if assignment is None or view["next_action"].get("command") != "complete":
            raise PipelineError("file read requires a live active assignment with no recovery boundary")
        relative = normalize_literal_path(relative)
        if not any(matches(relative, rule) for rule in assignment["access"]["read"]):
            raise PipelineError("file is outside the active assignment read access")
        target = safe_path(root, relative, "selected input", strict=True)
    if continuation is not None and offset:
        raise PipelineError("source continuation and numeric offset are mutually exclusive")
    if offset and version is None:
        raise PipelineError("continuation reads require the previous page version")
    try:
        payload = target.read_bytes()
        actual = hashlib.sha256(payload).hexdigest()
        if version is not None and version != actual:
            raise PipelineError("selected input changed; discard prior pages and restart at offset zero")
        text = payload.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise PipelineError(f"cannot read selected UTF-8 input: {exc}") from exc
    text, first, last = _source_selection(text, section, lines)
    metadata = {"format": "pipeline-source-page-v1", "path": relative, "version": actual,
                "source": {"path": relative, "sha256": actual, "start_line": first, "end_line": last},
                **({"assignment_id": assignment["id"]} if assignment else {"instruction": instruction})}
    if assignment is not None:
        from .qa_contract import source_reference
        metadata["evidence_origin"] = {"ref": source_reference(metadata["source"]), "source": deepcopy(metadata["source"])}
        metadata["semantic_credit"] = False
    elif feature is not None:
        metadata["linked_reads"] = _instruction_link_reads(root, feature, instruction, target, text)
    return _semantic_page(text, metadata, continuation, limit, raw_text=True, offset=offset)


def execute_step(controller: Any, root: Path, expected_generation: int, action_id: str,
                 *, through_handoff: bool = False) -> dict[str, Any]:
    """Optionally compose at most complete/accept/next, stopping at a new worker."""
    if not through_handoff:
        return _execute_one_step(controller, root, expected_generation, action_id)
    request = {"expected_generation": expected_generation, "action_id": action_id}
    steps = []
    for _ in range(3):
        response = _execute_one_step(controller, root, expected_generation, action_id, include_cursor=True)
        if response["result"] != "executed":
            break
        steps.append({key: response[key] for key in (
            "command", "action_id", "generation", "phase", "outcome", "semantic_outcome",
        ) if key in response})
        if response["outcome"] not in {"phase_passed", "accepted"}:
            break
        action = response.get("next_action", {})
        following = {"complete": "accept", "accept": "next"}.get(response["command"])
        if action.get("kind") != "command" or action.get("command") != following:
            break
        # Each new step revalidates the returned exact cursor and native CAS.
        expected_generation, action_id = action["expected_generation"], action["command_id"]
    return {**response, "outcome": response.get("outcome", response["result"]),
            "through_handoff": True, "request": request, "steps": steps}


def _execute_one_step(controller: Any, root: Path, expected_generation: int, action_id: str,
                      *, include_cursor: bool = False) -> dict[str, Any]:
    """Execute exactly one existing public action; never infer a semantic result."""
    if type(expected_generation) is not int or expected_generation < 0:
        raise PipelineError("expected generation must be a nonnegative integer")
    view = controller.status()
    action = view["next_action"]
    # Retry is a receipt, not execution of the now-current next action.
    state = controller.store.load()
    if state.get("generation", view["generation"]) != view["generation"]:
        raise PipelineError("controller changed while inspecting step; retry the same action ID")
    prior = next((item for item in state["history"] if item.get("id") == action_id), None)
    if prior is not None:
        if prior.get("generation") != expected_generation + 1 or prior.get("command") not in {"next", "complete", "accept"}:
            raise PipelineError("step identity conflicts with a recorded command")
        response = {"result": "already_applied", "outcome": "replayed", "action_id": action_id,
                "generation": view["generation"], "phase": view["phase"],
                "next_action": director_brief(view)["next_action"]}
        if include_cursor:
            brief = director_brief(view)
            response["active_assignment"] = brief["active_assignment"]
            if brief["active_assignment"] is not None and action.get("command") == "complete":
                # A replay writes no new transport file and executes no action.
                response["assignment_delivery"] = brief["assignment_delivery"]
        return response
    if view["generation"] != expected_generation:
        raise PipelineError("stale step generation; inspect current status")
    if action.get("kind") != "command" or action.get("command") not in {"next", "complete", "accept"}:
        return {"result": "stopped", "generation": view["generation"], "next_action": action}
    if action.get("command_id") != action_id:
        raise PipelineError("step action ID must match public status.next_action")
    command = action["command"]
    if command == "complete":
        artifact = safe_path(root, action["artifact_path"], "assigned artifact")
        if not artifact.is_file():
            return {"result": "waiting_for_artifact", "generation": view["generation"], "assignment_id": action["assignment_id"],
                    "artifact_path": action["artifact_path"],
                    **({"phase": view["phase"], "next_action": director_brief(view)["next_action"]} if include_cursor else {})}
        result = controller.complete(command_id=action_id, expected_generation=expected_generation)
    elif command == "next":
        result = controller.next(command_id=action_id, expected_generation=expected_generation)
    else:
        result = controller.transition({"name": "accept", "id": action_id, "expected_generation": expected_generation})
    updated = status_view(result)
    semantic = None
    failure = None
    if command == "complete":
        record = result.get("artifacts", {}).get(view["phase"], {})
        semantic = record.get("worker", {}).get("outcome")
        failure = record.get("controller_failure")
        outcome = "gate_failed" if failure else {
            "pass": "phase_passed", "fail": "phase_failed", "blocked": "blocked",
        }.get(semantic, "completed")
    else:
        outcome = "assignment_issued" if command == "next" else "accepted"
    response = {"result": "executed", "command": command, "action_id": action_id,
                "generation": updated["generation"], "phase": updated["phase"],
                "outcome": outcome, "next_action": director_brief(updated)["next_action"]}
    if semantic is not None:
        response["semantic_outcome"] = semantic
    if failure is not None:
        response["failure"] = deepcopy(failure)
    if updated["active_assignment"] is not None:
        response["assignment_delivery"] = export_assignment(root, updated)
    return response
