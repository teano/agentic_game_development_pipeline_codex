from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[2]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pipeline_v2.process_tree as process_tree


class _FakePosixProcess:
    def __init__(self, returncode: int):
        self.returncode = returncode
        self.stdout = io.BytesIO()
        self.stderr = io.BytesIO()

    def wait(self, timeout=None):
        return self.returncode

    def poll(self):
        return self.returncode

    def kill(self):
        self.returncode = -9


class PosixContainmentStructureTests(unittest.TestCase):
    def test_posix_implementation_has_no_pid_scan_or_group_kill_fallback(self) -> None:
        source = Path(process_tree.__file__).read_text(encoding="utf-8")
        self.assertNotIn("_TREE_TOKEN_ENV", source)
        self.assertNotIn('Path("/proc")', source)
        self.assertNotIn("os.killpg(", source)
        self.assertIn("--kill-child=KILL", source)
        self.assertIn("PR_SET_PDEATHSIG", source)
        self.assertIn("expected_parent=int(sys.argv[1])", source)

    def test_probe_tries_privileged_then_safe_user_namespace(self) -> None:
        calls: list[list[str]] = []

        def probe(argv: list[str], **_kwargs):
            calls.append(argv)
            return SimpleNamespace(returncode=0 if "--map-root-user" in argv else 1)

        adapter = process_tree._linux_namespace_adapter(
            platform="linux", which=lambda name: f"/usr/bin/{name}", probe=probe,
        )
        self.assertEqual(2, len(calls))
        self.assertNotIn("--user", calls[0])
        self.assertIn("--user", calls[1])
        self.assertIn("--map-root-user", adapter)

    def test_unavailable_adapter_fails_before_target_launch(self) -> None:
        with (
            mock.patch.object(process_tree, "_linux_namespace_adapter", return_value=None),
            mock.patch.object(process_tree.subprocess, "Popen") as popen,
        ):
            evidence = process_tree._run_posix(
                ["must-not-launch"], cwd=Path.cwd(), env=dict(os.environ), timeout=1.0,
            )
        self.assertEqual(125, evidence.returncode)
        popen.assert_not_called()

    def test_namespace_setup_exit_before_ready_maps_to_technical_125(self) -> None:
        with (
            mock.patch.object(
                process_tree, "_linux_namespace_adapter", return_value=["fake-unshare"],
            ),
            mock.patch.object(
                process_tree.subprocess, "Popen",
                side_effect=lambda *_args, **_kwargs: _FakePosixProcess(7),
            ),
        ):
            evidence = process_tree._run_posix(
                ["must-not-run"], cwd=Path.cwd(), env=dict(os.environ), timeout=1.0,
            )
        self.assertEqual(125, evidence.returncode)

    def test_post_ready_target_return_codes_are_preserved(self) -> None:
        for expected in (0, 7):
            with self.subTest(expected=expected):
                inherited_fds: list[tuple[int, ...]] = []

                def launch(*_args, **kwargs):
                    pass_fds = tuple(kwargs.get("pass_fds", ()))
                    inherited_fds.append(pass_fds)
                    if pass_fds:
                        child_ready_fd = os.dup(pass_fds[0])
                        try:
                            os.write(child_ready_fd, b"R")
                        finally:
                            os.close(child_ready_fd)
                    return _FakePosixProcess(expected)

                with (
                    mock.patch.object(
                        process_tree, "_linux_namespace_adapter",
                        return_value=["fake-unshare"],
                    ),
                    mock.patch.object(
                        process_tree.subprocess, "Popen", side_effect=launch,
                    ),
                ):
                    evidence = process_tree._run_posix(
                        ["target"], cwd=Path.cwd(), env=dict(os.environ), timeout=1.0,
                    )
                self.assertEqual(1, len(inherited_fds))
                self.assertEqual(1, len(inherited_fds[0]))
                self.assertEqual(expected, evidence.returncode)


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux PID namespace runtime test")
class LinuxNamespaceRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        if process_tree._linux_namespace_adapter() is None:
            self.skipTest("util-linux PID namespace containment is unavailable")

    @staticmethod
    def _run(argv: list[str], root: Path, timeout: float = 2.0):
        return process_tree.run_process_tree(
            argv, cwd=root, env=dict(os.environ), timeout=timeout,
        )

    def test_success_nonzero_and_timeout_return_codes_propagate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for expected in (0, 7):
                with self.subTest(expected=expected):
                    evidence = self._run(
                        [sys.executable, "-c", f"raise SystemExit({expected})"], root,
                    )
                    self.assertEqual(expected, evidence.returncode)
            evidence = self._run(
                [sys.executable, "-c", "import time;time.sleep(5)"],
                root, timeout=0.1,
            )
            self.assertEqual(124, evidence.returncode)

    def test_setsid_scrubbed_environment_cannot_escape_success_or_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for label, parent_sleep, timeout, expected in (
                ("success", 0.0, 2.0, 0),
                ("timeout", 5.0, 0.1, 124),
            ):
                with self.subTest(label=label):
                    marker = root / f"{label}.marker"
                    child = (
                        "import os,time,pathlib;os.environ.clear();os.setsid();"
                        "time.sleep(0.6);"
                        f"pathlib.Path({str(marker)!r}).write_text('escaped')"
                    )
                    launcher = (
                        "import subprocess,sys,time;"
                        "subprocess.Popen([sys.executable,'-c',sys.argv[1]],"
                        "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,close_fds=True);"
                        f"time.sleep({parent_sleep})"
                    )
                    evidence = self._run(
                        [sys.executable, "-c", launcher, child], root, timeout=timeout,
                    )
                    self.assertEqual(expected, evidence.returncode)
                    time.sleep(0.8)
                    self.assertFalse(marker.exists())

    def test_controller_crash_kills_namespace_without_touching_unrelated_process(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ready = root / "ready"
            marker = root / "escaped"
            child = (
                "import os,time,pathlib;os.environ.clear();os.setsid();time.sleep(0.8);"
                f"pathlib.Path({str(marker)!r}).write_text('escaped')"
            )
            target = (
                "import pathlib,subprocess,sys,time;"
                "subprocess.Popen([sys.executable,'-c',sys.argv[1]],"
                "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,close_fds=True);"
                f"pathlib.Path({str(ready)!r}).write_text('ready');time.sleep(10)"
            )
            controller_code = (
                "import os,pathlib,sys;"
                f"sys.path.insert(0,{str(SCRIPTS)!r});"
                "from pipeline_v2.process_tree import run_process_tree;"
                "run_process_tree(sys.argv[1:],cwd=pathlib.Path.cwd(),"
                "env=dict(os.environ),timeout=20)"
            )
            unrelated = subprocess.Popen([
                sys.executable, "-c", "import time;time.sleep(10)",
            ])
            controller = subprocess.Popen(
                [sys.executable, "-c", controller_code, sys.executable, "-c", target, child],
                cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            try:
                deadline = time.monotonic() + 5.0
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(ready.exists(), "contained target did not launch")
                controller.kill()
                controller.wait(timeout=2.0)
                time.sleep(1.0)
                self.assertFalse(marker.exists())
                self.assertIsNone(unrelated.poll())
            finally:
                if controller.poll() is None:
                    controller.kill()
                    controller.wait(timeout=2.0)
                if unrelated.poll() is None:
                    unrelated.terminate()
                    unrelated.wait(timeout=2.0)


if __name__ == "__main__":
    unittest.main()
