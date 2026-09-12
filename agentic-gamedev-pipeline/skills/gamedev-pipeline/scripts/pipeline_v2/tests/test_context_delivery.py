"""Required worker input survives dispatch, refresh and legacy projection."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline_v2.tests import test_core
from pipeline_v2.checkout import candidate_tree_oid
from pipeline_v2.reducer import reduce
from pipeline_v2.model import (
    PipelineError, digest, compact_assignment_context,
    journal_digest, required_assignment_context, status_view,
)


def _bounded_context_value(value):
    """Fixture for the former lossy wire format; not a production delivery path."""
    if isinstance(value, str) and len(value.encode("utf-8")) > 256:
        return value[:30] + f"…[sha256={digest(value)}]…" + value[-30:]
    if isinstance(value, list):
        result = [_bounded_context_value(item) for item in value[:4]]
        if len(value) > 4:
            result.append({"omitted_count": len(value) - 4, "omitted_sha256": digest(value[4:])})
        return result
    if isinstance(value, dict):
        return {key: _bounded_context_value(child) for key, child in value.items()}
    return deepcopy(value)


def decision(index=0):
    return {"id": f"TD-{index}", "situation": "Observed condition " * 50,
            "decision": "Preserve this exact constraint " * 50,
            "basis": "Direct project evidence " * 50,
            "checks": [f"Exact check {n} " * 40 for n in range(8)],
            "downstream": "Independent verification must inspect all evidence " * 30}


class ContextProjectionTests(unittest.TestCase):
    def test_long_journal_and_required_checks_survive_repeated_projection(self):
        entries = {f"TD-{n}": decision(n) for n in range(9)}
        candidate = {"generation": 7, "candidate_tree_oid": "a" * 40}
        source = {"technical_journal": {"path": "state.json#technical_decisions",
                  "sha256": journal_digest(entries), "count": len(entries)},
                  "technical_decisions": list(entries.values()),
                  "verification_failure": {"phase": "qa", "candidate": candidate,
                      "checks": [{"evidence": f"Scenario {n} " * 100} for n in range(19)]}}
        projected = compact_assignment_context(source, candidate)
        for _ in range(3):
            projected = compact_assignment_context(projected, candidate)
        self.assertEqual(source["technical_decisions"], projected["technical_decisions"])
        self.assertEqual(source["verification_failure"], projected["verification_failure"])
        self.assertFalse(projected["technical_journal"]["requires_current_journal_read"])
        self.assertNotIn("verification_failure", compact_assignment_context(source, None))

    def test_all_answered_clarifications_remain_operative_and_legacy_input_is_restored(self):
        questions = {f"Q-{n}": {"phase": "engineering", "status": "answered",
                     "prompt": f"Clarification {n} " * 60, "answer": f"Required constraint {n} " * 90}
                     for n in range(9)}
        expected = [{"id": key, **{field: value[field] for field in ("phase", "prompt", "answer")}}
                    for key, value in sorted(questions.items())]
        source = {"decisions": expected, "history": ["controller bookkeeping"]}
        projected = compact_assignment_context(source, None)
        self.assertEqual(expected, projected["decisions"])
        self.assertEqual(projected, compact_assignment_context(projected, None))
        self.assertNotIn("history", projected)
        legacy = {"decisions": _bounded_context_value(expected[-4:]),
                  "decision_history": {"total": 9, "included": 4, "omitted": 5}}
        active = {"capsule": {"context": legacy}}
        restored = required_assignment_context({"questions": questions}, active)
        self.assertEqual(expected, restored["decisions"])
        self.assertEqual(0, restored["decision_history"]["omitted"])
        with self.assertRaisesRegex(PipelineError, "no canonical questions"):
            required_assignment_context({"questions": {}}, active)
        with self.assertRaisesRegex(PipelineError, "canonical recovery"):
            compact_assignment_context(legacy, None)

    def test_canonical_literal_legacy_marker_is_data_and_remains_lossless(self):
        marker = "…[sha256=" + "a" * 64 + "]…"
        source = {"decisions": [{"id": "Q-LITERAL", "phase": "engineering",
                  "prompt": "How to describe clipping?", "answer": "Document " + marker}]}
        projected = compact_assignment_context(source, None, canonical_input=True)
        self.assertEqual(source["decisions"], projected["decisions"])
        self.assertEqual(projected, compact_assignment_context(projected, None))
        self.assertEqual(projected, required_assignment_context({"questions": {}}, {"capsule": {"context": projected}}))

    def test_legacy_clipped_text_requires_retrieval_even_when_count_matches(self):
        entry = decision()
        context = {"technical_journal": {"path": "state.json#technical_decisions",
                   "sha256": journal_digest({entry["id"]: entry}), "count": 1,
                   "requires_current_journal_read": False},
                   "technical_decisions": [_bounded_context_value(entry)]}
        projected = compact_assignment_context(context, None)
        self.assertEqual(0, projected["technical_journal"]["omitted_entry_count"])
        self.assertTrue(projected["technical_journal"]["requires_current_journal_read"])
        self.assertEqual(projected, compact_assignment_context(projected, None))


class AssignmentDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.h = test_core.PipelineV2CoreTests()
        self.h.setUp()
        self.addCleanup(self.h.tearDown)

    def failed_review(self):
        candidate = self.h._reach_candidate()
        marker = "…[sha256=" + "a" * 64 + "]…"
        findings = [{"text": f"Defect {n}: document literal {marker}. " + "Exact correction and evidence " * 50,
                     "severity": "high", "kind": "correctness"} for n in range(19)]
        self.h._complete_readonly("review", "review-delivery", {
            "outcome": "fail", "findings": findings})
        issued = self.h.controller.next(command_id="NEXT-delivery-remediation")
        return issued, candidate, findings

    def test_ordinary_review_failure_and_technical_refresh_keep_all_obligations(self):
        issued, candidate, findings = self.failed_review()
        active = issued["active_assignment"]
        failure = active["capsule"]["context"]["verification_failure"]
        self.assertEqual(candidate, failure["candidate"])
        self.assertEqual(findings, failure["findings"])
        before = self.h.store.path.read_bytes()
        for _ in range(3):
            self.assertEqual(failure, self.h.controller.status()["active_assignment"]["context"]["verification_failure"])
        self.assertEqual(before, self.h.store.path.read_bytes())
        for index in range(2):
            current = self.h.store.load()
            updated = self.h.controller.technical_action(command_id=f"TD-delivery-{index}",
                expected_generation=current["generation"], packet={
                    "assignment_id": current["active_assignment"]["id"],
                    "observed_tree_oid": candidate_tree_oid(self.h.root), "entry": decision(index)})
            context = updated["active_assignment"]["capsule"]["context"]
            self.assertEqual(failure, context["verification_failure"])
            self.assertEqual(list(updated["technical_decisions"].values()), context["technical_decisions"])
            self.assertFalse(context["technical_journal"]["requires_current_journal_read"])
            self.assertEqual(context, self.h.controller.status()["active_assignment"]["context"])
        self.h._complete("COMPLETE-delivery", {"outcome": "pass", "summary": "All defects fixed"})
        self.h._accept("delivery-remediation")
        self.assertEqual("review", self.h.store.load()["phase"])
        reviewing = self.h.controller.next(command_id="NEXT-independent-delivery-review")
        review_context = reviewing["active_assignment"]["capsule"]["context"]
        self.assertEqual(list(reviewing["technical_decisions"].values()), review_context["technical_decisions"])
        self.assertFalse(review_context["technical_journal"]["requires_current_journal_read"])

    def test_old_capsule_restores_only_matching_canonical_failure_without_state_mutation(self):
        issued, candidate, findings = self.failed_review()
        context = issued["active_assignment"]["capsule"]["context"]
        context.pop("delivery_version", None)  # A pre-fix persisted capsule.
        context["verification_failure"] = _bounded_context_value(context["verification_failure"])
        entry = decision()
        issued["technical_decisions"] = {entry["id"]: entry}
        context["technical_journal"] = {"path": f"{issued['workflow_path']}/pipeline-state.json#technical_decisions",
            "sha256": journal_digest(issued["technical_decisions"]), "count": 1,
            "requires_current_journal_read": False}
        context["technical_decisions"] = [_bounded_context_value(entry)]
        before = deepcopy(issued)
        restored = required_assignment_context(issued, issued["active_assignment"])
        self.assertEqual(findings, restored["verification_failure"]["findings"])
        self.assertEqual(candidate, restored["verification_failure"]["candidate"])
        self.assertEqual([entry], restored["technical_decisions"])
        self.assertFalse(restored["technical_journal"]["requires_current_journal_read"])
        self.assertEqual(before, issued)
        issued["artifacts"]["review"]["candidate_binding"] = {**candidate, "generation": candidate["generation"] + 1}
        with self.assertRaisesRegex(PipelineError, "no matching canonical artifact"):
            required_assignment_context(issued, issued["active_assignment"])
        with self.assertRaisesRegex(PipelineError, "no matching canonical artifact"):
            reduce(issued, {"name": "complete", "id": "FORGED-incomplete-completion",
                           "expected_generation": issued["generation"]})


if __name__ == "__main__":
    unittest.main()
