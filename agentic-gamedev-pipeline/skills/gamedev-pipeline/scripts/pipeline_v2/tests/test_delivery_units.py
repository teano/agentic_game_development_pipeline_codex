from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from pipeline_v2.delivery import export_assignment, read_delivery, read_delivery_unit
from pipeline_v2.cli import _render_assignment_unit
from pipeline_v2.model import PipelineError, canonical_bytes


class DeliveryUnitTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.workflow = ".agentic-pipeline/Workflows/test"
        self.definition = {"identities": [{"id": "QA-1", "assertions": [
            {"id": "ASSERT-1", "text": "Инвариант 🌍\r\n" * 2000,
             "methods": [{"id": "METHOD-1", "observation": "exact result\r\n"}]}]}],
            "a/b~c": {"": "Escaped child 🌍\r\n"}}
        finding = {"id": "F/~1", "text": "Original finding 🌍\r\n" * 100,
                   "conditions": [{"id": "C/~1", "text": "Original condition"},
                                  {"id": "C2", "text": "Second condition"}]}
        conflicting = {**deepcopy(finding), "text": "A distinct same-ID finding"}
        self.view = {"run_id": "run", "feature": "test", "workflow_path": self.workflow,
            "generation": 4, "next_action": {"kind": "command", "command": "complete"},
            "active_assignment": {"id": "A-1", "role": "engineer", "worker_id": "W-1",
                "access": {"read": ["src/**"], "write": ["src/**"]}, "output_path": "a.json",
                "context": {
                    "qa_contract": {"status": "bound", "binding": {
                        "contract_digest": "a" * 64, "authority_digest": "b" * 64, "slice_id": "SL-1"},
                        "definition": self.definition},
                    "verification_failure": {"phase": "review", "candidate": {"tree": "c" * 40},
                        "review_target": {"id": "T-1"}, "controller_failure": {"reason": "test failure"},
                        "findings": [deepcopy(finding), conflicting, {"id": "NEW", "text": "Unique finding"}]},
                    "convergence": {"open": {finding["id"]: finding, "OLD": {"id": "OLD", "text": "Old unresolved"}},
                        "condition_status": {finding["id"]: {
                            "C/~1": {"status": "unresolved", "evidence": finding["text"]},
                            "C2": {"status": "resolved", "evidence": "Unique later evidence"}}}},
                    "literal": {"$delivery_ref": "This is ordinary assignment data"}}}}

    def packet(self, version):
        return json.loads((self.root / self.workflow / "Delivery" / f"{version}.json").read_bytes())

    def save(self, value):
        payload = canonical_bytes(value)
        version = hashlib.sha256(payload).hexdigest()
        directory = self.root / self.workflow / "Delivery"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{version}.json").write_bytes(payload)
        return version

    def export(self, baseline=None):
        return export_assignment(self.root, self.view, baseline)

    def unit(self, version, pointer="/assignment", view="value"):
        return read_delivery_unit(self.root, self.workflow, version, pointer, view)

    def test_exact_lossless_assignment_and_local_dedup_preserve_all_original_material(self):
        original = deepcopy(self.view)
        exported = self.export()
        packet = self.packet(exported["packet_digest"])
        references = packet["references"]
        failure = "/assignment/context/verification_failure/findings/0"
        evidence = "/assignment/context/convergence/condition_status/F~1~01/C~1~01/evidence"
        self.assertEqual({"kind": "local", "pointer": "/assignment/context/convergence/open/F~1~01"}, references[failure])
        self.assertEqual({"kind": "local", "pointer": "/assignment/context/convergence/open/F~1~01/text"}, references[evidence])
        self.assertEqual(3, len(references))
        self.assertEqual("A distinct same-ID finding", packet["assignment"]["context"]["verification_failure"]["findings"][1]["text"])
        self.assertEqual(original["active_assignment"], self.unit(exported["packet_digest"])["value"])
        self.assertEqual(original, self.view)
        self.assertEqual(original["active_assignment"]["context"]["verification_failure"]["findings"][0],
                         self.unit(exported["packet_digest"], failure)["value"])
        self.assertEqual(original["active_assignment"]["context"]["convergence"]["open"]["F/~1"]["text"],
                         self.unit(exported["packet_digest"], evidence)["value"])

    def test_invariant_bound_qa_is_one_resource_and_deltas_show_changes_and_removals(self):
        first = self.export()
        resource = first["working_set"]["required_resources"][0]
        definition_path = "/assignment/context/qa_contract/definition"
        self.assertNotEqual("a" * 64, resource["digest"])
        self.assertEqual(self.definition, self.packet(resource["digest"])["definition"])
        self.assertNotIn("Инвариант", json.dumps(self.packet(first["packet_digest"]), ensure_ascii=False))
        self.view["generation"] += 1
        context = self.view["active_assignment"]["context"]
        context["verification_failure"]["findings"].pop()
        context["convergence"]["condition_status"]["F/~1"]["C/~1"]["evidence"] = "Changed meaningful evidence"
        second = self.export(first["packet_digest"])
        delta = self.packet(second["response_digest"])
        self.assertEqual("delta", second["mode"])
        self.assertTrue(any(op["op"] == "remove" for op in delta["patch"]))
        self.assertTrue(any(op["op"] == "remove" and op["path"].startswith("/references/") for op in delta["patch"]))
        encoded = json.dumps(delta, ensure_ascii=False)
        self.assertNotIn("Инвариант", encoded)
        self.assertNotIn(definition_path, encoded)
        self.assertIn("Changed meaningful evidence", encoded)
        self.assertEqual(self.view["active_assignment"], self.unit(second["response_digest"])["value"])
        self.assertEqual(resource["digest"], second["working_set"]["required_resources"][0]["digest"])
        resource_files = [item for item in (self.root / self.workflow / "Delivery").glob("*.json")
                          if json.loads(item.read_bytes()).get("format") == "pipeline-qa-definition-v1"]
        self.assertEqual(1, len(resource_files))
        context["qa_contract"]["definition"]["identities"][0]["assertions"][0]["text"] = "Changed QA obligation"
        third = self.export(second["packet_digest"])
        self.assertNotEqual(resource["digest"], third["working_set"]["required_resources"][0]["digest"])
        self.assertEqual("Changed QA obligation", self.unit(third["packet_digest"],
            definition_path + "/identities/0/assertions/0/text")["value"])

    def test_semantic_index_and_value_are_decoded_with_exact_pointers_and_provenance(self):
        exported = self.export()
        version = exported["packet_digest"]
        root_index = read_delivery_unit(self.root, self.workflow, version)
        self.assertEqual("index", root_index["view"])
        self.assertEqual("/assignment", root_index["pointer"])
        self.assertNotIn("value", root_index)
        self.assertNotIn("Original finding", json.dumps(root_index))
        assertion_path = "/assignment/context/qa_contract/definition/identities/0/assertions"
        index = self.unit(version, assertion_path, "index")
        self.assertEqual([{"selector": "0", "pointer": assertion_path + "/0", "type": "object", "id": "ASSERT-1"}], index["children"])
        self.assertNotIn("Инвариант", json.dumps(index, ensure_ascii=False))
        value = self.unit(version, assertion_path + "/0")
        self.assertIsInstance(value["value"], dict)
        self.assertNotIn("text", value)
        self.assertTrue(value["unit_complete"])
        self.assertFalse(value["delivery_complete"])
        self.assertEqual("resource", value["provenance"][0]["kind"])
        self.assertEqual("Escaped child 🌍\r\n", self.unit(version,
            "/assignment/context/qa_contract/definition/a~1b~0c/")["value"])
        self.assertEqual("exact result\r\n", self.unit(version, assertion_path + "/0/methods/0/observation")["value"])
        for bad in ("not-a-pointer", "/assignment/~2", assertion_path + "/00", assertion_path + "/٠"):
            with self.subTest(pointer=bad), self.assertRaises(PipelineError):
                self.unit(version, bad)

    def test_dispatch_has_generated_reader_argv_without_bodies(self):
        exported = self.export()
        reader = exported["dispatch"]["reader"]
        self.assertEqual("assignment-read", reader["command"])
        self.assertEqual("bootstrap", reader["default_view"])
        self.assertEqual(["--view", "bootstrap"], reader["bootstrap_argv"][-2:])
        self.assertEqual(["--view", "work"], reader["work_argv"][-2:])
        self.assertEqual(["--view", "work-index"], reader["work_index_argv"][-2:])
        self.assertEqual(["--view", "unit", "--pointer"], reader["unit_argv_prefix"][-3:])
        self.assertIn("recursive machine/debug-only", reader["value_usage"])
        self.assertIn(exported["packet_digest"], reader["index_argv"])
        self.assertEqual(["--view", "index"], reader["index_argv"][-2:])
        self.assertEqual(["--view", "value", "--pointer"], reader["value_argv_prefix"][-3:])
        self.assertNotIn("Инвариант", json.dumps(exported, ensure_ascii=False))
        self.assertNotIn("Original finding", json.dumps(exported))

    def test_structural_units_include_direct_scalars_but_not_nested_bodies(self):
        task = "Exact task 🌍\r\n" * 1000
        assignment = self.view["active_assignment"]
        assignment["task"] = task
        assignment["context"]["mixed/~"] = [None, False, 0, "Привет 🌍\r\n", {"id": "NESTED", "body": ["keep nested"]}, []]
        version = self.export()["packet_digest"]
        root = self.unit(version, view="unit")
        rows = {item["selector"]: item for item in root["children"]}
        for key in ("id", "worker_id", "role", "output_path", "task"):
            self.assertEqual(assignment[key], rows[key]["value"])
        self.assertEqual("object", rows["context"]["type"])
        self.assertNotIn("value", rows["context"])
        self.assertFalse(root["unit_complete"])
        self.assertFalse(root["delivery_complete"])
        context = self.unit(version, "/assignment/context", "unit")
        self.assertNotIn("Инвариант", json.dumps(context, ensure_ascii=False))
        self.assertNotIn("Original finding", json.dumps(context))
        mixed = self.unit(version, "/assignment/context/mixed~1~0", "unit")
        self.assertEqual([str(index) for index in range(6)], [item["selector"] for item in mixed["children"]])
        self.assertEqual([None, False, 0, "Привет 🌍\r\n"], [item["value"] for item in mixed["children"][:4]])
        self.assertEqual("NESTED", mixed["children"][4]["id"])
        self.assertTrue(all("value" not in item for item in mixed["children"][4:]))
        self.assertNotIn("keep nested", json.dumps(mixed))
        empty = self.unit(version, mixed["children"][5]["pointer"], "unit")
        self.assertEqual([], empty["children"])
        self.assertTrue(empty["unit_complete"])
        leaf = self.unit(version, mixed["children"][3]["pointer"], "unit")
        self.assertEqual("Привет 🌍\r\n", leaf["value"])
        self.assertTrue(leaf["unit_complete"])
        self.assertEqual("Привет 🌍\r\n", _render_assignment_unit(leaf).split("\n", 1)[1])
        literal = self.unit(version, "/assignment/context/literal", "unit")
        self.assertEqual("This is ordinary assignment data", literal["children"][0]["value"])
        self.assertTrue(literal["unit_complete"])

    def test_traversing_structural_units_reconstructs_exact_assignment_and_changed_delta(self):
        def rebuild(version, pointer="/assignment"):
            unit = self.unit(version, pointer, "unit")
            self.assertFalse(unit["delivery_complete"])
            if "value" in unit:
                return unit["value"]
            self.assertEqual(all("value" in child for child in unit["children"]), unit["unit_complete"])
            values = [(child["selector"], child["value"] if "value" in child else rebuild(version, child["pointer"]))
                      for child in unit["children"]]
            return [value for _, value in values] if unit["type"] == "array" else dict(values)

        first = self.export()
        self.assertEqual(self.view["active_assignment"], rebuild(first["packet_digest"]))
        self.view["generation"] += 1
        context = self.view["active_assignment"]["context"]
        context["verification_failure"]["findings"].pop()
        context["convergence"]["condition_status"]["F/~1"]["C/~1"]["evidence"] = "New evidence 🌍\r\n"
        second = self.export(first["packet_digest"])
        self.assertEqual(self.view["active_assignment"], rebuild(second["response_digest"]))
        self.assertEqual(self.view["active_assignment"], self.unit(second["packet_digest"], view="value")["value"])

    def test_structural_reference_children_expose_provenance_without_replaying_bodies(self):
        exported = self.export()
        version = exported["packet_digest"]
        condition = "/assignment/context/convergence/condition_status/F~1~01/C~1~01"
        rows = {item["selector"]: item for item in self.unit(version, condition, "unit")["children"]}
        self.assertEqual("unresolved", rows["status"]["value"])
        self.assertNotIn("value", rows["evidence"])
        self.assertEqual("string", rows["evidence"]["type"])
        self.assertEqual("local", rows["evidence"]["reference"]["kind"])
        value = self.unit(version, rows["evidence"]["pointer"], "unit")
        self.assertEqual(self.view["active_assignment"]["context"]["convergence"]["open"]["F/~1"]["text"], value["value"])
        self.assertEqual("local", value["provenance"][0]["kind"])
        qa = self.unit(version, "/assignment/context/qa_contract", "unit")
        definition = next(child for child in qa["children"] if child["selector"] == "definition")
        self.assertNotIn("value", definition)
        self.assertEqual(exported["working_set"]["required_resources"][0]["digest"], definition["reference"]["digest"])
        selected = self.unit(version, definition["pointer"], "unit")
        self.assertNotIn("Инвариант", json.dumps(selected, ensure_ascii=False))
        self.assertEqual(definition["reference"]["digest"], selected["provenance"][0]["digest"])
        resource = self.root / self.workflow / "Delivery" / f"{definition['reference']['digest']}.json"
        resource.unlink()
        with self.assertRaises(PipelineError):
            self.unit(version, "/assignment/context/qa_contract", "unit")

    def test_missing_corrupt_resource_and_cross_root_or_binding_substitution_fail(self):
        exported = self.export()
        version = exported["packet_digest"]
        source = "/assignment/context/qa_contract/definition"
        resource_digest = exported["working_set"]["required_resources"][0]["digest"]
        resource_path = self.root / self.workflow / "Delivery" / f"{resource_digest}.json"
        data = resource_path.read_bytes()
        resource_path.unlink()
        with self.assertRaises(PipelineError):
            self.unit(version, source)
        resource_path.write_bytes(data + b" ")
        with self.assertRaisesRegex(PipelineError, "digest does not match"):
            self.unit(version, source)
        resource_path.write_bytes(data)
        packet = self.packet(version)
        packet["references"][source]["digest"] = ["invalid"]
        with self.assertRaisesRegex(PipelineError, "invalid QA resource"):
            self.unit(self.save(packet), source)
        for key, value in (("run_id", "other"), ("feature", "other"), ("project_root", str(self.root / "other")),
                           ("binding", {"contract_digest": "c" * 64})):
            with self.subTest(field=key):
                resource = json.loads(data)
                resource[key] = value
                packet = self.packet(version)
                packet["references"][source]["digest"] = self.save(resource)
                with self.assertRaisesRegex(PipelineError, "binding does not match"):
                    self.unit(self.save(packet), source)
        packet = self.packet(version)
        packet["project_root"] = str(self.root / "other")
        with self.assertRaisesRegex(PipelineError, "different project_root"):
            self.unit(self.save(packet))

    def test_local_reference_cycles_and_tampered_registration_fail(self):
        exported = self.export()
        packet = self.packet(exported["packet_digest"])
        first = "/assignment/context/verification_failure/findings/0"
        second = "/assignment/context/convergence/condition_status/F~1~01/C~1~01/evidence"
        packet["references"][first]["pointer"] = second
        packet["references"][second]["pointer"] = first
        with self.assertRaisesRegex(PipelineError, "cycle"):
            self.unit(self.save(packet), first)
        packet = self.packet(exported["packet_digest"])
        packet["assignment"]["context"]["verification_failure"]["findings"][0] = {"id": "mutated"}
        with self.assertRaisesRegex(PipelineError, "registered assignment slot"):
            self.unit(self.save(packet))
        packet = self.packet(exported["packet_digest"])
        packet["references"][first]["pointer"] = "/assignment/context"
        with self.assertRaisesRegex(PipelineError, "cycle"):
            self.unit(self.save(packet), first)
        packet = self.packet(exported["packet_digest"])
        packet["references"][first]["pointer"] = None
        with self.assertRaises(PipelineError):
            self.unit(self.save(packet), first)

    def test_delta_tampering_delta_as_baseline_and_foreign_owner_are_rejected(self):
        first = self.export()
        self.view["generation"] += 1
        second = self.export(first["packet_digest"])
        delta = self.packet(second["response_digest"])
        delta["patch"].append({"op": "replace", "path": "/assignment/id", "value": "wrong"})
        with self.assertRaisesRegex(PipelineError, "packet digest"):
            self.unit(self.save(delta))
        with self.assertRaisesRegex(PipelineError, "same run, role and worker"):
            self.export(second["response_digest"])
        for key in ("worker_id", "role"):
            packet = self.packet(first["packet_digest"])
            packet["assignment"][key] = "other"
            delta = self.packet(second["response_digest"])
            delta["baseline_digest"] = self.save(packet)
            with self.assertRaisesRegex(PipelineError, "same run, role and worker"):
                self.unit(self.save(delta))

    def test_legacy_raw_pages_and_explicit_full_fallback_preserve_original_bytes(self):
        legacy = {"format": "pipeline-assignment-v1", "run_id": "run", "feature": "test", "generation": 3,
                  "assignment": deepcopy(self.view["active_assignment"]), "selected_inputs": []}
        version = self.save(legacy)
        path = self.root / self.workflow / "Delivery" / f"{version}.json"
        original = path.read_bytes()
        pages, offset = [], 0
        while True:
            page = read_delivery(self.root, self.workflow, version, offset, 16384)
            pages.append(page["text"])
            if page["complete"]:
                break
            offset = page["next_offset"]
        self.assertEqual(original, "".join(pages).encode("utf-8"))
        exported = self.export(version)
        self.assertEqual("full", exported["mode"])
        self.assertEqual("legacy_packet_requires_full_v2", exported["fallback"]["reason"])
        self.assertEqual(original, path.read_bytes())
        self.assertEqual(self.view["active_assignment"], self.unit(exported["packet_digest"])["value"])


if __name__ == "__main__":
    unittest.main()
