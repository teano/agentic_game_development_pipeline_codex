#!/usr/bin/env python3
"""Self-tests for the observable bundled-test runner."""

from __future__ import annotations

import importlib.util
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path


RUNNER = Path(__file__).resolve().parents[1] / "test_skills.py"
SPEC = importlib.util.spec_from_file_location("test_skills_runner", RUNNER)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


PASSING_TEST = """import unittest

class ExampleTests(unittest.TestCase):
    def test_passes(self):
        self.assertTrue(True)
"""


class TestSkillsRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_test(self, relative: str, content: str = PASSING_TEST) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_fast_mode_reports_the_exact_runtime_state_exclusion(self) -> None:
        self.write_test("scripts/tests/test_bundle.py")
        self.write_test("skills/gamedev-pipeline/scripts/pipeline_v2/tests/test_core.py")
        self.write_test("skills/gamedev-pipeline/scripts/test_runtime_smoke.py")
        output = io.StringIO()

        exit_code = runner.run(["fast"], root=self.root, stream=output)
        report = output.getvalue()

        self.assertEqual(0, exit_code, report)
        self.assertIn("DISCOVERY START mode=fast", report)
        self.assertIn("EXCLUDED group=runtime-state tests=1", report)
        self.assertIn("tests_run=2", report)
        self.assertIn("tests_excluded=1", report)
        self.assertIn("SUMMARY status=PASS mode=fast", report)

    def test_runtime_filter_is_explicit_and_failures_are_nonzero(self) -> None:
        self.write_test(
            "skills/gamedev-pipeline/scripts/pipeline_v2/tests/test_core.py",
            """import unittest

class RuntimeTests(unittest.TestCase):
    def test_smoke(self):
        self.assertTrue(True)

    def test_slow_failure(self):
        self.fail('visible failure')
""",
        )
        filtered_output = io.StringIO()
        filtered_exit = runner.run(
            [
                "full",
                "--runtime-only",
                "--runtime-group",
                "state",
                "--runtime-filter",
                "smoke",
            ],
            root=self.root,
            stream=filtered_output,
        )
        self.assertEqual(0, filtered_exit, filtered_output.getvalue())
        self.assertIn(
            "FILTERED group=runtime-state selected=1 excluded=1",
            filtered_output.getvalue(),
        )
        self.assertIn("tests_run=1", filtered_output.getvalue())
        self.assertIn("tests_excluded=1", filtered_output.getvalue())

        full_output = io.StringIO()
        full_exit = runner.run(
            ["full", "--runtime-only", "--runtime-group", "state"],
            root=self.root,
            stream=full_output,
        )
        self.assertEqual(1, full_exit)
        self.assertIn("[1/1] FAIL elapsed=", full_output.getvalue())
        self.assertIn("SUMMARY status=FAIL", full_output.getvalue())

    def test_runtime_partitions_are_balanced_disjoint_and_complete(self) -> None:
        methods = "\n".join(
            f"    def test_case_{index:02d}(self): self.assertTrue(True)"
            for index in range(23)
        )
        self.write_test(
            "skills/gamedev-pipeline/scripts/pipeline_v2/tests/test_core.py",
            f"import unittest\n\nclass RuntimeTests(unittest.TestCase):\n{methods}\n",
        )
        files = runner.discover(self.root)
        all_runtime_ids = {
            test.id()
            for item in files
            if item.group.startswith("runtime-")
            for test in item.tests
        }
        partitions: list[set[str]] = []
        for index in range(1, 11):
            selected, _, report = runner.select(
                files,
                mode="full",
                requested_runtime_groups=["state", f"{index}/10"],
                runtime_filters=[],
                runtime_only=True,
            )
            self.assertIsNotNone(report)
            partitions.append(
                {
                    test.id()
                    for item in selected
                    if item.source.group.startswith("runtime-")
                    for test in item.tests
                }
            )

        self.assertLessEqual(
            max(map(len, partitions)) - min(map(len, partitions)), 1
        )
        self.assertEqual(sum(map(len, partitions)), len(set().union(*partitions)))
        self.assertEqual(all_runtime_ids, set().union(*partitions))

    def test_full_runner_propagates_no_bytecode_policy_to_child_processes(self) -> None:
        helper = self.root / "scripts" / "tests" / "runner_helper.py"
        helper.parent.mkdir(parents=True, exist_ok=True)
        helper.write_text("VALUE = 1\n", encoding="utf-8")
        self.write_test(
            "scripts/tests/test_child_import.py",
            """import pathlib
import subprocess
import sys
import unittest

class ChildImportTests(unittest.TestCase):
    def test_child_import(self):
        subprocess.check_call(
            [sys.executable, '-c', 'import runner_helper'],
            cwd=pathlib.Path(__file__).parent,
        )
""",
        )
        old = os.environ.pop("PYTHONDONTWRITEBYTECODE", None)
        try:
            output = io.StringIO()
            self.assertEqual(0, runner.run(["full"], root=self.root, stream=output), output.getvalue())
            self.assertFalse(any(self.root.rglob("__pycache__")))
        finally:
            if old is not None:
                os.environ["PYTHONDONTWRITEBYTECODE"] = old
            else:
                os.environ.pop("PYTHONDONTWRITEBYTECODE", None)


if __name__ == "__main__":
    unittest.main()
