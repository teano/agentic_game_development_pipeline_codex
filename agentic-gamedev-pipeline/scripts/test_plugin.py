#!/usr/bin/env python3
"""Run every Python test bundled with the plugin and reject an empty suite."""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import unittest
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    loader = unittest.TestLoader()
    aggregate = unittest.TestSuite()
    discovered = 0
    for scripts_dir in sorted((root / "skills").glob("*/scripts")):
        suite = loader.discover(str(scripts_dir), pattern="test_*.py")
        aggregate.addTests(suite)
        discovered += suite.countTestCases()
    if discovered == 0:
        print("error: no plugin tests were discovered", file=sys.stderr)
        return 2
    result = unittest.TextTestRunner(verbosity=2).run(aggregate)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
