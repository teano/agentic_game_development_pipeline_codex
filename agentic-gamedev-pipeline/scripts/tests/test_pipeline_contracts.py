#!/usr/bin/env python3
"""Static parity checks between the Director protocol and controller CLI."""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import re
import sys
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[2]
CONTROLLER_PATH = (
    PLUGIN_ROOT / "skills" / "gamedev-pipeline" / "scripts" / "pipeline_state.py"
)
PROTOCOL_PATH = (
    PLUGIN_ROOT
    / "skills"
    / "gamedev-pipeline"
    / "references"
    / "pipeline-protocol.md"
)
sys.path.insert(0, str(CONTROLLER_PATH.parent))
MODULE_SPEC = importlib.util.spec_from_file_location(
    "pipeline_state_contract_tested", CONTROLLER_PATH
)
assert MODULE_SPEC and MODULE_SPEC.loader
controller = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(controller)


REQUIRED_FLAGS = {
    "recovery-remediation-complete": {
        "--project-root",
        "--run-id",
        "--worker-id",
        "--lease-id",
        "--capsule",
        "--machine-checks",
        "--semantic-report",
        "--coverage-manifest",
        "--report",
        "--resolved-finding",
    },
    "recovery-review-complete": {
        "--project-root",
        "--revision",
        "--product-revision",
        "--support-revision",
        "--evidence-revision",
        "--run-id",
        "--reviewer-id",
        "--capsule",
        "--status",
        "--report",
        "--credit-manifest",
    },
    "convergence-audit-complete": {
        "--project-root",
        "--revision",
        "--run-id",
        "--reviewer-id",
        "--capsule",
        "--lens",
        "--status",
        "--report",
        "--credit-manifest",
    },
    "review-complete": {
        "--project-root",
        "--revision",
        "--run-id",
        "--reviewer-id",
        "--capsule",
        "--status",
        "--report",
        "--credit-manifest",
    },
    "closure-review-complete": {
        "--project-root",
        "--revision",
        "--run-id",
        "--reviewer-id",
        "--capsule",
        "--status",
        "--report",
        "--credit-manifest",
    },
    "documentation-complete": {
        "--project-root",
        "--mode",
        "--worker-id",
        "--lease-id",
        "--capsule",
        "--semantic-packet",
        "--source-map",
        "--report",
    },
    "accept-finding": {
        "--project-root",
        "--id",
        "--reason",
        "--revision",
        "--authority-id",
    },
}


class PipelineCommandContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.parser = controller.build_parser()
        cls.command_action = next(
            action
            for action in cls.parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        cls.commands = cls.command_action.choices

    def required_flags(self, command: str) -> set[str]:
        return {
            option
            for action in self.commands[command]._actions
            if action.required
            for option in action.option_strings
        }

    def test_protocol_delegates_exact_command_syntax_to_argparse_help(self) -> None:
        protocol = PROTOCOL_PATH.read_text(encoding="utf-8")
        self.assertIn("exact CLI syntax stays in each command's `--help`", protocol)
        self.assertNotIn("| Purpose | Commands |", protocol)
        for command in self.commands:
            with self.subTest(command=command):
                with contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        self.parser.parse_args([command, "--help"])
                self.assertEqual(0, raised.exception.code)

    def test_generic_resolve_command_is_removed(self) -> None:
        self.assertNotIn("resolve-finding", self.commands)
        self.assertNotIn("resolve-finding", self.parser.format_help())
        self.assertNotIn("resolve-finding", PROTOCOL_PATH.read_text(encoding="utf-8").split(
            "## Revision and completion invariants", 1
        )[0].split("Generic `resolve-finding`", 1)[0])

    def test_high_risk_command_required_flags_match_help_contract(self) -> None:
        for command, expected in REQUIRED_FLAGS.items():
            with self.subTest(command=command):
                self.assertEqual(expected, self.required_flags(command))
                help_text = self.commands[command].format_help()
                for option in expected:
                    self.assertIn(option, help_text)

    def test_status_diagnostics_are_mutually_exclusive_and_allowlisted(self) -> None:
        status = self.commands["status"]
        section_action = next(
            action for action in status._actions if "--section" in action.option_strings
        )
        self.assertEqual(tuple(controller.STATUS_SECTIONS), tuple(section_action.choices))
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                self.parser.parse_args(
                    [
                        "status",
                        "--project-root",
                        ".",
                        "--section",
                        "leases",
                        "--full",
                    ]
                )


if __name__ == "__main__":
    unittest.main()
