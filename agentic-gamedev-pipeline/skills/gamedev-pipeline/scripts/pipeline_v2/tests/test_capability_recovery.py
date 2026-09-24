from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[2]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from pipeline_v2.tests import test_core as fixtures
from pipeline_v2.cli import parser, run
from pipeline_v2.model import PipelineError, current_candidate, default_assignment, digest, passing_artifact
from pipeline_v2.process_tree import ProcessEvidence
from pipeline_v2.runner import Controller


class CapabilityRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.h = fixtures.PipelineV2CoreTests()
        self.h.setUp()
        self.addCleanup(self.h.tearDown)
        self.h.controller = Controller(self.h.store)
        self.process = mock.patch("pipeline_v2.runner.run_process_tree", return_value=ProcessEvidence(0, digest("out"), digest("err"))).start()
        self.addCleanup(mock.patch.stopall)
        self.h.store.path.unlink()
        self.h.controller.reconfigure({
            "name": "init", "id": "RECOVERY-INITIAL", "expected_generation": None,
            "run_id": "RUN-RECOVERY", "feature": self.h.feature, "workflow_path": self.h.workflow_path,
            "project_root": str(self.h.root),
            "authority_paths": {"requirements": "requirements.md", "specification": "specification.md", "plan": "plan.md"},
            "slices": self.h.slices,
            "verification": {"version": 1, "confirm_approved_plan": True, "pure_documentation_paths": [],
                "slices": {item["id"]: [{"id": f"check-{index}", "argv": argv, "kind": "deterministic",
                    "timeout_seconds": 20, "independent": False, "input_paths": []}
                    for index, argv in enumerate(item["planned_commands"])] for item in self.h.slices}},
        })

    def cli(self, *args):
        return run(parser().parse_args(["--root", str(self.h.root), "--feature", self.h.feature, *args]))

    def native(self, name, *args):
        action = self.cli("status")["next_action"]
        self.assertEqual(name, action["command"])
        return self.cli(name, "--id", action["command_id"], "--expected-generation", str(action["expected_generation"]), *args)

    def complete(self, artifact):
        self.h._write_artifact(artifact)
        return self.native("complete")

    def reach_qa(self, decisions=None):
        self.native("next")
        (self.h.root / "game.txt").write_text("Reviewed candidate\n", encoding="utf-8")
        self.complete({"outcome": "pass", "summary": "Implemented approved behavior.",
                       **({"technical_decisions": decisions} if decisions else {})})
        self.native("accept")
        self.native("next")
        self.review_assignment = deepcopy(self.h.store.load()["active_assignment"])
        self.complete({"outcome": "pass", "findings": []})
        self.native("accept")
        self.before_qa = deepcopy(self.h.store.load())
        self.native("next")
        return deepcopy(self.h.store.load()["active_assignment"])

    def block(self, decisions=None):
        self.complete({"outcome": "blocked",
                       "checks": self.h._qa_checks("Authorized external channel unavailable.", outcome="not_run"),
                       "blocker": "Authorized external channel unavailable.",
                       "required_action": "Restore the same authorized channel.",
                       **({"technical_decisions": decisions} if decisions else {})})
        return self.h.store.load()

    def packet(self, action=None):
        action = action or self.cli("status")["next_action"]
        return {"binding": deepcopy(action["capability_binding"]),
                "prerequisite": "Authorized external channel",
                "resolution": "Channel restored with the same session ownership and configuration.",
                "evidence": "Read-only readiness probe returned the authorized session and expected response.",
                "unchanged_dependencies": "Candidate, authority, scope, toolchain and acceptance inputs remain unchanged."}

    def recover(self, action=None, packet=None):
        action = action or self.cli("status")["next_action"]
        packet = self.packet(action) if packet is None else packet
        path = self.h.root / self.h.workflow_path / "capability-evidence.json"
        path.write_text(json.dumps(packet), encoding="utf-8")
        return self.cli("recover-capability", "--id", action["command_id"],
                        "--expected-generation", str(action["expected_generation"]), "--evidence", str(path))

    @staticmethod
    def decision(identity="TD-ACTUAL"):
        return {"id": identity, "situation": "Existing integration constraint.", "decision": "Use the approved interface.",
                "basis": "Current source contract.", "checks": ["Read current integration source."],
                "downstream": "Review the interface contract."}

    def test_cli_blocked_qa_recovers_same_owner_with_preserved_credit_and_receipts(self):
        active = self.reach_qa()
        blocked = self.block()
        action = self.cli("status")["next_action"]
        saved = self.h.store.path.read_bytes()
        calls = self.process.call_count
        self.assertEqual("terminal", action["kind"])
        self.assertEqual("user_input_required", action["result"])
        self.assertEqual("recover-capability", action["command"])
        self.assertEqual(active["id"], action["capability_binding"]["assignment_id"])
        self.assertEqual(action, self.cli("status")["next_action"])
        step = self.cli("step", "--expected-generation", str(action["expected_generation"]),
                        "--action-id", action["command_id"], "--through-handoff")
        self.assertEqual("stopped", step["result"])
        self.assertEqual(saved, self.h.store.path.read_bytes())
        self.assertEqual(calls, self.process.call_count)
        for packet in ({}, {"binding": action["capability_binding"]}, {**self.packet(action), "evidence": ""}):
            with self.assertRaisesRegex(PipelineError, "prerequisite evidence"):
                self.recover(action, packet)
            self.assertEqual(saved, self.h.store.path.read_bytes())
        packet = self.packet(action)
        recovered_view = self.recover(action, packet)
        recovered = self.h.store.load()
        self.assertEqual("qa", recovered_view["phase"])
        self.assertEqual("next", recovered_view["next_action"]["command"])
        self.assertIsNone(recovered_view["active_assignment"])
        self.assertFalse(recovered_view["ready"])
        self.assertEqual(blocked["history"], recovered["history"][:-1])
        self.assertEqual(blocked["artifacts"]["qa"], recovered["history"][-1]["prior_artifacts"]["qa"])
        self.assertEqual(packet, recovered["history"][-1]["evidence"])
        self.assertEqual(self.before_qa.get("technical_decisions", {}), recovered.get("technical_decisions", {}))
        for phase in ("engineering", "review"):
            self.assertEqual(blocked["artifacts"][phase], recovered["artifacts"][phase])
            self.assertIsNotNone(passing_artifact(recovered, phase))
        self.assertIsNone(passing_artifact(recovered, "qa"))
        self.assertEqual(current_candidate(blocked), current_candidate(recovered))
        self.assertTrue(recovered["execution"]["receipts"])
        self.assertEqual(blocked["execution"], recovered["execution"])
        # Historical resolution stays local to this epoch, slice and exact candidate.
        for change in ("epoch", "slice", "candidate", "blocked_assignment"):
            moved = deepcopy(recovered)
            if change == "epoch":
                moved["history"].append({"command": "init"})
            elif change == "slice":
                moved["slices"][0]["read_paths"].append("different-input.txt")
            elif change == "candidate":
                moved["artifacts"]["engineering"]["candidate"]["generation"] += 1
            else:
                moved["artifacts"]["qa"]["assignment_id"] = "later-blocked-assignment"
            with self.subTest(context=change):
                self.assertNotIn("capability_recovery", default_assignment(moved).get("context", {}))
        replay_bytes = self.h.store.path.read_bytes()
        self.recover(action, packet)
        self.assertEqual(replay_bytes, self.h.store.path.read_bytes())
        with self.assertRaisesRegex(PipelineError, "different input"):
            self.recover(action, {**packet, "evidence": "Substituted evidence."})
        cursor = self.cli("status")["next_action"]
        issued = self.cli("step", "--expected-generation", str(cursor["expected_generation"]),
                          "--action-id", cursor["command_id"], "--through-handoff")
        self.assertEqual("assignment_issued", issued["outcome"])
        self.assertIn("dispatch", issued["assignment_delivery"])
        dispatch = issued["assignment_delivery"]["dispatch"]
        delivered = json.loads(Path(dispatch["input"]["path"]).read_text(encoding="utf-8"))
        self.assertEqual("full", dispatch["input"]["mode"])
        self.assertEqual(dispatch["input"]["digest"], digest(delivered))
        self.assertEqual(packet, delivered["assignment"]["context"]["capability_recovery"]["evidence"])
        fresh = self.h.store.load()["active_assignment"]
        self.assertEqual(active["worker_id"], fresh["worker_id"])
        self.assertNotEqual(active["id"], fresh["id"])
        self.assertNotEqual(active["output_path"], fresh["output_path"])
        self.assertEqual(active["access"], fresh["access"])
        self.assertEqual(["qa"], [fresh["phase"]])
        recovery_context = fresh["capsule"]["context"]["capability_recovery"]
        self.assertEqual(packet, recovery_context["evidence"])
        self.assertEqual(f"{self.h.workflow_path}/pipeline-state.json#/history/{len(blocked['history'])}/evidence",
                         recovery_context["source_locator"])
        with self.assertRaises(PipelineError):
            cursor = self.cli("status")["next_action"]
            self.cli("complete", "--id", cursor["command_id"], "--expected-generation", str(cursor["expected_generation"]),
                     "--artifact", str(self.h.root / active["output_path"]))
        self.complete({"outcome": "pass", "checks": self.h._qa_checks("Fresh QA observation after capability restoration.")})
        accepted = self.native("accept")
        self.assertEqual("docs", accepted["phase"])
        self.assertEqual(calls, self.process.call_count)

    def test_old_packet_cannot_open_a_second_blocker_or_replace_current_binding(self):
        self.reach_qa()
        self.block()
        first = self.cli("status")["next_action"]
        packet = self.packet(first)
        self.recover(first, packet)
        self.native("next")
        self.block()
        second = self.cli("status")["next_action"]
        saved = self.h.store.path.read_bytes()
        self.recover(first, packet)  # A replay is only a no-op receipt, never a second recovery.
        self.assertEqual(saved, self.h.store.path.read_bytes())
        with self.assertRaisesRegex(PipelineError, "current binding"):
            self.recover(second, packet)
        for key, value in second["capability_binding"].items():
            stale = self.packet(second)
            stale["binding"][key] = True if key == "generation" else str(value) + "-stale"
            with self.subTest(binding=key), self.assertRaisesRegex(PipelineError, "current binding"):
                self.recover(second, stale)
            self.assertEqual(saved, self.h.store.path.read_bytes())
        with self.assertRaises(PipelineError):
            self.recover({**second, "expected_generation": first["expected_generation"]})
        with self.assertRaises(PipelineError):
            self.recover({**second, "command_id": "invented-recovery-id"})
        self.assertEqual(saved, self.h.store.path.read_bytes())

    def test_live_candidate_authority_scope_runtime_and_policy_drift_reject_recovery(self):
        self.reach_qa()
        self.block()
        action, packet = self.cli("status")["next_action"], self.packet()
        saved = self.h.store.path.read_bytes()
        with mock.patch("pipeline_v2.runner.pipeline_runtime_digest", return_value=digest("different-runtime")):
            self.assertEqual("init", self.cli("status")["next_action"]["command"])
            with self.assertRaisesRegex(PipelineError, "runtime changed"):
                self.recover(action, packet)
        original = (self.h.root / "game.txt").read_bytes()
        (self.h.root / "game.txt").write_text("Different product candidate\n", encoding="utf-8")
        self.assertEqual("checkout_recovery_required", self.cli("status")["next_action"]["result"])
        with self.assertRaisesRegex(PipelineError, "drifted"):
            self.recover(action, packet)
        (self.h.root / "game.txt").write_bytes(original)
        plan = self.h.root / "plan.md"
        original = plan.read_bytes()
        self.h._write_approved_plan(self.h.slices, revision=2)
        self.assertEqual("init", self.cli("status")["next_action"]["command"])
        with self.assertRaises(PipelineError):
            self.recover(action, packet)
        altered_slices = deepcopy(self.h.slices)
        altered_slices[0]["allowed_paths"] = ["different-product.txt"]
        self.h._write_approved_plan(altered_slices, revision=3)
        self.assertEqual("init", self.cli("status")["next_action"]["command"])
        with self.assertRaises(PipelineError):
            self.recover(action, packet)
        plan.write_bytes(original)
        policy = self.h.root / ".gitignore"
        original = policy.read_bytes()
        policy.write_bytes(original + b"\n# Changed policy\n")
        self.assertEqual("fresh_init_required", self.cli("status")["next_action"]["result"])
        with self.assertRaisesRegex(PipelineError, "policy drift"):
            self.recover(action, packet)
        policy.write_bytes(original)
        self.assertEqual(saved, self.h.store.path.read_bytes())

    def test_unchanged_init_is_not_a_bypass_for_missing_prerequisite_evidence(self):
        self.reach_qa()
        state = self.block()
        saved = self.h.store.path.read_bytes()
        with self.assertRaisesRegex(PipelineError, "recover-capability"):
            self.h.controller.reconfigure({"name": "init", "id": "OLD-FALLBACK", "expected_generation": state["generation"],
                "run_id": state["run_id"], "feature": state["feature"], "workflow_path": state["workflow_path"],
                "project_root": state["project_root"], "slices": state["slices"],
                "authority_paths": {name: item["path"] for name, item in state["authority"]["items"].items()}})
        self.assertEqual(saved, self.h.store.path.read_bytes())

    def test_auto_blocker_restores_previous_real_decision_and_archives_observation(self):
        previous = self.decision(f"TD-BLOCK-{digest('SLICE-1')[:10]}-qa")
        self.reach_qa([previous])
        blocked = self.block()
        self.assertNotEqual(previous, blocked["technical_decisions"][previous["id"]])
        self.recover()
        recovered = self.h.store.load()
        self.assertEqual(previous, recovered["technical_decisions"][previous["id"]])
        archived = recovered["history"][-1]["prior_artifacts"]["qa"]["capability_blocker_journal"]
        self.assertEqual(previous, archived["previous"])
        self.assertEqual(blocked["technical_decisions"][previous["id"]], archived["entry"])
        self.assertIsNotNone(passing_artifact(recovered, "review"))

    def test_capability_recovery_cannot_undo_a_changed_controller_blocker_entry(self):
        self.reach_qa()
        state = self.block()
        original = deepcopy(state)
        change = state["artifacts"]["qa"]["capability_blocker_journal"]
        state["technical_decisions"][change["id"]] = self.decision(change["id"])
        self.h.store._write(state)
        saved = self.h.store.path.read_bytes()
        with self.assertRaisesRegex(PipelineError, "cannot undo semantic decisions"):
            self.recover()
        self.assertEqual(saved, self.h.store.path.read_bytes())
        original["artifacts"]["qa"]["capability_blocker_journal"] = {}
        self.h.store._write(original)
        saved = self.h.store.path.read_bytes()
        with self.assertRaisesRegex(PipelineError, "invalid controller blocker journal"):
            self.recover()
        self.assertEqual(saved, self.h.store.path.read_bytes())

    def assert_review_then_fresh_qa(self, old_qa, packet):
        view = self.cli("status")
        self.assertEqual("review", view["phase"])
        self.assertEqual("next", view["next_action"]["command"])
        self.assertIsNone(view["active_assignment"])
        self.native("next")
        active = self.h.store.load()["active_assignment"]
        self.assertEqual(self.review_assignment["worker_id"], active["worker_id"])
        self.assertNotEqual(self.review_assignment["id"], active["id"])
        self.assertEqual(packet, active["capsule"]["context"]["capability_recovery"]["evidence"])
        self.complete({"outcome": "pass", "findings": []})
        self.assertEqual("qa", self.native("accept")["phase"])
        self.native("next")
        qa = self.h.store.load()["active_assignment"]
        self.assertEqual(old_qa["worker_id"], qa["worker_id"])
        self.assertNotEqual(old_qa["id"], qa["id"])
        self.assertEqual(packet, qa["capsule"]["context"]["capability_recovery"]["evidence"])
        self.complete({"outcome": "pass", "checks": self.h._qa_checks("Fresh acceptance after renewed Review.")})
        self.assertEqual("docs", self.native("accept")["phase"])

    def test_genuine_worker_decision_routes_review_then_qa_without_stale_credit(self):
        old_qa = self.reach_qa()
        genuine = self.decision()
        blocked = self.block([genuine])
        packet = self.packet()
        self.recover(packet=packet)
        recovered = self.h.store.load()
        self.assertEqual(blocked["technical_decisions"], recovered["technical_decisions"])
        self.assertIsNone(passing_artifact(recovered, "review"))
        self.assertEqual(blocked["artifacts"]["review"], recovered["history"][-1]["prior_artifacts"]["review"])
        self.assert_review_then_fresh_qa(old_qa, packet)

    def test_legacy_blocker_without_previous_journal_metadata_is_not_guessed(self):
        old_qa = self.reach_qa()
        state = self.block()
        state["artifacts"]["qa"].pop("capability_blocker_journal")
        self.h.store._write(state)  # Persisted legacy fixture, not a production migration.
        packet = self.packet()
        self.recover(packet=packet)
        recovered = self.h.store.load()
        self.assertEqual(state["technical_decisions"], recovered["technical_decisions"])
        self.assertIsNone(passing_artifact(recovered, "review"))
        self.assert_review_then_fresh_qa(old_qa, packet)


if __name__ == "__main__":
    unittest.main()
