"""File-backed UTF-8 artifacts. Shape validation grants no semantic acceptance."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any


def write_json(path: Path, value: Any) -> None:
    """Atomically serialize once; callers own destination authorization."""
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    write_bytes(path, raw)


def write_bytes(path: Path, raw: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".artifact-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_bytes_immutable(path: Path, raw: bytes) -> None:
    """Publish once, recover identical retries, never replace different bytes."""
    from .model import PipelineError
    path = Path(path)
    if path.exists():
        if path.read_bytes() != raw:
            raise PipelineError("immutable capture already exists with different content")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".immutable-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != raw:
                raise PipelineError("immutable capture concurrently published with different content")
    finally:
        os.unlink(temporary)


def contained_path(directory: Path, destination: Path) -> Path:
    """Reject escape and linked components, including dangling links."""
    from .model import PipelineError
    directory = Path(os.path.abspath(directory))
    destination = Path(os.path.abspath(destination))
    try:
        destination.relative_to(directory)
    except ValueError as exc:
        raise PipelineError(f"output must stay within {directory}") from exc
    for part in (destination, *destination.parents):
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise PipelineError("artifact destination cannot traverse a symbolic link or junction")
    return destination


def write_read_output(root: Path, workflow: Path, destination: Path, value: Any) -> dict[str, Any]:
    from .model import PipelineError
    directory = Path(workflow) / "ReadOutputs"
    if not directory.is_absolute():
        directory = Path(root) / directory
    destination = Path(destination)
    if not destination.is_absolute():
        destination = Path(root) / destination
    path = contained_path(directory, destination)
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    if path.exists() and path.read_bytes() != raw:
        raise PipelineError("read output already exists with different content; choose another destination")
    write_bytes_immutable(path, raw)
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def read_json(path: Path) -> Any:
    from .model import PipelineError
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"),
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"invalid JSON constant {value}")))
    except (OSError, UnicodeError, ValueError) as exc:
        raise PipelineError(f"cannot read JSON artifact {path}: {exc}") from exc


def validation_errors(state: dict[str, Any], value: Any) -> list[dict[str, str]]:
    """Batch independent field errors, then invoke the existing full validator.

    This is an authoring aid, not an alternative acceptance implementation.
    Dependent contract errors may require another pass after shape repairs.
    """
    from .model import artifact_schema, PipelineError
    from .reducer import _worker_artifact
    active = state.get("active_assignment")
    if not isinstance(active, dict):
        raise PipelineError("artifact validation requires the current active assignment")
    phase, role = active["phase"], active["role"]
    schema = artifact_schema(phase, role)
    qa_contract = active.get("capsule", {}).get("context", {}).get("qa_contract", {})
    bound_qa = qa_contract.get("status") == "bound"
    errors: list[dict[str, str]] = []

    def add(path, message):
        row = {"path": path, "message": message}
        if row not in errors:
            errors.append(row)

    def shape(item, required, allowed, path):
        if not isinstance(item, dict):
            add(path, "must be an object")
            return False
        for key in sorted(set(required) - set(item)):
            add(path + "/" + key, "required field is missing")
        for key in sorted(set(item) - set(allowed)):
            add(path + "/" + key, "field is not allowed by the assignment schema")
        return True

    if shape(value, schema["required_keys"], schema["allowed_keys"], ""):
        if value.get("outcome") not in schema["outcome_enum"]:
            add("/outcome", "must be pass, fail or blocked")
        for key in ("summary", "blocker", "required_action"):
            required = key == "summary" and phase in {"plan", "slice", "engineering", "docs"}
            required |= key in {"blocker", "required_action"} and value.get("outcome") == "blocked"
            if (required or key in value) and (not isinstance(value.get(key), str) or not value[key].strip()):
                add("/" + key, "must be a non-empty string")
        for key in ("checks", "findings", "questions", "assumptions", "technical_decisions", "finding_resolutions"):
            if key in value and not isinstance(value[key], list):
                add("/" + key, "must be a list")
        if phase == "qa" and isinstance(value.get("checks"), list):
            for i, check in enumerate(value["checks"]):
                path = f"/checks/{i}"
                if not shape(check, ("id", "outcome", "evidence", "assertions") if bound_qa else ("id", "outcome", "evidence"),
                             ("id", "outcome", "evidence", "assertions"), path):
                    continue
                for key in ("id", "evidence"):
                    if not isinstance(check.get(key), str) or not check[key].strip():
                        add(path + "/" + key, "must be a non-empty string")
                if check.get("outcome") not in {"pass", "fail", "not_run"}:
                    add(path + "/outcome", "must be pass, fail or not_run")
                if not bound_qa:
                    continue
                if not isinstance(check.get("assertions"), list):
                    add(path + "/assertions", "must be a list")
                    continue
                for j, result in enumerate(check["assertions"]):
                    where = path + f"/assertions/{j}"
                    if not shape(result, ("id", "outcome", "method_id", "environment", "evidence"),
                                 ("id", "outcome", "method_id", "environment", "evidence", "reason", "assessment"), where):
                        continue
                    for key in ("id", "environment"):
                        if not isinstance(result.get(key), str) or not result[key].strip():
                            add(where + "/" + key, "must be a non-empty string")
                    if result.get("outcome") not in {"pass", "fail", "not_run", "not_applicable"}:
                        add(where + "/outcome", "invalid assertion outcome")
                    if not isinstance(result.get("evidence"), list):
                        add(where + "/evidence", "must be a list")
    if bound_qa and isinstance(value, dict) and isinstance(value.get("checks"), list):
        from .qa_contract import result_errors
        for row in result_errors(value["checks"], qa_contract["definition"], strict_gaps=True):
            add(row["path"], row["message"])
    try:
        required = active.get("capsule", {}).get("context", {}).get("required_identity_ids")
        _worker_artifact(value, phase, role, required, state=state)
    except (ValueError, KeyError, TypeError) as exc:
        if not errors:
            add("", str(exc))
    return errors
