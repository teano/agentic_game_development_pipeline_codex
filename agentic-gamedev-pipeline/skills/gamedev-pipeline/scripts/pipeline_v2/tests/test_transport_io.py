"""Exact JSON assembly and public I/O; no runtime pin, engine or candidate tests."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import io
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline_v2.cli import _check_delivery, parser, run
from pipeline_v2.delivery import (_semantic_page, assemble_delivery_pages,
                                  public_action_invocation, read_delivery_unit)
from pipeline_v2.model import PipelineError
from pipeline_v2.tests import test_delivery_work


class ExactAssemblyTests(unittest.TestCase):
    def pages(self, value, limit=47):
        metadata = {"format": "pipeline-delivery-page-v1", "version": "a" * 64,
                    "packet_digest": "a" * 64, "pointer": "/assignment/context/exact", "view": "section"}
        pages, token = [], None
        while True:
            page = _semantic_page(value, metadata, token, limit)
            pages.append(page)
            token = page["continuation"]
            if token is None:
                return pages

    def assemble(self, pages):
        remaining = iter(pages)
        return assemble_delivery_pages(lambda token: next(remaining))

    def test_exact_whitespace_unicode_and_crlf_shell_envelope_survive(self):
        value = {"text": '  Важные пробелы 🌍\r\n\n quote " slash \\ tail \t\r\n  ' * 20,
                 "empty": "", "lines": ["\n", "\r\n", "   "]}
        pages = self.pages(value)
        # A Windows text stream translates framing newlines. JSON escaping keeps
        # content CR/LF inside the text field separate from that framing.
        transported = []
        for page in pages:
            buffer = io.BytesIO()
            stream = io.TextIOWrapper(buffer, encoding="utf-8", newline="\r\n")
            print(json.dumps(page, ensure_ascii=False), file=stream)
            stream.flush()
            transported.append(json.loads(buffer.getvalue().decode("utf-8")))
        result = self.assemble(transported)
        self.assertEqual(value, result["value"])
        self.assertEqual(len(pages), result["assembled_pages"])
        self.assertEqual(pages[0]["content_digest"], result["content_digest"])
        self.assertFalse(result["delivery_complete"])
        self.assertTrue(result["selection_complete"])

    def test_rejects_clipped_reordered_missing_and_rebound_fragments(self):
        pages = self.pages({"text": "preserve meaning " * 80})
        variants = [pages[1:], pages[:-1], [pages[1], pages[0], *pages[2:]], [pages[0], *pages[2:]]]
        for key, value in (("packet_digest", "b" * 64), ("pointer", "/elsewhere"),
                           ("content_digest", "c" * 64), ("text", "clipped"),
                           ("page_digest", "d" * 64), ("complete", True),
                           ("continuation", pages[0]["continuation"]), ("next_offset", -1)):
            damaged = deepcopy(pages)
            damaged[1][key] = value
            variants.append(damaged)
        for damaged in variants:
            with self.subTest(change=damaged[0].get("offset")), self.assertRaises(PipelineError):
                self.assemble(damaged)
        final = deepcopy(pages)
        final[-1]["content_digest"] = "f" * 64
        with self.assertRaises(PipelineError):
            self.assemble(final)

    def test_content_digest_catches_consistently_rehashed_wrong_fragments(self):
        pages = self.pages({"text": "original" * 100})
        pages[1]["text"] = pages[1]["text"].replace("original", "tampered", 1)
        pages[1]["page_digest"] = hashlib.sha256(pages[1]["text"].encode()).hexdigest()
        with self.assertRaisesRegex(PipelineError, "content digest"):
            self.assemble(pages)


class ReadOnlyCLIAssemblyTests(unittest.TestCase):
    def setUp(self):
        self.h = test_delivery_work.DeliveryWorkTests("runTest")
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.value = '  exact 🌍\r\n \n tabs\t"\\ trailing   ' * 80
        self.h.view["active_assignment"]["context"]["exact"] = self.value
        self.version = self.h.export()["packet_digest"]
        self.prefix = [sys.executable, str(Path(__file__).resolve().parents[2] / "pipeline_state.py"),
                       "--root", str(self.h.root), "--feature", "test", "assignment-read",
                       "--digest", self.version, "--view", "section", "--pointer", "/assignment/context/exact",
                       "--format", "json", "--limit", "73"]

    def test_real_cli_decodes_exact_selection_and_readonly_pages(self):
        before = {p.name: p.read_bytes() for p in (self.h.root / self.h.workflow / "Delivery").glob("*.json")}
        result = subprocess.run([*self.prefix, "--assemble"], capture_output=True, check=True,
                                env={**os.environ, "PYTHONIOENCODING": "cp1252"})
        decoded = json.loads(result.stdout)
        self.assertEqual(self.value, decoded["value"])
        self.assertGreater(decoded["assembled_pages"], 1)
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.h.root / self.h.workflow / "Delivery").glob("*.json")})
        first = subprocess.run(self.prefix, capture_output=True, check=True)
        page = json.loads(first.stdout)
        self.assertFalse(page["complete"])
        self.assertEqual(73, len(page["text"]))

    def test_saved_assembly_returns_only_metadata_and_preserves_every_byte(self):
        large = self.value * 40
        self.h.view["active_assignment"]["context"]["exact"] = large
        version = self.h.export()["packet_digest"]
        argv = [version if item == self.version else item for item in self.prefix]
        output = self.h.root / self.h.workflow / "ReadOutputs" / "selected.json"
        completed = subprocess.run([*argv, "--limit", "8192", "--assemble", "--output", str(output)], capture_output=True, check=True)
        metadata = json.loads(completed.stdout)
        self.assertNotIn("value", metadata)
        self.assertFalse(metadata["content_included"])
        self.assertFalse(metadata["read_credit"])
        self.assertEqual(large, json.loads(output.read_text(encoding="utf-8"))["value"])
        self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), metadata["saved_output"]["sha256"])
        self.assertLess(len(completed.stdout), len(output.read_bytes()))
        self.assertLess(len(completed.stdout), 8192, "The large semantic body stays in the saved file, below one normal output page.")

    def test_real_powershell_json_pipe_preserves_content_and_compact_saved_result(self):
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if shell is None:
            self.skipTest("PowerShell not installed; direct subprocess and CRLF-envelope tests remain platform-independent")
        output = self.h.root / self.h.workflow / "ReadOutputs" / "shell.json"
        argv = [*self.prefix, "--assemble", "--output", str(output)]
        quoted = " ".join("'" + value.replace("'", "''") + "'" for value in argv)
        command = ("[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
                   "$transportResult = & " + quoted + "; "
                   "if($LASTEXITCODE -ne 0){throw 'Native reader failed'}; "
                   "$transportResult | ConvertFrom-Json | ConvertTo-Json -Compress -Depth 64")
        completed = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command", command],
                                   capture_output=True, check=True)
        metadata = json.loads(completed.stdout.decode("utf-8-sig"))
        self.assertFalse(metadata["content_included"])
        self.assertEqual(self.value, json.loads(output.read_text(encoding="utf-8"))["value"])

    def test_assembly_rejects_partial_start_and_nonpaged_views(self):
        with self.assertRaisesRegex(PipelineError, "starts the exact selection"):
            run(parser().parse_args(self.prefix[2:] + ["--assemble", "--continuation", "arbitrary"]))
        with self.assertRaisesRegex(PipelineError, "semantic JSON page"):
            run(parser().parse_args(self.prefix[2:] + ["--view", "value", "--limit", "8192", "--assemble"]))

    def test_check_context_does_not_retransmit_bootstrap_or_other_semantic_bodies(self):
        context = self.h.view["active_assignment"]["context"]
        context["diagnostic_checks"] = {"results": [{"check_id": "C1", "returncode": 7, "failure": "actual failure"}]}
        context["machine_checks"] = {"candidate_tree_oid": "a" * 40, "pending_check_ids": ["C2"]}
        version = self.h.export()["packet_digest"]
        result = assemble_delivery_pages(lambda token: read_delivery_unit(self.h.root, self.h.workflow, version,
                        view="check-context", continuation=token, limit=97))
        body = result["value"]
        self.assertEqual(context["diagnostic_checks"], body["check_context"]["diagnostic_checks"])
        self.assertEqual(context["machine_checks"], body["check_context"]["machine_checks"])
        self.assertEqual(4, body["generation"])
        self.assertNotIn("UNRELATED", json.dumps(body))
        self.assertNotIn("access", body["assignment"])


class PublicIOTests(unittest.TestCase):
    def test_init_request_preserves_fields_and_cannot_override_root_or_mix_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "init.json"
            request = {"id": "native-id", "run_id": "run", "expected_generation": 7,
                "authority_paths": {"requirements": "approved/r.md", "specification": "approved/s.md", "plan": "approved/p.md"},
                "slices": [{"id": "S1", "allowed_paths": ["source.txt"], "planned_commands": [["python", "verify.py"]]}],
                "verification": {"version": 1}}
            source.write_text(json.dumps(request), encoding="utf-8")
            argv = ["--root", str(root), "--feature", "test", "init", "--request", str(source)]
            with mock.patch("pipeline_v2.cli.Controller") as controller, \
                 mock.patch("pipeline_v2.cli.status_view", return_value={"observed": True}):
                self.assertEqual({"observed": True}, run(parser().parse_args(argv)))
                actual = controller.return_value.reconfigure.call_args.args[0]
                self.assertEqual(request, {key: actual[key] for key in request})
                self.assertEqual(str(root), actual["project_root"])
                self.assertEqual("test", actual["feature"])
                controller.reset_mock()
                for extra in (["--id", "different"], ["--authority", "plan=wrong.md"], ["--expected-generation", "8"]):
                    with self.assertRaisesRegex(PipelineError, "cannot be combined"):
                        run(parser().parse_args(argv + extra))
                    controller.return_value.reconfigure.assert_not_called()
                source.write_text(json.dumps({**request, "project_root": "elsewhere"}), encoding="utf-8")
                with self.assertRaisesRegex(PipelineError, "unknown fields"):
                    run(parser().parse_args(argv))
                controller.return_value.reconfigure.assert_not_called()

    def test_current_action_has_exact_bound_argv_and_recovery_missing_fields(self):
        view = {"project_root": str(Path.cwd()), "feature": "test", "next_action": {
            "command": "complete", "command_id": "native-current", "expected_generation": 19}}
        route = public_action_invocation(view)
        parsed = parser().parse_args(route["argv"][2:])
        self.assertEqual("step", parsed.command)
        self.assertEqual("native-current", parsed.action_id)
        self.assertEqual(19, parsed.expected_generation)
        view["next_action"] = {"command": "recover-capability", "command_id": "recover-19",
            "expected_generation": 19, "capability_binding": {"candidate_tree_oid": "a" * 40}}
        route = public_action_invocation(view)
        source = route["input"]["field_sources"]["binding"]
        self.assertEqual("/capability_binding", source)
        self.assertEqual({"candidate_tree_oid": "a" * 40}, view["next_action"][source[1:]])
        self.assertEqual({"prerequisite", "resolution", "evidence", "unchanged_dependencies"}, set(route["input"]["required_fields"]))
        self.assertEqual("--evidence", route["argv_prefix"][-1])

    def test_check_summary_survives_export_failure_without_inline_body(self):
        args = parser().parse_args(["--root", str(Path.cwd()), "--feature", "test", "check", "--id", "CHECK",
            "--expected-generation", "8", "--assignment-id", "A", "--quiescence", "stopped", "--with-delivery"])
        state = {"generation": 9, "history": [{"id": "CHECK", "generation": 9}]}
        view = {"generation": 9, "run_id": "run", "feature": "test", "workflow_path": "workflow",
            "next_action": {"command": "complete", "expected_generation": 9, "command_id": "complete-9"},
            "active_assignment": {"id": "A", "worker_id": "W", "context": {
                "diagnostic_checks": {"results": [{"check_id": "C1", "returncode": 7, "stderr": "large" * 10000,
                    "execution_evidence": "execution-evidence:failed-check", "execution_record_digest": "b" * 64}]},
                "machine_checks": {"candidate_tree_oid": "a" * 40, "checks": [], "pending_check_ids": ["C2"]}}}}
        with mock.patch("pipeline_v2.cli.status_view", return_value=view), \
             mock.patch("pipeline_v2.cli.export_assignment", side_effect=OSError("export lost")):
            result = _check_delivery(Path.cwd(), state, args)
        self.assertTrue(result["committed"])
        self.assertEqual("failed", result["transport"]["status"])
        self.assertEqual(7, result["result"]["checks"][0]["returncode"])
        self.assertEqual(["C2"], result["result"]["pending_check_ids"])
        self.assertEqual("a" * 40, result["binding"]["candidate_tree_oid"])
        self.assertNotIn("large", json.dumps(result))
        self.assertNotIn("check_result", result)
        origin = result["result"]["checks"][0]
        self.assertEqual("execution-evidence:failed-check", origin["execution_evidence"])
        parsed = parser().parse_args(origin["read_argv"][2:])
        self.assertEqual("failed-check", parsed.record_id)
        self.assertTrue(parsed.assemble)


if __name__ == "__main__":
    unittest.main()
