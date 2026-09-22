from __future__ import annotations

from pathlib import Path
import sys
import unittest


SCRIPTS = Path(__file__).resolve().parents[2]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from pipeline_v2.model import required_qa_identity_ids
from pipeline_v2.tests import test_core as fixtures


class ReviewIdentityContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.h = fixtures.PipelineV2CoreTests("runTest")
        self.h.setUp()
        self.addCleanup(self.h.tearDown)

    def issue(self):
        action = self.h.controller.status()["next_action"]
        return self.h.controller.next(
            command_id=action["command_id"], expected_generation=action["expected_generation"],
        )

    def test_native_current_slice_review_receives_plan_identity_inventory_and_target(self) -> None:
        self.h._reach_candidate()

        issued = self.issue()["active_assignment"]
        context = issued["capsule"]["context"]

        self.assertEqual("review", issued["phase"])
        self.assertEqual("current_slice_implementation", context["review_target"]["kind"])
        self.assertEqual(required_qa_identity_ids(self.h.store.load()), context["required_identity_ids"])
        self.assertEqual([], issued["access"]["write"])
        self.assertEqual(self.h.slices[0]["allowed_paths"], context["review_target"]["required_scope"])

    def test_native_post_docs_review_preserves_bounded_target_without_identity_inventory(self) -> None:
        self.h._resume_after_changed_docs_review_failure()
        docs = self.issue()["active_assignment"]
        docs_path = self.h.root / docs["access"]["write"][0]
        docs_path.parent.mkdir(parents=True, exist_ok=True)
        docs_path.write_text("Corrected documentation only.\n", encoding="utf-8")
        self.h._complete("COMPLETE-DOCS-IDENTITY-CONTEXT", {
            "outcome": "pass", "summary": "Corrected the issued documentation target.",
        })
        self.h._accept("docs-identity-context")

        issued = self.issue()["active_assignment"]
        context = issued["capsule"]["context"]

        self.assertEqual("review", issued["phase"])
        self.assertEqual("documentation_changes", context["review_target"]["kind"])
        self.assertEqual([docs_path.relative_to(self.h.root).as_posix()], context["review_target"]["candidate_changes"])
        self.assertNotIn("required_identity_ids", context)
        self.assertEqual([], issued["access"]["write"])


if __name__ == "__main__":
    unittest.main()
