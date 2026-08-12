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
    "references/lifecycle-projection-recovery.md",
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
        description = re.search(
            r"^description:\s*(?P<value>.+)$",
            match.group("frontmatter"),
            re.MULTILINE,
        )
        self.assertIsNotNone(description, "frontmatter must contain a description")
        return description.group("value")

    def test_descriptions_preserve_explicit_activation_semantics(self) -> None:
        for skill_name in STAGE_TOKENS:
            with self.subTest(skill=skill_name):
                description = self.description(self.read_skill(skill_name))
                self.assertTrue(description.startswith("Explicit-invocation only."))
                self.assertIn("Use only when the user explicitly requests", description)
                self.assertIn(f"`${skill_name}`", description)
                self.assertRegex(description, r"Do not activate|Never trigger")
                if skill_name != "gamedev-pipeline":
                    self.assertIn("`$gamedev-pipeline` Director delegates", description)

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
        self.assertIn("distinct delegated subagent context", contract)
        self.assertIn("One delegated agent performs one named specialized role only", contract)

    def test_pipeline_director_is_orchestration_only_and_compaction_safe(self) -> None:
        skill = self.read_skill("gamedev-pipeline")
        protocol = (
            self.plugin_root
            / "skills"
            / "gamedev-pipeline"
            / "references"
            / "pipeline-protocol.md"
        ).read_text(encoding="utf-8")
        self.assertIn("The Director is orchestration-only", skill)
        self.assertIn("distinct non-Director subagent", skill)
        self.assertIn("no inherited chat history", skill)
        self.assertIn("context compaction", skill)
        self.assertIn("never substitutes itself for a role", protocol)
        self.assertIn("A lost conversational window is not user input", protocol)

    def test_pipeline_instruction_bundles_are_structurally_progressive(self) -> None:
        pipeline_root = self.plugin_root / "skills" / "gamedev-pipeline"
        skill_text = (pipeline_root / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Do not preload conditional references", skill_text)

        routed_paths = PIPELINE_ALWAYS_CORE + PIPELINE_CONDITIONAL_REFERENCES
        self.assertEqual(len(routed_paths), len(set(routed_paths)))
        for path in routed_paths:
            with self.subTest(existing_reference=path):
                self.assertTrue((pipeline_root / path).is_file())

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

        trigger_by_path = {
            "references/role-artifacts-and-context.md": "Before the first capsule, lease, semantic packet, revision manifest, or handoff",
            "references/engineering-and-coverage.md": "Before slice research, coverage, engineering, normative docs, product remediation, or scope rebaseline",
            "references/review-qa-and-recovery.md": "Before convergence, Final Review, recovery, QA, derived docs, documentation closure, or readiness",
            "references/severity-and-readiness.md": "Before classifying any finding/gate/risk or evaluating readiness",
            "references/deferred-findings.md": "Before routing a supported out-of-scope candidate",
            "references/lifecycle-projection-recovery.md": "On generated dashboard revision drift",
        }
        conditional_lines = {
            linked_path.search(line).group(1): line
            for line in conditional_block.splitlines()
            if linked_path.search(line)
        }
        self.assertEqual(set(PIPELINE_CONDITIONAL_REFERENCES), set(conditional_lines))
        for path, trigger in trigger_by_path.items():
            with self.subTest(exact_route_trigger=path):
                self.assertIn(trigger, conditional_lines[path])

        always_text = "\n".join(
            (pipeline_root / path).read_text(encoding="utf-8")
            for path in PIPELINE_ALWAYS_CORE
        )
        unique_contract = {
            "references/role-artifacts-and-context.md": (
                "# Role artifacts and bounded context",
                "capsule_plus_referenced_files",
            ),
            "references/engineering-and-coverage.md": (
                "# Engineering and coverage phases",
                "research_not_required",
            ),
            "references/review-qa-and-recovery.md": (
                "# Review, QA, documentation closure, and recovery",
                "register all supported candidates",
            ),
            "references/severity-and-readiness.md": (
                "# Severity and readiness",
                "blocks_required_support_contract",
            ),
            "references/deferred-findings.md": (
                "# Deferred findings backlog",
                "backlog-scope-check",
            ),
            "references/lifecycle-projection-recovery.md": (
                "# Lifecycle projection recovery",
                "append-only SHA-bound receipt",
            ),
        }
        for path, (heading, marker) in unique_contract.items():
            with self.subTest(distinct_conditional_contract=path):
                conditional_text = (pipeline_root / path).read_text(encoding="utf-8")
                self.assertEqual(heading, conditional_text.splitlines()[0])
                self.assertIn(marker, conditional_text)
                self.assertNotIn(heading, always_text)
                self.assertNotIn(marker, always_text)

        lifecycle_path = "references/lifecycle-projection-recovery.md"
        self.assertIn(lifecycle_path, PIPELINE_CONDITIONAL_REFERENCES)
        protocol = (pipeline_root / "references" / "pipeline-protocol.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "](lifecycle-projection-recovery.md)",
            protocol,
        )
        lifecycle = (pipeline_root / lifecycle_path).read_text(encoding="utf-8")
        for invariant in (
            "no active write lease or pending Engineer completion",
            "exact active remediation batch",
            "unchanged support and evidence identities",
            "append-only SHA-bound receipt",
            "Unused Engineer capsules",
            "Component Review credits",
            "next Engineer capsule",
            "Pause/Continue",
        ):
            with self.subTest(lifecycle_invariant=invariant):
                self.assertIn(invariant, lifecycle)

        telemetry_contract = (
            pipeline_root / "references" / "role-artifacts-and-context.md"
        ).read_text(encoding="utf-8")
        self.assertIn("capsule_plus_referenced_files", telemetry_contract)
        self.assertIn("Never report it as total agent context", telemetry_contract)
        self.assertIn("structural progressive disclosure", telemetry_contract)

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

    def test_bundle_is_skill_only_without_plugin_manifest(self) -> None:
        self.assertFalse((self.plugin_root / ".codex-plugin" / "plugin.json").exists())
        self.assertEqual(
            set(STAGE_TOKENS),
            {
                path.parent.name
                for path in (self.plugin_root / "skills").glob("*/SKILL.md")
            },
        )


if __name__ == "__main__":
    unittest.main()
