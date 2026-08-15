#!/usr/bin/env python3
"""Small canonical acceptance-ID grammar shared by every pipeline stage.

This module intentionally does not implement CommonMark.  Authority comes from one
exact, top-level ``## Acceptance Criteria`` heading and plain list declarations:

    - PRD-AC-001: observable plain-text outcome

Fenced, quoted, indented, commented, and HTML-block examples are ignored.  The
remaining helpers parse literal comma-separated controller fields and visible plan
prose without expanding shorthand ranges.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterator


ACCEPTANCE_ID_PATTERN = r"PRD-AC-[A-Za-z0-9-]+"
_RAW_ACCEPTANCE_ID = re.compile(ACCEPTANCE_ID_PATTERN)
_FENCE = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})(?:[^\r\n]*)$")
_HEADING = re.compile(r"^#{1,2}(?:[ \t]+|$)")
_DECLARATION = re.compile(
    rf"^- (?P<id>{ACCEPTANCE_ID_PATTERN}): (?P<description>\S(?:.*\S)?)$"
)
_RANGE_AFTER_ID = re.compile(
    rf"(?P<start>{ACCEPTANCE_ID_PATTERN})[ \t]*"
    r"(?P<separator>\.+|…|–|—|\bto\b)[ \t]*"
    rf"(?P<end>{ACCEPTANCE_ID_PATTERN}|[A-Za-z0-9][A-Za-z0-9-]*)",
    re.IGNORECASE,
)
_MULTILINE_FULL_RANGE = re.compile(
    rf"(?P<start>{ACCEPTANCE_ID_PATTERN})\s*"
    r"(?P<separator>\.+|…|–|—|\bto\b)\s*"
    rf"(?P<end>{ACCEPTANCE_ID_PATTERN}|[0-9]+|[A-Za-z0-9]+-[A-Za-z0-9-]+)",
    re.IGNORECASE,
)
_RAW_HTML_TAG = re.compile(
    r"^<(?:script|pre|style|textarea)(?=[\s>/]|$)", re.IGNORECASE
)
_RAW_HTML_CLOSE = {
    "script": re.compile(r"</script\s*>", re.IGNORECASE),
    "pre": re.compile(r"</pre\s*>", re.IGNORECASE),
    "style": re.compile(r"</style\s*>", re.IGNORECASE),
    "textarea": re.compile(r"</textarea\s*>", re.IGNORECASE),
}
_ENTITY = re.compile(r"&(?:#[0-9]+|#[xX][0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]+);")
_INLINE_MARKDOWN_MARKERS = frozenset("`<>[]*_\\~")


def _markdown_lines(value: str) -> list[str]:
    """Only CR, LF, and CRLF are structural line endings."""
    return re.split(r"\r\n|\r|\n", value)


def _identifier_neighbor(character: str | None) -> bool:
    if not character:
        return False
    if character in {"-", "_"}:
        return True
    return unicodedata.category(character)[0] in {"L", "M", "N"} or unicodedata.category(
        character
    ) == "Cf"


def _literal_matches(value: str) -> Iterator[re.Match[str]]:
    for match in _RAW_ACCEPTANCE_ID.finditer(value):
        before = value[match.start() - 1] if match.start() else None
        after = value[match.end()] if match.end() < len(value) else None
        if not _identifier_neighbor(before) and not _identifier_neighbor(after):
            yield match


def markdown_authority_lines(value: str) -> Iterator[tuple[int, str]]:
    """Yield lines eligible for the strict canonical grammar.

    This is deliberately a small safety filter, not a rendering engine.  It ignores
    the literal/example containers that can otherwise counterfeit a top-level
    heading.  Canonical documents must keep authority outside those containers.
    """
    fence_character: str | None = None
    fence_length = 0
    html_terminator: str | re.Pattern[str] | None = None

    for line_number, line in enumerate(_markdown_lines(value), start=1):
        if fence_character is not None:
            if re.fullmatch(
                rf"[ ]{{0,3}}{re.escape(fence_character)}{{{fence_length},}}[ \t]*",
                line,
            ):
                fence_character = None
                fence_length = 0
            continue

        if html_terminator is not None:
            if html_terminator == "blank":
                if not line.strip():
                    html_terminator = None
            elif isinstance(html_terminator, str):
                if html_terminator in line:
                    html_terminator = None
            elif html_terminator.search(line):
                html_terminator = None
            continue

        fence = _FENCE.match(line)
        if fence:
            fence_character = fence.group(1)[0]
            fence_length = len(fence.group(1))
            continue

        stripped = line.lstrip(" ")
        leading_spaces = len(line) - len(stripped)
        if leading_spaces <= 3 and stripped.startswith("<"):
            terminator: str | re.Pattern[str] = "blank"
            raw_tag = _RAW_HTML_TAG.match(stripped)
            if stripped.startswith("<!--"):
                terminator = "-->"
            elif stripped.startswith("<?"):
                terminator = "?>"
            elif stripped.startswith("<![CDATA["):
                terminator = "]]>"
            elif re.match(r"^<![A-Z]", stripped):
                terminator = ">"
            elif raw_tag:
                tag = re.match(r"^<([A-Za-z]+)", stripped).group(1).casefold()
                terminator = _RAW_HTML_CLOSE[tag]
            if terminator == "blank":
                html_terminator = terminator
            elif isinstance(terminator, str):
                if terminator not in stripped[stripped.find("<") + 1 :]:
                    html_terminator = terminator
            elif not terminator.search(stripped[raw_tag.end() :]):
                html_terminator = terminator
            continue
        if line.startswith("\t") or leading_spaces >= 4 or stripped.startswith(">"):
            continue
        yield line_number, line


def find_acceptance_ranges(value: str) -> list[str]:
    """Return explicit acceptance ranges from the small visible line stream."""
    ranges: list[str] = []
    lines = [line for _, line in markdown_authority_lines(value)]

    def collect(source: str, pattern: re.Pattern[str]) -> None:
        for match in pattern.finditer(source):
            before = source[match.start() - 1] if match.start() else None
            after = source[match.end()] if match.end() < len(source) else None
            if not _identifier_neighbor(before) and not _identifier_neighbor(after):
                ranges.append(match.group(0))

    for line in lines:
        collect(line, _RANGE_AFTER_ID)
    collect("\n".join(lines), _MULTILINE_FULL_RANGE)
    ranges = list(dict.fromkeys(ranges))
    return ranges


def _reject_acceptance_ranges(value: str, *, label: str) -> None:
    ranges = find_acceptance_ranges(value)
    if ranges:
        raise ValueError(
            f"{label} contains ambiguous range shorthand; list every PRD-AC-* ID "
            "literally: " + ", ".join(ranges)
        )


def parse_acceptance_ids(value: str, *, label: str) -> list[str]:
    """Parse one strict comma-separated controller field."""
    parts = [item.strip() for item in value.split(",")]
    if not parts or any(not item for item in parts):
        raise ValueError(f"{label} must contain comma-separated literal PRD-AC-* IDs")
    invalid = [item for item in parts if not re.fullmatch(ACCEPTANCE_ID_PATTERN, item)]
    if invalid:
        raise ValueError(
            f"{label} contains invalid or non-literal acceptance ID(s): "
            + ", ".join(invalid)
        )
    if len(parts) != len(set(parts)):
        raise ValueError(f"{label} repeats an acceptance ID")
    return parts


def extract_literal_acceptance_ids(value: str, *, label: str) -> list[str]:
    """Extract exact ``- PRD-AC-ID`` assignment rows from a plan section."""
    _reject_acceptance_ranges(value, label=label)
    identifiers: list[str] = []
    assignment = re.compile(rf"^[ ]{{0,3}}- (?P<id>{ACCEPTANCE_ID_PATTERN})[ \t]*$")
    for line_number, line in markdown_authority_lines(value):
        matches = [match.group(0) for match in _literal_matches(line)]
        if not matches:
            continue
        parsed = assignment.fullmatch(line)
        if parsed is None or matches != [parsed.group("id")]:
            raise ValueError(
                f"{label} line {line_number} must assign one literal acceptance ID "
                "as `- PRD-AC-ID`"
            )
        identifiers.append(parsed.group("id"))
    duplicates = sorted(
        identifier for identifier, count in Counter(identifiers).items() if count > 1
    )
    if duplicates:
        raise ValueError(
            f"{label} repeats acceptance ID row(s): " + ", ".join(duplicates)
        )
    return identifiers


def _plain_description(value: str) -> bool:
    """Keep canonical declarations readable without an inline-Markdown emulator."""
    # Covers the GFM inline forms relevant inside one canonical list row: code,
    # links/images, emphasis, strikethrough, autolinks/HTML, and escapes. Image
    # syntax is already excluded by the bracket check; entities are handled below.
    if any(
        character in value for character in _INLINE_MARKDOWN_MARKERS
    ) or _ENTITY.search(value):
        return False
    return any(unicodedata.category(character)[0] in {"L", "N", "S"} for character in value)


def derive_prd_acceptance_inventory(value: str, *, label: str) -> frozenset[str]:
    """Derive the exact inventory from one canonical Acceptance Criteria section."""
    records = list(markdown_authority_lines(value))
    positions = [
        index
        for index, (_, line) in enumerate(records)
        if line == "## Acceptance Criteria"
    ]
    if len(positions) != 1:
        raise ValueError(
            f"{label} must contain exactly one exact top-level ## Acceptance Criteria section"
        )

    start = positions[0] + 1
    end = next(
        (
            index
            for index in range(start, len(records))
            if _HEADING.match(records[index][1])
        ),
        len(records),
    )
    section = [(number, line) for number, line in records[start:end] if line.strip()]
    identifiers: list[str] = []
    for line_number, line in section:
        declaration = _DECLARATION.fullmatch(line)
        if not declaration or not _plain_description(declaration.group("description")):
            raise ValueError(
                f"{label} Acceptance Criteria line {line_number} must use exact "
                "`- PRD-AC-ID: plain-text description` format"
            )
        literal_ids = [match.group(0) for match in _literal_matches(line)]
        if literal_ids != [declaration.group("id")]:
            raise ValueError(
                f"{label} Acceptance Criteria line {line_number} must declare exactly one literal ID"
            )
        identifiers.append(declaration.group("id"))

    if not identifiers:
        raise ValueError(f"{label} canonical Acceptance Criteria section is empty")
    duplicates = sorted(
        identifier for identifier, count in Counter(identifiers).items() if count > 1
    )
    if duplicates:
        raise ValueError(
            f"{label} Acceptance Criteria repeats criterion ID(s): " + ", ".join(duplicates)
        )
    return frozenset(identifiers)


def require_known_acceptance_ids(
    values: set[str] | frozenset[str], inventory: frozenset[str], *, label: str
) -> None:
    unknown = sorted(set(values) - inventory)
    if unknown:
        raise ValueError(
            f"{label} contains ID(s) absent from the approved PRD inventory: "
            + ", ".join(unknown)
        )


def require_complete_acceptance_coverage(
    slice_values: dict[str, set[str] | frozenset[str]],
    inventory: frozenset[str],
    *,
    label: str,
) -> None:
    """Require exact union coverage; the same AC may span multiple vertical slices."""
    covered = set().union(*(set(values) for values in slice_values.values()))
    missing = sorted(inventory - covered)
    unknown = sorted(covered - inventory)
    if missing or unknown:
        details: list[str] = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unknown:
            details.append("unknown " + ", ".join(unknown))
        raise ValueError(f"{label} must exactly cover the approved PRD inventory: " + "; ".join(details))
