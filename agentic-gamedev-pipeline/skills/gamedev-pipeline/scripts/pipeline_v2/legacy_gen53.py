"""Fail-closed tombstone for the retired schema-10 runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .model import PipelineError


SCHEMA10_UNSUPPORTED_MESSAGE = (
    "schema-10 migration is unsupported by git-tree-v1; "
    "archive legacy state/findings and run fresh Plan/init"
)


def import_schema10(
    legacy: dict[str, Any], slices: list[dict[str, Any]],
) -> dict[str, Any]:
    """Preserve the former public entry point as an explicit unsupported tombstone."""
    raise PipelineError(SCHEMA10_UNSUPPORTED_MESSAGE)


def load_schema10(path: Path, slices: list[dict[str, Any]]) -> dict[str, Any]:
    """Preserve the former loader entry point without reading or reconstructing state."""
    raise PipelineError(SCHEMA10_UNSUPPORTED_MESSAGE)
