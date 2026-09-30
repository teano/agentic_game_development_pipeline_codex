"""Pure public QA/source transport regressions; no native runtime-state grants."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline_v2.cli import _init_request, main, parser, run
from pipeline_v2.delivery import assemble_delivery_pages, read_delivery_unit, read_file, _instruction_path
from pipeline_v2.model import PipelineError
from pipeline_v2.tests import test_delivery_work


class QASelectionTests(unittest.TestCase):
    def setUp(self):
        self.h = test_delivery_work.DeliveryWorkTests("runTest")
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.method = {"id": "actual-semantic-method", "source": "approved/plan.md#methods",
            "description": "Read exact provided executable/tool locator; preserve actual result. 🌍\r\n" * 500,
            "capabilities": ["source-provided-channel"], "evidence_types": ["observed-case"],
            "producer": {"kind": "tool", "channel": "provided-tool-locator", "probe_ref": "execution-evidence:probe"}}
        self.definition = {"method_definitions": {"METHOD-c1c664f57341a565": self.method}, "identities": [
            {"id": "GROUP", "source": "approved/plan.md#group", "assertions": [
                {"id": name, "expected": expected, "methods": [{"ref": "METHOD-c1c664f57341a565"}],
                 "applicability": {"kind": "always", "condition": "always", "evidence_types": []}, "depends_on": []}
                for name, expected in [("A1", "Exact observation 1"), ("A2", "Exact observation 2")]]}]}
        self.h.view["active_assignment"]["context"]["qa_contract"]["definition"] = self.definition
        self.version = self.h.export()["packet_digest"]
        self.argv = [sys.executable, str(Path(__file__).resolve().parents[2] / "pipeline_state.py"),
            "--root", str(self.h.root), "--feature", "test", "assignment-read", "--digest", self.version]

    def read(self, view, ids=None, limit=8192):
        return assemble_delivery_pages(lambda token: read_delivery_unit(self.h.root, self.h.workflow, self.version,
            view=view, assertion_ids=ids, continuation=token, limit=limit))["value"]

    def test_index_keeps_complete_inventory_without_preloading_methods(self):
        index = self.read("qa-index")
        self.assertEqual(["A1", "A2"], index["identities"][0]["assertion_ids"])
        self.assertEqual(2, index["assertion_count"])
        self.assertNotIn("description", json.dumps(index))
        self.assertNotIn("METHOD-", json.dumps(index))

    def test_actual_group_resolves_semantic_ids_and_all_source_producer_fields(self):
        group = self.read("qa-assertion", ["A2"], limit=503)
        identity = group["identities"][0]
        self.assertEqual(["A2"], [item["id"] for item in identity["assertions"]])
        reference = identity["assertions"][0]["methods"][0]["ref"]
        self.assertEqual(self.method, group["method_definitions"][reference])
        self.assertEqual("approved/plan.md#group", identity["source"])
        self.assertEqual("Exact observation 2", identity["assertions"][0]["expected"])
        pair = self.read("qa-assertion", ["A1", "A2"])
        self.assertEqual(1, len(pair["method_definitions"]))
        self.assertEqual(2, len(pair["identities"][0]["assertions"]))
        self.assertEqual([{"ref": "METHOD-c1c664f57341a565"}], self.definition["identities"][0]["assertions"][0]["methods"])
        for ids in ([], ["missing"], ["A1", "A1"]):
            with self.assertRaisesRegex(PipelineError, "exact approved assertion"):
                self.read("qa-assertion", ids)

    def test_real_cli_plain_page_and_compact_saved_resolved_group(self):
        page = subprocess.run([*self.argv, "--view", "qa-assertion", "--assertion-id", "A1", "--format", "text", "--limit", "500"],
                              check=True, capture_output=True)
        header, body = page.stdout.decode("utf-8").split("\n", 1)
        self.assertFalse(json.loads(header)["complete"])
        self.assertIn('"identities"', body)
        self.assertNotIn('\\"identities\\"', body)
        output = self.h.root / self.h.workflow / "ReadOutputs" / "case.json"
        completed = subprocess.run([*self.argv, "--view", "qa-assertion", "--assertion-id", "A1", "--format", "json",
                                    "--assemble", "--output", str(output)], check=True, capture_output=True)
        receipt = json.loads(completed.stdout)
        self.assertNotIn("value", receipt)
        self.assertFalse(receipt["read_credit"])
        self.assertLess(len(completed.stdout), 8192)
        saved = json.loads(output.read_text(encoding="utf-8"))["value"]
        self.assertEqual([self.method], list(saved["method_definitions"].values()))


class SourceSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.text = "# Title\r\nintro 🌍  \r\n## Chosen\r\nExecutable: C:/Provided/tool.exe\r\n  exact whitespace  \r\n### Child\r\n```text\r\n## Fake\r\n```\r\nvalue\r\n## End\r\ntail\r\n"
        (self.root / "source.md").write_bytes(self.text.encode("utf-8"))
        self.view = {"active_assignment": {"id": "A", "access": {"read": ["source.md"], "write": []}},
                     "next_action": {"command": "complete"}}

    def test_selected_section_is_exact_nested_text_with_fullsource_binding(self):
        result = assemble_delivery_pages(lambda token: read_file(self.root, self.view, "source.md",
            section="## Chosen", continuation=token, limit=13))
        expected = self.text[self.text.index("## Chosen"):self.text.index("## End")]
        self.assertEqual(expected, result["value"])
        self.assertEqual({"path": "source.md", "sha256": hashlib.sha256(self.text.encode()).hexdigest(),
                          "start_line": 3, "end_line": 10}, result["source"])
        self.assertFalse(result["delivery_complete"])
        self.assertIn("C:/Provided/tool.exe", result["value"])
        self.assertEqual(result["source"], result["evidence_origin"]["source"])
        self.assertTrue(result["evidence_origin"]["ref"].endswith("#L3-L10"))
        self.assertFalse(result["semantic_credit"])

    def test_lines_duplicates_bounds_and_changed_source_fail_closed(self):
        result = read_file(self.root, self.view, "source.md", lines=(2, 2))
        self.assertEqual("intro 🌍  \r\n", result["text"])
        for span in ((0, 1), (2, 1), (1, 100)):
            with self.assertRaisesRegex(PipelineError, "inclusive range"):
                read_file(self.root, self.view, "source.md", lines=span)
        (self.root / "source.md").write_bytes((self.text + "## Chosen\r\nsecond").encode())
        with self.assertRaisesRegex(PipelineError, "exactly once"):
            read_file(self.root, self.view, "source.md", section="Chosen")
        with self.assertRaisesRegex(PipelineError, "changed"):
            read_file(self.root, self.view, "source.md", version=result["version"])
        with self.assertRaisesRegex(PipelineError, "outside.*read access"):
            read_file(self.root, self.view, "secret.md")

    def test_real_cli_preinit_role_and_linked_instruction_without_product_access(self):
        launcher = Path(__file__).resolve().parents[2] / "pipeline_state.py"
        base = [sys.executable, str(launcher), "--root", str(self.root), "--feature", "test", "file-read"]
        for role in ("director", "qa", "gamedev-development-plan"):
            result = subprocess.run([*base, "--instruction", role, "--lines", "1:3", "--format", "json", "--assemble"],
                                    capture_output=True, check=True)
            decoded = json.loads(result.stdout)
            target = _instruction_path(role, None)
            expected = "".join(target.read_bytes().decode("utf-8").splitlines(keepends=True)[:3])
            self.assertEqual(expected, decoded["value"])
            self.assertNotIn("evidence_origin", decoded)
        linked = _instruction_path("qa", "references/qa-output-contract.md")
        page = read_file(self.root, None, str(linked), instruction="qa", lines=(1, 1))
        self.assertEqual(str(linked), page["source"]["path"])
        with self.assertRaises(PipelineError):
            read_file(self.root, None, str(self.root / "source.md"), instruction="qa")
        with self.assertRaisesRegex(PipelineError, "Markdown"):
            read_file(self.root, None, str(launcher), instruction="director")
        self.assertFalse((self.root / ".agentic-pipeline/Workflows/test/pipeline-state.json").exists())


class InitAndDraftCLITests(unittest.TestCase):
    def test_init_paths_are_explicit_scoped_and_not_guessed_from_inline_strings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = ".agentic-pipeline/Workflows/test"
            folder = root / workflow
            folder.mkdir(parents=True)
            (folder / "qa.json").write_text('{"schema":1}', encoding="utf-8")
            source = root / "request.json"  # Existing project-contained requests remain compatible.
            initial = {"id": "I", "run_id": "run", "authority_paths": {}, "slices": [],
                       "qa_contract_path": workflow + "/qa.json", "verification": {"version": 1}}
            source.write_text(json.dumps(initial), encoding="utf-8")
            decoded = _init_request(root, workflow, source)
            self.assertEqual({"schema": 1}, decoded["qa_contract"])
            self.assertNotIn("qa_contract_path", decoded)
            for update, pattern in (({"qa_contract": "qa.json"}, "mutually exclusive"),
                ({"verification": "verification.json"}, "use verification_path"),
                ({"qa_contract_path": "request.json"}, "selected workflow"),
                ({"qa_contract_path": {}}, "path string"), ({"slices": "[]"}, "array"),
                ({"expected_generation": True}, "integer")):
                source.write_text(json.dumps({**initial, **update}), encoding="utf-8")
                with self.assertRaisesRegex(PipelineError, pattern):
                    _init_request(root, workflow, source)
            with tempfile.TemporaryDirectory() as outside:
                path = Path(outside) / "request.json"
                path.write_text(json.dumps(initial), encoding="utf-8")
                with self.assertRaises(PipelineError):
                    _init_request(root, workflow, path)

    def test_draft_selected_assessments_page_and_save_without_mass_stdout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prefix = ["--root", str(root), "--feature", "test"]
            compact = {"revision": 2, "total": 287, "assessed": 1, "pending": 286}
            selected = {**compact, "assessments": [{"id": "A1", "observed": "exact 🌍\r\n" * 5000}], "pending_ids": []}
            with mock.patch("pipeline_v2.cli.Controller") as controller:
                controller.return_value.qa_read.return_value = compact
                self.assertEqual(compact, run(parser().parse_args(prefix + ["qa-read", "--assignment-id", "QA"])))
                controller.return_value.qa_read.return_value = selected
                output = root / ".agentic-pipeline/Workflows/test/ReadOutputs/draft.json"
                result = run(parser().parse_args(prefix + ["qa-read", "--assignment-id", "QA", "--assertion-id", "A1",
                    "--assemble", "--output", str(output)]))
                self.assertNotIn("value", result)
                self.assertEqual(selected, json.loads(output.read_text(encoding="utf-8"))["value"])
                controller.return_value.qa_read.assert_called_with("QA", identity_id=None, assertion_id="A1")
                controller.return_value.qa_finalize.return_value = {"valid": False, "pending_count": 286}
                captured = io.StringIO()
                with redirect_stdout(captured):
                    self.assertEqual(2, main(prefix + ["qa-finalize", "--assignment-id", "QA", "--expected-revision", "2"]))
                self.assertEqual(286, json.loads(captured.getvalue())["pending_count"])


if __name__ == "__main__":
    unittest.main()
