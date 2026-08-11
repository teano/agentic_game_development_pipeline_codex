#!/usr/bin/env python3
"""Canonical capability identifiers shared by planning and runtime controllers."""

from __future__ import annotations

import re


CAPABILITY_ID_PATTERN = r"[a-z0-9]+(?:-[a-z0-9]+)*"


def parse_capability_ids(value: str, *, label: str) -> list[str]:
    parts = [item.strip() for item in value.split(",")]
    if not parts or any(not item for item in parts):
        raise ValueError(f"{label} must contain comma-separated canonical capability IDs")
    invalid = [item for item in parts if not re.fullmatch(CAPABILITY_ID_PATTERN, item)]
    if invalid:
        raise ValueError(
            f"{label} contains invalid capability ID(s): " + ", ".join(invalid)
        )
    if len(parts) != len(set(parts)):
        raise ValueError(f"{label} repeats a capability ID")
    return parts


def require_capability_id(value: str, *, label: str = "capability") -> str:
    parsed = parse_capability_ids(value, label=label)
    if len(parsed) != 1:
        raise ValueError(f"{label} must contain exactly one canonical capability ID")
    return parsed[0]
