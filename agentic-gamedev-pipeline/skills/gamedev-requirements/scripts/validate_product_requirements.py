#!/usr/bin/env python3
"""Validate the canonical product-requirements.md contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path


REQUIRED_HEADINGS = (
    "# Product Requirements",
    "## Product Outcome",
    "## Target Audience",
    "## Core Gameplay Loop",
    "## Release Target",
    "## Scope",
    "### In Scope",
    "### Out of Scope",
    "## Functional Requirements",
    "## Quality Requirements",
    "## Acceptance Criteria",
    "## Assumptions",
    "## Open Questions",
    "## Risks",
)
REQUIRED_APPROVED_SECTIONS = (
    "## Product Outcome",
    "## Target Audience",
    "## Core Gameplay Loop",
    "## Release Target",
    "### In Scope",
    "### Out of Scope",
    "## Functional Requirements",
    "## Quality Requirements",
    "## Acceptance Criteria",
)
ID_PATTERN = re.compile(r"\bPRD-(?:REQ|NFR|AC|OQ)-\d{3}\b")


def parse_frontmatter(text: str) -> tuple[dict[str, str], str, list[str]]:
    errors: list[str] = []
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text, ["missing YAML frontmatter"]
    try:
        end = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration:
        return {}, text, ["unterminated YAML frontmatter"]

    metadata: dict[str, str] = {}
    for line in lines[1:end]:
        match = re.fullmatch(r"([a-z_]+):\s*(.*?)\s*", line)
        if not match:
            errors.append(f"invalid frontmatter line: {line}")
            continue
        key, value = match.groups()
        if key in metadata:
            errors.append(f"duplicate frontmatter key: {key}")
        metadata[key] = value.strip('"\'')
    return metadata, "\n".join(lines[end + 1 :]), errors


def section_content(body: str, heading: str) -> str:
    lines = body.splitlines()
    try:
        start = lines.index(heading) + 1
    except ValueError:
        return ""
    level = len(heading) - len(heading.lstrip("#"))
    content: list[str] = []
    for line in lines[start:]:
        stripped = line.lstrip()
        if stripped.startswith("#"):
            next_level = len(stripped) - len(stripped.lstrip("#"))
            if next_level <= level:
                break
        content.append(line)
    return "\n".join(content).strip()


def validate(path: Path, require_approved: bool) -> dict:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return {"valid": False, "errors": [f"file is not valid UTF-8: {exc}"]}

    metadata, body, errors = parse_frontmatter(text)
    warnings: list[str] = []
    required_keys = {"document_type", "status", "revision", "language", "approved_at"}
    missing_keys = sorted(required_keys - metadata.keys())
    unexpected_keys = sorted(metadata.keys() - required_keys)
    errors.extend(f"missing frontmatter key: {key}" for key in missing_keys)
    errors.extend(f"unexpected frontmatter key: {key}" for key in unexpected_keys)

    if metadata.get("document_type") != "product-requirements":
        errors.append("document_type must be product-requirements")
    status = metadata.get("status")
    if status not in {"draft", "approved"}:
        errors.append("status must be draft or approved")
    try:
        revision = int(metadata.get("revision", ""))
        if revision < 1:
            raise ValueError
    except ValueError:
        errors.append("revision must be a positive integer")
        revision = None
    if not metadata.get("language") or metadata.get("language") == "unspecified":
        errors.append("language must be specified")

    body_lines = body.splitlines()
    positions: list[int] = []
    for heading in REQUIRED_HEADINGS:
        matches = [index for index, line in enumerate(body_lines) if line == heading]
        if not matches:
            errors.append(f"missing heading: {heading}")
            positions.append(-1)
            continue
        if len(matches) > 1:
            errors.append(f"duplicate heading: {heading}")
        positions.append(matches[0])
    present_positions = [position for position in positions if position >= 0]
    if present_positions != sorted(present_positions):
        errors.append("required headings are out of order")

    ids = ID_PATTERN.findall(body)
    duplicates = sorted(
        identifier for identifier, count in Counter(ids).items() if count > 1
    )
    errors.extend(f"duplicate identifier: {identifier}" for identifier in duplicates)

    approved_at = metadata.get("approved_at", "")
    if status == "approved" or require_approved:
        if status != "approved":
            errors.append("status must be approved")
        if approved_at in {"", "null"}:
            errors.append("approved_at must be set for an approved PRD")
        else:
            try:
                timestamp = datetime.fromisoformat(approved_at.replace("Z", "+00:00"))
                if timestamp.utcoffset() != timedelta(0):
                    raise ValueError
            except ValueError:
                errors.append("approved_at must be an ISO-8601 UTC timestamp")
        for heading in REQUIRED_APPROVED_SECTIONS:
            if not section_content(body, heading):
                errors.append(f"approved PRD section is empty: {heading}")
        if not re.search(r"\bPRD-REQ-\d{3}\b", body):
            errors.append("approved PRD requires at least one PRD-REQ identifier")
        if not re.search(r"\bPRD-AC-\d{3}\b", body):
            errors.append("approved PRD requires at least one PRD-AC identifier")
        if not re.search(r"\bPRD-NFR-\d{3}\b", body):
            errors.append("approved PRD requires at least one PRD-NFR identifier")
        if re.search(r"PRD-OQ-\d{3}.*\[blocking\]", body, flags=re.IGNORECASE):
            errors.append("approved PRD contains a blocking open question")
    elif approved_at != "null":
        errors.append("draft PRD must use approved_at: null")

    return {
        "valid": not errors,
        "path": str(path.resolve()),
        "status": status,
        "revision": revision,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path")
    parser.add_argument("--require-approved", action="store_true")
    args = parser.parse_args()
    path = Path(args.path)
    if not path.is_file():
        print(json.dumps({"valid": False, "errors": [f"file does not exist: {path}"]}, indent=2))
        return 1
    result = validate(path, args.require_approved)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
