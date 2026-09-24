"""Complete current rework presentation without broad assignment expansion."""
from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[2]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from pipeline_v2.cli import _render_assignment_unit, main, parser, run
from pipeline_v2.delivery import export_assignment, read_delivery_unit
from pipeline_v2.finding_contract import required_condition_roster
from pipeline_v2.model import PipelineError, canonical_bytes


class DeliveryWorkTests(unittest.TestCase):
    def expand_displayed_evidence(self, body):
        expanded = deepcopy(body)
        for group in expanded["findings"]:
            for row in group["conditions"]:
                evidence = row["latest_independent_result"]["evidence"]
                if isinstance(evidence, dict):
                    self.assertEqual({"same_exact_text_as"}, set(evidence))
                    self.assertTrue(evidence["same_exact_text_as"].startswith("#/"))
                    literal = body
                    for part in evidence["same_exact_text_as"][2:].split("/"):
                        key = part.replace("~1", "/").replace("~0", "~")
                        literal = literal[int(key)] if isinstance(literal, list) else literal[key]
                    self.assertIsInstance(literal, str, "display references must point directly to already printed literal text")
                    row["latest_independent_result"]["evidence"] = literal
        return expanded

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.workflow = ".agentic-pipeline/Workflows/test"
        self.convergence = {
            "open": {
                "F/~": {"id": "F/~", "severity": "high", "kind": "acceptance", "text": "Shared exact explanation 🌍\r\n",
                         "conditions": [{"id": "C1", "text": "Previously verified original condition"},
                                        {"id": "C/~", "text": "Current original condition 🌍\r\n"},
                                        {"id": "C3", "text": "Third original condition"}]},
                "F-OLD": {"id": "F-OLD", "severity": "high", "kind": "acceptance", "text": "Older still-open finding",
                          "conditions": [{"id": "OLD", "text": "Older required condition"}]},
            }, "resolved": [], "repeat_count": 2,
            "condition_status": {
                "F/~": {"C1": {"status": "resolved", "evidence": "Independent verified result"},
                         "C/~": {"status": "unresolved", "evidence": "Latest precise rejection 🌍\r\n"},
                         "C3": {"status": "unresolved", "evidence": "Different latest rejection"}},
                "F-OLD": {"OLD": {"status": "unresolved", "evidence": "Older unresolved evidence"}},
            }, "engineering_resolutions": [{"finding_id": "F/~", "condition_id": "C/~", "status": "addressed",
                                             "evidence": "STALE-ENGINEER-CLAIM"}],
        }
        self.view = {"run_id": "run", "feature": "test", "workflow_path": self.workflow, "generation": 4,
            "next_action": {"command": "complete"},
            "active_assignment": {"id": "A-1", "worker_id": "W-1", "role": "engineer", "task": "Repair the current exact conditions",
                "output_path": "output.json", "access": {"read": ["src/**"], "write": ["src/**"]},
                "context": {"convergence": deepcopy(self.convergence),
                    "required_finding_conditions": required_condition_roster(self.convergence, "engineering"),
                    "qa_contract": {"status": "bound", "binding": {"contract_digest": "a" * 64},
                                    "definition": {"text": "UNRELATED-QA-BODY" * 200}},
                    "technical_decisions": [{"id": "T-OLD", "decision": "UNRELATED-HISTORY-BODY"}]}}}

    def export(self, view=None, baseline=None):
        return export_assignment(self.root, self.view if view is None else view, baseline)

    def read(self, version):
        return read_delivery_unit(self.root, self.workflow, version, view="work")

    def save(self, packet):
        payload = canonical_bytes(packet)
        version = hashlib.sha256(payload).hexdigest()
        directory = self.root / self.workflow / "Delivery"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{version}.json").write_bytes(payload)
        return version

    def test_complete_work_preserves_exact_role_inventory_originals_and_latest_results(self):
        for role, phase, count in (("engineer", "engineering", 3), ("reviewer", "review", 4), ("documentation_finisher", "docs", 3)):
            with self.subTest(role=role):
                view = deepcopy(self.view)
                assignment = view["active_assignment"]
                assignment["role"] = role
                assignment["context"]["required_finding_conditions"] = required_condition_roster(self.convergence, phase)
                exported = self.export(view)
                response = self.read(exported["packet_digest"])
                self.assertTrue(response["work_complete"])
                self.assertFalse(response["unit_complete"])
                self.assertFalse(response["delivery_complete"])
                self.assertEqual(count, response["required_condition_count"])
                self.assertEqual("required_finding_conditions", response["roster_source"])
                self.assertEqual({key: assignment[key] for key in ("id", "worker_id", "role", "task", "output_path")}, response["value"]["assignment"])
                groups = response["value"]["findings"]
                flattened = [row for group in groups for row in group["conditions"]]
                self.assertEqual(assignment["context"]["required_finding_conditions"],
                                 [{key: row[key] for key in ("finding_id", "condition_id", "original_condition_pointer", "latest_independent_result_pointer")} for row in flattened])
                for group in groups:
                    original = self.convergence["open"][group["finding_id"]]
                    self.assertEqual({key: value for key, value in original.items() if key != "conditions"}, group["finding"])
                    for row in group["conditions"]:
                        self.assertEqual(next(item for item in original["conditions"] if item["id"] == row["condition_id"]), row["original_condition"])
                        self.assertEqual(self.convergence["condition_status"][row["finding_id"]][row["condition_id"]], row["latest_independent_result"])
                rendered = json.dumps(response, ensure_ascii=False)
                self.assertEqual(1, rendered.count("Shared exact explanation"))
                for absent in ("UNRELATED-QA-BODY", "UNRELATED-HISTORY-BODY", "STALE-ENGINEER-CLAIM"):
                    self.assertNotIn(absent, rendered)
                self.assertEqual("bootstrap", exported["dispatch"]["reader"]["default_view"])
                self.assertIn("work_argv", exported["dispatch"]["reader"])

    def test_work_is_complete_without_loading_unrelated_qa_resource_and_cli_displays_values(self):
        exported = self.export()
        resource = exported["working_set"]["required_resources"][0]
        (self.root / resource["path"]).unlink()
        expected = self.read(exported["packet_digest"])
        output = io.StringIO()
        argv = exported["dispatch"]["reader"]["work_argv"][2:]
        with redirect_stdout(output):
            self.assertEqual(0, main(argv))
        header, body = output.getvalue().split("\n", 1)
        self.assertEqual("work", json.loads(header)["view"])
        self.assertEqual(expected["value"], json.loads(body))
        self.assertIn("Latest precise rejection", body)
        self.assertIn("Current original condition", body)
        machine = io.StringIO()
        with redirect_stdout(machine):
            self.assertEqual(0, main(argv + ["--format", "json"]))
        self.assertEqual(expected, json.loads(machine.getvalue()))
        self.assertFalse((self.root / self.workflow / "pipeline-state.json").exists())
        for legacy_view in ("unit", "index"):
            result = read_delivery_unit(self.root, self.workflow, exported["packet_digest"], "/assignment", legacy_view)
            self.assertEqual(legacy_view, result["view"])
        value = read_delivery_unit(self.root, self.workflow, exported["packet_digest"], "/assignment/task", "value")
        self.assertEqual(self.view["active_assignment"]["task"], value["value"])

    def test_work_text_shares_exact_finding_evidence_and_preserves_literal_marker_strings(self):
        literal = 'Literal source {"same_exact_text_as":"#/not-a-reference"} 🌍\r\n'
        context = self.view["active_assignment"]["context"]
        context["convergence"]["open"]["F/~"]["text"] = literal
        for condition in ("C/~", "C3"):
            context["convergence"]["condition_status"]["F/~"][condition]["evidence"] = literal
        response = self.read(self.export()["packet_digest"])
        original = deepcopy(response)
        header, text = _render_assignment_unit(response).split("\n", 1)
        metadata, shown = json.loads(header), json.loads(text)
        self.assertIn("no additional read", metadata["text_rendering"])
        self.assertTrue(metadata["work_complete"])
        self.assertFalse(metadata["delivery_complete"])
        self.assertEqual(response["value"], self.expand_displayed_evidence(shown))
        group = next(group for group in shown["findings"] if group["finding_id"] == "F/~")
        self.assertEqual(literal, group["finding"]["text"])
        self.assertTrue(all(isinstance(row["latest_independent_result"]["evidence"], dict) for row in group["conditions"]))
        self.assertEqual(original, response, "human rendering must not change the decoded machine value")

    def test_work_text_shares_prior_evidence_only_and_json_and_explicit_value_stay_expanded(self):
        evidence = "Exact repeated independent rejection 🌍\r\n"
        context = self.view["active_assignment"]["context"]
        for condition in ("C/~", "C3"):
            context["convergence"]["condition_status"]["F/~"][condition]["evidence"] = evidence
        exported = self.export()
        response = self.read(exported["packet_digest"])
        header, text = _render_assignment_unit(response).split("\n", 1)
        shown = json.loads(text)
        self.assertEqual(response["value"], self.expand_displayed_evidence(shown))
        group = next(group for group in shown["findings"] if group["finding_id"] == "F/~")
        first, second = group["conditions"]
        self.assertEqual(evidence, first["latest_independent_result"]["evidence"])
        self.assertIn("/conditions/0/latest_independent_result/evidence",
                      second["latest_independent_result"]["evidence"]["same_exact_text_as"])
        machine = io.StringIO()
        with redirect_stdout(machine):
            self.assertEqual(0, main(exported["dispatch"]["reader"]["work_argv"][2:] + ["--format", "json"]))
        self.assertEqual(response, json.loads(machine.getvalue()))
        ordinary = read_delivery_unit(self.root, self.workflow, exported["packet_digest"],
                                      "/assignment/context/convergence", "value")
        ordinary_header, ordinary_body = _render_assignment_unit(ordinary).split("\n", 1)
        self.assertNotIn("text_rendering", json.loads(ordinary_header))
        self.assertEqual(ordinary["value"], json.loads(ordinary_body))

    def test_wrong_missing_duplicate_roster_or_incomplete_legacy_evidence_never_means_no_work(self):
        for change in ("missing_pair", "duplicate_pair", "wrong_pointer", "missing_evidence", "missing_conditions", "malformed_status"):
            with self.subTest(change=change):
                view = deepcopy(self.view)
                context = view["active_assignment"]["context"]
                if change == "missing_pair": context["required_finding_conditions"].pop()
                elif change == "duplicate_pair": context["required_finding_conditions"].append(deepcopy(context["required_finding_conditions"][0]))
                elif change == "wrong_pointer": context["required_finding_conditions"][0]["latest_independent_result_pointer"] = "/assignment/context/technical_decisions/0"
                elif change == "missing_evidence": context["convergence"]["condition_status"]["F/~"]["C/~"].pop("evidence")
                elif change == "missing_conditions": context["convergence"]["open"]["F/~"].pop("conditions")
                else: context["convergence"]["condition_status"]["F/~"]["C/~"]["status"] = []
                with self.assertRaises(PipelineError):
                    self.read(self.export(view)["packet_digest"])
        missing = deepcopy(self.view)
        missing["active_assignment"]["context"] = {}
        with self.assertRaisesRegex(PipelineError, "complete rework is unavailable"):
            self.read(self.export(missing)["packet_digest"])
        missing["active_assignment"]["context"] = {"required_finding_conditions": []}
        exported = self.export(missing)
        self.assertEqual([], self.read(exported["packet_digest"])["value"]["findings"])
        self.assertEqual("bootstrap", exported["dispatch"]["reader"]["default_view"])
        self.assertNotIn("work_argv", exported["dispatch"]["reader"])
        with self.assertRaisesRegex(PipelineError, "work view selects only"):
            read_delivery_unit(self.root, self.workflow, exported["packet_digest"], "/assignment/context", "work")

    def test_legacy_work_derives_exact_inventory_and_delta_preserves_latest_rejection(self):
        view = deepcopy(self.view)
        view["active_assignment"]["context"].pop("required_finding_conditions")
        legacy = {"format": "pipeline-assignment-v1", "project_root": str(self.root), "run_id": "run", "feature": "test",
                  "generation": 4, "assignment": view["active_assignment"], "selected_inputs": []}
        version = self.save(legacy)
        received = self.read(version)
        self.assertEqual("legacy_convergence", received["roster_source"])
        self.assertEqual(3, received["required_condition_count"])
        original = self.export()
        self.view["generation"] += 1
        self.view["active_assignment"]["context"]["convergence"]["condition_status"]["F/~"]["C/~"]["evidence"] = "Changed exact latest rejection"
        changed = self.export(baseline=original["packet_digest"])
        response = self.read(changed["response_digest"])
        self.assertEqual(changed["packet_digest"], response["packet_digest"])
        self.assertEqual(changed["response_digest"], response["version"])
        self.assertIn("Changed exact latest rejection", json.dumps(response))
        self.assertNotIn("Latest precise rejection", json.dumps(response))


class NativeWorkReaderTests(unittest.TestCase):
    def test_issued_rework_legacy_work_is_complete_and_never_changes_state_or_runs_checks(self):
        from pipeline_v2.tests.test_core import PipelineV2CoreTests
        fixture = PipelineV2CoreTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        fixture._reach_candidate()
        action = fixture.controller.status()["next_action"]
        fixture.controller.next(command_id=action["command_id"], expected_generation=action["expected_generation"])
        finding = {"id": "F-WORK", "severity": "high", "kind": "acceptance", "text": "Exact independent rejection",
                   "conditions": [{"id": "C1", "text": "First exact required condition"},
                                  {"id": "C2", "text": "Second exact required condition"}]}
        fixture._complete("REVIEW-WORK", {"outcome": "fail", "findings": [finding], "finding_resolutions": []})
        action = fixture.controller.status()["next_action"]
        fixture.controller.next(command_id=action["command_id"], expected_generation=action["expected_generation"])
        view = fixture.controller.status()
        exported = export_assignment(fixture.root, view)
        before = fixture.store.path.read_bytes()
        directory = fixture.root / fixture.workflow_path / "Delivery"
        files = {path.name: path.read_bytes() for path in directory.iterdir()}
        with mock.patch("pipeline_v2.runner.run_process_tree", side_effect=AssertionError("reader must not execute checks")) as process:
            response = run(parser().parse_args(exported["dispatch"]["reader"]["work_argv"][2:]))
            self.assertEqual("work", response["view"])
            self.assertEqual(2, response["required_condition_count"])
            self.assertEqual(["C1", "C2"], [row["condition_id"] for row in response["value"]["findings"][0]["conditions"]])
            for row in response["value"]["findings"][0]["conditions"]:
                self.assertEqual("Exact independent rejection", row["latest_independent_result"]["evidence"])
            self.assertEqual(view["active_assignment"]["id"], response["value"]["assignment"]["id"])
            self.assertTrue(response["work_complete"])
            self.assertFalse(response["delivery_complete"])
            process.assert_not_called()
        self.assertEqual(before, fixture.store.path.read_bytes())
        self.assertEqual(files, {path.name: path.read_bytes() for path in directory.iterdir()})


if __name__ == "__main__":
    unittest.main()
