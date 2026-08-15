#!/usr/bin/env python3
"""Focused tests for the shared canonical acceptance grammar."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE = Path(__file__).resolve().parents[3] / "scripts" / "acceptance_contract.py"
SPEC = importlib.util.spec_from_file_location("acceptance_contract_tested", MODULE)
assert SPEC and SPEC.loader
contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)


class AcceptanceContractTests(unittest.TestCase):
    def test_comma_separated_fields_require_unique_literal_ids(self) -> None:
        self.assertEqual(
            ["PRD-AC-save-v2", "PRD-AC-002"],
            contract.parse_acceptance_ids(
                "PRD-AC-save-v2, PRD-AC-002", label="scope"
            ),
        )
        for value in (
            "",
            "PRD-AC-001,",
            "PRD-AC-001, PRD-AC-001",
            "PRD-AC-001 .. PRD-AC-003",
            "criterion PRD-AC-001",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                contract.parse_acceptance_ids(value, label="scope")

    def test_inventory_uses_one_exact_top_level_canonical_section(self) -> None:
        text = """# PRD

## Acceptance Criteria

- PRD-AC-001: First observable outcome.
- PRD-AC-save-v2: Второй проверяемый результат.

## Risks
"""
        self.assertEqual(
            frozenset({"PRD-AC-001", "PRD-AC-save-v2"}),
            contract.derive_prd_acceptance_inventory(text, label="PRD"),
        )
        for replacement in (
            "### Acceptance Criteria",
            "## Acceptance Criteria ",
            " ## Acceptance Criteria",
        ):
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                contract.derive_prd_acceptance_inventory(
                    text.replace("## Acceptance Criteria", replacement), label="PRD"
                )

    def test_literal_examples_cannot_create_heading_authority(self) -> None:
        hidden = (
            "```md\n## Acceptance Criteria\n- PRD-AC-hidden: no\n```",
            "<!--\n## Acceptance Criteria\n- PRD-AC-hidden: no\n-->",
            "> ## Acceptance Criteria\n> - PRD-AC-hidden: no",
            "    ## Acceptance Criteria\n    - PRD-AC-hidden: no",
            "<div>\n## Acceptance Criteria\n- PRD-AC-hidden: no\n</div>\n",
        )
        canonical = "## Acceptance Criteria\n\n- PRD-AC-001: Visible outcome."
        for example in hidden:
            with self.subTest(example=example):
                self.assertEqual(
                    frozenset({"PRD-AC-001"}),
                    contract.derive_prd_acceptance_inventory(
                        example + "\n\n" + canonical, label="PRD"
                    ),
                )

    def test_html_blocks_use_their_own_terminators(self) -> None:
        hidden = "\n".join(
            (
                "<pre>\n\n## Acceptance Criteria\n- PRD-AC-pre: hidden\n</pre>",
                "<SCRIPT>\n\n## Acceptance Criteria\n- PRD-AC-script: hidden\n</SCRIPT>",
                "<style>\n\n## Acceptance Criteria\n- PRD-AC-style: hidden\n</style>",
                "<textarea>\n\n## Acceptance Criteria\n- PRD-AC-textarea: hidden\n</textarea>",
                "<!--\n\n## Acceptance Criteria\n- PRD-AC-comment: hidden\n-->",
                "<?example\n\n## Acceptance Criteria\n- PRD-AC-pi: hidden\n?>",
                "<!DOCTYPE\n\n## Acceptance Criteria\n- PRD-AC-declaration: hidden\n>",
                "<![CDATA[\n\n## Acceptance Criteria\n- PRD-AC-cdata: hidden\n]]>",
            )
        )
        visible = "## Acceptance Criteria\n\n- PRD-AC-001: Visible after close."
        self.assertEqual(
            frozenset({"PRD-AC-001"}),
            contract.derive_prd_acceptance_inventory(
                hidden + "\n" + visible, label="PRD"
            ),
        )

        # Generic HTML blocks remain deliberately blank-terminated.
        self.assertEqual(
            frozenset({"PRD-AC-002"}),
            contract.derive_prd_acceptance_inventory(
                "<div>\n## Acceptance Criteria\n- PRD-AC-hidden: hidden\n\n"
                "## Acceptance Criteria\n- PRD-AC-002: Visible after blank.",
                label="PRD",
            ),
        )

    def test_section_allows_only_plain_single_id_declarations(self) -> None:
        invalid_lines = (
            "PRD-AC-001: no list marker",
            "- `PRD-AC-001`: code-wrapped ID",
            "- PRD-AC-001: [linked](destination)",
            "- PRD-AC-001: <span>hidden</span>",
            "- PRD-AC-001:",
            "- PRD-AC-001: maps PRD-AC-002 too",
            "- PRD-AC-001: *emphasized outcome*",
            "- PRD-AC-001: under_scored outcome",
            "- PRD-AC-001: ~~struck outcome~~",
            "- PRD-AC-001: escaped \\* marker",
            "- PRD-AC-001: encoded &amp; outcome",
            "Narrative prose is ambiguous here.",
        )
        for line in invalid_lines:
            with self.subTest(line=line), self.assertRaises(ValueError):
                contract.derive_prd_acceptance_inventory(
                    "## Acceptance Criteria\n\n" + line, label="PRD"
                )

    def test_duplicate_declarations_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "repeats criterion"):
            contract.derive_prd_acceptance_inventory(
                "## Acceptance Criteria\n\n"
                "- PRD-AC-001: First.\n"
                "- PRD-AC-001: Second.\n",
                label="PRD",
            )

    def test_plan_extraction_is_visible_literal_and_rejects_ranges(self) -> None:
        text = """- PRD-AC-001
```md
- PRD-AC-hidden
```
<!-- PRD-AC-comment -->
- PRD-AC-save-v2
"""
        self.assertEqual(
            ["PRD-AC-001", "PRD-AC-save-v2"],
            contract.extract_literal_acceptance_ids(text, label="requirements"),
        )
        for value in (
            "PRD-AC-001..003",
            "PRD-AC-001 to PRD-AC-003",
            "PRD-AC-001 — save-v2",
            "PRD-AC-001\n  to\n  PRD-AC-003",
            "PRD-AC-001\n  .. 003",
            "PRD-AC-save-v1\n  to save-v2",
        ):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "range"):
                contract.extract_literal_acceptance_ids(value, label="requirements")
        self.assertEqual(
            ["PRD-AC-001", "PRD-AC-002"],
            contract.extract_literal_acceptance_ids(
                "- PRD-AC-001\nto support players\n- PRD-AC-002",
                label="requirements",
            ),
        )

        with self.assertRaisesRegex(ValueError, "repeats acceptance ID row"):
            contract.extract_literal_acceptance_ids(
                "- PRD-AC-001\n- PRD-AC-001", label="requirements"
            )

    def test_unicode_neighbors_do_not_form_literal_ids(self) -> None:
        for value in (
            "xPRD-AC-001",
            "PRD-AC-001_suffix",
            "яPRD-AC-001",
            "PRD-AC-001я",
            "PRD-AC-001\u200d",
        ):
            with self.subTest(value=value):
                self.assertEqual(
                    [], contract.extract_literal_acceptance_ids(value, label="requirements")
                )

    def test_exact_union_allows_cross_slice_overlap_but_not_loss(self) -> None:
        inventory = frozenset({"PRD-AC-001", "PRD-AC-002"})
        # Overlap is explicit: one end-to-end criterion may span sequential slices.
        contract.require_complete_acceptance_coverage(
            {
                "SLICE-001": {"PRD-AC-001"},
                "SLICE-002": {"PRD-AC-001", "PRD-AC-002"},
            },
            inventory,
            label="plan",
        )
        with self.assertRaisesRegex(ValueError, "missing PRD-AC-002"):
            contract.require_complete_acceptance_coverage(
                {"SLICE-001": {"PRD-AC-001"}}, inventory, label="plan"
            )
        with self.assertRaisesRegex(ValueError, "unknown PRD-AC-003"):
            contract.require_complete_acceptance_coverage(
                {"SLICE-001": {"PRD-AC-001", "PRD-AC-002", "PRD-AC-003"}},
                inventory,
                label="plan",
            )


if __name__ == "__main__":
    unittest.main()
