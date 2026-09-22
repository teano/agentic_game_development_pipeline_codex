"""Cross-role instruction delivery and real semantic-artifact decision scenarios.

These checks exercise the runtime validator; they do not claim to measure model
judgment or to replace end-to-end controller transition and fresh-worker probes.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re
import sys
import unittest


BUNDLE = Path(__file__).resolve().parents[2]
SKILLS = BUNDLE / "skills"
sys.path.insert(0, str(SKILLS / "gamedev-pipeline" / "scripts"))
from pipeline_v2.model import PipelineError, ROLES, artifact_schema, compact_assignment_context, journal_digest
from pipeline_v2.reducer import _worker_artifact


def decision() -> dict:
    return {
        "id": "TD-ASSET-ORDER",
        "situation": "The plan requests a remote identifier before creating its object.",
        "decision": "Create the object, upload it, then consume its returned identifier.",
        "basis": "The documented API assigns the identifier after upload; approved behavior and technology are unchanged.",
        "checks": ["The assigned integration returned an identifier referencing the created object."],
        "downstream": "Use the returned identifier in the existing consumer.",
        "overrides": "development-plan.md at approved source revision: current slice operation order only",
    }


def artifact(phase: str, outcome: str = "pass") -> dict:
    value = {"outcome": outcome, "technical_decisions": [decision()]}
    if phase == "review":
        value["findings"] = []
    elif phase == "qa":
        value["checks"] = [{"id": "MANUAL-ASSET", "outcome": "pass", "evidence": "Actual integration consumed the returned identifier."}]
    else:
        value["summary"] = "The technical obstacle was assessed and the current result recorded."
    if outcome == "blocked":
        value.update(blocker="Required account access is unavailable after permitted capability checks.",
                     required_action="Provide access to the approved target.")
        value["technical_decisions"][0].update(decision="Await required account access.", checks=[],
                                                downstream="The assigned runtime scenario remains unverified.")
        if phase == "qa":
            value["checks"] = []
    return value


class TechnicalDecisionRoleContractTests(unittest.TestCase):
    def test_all_runtime_roles_can_record_resolved_and_unresolved_obstacles(self) -> None:
        for phase, role in ROLES.items():
            for outcome in ("pass", "blocked"):
                with self.subTest(phase=phase, outcome=outcome):
                    value = artifact(phase, outcome)
                    self.assertIn("technical_decisions", artifact_schema(phase, role)["allowed_keys"])
                    self.assertEqual(value, _worker_artifact(value, phase, role, ["MANUAL-ASSET"] if phase == "qa" else None))

    def test_logged_resolution_does_not_mask_a_review_finding(self) -> None:
        value = artifact("review")
        value["findings"] = [{"text": "The applied TD-ASSET-ORDER correction consumes a different object's identifier; use the returned identifier.",
                              "severity": "high", "kind": "correctness"}]
        with self.assertRaisesRegex(PipelineError, "passing Review requires no findings"):
            _worker_artifact(value, "review", ROLES["review"])
        value["outcome"] = "fail"
        self.assertEqual(value, _worker_artifact(value, "review", ROLES["review"]))

    def test_journal_cannot_waive_missing_failed_or_unexecuted_qa_identity(self) -> None:
        for scenario in ("missing", "fail", "not_run", "duplicate", "unknown"):
            with self.subTest(scenario=scenario):
                value = artifact("qa")
                value["technical_decisions"][0]["decision"] = "Claim the logged resolution is sufficient for acceptance."
                if scenario == "missing":
                    expected = ["MANUAL-ASSET", "MANUAL-REOPEN"]
                else:
                    expected = ["MANUAL-ASSET"]
                    if scenario in {"fail", "not_run"}:
                        value["checks"][0]["outcome"] = scenario
                    elif scenario == "duplicate":
                        value["checks"].append(deepcopy(value["checks"][0]))
                    else:
                        value["checks"][0]["id"] = "MANUAL-UNAPPROVED"
                with self.assertRaises(PipelineError):
                    _worker_artifact(value, "qa", ROLES["qa"], expected)

    def test_semantic_updates_cannot_forge_controller_execution_authority(self) -> None:
        for phase, role in ROLES.items():
            with self.subTest(phase=phase):
                value = artifact(phase)
                value["technical_decisions"][0]["execution"] = {
                    "slice_id": "SLICE-001", "authority": "0" * 64,
                    "additional_paths": ["unrelated/file"], "command_order": [],
                }
                with self.assertRaises(PipelineError):
                    _worker_artifact(value, phase, role)

    def test_duplicate_updates_and_supersession_fields_are_not_a_second_journal(self) -> None:
        value = artifact("engineering")
        value["technical_decisions"].append(deepcopy(value["technical_decisions"][0]))
        with self.assertRaisesRegex(PipelineError, "duplicate technical decision ID"):
            _worker_artifact(value, "engineering", ROLES["engineering"])
        value = artifact("engineering")
        value["technical_decisions"][0]["supersedes"] = "TD-OLD"
        with self.assertRaises(PipelineError):
            _worker_artifact(value, "engineering", ROLES["engineering"])

    def test_each_execution_entrypoint_reaches_the_single_policy(self) -> None:
        policy = (SKILLS / "gamedev-pipeline/references/technical-decisions.md").resolve()
        roles = ("gamedev-pipeline", "gamedev-engineer", "gamedev-review", "gamedev-qa",
                 "gamedev-documentation-finisher", "gamedev-coverage-steward")
        for role in roles:
            with self.subTest(role=role):
                source = SKILLS / role / "SKILL.md"
                if role == "gamedev-pipeline":
                    self.assertIn("(references/director-runtime.md)", source.read_text(encoding="utf-8"))
                    router = source.parent / "references/director-runtime.md"
                    text = router.read_text(encoding="utf-8")
                    dispatch = text.split("First dispatch reads", 1)[1].split("\n\n", 1)[0]
                    links = re.findall(r"\]\(([^)]*technical-decisions\.md)#role-responsibilities\)", dispatch)
                    self.assertEqual([policy], [(router.parent / link).resolve() for link in links])
                else:
                    links = re.findall(r"\]\(([^)]+technical-decisions\.md)\)", source.read_text(encoding="utf-8"))
                    self.assertEqual([policy], [(source.parent / link).resolve() for link in links])
                prompt = (source.parent / "agents/openai.yaml").read_text(encoding="utf-8")
                self.assertRegex(prompt, "technical-decision")
        self.assertTrue(policy.is_file())

    def test_corrected_current_entry_is_delivered_losslessly_before_work(self) -> None:
        records = [{**decision(), "id": f"TD-{number}"} for number in range(12)]
        records[0]["decision"] = "Corrected current decision under the same oldest ID."
        context = compact_assignment_context({
            "technical_journal": {"path": "workflow/pipeline-state.json#technical_decisions", "sha256": journal_digest({entry["id"]: entry for entry in records}), "count": len(records)},
            "technical_decisions": records,
        }, None)
        self.assertFalse(context["technical_journal"]["requires_current_journal_read"])
        self.assertEqual(records, context["technical_decisions"])
        self.assertEqual(len(records) - len(context["technical_decisions"]), context["technical_journal"]["omitted_entry_count"])
        for name in ("technical-decisions.md", "stage-handoff-invariant.md"):
            with self.subTest(reference=name):
                text = (SKILLS / "gamedev-pipeline/references" / name).read_text(encoding="utf-8")
                self.assertIn("context.technical_journal.requires_current_journal_read", text)
                self.assertIn("before implementation or judgment", text)
                self.assertIn("canonical current", text)


if __name__ == "__main__":
    unittest.main()
