#!/usr/bin/env python3
"""Observable sequential runner for every Python test bundled with the pipeline."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import re
import sys
import time
import traceback
import unittest
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
from typing import TextIO


sys.dont_write_bytecode = True

RUNTIME_GROUPS = {"state", "findings", "activation", "other"}
FAST_EXCLUDED_RUNTIME_GROUPS = {"state"}
RUNTIME_PARTITION_PATTERN = re.compile(r"([1-9][0-9]*)/([1-9][0-9]*)")


@dataclass(frozen=True)
class TestFile:
    path: Path
    relative: str
    group: str
    tests: tuple[unittest.TestCase, ...]
    discovery_error: str | None = None


@dataclass(frozen=True)
class SelectedFile:
    source: TestFile
    tests: tuple[unittest.TestCase, ...]


def _flatten(suite: unittest.TestSuite) -> tuple[unittest.TestCase, ...]:
    tests: list[unittest.TestCase] = []
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            tests.extend(_flatten(item))
        else:
            tests.append(item)
    return tuple(tests)


def _runtime_group(path: Path) -> str:
    return {
        "test_pipeline_state.py": "runtime-state",
        "test_deferred_findings.py": "runtime-findings",
        "test_skill_activation.py": "runtime-activation",
    }.get(path.name, "runtime-other")


def _group(root: Path, path: Path) -> str:
    relative = path.relative_to(root)
    if relative.parts[:2] == ("scripts", "tests"):
        return "bundle"
    skill = relative.parts[1]
    if skill == "gamedev-pipeline":
        return _runtime_group(path)
    return skill.removeprefix("gamedev-")


def _load_file(root: Path, path: Path) -> TestFile:
    relative = path.relative_to(root).as_posix()
    group = _group(root, path)
    module_token = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:12]
    module_name = f"skilltests_{path.stem}_{module_token}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot create import spec for {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        tests = _flatten(unittest.defaultTestLoader.loadTestsFromModule(module))
        return TestFile(path, relative, group, tests)
    except Exception:
        return TestFile(path, relative, group, (), traceback.format_exc())


def discover(
    root: Path, progress: Callable[[int, int, Path], None] | None = None
) -> list[TestFile]:
    paths: set[Path] = set()
    for scripts_dir in (root / "skills").glob("*/scripts"):
        paths.update(scripts_dir.glob("test_*.py"))
    bundle_tests = root / "scripts" / "tests"
    if bundle_tests.is_dir():
        paths.update(bundle_tests.glob("test_*.py"))
    ordered = sorted(paths)
    loaded: list[TestFile] = []
    for index, path in enumerate(ordered, start=1):
        if progress:
            progress(index, len(ordered), path)
        loaded.append(_load_file(root, path))
    return loaded


def _runtime_name(group: str) -> str | None:
    return group.removeprefix("runtime-") if group.startswith("runtime-") else None


def _parse_runtime_requests(
    requests: list[str],
) -> tuple[list[str], tuple[int, int] | None]:
    groups: list[str] = []
    partition: tuple[int, int] | None = None
    for request in requests:
        match = RUNTIME_PARTITION_PATTERN.fullmatch(request)
        if match:
            candidate = (int(match.group(1)), int(match.group(2)))
            if candidate[0] > candidate[1]:
                raise ValueError("runtime partition must use one-based N/TOTAL")
            if partition is not None:
                raise ValueError("only one runtime N/TOTAL partition may be selected")
            partition = candidate
        elif request in RUNTIME_GROUPS or request == "all":
            groups.append(request)
        else:
            choices = ", ".join(("all", *sorted(RUNTIME_GROUPS), "N/TOTAL"))
            raise ValueError(f"unknown runtime group {request!r}; choose {choices}")
    return groups, partition


def _partition_selected_runtime(
    selected: list[SelectedFile],
    partition: tuple[int, int],
    excluded: list[tuple[TestFile, str]],
) -> tuple[list[SelectedFile], int, int, int]:
    runtime_tests = sorted(
        (
            item.source.relative,
            test.id(),
            test,
        )
        for item in selected
        if _runtime_name(item.source.group) is not None
        for test in item.tests
    )
    group_index, group_count = partition
    start = len(runtime_tests) * (group_index - 1) // group_count
    end = len(runtime_tests) * group_index // group_count
    selected_test_ids = {id(test) for _, _, test in runtime_tests[start:end]}
    partitioned: list[SelectedFile] = []
    for item in selected:
        if _runtime_name(item.source.group) is None or item.source.discovery_error:
            partitioned.append(item)
            continue
        tests = tuple(test for test in item.tests if id(test) in selected_test_ids)
        if tests:
            partitioned.append(SelectedFile(item.source, tests))
        else:
            excluded.append(
                (item.source, f"outside runtime partition {group_index}/{group_count}")
            )
    return partitioned, len(runtime_tests), start, end


def select(
    files: list[TestFile],
    *,
    mode: str,
    requested_runtime_groups: list[str],
    runtime_filters: list[str],
    runtime_only: bool,
) -> tuple[
    list[SelectedFile],
    list[tuple[TestFile, str]],
    tuple[int, int, int, int, int, int] | None,
]:
    requested_runtime_groups, runtime_partition = _parse_runtime_requests(
        requested_runtime_groups
    )
    available_runtime = {
        name
        for item in files
        if (name := _runtime_name(item.group)) is not None
    }
    requested = set(requested_runtime_groups)
    if "all" in requested:
        requested = available_runtime
    elif not requested:
        requested = (
            available_runtime
            if mode == "full" or runtime_filters
            else available_runtime - FAST_EXCLUDED_RUNTIME_GROUPS
        )

    selected: list[SelectedFile] = []
    excluded: list[tuple[TestFile, str]] = []
    for item in files:
        runtime_name = _runtime_name(item.group)
        if runtime_name is None:
            if runtime_only:
                excluded.append((item, "--runtime-only"))
            else:
                selected.append(SelectedFile(item, item.tests))
            continue
        if runtime_name not in requested:
            excluded.append((item, f"runtime group {runtime_name!r} not selected"))
            continue
        tests = item.tests
        if runtime_filters and not item.discovery_error:
            tests = tuple(
                test
                for test in tests
                if any(pattern in test.id() for pattern in runtime_filters)
            )
            if not tests:
                excluded.append((item, "no --runtime-filter match"))
                continue
        selected.append(SelectedFile(item, tests))
    partition_report = None
    if runtime_partition is not None:
        selected, candidate_count, start, end = _partition_selected_runtime(
            selected, runtime_partition, excluded
        )
        partition_report = (*runtime_partition, candidate_count, start, end)
    return selected, excluded, partition_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        nargs="?",
        choices=("fast", "full"),
        default="full",
        help=(
            "full (default, backward compatible) runs every discovered file; "
            "fast excludes only runtime-state by default"
        ),
    )
    parser.add_argument(
        "--runtime-group",
        action="append",
        default=[],
        metavar="NAME|N/TOTAL",
        help=(
            "select runtime file groups (all/state/findings/activation/other) or "
            "a deterministic N/TOTAL partition after discovery; repeat to combine "
            "named groups with one partition"
        ),
    )
    parser.add_argument(
        "--runtime-filter",
        action="append",
        default=[],
        metavar="TEXT",
        help=(
            "run runtime test IDs containing TEXT (OR across repeats); without an "
            "explicit runtime group, searches every runtime group"
        ),
    )
    parser.add_argument(
        "--runtime-only",
        action="store_true",
        help="exclude non-runtime files explicitly",
    )
    return parser


def _emit(stream: TextIO, message: str) -> None:
    print(message, file=stream, flush=True)


def run(
    argv: list[str] | None = None,
    *,
    root: Path | None = None,
    stream: TextIO | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    root = root or Path(__file__).resolve().parents[1]
    stream = stream or sys.stdout
    started = time.monotonic()
    _emit(stream, f"DISCOVERY START mode={args.mode}")
    files = discover(
        root,
        lambda index, total, path: _emit(
            stream,
            f"[D {index}/{total}] file={path.relative_to(root).as_posix()}",
        ),
    )
    discovered_tests = sum(len(item.tests) for item in files)
    _emit(
        stream,
        f"DISCOVERED files={len(files)} tests={discovered_tests} mode={args.mode}",
    )
    if not files:
        _emit(stream, "SUMMARY status=ERROR reason=no-tests-discovered")
        return 2

    try:
        selected, excluded, partition_report = select(
            files,
            mode=args.mode,
            requested_runtime_groups=args.runtime_group,
            runtime_filters=args.runtime_filter,
            runtime_only=args.runtime_only,
        )
    except ValueError as exc:
        _emit(stream, f"SUMMARY status=ERROR reason={exc}")
        return 2
    if partition_report is not None:
        group_index, group_count, candidate_count, start, end = partition_report
        _emit(
            stream,
            f"RUNTIME PARTITION group={group_index}/{group_count} "
            f"candidates={candidate_count} selected={end - start} "
            f"range={start + 1}-{end}",
        )
    selected_tests = sum(len(item.tests) for item in selected)
    excluded_tests = discovered_tests - selected_tests
    for item in selected:
        source = item.source
        filtered_count = len(source.tests) - len(item.tests)
        if filtered_count:
            _emit(
                stream,
                f"FILTERED group={source.group} selected={len(item.tests)} "
                f"excluded={filtered_count} file={source.relative} "
                f"patterns={args.runtime_filter!r} "
                f"partition={args.runtime_group!r}",
            )
    for item, reason in excluded:
        _emit(
            stream,
            f"EXCLUDED group={item.group} tests={len(item.tests)} "
            f"file={item.relative} reason={reason}",
        )
    if not selected or not any(item.tests or item.source.discovery_error for item in selected):
        _emit(
            stream,
            f"SUMMARY status=ERROR reason=no-tests-selected excluded_tests={excluded_tests}",
        )
        return 2

    failed_files = 0
    executed_tests = 0
    for index, item in enumerate(selected, start=1):
        source = item.source
        file_started = time.monotonic()
        _emit(
            stream,
            f"[{index}/{len(selected)}] START group={source.group} "
            f"tests={len(item.tests)} file={source.relative}",
        )
        if source.discovery_error:
            _emit(stream, source.discovery_error.rstrip())
            successful = False
        else:
            result = unittest.TextTestRunner(
                stream=stream, verbosity=2, buffer=False
            ).run(unittest.TestSuite(item.tests))
            executed_tests += result.testsRun
            successful = result.wasSuccessful()
        elapsed = time.monotonic() - file_started
        status = "PASS" if successful else "FAIL"
        failed_files += not successful
        _emit(
            stream,
            f"[{index}/{len(selected)}] {status} elapsed={elapsed:.2f}s "
            f"file={source.relative}",
        )

    elapsed = time.monotonic() - started
    status = "PASS" if failed_files == 0 else "FAIL"
    _emit(
        stream,
        f"SUMMARY status={status} mode={args.mode} files_run={len(selected)} "
        f"files_excluded={len(files) - len(selected)} files_failed={failed_files} "
        f"tests_run={executed_tests} "
        f"tests_excluded={excluded_tests} elapsed={elapsed:.2f}s",
    )
    return 0 if failed_files == 0 else 1


def main(argv: list[str] | None = None) -> int:
    for output in (sys.stdout, sys.stderr):
        reconfigure = getattr(output, "reconfigure", None)
        if reconfigure:
            reconfigure(line_buffering=True, write_through=True)
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
