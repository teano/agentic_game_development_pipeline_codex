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
    "gamedev-recovery-remediator": "RECOVERY_COMPLETE",
}

PIPELINE_ALWAYS_CORE = (
    "SKILL.md",
    "references/stage-handoff-invariant.md",
    "references/pipeline-protocol.md",
)
PIPELINE_CONDITIONAL_REFERENCES = (
    "references/engineering-and-coverage.md",
    "references/review-qa-and-recovery.md",
    "references/severity-and-readiness.md",
    "references/deferred-findings.md",
    "references/lifecycle-projection-recovery.md",
)
PIPELINE_ALWAYS_CORE_MAX_BYTES = 16_384
RUNTIME_ROLE_SKILLS = {
    "decision_recorder": ("gamedev-decision-recorder",),
    "documentation_finisher": ("gamedev-documentation-finisher",),
    "engineer": ("gamedev-engineer",),
    "recovery_remediator": ("gamedev-recovery-remediator",),
    "reviewer": ("gamedev-review", "gamedev-qa"),
}
WORKER_SCHEMA_REFERENCES = {
    "gamedev-engineer": "../gamedev-pipeline/references/semantic-write-packet.md",
    "gamedev-documentation-finisher": "../gamedev-pipeline/references/semantic-write-packet.md",
    "gamedev-recovery-remediator": "../gamedev-pipeline/references/semantic-write-packet.md",
    "gamedev-review": "references/review-output-contract.md",
    "gamedev-qa": "references/qa-output-contract.md",
    "gamedev-research": "references/research-bundle-contract.md",
}


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
                if skill_name not in {"gamedev-pipeline", "gamedev-coverage-steward"}:
                    self.assertIn("`$gamedev-pipeline` Director delegates", description)
                if skill_name == "gamedev-coverage-steward":
                    self.assertIn("standalone advisory", description)
                    self.assertNotIn("Director delegates", description)

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
        self.assertIn(
            "one logical independent non-writer verifier ID across sequential convergence Review, Final Review, QA",
            contract,
        )
        self.assertIn("Every phase starts a new isolated session", contract)
        self.assertIn("must never be the Engineer or any writer", contract)

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
        self.assertIn("real non-Director worker", skill)
        self.assertIn("no inherited Director or worker chat history", skill)
        self.assertIn("After compaction/replacement", skill)
        self.assertIn("never substitutes itself for a specialized role", protocol)
        self.assertIn("prior conversation is never retained or supplied", protocol)

    def test_engineer_rejects_unrelated_allowed_path_cleanup(self) -> None:
        skill = self.read_skill("gamedev-engineer")
        self.assertIn("unrelated allowed-path cleanup", skill)
        self.assertIn("is not an `assigned_goal_effect`", skill)
        self.assertIn("candidate for Director backlog routing", skill)

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
            "references/engineering-and-coverage.md": "Before slice research, coverage, engineering, normative docs, product remediation, or scope rebaseline",
            "references/review-qa-and-recovery.md": "Before convergence, Final Review, recovery, QA, derived docs, documentation closure, or readiness",
            "references/severity-and-readiness.md": "Before classifying a finding/gate/risk or evaluating readiness",
            "references/deferred-findings.md": "Before routing a supported out-of-scope candidate",
            "references/lifecycle-projection-recovery.md": "Only when compact status reports generated dashboard revision drift",
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
        self.assertIn(
            "](references/lifecycle-projection-recovery.md)",
            conditional_block,
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
        self.assertIn("not Director startup material", telemetry_contract)
        self.assertIn("never reported as total agent context", telemetry_contract)
        self.assertIn("prior worker chat history", telemetry_contract)

    def test_pipeline_always_core_has_a_hard_startup_ceiling(self) -> None:
        pipeline_root = self.plugin_root / "skills" / "gamedev-pipeline"
        files = [pipeline_root / "agents" / "openai.yaml"] + [
            pipeline_root / path for path in PIPELINE_ALWAYS_CORE
        ]
        total_bytes = sum(path.stat().st_size for path in files)
        self.assertLessEqual(total_bytes, PIPELINE_ALWAYS_CORE_MAX_BYTES)
        self.assertLessEqual((total_bytes + 3) // 4, PIPELINE_ALWAYS_CORE_MAX_BYTES // 4)
        skill = (pipeline_root / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("role-artifacts-and-context.md", skill)
        self.assertIn("Do not preload conditional references or worker-owned schema", skill)

    def test_each_runtime_role_has_explicit_skill_documentation(self) -> None:
        controller = (
            self.plugin_root
            / "skills"
            / "gamedev-pipeline"
            / "scripts"
            / "pipeline_state.py"
        ).read_text(encoding="utf-8")
        for role, skill_names in RUNTIME_ROLE_SKILLS.items():
            with self.subTest(runtime_role=role):
                self.assertIn(f'"{role}"', controller)
                for skill_name in skill_names:
                    skill_root = self.plugin_root / "skills" / skill_name
                    self.assertTrue((skill_root / "SKILL.md").is_file())
                    self.assertTrue((skill_root / "agents" / "openai.yaml").is_file())

    def test_worker_output_schemas_are_role_owned_and_not_director_preloads(self) -> None:
        pipeline_skill = self.read_skill("gamedev-pipeline")
        self.assertNotIn("role-artifacts-and-context.md", pipeline_skill)
        for skill_name, reference in WORKER_SCHEMA_REFERENCES.items():
            with self.subTest(skill=skill_name):
                skill = self.read_skill(skill_name)
                self.assertIn(reference, skill)
        for skill_name in ("gamedev-engineer", "gamedev-documentation-finisher"):
            self.assertNotIn("role-artifacts-and-context.md", self.read_skill(skill_name))

    def test_worker_contract_markers_match_controller_validators(self) -> None:
        pipeline_root = self.plugin_root / "skills" / "gamedev-pipeline"
        controller = (pipeline_root / "scripts" / "pipeline_state.py").read_text(
            encoding="utf-8"
        )
        contracts = {
            "semantic": (
                pipeline_root / "references" / "semantic-write-packet.md"
            ).read_text(encoding="utf-8"),
            "review": (
                self.plugin_root
                / "skills"
                / "gamedev-review"
                / "references"
                / "review-output-contract.md"
            ).read_text(encoding="utf-8"),
            "qa": (
                self.plugin_root
                / "skills"
                / "gamedev-qa"
                / "references"
                / "qa-output-contract.md"
            ).read_text(encoding="utf-8"),
            "research": (
                self.plugin_root
                / "skills"
                / "gamedev-research"
                / "references"
                / "research-bundle-contract.md"
            ).read_text(encoding="utf-8"),
        }
        for marker in (
            "inventory_complete",
            "domain_inventory",
            "assigned_goal_effect:",
            "open_assumptions",
        ):
            with self.subTest(semantic_marker=marker):
                self.assertIn(marker, contracts["semantic"])
                self.assertIn(marker, controller)
        for marker in (
            "full_convergence",
            "final_whole_feature_review",
            "targeted_closure",
            "recovery_verification",
            "documentation_closure",
        ):
            with self.subTest(review_mode=marker):
                self.assertIn(marker, contracts["review"])
                self.assertIn(marker, controller)
        for marker in (
            "manual_execution",
            "blocked_by_finding",
            "minimum_resume_action",
        ):
            with self.subTest(qa_marker=marker):
                self.assertIn(marker, contracts["qa"])
                self.assertIn(marker, controller)
        for marker in (
            "schema_version",
            "brief_sha256",
            "limit_reached",
        ):
            with self.subTest(research_marker=marker):
                self.assertIn(marker, contracts["research"])
                self.assertIn(marker, controller)

    def test_review_count_is_singular_and_phase_context_is_isolated(self) -> None:
        pipeline_root = self.plugin_root / "skills" / "gamedev-pipeline"
        routed = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                pipeline_root / "SKILL.md",
                pipeline_root / "references" / "pipeline-protocol.md",
                pipeline_root / "references" / "review-qa-and-recovery.md",
                pipeline_root / "references" / "severity-and-readiness.md",
                pipeline_root / "references" / "role-artifacts-and-context.md",
            )
        )
        self.assertNotIn("two distinct full Reviews", routed)
        self.assertNotRegex(routed, r"Review A\s*\|\|")
        self.assertIn("single controller-required Final Review", routed)
        self.assertIn("fork_turns: none", routed)
        self.assertIn("never predecessor human conclusions", routed)

    def test_derived_documentation_sources_match_worker_capsule_contract(self) -> None:
        contract = (
            self.plugin_root
            / "skills"
            / "gamedev-documentation-finisher"
            / "references"
            / "documentation-contract.md"
        ).read_text(encoding="utf-8")
        derived_line = next(
            line for line in contract.splitlines() if "derived source kinds are" in line
        )
        self.assertIn(
            "`decision`, `qa`, `review`, and `controller_handoff`", derived_line
        )
        self.assertNotIn("capability_probe", derived_line)

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
