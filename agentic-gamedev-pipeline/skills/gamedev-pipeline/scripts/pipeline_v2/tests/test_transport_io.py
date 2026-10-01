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
from pipeline_v2.cli import _check_delivery, _render_assignment_unit, parser, run
from pipeline_v2.delivery import (_semantic_page, assemble_delivery_pages,
                                  public_action_invocation, read_delivery_unit)
from pipeline_v2.model import PipelineError
from pipeline_v2.tests import test_delivery_work


class SavedPresentationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="saved Ω ' $() ` ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prefix = ["--root", str(self.root), "--feature", "presentation"]

    def source(self, path="../gamedev-pipeline/references/delivery-contract.md", section="Worker read route", limit=8192):
        args = self.prefix + ["file-read", "--instruction", "qa", "--path", path, "--format", "json", "--limit", str(limit)]
        if section:
            args += ["--section", section]
        return args

    def saved(self, page, *, pointer="/value", continuation=None, root=None, feature="presentation", limit=8192):
        args = ["--root", str(root or self.root), "--feature", feature, "delivery-read", "--saved-output", page["saved_output"]["path"],
                "--digest", page["saved_output"]["sha256"], "--pointer", pointer, "--format", "json", "--limit", str(limit)]
        if continuation:
            args += ["--continuation", continuation]
        return run(parser().parse_args(args))

    def test_full_envelope_is_preserved_and_progressive_body_equals_legacy_rendering(self):
        for path, section in (("../gamedev-pipeline/references/delivery-contract.md", "Worker read route"),
                              ("../gamedev-pipeline/references/qa-acceptance-contract.md", "Incremental assessment"),
                              ("../gamedev-pipeline/references/director-runtime.md", None)):
            with self.subTest(path=path):
                args = self.source(path, section, limit=8192)
                legacy = run(parser().parse_args(args + ["--assemble"]))
                first = run(parser().parse_args(args + ["--present"]))
                snapshot = json.loads(Path(first["saved_output"]["path"]).read_bytes())
                self.assertEqual(legacy, {key: value for key, value in snapshot.items() if key != "presentation_origin"})
                expected = _render_assignment_unit(legacy).split("\n", 1)[1]
                restored = assemble_delivery_pages(lambda token: self.saved(first, continuation=token))
                self.assertEqual(expected, restored["value"])
                self.assertFalse(first["read_credit"])
                self.assertFalse(first["semantic_credit"])
                self.assertFalse(first["delivery_complete"])
                self.assertEqual(legacy["source"], first["original_selection"]["source"])
                self.assertNotIn("evidence_origin", first["original_selection"])
                self.assertNotIn("linked_reads", first)
                self.assertEqual(len(legacy["linked_reads"]), len(first["links"]["inventory"]))
                self.assertLess(len(_render_assignment_unit(first).split("\n", 1)[0]),
                                len(_render_assignment_unit(legacy).split("\n", 1)[0]))

    def test_current_replays_same_page_and_wrong_pointer_snapshot_or_raw_bytes_fail(self):
        first = run(parser().parse_args(self.source(limit=73) + ["--present"]))
        second = self.saved(first, continuation=first["continuation"], limit=73)
        from pipeline_v2.tests.test_presentation_navigation import execute_handle
        with tempfile.TemporaryDirectory() as foreign:
            replay = execute_handle(second["reread_current"], cwd=foreign, binary=True)
        header, body = replay.stdout.split(b"\n", 1)
        self.assertEqual(second["offset"], json.loads(header)["offset"])
        self.assertEqual(second["text"].encode("utf-8") + b"\n", body)
        with self.assertRaisesRegex(PipelineError, "continuation does not match"):
            self.saved(first, pointer="/source", continuation=first["continuation"], limit=73)
        other = run(parser().parse_args(self.source(section="Host command presentation", limit=73) + ["--present"]))
        with self.assertRaisesRegex(PipelineError, "continuation does not match"):
            self.saved(other, continuation=first["continuation"], limit=73)
        target = Path(first["saved_output"]["path"])
        target.write_bytes(target.read_bytes() + b" ")
        with self.assertRaisesRegex(PipelineError, "changed"):
            self.saved(first)

    def test_forged_body_origin_or_feature_cannot_become_a_native_snapshot(self):
        from pipeline_v2.artifact_io import write_read_output
        first = run(parser().parse_args(self.source() + ["--present"]))
        original = json.loads(Path(first["saved_output"]["path"]).read_bytes())
        for change in ("body", "origin", "feature"):
            snapshot = deepcopy(original)
            if change == "body":
                snapshot["value"] = "Forged source body"
                snapshot["content_digest"] = hashlib.sha256(snapshot["value"].encode()).hexdigest()
            elif change == "origin":
                snapshot["source"]["path"] = str(self.root / "outside.md")
            else:
                snapshot["presentation_origin"]["feature"] = "foreign"
            saved = write_read_output(self.root, self.root / ".agentic-pipeline/Workflows/presentation", None, snapshot)
            with self.subTest(change=change), self.assertRaises(PipelineError):
                self.saved({"saved_output": saved})
        outside = self.root / "outside.json"; outside.write_bytes(Path(first["saved_output"]["path"]).read_bytes())
        with self.assertRaisesRegex(PipelineError, "within"):
            self.saved({"saved_output": {**first["saved_output"], "path": str(outside)}})
        with self.assertRaises(PipelineError):
            self.saved(first, feature="foreign")

    def test_known_link_cardinalities_keep_complete_lazy_rows_and_subprocess_boundaries(self):
        import pipeline_v2.delivery as delivery
        import pipeline_v2.cli as cli
        from pipeline_v2.tests.test_presentation_navigation import execute_handle
        source_bundle = Path(delivery.__file__).resolve().parents[4]
        bundle = self.root / "fixture bundle"
        shutil.copytree(source_bundle, bundle, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        scripts = bundle / "skills/gamedev-pipeline/scripts/pipeline_v2"
        entry = bundle / "skills/gamedev-pipeline/SKILL.md"
        references = entry.parent / "references"
        for count in (9, 13, 29):
            entry.write_text("# Entry\n" + "".join(f"[part {index}](references/present-part-{index}.md)\n" for index in range(count)), encoding="utf-8")
            for index in range(count):
                (references / f"present-part-{index}.md").write_bytes(f"# Part {index}\r\n  exact Ω ' {index}  \r\n".encode("utf-8"))
            with mock.patch.object(delivery, "__file__", str(scripts / "delivery.py")), mock.patch.object(cli, "__file__", str(scripts / "cli.py")):
                args = self.prefix + ["file-read", "--instruction", "director", "--format", "json"]
                legacy = run(parser().parse_args(args + ["--assemble"]))
                first = run(parser().parse_args(args + ["--present"]))
                self.assertEqual(count, len(first["links"]["inventory"]))
                self.assertEqual(legacy["value"], first["text"])
                for index, row in enumerate(legacy["linked_reads"]):
                    selected = assemble_delivery_pages(lambda token: self.saved(first, pointer=f"/linked_reads/{index}", continuation=token))
                    self.assertEqual(row, selected["value"])
                with tempfile.TemporaryDirectory() as foreign:
                    replay = execute_handle(first["reread_current"], cwd=foreign, binary=True)
                    row = self.saved(first, pointer=f"/linked_reads/{count - 1}")
                    selected = json.loads(row["text"])
                    linked = execute_handle(selected, cwd=foreign, binary=True)
                header, body = replay.stdout.split(b"\n", 1)
                self.assertEqual(first["text"].encode("utf-8") + b"\n", body)
                self.assertLess(len(json.dumps(json.loads(header), ensure_ascii=False)),
                                len(_render_assignment_unit(legacy).split("\n", 1)[0]))
                self.assertEqual((references / f"present-part-{count - 1}.md").read_bytes() + b"\n", linked.stdout.split(b"\n", 1)[1])
                # Rewrapping expands text independently of native assembly;
                # full linked commands remain saved rather than retransmitted.
                self.assertLess(len(json.dumps(replay.stdout.decode("utf-8"))),
                                len(json.dumps(_render_assignment_unit(legacy))))
                (references / f"present-part-{count - 1}.md").write_text("# Changed linked source\n", encoding="utf-8")
                with self.assertRaisesRegex(PipelineError, "no longer current"):
                    self.saved(first)


class SavedPresentationNativeTests(unittest.TestCase):
    def setUp(self):
        from pipeline_v2.tests.test_core import PipelineV2CoreTests, _CanonicalTestController

        class ReceiptFixture(PipelineV2CoreTests):
            @staticmethod
            def _fixture_qa_contract(slices):
                contract = PipelineV2CoreTests._fixture_qa_contract(slices)
                for definition in contract["slices"].values():
                    method = definition["identities"][0]["assertions"][0]["methods"][0]
                    method["producer"] = {"kind": "controller_check", "check_ids": ["command-1"]}
                    method["evidence_types"] = ["bound-machine-receipt"]
                return contract

            def _initialize(self):
                self.controller = _CanonicalTestController(self.store, timeout=10)
                self.controller.reconfigure({"name": "init", "id": "CMD-INIT", "run_id": "RUN-TEST", "feature": self.feature,
                    "workflow_path": self.workflow_path, "project_root": str(self.root),
                    "authority_paths": {"requirements": "requirements.md", "specification": "specification.md", "plan": "plan.md"},
                    "slices": self.slices, "verification": {"version": 1, "pure_documentation_paths": [], "confirm_approved_plan": True, "slices": {"SLICE-1": [{"id": "command-1", "argv": self.command,
                        "kind": "deterministic", "timeout_seconds": 10, "independent": False, "input_paths": ["game.txt"]}]}}})

        self.h = ReceiptFixture("runTest"); self.h.setUp(); self.addCleanup(self.h.tearDown)
        if self.h.store.load()["phase"] == "plan":
            self.h._reach_engineering()
        self.h._engineer("saved-engineer", "candidate-1\n")
        self.h._accept("saved-engineering")
        self.h._review_pass("saved-review")
        action = self.h.controller.status()["next_action"]
        self.h.controller.next(command_id=action["command_id"], expected_generation=action["expected_generation"])
        self.prefix = ["--root", str(self.h.root), "--feature", self.h.feature]

    def invoke(self, *args):
        return run(parser().parse_args([*self.prefix, *args]))

    def read_saved(self, page, pointer="/value", continuation=None):
        args = ["delivery-read", "--saved-output", page["saved_output"]["path"], "--digest", page["saved_output"]["sha256"], "--pointer", pointer]
        if continuation:
            args += ["--continuation", continuation]
        return self.invoke(*args)

    def test_generated_current_bootstrap_index_group_and_source_handles_preserve_admission(self):
        from pipeline_v2.delivery import export_assignment
        from pipeline_v2.tests.test_presentation_navigation import execute_handle
        exported = export_assignment(self.h.root, self.h.controller.status())
        dispatch = exported["dispatch"]
        with tempfile.TemporaryDirectory() as foreign:
            result = execute_handle(dispatch["reader"]["bootstrap"], cwd=foreign, binary=True)
            header, body = result.stdout.split(b"\n", 1)
            startup = json.loads(body)
            self.assertEqual(exported["assignment_id"], startup["assignment"]["id"])
            self.assertFalse(json.loads(header)["read_credit"])
            result = execute_handle(dispatch["reader"]["qa_index"], cwd=foreign, binary=True)
            index = json.loads(result.stdout.split(b"\n", 1)[1])
            group = index["identities"][0]
            result = execute_handle(group["prepare"], cwd=foreign, binary=True)
            prepared = json.loads(result.stdout.split(b"\n", 1)[1])
            self.assertEqual(group["id"], prepared["obligations"]["identities"][0]["id"])
        source = self.invoke("file-read", "--path", "game.txt", "--present")
        origin = source["original_selection"]
        self.assertEqual(origin["source"], origin["evidence_origin"]["source"])
        self.assertEqual((self.h.root / "game.txt").read_bytes().decode("utf-8"), source["text"])
        private = self.h.root / "private.txt"; private.write_text("private\n", encoding="utf-8")
        with self.assertRaises(PipelineError):
            self.invoke("file-read", "--path", "private.txt", "--present")
        private.unlink()
        (self.h.root / "game.txt").write_text("changed candidate\n", encoding="utf-8")
        with self.assertRaises(PipelineError):
            self.read_saved(source)

    def test_incomplete_native_attempt_is_preserved_without_execution_or_capture_credit(self):
        from pipeline_v2.execution_evidence import native_attempt
        state = self.h.store.load()
        binding = self.h.controller._evidence_binding(state, self.h.root)
        native_attempt(self.h.root, self.h.feature, "unfinished-presentation", {"binding": binding, "invocation": {"channel": "fixture"}})
        page = self.invoke("evidence-read", "--record-id", "unfinished-presentation", "--present")
        restored = assemble_delivery_pages(lambda token: self.read_saved(page, continuation=token))["value"]
        self.assertFalse(restored["capture_complete"])
        self.assertFalse(restored["semantic_credit"])
        self.assertIn("attempt", restored)
        self.assertNotIn("record", restored)

    def test_old_receipt_context_survives_new_diagnostic_and_template_edit_without_freshness_credit(self):
        import pipeline_v2.runner as runner
        from pipeline_v2.artifact_io import write_json, read_json, write_read_output
        state = self.h.store.load(); active = state["active_assignment"]
        definition = active["capsule"]["context"]["qa_contract"]["definition"]
        identity = definition["identities"][0]["id"]
        first = self.invoke("qa-prepare", "--assignment-id", active["id"], "--identity-id", identity, "--present")
        snapshot = read_json(Path(first["saved_output"]["path"]))
        old_rows = [row for context in snapshot["value"]["producer_context"] for row in context.get("receipts", [])]
        self.assertTrue(old_rows)
        request_path = Path(snapshot["value"]["saved_record_request"]["path"])
        request = read_json(request_path)
        request["assessments"][0]["assessment"]["observed"] = "Unsaved authored observation; no acceptance credit."
        write_json(request_path, request)
        before = request_path.read_bytes()
        environment = {**runner.execution_environment(), "PRESENTATION_DIAGNOSTIC_FIXTURE": "new-valid-binding"}
        with mock.patch.object(runner, "execution_environment", return_value=environment):
            action = self.h.controller.status()["next_action"]
            self.invoke("check", "--id", "saved-current-diagnostic", "--expected-generation", str(action["expected_generation"]),
                "--assignment-id", active["id"], "--quiescence", "The mechanical fixture owns no live work.")
        current = self.h.controller.qa_prepare(active["id"], identity_id=identity)
        new_rows = [row for context in current["producer_context"] for row in context.get("receipts", [])]
        self.assertNotEqual(old_rows, new_rows)
        files_before = sorted(request_path.parent.glob("*.json"))
        restored = assemble_delivery_pages(lambda token: self.read_saved(first, continuation=token))
        self.assertEqual(snapshot["value"], restored["value"])
        methods = assemble_delivery_pages(lambda token: self.read_saved(first, "/value/obligations/method_definitions", token))
        self.assertEqual(snapshot["value"]["obligations"]["method_definitions"], methods["value"])
        self.assertEqual(before, request_path.read_bytes())
        self.assertEqual(files_before, sorted(request_path.parent.glob("*.json")))
        self.assertTrue(restored["snapshot_read"])
        self.assertFalse(restored["read_credit"])
        forged = deepcopy(snapshot)
        forged["value"]["producer_context"][0]["receipts"][0]["source_locator"] += "forged"
        saved = write_read_output(self.h.root, self.h.store.path.parent, None, forged)
        with self.assertRaises(PipelineError):
            self.read_saved({"saved_output": saved})
        stale = self.h.controller.qa_record(active["id"], {"binding": snapshot["value"]["binding"], "expected_revision": -1, "assessments": request["assessments"]})
        self.assertFalse(stale["valid"])
        self.assertEqual(before, request_path.read_bytes())


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
        self.assertTrue(parsed.present)


if __name__ == "__main__":
    unittest.main()
