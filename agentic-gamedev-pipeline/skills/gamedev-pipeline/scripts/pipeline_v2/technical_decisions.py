"""Current technical decisions: one controller-owned map, with a read-only upstream API."""
from __future__ import annotations

import hashlib
import json
import os
import re
from copy import deepcopy
from pathlib import Path


def journal_digest(entries: dict) -> str:
    return hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def validate_entry(entry: dict, *, sealed: bool = False) -> dict:
    required = {"id", "situation", "decision", "basis", "checks", "downstream"}
    optional = {"overrides"} | ({"execution"} if sealed else set())
    if not isinstance(entry, dict) or not required <= set(entry) or set(entry) - required - optional:
        raise ValueError("technical decision requires id, situation, decision, basis, checks, downstream and optional overrides")
    if not isinstance(entry["id"], str) or not re.fullmatch(r"TD-[A-Za-z0-9-]+", entry["id"]):
        raise ValueError("technical decision ID must be a stable TD-* identifier")
    for key in required - {"checks"} | ({"overrides"} & set(entry)):
        if not isinstance(entry[key], str) or not entry[key].strip():
            raise ValueError(f"technical decision {key} must be non-empty text")
    if not isinstance(entry["checks"], list) or any(not isinstance(x, str) or not x.strip() for x in entry["checks"]):
        raise ValueError("technical decision checks must be a list of actual evidence strings")
    if "execution" in entry:
        execution = entry["execution"]
        if not isinstance(execution, dict) or set(execution) != {"slice_id", "authority", "additional_paths", "command_order"}:
            raise ValueError("malformed sealed technical execution overlay")
        if not isinstance(execution["slice_id"], str) or not isinstance(execution["authority"], str) or not re.fullmatch(r"[0-9a-f]{64}", execution["authority"]):
            raise ValueError("malformed technical overlay binding")
        if not isinstance(execution["additional_paths"], list) or not isinstance(execution["command_order"], list):
            raise ValueError("malformed technical overlay paths or command order")
        paths = execution["additional_paths"]
        for path in paths:
            if (not isinstance(path, str) or not path or path.startswith("/") or ":" in path or "\\" in path or "*" in path
                    or any(part in {"", ".", ".."} for part in path.split("/"))
                    or any(part.casefold() in {".git", ".agentic-pipeline", ".agentic-pipeline-v2", ".gitignore", ".gitattributes", ".gitmodules", "agents.md"} for part in path.split("/"))):
                raise ValueError("technical overlay requires exact non-authority product file paths")
        if len(paths) != len(set(paths)):
            raise ValueError("duplicate technical overlay path")
        if any(not isinstance(argv, list) or not argv or any(not isinstance(arg, str) or not arg for arg in argv) for argv in execution["command_order"]):
            raise ValueError("technical overlay command order must contain argv lists")
    return deepcopy(entry)


def validate_journal(entries: dict) -> dict:
    if not isinstance(entries, dict):
        raise ValueError("technical_decisions must be an object keyed by stable ID")
    for key, entry in entries.items():
        validate_entry(entry, sealed=True)
        if key != entry["id"]:
            raise ValueError("technical decision key does not match its ID")
    return entries


def journal_reference(state: dict) -> dict:
    entries = state.get("technical_decisions", {})
    return {"path": f"{state['workflow_path']}/pipeline-state.json#technical_decisions",
            "sha256": journal_digest(entries), "count": len(entries)}


def technical_decisions_context(root: Path | str, feature: str) -> dict:
    """Read the current feature journal; absent runtime means an empty journal.

    Fail closed on malformed, foreign or linked state; never rewrite upstream authority.
    """
    if not isinstance(feature, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", feature):
        raise ValueError("invalid technical journal feature")
    root = Path(root).resolve(strict=True)
    relative = f".agentic-pipeline/Workflows/{feature}/pipeline-state.json"
    path = root / relative
    for parent in [path, *path.parents]:
        if parent == root:
            break
        if parent.is_symlink() or getattr(parent, "is_junction", lambda: False)():
            raise ValueError("technical journal must not use linked paths")
    entries = {}
    if path.exists():
        state = json.loads(path.read_text(encoding="utf-8"))
        stored_root = state.get("project_root") if isinstance(state, dict) else None
        if not isinstance(stored_root, str) or not stored_root.strip() or not Path(stored_root).is_absolute():
            raise ValueError("technical journal requires an explicit absolute project_root")
        if (not isinstance(state, dict) or state.get("feature") != feature
                or state.get("workflow_path") != relative.rsplit("/", 1)[0]
                or os.path.normcase(str(Path(stored_root).resolve())) != os.path.normcase(str(root))):
            raise ValueError("technical journal is bound to a different feature or project")
        entries = validate_journal(state.get("technical_decisions", {}))
    return {"path": relative + "#technical_decisions", "sha256": journal_digest(entries), "entries": deepcopy(entries)}
