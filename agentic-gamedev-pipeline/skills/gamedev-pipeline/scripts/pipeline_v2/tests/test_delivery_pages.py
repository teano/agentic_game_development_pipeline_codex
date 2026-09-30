"""Lossless transport regressions: bound startup, exact work selectors and commit recovery."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline_v2.cli import _check_delivery, _render_assignment_unit, parser
from pipeline_v2.delivery import read_delivery_unit
from pipeline_v2.finding_contract import required_condition_roster
from pipeline_v2.model import PipelineError
from pipeline_v2.tests import test_delivery_work


def assemble(pages):
    """A consumer must reject missing/clipped/reordered fragments before decoding."""
    expected, fragments = 0, []
    first = pages[0]
    for page in pages:
        assert page["offset"] == expected
        assert page["content_digest"] == first["content_digest"]
        assert page["version"] == first["version"]
        assert len(page["text"]) == page["end_offset"] - page["offset"]
        assert hashlib.sha256(page["text"].encode("utf-8")).hexdigest() == page["page_digest"]
        expected = page["end_offset"]
        fragments.append(page["text"])
    assert pages[-1]["complete"] and pages[-1]["continuation"] is None
    text = "".join(fragments)
    assert expected == first["total_characters"] == len(text)
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == first["content_digest"]
    return json.loads(text)


class DeliveryPageTests(unittest.TestCase):
    def setUp(self):
        self.h = test_delivery_work.DeliveryWorkTests("runTest")
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        assignment = self.h.view["active_assignment"]
        assignment["artifact_schema"] = {"required": ["outcome", "finding_resolutions"],
                                         "row": {"finding_id": "exact", "condition_id": "exact"}}
        assignment["checks"] = [["python", "verify.py"]]
        assignment["context"]["current_slice"] = {"id": "S1", "read_paths": ["src/**"],
            "allowed_paths": ["src/**"], "planned_commands": [["python", "verify.py"]]}

    def pages(self, version, view, **kwargs):
        result, token = [], None
        while True:
            page = read_delivery_unit(self.h.root, self.h.workflow, version, view=view,
                                      continuation=token, **kwargs)
            result.append(page)
            token = page["continuation"]
            if token is None:
                return result

    def expand_retained(self, body):
        body = deepcopy(body)
        for ref in body.pop("retained_originals", []):
            value = read_delivery_unit(self.h.root, self.h.workflow, ref["packet_digest"], ref["pointer"], "value")["value"]
            if "omit_fields" in ref:
                value = {key: item for key, item in value.items() if key not in ref["omit_fields"]}
            parent = body
            parts = ref["source_pointer"][1:].split("/")
            for part in parts[:-1]:
                key = part.replace("~1", "/").replace("~0", "~")
                parent = parent[int(key)] if isinstance(parent, list) else parent[key]
            parent[parts[-1]] = value
        return self.h.expand_displayed_evidence(body)

    def test_startup_groups_complete_scope_schema_checks_slice_and_addresses_every_deferred_body(self):
        exported = self.h.export()
        body = assemble(self.pages(exported["packet_digest"], "bootstrap"))
        original = self.h.view["active_assignment"]
        for key, value in original.items():
            if key != "context":
                self.assertEqual(value, body["assignment"][key])
        self.assertEqual(original["context"]["current_slice"], body["assignment"]["context"]["current_slice"])
        self.assertEqual(original["context"]["qa_contract"]["binding"], body["assignment"]["context"]["qa_contract"]["binding"])
        self.assertNotIn("UNRELATED-QA-BODY", json.dumps(body))
        pointers = {item["pointer"] for item in body["sources"]}
        for key in ("convergence", "required_finding_conditions", "technical_decisions"):
            self.assertIn("/assignment/context/" + key, pointers)
        self.assertIn("/assignment/context/qa_contract/definition", pointers)
        self.assertEqual("work-index", body["required_work"]["view"])

    def test_exact_index_and_selected_parts_reconstruct_legacy_work_for_every_role(self):
        for role, phase in (("engineer", "engineering"), ("reviewer", "review"), ("documentation_finisher", "docs")):
            assignment = self.h.view["active_assignment"]
            assignment["role"] = role
            assignment["context"]["required_finding_conditions"] = required_condition_roster(self.h.convergence, phase)
            version = self.h.export()["packet_digest"]
            pages = self.pages(version, "work-index", limit=301)
            index = assemble(pages)
            self.assertEqual(assignment["context"]["required_finding_conditions"], index["roster"])
            self.assertEqual(len(index["roster"]), pages[0]["required_condition_count"])
            self.assertNotIn("Latest precise rejection", "".join(page["text"] for page in pages))
            restored = []
            for finding in dict.fromkeys(row["finding_id"] for row in index["roster"]):
                selected = self.pages(version, "work-item", finding_id=finding, limit=257)
                restored.extend(self.expand_retained(assemble(selected))["findings"])
                self.assertTrue(all(not page["work_complete"] and not page["delivery_complete"] for page in selected))
            expected = self.h.read(version)["value"]
            self.assertEqual(expected, {"assignment": index["assignment"], "findings": restored})
            if role == "engineer":
                with self.assertRaisesRegex(PipelineError, "role-specific"):
                    self.pages(version, "work-item", finding_id="F/~", condition_id="C1")
            if role == "reviewer":
                resolved = assemble(self.pages(version, "work-item", finding_id="F/~", condition_id="C1"))
                self.assertEqual("resolved", resolved["findings"][0]["conditions"][0]["latest_independent_result"]["status"])

    def test_single_huge_condition_and_shared_context_survive_unicode_boundaries_and_missing_parts_fail(self):
        context = self.h.view["active_assignment"]["context"]
        long_text = 'Single exact condition 🌍\r\n quote " slash / tilde ~\\' * 1900
        context["convergence"]["open"]["F/~"]["conditions"][1]["text"] = long_text
        context["convergence"]["condition_status"]["F/~"]["C/~"]["evidence"] = context["convergence"]["open"]["F/~"]["text"]
        version = self.h.export()["packet_digest"]
        pages = self.pages(version, "work-item", finding_id="F/~", condition_id="C/~", limit=8192)
        self.assertGreater(len(pages), 10)
        body = self.expand_retained(assemble(pages))
        self.assertEqual(long_text, body["findings"][0]["conditions"][0]["original_condition"]["text"])
        self.assertEqual(context["convergence"]["open"]["F/~"]["text"], body["findings"][0]["conditions"][0]["latest_independent_result"]["evidence"])
        for damaged in (pages[1:], pages[:-1], pages[:1] + pages[2:], [*pages[:1], *pages[:1], *pages[1:]]):
            with self.assertRaises(AssertionError):
                assemble(damaged)
        clipped = deepcopy(pages)
        clipped[2]["text"] = clipped[2]["text"][:-1]
        with self.assertRaises(AssertionError):
            assemble(clipped)

    def test_continuations_reject_wrong_selection_digest_baseline_corruption_and_can_resize_retry(self):
        version = self.h.export()["packet_digest"]
        first = read_delivery_unit(self.h.root, self.h.workflow, version, view="work-item", finding_id="F/~", limit=180)
        for change in ({"view": "work-index"}, {"finding_id": "F-OLD"}, {"condition_id": "C/~"}, {"baseline": version}):
            options = {"view": "work-item", "finding_id": "F/~", "continuation": first["continuation"]}
            options.update(change)
            if options["view"] == "work-index":
                options.pop("finding_id")
            with self.assertRaises(PipelineError):
                read_delivery_unit(self.h.root, self.h.workflow, version, **options)
        for invalid in ("", "garbage", "e30=", "bnVsbA=="):
            with self.assertRaises(PipelineError):
                read_delivery_unit(self.h.root, self.h.workflow, version, view="work-item", finding_id="F/~", continuation=invalid)
        continued = read_delivery_unit(self.h.root, self.h.workflow, version, view="work-item", finding_id="F/~", continuation=first["continuation"], limit=73)
        self.assertEqual(first["end_offset"], continued["offset"])
        self.assertEqual(73, len(continued["text"]))
        restarted = read_delivery_unit(self.h.root, self.h.workflow, version, view="work-item", finding_id="F/~", limit=73)
        self.assertEqual(0, restarted["offset"], "No token starts at zero; it never guesses continuation")
        self.h.view["generation"] += 1
        changed = self.h.export()["packet_digest"]
        with self.assertRaises(PipelineError):
            read_delivery_unit(self.h.root, self.h.workflow, changed, view="work-item", finding_id="F/~", continuation=first["continuation"])
        target = self.h.root / self.h.workflow / "Delivery" / f"{version}.json"
        target.write_bytes(target.read_bytes() + b" ")
        with self.assertRaisesRegex(PipelineError, "digest does not match"):
            self.pages(version, "work-index")

    def test_retained_baseline_omits_only_exact_originals_and_lost_context_returns_full(self):
        original = self.h.export()["packet_digest"]
        self.h.view["generation"] += 1
        active = self.h.view["active_assignment"]
        active["id"] = "A-2"
        active["context"]["convergence"]["condition_status"]["F/~"]["C/~"]["evidence"] = "Current independent rejection, never omitted"
        current = self.h.export()["packet_digest"]
        full = assemble(self.pages(current, "work-item", finding_id="F/~"))
        retained = assemble(self.pages(current, "work-item", finding_id="F/~", baseline=original))
        self.assertEqual(self.expand_retained(full), self.expand_retained(retained))
        self.assertTrue(retained["retained_originals"])
        self.assertIn("Current independent rejection, never omitted", json.dumps(retained))
        self.assertNotIn("retained_originals", full)
        with self.assertRaisesRegex(PipelineError, "newer"):
            self.pages(original, "work-item", finding_id="F/~", baseline=current)
        active["worker_id"] = "NEW-OWNER"
        foreign = self.h.export()["packet_digest"]
        with self.assertRaisesRegex(PipelineError, "same run"):
            self.pages(foreign, "work-item", finding_id="F/~", baseline=original)
        active["worker_id"] = "W-1"
        active["context"]["qa_contract"]["binding"]["contract_digest"] = "b" * 64
        rebound = self.h.export()["packet_digest"]
        with self.assertRaisesRegex(PipelineError, "binding changed"):
            self.pages(rebound, "work-item", finding_id="F/~", baseline=original)
        # Missing full baseline fails instead of treating digest possession as retained meaning.
        (self.h.root / self.h.workflow / "Delivery" / f"{original}.json").unlink()
        with self.assertRaises(PipelineError):
            self.pages(current, "work-item", finding_id="F/~", baseline=original)

    def test_section_pages_resolve_escaped_pointer_and_cli_human_fragment_is_not_double_encoded(self):
        self.h.view["active_assignment"]["context"]["a/b~c"] = {"": "Exact unicode 🌍\r\n" * 100}
        version = self.h.export()["packet_digest"]
        pages = self.pages(version, "section", pointer="/assignment/context/a~1b~0c/", limit=257)
        self.assertEqual("Exact unicode 🌍\r\n" * 100, assemble(pages))
        header, body = _render_assignment_unit(pages[0]).split("\n", 1)
        self.assertEqual(pages[0]["text"], body)
        self.assertEqual(pages[0]["page_digest"], json.loads(header)["page_digest"])
        with self.assertRaises(PipelineError):
            self.pages(version, "section", pointer="/assignment/context/a~2b")

    def test_section_empty_pointer_selects_packet_root_and_continuation_keeps_that_selection(self):
        version = self.h.export()["packet_digest"]
        root_pages = self.pages(version, "section", pointer="", limit=701)
        root = assemble(root_pages)
        expected = read_delivery_unit(self.h.root, self.h.workflow, version, "", "value")["value"]
        self.assertEqual(expected, root)
        self.assertEqual("pipeline-assignment-v2", root["format"])
        self.assertEqual(self.h.view["generation"], root["generation"])
        self.assertTrue(all(page["pointer"] == "" for page in root_pages))
        default = assemble(self.pages(version, "section"))
        self.assertEqual(root["assignment"], default, "Omitted pointer still defaults to the assignment")
        self.assertGreater(len(root_pages), 1)
        for pointer in (None, "/assignment"):
            with self.subTest(pointer=pointer), self.assertRaisesRegex(PipelineError, "continuation does not match"):
                read_delivery_unit(self.h.root, self.h.workflow, version, pointer, "section",
                                   continuation=root_pages[0]["continuation"])

    def test_changed_originals_and_removed_required_rows_are_never_reused_from_baseline(self):
        previous = self.h.export()["packet_digest"]
        self.h.view["generation"] += 1
        context = self.h.view["active_assignment"]["context"]
        convergence = context["convergence"]
        convergence["open"]["F/~"]["conditions"][1]["text"] = "Changed original text must be delivered"
        convergence["condition_status"]["F/~"]["C3"]["status"] = "resolved"
        context["required_finding_conditions"] = required_condition_roster(convergence, "engineering")
        current = self.h.export(baseline=previous)
        retained = assemble(self.pages(current["packet_digest"], "work-item", finding_id="F/~", baseline=previous))
        rows = retained["findings"][0]["conditions"]
        self.assertEqual(["C/~"], [row["condition_id"] for row in rows])
        self.assertEqual("Changed original text must be delivered", rows[0]["original_condition"]["text"])
        full = assemble(self.pages(current["response_digest"], "work-item", finding_id="F/~"))
        self.assertEqual(self.expand_retained(full), self.expand_retained(retained))
        self.h.view["generation"] -= 1
        with self.assertRaisesRegex(PipelineError, "newer"):
            self.h.export(baseline=current["packet_digest"])


class CommittedDeliveryTests(unittest.TestCase):
    def test_export_failure_retains_cursor_and_success_avoids_inline_read_render(self):
        args = parser().parse_args(["--root", str(Path.cwd()), "--feature", "test", "check", "--id", "CHECK-1",
            "--expected-generation", "8", "--assignment-id", "A-1", "--quiescence", "stopped", "--with-delivery"])
        state = {"generation": 9, "history": [{"id": "CHECK-1", "generation": 9}]}
        view = {"generation": 9, "workflow_path": ".agentic-pipeline/Workflows/test", "next_action": {"command": "complete", "expected_generation": 9, "command_id": "NEXT-9"}}
        exported = {"packet_digest": "a" * 64, "generation": 9, "assignment_id": "A-1", "worker_id": "W-1", "mode": "full"}
        with mock.patch("pipeline_v2.cli.status_view", return_value=view), \
             mock.patch("pipeline_v2.cli.export_assignment", side_effect=RuntimeError("transport broke")):
            result = _check_delivery(Path.cwd(), state, args)
        self.assertTrue(result["committed"])
        self.assertEqual(9, result["committed_generation"])
        self.assertEqual(view["next_action"], result["next_action"])
        self.assertEqual("failed", result["transport"]["status"])
        self.assertEqual("assignment-export", result["recovery"]["export_argv"][-1])
        with mock.patch("pipeline_v2.cli.status_view", return_value=view), \
             mock.patch("pipeline_v2.cli.export_assignment", return_value=exported), \
             mock.patch("pipeline_v2.cli.read_delivery_unit") as read, \
             mock.patch("pipeline_v2.cli._render_assignment_unit") as render:
            delivered = _check_delivery(Path.cwd(), state, args)
            read.assert_not_called()
            render.assert_not_called()
        self.assertEqual("delivered", delivered["transport"]["status"])
        self.assertFalse(delivered["transport"]["content_included"])
        self.assertNotIn("check_result", delivered)
        self.assertIn("check-context", delivered["recovery"]["read_argv"])
        self.assertIn("text", delivered["recovery"]["read_argv"])
        self.assertIn("exec_command", delivered["recovery"]["read"])
        state["generation"] = 11
        with mock.patch("pipeline_v2.cli.status_view", return_value={**view, "generation": 11}), \
             mock.patch("pipeline_v2.cli.export_assignment") as export:
            result = _check_delivery(Path.cwd(), state, args)
            export.assert_not_called()
        self.assertEqual("cursor_advanced", result["transport"]["status"])
        self.assertEqual(9, result["committed_generation"])
        self.assertEqual(11, result["generation"])


if __name__ == "__main__":
    unittest.main()
