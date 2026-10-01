"""Run on a frozen runtime: incremental QA decisions reach the native journal."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest import mock

from pipeline_v2.artifact_io import read_json, write_json
from pipeline_v2.checkout import candidate_tree_oid, pipeline_runtime_digest
from pipeline_v2.model import PipelineError, WorkerArtifactValidationError
from pipeline_v2.runner import Controller
from pipeline_v2.technical_decisions import journal_digest
from pipeline_v2.tests import test_qa_working_native as fixtures
from pipeline_v2.tests.test_qa_decision_draft import decision


class QADecisionNativeTests(unittest.TestCase):
    setUp = fixtures.QAWorkingNativeTests.setUp
    rows = fixtures.QAWorkingNativeTests.rows

    def test_incremental_decision_reaches_journal_and_requires_fresh_review(self):
        controller, assignment = self.h.controller, self.active["id"]
        before = self.h.store.load()
        runtime = pipeline_runtime_digest()
        self.assertEqual(runtime, before["pipeline_runtime_digest"])
        candidate = candidate_tree_oid(self.h.root)
        entry = decision()
        rows = self.rows()
        first = controller.qa_record(assignment, {"expected_revision": 0, "assessments": rows[:1], "technical_decisions": [entry]})
        self.assertTrue(first["valid"], first.get("errors"))
        self.assertEqual((1, 1, 1), (first["revision"], first["assessed"], first["pending"]))
        self.assertEqual(before, self.h.store.load(), "A draft update must not write the canonical journal")
        controller = Controller(self.h.store, timeout=10)  # Resume from disk in a fresh controller.
        self.assertEqual([entry], controller.qa_read(assignment)["technical_decisions"])
        self.assertFalse(controller.qa_finalize(assignment, 1)["valid"])
        result = controller.qa_record(assignment, {"expected_revision": 1, "assessments": rows[1:]})
        self.assertTrue(result["valid"], result.get("errors"))
        finalized = controller.qa_finalize(assignment, 2)
        self.assertTrue(finalized["valid"], finalized.get("errors"))
        output = Path(finalized["path"])
        artifact = read_json(output)
        self.assertEqual([entry], artifact["technical_decisions"])
        self.assertEqual(before, self.h.store.load())
        action = controller.status()["next_action"]
        with mock.patch("pipeline_v2.runner.run_process_tree") as process:
            forbidden = deepcopy(artifact)
            forbidden["technical_decisions"][0]["execution"] = {"additional_paths": ["unauthorized.txt"]}
            write_json(output, forbidden)
            with self.assertRaises(PipelineError):
                controller.complete(command_id=action["command_id"], expected_generation=action["expected_generation"])
            replaced = deepcopy(artifact)
            replaced["technical_decisions"][0]["decision"] = "Unrecorded semantic change"
            write_json(output, replaced)
            with self.assertRaisesRegex(WorkerArtifactValidationError, "differs"):
                controller.complete(command_id=action["command_id"], expected_generation=action["expected_generation"])
            with self.assertRaisesRegex(PipelineError, "Engineering assignment"):
                controller.technical_action(command_id="qa-cannot-engineer", expected_generation=before["generation"],
                    packet={"assignment_id": assignment, "observed_tree_oid": candidate, "entry": entry, "additional_paths": ["unauthorized.txt"]})
            process.assert_not_called()
        self.assertEqual(before, self.h.store.load())
        self.assertTrue(controller.qa_finalize(assignment, 2)["valid"])
        completed = controller.complete(command_id=action["command_id"], expected_generation=action["expected_generation"])
        self.assertEqual({entry["id"]: entry}, completed["technical_decisions"])
        record = completed["artifacts"]["qa"]
        self.assertEqual(assignment, record["assignment_id"])
        self.assertEqual(artifact, record["worker"])
        self.assertEqual(journal_digest(completed["technical_decisions"]), record["technical_journal_digest"])
        self.assertEqual(runtime, record["controller"]["pipeline_runtime_digest"])
        self.assertEqual(before["authority"], completed["authority"])
        self.assertEqual(candidate, candidate_tree_oid(self.h.root))
        action = controller.status()["next_action"]
        accepted = controller.transition({"name": "accept", "id": action["command_id"], "expected_generation": action["expected_generation"]})
        self.assertEqual("review", accepted["phase"], "The old Review cannot accept a new semantic journal")
        self.assertNotIn("review", accepted["artifacts"])
        self.assertEqual(completed["artifacts"]["qa"], accepted["artifacts"]["qa"])
        action = controller.status()["next_action"]
        issued = controller.next(command_id=action["command_id"], expected_generation=action["expected_generation"])
        context = issued["active_assignment"]["capsule"]["context"]
        self.assertEqual([entry], context["technical_decisions"])
        self.assertEqual(journal_digest(completed["technical_decisions"]), context["technical_journal"]["sha256"])
        self.assertEqual(runtime, pipeline_runtime_digest(), "Native evidence must bind one unchanged runtime")


if __name__ == "__main__":
    unittest.main()
