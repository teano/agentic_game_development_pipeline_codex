"""Independent protocol-simplification probes.

Pure cases reuse the existing real draft/schema/provenance fixture with mocked
native checkout acquisition. Conditional native/CLI coverage runs only when
the caller supplies the collectively frozen runtime digest.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import unittest

from pipeline_v2.delivery import read_file
from pipeline_v2.model import qa_contract_context
from pipeline_v2.qa_contract import contract_digest, expand_slice_contract, source_reference
from pipeline_v2.qa_draft import assemble, load
from pipeline_v2.tests import test_qa_working_draft as draft_fixtures
from pipeline_v2.tests.test_qa_decision_draft import decision


class ProtocolSimplificationAdversarialTests(unittest.TestCase):
    def setUp(self):
        self.f = draft_fixtures.QAWorkingDraftTests("runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.controller = self.f.controller

    def binding(self):
        return load(self.f.state, self.f.root, self.f.binding)[0]["binding"]

    def request(self, identifiers=("enter", "reset", "core"), revision=0):
        rows = []
        for identifier in identifiers:
            row = self.f.row(identifier)
            row.pop("method_id")
            row.pop("environment")
            row["evidence"][0].pop("ref")
            rows.append(row)
        return {"binding": deepcopy(self.binding()), "expected_revision": revision,
                "shared": {"method_id": "observed-action", "environment": "Observed fixture session",
                           "evidence": [{"type": "observation", "ref": "fixture:observation"}]},
                "assessments": rows}

    def record(self, request):
        return self.controller.qa_record("qa-current", request)

    def unchanged_rejection(self, request):
        draft = self.controller.qa_draft("qa-current")
        path = Path(draft["working_path"])
        before = path.read_bytes()
        submitted = deepcopy(request)
        result = self.record(request)
        self.assertFalse(result["valid"], result)
        self.assertTrue(result["errors"])
        self.assertEqual(before, path.read_bytes(), "A rejected group must be an exact disk no-op")
        self.assertEqual(submitted, request, "Normalization must not mutate caller input")
        return result

    def test_shared_request_matches_explicit_canonical_rows_and_retains_decisions_on_replay(self):
        entry = decision()
        saved = self.record({"expected_revision": 0, "assessments": [], "technical_decisions": [entry]})
        self.assertTrue(saved["valid"])
        compact = self.request(revision=1)
        submitted = deepcopy(compact)
        result = self.record(compact)
        self.assertTrue(result["valid"], result.get("errors"))
        path = Path(result["working_path"])
        before_replay = path.read_bytes()
        replay = self.record(compact)
        self.assertTrue(replay["valid"])
        self.assertEqual(before_replay, path.read_bytes())
        self.assertEqual(submitted, compact)
        draft, definition, _, _ = load(self.f.state, self.f.root, self.f.binding)
        terminal = assemble(draft, definition)
        self.assertEqual([entry], terminal["technical_decisions"])
        for identifier in ("enter", "reset", "core"):
            expected = self.f.row(identifier)
            expected["method_id"] = "observed-action"
            expected["outcome"] = "pass"
            expected["assessment"]["expected"] = "The approved transition completes."
            self.assertEqual(expected, draft["assessments"][identifier])
        conflicting = deepcopy(compact)
        conflicting["assessments"][0]["assessment"]["observed"] = "A different later observation"
        self.unchanged_rejection(conflicting)

    def test_one_bad_shared_group_row_cannot_partially_replace_previous_work(self):
        first = self.record({"expected_revision": 0, "assessments": [self.f.row()]})
        self.assertTrue(first["valid"])
        request = self.request(("reset", "core"), revision=1)
        request["assessments"][1]["evidence"][0]["observation"] = None
        result = self.unchanged_rejection(request)
        self.assertEqual((1, 1, 2), (result["revision"], result["assessed"], result["pending"]))

    def test_shared_metadata_never_supplies_semantic_observations_or_comparison(self):
        for key, value in (("outcome", "pass"), ("assessment", {"observed": "green", "comparison": "matches"}),
                           ("observation", "all tests green")):
            with self.subTest(key=key):
                request = self.request(("enter",))
                request["shared"][key] = value
                self.unchanged_rejection(request)
        request = self.request(("enter",))
        request["shared"]["evidence"][0]["observation"] = "all tests green"
        self.unchanged_rejection(request)
        for field in ("observed", "comparison"):
            request = self.request(("enter",))
            request["assessments"][0]["assessment"][field] = None
            self.unchanged_rejection(request)

    def test_shared_metadata_requires_every_exact_current_binding_component(self):
        request = self.request(("enter",))
        missing = deepcopy(request)
        del missing["binding"]
        self.assertEqual("/binding", self.unchanged_rejection(missing)["errors"][0]["path"])
        for key in request["binding"]:
            with self.subTest(key=key):
                changed = deepcopy(request)
                if isinstance(changed["binding"][key], dict):
                    changed["binding"][key] = {**changed["binding"][key], "contract_digest": "d" * 64}
                else:
                    changed["binding"][key] = "foreign-" + str(changed["binding"][key])
                self.assertEqual("/binding", self.unchanged_rejection(changed)["errors"][0]["path"])

    def test_explicit_row_defaults_must_agree_and_never_mask_an_unknown_method(self):
        for key, value in (("environment", "another environment"), ("method_id", "not-approved")):
            with self.subTest(key=key):
                request = self.request(("enter",))
                request["assessments"][0][key] = value
                self.unchanged_rejection(request)
        valid = self.request(("enter",))
        valid["assessments"][0].update(method_id="METHOD-fe82d465e8433451", environment="Observed fixture session")
        self.assertTrue(self.record(valid)["valid"], "An explicit equivalent approved selector is compatible")

    def test_ambiguous_shared_origins_require_one_whole_explicit_origin(self):
        request = self.request(("enter",))
        source = self.f.source()
        origin = {"type": "observation", "ref": source_reference(source), "source": source}
        request["shared"]["evidence"] = [origin, {"type": "observation", "ref": "fixture:other"}]
        self.unchanged_rejection(request)
        partial = deepcopy(request)
        partial["assessments"][0]["evidence"][0]["ref"] = origin["ref"]
        self.unchanged_rejection(partial)
        explicit = deepcopy(request)
        explicit["assessments"][0]["evidence"][0].update(ref=origin["ref"], source=deepcopy(source))
        self.assertTrue(self.record(explicit)["valid"])

    def test_single_shared_origin_cannot_stitch_explicit_ref_and_source(self):
        request = self.request(("enter",))
        source = self.f.source()
        request["shared"]["evidence"] = [{"type": "observation", "ref": source_reference(source), "source": source}]
        for explicit in ({"ref": "execution-evidence:unrelated"}, {"source": source}, {"ref": source_reference(source)}):
            with self.subTest(explicit=explicit):
                changed = deepcopy(request)
                changed["assessments"][0]["evidence"][0].update(explicit)
                self.unchanged_rejection(changed)
        self.assertTrue(self.record(request)["valid"])

    def test_shared_source_still_checks_live_bytes_before_any_group_write(self):
        request = self.request(("enter", "reset"))
        source = self.f.source()
        request["shared"]["evidence"] = [{"type": "observation", "ref": source_reference(source), "source": source}]
        original = (self.f.root / "game.txt").read_bytes()
        (self.f.root / "game.txt").write_bytes(b"state = different\n")
        self.unchanged_rejection(request)
        (self.f.root / "game.txt").write_bytes(original)
        self.assertTrue(self.record(request)["valid"])

    def test_nonexecution_row_does_not_inherit_an_executed_shared_method(self):
        request = self.request(("enter",))
        external = self.f.external("reset")
        external.pop("environment")
        external["method_id"] = None
        request["assessments"].append(external)
        result = self.record(request)
        self.assertTrue(result["valid"], result.get("errors"))
        row = self.controller.qa_read("qa-current", assertion_id="reset")["assessments"][0]
        self.assertEqual(("not_run", None, "insufficient"), (row["outcome"], row["method_id"], row["assessment"]["comparison"]))
        self.assertFalse(self.controller.qa_finalize("qa-current", result["revision"])["valid"], "The remaining pending row is not a verdict")

    def test_prepare_preserves_all_alternatives_and_different_same_id_method_bodies(self):
        definition = self.f.definition
        original = deepcopy(definition["method_definitions"]["METHOD-fe82d465e8433451"])
        alternative = {**deepcopy(original), "id": "other-observation", "description": "A separately approved complete alternate procedure."}
        changed_same_id = {**deepcopy(original), "description": "A different required procedure for this other criterion."}
        definition["identities"][0]["assertions"][0]["methods"] = [deepcopy(original), alternative]
        definition["identities"][0]["assertions"][1]["methods"] = [changed_same_id]
        definition["identities"][0]["assertions"][1]["depends_on"] = ["core"]
        definition["identities"][0]["assertions"][1]["applicability"] = {"kind": "conditional", "condition": "A reset-capable session exists.", "evidence_types": ["source-observation"]}
        self.f.state["execution"]["qa_contract_binding"]["contract_digest"] = contract_digest(self.f.contract)
        self.f.state["active_assignment"]["capsule"]["context"]["qa_contract"] = qa_contract_context(self.f.state)
        result = self.controller.qa_prepare("qa-current", ["enter", "reset"])
        # A selected view intentionally retains references to dependencies
        # outside the selection; it is not an independently valid whole slice.
        selected = deepcopy(result["obligations"])
        for identity in selected["identities"]:
            for row in identity["assertions"]:
                row["methods"] = [deepcopy(selected["method_definitions"][item["ref"]]) for item in row["methods"]]
        expected = expand_slice_contract(definition)
        self.assertEqual(expected["identities"][0], selected["identities"][0])
        self.assertEqual(3, len(result["obligations"]["method_definitions"]))
        self.assertIsNone(result["prepared_methods"][0]["method_id"], "Multiple alternatives cannot be silently selected")
        self.assertEqual("observed-action", result["prepared_methods"][1]["method_id"])
        self.assertFalse(result["semantic_credit"])
        self.assertFalse(result["tests_executed"])
        self.assertFalse(Path(result["working_path"]).exists())
        for row in result["record_request"]["assessments"]:
            self.assertIsNone(row["assessment"]["observed"])
            self.assertIsNone(row["assessment"]["comparison"])
            self.assertNotIn("outcome", row)

    def test_generated_source_origin_is_exact_and_contains_no_observation(self):
        view = {"active_assignment": self.f.state["active_assignment"], "next_action": {"command": "complete"}}
        result = read_file(self.f.root, view, "game.txt", lines=(1, 1))
        self.assertEqual({"ref": source_reference(result["source"]), "source": result["source"]}, result["evidence_origin"])
        self.assertNotIn("observation", result["evidence_origin"])
        self.assertNotIn("outcome", result["evidence_origin"])


@unittest.skipUnless(os.environ.get("PROTOCOL_NATIVE_FROZEN_DIGEST"), "Requires collectively frozen production runtime")
class ProtocolSimplificationNativeTests(unittest.TestCase):
    def setUp(self):
        from pipeline_v2.checkout import pipeline_runtime_digest
        from pipeline_v2.tests.test_core import PipelineV2CoreTests
        self.expected = os.environ["PROTOCOL_NATIVE_FROZEN_DIGEST"]
        self.assertEqual(self.expected, pipeline_runtime_digest())
        self.h = PipelineV2CoreTests("runTest")
        self.h.setUp()
        self.addCleanup(self.h.tearDown)

    def bootstrap(self):
        from pipeline_v2.delivery import export_assignment
        exported = export_assignment(self.h.root, self.h.controller.status())
        dispatch = exported["dispatch"]
        argv = dispatch["reader"]["bootstrap_argv"]
        self.assertIn("--assemble", argv)
        process = subprocess.run(argv, cwd=self.h.root, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"), capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(0, process.returncode, process.stderr)
        value = json.loads(process.stdout)["value"]
        self.assertEqual(dispatch["assignment_id"], value["assignment"]["id"])
        self.assertEqual(dispatch["role"], value["assignment"]["role"])
        return dispatch, value["assignment"]

    def issue(self):
        action = self.h.controller.status()["next_action"]
        return self.h.controller.next(command_id=action["command_id"], expected_generation=action["expected_generation"])

    def complete(self, artifact):
        self.h._write_artifact(artifact)
        action = self.h.controller.status()["next_action"]
        return self.h.controller.complete(command_id=action["command_id"], expected_generation=action["expected_generation"])

    def test_conditional_plan_slice_docs_readers_execute_and_docs_still_requires_fresh_review(self):
        from pipeline_v2.checkout import pipeline_runtime_digest
        for phase, role in (("plan", "planner"), ("slice", "slicer")):
            self.assertEqual(phase, self.issue()["phase"])
            dispatch, assignment = self.bootstrap()
            self.assertEqual(role, dispatch["role"])
            self.assertEqual("Runtime Plan and Slice", dispatch["role_instructions"]["section"])
            self.assertEqual([], assignment["access"]["write"])
            self.assertIn("current_slice", assignment["context"])
            self.complete({"outcome": "pass", "summary": "Native test fixture confirms unchanged approved scope."})
            self.h._accept("protocol-" + phase)
        self.h._engineer("protocol-engineer", "implemented fixture\n")
        self.h._accept("protocol-engineer")
        self.h._review_pass("protocol-review")
        self.h._qa_pass("protocol-qa")
        self.assertEqual("docs", self.issue()["phase"])
        dispatch, assignment = self.bootstrap()
        self.assertEqual("documentation_finisher", dispatch["role"])
        path = "docs/RUN-TEST-verification.md"
        self.assertEqual([path], assignment["access"]["write"])
        destination = self.h.root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("Verified fixture documentation.\n", encoding="utf-8")
        self.complete({"outcome": "pass", "summary": "Native fixture writes only its exact governed documentation."})
        accepted = self.h._accept("protocol-docs")
        self.assertEqual("review", accepted["phase"])
        fresh = self.issue()["active_assignment"]
        self.assertEqual("review", fresh["phase"])
        self.assertIn(path, fresh["access"]["read"])
        self.assertEqual(self.expected, pipeline_runtime_digest())


if __name__ == "__main__":
    unittest.main()
