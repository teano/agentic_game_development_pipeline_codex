#!/usr/bin/env python3
"""Regression tests for explicit activation and stage handoff semantics."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


STAGE_TOKENS = {
    "gamedev-requirements": "PRD_READY",
    "gamedev-specification": "SPEC_READY",
    "gamedev-development-plan": "PLAN_READY",
    "gamedev-pipeline": "PRODUCTION_READY_CANDIDATE",
    "gamedev-engineer": "ENGINEERING_COMPLETE",
    "gamedev-research": "RESEARCH_COMPLETE",
    "gamedev-review": "REVIEW_COMPLETE",
    "gamedev-qa": "QA_COMPLETE",
    "gamedev-decision-recorder": "RECORDING_COMPLETE",
    "gamedev-coverage-steward": "COVERAGE_COMPLETE",
    "gamedev-documentation-finisher": "DOCUMENTATION_COMPLETE",
}

PIPELINE_ALWAYS_CORE = (
    "SKILL.md",
    "references/stage-handoff-invariant.md",
    "references/pipeline-protocol.md",
)
PIPELINE_CONDITIONAL_REFERENCES = (
    "references/role-artifacts-and-context.md",
    "references/engineering-and-coverage.md",
    "references/review-qa-and-recovery.md",
    "references/severity-and-readiness.md",
    "references/deferred-findings.md",
)
STATIC_DESCRIPTION_LIST_MAX_CHARS = 4000
STATIC_INITIAL_CORE_MAX_CHARS = 16000
STATIC_DIRECT_ROUTE_MAX_CHARS = 24000
STATIC_ALL_ROUTES_MAX_CHARS = 50000


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
        description = re.search(
            r"^description:\s*(?P<value>.+)$",
            match.group("frontmatter"),
            re.MULTILINE,
        )
        self.assertIsNotNone(description, "frontmatter must contain a description")
        return description.group("value")

    def test_descriptions_preserve_explicit_activation_semantics(self) -> None:
        total_chars = 0
        for skill_name in STAGE_TOKENS:
            with self.subTest(skill=skill_name):
                description = self.description(self.read_skill(skill_name))
                total_chars += len(description)
                self.assertTrue(description.startswith("Explicit-invocation only."))
                self.assertIn("Use only when the user explicitly requests", description)
                self.assertIn(f"`${skill_name}`", description)
                self.assertRegex(description, r"Do not activate|Never trigger")
                if skill_name != "gamedev-pipeline":
                    self.assertIn("`$gamedev-pipeline` Director delegates", description)
        self.assertLessEqual(total_chars, STATIC_DESCRIPTION_LIST_MAX_CHARS)

    def test_runtime_gate_and_shared_handoff_contract_are_present(self) -> None:
        shared_link = "stage-handoff-invariant.md"
        for skill_name in STAGE_TOKENS:
            with self.subTest(skill=skill_name):
                skill_text = self.read_skill(skill_name)
                self.assertIn("## Activation gate", skill_text)
                self.assertIn(shared_link, skill_text)
                self.assertIn("NEXT_ACTION", skill_text)
                self.assertIn(STAGE_TOKENS[skill_name], skill_text)

    def test_specialized_stages_do_not_execute_cross_stage_routes(self) -> None:
        forbidden = re.compile(
            r"(?i)\b(?:invoke|run|launch|spawn|delegate|activate|start)\b[^\n]{0,100}`\$gamedev-"
        )
        for skill_name in STAGE_TOKENS:
            if skill_name == "gamedev-pipeline":
                continue
            with self.subTest(skill=skill_name):
                skill_root = self.plugin_root / "skills" / skill_name
                routed_contract = "\n".join(
                    path.read_text(encoding="utf-8")
                    for path in sorted(skill_root.rglob("*.md"))
                )
                self.assertIsNone(forbidden.search(routed_contract))
        self.assertNotIn(
            "$skill-specification-pipeline",
            "\n".join(
                path.read_text(encoding="utf-8")
                for path in sorted(
                    (self.plugin_root / "skills" / "gamedev-requirements").rglob(
                        "*.md"
                    )
                )
            ),
        )

    def test_shared_handoff_contract_names_the_only_activators(self) -> None:
        contract = (
            self.plugin_root
            / "skills"
            / "gamedev-pipeline"
            / "references"
            / "stage-handoff-invariant.md"
        ).read_text(encoding="utf-8")
        self.assertIn("current user explicitly invokes", contract)
        self.assertIn("active `$gamedev-pipeline` Director", contract)
        self.assertIn("routing data, not permission", contract)
        self.assertIn("PRD_READY -> SPEC_READY -> PLAN_READY -> runtime pipeline", contract)

    def test_pipeline_static_instruction_bundles_are_progressive_and_bounded(self) -> None:
        pipeline_root = self.plugin_root / "skills" / "gamedev-pipeline"

        def bundle_chars(paths: tuple[str, ...]) -> int:
            return sum(
                len((pipeline_root / path).read_text(encoding="utf-8"))
                for path in paths
            )

        skill_text = (pipeline_root / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Do not preload conditional references", skill_text)

        always_block = skill_text.split(
            "Read these compact always-core contracts before startup:", 1
        )[1].split("## Load phase contracts only when needed", 1)[0]
        conditional_block = skill_text.split(
            "## Load phase contracts only when needed", 1
        )[1].split("Do not preload conditional references", 1)[0]
        linked_path = re.compile(r"\]\((references/[^)]+)\)")
        self.assertEqual(
            list(PIPELINE_ALWAYS_CORE[1:]), linked_path.findall(always_block)
        )
        self.assertEqual(
            list(PIPELINE_CONDITIONAL_REFERENCES),
            linked_path.findall(conditional_block),
        )

        initial_chars = bundle_chars(PIPELINE_ALWAYS_CORE)
        direct_route_chars = {
            path: bundle_chars(PIPELINE_ALWAYS_CORE + (path,))
            for path in PIPELINE_CONDITIONAL_REFERENCES
        }
        worst_case_chars = bundle_chars(
            PIPELINE_ALWAYS_CORE + PIPELINE_CONDITIONAL_REFERENCES
        )
        # These are repository-owned static skill files only. Dynamic system
        # instructions, conversation history, and tool output are deliberately
        # not represented as measured context.
        self.assertLessEqual(initial_chars, STATIC_INITIAL_CORE_MAX_CHARS)
        for path, character_count in direct_route_chars.items():
            with self.subTest(direct_route=path):
                self.assertLessEqual(
                    character_count, STATIC_DIRECT_ROUTE_MAX_CHARS
                )
        self.assertLessEqual(worst_case_chars, STATIC_ALL_ROUTES_MAX_CHARS)

        telemetry_contract = (
            pipeline_root / "references" / "role-artifacts-and-context.md"
        ).read_text(encoding="utf-8")
        self.assertIn("capsule_plus_referenced_files", telemetry_contract)
        self.assertIn("Never report it as total agent context", telemetry_contract)
        self.assertIn("separate CI static-instruction budget", telemetry_contract)

    def test_every_skill_disables_implicit_invocation_in_agent_metadata(self) -> None:
        for skill_name in STAGE_TOKENS:
            with self.subTest(skill=skill_name):
                metadata = self.read_openai_yaml(skill_name)
                self.assertRegex(
                    metadata,
                    r"(?ms)^policy:\s*\n\s+allow_implicit_invocation:\s*false\s*$",
                )
                if skill_name != "gamedev-pipeline":
                    self.assertIn("NEXT_ACTION", metadata)
                    self.assertRegex(metadata, r"\bstop\b")

    def test_plugin_metadata_advertises_explicit_only_behavior(self) -> None:
        manifest = (self.plugin_root / ".codex-plugin" / "plugin.json").read_text(
            encoding="utf-8"
        )
        self.assertIn("explicitly invoked", manifest)
        self.assertIn("Runs only when the user explicitly requests", manifest)


if __name__ == "__main__":
    unittest.main()
