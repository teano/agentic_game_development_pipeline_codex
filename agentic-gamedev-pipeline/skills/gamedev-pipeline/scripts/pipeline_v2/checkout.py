"""Controller-owned filesystem inventory, hashes, and allowed-path diff."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from .model import PipelineError, digest, normalize_rule

DEFAULT_EXCLUDES = (
    ".git", ".agentic-pipeline", ".agentic-pipeline-v2", "__pycache__",
)
ROOT_CONTROL_DIRECTORY = ".codegraph"


def safe_path(root: Path, supplied: str | Path | None, label: str, *, strict: bool = False) -> Path:
    """Confine a lexical path and reject every symlink/junction/reparse component."""
    root = Path(os.path.abspath(root))
    candidate = root if supplied is None else Path(supplied)
    candidate = Path(os.path.abspath(candidate if candidate.is_absolute() else root / candidate))
    try:
        if os.path.commonpath((os.path.normcase(root), os.path.normcase(candidate))) != os.path.normcase(root):
            raise ValueError
    except (OSError, ValueError) as exc:
        raise PipelineError(f"{label} escapes the project root") from exc
    components = list(reversed(root.parents[:-1])) + [root]
    if candidate != root:
        current = root
        for part in candidate.relative_to(root).parts:
            current /= part
            components.append(current)
    for component in components:
        try:
            stat = component.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise PipelineError(f"cannot inspect {label}: {exc}") from exc
        if component.is_symlink() or bool(getattr(stat, "st_file_attributes", 0) & 0x400):
            raise PipelineError(f"{label} crosses a symlink/junction/reparse component: {component}")
    if strict and not candidate.exists():
        raise PipelineError(f"{label} does not exist: {candidate}")
    return candidate


def canonical_project_root(supplied: str | Path) -> Path:
    """Return the existing physical root spelling after rejecting reparse traversal."""
    lexical = Path(supplied)
    if not lexical.is_absolute():
        raise PipelineError("project root must be absolute")
    lexical = safe_path(lexical, None, "project root", strict=True)
    try:
        resolved = lexical.resolve(strict=True)
    except OSError as exc:
        raise PipelineError(f"cannot resolve project root: {exc}") from exc
    return safe_path(resolved, None, "project root", strict=True)


def path_identity(value: str) -> str:
    """Compare project-relative paths using the host filesystem's case rules."""
    native = value.replace("/", os.sep)
    return os.path.normcase(os.path.normpath(native)).replace(os.sep, "/")


def _root_control_descendant(path: str) -> bool:
    parts = Path(path).parts
    return (
        len(parts) > 1
        and path_identity(parts[0]) == path_identity(ROOT_CONTROL_DIRECTORY)
    )


def authority_items_equal(
    left: dict[str, dict[str, str]], right: dict[str, dict[str, str]],
) -> bool:
    """Compare authority path identity and exact bytes without spelling aliases."""
    if set(left) != set(right):
        return False
    return all(
        left[name].get("sha256") == right[name].get("sha256")
        and path_identity(left[name].get("path", ""))
        == path_identity(right[name].get("path", ""))
        for name in left
    )


def file_sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def inventory(root: Path, *, excludes: tuple[str, ...] = DEFAULT_EXCLUDES) -> dict[str, dict[str, Any]]:
    root = safe_path(root, None, "project root", strict=True)
    if not root.is_dir():
        raise PipelineError("project root must be a directory")
    result: dict[str, dict[str, Any]] = {}
    for base, dirs, files in os.walk(root, followlinks=False):
        base_path = Path(base)
        kept = []
        for name in sorted(dirs):
            path = safe_path(root, base_path / name, "inventory path")
            if (
                name not in excludes
                and not (
                    base_path == root
                    and path_identity(name) == path_identity(ROOT_CONTROL_DIRECTORY)
                )
            ):
                kept.append(name)
        dirs[:] = kept
        for name in sorted(files):
            path = safe_path(root, base_path / name, "inventory path")
            relative = path.relative_to(root).as_posix()
            if (
                _root_control_descendant(relative)
                or any(part in excludes for part in Path(relative).parts)
            ):
                continue
            if path.is_file():
                stat = path.stat()
                result[relative] = {"kind": "file", "sha256": file_sha256(path), "size": stat.st_size}
    return result


def inventory_digest(value: dict[str, dict[str, Any]]) -> str:
    return digest(value)


def diff(
    base: dict[str, Any], current: dict[str, Any],
    *, excludes: tuple[str, ...] = DEFAULT_EXCLUDES,
) -> list[dict[str, Any]]:
    changes = []
    for path in sorted(set(base) | set(current)):
        if (
            _root_control_descendant(path)
            or any(part in excludes for part in Path(path).parts)
        ):
            continue
        if base.get(path) == current.get(path):
            continue
        kind = "add" if path not in base else "delete" if path not in current else "modify"
        changes.append({"path": path, "kind": kind, "before": base.get(path), "after": current.get(path)})
    return changes


def matches(path: str, rule: str) -> bool:
    rule = normalize_rule(rule)
    if rule == "**":
        return True
    if rule.endswith("/**"):
        prefix = rule[:-3].rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    return path == rule


def violations(changes: list[dict[str, Any]], write_rules: list[str]) -> list[str]:
    return [item["path"] for item in changes if not any(matches(item["path"], rule) for rule in write_rules)]


def authority_items(root: Path, paths: dict[str, str]) -> dict[str, dict[str, str]]:
    root = safe_path(root, None, "project root", strict=True)
    items = {}
    for name, relative in paths.items():
        rule = normalize_rule(relative)
        if rule == "**" or rule.endswith("/**"):
            raise PipelineError("authority paths must name exact files")
        path = safe_path(root, rule, "authority path", strict=True)
        if not path.is_file():
            raise PipelineError(f"authority path is not a file: {rule}")
        items[name] = {"path": rule, "sha256": file_sha256(path)}
    return items


def verify_authority(root: Path, authority: dict[str, Any]) -> None:
    actual = authority_items(root, {name: item["path"] for name, item in authority["items"].items()})
    if not authority_items_equal(actual, authority["items"]):
        raise PipelineError(
            "authority bytes changed; run status and execute its init reconfiguration"
        )
