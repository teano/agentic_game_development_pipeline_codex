from __future__ import annotations

import ctypes
import gc
import hashlib
import os
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pipeline_v2.process_tree as process_tree


if os.name == "nt":
    from ctypes import wintypes

    _TEST_KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _TEST_KERNEL32.GetCurrentProcess.argtypes = ()
    _TEST_KERNEL32.GetCurrentProcess.restype = wintypes.HANDLE
    _TEST_KERNEL32.GetProcessHandleCount.argtypes = (
        wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD),
    )
    _TEST_KERNEL32.GetProcessHandleCount.restype = wintypes.BOOL
    _TEST_KERNEL32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _TEST_KERNEL32.OpenProcess.restype = wintypes.HANDLE
    _TEST_KERNEL32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    _TEST_KERNEL32.WaitForSingleObject.restype = wintypes.DWORD
    _TEST_KERNEL32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _TEST_KERNEL32.CloseHandle.restype = wintypes.BOOL

    _SYNCHRONIZE = 0x00100000
    _WAIT_TIMEOUT = 0x00000102


def _handle_count() -> int:
    count = wintypes.DWORD()
    if not _TEST_KERNEL32.GetProcessHandleCount(
        _TEST_KERNEL32.GetCurrentProcess(), ctypes.byref(count),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(count.value)


def _pid_is_running(pid: int) -> bool:
    handle = _TEST_KERNEL32.OpenProcess(_SYNCHRONIZE, False, pid)
    if not handle:
        return False
    try:
        return _TEST_KERNEL32.WaitForSingleObject(handle, 0) == _WAIT_TIMEOUT
    finally:
        _TEST_KERNEL32.CloseHandle(handle)


@unittest.skipUnless(os.name == "nt", "requires real Windows Job Object behavior")
class WindowsProcessTreeTests(unittest.TestCase):
    def test_posix_implementation_uses_kernel_namespace_containment_only(self) -> None:
        source = Path(process_tree.__file__).read_text(encoding="utf-8")
        self.assertNotIn("_TREE_TOKEN_ENV", source)
        self.assertNotIn('Path("/proc")', source)
        self.assertNotIn("os.killpg(", source)
        self.assertIn("--kill-child=KILL", source)
        self.assertIn("PR_SET_PDEATHSIG", source)

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.environment = os.environ.copy()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_tree(self, code: str, *, timeout: float = 15.0) -> process_tree.ProcessEvidence:
        return process_tree.run_process_tree(
            [sys.executable, "-c", code],
            cwd=self.root,
            env=self.environment,
            timeout=timeout,
        )

    def test_drains_32_mib_from_each_pipe_without_deadlock_and_hashes_exactly(self) -> None:
        chunk_size = 64 * 1024
        repeats = 512
        code = (
            "import os; "
            f"out=b'O'*{chunk_size}; err=b'E'*{chunk_size}; "
            f"exec(\"for _ in range({repeats}):\\n os.write(1, out)\\n os.write(2, err)\")"
        )

        result = self.run_tree(code, timeout=20.0)

        expected_stdout = hashlib.sha256()
        expected_stderr = hashlib.sha256()
        for _ in range(repeats):
            expected_stdout.update(b"O" * chunk_size)
            expected_stderr.update(b"E" * chunk_size)
        self.assertEqual(0, result.returncode)
        self.assertEqual(expected_stdout.hexdigest(), result.stdout_sha256)
        self.assertEqual(expected_stderr.hexdigest(), result.stderr_sha256)
        self.assertEqual(process_tree._STDERR_TAIL_BYTES, len(result.stderr_tail))
        self.assertEqual(b"E" * process_tree._STDERR_TAIL_BYTES, result.stderr_tail)
        self.assertTrue(result.stderr_tail_truncated)

    def test_successful_parent_cannot_escape_twenty_five_ready_children(self) -> None:
        child_count = 25
        child_code = (
            "import os, sys, time; from pathlib import Path; "
            "index=sys.argv[1]; root=Path(sys.argv[2]); "
            "(root / ('ready-' + index)).write_text(str(os.getpid()), encoding='ascii'); "
            "release=root / 'release-children'; "
            "exec(\"while not release.exists():\\n time.sleep(0.005)\"); "
            "time.sleep(0.6); "
            "(root / ('escaped-' + index)).write_text('escaped', encoding='ascii')"
        )
        parent_code = textwrap.dedent(
            f"""
            import subprocess
            import sys
            import time
            from pathlib import Path

            root = Path({str(self.root)!r})
            child_code = {child_code!r}
            for index in range({child_count}):
                subprocess.Popen([sys.executable, "-c", child_code, str(index), str(root)])
            deadline = time.monotonic() + 10
            while len(list(root.glob("ready-*"))) != {child_count} and time.monotonic() < deadline:
                time.sleep(0.01)
            if len(list(root.glob("ready-*"))) != {child_count}:
                raise SystemExit(81)
            (root / "release-children").write_text("release", encoding="ascii")
            """
        )

        result = self.run_tree(parent_code, timeout=15.0)

        self.assertEqual(0, result.returncode)
        ready = sorted(self.root.glob("ready-*"))
        self.assertEqual(child_count, len(ready))
        pids = [int(path.read_text(encoding="ascii")) for path in ready]
        self.assertEqual([], [pid for pid in pids if _pid_is_running(pid)])
        time.sleep(0.8)
        self.assertEqual([], list(self.root.glob("escaped-*")))

    def test_assignment_failure_never_resumes_the_real_suspended_process(self) -> None:
        marker = self.root / "must-not-run.txt"
        real_api = process_tree._WINDOWS_API

        class AssignmentFailureApi:
            def __init__(self) -> None:
                self.resume_called = False

            def create_kill_job(self) -> int:
                return real_api.create_kill_job()

            def assign_process(self, job: int, process: object) -> None:
                raise OSError("injected AssignProcessToJobObject failure")

            def resume_process(self, process: object) -> None:
                self.resume_called = True
                raise AssertionError("an unassigned planned command was resumed")

            def terminate_and_close_job(self, job: int) -> None:
                real_api.terminate_and_close_job(job)

        failing_api = AssignmentFailureApi()
        code = f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')"

        with self.assertRaisesRegex(OSError, "injected AssignProcessToJobObject failure"):
            process_tree._run_windows(
                [sys.executable, "-c", code],
                cwd=self.root,
                env=self.environment,
                timeout=5.0,
                _windows_api=failing_api,
            )

        self.assertFalse(failing_api.resume_called)
        time.sleep(0.2)
        self.assertFalse(marker.exists())

    def test_real_nested_job_can_run_a_planned_command(self) -> None:
        environment = self.environment.copy()
        environment["PYTHONPATH"] = str(SCRIPTS) + os.pathsep + environment.get("PYTHONPATH", "")
        inner_code = textwrap.dedent(
            """
            import ctypes
            import os
            import sys
            import traceback
            from ctypes import wintypes
            from pathlib import Path
            from pipeline_v2.process_tree import run_process_tree

            try:
                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel32.GetCurrentProcess.restype = wintypes.HANDLE
                kernel32.IsProcessInJob.argtypes = (
                    wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL),
                )
                kernel32.IsProcessInJob.restype = wintypes.BOOL
                inside_job = wintypes.BOOL()
                if not kernel32.IsProcessInJob(
                    kernel32.GetCurrentProcess(), None, ctypes.byref(inside_job),
                ):
                    raise ctypes.WinError(ctypes.get_last_error())
                if not inside_job.value:
                    raise RuntimeError("nested helper is not inside its outer job")
                result = run_process_tree(
                    [sys.executable, "-c", "raise SystemExit(23)"],
                    cwd=Path.cwd(), env=os.environ.copy(), timeout=5.0,
                )
                if result.returncode != 23:
                    raise RuntimeError(f"nested planned command returned {result.returncode}")
            except BaseException:
                Path("nested-job-error.txt").write_text(traceback.format_exc(), encoding="utf-8")
                raise
            """
        )

        result = process_tree.run_process_tree(
            [sys.executable, "-c", inner_code],
            cwd=self.root,
            env=environment,
            timeout=10.0,
        )

        error = self.root / "nested-job-error.txt"
        self.assertEqual(0, result.returncode, error.read_text(encoding="utf-8") if error.exists() else "")

    def test_direct_exit_code_and_handles_are_stable_across_repetition(self) -> None:
        def exit_23() -> process_tree.ProcessEvidence:
            return self.run_tree("raise SystemExit(23)", timeout=5.0)

        self.assertEqual(23, exit_23().returncode)
        gc.collect()
        before = _handle_count()
        for _ in range(20):
            self.assertEqual(23, exit_23().returncode)
        gc.collect()
        self.assertEqual(before, _handle_count())

if __name__ == "__main__":
    unittest.main()
