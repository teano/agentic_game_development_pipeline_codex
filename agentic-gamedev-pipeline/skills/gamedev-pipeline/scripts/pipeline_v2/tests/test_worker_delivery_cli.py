"""Native default-short check, exact replay and decoded reader integration."""
import io
import hashlib
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline_v2.cli import parser, run, main
from pipeline_v2.delivery import export_assignment
from pipeline_v2.process_tree import ProcessEvidence
from pipeline_v2.tests import test_core


def captured_failure(stdout, stderr):
    def execute(*args, **kwargs):
        kwargs["stdout_path"].write_bytes(stdout)
        kwargs["stderr_path"].write_bytes(stderr)
        return ProcessEvidence(7, hashlib.sha256(stdout).hexdigest(), hashlib.sha256(stderr).hexdigest(),
                               stderr, False, stdout, False, 12,
                               stderr_raw_sha256=hashlib.sha256(stderr).hexdigest())
    return execute


class WorkerDeliveryCLITests(unittest.TestCase):
    def setUp(self):
        self.h = test_core.PipelineV2CoreTests("runTest")
        self.h.setUp()
        self.addCleanup(self.h.tearDown)
        self.h._reach_engineering("-worker-delivery")
        action = self.h.controller.status()["next_action"]
        self.h.controller.next(command_id=action["command_id"], expected_generation=action["expected_generation"])
        self.prefix = ["--root", str(self.h.root), "--feature", self.h.feature]

    def test_default_check_is_short_and_replay_neither_runs_checks_nor_exports(self):
        state = self.h.store.load()
        active = state["active_assignment"]
        argv = self.prefix + ["check", "--id", "short-check", "--expected-generation", str(state["generation"]),
                "--assignment-id", active["id"], "--quiescence", "All owned work is stopped."]
        delivery = self.h.root / self.h.workflow_path / "Delivery"
        before = sorted(delivery.glob("*.json"))
        with mock.patch("pipeline_v2.runner.run_process_tree",
                        side_effect=captured_failure(b"full output detail", b"full failure detail")) as process:
            result = run(parser().parse_args(argv))
            saved = self.h.store.path.read_bytes()
            replay = run(parser().parse_args(argv))
            full = run(parser().parse_args(self.prefix + ["--full"] + argv[len(self.prefix):]))
            self.assertEqual(1, process.call_count)
        self.assertEqual(saved, self.h.store.path.read_bytes())
        self.assertEqual(before, sorted(delivery.glob("*.json")))
        self.assertEqual(result, replay)
        self.assertNotIn("context", result["active_assignment"])
        self.assertIn("context", full["active_assignment"])
        self.assertNotIn("qa_contract", json.dumps(result))
        diagnostic = result["active_assignment"]["diagnostic_checks"]
        self.assertEqual(7, diagnostic["results"][0]["returncode"])
        self.assertIn("pending_check_ids", diagnostic)
        self.assertFalse(diagnostic["grants_semantic_credit"])
        self.assertFalse(diagnostic["grants_manual_acceptance"])
        self.assertEqual("assignment-export", result["assignment_delivery"]["command"])
        packet = export_assignment(self.h.root, self.h.controller.status())
        read = run(parser().parse_args(self.prefix + ["assignment-read", "--digest", packet["packet_digest"],
                    "--view", "value", "--pointer", "/assignment/context/diagnostic_checks"]))
        self.assertIn("full failure detail", json.dumps(read))
        self.assertTrue(read["unit_complete"])
        self.assertFalse(read["delivery_complete"])

    def test_reader_default_is_structural_unit_and_text_is_not_an_encoded_json_payload(self):
        packet = export_assignment(self.h.root, self.h.controller.status())
        argv = self.prefix + ["assignment-read", "--digest", packet["packet_digest"]]
        state_before = self.h.store.path.read_bytes()
        files_before = sorted((self.h.root / self.h.workflow_path / "Delivery").glob("*.json"))
        result = run(parser().parse_args(argv))
        self.assertEqual("unit", result["view"])
        self.assertNotIn("value", result)
        self.assertFalse(result["unit_complete"])
        self.assertFalse(result["delivery_complete"])
        rows = {item["selector"]: item for item in result["children"]}
        active = self.h.controller.status()["active_assignment"]
        for key in ("id", "output_path", "role", "task", "worker_id"):
            self.assertEqual(active[key], rows[key]["value"])
        self.assertNotIn("value", rows["context"])
        startup = run(parser().parse_args(packet["dispatch"]["reader"]["bootstrap_argv"][2:]))
        self.assertEqual("bootstrap", startup["view"])
        self.assertFalse(startup["delivery_complete"])
        explicit_index = run(parser().parse_args(argv + ["--view", "index"]))
        self.assertEqual("index", explicit_index["view"])
        self.assertTrue(all("value" not in item for item in explicit_index["children"]))
        default_text = io.StringIO()
        with redirect_stdout(default_text):
            self.assertEqual(0, main(argv))
        header, body = default_text.getvalue().split("\n", 1)
        self.assertEqual("unit", json.loads(header)["view"])
        self.assertEqual(result["children"], json.loads(body))
        scalar_text = io.StringIO()
        with redirect_stdout(scalar_text):
            self.assertEqual(0, main(argv + ["--pointer", "/assignment/id"]))
        self.assertEqual(active["id"], scalar_text.getvalue().split("\n", 1)[1].rstrip("\n"))
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, main(argv + ["--view", "value", "--pointer", "/assignment/context/qa_contract/definition/identities/0"]))
        rendered = output.getvalue()
        self.assertNotIn('\\"assertions\\"', rendered)
        self.assertIn('"assertions"', rendered)
        self.assertNotIn('"text":', rendered)
        encoded = io.StringIO()
        with redirect_stdout(encoded):
            self.assertEqual(0, main(argv + ["--view", "value", "--pointer", "/assignment/context/qa_contract/definition/identities/0", "--format", "json"]))
        value = json.loads(encoded.getvalue())["value"]
        self.assertEqual("AUTO-SLICE-1-CORE", value["id"])
        self.assertTrue(value["assertions"])
        self.assertEqual(state_before, self.h.store.path.read_bytes())
        self.assertEqual(files_before, sorted((self.h.root / self.h.workflow_path / "Delivery").glob("*.json")))

    def test_committed_check_transport_failures_and_same_id_replay_do_not_execute_again(self):
        state = self.h.store.load()
        argv = self.prefix + ["check", "--id", "composed-check", "--expected-generation", str(state["generation"]),
                "--assignment-id", state["active_assignment"]["id"], "--quiescence", "All owned work is stopped.", "--with-delivery"]
        with mock.patch("pipeline_v2.runner.run_process_tree",
                        side_effect=captured_failure(b"full output", b"complete independent failure")) as process:
            with mock.patch("pipeline_v2.cli.export_assignment", side_effect=OSError("export failed after commit")):
                failed = run(parser().parse_args(argv))
            saved = self.h.store.path.read_bytes()
            self.assertTrue(failed["committed"])
            self.assertEqual(state["generation"] + 1, failed["committed_generation"])
            self.assertEqual("failed", failed["transport"]["status"])
            self.assertEqual(failed["generation"], failed["next_action"]["expected_generation"])
            recovered = run(parser().parse_args(failed["recovery"]["export_argv"][2:]))
            self.assertEqual(failed["generation"], recovered["generation"])
            with mock.patch("pipeline_v2.cli._render_assignment_unit", side_effect=RuntimeError("render failed")) as render:
                compact = run(parser().parse_args(argv))
                render.assert_not_called()
            self.assertEqual("delivered", compact["transport"]["status"])
            self.assertIn("read_argv", compact["recovery"])
            self.assertNotIn("check_result", compact)
            replay = run(parser().parse_args(argv))
            self.assertEqual("delivered", replay["transport"]["status"])
            self.assertEqual(1, process.call_count)
        self.assertEqual(saved, self.h.store.path.read_bytes())
        read = replay["recovery"]["read_argv"][2:]
        self.assertIn("--assemble", read)
        selected = run(parser().parse_args(read))
        self.assertTrue(selected["selection_complete"])
        body = selected["value"]
        self.assertIn("complete independent failure", json.dumps(body["check_context"]["diagnostic_checks"]))
        self.assertIn("pending_check_ids", body["check_context"]["machine_checks"])
        self.assertFalse(body["check_context"]["machine_checks"]["grants_manual_acceptance"])
        origin = replay["result"]["checks"][0]
        self.assertTrue(origin["execution_evidence"].startswith("execution-evidence:"))
        evidence = run(parser().parse_args(origin["read_argv"][2:]))["value"]
        self.assertEqual(origin["execution_evidence"], evidence["ref"])
        self.assertEqual(origin["execution_record_digest"], evidence["record"]["digest"])
        self.assertEqual("controller-process-execution", evidence["record"]["provenance"])

    def test_old_check_replay_after_new_check_reports_advanced_cursor_without_export(self):
        state = self.h.store.load()
        base = self.prefix + ["check", "--assignment-id", state["active_assignment"]["id"],
                            "--quiescence", "All owned work is stopped.", "--with-delivery"]
        first = base + ["--id", "first-check", "--expected-generation", str(state["generation"])]
        second = base + ["--id", "second-check", "--expected-generation", str(state["generation"] + 1)]
        with mock.patch("pipeline_v2.runner.run_process_tree",
                        side_effect=captured_failure(b"output", b"failure")) as process:
            run(parser().parse_args(first))
            current = run(parser().parse_args(second))
            before = self.h.store.path.read_bytes()
            with mock.patch("pipeline_v2.cli.export_assignment") as export:
                replay = run(parser().parse_args(first))
                export.assert_not_called()
            self.assertEqual(2, process.call_count)
        self.assertEqual(before, self.h.store.path.read_bytes())
        self.assertEqual("cursor_advanced", replay["transport"]["status"])
        self.assertEqual(current["generation"], replay["generation"])
        self.assertEqual(state["generation"] + 1, replay["committed_generation"])


if __name__ == "__main__":
    unittest.main()
