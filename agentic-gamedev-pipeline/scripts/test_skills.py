#!/usr/bin/env python3
"""Check the current skill package's metadata and local references.

Requires PyYAML, also used by Codex skill-creator's syntax validator.
This suite reads package files only; it does not run a workflow or product.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit

sys.dont_write_bytecode = True

import yaml


BUNDLE = Path(__file__).resolve().parents[1]
REPOSITORY = BUNDLE.parent
SKILLS = BUNDLE / "skills"
PUBLIC_SKILLS = {
    "gamedev-requirements",
    "gamedev-specification",
    "gamedev-development-plan",
    "gamedev-orchestrator",
    "gamedev-pipeline",
    "gamedev-engineer",
    "gamedev-qa",
    "gamedev-review",
    "gamedev-documentation-finisher",
}
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


class SkillPackageTests(unittest.TestCase):
    def test_discoverable_entry_points(self) -> None:
        entries = {path.parent.name: path for path in SKILLS.glob("*/SKILL.md")}
        self.assertEqual(PUBLIC_SKILLS, set(entries))
        for name, path in entries.items():
            with self.subTest(skill=name):
                text = path.read_text(encoding="utf-8")
                self.assertTrue(text.startswith("---\n"))
                frontmatter, body = text[4:].split("\n---\n", 1)
                metadata = yaml.safe_load(frontmatter)
                self.assertEqual(name, metadata["name"])
                self.assertRegex(name, r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
                self.assertIsInstance(metadata["description"], str)
                self.assertTrue(metadata["description"].strip())
                self.assertTrue(body.strip())

    def test_explicit_invocation_and_ui_metadata(self) -> None:
        for name in sorted(PUBLIC_SKILLS):
            with self.subTest(skill=name):
                path = SKILLS / name / "agents" / "openai.yaml"
                metadata = yaml.safe_load(path.read_text(encoding="utf-8"))
                self.assertIs(metadata["policy"]["allow_implicit_invocation"], False)
                interface = metadata["interface"]
                self.assertTrue(interface["display_name"].strip())
                self.assertGreaterEqual(len(interface["short_description"]), 25)
                self.assertLessEqual(len(interface["short_description"]), 64)
                self.assertIn(f"${name}", interface["default_prompt"])

    def test_local_references_and_supporting_document_reachability(self) -> None:
        linked_files: set[Path] = set()
        documents = list(BUNDLE.rglob("*.md")) + [REPOSITORY / "README.md"]
        for document in documents:
            for match in MARKDOWN_LINK.finditer(document.read_text(encoding="utf-8")):
                href = match.group(1).strip().strip("<>")
                if urlsplit(href).scheme or href.startswith("#"):
                    continue
                target = (document.parent / unquote(href.split("#", 1)[0])).resolve()
                with self.subTest(document=document.relative_to(REPOSITORY), href=href):
                    self.assertTrue(target.is_relative_to(REPOSITORY))
                    self.assertTrue(target.is_file(), f"Missing local reference: {target}")
                linked_files.add(target)
        supporting = {
            path.resolve()
            for directory in SKILLS.glob("*/references")
            for path in directory.rglob("*.md")
        } | {
            path.resolve()
            for directory in SKILLS.glob("*/assets")
            for path in directory.rglob("*.md")
        }
        self.assertFalse(supporting - linked_files, "Unreferenced supporting instructions")

    def test_bundle_version_is_identified(self) -> None:
        version = (BUNDLE / "VERSION").read_text(encoding="utf-8").strip()
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        for name in ("README.md", "CHANGELOG.md"):
            with self.subTest(document=name):
                self.assertIn(version, (REPOSITORY / name).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
