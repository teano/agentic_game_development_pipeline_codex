"""Pure reader/host presentation and authoring fixtures; no native state run."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from pipeline_v2.cli import main, _render_assignment_unit
from pipeline_v2.delivery import (host_read_command, read_file, assemble_delivery_pages,
                                  _instruction_path, _instruction_link_reads, export_assignment, read_delivery_unit)
from pipeline_v2.tests import test_qa_working_draft as draft_fixtures
from pipeline_v2.tests import test_qa_public_io as selection_fixtures
from pipeline_v2.tests import test_delivery_tools as delivery_fixtures


def execute_handle(handle, *, cwd, binary=False):
    request = handle["exec_command"] if "exec_command" in handle else handle
    if request["shell"] == "powershell":
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if shell is None:
            raise unittest.SkipTest("PowerShell unavailable for actual host quoting test")
        argv = [shell, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", request["cmd"]]
    else:
        argv = [request["shell"], "-c", request["cmd"]]
    return subprocess.run(argv, cwd=cwd, capture_output=True, encoding=None if binary else "utf-8", check=True,
                          env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"})


class PresentationNavigationTests(unittest.TestCase):
    def test_ready_host_command_preserves_literal_special_arguments_from_foreign_cwd(self):
        with tempfile.TemporaryDirectory(prefix="reader Ω ' $() ` ") as directory, tempfile.TemporaryDirectory() as foreign:
            root = Path(directory)
            script = root / "read Ω ' source.py"
            script.write_text("import json,sys; print(json.dumps(sys.argv[1:]))", encoding="utf-8")
            arguments = ["space Ω", "single ' double \"", "$(Write-Output injected)", "literal `n `t", "; exit 13", "trailing\\"]
            command = host_read_command([sys.executable, "-B", str(script), *arguments], root)
            result = execute_handle(command, cwd=foreign)
            self.assertEqual(arguments, json.loads(result.stdout))
            self.assertEqual(str(root), command["workdir"])
            self.assertEqual({"cmd", "shell", "workdir"}, set(command))
            import shlex
            posix = host_read_command(["python", *arguments], root, windows=False)
            self.assertEqual(["python", *arguments], shlex.split(posix["cmd"]))

    def test_generated_startup_handle_keeps_bound_source_and_saved_full_envelope(self):
        fixture = delivery_fixtures.DeliveryTests("runTest"); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        root = fixture.root / "project Ω ' $() `"
        root.mkdir()
        exported = export_assignment(root, fixture.view)
        handle = exported["dispatch"]["role_instructions"]
        with tempfile.TemporaryDirectory() as foreign:
            completed = execute_handle(handle, cwd=foreign, binary=True)
            header, body = completed.stdout.split(b"\n", 1)
            metadata = json.loads(header)
            output = root / fixture.workflow / "ReadOutputs" / "startup.json"
            saved = execute_handle(host_read_command([*handle["read_argv"], "--output", str(output)], root), cwd=foreign)
        receipt = json.loads(saved.stdout.split("\n", 1)[0])
        retained = json.loads(output.read_bytes())
        source_text = Path(handle["path"]).read_bytes().decode("utf-8")
        self.assertEqual(source_text.encode("utf-8"), body[:-1])
        self.assertEqual(source_text, retained["value"])
        self.assertEqual(handle["version"], metadata["version"])
        self.assertEqual(handle["version"], metadata["original_selection"]["source"]["sha256"])
        self.assertEqual(retained["source"], metadata["original_selection"]["source"])
        self.assertEqual(str(root), handle["exec_command"]["workdir"])
        self.assertFalse(receipt["read_credit"])
        self.assertTrue(receipt["snapshot_read"])
        self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), receipt["saved_output"]["sha256"])
        self.assertFalse(metadata["delivery_complete"])
        self.assertNotIn("evidence_origin", retained)

    def test_link_handle_reads_exact_selected_source_and_deduplicates_targets(self):
        with tempfile.TemporaryDirectory(prefix="instruction Ω ' $() ` ") as directory, tempfile.TemporaryDirectory() as foreign:
            root = Path(directory)
            entry = _instruction_path("qa", None)
            linked = _instruction_link_reads(root, "fixture", "qa", entry,
                "[route](../gamedev-pipeline/references/delivery-contract.md#worker-read-route)\n"
                "[same route](../gamedev-pipeline/references/delivery-contract.md#worker-read-route)\n")
            self.assertEqual(1, len(linked))
            handle = linked[0]
            self.assertEqual(2, len(handle["links"]))
            self.assertNotIn("read_argv", handle)
            completed = execute_handle(handle, cwd=foreign)
            header, body = completed.stdout.split("\n", 1)
            metadata = json.loads(header)
            source = handle["source"]
            expected = "".join(Path(source["path"]).read_bytes().decode("utf-8").splitlines(keepends=True)[source["start_line"] - 1:source["end_line"]])
            self.assertEqual(expected, body[:-1])  # print adds exactly one framing newline.
            self.assertEqual(source, metadata["original_selection"]["source"])
            self.assertFalse(metadata["delivery_complete"])
            self.assertTrue(metadata["selection_complete"])
            self.assertTrue(metadata["links"]["inventory"])
            self.assertNotIn("evidence_origin", metadata)

    def test_missing_ambiguous_and_unadmitted_links_never_select_whole_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = _instruction_path("qa", None)
            missing = _instruction_link_reads(root, "fixture", "qa", entry, "[missing](#not-a-real-heading)")
            self.assertIn("error", missing[0]); self.assertNotIn("exec_command", missing[0])
            outside = root / "private.md"; outside.write_text("# Private\n", encoding="utf-8")
            escaped = _instruction_link_reads(root, "fixture", "qa", entry, "[outside](" + outside.as_posix() + ")")
            self.assertFalse(any("exec_command" in item for item in escaped))
            target = root / "duplicate.md"; target.write_text("# Same\nfirst\n# Same\nsecond\n", encoding="utf-8")
            with mock.patch("pipeline_v2.delivery._instruction_path", return_value=target):
                duplicate = _instruction_link_reads(root, "fixture", "qa", target, "[duplicate](#same)")
            self.assertIn("exactly one", duplicate[0]["error"])
            self.assertNotIn("exec_command", duplicate[0])
            self.assertEqual([], _instruction_link_reads(root, "fixture", "qa", entry,
                "```text\n[example](#not-a-real-heading)\n```\n"))

    def test_link_version_rejects_changed_target_and_preserves_original_selected_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); target = root / "instruction.md"
            exact = "# Entry\r\n## Chosen\r\n  exact Ω  \r\n## Other\r\nnot selected\r\n"
            target.write_bytes(exact.encode("utf-8"))
            with mock.patch("pipeline_v2.delivery._instruction_path", return_value=target):
                handle = _instruction_link_reads(root, "fixture", "qa", target, "[chosen](#chosen)")[0]
                source = handle["source"]
                first = read_file(root, None, str(target), instruction="qa", feature="fixture", version=source["sha256"],
                    lines=(source["start_line"], source["end_line"]), limit=7)
                self.assertIsNotNone(first["continuation"])
                with self.assertRaisesRegex(ValueError, "continuation does not match"):
                    read_file(root, None, str(target), instruction="qa", feature="fixture", version=source["sha256"],
                        lines=(1, source["end_line"]), continuation=first["continuation"], limit=7)
                result = assemble_delivery_pages(lambda token: read_file(root, None, str(target), instruction="qa",
                    feature="fixture", version=source["sha256"], lines=(source["start_line"], source["end_line"]), continuation=token, limit=7))
                self.assertEqual("## Chosen\r\n  exact Ω  \r\n", result["value"])
                rendered = _render_assignment_unit(result)
                self.assertEqual(result["value"], rendered.split("\n", 1)[1])
                target.write_text("# Changed\n", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "changed"):
                    read_file(root, None, str(target), instruction="qa", version=source["sha256"])

    def test_actual_cli_text_renderer_preserves_original_crlf_bytes(self):
        root = Path(__file__).resolve().parents[5]
        source = _instruction_path("qa", "../gamedev-pipeline/references/interaction-evidence.md")
        expected = "".join(source.read_bytes().decode("utf-8").splitlines(keepends=True)[:3])
        script = Path(__file__).resolve().parents[2] / "pipeline_state.py"
        result = subprocess.run([sys.executable, "-B", str(script), "--root", str(root), "--feature", "readcheck",
            "file-read", "--instruction", "qa", "--path", str(source), "--lines", "1:3", "--format", "text", "--assemble"],
            capture_output=True, check=True)
        header, body = result.stdout.split(b"\n", 1)
        self.assertTrue(json.loads(header)["selection_complete"])
        self.assertEqual(expected.encode("utf-8") + b"\n", body)

    def test_inventory_returns_one_role_action_with_exact_identity_selector(self):
        fixture = selection_fixtures.QASelectionTests("runTest"); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        fixture.h.view["active_assignment"]["role"] = "qa"
        exported = fixture.h.export(); version = exported["packet_digest"]
        result = assemble_delivery_pages(lambda token: read_delivery_unit(fixture.h.root, fixture.h.workflow, version,
            view="qa-index", continuation=token))["value"]
        group = result["identities"][0]
        self.assertEqual({"id", "source", "assertion_ids", "prepare"}, set(group))
        self.assertEqual(["A1", "A2"], group["assertion_ids"])
        self.assertIn("qa-prepare", group["prepare"]["exec_command"]["cmd"])
        self.assertIn("--identity-id", group["prepare"]["exec_command"]["cmd"])
        self.assertNotIn("--assertion-id", group["prepare"]["exec_command"]["cmd"])
        self.assertNotIn("GROUP/A1", json.dumps(group))
        fixture.h.view["active_assignment"]["role"] = "engineer"
        version = fixture.h.export()["packet_digest"]
        inventory = assemble_delivery_pages(lambda token: read_delivery_unit(fixture.h.root, fixture.h.workflow, version,
            view="qa-index", continuation=token))["value"]
        group = inventory["identities"][0]
        self.assertEqual({"id", "source", "assertion_ids", "read"}, set(group))
        self.assertIn("--present", group["read"]["exec_command"]["cmd"])
        # This is a pure immutable packet fixture, without an issued controller.
        # Exercise its unchanged legacy transport; real current-owner generated
        # handles are exercised by SavedPresentationNativeTests.
        legacy = deepcopy(group["read"])
        legacy["exec_command"]["cmd"] = legacy["exec_command"]["cmd"].replace("--present", "--assemble")
        with tempfile.TemporaryDirectory() as foreign:
            complete = execute_handle(legacy, cwd=foreign)
        metadata, body = complete.stdout.split("\n", 1)
        self.assertTrue(json.loads(metadata)["selection_complete"])
        selected = json.loads(body)
        self.assertEqual(["A1", "A2"], [row["id"] for row in selected["identities"][0]["assertions"]])
        self.assertEqual([fixture.method], list(selected["method_definitions"].values()))


class PreparedDestinationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = draft_fixtures.QAWorkingDraftTests("runTest"); self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)

    def invoke(self, *extra):
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch("pipeline_v2.cli.Controller", return_value=self.fixture.controller), redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--root", str(self.fixture.root), "--feature", "feature", "qa-prepare",
                         "--assignment-id", "qa-current", "--assertion-id", "enter", *extra])
        self.assertEqual((0, ""), (code, stderr.getvalue()))
        return json.loads(stdout.getvalue())["value"]

    def test_default_destination_is_bound_and_unsaved_edits_are_preserved_on_retry(self):
        first = self.invoke()
        path = Path(first["saved_record_request"]["path"])
        self.assertTrue(path.is_relative_to(self.fixture.store.path.parent / "ReadOutputs"))
        original = path.read_bytes()
        self.assertNotIn("record_request", first)
        self.assertIn("obligations", first)
        repeated = self.invoke()
        self.assertEqual(first["saved_record_request"], repeated["saved_record_request"])
        self.assertEqual(original, path.read_bytes())
        request = json.loads(original)
        request["assessments"][0].update(self.fixture.row())
        request["assessments"][0]["assessment"]["observed"] = "Actual unsaved assertion-specific observation"
        edited = json.dumps(request, ensure_ascii=False, indent=2).encode("utf-8")
        path.write_bytes(edited)
        resumed = self.invoke()
        self.assertEqual("preserved_edited_request", resumed["request_status"])
        self.assertEqual(str(path), resumed["saved_record_request"]["path"])
        self.assertEqual(hashlib.sha256(edited).hexdigest(), resumed["saved_record_request"]["sha256"])
        self.assertEqual(edited, path.read_bytes())
        self.assertFalse(self.fixture.controller.qa_read("qa-current")["exists"])
        recorded = self.fixture.controller.qa_record("qa-current", request)
        self.assertTrue(recorded["valid"], recorded.get("errors"))
        later = self.invoke()
        self.assertNotEqual(str(path), later["saved_record_request"]["path"])
        self.assertEqual(edited, path.read_bytes())

    def test_incomplete_unsaved_json_is_not_overwritten_and_pointer_route_stays_readonly(self):
        first = self.invoke(); path = Path(first["saved_record_request"]["path"])
        partial = b'{"unfinished worker edit":'
        path.write_bytes(partial)
        restored = self.invoke()
        self.assertEqual("preserved_edited_request", restored["request_status"])
        self.assertEqual(partial, path.read_bytes())
        before = {file.name: file.read_bytes() for file in path.parent.iterdir()}
        inline = self.invoke("--pointer", "/record_request", "--assemble")
        self.assertEqual("enter", inline["assessments"][0]["id"])
        self.assertEqual(before, {file.name: file.read_bytes() for file in path.parent.iterdir()})


if __name__ == "__main__":
    unittest.main()
