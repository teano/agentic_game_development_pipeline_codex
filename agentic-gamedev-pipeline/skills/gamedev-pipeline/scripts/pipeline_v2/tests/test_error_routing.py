from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest


SCRIPTS = Path(__file__).resolve().parents[2]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from pipeline_v2.execution import classify_error
from pipeline_v2.model import PipelineError, WorkerArtifactValidationError
from pipeline_v2.reducer import _worker_artifact
from pipeline_v2.runner import Controller
from pipeline_v2.tests import test_core as fixtures


class NativeArtifactErrorRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = fixtures.PipelineV2CoreTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.controller = Controller(self.fixture.store)
        action = self.controller.status()["next_action"]
        self.controller.next(command_id=action["command_id"], expected_generation=action["expected_generation"])
        self.complete_action = self.controller.status()["next_action"]
        self.argv = [
            sys.executable, "-B", str(SCRIPTS / "pipeline_state.py"),
            "--root", str(self.fixture.root), "--feature", self.fixture.feature, "--brief", "complete",
            "--id", self.complete_action["command_id"],
            "--expected-generation", str(self.complete_action["expected_generation"]),
        ]

    def invoke(self, artifact: dict, *extra: str) -> tuple[dict, bytes]:
        self.fixture._write_artifact(artifact)
        before = self.fixture.store.path.read_bytes()
        result = subprocess.run([*self.argv, *extra], capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(2, result.returncode, result.stdout or result.stderr)
        self.assertEqual(before, self.fixture.store.path.read_bytes())
        return json.loads(result.stderr), before

    def test_native_missing_and_empty_summary_are_same_owner_artifact_corrections(self) -> None:
        cases = (
            ({"outcome": "pass"},
             "plan worker artifact must use only ['blocker', 'outcome', 'questions', 'required_action', 'summary', 'technical_decisions'] and require ['outcome', 'summary']"),
            ({"outcome": "pass", "summary": ""}, "summary is required"),
        )
        active_id = self.fixture.store.load()["active_assignment"]["id"]
        for artifact, expected_error in cases:
            with self.subTest(artifact=artifact):
                response, _ = self.invoke(artifact)
                self.assertEqual(expected_error, response["error"])
                self.assertEqual("artifact_format", response["category"])
                self.assertFalse(response["retryable"])
                self.assertEqual("Correct only the same owned output artifact truthfully and resubmit.",
                                 response["required_action"])
                self.assertEqual(active_id, self.fixture.store.load()["active_assignment"]["id"])

    def test_qa_validator_keeps_the_same_typed_route(self) -> None:
        with self.assertRaises(WorkerArtifactValidationError) as caught:
            _worker_artifact({
                "outcome": "pass",
                "checks": [{"id": "AUTO-QA", "outcome": "pass", "evidence": ""}],
            }, "qa", "qa", ["AUTO-QA"])
        self.assertIsInstance(caught.exception, PipelineError)
        response = classify_error(caught.exception)
        self.assertEqual("artifact_format", response["category"])
        self.assertEqual("QA checks require exact id, outcome (pass|fail|not_run), and non-empty execution evidence",
                         response["error"])

    def test_non_validator_and_stale_errors_keep_their_existing_routes(self) -> None:
        self.assertEqual("invalid_request", classify_error(PipelineError("worker artifact text alone is not typed"))["category"])

        alternate = self.fixture.root / self.fixture.workflow_path / "other-artifact.json"
        alternate.parent.mkdir(parents=True, exist_ok=True)
        alternate.write_text("{}", encoding="utf-8")
        response, _ = self.invoke(
            {"outcome": "pass", "summary": "Truthful plan result."}, "--artifact",
            alternate.relative_to(self.fixture.root).as_posix(),
        )
        self.assertEqual("invalid_request", response["category"])

        stale = [*self.argv]
        generation = stale.index("--expected-generation") + 1
        stale[generation] = str(self.complete_action["expected_generation"] - 1)
        self.fixture._write_artifact({"outcome": "pass", "summary": "Truthful plan result."})
        before = self.fixture.store.path.read_bytes()
        result = subprocess.run(stale, capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(2, result.returncode, result.stdout or result.stderr)
        self.assertEqual(before, self.fixture.store.path.read_bytes())
        response = json.loads(result.stderr)
        self.assertEqual("stale_action", response["category"])
        self.assertTrue(response["retryable"])


if __name__ == "__main__":
    unittest.main()
