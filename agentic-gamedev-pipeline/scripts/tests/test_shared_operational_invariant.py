#!/usr/bin/env python3
"""Structural regressions for the shared worker/director operating invariant."""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path


BUNDLE = Path(__file__).resolve().parents[2]
SKILLS = BUNDLE / "skills"
INVARIANT = SKILLS / "gamedev-pipeline" / "references" / "stage-handoff-invariant.md"
sys.path.insert(0, str(SKILLS / "gamedev-pipeline" / "scripts"))

from pipeline_v2.model import PipelineError, ROLES, artifact_schema
from pipeline_v2.reducer import _worker_artifact
from pipeline_v2.runner import _caller_slices


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

    def test_director_waits_for_and_consumes_each_child_result_before_final(self) -> None:
        text = INVARIANT.read_text(encoding="utf-8")
        required = (
            "After spawning any phase worker",
            "owns that exact child until its terminal result",
            "MUST wait using the available coordination primitive",
            "MUST NOT send a final response",
            "`work continues asynchronously`",
            "while that child is live",
            "re-read public controller status",
            "same active assignment",
            "exact returned output artifact",
            "exact public controller `complete` action",
            "including for a blocked outcome",
            "re-read the resulting public controller status",
            "no child owning an active assignment",
            "no completed child artifact remaining unconsumed",
        )
        for phrase in required:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

        section = text.split("## Director child-result consumption", 1)[1].split(
            "\n## ", 1
        )[0]
        self.assertNotRegex(
            section,
            r"(?i)\b(?:timeout|retry|retries|daemon|service|sleep)\b",
        )

    def test_minimal_role_examples_pass_the_actual_semantic_validator(self) -> None:
        examples = (
            ("plan", "gamedev-pipeline/references/pipeline-protocol.md"),
            ("slice", "gamedev-pipeline/references/pipeline-protocol.md"),
            ("engineering", "gamedev-pipeline/references/semantic-write-packet.md"),
            ("review", "gamedev-review/references/review-output-contract.md"),
            ("qa", "gamedev-qa/references/qa-output-contract.md"),
        )
        for phase, relative in examples:
            with self.subTest(phase=phase):
                text = (SKILLS / relative).read_text(encoding="utf-8")
                blocks = re.findall(r"```json\n(.*?)\n```", text, re.DOTALL)
                self.assertEqual(1, len(blocks), "one minimal example per contract")
                value = json.loads(blocks[0])
                schema = artifact_schema(phase, ROLES[phase])
                self.assertEqual(set(schema["required_keys"]), set(value))
                self.assertEqual(value, _worker_artifact(value, phase, ROLES[phase]))

    def test_observed_format_errors_still_fail_without_weakening_validation(self) -> None:
        cases = (
            ("plan", {"outcome": "pass", "summary": "Confirmed.",
                      "blocker": "", "required_action": ""},
             {"outcome": "pass", "summary": "Confirmed."}),
            ("review", {"outcome": "pass", "findings": [], "summary": "Reviewed."},
             {"outcome": "pass", "findings": []}),
            ("qa", {"outcome": "blocked", "checks": ["Assigned scenario failed."],
                    "source_revision": "old", "source_scope_sha256": "old",
                    "blocker": "A test failed.", "required_action": "Repair the defect."},
             {"outcome": "fail", "checks": [{"id": "MANUAL-FEATURE-RUNTIME", "outcome": "fail", "evidence": "Assigned scenario failed."}]}),
            ("engineering", {"outcome": "pass", "summary": "Implemented.",
                             "checks": ["build"], "not_run": ["runtime"]},
             {"outcome": "pass", "summary": "Implemented; runtime remains unverified."}),
        )
        for phase, malformed, corrected in cases:
            with self.subTest(phase=phase):
                before = json.dumps(malformed, sort_keys=True)
                with self.assertRaises(PipelineError):
                    _worker_artifact(malformed, phase, ROLES[phase])
                self.assertEqual(before, json.dumps(malformed, sort_keys=True))
                self.assertEqual(corrected, _worker_artifact(corrected, phase, ROLES[phase]))

        # Slice semantic parsing also accepts sealed records; the caller boundary
        # is what rejected the session's leaked read_paths. Keep the slice intact.
        corrected_slice = {"id": "SLICE-001", "allowed_paths": ["src/a.py"],
                           "planned_commands": [["python", "-c", "pass"]]}
        malformed_slices = [{**corrected_slice, "read_paths": ["src/a.py"]}]
        before = json.dumps(malformed_slices, sort_keys=True)
        with self.assertRaisesRegex(PipelineError, "exactly id, allowed_paths, and planned_commands"):
            _caller_slices(malformed_slices)
        self.assertEqual(before, json.dumps(malformed_slices, sort_keys=True))
        self.assertEqual([corrected_slice], _caller_slices([corrected_slice]))
        corrected = {"outcome": "pass", "summary": "Slice confirmed.", "slices": [corrected_slice]}
        self.assertEqual(corrected, _worker_artifact(corrected, "slice", ROLES["slice"]))

    def test_review_contract_keeps_target_separate_from_evidence_context(self) -> None:
        reviewer = (SKILLS / "gamedev-review" / "SKILL.md").read_text(encoding="utf-8")
        contract = (
            SKILLS / "gamedev-review" / "references" / "review-output-contract.md"
        ).read_text(encoding="utf-8")
        protocol = (
            SKILLS / "gamedev-pipeline" / "references" / "pipeline-protocol.md"
        ).read_text(encoding="utf-8")

        # Semantic policy has one canonical owner; linked summaries need not
        # duplicate exact sentences to satisfy a phrase-presence test.
        self.assertIn("references/review-output-contract.md", reviewer)
        self.assertIn("linked role contracts", protocol)
        for phrase in (
            "evidence context", "documentation_changes", "candidate_changes",
            "direct regression", "missing mandatory implementation",
            "current-candidate evidence", "simpler sufficient implementation",
        ):
            self.assertIn(phrase, contract)
        self.assertIn("no suggestions or backlog", contract)
        self.assertIn("reversible technical clarification consistent with approved authority", contract)
        self.assertIn("An authority contradiction affecting product behavior or scope is `blocked`", contract)
        self.assertIn("mandatory assigned input or capability", contract)

    def test_dispatch_instructions_name_fresh_context_and_existing_role_paths(self) -> None:
        skill = (SKILLS / "gamedev-pipeline" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn('fork_turns: "none"', skill)
        self.assertIn("self-contained packet", skill)
        for relative in re.findall(r"\]\((\.\./[^)]+/SKILL\.md)\)", skill):
            self.assertTrue((SKILLS / "gamedev-pipeline" / relative).is_file(), relative)

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
        self.assertIn(
            ".agentic-pipeline/Workflows/<feature>/pipeline-state.json",
            plan_contract,
        )
        self.assertIn("status", plan_contract)
        self.assertIn(
            'RUNTIME_STATE_FILENAME = "pipeline-state.json"',
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
