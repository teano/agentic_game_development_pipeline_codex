#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).with_name("validate_product_requirements.py")
TEMPLATE = Path(__file__).parent.parent / "assets" / "product-requirements.md"
VALIDATOR_SPEC = importlib.util.spec_from_file_location("prd_validator", SCRIPT)
if VALIDATOR_SPEC is None or VALIDATOR_SPEC.loader is None:
    raise RuntimeError("Cannot load PRD validator")
validator = importlib.util.module_from_spec(VALIDATOR_SPEC)
VALIDATOR_SPEC.loader.exec_module(validator)


class ProductRequirementsValidatorTests(unittest.TestCase):
    def validate_direct(self, text: str, approved: bool = True) -> dict:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "product-requirements.md"
            path.write_text(text, encoding="utf-8")
            return validator.validate(path, approved)

    def run_validator(self, text: str, approved: bool = False, expected: int = 0) -> dict:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "product-requirements.md"
            path.write_text(text, encoding="utf-8")
            command = [sys.executable, str(SCRIPT), str(path)]
            if approved:
                command.append("--require-approved")
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(expected, result.returncode, msg=result.stdout or result.stderr)
            return json.loads(result.stdout)

    def approved_document(self) -> str:
        text = TEMPLATE.read_text(encoding="utf-8")
        text = text.replace("status: draft", "status: approved")
        text = text.replace("language: unspecified", "language: Russian")
        text = text.replace("approved_at: null", "approved_at: 2026-08-03T12:00:00Z")
        replacements = {
            "## Product Outcome\n": "## Product Outcome\n\nПроверяемый результат.\n",
            "## Target Audience\n": "## Target Audience\n\nЦелевая аудитория.\n",
            "## Core Gameplay Loop\n": "## Core Gameplay Loop\n\nОсновной цикл.\n",
            "## Release Target\n": "## Release Target\n\nVertical slice.\n",
            "### In Scope\n": "### In Scope\n\nОсновной режим.\n",
            "### Out of Scope\n": "### Out of Scope\n\nСетевая игра.\n",
            "## Functional Requirements\n": "## Functional Requirements\n\n- PRD-REQ-001: Игра запускается.\n",
            "## Quality Requirements\n": "## Quality Requirements\n\n- PRD-NFR-001: Запуск не дольше 5 секунд.\n",
            "## Acceptance Criteria\n": "## Acceptance Criteria\n\n- PRD-AC-001: Запуск подтверждён сборкой.\n",
        }
        for source, replacement in replacements.items():
            text = text.replace(source, replacement)
        return text

    def test_draft_template_requires_language(self) -> None:
        result = self.run_validator(TEMPLATE.read_text(encoding="utf-8"), expected=1)
        self.assertIn("language must be specified", result["errors"])

    def test_complete_approved_document_passes(self) -> None:
        result = self.run_validator(self.approved_document(), approved=True)
        self.assertTrue(result["valid"])
        self.assertEqual(64, len(result["sha256"]))

    def test_approved_document_rejects_blocking_question(self) -> None:
        text = self.approved_document().replace(
            "## Open Questions\n", "## Open Questions\n\n- PRD-OQ-001: [blocking] Выбрать платформу.\n"
        )
        result = self.run_validator(text, approved=True, expected=1)
        self.assertIn("approved PRD contains a blocking open question", result["errors"])

    def test_duplicate_ids_are_rejected(self) -> None:
        text = self.approved_document().replace(
            "- PRD-REQ-001: Игра запускается.\n",
            "- PRD-REQ-001: Игра запускается.\n- PRD-REQ-001: Повторный ID.\n",
        )
        direct = self.validate_direct(text)
        result = self.run_validator(text, approved=True, expected=1)
        self.assertIn("duplicate identifier: PRD-REQ-001", direct["errors"])
        self.assertIn("duplicate identifier: PRD-REQ-001", result["errors"])

    def test_non_acceptance_references_outside_declaration_sections_are_legitimate(self) -> None:
        text = self.approved_document().replace(
            "## Risks\n",
            "## Risks\n\nTrace PRD-REQ-001, PRD-NFR-001, and PRD-OQ-001 [blocking].\n",
        )
        direct = self.validate_direct(text)
        cli = self.run_validator(text, approved=True)
        self.assertTrue(direct["valid"])
        self.assertTrue(cli["valid"])

    def test_reference_does_not_satisfy_required_canonical_declaration(self) -> None:
        text = self.approved_document().replace(
            "- PRD-NFR-001: Запуск не дольше 5 секунд.",
            "This paragraph only references PRD-NFR-001.",
        )
        direct = self.validate_direct(text)
        cli = self.run_validator(text, approved=True, expected=1)
        message = (
            "approved PRD requires at least one PRD-NFR declaration in Quality Requirements"
        )
        self.assertIn(message, direct["errors"])
        self.assertIn(message, cli["errors"])

    def test_only_canonical_open_question_declarations_block_approval(self) -> None:
        referenced = self.approved_document().replace(
            "## Assumptions\n",
            "## Assumptions\n\nPRD-OQ-001 [blocking] is cited only as historical context.\n",
        )
        self.assertTrue(self.validate_direct(referenced)["valid"])
        self.assertTrue(self.run_validator(referenced, approved=True)["valid"])

        declared = self.approved_document().replace(
            "## Open Questions\n",
            "## Open Questions\n\n- PRD-OQ-001: [blocking] Выбрать платформу.\n",
        )
        self.assertFalse(self.validate_direct(declared)["valid"])
        self.assertFalse(self.run_validator(declared, approved=True, expected=1)["valid"])

    def test_req_nfr_oq_declarations_require_exact_literal_rows_direct_and_cli(self) -> None:
        cases = (
            (
                "- PRD-REQ-001: Игра запускается.",
                "PRD-REQ-001: Игра запускается.",
                "PRD-REQ",
            ),
            (
                "- PRD-REQ-001: Игра запускается.",
                "- PRD-REQ-001",
                "PRD-REQ",
            ),
            (
                "- PRD-REQ-001: Игра запускается.",
                "- PRD-REQ-001:",
                "PRD-REQ",
            ),
            (
                "- PRD-REQ-001: Игра запускается.",
                "- PRD-REQ-001: **Игра запускается.**",
                "PRD-REQ",
            ),
            (
                "- PRD-REQ-001: Игра запускается.",
                "- PRD-REQ-001: ~~Игра запускается.~~",
                "PRD-REQ",
            ),
            (
                "- PRD-NFR-001: Запуск не дольше 5 секунд.",
                "* PRD-NFR-001: Запуск не дольше 5 секунд.",
                "PRD-NFR",
            ),
            (
                "- PRD-NFR-001: Запуск не дольше 5 секунд.",
                "- PRD-NFR-001 : Запуск не дольше 5 секунд.",
                "PRD-NFR",
            ),
            (
                "- PRD-NFR-001: Запуск не дольше 5 секунд.",
                "- PRD-NFR-001:Запуск не дольше 5 секунд.",
                "PRD-NFR",
            ),
            (
                "- PRD-NFR-001: Запуск не дольше 5 секунд.",
                "  - PRD-NFR-001: Запуск не дольше 5 секунд.",
                "PRD-NFR",
            ),
        )
        for canonical, invalid, prefix in cases:
            with self.subTest(invalid=invalid):
                text = self.approved_document().replace(canonical, invalid)
                direct = self.validate_direct(text)
                cli = self.run_validator(text, approved=True, expected=1)
                message = f"approved PRD requires at least one {prefix} declaration"
                self.assertTrue(any(message in error for error in direct["errors"]))
                self.assertTrue(any(message in error for error in cli["errors"]))

        invalid_open_question = self.approved_document().replace(
            "## Open Questions\n",
            "## Open Questions\n\n- PRD-OQ-001 [blocking]: legacy delimiter.\n",
        )
        self.assertFalse(self.validate_direct(invalid_open_question)["valid"])
        self.assertFalse(
            self.run_validator(invalid_open_question, approved=True, expected=1)["valid"]
        )

    def test_acceptance_references_outside_canonical_section_are_legitimate(self) -> None:
        text = self.approved_document().replace(
            "## Assumptions\n",
            "## Assumptions\n\nTrace PRD-AC-001 and example PRD-AC-not-authority.\n",
        )
        direct = self.validate_direct(text)
        cli = self.run_validator(text, approved=True)
        self.assertTrue(direct["valid"])
        self.assertTrue(cli["valid"])

    def test_markdown_literal_headings_and_ids_do_not_create_authority(self) -> None:
        examples = (
            "```md\n## Acceptance Criteria\n- PRD-AC-fenced: no\n```",
            "~~~~ markdown\n## Acceptance Criteria\n- PRD-AC-fenced: no\n~~~~",
            "    ## Acceptance Criteria\n    - PRD-AC-indented: no",
            "> ## Acceptance Criteria\n> - PRD-AC-quoted: no",
        )
        for example in examples:
            with self.subTest(example=example):
                text = self.approved_document().replace(
                    "## Risks\n", f"## Risks\n\n{example}\n"
                )
                self.assertTrue(self.validate_direct(text)["valid"])
                self.assertTrue(self.run_validator(text, approved=True)["valid"])

    def test_fenced_only_near_and_blockquote_headings_fail_direct_and_cli(self) -> None:
        invalid_headings = (
            "```\n## Acceptance Criteria\n- PRD-AC-001: hidden\n```",
            "    ## Acceptance Criteria\n    - PRD-AC-001: hidden",
            "> ## Acceptance Criteria\n> - PRD-AC-001: hidden",
            "### Acceptance Criteria\n- PRD-AC-001: near",
            "## Acceptance Criteria \n- PRD-AC-001: near",
        )
        for replacement in invalid_headings:
            with self.subTest(replacement=replacement):
                text = self.approved_document().replace(
                    "## Acceptance Criteria\n\n- PRD-AC-001: Запуск подтверждён сборкой.",
                    replacement,
                )
                self.assertFalse(self.validate_direct(text)["valid"])
                self.assertFalse(self.run_validator(text, approved=True, expected=1)["valid"])

    def test_acceptance_declaration_and_range_matrix_fails_direct_and_cli(self) -> None:
        invalid_declarations = (
            "- PRD-AC-001",
            "- PRD-AC-001:",
            "- PRD-AC-001: first\n- PRD-AC-001: duplicate",
            "- PRD-AC-001 and PRD-AC-002: multiple",
            "- PRD-AC-001_invalid: adjacent invalid token",
            "- PRD-AC-001: ~~rendered strikethrough~~",
            "- PRD-AC-001..003: short range",
            "- PRD-AC-start-v1 … PRD-AC-end-v2: full Unicode range",
            "- PRD-AC-start-v1 to end-v2: textual short range",
            "- PRD-AC-start-v1\n  ..\n  end-v2: multiline range",
            "- PRD-AC-start-v1 to\n  PRD-AC-end-v2: multiline textual range",
        )
        needle = "- PRD-AC-001: Запуск подтверждён сборкой."
        for declaration in invalid_declarations:
            with self.subTest(declaration=declaration):
                text = self.approved_document().replace(needle, declaration)
                self.assertFalse(self.validate_direct(text)["valid"])
                self.assertFalse(self.run_validator(text, approved=True, expected=1)["valid"])

    def test_public_alnum_hyphen_acceptance_id_passes_direct_and_cli(self) -> None:
        text = self.approved_document().replace(
            "- PRD-AC-001: Запуск подтверждён сборкой.",
            "- PRD-AC-save-v2: Запуск подтверждён сборкой.",
        )
        self.assertTrue(self.validate_direct(text)["valid"])
        self.assertTrue(self.run_validator(text, approved=True)["valid"])

    def test_structural_html_and_exact_rendering_matrix_direct_and_cli(self) -> None:
        needle = "- PRD-AC-001: Запуск подтверждён сборкой."
        hidden_blocks = (
            "<!--\n## Acceptance Criteria\n- PRD-AC-hidden: no\n-->",
            "<pre>\n## Acceptance Criteria\n- PRD-AC-hidden: no\n</pre>",
            "<script>\n## Acceptance Criteria\n- PRD-AC-hidden: no\n</script>",
        )
        for hidden in hidden_blocks:
            with self.subTest(hidden=hidden):
                text = self.approved_document().replace(needle, needle + "\n" + hidden)
                self.assertTrue(self.validate_direct(text)["valid"])
                self.assertTrue(self.run_validator(text, approved=True)["valid"])
        declarations = (
            ("- PRD-AC-visible-v2: Visible Unicode 世界", True),
            ("- `PRD-AC-001: unmatched", False),
            ("- PRD-AC-001: unmatched `code", False),
            ("- PRD-AC-001: <!-- hidden -->", False),
            ("- PRD-AC-001: <br>", False),
            ("- PRD-AC-001: [](https://example.invalid)", False),
            ("- PRD-AC-001\u200d: adjacent join control", False),
        )
        for declaration, valid in declarations:
            with self.subTest(declaration=declaration):
                text = self.approved_document().replace(needle, declaration)
                self.assertEqual(valid, self.validate_direct(text)["valid"])
                self.assertEqual(
                    valid,
                    self.run_validator(text, approved=True, expected=0 if valid else 1)["valid"],
                )

    def test_commonmark_sixth_audit_matrix_direct_and_cli(self) -> None:
        needle = "- PRD-AC-001: Запуск подтверждён сборкой."
        hidden = (
            "<textarea>\n## Acceptance Criteria\n- PRD-AC-hidden: no\n</textarea>",
            "<?pi\n## Acceptance Criteria\n?>",
            "<!DECL\n## Acceptance Criteria\n>",
            "<![CDATA[\n## Acceptance Criteria\n]]>",
            "<custom-tag>\n## Acceptance Criteria\n- PRD-AC-hidden: no\n\n",
        )
        for block in hidden:
            with self.subTest(block=block):
                text = self.approved_document().replace(needle, needle + "\n" + block)
                self.assertTrue(self.validate_direct(text)["valid"])
                self.assertTrue(self.run_validator(text, approved=True)["valid"])
        invalid = (
            "- PRD-AC-001: <template>hidden</template>",
            "- PRD-AC-001: ``unmatched `",
            "- PRD-AC-001\u200b: boundary",
            "- PRD-AC-001: visible\u2028## Risks",
        )
        for declaration in invalid:
            with self.subTest(declaration=declaration):
                text = self.approved_document().replace(needle, declaration)
                self.assertFalse(self.validate_direct(text)["valid"])
                self.assertFalse(self.run_validator(text, approved=True, expected=1)["valid"])
        ranged = self.approved_document().replace(
            needle, "- PRD-AC-001 **..** `003`: range"
        )
        self.assertFalse(self.validate_direct(ranged)["valid"])
        self.assertFalse(self.run_validator(ranged, approved=True, expected=1)["valid"])

    def test_frontmatter_rejects_extra_keys_and_non_utc_approval(self) -> None:
        text = self.approved_document().replace(
            "approved_at: 2026-08-03T12:00:00Z",
            "approved_at: 2026-08-03T12:00:00+03:00\nowner: team",
        )
        result = self.run_validator(text, approved=True, expected=1)
        self.assertIn("unexpected frontmatter key: owner", result["errors"])
        self.assertIn("approved_at must be an ISO-8601 UTC timestamp", result["errors"])

    def test_draft_requires_null_approval_timestamp(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8").replace(
            "language: unspecified", "language: Russian"
        ).replace("approved_at: null", "approved_at: 2026-08-03T12:00:00Z")
        result = self.run_validator(text, expected=1)
        self.assertIn("draft PRD must use approved_at: null", result["errors"])

    def test_duplicate_heading_is_rejected(self) -> None:
        text = self.approved_document().replace(
            "## Risks\n", "## Risks\n\n## Risks\n"
        )
        result = self.run_validator(text, approved=True, expected=1)
        self.assertIn("duplicate heading: ## Risks", result["errors"])


if __name__ == "__main__":
    unittest.main()
