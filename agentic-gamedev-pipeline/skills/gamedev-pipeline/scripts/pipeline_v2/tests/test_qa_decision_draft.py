"""QA decisions use the existing draft and terminal journal path, without credit."""
from copy import deepcopy
from pathlib import Path
import unittest

from pipeline_v2.artifact_io import read_json, write_json
from pipeline_v2.execution_evidence import begin, capture
from pipeline_v2.model import PipelineError
from pipeline_v2.qa_draft import load, validate_projection
from pipeline_v2.reducer import _worker_artifact
from pipeline_v2.tests import test_qa_working_draft as fixtures


def decision(identifier="TD-QA-SETUP"):
    return {"id": identifier, "situation": "The shared method selector needed resolution.",
            "decision": "Record the canonical observed-action method ID after reading its definition.",
            "basis": "The issued method definition names this exact approved method; its obligations are unchanged.",
            "checks": ["fixture:method-definition — observed-action"],
            "downstream": "Retain every assertion and its independent comparison; no method substitution."}


class QADecisionDraftTests(unittest.TestCase):
    setUp = fixtures.QAWorkingDraftTests.setUp
    row = fixtures.QAWorkingDraftTests.row
    set_producer = fixtures.QAWorkingDraftTests.set_producer

    def record(self, revision, rows, **extra):
        return self.controller.qa_record("qa-current", {"expected_revision": revision, "assessments": rows, **extra})

    def test_decision_checkpoint_survives_groups_resume_and_exact_terminal_projection(self):
        entry = decision()
        request = {"expected_revision": 0, "assessments": [], "technical_decisions": [entry]}
        original_request = deepcopy(request)
        result = self.controller.qa_record("qa-current", request)
        self.assertTrue(result["valid"], result.get("errors"))
        self.assertEqual((1, 0, 3), (result["revision"], result["assessed"], result["pending"]))
        self.assertFalse(result["semantic_credit"])
        self.assertEqual(original_request, request)
        self.assertNotIn("technical_decisions", self.state)
        self.assertFalse(self.controller.qa_finalize("qa-current", 1)["valid"])
        self.assertTrue(self.record(1, [self.row()])["valid"])
        self.state["generation"] += 1
        resumed = self.controller.qa_read("qa-current")
        self.assertEqual([entry], resumed["technical_decisions"])
        self.assertEqual((2, 1, 2), (resumed["revision"], resumed["assessed"], resumed["pending"]))
        prepared = self.controller.qa_prepare("qa-current", ["reset"], "METHOD-fe82d465e8433451")
        prepared["record_request"]["assessments"][0].update(self.row("reset"))
        self.assertTrue(self.controller.qa_record("qa-current", prepared["record_request"])["valid"])
        final_group = self.record(3, [self.row("core")])
        self.assertTrue(final_group["valid"], final_group.get("errors"))
        finalized = self.controller.qa_finalize("qa-current", 4)
        self.assertTrue(finalized["valid"], finalized.get("errors"))
        artifact = read_json(Path(finalized["path"]))
        self.assertEqual([entry], artifact["technical_decisions"])
        self.assertEqual("observed-action", artifact["checks"][0]["assertions"][0]["method_id"])
        validate_projection(self.state, self.root, self.binding, artifact)
        changed = deepcopy(artifact)
        changed["technical_decisions"][0]["decision"] = "Unrecorded terminal edit"
        with self.assertRaisesRegex(PipelineError, "differs"):
            validate_projection(self.state, self.root, self.binding, changed)
        del changed["technical_decisions"]
        with self.assertRaisesRegex(PipelineError, "differs"):
            validate_projection(self.state, self.root, self.binding, changed)
        self.assertNotIn("technical_decisions", self.state)

    def test_updates_replace_stable_id_preserve_other_groups_and_reject_stale_conflicts(self):
        first, second = decision(), decision("TD-QA-SECOND")
        initial = self.record(0, [self.row()], technical_decisions=[first])
        self.assertTrue(initial["valid"])
        result = self.record(1, [self.row("reset")], technical_decisions=[second])
        self.assertEqual([first, second], self.controller.qa_read("qa-current")["technical_decisions"])
        corrected = {**first, "checks": [*first["checks"], "fixture:independent-definition-recheck"]}
        result = self.record(2, [], technical_decisions=[corrected])
        self.assertEqual([corrected, second], self.controller.qa_read("qa-current")["technical_decisions"])
        self.assertEqual(3, result["revision"])
        retry = self.record(2, [], technical_decisions=[corrected])
        self.assertTrue(retry["valid"])
        self.assertEqual(3, retry["revision"])
        snapshot = Path(result["working_path"]).read_bytes()
        stale = self.record(2, [self.row()], technical_decisions=[first])
        self.assertFalse(stale["valid"])
        self.assertIn("stale QA draft revision", str(stale["errors"]))
        self.assertEqual(snapshot, Path(result["working_path"]).read_bytes())
        empty = self.record(3, [self.row()], technical_decisions=[])
        self.assertEqual([corrected, second], self.controller.qa_read("qa-current")["technical_decisions"])
        self.assertEqual(3, empty["revision"])
        omitted = self.record(3, [self.row("core")])
        self.assertEqual([corrected, second], self.controller.qa_read("qa-current")["technical_decisions"])
        self.assertEqual(4, omitted["revision"])

    def test_malformed_or_controller_owned_decisions_reject_atomically_with_canonical_validator(self):
        first = self.record(0, [self.row()], technical_decisions=[decision()])
        path = Path(first["working_path"])
        snapshot = path.read_bytes()
        access = deepcopy(self.state["active_assignment"]["access"])
        for entries in (None, {}, [None], [decision(), decision()], [{**decision(), "id": "INVALID"}],
                        [{**decision(), "checks": "unverified"}], [{**decision(), "basis": ""}],
                        [{**decision(), "execution": {"additional_paths": ["game.txt"]}}],
                        [{**decision(), "additional_paths": ["game.txt"]}],
                        [{**decision(), "observations": [None]}]):
            with self.subTest(entries=entries):
                request = {"expected_revision": 1, "assessments": [self.row("reset")], "technical_decisions": entries}
                original = deepcopy(request)
                result = self.controller.qa_record("qa-current", request)
                self.assertFalse(result["valid"])
                self.assertEqual("/technical_decisions", result["errors"][0]["path"])
                self.assertEqual((1, 1, 2), (result["revision"], result["assessed"], result["pending"]))
                self.assertEqual(snapshot, path.read_bytes())
                self.assertEqual(original, request)
                with self.assertRaises(PipelineError) as terminal_error:
                    _worker_artifact({"outcome": "pass", "summary": "Fixture", "technical_decisions": entries}, "engineering", "engineer")
                self.assertEqual(result["errors"][0]["message"], str(terminal_error.exception))
        self.assertEqual(access, self.state["active_assignment"]["access"])
        self.assertFalse((path.parent / "qa-current.json").exists())

    def test_absent_decisions_preserve_existing_v1_draft_and_output_shape(self):
        initial = self.controller.qa_draft("qa-current")
        path = Path(initial["working_path"])
        self.assertEqual({"format", "binding", "revision", "assessments"}, set(read_json(path)))
        self.assertNotIn("technical_decisions", initial)
        rejected = self.record(0, [])
        self.assertFalse(rejected["valid"])
        result = self.record(0, [self.row(key) for key in ("enter", "reset", "core")])
        self.assertTrue(result["valid"])
        self.assertNotIn("technical_decisions", read_json(path))
        finalized = self.controller.qa_finalize("qa-current", 1)
        self.assertTrue(finalized["valid"])
        artifact = read_json(Path(finalized["path"]))
        self.assertEqual({"outcome", "checks"}, set(artifact))
        validate_projection(self.state, self.root, self.binding, artifact)

    def test_decisions_cannot_be_reused_after_assignment_candidate_authority_runtime_or_contract_drift(self):
        result = self.record(0, [self.row()], technical_decisions=[decision()])
        path = Path(result["working_path"])
        snapshot = path.read_bytes()
        for field in ("assignment_id", "candidate_tree_oid", "authority_digest", "pipeline_runtime_digest", "run_id"):
            with self.subTest(field=field), self.assertRaises(PipelineError):
                load(self.state, self.root, {**self.binding, field: "different"}, create=True)
            self.assertEqual(snapshot, path.read_bytes())
        self.definition["identities"][0]["assertions"][0]["expected"] = "Different requirement"
        with self.assertRaises(PipelineError):
            load(self.state, self.root, self.binding, create=True)
        self.assertEqual(snapshot, path.read_bytes())

    def test_stored_malformed_decision_is_rejected_without_reset_or_finalization(self):
        result = self.record(0, [self.row()], technical_decisions=[decision()])
        path = Path(result["working_path"])
        draft = read_json(path)
        draft["technical_decisions"][0]["execution"] = {}
        write_json(path, draft)
        snapshot = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "technical decision requires"):
            load(self.state, self.root, self.binding, create=True)
        self.assertEqual(snapshot, path.read_bytes())
        self.assertFalse((path.parent / "qa-current.json").exists())

    def test_decision_does_not_authorize_substituted_method_or_producer(self):
        self.set_producer()
        request = {"record_id": "layout", "invocation": {"channel": "external-playwright.chromium"},
                   "environment": {"browser": "Chrome"}, "input_paths": []}
        raw = self.root / "capture.bin"
        raw.write_bytes(b"actual external fixture capture")
        begin(self.root, "feature", request, self.binding)
        captured = capture(self.root, "feature", "layout", raw, request["environment"], self.binding)
        entry = {**decision(), "decision": "Treat the external capture as equivalent to the approved producer."}
        row = self.row()
        row["evidence"][0]["ref"] = captured["ref"]
        result = self.record(0, [row], technical_decisions=[entry])
        self.assertFalse(result["valid"])
        self.assertIn("external-playwright.chromium", str(result["errors"]))
        self.assertEqual((0, 0, 3), (result["revision"], result["assessed"], result["pending"]))
        self.assertNotIn("technical_decisions", result)
        row["method_id"] = "unapproved-alternative"
        result = self.record(0, [row], technical_decisions=[entry])
        self.assertFalse(result["valid"])
        self.assertEqual(0, result["assessed"])


if __name__ == "__main__":
    unittest.main()
