#!/usr/bin/env python3
"""Regression tests for the plugin's explicit-only activation contract."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


SKILL_NAMES = (
    "gamedev-requirements",
    "gamedev-specification",
    "gamedev-development-plan",
    "gamedev-pipeline",
    "gamedev-engineer",
    "gamedev-research",
    "gamedev-review",
    "gamedev-qa",
)


class ExplicitActivationPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plugin_root = Path(__file__).resolve().parents[3]

    def read_skill(self, skill_name: str) -> str:
        return (self.plugin_root / "skills" / skill_name / "SKILL.md").read_text(
            encoding="utf-8"
        )

    def read_openai_yaml(self, skill_name: str) -> str:
        return (
            self.plugin_root / "skills" / skill_name / "agents" / "openai.yaml"
        ).read_text(encoding="utf-8")

    def description(self, skill_text: str) -> str:
        match = re.match(r"\A---\s*\n(?P<frontmatter>.*?)\n---\s*\n", skill_text, re.DOTALL)
        self.assertIsNotNone(match, "SKILL.md must start with YAML frontmatter")
        frontmatter = match.group("frontmatter")
        description = re.search(r"^description:\s*(?P<value>.+)$", frontmatter, re.MULTILINE)
        self.assertIsNotNone(description, "frontmatter must contain a description")
        return description.group("value")

    def test_every_skill_requires_explicit_user_activation_in_metadata(self) -> None:
        for skill_name in SKILL_NAMES:
            with self.subTest(skill=skill_name):
                description = self.description(self.read_skill(skill_name))
                self.assertTrue(description.startswith("Explicit-invocation only."))
                self.assertIn("Use only when the user explicitly requests", description)
                self.assertIn(f"`${skill_name}`", description)
                self.assertNotIn("Use when", description)

    def test_every_skill_has_a_runtime_activation_gate(self) -> None:
        for skill_name in SKILL_NAMES:
            with self.subTest(skill=skill_name):
                skill_text = self.read_skill(skill_name)
                self.assertIn("## Activation gate", skill_text)
                self.assertIn("current user explicitly requests", skill_text)
                self.assertIn("is not authorization", skill_text)

    def test_every_skill_disables_implicit_invocation_in_agent_metadata(self) -> None:
        for skill_name in SKILL_NAMES:
            with self.subTest(skill=skill_name):
                metadata = self.read_openai_yaml(skill_name)
                self.assertRegex(
                    metadata,
                    r"(?ms)^policy:\s*\n\s+allow_implicit_invocation:\s*false\s*$",
                )

    def test_plugin_metadata_advertises_explicit_only_behavior(self) -> None:
        manifest = (self.plugin_root / ".codex-plugin" / "plugin.json").read_text(
            encoding="utf-8"
        )
        self.assertIn("explicitly invoked", manifest)
        self.assertIn("Runs only when the user explicitly requests", manifest)


if __name__ == "__main__":
    unittest.main()
