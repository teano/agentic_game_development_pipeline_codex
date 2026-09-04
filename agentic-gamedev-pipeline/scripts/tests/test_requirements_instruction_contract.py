#!/usr/bin/env python3
"""Section-aware regressions for the requirements instruction contract."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


BUNDLE = Path(__file__).resolve().parents[2]
REQUIREMENTS = BUNDLE / "skills" / "gamedev-requirements"
SKILL_PATH = REQUIREMENTS / "SKILL.md"
CONTRACT_PATH = REQUIREMENTS / "references" / "product-requirements-contract.md"
INVARIANT_PATH = BUNDLE / "skills/gamedev-pipeline/references/stage-handoff-invariant.md"

INTERVIEW_RULES = (
    "strictly in the active task",
    "actual detected project stack",
    "current repository instructions and conventions",
    "Do not run an abstract checklist",
    "up to five",
    "Five is a ceiling, not a quota",
    "one prerequisite or conflict blocks",
    "often with one question",
    "Parse each numbered answer independently",
    "Free text applies only to its corresponding question and overrides shorthand",
    "A request for clarification is not an answer or option selection",
    "apply the contract's ambiguity rule only to that question",
)
RECOMMENDATION_RULES = (
    "If a current-project-grounded expert recommendation exists, place it first",
    "best-practice alternatives or materially simpler alternatives that actually apply",
    "Never invent a recommendation or alternatives to reach an option count",
    "Do not force mutual exclusivity",
    "displayed option as authority until the user selects it",
)
LANE_RULES = (
    "Requirements sessions need not spawn subagents",
    "only when nontrivial research or review is required",
    "user explicitly requests delegation",
    "collaboration is available, offload it from the root context",
    "persistent, reusable, read-only lanes",
    "Allow every started lane to finish or to checkpoint and hand off",
    "Do not cancel and restart lanes per answer",
    "root must consume every terminal lane result before requesting approval",
    "root Requirements agent alone interprets user decisions",
    "edits the canonical PRD",
    "requests or records approval",
)
APPROVAL_RULES = (
    "full current revision is semantically complete, feasible, and testable", "all material product decisions are closed",
    "required evidence category can verify each material behavior", "do not approve unseen semantics",
    "A semantic edit, or a change request accompanying an approval message, invalidates",
    "show the final current revision and request fresh explicit approval", "modify only approval metadata",
    "validate with `--require-approved`", "same semantic bytes",
)
OUTPUT_RULES = (
    "During discovery, report only concrete important new decisions",
    "Do not require revision, ID, or SHA boilerplate in an interim response",
    "At terminal handoff, return only:", "`PRD_READY: yes|no`",
    "`NEXT_ACTION: $gamedev-specification`", "`NEXT_ACTION` is advisory routing data",
    "Do not invoke or delegate the next stage",
)


def sections(text: str, names: tuple[str, ...]) -> dict[str, str]:
    headings = "|".join(map(re.escape, names))
    matches = list(re.finditer(rf"(?m)^## ({headings})\r?\n", text))
    result: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        result[match.group(1)] = text[match.end() : end]
    return result


def require(text: str, rules: tuple[str, ...]) -> None:
    missing = [rule for rule in rules if rule not in text]
    if missing:
        raise AssertionError("missing rules: " + ", ".join(missing))


class RequirementsInstructionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill = SKILL_PATH.read_text(encoding="utf-8")
        cls.contract = CONTRACT_PATH.read_text(encoding="utf-8")
        cls.invariant = INVARIANT_PATH.read_text(encoding="utf-8")
        cls.skill_parts = sections(
            cls.skill,
            ("Activation gate", "Resolve product decisions", "Conditional read-only lanes", "Complete the stage"),
        )
        cls.contract_parts = sections(
            cls.contract,
            ("Canonical location", "Frontmatter", "Required structure", "Content boundary", "Evidence taxonomy", "Approval and changes"),
        )

    def test_named_sections_own_complete_nonduplicated_rules(self) -> None:
        resolve = self.skill_parts["Resolve product decisions"]
        content = self.contract_parts["Content boundary"]
        evidence = self.contract_parts["Evidence taxonomy"]
        approval = self.contract_parts["Approval and changes"]
        require(resolve, INTERVIEW_RULES + RECOMMENDATION_RULES)
        require(content, (
            "Only the user's direct answer or explicit selection becomes a requirement",
            "Explicit approval applies only to the exact current PRD revision shown to the user",
            "risks, reviewer opinions",
            "stay outside the PRD unless the user explicitly confirms their exact content",
            "Demo, sample, fixture, example, and placeholder data is non-authoritative",
            "Never guess through ambiguity or contradiction",
        ))
        require(evidence, (
            "static inspection", "compilation or build", "automated runtime execution",
            "interactive editor or authoring-environment runtime execution",
            "published or deployed execution", "manual observation",
            "One category does not prove a stronger or different category",
            "structural validator proves document structure rather than user consent",
            "outside the canonical PRD",
            "No source, reviewer, or risk evidence gains product authority",
        ))
        require(approval, APPROVAL_RULES)

        authority = (
            "Only the user's direct answer or explicit selection becomes a requirement",
            "Never guess through ambiguity or contradiction", "No source, reviewer, or risk evidence gains product authority",
        )
        combined = self.skill + self.contract
        for rule in authority:
            self.assertEqual(1, combined.count(rule), rule)
        wrong_skill_sections = resolve + self.skill_parts["Conditional read-only lanes"] + self.skill_parts["Complete the stage"]
        for rule in authority:
            self.assertNotIn(rule, wrong_skill_sections)

    def test_interview_mutations_reject_false_selection_and_forced_options(self) -> None:
        resolve = self.skill_parts["Resolve product decisions"]
        mutations = (
            (RECOMMENDATION_RULES, resolve.replace(RECOMMENDATION_RULES[0], "Place an expert recommendation first")),
            (RECOMMENDATION_RULES, resolve.replace(RECOMMENDATION_RULES[2], "Invent alternatives to reach an option count")),
            (INTERVIEW_RULES, resolve.replace(INTERVIEW_RULES[10], "A request for clarification is an option selection")),
        )
        for rules, mutated in mutations:
            with self.assertRaises(AssertionError):
                require(mutated, rules)

    def test_lane_ownership_consumption_and_shared_rotation(self) -> None:
        lanes = self.skill_parts["Conditional read-only lanes"]
        require(lanes, LANE_RULES)
        mutations = (
            lanes.replace(
                "The root Requirements agent alone interprets user decisions, edits the canonical PRD, and requests or records approval",
                "A read-only lane may interpret decisions, edit the PRD, and approve it",
            ),
            lanes.replace(LANE_RULES[7], "root may ignore a terminal lane result before requesting approval"),
        )
        for mutated in mutations:
            with self.assertRaises(AssertionError):
                require(mutated, LANE_RULES)
        self.assertIn("stage-handoff-invariant.md", lanes)
        thresholds = {f"{value}%" for value in (7 * 10, 9 * 10)}
        self.assertTrue(thresholds.issubset(set(re.findall(r"\b\d{2}%", self.invariant))))
        self.assertNotRegex(self.skill + self.contract, r"\b\d{1,3}%")

    def test_approval_and_output_mutations_fail_closed(self) -> None:
        approval = self.contract_parts["Approval and changes"]
        require(approval, APPROVAL_RULES)
        survives = approval.replace("invalidates any prior or conditional approval", "preserves prior conditional approval")
        with self.assertRaises(AssertionError):
            require(survives, APPROVAL_RULES)

        complete = self.skill_parts["Complete the stage"]
        require(complete, OUTPUT_RULES)
        self.assertLess(complete.index(OUTPUT_RULES[0]), complete.index(OUTPUT_RULES[2]))
        collapsed = complete.replace(OUTPUT_RULES[2], "During discovery, return the terminal handoff:")
        with self.assertRaises(AssertionError):
            require(collapsed, OUTPUT_RULES)

    def test_existing_schema_and_stack_neutrality_remain_intact(self) -> None:
        require(self.contract_parts["Required structure"], (
            "- PRD-REQ-001: plain-text description",
            "- PRD-NFR-001: plain-text description",
            "- PRD-OQ-001: plain-text description",
            "- PRD-AC-ID: plain-text description",
        ))
        self.assertIn("Stop discovery as soon as all material product decisions and the completeness, feasibility, and testability gate are closed", self.skill_parts["Resolve product decisions"])
        encoded_terms = (
            (85, 110, 105, 116, 121), (82, 111, 98, 108, 111, 120),
            (85, 110, 114, 101, 97, 108), (87, 101, 98, 71, 76),
            (98, 114, 111, 119, 115, 101, 114),
            (68, 101, 115, 107, 116, 111, 112),
        )
        forbidden = tuple("".join(map(chr, term)).casefold() for term in encoded_terms)
        for source in (SKILL_PATH, CONTRACT_PATH, Path(__file__).resolve()):
            text = source.read_text(encoding="utf-8").casefold()
            for term in forbidden:
                self.assertNotIn(term, text, f"{term} in {source.name}")


if __name__ == "__main__":
    unittest.main()
