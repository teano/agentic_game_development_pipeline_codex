#!/usr/bin/env python3
"""Validate the canonical product-requirements.md contract."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
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
DECLARATION_SECTIONS = {
    "PRD-REQ": "## Functional Requirements",
    "PRD-NFR": "## Quality Requirements",
    "PRD-OQ": "## Open Questions",
}

_acceptance_contract_path = (
    Path(__file__).resolve().parents[3] / "scripts" / "acceptance_contract.py"
)
_acceptance_contract_spec = importlib.util.spec_from_file_location(
    "gamedev_acceptance_contract", _acceptance_contract_path
)
if _acceptance_contract_spec is None or _acceptance_contract_spec.loader is None:
    raise RuntimeError("Cannot load the canonical acceptance contract")
_acceptance_contract = importlib.util.module_from_spec(_acceptance_contract_spec)
_acceptance_contract_spec.loader.exec_module(_acceptance_contract)
derive_prd_acceptance_inventory = _acceptance_contract.derive_prd_acceptance_inventory
markdown_authority_lines = _acceptance_contract.markdown_authority_lines
plain_text_description = _acceptance_contract._plain_description


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


def section_authority_lines(body: str, heading: str) -> list[tuple[int, str]]:
    lines = list(markdown_authority_lines(body))
    try:
        start = next(index for index, (_, line) in enumerate(lines) if line == heading) + 1
    except StopIteration:
        return []
    level = len(heading) - len(heading.lstrip("#"))
    content: list[tuple[int, str]] = []
    for line_number, line in lines[start:]:
        if line.startswith("#"):
            next_level = len(line) - len(line.lstrip("#"))
            if next_level <= level:
                break
        content.append((line_number, line))
    return content


def section_content(body: str, heading: str) -> str:
    return "\n".join(
        line for _, line in section_authority_lines(body, heading)
    ).strip()


def canonical_declarations(
    body: str, heading: str, identifier_prefix: str
) -> tuple[list[tuple[str, str]], list[tuple[int, str]]]:
    """Return exact declarations and declaration-like invalid rows from one section."""
    identifier = rf"{re.escape(identifier_prefix)}-\d{{3}}"
    declaration = re.compile(
        rf"^- (?P<id>{identifier}): (?P<description>\S(?:.*\S)?)$"
    )
    candidate = re.compile(
        rf"^[ \t]*(?:(?:[-+*]|\d+[.)])\s+)?`?{re.escape(identifier_prefix)}-"
    )
    result: list[tuple[str, str]] = []
    invalid: list[tuple[int, str]] = []
    for line_number, line in section_authority_lines(body, heading):
        match = declaration.fullmatch(line)
        description = match.group("description") if match else ""
        if identifier_prefix == "PRD-OQ" and description.lower().startswith("[blocking] "):
            description = description[len("[blocking] ") :]
        if match and plain_text_description(description):
            result.append((match.group("id"), line))
        elif candidate.match(line):
            invalid.append((line_number, line))
    return result, invalid


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

    body_lines = list(markdown_authority_lines(body))
    positions: list[int] = []
    for heading in REQUIRED_HEADINGS:
        matches = [line_number for line_number, line in body_lines if line == heading]
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

    declaration_inventory = {
        prefix: canonical_declarations(body, heading, prefix)
        for prefix, heading in DECLARATION_SECTIONS.items()
    }
    declarations = {
        prefix: inventory[0] for prefix, inventory in declaration_inventory.items()
    }
    for prefix, (_, invalid) in declaration_inventory.items():
        heading = DECLARATION_SECTIONS[prefix]
        errors.extend(
            f"{heading} line {line_number} has invalid {prefix} declaration; "
            f"use exact `- {prefix}-001: plain-text description` format"
            for line_number, _ in invalid
        )
    ids = [
        identifier
        for section_declarations in declarations.values()
        for identifier, _ in section_declarations
    ]
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
        try:
            acceptance_inventory = derive_prd_acceptance_inventory(
                body, label="approved PRD"
            )
        except ValueError as exc:
            errors.append(str(exc))
            acceptance_inventory = frozenset()
        if not declarations["PRD-REQ"]:
            errors.append(
                "approved PRD requires at least one PRD-REQ declaration in Functional Requirements"
            )
        if not acceptance_inventory:
            errors.append("approved PRD requires a canonical PRD-AC inventory")
        if not declarations["PRD-NFR"]:
            errors.append(
                "approved PRD requires at least one PRD-NFR declaration in Quality Requirements"
            )
        if any(
            re.search(r"\[blocking\]", line, flags=re.IGNORECASE)
            for _, line in declarations["PRD-OQ"]
        ):
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
