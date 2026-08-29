from __future__ import annotations

import json
import ast
import inspect
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[2]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pipeline_v2
import pipeline_v2.reducer as reducer_module
import pipeline_v2.runner as runner_module
import pipeline_v2.transaction as transaction_module
from pipeline_v2.checkout import authority_items, inventory, inventory_digest, matches
from pipeline_v2.cli import parser as cli_parser, run as cli_run
from pipeline_v2.legacy_gen53 import import_schema10
from pipeline_v2.model import ConflictError, PHASES, ROLES, PipelineError, artifact_schema, assignment_output_path, command_intent_digest, current_candidate, current_slice, default_assignment, digest, normalize_rule, status_view, validate_state
from pipeline_v2.process_tree import ProcessEvidence
from pipeline_v2.reducer import COMMANDS, reduce
from pipeline_v2.runner import Controller
from pipeline_v2.transaction import StateStore


class _CanonicalTestController(Controller):
    """Adapt legacy fixtures to controller-owned command and assignment identity."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._next_command_aliases: dict[str, str] = {}

    def next(self, *, command_id, assignment=None, expected_generation=None):
        state = self.store.load()
        actual_command_id = self._next_command_aliases.get(command_id)
        if actual_command_id is None:
            action = status_view(state)["next_action"]
            actual_command_id = (
                action["command_id"] if action.get("command") == "next" else command_id
            )
            self._next_command_aliases[command_id] = actual_command_id
        supplied = deepcopy(assignment or {})
        prior = next((
            item for item in state["history"]
            if item.get("id") == actual_command_id
        ), None)
        if prior is None:
            canonical = default_assignment(state)
            supplied.update({
                field: canonical[field] for field in ("id", "worker_id", "task")
            })
        return super().next(
            command_id=actual_command_id, assignment=supplied,
            expected_generation=expected_generation,
        )


class PipelineV2CoreTests(unittest.TestCase):
    def test_default_controller_timeout_covers_bounded_large_project_checks(self) -> None:
        self._reach_engineering("-large-project-timeout")
        controller = _CanonicalTestController(self.store)
        controller.next(command_id="NEXT-LARGE-PROJECT-TIMEOUT", assignment={
            "id": "ASSIGN-LARGE-PROJECT-TIMEOUT",
            "worker_id": "engineer-large-project-timeout",
            "task": "Run a bounded large-project aggregate",
        })
        artifact = self._write_artifact({"outcome": "pass", "summary": "Aggregate passed"})

        def simulated_aggregate(*_args, timeout: float, **_kwargs) -> ProcessEvidence:
            return ProcessEvidence(
                0 if timeout >= 254.008 else 124,
                digest("large-project-stdout"), digest("large-project-stderr"),
            )

        with mock.patch(
            "pipeline_v2.runner.run_process_tree", side_effect=simulated_aggregate,
        ):
            completed = controller.complete(
                command_id="COMPLETE-LARGE-PROJECT-TIMEOUT", artifact_path=artifact,
            )

        command = completed["artifacts"]["engineering"]["controller"]["commands"][0]
        self.assertEqual(600.0, controller.timeout)
        self.assertEqual(0, command["returncode"])

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        for name in ("requirements.md", "specification.md"):
            (self.root / name).write_text(f"approved {name}\n", encoding="utf-8")
        (self.root / "game.txt").write_text("old\n", encoding="utf-8")
        self.command = [sys.executable, "-c", "raise SystemExit(0)"]
        self.slices = [{
            "id": "SLICE-1", "allowed_paths": ["game.txt", "tests/**"],
            "planned_commands": [self.command],
        }]
        self._write_approved_plan(self.slices)
        self.store = StateStore(self.root / ".agentic-pipeline-v2" / "state.json")
        self._initialize()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _initialize(self) -> None:
        paths = {"requirements": "requirements.md", "specification": "specification.md", "plan": "plan.md"}
        self.store.dispatch({
            "name": "init", "id": "CMD-INIT", "run_id": "RUN-TEST", "project_root": str(self.root),
            "authority": {"items": authority_items(self.root, paths)}, "slices": self._sealed(self.slices),
        })
        self.controller = _CanonicalTestController(self.store, timeout=10)

    @staticmethod
    def _sealed(slices: list[dict], reads: dict[str, list[str]] | None = None) -> list[dict]:
        reads = reads or {item["id"]: item["allowed_paths"] for item in slices}
        return [deepcopy(item) | {"read_paths": deepcopy(reads[item["id"]])} for item in slices]

    def _write_approved_plan(
        self, slices: list[dict], *, reads: dict[str, list[str]] | None = None,
        revision: int = 1, documentation_policy: str | None = None,
        normative_documentation_policy: str | None = None,
        derived_documentation_policy: str | None = None,
        documentation_path: str | None = "docs/RUN-TEST-verification.md",
        slice_documentation: dict[str, tuple[str, str]] | None = None,
    ) -> None:
        if documentation_policy is not None:
            if (
                normative_documentation_policy is not None
                or derived_documentation_policy is not None
            ):
                raise ValueError("use one shared policy or category-specific policies")
            normative_documentation_policy = documentation_policy
            derived_documentation_policy = documentation_policy

        def documentation_value(policy: str | None) -> str | None:
            if policy is not None:
                return f"not_required | policy={policy}"
            return documentation_path

        normative_documentation = documentation_value(normative_documentation_policy)
        derived_documentation = documentation_value(derived_documentation_policy)
        reads = reads or {item["id"]: item["allowed_paths"] for item in slices}
        sections = []
        for item in slices:
            paths = reads[item["id"]]
            documentation = ""
            slice_normative, slice_derived = (
                slice_documentation.get(
                    item["id"], (normative_documentation, derived_documentation),
                )
                if slice_documentation is not None
                else (normative_documentation, derived_documentation)
            )
            if slice_normative is not None and slice_derived is not None:
                documentation = (
                    "\n### Documentation Contract\n\n"
                    f"- normative_pre_review_paths: {slice_normative}\n"
                    f"- derived_post_qa_paths: {slice_derived}\n"
                    "- decision_ids: none\n"
                    "- evidence_sources: approved test authority\n"
                )
            sections.append(
                f"## Slice {item['id']}\n\n"
                "### Context Capsule Budget\n\n"
                "- max_authority_files: 20\n"
                "- max_evidence_files: 20\n"
                "- max_total_files: 40\n"
                "- max_payload_bytes: 100000\n"
                "- max_estimated_tokens: 25000\n"
                "- metric_scope: capsule_plus_referenced_files\n"
                f"- authority_paths: {paths[0]}\n"
                f"- evidence_paths: {', '.join(paths)}\n"
                f"{documentation}"
            )
        documentation_strategy = ""
        if normative_documentation is not None and derived_documentation is not None:
            documentation_strategy = (
                "## Documentation Strategy\n\n"
                f"- normative_pre_review: {normative_documentation}\n"
                f"- derived_post_qa: {derived_documentation}\n"
                "- source_rule: approved test authority\n\n"
            )
        text = (
            "---\n"
            "document_type: development-plan\n"
            "status: approved\n"
            f"revision: {revision}\n"
            "feature: test-feature\n"
            "mode: sequential_slices\n"
            "writer_strategy: sequential\n"
            "planning_analyst_id: analyst-test\n"
            "source_prd_path: requirements.md\n"
            "source_prd_revision: 1\n"
            f"source_prd_sha256: {'1' * 64}\n"
            "source_spec_path: specification.md\n"
            "source_spec_revision: 1\n"
            f"source_spec_sha256: {'2' * 64}\n"
            "decision_ledger_path: decisions.jsonl\n"
            f"slice_count: {len(slices)}\n"
            "approved_by: controller-test\n"
            "approved_at: 2026-08-24T00:00:00+00:00\n"
            "---\n"
            "# Test plan\n\n"
            + documentation_strategy
            + "\n".join(sections)
        )
        (self.root / "plan.md").write_text(text, encoding="utf-8")

    def _reconfigure_documentation_contract(
        self, *, policy: str | None = None,
        normative_policy: str | None = None,
        derived_policy: str | None = None,
        path: str | None = None,
        slice_documentation: dict[str, tuple[str, str]] | None = None,
    ) -> None:
        self._write_approved_plan(
            self.slices, revision=2, documentation_policy=policy,
            normative_documentation_policy=normative_policy,
            derived_documentation_policy=derived_policy,
            documentation_path=path,
            slice_documentation=slice_documentation,
        )
        action = self.controller.status()["next_action"]
        self.controller.reconfigure({
            "name": "init", "id": action["command_id"],
            "expected_generation": action["expected_generation"],
            "run_id": action["run_id"], "project_root": action["project_root"],
            "authority_paths": action["authority"], "slices": action["slices"],
        })

    def _accept(self, suffix: str) -> dict:
        state = self.store.load()
        return self.store.dispatch({
            "name": "accept", "id": f"ACCEPT-{suffix}", "expected_generation": state["generation"],
        })

    def _write_artifact(self, artifact: dict) -> Path:
        active = self.store.load()["active_assignment"]
        path = self.root / assignment_output_path(active)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(artifact), encoding="utf-8")
        return path

    def _complete(self, command_id: str, artifact: dict, *, artifact_path: Path | None = None) -> dict:
        assigned = self._write_artifact(artifact)
        return self.controller.complete(command_id=command_id, artifact_path=artifact_path or assigned)

    def _complete_readonly(self, phase: str, worker: str, artifact: dict) -> dict:
        self.assertEqual(phase, self.store.load()["phase"])
        self.controller.next(
            command_id=f"NEXT-{worker}",
            assignment={
                "id": f"ASSIGN-{worker}", "worker_id": worker, "task": f"Complete {phase}",
                "access": {"read": ["**"], "write": []},
                "commands": [self.command] if phase == "qa" else [],
            },
        )
        return self._complete(f"COMPLETE-{worker}", artifact)

    def _reach_engineering(self, suffix: str = "") -> None:
        self._complete_readonly("plan", f"planner{suffix}", {"outcome": "pass", "summary": "Plan confirmed"})
        self._accept(f"plan{suffix}")
        self._complete_readonly("slice", f"slicer{suffix}", {"outcome": "pass", "summary": "Slice confirmed"})
        self._accept(f"slice{suffix}")

    def _begin_four_record_slice_complete(
        self, state_name: str,
    ) -> tuple[dict, Path, dict, dict]:
        self.slices = [
            {
                "id": f"SLICE-{index:03d}",
                "allowed_paths": ["game.txt", f"tests/slice-{index}/**"],
                "planned_commands": [self.command],
            }
            for index in range(1, 5)
        ]
        reads = {
            item["id"]: ["requirements.md", item["allowed_paths"][0]]
            for item in self.slices
        }
        self._write_approved_plan(self.slices, reads=reads, revision=3)
        self.store = StateStore(
            self.root / ".agentic-pipeline-v2" / state_name,
        )
        paths = {
            "requirements": "requirements.md",
            "specification": "specification.md",
            "plan": "plan.md",
        }
        self.store.dispatch({
            "name": "init",
            "id": f"INIT-{state_name}",
            "run_id": f"RUN-{state_name}",
            "project_root": str(self.root),
            "authority": {"items": authority_items(self.root, paths)},
            "slices": self._sealed(self.slices, reads),
        })
        self.controller = _CanonicalTestController(self.store, timeout=10)
        self._complete_readonly(
            "plan", f"planner-{state_name}",
            {"outcome": "pass", "summary": "Plan confirmed"},
        )
        self._accept(f"plan-{state_name}")
        next_action = status_view(self.store.load())["next_action"]
        issued = self.controller.next(
            command_id=next_action["command_id"],
            expected_generation=next_action["expected_generation"],
        )
        artifact = {
            "outcome": "pass",
            "summary": "Approved Plan defines four bounded sequential slices.",
            "slices": deepcopy(self.slices),
        }
        path = self._write_artifact(artifact)
        return issued, path, artifact, status_view(issued)["next_action"]

    def _engineer(self, worker: str, text: str) -> dict:
        return self._engineer_slice(worker, text, slice_index=0, target="game.txt")

    def _engineer_slice(self, worker: str, text: str, *, slice_index: int, target: str) -> dict:
        self.assertEqual("engineering", self.store.load()["phase"])
        issued = self.controller.next(
            command_id=f"NEXT-{worker}",
            assignment={
                "id": f"ASSIGN-{worker}", "worker_id": worker, "task": "Implement current slice",
                "access": {"read": [], "write": []}, "commands": [],
            },
        )
        selected = self.slices[slice_index]
        actual_slice = issued["active_assignment"]["capsule"]["context"]["current_slice"]
        self.assertEqual(
            selected,
            {key: actual_slice[key] for key in ("id", "allowed_paths", "planned_commands")},
        )
        self.assertIn("read_paths", actual_slice)
        self.assertEqual(selected["allowed_paths"], issued["active_assignment"]["access"]["write"])
        self.assertEqual(selected["planned_commands"], issued["active_assignment"]["commands"])
        (self.root / target).write_text(text, encoding="utf-8")
        return self._complete(f"COMPLETE-{worker}", {"outcome": "pass", "summary": "Implemented slice"})

    def _configure_two_slices(self) -> None:
        (self.root / "slice-one.txt").write_text("old one\n", encoding="utf-8")
        (self.root / "slice-two.txt").write_text("old two\n", encoding="utf-8")
        self.slices = [
            {"id": "SLICE-1", "allowed_paths": ["slice-one.txt"], "planned_commands": [self.command]},
            {"id": "SLICE-2", "allowed_paths": ["slice-two.txt"], "planned_commands": [self.command]},
        ]
        state = self.store.load()
        self.store.dispatch({
            "name": "init", "id": "CMD-TWO-SLICES", "expected_generation": state["generation"],
            "run_id": state["run_id"], "project_root": state["project_root"],
            "authority": state["authority"], "slices": self._sealed(self.slices),
        })

    def _reach_docs_after_two_slices(self, suffix: str) -> None:
        self._reach_engineering(f"-{suffix}")
        for index, target in enumerate(("slice-one.txt", "slice-two.txt"), start=1):
            worker = f"{suffix}-s{index}"
            self._engineer_slice(
                f"engineer-{worker}", f"candidate {worker}\n",
                slice_index=index - 1, target=target,
            )
            self._accept(f"engineering-{worker}")
            self._review_pass(f"reviewer-{worker}")
            self._qa_pass(f"qa-{worker}")
        self.assertEqual("docs", self.store.load()["phase"])

    def _review_pass(self, worker: str) -> None:
        self._complete_readonly("review", worker, {"outcome": "pass", "findings": []})
        self._accept(worker)

    def _qa_pass(self, worker: str) -> dict:
        self._complete_readonly("qa", worker, {"outcome": "pass", "checks": ["acceptance: pass"]})
        return self._accept(worker)

    def _docs_no_change(self, worker: str) -> dict:
        self.controller.next(
            command_id=f"NEXT-{worker}",
            assignment={
                "id": f"ASSIGN-{worker}", "worker_id": worker, "task": "Confirm docs",
                "access": {"read": ["**"], "write": ["notes.md"]}, "commands": [],
            },
        )
        self._complete(f"COMPLETE-{worker}", {"outcome": "pass", "summary": "No documentation change required"})
        return self._accept(worker)

    def _resume_after_changed_docs_review_failure(
        self,
    ) -> tuple[dict, dict, dict, str]:
        retained_candidate = self._reach_candidate()
        self._review_pass("reviewer-before-docs-change")
        self._qa_pass("qa-before-docs-change")
        issued = self.controller.next(
            command_id="NEXT-docs-change-before-fail",
            assignment={
                "id": "ASSIGN-docs-change-before-fail",
                "worker_id": "docs-change-before-fail",
                "task": "Update accepted documentation",
            },
        )
        docs_path = self.root / issued["active_assignment"]["access"]["write"][0]
        docs_path.parent.mkdir(parents=True, exist_ok=True)
        docs_path.write_text("accepted documentation change\n", encoding="utf-8")
        completed_docs = self._complete(
            "COMPLETE-docs-change-before-fail",
            {"outcome": "pass", "summary": "Updated accepted documentation"},
        )
        docs_candidate = completed_docs["artifacts"]["docs"]["candidate"]
        self.assertGreater(docs_candidate["generation"], retained_candidate["generation"])
        self._accept("docs-change-before-fail")
        failed = self._complete_readonly(
            "review", "reviewer-after-docs-change-fail",
            {
                "outcome": "fail",
                "findings": [{
                    "text": "Release evidence is incomplete",
                    "severity": "P1",
                    "kind": "evidence",
                }],
            },
        )
        gate_id = next(
            key for key, item in failed["gates"].items() if item["status"] == "open"
        )
        resumed = self.controller.transition({
            "name": "resume", "id": "RESUME-review-after-docs-change-fail",
            "expected_generation": failed["generation"], "gate_id": gate_id,
            "resolution": "Add the missing release evidence",
        })
        self.assertEqual("engineering", resumed["phase"])
        self.assertEqual(retained_candidate, current_candidate(resumed))
        self.assertEqual(docs_candidate, resumed["gates"][gate_id]["candidate_base"])
        return resumed, retained_candidate, docs_candidate, gate_id

    def _resume_after_verification_and_nonpassing_engineering(
        self, verification_phase: str, engineering_outcome: str,
    ) -> tuple[dict, dict]:
        candidate = self._reach_candidate()
        if verification_phase == "qa":
            self._review_pass("reviewer-before-nonpassing-engineering")
            failed = self._complete_readonly(
                "qa", "qa-before-nonpassing-engineering",
                {"outcome": "fail", "checks": ["runtime: product failure"]},
            )
        else:
            failed = self._complete_readonly(
                "review", "reviewer-before-nonpassing-engineering",
                {
                    "outcome": "fail",
                    "findings": [{
                        "text": "Repair the candidate",
                        "severity": "P1",
                        "kind": "correctness",
                    }],
                },
            )
        verification_gate = next(
            key for key, item in failed["gates"].items() if item["status"] == "open"
        )
        self.controller.transition({
            "name": "resume", "id": "RESUME-verification-before-nonpassing-engineering",
            "expected_generation": failed["generation"], "gate_id": verification_gate,
            "resolution": "Repair the verification failure",
        })
        self.controller.next(
            command_id="NEXT-first-nonpassing-engineering",
            assignment={
                "id": "ASSIGN-first-nonpassing-engineering",
                "worker_id": "engineer-first-nonpassing-engineering",
                "task": "Attempt the verification repair",
            },
        )
        (self.root / "game.txt").write_text(
            f"allowed {engineering_outcome} repair bytes\n", encoding="utf-8",
        )
        completed = self._complete(
            "COMPLETE-first-nonpassing-engineering",
            {
                "outcome": engineering_outcome,
                "summary": f"Engineering {engineering_outcome} after allowed edits",
            },
        )
        engineering_gate = next(
            key for key, item in completed["gates"].items() if item["status"] == "open"
        )
        resumed = self.controller.transition({
            "name": "resume", "id": "RESUME-first-nonpassing-engineering",
            "expected_generation": completed["generation"], "gate_id": engineering_gate,
            "resolution": "Continue from the controller-validated allowed edits",
        })
        self.assertEqual("engineering", resumed["phase"])
        self.assertIsNone(resumed["active_assignment"])
        return resumed, candidate

    def _reach_candidate(self) -> dict:
        self._reach_engineering()
        completed = self._engineer("engineer-1", "candidate-1\n")
        self._accept("engineering-1")
        return completed["artifacts"]["engineering"]["candidate"]

    def _finish_ready(self, review: str, qa: str, docs: str) -> dict:
        self._review_pass(review)
        self._qa_pass(qa)
        terminal = self._docs_no_change(docs)
        ready = self.controller.ready(command_id=f"READY-{docs}", expected_generation=terminal["generation"])
        self.assertTrue(status_view(ready)["ready"])
        return ready

    def test_normal_run_reaches_ready_with_twelve_top_fields(self) -> None:
        self._reach_candidate()
        ready = self._finish_ready("reviewer-1", "qa-1", "docs-1")
        self.assertEqual(12, len(ready))
        self.assertEqual(7, len(PHASES)); self.assertEqual(9, len(COMMANDS))

    def test_public_dispatch_rejects_mapping_subclass_before_controller_guard(self) -> None:
        class GuardBypass(dict):
            def get(self, key, default=None):
                if key == "name":
                    return "accept"
                return super().get(key, default)

        issued = self.controller.next(
            command_id="FORGED-COMPLETE-NEXT",
            assignment={
                "id": "FORGED-COMPLETE-ASSIGNMENT", "worker_id": "forged-worker",
                "task": "Exercise the public dispatch boundary",
            },
        )
        active = issued["active_assignment"]
        snapshot = inventory(self.root)
        forged = GuardBypass({
            "name": "complete", "id": "FORGED-COMPLETE",
            "expected_generation": issued["generation"],
            "artifact": {"outcome": "pass", "summary": "forged"},
            "controller": {
                "authority_digest": issued["authority"]["digest"],
                "base_checkout_sha256": active["base"]["checkout_sha256"],
                "current_checkout_sha256": inventory_digest(snapshot),
                "inventory": snapshot, "diff": [], "diff_sha256": digest([]),
                "violations": [], "commands": [],
            },
        })
        before_state = self.store.path.read_bytes()
        before_checkout = inventory(self.root)

        with self.assertRaisesRegex(PipelineError, "plain JSON object"):
            self.store.dispatch(forged)

        self.assertEqual(before_state, self.store.path.read_bytes())
        self.assertEqual(before_checkout, inventory(self.root))
        self.assertNotIn("plan", self.store.load()["artifacts"])

    def test_public_controller_rejects_noncanonical_state_path_before_lock_or_state_mutation(self) -> None:
        external_path = self.root / "external-state.json"
        external_store = StateStore(external_path)
        external_controller = Controller(external_store)
        command = {
            "name": "init", "id": "EXTERNAL-STATE-INIT", "expected_generation": None,
            "run_id": "RUN-EXTERNAL", "project_root": str(self.root),
            "authority_paths": {
                "requirements": "requirements.md", "specification": "specification.md",
                "plan": "plan.md",
            },
            "slices": self.slices,
        }

        with self.assertRaisesRegex(PipelineError, "direct .json child"):
            external_controller.reconfigure(command)
        self.assertFalse(external_path.exists())
        self.assertFalse(external_store.lock_path.exists())

        original = self.store.path.read_bytes()
        external_path.write_bytes(original)
        with self.assertRaisesRegex(PipelineError, "direct .json child"):
            external_controller.status()
        self.assertEqual(original, external_path.read_bytes())
        self.assertFalse(external_store.lock_path.exists())

    def test_public_controller_allows_custom_json_state_inside_canonical_directory(self) -> None:
        custom_store = StateStore(
            self.root / ".agentic-pipeline-v2" / "custom-state.json",
        )
        custom_controller = Controller(custom_store)
        initialized = custom_controller.reconfigure({
            "name": "init", "id": "CUSTOM-STATE-INIT", "expected_generation": None,
            "run_id": "RUN-CUSTOM", "project_root": str(self.root),
            "authority_paths": {
                "requirements": "requirements.md", "specification": "specification.md",
                "plan": "plan.md",
            },
            "slices": self.slices,
        })

        self.assertEqual("plan", initialized["phase"])
        self.assertTrue(custom_store.path.is_file())
        self.assertEqual("next", custom_controller.status()["next_action"]["command"])

    def test_next_rejects_forged_controller_assignment_identity_and_cli_can_omit_it(self) -> None:
        for field in ("id", "worker_id", "task"):
            with self.subTest(field=field):
                harness = PipelineV2CoreTests("runTest")
                harness.setUp()
                try:
                    expected = default_assignment(harness.store.load())
                    forged = deepcopy(expected)
                    forged[field] = f"forged-{field}"
                    before = harness.store.path.read_bytes()
                    with self.assertRaisesRegex(PipelineError, "controller-derived"):
                        Controller(harness.store).next(
                            command_id=f"NEXT-FORGED-{field}", assignment=forged,
                        )
                    self.assertEqual(before, harness.store.path.read_bytes())
                finally:
                    harness.tearDown()

        action = self.controller.status()["next_action"]
        view = cli_run(cli_parser().parse_args([
            "--state", str(self.store.path), "next",
            "--id", action["command_id"],
            "--expected-generation", str(action["expected_generation"]),
        ]))
        active = view["active_assignment"]
        self.assertEqual(action["assignment"]["id"], active["id"])
        self.assertEqual(action["assignment"]["worker_id"], active["worker_id"])
        self.assertEqual(action["assignment"]["task"], active["task"])

    def test_first_next_rejects_forged_public_command_id_before_mutation(self) -> None:
        for include_identity in (False, True):
            with self.subTest(include_identity=include_identity):
                harness = PipelineV2CoreTests("runTest")
                harness.setUp()
                try:
                    controller = Controller(harness.store)
                    action = controller.status()["next_action"]
                    assignment = deepcopy(action["assignment"]) if include_identity else None
                    before = harness.store.path.read_bytes()

                    with self.assertRaisesRegex(
                        PipelineError,
                        "command ID is controller-derived and must match status.next_action",
                    ):
                        controller.next(
                            command_id=f"forged-{action['command_id']}",
                            assignment=assignment,
                            expected_generation=action["expected_generation"],
                        )

                    self.assertEqual(before, harness.store.path.read_bytes())
                    state = harness.store.load()
                    self.assertIsNone(state["active_assignment"])
                    self.assertEqual(action["expected_generation"], state["generation"])
                    self.assertFalse(any(
                        item.get("id") == f"forged-{action['command_id']}"
                        for item in state["history"]
                    ))
                finally:
                    harness.tearDown()

    def test_exact_next_cli_replay_is_a_byte_noop_with_omitted_or_exact_identity(self) -> None:
        for include_identity in (False, True):
            with self.subTest(include_identity=include_identity):
                harness = PipelineV2CoreTests("runTest")
                harness.setUp()
                try:
                    status_args = cli_parser().parse_args([
                        "--state", str(harness.store.path), "status",
                    ])
                    action = cli_run(status_args)["next_action"]
                    argv = [
                        "--state", str(harness.store.path), "next",
                        "--id", action["command_id"],
                        "--expected-generation", str(action["expected_generation"]),
                    ]
                    if include_identity:
                        assignment = action["assignment"]
                        argv += [
                            "--assignment-id", assignment["id"],
                            "--worker", assignment["worker_id"],
                            "--task", assignment["task"],
                        ]
                    parsed = cli_parser().parse_args(argv)
                    first = cli_run(parsed)
                    before = harness.store.path.read_bytes()
                    replay = cli_run(parsed)
                    self.assertEqual(first, replay)
                    self.assertEqual(before, harness.store.path.read_bytes())
                finally:
                    harness.tearDown()

    def test_pre_patch_review_next_replays_with_omitted_or_exact_identity(self) -> None:
        legacy_task = "Independently review the current candidate and report actionable findings."
        for include_identity in (False, True):
            with self.subTest(include_identity=include_identity):
                harness = PipelineV2CoreTests("runTest")
                harness.setUp()
                try:
                    harness._reach_candidate()
                    controller = Controller(harness.store)
                    action = controller.status()["next_action"]
                    identity = {
                        field: action["assignment"][field]
                        for field in ("id", "worker_id", "task")
                    }
                    self.assertEqual(legacy_task, identity["task"])
                    self.assertEqual(
                        ["game.txt"],
                        action["assignment"]["context"]["review_target"]["candidate_changes"],
                    )

                    issued = controller.next(
                        command_id=action["command_id"], assignment=identity,
                        expected_generation=action["expected_generation"],
                    )
                    history = issued["history"][-1]
                    self.assertEqual(
                        command_intent_digest({
                            "name": "next", "id": action["command_id"],
                            "assignment": identity,
                        }),
                        history["command_digest"],
                    )
                    before = harness.store.path.read_bytes()
                    replay = controller.next(
                        command_id=action["command_id"],
                        assignment=identity if include_identity else None,
                        expected_generation=-1,
                    )
                    self.assertEqual(issued, replay)
                    self.assertEqual(before, harness.store.path.read_bytes())
                finally:
                    harness.tearDown()

    def test_init_rejects_unsafe_run_ids_before_state_or_lock_mutation(self) -> None:
        for index, run_id in enumerate((".", "..", "../escape", "nested/run", r"nested\run")):
            with self.subTest(run_id=run_id):
                store = StateStore(
                    self.root / ".agentic-pipeline-v2" / f"invalid-run-{index}.json",
                )
                with self.assertRaisesRegex(PipelineError, "run_id.*safe identifier"):
                    Controller(store).reconfigure({
                        "name": "init", "id": f"INVALID-RUN-{index}",
                        "expected_generation": None, "run_id": run_id,
                        "project_root": str(self.root),
                        "authority_paths": {
                            "requirements": "requirements.md",
                            "specification": "specification.md", "plan": "plan.md",
                        },
                        "slices": self._sealed(self.slices),
                    })
                self.assertFalse(store.path.exists())
                self.assertFalse(store.lock_path.exists())

    def test_blocked_precandidate_phases_retain_environment_resolution_in_retry_capsule(self) -> None:
        for phase in ("plan", "slice", "engineering"):
            with self.subTest(phase=phase):
                harness = PipelineV2CoreTests("runTest")
                harness.setUp()
                try:
                    phases = ("plan", "slice", "engineering")
                    for prior in phases[:phases.index(phase)]:
                        action = harness.controller.status()["next_action"]
                        harness.controller.next(
                            command_id=action["command_id"],
                            expected_generation=action["expected_generation"],
                            assignment=action["assignment"],
                        )
                        harness._complete(
                            f"COMPLETE-{prior}",
                            {"outcome": "pass", "summary": f"{prior} accepted"},
                        )
                        accept = harness.controller.status()["next_action"]
                        harness.controller.transition({
                            "name": "accept", "id": accept["command_id"],
                            "expected_generation": accept["expected_generation"],
                        })

                    action = harness.controller.status()["next_action"]
                    harness.controller.next(
                        command_id=action["command_id"],
                        expected_generation=action["expected_generation"],
                        assignment=action["assignment"],
                    )
                    harness._complete(
                        f"COMPLETE-BLOCKED-{phase}",
                        {"outcome": "blocked", "summary": "WSL unavailable; do not retry unchanged"},
                    )
                    resume = harness.controller.status()["next_action"]
                    harness.controller.transition({
                        "name": "resume", "id": resume["command_id"],
                        "expected_generation": resume["expected_generation"],
                        "gate_id": resume["gate_id"],
                        "resolution": "Use recorded portable environment; capability unchanged",
                    })
                    retry = harness.controller.status()["next_action"]
                    issued = harness.controller.next(
                        command_id=retry["command_id"],
                        expected_generation=retry["expected_generation"],
                        assignment=retry["assignment"],
                    )
                    remediation = issued["active_assignment"]["capsule"]["context"]["remediation"]
                    self.assertEqual(1, len(remediation))
                    self.assertEqual(phase, remediation[0]["phase"])
                    self.assertIn("do not retry unchanged", remediation[0]["worker_artifact"]["summary"])
                    self.assertIn("capability unchanged", remediation[0]["resolution"])
                finally:
                    harness.tearDown()

    def test_public_dispatch_rejects_nested_mutable_subclasses_without_mutation(self) -> None:
        class NestedMapping(dict):
            pass

        class NestedList(list):
            pass

        before_state = self.store.path.read_bytes()
        before_checkout = inventory(self.root)
        for nested in (NestedMapping({"value": "mutable"}), NestedList(["mutable"])):
            with self.subTest(nested=type(nested).__name__):
                with self.assertRaisesRegex(PipelineError, "plain JSON values"):
                    self.store.dispatch({"name": "status", "intent": nested})
                self.assertEqual(before_state, self.store.path.read_bytes())
                self.assertEqual(before_checkout, inventory(self.root))

    def test_public_dispatch_uses_one_detached_command_snapshot_for_reduce(self) -> None:
        original = {"name": "status", "intent": {"items": ["plain"]}}
        snapshots = []
        real_canonical = transaction_module.canonical_command

        def tracked_canonical(command):
            snapshot = real_canonical(command)
            snapshots.append(snapshot)
            return snapshot

        def tracked_reduce(state, command):
            snapshots.append(command)
            return reduce(state, command)

        with (
            mock.patch.object(transaction_module, "canonical_command", side_effect=tracked_canonical),
            mock.patch.object(transaction_module, "reduce", side_effect=tracked_reduce),
        ):
            self.store.dispatch(original)

        self.assertEqual(2, len(snapshots))
        self.assertIs(snapshots[0], snapshots[1])
        self.assertIsNot(original, snapshots[0])
        self.assertIsNot(original["intent"], snapshots[0]["intent"])

    def test_precondition_proof_cannot_be_minted_without_validation(self) -> None:
        state = self.store.load()
        stale = {
            "name": "accept", "id": "STALE-PROOF",
            "expected_generation": state["generation"] + 1,
        }
        missing_id = {"name": "accept", "expected_generation": state["generation"]}

        with self.assertRaisesRegex(ConflictError, "stale generation"):
            reducer_module._precondition_proof(state, stale)
        with self.assertRaisesRegex(PipelineError, "command id is required"):
            reducer_module._precondition_proof(state, missing_id)

    def test_two_slices_each_require_fresh_engineering_review_and_qa_before_docs(self) -> None:
        self._configure_two_slices()
        self._reach_engineering("-multi")
        self._engineer_slice("engineer-s1", "candidate one\n", slice_index=0, target="slice-one.txt")
        self._accept("engineering-s1")
        failed_first_review = self._complete_readonly("review", "reviewer-s1-fail", {
            "outcome": "fail",
            "findings": [{"text": "repair slice one", "severity": "high", "kind": "correctness"}],
        })
        first_gate = next(key for key, item in failed_first_review["gates"].items() if item["status"] == "open")
        self.store.dispatch({
            "name": "resume", "id": "RESUME-S1-REVIEW",
            "expected_generation": failed_first_review["generation"],
            "gate_id": first_gate, "resolution": "repair the first slice",
        })
        self._engineer_slice("engineer-s1-fix", "candidate one repaired\n", slice_index=0, target="slice-one.txt")
        self._accept("engineering-s1-fix")
        self._review_pass("reviewer-s1")
        after_first_qa = self._qa_pass("qa-s1")

        self.assertEqual("engineering", after_first_qa["phase"])
        self.assertEqual(12, len(after_first_qa))
        self.assertNotIn("current_slice", after_first_qa)
        self.assertEqual(7, len(PHASES)); self.assertEqual(9, len(COMMANDS))

        self._engineer_slice("engineer-s2", "candidate two\n", slice_index=1, target="slice-two.txt")
        self._accept("engineering-s2")
        failed_review = self._complete_readonly("review", "reviewer-s2-fail", {
            "outcome": "fail",
            "findings": [{"text": "repair slice two", "severity": "high", "kind": "correctness"}],
        })
        review_gate = next(key for key, item in failed_review["gates"].items() if item["status"] == "open")
        resumed_review = self.store.dispatch({
            "name": "resume", "id": "RESUME-S2-REVIEW", "expected_generation": failed_review["generation"],
            "gate_id": review_gate, "resolution": "repair the second slice",
        })
        self.assertEqual("SLICE-2", current_slice(resumed_review)["id"])
        self._engineer_slice("engineer-s2-review-fix", "review fixed\n", slice_index=1, target="slice-two.txt")
        self._accept("engineering-s2-review-fix")
        self._review_pass("reviewer-s2-pass")
        failed_qa = self._complete_readonly("qa", "qa-s2-fail", {"outcome": "fail", "checks": ["runtime: fail"]})
        qa_gate = next(key for key, item in failed_qa["gates"].items() if item["status"] == "open")
        resumed_qa = self.store.dispatch({
            "name": "resume", "id": "RESUME-S2-QA", "expected_generation": failed_qa["generation"],
            "gate_id": qa_gate, "resolution": "repair the second slice again",
        })
        self.assertEqual("SLICE-2", current_slice(resumed_qa)["id"])
        self._engineer_slice("engineer-s2-qa-fix", "qa fixed\n", slice_index=1, target="slice-two.txt")
        self._accept("engineering-s2-qa-fix")
        self._review_pass("reviewer-s2-final")
        self._qa_pass("qa-s2-pass")
        terminal = self._docs_no_change("docs-multi")
        ready = self.controller.ready(command_id="READY-MULTI", expected_generation=terminal["generation"])
        self.assertTrue(status_view(ready)["ready"])
        self.assertEqual(12, len(ready))

    def test_next_slice_rejects_tampering_with_the_accepted_slice_surface(self) -> None:
        self._configure_two_slices()
        self._reach_engineering("-accepted-baseline")
        self._engineer_slice(
            "engineer-accepted-s1", "accepted slice one\n",
            slice_index=0, target="slice-one.txt",
        )
        self._accept("engineering-accepted-s1")
        self._review_pass("reviewer-accepted-s1")
        after_first_qa = self._qa_pass("qa-accepted-s1")
        accepted_candidate = current_candidate(after_first_qa)
        self.assertIsNotNone(accepted_candidate)

        clean_action = self.controller.status()["next_action"]
        self.assertEqual("next", clean_action["command"])
        self.assertEqual("SLICE-2", current_slice(after_first_qa)["id"])
        (self.root / "slice-one.txt").write_text("tampered sealed slice one\n", encoding="utf-8")
        before = self.store.path.read_bytes()

        view = self.controller.status()
        self.assertEqual("terminal", view["next_action"]["kind"])
        self.assertEqual("checkout_recovery_required", view["next_action"]["result"])
        self.assertIn("slice-one.txt", view["next_action"]["reason"])
        with self.assertRaisesRegex(PipelineError, "checkout drifted"):
            self.controller.next(
                command_id=clean_action["command_id"],
                expected_generation=clean_action["expected_generation"],
                assignment=clean_action["assignment"],
            )
        self.assertEqual(before, self.store.path.read_bytes())

        (self.root / "slice-one.txt").write_text("accepted slice one\n", encoding="utf-8")
        issued = self.controller.next(
            command_id=clean_action["command_id"],
            expected_generation=clean_action["expected_generation"],
            assignment=clean_action["assignment"],
        )
        active = issued["active_assignment"]
        self.assertEqual(accepted_candidate, active["capsule"]["candidate"])
        self.assertEqual(
            accepted_candidate["checkout_sha256"], active["base"]["checkout_sha256"],
        )
        self.assertEqual(
            ["slice-one.txt", "slice-two.txt"],
            [path for path in active["access"]["read"] if path.startswith("slice-")],
        )
        self.assertEqual(["slice-two.txt"], active["access"]["write"])

    def test_later_slice_integrated_checks_receive_cumulative_read_and_current_write(self) -> None:
        (self.root / "src").mkdir()
        (self.root / "tests" / "foundation").mkdir(parents=True)
        (self.root / "src" / "levels.js").write_text("export const levels = [1];\n", encoding="utf-8")
        (self.root / "src" / "config.js").write_text("export const shared = 1;\n", encoding="utf-8")
        (self.root / "src" / "future.js").write_text("future slice\n", encoding="utf-8")
        (self.root / "tests" / "foundation" / "winnable.test.js").write_text(
            "// the integrated check depends on the sealed level generator\n", encoding="utf-8",
        )
        integrated_check = [
            sys.executable, "-c",
            (
                "from pathlib import Path; "
                "assert Path('src/levels.js').read_text(); "
                "assert Path('tests/foundation/winnable.test.js').read_text(); "
                "assert 'shared = 2' in Path('src/config.js').read_text()"
            ),
        ]
        self.slices = [
            {
                "id": "SLICE-FOUNDATION",
                "allowed_paths": ["src/levels.js", "tests/foundation/**"],
                "planned_commands": [self.command],
            },
            {
                "id": "SLICE-INTEGRATION",
                "allowed_paths": ["src/config.js"],
                "planned_commands": [integrated_check],
            },
            {
                "id": "SLICE-FUTURE",
                "allowed_paths": ["src/future.js"],
                "planned_commands": [self.command],
            },
        ]
        scoped_reads = {
            "SLICE-FOUNDATION": ["src/foundation-bootstrap.js"],
            "SLICE-INTEGRATION": ["src/integration-reference.js"],
            "SLICE-FUTURE": ["src/future-reference.js"],
        }
        state = self.store.load()
        self.store.dispatch({
            "name": "init", "id": "CONFIGURE-INTEGRATED-READ",
            "expected_generation": state["generation"], "run_id": state["run_id"],
            "project_root": state["project_root"], "authority": state["authority"],
            "slices": self._sealed(self.slices, scoped_reads),
        })
        self._reach_engineering("-integrated-read")
        self._engineer_slice(
            "engineer-foundation", "export const levels = [1, 2];\n",
            slice_index=0, target="src/levels.js",
        )
        self._accept("engineering-foundation")
        self._review_pass("reviewer-foundation")
        self._qa_pass("qa-foundation")

        authority_paths = [item["path"] for item in self.store.load()["authority"]["items"].values()]
        expected_read = authority_paths + [
            "src/levels.js", "tests/foundation/**", "src/foundation-bootstrap.js",
            "src/config.js", "src/integration-reference.js",
        ]

        def issue_and_assert(phase: str, worker: str) -> dict:
            self.assertEqual(phase, self.store.load()["phase"])
            expected = status_view(self.store.load())["next_action"]["assignment"]
            self.assertEqual(expected_read, expected["access"]["read"])
            self.assertNotIn("src/future.js", expected["access"]["read"])
            self.assertNotIn("src/future-reference.js", expected["access"]["read"])
            issued = self.controller.next(
                command_id=f"NEXT-{worker}",
                assignment={
                    "id": f"ASSIGN-{worker}", "worker_id": worker,
                    "task": f"Complete integrated {phase}",
                },
            )["active_assignment"]
            self.assertEqual(expected_read, issued["access"]["read"])
            return issued

        engineering = issue_and_assert("engineering", "engineer-integration")
        self.assertEqual(["src/config.js"], engineering["access"]["write"])
        self.assertEqual([integrated_check], engineering["commands"])
        (self.root / "src" / "config.js").write_text("export const shared = 2;\n", encoding="utf-8")
        self._complete("COMPLETE-engineer-integration", {"outcome": "pass", "summary": "Updated shared config"})
        self._accept("engineering-integration")

        review = issue_and_assert("review", "reviewer-integration")
        self.assertEqual([], review["access"]["write"])
        review_target = review["capsule"]["context"]["review_target"]
        self.assertEqual(
            {
                "kind": "current_slice_implementation",
                "slice_id": "SLICE-INTEGRATION",
                "required_scope": ["src/config.js"],
                "candidate_changes": ["src/config.js"],
            },
            review_target,
        )
        self.assertLess(
            len(json.dumps(review_target, separators=(",", ":")).encode("utf-8")),
            192,
        )
        self.assertEqual(["src/config.js"], review["capsule"]["context"]["current_slice"]["allowed_paths"])
        self.assertIn("src/levels.js", review["access"]["read"])
        self.assertIn("src/integration-reference.js", review["access"]["read"])
        self.assertNotIn("src/future.js", review["access"]["read"])
        self._complete("COMPLETE-reviewer-integration", {"outcome": "pass", "findings": []})
        self._accept("reviewer-integration")

        qa = issue_and_assert("qa", "qa-integration")
        self.assertEqual([], qa["access"]["write"])
        self.assertEqual([integrated_check], qa["commands"])

    def test_broad_required_scope_keeps_untouched_paths_out_of_candidate_changes(self) -> None:
        (self.root / "src").mkdir()
        (self.root / "src" / "changed.luau").write_text("return 1\n", encoding="utf-8")
        (self.root / "src" / "untouched.luau").write_text("return 2\n", encoding="utf-8")
        self.slices = [{
            "id": "SLICE-BROAD",
            "allowed_paths": ["src/**"],
            "planned_commands": [self.command],
        }]
        state = self.store.load()
        self.store.dispatch({
            "name": "init", "id": "CONFIGURE-BROAD-REVIEW-TARGET",
            "expected_generation": state["generation"], "run_id": state["run_id"],
            "project_root": state["project_root"], "authority": state["authority"],
            "slices": self._sealed(self.slices),
        })
        self._reach_engineering("-broad-review-target")
        self._engineer_slice(
            "engineer-broad-review-target", "return 3\n",
            slice_index=0, target="src/changed.luau",
        )
        self._accept("engineering-broad-review-target")

        assignment = self.controller.status()["next_action"]["assignment"]
        self.assertEqual(
            {
                "kind": "current_slice_implementation",
                "slice_id": "SLICE-BROAD",
                "required_scope": ["src/**"],
                "candidate_changes": ["src/changed.luau"],
            },
            assignment["context"]["review_target"],
        )
        self.assertNotIn(
            "src/untouched.luau",
            assignment["context"]["review_target"]["candidate_changes"],
        )

    def test_old_scope_status_projects_exact_init_and_replay_seals_plan_reads(self) -> None:
        legacy = self.store.load()
        for item in legacy["slices"]:
            item.pop("read_paths")
        self.store.path.write_text(
            json.dumps(legacy, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        self._write_approved_plan(
            self.slices,
            reads={"SLICE-1": ["game.txt", "src/bootstrap.js", "game.txt"]},
            revision=2,
        )
        before = self.store.path.read_bytes()

        action = self.controller.status()["next_action"]
        self.assertEqual("init", action["command"])
        self.assertFalse(action["user_input_required"])
        self.assertIn("scope binding", action["reason"])
        self.assertEqual(
            ["game.txt", "src/bootstrap.js"], action["slices"][0]["read_paths"],
        )
        self.assertEqual(before, self.store.path.read_bytes())
        with self.assertRaisesRegex(PipelineError, "authority bytes changed|read scope is not sealed"):
            self.controller.next(command_id="NEXT-LEGACY-SCOPE")
        self.assertEqual(before, self.store.path.read_bytes())

        command = {
            "name": "init", "id": action["command_id"],
            "expected_generation": action["expected_generation"],
            "run_id": action["run_id"], "project_root": action["project_root"],
            "authority_paths": action["authority"], "slices": action["slices"],
        }
        sealed = self.controller.reconfigure(command)
        persisted = self.store.path.read_bytes()
        self.assertEqual(action["slices"], sealed["slices"])
        self.assertEqual(sealed, self.controller.reconfigure(command))
        self.assertEqual(persisted, self.store.path.read_bytes())

    def test_controller_rejects_read_scope_smuggling_and_adversarial_plan_paths(self) -> None:
        self._complete_readonly(
            "plan", "planner-read-scope", {"outcome": "pass", "summary": "Plan confirmed"},
        )
        self._accept("plan-read-scope")
        self.controller.next(command_id="NEXT-SLICER-READ-SCOPE")
        self._write_artifact({
            "outcome": "pass", "summary": "Attempted read smuggle",
            "slices": self._sealed(self.slices, {"SLICE-1": ["secret/**"]}),
        })
        before = self.store.path.read_bytes()
        with self.assertRaisesRegex(PipelineError, "requires exactly id, allowed_paths, and planned_commands"):
            self.controller.complete(command_id="COMPLETE-SLICER-READ-SCOPE")
        self.assertEqual(before, self.store.path.read_bytes())

        cases = {
            "bare glob": "**",
            "absolute": "/outside",
            "drive": "C:/outside",
            "parent": "../outside",
            "embedded glob": "src/*/file",
            "nonterminal recursive glob": "src/**/file",
            "control": "src/bad\x01file",
        }
        for label, invalid in cases.items():
            with self.subTest(label=label):
                self.store.path.unlink(missing_ok=True)
                self._write_approved_plan(
                    self.slices, reads={"SLICE-1": [invalid]}, revision=3,
                )
                with self.assertRaisesRegex(PipelineError, "cannot seal approved plan read scopes"):
                    self.controller.reconfigure({
                        "name": "init", "id": f"INIT-{label}",
                        "expected_generation": None, "run_id": "RUN-TEST",
                        "project_root": str(self.root),
                        "authority_paths": {
                            "requirements": "requirements.md",
                            "specification": "specification.md", "plan": "plan.md",
                        },
                        "slices": self.slices,
                    })
                self.assertFalse(self.store.path.exists())

        self._write_approved_plan(
            [{**self.slices[0], "id": "SLICE-UNKNOWN"}], revision=4,
        )
        with self.assertRaisesRegex(PipelineError, "missing=.*SLICE-1.*unknown=.*SLICE-UNKNOWN"):
            self.controller.reconfigure({
                "name": "init", "id": "INIT-UNKNOWN-SLICE", "expected_generation": None,
                "run_id": "RUN-TEST", "project_root": str(self.root),
                "authority_paths": {
                    "requirements": "requirements.md", "specification": "specification.md",
                    "plan": "plan.md",
                },
                "slices": self.slices,
            })
        self.assertFalse(self.store.path.exists())

        self._write_approved_plan([self.slices[0], deepcopy(self.slices[0])], revision=5)
        with self.assertRaisesRegex(PipelineError, "repeats slice ID"):
            self.controller.reconfigure({
                "name": "init", "id": "INIT-DUPLICATE-SLICE", "expected_generation": None,
                "run_id": "RUN-TEST", "project_root": str(self.root),
                "authority_paths": {
                    "requirements": "requirements.md", "specification": "specification.md",
                    "plan": "plan.md",
                },
                "slices": self.slices,
            })
        self.assertFalse(self.store.path.exists())

    def test_blocked_stale_assignment_publicly_resumes_with_fresh_cumulative_read(self) -> None:
        (self.root / "src").mkdir()
        (self.root / "tests" / "foundation").mkdir(parents=True)
        (self.root / "src" / "levels.js").write_text("sealed\n", encoding="utf-8")
        (self.root / "src" / "config.js").write_text("shared\n", encoding="utf-8")
        (self.root / "tests" / "foundation" / "winnable.test.js").write_text("sealed test\n", encoding="utf-8")
        failing_check = [sys.executable, "-c", "raise SystemExit(17)"]
        self.slices = [
            {
                "id": "SLICE-FOUNDATION",
                "allowed_paths": ["src/levels.js", "tests/foundation/**"],
                "planned_commands": [self.command],
            },
            {
                "id": "SLICE-INTEGRATION",
                "allowed_paths": ["src/config.js"],
                "planned_commands": [failing_check],
            },
        ]
        state = self.store.load()
        self.store.dispatch({
            "name": "init", "id": "CONFIGURE-STALE-RECOVERY",
            "expected_generation": state["generation"], "run_id": state["run_id"],
            "project_root": state["project_root"], "authority": state["authority"],
            "slices": self._sealed(self.slices),
        })
        self._reach_engineering("-stale-recovery")
        self._engineer_slice(
            "engineer-recovery-foundation", "sealed foundation\n",
            slice_index=0, target="src/levels.js",
        )
        self._accept("engineering-recovery-foundation")
        self._review_pass("reviewer-recovery-foundation")
        self._qa_pass("qa-recovery-foundation")

        state = self.store.load()
        current = current_slice(state)
        authority_paths = [item["path"] for item in state["authority"]["items"].values()]
        stale = deepcopy(status_view(state)["next_action"]["assignment"])
        stale["access"]["read"] = authority_paths + current["allowed_paths"]
        with mock.patch("pipeline_v2.reducer.default_assignment", return_value=stale):
            issued = self.controller.next(
                command_id="NEXT-STALE-INTEGRATION",
                assignment={
                    "id": "ASSIGN-STALE-INTEGRATION", "worker_id": "engineer-stale-integration",
                    "task": "Complete integration with the pre-upgrade read scope",
                },
            )["active_assignment"]
        self.assertNotIn("src/levels.js", issued["access"]["read"])
        self.assertNotIn("tests/foundation/**", issued["access"]["read"])

        blocked = self._complete("COMPLETE-STALE-INTEGRATION", {
            "outcome": "blocked",
            "summary": "The assigned check depends on sealed prior-slice files outside read scope",
        })
        command_evidence = blocked["artifacts"]["engineering"]["controller"]["commands"]
        self.assertEqual([failing_check], [item["argv"] for item in command_evidence])
        self.assertEqual([17], [item["returncode"] for item in command_evidence])
        self.assertEqual(
            {
                "argv", "returncode", "stdout_sha256", "stderr_sha256",
                "stderr_excerpt", "stderr_excerpt_truncated",
                "stderr_excerpt_redacted",
            },
            set(command_evidence[0]),
        )
        gate_id = next(key for key, item in blocked["gates"].items() if item["status"] == "open")
        before_rejected_accept = self.store.path.read_bytes()
        with self.assertRaisesRegex(PipelineError, "cannot accept"):
            self.store.dispatch({
                "name": "accept", "id": "ACCEPT-BLOCKED-STALE",
                "expected_generation": blocked["generation"],
            })
        self.assertEqual(before_rejected_accept, self.store.path.read_bytes())
        resume_action = status_view(blocked)["next_action"]
        self.assertEqual("resume", resume_action["command"])
        resumed = self.store.dispatch({
            "name": "resume", "id": resume_action["command_id"],
            "expected_generation": resume_action["expected_generation"],
            "gate_id": gate_id, "resolution": "Retry under the controller-derived integrated read scope",
        })
        self.assertEqual("engineering", resumed["phase"])
        self.assertIsNone(resumed["active_assignment"])

        fresh = status_view(resumed)["next_action"]["assignment"]
        self.assertEqual(
            authority_paths + ["src/levels.js", "tests/foundation/**", "src/config.js"],
            fresh["access"]["read"],
        )
        self.assertEqual(["src/config.js"], fresh["access"]["write"])
        self.assertEqual([failing_check], fresh["checks"])

    def test_nonzero_planned_check_with_pass_persists_controller_gate_without_credit(self) -> None:
        failing_check = [sys.executable, "-c", "raise SystemExit(19)"]
        self.slices = [{
            "id": "SLICE-FAILING-PASS",
            "allowed_paths": ["game.txt"],
            "planned_commands": [failing_check],
        }]
        state = self.store.load()
        self.store.dispatch({
            "name": "init", "id": "CONFIGURE-FAILING-PASS",
            "expected_generation": state["generation"], "run_id": state["run_id"],
            "project_root": state["project_root"], "authority": state["authority"],
            "slices": self._sealed(self.slices),
        })
        self._reach_engineering("-failing-pass")
        self.controller.next(
            command_id="NEXT-FAILING-PASS",
            assignment={
                "id": "ASSIGN-FAILING-PASS",
                "worker_id": "engineer-failing-pass",
                "task": "Exercise a nonzero planned check",
            },
        )
        self._write_artifact({"outcome": "pass", "summary": "Implementation claimed complete"})
        before_generation = self.store.load()["generation"]
        completed = self.controller.complete(command_id="COMPLETE-FAILING-PASS")

        self.assertEqual(before_generation + 1, completed["generation"])
        self.assertIsNone(completed["active_assignment"])
        record = completed["artifacts"]["engineering"]
        self.assertEqual(
            {"outcome": "pass", "summary": "Implementation claimed complete"},
            record["worker"],
        )
        self.assertNotIn("candidate", record)
        self.assertEqual(19, record["controller"]["commands"][0]["returncode"])
        gate_id = next(
            key for key, item in completed["gates"].items()
            if item["status"] == "open"
        )
        self.assertEqual("controller_result", completed["gates"][gate_id]["kind"])
        self.assertEqual("fail", completed["gates"][gate_id]["reason"])
        self.assertEqual("resume", status_view(completed)["next_action"]["command"])
        persisted = self.store.path.read_bytes()
        with mock.patch("pipeline_v2.runner.run_process_tree") as rerun:
            self.assertEqual(
                completed,
                self.controller.complete(command_id="COMPLETE-FAILING-PASS"),
            )
        rerun.assert_not_called()
        self.assertEqual(persisted, self.store.path.read_bytes())

        resumed = self.controller.transition({
            "name": "resume", "id": "RESUME-FAILING-PASS",
            "expected_generation": completed["generation"], "gate_id": gate_id,
            "resolution": "Repair the controller-owned check failure",
        })
        self.assertEqual("engineering", resumed["phase"])
        self.assertEqual("next", status_view(resumed)["next_action"]["command"])

    def test_nonzero_planned_check_with_fail_persists_gate_and_resumes(self) -> None:
        failing_check = [sys.executable, "-c", "raise SystemExit(19)"]
        self.slices = [{
            "id": "SLICE-FAILING-OUTCOME",
            "allowed_paths": ["game.txt"],
            "planned_commands": [failing_check],
        }]
        state = self.store.load()
        self.store.dispatch({
            "name": "init", "id": "CONFIGURE-FAILING-OUTCOME",
            "expected_generation": state["generation"], "run_id": state["run_id"],
            "project_root": state["project_root"], "authority": state["authority"],
            "slices": self._sealed(self.slices),
        })
        self._reach_engineering("-failing-outcome")
        self.controller.next(
            command_id="NEXT-FAILING-OUTCOME",
            assignment={
                "id": "ASSIGN-FAILING-OUTCOME",
                "worker_id": "engineer-failing-outcome",
                "task": "Report the failed controller check",
            },
        )

        failed = self._complete(
            "COMPLETE-FAILING-OUTCOME",
            {"outcome": "fail", "summary": "The planned check failed"},
        )

        evidence = failed["artifacts"]["engineering"]["controller"]["commands"]
        self.assertEqual([19], [item["returncode"] for item in evidence])
        gate_id = next(key for key, item in failed["gates"].items() if item["status"] == "open")
        resumed = self.controller.transition({
            "name": "resume", "id": "RESUME-FAILING-OUTCOME",
            "expected_generation": failed["generation"], "gate_id": gate_id,
            "resolution": "Retry Engineering after the failed check is repaired",
        })
        self.assertEqual("engineering", resumed["phase"])
        self.assertIsNone(resumed["active_assignment"])

    def test_nonzero_qa_fail_routes_to_engineering_rework(self) -> None:
        failing_check = [sys.executable, "-c", "raise SystemExit(29)"]
        self.slices = [{
            "id": "SLICE-QA-FAIL",
            "allowed_paths": ["game.txt"],
            "planned_commands": [failing_check],
        }]
        state = self.store.load()
        self.store.dispatch({
            "name": "init", "id": "CONFIGURE-QA-FAIL",
            "expected_generation": state["generation"], "run_id": state["run_id"],
            "project_root": state["project_root"], "authority": state["authority"],
            "slices": self._sealed(self.slices),
        })
        with mock.patch(
            "pipeline_v2.runner.run_process_tree",
            side_effect=(
                ProcessEvidence(0, digest("engineering-out"), digest("engineering-err")),
                ProcessEvidence(29, digest("qa-out"), digest("qa-err")),
            ),
        ):
            self._reach_candidate()
            self._review_pass("reviewer-before-nonzero-qa")
            failed = self._complete_readonly(
                "qa", "qa-nonzero-fail",
                {"outcome": "fail", "checks": ["planned acceptance check returned 29"]},
            )
        gate_id = next(key for key, item in failed["gates"].items() if item["status"] == "open")
        resumed = self.controller.transition({
            "name": "resume", "id": "RESUME-NONZERO-QA-FAIL",
            "expected_generation": failed["generation"], "gate_id": gate_id,
            "resolution": "Repair the QA failure",
        })

        self.assertEqual("engineering", resumed["phase"])
        self.assertNotIn("review", resumed["artifacts"])
        self.assertNotIn("qa", resumed["artifacts"])

    def test_nonzero_qa_check_with_worker_pass_routes_to_engineering_rework(self) -> None:
        failing_check = [sys.executable, "-c", "raise SystemExit(37)"]
        self.slices = [{
            "id": "SLICE-QA-CONTROLLER-FAIL",
            "allowed_paths": ["game.txt"],
            "planned_commands": [failing_check],
        }]
        state = self.store.load()
        self.store.dispatch({
            "name": "init", "id": "CONFIGURE-QA-CONTROLLER-FAIL",
            "expected_generation": state["generation"], "run_id": state["run_id"],
            "project_root": state["project_root"], "authority": state["authority"],
            "slices": self._sealed(self.slices),
        })
        with mock.patch(
            "pipeline_v2.runner.run_process_tree",
            side_effect=(
                ProcessEvidence(0, digest("engineering-out"), digest("engineering-err")),
                ProcessEvidence(37, digest("qa-out"), digest("qa-err"), b"qa failed"),
            ),
        ):
            self._reach_candidate()
            self._review_pass("reviewer-before-controller-qa-fail")
            failed = self._complete_readonly(
                "qa", "qa-controller-fail",
                {"outcome": "pass", "checks": ["worker inspection passed"]},
            )
        gate_id = next(
            key for key, item in failed["gates"].items()
            if item["status"] == "open"
        )
        self.assertEqual("controller_result", failed["gates"][gate_id]["kind"])
        self.assertEqual("pass", failed["artifacts"]["qa"]["worker"]["outcome"])
        resumed = self.controller.transition({
            "name": "resume", "id": "RESUME-QA-CONTROLLER-FAIL",
            "expected_generation": failed["generation"], "gate_id": gate_id,
            "resolution": "Repair the failing QA command",
        })
        self.assertEqual("engineering", resumed["phase"])
        self.assertIn("engineering", resumed["artifacts"])
        self.assertNotIn("review", resumed["artifacts"])
        self.assertNotIn("qa", resumed["artifacts"])

        engineering_action = status_view(resumed)["next_action"]
        self.assertEqual("next", engineering_action.get("command"), engineering_action)
        self.controller.next(
            command_id=engineering_action["command_id"],
            assignment=engineering_action["assignment"],
        )
        (self.root / "game.txt").write_text(
            "allowed remediation before controller failure\n", encoding="utf-8",
        )
        remediation_artifact = self._write_artifact({
            "outcome": "pass", "summary": "Remediation implemented",
        })
        with mock.patch(
            "pipeline_v2.runner.run_process_tree",
            return_value=ProcessEvidence(
                41, digest("remediation-out"), digest("remediation-err"),
                b"remediation check failed",
            ),
        ):
            remediation_failed = self.controller.complete(
                command_id="COMPLETE-CONTROLLER-FAILED-REMEDIATION",
                artifact_path=remediation_artifact,
            )
        remediation_gate = self.controller.status()["next_action"]["gate_id"]
        retried = self.controller.transition({
            "name": "resume", "id": "RESUME-CONTROLLER-FAILED-REMEDIATION",
            "expected_generation": remediation_failed["generation"],
            "gate_id": remediation_gate,
            "resolution": "Retry from the newest non-passing Engineering inventory",
        })
        retry_action = status_view(retried)["next_action"]
        retried = self.controller.next(
            command_id=retry_action["command_id"], assignment=retry_action["assignment"],
        )
        self.assertEqual(
            inventory_digest(inventory(self.root)),
            retried["active_assignment"]["base"]["checkout_sha256"],
        )

    def test_fail_fast_runs_only_through_first_failure_or_the_full_success_plan(self) -> None:
        cases = (
            ("first", [31, 0, 0], [31]),
            ("second", [0, 23, 0], [0, 23]),
            ("all-pass", [0, 0, 0], [0, 0, 0]),
        )
        for label, available_codes, expected_codes in cases:
            with self.subTest(label=label):
                harness = PipelineV2CoreTests("runTest")
                harness.setUp()
                try:
                    commands = [
                        [sys.executable, "-c", f"raise SystemExit({index})"]
                        for index in range(len(available_codes))
                    ]
                    harness.slices = [{
                        "id": f"SLICE-FAIL-FAST-{label.upper()}",
                        "allowed_paths": ["game.txt"],
                        "planned_commands": commands,
                    }]
                    current = harness.store.load()
                    harness.store.dispatch({
                        "name": "init", "id": f"CONFIGURE-FAIL-FAST-{label.upper()}",
                        "expected_generation": current["generation"],
                        "run_id": current["run_id"],
                        "project_root": current["project_root"],
                        "authority": current["authority"],
                        "slices": harness._sealed(harness.slices),
                    })
                    harness._reach_engineering(f"-fail-fast-{label}")
                    harness.controller.next(
                        command_id=f"NEXT-FAIL-FAST-{label.upper()}",
                        assignment={
                            "id": f"ASSIGN-FAIL-FAST-{label.upper()}",
                            "worker_id": f"engineer-fail-fast-{label}",
                            "task": "Exercise fail-fast command execution",
                        },
                    )
                    artifact = harness._write_artifact({
                        "outcome": "pass", "summary": "Worker completed",
                    })
                    effects = [
                        ProcessEvidence(
                            code, digest(f"stdout-{index}"), digest(f"stderr-{index}"),
                            f"failure-{code}".encode() if code else b"",
                        )
                        for index, code in enumerate(available_codes)
                    ]
                    with mock.patch(
                        "pipeline_v2.runner.run_process_tree", side_effect=effects,
                    ) as invoked:
                        completed = harness.controller.complete(
                            command_id=f"COMPLETE-FAIL-FAST-{label.upper()}",
                            artifact_path=artifact,
                        )
                    evidence = completed["artifacts"]["engineering"]["controller"]["commands"]
                    self.assertEqual(expected_codes, [item["returncode"] for item in evidence])
                    self.assertEqual(len(expected_codes), invoked.call_count)
                    self.assertEqual(
                        bool(expected_codes[-1]),
                        any(item["status"] == "open" for item in completed["gates"].values()),
                    )
                finally:
                    harness.tearDown()

    def test_reducer_rejects_forged_command_prefixes_and_accepts_legacy_failure_shape(self) -> None:
        self.slices = [{
            "id": "SLICE-FORGED-PREFIX",
            "allowed_paths": ["game.txt"],
            "planned_commands": [
                [sys.executable, "-c", "raise SystemExit(0)"],
                [sys.executable, "-c", "raise SystemExit(2)"],
            ],
        }]
        current = self.store.load()
        self.store.dispatch({
            "name": "init", "id": "CONFIGURE-FORGED-PREFIX",
            "expected_generation": current["generation"], "run_id": current["run_id"],
            "project_root": current["project_root"], "authority": current["authority"],
            "slices": self._sealed(self.slices),
        })
        self._reach_engineering("-forged-prefix")
        issued = self.controller.next(
            command_id="NEXT-FORGED-PREFIX",
            assignment={
                "id": "ASSIGN-FORGED-PREFIX", "worker_id": "engineer-forged-prefix",
                "task": "Reject forged controller evidence",
            },
        )
        active = issued["active_assignment"]
        empty_digest = digest("")
        base_result = {
            "returncode": 0, "stdout_sha256": empty_digest,
            "stderr_sha256": empty_digest,
        }
        evidence = {
            "authority_digest": issued["authority"]["digest"],
            "base_checkout_sha256": active["base"]["checkout_sha256"],
            "current_checkout_sha256": active["base"]["checkout_sha256"],
            "inventory": deepcopy(active["base"]["inventory"]),
            "diff": [], "diff_sha256": digest([]), "violations": [],
        }

        def completion(results: list[dict], command_id: str) -> dict:
            return {
                "name": "complete", "id": command_id,
                "expected_generation": issued["generation"],
                "artifact": {"outcome": "pass", "summary": "Worker completed"},
                "controller": {**deepcopy(evidence), "commands": results},
            }

        first = {"argv": active["commands"][0], **base_result}
        second = {"argv": active["commands"][1], **base_result}
        failed_first = {**first, "returncode": 31}
        with self.assertRaisesRegex(PipelineError, "exact planned prefix"):
            reduce(issued, completion([second], "FORGED-NON-PREFIX"))
        with self.assertRaisesRegex(PipelineError, "truncated a successful plan"):
            reduce(issued, completion([first], "FORGED-TRUNCATED-SUCCESS"))
        with self.assertRaisesRegex(PipelineError, "continued after the first failure"):
            reduce(issued, completion([failed_first, second], "FORGED-AFTER-FAILURE"))

        legacy = reduce(issued, completion([failed_first], "LEGACY-FOUR-FIELD-FAILURE"))
        self.assertEqual(2, legacy["schema"])
        validate_state(legacy)
        legacy_path = self.root / ".agentic-pipeline-v2" / "legacy-state.json"
        legacy_path.write_text(json.dumps(legacy), encoding="utf-8")
        legacy_controller = Controller(StateStore(legacy_path))
        self.assertEqual("resume", legacy_controller.status()["next_action"]["command"])

    def test_newer_blocked_engineering_inventory_recovers_old_remediation_candidate(self) -> None:
        self._reach_candidate()
        failed_review = self._complete_readonly(
            "review", "reviewer-old-candidate",
            {
                "outcome": "fail",
                "findings": [{"text": "Repair the UI seam", "severity": "P1", "kind": "defect"}],
            },
        )
        review_gate = next(
            key for key, item in failed_review["gates"].items() if item["status"] == "open"
        )
        self.controller.transition({
            "name": "resume", "id": "RESUME-OLD-CANDIDATE-REVIEW",
            "expected_generation": failed_review["generation"], "gate_id": review_gate,
            "resolution": "Repair the reviewed candidate",
        })
        self.controller.next(
            command_id="NEXT-BLOCKED-REMEDIATION",
            assignment={
                "id": "ASSIGN-BLOCKED-REMEDIATION",
                "worker_id": "engineer-blocked-remediation",
                "task": "Repair the reviewed candidate",
            },
        )
        (self.root / "game.txt").write_text("allowed remediation before blocker\n", encoding="utf-8")
        completed = self._complete(
            "COMPLETE-BLOCKED-REMEDIATION",
            {"outcome": "blocked", "summary": "A required read-only integration seam is unavailable"},
        )
        self.assertIsNone(completed["active_assignment"])
        self.assertNotIn("review", completed["artifacts"])
        persisted = self.store.path.read_bytes()

        clean_status = self.controller.status()
        self.assertEqual("resume", clean_status["next_action"]["command"])
        replay = self.controller.complete(command_id="COMPLETE-BLOCKED-REMEDIATION")
        self.assertEqual(completed, replay)
        self.assertEqual(persisted, self.store.path.read_bytes())

        foreign = self.root / "foreign-after-blocked.txt"
        foreign.write_text("foreign drift\n", encoding="utf-8")
        drifted_status = self.controller.status()
        self.assertEqual("checkout_recovery_required", drifted_status["next_action"]["result"])
        with self.assertRaisesRegex(PipelineError, "checkout drifted"):
            self.controller.complete(command_id="COMPLETE-BLOCKED-REMEDIATION")
        self.assertEqual(persisted, self.store.path.read_bytes())
        foreign.unlink()

        action = self.controller.status()["next_action"]
        resumed = self.controller.transition({
            "name": "resume", "id": action["command_id"],
            "expected_generation": action["expected_generation"],
            "gate_id": action["gate_id"], "resolution": "Provide the required integration seam",
        })
        self.assertEqual("engineering", resumed["phase"])
        self.assertIsNone(resumed["active_assignment"])

    def test_nonpassing_engineering_never_creates_or_publishes_a_candidate(self) -> None:
        cases = (
            ("blocked", [sys.executable, "-c", "raise SystemExit(23)"]),
            ("fail", self.command),
        )
        for outcome, planned_check in cases:
            with self.subTest(outcome=outcome):
                harness = PipelineV2CoreTests("runTest")
                harness.setUp()
                try:
                    harness.slices = [{
                        "id": f"SLICE-{outcome.upper()}",
                        "allowed_paths": ["game.txt"],
                        "planned_commands": [planned_check],
                    }]
                    state = harness.store.load()
                    harness.store.dispatch({
                        "name": "init", "id": f"CONFIGURE-{outcome.upper()}",
                        "expected_generation": state["generation"], "run_id": state["run_id"],
                        "project_root": state["project_root"], "authority": state["authority"],
                        "slices": harness._sealed(harness.slices),
                    })
                    harness._reach_engineering(f"-{outcome}-candidate")
                    harness.controller.next(
                        command_id=f"NEXT-{outcome.upper()}-CANDIDATE",
                        assignment={
                            "id": f"ASSIGN-{outcome.upper()}-CANDIDATE",
                            "worker_id": f"engineer-{outcome}-candidate",
                            "task": "Exercise a non-passing Engineering result",
                        },
                    )
                    (harness.root / "game.txt").write_text(
                        f"{outcome} checkout change\n", encoding="utf-8",
                    )
                    artifact = {"outcome": outcome, "summary": "Engineering did not pass"}
                    completed = harness._complete(f"COMPLETE-{outcome.upper()}-CANDIDATE", artifact)
                    persisted = harness.store.load()
                    self.assertEqual(completed, persisted)
                    self.assertNotIn("candidate", persisted["artifacts"]["engineering"])
                    self.assertIsNone(current_candidate(persisted))
                    self.assertIsNone(status_view(persisted)["candidate"])
                    gate_id = next(
                        key for key, item in persisted["gates"].items()
                        if item["status"] == "open"
                    )
                    self.assertIsNone(persisted["gates"][gate_id]["candidate_base"])

                    completed_bytes = harness.store.path.read_bytes()
                    self.assertEqual(
                        completed,
                        harness.controller.complete(
                            command_id=f"COMPLETE-{outcome.upper()}-CANDIDATE",
                            expected_generation=-1,
                        ),
                    )
                    self.assertEqual(completed_bytes, harness.store.path.read_bytes())

                    with self.assertRaises(ConflictError):
                        harness.store.dispatch({
                            "name": "resume", "id": f"STALE-RESUME-{outcome.upper()}",
                            "expected_generation": completed["generation"] - 1,
                            "gate_id": gate_id, "resolution": "Retry Engineering",
                        })
                    self.assertEqual(completed_bytes, harness.store.path.read_bytes())

                    resume = {
                        "name": "resume", "id": f"RESUME-{outcome.upper()}-CANDIDATE",
                        "expected_generation": completed["generation"],
                        "gate_id": gate_id, "resolution": "Retry Engineering",
                    }
                    resumed = harness.store.dispatch(resume)
                    resumed_bytes = harness.store.path.read_bytes()
                    replay = deepcopy(resume); replay["expected_generation"] = -1
                    self.assertEqual(resumed, harness.store.dispatch(replay))
                    self.assertEqual(resumed_bytes, harness.store.path.read_bytes())
                    self.assertIsNone(current_candidate(resumed))
                    self.assertIsNone(status_view(resumed)["candidate"])
                    self.assertIsNone(status_view(resumed)["next_action"]["assignment"].get("candidate"))
                finally:
                    harness.tearDown()

    def test_nonpassing_engineering_is_not_captured_as_reconfiguration_audit_candidate(self) -> None:
        self._reach_engineering("-audit")
        self.controller.next(command_id="NEXT-FAIL-AUDIT", assignment={
            "id": "ASSIGN-FAIL-AUDIT", "worker_id": "engineer-fail-audit",
            "task": "Report a failed Engineering result",
        })
        (self.root / "game.txt").write_text("failed checkout change\n", encoding="utf-8")
        failed = self._complete("COMPLETE-FAIL-AUDIT", {
            "outcome": "fail", "summary": "Engineering failed",
        })
        revised_slices = [{
            "id": "SLICE-AUDIT-REVISED", "allowed_paths": ["game.txt"],
            "planned_commands": [self.command],
        }]
        reconfigured = self.store.dispatch({
            "name": "init", "id": "RECONFIGURE-FAIL-AUDIT",
            "expected_generation": failed["generation"], "run_id": failed["run_id"],
            "project_root": failed["project_root"], "authority": failed["authority"],
            "slices": self._sealed(revised_slices),
        })
        self.assertIsNone(reconfigured["history"][-1]["prior"]["candidate"])

    def test_passing_engineering_still_persists_and_publishes_the_exact_candidate(self) -> None:
        completed = self._reach_candidate()
        persisted = self.store.load()
        candidate = persisted["artifacts"]["engineering"]["candidate"]
        self.assertEqual(completed, candidate)
        self.assertEqual(candidate, current_candidate(persisted))
        self.assertEqual(candidate, status_view(persisted)["candidate"])
        self.assertEqual(
            persisted["artifacts"]["engineering"]["controller"]["current_checkout_sha256"],
            candidate["checkout_sha256"],
        )

    def test_ready_rejects_a_declared_slice_without_engineering_review_and_qa_evidence(self) -> None:
        self._reach_candidate()
        ready = self._finish_ready("reviewer-missing", "qa-missing", "docs-missing")
        incomplete = deepcopy(ready)
        incomplete["slices"].append({
            "id": "SLICE-2", "allowed_paths": ["game.txt"], "planned_commands": [self.command],
        })
        incomplete["artifacts"].pop("ready")
        self.store._write(incomplete)
        before = self.store.path.read_bytes()
        with self.assertRaises(PipelineError):
            self.controller.ready(command_id="READY-MISSING-SLICE", expected_generation=incomplete["generation"])
        self.assertEqual(before, self.store.path.read_bytes())

    def test_native_transaction_lock_is_released_after_holder_process_is_killed(self) -> None:
        completed = self._complete_readonly("plan", "planner-crash", {"outcome": "pass", "summary": "done"})
        marker = self.root / ".agentic-pipeline-v2" / "holder.ready"
        module_path = json.dumps(str(SCRIPTS))
        state_path = json.dumps(str(self.store.path))
        marker_path = json.dumps(str(marker))
        holder_source = (
            f"import sys,time; from pathlib import Path; sys.path.insert(0,{module_path}); "
            f"from pipeline_v2.transaction import StateStore; store=StateStore(Path({state_path})); "
            f"lock=store.transaction(); lock.__enter__(); Path({marker_path}).write_text('locked'); time.sleep(30)"
        )
        resume_source = (
            f"import json,sys; from pathlib import Path; sys.path.insert(0,{module_path}); "
            f"from pipeline_v2.transaction import StateStore; store=StateStore(Path({state_path})); state=store.load(); "
            "result=store.dispatch({'name':'accept','id':'ACCEPT-AFTER-CRASH','expected_generation':state['generation']}); "
            "print(json.dumps(result, sort_keys=True))"
        )
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        holder = subprocess.Popen([sys.executable, "-c", holder_source], creationflags=flags)
        resumer = None
        try:
            deadline = time.monotonic() + 5
            while not marker.exists() and holder.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(marker.exists(), "holder child never acquired the native lock")
            resumer = subprocess.Popen(
                [sys.executable, "-c", resume_source], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, creationflags=flags,
            )
            time.sleep(0.1)
            self.assertIsNone(resumer.poll(), "resumer did not wait for the held transaction")
            holder.kill(); holder.wait(timeout=5)
            stdout, stderr = resumer.communicate(timeout=10)
            self.assertEqual(0, resumer.returncode, stderr)
            resumed = json.loads(stdout)
            persisted = json.loads(self.store.path.read_text(encoding="utf-8"))
            validate_state(persisted)
            self.assertEqual(resumed, persisted)
            self.assertEqual(completed["generation"] + 1, persisted["generation"])
            self.assertEqual("slice", persisted["phase"])
            self.assertEqual(12, len(persisted))
        finally:
            for child in (resumer, holder):
                if child is not None and child.poll() is None:
                    child.kill(); child.wait(timeout=5)

    def test_lost_complete_and_accept_responses_replay_as_exact_atomic_noops(self) -> None:
        self.controller.next(command_id="NEXT-LOST", assignment={
            "id": "ASSIGN-LOST", "worker_id": "planner-lost", "task": "plan",
            "access": {"read": ["**"], "write": []}, "commands": [],
        })
        artifact = self._write_artifact({"outcome": "pass", "summary": "planned"})
        completed = self.controller.complete(command_id="COMPLETE-LOST", artifact_path=artifact)
        completed_bytes = self.store.path.read_bytes()
        self.assertEqual(completed, self.controller.complete(command_id="COMPLETE-LOST", artifact_path=artifact, expected_generation=-1))
        self.assertEqual(completed_bytes, self.store.path.read_bytes())

        accept = {"name": "accept", "id": "ACCEPT-LOST", "expected_generation": completed["generation"]}
        accepted = self.store.dispatch(accept)
        accepted_bytes = self.store.path.read_bytes()
        replay = deepcopy(accept); replay["expected_generation"] = -1
        self.assertEqual(accepted, self.store.dispatch(replay))
        self.assertEqual(accepted_bytes, self.store.path.read_bytes())
        self.assertEqual(completed["generation"] + 1, accepted["generation"])
        self.assertEqual(len(completed["history"]) + 1, len(accepted["history"]))

    def test_four_record_slice_complete_replay_reseals_exact_intent_direct_and_cli(
        self,
    ) -> None:
        issued, artifact_path, raw_artifact, action = (
            self._begin_four_record_slice_complete("slice-record-replay-exact.json")
        )
        raw_bytes = artifact_path.read_bytes()
        with mock.patch("pipeline_v2.runner.run_process_tree") as run_checks:
            completed = self.controller.complete(
                command_id=action["command_id"],
                artifact_path=artifact_path,
                expected_generation=action["expected_generation"],
            )
            committed_bytes = self.store.path.read_bytes()
            direct_replay = self.controller.complete(
                command_id=action["command_id"],
                artifact_path=artifact_path,
                expected_generation=action["expected_generation"],
            )
            cli_replay = cli_run(cli_parser().parse_args([
                "--state", str(self.store.path),
                "complete",
                "--id", action["command_id"],
                "--expected-generation", str(action["expected_generation"]),
            ]))
        self.assertEqual(completed, direct_replay)
        self.assertEqual(status_view(completed), cli_replay)
        self.assertEqual(committed_bytes, self.store.path.read_bytes())
        self.assertEqual(raw_bytes, artifact_path.read_bytes())
        run_checks.assert_not_called()

        self.assertTrue(all(
            set(item) == {"id", "allowed_paths", "planned_commands"}
            for item in raw_artifact["slices"]
        ))
        sealed_artifact = completed["artifacts"]["slice"]["worker"]
        self.assertTrue(all(
            set(item) == {"id", "allowed_paths", "planned_commands", "read_paths"}
            for item in sealed_artifact["slices"]
        ))
        history = next(
            item for item in completed["history"]
            if item["id"] == action["command_id"]
        )
        self.assertEqual(
            history["command_digest"],
            command_intent_digest({
                "name": "complete",
                "id": action["command_id"],
                "artifact": sealed_artifact,
            }),
        )
        self.assertNotEqual(
            history["command_digest"],
            command_intent_digest({
                "name": "complete",
                "id": action["command_id"],
                "artifact": raw_artifact,
            }),
        )
        accept_action = status_view(completed)["next_action"]
        self.assertEqual(issued["generation"] + 1, completed["generation"])
        self.assertEqual("accept", accept_action["command"])
        self.assertEqual(completed["generation"], accept_action["expected_generation"])

    def test_four_record_slice_complete_replay_adversarial_inputs_fail_closed(
        self,
    ) -> None:
        _, artifact_path, raw_artifact, action = (
            self._begin_four_record_slice_complete("slice-record-replay-adversarial.json")
        )
        completed = self.controller.complete(
            command_id=action["command_id"],
            artifact_path=artifact_path,
            expected_generation=action["expected_generation"],
        )
        committed_bytes = self.store.path.read_bytes()

        changed = []
        for label, mutate in (
            ("summary", lambda value: value.update(summary="changed")),
            ("outcome", lambda value: value.update(outcome="blocked")),
            ("questions", lambda value: value.update(questions=["changed"])),
            ("slice-order", lambda value: value["slices"].reverse()),
            ("slice-count", lambda value: value["slices"].pop()),
            ("slice-id", lambda value: value["slices"][0].update(id="UNKNOWN")),
            (
                "allowed-paths",
                lambda value: value["slices"][0].update(
                    allowed_paths=["changed.txt"],
                ),
            ),
            (
                "planned-commands",
                lambda value: value["slices"][0].update(
                    planned_commands=[[sys.executable, "-c", "raise SystemExit(1)"]],
                ),
            ),
            (
                "smuggled-read-paths",
                lambda value: value["slices"][0].update(
                    read_paths=["forged.txt"],
                ),
            ),
        ):
            with self.subTest(label=label):
                candidate = deepcopy(raw_artifact)
                mutate(candidate)
                artifact_path.write_text(json.dumps(candidate), encoding="utf-8")
                candidate_bytes = artifact_path.read_bytes()
                with self.assertRaises(PipelineError):
                    self.controller.complete(
                        command_id=action["command_id"],
                        artifact_path=artifact_path,
                        expected_generation=action["expected_generation"],
                    )
                self.assertEqual(committed_bytes, self.store.path.read_bytes())
                self.assertEqual(candidate_bytes, artifact_path.read_bytes())
                changed.append(label)
        self.assertEqual(9, len(changed))
        artifact_path.write_text(json.dumps(raw_artifact), encoding="utf-8")

        plan = self.root / "plan.md"
        plan_bytes = plan.read_bytes()
        plan.write_bytes(plan_bytes + b"\n")
        try:
            with self.assertRaises(PipelineError):
                self.controller.complete(
                    command_id=action["command_id"],
                    artifact_path=artifact_path,
                    expected_generation=action["expected_generation"],
                )
            self.assertEqual(committed_bytes, self.store.path.read_bytes())
        finally:
            plan.write_bytes(plan_bytes)

        alternate = artifact_path.with_name("alternate.json")
        alternate.write_text(json.dumps(raw_artifact), encoding="utf-8")
        with self.assertRaisesRegex(PipelineError, "only the assigned artifact path"):
            self.controller.complete(
                command_id=action["command_id"],
                artifact_path=alternate,
                expected_generation=action["expected_generation"],
            )
        self.assertEqual(committed_bytes, self.store.path.read_bytes())

        with self.assertRaisesRegex(PipelineError, "there is no active assignment"):
            self.controller.complete(
                command_id="changed-command-id",
                artifact_path=artifact_path,
                expected_generation=completed["generation"],
            )
        self.assertEqual(committed_bytes, self.store.path.read_bytes())

        checkout = self.root / "game.txt"
        checkout_bytes = checkout.read_bytes()
        checkout.write_text("drift\n", encoding="utf-8")
        try:
            with self.assertRaisesRegex(PipelineError, "checkout drifted"):
                self.controller.complete(
                    command_id=action["command_id"],
                    artifact_path=artifact_path,
                    expected_generation=action["expected_generation"],
                )
            self.assertEqual(committed_bytes, self.store.path.read_bytes())
        finally:
            checkout.write_bytes(checkout_bytes)

        accept = status_view(self.store.load())["next_action"]
        self.store.dispatch({
            "name": "accept",
            "id": accept["command_id"],
            "expected_generation": accept["expected_generation"],
        })
        next_action = status_view(self.store.load())["next_action"]
        self.controller.next(
            command_id=next_action["command_id"],
            expected_generation=next_action["expected_generation"],
        )
        self._write_artifact({"outcome": "pass", "summary": "current work"})
        active_bytes = self.store.path.read_bytes()
        with mock.patch("pipeline_v2.runner.run_process_tree") as run_checks:
            with self.assertRaisesRegex(ConflictError, "different input"):
                self.controller.complete(
                    command_id=action["command_id"],
                    expected_generation=action["expected_generation"],
                )
        self.assertEqual(active_bytes, self.store.path.read_bytes())
        run_checks.assert_not_called()

    def test_complete_preflights_stale_conflict_and_replay_before_planned_commands(self) -> None:
        marker = self.root / "check-side-effect.txt"
        side_effect = [
            sys.executable, "-c",
            "from pathlib import Path; p=Path('check-side-effect.txt'); "
            "p.write_text((p.read_text() if p.exists() else '') + 'run\\n', encoding='utf-8')",
        ]
        self.slices = [{
            "id": "SLICE-COMPLETE-PREFLIGHT",
            "allowed_paths": ["game.txt", marker.name],
            "planned_commands": [side_effect],
        }]
        initial = self.store.load()
        self.store.dispatch({
            "name": "init", "id": "CONFIGURE-COMPLETE-PREFLIGHT",
            "expected_generation": initial["generation"], "run_id": initial["run_id"],
            "project_root": initial["project_root"], "authority": initial["authority"],
            "slices": self._sealed(self.slices),
        })
        self._reach_engineering("-complete-preflight")
        issued = self.controller.next(command_id="NEXT-COMPLETE-PREFLIGHT", assignment={
            "id": "ASSIGN-COMPLETE-PREFLIGHT", "worker_id": "engineer-complete-preflight",
            "task": "Exercise complete transaction preflight",
        })
        artifact = self._write_artifact({"outcome": "pass", "summary": "Implemented"})

        before_stale_state = self.store.path.read_bytes()
        before_stale_checkout = inventory(self.root)
        with self.assertRaisesRegex(ConflictError, "stale generation"):
            self.controller.complete(
                command_id="COMPLETE-PREFLIGHT-STALE", artifact_path=artifact,
                expected_generation=issued["generation"] - 1,
            )
        self.assertEqual(before_stale_state, self.store.path.read_bytes())
        self.assertEqual(before_stale_checkout, inventory(self.root))
        self.assertFalse(marker.exists())

        completed = self.controller.complete(
            command_id="COMPLETE-PREFLIGHT", artifact_path=artifact,
            expected_generation=issued["generation"],
        )
        self.assertEqual("run\n", marker.read_text(encoding="utf-8"))
        completed_bytes = self.store.path.read_bytes()
        self.assertEqual(
            completed,
            self.controller.complete(
                command_id="COMPLETE-PREFLIGHT", artifact_path=artifact,
                expected_generation=-1,
            ),
        )
        self.assertEqual(completed_bytes, self.store.path.read_bytes())
        self.assertEqual("run\n", marker.read_text(encoding="utf-8"))

        artifact.write_text(
            json.dumps({"outcome": "pass", "summary": "Conflicting replacement"}),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ConflictError, "different input"):
            self.controller.complete(
                command_id="COMPLETE-PREFLIGHT", artifact_path=artifact,
                expected_generation=completed["generation"],
            )
        self.assertEqual(completed_bytes, self.store.path.read_bytes())
        self.assertEqual("run\n", marker.read_text(encoding="utf-8"))

    def test_launch_error_has_distinct_technical_return_code_and_blocked_gate(self) -> None:
        missing = str(self.root / "definitely-missing-planned-command.exe")
        self.slices = [{
            "id": "SLICE-LAUNCH-ERROR",
            "allowed_paths": ["game.txt"],
            "planned_commands": [[missing]],
        }]
        initial = self.store.load()
        self.store.dispatch({
            "name": "init", "id": "CONFIGURE-LAUNCH-ERROR",
            "expected_generation": initial["generation"], "run_id": initial["run_id"],
            "project_root": initial["project_root"], "authority": initial["authority"],
            "slices": self._sealed(self.slices),
        })
        self._reach_engineering("-launch-error")
        self.controller.next(
            command_id="NEXT-LAUNCH-ERROR",
            assignment={
                "id": "ASSIGN-LAUNCH-ERROR", "worker_id": "engineer-launch-error",
                "task": "Report the controller-owned technical check failure",
            },
        )

        completed = self._complete("COMPLETE-LAUNCH-ERROR", {
            "outcome": "blocked", "summary": "The planned command could not launch",
        })

        command = completed["artifacts"]["engineering"]["controller"]["commands"][0]
        self.assertEqual([missing], command["argv"])
        self.assertEqual(125, command["returncode"])
        self.assertNotEqual(124, command["returncode"])
        self.assertTrue(any(gate["status"] == "open" for gate in completed["gates"].values()))

    def _configure_live_read_only_check(self, command: list[str], suffix: str) -> None:
        self.slices = [{
            "id": f"SLICE-LIVE-READ-ONLY-{suffix}",
            "allowed_paths": ["game.txt", "engineering-check.txt"],
            "planned_commands": [command],
        }]
        initial = self.store.load()
        self.store.dispatch({
            "name": "init", "id": f"CONFIGURE-LIVE-READ-ONLY-{suffix}",
            "expected_generation": initial["generation"], "run_id": initial["run_id"],
            "project_root": initial["project_root"], "authority": initial["authority"],
            "slices": self._sealed(self.slices),
        })
        self._reach_candidate()
        self._review_pass(f"reviewer-live-read-only-{suffix}")

    def test_read_only_qa_runs_in_canonical_checkout_with_confined_cleaned_temp(self) -> None:
        command = [
            sys.executable, "-c",
            "import os,sys; from pathlib import Path; marker=Path('engineering-check.txt'); "
            "root=Path(sys.argv[1]).resolve(); "
            "exec(\"if not marker.exists():\\n marker.write_text('engineering pass', encoding='utf-8')\\n"
            "else:\\n assert Path.cwd().resolve() == root\\n"
            " scratch=Path(os.environ['TEMP']).resolve()\\n"
            " control=(root/'.agentic-pipeline-v2'/'read-only-temp').resolve()\\n"
            " assert scratch.is_relative_to(control)\\n"
            " assert all(Path(os.environ[key]).resolve() == scratch for key in "
            "('TMP','TMPDIR','XDG_CACHE_HOME','NPM_CONFIG_CACHE','npm_config_cache','YARN_CACHE_FOLDER','PIP_CACHE_DIR'))\\n"
            " assert not list(scratch.rglob('game.txt'))\\n"
            " (scratch/'probe.tmp').write_text('temporary', encoding='utf-8')\")",
            str(self.root),
        ]
        self._configure_live_read_only_check(command, "CANONICAL")
        before = inventory(self.root)
        stale = self.root / ".agentic-pipeline-v2" / "read-only-temp" / "stale-command"
        stale.mkdir(parents=True)
        (stale / "orphan.tmp").write_text("stale controller scratch", encoding="utf-8")

        completed = self._complete_readonly(
            "qa", "qa-live-canonical",
            {"outcome": "pass", "checks": ["canonical live read-only check passed"]},
        )

        self.assertEqual(0, completed["artifacts"]["qa"]["controller"]["commands"][0]["returncode"])
        self.assertEqual(before, inventory(self.root))
        self.assertFalse((self.root / ".agentic-pipeline-v2" / "read-only-checks").exists())
        self.assertFalse((self.root / ".agentic-pipeline-v2" / "read-only-temp").exists())

    def test_read_only_relative_mutation_is_detected_without_state_commit(self) -> None:
        command = [
            sys.executable, "-c",
            "from pathlib import Path; marker=Path('engineering-check.txt'); "
            "marker.write_text('engineering pass', encoding='utf-8') if not marker.exists() "
            "else Path('game.txt').write_text('forbidden read-only mutation\\n', encoding='utf-8')",
        ]
        self._configure_live_read_only_check(command, "MUTATION")
        self.controller.next(command_id="NEXT-QA-LIVE-MUTATION", assignment={
            "id": "ASSIGN-QA-LIVE-MUTATION", "worker_id": "qa-live-mutation",
            "task": "Detect a forbidden live mutation",
        })
        artifact = self._write_artifact({
            "outcome": "pass", "checks": ["command declared non-mutating"],
        })
        before_state = self.store.path.read_bytes()

        with self.assertRaisesRegex(PipelineError, "forbidden paths"):
            self.controller.complete(command_id="COMPLETE-QA-LIVE-MUTATION", artifact_path=artifact)

        self.assertEqual(before_state, self.store.path.read_bytes())
        self.assertEqual("forbidden read-only mutation\n", (self.root / "game.txt").read_text(encoding="utf-8"))

    def test_read_only_mutation_cannot_be_hidden_by_a_later_restore_command(self) -> None:
        mutate = [
            sys.executable, "-c",
            "from pathlib import Path; marker=Path('engineering-check.txt'); "
            "marker.write_text('engineering pass', encoding='utf-8') if not marker.exists() "
            "else Path('game.txt').write_text('forbidden transient mutation\\n', encoding='utf-8')",
        ]
        restore = [
            sys.executable, "-c",
            "from pathlib import Path; "
            "Path('game.txt').write_text('candidate-1\\n', encoding='utf-8')",
        ]
        self.slices = [{
            "id": "SLICE-LIVE-READ-ONLY-MUTATE-RESTORE",
            "allowed_paths": ["game.txt", "engineering-check.txt"],
            "planned_commands": [mutate, restore],
        }]
        initial = self.store.load()
        self.store.dispatch({
            "name": "init", "id": "CONFIGURE-LIVE-READ-ONLY-MUTATE-RESTORE",
            "expected_generation": initial["generation"], "run_id": initial["run_id"],
            "project_root": initial["project_root"], "authority": initial["authority"],
            "slices": self._sealed(self.slices),
        })
        self._reach_candidate()
        self._review_pass("reviewer-live-read-only-mutate-restore")
        self.controller.next(command_id="NEXT-QA-LIVE-MUTATE-RESTORE", assignment={
            "id": "ASSIGN-QA-LIVE-MUTATE-RESTORE", "worker_id": "qa-live-mutate-restore",
            "task": "Detect a transient forbidden live mutation",
        })
        artifact = self._write_artifact({
            "outcome": "pass", "checks": ["commands declared non-mutating"],
        })
        before_state = self.store.path.read_bytes()

        with self.assertRaisesRegex(PipelineError, "forbidden paths"):
            self.controller.complete(command_id="COMPLETE-QA-LIVE-MUTATE-RESTORE", artifact_path=artifact)

        self.assertEqual(before_state, self.store.path.read_bytes())
        self.assertEqual("forbidden transient mutation\n", (self.root / "game.txt").read_text(encoding="utf-8"))

    def test_read_only_complete_stale_and_replay_execute_check_exactly_once(self) -> None:
        command = [sys.executable, "-c", "from pathlib import Path; assert Path('game.txt').is_file()"]
        self._configure_live_read_only_check(command, "PREFLIGHT")
        issued = self.controller.next(command_id="NEXT-QA-LIVE-PREFLIGHT", assignment={
            "id": "ASSIGN-QA-LIVE-PREFLIGHT", "worker_id": "qa-live-preflight",
            "task": "Exercise read-only preflight",
        })
        artifact = self._write_artifact({"outcome": "pass", "checks": ["read-only check passed"]})
        result = ProcessEvidence(0, digest("stdout"), digest("stderr"))

        with mock.patch("pipeline_v2.runner.run_process_tree", return_value=result) as invoked:
            with self.assertRaisesRegex(ConflictError, "stale generation"):
                self.controller.complete(
                    command_id="COMPLETE-QA-LIVE-STALE", artifact_path=artifact,
                    expected_generation=issued["generation"] - 1,
                )
            self.assertEqual(0, invoked.call_count)
            completed = self.controller.complete(
                command_id="COMPLETE-QA-LIVE-PREFLIGHT", artifact_path=artifact,
                expected_generation=issued["generation"],
            )
            self.assertEqual(1, invoked.call_count)
            self.assertEqual(
                completed,
                self.controller.complete(
                    command_id="COMPLETE-QA-LIVE-PREFLIGHT", artifact_path=artifact,
                    expected_generation=-1,
                ),
            )
            self.assertEqual(1, invoked.call_count)

    def test_public_failure_capsule_is_bounded_redacted_and_reaches_remediation(self) -> None:
        secret = "PIPELINE_SECRET_SENTINEL_7F42"
        bearer = "BEARER_SENTINEL_28A1"
        password = "PASSWORD_SENTINEL_19C3"
        github_pat = "GITHUB_PAT_SENTINEL_91F2"
        database_password = "DB_PASSWORD_SENTINEL_6A31"
        dsn_secret = "SENTRY_DSN_SENTINEL_4C77"
        uri_secret = "URI_USERINFO_SENTINEL_5D88"
        database_env = "DATABASE_URL_ENV_SENTINEL_3B55"
        dsn_env = "SENTRY_DSN_ENV_SENTINEL_8E29"
        database_url = f"postgres://user:{database_password}@db.example/game"
        sentry_dsn = f"https://public:{dsn_secret}@o0.ingest.sentry.io/0"
        failing_check = [sys.executable, "-c", "raise SystemExit(31)"]
        skipped_checks = [
            [sys.executable, "-c", "raise SystemExit(0)"],
            [sys.executable, "-c", "raise SystemExit(0)"],
        ]
        self.slices = [{
            "id": "SLICE-REDACTED-STDERR",
            "allowed_paths": ["game.txt"],
            "planned_commands": [failing_check, *skipped_checks],
        }]
        current = self.store.load()
        self.store.dispatch({
            "name": "init", "id": "CONFIGURE-REDACTED-STDERR",
            "expected_generation": current["generation"], "run_id": current["run_id"],
            "project_root": current["project_root"], "authority": current["authority"],
            "slices": self._sealed(self.slices),
        })
        self._reach_engineering("-redacted-stderr")
        self.controller.next(
            command_id="NEXT-REDACTED-STDERR",
            assignment={
                "id": "ASSIGN-REDACTED-STDERR",
                "worker_id": "engineer-redacted-stderr",
                "task": "Persist safe failure diagnostics",
            },
        )
        artifact = self._write_artifact({
            "outcome": "pass", "summary": "Worker completed",
        })
        observed_raw: list[bytes] = []

        def failure(*_args, cwd: Path, env: dict[str, str], **_kwargs) -> ProcessEvidence:
            raw = (
                "x" * 5000
                + f"\nenv={secret}\nAuthorization: Bearer {bearer}\n"
                + f"password={password}\npat={github_pat}\ndatabase_env={database_env}\n"
                + f"dsn_env={dsn_env}\ndatabase={database_url}\ndsn={sentry_dsn}\n"
                + f"uri=redis://user:{uri_secret}@cache.example/0\n"
                + f"project={cwd}\nscratch={env['TEMP']}\n"
            ).encode("utf-8")
            observed_raw.append(raw)
            return ProcessEvidence(
                31, digest("stdout"), runner_module._stream_digest(raw), raw, False,
            )

        with (
            mock.patch.dict(os.environ, {
                "PIPELINE_API_TOKEN": secret,
                "GITHUB_PAT": github_pat,
                "DATABASE_URL": database_env,
                "SENTRY_DSN": dsn_env,
            }),
            mock.patch("pipeline_v2.runner.run_process_tree", side_effect=failure),
        ):
            completed = self.controller.complete(
                command_id="COMPLETE-REDACTED-STDERR", artifact_path=artifact,
            )
        command = completed["artifacts"]["engineering"]["controller"]["commands"][0]
        self.assertEqual(runner_module._stream_digest(observed_raw[0]), command["stderr_sha256"])
        self.assertLessEqual(len(command["stderr_excerpt"].encode("utf-8")), 4096)
        self.assertTrue(command["stderr_excerpt_truncated"])
        self.assertTrue(command["stderr_excerpt_redacted"])
        self.assertIn("[REDACTED]", command["stderr_excerpt"])
        self.assertIn("redis://[REDACTED]@cache.example/0", command["stderr_excerpt"])
        self.assertIn("[PROJECT_ROOT]", command["stderr_excerpt"])
        self.assertIn("[SCRATCH_ROOT]", command["stderr_excerpt"])
        self.assertNotIn("stdout", command)
        self.assertNotIn("env", command)
        self.assertNotIn("cwd", command)
        view = status_view(completed)
        gate_id = view["next_action"]["gate_id"]
        gate = completed["gates"][gate_id]
        public_gate = view["next_action"]["gate"]
        expected_failure_keys = {
            "command_index", "returncode", "stdout_sha256", "stderr_sha256",
            "stderr_excerpt", "stderr_excerpt_truncated", "stderr_excerpt_redacted",
            "unexecuted_count",
        }
        for capsule in (gate["controller_failure"], public_gate["controller_failure"]):
            self.assertEqual(expected_failure_keys, set(capsule))
            self.assertEqual(1, capsule["command_index"])
            self.assertEqual(31, capsule["returncode"])
            self.assertEqual(command["stdout_sha256"], capsule["stdout_sha256"])
            self.assertEqual(command["stderr_sha256"], capsule["stderr_sha256"])
            self.assertEqual(2, capsule["unexecuted_count"])
            self.assertNotIn("argv", capsule)
            self.assertNotIn("env", capsule)
            self.assertNotIn("cwd", capsule)
            self.assertNotIn("stdout", capsule)

        before_replay = self.store.path.read_bytes()
        with mock.patch("pipeline_v2.runner.run_process_tree") as rerun:
            complete_view = cli_run(cli_parser().parse_args([
                "--state", str(self.store.path), "complete",
                "--id", "COMPLETE-REDACTED-STDERR", "--artifact", str(artifact),
            ]))
        rerun.assert_not_called()
        self.assertEqual(before_replay, self.store.path.read_bytes())
        status = cli_run(cli_parser().parse_args([
            "--state", str(self.store.path), "status",
        ]))
        self.assertEqual(view, complete_view)
        self.assertEqual(view, status)
        sentinels = (
            secret, bearer, password, github_pat, database_password, dsn_secret,
            uri_secret, database_env, dsn_env,
        )
        public_payloads = (completed, complete_view, status, gate, public_gate)
        for sentinel in sentinels:
            for payload in public_payloads:
                self.assertNotIn(sentinel, json.dumps(payload, ensure_ascii=False))

        resumed = self.controller.transition({
            "name": "resume", "id": "RESUME-REDACTED-STDERR",
            "expected_generation": completed["generation"], "gate_id": gate_id,
            "resolution": "Retry after the controller failure",
        })
        next_action = status_view(resumed)["next_action"]
        fresh = self.controller.next(
            command_id=next_action["command_id"], assignment=next_action["assignment"],
        )
        assignment_context = status_view(fresh)["active_assignment"]["context"]
        remediation_failure = assignment_context["remediation"][0]["controller_failure"]
        self.assertEqual(expected_failure_keys, set(remediation_failure))
        for key in expected_failure_keys - {"stderr_excerpt"}:
            self.assertEqual(public_gate["controller_failure"][key], remediation_failure[key])
        self.assertIn("[REDACTED]", remediation_failure["stderr_excerpt"])
        self.assertLess(
            len(remediation_failure["stderr_excerpt"].encode("utf-8")),
            len(public_gate["controller_failure"]["stderr_excerpt"].encode("utf-8")),
        )
        for sentinel in sentinels:
            self.assertNotIn(
                sentinel, json.dumps(assignment_context, ensure_ascii=False),
            )

    def test_nonpassing_worker_keeps_one_worker_gate_with_safe_controller_failure(self) -> None:
        for outcome in ("fail", "blocked"):
            with self.subTest(outcome=outcome):
                harness = PipelineV2CoreTests("runTest")
                harness.setUp()
                try:
                    failing_check = [sys.executable, "-c", "raise SystemExit(47)"]
                    skipped_check = [sys.executable, "-c", "raise SystemExit(0)"]
                    harness.slices = [{
                        "id": f"SLICE-WORKER-{outcome.upper()}-CONTROLLER-FAIL",
                        "allowed_paths": ["game.txt"],
                        "planned_commands": [failing_check, skipped_check],
                    }]
                    harness._write_approved_plan(harness.slices)
                    current = harness.store.load()
                    harness.store.dispatch({
                        "name": "init", "id": f"CONFIGURE-WORKER-{outcome.upper()}-FAILURE",
                        "expected_generation": current["generation"],
                        "run_id": current["run_id"],
                        "project_root": current["project_root"],
                        "authority": {
                            "items": authority_items(harness.root, {
                                "requirements": "requirements.md",
                                "specification": "specification.md",
                                "plan": "plan.md",
                            }),
                        },
                        "slices": harness._sealed(harness.slices),
                    })
                    harness._reach_engineering(f"-worker-{outcome}-controller-fail")
                    harness.controller.next(
                        command_id=f"NEXT-WORKER-{outcome.upper()}-CONTROLLER-FAIL",
                        assignment={
                            "id": f"ASSIGN-WORKER-{outcome.upper()}-CONTROLLER-FAIL",
                            "worker_id": f"engineer-worker-{outcome}-controller-fail",
                            "task": "Preserve both worker and controller failure evidence",
                        },
                    )
                    worker_artifact = {
                        "outcome": outcome,
                        "summary": f"Worker reported {outcome}",
                    }
                    artifact_path = harness._write_artifact(worker_artifact)
                    sentinel = f"WORKER_{outcome.upper()}_SECRET_SENTINEL_4F19"
                    raw_stderr = f"token={sentinel}\ncontroller check failed\n".encode()
                    with (
                        mock.patch.dict(os.environ, {"PIPELINE_API_TOKEN": sentinel}),
                        mock.patch(
                            "pipeline_v2.runner.run_process_tree",
                            return_value=ProcessEvidence(
                                47, digest("worker-nonpass-out"),
                                runner_module._stream_digest(raw_stderr), raw_stderr, False,
                            ),
                        ),
                    ):
                        completed = harness.controller.complete(
                            command_id=f"COMPLETE-WORKER-{outcome.upper()}-CONTROLLER-FAIL",
                            artifact_path=artifact_path,
                        )

                    open_gates = [
                        (key, item) for key, item in completed["gates"].items()
                        if item["status"] == "open"
                    ]
                    self.assertEqual(1, len(open_gates))
                    gate_id, gate = open_gates[0]
                    self.assertEqual("worker_result", gate["kind"])
                    self.assertEqual(outcome, gate["reason"])
                    self.assertEqual(worker_artifact, gate["worker_artifact"])
                    self.assertNotIn(
                        f"{completed['artifacts']['engineering']['assignment_id']}-controller-result",
                        completed["gates"],
                    )
                    self.assertNotIn("candidate", completed["artifacts"]["engineering"])
                    capsule = gate["controller_failure"]
                    self.assertEqual(1, capsule["command_index"])
                    self.assertEqual(47, capsule["returncode"])
                    self.assertEqual(1, capsule["unexecuted_count"])
                    self.assertIn("[REDACTED]", capsule["stderr_excerpt"])
                    for forbidden in ("argv", "env", "cwd", "stdout"):
                        self.assertNotIn(forbidden, capsule)

                    view = status_view(completed)
                    public_gate = view["next_action"]["gate"]
                    self.assertEqual(gate_id, public_gate["id"])
                    self.assertEqual("worker_result", public_gate["kind"])
                    self.assertEqual(capsule, public_gate["controller_failure"])

                    before_replay = harness.store.path.read_bytes()
                    with mock.patch("pipeline_v2.runner.run_process_tree") as rerun:
                        complete_view = cli_run(cli_parser().parse_args([
                            "--state", str(harness.store.path), "complete",
                            "--id", f"COMPLETE-WORKER-{outcome.upper()}-CONTROLLER-FAIL",
                            "--artifact", str(artifact_path),
                        ]))
                    rerun.assert_not_called()
                    self.assertEqual(before_replay, harness.store.path.read_bytes())
                    status = cli_run(cli_parser().parse_args([
                        "--state", str(harness.store.path), "status",
                    ]))
                    self.assertEqual(view, complete_view)
                    self.assertEqual(view, status)
                    for payload in (completed, complete_view, status, public_gate):
                        self.assertNotIn(
                            sentinel, json.dumps(payload, ensure_ascii=False),
                        )

                    resumed = harness.controller.transition({
                        "name": "resume",
                        "id": f"RESUME-WORKER-{outcome.upper()}-CONTROLLER-FAIL",
                        "expected_generation": completed["generation"],
                        "gate_id": gate_id,
                        "resolution": "Retry with the controller failure evidence",
                    })
                    action = status_view(resumed)["next_action"]
                    fresh = harness.controller.next(
                        command_id=action["command_id"], assignment=action["assignment"],
                    )
                    context = status_view(fresh)["active_assignment"]["context"]
                    remediation = context["remediation"][0]
                    self.assertEqual(worker_artifact, remediation["worker_artifact"])
                    self.assertEqual(capsule, remediation["controller_failure"])
                    self.assertNotIn(
                        sentinel, json.dumps(context, ensure_ascii=False),
                    )
                finally:
                    harness.tearDown()

    def test_worker_result_without_controller_failure_keeps_legacy_gate_shape(self) -> None:
        for case in ("no-checks", "all-pass"):
            with self.subTest(case=case):
                harness = PipelineV2CoreTests("runTest")
                harness.setUp()
                try:
                    worker_artifact = {
                        "outcome": "fail", "summary": f"Worker failed with {case}",
                    }
                    if case == "no-checks":
                        completed = harness._complete_readonly(
                            "plan", "planner-worker-fail-no-checks", worker_artifact,
                        )
                    else:
                        harness._reach_engineering("-worker-fail-all-pass")
                        harness.controller.next(
                            command_id="NEXT-WORKER-FAIL-ALL-PASS",
                            assignment={
                                "id": "ASSIGN-WORKER-FAIL-ALL-PASS",
                                "worker_id": "engineer-worker-fail-all-pass",
                                "task": "Keep the ordinary worker-result gate",
                            },
                        )
                        completed = harness._complete(
                            "COMPLETE-WORKER-FAIL-ALL-PASS", worker_artifact,
                        )
                    gate = next(
                        item for item in completed["gates"].values()
                        if item["status"] == "open"
                    )
                    self.assertEqual({
                        "status", "phase", "kind", "reason", "worker_artifact",
                        "candidate_base", "slice_id",
                    }, set(gate))
                    self.assertEqual("worker_result", gate["kind"])
                    self.assertEqual(worker_artifact, gate["worker_artifact"])
                    self.assertNotIn(
                        "controller_failure",
                        status_view(completed)["next_action"]["gate"],
                    )
                finally:
                    harness.tearDown()

    @unittest.skipUnless(os.name == "nt", "Windows read-only cleanup behavior")
    def test_windows_scratch_cleanup_handles_stale_and_fresh_readonly_git_objects(self) -> None:
        scratch_root = self.root / ".agentic-pipeline-v2" / "read-only-temp"
        stale = scratch_root / "stale-command" / ".git" / "objects" / "stale-object"
        stale.parent.mkdir(parents=True)
        stale.write_text("stale", encoding="utf-8")
        os.chmod(stale, stat.S_IREAD)

        with runner_module._read_only_process_environment(self.root) as environment:
            self.assertFalse(stale.exists())
            fresh = Path(environment["TEMP"]) / ".git" / "objects" / "fresh-object"
            fresh.parent.mkdir(parents=True)
            fresh.write_text("fresh", encoding="utf-8")
            os.chmod(fresh, stat.S_IREAD)

        self.assertFalse(scratch_root.exists())
        runner_module._remove_read_only_temp(scratch_root, "absent scratch")
        self.assertFalse(scratch_root.exists())

    @unittest.skipUnless(os.name == "nt", "Windows junction behavior")
    def test_windows_scratch_cleanup_does_not_touch_external_junction_target(self) -> None:
        scratch_root = self.root / ".agentic-pipeline-v2" / "read-only-temp"
        scratch_root.mkdir(parents=True)
        with tempfile.TemporaryDirectory() as external_temporary:
            external = Path(external_temporary).resolve()
            sentinel = external / "external-sentinel.txt"
            sentinel.write_text("untouched", encoding="utf-8")
            junction = scratch_root / "external-link"
            created = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(junction), str(external)],
                capture_output=True, text=True, check=False,
            )
            if created.returncode != 0:
                self.skipTest("junction creation is unavailable")

            runner_module._remove_read_only_temp(scratch_root, "junction scratch")

            self.assertFalse(scratch_root.exists())
            self.assertEqual("untouched", sentinel.read_text(encoding="utf-8"))

    def test_runner_has_no_candidate_tree_materialization_path(self) -> None:
        source = inspect.getsource(runner_module)
        tree = ast.parse(source)
        banned_calls = {
            "shutil.copy", "shutil.copy2", "shutil.copyfile", "shutil.copytree",
            "os.link", "Path.hardlink_to", "Path.link_to", "clone", "clonefile",
            "reflink", "snapshot", "worktree",
        }

        def call_name(node: ast.expr) -> str:
            if isinstance(node, ast.Name):
                return node.id
            if isinstance(node, ast.Attribute):
                return f"{call_name(node.value)}.{node.attr}"
            return ""

        calls = {call_name(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
        self.assertFalse(hasattr(runner_module, "_read_only_checkout"))
        self.assertEqual(set(), calls & banned_calls)

    def test_engineering_checks_use_cleaned_controller_scratch_in_canonical_checkout(self) -> None:
        self._reach_engineering("-engineering-live")
        self.controller.next(command_id="NEXT-ENGINEERING-LIVE", assignment={
            "id": "ASSIGN-ENGINEERING-LIVE", "worker_id": "engineer-live",
            "task": "Use the controller scratch without leaving generated output",
        })
        (self.root / "game.txt").write_text("engineering live\n", encoding="utf-8")
        artifact = self._write_artifact({"outcome": "pass", "summary": "Implemented live"})
        result = ProcessEvidence(0, digest("stdout"), digest("stderr"))

        def write_generated_output(*args, **kwargs):
            scratch_root = self.root / ".agentic-pipeline-v2" / "read-only-temp"
            (scratch_root / "build.output").write_text("generated", encoding="utf-8")
            return result

        with mock.patch("pipeline_v2.runner.run_process_tree", side_effect=write_generated_output) as invoked:
            self.controller.complete(command_id="COMPLETE-ENGINEERING-LIVE", artifact_path=artifact)

        self.assertEqual(self.root, invoked.call_args.kwargs["cwd"])
        temp_value = Path(invoked.call_args.kwargs["env"]["TEMP"])
        self.assertTrue(temp_value.is_relative_to(self.root / ".agentic-pipeline-v2" / "read-only-temp"))
        self.assertFalse((self.root / ".agentic-pipeline-v2" / "read-only-temp").exists())

    def test_complete_checks_replay_and_cas_exactly_once_for_stale_normal_and_replay(self) -> None:
        marker = self.root / "single-precondition.txt"
        side_effect = [
            sys.executable, "-c",
            "from pathlib import Path; p=Path('single-precondition.txt'); "
            "p.write_text((p.read_text() if p.exists() else '') + 'run\\n', encoding='utf-8')",
        ]
        self.slices = [{
            "id": "SLICE-SINGLE-PRECONDITION",
            "allowed_paths": ["game.txt", marker.name],
            "planned_commands": [side_effect],
        }]
        initial = self.store.load()
        self.store.dispatch({
            "name": "init", "id": "CONFIGURE-SINGLE-PRECONDITION",
            "expected_generation": initial["generation"], "run_id": initial["run_id"],
            "project_root": initial["project_root"], "authority": initial["authority"],
            "slices": self._sealed(self.slices),
        })
        self._reach_engineering("-single-precondition")
        issued = self.controller.next(command_id="NEXT-SINGLE-PRECONDITION", assignment={
            "id": "ASSIGN-SINGLE-PRECONDITION", "worker_id": "engineer-single-precondition",
            "task": "Exercise one complete transaction precondition",
        })
        artifact = self._write_artifact({"outcome": "pass", "summary": "Implemented"})
        real_precondition = reducer_module.transaction_precondition

        calls = []

        def tracked_precondition(state, command):
            calls.append((state, command))
            return real_precondition(state, command)

        with (
            mock.patch.object(transaction_module, "transaction_precondition", side_effect=tracked_precondition),
            mock.patch.object(reducer_module, "transaction_precondition", side_effect=tracked_precondition),
        ):
            stale_bytes = self.store.path.read_bytes()
            stale_inventory = inventory(self.root)
            with self.assertRaisesRegex(ConflictError, "stale generation"):
                self.controller.complete(
                    command_id="COMPLETE-SINGLE-PRECONDITION-STALE",
                    artifact_path=artifact,
                    expected_generation=issued["generation"] - 1,
                )
            self.assertEqual(1, len(calls))
            self.assertEqual(stale_bytes, self.store.path.read_bytes())
            self.assertEqual(stale_inventory, inventory(self.root))
            self.assertFalse(marker.exists())

            calls.clear()
            completed = self.controller.complete(
                command_id="COMPLETE-SINGLE-PRECONDITION",
                artifact_path=artifact,
                expected_generation=issued["generation"],
            )
            self.assertEqual(1, len(calls))
            self.assertEqual("run\n", marker.read_text(encoding="utf-8"))
            completed_bytes = self.store.path.read_bytes()

            calls.clear()
            self.assertEqual(
                completed,
                self.controller.complete(
                    command_id="COMPLETE-SINGLE-PRECONDITION",
                    artifact_path=artifact,
                    expected_generation=-1,
                ),
            )
            self.assertEqual(1, len(calls))
            self.assertEqual(completed_bytes, self.store.path.read_bytes())
            self.assertEqual("run\n", marker.read_text(encoding="utf-8"))

    def test_complete_reduces_checked_snapshot_when_command_replaces_controller_state(self) -> None:
        replace_state = [
            sys.executable, "-c",
            "import json; from pathlib import Path; p=Path('.agentic-pipeline-v2/state.json'); "
            "state=json.loads(p.read_text(encoding='utf-8')); state['run_id']='RUN-TAMPERED'; "
            "p.write_text(json.dumps(state), encoding='utf-8')",
        ]
        self.slices = [{
            "id": "SLICE-STATE-REPLACEMENT",
            "allowed_paths": ["game.txt"],
            "planned_commands": [replace_state],
        }]
        initial = self.store.load()
        self.store.dispatch({
            "name": "init", "id": "CONFIGURE-STATE-REPLACEMENT",
            "expected_generation": initial["generation"], "run_id": initial["run_id"],
            "project_root": initial["project_root"], "authority": initial["authority"],
            "slices": self._sealed(self.slices),
        })
        self._reach_engineering("-state-replacement")
        issued = self.controller.next(command_id="NEXT-STATE-REPLACEMENT", assignment={
            "id": "ASSIGN-STATE-REPLACEMENT", "worker_id": "engineer-state-replacement",
            "task": "Replace state during a controller-owned command",
        })
        artifact = self._write_artifact({"outcome": "pass", "summary": "Implemented"})
        checked_run_id = issued["run_id"]
        real_precondition = reducer_module.transaction_precondition
        calls = []

        def tracked_precondition(state, command):
            calls.append((state, command))
            return real_precondition(state, command)

        with (
            mock.patch.object(transaction_module, "transaction_precondition", side_effect=tracked_precondition),
            mock.patch.object(reducer_module, "transaction_precondition", side_effect=tracked_precondition),
        ):
            completed = self.controller.complete(
                command_id="COMPLETE-STATE-REPLACEMENT",
                artifact_path=artifact,
                expected_generation=issued["generation"],
            )

        persisted = json.loads(self.store.path.read_text(encoding="utf-8"))
        self.assertEqual(1, len(calls))
        self.assertEqual(checked_run_id, completed["run_id"])
        self.assertEqual(completed, persisted)
        self.assertNotEqual("RUN-TAMPERED", persisted["run_id"])
        validate_state(persisted)

    def test_each_phase_exposes_the_exact_small_artifact_schema(self) -> None:
        expected = {
            "plan": ({"outcome", "summary", "questions"}, {"outcome", "summary"}),
            "slice": ({"outcome", "summary", "slices", "questions"}, {"outcome", "summary"}),
            "engineering": ({"outcome", "summary", "questions", "assumptions"}, {"outcome", "summary"}),
            "review": ({"outcome", "findings", "questions"}, {"outcome", "findings"}),
            "qa": ({"outcome", "checks", "blocker", "questions"}, {"outcome", "checks"}),
            "docs": ({"outcome", "summary", "questions"}, {"outcome", "summary"}),
        }
        for phase, (allowed, required) in expected.items():
            with self.subTest(phase=phase):
                schema = artifact_schema(phase, ROLES[phase])
                self.assertEqual(allowed, set(schema["allowed_keys"]))
                self.assertEqual(required, set(schema["required_keys"]))
                self.assertEqual(["pass", "fail", "blocked"], schema["outcome_enum"])
                self.assertTrue(schema["item_shapes"])
                self.assertFalse({"sha256", "id", "inventory"} & set(json.dumps(schema).lower().split('"')))

        issued = self.controller.next(
            command_id="SCHEMA-NEXT", assignment={
                "id": "SCHEMA-A", "worker_id": "schema-planner", "task": "plan",
                "access": {"read": ["**"], "write": []}, "commands": [],
            },
        )
        self.assertEqual(artifact_schema("plan", "planner"), issued["active_assignment"]["artifact_schema"])
        self.assertEqual(issued["active_assignment"]["artifact_schema"], status_view(issued)["active_assignment"]["artifact_schema"])

    def test_unknown_artifact_key_is_rejected(self) -> None:
        self.controller.next(
            command_id="UNKNOWN-NEXT", assignment={
                "id": "UNKNOWN-A", "worker_id": "unknown-planner", "task": "plan",
                "access": {"read": ["**"], "write": []}, "commands": [],
            },
        )
        with self.assertRaisesRegex(PipelineError, "use only"):
            self._complete("UNKNOWN-COMPLETE", {"outcome": "pass", "summary": "done", "unknown": True})

    def test_plan_review_and_qa_outputs_are_assigned_and_excluded_from_checkout(self) -> None:
        plan = self._complete_readonly("plan", "planner-output", {"outcome": "pass", "summary": "planned"})
        self.assertEqual([], plan["artifacts"]["plan"]["controller"]["diff"])
        self.assertNotIn(".agentic-pipeline/outputs/ASSIGN-planner-output.json", plan["artifacts"]["plan"]["controller"]["inventory"])
        self._accept("plan-output")
        self._complete_readonly("slice", "slicer-output", {"outcome": "pass", "summary": "sliced"})
        self._accept("slice-output")
        self._engineer("engineer-output", "candidate-output\n")
        self._accept("engineering-output")
        review = self._complete_readonly("review", "reviewer-output", {"outcome": "pass", "findings": []})
        self.assertEqual([], review["artifacts"]["review"]["controller"]["diff"])
        self._accept("review-output")
        qa = self._complete_readonly("qa", "qa-output", {"outcome": "pass", "checks": ["acceptance: pass"]})
        self.assertEqual([], qa["artifacts"]["qa"]["controller"]["diff"])

    def test_complete_rejects_path_substitution_and_replays_exact_output(self) -> None:
        issued = self.controller.next(
            command_id="OUTPUT-NEXT", assignment={
                "id": "ASSIGN-output", "worker_id": "planner-output", "task": "plan",
                "access": {"read": ["**"], "write": []}, "commands": [],
            },
        )
        self.assertEqual(
            assignment_output_path(issued["active_assignment"]),
            issued["active_assignment"]["output_path"],
        )
        assigned = self._write_artifact({"outcome": "pass", "summary": "planned"})
        wrong = self.root / ".agentic-pipeline" / "outputs" / "substitute.json"
        wrong.write_text('{"outcome":"pass","summary":"wrong"}', encoding="utf-8")
        with self.assertRaisesRegex(PipelineError, "only the assigned artifact path"):
            self.controller.complete(command_id="OUTPUT-COMPLETE", artifact_path=wrong)
        completed = self.controller.complete(command_id="OUTPUT-COMPLETE", artifact_path=assigned)
        self.assertEqual(completed, self.controller.complete(command_id="OUTPUT-COMPLETE", artifact_path=assigned))

    def test_existing_assignment_derives_output_and_reparse_is_rejected(self) -> None:
        issued = self.controller.next(
            command_id="LEGACY-OUTPUT-NEXT", assignment={
                "id": "ASSIGN-legacy-output", "worker_id": "planner-legacy-output", "task": "plan",
                "access": {"read": ["**"], "write": []}, "commands": [],
            },
        )
        legacy = deepcopy(issued)
        legacy["active_assignment"].pop("output_path")
        validate_state(legacy)
        self.store._write(legacy)
        self.assertEqual(
            assignment_output_path(legacy["active_assignment"]),
            status_view(legacy)["active_assignment"]["output_path"],
        )
        assigned = self.root / assignment_output_path(legacy["active_assignment"])
        assigned.parent.mkdir(parents=True, exist_ok=True)
        alternate = assigned.with_name("alternate.json")
        alternate.write_text('{"outcome":"pass","summary":"planned"}', encoding="utf-8")
        try:
            os.symlink(alternate, assigned)
        except OSError as exc:
            assigned.write_text('{"outcome":"pass","summary":"planned"}', encoding="utf-8")
            with mock.patch.object(type(assigned), "is_symlink", autospec=True, side_effect=lambda path: path == assigned):
                with self.assertRaisesRegex(PipelineError, "symlink/junction/reparse"):
                    self.controller.complete(command_id="LEGACY-OUTPUT-COMPLETE")
        else:
            with self.assertRaisesRegex(PipelineError, "symlink/junction/reparse"):
                self.controller.complete(command_id="LEGACY-OUTPUT-COMPLETE")
        assigned.unlink()
        assigned.write_text('{"outcome":"pass","summary":"planned"}', encoding="utf-8")
        self.controller.complete(command_id="LEGACY-OUTPUT-COMPLETE")

    def test_generation_67_review_without_persisted_schema_derives_compatibly(self) -> None:
        self._reach_candidate()
        issued = self.controller.next(
            command_id="GEN67-REVIEW-NEXT", assignment={
                "id": "GEN67-REVIEW", "worker_id": "gen67-reviewer", "task": "review",
                "access": {"read": ["**"], "write": []}, "commands": [],
            },
        )
        legacy = deepcopy(issued)
        legacy["generation"] = 67
        legacy["active_assignment"].pop("artifact_schema")
        legacy["active_assignment"]["capsule"]["context"].pop("review_target")
        self.assertEqual(
            "Independently review the current candidate and report actionable findings.",
            legacy["active_assignment"]["task"],
        )
        validate_state(legacy)
        self.store._write(legacy)
        before = self.store.path.read_bytes()
        view = self.controller.status()["active_assignment"]
        self.assertEqual(artifact_schema("review", "reviewer"), view["artifact_schema"])
        self.assertEqual(assignment_output_path(legacy["active_assignment"]), view["output_path"])
        self.assertEqual(
            {
                "kind": "current_slice_implementation",
                "slice_id": "SLICE-1",
                "required_scope": ["game.txt", "tests/**"],
                "candidate_changes": ["game.txt"],
            },
            view["context"]["review_target"],
        )
        self.assertEqual(before, self.store.path.read_bytes())
        completed = self._complete("GEN67-REVIEW-COMPLETE", {"outcome": "pass", "findings": []})
        self.assertEqual(68, completed["generation"])

    def test_failed_review_routes_to_writable_engineering_and_fresh_verification(self) -> None:
        candidate = self._reach_candidate()
        failed = self._complete_readonly("review", "reviewer-1", {
            "outcome": "fail",
            "findings": [{"text": "Incorrect transition", "severity": "high", "kind": "correctness"}],
        })
        gate_id = next(key for key, item in failed["gates"].items() if item["status"] == "open")
        resumed = self.store.dispatch({
            "name": "resume", "id": "RESUME-REVIEW", "expected_generation": failed["generation"],
            "gate_id": gate_id, "resolution": "remediate finding",
        })
        self.assertEqual("engineering", resumed["phase"])
        self.assertEqual({"plan", "slice", "engineering"}, set(resumed["artifacts"]))
        self.assertEqual("next", status_view(resumed)["next_action"]["command"])
        self.assertEqual(candidate, resumed["gates"][gate_id]["candidate_base"])
        self.assertEqual("Incorrect transition", resumed["gates"][gate_id]["worker_artifact"]["findings"][0]["text"])

        issued = self.controller.next(
            command_id="NEXT-engineer-2",
            assignment={
                "id": "ASSIGN-engineer-2", "worker_id": "engineer-2", "task": "Remediate Review",
                "access": {"read": [], "write": []}, "commands": [],
            },
        )
        self.assertEqual(candidate, issued["active_assignment"]["capsule"]["candidate"])
        self.assertEqual(gate_id, issued["active_assignment"]["capsule"]["context"]["remediation"][0]["gate_id"])
        (self.root / "game.txt").write_text("review-remediated\n", encoding="utf-8")
        self._complete("COMPLETE-engineer-2", {"outcome": "pass", "summary": "Remediated Review finding"})
        self._accept("engineering-2")
        fresh_review = self.controller.status()["next_action"]["assignment"]
        self.assertNotEqual("reviewer-1", fresh_review["worker_id"])
        self.assertEqual(
            {
                "kind": "current_slice_implementation",
                "slice_id": "SLICE-1",
                "required_scope": ["game.txt", "tests/**"],
                "candidate_changes": ["game.txt"],
            },
            fresh_review["context"]["review_target"],
        )
        self._finish_ready("reviewer-2", "qa-2", "docs-2")

    def test_failed_qa_invalidates_engineering_and_review_then_reaches_ready(self) -> None:
        candidate = self._reach_candidate()
        self._review_pass("reviewer-1")
        failed = self._complete_readonly("qa", "qa-1", {"outcome": "fail", "checks": ["launch: product failure"]})
        gate_id = next(key for key, item in failed["gates"].items() if item["status"] == "open")
        resumed = self.store.dispatch({
            "name": "resume", "id": "RESUME-QA", "expected_generation": failed["generation"],
            "gate_id": gate_id, "resolution": "repair product failure",
        })
        self.assertEqual("engineering", resumed["phase"])
        self.assertEqual({"plan", "slice", "engineering"}, set(resumed["artifacts"]))
        self.assertEqual("next", status_view(resumed)["next_action"]["command"])
        self.assertEqual(candidate, resumed["gates"][gate_id]["candidate_base"])
        self._engineer("engineer-2", "qa-remediated\n")
        self._accept("engineering-2")
        self._finish_ready("reviewer-2", "qa-2", "docs-2")

    def test_multiple_failed_gates_use_newest_candidate_independent_of_gate_order(self) -> None:
        first_candidate = self._reach_candidate()
        review_failed = self._complete_readonly("review", "z-reviewer-1", {
            "outcome": "fail",
            "findings": [{"text": "Review failure", "severity": "high", "kind": "correctness"}],
        })
        review_gate = next(key for key, item in review_failed["gates"].items() if item["status"] == "open")
        review_resumed = self.store.dispatch({
            "name": "resume", "id": "RESUME-Z-REVIEW", "expected_generation": review_failed["generation"],
            "gate_id": review_gate, "resolution": "repair Review failure",
        })
        self.assertEqual(review_resumed, self.store.dispatch({
            "name": "resume", "id": "RESUME-Z-REVIEW", "expected_generation": -1,
            "gate_id": review_gate, "resolution": "repair Review failure",
        }))
        second_completed = self._engineer("engineer-review-repair", "candidate-2\n")
        second_candidate = second_completed["artifacts"]["engineering"]["candidate"]
        self.assertGreater(second_candidate["generation"], first_candidate["generation"])
        self._accept("engineering-review-repair")
        self._review_pass("reviewer-2")

        qa_failed = self._complete_readonly("qa", "a-qa-1", {
            "outcome": "fail", "checks": ["runtime: product failure"],
        })
        qa_gate = next(key for key, item in qa_failed["gates"].items() if item["status"] == "open")
        self.assertLess(qa_gate, review_gate)
        qa_resumed = self.store.dispatch({
            "name": "resume", "id": "RESUME-A-QA", "expected_generation": qa_failed["generation"],
            "gate_id": qa_gate, "resolution": "repair QA failure",
        })

        snapshot = inventory(self.root)
        direct_assignment = default_assignment(qa_resumed)
        direct_command = {
            "name": "next", "id": "REDUCER-MULTIGATE-NEXT",
            "expected_generation": qa_resumed["generation"],
            "assignment": {
                "id": direct_assignment["id"],
                "worker_id": direct_assignment["worker_id"],
                "task": direct_assignment["task"], "access": {"read": [], "write": []},
                "commands": [],
            },
            "controller_base": {"inventory": snapshot, "checkout_sha256": inventory_digest(snapshot)},
        }
        for ordered_gate_ids in ((qa_gate, review_gate), (review_gate, qa_gate)):
            reducer_state = deepcopy(qa_resumed)
            reducer_state["gates"] = {
                gate_id: deepcopy(qa_resumed["gates"][gate_id]) for gate_id in ordered_gate_ids
            }
            reduced = reduce(reducer_state, direct_command)
            self.assertEqual(second_candidate, reduced["active_assignment"]["capsule"]["candidate"])
            replay = deepcopy(direct_command); replay["expected_generation"] = -1
            self.assertEqual(reduced, reduce(reduced, replay))
            stale = deepcopy(direct_command); stale.update({"id": "REDUCER-MULTIGATE-STALE", "expected_generation": -1})
            with self.assertRaises(ConflictError):
                reduce(reducer_state, stale)

        issued = self.controller.next(
            command_id="NEXT-engineer-qa-repair",
            assignment={
                "id": "ASSIGN-engineer-qa-repair", "worker_id": "engineer-qa-repair",
                "task": "Repair QA failure", "access": {"read": [], "write": []}, "commands": [],
            },
        )
        self.assertEqual(second_candidate, issued["active_assignment"]["capsule"]["candidate"])
        (self.root / "game.txt").write_text("candidate-3\n", encoding="utf-8")
        self._complete("COMPLETE-engineer-qa-repair", {"outcome": "pass", "summary": "Repaired QA failure"})
        self._accept("engineering-qa-repair")
        ready = self._finish_ready("reviewer-3", "qa-2", "docs-2")
        self.assertTrue(status_view(ready)["ready"])

    def test_reconfigure_after_verification_rework_audits_latest_failed_candidate_only(self) -> None:
        first_candidate = self._reach_candidate()
        review_failed = self._complete_readonly("review", "reviewer-reconfigure-fail", {
            "outcome": "fail",
            "findings": [{"text": "Review failure", "severity": "high", "kind": "correctness"}],
        })
        review_gate = next(key for key, item in review_failed["gates"].items() if item["status"] == "open")
        self.store.dispatch({
            "name": "resume", "id": "RESUME-RECONFIGURE-REVIEW",
            "expected_generation": review_failed["generation"], "gate_id": review_gate,
            "resolution": "Repair Review failure",
        })
        second_completed = self._engineer("engineer-reconfigure-repair", "candidate-2\n")
        second_candidate = second_completed["artifacts"]["engineering"]["candidate"]
        self.assertGreater(second_candidate["generation"], first_candidate["generation"])
        self._accept("engineering-reconfigure-repair")
        self._review_pass("reviewer-reconfigure-pass")
        qa_failed = self._complete_readonly("qa", "qa-reconfigure-fail", {
            "outcome": "fail", "checks": ["runtime: product failure"],
        })
        qa_gate = next(key for key, item in qa_failed["gates"].items() if item["status"] == "open")
        resumed = self.store.dispatch({
            "name": "resume", "id": "RESUME-RECONFIGURE-QA",
            "expected_generation": qa_failed["generation"], "gate_id": qa_gate,
            "resolution": "Repair QA failure",
        })
        self.assertEqual(second_candidate, current_candidate(resumed))

        revised_slices = [{
            "id": "SLICE-RECONFIGURED-AFTER-FAIL",
            "allowed_paths": ["game.txt"], "planned_commands": [self.command],
        }]
        command = {
            "name": "init", "id": "RECONFIGURE-AFTER-VERIFICATION-FAIL",
            "expected_generation": resumed["generation"], "run_id": resumed["run_id"],
            "project_root": resumed["project_root"], "authority": resumed["authority"],
            "slices": self._sealed(revised_slices),
        }
        reconfigured = self.store.dispatch(command)
        prior = reconfigured["history"][-1]["prior"]
        self.assertEqual(second_candidate, prior["candidate"])
        self.assertNotEqual(first_candidate, prior["candidate"])
        self.assertIsNone(current_candidate(reconfigured))
        self.assertIsNone(status_view(reconfigured)["candidate"])
        self.assertEqual({"engineering"}, set(reconfigured["artifacts"]))
        self.assertEqual({}, reconfigured["gates"])

        persisted_bytes = self.store.path.read_bytes()
        replay = deepcopy(command)
        replay["expected_generation"] = -1
        self.assertEqual(reconfigured, self.store.dispatch(replay))
        self.assertEqual(persisted_bytes, self.store.path.read_bytes())
        stale = deepcopy(command)
        stale.update({"id": "RECONFIGURE-AFTER-VERIFICATION-FAIL-STALE", "expected_generation": resumed["generation"]})
        with self.assertRaisesRegex(ConflictError, "stale generation"):
            self.store.dispatch(stale)
        self.assertEqual(persisted_bytes, self.store.path.read_bytes())

    def test_blocked_qa_resumes_qa_but_retry_session_must_be_fresh(self) -> None:
        self._reach_candidate()
        self._review_pass("reviewer-1")
        blocked = self._complete_readonly("qa", "qa-1", {
            "outcome": "blocked", "checks": [], "blocker": "device unavailable",
        })
        gate_id = next(key for key, item in blocked["gates"].items() if item["status"] == "open")
        resumed = self.store.dispatch({
            "name": "resume", "id": "RESUME-QA-BLOCK", "expected_generation": blocked["generation"],
            "gate_id": gate_id, "resolution": "device restored",
        })
        self.assertEqual("qa", resumed["phase"])
        expected = default_assignment(resumed)
        completed_ids = {
            item["actor_id"] for item in resumed["history"] if item.get("actor_id")
        }
        self.assertNotIn(expected["worker_id"], completed_ids)
        action = Controller(self.store).status()["next_action"]
        issued = Controller(self.store).next(
            command_id=action["command_id"], assignment=expected,
            expected_generation=action["expected_generation"],
        )
        self.assertEqual(expected["worker_id"], issued["active_assignment"]["worker_id"])

    def test_engineering_scope_and_commands_ignore_caller_overrides(self) -> None:
        self._reach_engineering()
        issued = self.controller.next(
            command_id="OVERRIDE", assignment={
                "id": "OVERRIDE-A", "worker_id": "engineer-x", "task": "too broad",
                "access": {"read": ["**"], "write": ["**"]}, "commands": [["echo", "forged"]],
            },
        )
        active = issued["active_assignment"]
        self.assertEqual(self.slices[0]["allowed_paths"], active["access"]["write"])
        self.assertEqual(self.slices[0]["planned_commands"], active["commands"])
        self.assertNotIn("**", active["access"]["read"])

    def test_windows_controller_resolves_cmd_shims_without_changing_evidence_argv(self) -> None:
        self.slices = [{
            "id": "SLICE-WINDOWS", "allowed_paths": ["game.txt"],
            "planned_commands": [["npm", "test"]],
        }]
        state = self.store.load()
        self.store.dispatch({
            "name": "init", "id": "WINDOWS-COMMAND-SCOPE",
            "expected_generation": state["generation"], "run_id": state["run_id"],
            "project_root": state["project_root"], "authority": state["authority"],
            "slices": self._sealed(self.slices),
        })
        self._reach_engineering("-windows-command")
        self.controller.next(command_id="WINDOWS-COMMAND-NEXT", assignment={
            "id": "WINDOWS-COMMAND-A", "worker_id": "engineer-windows-command",
            "task": "Implement", "access": {"read": [], "write": []}, "commands": [],
        })
        (self.root / "game.txt").write_text("windows command candidate\n", encoding="utf-8")
        self._write_artifact({"outcome": "pass", "summary": "Implemented"})
        result = ProcessEvidence(0, digest(""), digest(""))
        resolved = r"C:\Program Files\nodejs\npm.CMD"
        with (
            mock.patch("pipeline_v2.runner.os.name", "nt"),
            mock.patch("pipeline_v2.runner.shutil.which", return_value=resolved),
            mock.patch("pipeline_v2.runner.run_process_tree", return_value=result) as invoked,
        ):
            completed = self.controller.complete(command_id="WINDOWS-COMMAND-COMPLETE")
        self.assertEqual([resolved, "test"], invoked.call_args.args[0])
        evidence = completed["artifacts"]["engineering"]["controller"]["commands"]
        self.assertEqual([["npm", "test"]], [item["argv"] for item in evidence])

    def test_controller_disables_node_compile_cache_for_planned_checks(self) -> None:
        cache_command = [
            sys.executable,
            "-c",
            (
                "import os, pathlib; "
                "disabled = os.environ.get('NODE_DISABLE_COMPILE_CACHE') == '1'; "
                "cache = pathlib.Path('node-compile-cache/v-test/cache.bin'); "
                "cache.parent.mkdir(parents=True, exist_ok=True) if not disabled else None; "
                "cache.write_bytes(b'cache') if not disabled else None"
            ),
        ]
        self.slices = [{
            "id": "SLICE-NODE-CACHE", "allowed_paths": ["game.txt"],
            "planned_commands": [cache_command],
        }]
        state = self.store.load()
        self.store.dispatch({
            "name": "init", "id": "NODE-CACHE-SCOPE",
            "expected_generation": state["generation"], "run_id": state["run_id"],
            "project_root": state["project_root"], "authority": state["authority"],
            "slices": self._sealed(self.slices),
        })
        self._reach_engineering("-node-cache")
        completed = self._engineer("engineer-node-cache", "cache-safe candidate\n")
        self.assertFalse((self.root / "node-compile-cache").exists())
        evidence = completed["artifacts"]["engineering"]["controller"]["commands"]
        self.assertEqual([cache_command], [item["argv"] for item in evidence])

    def test_exact_authority_and_structured_slices_are_required(self) -> None:
        state = self.store.load()
        authority = deepcopy(state["authority"])
        authority["items"].pop("requirements"); authority["digest"] = digest(authority["items"])
        malformed = deepcopy(state); malformed["authority"] = authority
        with self.assertRaisesRegex(PipelineError, "exactly requirements"):
            validate_state(malformed)
        invalid_slices = ([], ["SLICE-1"], [{"id": "S", "allowed_paths": ["**"], "planned_commands": [self.command]}])
        for slices in invalid_slices:
            malformed = deepcopy(state); malformed["slices"] = slices
            with self.subTest(slices=slices), self.assertRaises(PipelineError):
                validate_state(malformed)

    def test_generation_fields_reject_booleans_and_floats_before_status_mutation(self) -> None:
        resumed, _, _, gate_id = self._resume_after_changed_docs_review_failure()
        base = deepcopy(resumed)

        def poison_top_level(state: dict, value: object) -> None:
            state["generation"] = value

        def poison_history(state: dict, value: object) -> None:
            state["history"][-1]["generation"] = value

        def poison_artifact_candidate(state: dict, value: object) -> None:
            state["artifacts"]["engineering"]["candidate"]["generation"] = value

        def poison_gate_candidate(state: dict, value: object) -> None:
            state["gates"][gate_id]["candidate_base"]["generation"] = value

        for location, poison in {
            "top-level": poison_top_level,
            "history": poison_history,
            "artifact candidate": poison_artifact_candidate,
            "gate candidate_base": poison_gate_candidate,
        }.items():
            for value in (False, True, 1.5):
                with self.subTest(location=location, value=value):
                    malformed = deepcopy(base)
                    poison(malformed, value)
                    self.store._write(malformed)
                    persisted = self.store.path.read_bytes()
                    with self.assertRaisesRegex(PipelineError, "generation|candidate"):
                        validate_state(malformed)
                    with self.assertRaisesRegex(PipelineError, "generation|candidate"):
                        self.controller.status()
                    self.assertEqual(persisted, self.store.path.read_bytes())
        self.store._write(base)

    def test_candidate_and_gate_candidate_base_require_the_exact_bound_shape(self) -> None:
        resumed, _, _, gate_id = self._resume_after_changed_docs_review_failure()
        targets = {
            "artifact candidate": lambda state: state["artifacts"]["engineering"]["candidate"],
            "gate candidate_base": lambda state: state["gates"][gate_id]["candidate_base"],
        }

        def remove_digest(candidate: dict) -> None:
            candidate.pop("diff_sha256")

        def add_field(candidate: dict) -> None:
            candidate["unexpected"] = "field"

        def change_authority(candidate: dict) -> None:
            candidate["authority_digest"] = digest("foreign authority")

        def use_negative_generation(candidate: dict) -> None:
            candidate["generation"] = -1

        for location, target in targets.items():
            for defect, mutate in {
                "missing digest": remove_digest,
                "extra field": add_field,
                "foreign authority": change_authority,
                "negative generation": use_negative_generation,
            }.items():
                with self.subTest(location=location, defect=defect):
                    malformed = deepcopy(resumed)
                    mutate(target(malformed))
                    with self.assertRaisesRegex(PipelineError, "candidate"):
                        validate_state(malformed)

    def test_runner_and_reducer_reject_noninteger_expected_generation_before_replay(self) -> None:
        action = self.controller.status()["next_action"]
        state = self.store.load()
        snapshot = inventory(self.root)
        command = {
            "name": "next",
            "id": action["command_id"],
            "expected_generation": state["generation"],
            "assignment": action["assignment"],
            "controller_base": {
                "inventory": snapshot,
                "checkout_sha256": inventory_digest(snapshot),
            },
        }
        state_before = deepcopy(state)
        for value in (False, True, 0.0, 1.5):
            with self.subTest(boundary="reducer", value=value):
                malformed = deepcopy(command)
                malformed["expected_generation"] = value
                with self.assertRaisesRegex(PipelineError, "expected generation must be an integer"):
                    reduce(state, malformed)
                self.assertEqual(state_before, state)

        persisted = self.store.path.read_bytes()
        for value in (False, True, 0.0, 1.5):
            with self.subTest(boundary="runner", value=value):
                with self.assertRaisesRegex(PipelineError, "expected generation must be an integer"):
                    self.controller.next(
                        command_id=action["command_id"],
                        assignment=action["assignment"],
                        expected_generation=value,
                    )
                self.assertEqual(persisted, self.store.path.read_bytes())

        issued = self.controller.next(
            command_id=action["command_id"],
            assignment=action["assignment"],
            expected_generation=0,
        )
        issued_bytes = self.store.path.read_bytes()
        for value in (True, 1.0):
            with self.subTest(boundary="runner replay", value=value):
                with self.assertRaisesRegex(PipelineError, "expected generation must be an integer"):
                    self.controller.next(
                        command_id=action["command_id"],
                        assignment=action["assignment"],
                        expected_generation=value,
                    )
                self.assertEqual(issued_bytes, self.store.path.read_bytes())
        self.assertEqual(
            issued,
            self.controller.next(
                command_id=action["command_id"],
                assignment=action["assignment"],
                expected_generation=-1,
            ),
        )
        self.assertEqual(issued_bytes, self.store.path.read_bytes())

    def test_semantic_artifacts_require_summary_structured_findings_and_blocker(self) -> None:
        self.controller.next(
            command_id="ART-N", assignment={
                "id": "ART-A", "worker_id": "planner-art", "task": "plan",
                "access": {"read": ["**"], "write": []}, "commands": [],
            },
        )
        with self.assertRaisesRegex(PipelineError, "summary"):
            self._complete("ART-C", {"outcome": "pass"})
        self.assertIsNotNone(self.store.load()["active_assignment"])

        other = PipelineV2CoreTests("runTest")
        other.setUp()
        try:
            other._reach_candidate()
            with self.assertRaisesRegex(PipelineError, "text, severity, and kind"):
                other._complete_readonly("review", "reviewer-bad", {"outcome": "fail", "findings": [{"impact": "bug"}]})
        finally:
            other.tearDown()

        third = PipelineV2CoreTests("runTest")
        third.setUp()
        try:
            third._reach_candidate(); third._review_pass("reviewer-ok")
            with self.assertRaisesRegex(PipelineError, "blocker"):
                third._complete_readonly("qa", "qa-bad", {"outcome": "blocked", "checks": []})
        finally:
            third.tearDown()

    def test_completed_actor_ids_enforce_engineer_reviewer_independence(self) -> None:
        self._reach_candidate()
        state = self.store.load()
        completed = [item for item in state["history"] if item.get("actor_id")]
        completed_ids = {item["actor_id"].strip().casefold() for item in completed}
        expected = default_assignment(state)
        self.assertNotIn(expected["worker_id"].strip().casefold(), completed_ids)
        action = Controller(self.store).status()["next_action"]
        issued = Controller(self.store).next(
            command_id=action["command_id"], assignment=expected,
            expected_generation=action["expected_generation"],
        )
        self.assertEqual("reviewer", issued["active_assignment"]["role"])
        self.assertTrue(any(item.startswith("engineer-session") for item in completed_ids))

    def test_docs_write_requires_fresh_review_and_qa(self) -> None:
        self._reach_candidate(); self._review_pass("reviewer-1"); self._qa_pass("qa-1")
        issued = self.controller.next(
            command_id="NEXT-docs-1", assignment={
                "id": "ASSIGN-docs-1", "worker_id": "docs-1", "task": "write docs",
                "access": {"read": ["**"], "write": ["notes.md"]}, "commands": [],
            },
        )
        docs_path = self.root / issued["active_assignment"]["access"]["write"][0]
        docs_path.parent.mkdir(parents=True, exist_ok=True)
        docs_path.write_text("documented\n", encoding="utf-8")
        self._complete("COMPLETE-docs-1", {"outcome": "pass", "summary": "Updated docs"})
        self.assertEqual("review", self._accept("docs-1")["phase"])
        action = self.controller.status()["next_action"]
        review_target = action["assignment"]["context"]["review_target"]
        self.assertEqual(
            {
                "kind": "documentation_changes",
                "required_scope": "candidate_changes",
                "candidate_changes": [docs_path.relative_to(self.root).as_posix()],
            },
            review_target,
        )
        self.assertEqual({"kind", "required_scope", "candidate_changes"}, set(review_target))
        self.assertIn(docs_path.relative_to(self.root).as_posix(), action["assignment"]["access"]["read"])
        self.assertLess(
            len(json.dumps(review_target, separators=(",", ":")).encode("utf-8")),
            512,
        )
        issued_review = self.controller.next(
            command_id=action["command_id"], assignment=action["assignment"],
            expected_generation=action["expected_generation"],
        )
        self.assertEqual(
            review_target,
            issued_review["active_assignment"]["capsule"]["context"]["review_target"],
        )
        self._complete("COMPLETE-reviewer-2", {"outcome": "pass", "findings": []})
        self._accept("reviewer-2"); self._qa_pass("qa-2")
        terminal = self.store.load()
        ready = self.controller.ready(command_id="READY-DOCS", expected_generation=terminal["generation"])
        self.assertTrue(status_view(ready)["ready"])

    def test_docs_not_required_contract_grants_no_project_writes_and_allows_noop(self) -> None:
        self._reconfigure_documentation_contract(policy="TS-SCOPE-001")
        self._reach_candidate(); self._review_pass("reviewer-no-docs"); self._qa_pass("qa-no-docs")
        action = self.controller.status()["next_action"]
        self.assertEqual([], action["assignment"]["access"]["write"])
        self.assertEqual(
            [item["path"] for item in self.store.load()["authority"]["items"].values()],
            action["assignment"]["access"]["read"],
        )
        self.assertEqual(
            ".agentic-pipeline/outputs/" + action["assignment"]["id"] + ".json",
            action["assignment"]["output_path"],
        )
        issued = self.controller.next(
            command_id=action["command_id"], assignment=action["assignment"],
            expected_generation=action["expected_generation"],
        )
        self.assertEqual([], issued["active_assignment"]["access"]["write"])
        self._complete("COMPLETE-docs-noop", {
            "outcome": "pass", "summary": "No documentation change required",
        })
        self.assertEqual("ready", self._accept("docs-noop")["phase"])

    def test_docs_distinct_category_policies_allow_noop(self) -> None:
        self._reconfigure_documentation_contract(
            normative_policy="POLICY-NORM", derived_policy="POLICY-DERIVED",
        )
        self._reach_candidate(); self._review_pass("reviewer-distinct-policy"); self._qa_pass("qa-distinct-policy")

        action = self.controller.status()["next_action"]

        self.assertEqual([], action["assignment"]["access"]["write"])
        self.controller.next(
            command_id=action["command_id"], assignment=action["assignment"],
            expected_generation=action["expected_generation"],
        )
        self._complete("COMPLETE-docs-distinct-policy", {
            "outcome": "pass", "summary": "No documentation change required",
        })
        self.assertEqual("ready", self._accept("docs-distinct-policy")["phase"])

    def test_docs_slice_policy_must_match_its_plan_wide_category_policy(self) -> None:
        self._write_approved_plan(
            self.slices,
            normative_documentation_policy="POLICY-NORM",
            derived_documentation_policy="POLICY-DERIVED",
        )
        self.root.joinpath("plan.md").write_text(
            self.root.joinpath("plan.md").read_text(encoding="utf-8").replace(
                "- derived_post_qa_paths: not_required | policy=POLICY-DERIVED",
                "- derived_post_qa_paths: not_required | policy=POLICY-WRONG",
                1,
            ),
            encoding="utf-8",
        )
        self.store = StateStore(
            self.root / ".agentic-pipeline-v2" / "docs-policy-mismatch-state.json"
        )
        self._initialize()
        self._reach_candidate(); self._review_pass("reviewer-policy-mismatch"); self._qa_pass("qa-policy-mismatch")

        with self.assertRaisesRegex(
            PipelineError, "derived slice declarations must repeat the plan-wide policy",
        ):
            self.controller.status()

    def test_docs_required_plan_allows_a_noop_slice_and_grants_only_plan_paths(self) -> None:
        expected = "docs/multi-slice.md"
        self._configure_two_slices()
        self._reconfigure_documentation_contract(
            path=expected,
            slice_documentation={
                "SLICE-2": (
                    "not_required | policy=POLICY-NORM",
                    "not_required | policy=POLICY-DERIVED",
                ),
            },
        )
        self._reach_docs_after_two_slices("docs-partial-noop")

        action = self.controller.status()["next_action"]

        self.assertEqual([expected], action["assignment"]["access"]["write"])

    def test_docs_slice_cannot_invent_a_path_absent_from_plan_wide_authority(self) -> None:
        expected = "docs/multi-slice.md"
        self._configure_two_slices()
        self._reconfigure_documentation_contract(
            path=expected,
            slice_documentation={
                "SLICE-1": ("docs/invented.md", expected),
                "SLICE-2": (
                    "not_required | policy=POLICY-NORM",
                    "not_required | policy=POLICY-DERIVED",
                ),
            },
        )
        self._reach_docs_after_two_slices("docs-invented-path")

        with self.assertRaisesRegex(
            PipelineError, "normative slice paths are absent from the plan-wide declaration",
        ):
            self.controller.status()

    def test_docs_required_plan_rejects_all_slices_as_noop(self) -> None:
        expected = "docs/multi-slice.md"
        noop = (
            "not_required | policy=POLICY-NORM",
            "not_required | policy=POLICY-DERIVED",
        )
        self._configure_two_slices()
        self._reconfigure_documentation_contract(
            path=expected,
            slice_documentation={"SLICE-1": noop, "SLICE-2": noop},
        )
        self._reach_docs_after_two_slices("docs-all-noop")

        with self.assertRaisesRegex(
            PipelineError, "normative plan-wide paths require at least one slice path declaration",
        ):
            self.controller.status()

    def test_docs_slice_rejects_not_required_policy_mixed_with_a_path(self) -> None:
        expected = "docs/multi-slice.md"
        self._configure_two_slices()
        self._reconfigure_documentation_contract(
            path=expected,
            slice_documentation={
                "SLICE-2": (
                    "not_required | policy=POLICY-NORM, docs/extra.md",
                    "not_required | policy=POLICY-DERIVED",
                ),
            },
        )
        self._reach_docs_after_two_slices("docs-malformed-mix")

        with self.assertRaisesRegex(
            PipelineError, "normative declaration must use exact not_required policy syntax",
        ):
            self.controller.status()

    def test_docs_required_category_writes_exact_path_while_other_is_not_required(self) -> None:
        expected = "docs/derived-only.md"
        self._reconfigure_documentation_contract(
            normative_policy="POLICY-NORM", path=expected,
        )
        self._reach_candidate(); self._review_pass("reviewer-derived-only"); self._qa_pass("qa-derived-only")

        action = self.controller.status()["next_action"]

        self.assertEqual([expected], action["assignment"]["access"]["write"])

    def test_docs_required_contract_writes_only_exact_declared_path(self) -> None:
        expected = "docs/declared-release-notes.md"
        unrelated = self.root / "docs" / "unrelated.md"
        unrelated.parent.mkdir(parents=True, exist_ok=True)
        unrelated.write_text("unrelated baseline documentation\n", encoding="utf-8")
        self.store = StateStore(
            self.root / ".agentic-pipeline-v2" / "docs-authority-state.json"
        )
        self._initialize()
        self._reconfigure_documentation_contract(path=expected)
        self._reach_candidate(); self._review_pass("reviewer-docs-required"); self._qa_pass("qa-docs-required")
        action = self.controller.status()["next_action"]
        self.assertEqual([expected], action["assignment"]["access"]["write"])
        self.assertNotIn("docs/unrelated.md", action["assignment"]["access"]["write"])

    def test_docs_missing_plan_declaration_fails_closed(self) -> None:
        self._write_approved_plan(
            self.slices, revision=2, documentation_path=None,
        )
        self.store = StateStore(
            self.root / ".agentic-pipeline-v2" / "missing-docs-state.json"
        )
        self._initialize()
        self._reach_candidate(); self._review_pass("reviewer-docs-missing"); self._qa_pass("qa-docs-missing")

        with self.assertRaisesRegex(
            PipelineError, "exactly one Documentation Strategy",
        ):
            self.controller.status()

    def test_review_target_cannot_be_replaced_by_caller_context(self) -> None:
        self._reach_candidate()
        action = self.controller.status()["next_action"]
        forged = deepcopy(action["assignment"])
        forged["context"]["review_target"] = {
            "kind": "documentation_changes",
            "required_scope": "candidate_changes",
            "candidate_changes": ["future/unassigned.md"],
        }
        before = self.store.path.read_bytes()
        with self.assertRaisesRegex(PipelineError, "review target is controller-derived"):
            Controller(self.store).next(
                command_id=action["command_id"], assignment=forged,
                expected_generation=action["expected_generation"],
            )
        self.assertEqual(before, self.store.path.read_bytes())

    def test_status_prefers_newer_post_docs_review_failure_candidate_and_rejects_drift(self) -> None:
        resumed, _, docs_candidate, _ = self._resume_after_changed_docs_review_failure()
        persisted = self.store.path.read_bytes()

        clean = self.controller.status()
        self.assertEqual("next", clean["next_action"]["command"])
        self.assertEqual(resumed["generation"], clean["next_action"]["expected_generation"])
        self.assertEqual(persisted, self.store.path.read_bytes())

        foreign = self.root / "foreign-after-docs-review-fail.txt"
        foreign.write_text("foreign drift\n", encoding="utf-8")
        drifted = self.controller.status()
        self.assertEqual("terminal", drifted["next_action"]["kind"])
        self.assertEqual("checkout_recovery_required", drifted["next_action"]["result"])
        self.assertEqual(persisted, self.store.path.read_bytes())
        foreign.unlink()

        docs_path = next((self.root / "docs").glob("*.md"))
        accepted_docs = docs_path.read_bytes()
        docs_path.write_text("tampered documentation bytes\n", encoding="utf-8")
        digest_mismatch = self.controller.status()
        self.assertEqual("checkout_recovery_required", digest_mismatch["next_action"]["result"])
        self.assertEqual(persisted, self.store.path.read_bytes())
        docs_path.write_bytes(accepted_docs)

        restored = self.controller.status()
        self.assertEqual("next", restored["next_action"]["command"])
        self.assertEqual(docs_candidate["checkout_sha256"], inventory_digest(inventory(self.root)))
        action = restored["next_action"]
        issued = self.controller.next(
            command_id=action["command_id"], assignment=action["assignment"],
            expected_generation=action["expected_generation"],
        )
        self.assertEqual(docs_candidate, issued["active_assignment"]["capsule"]["candidate"])
        self.assertEqual(
            docs_candidate["checkout_sha256"],
            issued["active_assignment"]["base"]["checkout_sha256"],
        )
        issued_bytes = self.store.path.read_bytes()
        self.assertEqual(
            issued,
            self.controller.next(
                command_id=action["command_id"], assignment=action["assignment"],
                expected_generation=-1,
            ),
        )
        self.assertEqual(issued_bytes, self.store.path.read_bytes())

    def test_reducer_next_prefers_newer_post_docs_review_failure_candidate_and_replays(self) -> None:
        resumed, _, docs_candidate, _ = self._resume_after_changed_docs_review_failure()
        action = status_view(resumed)["next_action"]
        snapshot = inventory(self.root)
        command = {
            "name": "next", "id": action["command_id"],
            "expected_generation": action["expected_generation"],
            "assignment": action["assignment"],
            "controller_base": {
                "inventory": snapshot, "checkout_sha256": inventory_digest(snapshot),
            },
        }

        reduced = reduce(resumed, command)
        active = reduced["active_assignment"]
        self.assertEqual(docs_candidate, active["capsule"]["candidate"])
        self.assertEqual(docs_candidate["checkout_sha256"], active["base"]["checkout_sha256"])

        replay = deepcopy(command)
        replay["expected_generation"] = -1
        self.assertEqual(reduced, reduce(reduced, replay))
        stale = deepcopy(command)
        stale.update({"id": "STALE-POST-DOCS-REMEDIATION-NEXT", "expected_generation": resumed["generation"] - 1})
        with self.assertRaisesRegex(ConflictError, "stale generation"):
            reduce(resumed, stale)

    def test_post_docs_remediation_candidate_is_authority_strict_and_slice_bounded(self) -> None:
        resumed, retained, docs_candidate, gate_id = self._resume_after_changed_docs_review_failure()
        completed_event = next(
            item for item in reversed(resumed["history"])
            if isinstance(item.get("completed_slice_id"), str)
        )
        invalid_cases = {}
        authority_mismatch = deepcopy(resumed)
        authority_mismatch["gates"][gate_id]["candidate_base"]["authority_digest"] = digest("other authority")
        invalid_cases["authority mismatch"] = authority_mismatch
        malformed_digest = deepcopy(resumed)
        malformed_digest["gates"][gate_id]["candidate_base"]["checkout_sha256"] = "not-a-digest"
        invalid_cases["malformed digest"] = malformed_digest
        completed_slice_boundary = deepcopy(resumed)
        boundary_event = next(
            item for item in reversed(completed_slice_boundary["history"])
            if item.get("id") == completed_event["id"]
        )
        boundary_event["generation"] = docs_candidate["generation"]
        wrong_phase = deepcopy(resumed)
        wrong_phase["phase"] = "review"
        validate_state(wrong_phase)
        self.assertIsNone(Controller._remediation_candidate(wrong_phase))
        self.assertIsNone(reducer_module._latest_remediation_candidate(wrong_phase))

        snapshot = inventory(self.root)
        checkout_sha256 = inventory_digest(snapshot)
        for label, state in invalid_cases.items():
            with self.subTest(label=label):
                with self.assertRaisesRegex(PipelineError, "gate candidate_base is malformed"):
                    validate_state(state)
                self.assertIsNone(Controller._remediation_candidate(state))
                self.assertIsNone(reducer_module._latest_remediation_candidate(state))
                self.store._write(state)
                before = self.store.path.read_bytes()
                with self.assertRaisesRegex(PipelineError, "gate candidate_base is malformed"):
                    self.controller.status()
                self.assertEqual(before, self.store.path.read_bytes())

        validate_state(completed_slice_boundary)
        self.assertIsNone(Controller._remediation_candidate(completed_slice_boundary))
        self.assertIsNone(reducer_module._latest_remediation_candidate(completed_slice_boundary))
        action = status_view(completed_slice_boundary)["next_action"]
        command = {
            "name": "next", "id": action["command_id"],
            "expected_generation": action["expected_generation"],
            "assignment": action["assignment"],
            "controller_base": {
                "inventory": snapshot, "checkout_sha256": checkout_sha256,
            },
        }
        with self.assertRaisesRegex(PipelineError, "retained candidate base"):
            reduce(completed_slice_boundary, command)
        self.store._write(completed_slice_boundary)
        view = self.controller.status()
        self.assertEqual("checkout_recovery_required", view["next_action"]["result"])

        tampered = deepcopy(resumed)
        tampered["gates"][gate_id]["candidate_base"]["checkout_sha256"] = digest("tampered checkout")
        self.store._write(tampered)
        self.assertEqual(
            "checkout_recovery_required", self.controller.status()["next_action"]["result"],
        )
        action = status_view(tampered)["next_action"]
        with self.assertRaisesRegex(PipelineError, "retained candidate base"):
            reduce(tampered, {
                "name": "next", "id": action["command_id"],
                "expected_generation": action["expected_generation"],
                "assignment": action["assignment"],
                "controller_base": {
                    "inventory": snapshot, "checkout_sha256": checkout_sha256,
                },
            })

    def test_equal_or_older_remediation_gate_never_overrides_retained_candidate(self) -> None:
        retained = self._reach_candidate()
        failed = self._complete_readonly(
            "review", "reviewer-equal-gate",
            {
                "outcome": "fail",
                "findings": [{
                    "text": "Repair the retained candidate",
                    "severity": "P1",
                    "kind": "correctness",
                }],
            },
        )
        gate_id = next(
            key for key, item in failed["gates"].items() if item["status"] == "open"
        )
        resumed = self.controller.transition({
            "name": "resume", "id": "RESUME-equal-gate",
            "expected_generation": failed["generation"], "gate_id": gate_id,
            "resolution": "Repair the retained candidate",
        })
        self.assertEqual(retained, current_candidate(resumed))
        snapshot = inventory(self.root)
        checkout_sha256 = inventory_digest(snapshot)

        for label, generation in (
            ("equal", retained["generation"]),
            ("older", retained["generation"] - 1),
        ):
            with self.subTest(label=label):
                state = deepcopy(resumed)
                candidate = state["gates"][gate_id]["candidate_base"]
                candidate["generation"] = generation
                candidate["checkout_sha256"] = digest(f"{label} untrusted checkout")
                state["artifacts"]["engineering"]["worker"]["outcome"] = "blocked"
                validate_state(state)
                self.assertIsNone(Controller._remediation_candidate(state))
                self.assertIsNone(reducer_module._latest_remediation_candidate(state))
                self.store._write(state)
                action = self.controller.status()["next_action"]
                self.assertEqual("next", action["command"])
                reduced = reduce(state, {
                    "name": "next", "id": action["command_id"],
                    "expected_generation": action["expected_generation"],
                    "assignment": action["assignment"],
                    "controller_base": {
                        "inventory": snapshot, "checkout_sha256": checkout_sha256,
                    },
                })
                self.assertEqual(retained, reduced["active_assignment"]["capsule"]["candidate"])

    def test_newer_nonpassing_engineering_inventory_is_the_next_base_for_all_verification_failures(self) -> None:
        for verification_phase in ("review", "qa"):
            for engineering_outcome in ("blocked", "fail"):
                with self.subTest(
                    verification_phase=verification_phase,
                    engineering_outcome=engineering_outcome,
                ):
                    harness = PipelineV2CoreTests("runTest")
                    harness.setUp()
                    try:
                        resumed, candidate = harness._resume_after_verification_and_nonpassing_engineering(
                            verification_phase, engineering_outcome,
                        )
                        persisted = harness.store.path.read_bytes()
                        action = harness.controller.status()["next_action"]
                        self.assertEqual("next", action["command"])

                        foreign = harness.root / "foreign-before-second-engineering.txt"
                        foreign.write_text("foreign drift\n", encoding="utf-8")
                        view = harness.controller.status()
                        self.assertEqual(
                            "checkout_recovery_required", view["next_action"]["result"],
                        )
                        with self.assertRaisesRegex(PipelineError, "checkout drifted"):
                            harness.controller.next(
                                command_id=action["command_id"],
                                assignment=action["assignment"],
                                expected_generation=action["expected_generation"],
                            )
                        self.assertEqual(persisted, harness.store.path.read_bytes())
                        foreign.unlink()

                        with self.assertRaisesRegex(ConflictError, "stale generation"):
                            harness.controller.next(
                                command_id=action["command_id"],
                                assignment=action["assignment"],
                                expected_generation=action["expected_generation"] - 1,
                            )
                        self.assertEqual(persisted, harness.store.path.read_bytes())

                        expected_base = inventory_digest(inventory(harness.root))
                        issued = harness.controller.next(
                            command_id=action["command_id"],
                            assignment=action["assignment"],
                            expected_generation=action["expected_generation"],
                        )
                        self.assertEqual(
                            expected_base,
                            issued["active_assignment"]["base"]["checkout_sha256"],
                        )
                        self.assertEqual(
                            candidate,
                            issued["active_assignment"]["capsule"]["candidate"],
                        )
                        issued_bytes = harness.store.path.read_bytes()
                        self.assertEqual(
                            issued,
                            harness.controller.next(
                                command_id=action["command_id"],
                                assignment=action["assignment"],
                                expected_generation=-1,
                            ),
                        )
                        self.assertEqual(issued_bytes, harness.store.path.read_bytes())
                    finally:
                        harness.tearDown()

    def test_nonpassing_engineering_inventory_baseline_is_strict_and_trusted(self) -> None:
        resumed, candidate = self._resume_after_verification_and_nonpassing_engineering(
            "review", "blocked",
        )
        trusted_inventory = reducer_module._newer_nonpassing_engineering_inventory(
            resumed, candidate,
        )
        self.assertEqual(inventory(self.root), trusted_inventory)

        record = resumed["artifacts"]["engineering"]
        assignment_id = record["assignment_id"]
        cases = {}

        authority_mismatch = deepcopy(resumed)
        authority_mismatch["artifacts"]["engineering"]["controller"]["authority_digest"] = (
            digest("foreign authority")
        )
        cases["authority mismatch"] = authority_mismatch

        digest_mismatch = deepcopy(resumed)
        digest_mismatch["artifacts"]["engineering"]["controller"]["current_checkout_sha256"] = (
            digest("unsealed checkout")
        )
        cases["digest mismatch"] = digest_mismatch

        malformed = deepcopy(resumed)
        malformed_inventory = malformed["artifacts"]["engineering"]["controller"]["inventory"]
        malformed_inventory[next(iter(malformed_inventory))]["size"] = -1
        malformed["artifacts"]["engineering"]["controller"]["current_checkout_sha256"] = (
            inventory_digest(malformed_inventory)
        )
        cases["malformed inventory"] = malformed

        untrusted = deepcopy(resumed)
        untrusted["artifacts"]["engineering"]["candidate_binding"] = None
        cases["untrusted binding"] = untrusted

        for label, generation in (
            ("equal completion", candidate["generation"]),
            ("older completion", candidate["generation"] - 1),
        ):
            state = deepcopy(resumed)
            completion = next(
                item for item in state["history"]
                if item.get("command") == "complete"
                and item.get("assignment_id") == assignment_id
            )
            completion["generation"] = generation
            cases[label] = state

        snapshot = inventory(self.root)
        checkout_sha256 = inventory_digest(snapshot)
        for label, state in cases.items():
            with self.subTest(label=label):
                validate_state(state)
                remediation = Controller._remediation_candidate(state)
                self.assertEqual(candidate, remediation)
                self.assertIsNone(
                    reducer_module._newer_nonpassing_engineering_inventory(state, remediation),
                )
                action = status_view(state)["next_action"]
                with self.assertRaisesRegex(PipelineError, "retained candidate base"):
                    reduce(state, {
                        "name": "next", "id": action["command_id"],
                        "expected_generation": action["expected_generation"],
                        "assignment": action["assignment"],
                        "controller_base": {
                            "inventory": snapshot, "checkout_sha256": checkout_sha256,
                        },
                    })
                self.store._write(state)
                self.assertEqual(
                    "checkout_recovery_required",
                    self.controller.status()["next_action"]["result"],
                )

    def test_forbidden_changes_fail_closed(self) -> None:
        self._reach_engineering()
        self.controller.next(
            command_id="SCOPE-N", assignment={
                "id": "SCOPE-A", "worker_id": "engineer-scope", "task": "bounded",
                "access": {"read": [], "write": []}, "commands": [],
            },
        )
        (self.root / "rogue.txt").write_text("forbidden\n", encoding="utf-8")
        with self.assertRaisesRegex(PipelineError, "forbidden paths"):
            self._complete("SCOPE-C", {"outcome": "pass", "summary": "done"})
        self.assertIsNotNone(self.store.load()["active_assignment"])

    def test_replay_cas_and_controller_only_evidence(self) -> None:
        snapshot = inventory(self.root)
        for command in (
            {"name": "next", "id": "FORGE-N", "controller_base": {"inventory": snapshot, "checkout_sha256": inventory_digest(snapshot)}},
            {"name": "complete", "id": "FORGE-C", "controller": {}},
            {"name": "ready", "id": "FORGE-R", "controller": {}},
        ):
            with self.assertRaisesRegex(PipelineError, "controller-only"):
                self.store.dispatch(command)
        self.assertFalse(hasattr(pipeline_v2, "reduce"))
        self._complete_readonly("plan", "planner-cas", {"outcome": "pass", "summary": "done"})
        state = self.store.load()
        command = {"name": "accept", "id": "CAS-ACCEPT", "expected_generation": state["generation"]}
        accepted = self.store.dispatch(command)
        self.assertEqual(accepted, self.store.dispatch(command))
        with self.assertRaises(ConflictError):
            self.store.dispatch({"name": "accept", "id": "CAS-STALE", "expected_generation": state["generation"]})

    def test_path_rules_are_canonical(self) -> None:
        self.assertTrue(matches("dir/a/b.txt", "dir/**")); self.assertTrue(matches("anything.txt", "**"))
        with self.assertRaises(PipelineError):
            matches("dir/a/b.txt", "dir/*")
        self.assertEqual("dir/file.txt", normalize_rule(r"dir\file.txt"))
        for unsafe in ("C:/file.txt", "C:file.txt", "dir/./file.txt", "dir//file.txt", "bad\x00name"):
            with self.subTest(unsafe=unsafe), self.assertRaises(PipelineError):
                normalize_rule(unsafe)

    def test_existing_init_reconfigures_ready_run_with_cas_replay_and_audit(self) -> None:
        self._reach_candidate()
        before = self._finish_ready("reviewer-reconfig", "qa-reconfig", "docs-reconfig")
        candidate = current_candidate(before)
        self.assertIsNotNone(candidate)

        self._write_approved_plan(self.slices, revision=2)
        revised_slices = [{
            "id": "SLICE-REVISED",
            "allowed_paths": ["game.txt", "tests/**", "docs/**"],
            "planned_commands": [self.command],
        }]
        command = {
            "name": "init", "id": "CMD-RECONFIGURE",
            "expected_generation": before["generation"],
            "run_id": before["run_id"], "project_root": before["project_root"],
            "authority": {"items": authority_items(self.root, {
                "requirements": "requirements.md",
                "specification": "specification.md",
                "plan": "plan.md",
            })},
            "slices": self._sealed(revised_slices),
        }
        try:
            reconfigured = self.store.dispatch(command)
        except ConflictError as exc:
            self.fail(f"existing init must reconfigure a safe-boundary run: {exc}")

        self.assertEqual("plan", reconfigured["phase"])
        self.assertEqual(self._sealed(revised_slices), reconfigured["slices"])
        self.assertEqual({"engineering"}, set(reconfigured["artifacts"]))
        self.assertIsNone(reconfigured["active_assignment"])
        self.assertFalse(any(item["status"] == "open" for item in reconfigured["questions"].values()))
        self.assertFalse(any(item["status"] == "open" for item in reconfigured["gates"].values()))
        self.assertEqual(before["history"], reconfigured["history"][:len(before["history"])])
        audit_json = json.dumps(
            {"history": reconfigured["history"], "gates": reconfigured["gates"]},
            ensure_ascii=False, sort_keys=True,
        )
        self.assertIn(json.dumps(candidate, ensure_ascii=False, sort_keys=True), audit_json)
        self.assertEqual(12, len(reconfigured))
        self.assertEqual(7, len(PHASES)); self.assertEqual(9, len(COMMANDS))

        replay = deepcopy(command); replay["expected_generation"] = -1
        self.assertEqual(reconfigured, self.store.dispatch(replay))
        conflicting = deepcopy(replay)
        conflicting["slices"][0]["allowed_paths"] = ["other/**"]
        with self.assertRaisesRegex(ConflictError, "different input"):
            self.store.dispatch(conflicting)

    def test_public_status_derives_one_machine_action_for_every_route(self) -> None:
        def public_status() -> dict:
            args = cli_parser().parse_args(["--state", str(self.store.path), "status"])
            first = cli_run(args)
            self.assertEqual(first, cli_run(args))
            return first

        views = {"next": public_status()}
        issued = self.controller.next(command_id="NEXT-STATUS-1", assignment={
            "id": "ASSIGN-STATUS-1", "worker_id": "planner-status-1", "task": "Complete plan",
            "access": {"read": ["requirements.md", "specification.md", "plan.md"], "write": []},
            "commands": [],
        })
        views["complete"] = public_status()
        self._complete("COMPLETE-STATUS-1", {
            "outcome": "pass", "summary": "Needs a decision", "questions": ["Choose the approved option"],
        })
        views["decision"] = public_status()
        question_id = views["decision"]["open_questions"][0]
        state = self.store.load()
        self.store.dispatch({
            "name": "answer", "id": "ANSWER-STATUS", "expected_generation": state["generation"],
            "question_id": question_id, "answer": "Use the approved option",
        })
        self._complete_readonly("plan", "planner-status-2", {"outcome": "fail", "summary": "Retry"})
        views["resume"] = public_status()
        gate_id = views["resume"]["open_gates"][0]
        state = self.store.load()
        self.store.dispatch({
            "name": "resume", "id": "RESUME-STATUS", "expected_generation": state["generation"],
            "gate_id": gate_id, "resolution": "Retry the failed plan",
        })
        self._complete_readonly("plan", "planner-status-3", {"outcome": "pass", "summary": "Plan confirmed"})
        views["accept"] = public_status()
        self._accept("status-plan")
        self._complete_readonly("slice", "slicer-status", {"outcome": "pass", "summary": "Slice confirmed"})
        self._accept("status-slice")
        self._engineer("engineer-status", "status-candidate\n"); self._accept("status-engineering")
        self._review_pass("reviewer-status"); self._qa_pass("qa-status")
        ready_state = self._docs_no_change("docs-status")
        views["ready"] = public_status()
        self.controller.ready(command_id="READY-STATUS", expected_generation=ready_state["generation"])
        views["terminal"] = public_status()

        for route, view in views.items():
            with self.subTest(route=route):
                self.assertIn("next_action", view)
                self.assertIsInstance(view["next_action"], dict)
        if not all("next_action" in view for view in views.values()):
            return
        self.assertEqual("next", views["next"]["next_action"]["command"])
        next_assignment = views["next"]["next_action"]["assignment"]
        self.assertEqual(assignment_output_path(next_assignment["id"]), next_assignment["output_path"])
        self.assertTrue(next_assignment["worker_id"] and next_assignment["task"])
        self.assertEqual({"read", "write"}, set(next_assignment["access"]))
        self.assertIn("checks", next_assignment)
        self.assertEqual("complete", views["complete"]["next_action"]["command"])
        self.assertEqual(issued["active_assignment"]["id"], views["complete"]["next_action"]["assignment_id"])
        self.assertEqual("accept", views["accept"]["next_action"]["command"])
        self.assertEqual("resume", views["resume"]["next_action"]["command"])
        self.assertEqual(gate_id, views["resume"]["next_action"]["gate_id"])
        self.assertTrue(views["resume"]["next_action"]["resume_reason"])
        self.assertEqual("answer", views["decision"]["next_action"]["command"])
        self.assertEqual("controller_decision", views["decision"]["next_action"]["route"])
        self.assertEqual(question_id, views["decision"]["next_action"]["question_id"])
        self.assertEqual("ready", views["ready"]["next_action"]["command"])
        self.assertEqual("terminal", views["terminal"]["next_action"]["kind"])
        for route in ("next", "complete", "accept", "resume", "decision", "ready"):
            action = views[route]["next_action"]
            self.assertTrue(action["command_id"])
            self.assertEqual(views[route]["generation"], action["expected_generation"])

    def test_public_status_recovers_the_controller_derived_engineering_packet(self) -> None:
        self._reach_engineering("-packet")
        status_args = cli_parser().parse_args(["--state", str(self.store.path), "status"])
        action = cli_run(status_args)["next_action"]
        assignment = action["assignment"]
        self.assertEqual(self.slices[0]["allowed_paths"], assignment["access"]["write"])
        self.assertEqual(self.slices[0]["planned_commands"], assignment["checks"])

        next_argv = [
            "--state", str(self.store.path), "next",
            "--id", action["command_id"],
            "--expected-generation", str(action["expected_generation"]),
            "--assignment-id", assignment["id"],
            "--worker", assignment["worker_id"],
            "--task", assignment["task"],
        ]
        cli_run(cli_parser().parse_args(next_argv))

        # A lost `next` response must be recoverable from the public status
        # without reading controller state or guessing the derived slice scope.
        active = cli_run(status_args)["active_assignment"]
        self.assertEqual(assignment["worker_id"], active["worker_id"])
        self.assertEqual(assignment["task"], active["task"])
        self.assertEqual(self.slices[0]["allowed_paths"], active["access"]["write"])
        self.assertEqual(self.slices[0]["planned_commands"], active["checks"])
        self.assertEqual(
            self.slices[0],
            {
                key: active["context"]["current_slice"][key]
                for key in ("id", "allowed_paths", "planned_commands")
            },
        )

    def test_next_derives_scope_and_checks_despite_omitted_or_malicious_cli_values(self) -> None:
        status_args = cli_parser().parse_args(["--state", str(self.store.path), "status"])

        def issue(*caller_values: str) -> dict:
            action = cli_run(status_args)["next_action"]
            expected = action["assignment"]
            argv = [
                "--state", str(self.store.path), "next",
                "--id", action["command_id"],
                "--expected-generation", str(action["expected_generation"]),
                "--assignment-id", expected["id"],
                "--worker", expected["worker_id"],
                "--task", expected["task"],
                *caller_values,
            ]
            issued = cli_run(cli_parser().parse_args(argv))["active_assignment"]
            self.assertEqual(expected["access"], issued["access"])
            self.assertEqual(expected["checks"], issued["checks"])
            return issued

        issue("--read", "game.txt")
        self._complete("DERIVE-PLAN-C", {"outcome": "pass", "summary": "Plan confirmed"})
        self._accept("derive-plan")

        issue("--read", "game.txt")
        self._complete("DERIVE-SLICE-C", {"outcome": "pass", "summary": "Slice confirmed"})
        self._accept("derive-slice")

        issue()
        (self.root / "game.txt").write_text("derived assignment candidate\n", encoding="utf-8")
        self._complete("DERIVE-ENGINEERING-C", {"outcome": "pass", "summary": "Implemented"})
        self._accept("derive-engineering")

        issue("--read", "game.txt")
        self._complete("DERIVE-REVIEW-C", {"outcome": "pass", "findings": []})
        self._accept("derive-review")

        wrong_check = json.dumps([sys.executable, "-c", "raise SystemExit(0)"])
        issue("--read", "game.txt", "--run", wrong_check)
        self._complete("DERIVE-QA-C", {"outcome": "pass", "checks": ["canonical checks passed"]})
        self._accept("derive-qa")

        issue("--read", "game.txt", "--write", "game.txt")
        self._complete("DERIVE-DOCS-C", {"outcome": "pass", "summary": "Documentation is current"})

    def test_public_assignment_context_stays_bounded_after_many_decisions(self) -> None:
        status_args = cli_parser().parse_args(["--state", str(self.store.path), "status"])

        for index in range(12):
            action = cli_run(status_args)["next_action"]
            assignment = action["assignment"]
            next_argv = [
                "--state", str(self.store.path), "next",
                "--id", action["command_id"],
                "--expected-generation", str(action["expected_generation"]),
                "--assignment-id", assignment["id"],
                "--worker", assignment["worker_id"],
                "--task", assignment["task"],
            ]
            cli_run(cli_parser().parse_args(next_argv))
            self._complete(f"DECISION-COMPLETE-{index}", {
                "outcome": "pass", "summary": "A bounded Director decision is needed",
                "questions": [f"question-{index}-" + "q" * 900],
            })
            decision = cli_run(status_args)["next_action"]
            answer_argv = [
                "--state", str(self.store.path), "answer",
                "--id", decision["command_id"],
                "--expected-generation", str(decision["expected_generation"]),
                "--question-id", decision["question_id"],
                "--text", f"answer-{index}-" + "a" * 900,
            ]
            cli_run(cli_parser().parse_args(answer_argv))

        action = cli_run(status_args)["next_action"]
        assignment = action["assignment"]
        cli_run(cli_parser().parse_args([
            "--state", str(self.store.path), "next",
            "--id", action["command_id"],
            "--expected-generation", str(action["expected_generation"]),
            "--assignment-id", assignment["id"],
            "--worker", assignment["worker_id"],
            "--task", assignment["task"],
        ]))
        view = cli_run(status_args)
        self.assertLessEqual(len(json.dumps(view, ensure_ascii=False).encode("utf-8")), 8192)
        self.assertEqual(12, view["active_assignment"]["context"]["decision_history"]["total"])

    def test_public_status_routes_approved_authority_drift_to_existing_init(self) -> None:
        self._reach_candidate()
        ready = self._finish_ready("reviewer-authority", "qa-authority", "docs-authority")
        before = self.store.path.read_bytes()
        self._write_approved_plan(self.slices, revision=2)
        args = cli_parser().parse_args(["--state", str(self.store.path), "status"])
        view = cli_run(args)
        self.assertEqual(before, self.store.path.read_bytes())
        action = view["next_action"]
        self.assertEqual("init", action["command"])
        self.assertEqual(ready["generation"], action["expected_generation"])
        self.assertEqual(ready["run_id"], action["run_id"])
        self.assertEqual(ready["project_root"], action["project_root"])
        self.assertEqual({
            name: item["path"] for name, item in ready["authority"]["items"].items()
        }, action["authority"])
        self.assertEqual(ready["slices"], action["slices"])
        self.assertFalse(action["user_input_required"])

        init_argv = [
            "--state", str(self.store.path), "init",
            "--id", action["command_id"], "--root", action["project_root"],
            "--run-id", action["run_id"], "--expected-generation", str(action["expected_generation"]),
        ]
        for name, path in action["authority"].items():
            init_argv += ["--authority", f"{name}={path}"]
        for item in action["slices"]:
            init_argv += ["--slice", json.dumps(item)]
        reconfigured_view = cli_run(cli_parser().parse_args(init_argv))
        reconfigured = self.store.load()
        self.assertEqual("plan", reconfigured_view["phase"])
        self.assertEqual(ready["slices"], reconfigured["slices"])

        self._complete_readonly("plan", "planner-rescope", {"outcome": "pass", "summary": "Authority confirmed"})
        self._accept("authority-plan")
        self._complete_readonly("slice", "slicer-rescope", {
            "outcome": "pass", "summary": "Controller-sealed approved scope confirmed",
        })
        accepted = self._accept("authority-slice")
        self.assertEqual("engineering", accepted["phase"])
        self.assertEqual(ready["slices"], accepted["slices"])
        self.assertEqual("SLICE-1", current_slice(accepted)["id"])

    def test_status_reconfiguration_action_binds_observed_authority_bytes_and_paths(self) -> None:
        before = self.store.path.read_bytes()
        self._write_approved_plan(self.slices, revision=2)
        status_args = cli_parser().parse_args(["--state", str(self.store.path), "status"])
        first = cli_run(status_args)["next_action"]
        self.assertEqual("init", first["command"])

        def init_argv(action: dict, *, plan_path: str | None = None) -> list[str]:
            argv = [
                "--state", str(self.store.path), "init",
                "--id", action["command_id"], "--root", action["project_root"],
                "--run-id", action["run_id"],
                "--expected-generation", str(action["expected_generation"]),
            ]
            for name, path in action["authority"].items():
                argv += ["--authority", f"{name}={plan_path if name == 'plan' and plan_path else path}"]
            for item in action["slices"]:
                argv += ["--slice", json.dumps(item)]
            return argv

        # A status response is a capability for the bytes observed by that status,
        # not permission to hash and bind whichever bytes happen to exist later.
        self._write_approved_plan(self.slices, revision=3)
        with self.assertRaisesRegex(PipelineError, "stale.*authority.*action"):
            cli_run(cli_parser().parse_args(init_argv(first)))
        self.assertEqual(before, self.store.path.read_bytes())

        second = cli_run(status_args)["next_action"]
        self.assertNotEqual(first["command_id"], second["command_id"])
        alternate = self.root / "alternate-plan.md"
        alternate.write_bytes((self.root / "plan.md").read_bytes())
        with self.assertRaisesRegex(PipelineError, "stale.*authority.*action"):
            cli_run(cli_parser().parse_args(init_argv(second, plan_path="alternate-plan.md")))
        self.assertEqual(before, self.store.path.read_bytes())
        alternate.unlink()

        reconfigured = cli_run(cli_parser().parse_args(init_argv(second)))
        self.assertEqual("plan", reconfigured["phase"])
        self.assertEqual(
            authority_items(self.root, second["authority"]), self.store.load()["authority"]["items"],
        )

    def test_inactive_reconfiguration_and_its_replay_reject_late_checkout_drift(self) -> None:
        self._reach_candidate()
        self._write_approved_plan(self.slices, revision=2)
        action = self.controller.status()["next_action"]
        self.assertEqual("init", action["command"])
        command = {
            "name": "init", "id": action["command_id"],
            "expected_generation": action["expected_generation"],
            "run_id": action["run_id"], "project_root": action["project_root"],
            "authority_paths": action["authority"], "slices": action["slices"],
        }

        foreign = self.root / "foreign.txt"
        foreign.write_text("late foreign drift\n", encoding="utf-8")
        before = self.store.path.read_bytes()
        with self.assertRaisesRegex(PipelineError, "checkout drifted"):
            self.controller.reconfigure(command)
        self.assertEqual(before, self.store.path.read_bytes())
        foreign.unlink()

        reconfigured = self.controller.reconfigure(command)
        persisted = self.store.path.read_bytes()
        foreign.write_text("fresh replay drift\n", encoding="utf-8")
        replay_status = self.controller.status()
        self.assertEqual("terminal", replay_status["next_action"]["kind"])
        self.assertEqual("checkout_recovery_required", replay_status["next_action"]["result"])
        with self.assertRaisesRegex(PipelineError, "checkout drifted"):
            self.controller.reconfigure(command)
        self.assertEqual(persisted, self.store.path.read_bytes())
        foreign.unlink()

        self.assertEqual(reconfigured, self.controller.reconfigure(command))
        self.assertEqual(persisted, self.store.path.read_bytes())

    def test_initial_public_baseline_closes_empty_epoch_reconfiguration_and_replay(self) -> None:
        self.store.path.unlink()
        initialized = self.controller.reconfigure({
            "name": "init", "id": "PUBLIC-INIT-BASELINE", "expected_generation": None,
            "run_id": "RUN-TEST", "project_root": str(self.root),
            "authority_paths": {
                "requirements": "requirements.md", "specification": "specification.md",
                "plan": "plan.md",
            },
            "slices": self.slices,
        })
        self.assertEqual("plan", initialized["phase"])
        self.assertIsNone(current_candidate(initialized))

        self._write_approved_plan(self.slices, revision=2)
        action = self.controller.status()["next_action"]
        self.assertEqual("init", action["command"])
        command = {
            "name": "init", "id": action["command_id"],
            "expected_generation": action["expected_generation"],
            "run_id": action["run_id"], "project_root": action["project_root"],
            "authority_paths": action["authority"], "slices": action["slices"],
        }
        foreign = self.root / "foreign.txt"
        foreign.write_text("late empty-epoch drift\n", encoding="utf-8")
        before = self.store.path.read_bytes()
        with self.assertRaisesRegex(PipelineError, "checkout drifted"):
            self.controller.reconfigure(command)
        self.assertEqual(before, self.store.path.read_bytes())
        foreign.unlink()

        reconfigured = self.controller.reconfigure(command)
        persisted = self.store.path.read_bytes()
        foreign2 = self.root / "foreign2.txt"
        foreign2.write_text("post-reconfiguration replay drift\n", encoding="utf-8")
        view = self.controller.status()
        self.assertEqual("checkout_recovery_required", view["next_action"]["result"])
        with self.assertRaisesRegex(PipelineError, "checkout drifted"):
            self.controller.reconfigure(command)
        self.assertEqual(persisted, self.store.path.read_bytes())
        foreign2.unlink()
        self.assertEqual(reconfigured, self.controller.reconfigure(command))
        self.assertEqual(persisted, self.store.path.read_bytes())

    def test_sequential_authority_reconfiguration_uses_epoch_baseline_not_full_interrupt_digest(self) -> None:
        self._reach_engineering("-sequential-reconfigure")
        self.controller.next(command_id="NEXT-SEQUENTIAL-RECONFIGURE", assignment={
            "id": "ASSIGN-SEQUENTIAL-RECONFIGURE",
            "worker_id": "engineer-sequential-reconfigure", "task": "Implement",
        })
        (self.root / "game.txt").write_text("authorized interrupted bytes\n", encoding="utf-8")
        self._write_approved_plan(self.slices, revision=2)

        stale_first = self.controller.status()["next_action"]
        (self.root / "game.txt").write_text("later authorized interrupted bytes\n", encoding="utf-8")
        first = self.controller.status()["next_action"]
        self.assertNotEqual(stale_first["command_id"], first["command_id"])
        stale_command = {
            "name": "init", "id": stale_first["command_id"],
            "expected_generation": stale_first["expected_generation"],
            "run_id": stale_first["run_id"], "project_root": stale_first["project_root"],
            "authority_paths": stale_first["authority"], "slices": stale_first["slices"],
        }
        before_stale = self.store.path.read_bytes()
        with self.assertRaisesRegex(PipelineError, "stale.*authority.*action"):
            self.controller.reconfigure(stale_command)
        self.assertEqual(before_stale, self.store.path.read_bytes())
        first_command = {
            "name": "init", "id": first["command_id"],
            "expected_generation": first["expected_generation"],
            "run_id": first["run_id"], "project_root": first["project_root"],
            "authority_paths": first["authority"], "slices": first["slices"],
        }
        reconfigured = self.controller.reconfigure(first_command)
        self.assertEqual("plan", reconfigured["phase"])

        self._write_approved_plan(self.slices, revision=3)
        second = self.controller.status()["next_action"]
        self.assertEqual("init", second["command"])
        self.assertNotEqual(first["command_id"], second["command_id"])
        second_command = {
            "name": "init", "id": second["command_id"],
            "expected_generation": second["expected_generation"],
            "run_id": second["run_id"], "project_root": second["project_root"],
            "authority_paths": second["authority"], "slices": second["slices"],
        }
        twice_reconfigured = self.controller.reconfigure(second_command)
        self.assertEqual("plan", twice_reconfigured["phase"])

        self._write_approved_plan(self.slices, revision=4)
        third = self.controller.status()["next_action"]
        foreign = self.root / "foreign-sequential.txt"
        foreign.write_text("late foreign drift\n", encoding="utf-8")
        before = self.store.path.read_bytes()
        with self.assertRaisesRegex(PipelineError, "checkout drifted"):
            self.controller.reconfigure({
                "name": "init", "id": third["command_id"],
                "expected_generation": third["expected_generation"],
                "run_id": third["run_id"], "project_root": third["project_root"],
                "authority_paths": third["authority"], "slices": third["slices"],
            })
        self.assertEqual(before, self.store.path.read_bytes())

    @unittest.skipUnless(os.name == "nt", "Windows authority aliases are case-insensitive")
    def test_windows_authority_alias_reconfiguration_returns_and_executes_init(self) -> None:
        store = StateStore(self.root / ".agentic-pipeline-v2" / "authority-alias.json")
        controller = Controller(store)
        initialized = controller.reconfigure({
            "name": "init", "id": "ALIAS-INIT", "expected_generation": None,
            "run_id": "RUN-ALIAS", "project_root": str(self.root),
            "authority_paths": {
                "requirements": "REQUIREMENTS.MD",
                "specification": "SPECIFICATION.MD", "plan": "PLAN.MD",
            },
            "slices": self.slices,
        })
        self._write_approved_plan(self.slices, revision=2)

        action = controller.status()["next_action"]
        self.assertEqual("init", action["command"])
        reconfigured = controller.reconfigure({
            "name": "init", "id": action["command_id"],
            "expected_generation": action["expected_generation"],
            "run_id": action["run_id"], "project_root": action["project_root"],
            "authority_paths": action["authority"], "slices": action["slices"],
        })
        self.assertEqual(initialized["generation"] + 1, reconfigured["generation"])
        self.assertEqual("plan", reconfigured["phase"])

    def test_answer_and_blocked_engineering_resume_replays_verify_checkout_baseline(self) -> None:
        self._reach_engineering("-answer-baseline")
        self.controller.next(command_id="NEXT-ANSWER-BASELINE", assignment={
            "id": "ASSIGN-ANSWER-BASELINE", "worker_id": "engineer-answer-baseline",
            "task": "Implement with an authority-consistent question",
        })
        (self.root / "game.txt").write_text("question candidate\n", encoding="utf-8")
        questioned = self._complete("COMPLETE-ANSWER-BASELINE", {
            "outcome": "pass", "summary": "Decision required",
            "questions": ["Choose the approved behavior"],
        })
        question_id = next(key for key, item in questioned["questions"].items() if item["status"] == "open")
        answer = {
            "name": "answer", "id": "ANSWER-BASELINE",
            "expected_generation": questioned["generation"],
            "question_id": question_id, "answer": "Use the reversible approved behavior",
        }
        answered = self.controller.transition(answer)
        persisted = self.store.path.read_bytes()
        foreign = self.root / "foreign.txt"
        foreign.write_text("drift after answer\n", encoding="utf-8")
        with self.assertRaisesRegex(PipelineError, "checkout drifted"):
            self.controller.transition(answer)
        self.assertEqual(persisted, self.store.path.read_bytes())
        foreign.unlink()
        self.assertEqual(answered, self.controller.transition(answer))
        self.assertEqual(persisted, self.store.path.read_bytes())

        self.controller.next(command_id="NEXT-BLOCKED-BASELINE", assignment={
            "id": "ASSIGN-BLOCKED-BASELINE", "worker_id": "engineer-blocked-baseline",
            "task": "Retry Engineering",
        })
        (self.root / "game.txt").write_text("blocked candidate\n", encoding="utf-8")
        blocked = self._complete("COMPLETE-BLOCKED-BASELINE", {
            "outcome": "blocked", "summary": "External prerequisite unavailable",
        })
        gate_id = next(key for key, item in blocked["gates"].items() if item["status"] == "open")
        resume = {
            "name": "resume", "id": "RESUME-BLOCKED-BASELINE",
            "expected_generation": blocked["generation"], "gate_id": gate_id,
            "resolution": "Retry after the prerequisite recovers",
        }
        resumed = self.controller.transition(resume)
        persisted = self.store.path.read_bytes()
        foreign.write_text("drift after resume\n", encoding="utf-8")
        replay_status = self.controller.status()
        self.assertEqual("terminal", replay_status["next_action"]["kind"])
        self.assertEqual("checkout_recovery_required", replay_status["next_action"]["result"])
        with self.assertRaisesRegex(PipelineError, "checkout drifted"):
            self.controller.transition(resume)
        clean_next = status_view(resumed)["next_action"]
        with self.assertRaisesRegex(PipelineError, "checkout drifted"):
            self.controller.next(
                command_id=clean_next["command_id"],
                expected_generation=clean_next["expected_generation"],
                assignment=clean_next["assignment"],
            )
        self.assertEqual(persisted, self.store.path.read_bytes())
        foreign.unlink()
        self.assertEqual(resumed, self.controller.transition(resume))
        self.assertEqual(persisted, self.store.path.read_bytes())

    def test_every_exact_public_replay_verifies_live_authority_before_returning(self) -> None:
        next_action = Controller(self.store).status()["next_action"]
        next_command_id = next_action["command_id"]
        next_assignment = next_action["assignment"]
        Controller(self.store).next(
            command_id=next_command_id, assignment=next_assignment,
            expected_generation=next_action["expected_generation"],
        )
        completed = self._complete("COMPLETE-AUTHORITY-REPLAY-QUESTION", {
            "outcome": "pass", "summary": "Decision needed", "questions": ["Choose approved option"],
        })
        question_id = next(iter(completed["questions"]))
        answer = {
            "name": "answer", "id": "ANSWER-AUTHORITY-REPLAY",
            "expected_generation": completed["generation"], "question_id": question_id,
            "answer": "Use the approved option",
        }
        self.controller.transition(answer)
        failed = self._complete_readonly(
            "plan", "planner-authority-replay-fail",
            {"outcome": "fail", "summary": "Retry"},
        )
        gate_id = next(key for key, item in failed["gates"].items() if item["status"] == "open")
        resume = {
            "name": "resume", "id": "RESUME-AUTHORITY-REPLAY",
            "expected_generation": failed["generation"], "gate_id": gate_id,
            "resolution": "Retry plan",
        }
        self.controller.transition(resume)
        passed = self._complete_readonly(
            "plan", "planner-authority-replay-pass",
            {"outcome": "pass", "summary": "Plan confirmed"},
        )
        accept = {
            "name": "accept", "id": "ACCEPT-AUTHORITY-REPLAY",
            "expected_generation": passed["generation"],
        }
        self.controller.transition(accept)
        self._complete_readonly("slice", "slicer-authority-replay", {"outcome": "pass", "summary": "Slice confirmed"})
        self._accept("authority-replay-slice")
        self._engineer("engineer-authority-replay", "authority replay candidate\n")
        self._accept("authority-replay-engineering")
        self._review_pass("reviewer-authority-replay")
        self._qa_pass("qa-authority-replay")
        ready_phase = self._docs_no_change("docs-authority-replay")
        self.controller.ready(
            command_id="READY-AUTHORITY-REPLAY", expected_generation=ready_phase["generation"],
        )
        persisted = self.store.path.read_bytes()
        (self.root / "requirements.md").write_text("reopened requirements\n", encoding="utf-8")

        replays = {
            "next": lambda: Controller(self.store).next(
                command_id=next_command_id, assignment=next_assignment,
                expected_generation=next_action["expected_generation"],
            ),
            "answer": lambda: self.controller.transition(answer),
            "resume": lambda: self.controller.transition(resume),
            "accept": lambda: self.controller.transition(accept),
            "ready": lambda: self.controller.ready(
                command_id="READY-AUTHORITY-REPLAY",
                expected_generation=ready_phase["generation"],
            ),
        }
        for route, replay in replays.items():
            with self.subTest(route=route), self.assertRaisesRegex(
                PipelineError, "authority bytes changed"
            ):
                replay()
            self.assertEqual(persisted, self.store.path.read_bytes())

        (self.root / "requirements.md").write_text(
            "approved requirements.md\n", encoding="utf-8",
        )
        (self.root / "game.txt").write_text("post-ready checkout drift\n", encoding="utf-8")
        for route, replay in replays.items():
            with self.subTest(route=route, drift="checkout"), self.assertRaisesRegex(
                PipelineError, "checkout drifted"
            ):
                replay()
            self.assertEqual(persisted, self.store.path.read_bytes())

    def test_status_is_terminal_when_active_checkout_already_has_foreign_drift(self) -> None:
        self._reach_engineering("-status-foreign")
        self.controller.next(command_id="NEXT-STATUS-FOREIGN", assignment={
            "id": "ASSIGN-STATUS-FOREIGN", "worker_id": "engineer-status-foreign",
            "task": "Implement current slice",
        })
        (self.root / "foreign.txt").write_text("not assigned\n", encoding="utf-8")
        self._write_approved_plan(self.slices, revision=2)
        before = self.store.path.read_bytes()

        view = cli_run(cli_parser().parse_args(["--state", str(self.store.path), "status"]))

        self.assertEqual(before, self.store.path.read_bytes())
        self.assertEqual("terminal", view["next_action"]["kind"])
        self.assertEqual("checkout_recovery_required", view["next_action"]["result"])
        self.assertIn("foreign.txt", view["next_action"]["reason"])

    def test_codegraph_control_files_do_not_create_live_checkout_drift(self) -> None:
        control = self.root / ".codegraph"
        control.mkdir()
        database = control / "codegraph.db"
        database.write_bytes(b"before")
        self._reach_engineering("-codegraph-live")
        self.controller.next(command_id="NEXT-CODEGRAPH-LIVE", assignment={
            "id": "ASSIGN-CODEGRAPH-LIVE", "worker_id": "engineer-codegraph-live",
            "task": "Implement current slice",
        })

        database.write_bytes(b"after")
        view = self.controller.status()

        self.assertEqual("complete", view["next_action"]["command"])
        self.assertNotIn(".codegraph/codegraph.db", inventory(self.root))

    def test_pre_exclusion_codegraph_base_is_ignored_compatibly(self) -> None:
        self._reach_engineering("-codegraph-persisted")
        self.controller.next(command_id="NEXT-CODEGRAPH-PERSISTED", assignment={
            "id": "ASSIGN-CODEGRAPH-PERSISTED",
            "worker_id": "engineer-codegraph-persisted",
            "task": "Implement current slice",
        })
        state = self.store.load()
        base = state["active_assignment"]["base"]
        base["inventory"][".codegraph/codegraph.db"] = {
            "kind": "file", "sha256": digest("pre-exclusion-codegraph"), "size": 17,
        }
        base["checkout_sha256"] = inventory_digest(base["inventory"])
        self.store._write(state)
        control = self.root / ".codegraph"
        control.mkdir()
        (control / "codegraph.db").write_bytes(b"live companion bytes")

        view = self.controller.status()

        self.assertEqual("complete", view["next_action"]["command"])

    def test_only_checkout_root_codegraph_directory_is_excluded(self) -> None:
        root_file = self.root / ".codegraph"
        root_file.write_bytes(b"ordinary root file before")
        nested = self.root / "src" / ".codegraph" / "foreign.luau"
        nested.parent.mkdir(parents=True)
        nested.write_text("ordinary nested source before\n", encoding="utf-8")
        self._reach_engineering("-codegraph-boundary")
        self.controller.next(command_id="NEXT-CODEGRAPH-BOUNDARY", assignment={
            "id": "ASSIGN-CODEGRAPH-BOUNDARY",
            "worker_id": "engineer-codegraph-boundary",
            "task": "Implement current slice",
        })

        root_file.write_bytes(b"ordinary root file after")
        nested.write_text("ordinary nested source after\n", encoding="utf-8")
        view = self.controller.status()

        self.assertEqual("checkout_recovery_required", view["next_action"]["result"])
        self.assertIn(".codegraph", view["next_action"]["reason"])
        self.assertIn("src/.codegraph/foreign.luau", view["next_action"]["reason"])

    def test_public_non_init_transition_fails_closed_after_authority_reopen(self) -> None:
        completed = self._complete_readonly(
            "plan", "planner-authority-reopen",
            {"outcome": "pass", "summary": "Plan confirmed"},
        )
        persisted_before = self.store.path.read_bytes()
        self._write_approved_plan(self.slices, revision=2)

        args = cli_parser().parse_args([
            "--state", str(self.store.path), "accept",
            "--id", "ACCEPT-STALE-AUTHORITY",
            "--expected-generation", str(completed["generation"]),
        ])
        with self.assertRaisesRegex(PipelineError, "authority bytes changed.*status.*init"):
            cli_run(args)

        self.assertEqual(persisted_before, self.store.path.read_bytes())
        status = cli_run(
            cli_parser().parse_args(["--state", str(self.store.path), "status"])
        )
        self.assertEqual("init", status["next_action"]["command"])
        self.assertFalse(status["next_action"]["user_input_required"])

    def test_authority_drift_interrupts_active_engineering_with_controller_scope_proof(self) -> None:
        self._reach_engineering("-interrupt")
        issued = self.controller.next(command_id="NEXT-INTERRUPTED", assignment={
            "id": "ASSIGN-INTERRUPTED", "worker_id": "engineer-interrupted", "task": "Implement",
            "access": {"read": [], "write": []}, "commands": [],
        })
        (self.root / "game.txt").write_text("authorized interrupted candidate\n", encoding="utf-8")
        self._write_approved_plan(self.slices, revision=2)
        status_args = cli_parser().parse_args(["--state", str(self.store.path), "status"])
        action = cli_run(status_args)["next_action"]
        self.assertEqual("init", action["command"])

        init_argv = [
            "--state", str(self.store.path), "init", "--id", action["command_id"],
            "--root", action["project_root"], "--run-id", action["run_id"],
            "--expected-generation", str(action["expected_generation"]),
        ]
        for name, path in action["authority"].items():
            init_argv += ["--authority", f"{name}={path}"]
        for item in action["slices"]:
            init_argv += ["--slice", json.dumps(item)]
        foreign = self.root / "foreign.txt"
        foreign.write_text("not assigned\n", encoding="utf-8")
        state_before_rejection = self.store.path.read_bytes()
        with self.assertRaisesRegex(PipelineError, "forbidden paths"):
            cli_run(cli_parser().parse_args(init_argv))
        self.assertEqual(state_before_rejection, self.store.path.read_bytes())
        foreign.unlink()
        reconfigured_view = cli_run(cli_parser().parse_args(init_argv))
        reconfigured = self.store.load()
        self.assertEqual("plan", reconfigured_view["phase"])
        self.assertIsNone(reconfigured["active_assignment"])
        prior = reconfigured["history"][-1]["prior"]
        self.assertEqual(issued["active_assignment"]["id"], prior["interrupted_assignment"]["id"])
        self.assertEqual(["game.txt"], prior["interrupted_paths"])
        interruption = prior["interrupted_assignment"]
        authority_paths = {item["path"] for item in issued["authority"]["items"].values()}
        interrupted_diff = [
            item for item in runner_module.diff(
                issued["active_assignment"]["base"]["inventory"], inventory(self.root),
            )
            if item["path"] not in authority_paths
        ]
        self.assertEqual(inventory_digest(inventory(self.root)), interruption["after_checkout_sha256"])
        self.assertEqual(digest(interrupted_diff), interruption["diff_sha256"])
        self.assertEqual([{"path": "game.txt", "kind": "modify"}], interruption["changes"])

        before = self.store.path.read_bytes()
        self.assertEqual(reconfigured_view, cli_run(cli_parser().parse_args(init_argv)))
        self.assertEqual(before, self.store.path.read_bytes())
        self._complete_readonly("plan", "planner-after-interrupt", {"outcome": "pass", "summary": "Replanned"})
        self._accept("interrupted-plan")
        self._complete_readonly("slice", "slicer-after-interrupt", {
            "outcome": "pass", "summary": "Interrupted path remains in controller-sealed scope",
        })
        accepted = self._accept("interrupted-slice")
        self.assertEqual("engineering", accepted["phase"])
        self.assertEqual("SLICE-1", current_slice(accepted)["id"])


class Schema10ImporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = PipelineV2CoreTests("runTest")
        self.harness.setUp()
        self.root = self.harness.root
        self.slices = self.harness.slices
        self.store = self.harness.store
        self.store.path.unlink()

    def tearDown(self) -> None:
        self.harness.tearDown()

    def _legacy(self) -> dict:
        hashes = authority_items(self.root, {
            "requirements": "requirements.md", "specification": "specification.md", "plan": "plan.md",
        })
        return {
            "schema_version": 10, "project_root": str(self.root), "feature": "legacy-feature", "generation": 10,
            "requirements_path": str(self.root / "requirements.md"), "requirements_sha256": hashes["requirements"]["sha256"],
            "spec_path": str(self.root / "specification.md"), "spec_sha256": hashes["specification"]["sha256"],
            "development_plan_path": str(self.root / "plan.md"), "development_plan_sha256": hashes["plan"]["sha256"],
            "active_write_lease": {"lease_id": "LEASE-1", "role": "engineer", "worker_id": "legacy-worker", "capsule_id": "CAPSULE-1"},
            "lease_snapshots": {"LEASE-1": {"checkout": {"game.txt": digest("legacy game")}}},
        }

    def _first_slice_scope_hold(self) -> dict:
        legacy = self._legacy()
        selected = self.slices[0]
        lease = legacy["active_write_lease"]
        lease.update({
            "phase": "slice_engineering", "write_scope": selected["id"],
            "status": "active", "rebaseline_carried": False,
            "allowed_paths": list(selected["allowed_paths"]),
        })
        legacy.update({
            "phase": "scope_expansion_hold", "execution_stage": "implementation",
            "active_slice": selected["id"], "slice_id": selected["id"],
            "ordered_slices": [item["id"] for item in self.slices],
            "slices": {
                item["id"]: {
                    "id": item["id"],
                    "status": "active" if index == 0 else "pending",
                    "scope_contract": {"editable_paths": list(item["allowed_paths"])},
                }
                for index, item in enumerate(self.slices)
            },
            "engineer_runs": [], "last_engineer_run_id": None,
            "last_engineer_outcome": None,
            "scope_guard": {
                "status": "scope_expansion_hold",
                "hold": {
                    "slice_id": selected["id"], "resume_phase": "slice_engineering",
                    "lease_id": lease["lease_id"],
                    "candidate_paths": list(selected["allowed_paths"]),
                    "development_plan_sha256": legacy["development_plan_sha256"],
                },
            },
        })
        legacy["slices"][selected["id"]]["scope_pre_edit_check"] = {
            "slice_id": selected["id"], "owner_id": lease["worker_id"],
            "development_plan_sha256": legacy["development_plan_sha256"],
            "scope_contract": {"editable_paths": list(selected["allowed_paths"])},
            "status": "passed",
        }
        return legacy

    def test_public_migration_preserves_exact_first_slice_engineering_credit(self) -> None:
        legacy_path = self.root / "legacy-scope-hold.json"
        legacy_path.write_text(json.dumps(self._first_slice_scope_hold()), encoding="utf-8")
        argv = [
            "--state", str(self.store.path), "migrate", "--id", "MIGRATE-SCOPE-HOLD",
            "--legacy-state", str(legacy_path),
            "--slice", json.dumps(self.slices[0]),
        ]

        migrated = cli_run(cli_parser().parse_args(argv))

        self.assertEqual("engineering", migrated["phase"])
        self.assertIsNone(migrated["active_assignment"])
        self.assertEqual("next", migrated["next_action"]["command"])
        self.assertEqual(self.slices[0]["allowed_paths"], migrated["next_action"]["assignment"]["access"]["write"])
        self.assertEqual(self.slices[0]["planned_commands"], migrated["next_action"]["assignment"]["checks"])
        state = self.store.load()
        self.assertEqual("pass", state["artifacts"]["plan"]["worker"]["outcome"])
        self.assertEqual("pass", state["artifacts"]["slice"]["worker"]["outcome"])
        audit = state["gates"]["migration-audit"]
        self.assertEqual("resume_first_slice_engineering", audit["resolution"])
        self.assertEqual("legacy-worker", audit["legacy_context"]["migration"]["legacy_worker_id"])
        self.assertNotEqual(
            "legacy-worker", migrated["next_action"]["assignment"]["worker_id"],
        )
        persisted = self.store.path.read_bytes()
        self.assertEqual(migrated, cli_run(cli_parser().parse_args(argv)))
        self.assertEqual(persisted, self.store.path.read_bytes())

        self.harness._engineer("engineer-after-migration", "migrated-v2\n")
        self.harness._accept("engineering-after-migration")
        self.harness._finish_ready("reviewer-after-migration", "qa-after-migration", "docs-after-migration")

    def test_scope_hold_resume_requires_exact_first_slice_boundary(self) -> None:
        cases = {
            "slice order": lambda legacy: legacy.update({"ordered_slices": ["OTHER"]}),
            "candidate paths": lambda legacy: legacy["scope_guard"]["hold"].update({"candidate_paths": ["other.txt"]}),
            "plan": lambda legacy: legacy["scope_guard"]["hold"].update({"development_plan_sha256": digest("other plan")}),
            "prior engineering": lambda legacy: legacy.update({"engineer_runs": [{"outcome": "pass"}]}),
            "missing pre-edit proof": lambda legacy: legacy["slices"][self.slices[0]["id"]].pop("scope_pre_edit_check"),
            "conflicting run markers": lambda legacy: legacy.update({"last_engineer_run_id": "RUN-OLD", "last_engineer_outcome": "pass"}),
        }
        for label, mutate in cases.items():
            with self.subTest(label=label):
                legacy = self._first_slice_scope_hold()
                mutate(legacy)
                imported = import_schema10(legacy, self.slices)
                self.assertEqual("plan", imported["phase"])
                self.assertEqual("rerun_all_v2_phases", imported["gates"]["migration-audit"]["resolution"])

        self.slices.append({
            "id": "SLICE-2", "allowed_paths": ["legacy-second.txt"],
            "planned_commands": [self.harness.command],
        })
        legacy = self._first_slice_scope_hold()
        supplied = deepcopy(self.slices)
        supplied[1]["allowed_paths"] = ["fresh-second.txt"]
        imported = import_schema10(legacy, supplied)
        self.assertEqual("plan", imported["phase"])
        self.assertEqual("rerun_all_v2_phases", imported["gates"]["migration-audit"]["resolution"])

    def test_missing_engineer_snapshot_falls_back_to_public_plan_baseline(self) -> None:
        legacy = self._first_slice_scope_hold()
        legacy["lease_snapshots"].pop(legacy["active_write_lease"]["lease_id"])
        legacy_path = self.root / "legacy-missing-snapshot.json"
        legacy_path.write_text(json.dumps(legacy), encoding="utf-8")
        migrated = cli_run(cli_parser().parse_args([
            "--state", str(self.store.path), "migrate", "--id", "MIGRATE-NO-SNAPSHOT",
            "--legacy-state", str(legacy_path),
            "--slice", json.dumps(self.slices[0]),
        ]))

        self.assertEqual("plan", migrated["phase"])
        self.assertEqual("next", migrated["next_action"]["command"])
        state = self.store.load()
        self.assertEqual({}, state["gates"])
        self.assertEqual("blocked", state["artifacts"]["plan"]["worker"]["outcome"])
        self.assertEqual(
            state["artifacts"]["plan"]["controller"]["current_checkout_sha256"],
            state["artifacts"]["plan"]["controller"]["base_checkout_sha256"],
        )

    def test_malformed_lease_identity_falls_back_to_plan_without_credit(self) -> None:
        cases = {
            "empty worker": ("LEASE-1", ""),
            "empty lease": ("", "legacy-worker"),
            "unhashable lease": ([], "legacy-worker"),
        }
        for label, (lease_id, worker_id) in cases.items():
            with self.subTest(label=label):
                legacy = self._first_slice_scope_hold()
                legacy["active_write_lease"].update({
                    "lease_id": lease_id, "worker_id": worker_id,
                })
                legacy["scope_guard"]["hold"]["lease_id"] = lease_id
                legacy["slices"][self.slices[0]["id"]]["scope_pre_edit_check"]["owner_id"] = worker_id

                imported = import_schema10(legacy, self.slices)

                self.assertEqual("plan", imported["phase"])
                self.assertEqual({}, imported["gates"])

    def test_schema10_migrates_to_plan_preserves_audit_and_reaches_ready(self) -> None:
        imported = import_schema10(self._legacy(), self.slices)
        validate_state(imported)
        self.assertEqual("plan", imported["phase"]); self.assertEqual({}, imported["artifacts"])
        audit = imported["gates"]["migration-audit"]
        self.assertEqual("closed", audit["status"])
        self.assertEqual("legacy-worker", audit["legacy_context"]["migration"]["legacy_worker_id"])
        imported["slices"] = self.harness._sealed(imported["slices"])
        self.store.dispatch({"name": "migrate", "id": "MIGRATE", "imported": imported})
        self.harness._reach_engineering("-m")
        self.harness._engineer("engineer-m", "migrated-v2\n"); self.harness._accept("engineering-m")
        self.harness._finish_ready("reviewer-m", "qa-m", "docs-m")

    def test_public_migration_baseline_rejects_drift_on_status_replay_and_next(self) -> None:
        legacy_path = self.root / "legacy-state.json"
        legacy_path.write_text(json.dumps(self._legacy()), encoding="utf-8")
        argv = [
            "--state", str(self.store.path), "migrate", "--id", "MIGRATE-BASELINE",
            "--legacy-state", str(legacy_path),
            "--slice", json.dumps(self.slices[0]),
        ]
        migrated_view = cli_run(cli_parser().parse_args(argv))
        self.assertEqual("plan", migrated_view["phase"])
        clean_next = migrated_view["next_action"]
        persisted = self.store.path.read_bytes()

        foreign = self.root / "foreign-after-migrate.txt"
        foreign.write_text("migration drift\n", encoding="utf-8")
        status = self.harness.controller.status()
        self.assertEqual("checkout_recovery_required", status["next_action"]["result"])
        with self.assertRaisesRegex(PipelineError, "checkout drifted"):
            cli_run(cli_parser().parse_args(argv))
        with self.assertRaisesRegex(PipelineError, "checkout drifted"):
            self.harness.controller.next(
                command_id=clean_next["command_id"],
                expected_generation=clean_next["expected_generation"],
                assignment=clean_next["assignment"],
            )
        self.assertEqual(persisted, self.store.path.read_bytes())

        foreign.unlink()
        self.assertEqual(migrated_view, cli_run(cli_parser().parse_args(argv)))
        self.assertEqual(persisted, self.store.path.read_bytes())

    def test_migration_canonicalizes_root_variants_and_exact_init_remains_executable(self) -> None:
        variants = [str(self.root) + os.sep, str(self.root) + os.sep + "."]
        if os.name == "nt":
            variants.append(str(self.root).swapcase())
        for index, variant in enumerate(variants):
            with self.subTest(variant=variant):
                legacy = self._legacy()
                legacy["project_root"] = variant
                imported = import_schema10(legacy, self.slices)
                self.assertEqual(str(self.root), imported["project_root"])
                store = StateStore(
                    self.root / ".agentic-pipeline-v2" / f"migration-root-{index}.json",
                )
                controller = Controller(store)
                controller.migrate({
                    "name": "migrate", "id": f"MIGRATE-ROOT-{index}",
                    "imported": imported,
                })
                self.harness._write_approved_plan(self.slices, revision=index + 2)
                action = controller.status()["next_action"]
                self.assertEqual("init", action["command"])
                reconfigured = controller.reconfigure({
                    "name": "init", "id": action["command_id"],
                    "expected_generation": action["expected_generation"],
                    "run_id": action["run_id"], "project_root": action["project_root"],
                    "authority_paths": action["authority"], "slices": action["slices"],
                })
                self.assertEqual("plan", reconfigured["phase"])
                self.assertEqual(str(self.root), reconfigured["project_root"])

    def test_migration_rejects_unsafe_derived_run_id_before_state(self) -> None:
        legacy = self._legacy()
        legacy["feature"] = "../escape"
        with self.assertRaisesRegex(PipelineError, "run_id.*safe identifier"):
            import_schema10(legacy, self.slices)
        self.assertFalse(self.store.path.exists())

    def test_migration_requires_exact_authority_and_new_slice_records(self) -> None:
        legacy = self._legacy(); legacy.pop("requirements_path")
        with self.assertRaisesRegex(PipelineError, "exactly requirements"):
            import_schema10(legacy, self.slices)
        with self.assertRaisesRegex(PipelineError, "slice"):
            import_schema10(self._legacy(), [])
        with self.assertRaisesRegex(PipelineError, "schema_version 10"):
            import_schema10({"schema_version": 9}, self.slices)


if __name__ == "__main__":
    unittest.main()
