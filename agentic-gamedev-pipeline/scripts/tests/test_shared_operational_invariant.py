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
DIRECTOR = INVARIANT.with_name("director-runtime.md")
INTERACTION = INVARIANT.with_name("interaction-evidence.md")
MAINTENANCE = INVARIANT.with_name("maintenance-observation.md")
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
                if role == "gamedev-pipeline":
                    self.assertIn("(references/director-runtime.md)", text)
                    text = DIRECTOR.read_text(encoding="utf-8")
                    self.assertIn("First dispatch reads shared [ownership]", text)
                    self.assertIn("stage-handoff-invariant.md#one-owner-and-one-current-assignment", text)
                self.assertIn("stage-handoff-invariant.md", text)

    def test_context_rotation_has_one_owner_and_economic_handoff_contract(self) -> None:
        text = INVARIANT.read_text(encoding="utf-8")
        self.assertNotRegex(text, r"\b(?:70|90)%")
        for required in ("useful working set", "Never mark incomplete work PASS", "quiescence", "idle `rotate-owner`", "exact next public action"):
            self.assertIn(required, text)
        # Role routers must discover the shared contract, not invent local
        # thresholds. Behavior under pressure is exercised by role-scenarios.
        for role in ("gamedev-pipeline", "gamedev-engineer", "gamedev-review", "gamedev-qa"):
            source = (SKILLS / role / "SKILL.md").read_text(encoding="utf-8")
            if role == "gamedev-pipeline":
                self.assertIn("(references/director-runtime.md)", source)
                source = DIRECTOR.read_text(encoding="utf-8")
                self.assertIn("For context checkpoint/owner turnover, first read", source)
                self.assertIn("stage-handoff-invariant.md#working-set-checkpoint-and-rotation", source)
            self.assertIn("stage-handoff-invariant.md", source)
            self.assertNotRegex(source, r"\b(?:70|90)%")


    def test_platform_and_observer_rules_are_shared_and_fail_closed(self) -> None:
        text = "\n".join(path.read_text(encoding="utf-8") for path in (INVARIANT, INTERACTION, MAINTENANCE))
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

    def test_director_owns_consumption_status_steering_and_host_limits(self) -> None:
        text = DIRECTOR.read_text(encoding="utf-8")
        # The closed event table now owns these obligations; do not require
        # superseded prose from the former monolithic runtime manual.
        rules = {
            "assignment continuation": ("same assignment active", "idle/completed owner: `followup_task` in that assignment"),
            "exact output and blocked consumption": ("exact assignment/output", "including fail/blocked output"),
            "terminal consumption": ("Do not finalize an authorized run with a live child or unconsumed terminal output",),
            "status steering": ("Status: answer from retained facts and resume work/wait", "A necessary question is nonterminal"),
            "typed native result": ("Use returned typed outcome, final cursor and delivery",),
            "no message is not a stall": ("Unchanged timeout/empty stdout: only renew the matching host wait", "No timer-driven inventories, messages or packet resend"),
            "host slot boundary": ("capacity/pending-init/lost-owner", "`interrupt_agent` proves neither free slot nor dead subprocesses", "Retry dispatch only after changed lifecycle evidence"),
        }
        for obligation, phrases in rules.items():
            with self.subTest(obligation=obligation):
                for phrase in phrases:
                    self.assertIn(phrase, text)
        skill = (SKILLS / "gamedev-pipeline" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("(references/director-runtime.md)", skill)
        self.assertIn("Do not poll, request transcripts, send unchanged packets, create a second observer", skill)
        self.assertNotRegex(text, r"wait_agent\(\{timeout_ms:600000\}\)")
        self.assertIn("director-runtime.md", INVARIANT.read_text(encoding="utf-8"))


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
        self.assertIn("(references/director-runtime.md)", skill)
        runtime = DIRECTOR.read_text(encoding="utf-8")
        self.assertRegex(runtime, r'fork_turns:\s*"none"')
        self.assertIn("control-return.md#caller-binding-and-dispatch", runtime)
        self.assertIn("Forward delivery/`role_instructions` unchanged", runtime)
        self.assertIn("Fresh/replaced/lost-context owners need full content", runtime)
        self.assertIn("self-contained current packet", INVARIANT.read_text(encoding="utf-8"))
        control = INVARIANT.with_name("control-return.md")
        template = control.read_text(encoding="utf-8")
        for field in ("Role instructions:", "Task and stop boundary:", "Inputs:", "Permissions:", "consume required input completely before work"):
            self.assertIn(field, template)
        self.assertIn("control-return.md#stage-ingress", runtime)
        links = re.findall(r"\]\((\.\./[^)]+/SKILL\.md)\)", template)
        self.assertTrue(links, "The ingress route must name existing role entrypoints")
        for relative in links:
            self.assertTrue((control.parent / relative).is_file(), relative)

    def test_incident_authority_is_scoped_and_prior_delegation_is_preserved(self) -> None:
        authority = INVARIANT.with_name("authority-contract.md")
        text = authority.read_text(encoding="utf-8")
        self.assertIn("authority-contract.md", INVARIANT.read_text(encoding="utf-8"))
        self.assertIn("A user may explicitly delegate", text)
        self.assertIn("Reuse explicit prior maintenance authority", text)
        self.assertIn("otherwise obtain it before changing shared pipeline code", text)
        self.assertIn("never manufacture a user message", text)
        self.assertIn("incident is never blanket permission", text)
        self.assertIn("MUST NOT edit, patch, bypass", INVARIANT.read_text(encoding="utf-8"))


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

        self.assertIn("(references/director-runtime.md)", pipeline_skill)
        runtime = DIRECTOR.read_text(encoding="utf-8")
        self.assertIn("pipeline-protocol.md#authority-and-phases", runtime)
        authority = protocol.split("## Authority and phases", 1)[1].split("\n## ", 1)[0]
        self.assertIn("v2 has no `authority_recovery_hold`", authority)
        self.assertIn("every other public mutation fails closed", authority)
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
