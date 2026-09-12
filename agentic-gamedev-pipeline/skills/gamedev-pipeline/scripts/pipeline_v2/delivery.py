"""Lossless, content-addressed delivery and one-step controller execution.

Delivery files are transport artifacts, never controller evidence or read receipts.
Offsets count Unicode code points in decoded UTF-8 text (not bytes or tokens).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from .checkout import matches, safe_path
from .model import PipelineError, canonical_bytes, is_digest, normalize_literal_path, status_view


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
        metadata["content_included"] = False
        observation = assignment.get("technical_observation")
        if isinstance(observation, dict):
            metadata["technical_observation"] = {key: observation[key] for key in ("id", "tree", "assignment_id") if key in observation}
        return metadata

    if result["active_assignment"] is not None:
        result["active_assignment"] = identity(result["active_assignment"])
        result["assignment_delivery"] = {"command": "assignment-export", "content_included": False}
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
    return {"digest": version, "path": target.relative_to(root).as_posix(), "characters": len(payload.decode("utf-8"))}


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


def export_assignment(root: Path, view: dict[str, Any], baseline: str | None = None,
                      inputs: list[str] | None = None) -> dict[str, Any]:
    assignment = view.get("active_assignment")
    if assignment is None or view["next_action"].get("command") != "complete":
        raise PipelineError("assignment export requires a live active assignment with no recovery boundary")
    selected = []
    for relative in dict.fromkeys(inputs or []):
        relative = normalize_literal_path(relative)
        if not any(matches(relative, rule) for rule in assignment["access"]["read"]):
            raise PipelineError("selected input is outside the active assignment read access")
        target = safe_path(root, relative, "selected input", strict=True)
        try:
            selected.append({"path": relative, "version": hashlib.sha256(target.read_bytes()).hexdigest()})
        except OSError as exc:
            raise PipelineError(f"cannot inspect selected input: {exc}") from exc
    packet = {"format": "pipeline-assignment-v1", "run_id": view["run_id"], "feature": view["feature"],
              "generation": view["generation"], "assignment": assignment, "selected_inputs": selected}
    workflow = view["workflow_path"]
    saved = _save(root, workflow, packet)
    if baseline is None:
        response = saved
        mode = "full"
    else:
        previous, _ = _load(root, workflow, baseline)
        if (previous.get("format") != packet["format"] or previous.get("run_id") != packet["run_id"]
                or previous.get("feature") != packet["feature"]
                or previous.get("assignment", {}).get("role") != assignment["role"]
                or previous.get("assignment", {}).get("worker_id") != assignment["worker_id"]):
            raise PipelineError("delta baseline must belong to the same run, role and worker")
        response = _save(root, workflow, {"format": "pipeline-assignment-delta-v1", "baseline_digest": baseline,
            "packet_digest": saved["digest"], "patch": json_patch(previous, packet)})
        mode = "delta"
    return {"mode": mode, "packet_digest": saved["digest"], "response_digest": response["digest"],
            "path": response["path"], "characters": response["characters"], "assignment_id": assignment["id"],
            "generation": view["generation"], "delivery_complete": False}


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


def execute_step(controller: Any, root: Path, expected_generation: int, action_id: str) -> dict[str, Any]:
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
        return {"result": "already_applied", "action_id": action_id, "generation": view["generation"]}
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
                    "artifact_path": action["artifact_path"]}
        result = controller.complete(command_id=action_id, expected_generation=expected_generation)
    elif command == "next":
        result = controller.next(command_id=action_id, expected_generation=expected_generation)
    else:
        result = controller.transition({"name": "accept", "id": action_id, "expected_generation": expected_generation})
    updated = status_view(result)
    response = {"result": "executed", "command": command, "action_id": action_id,
                "generation": updated["generation"], "phase": updated["phase"]}
    if updated["active_assignment"] is not None:
        response["assignment_delivery"] = export_assignment(root, updated)
    return response
