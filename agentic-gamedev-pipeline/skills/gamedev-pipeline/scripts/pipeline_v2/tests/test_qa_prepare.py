"""Pure authoring/reader fixtures; no native runtime digest or product execution."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import io
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock

from pipeline_v2.artifact_io import read_json, write_json
from pipeline_v2.cli import main, parser, run
from pipeline_v2.delivery import read_file
from pipeline_v2.delivery import assemble_delivery_pages
from pipeline_v2.execution_evidence import begin, capture, input_snapshot, native_record, native_attempt, finish_native_attempt, read, _directory
from pipeline_v2.model import PipelineError, qa_contract_context, digest
from pipeline_v2.qa_contract import contract_digest, source_reference
from pipeline_v2.tests import test_qa_working_draft as fixtures


class QAPrepareTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.QAWorkingDraftTests("runTest")
        self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.controller, self.root = self.f.controller, self.f.root

    def cli(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch("pipeline_v2.cli.Controller", return_value=self.controller), redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--root", str(self.root), "--feature", "feature", *args])
        return code, json.loads(stdout.getvalue()) if stdout.getvalue() else None, stderr.getvalue()

    def prepare(self, *ids, method="observed-action"):
        return self.controller.qa_prepare("qa-current", list(ids), method)

    def present(self, *args):
        with mock.patch("pipeline_v2.cli.Controller", return_value=self.controller):
            return run(parser().parse_args(["--root", str(self.root), "--feature", "feature", *args]))

    def saved(self, page, *, pointer="/value", continuation=None, limit=8192):
        args = ["delivery-read", "--saved-output", page["saved_output"]["path"], "--digest", page["saved_output"]["sha256"],
                "--pointer", pointer, "--limit", str(limit)]
        if continuation:
            args += ["--continuation", continuation]
        return self.present(*args)

    def test_large_prepared_context_survives_edit_and_lazy_read_without_repreparing_template(self):
        identity = self.f.definition["identities"][0]
        prototype = deepcopy(identity["assertions"][0])
        identity["assertions"] = [{**deepcopy(prototype), "id": f"case-{index}"} for index in range(39)]
        self.f.state["execution"]["qa_contract_binding"]["contract_digest"] = contract_digest(self.f.contract)
        self.f.state["active_assignment"]["capsule"]["context"]["qa_contract"] = qa_contract_context(self.f.state)
        first = self.present("qa-prepare", "--assignment-id", "qa-current", "--identity-id", identity["id"], "--present", "--limit", "8192")
        snapshot = read_json(Path(first["saved_output"]["path"]))
        self.assertFalse(first["complete"])
        self.assertEqual(39, len(snapshot["value"]["obligations"]["identities"][0]["assertions"]))
        request = Path(snapshot["value"]["saved_record_request"]["path"])
        edited = read_json(request)
        edited["assessments"][0]["assessment"]["observed"] = "Actual unsaved local observation"
        write_json(request, edited)
        before = request.read_bytes()
        files_before = sorted(request.parent.glob("*.json"))
        restored = assemble_delivery_pages(lambda token: self.saved(first, continuation=token))
        self.assertEqual(snapshot["value"], restored["value"])
        methods = assemble_delivery_pages(lambda token: self.saved(first, pointer="/value/obligations/method_definitions", continuation=token))
        self.assertEqual(snapshot["value"]["obligations"]["method_definitions"], methods["value"])
        self.assertEqual(before, request.read_bytes())
        self.assertEqual(files_before, sorted(request.parent.glob("*.json")))
        self.assertFalse(restored["read_credit"])
        self.assertTrue(restored["snapshot_read"])
        self.assertFalse(self.controller.qa_record("qa-current", {"expected_revision": -1, "assessments": [self.f.row("case-0")]})["valid"])

    def test_saved_context_rejects_current_owner_candidate_and_forged_producer_facts(self):
        from pipeline_v2.artifact_io import write_read_output
        first = self.present("qa-prepare", "--assignment-id", "qa-current", "--assertion-id", "enter", "--present")
        snapshot = read_json(Path(first["saved_output"]["path"]))
        forged = deepcopy(snapshot)
        forged["value"]["producer_context"][0]["prerequisite"]["status"] = "receipts_available"
        saved = write_read_output(self.root, self.f.store.path.parent, None, forged)
        with self.assertRaises(PipelineError):
            self.saved({"saved_output": saved})
        old = self.f.binding["candidate_tree_oid"]
        self.f.binding["candidate_tree_oid"] = "d" * 40
        with self.assertRaises(PipelineError):
            self.saved(first)
        self.f.binding["candidate_tree_oid"] = old
        self.f.state["active_assignment"]["worker_id"] = "different-reader"
        with self.assertRaises(PipelineError):
            self.saved(first)

    def capture(self, record_id, raw, *, channel="exec_command.playwright", preflight=False):
        request = {"record_id": record_id, "invocation": {"channel": channel, "request": {"argv": ["probe-only-fixture", "not-product.html"]}},
                   "environment": {"surface": "fixture"}, "input_paths": ["game.txt"]}
        binding = deepcopy(self.f.binding)
        if preflight:
            binding["kind"] = "preflight"
        path = self.root / (record_id + ".raw"); path.write_bytes(raw)
        begin(self.root, "feature", request, binding)
        return capture(self.root, "feature", record_id, path, request["environment"], binding)

    def test_explicit_selection_produces_only_canonical_pending_rows_without_credit(self):
        result = self.prepare("reset", method="METHOD-fe82d465e8433451")
        row = result["record_request"]["assessments"][0]
        self.assertEqual(("reset", "observed-action"), (row["id"], row["method_id"]))
        self.assertEqual(["observation"], [item["type"] for item in row["evidence"]])
        self.assertIsNone(row["assessment"]["observed"])
        self.assertIsNone(row["assessment"]["comparison"])
        self.assertNotIn("outcome", row)
        self.assertEqual("observed-action", result["prepared_methods"][0]["method_id"])
        self.assertNotIn("expected", row["assessment"])
        self.assertTrue(next(iter(result["obligations"]["method_definitions"].values()))["description"])
        self.assertFalse(Path(result["working_path"]).exists())
        rejected = self.controller.qa_record("qa-current", result["record_request"])
        self.assertFalse(rejected["valid"])
        self.assertEqual("/assessments/0/evidence/0/ref", rejected["errors"][0]["path"])
        self.assertFalse(Path(result["working_path"]).exists())
        self.assertEqual("observed-action", self.prepare("enter", method=None)["record_request"]["assessments"][0]["method_id"])
        for identifiers, method in ((["unknown"], "observed-action"), (["enter", "enter"], "observed-action"), (["enter"], "not-approved")):
            with self.assertRaises(PipelineError):
                self.controller.qa_prepare("qa-current", identifiers, method)

    def test_output_is_editable_record_input_and_first_group_survives_resume(self):
        destination = Path(self.f.state["workflow_path"]) / "ReadOutputs/group.json"
        code, response, stderr = self.cli("qa-prepare", "--assignment-id", "qa-current", "--assertion-id", "enter", "--method-id", "observed-action", "--output", str(destination))
        self.assertEqual((0, ""), (code, stderr))
        packet = read_json(self.root / destination)
        self.assertEqual({"binding", "expected_revision", "assessments"}, set(packet))
        self.assertTrue(response["selection_complete"])
        self.assertNotIn("record_request", response["value"])
        self.assertNotIn("prepared_context_read_arguments", response["value"])
        self.assertEqual(str(self.root / destination), response["value"]["saved_record_request"]["path"])
        self.assertEqual("enter", response["value"]["obligations"]["identities"][0]["assertions"][0]["id"])
        packet["assessments"][0].update(self.f.row())
        self.assertTrue(self.controller.qa_record("qa-current", packet)["valid"])
        self.f.state["generation"] += 1
        resumed = self.prepare("enter", "reset")
        self.assertEqual(1, resumed["revision"])
        stored = self.controller.qa_read("qa-current", assertion_id="enter")["assessments"][0]
        self.assertEqual(stored, resumed["record_request"]["assessments"][0])
        self.assertIsNone(resumed["record_request"]["assessments"][1]["assessment"]["comparison"])
        self.assertEqual(1, self.controller.qa_read("qa-current")["assessed"])
        code, _, stderr = self.cli("qa-prepare", "--assignment-id", "qa-current", "--assertion-id", "reset", "--method-id", "observed-action", "--output", "game.txt")
        self.assertEqual(2, code)
        self.assertIn("ReadOutputs", stderr)

    def prepared_source_request(self, identifier="enter"):
        method = self.f.definition["method_definitions"]["METHOD-fe82d465e8433451"]
        method.update(id="source-read", description="Inspect the initial state assignment in the current source.",
                      capabilities=[], evidence_types=["source-observation"])
        for identity in self.f.definition["identities"]:
            for assertion in identity["assertions"]:
                assertion["expected"] = "The source initializes state."
        self.f.state["execution"]["qa_contract_binding"]["contract_digest"] = contract_digest(self.f.contract)
        self.f.state["active_assignment"]["capsule"]["context"]["qa_contract"] = qa_contract_context(self.f.state)
        prepared = self.prepare(identifier, method="source-read")
        request = prepared["record_request"]
        row = request["assessments"][0]
        self.assertIsNone(row["evidence"][0]["ref"])
        self.assertNotIn("outcome", row)
        view = {"active_assignment": self.f.state["active_assignment"], "next_action": {"command": "complete"}}
        source = read_file(self.root, view, "game.txt", lines=(1, 1))
        self.assertEqual((self.root / "game.txt").read_bytes().decode("utf-8"), source["text"])
        self.assertEqual(["state = initialized"], source["text"].splitlines())
        row["environment"] = "Current assigned source inspected through file-read."
        row["evidence"][0].update(source=source["source"], observation=source["text"])
        row["assessment"].update(observed="The selected source assigns the initialized state.", comparison="matches")
        return request

    def test_prepared_source_null_and_omitted_refs_record_without_mutating_input(self):
        for identifier, omit in (("enter", False), ("reset", True)):
            with self.subTest(omit_ref=omit):
                request = self.prepared_source_request(identifier)
                evidence = request["assessments"][0]["evidence"][0]
                if omit:
                    del evidence["ref"]
                submitted = deepcopy(request)
                result = self.controller.qa_record("qa-current", request)
                self.assertTrue(result["valid"], result.get("errors"))
                self.assertEqual(submitted, request)
                saved = self.controller.qa_read("qa-current", assertion_id=identifier)["assessments"][0]
                self.assertEqual(source_reference(evidence["source"]), saved["evidence"][0]["ref"])
                expected = deepcopy(submitted["assessments"][0])
                expected["evidence"][0]["ref"] = saved["evidence"][0]["ref"]
                expected["assessment"]["expected"] = "The source initializes state."
                expected["outcome"] = "pass"
                self.assertEqual(expected, saved)

    def test_all_alternatives_are_read_before_selection_and_same_id_bodies_stay_distinct(self):
        original = self.f.definition["method_definitions"]["METHOD-fe82d465e8433451"]
        alternative = deepcopy(original)
        alternative.update(id="alternate", description="Different full method with exact whitespace\r\n and a second condition.")
        self.f.definition["method_definitions"]["alternate-ref"] = alternative
        rows = self.f.definition["identities"][0]["assertions"]
        rows[0]["methods"].append({"ref": "alternate-ref"})
        different_same_id = deepcopy(original)
        different_same_id["description"] += " A different mandatory procedure for reset."
        rows[1]["methods"] = [different_same_id]
        self.f.state["execution"]["qa_contract_binding"]["contract_digest"] = contract_digest(self.f.contract)
        self.f.state["active_assignment"]["capsule"]["context"]["qa_contract"] = qa_contract_context(self.f.state)
        prepared = self.prepare("enter", "reset", method=None)
        definitions = prepared["obligations"]["method_definitions"]
        self.assertEqual(3, len(definitions))
        self.assertEqual(2, sum(method["id"] == "observed-action" for method in definitions.values()))
        self.assertIn(alternative, definitions.values())
        self.assertIsNone(prepared["record_request"]["assessments"][0]["method_id"])
        self.assertEqual([], prepared["record_request"]["assessments"][0]["evidence"])
        explicit = self.prepare("enter", method="observed-action")
        self.assertEqual(2, len(explicit["obligations"]["method_definitions"]))
        self.assertEqual("observed-action", explicit["record_request"]["assessments"][0]["method_id"])

    def test_group_scaffold_shares_only_metadata_and_saves_distinct_assessments(self):
        prepared = self.prepare("enter", "reset", method=None)
        request = prepared["record_request"]
        self.assertEqual({"method_id": "observed-action", "environment": None}, request["shared"])
        self.assertEqual(1, len(prepared["obligations"]["method_definitions"]))
        request["shared"]["environment"] = "One actual observed fixture session"
        for row in request["assessments"]:
            row["evidence"][0].update(ref="fixture:" + row["id"], observation="Actual " + row["id"] + " result")
            row["assessment"].update(observed="Observed " + row["id"], comparison="matches")
        result = self.controller.qa_record("qa-current", request)
        self.assertTrue(result["valid"], result.get("errors"))
        self.assertEqual(["enter", "reset"], result["changed_assertion_ids"])
        self.assertNotIn("identities", result)
        self.assertNotIn("technical_decisions", result)
        self.assertEqual(2, result["assessed"])
        for row in request["assessments"]:
            stored = self.controller.qa_read("qa-current", assertion_id=row["id"])["assessments"][0]
            self.assertEqual(row["assessment"]["observed"], stored["assessment"]["observed"])
            self.assertEqual(request["shared"]["environment"], stored["environment"])
        retry = self.controller.qa_record("qa-current", request)
        self.assertTrue(retry["valid"])
        self.assertEqual([], retry["changed_assertion_ids"])

    def test_unused_malformed_shared_origin_has_its_exact_request_path_and_no_write(self):
        request = self.prepare("enter")["record_request"]
        request["assessments"][0] = self.f.row()
        request["shared"] = {"evidence": [{"type": "unused-type", "ref": "", "source": self.f.source()}]}
        result = self.controller.qa_record("qa-current", request)
        self.assertFalse(result["valid"])
        self.assertEqual("/shared/evidence/0/ref", result["errors"][0]["path"])
        self.assertFalse(Path(result["working_path"]).exists())

    def test_prepared_source_refs_preserve_nonnull_and_reject_invalid_or_stale_metadata(self):
        request = self.prepared_source_request()
        progress = self.controller.qa_draft("qa-current")
        draft_path = Path(progress["working_path"])
        original_draft = draft_path.read_bytes()
        source_path = self.root / "game.txt"
        original_source = source_path.read_bytes()
        for variant, field in (("missing_source", "ref"), ("invalid_source", "source"),
                               ("stale_source", "source"), ("nonnull_ref", "ref"), ("empty_ref", "ref")):
            with self.subTest(variant=variant):
                changed = deepcopy(request)
                evidence = changed["assessments"][0]["evidence"][0]
                source_path.write_bytes(original_source)
                if variant == "missing_source":
                    del evidence["source"]
                elif variant == "invalid_source":
                    evidence["source"]["sha256"] = "not-a-source-hash"
                elif variant == "stale_source":
                    source_path.write_bytes(b"state = changed\n")
                elif variant == "nonnull_ref":
                    evidence["ref"] = "caller-provided:preserve-me"
                else:
                    evidence["ref"] = ""
                submitted = deepcopy(changed)
                result = self.controller.qa_record("qa-current", changed)
                self.assertFalse(result["valid"])
                self.assertEqual("/assessments/0/evidence/0/" + field, result["errors"][0]["path"])
                self.assertEqual(submitted, changed)
                self.assertEqual(original_draft, draft_path.read_bytes())
        source_path.write_bytes(original_source)
        request["assessments"][0]["evidence"][0]["ref"] = source_reference(request["assessments"][0]["evidence"][0]["source"])
        submitted = deepcopy(request)
        result = self.controller.qa_record("qa-current", request)
        self.assertTrue(result["valid"], result.get("errors"))
        self.assertEqual(submitted, request)
        saved = self.controller.qa_read("qa-current", assertion_id="enter")["assessments"][0]["evidence"][0]
        self.assertEqual(submitted["assessments"][0]["evidence"][0], saved)

    def test_probe_projection_preserves_origin_and_never_offers_fixture_as_product_invocation(self):
        self.f.set_producer("tool", "exec_command.playwright")
        self.capture("probe", b'{"channelAvailable":true}', preflight=True)
        context = self.prepare("enter", "reset")["producer_context"]
        self.assertEqual(1, len(context))
        context = context[0]
        self.assertEqual("probe_bound", context["prerequisite"]["status"])
        self.assertEqual("caller-captured-original-result", context["provenance"])
        self.assertIsNone(context["product_invocation"])
        self.assertNotIn("probe-only-fixture", json.dumps(context))
        self.assertTrue(context["probe"]["request_locator"].endswith("#/before/invocation"))
        self.assertEqual("exec_command.playwright", context["evidence_begin_request"]["invocation"]["channel"])
        self.assertIsNone(context["evidence_begin_request"]["invocation"]["request"])
        (self.root / "game.txt").write_text("changed probe input", encoding="utf-8")
        self.assertEqual("unresolved", self.prepare("enter")["producer_context"][0]["prerequisite"]["status"])

    def test_preparation_preserves_recorded_unavailable_and_conditional_applicability(self):
        spec = self.f.definition["identities"][1]["assertions"][0]
        spec["applicability"] = {"kind": "conditional", "condition": "Approved absent fixture condition", "evidence_types": ["observation"]}
        self.f.state["execution"]["qa_contract_binding"]["contract_digest"] = contract_digest(self.f.contract)
        self.f.state["active_assignment"]["capsule"]["context"]["qa_contract"] = qa_contract_context(self.f.state)
        conditional = self.f.row("core"); conditional.update(outcome="not_applicable", method_id=None)
        request = {"expected_revision": 0, "assessments": [self.f.external("enter"), conditional]}
        self.assertTrue(self.controller.qa_record("qa-current", request)["valid"])
        prepared = self.prepare("enter", "core")
        self.assertEqual(["not_run", "not_applicable"], [row["outcome"] for row in prepared["record_request"]["assessments"]])
        for row in prepared["record_request"]["assessments"]:
            self.assertEqual(row, self.controller.qa_read("qa-current", assertion_id=row["id"])["assessments"][0])

    def test_native_preparation_uses_current_receipt_refs_without_assessing_them(self):
        self.f.set_producer("controller_check")
        method = self.f.definition["method_definitions"]["METHOD-fe82d465e8433451"]
        method["evidence_types"] = ["controller-check-receipt", "case-observation"]
        self.f.state["execution"]["qa_contract_binding"]["contract_digest"] = contract_digest(self.f.contract)
        self.f.state["active_assignment"]["capsule"]["context"]["qa_contract"] = qa_contract_context(self.f.state)
        self.f.state["slices"][0]["planned_commands"] = [["declared-native", "--test"]]
        recipe = {"id": "native-check", "argv": ["declared-native", "--test"], "kind": "deterministic", "timeout_seconds": 10, "independent": False, "input_paths": []}
        self.f.state["execution"]["verification"] = {"slices": {"SLICE-001": [recipe]}}
        with mock.patch("pipeline_v2.runner.machine_check_inputs", return_value={"checks": [{"id": "native-check", "execution_evidence": "execution-evidence:native", "returncode": 0}]}):
            result = self.prepare("enter")
        self.assertEqual([recipe], result["producer_context"][0]["checks"])
        evidence = result["record_request"]["assessments"][0]["evidence"]
        self.assertEqual("execution-evidence:native", evidence[0]["ref"])
        self.assertIsNone(evidence[0]["observation"])
        self.assertIsNone(evidence[1]["ref"])
        self.assertFalse(result["semantic_credit"])

    def test_actual_channel_mismatch_and_wrong_authoring_field_have_exact_input_paths(self):
        self.f.set_producer("tool", "exec_command.playwright")
        record = self.capture("actual-cua", b'{"actual":true}', channel="cua-repl.chrome.extension")
        row = self.f.row(); row["evidence"][0]["ref"] = record["ref"]
        result = self.controller.qa_record("qa-current", {"expected_revision": 0, "assessments": [row]})
        self.assertFalse(result["valid"])
        self.assertEqual("/assessments/0/evidence/0/ref", result["errors"][0]["path"])
        self.assertIn("cua-repl.chrome.extension", result["errors"][0]["message"])
        self.assertIn("exec_command.playwright", result["errors"][0]["message"])
        row["environment"] = {"not": "a string"}
        result = self.controller.qa_record("qa-current", {"expected_revision": 0, "assessments": [row]})
        self.assertEqual("/assessments/0/environment", result["errors"][0]["path"])

    def issued_native(self, returncode=0):
        self.f.set_producer("controller_check")
        self.f.state["slices"][0]["planned_commands"] = [["test", "native-check"]]
        recipe = {"id": "native-check", "argv": ["test", "native-check"], "kind": "deterministic", "timeout_seconds": 10, "independent": False, "input_paths": ["game.txt"]}
        self.f.state["execution"]["verification"] = {"slices": {"SLICE-001": [recipe]}}
        directory = _directory(self.root, "feature", "issued-check"); directory.mkdir(parents=True)
        for name in ("stdout", "stderr"):
            (directory / (name + ".bin")).write_bytes(b"")
        inputs = input_snapshot(self.root, ["game.txt"])
        invocation = {"argv": recipe["argv"], "check_id": recipe["id"], "action_id": "original-check"}
        native_attempt(self.root, "feature", "issued-check", {"binding": self.f.binding, "invocation": invocation,
            "recipe": recipe, "environment": {"original_process": "captured"}, "inputs": inputs})
        ref = native_record(self.root, "feature", "issued-check", invocation=invocation, binding=self.f.binding,
            environment={"original_process": "captured"}, inputs_before=inputs, inputs_after=inputs, after_binding=self.f.binding,
            result={"returncode": returncode}, stream_digests={name: hashlib.sha256(b"").hexdigest() for name in ("stdout", "stderr")})
        record = read(self.root, "feature", "issued-check")["record"]
        finish_native_attempt(self.root, "feature", "issued-check", {"execution_evidence": ref, "execution_record_digest": record["digest"]})
        self.f.state["history"] = [{"execution_records": [{"ref": ref, "digest": record["digest"], "check_id": recipe["id"], "returncode": returncode, "argv_sha256": digest(recipe["argv"])}]}]
        machine = {key: self.f.binding[key] for key in ("candidate_tree_oid", "authority_digest", "pipeline_runtime_digest")}
        machine.update(checks=[{"id": recipe["id"], "outcome": "pass" if returncode == 0 else "fail", "returncode": returncode,
                               "execution_evidence": ref, "execution_record_digest": record["digest"]}], pending_check_ids=[])
        self.f.state["active_assignment"]["capsule"]["context"]["machine_checks"] = machine
        return machine, directory

    def test_issued_failed_receipt_stays_available_without_reader_env_reuse_or_pass(self):
        machine, _ = self.issued_native(returncode=7)
        with mock.patch("pipeline_v2.runner.machine_check_inputs", side_effect=AssertionError("reader must not recalculate execution reuse")):
            result = self.prepare("enter")
        context = result["producer_context"][0]
        self.assertEqual("receipts_available", context["prerequisite"]["status"])
        self.assertEqual(machine["checks"], context["receipts"])
        self.assertEqual("fail", context["receipts"][0]["outcome"])
        self.assertNotIn("outcome", result["record_request"]["assessments"][0])
        self.assertFalse(result["semantic_credit"])

    def test_mixed_execution_and_source_origin_points_to_conflicting_ref_without_rewriting(self):
        machine, _ = self.issued_native()
        original = self.controller.qa_draft("qa-current")
        path = Path(original["working_path"]); original_bytes = path.read_bytes()
        row = self.f.row()
        row["evidence"][0].update(ref=machine["checks"][0]["execution_evidence"] + "#actual-case", source=self.f.source())
        request = {"expected_revision": 0, "assessments": [row]}
        submitted = deepcopy(request)
        result = self.controller.qa_record("qa-current", request)
        self.assertFalse(result["valid"])
        self.assertEqual("/assessments/0/evidence/0/ref", result["errors"][0]["path"])
        self.assertIn("execution-record ref cannot also be a candidate-source reference", result["errors"][0]["message"])
        self.assertIn("separate evidence items", result["errors"][0]["message"])
        self.assertEqual(submitted, request)
        self.assertEqual(original_bytes, path.read_bytes())
        source = row["evidence"][0].pop("source")
        row["evidence"].append({"type": "source-context", "source": source, "observation": "Actual inspected source context for the recorded execution."})
        result = self.controller.qa_record("qa-current", request)
        self.assertTrue(result["valid"], result.get("errors"))
        saved = self.controller.qa_read("qa-current", assertion_id="enter")["assessments"][0]["evidence"]
        self.assertEqual(submitted["assessments"][0]["evidence"][0]["ref"], saved[0]["ref"])
        self.assertNotIn("source", saved[0])
        self.assertEqual(source, saved[1]["source"])
        self.assertTrue(saved[1]["ref"].startswith("candidate-source:"))

    def test_issued_receipt_rejects_binding_input_raw_history_and_caller_origin_drift(self):
        machine, directory = self.issued_native()
        source = self.root / "game.txt"; original_source = source.read_bytes()
        original_machine, original_history = deepcopy(machine), deepcopy(self.f.state["history"])
        original_recipe = deepcopy(self.f.state["execution"]["verification"]["slices"]["SLICE-001"][0])
        caller = self.capture("caller", b'{"claimed":"native"}')
        for variant in ("binding", "input", "raw", "history", "caller", "recipe"):
            with self.subTest(variant=variant):
                self.f.state["active_assignment"]["capsule"]["context"]["machine_checks"] = machine = deepcopy(original_machine)
                self.f.state["history"] = deepcopy(original_history)
                self.f.state["execution"]["verification"]["slices"]["SLICE-001"][0] = deepcopy(original_recipe)
                source.write_bytes(original_source); (directory / "stdout.bin").write_bytes(b"")
                if variant == "binding": machine["candidate_tree_oid"] = "d" * 40
                elif variant == "input": source.write_bytes(b"changed input")
                elif variant == "raw": (directory / "stdout.bin").write_bytes(b"changed raw")
                elif variant == "history": self.f.state["history"] = []
                elif variant == "recipe": self.f.state["execution"]["verification"]["slices"]["SLICE-001"][0]["timeout_seconds"] = 11
                else: machine["checks"][0].update(execution_evidence=caller["ref"], execution_record_digest=caller["record"]["digest"])
                with mock.patch("pipeline_v2.runner.machine_check_inputs", side_effect=AssertionError("must not hide an invalid issued receipt via fallback")):
                    result = self.prepare("enter")
                self.assertEqual("unresolved", result["producer_context"][0]["prerequisite"]["status"])
                self.assertEqual([], result["producer_context"][0]["receipts"])
                self.assertIsNone(result["record_request"]["assessments"][0]["evidence"][0]["ref"])

    def test_raw_json_and_text_focus_are_lossless_and_do_not_dump_unselected_values(self):
        selected = {"label": "Ёж 🟢\r\nexact", "observations": [1, 2, 3]}
        record = self.capture("large", json.dumps({"selected": selected, "unrelated": "NEVER-DUMP-" * 100000}, ensure_ascii=False).encode("utf-8"))
        code, response, stderr = self.cli("evidence-read", "--record-id", "large", "--raw-file", "result.bin", "--pointer", "/value/selected", "--assemble", "--limit", "13")
        self.assertEqual((0, ""), (code, stderr))
        self.assertEqual(selected, response["value"])
        self.assertEqual(record["ref"], response["ref"])
        self.assertEqual(record["path"], response["record_path"])
        self.assertNotIn("NEVER-DUMP", json.dumps(response))
        self.assertEqual(record["record"]["raw"]["sha256"], response["raw"]["sha256"])
        text = "first\r\nЁж 🟢\nlast\t "
        self.capture("text", text.encode("utf-8"))
        _, response, _ = self.cli("evidence-read", "--record-id", "text", "--raw-file", "result.bin", "--pointer", "/value", "--assemble", "--limit", "7")
        self.assertEqual(text, response["value"])

    def test_raw_reader_rejects_unrecorded_path_unknown_pointer_tamper_and_binary(self):
        record = self.capture("raw", b'{"one":1}')
        for file, pointer in (("../request.json", "/value"), ("result.bin", "/value/missing")):
            code, _, stderr = self.cli("evidence-read", "--record-id", "raw", "--raw-file", file, "--pointer", pointer)
            self.assertEqual(2, code)
            self.assertTrue(stderr)
        (Path(record["path"]).parent / "result.bin").write_bytes(b'{"one":2}')
        code, _, stderr = self.cli("evidence-read", "--record-id", "raw", "--raw-file", "result.bin", "--pointer", "/value/one")
        self.assertEqual(2, code); self.assertIn("digest", stderr)
        self.capture("binary", b'\x89PNG\xff\x00')
        code, _, stderr = self.cli("evidence-read", "--record-id", "binary", "--raw-file", "result.bin")
        self.assertEqual(2, code); self.assertIn("original file reader", stderr)

    def test_evidence_request_file_and_declared_input_errors_are_distinct(self):
        code, _, stderr = self.cli("evidence-begin", "--request", "missing-request.json")
        self.assertEqual(2, code); self.assertIn("missing-request.json", stderr)
        request = {"record_id": "input-error", "invocation": {"channel": "test"}, "environment": {"fixture": True}, "input_paths": ["missing-input.txt"]}
        with self.assertRaises(PipelineError) as error:
            begin(self.root, "feature", request, self.f.binding)
        self.assertEqual("/input_paths/0", error.exception.path)
        self.assertIn("missing-input.txt", str(error.exception))


if __name__ == "__main__":
    unittest.main()
