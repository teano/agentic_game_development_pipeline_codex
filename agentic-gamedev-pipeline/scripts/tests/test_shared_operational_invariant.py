#!/usr/bin/env python3
"""Structural regressions for the shared worker/director operating invariant."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


BUNDLE = Path(__file__).resolve().parents[2]
SKILLS = BUNDLE / "skills"
INVARIANT = SKILLS / "gamedev-pipeline" / "references" / "stage-handoff-invariant.md"


class SharedOperationalInvariantTests(unittest.TestCase):
    def test_every_pipeline_role_reads_the_one_shared_invariant(self) -> None:
        roles = (
            "gamedev-pipeline",
            "gamedev-requirements",
            "gamedev-specification",
            "gamedev-development-plan",
            "gamedev-engineer",
            "gamedev-review",
            "gamedev-qa",
            "gamedev-documentation-finisher",
            "gamedev-coverage-steward",
        )
        for role in roles:
            with self.subTest(role=role):
                text = (SKILLS / role / "SKILL.md").read_text(encoding="utf-8")
                self.assertIn("stage-handoff-invariant.md", text)

    def test_context_rotation_has_one_safe_late_contract(self) -> None:
        text = INVARIANT.read_text(encoding="utf-8")
        required = (
            "MUST NOT rotate or hand off solely because of context below 70%",
            "At 70% context use",
            "At 90% context use",
            "before 100%",
            "task or assignment is complete",
            "real blocker",
            "current project root",
            "phase and generation",
            "exact next public action",
        )
        for phrase in required:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

        offenders: list[str] = []
        for path in SKILLS.glob("gamedev-*/**/*.md"):
            if "gamedev-specification" in path.parts or path == INVARIANT:
                continue
            for line_number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if not re.search(r"context|rotation|handoff", line, re.IGNORECASE):
                    continue
                for raw in re.findall(r"(?<!\d)(\d{1,3})\s*%", line):
                    if int(raw) < 70:
                        offenders.append(f"{path.relative_to(BUNDLE)}:{line_number}:{raw}%")
        self.assertEqual([], offenders, "early context-only thresholds: " + ", ".join(offenders))

    def test_platform_and_observer_rules_are_shared_and_fail_closed(self) -> None:
        text = INVARIANT.read_text(encoding="utf-8")
        required = (
            "platform-neutral",
            "explicit user-approved product authority",
            "observed project or runtime capability",
            "fail closed",
            "MUST NOT retry the same unavailable environment",
            "authority or capability evidence changes",
            "Pipeline-observation workers report every issue observed",
            "pipeline`, `test`, `product`, or `environment",
            "verify the evidence before concluding",
            "pipeline-maintenance observer ledger",
            "Review and QA instead stop at their bounded stage contracts",
            "only findings eligible under its controller-derived `review_target`",
            "only assigned acceptance checks",
        )
        for phrase in required:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        self.assertNotIn(
            "Review, QA, and pipeline-observation workers report every issue",
            text,
        )

        template = (
            SKILLS / "gamedev-development-plan" / "assets" / "development-plan.md"
        ).read_text(encoding="utf-8")
        self.assertEqual(2, template.count("capability_prerequisites: project-runtime-capability"))
        for platform_default in (
            "studio-editor-sync",
            "test-server-two-clients",
            "window-control-path",
            "windows",
            "linux",
            "macos",
            "chrome",
            "chromium",
            "firefox",
            "webkit",
            "playwright",
            "selenium",
        ):
            with self.subTest(platform_default=platform_default):
                self.assertNotIn(platform_default, template.lower())

    def test_review_contract_keeps_target_separate_from_evidence_context(self) -> None:
        reviewer = (SKILLS / "gamedev-review" / "SKILL.md").read_text(encoding="utf-8")
        contract = (
            SKILLS / "gamedev-review" / "references" / "review-output-contract.md"
        ).read_text(encoding="utf-8")
        protocol = (
            SKILLS / "gamedev-pipeline" / "references" / "pipeline-protocol.md"
        ).read_text(encoding="utf-8")

        for text in (reviewer, contract, protocol):
            self.assertIn("evidence context", text)
            self.assertIn("documentation_changes", text)
            self.assertIn("candidate_changes", text)
            self.assertIn("direct regression", text)
            self.assertIn("missing mandatory implementation", text)
            self.assertIn("current-candidate evidence", text)
            self.assertIn("simpler sufficient implementation", text)
        self.assertIn("no suggestions or backlog", contract)
        self.assertIn("direct authority contradiction that changes the verdict", contract)
        self.assertIn("mandatory assigned input or capability", contract)

    def test_pipeline_defect_is_an_instruction_only_incident_stop(self) -> None:
        pipeline_skill = (SKILLS / "gamedev-pipeline" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        protocol = (
            SKILLS / "gamedev-pipeline" / "references" / "pipeline-protocol.md"
        ).read_text(encoding="utf-8")
        default_prompt = (
            SKILLS / "gamedev-pipeline" / "agents" / "openai.yaml"
        ).read_text(encoding="utf-8")
        root_readme = (BUNDLE.parent / "README.md").read_text(encoding="utf-8")
        invariant = INVARIANT.read_text(encoding="utf-8")

        self.assertIn("MUST immediately stop the product run", invariant)
        self.assertIn("MUST NOT edit, patch, bypass", invariant)
        self.assertIn("new explicit user command", invariant)
        for text in (pipeline_skill, protocol, default_prompt, root_readme):
            with self.subTest(source=text[:40]):
                self.assertRegex(text, r"(?i)stop|остана")
                self.assertRegex(text, r"(?i)patch|патч|менять")
                self.assertRegex(text, r"(?i)new explicit user|новой явной команд")

    def test_v2_authority_reopen_has_one_public_fail_closed_route(self) -> None:
        protocol = (
            SKILLS / "gamedev-pipeline" / "references" / "pipeline-protocol.md"
        ).read_text(encoding="utf-8")
        pipeline_skill = (SKILLS / "gamedev-pipeline" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        plan_contract = (
            SKILLS
            / "gamedev-development-plan"
            / "references"
            / "development-plan-contract.md"
        ).read_text(encoding="utf-8")
        plan_controller = (
            SKILLS
            / "gamedev-development-plan"
            / "scripts"
            / "development_plan_state.py"
        ).read_text(encoding="utf-8")

        for text in (protocol, pipeline_skill):
            self.assertIn("v2 has no `authority_recovery_hold`", text)
            self.assertIn("every other public mutation fails closed", text)
        self.assertIn(
            "only after every changed upstream controller reports readiness", protocol
        )
        self.assertIn("unsanctioned drift must be restored", protocol)
        self.assertIn(".agentic-pipeline-v2/state.json", plan_contract)
        self.assertIn("status", plan_contract)
        self.assertIn("`init` reconfiguration", plan_contract)
        self.assertIn(
            'V2_RUNTIME_STATE_RELATIVE_PATH = Path(".agentic-pipeline-v2/state.json")',
            plan_controller,
        )

        template = (
            SKILLS / "gamedev-development-plan" / "assets" / "development-plan.md"
        ).read_text(encoding="utf-8")
        for removed_manifest_default in (
            "manifest_path:",
            "planned_manifest:",
            "finalized_manifest:",
        ):
            self.assertNotIn(removed_manifest_default, template)
        self.assertIn(
            "Sole runtime v2 does not create coverage manifests", plan_contract
        )


if __name__ == "__main__":
    unittest.main()
