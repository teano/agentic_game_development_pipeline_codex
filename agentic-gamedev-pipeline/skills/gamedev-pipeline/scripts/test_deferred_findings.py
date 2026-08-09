#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("deferred_findings.py")


class DeferredFindingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @property
    def backlog_path(self) -> Path:
        return self.root / "docs" / "engineering" / "deferred-findings.json"

    def run_command(
        self, *arguments: str, expected: int = 0
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *arguments, "--project-root", str(self.root)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(expected, result.returncode, msg=result.stderr or result.stdout)
        return result

    def defer(
        self,
        *,
        occurrence: str = "review-1:F-1",
        severity: str = "major",
        evidence: str = "src/save.lua:42 reproduces loss",
        component: str = "Save",
        root_cause: str = "write is not atomic",
    ) -> dict:
        result = self.run_command(
            "backlog-upsert",
            "--component",
            component,
            "--contract",
            "SaveProfile",
            "--root-cause",
            root_cause,
            "--failure-mode",
            "partial write",
            "--effect",
            "profile loss",
            "--title",
            "Save can lose profile",
            "--problem",
            "A partial write replaces the prior profile",
            "--violated-invariant",
            "last valid profile remains readable",
            "--provisional-severity",
            severity,
            "--reachability",
            "supported_failure_path",
            "--condition",
            "storage rejects second page",
            "--impact",
            "player progress is lost",
            "--evidence",
            evidence,
            "--reentry-condition",
            "a feature changes SaveProfile",
            "--occurrence-id",
            occurrence,
            "--observed-by",
            "reviewer-1",
            "--origin-feature",
            "teleport-module",
            "--current-feature",
            "teleport-module",
            "--current-slice",
            "SLICE-001",
            "--current-revision",
            "rev-1",
            "--scope-relation",
            "preexisting_adjacent",
        )
        return json.loads(result.stdout)

    def read_backlog(self) -> dict:
        return json.loads(self.backlog_path.read_text(encoding="utf-8"))

    def test_init_creates_canonical_tracked_schema_atomically(self) -> None:
        self.run_command("init")
        self.assertEqual(
            {"schema_version": 1, "entries": {}},
            self.read_backlog(),
        )
        self.assertEqual([], list(self.backlog_path.parent.glob("*.tmp")))
        self.assertFalse(self.backlog_path.with_suffix(".json.lock").exists())

    def test_same_fingerprint_extends_one_entry_and_deduplicates_occurrence(self) -> None:
        first = self.defer()
        second = self.defer(
            occurrence="review-2:F-9",
            evidence="tests/save.spec.lua:18 confirms profile loss",
        )
        third = self.defer(
            occurrence="review-2:F-9",
            evidence="tests/save.spec.lua:18 confirms profile loss",
        )
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(second["id"], third["id"])
        backlog = self.read_backlog()
        self.assertEqual(1, len(backlog["entries"]))
        entry = backlog["entries"][first["id"]]
        self.assertEqual(2, len(entry["occurrences"]))
        self.assertEqual(2, len(entry["evidence"]))

    def test_title_revision_and_trigger_do_not_change_fingerprint(self) -> None:
        first = self.defer()
        result = self.run_command(
            "backlog-upsert",
            "--component",
            "  SAVE ",
            "--contract",
            "saveprofile",
            "--root-cause",
            "write   is not atomic",
            "--failure-mode",
            "partial write",
            "--effect",
            "profile loss",
            "--title",
            "Different title and trigger",
            "--problem",
            "Observed on a different concrete trigger and revision",
            "--violated-invariant",
            "last valid profile remains readable",
            "--provisional-severity",
            "major",
            "--reachability",
            "supported_failure_path",
            "--evidence",
            "rev-99 new trigger",
            "--occurrence-id",
            "qa-4:F-2",
            "--observed-by",
            "qa-4",
            "--origin-feature",
            "inventory",
        )
        self.assertEqual(first["id"], json.loads(result.stdout)["id"])

    def test_severity_escalation_requires_new_evidence_and_preserves_history(self) -> None:
        created = self.defer(severity="minor")
        self.run_command(
            "extend",
            "--id",
            created["id"],
            "--provisional-severity",
            "critical",
            expected=2,
        )
        self.run_command(
            "extend",
            "--id",
            created["id"],
            "--provisional-severity",
            "critical",
            "--evidence",
            "production incident INC-42",
        )
        entry = self.read_backlog()["entries"][created["id"]]
        self.assertEqual("critical", entry["provisional_severity"])
        self.assertEqual("minor", entry["severity_history"][0]["from"])
        self.assertEqual("critical", entry["severity_history"][0]["to"])
        self.assertIn("production incident INC-42", entry["severity_history"][0]["evidence"])

    def test_resolved_rediscovery_reopens_without_replacing_history(self) -> None:
        created = self.defer()
        self.run_command(
            "resolve",
            "--id",
            created["id"],
            "--resolved-by",
            "owner-save",
            "--reason",
            "transactional write deployed",
            "--evidence",
            "commit abc fixed write",
        )
        self.defer(
            occurrence="qa-8:F-3",
            evidence="new reproduction after fix",
        )
        entry = self.read_backlog()["entries"][created["id"]]
        self.assertEqual("reopened", entry["status"])
        transitions = [(item["from"], item["to"]) for item in entry["status_history"]]
        self.assertEqual(
            [("deferred_untriaged", "resolved"), ("resolved", "reopened")],
            transitions,
        )
        self.assertEqual(2, len(entry["occurrences"]))

    def test_link_duplicate_and_assign_are_controller_managed(self) -> None:
        canonical = self.defer()
        duplicate = self.defer(
            component="SessionSave",
            root_cause="wrapper does not make the underlying write atomic",
            occurrence="review-3:F-2",
        )
        self.run_command(
            "assign",
            "--id",
            canonical["id"],
            "--owner",
            "save-team",
            "--assigned-by",
            "director",
            "--reason",
            "component ownership",
        )
        self.run_command(
            "link-duplicate",
            "--id",
            duplicate["id"],
            "--canonical-id",
            canonical["id"],
            "--linked-by",
            "director",
            "--reason",
            "same independently fixable defect",
        )
        entries = self.read_backlog()["entries"]
        self.assertEqual("deferred_owned", entries[canonical["id"]]["status"])
        self.assertEqual("save-team", entries[canonical["id"]]["owner"])
        self.assertEqual("duplicate", entries[duplicate["id"]]["status"])
        self.assertEqual(canonical["id"], entries[duplicate["id"]]["links"]["duplicate_of"])

    def write_pipeline_findings(self, item: dict) -> None:
        path = self.root / ".agentic-pipeline" / "findings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"schema_version": 8, "items": [item]}), encoding="utf-8"
        )

    def deferred_candidate(self, reference: str | None = None) -> dict:
        return {
            "id": "F-OUT-1",
            "status": "open",
            "source": "convergence",
            "revision": "rev-1",
            "blocking": False,
            "scope_relation": "preexisting_adjacent",
            "introduced_by_candidate": False,
            "production_reachability": "normal",
            "blocks_acceptance_ids": [],
            "violates_required_invariant": False,
            "deferred_reference": reference,
        }

    def test_scope_check_rejects_silent_discard_then_accepts_canonical_link(self) -> None:
        self.write_pipeline_findings(self.deferred_candidate())
        self.run_command(
            "backlog-scope-check",
            "--revision",
            "rev-1",
            "--source",
            "convergence",
            expected=2,
        )
        entry = self.defer()
        self.write_pipeline_findings(
            self.deferred_candidate(
                f"docs/engineering/deferred-findings.json#{entry['id']}"
            )
        )
        result = self.run_command(
            "backlog-scope-check",
            "--revision",
            "rev-1",
            "--source",
            "convergence",
        )
        self.assertEqual("pass", json.loads(result.stdout)["status"])

    def test_scope_check_returns_candidate_introduction_to_current_scope(self) -> None:
        entry = self.defer()
        candidate = self.deferred_candidate(
            f"docs/engineering/deferred-findings.json#{entry['id']}"
        )
        candidate["introduced_by_candidate"] = True
        candidate["material_scope_change"] = True
        self.write_pipeline_findings(candidate)
        result = self.run_command(
            "backlog-scope-check",
            "--revision",
            "rev-1",
            expected=2,
        )
        self.assertIn("must return to current scope", result.stdout)
        self.assertIn("scope_expansion_hold", result.stdout)


if __name__ == "__main__":
    unittest.main()
