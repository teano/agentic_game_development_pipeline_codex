from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock

SCRIPTS = Path(__file__).resolve().parents[2]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from pipeline_v2.cli import main, parser, run
from pipeline_v2.checkout import candidate_tree_oid
from pipeline_v2.delivery import director_brief, execute_step, export_assignment, json_patch, read_delivery, read_file
from pipeline_v2.model import PipelineError, canonical_bytes


def apply_patch(document, patch):
    """Independent small RFC 6902 interpreter for reconstruction assertions."""
    result = deepcopy(document)
    for operation in patch:
        if operation["path"] == "":
            result = deepcopy(operation["value"])
            continue
        parts = [part.replace("~1", "/").replace("~0", "~") for part in operation["path"][1:].split("/")]
        parent = result
        for part in parts[:-1]:
            parent = parent[int(part)] if isinstance(parent, list) else parent[part]
        key = int(parts[-1]) if isinstance(parent, list) else parts[-1]
        if operation["op"] == "remove":
            del parent[key]
        elif operation["op"] == "add" and isinstance(parent, list):
            parent.insert(key, deepcopy(operation["value"]))
        else:
            parent[key] = deepcopy(operation["value"])
    return result


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.workflow = ".agentic-pipeline/Workflows/test"
        self.view = {"run_id": "run", "feature": "test", "workflow_path": self.workflow, "generation": 4,
            "next_action": {"kind": "command", "command": "complete"},
            "active_assignment": {"id": "A-1", "role": "Engineering", "worker_id": "W-1",
                "access": {"read": ["src/**"], "write": ["src/**"]}, "output_path": "a.json",
                "context": {"technical_decisions": [{"id": "T-1", "text": "unchanged " * 600},
                    {"id": "T-2", "text": "Привет 🌍\r\n" * 1000}]}}}
        (self.root / "src").mkdir()
        (self.root / "src" / "a.txt").write_bytes("Привет 🌍\r\n".encode("utf-8"))

    def receive(self, version, limit=127):
        offset = 0
        pieces = []
        while True:
            page = read_delivery(self.root, self.workflow, version, offset, limit)
            self.assertLessEqual(len(page["text"]), limit)
            self.assertEqual(offset, page["offset"])
            pieces.append(page["text"])
            if page["complete"]:
                self.assertIsNone(page["next_offset"])
                break
            offset = page["next_offset"]
        text = "".join(pieces)
        self.assertEqual(version, hashlib.sha256(text.encode("utf-8")).hexdigest())
        return json.loads(text)

    def test_unicode_full_delta_reconstructs_exact_assignment_without_unchanged_text(self):
        full = export_assignment(self.root, self.view, inputs=["src/a.txt"])
        before = self.receive(full["response_digest"])
        self.assertFalse(full["delivery_complete"])
        self.assertEqual(self.view["active_assignment"], before["assignment"])
        self.assertEqual(1, len(before["selected_inputs"]))
        self.view["generation"] += 1
        self.view["active_assignment"]["id"] = "A-2"
        self.view["active_assignment"]["context"]["technical_decisions"][1]["text"] = "Fixed completely."
        result = export_assignment(self.root, self.view, full["packet_digest"], ["src/a.txt"])
        delta = self.receive(result["response_digest"])
        self.assertNotIn("unchanged", json.dumps(delta))
        rebuilt = apply_patch(before, delta["patch"])
        self.assertEqual(result["packet_digest"], hashlib.sha256(canonical_bytes(rebuilt)).hexdigest())
        self.assertEqual(self.view["active_assignment"], rebuilt["assignment"])
        identical = export_assignment(self.root, self.view, result["packet_digest"], ["src/a.txt"])
        self.assertEqual([], self.receive(identical["response_digest"])["patch"])

    def test_patch_handles_deletion_appends_types_empty_values_and_escaped_keys(self):
        before = {"a/b": [{"~": 2}, 4, 5], "delete": 0, "type": False}
        after = {"a/b": [{"~": 3}], "add": [1, 2], "type": 0}
        self.assertEqual(after, apply_patch(before, json_patch(before, after)))
        self.assertEqual(before, apply_patch(after, json_patch(after, before)))
        self.assertEqual({"value": 0}, apply_patch({"value": False}, json_patch({"value": False}, {"value": 0})))
        self.assertTrue(json_patch({"value": False}, {"value": 0}))

    def test_section_reader_delivers_whole_requested_value_without_other_fields(self):
        full = export_assignment(self.root, self.view)
        pointer = "/assignment/context/technical_decisions/0"
        page = read_delivery(self.root, self.workflow, full["packet_digest"], pointer=pointer)
        self.assertTrue(page["complete"])
        self.assertEqual(self.view["active_assignment"]["context"]["technical_decisions"][0], json.loads(page["text"]))
        self.assertNotIn("Привет", page["text"])
        self.assertEqual(pointer, page["pointer"])
        for invalid in ("missing", "/missing", "/assignment/context/technical_decisions/-1"):
            with self.assertRaises(PipelineError):
                read_delivery(self.root, self.workflow, full["packet_digest"], pointer=invalid)

    def test_fresh_worker_or_role_cannot_reuse_prior_packet(self):
        full = export_assignment(self.root, self.view)
        for field in ("worker_id", "role"):
            changed = deepcopy(self.view)
            changed["active_assignment"][field] = "different"
            with self.assertRaisesRegex(PipelineError, "same run, role and worker"):
                export_assignment(self.root, changed, full["packet_digest"])

    def test_reader_preserves_crlf_unicode_and_rejects_changed_or_unversioned_continuation(self):
        page = read_file(self.root, self.view, "src/a.txt", limit=8)
        rest = read_file(self.root, self.view, "src/a.txt", version=page["version"], offset=page["next_offset"])
        self.assertEqual("Привет 🌍\r\n", page["text"] + rest["text"])
        with self.assertRaisesRegex(PipelineError, "require the previous page version"):
            read_file(self.root, self.view, "src/a.txt", offset=1)
        (self.root / "src/a.txt").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(PipelineError, "changed"):
            read_file(self.root, self.view, "src/a.txt", version=page["version"], offset=1)
        fresh = read_file(self.root, self.view, "src/a.txt")
        self.assertNotEqual(page["version"], fresh["version"])

    def test_read_scope_selection_path_and_corrupt_snapshot_guards(self):
        with self.assertRaises(PipelineError):
            read_file(self.root, self.view, "../escape.txt")
        with self.assertRaisesRegex(PipelineError, "outside"):
            export_assignment(self.root, self.view, inputs=["private.txt"])
        with self.assertRaisesRegex(PipelineError, "outside"):
            read_file(self.root, self.view, "private.txt")
        full = export_assignment(self.root, self.view)
        (self.root / full["path"]).write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(PipelineError, "digest does not match"):
            read_delivery(self.root, self.workflow, full["response_digest"])

    def test_boundary_actions_never_dispatch(self):
        for action in ({"kind": "controller_decision", "command": "answer"},
                       {"kind": "terminal", "result": "recovery_required"},
                       {"kind": "command", "command": "init"},
                       {"kind": "command", "command": "ready"}):
            controller = Mock()
            controller.status.return_value = {"generation": 4, "next_action": action}
            controller.store.load.return_value = {"history": []}
            result = execute_step(controller, self.root, 4, "unused")
            self.assertEqual("stopped", result["result"])
            controller.next.assert_not_called()
            controller.complete.assert_not_called()
            controller.transition.assert_not_called()

    def test_brief_next_omits_packet_but_keeps_exact_action_and_semantic_boundaries(self):
        view = deepcopy(self.view)
        view["active_assignment"] = None
        view["next_action"] = {"kind": "command", "command": "next", "command_id": "NEXT-1", "expected_generation": 4,
                               "assignment": self.view["active_assignment"]}
        brief = director_brief(view)
        self.assertEqual("NEXT-1", brief["next_action"]["command_id"])
        self.assertEqual(4, brief["next_action"]["expected_generation"])
        self.assertNotIn("unchanged", json.dumps(brief))
        self.assertFalse(brief["next_action"]["assignment"]["content_included"])
        for action in ({"kind": "controller_decision", "command": "answer", "prompt": "Resolve the actual semantic question"},
                       {"kind": "terminal", "recovery_binding": {"exact": "binding"}, "result": "recovery_required"}):
            view["next_action"] = action
            self.assertEqual(action, director_brief(view)["next_action"])


class ControllerDeliveryIntegrationTests(unittest.TestCase):
    def setUp(self):
        from pipeline_v2.tests.test_core import PipelineV2CoreTests
        from pipeline_v2.runner import Controller
        self.fixture = PipelineV2CoreTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.root
        self.controller = Controller(self.fixture.store)

    def test_cli_step_issues_once_retries_without_advancing_and_waits_for_real_artifact(self):
        initial_tree = candidate_tree_oid(self.root)
        action = self.controller.status()["next_action"]
        argv = ["--root", str(self.root), "--feature", self.fixture.feature, "step",
                "--expected-generation", str(action["expected_generation"]), "--action-id", action["command_id"]]
        issued = run(parser().parse_args(argv))
        self.assertEqual("executed", issued["result"])
        self.assertIn("assignment_delivery", issued)
        self.assertEqual(initial_tree, candidate_tree_oid(self.root))
        replay = run(parser().parse_args(argv))
        self.assertEqual("already_applied", replay["result"])
        self.assertEqual(issued["generation"], replay["generation"])
        action = self.controller.status()["next_action"]
        result = execute_step(self.controller, self.root, action["expected_generation"], action["command_id"])
        self.assertEqual("waiting_for_artifact", result["result"])
        self.assertEqual(issued["generation"], self.controller.status()["generation"])

    def test_stale_or_wrong_action_cannot_execute(self):
        action = self.controller.status()["next_action"]
        with self.assertRaisesRegex(PipelineError, "stale"):
            execute_step(self.controller, self.root, action["expected_generation"] + 1, action["command_id"])
        with self.assertRaisesRegex(PipelineError, "action ID"):
            execute_step(self.controller, self.root, action["expected_generation"], "wrong")
        self.assertIsNone(self.controller.status()["active_assignment"])

    def test_step_complete_validates_artifact_and_accept_is_a_separate_action(self):
        action = self.controller.status()["next_action"]
        execute_step(self.controller, self.root, action["expected_generation"], action["command_id"])
        action = self.controller.status()["next_action"]
        self.fixture._write_artifact({"outcome": "invented", "summary": "Invalid semantic result."})
        with self.assertRaises(PipelineError):
            execute_step(self.controller, self.root, action["expected_generation"], action["command_id"])
        self.assertEqual(action["expected_generation"], self.controller.status()["generation"])
        self.fixture._write_artifact({"outcome": "pass", "summary": "Delivered the assigned result."})
        completed = execute_step(self.controller, self.root, action["expected_generation"], action["command_id"])
        self.assertEqual("complete", completed["command"])
        self.assertEqual("accept", self.controller.status()["next_action"]["command"])
        action = self.controller.status()["next_action"]
        accepted = execute_step(self.controller, self.root, action["expected_generation"], action["command_id"])
        self.assertEqual("accept", accepted["command"])
        self.assertEqual("next", self.controller.status()["next_action"]["command"])

    def test_brief_cli_status_and_technical_actions_do_not_print_unchanged_journal(self):
        self.fixture._reach_engineering("-brief")
        action = self.controller.status()["next_action"]
        self.controller.next(command_id=action["command_id"], expected_generation=action["expected_generation"])
        prefix = ["--root", str(self.root), "--feature", self.fixture.feature]
        unchanged = "UNCHANGED-REQUIRED-DETAIL " * 2500

        def brief_stdout(command):
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, main(prefix + ["--brief"] + command))
            self.assertNotIn("UNCHANGED-REQUIRED-DETAIL", output.getvalue())
            return json.loads(output.getvalue())

        def decision(identifier, decision_text):
            state = self.fixture.store.load()
            packet = {"assignment_id": state["active_assignment"]["id"], "observed_tree_oid": candidate_tree_oid(self.root),
                "entry": {"id": identifier, "situation": "Observed bounded issue", "decision": decision_text,
                    "basis": "Exact observed behavior", "checks": ["Inspect the actual changed bytes"],
                    "downstream": "Independent Review and QA remain mandatory"}}
            path = self.root / self.fixture.workflow_path / "decision-input.json"
            path.write_text(json.dumps(packet), encoding="utf-8")
            return brief_stdout(["technical-decision", "--id", identifier, "--expected-generation", str(state["generation"]),
                                 "--packet", str(path)])

        first = decision("TD-FIRST", unchanged)
        self.assertFalse(first["active_assignment"]["content_included"])
        self.assertEqual(1, first["technical_journal"]["count"])
        baseline = run(parser().parse_args(prefix + ["assignment-export"]))
        full_packet = json.loads((self.root / baseline["path"]).read_text(encoding="utf-8"))
        self.assertEqual(unchanged, full_packet["assignment"]["context"]["technical_decisions"][0]["decision"])
        brief = brief_stdout(["status"])
        self.assertEqual(first["active_assignment"]["id"], brief["active_assignment"]["id"])
        full_output = io.StringIO()
        with redirect_stdout(full_output):
            self.assertEqual(0, main(prefix + ["status"]))
        self.assertIn("UNCHANGED-REQUIRED-DETAIL", full_output.getvalue())
        second = decision("TD-SECOND", "Apply the exact small additional decision")
        self.assertEqual(2, second["technical_journal"]["count"])
        delta_export = run(parser().parse_args(prefix + ["assignment-export", "--baseline", baseline["packet_digest"]]))
        delta = json.loads((self.root / delta_export["path"]).read_text(encoding="utf-8"))
        self.assertNotIn("UNCHANGED-REQUIRED-DETAIL", json.dumps(delta))
        self.assertEqual(delta_export["packet_digest"], hashlib.sha256(canonical_bytes(apply_patch(full_packet, delta["patch"]))).hexdigest())
        state = self.fixture.store.load()
        observed = brief_stdout(["technical-observe", "--id", "OBS-BRIEF", "--expected-generation", str(state["generation"]),
                                 "--action", "Inspect the current project state"])
        self.assertEqual("OBS-BRIEF", observed["active_assignment"]["technical_observation"]["id"])
        self.assertEqual(candidate_tree_oid(self.root), observed["active_assignment"]["technical_observation"]["tree"])


if __name__ == "__main__":
    unittest.main()
