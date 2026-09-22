"""Lossless, content-addressed delivery and one-step controller execution.

Delivery files are transport artifacts, never controller evidence or read receipts.
Offsets count Unicode code points in decoded UTF-8 text (not bytes or tokens).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from .checkout import matches, safe_path
from .model import ROLES, PipelineError, canonical_bytes, is_digest, normalize_literal_path, status_view


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
        locator["section"] = "Assignment and artifact boundaries"
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
            if isinstance(machine, dict) and "grants_manual_acceptance" in machine:
                projected["grants_manual_acceptance"] = deepcopy(machine["grants_manual_acceptance"])
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
    result["view"] = "director-brief"
    return result


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
    packet = {"format": "pipeline-assignment-v1", "run_id": view["run_id"], "feature": view["feature"],
              "project_root": project_root,
              "generation": view["generation"], "assignment": assignment, "selected_inputs": selected}
    instructions = _role_instructions(assignment.get("role"))
    if instructions is not None:
        packet["role_instructions"] = instructions
    workflow = view["workflow_path"]
    saved = _save(root, workflow, packet)
    if baseline is None:
        response = saved
        mode = "full"
    else:
        previous, _ = _load(root, workflow, baseline)
        if (previous.get("format") != packet["format"] or previous.get("run_id") != packet["run_id"]
                or previous.get("feature") != packet["feature"]
                or previous.get("project_root", project_root) != project_root
                or previous.get("assignment", {}).get("role") != assignment["role"]
                or previous.get("assignment", {}).get("worker_id") != assignment["worker_id"]):
            raise PipelineError("delta baseline must belong to the same run, role and worker in this project_root")
        response = _save(root, workflow, {"format": "pipeline-assignment-delta-v1", "baseline_digest": baseline,
            "packet_digest": saved["digest"], "project_root": project_root,
            "patch": json_patch(previous, packet)})
        mode = "delta"
    source_bytes = sum(item["bytes"] for item in selected)
    context = assignment.get("context", {})
    sections = [
        {"name": key, "pointer": "/assignment/context/" + key,
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
        "estimated_tokens": (saved["bytes"] + source_bytes + 3) // 4,
        "measurement": "UTF-8 bytes/4 estimate; excludes conversation, tools and system context",
        "context_sections": sections, "technical_decision_index": journal_index}
    locator = _verification_exit_criteria_locator(root, view, assignment)
    if locator is not None:
        working_set["verification_exit_criteria"] = locator
    dispatch = _dispatch_descriptor(root, view, packet, saved, response, mode, baseline)
    return {"mode": mode, "packet_digest": saved["digest"], "response_digest": response["digest"],
            "path": response["path"], "characters": response["characters"], "assignment_id": assignment["id"],
            "worker_id": assignment["worker_id"], "project_root": project_root,
            **({"role_instructions": instructions} if instructions is not None else {}),
            "generation": view["generation"], "delivery_complete": False,
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


def read_file(root: Path, view: dict[str, Any], relative: str, *, version: str | None = None,
              offset: int = 0, limit: int = 8192) -> dict[str, Any]:
    assignment = view.get("active_assignment")
    if assignment is None or view["next_action"].get("command") != "complete":
        raise PipelineError("file read requires a live active assignment with no recovery boundary")
    relative = normalize_literal_path(relative)
    if not any(matches(relative, rule) for rule in assignment["access"]["read"]):
        raise PipelineError("file is outside the active assignment read access")
    target = safe_path(root, relative, "selected input", strict=True)
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
    return {"path": relative, "assignment_id": assignment["id"], **text_page(text, actual, offset, limit)}


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
