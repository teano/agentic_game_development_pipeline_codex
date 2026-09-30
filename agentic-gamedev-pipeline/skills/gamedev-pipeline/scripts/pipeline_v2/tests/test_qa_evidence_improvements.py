"""Counterexamples: contradictory QA, external waits, raw evidence and producer routes."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from pipeline_v2.qa_contract import QAContractError, producer_feasibility, validate_results
from pipeline_v2.artifact_io import read_json, write_json, write_read_output, validation_errors
from pipeline_v2.execution_evidence import begin, capture, read, validate_references, native_record, _directory
from pipeline_v2.model import PipelineError, digest, compact_assignment_context, unresolved_qa_observations
from pipeline_v2.tests.test_qa_contract import sample_contract, passing_checks


class QAReasonAndProducerTests(unittest.TestCase):
    def setUp(self):
        self.contract = sample_contract()
        self.definition = self.contract["slices"]["SLICE-001"]
        self.checks = passing_checks(self.contract)

    def test_negative_direction_observation_cannot_claim_pass_when_compared_truthfully(self):
        definition = self.definition["identities"][0]["assertions"][0]
        definition["expected"] = "Hands and feet extend forward."
        definition["methods"][0]["require_assessment"] = True
        row = self.checks[0]["assertions"][0]
        row["assessment"] = {"expected": definition["expected"], "observed": "hands forwardDot=-1.70587; feet=-1.91361",
                             "comparison": "contradicts"}
        with self.assertRaisesRegex(QAContractError, "cannot PASS"):
            validate_results(self.checks, self.definition, outcome="pass")
        row["assessment"]["comparison"] = "insufficient"
        with self.assertRaisesRegex(QAContractError, "cannot PASS"):
            validate_results(self.checks, self.definition, outcome="pass")
        # The validator enforces a declared comparison; it does not pretend to
        # infer arbitrary prose/vector semantics if the worker lies about it.

    def test_external_only_blocked_and_mixed_repair_preserves_inventory(self):
        row = self.checks[0]["assertions"][0]
        row.update(outcome="not_run", method_id=None,
                   reason={"kind": "external_wait", "detail": "User will supply the two-account observation after implementation.", "refs": ["owner-observation"]},
                   evidence=[{"type": "external-prerequisite", "ref": "user-decision:1", "observation": "Named user owns pending two-account action; criterion remains mandatory."}])
        self.checks[0]["outcome"] = "not_run"
        validate_results(self.checks, self.definition, outcome="blocked")
        self.checks[1]["assertions"][0]["outcome"] = "fail"
        self.checks[1]["outcome"] = "fail"
        result = validate_results(self.checks, self.definition, outcome="fail")
        self.assertEqual("external_wait", result[0]["assertions"][0]["reason"]["kind"])
        self.assertEqual(3, sum(len(c["assertions"]) for c in result))

    def test_method_unavailable_is_not_repairable_product_failure(self):
        row = self.checks[0]["assertions"][0]
        row.update(outcome="not_run", method_id=None, evidence=[{"type": "method-gap", "ref": "probe:1", "observation": "Actual channel cannot return the required receipt."}],
                   reason={"kind": "method_unavailable", "detail": "Owning plan method prerequisite needs correction.", "refs": ["observed-action"]})
        self.checks[0]["outcome"] = "not_run"
        validate_results(self.checks, self.definition, outcome="blocked")

    def test_initial_receipt_contract_is_rejected_without_exact_producer(self):
        method = self.definition["identities"][0]["assertions"][0]["methods"][0]
        method["evidence_types"] = ["bound-machine-receipt"]
        recipes = [{"id": "build-only"}]
        self.assertEqual("incompatible", producer_feasibility(self.definition, recipes)["status"])
        method["producer"] = {"kind": "controller_check", "check_ids": ["runtime-suite"]}
        self.assertIn("not sealed", producer_feasibility(self.definition, recipes)["errors"][0]["detail"])
        self.assertFalse(producer_feasibility(self.definition, [{"id": "runtime-suite"}])["errors"])

    def test_manual_and_tool_routes_do_not_need_cli_and_legacy_is_unverified(self):
        self.assertEqual("legacy_unverified", producer_feasibility(self.definition, [])["status"])
        for identity in self.definition["identities"]:
            for row in identity["assertions"]:
                row["methods"][0]["producer"] = {"kind": "manual", "channel": "assigned observation surface", "probe_ref": "execution-evidence:probe"}
        result = producer_feasibility(self.definition, [])
        self.assertEqual("declared", result["status"])
        self.assertFalse(result["executed_acceptance_credit"])
        self.assertTrue(result["probes"])

    def test_one_valid_approved_alternative_suffices(self):
        row = self.definition["identities"][0]["assertions"][0]
        original = row["methods"][0]
        original["evidence_types"] = ["controller-check-receipt"]
        original["producer"] = {"kind": "controller_check", "check_ids": ["missing"]}
        alternate = deepcopy(original)
        alternate["id"] = "valid-alternative"
        alternate["producer"]["check_ids"] = ["present"]
        row["methods"].append(alternate)
        result = producer_feasibility(self.definition, [{"id": "present"}])
        self.assertFalse(result["errors"])

    def test_independent_artifact_errors_are_batched_by_assertion(self):
        self.checks[0]["assertions"][0]["evidence"] = [[{"type": "observation"}]]
        self.checks[0]["assertions"][0]["method_id"] = "wrong-method"
        self.checks[0]["assertions"][1]["evidence"] = {"type": "observation", "ref": "one", "observation": "singleton"}
        self.checks[1]["assertions"][0]["evidence"] = [{"type": "wrong-type", "ref": "one", "observation": "wrong evidence type"}]
        state = {"active_assignment": {"phase": "qa", "role": "qa", "capsule": {"context": {
            "qa_contract": {"status": "bound", "definition": self.definition}}}}}
        errors = validation_errors(state, {"outcome": "pass", "checks": self.checks})
        messages = "\n".join(e["message"] for e in errors)
        self.assertIn("approved method", messages)
        self.assertIn("evidence must be a list", messages)
        self.assertIn("lacks required types", messages)
        self.assertIn("evidence item", messages)

    def test_feasibility_survives_lossless_capsule_projection(self):
        source = {"verification_feasibility": producer_feasibility(self.definition, []),
                  "required_finding_conditions": [{"id": "condition-1", "text": "keep exactly"}]}
        projected = compact_assignment_context(source, None, canonical_input=True)
        self.assertEqual(source["verification_feasibility"], projected["verification_feasibility"])
        self.assertEqual(source["required_finding_conditions"], projected["required_finding_conditions"])

    def test_historical_residual_filters_pass_and_rejects_other_contract_or_slice(self):
        from pipeline_v2.qa_contract import contract_digest
        binding = {"authority_digest": "a" * 64, "contract_digest": contract_digest(self.contract), "slice_id": "SLICE-001"}
        checks = deepcopy(self.checks)
        checks[0]["assertions"][0]["outcome"] = "not_run"
        previous = {"assignment_id": "qa-old", "qa_contract": {"binding": binding}, "candidate_binding": {"candidate_tree_oid": "old"},
                    "worker": {"checks": checks}}
        state = {"feature": "feature", "workflow_path": ".agentic-pipeline/Workflows/feature", "authority": {"digest": "a" * 64},
                 "slices": [{"id": "SLICE-001"}], "artifacts": {}, "history": [{"prior_artifacts": {"qa": previous}}],
                 "execution": {"qa_contract": self.contract, "qa_contract_binding": {k: binding[k] for k in ("authority_digest", "contract_digest")}}}
        result = unresolved_qa_observations(state)
        self.assertEqual(1, len(result["checks"]))
        self.assertEqual(1, len(result["checks"][0]["assertions"]))
        self.assertFalse(result["grants_credit"])
        for key, value in (("authority_digest", "different"), ("slice_id", "other-slice"), ("contract_digest", "different")):
            altered = deepcopy(state)
            altered["history"][0]["prior_artifacts"]["qa"]["qa_contract"]["binding"][key] = value
            self.assertIsNone(unresolved_qa_observations(altered))
        # A newer completed QA prevents resurrecting the older residual.
        state["artifacts"]["qa"] = deepcopy(previous)
        state["artifacts"]["qa"]["worker"]["checks"] = self.checks
        self.assertIsNone(unresolved_qa_observations(state))
        state["artifacts"].clear()
        state["history"].append({"command": "complete", "phase": "qa", "assignment_id": "newer-qa"})
        self.assertIsNone(unresolved_qa_observations(state))


class EvidenceFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "input.txt").write_text("fixed input", encoding="utf8")
        self.binding = {"kind": "assignment", "project_root": str(self.root), "feature": "feature",
                        "authority_digest": "a" * 64, "pipeline_runtime_digest": "b" * 64,
                        "candidate_tree_oid": "c" * 40, "assignment_id": "qa-current"}
        self.request = {"record_id": "actual-run", "invocation": {"channel": "editor-tool", "action": "observe"},
                        "environment": {"session": "owned-session", "version": "1"}, "input_paths": ["input.txt"]}
        self.raw = self.root / "original.bin"
        self.raw.write_bytes(b'original\r\n\x00\xff response \xe2\x98\x83')

    def record(self):
        begin(self.root, "feature", self.request, self.binding)
        return capture(self.root, "feature", "actual-run", self.raw, self.request["environment"], self.binding)

    def test_exact_original_bytes_survive_source_cleanup_and_are_shared(self):
        expected = self.raw.read_bytes()
        result = self.record()
        self.raw.unlink()
        again = read(self.root, "feature", "actual-run")
        self.assertEqual(result, again)
        self.assertEqual(expected, (Path(result["path"]).parent / "result.bin").read_bytes())
        self.assertEqual(hashlib.sha256(expected).hexdigest(), result["record"]["raw"]["sha256"])
        self.assertFalse(result["semantic_credit"])

    def test_same_id_replay_is_safe_but_different_result_cannot_overwrite(self):
        first = self.record()
        self.assertEqual(first, self.record())
        self.raw.write_bytes(b"different")
        with self.assertRaisesRegex(PipelineError, "immutable"):
            self.record()

    def test_orphan_capture_recovers_identical_bytes_and_rejects_other_bytes(self):
        begin(self.root, "feature", self.request, self.binding)
        with mock.patch("pipeline_v2.execution_evidence.write_json", side_effect=OSError("metadata publication failed")):
            with self.assertRaises(OSError):
                capture(self.root, "feature", "actual-run", self.raw, self.request["environment"], self.binding)
        preserved = (_directory(self.root, "feature", "actual-run") / "result.bin").read_bytes()
        self.raw.write_bytes(b"different retry")
        with self.assertRaisesRegex(PipelineError, "immutable"):
            capture(self.root, "feature", "actual-run", self.raw, self.request["environment"], self.binding)
        self.assertEqual(preserved, (_directory(self.root, "feature", "actual-run") / "result.bin").read_bytes())
        self.raw.write_bytes(preserved)
        self.assertTrue(capture(self.root, "feature", "actual-run", self.raw, self.request["environment"], self.binding)["record"]["capture_complete"])

    def native(self, check_id, returncode=0, capture_error=None):
        record_id = "native-" + check_id
        directory = _directory(self.root, "feature", record_id)
        directory.mkdir(parents=True)
        for name in ("stdout", "stderr"):
            (directory / (name + ".bin")).write_bytes(b"")
        invocation = {"argv": ["test", check_id], "check_id": check_id, "action_id": "check-action"}
        ref = native_record(self.root, "feature", record_id, invocation=invocation, binding=self.binding,
            environment={"session": "fixture"}, inputs_before=[], inputs_after=[], after_binding=self.binding,
            result={"returncode": returncode}, stream_digests={name: hashlib.sha256(b"").hexdigest() for name in ("stdout", "stderr")},
            capture_error=capture_error)
        record = read(self.root, "feature", record_id)["record"]
        anchor = {"ref": ref, "digest": record["digest"], "check_id": check_id, "returncode": returncode,
                  "argv_sha256": digest(invocation["argv"])}
        return ref, anchor

    def test_producer_records_require_controller_attestation_and_complete_check_set(self):
        contract = sample_contract()
        definition = contract["slices"]["SLICE-001"]
        method = definition["identities"][0]["assertions"][0]["methods"][0]
        method.update(evidence_types=["bound-machine-receipt"], producer={"kind": "controller_check", "check_ids": ["one", "two"]})
        artifact = {"checks": passing_checks(contract)}
        row = artifact["checks"][0]["assertions"][0]
        external = self.record()
        row["evidence"] = [{"type": "bound-machine-receipt", "ref": external["ref"], "observation": "claimed success"}]
        with self.assertRaisesRegex(PipelineError, "relabelled"):
            validate_references(self.root, "feature", artifact, self.binding, state={}, contract_slice=definition)
        one, anchor1 = self.native("one")
        two, anchor2 = self.native("two")
        wrong, anchor3 = self.native("wrong")
        row["evidence"][0]["ref"] = one
        with self.assertRaisesRegex(PipelineError, "attestation"):
            validate_references(self.root, "feature", artifact, self.binding, state={}, contract_slice=definition)
        state = {"history": [{"execution_records": [anchor1, anchor2, anchor3]}]}
        with self.assertRaisesRegex(PipelineError, "every declared check_id"):
            validate_references(self.root, "feature", artifact, self.binding, state=state, contract_slice=definition)
        row["evidence"][0]["ref"] = wrong
        with self.assertRaisesRegex(PipelineError, "different approved"):
            validate_references(self.root, "feature", artifact, self.binding, state=state, contract_slice=definition)
        row["evidence"] = [{"type": "bound-machine-receipt", "ref": ref, "observation": "actual native result"} for ref in (one, two)]
        validate_references(self.root, "feature", artifact, self.binding, state=state, contract_slice=definition)

    def test_failed_native_can_explain_failure_but_cannot_support_pass(self):
        contract = sample_contract(); definition = contract["slices"]["SLICE-001"]
        method = definition["identities"][0]["assertions"][0]["methods"][0]
        method.update(evidence_types=["bound-machine-receipt"], producer={"kind": "controller_check", "check_ids": ["failed"]})
        artifact = {"checks": passing_checks(contract)}
        ref, anchor = self.native("failed", 7)
        row = artifact["checks"][0]["assertions"][0]
        row["evidence"] = [{"type": "bound-machine-receipt", "ref": ref, "observation": "actual failed native result"}]
        state = {"history": [{"execution_records": [anchor]}]}
        with self.assertRaisesRegex(PipelineError, "failed native"):
            validate_references(self.root, "feature", artifact, self.binding, state=state, contract_slice=definition)
        row["outcome"] = "fail"
        validate_references(self.root, "feature", artifact, self.binding, state=state, contract_slice=definition)

    def test_wrong_tool_channel_and_legacy_receipt_relabelling_are_rejected(self):
        external = self.record()
        contract = sample_contract(); definition = contract["slices"]["SLICE-001"]
        method = definition["identities"][0]["assertions"][0]["methods"][0]
        method["producer"] = {"kind": "tool", "channel": "different-tool", "probe_ref": "execution-evidence:probe"}
        artifact = {"checks": passing_checks(contract)}
        row = artifact["checks"][0]["assertions"][0]
        row["evidence"] = [{"type": "observation", "ref": external["ref"], "observation": "observed"}]
        with self.assertRaisesRegex(PipelineError, "producer channel"):
            validate_references(self.root, "feature", artifact, self.binding, contract_slice=definition)
        method.pop("producer")
        method["evidence_types"] = ["bound-machine-receipt"]
        row["evidence"][0]["type"] = "bound-machine-receipt"
        with self.assertRaisesRegex(PipelineError, "explicit approved"):
            validate_references(self.root, "feature", artifact, self.binding, contract_slice=definition)

    def test_changed_input_is_preserved_without_credit(self):
        begin(self.root, "feature", self.request, self.binding)
        (self.root / "input.txt").write_text("changed", encoding="utf8")
        result = capture(self.root, "feature", "actual-run", self.raw, self.request["environment"], self.binding)
        self.assertFalse(result["record"]["inputs_unchanged"])
        artifact = {"checks": [{"assertions": [{"outcome": "pass", "evidence": [{"ref": result["ref"]}]}]}]}
        with self.assertRaisesRegex(PipelineError, "unchanged inputs"):
            validate_references(self.root, "feature", artifact, self.binding)

    def test_raw_tampering_is_detected(self):
        result = self.record()
        (Path(result["path"]).parent / "result.bin").write_bytes(b"modified")
        with self.assertRaisesRegex(PipelineError, "preserved digest"):
            read(self.root, "feature", "actual-run")

    def test_preflight_never_becomes_product_acceptance(self):
        self.binding["kind"] = "preflight"
        result = self.record()
        artifact = {"checks": [{"assertions": [{"outcome": "pass", "evidence": [{"ref": result["ref"]}]}]}]}
        with self.assertRaisesRegex(PipelineError, "preflight"):
            validate_references(self.root, "feature", artifact, self.binding)

    def conditional_artifact(self, reference, evidence_type="observation"):
        contract = sample_contract(); definition = contract["slices"]["SLICE-001"]
        definition["identities"][0]["assertions"][0]["applicability"] = {
            "kind": "conditional", "condition": "Only when the feature is enabled.", "evidence_types": [evidence_type]}
        checks = passing_checks(contract)
        checks[0]["assertions"][0].update(outcome="not_applicable", method_id=None,
            evidence=[{"type": evidence_type, "ref": reference, "observation": "The approved condition is not met."}])
        validate_results(checks, definition, outcome="pass")
        return {"outcome": "pass", "checks": checks}, definition

    def test_conditional_applicability_needs_current_binding_and_unchanged_inputs(self):
        record = self.record()
        artifact, definition = self.conditional_artifact(record["ref"])
        validate_references(self.root, "feature", artifact, self.binding, contract_slice=definition)
        self.assertIsNone(artifact["checks"][0]["assertions"][0]["method_id"])
        newer = {**self.binding, "candidate_tree_oid": "d" * 40}
        with self.assertRaisesRegex(PipelineError, "unchanged inputs"):
            validate_references(self.root, "feature", artifact, newer, contract_slice=definition)
        (self.root / "input.txt").write_text("changed after observation", encoding="utf8")
        with self.assertRaisesRegex(PipelineError, "inputs changed"):
            validate_references(self.root, "feature", artifact, self.binding, contract_slice=definition)
        artifact["checks"][0]["assertions"][0]["outcome"] = "not_run"
        # Historical unexecuted observations can still be read, without credit.
        validate_references(self.root, "feature", artifact, newer, contract_slice=definition)

    def test_conditional_applicability_rejects_preflight_and_receipt_relabelling(self):
        self.binding["kind"] = "preflight"
        record = self.record()
        artifact, definition = self.conditional_artifact(record["ref"])
        with self.assertRaisesRegex(PipelineError, "preflight"):
            validate_references(self.root, "feature", artifact, self.binding, contract_slice=definition)
        self.binding["kind"] = "assignment"
        request = {**self.request, "record_id": "product-observation"}
        begin(self.root, "feature", request, self.binding)
        captured = capture(self.root, "feature", request["record_id"], self.raw, request["environment"], self.binding)
        artifact, definition = self.conditional_artifact(captured["ref"], "bound-machine-receipt")
        with self.assertRaisesRegex(PipelineError, "relabelled"):
            validate_references(self.root, "feature", artifact, self.binding, contract_slice=definition)

    def test_large_unicode_file_writer_and_read_output_boundary(self):
        value = {"text": " \r\n雪 Привет " * 20000}
        path = self.root / "large.json"
        write_json(path, value)
        self.assertEqual(value, read_json(path))
        workflow = self.root / ".agentic-pipeline/Workflows/feature"
        destination = workflow / "ReadOutputs/source.json"
        first = write_read_output(self.root, workflow, destination, value)
        self.assertEqual(first, write_read_output(self.root, workflow, destination, value))
        with self.assertRaises(PipelineError):
            write_read_output(self.root, workflow, destination, {"different": True})
        with self.assertRaises(PipelineError):
            write_read_output(self.root, workflow, workflow / "pipeline-state.json", value)


class NativeAttemptReplayPureTests(unittest.TestCase):
    """No real process, Git scan, native state or runtime digest execution."""
    def setUp(self):
        from pipeline_v2.runner import Controller
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.active = {"id": "engineering-current", "phase": "engineering", "commands": [["test-command"]]}
        self.state = {"run_id": "run", "feature": "feature", "project_root": str(self.root),
                      "base_tree_oid": "c" * 40,
                      "authority": {"digest": "a" * 64}, "pipeline_runtime_digest": "b" * 64,
                      "history": [], "phase": "engineering", "active_assignment": self.active,
                      "slices": [{"id": "SLICE-1", "planned_commands": self.active["commands"]}]}
        self.controller = Controller(None)
        self.calls = 0
        for target, value in (("candidate_tree_oid", "c" * 40), ("repository_policy_changed", []), ("_process_environment", {})):
            patcher = mock.patch("pipeline_v2.runner." + target, return_value=value)
            patcher.start(); self.addCleanup(patcher.stop)

    def process(self, *args, **kwargs):
        from pipeline_v2.process_tree import ProcessEvidence
        self.calls += 1
        output, error = kwargs["stdout_path"], kwargs["stderr_path"]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"actual output"); error.write_bytes(b"")
        return ProcessEvidence(0, hashlib.sha256(b"actual output").hexdigest(), hashlib.sha256(b"").hexdigest(),
                               capture_error="injected sink failure")

    def test_capture_failure_is_durable_and_exact_retry_does_not_execute_twice(self):
        with mock.patch("pipeline_v2.runner.run_process_tree", side_effect=self.process):
            first, receipts = self.controller._execute_checks(self.state, self.root, self.active, "same-action")
            second, _ = self.controller._execute_checks(self.state, self.root, self.active, "same-action")
        self.assertEqual(1, self.calls)
        self.assertEqual(first, second)
        self.assertEqual(125, first[0]["returncode"])
        self.assertEqual(0, first[0]["process_returncode"])
        self.assertFalse(receipts)
        record_id = first[0]["execution_evidence"].partition(":")[2]
        self.assertFalse(read(self.root, "feature", record_id)["record"]["capture_complete"])

    def test_metadata_failure_retains_started_action_and_readable_recovery(self):
        with mock.patch("pipeline_v2.runner.run_process_tree", side_effect=self.process), \
             mock.patch("pipeline_v2.execution_evidence.native_record", side_effect=OSError("metadata disk error")):
            with self.assertRaises(OSError):
                self.controller._execute_checks(self.state, self.root, self.active, "same-action")
            with self.assertRaisesRegex(PipelineError, "already started"):
                self.controller._execute_checks(self.state, self.root, self.active, "same-action")
        self.assertEqual(1, self.calls)
        path = next((self.root / ".agentic-pipeline/Workflows/feature/Evidence").glob("*/attempt.json"))
        result = read(self.root, "feature", path.parent.name, allow_incomplete=True)
        self.assertEqual("started", result["attempt"]["status"])
        self.assertFalse(result["semantic_credit"])

    def test_saved_attempt_cannot_rebind_old_success_to_changed_executable(self):
        from dataclasses import replace
        executable = self.root / "test-tool.exe"
        executable.write_bytes(b"tool version one"); executable.chmod(0o755)
        argv = [str(executable)]
        self.active["commands"] = [argv]
        self.state["slices"][0]["planned_commands"] = [argv]
        recipe = {"id": "scenario", "argv": argv, "kind": "deterministic", "timeout_seconds": 10,
                  "independent": False, "input_paths": []}
        self.state["execution"] = {"receipts": {}, "verification": {"slices": {"SLICE-1": [recipe]}}}
        with mock.patch("pipeline_v2.runner.run_process_tree", side_effect=lambda *a, **k: replace(self.process(*a, **k), capture_error=None)):
            first, receipts = self.controller._execute_checks(self.state, self.root, self.active, "same-action")
            self.assertEqual(1, len(receipts))
            record_id = first[0]["execution_evidence"].partition(":")[2]
            attempt = read_json(_directory(self.root, "feature", record_id) / "attempt.json")
            self.assertEqual(next(iter(receipts)), attempt["request"]["reusable_binding"])
            executable.write_bytes(b"tool version two")
            with self.assertRaisesRegex(PipelineError, "different inputs"):
                self.controller._execute_checks(self.state, self.root, self.active, "same-action")
        self.assertEqual(1, self.calls)


if __name__ == "__main__":
    unittest.main()
