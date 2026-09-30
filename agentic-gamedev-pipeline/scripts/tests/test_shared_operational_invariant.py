#!/usr/bin/env python3
"""Structural regressions for the shared worker/director operating invariant."""

from __future__ import annotations

import json
import re
import shlex
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
from pipeline_v2.qa_contract import QAContractError, validate_contract, validate_results
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

    def test_context_handoff_preserves_related_owner_and_accepted_slice_boundary(self) -> None:
        text = INVARIANT.read_text(encoding="utf-8")
        self.assertNotRegex(text, r"\b(?:70|90)%")
        section = text.split("## Working-set checkpoint and rotation\n", 1)[1].split("\n## ", 1)[0]
        obligations = {
            "related remediation retains owner": ("same Engineer", "related repairs"),
            "accepted slice changes physical context": ("accepted behavioral slice boundary", "fresh physical Engineer"),
            "continuation has actual authority": ("concrete continuity reason", "explicit applicable user authority"),
            "handoff is quiescent": ("actual termination/quiescence", "no active write/check grant"),
            "no false completion or quotas": ("Do not manufacture PASS", "telemetry is evidence, never a threshold"),
            "checkpoint uses current sources": ("current authority paths/revisions/hashes", "native phase/generation/action", "candidate binding from actual sources"),
            "fresh owner needs actual input": ("full current relevant input", "never another owner's retained baseline"),
        }
        for obligation, required in obligations.items():
            with self.subTest(obligation=obligation):
                for phrase in required:
                    self.assertIn(phrase, section)
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


    def test_minimal_non_qa_role_examples_pass_the_actual_semantic_validator(self) -> None:
        examples = (
            ("plan", "gamedev-pipeline/references/pipeline-protocol.md"),
            ("slice", "gamedev-pipeline/references/pipeline-protocol.md"),
            ("engineering", "gamedev-pipeline/references/semantic-write-packet.md"),
            ("review", "gamedev-review/references/review-output-contract.md"),
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

    def test_qa_example_uses_reachable_bound_assertion_contract(self) -> None:
        role_contract = SKILLS / "gamedev-qa/references/qa-output-contract.md"
        source = role_contract.read_text(encoding="utf-8")
        # QA's canonical example is an assertion plus its approved method, not
        # a second generic checks-only PASS in the role router.
        target = re.search(r"\]\(([^)]+/qa-acceptance-contract\.md)\)", source)
        self.assertIsNotNone(target)
        canonical = (role_contract.parent / target.group(1)).resolve()
        self.assertEqual(INVARIANT.with_name("qa-acceptance-contract.md").resolve(), canonical)
        text = canonical.read_text(encoding="utf-8")

        def example(heading: str) -> dict:
            section = text.split("## " + heading + "\n", 1)[1].split("\n## ", 1)[0]
            blocks = re.findall(r"```json\n(.*?)\n```", section, re.DOTALL)
            self.assertTrue(blocks, heading + " must supply its schema example")
            return json.loads(blocks[0])

        manifest = example("Manifest")
        assertion = example("Complete terminal results")
        slice_id, definition = next(iter(manifest["slices"].items()))
        identity = definition["identities"][0]
        validate_contract(manifest, {slice_id: [identity["id"]]})
        value = {"outcome": assertion["outcome"], "checks": [{
            "id": identity["id"], "outcome": assertion["outcome"],
            "evidence": "Canonical documentation example; not a claim of product execution.",
            "assertions": [assertion],
        }]}
        self.assertEqual(value, _worker_artifact(value, "qa", ROLES["qa"], [identity["id"]]))
        self.assertEqual(value["checks"], validate_results(value["checks"], definition, outcome=value["outcome"]))
        for mutation in ("contradiction", "missing_evidence", "unknown_method"):
            with self.subTest(mutation=mutation):
                invalid = json.loads(json.dumps(value))
                row = invalid["checks"][0]["assertions"][0]
                if mutation == "contradiction":
                    row["assessment"]["comparison"] = "contradicts"
                elif mutation == "missing_evidence":
                    row["evidence"] = []
                else:
                    row["method_id"] = "unapproved-method"
                with self.assertRaises(QAContractError):
                    validate_results(invalid["checks"], definition, outcome=invalid["outcome"])

        # A fully populated legacy-looking gap row can still be unfinished QA:
        # current publication requires a concrete, evidenced Engineering repair.
        unfinished = json.loads(json.dumps(value))
        unfinished["outcome"] = unfinished["checks"][0]["outcome"] = "fail"
        row = unfinished["checks"][0]["assertions"][0]
        method = row["method_id"]
        row.update(outcome="not_run", method_id=None,
                   reason={"kind": "verification_incomplete", "detail": "Captured results are not yet mapped.", "refs": [method]},
                   evidence=[{"type": "verification-gap", "ref": method, "observation": "Assessment is unfinished."}])
        row["assessment"].update(observed="No completed comparison yet.", comparison="insufficient")
        with self.assertRaisesRegex(QAContractError, "Engineering repair"):
            validate_results(unfinished["checks"], definition, outcome="fail", strict_gaps=True)

    def test_documented_incremental_qa_and_selected_read_commands_are_public(self) -> None:
        from pipeline_v2.cli import parser

        qa = INVARIANT.with_name("qa-acceptance-contract.md").read_text(encoding="utf-8")
        incremental = qa.split("## Incremental assessment\n", 1)[1].split("\n## ", 1)[0]
        delivery = INVARIANT.with_name("delivery-contract.md").read_text(encoding="utf-8")
        execution = INVARIANT.with_name("execution-contract.md").read_text(encoding="utf-8")
        examples = (
            (incremental, ["qa-draft", "--assignment-id", "qa-bound"]),
            (incremental, ["qa-read", "--assignment-id", "qa-bound", "--identity-id", "MANUAL-FEATURE-RUNTIME", "--format", "json", "--assemble"]),
            (incremental, ["qa-record", "--assignment-id", "qa-bound", "--source", "assessed-group.json"]),
            (incremental, ["qa-finalize", "--assignment-id", "qa-bound", "--expected-revision", "1"]),
            (delivery, ["assignment-read", "--digest", "a" * 64, "--view", "qa-index", "--format", "json", "--assemble"]),
            (delivery, ["assignment-read", "--digest", "a" * 64, "--view", "qa-assertion", "--assertion-id", "runtime-reset", "--assertion-id", "runtime-exit", "--format", "json", "--assemble"]),
            (delivery, ["file-read", "--instruction", "director", "--path", "references/director-runtime.md", "--section", "Ordinary event map", "--format", "json", "--assemble"]),
            (delivery, ["file-read", "--path", "docs/plan.md", "--lines", "1:5", "--format", "text"]),
            (execution, ["evidence-read", "--record-id", "feature-channel-probe", "--raw-file", "raw.json", "--pointer", "/value/observations", "--format", "json", "--assemble"]),
        )
        for instructions, argv in examples:
            with self.subTest(argv=argv):
                self.assertIn(argv[0], instructions)
                actual = parser().parse_args(["--root", str(BUNDLE), "--feature", "sample-feature", *argv])
                self.assertEqual(argv[0], actual.command)

        # Parse the actual copyable prepared-context examples, so changing a
        # documented flag cannot leave a separate handwritten test argv green.
        blocks = re.findall(r"```console\n(.*?)\n```", incremental, re.DOTALL)
        self.assertTrue(blocks, "The incremental route must expose concrete helper calls")
        for block in blocks:
            for line in block.splitlines():
                argv = shlex.split(line)
                with self.subTest(documented_command=line):
                    actual = parser().parse_args(["--root", str(BUNDLE), "--feature", "sample-feature", *argv])
                    self.assertEqual(argv[0], actual.command)
                    if actual.command == "qa-prepare" and actual.output:
                        self.assertFalse(actual.pointer or actual.continuation or actual.assemble)

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
        invariant = INVARIANT.read_text(encoding="utf-8")
        self.assertIn("full current relevant input", invariant)
        self.assertIn("never another owner's retained baseline or session-local handles", invariant)
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
        invariant = INVARIANT.read_text(encoding="utf-8")
        restriction = invariant.split("## Evidence, artifacts and incidents\n", 1)[1]
        self.assertRegex(restriction, r"(?i)workers must not edit, patch, bypass or replace the pipeline under product-only authority")
        self.assertIn("including a valid prior delegation", restriction)


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
