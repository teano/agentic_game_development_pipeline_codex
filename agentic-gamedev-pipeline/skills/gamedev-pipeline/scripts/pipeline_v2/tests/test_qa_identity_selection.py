"""Exact identity navigation; pure tests and separately released native coverage."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import io
import json
from pathlib import Path
import unittest
from unittest import mock

from pipeline_v2.cli import main, parser, run
from pipeline_v2.delivery import assemble_delivery_pages, read_delivery_unit
from pipeline_v2.model import PipelineError
from pipeline_v2.qa_contract import resolve_assertion_selection, selected_contract, QAContractError
from pipeline_v2.tests import test_qa_public_io as selection_fixtures
from pipeline_v2.tests import test_qa_working_draft as draft_fixtures


class QAIdentitySelectionTests(unittest.TestCase):
    def setUp(self):
        self.selection = selection_fixtures.QASelectionTests("runTest")
        self.selection.setUp(); self.addCleanup(self.selection.doCleanups)
        self.draft = draft_fixtures.QAWorkingDraftTests("runTest")
        self.draft.setUp(); self.addCleanup(self.draft.doCleanups)

    def read(self, **selection):
        h = self.selection.h
        return assemble_delivery_pages(lambda token: read_delivery_unit(h.root, h.workflow, self.selection.version,
            view="qa-assertion", continuation=token, limit=503, **selection))

    def test_identity_read_equals_complete_explicit_subset_without_mutating_sources(self):
        original = deepcopy(self.selection.definition)
        by_identity = self.read(identity_id="GROUP")
        explicit = self.read(assertion_ids=["A1", "A2"])
        self.assertEqual(explicit["value"], by_identity["value"])
        self.assertEqual("GROUP", by_identity["identity_id"])
        self.assertNotIn("assertion_ids", by_identity)
        self.assertTrue(by_identity["selection_complete"])
        self.assertFalse(by_identity["delivery_complete"])
        self.assertEqual(original, self.selection.definition)
        self.assertFalse((self.selection.h.root / self.selection.h.workflow / "ReadOutputs").exists())

    def test_selection_modes_bind_continuations_and_reject_unknown_duplicate_mixed_inputs(self):
        h = self.selection.h
        first = read_delivery_unit(h.root, h.workflow, self.selection.version, view="qa-assertion", identity_id="GROUP", limit=503)
        self.assertIsNotNone(first["continuation"])
        with self.assertRaises(PipelineError):
            read_delivery_unit(h.root, h.workflow, self.selection.version, view="qa-assertion", assertion_ids=["A1", "A2"],
                               continuation=first["continuation"], limit=503)
        for selection in ({"identity_id": "unknown"}, {"identity_id": ""}, {"identity_id": ["GROUP", "GROUP"]},
                          {"identity_id": "GROUP", "assertion_ids": ["A1"]}, {"assertion_ids": ["A1", "A1"]},
                          {"assertion_ids": ["unknown"]}, {}):
            with self.subTest(selection=selection), self.assertRaises(PipelineError):
                self.read(**selection)
        with self.assertRaises(PipelineError):
            read_delivery_unit(h.root, h.workflow, self.selection.version, view="qa-index", identity_id="GROUP")

    def test_cli_refuses_repeated_identity_and_mixed_modes_before_reading(self):
        prefix = ["--root", str(self.draft.root), "--feature", "feature"]
        for command in (["assignment-read", "--digest", "a" * 64, "--view", "qa-assertion"],
                        ["qa-prepare", "--assignment-id", "qa-current"]):
            for selection in (["--identity-id", "GROUP", "--identity-id", "GROUP"],
                              ["--identity-id", "GROUP", "--assertion-id", "A1"],
                              ["--assertion-id", "A1", "--identity-id", "GROUP"]):
                with self.subTest(command=command, selection=selection), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as rejected:
                    parser().parse_args([*prefix, *command, *selection])
                self.assertEqual(2, rejected.exception.code)

    def test_prepare_uses_identical_binding_request_and_restoration_for_either_selection(self):
        identity = self.draft.definition["identities"][0]
        ids = [row["id"] for row in identity["assertions"]]
        state_before = deepcopy(self.draft.state)
        selected = self.draft.controller.qa_prepare("qa-current", identity_id=identity["id"])
        explicit = self.draft.controller.qa_prepare("qa-current", ids)
        self.assertEqual(explicit, selected)
        self.assertEqual(ids, [row["id"] for row in selected["record_request"]["assessments"]])
        self.assertTrue(all(row["assessment"]["observed"] is None for row in selected["record_request"]["assessments"]))
        self.assertFalse(selected["semantic_credit"])
        self.assertEqual(state_before, self.draft.state)
        self.assertFalse(Path(selected["working_path"]).exists())
        request = {"expected_revision": 0, "assessments": [self.draft.row(ids[0])]}
        self.assertTrue(self.draft.controller.qa_record("qa-current", request)["valid"])
        self.assertEqual(self.draft.controller.qa_prepare("qa-current", ids),
                         self.draft.controller.qa_prepare("qa-current", identity_id=identity["id"]))

    def test_invalid_prepare_does_not_create_or_change_authoring_files(self):
        controller = self.draft.controller
        for selection in ({"identity_id": "missing"}, {"identity_id": ""}, {"identity_id": ["CORE", "CORE"]},
                          {"identity_id": self.draft.definition["identities"][0]["id"], "assertion_ids": ["enter"]},
                          {"assertion_ids": ["enter", "enter"]}):
            with self.subTest(selection=selection), self.assertRaises(PipelineError):
                controller.qa_prepare("qa-current", **selection)
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch("pipeline_v2.cli.Controller", return_value=controller), redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--root", str(self.draft.root), "--feature", "feature", "qa-prepare", "--assignment-id", "qa-current", "--identity-id", "missing"])
        self.assertEqual(2, code)
        self.assertIn("identity", stderr.getvalue())
        self.assertFalse((self.draft.store.path.parent / "ReadOutputs").exists())

    def test_full_inventory_is_once_and_all_identity_bodies_are_losslessly_equivalent(self):
        method = deepcopy(self.selection.method)
        identities = [{"id": f"IDENTITY-{i}", "source": "approved/plan.md#group",
            "assertions": [{"id": f"ASSERT-{i}-{j}", "expected": f"Exact mandatory condition {i}/{j} Ω\r\n",
                "methods": [{"ref": "shared"}], "applicability": {"kind": "always", "condition": "always", "evidence_types": []},
                "depends_on": []} for j in range(16 if i < 2 else 17)]} for i in range(17)]
        definition = {"identities": identities, "method_definitions": {"shared": method}}
        h = self.selection.h
        h.view["active_assignment"]["context"]["qa_contract"]["definition"] = definition
        inventory = [{"id": item["id"], "source": item["source"], "assertion_ids": [row["id"] for row in item["assertions"]]} for item in identities]
        self.assertEqual(287, sum(len(row["assertion_ids"]) for row in inventory))
        for role, operation in (("engineer", "read"), ("reviewer", "read"), ("qa", "prepare")):
            h.view["active_assignment"]["role"] = role
            version = h.export()["packet_digest"]
            result = assemble_delivery_pages(lambda token: read_delivery_unit(h.root, h.workflow, version, view="qa-index", continuation=token))["value"]
            self.assertEqual(inventory, [{key: row[key] for key in ("id", "source", "assertion_ids")} for row in result["identities"]])
            self.assertEqual(287, result["assertion_count"])
            for row in result["identities"]:
                self.assertEqual({"id", "source", "assertion_ids", operation}, set(row))
                command = row[operation]["exec_command"]["cmd"]
                self.assertIn("--identity-id", command)
                self.assertNotIn("--assertion-id", command)
                self.assertFalse(any(identifier in command for identifier in row["assertion_ids"]))
                selected_ids = resolve_assertion_selection(definition, identity_id=row["id"])
                self.assertEqual(row["assertion_ids"], selected_ids)
                self.assertEqual(selected_contract(definition, row["assertion_ids"]), selected_contract(definition, selected_ids))


class QAIdentityNativeTests(unittest.TestCase):
    """Run only after the production/documentation writers are frozen."""
    def test_identity_prepare_uses_current_native_guard_and_same_request_as_explicit_ids(self):
        from pipeline_v2.tests import test_acceptance_integration as fixtures
        fixture = fixtures.AcceptanceIntegrationTests("runTest"); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        fixture.bind(); fixture.h._reach_engineering(); fixture.issue()
        fixture.submit({"outcome": "pass", "summary": "Current native fixture."})
        fixture.h._accept("engineering"); fixture.issue()
        fixture.submit({"outcome": "pass", "findings": []})
        fixture.h._accept("review"); active = fixture.issue()["active_assignment"]
        controller = fixture.h.controller
        definition = fixture.contract["slices"]["SLICE-1"]["identities"][0]
        ids = [row["id"] for row in definition["assertions"]]
        before = fixture.h.store.path.read_bytes()
        prepared = controller.qa_prepare(active["id"], identity_id=definition["id"])
        self.assertEqual(prepared, controller.qa_prepare(active["id"], ids))
        self.assertEqual(before, fixture.h.store.path.read_bytes())
        self.assertFalse(Path(prepared["working_path"]).exists())
        response = run(parser().parse_args(["--root", str(fixture.h.root), "--feature", fixture.h.feature,
            "qa-prepare", "--assignment-id", active["id"], "--identity-id", definition["id"], "--format", "json", "--assemble"]))
        request_path = Path(response["value"]["saved_record_request"]["path"])
        self.assertEqual(prepared["record_request"], json.loads(request_path.read_text(encoding="utf-8")))
        self.assertEqual(prepared["obligations"], response["value"]["obligations"])
        self.assertFalse(response["value"]["semantic_credit"])
        self.assertEqual(before, fixture.h.store.path.read_bytes())
        for kwargs in ({"identity_id": "unknown"}, {"identity_id": definition["id"], "assertion_ids": ids}):
            with self.assertRaises(PipelineError):
                controller.qa_prepare(active["id"], **kwargs)
        with self.assertRaises(PipelineError):
            controller.qa_prepare("different-assignment", identity_id=definition["id"])
        self.assertEqual(before, fixture.h.store.path.read_bytes())


if __name__ == "__main__":
    unittest.main()
