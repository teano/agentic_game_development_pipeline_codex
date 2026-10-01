from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock
from unittest.mock import Mock

SCRIPTS = Path(__file__).resolve().parents[2]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from pipeline_v2.cli import main, parser, run
from pipeline_v2.checkout import candidate_tree_oid
from pipeline_v2.delivery import director_brief, execute_step, export_assignment, json_patch, read_delivery, read_delivery_unit, read_file
from pipeline_v2.model import ROLES, PipelineError, canonical_bytes, digest
from pipeline_v2.process_tree import ProcessEvidence


def apply_patch(document, patch):
    """Independent small RFC 6902 interpreter for reconstruction assertions."""
    result = deepcopy(document)
    for operation in patch:
        if operation["path"] == "":
            result = deepcopy(operation["value"])
            continue
        parts = [part.replace("~1", "/").replace("~0", "~") for part in operation["path"][1:].split("/")]
        parent = result
        for part in parts[:-1]:
            parent = parent[int(part)] if isinstance(parent, list) else parent[part]
        key = int(parts[-1]) if isinstance(parent, list) else parts[-1]
        if operation["op"] == "remove":
            del parent[key]
        elif operation["op"] == "add" and isinstance(parent, list):
            parent.insert(key, deepcopy(operation["value"]))
        else:
            parent[key] = deepcopy(operation["value"])
    return result


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.workflow = ".agentic-pipeline/Workflows/test"
        self.view = {"run_id": "run", "feature": "test", "workflow_path": self.workflow, "generation": 4,
            "next_action": {"kind": "command", "command": "complete"},
            "active_assignment": {"id": "A-1", "role": "engineer", "worker_id": "W-1",
                "access": {"read": ["src/**"], "write": ["src/**"]}, "output_path": "a.json",
                "context": {"technical_decisions": [{"id": "T-1", "text": "unchanged " * 600},
                    {"id": "T-2", "text": "Привет 🌍\r\n" * 1000}]}}}
        (self.root / "src").mkdir()
        (self.root / "src" / "a.txt").write_bytes("Привет 🌍\r\n".encode("utf-8"))

    def receive(self, version, limit=127):
        offset = 0
        pieces = []
        while True:
            page = read_delivery(self.root, self.workflow, version, offset, limit)
            self.assertLessEqual(len(page["text"]), limit)
            self.assertEqual(offset, page["offset"])
            pieces.append(page["text"])
            if page["complete"]:
                self.assertIsNone(page["next_offset"])
                break
            offset = page["next_offset"]
        text = "".join(pieces)
        self.assertEqual(version, hashlib.sha256(text.encode("utf-8")).hexdigest())
        return json.loads(text)

    def test_unicode_full_delta_reconstructs_exact_assignment_without_unchanged_text(self):
        full = export_assignment(self.root, self.view, inputs=["src/a.txt"])
        before = self.receive(full["response_digest"])
        self.assertFalse(full["delivery_complete"])
        self.assertEqual(self.view["active_assignment"]["worker_id"], full["worker_id"])
        self.assertEqual("full", full["dispatch"]["input"]["mode"])
        self.assertNotIn("baseline_digest", full["dispatch"]["input"])
        self.assertEqual(self.view["active_assignment"], before["assignment"])
        self.assertEqual(1, len(before["selected_inputs"]))
        self.view["generation"] += 1
        self.view["active_assignment"]["id"] = "A-2"
        self.view["active_assignment"]["context"]["technical_decisions"][1]["text"] = "Fixed completely."
        result = export_assignment(self.root, self.view, full["packet_digest"], ["src/a.txt"])
        delta = self.receive(result["response_digest"])
        self.assertEqual(self.view["active_assignment"]["worker_id"], result["worker_id"])
        self.assertEqual("A-2", result["dispatch"]["assignment_id"])
        self.assertEqual(full["packet_digest"], result["dispatch"]["input"]["baseline_digest"])
        self.assertEqual(result["response_digest"], result["dispatch"]["input"]["digest"])
        self.assertEqual(result["packet_digest"], result["dispatch"]["input"]["packet_digest"])
        self.assertNotIn("unchanged", json.dumps(delta))
        rebuilt = apply_patch(before, delta["patch"])
        self.assertEqual(result["packet_digest"], hashlib.sha256(canonical_bytes(rebuilt)).hexdigest())
        self.assertEqual(self.view["active_assignment"], rebuilt["assignment"])
        identical = export_assignment(self.root, self.view, result["packet_digest"], ["src/a.txt"])
        self.assertEqual([], self.receive(identical["response_digest"])["patch"])

    def test_role_instruction_locators_match_existing_sources_without_expanding_assignment(self):
        expected = {
            "engineer": "gamedev-engineer/SKILL.md",
            "reviewer": "gamedev-review/SKILL.md",
            "qa": "gamedev-qa/SKILL.md",
            "documentation_finisher": "gamedev-documentation-finisher/SKILL.md",
            "planner": "gamedev-pipeline/references/pipeline-protocol.md",
            "slicer": "gamedev-pipeline/references/pipeline-protocol.md",
        }
        self.assertEqual(set(ROLES.values()), set(expected))
        skills = SCRIPTS.parents[1]
        for role, relative in expected.items():
            with self.subTest(role=role):
                view = deepcopy(self.view)
                view["active_assignment"]["role"] = role
                original = deepcopy(view)
                exported = export_assignment(self.root, view)
                locator = exported["role_instructions"]
                self.assertEqual(role, locator["role"])
                self.assertEqual((skills / relative).resolve(), Path(locator["path"]))
                self.assertTrue(Path(locator["path"]).is_file())
                self.assertEqual(hashlib.sha256(Path(locator["path"]).read_bytes()).hexdigest(), locator["version"])
                if role in {"planner", "slicer"}:
                    self.assertEqual("Runtime Plan and Slice", locator["section"])
                    self.assertIn("## " + locator["section"], Path(locator["path"]).read_text(encoding="utf-8"))
                else:
                    self.assertNotIn("section", locator)
                self.assertNotEqual(skills / "gamedev-pipeline/SKILL.md", Path(locator["path"]))
                packet = self.receive(exported["packet_digest"])
                self.assertEqual(locator, packet["role_instructions"])
                self.assertEqual(locator, director_brief(view)["active_assignment"]["role_instructions"])
                self.assertEqual(view["active_assignment"], packet["assignment"])
                self.assertEqual(original, view)
                self.assertEqual({"role", "path", "version", "section"} if role in {"planner", "slicer"}
                                 else {"role", "path", "version"}, set(locator))

    def test_generated_normal_readers_execute_without_appended_transport_arguments(self):
        for role in ROLES.values():
            view = deepcopy(self.view)
            view["active_assignment"]["role"] = role
            dispatch = export_assignment(self.root, view)["dispatch"]
            self.assertIn("--present", dispatch["reader"]["bootstrap_argv"])
            # This pure packet fixture has no live controller. Its legacy read
            # remains supported; current issued handles are exercised natively
            # by SavedPresentationNativeTests.
            startup = run(parser().parse_args(["--assemble" if item == "--present" else item for item in dispatch["reader"]["bootstrap_argv"][2:]]))
            self.assertTrue(startup["selection_complete"])
            self.assertEqual(role, startup["value"]["assignment"]["role"])
            instruction = run(parser().parse_args(dispatch["role_instructions"]["read_argv"][2:]))
            locator = dispatch["role_instructions"]
            self.assertEqual(locator["version"], parser().parse_args(locator["read_argv"][2:]).version)
            self.assertEqual(locator["version"], instruction["original_selection"]["source"]["sha256"])
            self.assertEqual(locator["path"], instruction["original_selection"]["source"]["path"])
            self.assertTrue(instruction["selection_complete"])
            self.assertFalse(instruction["delivery_complete"])
            self.assertNotIn("evidence_origin", instruction)
            if role in {"planner", "slicer"}:
                self.assertTrue(instruction["text"].startswith("## Runtime Plan and Slice"))
            with mock.patch("pipeline_v2.cli.Controller") as controller:
                controller.return_value.read_status.return_value = view
                source = run(parser().parse_args(["--assemble" if item == "--present" else item for item in dispatch["reader"]["source_argv_prefix"][2:]] + ["src/a.txt"]))
            self.assertEqual("Привет 🌍\r\n", source["value"])
            self.assertEqual(source["source"], source["evidence_origin"]["source"])
            self.assertTrue(source["evidence_origin"]["ref"].startswith("candidate-source:src/a.txt@"))

    def test_generated_startup_refuses_changed_source_even_outside_selected_role_section(self):
        for role in ("engineer", "planner"):
            with self.subTest(role=role):
                view = deepcopy(self.view)
                view["active_assignment"]["role"] = role
                locator = export_assignment(self.root, view)["dispatch"]["role_instructions"]
                target = self.root / f"{role}-instructions.md"
                payload = Path(locator["path"]).read_bytes()
                target.write_bytes(payload)
                with mock.patch("pipeline_v2.delivery._instruction_path", return_value=target):
                    args = parser().parse_args(locator["read_argv"][2:])
                    original = run(args)
                    self.assertEqual(locator["version"], original["original_selection"]["source"]["sha256"])
                    target.write_bytes(payload + b"\n## Unselected newer section\nChanged source bytes.\n")
                    with self.assertRaisesRegex(PipelineError, "selected input changed"):
                        run(args)
                    args.version = hashlib.sha256(target.read_bytes()).hexdigest()
                    current = run(args)
                if role == "planner":
                    self.assertEqual(original["text"], current["text"])
                self.assertNotEqual(original["original_selection"]["source"]["sha256"], current["original_selection"]["source"]["sha256"])
                self.assertFalse(current["delivery_complete"])
                self.assertNotIn("evidence_origin", current)

    def test_unversioned_v2_role_locator_is_readable_and_upgrades_by_exact_delta(self):
        exported = export_assignment(self.root, self.view)
        legacy = self.receive(exported["packet_digest"])
        legacy["role_instructions"].pop("version")
        payload = canonical_bytes(legacy)
        version = hashlib.sha256(payload).hexdigest()
        (self.root / self.workflow / "Delivery" / f"{version}.json").write_bytes(payload)
        startup = run(parser().parse_args(["--root", str(self.root), "--feature", self.view["feature"],
            "assignment-read", "--digest", version, "--view", "bootstrap", "--assemble"]))
        self.assertEqual(legacy["role_instructions"], startup["value"]["role_instructions"])
        self.assertFalse(startup["delivery_complete"])
        current = export_assignment(self.root, self.view, baseline=version)
        delta = self.receive(current["response_digest"])
        self.assertEqual("delta", current["mode"])
        self.assertEqual(self.receive(current["packet_digest"]), apply_patch(legacy, delta["patch"]))
        self.assertEqual(legacy["assignment"], self.receive(current["packet_digest"])["assignment"])
        self.assertEqual(current["role_instructions"]["version"],
                         parser().parse_args(current["dispatch"]["role_instructions"]["read_argv"][2:]).version)

    def test_full_and_delta_keep_exact_output_right_separate_from_product_scope(self):
        from pipeline_v2.model import artifact_schema
        for phase, role in (("engineering", "engineer"), ("review", "reviewer"), ("qa", "qa")):
            with self.subTest(role=role):
                view = deepcopy(self.view)
                assignment = view["active_assignment"]
                assignment["role"] = role
                assignment["access"]["write"] = ["src/**"] if role == "engineer" else []
                assignment["artifact_schema"] = artifact_schema(phase, role)
                # An older view without root still binds the trusted export root,
                # never the process cwd or the output's containing directory.
                self.assertNotIn("project_root", view)
                assignment["output_path"] = f"{self.workflow}/Outputs/{role}-1.json"
                access = deepcopy(assignment["access"])
                schema = deepcopy(assignment["artifact_schema"])
                baseline = None
                previous = None
                for mode in ("full", "delta"):
                    original = deepcopy(view)
                    exported = export_assignment(self.root, view, baseline=baseline)
                    transport = self.receive(exported["response_digest"])
                    packet = transport if mode == "full" else apply_patch(previous, transport["patch"])
                    descriptor = exported["dispatch"]
                    self.assertEqual(mode, descriptor["input"]["mode"])
                    self.assertEqual(original, view)
                    self.assertEqual(assignment, packet["assignment"])
                    self.assertEqual(access, packet["assignment"]["access"])
                    self.assertEqual(schema, packet["assignment"]["artifact_schema"])
                    self.assertEqual(exported["packet_digest"], hashlib.sha256(canonical_bytes(packet)).hexdigest())
                    self.assertEqual("issued_exact_terminal_artifact", descriptor["output"]["write_authority"])
                    self.assertEqual("requires_separate_bounded_grant", descriptor["controller_mutation_authority"])
                    self.assertNotIn("native_mutation_authority", descriptor)
                    self.assertEqual("terminal_artifact_or_required_control_pause", descriptor["stop_boundary"])
                    output = self.root / assignment["output_path"]
                    self.assertEqual(str(output), descriptor["output"]["path"])
                    self.assertEqual(assignment["output_path"], descriptor["output"]["relative_path"])
                    self.assertFalse(output.exists(), "export describes output authority; it does not write the artifact")
                    self.assertEqual(access, json.loads(read_delivery(
                        self.root, self.workflow, descriptor["scope"]["packet_digest"],
                        pointer=descriptor["scope"]["pointer"])["text"]))
                    previous, baseline = packet, exported["packet_digest"]
                    view["generation"] += 1
                    assignment["id"] = "A-2"
                    assignment["output_path"] = f"{self.workflow}/Outputs/{role}-2.json"

    def test_draft_brief_locates_current_phase_only_and_idle_boundaries_have_no_locator(self):
        view = deepcopy(self.view)
        draft = view["active_assignment"]
        draft.pop("role")
        view["active_assignment"] = None
        view["next_action"] = {"kind": "command", "command": "next", "assignment": draft}
        for phase, role in ROLES.items():
            view["phase"] = phase
            brief = director_brief(view)
            self.assertEqual(role, brief["next_action"]["assignment"]["role_instructions"]["role"])
            self.assertNotIn("role_instructions", draft)
        for action in ({"kind": "command", "command": "init"}, {"kind": "command", "command": "accept"},
                       {"kind": "command", "command": "ready"}, {"kind": "controller_decision", "command": "answer"},
                       {"kind": "terminal", "result": "recovery_required"}):
            view["next_action"] = action
            brief = director_brief(view)
            self.assertEqual(action, brief["next_action"])
            self.assertNotIn("role_instructions", json.dumps(brief))

    def test_instruction_locator_resolves_from_relocated_bundle_not_project_or_main_source(self):
        # Load just the transport module from an isolated fixture bundle. This
        # exercises its real __file__ without creating/changing an immutable pin.
        import pipeline_v2.delivery as source
        bundle = self.root / "relocated runtime with spaces"
        module_path = bundle / "skills/gamedev-pipeline/scripts/pipeline_v2/delivery.py"
        module_path.parent.mkdir(parents=True)
        module_path.write_bytes(Path(source.__file__).read_bytes())
        (module_path.parent.parent / "pipeline_state.py").write_bytes((SCRIPTS / "pipeline_state.py").read_bytes())
        for role in ROLES.values():
            locator = source._role_instructions(role)
            relative = Path(locator["path"]).relative_to(SCRIPTS.parents[2])
            target = bundle / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(Path(locator["path"]).read_bytes())
        spec = importlib.util.spec_from_file_location("pipeline_v2.relocated_delivery_fixture", module_path)
        relocated = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(relocated)
        for role in ROLES.values():
            view = deepcopy(self.view)
            view["active_assignment"]["role"] = role
            exported = relocated.export_assignment(self.root, view)
            locator = exported["role_instructions"]
            self.assertTrue(Path(locator["path"]).is_relative_to(bundle))
            self.assertTrue(Path(exported["dispatch"]["launcher_argv"][1]).is_relative_to(bundle))
            self.assertEqual(locator, {key: value for key, value in exported["dispatch"]["role_instructions"].items() if key not in {"read_argv", "exec_command"}})
            self.assertEqual(locator, self.receive(exported["packet_digest"])["role_instructions"])
            self.assertEqual(locator, relocated.director_brief(view)["active_assignment"]["role_instructions"])
        (bundle / "skills/gamedev-engineer/SKILL.md").unlink()
        with self.assertRaisesRegex(PipelineError, "inside the running bundle"):
            relocated.export_assignment(self.root, self.view)

    def test_legacy_delivery_uses_explicit_full_v2_fallback_and_unknown_roles_invent_no_path(self):
        full = export_assignment(self.root, self.view)
        legacy = self.receive(full["packet_digest"])
        legacy.pop("role_instructions")
        legacy.pop("project_root")
        legacy.pop("references")
        legacy["format"] = "pipeline-assignment-v1"
        payload = canonical_bytes(legacy)
        version = hashlib.sha256(payload).hexdigest()
        (self.root / self.workflow / "Delivery" / f"{version}.json").write_bytes(payload)
        exported = export_assignment(self.root, self.view, baseline=version)
        rebuilt = self.receive(exported["response_digest"])
        self.assertEqual("full", exported["mode"])
        self.assertEqual("legacy_packet_requires_full_v2", exported["fallback"]["reason"])
        self.assertEqual("pipeline-assignment-v2", rebuilt["format"])
        self.assertEqual(str(self.root.resolve()), rebuilt["project_root"])
        self.assertNotIn("patch", rebuilt)
        self.assertNotIn("baseline_digest", exported["dispatch"]["input"])
        self.assertEqual(exported["packet_digest"], hashlib.sha256(canonical_bytes(rebuilt)).hexdigest())
        self.assertEqual(legacy["assignment"], rebuilt["assignment"])
        for role in ("director", "../external/SKILL.md", "gamedev-engineering", "unknown"):
            view = deepcopy(self.view)
            view["active_assignment"]["role"] = role
            self.assertNotIn("role_instructions", export_assignment(self.root, view))
            self.assertNotIn("role_instructions", director_brief(view)["active_assignment"])

    def test_export_measures_working_set_and_locates_complete_decisions_without_inlining(self):
        exported = export_assignment(self.root, self.view, inputs=["src/a.txt"])
        measurements = exported["working_set"]
        self.assertEqual(len((self.root / "src/a.txt").read_bytes()), measurements["selected_source_bytes"])
        self.assertEqual(1, measurements["selected_source_count"])
        self.assertIn("excludes conversation", measurements["measurement"])
        index = measurements["technical_decision_index"]
        self.assertEqual(["T-1", "T-2"], [item["id"] for item in index])
        self.assertNotIn("Привет", json.dumps(exported, ensure_ascii=False))
        page = read_delivery(self.root, self.workflow, exported["packet_digest"],
                             limit=16384, pointer=index[0]["pointer"])
        self.assertTrue(page["complete"])
        self.assertEqual(self.view["active_assignment"]["context"]["technical_decisions"][0], json.loads(page["text"]))

    def test_export_locates_only_current_slice_verification_source_with_exact_file_read_range(self):
        current_slice = {"id": "SLICE-1", "allowed_paths": ["src/**"], "planned_commands": [["python", "-c", "pass"]]}
        plan_text = (
            "# Approved plan\r\n\r\n"
            "## Slice SLICE-1\r\n\r\n"
            "### Verification and Exit Criteria\r\n\r\n"
            "Observe board state \U0001f7e2\r\n"
            "Keep this exact CRLF content.\r\n\r\n"
            "### Rollback and Recovery\r\n\r\n"
            "Restore the prior state.\r\n\r\n"
            "## Slice SLICE-2\r\n\r\n"
            "### Verification and Exit Criteria\r\n\r\n"
            "Do not select this slice.\r\n"
        )
        plan_path = self.root / "plan.md"
        plan_path.write_bytes(plan_text.encode("utf-8"))
        version = hashlib.sha256(plan_path.read_bytes()).hexdigest()
        self.view["active_assignment"]["access"] = {"read": ["src/**", "plan.md"], "write": ["src/**"]}
        self.view["active_assignment"]["context"] = {"current_slice": current_slice}
        state_path = self.root / self.workflow / "pipeline-state.json"
        state_path.parent.mkdir(parents=True)
        state_path.write_text(json.dumps({
            "active_assignment": {"id": "A-1", "capsule": {"context": {"current_slice": current_slice}}},
            "authority": {"items": {"plan": {"path": "plan.md", "sha256": version}}},
        }), encoding="utf-8")
        before = deepcopy(self.view["active_assignment"])

        locator = export_assignment(self.root, self.view)["working_set"]["verification_exit_criteria"]

        self.assertEqual({"path": "plan.md", "version": version, "total_characters": len(plan_text)},
                         {key: locator[key] for key in ("path", "version", "total_characters")})
        start = plan_text.index("### Verification and Exit Criteria")
        end = plan_text.index("### Rollback and Recovery")
        self.assertEqual({"heading": "Verification and Exit Criteria", "start_offset": start, "end_offset": end},
                         locator["section"])
        self.assertEqual(before, self.view["active_assignment"])

        offset = start
        received = []
        while offset < end:
            page = read_file(self.root, self.view, "plan.md", version=version, offset=offset,
                             limit=min(13, end - offset))
            received.append(page["text"])
            offset = page["next_offset"]
        self.assertEqual(plan_text[start:end], "".join(received))

    def test_export_keeps_bound_full_plan_source_when_exact_section_is_unavailable(self):
        current_slice = {"id": "SLICE-1", "allowed_paths": ["src/**"], "planned_commands": [["python", "-c", "pass"]]}
        plan_text = "## Slice SLICE-1\r\n\r\n### Coverage Contract\r\n\r\n- required evidence\r\n"
        plan_path = self.root / "plan.md"
        plan_path.write_bytes(plan_text.encode("utf-8"))
        version = hashlib.sha256(plan_path.read_bytes()).hexdigest()
        self.view["active_assignment"]["access"] = {"read": ["src/**", "plan.md"], "write": ["src/**"]}
        self.view["active_assignment"]["context"] = {"current_slice": current_slice}
        state_path = self.root / self.workflow / "pipeline-state.json"
        state_path.parent.mkdir(parents=True)
        state_path.write_text(json.dumps({
            "active_assignment": {"id": "A-1", "capsule": {"context": {"current_slice": current_slice}}},
            "authority": {"items": {"plan": {"path": "plan.md", "sha256": version}}},
        }), encoding="utf-8")

        locator = export_assignment(self.root, self.view)["working_set"]["verification_exit_criteria"]

        self.assertEqual({"path": "plan.md", "version": version, "total_characters": len(plan_text)}, locator)
        page = read_file(self.root, self.view, locator["path"], version=locator["version"])
        self.assertEqual(plan_text, page["text"])
    def test_patch_handles_deletion_appends_types_empty_values_and_escaped_keys(self):
        before = {"a/b": [{"~": 2}, 4, 5], "delete": 0, "type": False}
        after = {"a/b": [{"~": 3}], "add": [1, 2], "type": 0}
        self.assertEqual(after, apply_patch(before, json_patch(before, after)))
        self.assertEqual(before, apply_patch(after, json_patch(after, before)))
        self.assertEqual({"value": 0}, apply_patch({"value": False}, json_patch({"value": False}, {"value": 0})))
        self.assertTrue(json_patch({"value": False}, {"value": 0}))

    def test_section_reader_delivers_whole_requested_value_without_other_fields(self):
        full = export_assignment(self.root, self.view)
        pointer = "/assignment/context/technical_decisions/0"
        page = read_delivery(self.root, self.workflow, full["packet_digest"], pointer=pointer)
        self.assertTrue(page["complete"])
        self.assertEqual(self.view["active_assignment"]["context"]["technical_decisions"][0], json.loads(page["text"]))
        self.assertNotIn("Привет", page["text"])
        self.assertEqual(pointer, page["pointer"])
        for invalid in ("missing", "/missing", "/assignment/context/technical_decisions/-1"):
            with self.assertRaises(PipelineError):
                read_delivery(self.root, self.workflow, full["packet_digest"], pointer=invalid)

    def test_fresh_worker_or_role_cannot_reuse_prior_packet(self):
        full = export_assignment(self.root, self.view)
        for field in ("worker_id", "role"):
            changed = deepcopy(self.view)
            changed["active_assignment"][field] = "different"
            with self.assertRaisesRegex(PipelineError, "same run, role and worker"):
                export_assignment(self.root, changed, full["packet_digest"])

    def test_reader_preserves_crlf_unicode_and_rejects_changed_or_unversioned_continuation(self):
        page = read_file(self.root, self.view, "src/a.txt", limit=8)
        rest = read_file(self.root, self.view, "src/a.txt", version=page["version"], offset=page["next_offset"])
        self.assertEqual("Привет 🌍\r\n", page["text"] + rest["text"])
        with self.assertRaisesRegex(PipelineError, "require the previous page version"):
            read_file(self.root, self.view, "src/a.txt", offset=1)
        (self.root / "src/a.txt").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(PipelineError, "changed"):
            read_file(self.root, self.view, "src/a.txt", version=page["version"], offset=1)
        fresh = read_file(self.root, self.view, "src/a.txt")
        self.assertNotEqual(page["version"], fresh["version"])

    def test_export_rejects_conflicting_project_root_without_widening_access(self):
        view = deepcopy(self.view)
        view["project_root"] = str(self.root / "other-checkout")
        with self.assertRaisesRegex(PipelineError, "controller-bound project_root"):
            export_assignment(self.root, view)
        view["project_root"] = "."
        with self.assertRaisesRegex(PipelineError, "controller-bound project_root"):
            export_assignment(self.root, view)
        full = export_assignment(self.root, self.view)
        foreign = self.receive(full["packet_digest"])
        foreign["project_root"] = str(self.root / "other-checkout")
        payload = canonical_bytes(foreign)
        version = hashlib.sha256(payload).hexdigest()
        (self.root / self.workflow / "Delivery" / f"{version}.json").write_bytes(payload)
        with self.assertRaisesRegex(PipelineError, "this project_root"):
            export_assignment(self.root, self.view, baseline=version)

    def test_read_scope_selection_path_and_corrupt_snapshot_guards(self):
        with self.assertRaises(PipelineError):
            read_file(self.root, self.view, "../escape.txt")
        with self.assertRaisesRegex(PipelineError, "outside"):
            export_assignment(self.root, self.view, inputs=["private.txt"])
        with self.assertRaisesRegex(PipelineError, "outside"):
            read_file(self.root, self.view, "private.txt")
        full = export_assignment(self.root, self.view)
        (self.root / full["path"]).write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(PipelineError, "digest does not match"):
            read_delivery(self.root, self.workflow, full["response_digest"])

    def test_dispatch_cannot_direct_an_artifact_outside_the_project(self):
        view = deepcopy(self.view)
        view["active_assignment"]["output_path"] = "../foreign-artifact.json"
        with self.assertRaises(PipelineError):
            export_assignment(self.root, view)

    def test_boundary_actions_never_dispatch(self):
        for action in ({"kind": "controller_decision", "command": "answer"},
                       {"kind": "terminal", "result": "recovery_required"},
                       {"kind": "command", "command": "init"},
                       {"kind": "command", "command": "ready"}):
            controller = Mock()
            controller.status.return_value = {"generation": 4, "next_action": action}
            controller.store.load.return_value = {"history": []}
            result = execute_step(controller, self.root, 4, "unused")
            self.assertEqual("stopped", result["result"])
            controller.next.assert_not_called()
            controller.complete.assert_not_called()
            controller.transition.assert_not_called()

    def test_handoff_option_never_crosses_decision_recovery_init_or_ready(self):
        for action in ({"kind": "controller_decision", "command": "answer"},
                       {"kind": "terminal", "result": "recovery_required"},
                       {"kind": "command", "command": "init"},
                       {"kind": "command", "command": "ready"}):
            controller = Mock()
            controller.status.return_value = {"generation": 4, "next_action": action}
            controller.store.load.return_value = {"history": []}
            result = execute_step(controller, self.root, 4, "unused", through_handoff=True)
            self.assertEqual("stopped", result["result"])
            self.assertEqual([], result["steps"])
            self.assertEqual(action, result["next_action"])
            controller.next.assert_not_called()
            controller.complete.assert_not_called()
            controller.transition.assert_not_called()

    def test_brief_next_omits_packet_but_keeps_exact_action_and_semantic_boundaries(self):
        view = deepcopy(self.view)
        view["active_assignment"] = None
        view["next_action"] = {"kind": "command", "command": "next", "command_id": "NEXT-1", "expected_generation": 4,
                               "assignment": self.view["active_assignment"]}
        brief = director_brief(view)
        self.assertEqual("NEXT-1", brief["next_action"]["command_id"])
        self.assertEqual(4, brief["next_action"]["expected_generation"])
        self.assertNotIn("unchanged", json.dumps(brief))
        self.assertFalse(brief["next_action"]["assignment"]["content_included"])
        for action in ({"kind": "controller_decision", "command": "answer", "prompt": "Resolve the actual semantic question"},
                       {"kind": "terminal", "recovery_binding": {"exact": "binding"}, "result": "recovery_required"}):
            view["next_action"] = action
            self.assertEqual(action, director_brief(view)["next_action"])

    def test_brief_projects_only_bound_diagnostic_result_metadata_without_acceptance_credit(self):
        view = deepcopy(self.view)
        view["active_assignment"]["context"].update({
            "diagnostic_checks": {
                "assignment_id": "A-1", "candidate_tree_oid": "candidate-1",
                "grants_semantic_credit": False, "overall": "pass",
                "results": [
                    {"check_id": "unit", "returncode": 0, "duration_ms": 321,
                     "argv": ["python", "-m", "unittest"], "stdout_excerpt": "secret output",
                     "stderr_excerpt": "secret error", "execution_reason": "new_input_binding"},
                    {"check_id": "partial", "returncode": 7},
                ],
            },
            "machine_checks": {"grants_manual_acceptance": False, "outcome": "pass",
                               "pending_check_ids": ["not-run"]},
            "private_context": "must stay in the lossless packet",
        })
        brief = director_brief(view)
        projected = brief["active_assignment"]["diagnostic_checks"]
        self.assertEqual({
            "assignment_id": "A-1", "candidate_tree_oid": "candidate-1",
            "grants_semantic_credit": False, "grants_manual_acceptance": False,
            "pending_check_ids": ["not-run"],
            "results": [
                {"check_id": "unit", "returncode": 0, "duration_ms": 321},
                {"check_id": "partial", "returncode": 7},
            ],
        }, projected)
        encoded = json.dumps(brief)
        for forbidden in ("secret output", "secret error", "argv", "execution_reason",
                          "private_context", '"overall"', '"outcome"'):
            self.assertNotIn(forbidden, encoded)
        packet = self.receive(export_assignment(self.root, view)["packet_digest"])
        self.assertEqual(view["active_assignment"], packet["assignment"])
        self.assertEqual("secret output", packet["assignment"]["context"]["diagnostic_checks"]
                         ["results"][0]["stdout_excerpt"])
        view["active_assignment"]["context"]["diagnostic_checks"]["results"] = []
        empty = director_brief(view)["active_assignment"]["diagnostic_checks"]
        self.assertEqual([], empty["results"])
        self.assertNotIn("outcome", empty)
        self.assertNotIn("passed", empty)


class ControllerDeliveryIntegrationTests(unittest.TestCase):
    @staticmethod
    def captured_process(returncode, stdout=b"fixture stdout", stderr=b"fixture stderr"):
        def execute(*args, **kwargs):
            kwargs["stdout_path"].write_bytes(stdout)
            kwargs["stderr_path"].write_bytes(stderr)
            stdout_sha = hashlib.sha256(stdout).hexdigest()
            stderr_sha = hashlib.sha256(stderr).hexdigest()
            return ProcessEvidence(returncode, stdout_sha, stderr_sha, stderr, False,
                                   stdout, False, 321, stderr_raw_sha256=stderr_sha)
        return execute

    def setUp(self):
        from pipeline_v2.tests.test_core import PipelineV2CoreTests
        from pipeline_v2.runner import Controller
        self.fixture = PipelineV2CoreTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.root
        self.controller = Controller(self.fixture.store)

    def test_worker_can_consume_and_return_using_only_dispatch_from_foreign_cwd(self):
        action = self.controller.status()["next_action"]
        issued = execute_step(self.controller, self.root, action["expected_generation"], action["command_id"])
        # The Director forwards only the generated descriptor and host binding.
        # A worker can resolve every native input/output without the caller cwd,
        # source inspection, hand-built launcher, or full Director-side packet read.
        dispatch = issued["assignment_delivery"]["dispatch"]
        before = self.fixture.store.path.read_bytes()
        tree = candidate_tree_oid(self.root)
        with tempfile.TemporaryDirectory(prefix="foreign dispatch cwd ") as foreign:
            response = subprocess.run(
                dispatch["reader"]["bootstrap_argv"],
                cwd=foreign, capture_output=True, text=True, encoding="utf-8", check=True,
            )
            header, body = response.stdout.split("\n", 1)
            page = json.loads(header)
            self.assertTrue(page["unit_complete"])
            self.assertFalse(page["delivery_complete"])
            assignment = json.loads(body)["assignment"]
            self.assertEqual(dispatch["assignment_id"], assignment["id"])
            self.assertEqual(dispatch["worker_id"], assignment["worker_id"])
            self.assertEqual(str(self.root), dispatch["cwd"])
            self.assertEqual("requires_separate_bounded_grant", dispatch["controller_mutation_authority"])
            self.assertEqual("execute_issued_assignment", dispatch["allowed_action"])
            self.assertEqual("terminal_artifact_or_required_control_pause", dispatch["stop_boundary"])
            self.assertEqual("issued_exact_terminal_artifact", dispatch["output"]["write_authority"])
            packet_bytes = Path(dispatch["input"]["packet_path"]).read_bytes()
            self.assertEqual(dispatch["input"]["packet_digest"], hashlib.sha256(packet_bytes).hexdigest())
            packet = json.loads(packet_bytes)
            self.assertEqual(assignment, packet["assignment"])
            self.assertEqual(assignment["access"], json.loads(read_delivery(
                self.root, self.fixture.workflow_path, dispatch["scope"]["packet_digest"],
                pointer=dispatch["scope"]["pointer"], limit=16384)["text"]))
            self.assertEqual(assignment["artifact_schema"], json.loads(read_delivery(
                self.root, self.fixture.workflow_path, dispatch["output"]["schema"]["packet_digest"],
                pointer=dispatch["output"]["schema"]["pointer"], limit=16384)["text"]))
            self.assertEqual(before, self.fixture.store.path.read_bytes())
            self.assertEqual(tree, candidate_tree_oid(self.root))
            output = Path(dispatch["output"]["path"])
            self.assertEqual(self.root / assignment["output_path"], output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps({"outcome": "pass", "summary": "Assigned plan confirmed."}), encoding="utf-8")
            self.assertFalse((Path(foreign) / assignment["output_path"]).exists())
        complete = issued["next_action"]
        consumed = execute_step(self.controller, self.root, complete["expected_generation"], complete["command_id"])
        self.assertEqual("phase_passed", consumed["outcome"])
        self.assertEqual("accept", consumed["next_action"]["command"])
        self.assertEqual(tree, candidate_tree_oid(self.root))

    def test_readonly_roles_write_exact_dispatched_output_without_product_or_state_access(self):
        self.fixture._reach_candidate()
        for phase, artifact in (
            ("review", {"outcome": "pass", "findings": []}),
            ("qa", {"outcome": "pass", "checks": self.fixture._qa_checks("Assigned fixture scenarios observed.")}),
        ):
            with self.subTest(phase=phase):
                view = self.controller.status()
                self.assertEqual(phase, view["phase"])
                action = view["next_action"]
                issued = execute_step(self.controller, self.root, action["expected_generation"], action["command_id"])
                dispatch = issued["assignment_delivery"]["dispatch"]
                packet = json.loads(Path(dispatch["input"]["packet_path"]).read_bytes())
                assignment = packet["assignment"]
                self.assertEqual([], assignment["access"]["write"])
                self.assertEqual("issued_exact_terminal_artifact", dispatch["output"]["write_authority"])
                self.assertEqual("requires_separate_bounded_grant", dispatch["controller_mutation_authority"])
                state_before = self.fixture.store.path.read_bytes()
                tree_before = candidate_tree_oid(self.root)
                output = Path(dispatch["output"]["path"])
                self.assertEqual(self.root / assignment["output_path"], output)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps(artifact), encoding="utf-8")
                self.assertEqual(tree_before, candidate_tree_oid(self.root))
                self.assertEqual(state_before, self.fixture.store.path.read_bytes())
                # Terminal-output authority cannot be substituted with state or
                # Delivery, even though those paths are in the same workflow.
                for wrong_path in (self.fixture.store.path, Path(dispatch["input"]["packet_path"])):
                    with self.assertRaisesRegex(PipelineError, "only the assigned artifact path"):
                        self.controller.complete(command_id=f"WRONG-OUTPUT-{phase}", artifact_path=wrong_path)
                    self.assertEqual(state_before, self.fixture.store.path.read_bytes())
                action = issued["next_action"]
                completed = execute_step(self.controller, self.root, action["expected_generation"], action["command_id"])
                self.assertEqual("phase_passed", completed["outcome"])
                self.assertEqual(tree_before, candidate_tree_oid(self.root))
                self.fixture._accept(f"dispatched-{phase}")

    def test_native_project_root_survives_full_and_continued_delivery_from_foreign_cwd(self):
        with tempfile.TemporaryDirectory() as previous_project:
            old_root = Path(previous_project).resolve()
            (old_root / "index.html").write_text("Historical project entry", encoding="utf-8")
            (old_root / "game.txt").write_text("Do not change this checkout", encoding="utf-8")
            # Real sealed authority includes a historical URL that must not select cwd.
            plan = self.root / self.fixture.store.load()["authority"]["items"]["plan"]["path"]
            with plan.open("a", encoding="utf-8") as stream:
                stream.write("\n## Historical manual entry\n\n" + (old_root / "index.html").as_uri() + "\n")
            (self.root / "game.txt").unlink()  # Assigned greenfield file, not a missing root.
            self.fixture._commit_fixture_and_restart("root binding delivery fixture")
            self.fixture._reach_engineering("-root-binding")
            from pipeline_v2.runner import Controller
            self.controller = Controller(self.fixture.store)
            prefix = ["--root", str(self.root), "--feature", self.fixture.feature]
            saved_cwd = Path.cwd()
            try:
                os.chdir(old_root)
                pending = self.controller.status()["next_action"]
                issued = run(parser().parse_args(prefix + ["step", "--expected-generation",
                    str(pending["expected_generation"]), "--action-id", pending["command_id"]]))
                full = issued["assignment_delivery"]
                packet = json.loads((self.root / full["path"]).read_text(encoding="utf-8"))
                view = self.controller.status()
                brief = director_brief(view)
                for value in (view, brief, brief["assignment_delivery"], full, packet):
                    self.assertEqual(str(self.root), value["project_root"])
                    self.assertTrue(Path(value["project_root"]).is_absolute())
                self.assertEqual(view["active_assignment"], read_delivery_unit(
                    self.root, self.fixture.workflow_path, full["packet_digest"], "/assignment", "value")["value"])
                access = deepcopy(packet["assignment"]["access"])
                self.assertFalse((Path(packet["project_root"]) / "game.txt").exists())
                self.assertEqual("Do not change this checkout", Path("game.txt").read_text(encoding="utf-8"))
                # Real native refresh; no planned product command/check is run.
                self.controller.technical_action(command_id="OBS-ROOT-BINDING",
                    expected_generation=view["generation"], action="Observe assigned greenfield files before creation")
                continued = run(parser().parse_args(prefix + ["assignment-export", "--baseline", full["packet_digest"]]))
                delta = json.loads((self.root / continued["path"]).read_text(encoding="utf-8"))
                rebuilt = apply_patch(packet, delta["patch"])
                for value in (continued, delta, rebuilt):
                    self.assertEqual(str(self.root), value["project_root"])
                self.assertEqual(continued["packet_digest"], hashlib.sha256(canonical_bytes(rebuilt)).hexdigest())
                self.assertEqual(access, rebuilt["assignment"]["access"])
                self.assertEqual(packet["assignment"]["id"], rebuilt["assignment"]["id"])
                bound_root = Path(rebuilt["project_root"])
                (bound_root / "game.txt").write_text("Created in assigned root", encoding="utf-8")
                output = bound_root / rebuilt["assignment"]["output_path"]
                self.assertTrue(output.is_relative_to(self.root))
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text('{"fixture": "relative artifact location"}', encoding="utf-8")
                self.assertTrue(output.is_file())
                self.assertFalse((old_root / rebuilt["assignment"]["output_path"]).exists())
                self.assertEqual("Do not change this checkout", (old_root / "game.txt").read_text(encoding="utf-8"))
                page = read_file(bound_root, self.controller.status(), "game.txt")
                self.assertEqual("Created in assigned root", page["text"])
                with self.assertRaisesRegex(PipelineError, "outside"):
                    read_file(bound_root, self.controller.status(), "private.txt")
            finally:
                os.chdir(saved_cwd)

    def test_cli_step_issues_once_retries_without_advancing_and_waits_for_real_artifact(self):
        initial_tree = candidate_tree_oid(self.root)
        action = self.controller.status()["next_action"]
        pending = director_brief(self.controller.status())["next_action"]["assignment"]["role_instructions"]
        self.assertEqual("planner", pending["role"])
        self.assertEqual("Runtime Plan and Slice", pending["section"])
        argv = ["--root", str(self.root), "--feature", self.fixture.feature, "step",
                "--expected-generation", str(action["expected_generation"]), "--action-id", action["command_id"]]
        issued = run(parser().parse_args(argv))
        self.assertEqual("executed", issued["result"])
        self.assertIn("assignment_delivery", issued)
        self.assertEqual(self.controller.status()["active_assignment"]["worker_id"], issued["assignment_delivery"]["worker_id"])
        self.assertEqual(pending, issued["assignment_delivery"]["role_instructions"])
        before = self.fixture.store.path.read_bytes()
        exported = export_assignment(self.root, self.controller.status())
        self.assertEqual(self.controller.status()["active_assignment"]["worker_id"], exported["worker_id"])
        self.assertEqual(pending, exported["role_instructions"])
        self.assertEqual(before, self.fixture.store.path.read_bytes())
        self.assertEqual(initial_tree, candidate_tree_oid(self.root))
        replay = run(parser().parse_args(argv))
        self.assertEqual("already_applied", replay["result"])
        self.assertEqual(issued["generation"], replay["generation"])
        action = self.controller.status()["next_action"]
        result = execute_step(self.controller, self.root, action["expected_generation"], action["command_id"])
        self.assertEqual("waiting_for_artifact", result["result"])
        self.assertEqual(issued["generation"], self.controller.status()["generation"])

    def test_stale_or_wrong_action_cannot_execute(self):
        action = self.controller.status()["next_action"]
        with self.assertRaisesRegex(PipelineError, "stale"):
            execute_step(self.controller, self.root, action["expected_generation"] + 1, action["command_id"])
        with self.assertRaisesRegex(PipelineError, "action ID"):
            execute_step(self.controller, self.root, action["expected_generation"], "wrong")
        self.assertIsNone(self.controller.status()["active_assignment"])

    def test_brief_cli_check_returns_bound_metadata_without_full_check_payload(self):
        self.fixture._reach_engineering("-brief-check")
        action = self.controller.status()["next_action"]
        self.controller.next(command_id=action["command_id"], expected_generation=action["expected_generation"])
        active = self.controller.status()["active_assignment"]
        state = self.fixture.store.load()
        argv = ["--root", str(self.root), "--feature", self.fixture.feature, "--brief", "check",
                "--id", "CLI-BRIEF-CHECK", "--expected-generation", str(state["generation"]),
                "--assignment-id", active["id"], "--quiescence", "Writer stopped for this check."]
        evidence = self.captured_process(7, b"full stdout must not be projected", b"full stderr must not be projected")
        with mock.patch("pipeline_v2.runner.run_process_tree", side_effect=evidence):
            checked = run(parser().parse_args(argv))
        diagnostic = checked["active_assignment"]["diagnostic_checks"]
        self.assertEqual(active["id"], diagnostic["assignment_id"])
        self.assertEqual(7, diagnostic["results"][0]["returncode"])
        self.assertIsInstance(diagnostic["results"][0]["duration_ms"], int)
        self.assertGreaterEqual(diagnostic["results"][0]["duration_ms"], 0)
        self.assertFalse(diagnostic["grants_semantic_credit"])
        self.assertFalse(diagnostic["grants_manual_acceptance"])
        encoded = json.dumps(checked)
        self.assertNotIn("full stderr", encoded)
        self.assertNotIn("full stdout", encoded)
        self.assertNotIn('"argv"', json.dumps(diagnostic))
        invocation = parser().parse_args(checked["next_action"]["invocation"]["argv"][2:])
        self.assertEqual("step", invocation.command)
        self.assertEqual(checked["generation"], invocation.expected_generation)
        self.assertEqual(checked["next_action"]["command_id"], invocation.action_id)

    def test_step_complete_validates_artifact_and_accept_is_a_separate_action(self):
        action = self.controller.status()["next_action"]
        execute_step(self.controller, self.root, action["expected_generation"], action["command_id"])
        action = self.controller.status()["next_action"]
        self.fixture._write_artifact({"outcome": "invented", "summary": "Invalid semantic result."})
        with self.assertRaises(PipelineError):
            execute_step(self.controller, self.root, action["expected_generation"], action["command_id"])
        self.assertEqual(action["expected_generation"], self.controller.status()["generation"])
        self.fixture._write_artifact({"outcome": "pass", "summary": "Delivered the assigned result."})
        completed = execute_step(self.controller, self.root, action["expected_generation"], action["command_id"])
        self.assertEqual("complete", completed["command"])
        self.assertEqual("phase_passed", completed["outcome"])
        self.assertEqual("accept", completed["next_action"]["command"])
        self.assertEqual("accept", self.controller.status()["next_action"]["command"])
        action = self.controller.status()["next_action"]
        accepted = execute_step(self.controller, self.root, action["expected_generation"], action["command_id"])
        self.assertEqual("accept", accepted["command"])
        self.assertEqual("accepted", accepted["outcome"])
        self.assertEqual("next", accepted["next_action"]["command"])
        self.assertEqual("next", self.controller.status()["next_action"]["command"])

    def handoff(self, action=None):
        action = action or self.controller.status()["next_action"]
        return execute_step(self.controller, self.root, action["expected_generation"],
                            action["command_id"], through_handoff=True)

    def test_handoff_engineer_and_reviewer_each_stop_at_new_assignment_and_full_replay_is_readonly(self):
        self.fixture._reach_engineering("-handoff")
        issued = self.handoff()  # Starting at next must issue exactly one assignment.
        self.assertEqual(self.controller.status()["active_assignment"]["worker_id"], issued["assignment_delivery"]["worker_id"])
        self.fixture._write_artifact({"outcome": "pass", "summary": "Owned implementation complete."})
        original = self.controller.status()["next_action"]
        native_next = self.controller.next

        def next_with_new_worker_output(**kwargs):
            state = native_next(**kwargs)
            self.fixture._write_artifact({"outcome": "pass", "findings": []})
            return state

        with mock.patch.object(self.controller, "next", side_effect=next_with_new_worker_output):
            result = self.handoff(original)
        self.assertEqual(["complete", "accept", "next"], [item["command"] for item in result["steps"]])
        self.assertEqual(["phase_passed", "accepted", "assignment_issued"], [item["outcome"] for item in result["steps"]])
        self.assertEqual(original["expected_generation"] + 3, result["generation"])
        self.assertEqual({"expected_generation": original["expected_generation"], "action_id": original["command_id"]}, result["request"])
        self.assertEqual("review", result["phase"])
        state = self.fixture.store.load()
        self.assertEqual("review", state["active_assignment"]["phase"])
        self.assertNotIn("review", state["artifacts"])
        self.assertTrue((self.root / state["active_assignment"]["output_path"]).is_file())
        before = self.fixture.store.path.read_bytes()
        delivery = self.root / self.fixture.workflow_path / "Delivery"
        files = {p.name: p.read_bytes() for p in delivery.iterdir()}
        replay = self.handoff(original)
        self.assertEqual("already_applied", replay["result"])
        self.assertEqual([], replay["steps"])
        self.assertEqual(state["active_assignment"]["id"], replay["active_assignment"]["id"])
        self.assertEqual("assignment-export", replay["assignment_delivery"]["command"])
        self.assertEqual(before, self.fixture.store.path.read_bytes())
        self.assertEqual(files, {p.name: p.read_bytes() for p in delivery.iterdir()})
        reviewed = self.handoff()  # Separately established terminal Review output.
        self.assertEqual(["complete", "accept", "next"], [item["command"] for item in reviewed["steps"]])
        self.assertEqual("qa", reviewed["phase"])
        self.assertEqual("qa", self.fixture.store.load()["active_assignment"]["phase"])
        self.assertNotIn("qa", self.fixture.store.load()["artifacts"])

    def test_handoff_cli_missing_artifact_and_partial_replays_do_not_finish_remaining_chain(self):
        issued = self.handoff()
        self.assertEqual(["next"], [item["command"] for item in issued["steps"]])
        original = self.controller.status()["next_action"]
        argv = ["--root", str(self.root), "--feature", self.fixture.feature, "step", "--through-handoff",
                "--expected-generation", str(original["expected_generation"]), "--action-id", original["command_id"]]
        waiting = run(parser().parse_args(argv))
        self.assertEqual("waiting_for_artifact", waiting["outcome"])
        self.assertEqual([], waiting["steps"])
        self.assertEqual(original, {key: value for key, value in waiting["next_action"].items() if key != "invocation"})
        invocation = parser().parse_args(waiting["next_action"]["invocation"]["argv"][2:])
        self.assertEqual(("step", original["expected_generation"], original["command_id"], self.root, self.fixture.feature),
                         (invocation.command, invocation.expected_generation, invocation.action_id, invocation.root, invocation.feature))
        self.assertTrue(invocation.through_handoff)
        self.fixture._write_artifact({"outcome": "pass", "summary": "Plan confirmed."})
        execute_step(self.controller, self.root, original["expected_generation"], original["command_id"])
        for after_accept in (False, True):
            if after_accept:
                action = self.controller.status()["next_action"]
                execute_step(self.controller, self.root, action["expected_generation"], action["command_id"])
            before = self.fixture.store.path.read_bytes()
            replay = run(parser().parse_args(argv))
            self.assertEqual("already_applied", replay["result"])
            self.assertEqual([], replay["steps"])
            self.assertEqual("next" if after_accept else "accept", replay["next_action"]["command"])
            self.assertIsNone(replay["active_assignment"])
            self.assertEqual(before, self.fixture.store.path.read_bytes())
        with self.assertRaisesRegex(PipelineError, "identity conflicts"):
            execute_step(self.controller, self.root, original["expected_generation"] + 1,
                         original["command_id"], through_handoff=True)
        current = self.controller.status()["next_action"]
        with self.assertRaisesRegex(PipelineError, "action ID"):
            execute_step(self.controller, self.root, current["expected_generation"], "wrong", through_handoff=True)
        with self.assertRaisesRegex(PipelineError, "stale"):
            execute_step(self.controller, self.root, current["expected_generation"] - 1, "stale", through_handoff=True)
        self.assertEqual(before, self.fixture.store.path.read_bytes())

    def test_handoff_partial_error_replays_original_request_without_any_new_action(self):
        self.handoff()
        original = self.controller.status()["next_action"]
        self.fixture._write_artifact({"outcome": "pass", "summary": "Plan confirmed."})
        with mock.patch.object(self.controller, "transition", side_effect=PipelineError("Concurrent boundary changed")):
            with self.assertRaisesRegex(PipelineError, "Concurrent boundary changed"):
                self.handoff(original)
        before = self.fixture.store.path.read_bytes()
        self.assertEqual(original["expected_generation"] + 1, self.fixture.store.load()["generation"])
        replay = self.handoff(original)
        self.assertEqual([], replay["steps"])
        self.assertEqual("accept", replay["next_action"]["command"])
        self.assertEqual(before, self.fixture.store.path.read_bytes())
        remaining = self.handoff()
        self.assertEqual(["accept", "next"], [item["command"] for item in remaining["steps"]])
        self.assertEqual("slice", remaining["phase"])

    def test_handoff_stops_when_concurrent_actor_already_applied_following_action(self):
        self.handoff()
        self.fixture._write_artifact({"outcome": "pass", "summary": "Plan confirmed."})
        original = self.controller.status()["next_action"]
        native_complete = self.controller.complete

        def complete_then_external_accept(**kwargs):
            result = native_complete(**kwargs)
            action = self.controller.status()["next_action"]
            self.controller.transition({"name": "accept", "id": action["command_id"], "expected_generation": action["expected_generation"]})
            return result

        with mock.patch.object(self.controller, "complete", side_effect=complete_then_external_accept):
            result = self.handoff(original)
        self.assertEqual("replayed", result["outcome"])
        self.assertEqual(["complete"], [item["command"] for item in result["steps"]])
        self.assertEqual(original["expected_generation"] + 2, result["generation"])
        self.assertIsNone(self.fixture.store.load()["active_assignment"])
        self.assertEqual("next", result["next_action"]["command"])

    def test_handoff_stops_on_semantic_failure_block_and_question(self):
        self.handoff()
        self.fixture._write_artifact({"outcome": "fail", "summary": "Plan needs correction."})
        failed = self.handoff()
        self.assertEqual("phase_failed", failed["outcome"])
        self.assertEqual(["complete"], [item["command"] for item in failed["steps"]])
        self.assertIsNone(self.fixture.store.load()["active_assignment"])
        self.handoff()
        self.fixture._write_artifact({"outcome": "pass", "summary": "Technical choice needs resolution.",
                                     "questions": ["Which existing implementation should be used?"]})
        question = self.handoff()
        self.assertEqual(["complete"], [item["command"] for item in question["steps"]])
        self.assertEqual("answer", question["next_action"]["command"])
        stopped = self.handoff()
        self.assertEqual([], stopped["steps"])
        action = self.controller.status()["next_action"]
        self.controller.transition({"name": "answer", "id": action["command_id"], "expected_generation": action["expected_generation"],
                                    "question_id": action["question_id"], "answer": "Use the existing supported implementation."})
        self.handoff()
        self.fixture._write_artifact({"outcome": "blocked", "summary": "Required capability unavailable.",
                                     "blocker": "Mandatory capability remains unavailable.", "required_action": "Restore that capability."})
        blocked = self.handoff()
        self.assertEqual("blocked", blocked["outcome"])
        self.assertEqual(["complete"], [item["command"] for item in blocked["steps"]])
        self.assertIsNone(self.fixture.store.load()["active_assignment"])

    def test_handoff_stops_on_gate_failure_and_replay_never_reruns_checks(self):
        self.fixture._reach_engineering("-handoff-gate")
        self.handoff()
        original = self.controller.status()["next_action"]
        self.fixture._write_artifact({"outcome": "pass", "summary": "Implementation ready for its mandatory check."})
        with mock.patch("pipeline_v2.runner.run_process_tree", side_effect=self.captured_process(7)) as process:
            failed = self.handoff(original)
            self.assertEqual("gate_failed", failed["outcome"])
            self.assertEqual("pass", failed["semantic_outcome"])
            self.assertEqual(["complete"], [item["command"] for item in failed["steps"]])
            self.assertEqual(7, failed["failure"]["returncode"])
            before = self.fixture.store.path.read_bytes()
            replay = self.handoff(original)
            self.assertEqual([], replay["steps"])
            self.assertEqual(1, process.call_count)
            self.assertEqual(before, self.fixture.store.path.read_bytes())

    def test_handoff_stops_when_checkout_drifts_after_first_action(self):
        self.handoff()
        self.fixture._write_artifact({"outcome": "pass", "summary": "Plan confirmed."})
        native_complete = self.controller.complete

        def complete_then_drift(**kwargs):
            result = native_complete(**kwargs)
            (self.root / "game.txt").write_text("External change after completion\n", encoding="utf-8")
            return result

        original = self.controller.status()["next_action"]
        with mock.patch.object(self.controller, "complete", side_effect=complete_then_drift):
            result = self.handoff(original)
        self.assertEqual("stopped", result["result"])
        self.assertEqual(["complete"], [item["command"] for item in result["steps"]])
        self.assertEqual("terminal", result["next_action"]["kind"])
        self.assertEqual(original["expected_generation"] + 1, result["generation"])
        self.assertIsNone(self.fixture.store.load()["active_assignment"])

    def test_brief_cli_status_and_technical_actions_do_not_print_unchanged_journal(self):
        self.fixture._reach_engineering("-brief")
        action = self.controller.status()["next_action"]
        self.controller.next(command_id=action["command_id"], expected_generation=action["expected_generation"])
        prefix = ["--root", str(self.root), "--feature", self.fixture.feature]
        unchanged = "UNCHANGED-REQUIRED-DETAIL " * 2500

        def brief_stdout(command):
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(0, main(prefix + ["--brief"] + command))
            self.assertNotIn("UNCHANGED-REQUIRED-DETAIL", output.getvalue())
            return json.loads(output.getvalue())

        def decision(identifier, decision_text):
            state = self.fixture.store.load()
            packet = {"assignment_id": state["active_assignment"]["id"], "observed_tree_oid": candidate_tree_oid(self.root),
                "entry": {"id": identifier, "situation": "Observed bounded issue", "decision": decision_text,
                    "basis": "Exact observed behavior", "checks": ["Inspect the actual changed bytes"],
                    "downstream": "Independent Review and QA remain mandatory"}}
            path = self.root / self.fixture.workflow_path / "decision-input.json"
            path.write_text(json.dumps(packet), encoding="utf-8")
            return brief_stdout(["technical-decision", "--id", identifier, "--expected-generation", str(state["generation"]),
                                 "--packet", str(path)])

        first = decision("TD-FIRST", unchanged)
        self.assertFalse(first["active_assignment"]["content_included"])
        self.assertEqual(1, first["technical_journal"]["count"])
        baseline = run(parser().parse_args(prefix + ["assignment-export"]))
        full_packet = json.loads((self.root / baseline["path"]).read_text(encoding="utf-8"))
        self.assertEqual(unchanged, full_packet["assignment"]["context"]["technical_decisions"][0]["decision"])
        brief = brief_stdout(["status"])
        self.assertEqual(first["active_assignment"]["id"], brief["active_assignment"]["id"])
        full_output = io.StringIO()
        with redirect_stdout(full_output):
            self.assertEqual(0, main(prefix + ["--full", "status"]))
        self.assertIn("UNCHANGED-REQUIRED-DETAIL", full_output.getvalue())
        second = decision("TD-SECOND", "Apply the exact small additional decision")
        self.assertEqual(2, second["technical_journal"]["count"])
        delta_export = run(parser().parse_args(prefix + ["assignment-export", "--baseline", baseline["packet_digest"]]))
        delta = json.loads((self.root / delta_export["path"]).read_text(encoding="utf-8"))
        self.assertNotIn("UNCHANGED-REQUIRED-DETAIL", json.dumps(delta))
        self.assertEqual(delta_export["packet_digest"], hashlib.sha256(canonical_bytes(apply_patch(full_packet, delta["patch"]))).hexdigest())
        state = self.fixture.store.load()
        observed = brief_stdout(["technical-observe", "--id", "OBS-BRIEF", "--expected-generation", str(state["generation"]),
                                 "--action", "Inspect the current project state"])
        self.assertEqual("OBS-BRIEF", observed["active_assignment"]["technical_observation"]["id"])
        self.assertEqual(candidate_tree_oid(self.root), observed["active_assignment"]["technical_observation"]["tree"])


if __name__ == "__main__":
    unittest.main()
