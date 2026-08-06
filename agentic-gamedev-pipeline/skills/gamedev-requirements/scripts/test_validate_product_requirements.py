#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("validate_product_requirements.py")
TEMPLATE = Path(__file__).parent.parent / "assets" / "product-requirements.md"


class ProductRequirementsValidatorTests(unittest.TestCase):
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
            "## Open Questions\n", "## Open Questions\n\n- PRD-OQ-001 [blocking]: Выбрать платформу.\n"
        )
        result = self.run_validator(text, approved=True, expected=1)
        self.assertIn("approved PRD contains a blocking open question", result["errors"])

    def test_duplicate_ids_are_rejected(self) -> None:
        text = self.approved_document().replace(
            "## Risks\n", "## Risks\n\n- PRD-REQ-001: Повторный ID.\n"
        )
        result = self.run_validator(text, approved=True, expected=1)
        self.assertIn("duplicate identifier: PRD-REQ-001", result["errors"])

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
