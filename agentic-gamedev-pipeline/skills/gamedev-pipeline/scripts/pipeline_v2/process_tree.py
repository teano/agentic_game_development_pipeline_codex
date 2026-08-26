"""Bounded planned-command execution with controller-owned process trees."""

from __future__ import annotations

import ctypes
import hashlib
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO


_PIPE_JOIN_SECONDS = 2.0
_PROCESS_JOIN_SECONDS = 2.0
_TECHNICAL_LAUNCH_RETURN_CODE = 125
_LINUX_EXEC = (
    "import os,sys;"
    "ready_fd=int(sys.argv[1]);argv=sys.argv[2:];"
    "\ntry: os.write(ready_fd,b'R');os.close(ready_fd)"
    "\nexcept OSError as exc:"
    "\n sys.stderr.write(f'cannot signal Linux containment readiness: {exc}\\n');sys.exit(125)"
    "\ntry: os.execvpe(argv[0],argv,os.environ)"
    "\nexcept OSError as exc:"
    "\n sys.stderr.write(f'planned command launch failed: {exc}\\n');sys.exit(125)"
)
_LINUX_PDEATH_EXEC = (
    "import ctypes,os,signal,sys;"
    "expected_parent=int(sys.argv[1]);libc=ctypes.CDLL(None,use_errno=True);"
    "PR_SET_PDEATHSIG=1;"
    "\nif libc.prctl(PR_SET_PDEATHSIG,signal.SIGKILL,0,0,0) != 0:"
    "\n sys.stderr.write('cannot establish controller parent-death containment\\n');sys.exit(125)"
    "\nif os.getppid() != expected_parent: os.kill(os.getpid(),signal.SIGKILL)"
    "\ntry: os.execv(sys.argv[2],sys.argv[2:])"
    "\nexcept OSError as exc:"
    "\n sys.stderr.write(f'cannot launch Linux containment adapter: {exc}\\n');sys.exit(125)"
)


@dataclass(frozen=True)
class ProcessEvidence:
    returncode: int
    stdout_sha256: str
    stderr_sha256: str


class _DigestReader(threading.Thread):
    """Drain a pipe without retaining attacker-controlled output in memory."""

    def __init__(self, stream: BinaryIO):
        super().__init__(daemon=True)
        self.stream = stream
        self.hasher = hashlib.sha256()
        self.lock = threading.Lock()

    def run(self) -> None:
        try:
            while chunk := self.stream.read(64 * 1024):
                with self.lock:
                    self.hasher.update(chunk)
        except (OSError, ValueError):
            # Tree termination can close a pipe concurrently with the reader.
            pass
        finally:
            try:
                self.stream.close()
            except OSError:
                pass

    def hexdigest(self, suffix: bytes = b"") -> str:
        with self.lock:
            value = self.hasher.copy()
        value.update(suffix)
        return value.hexdigest()


class _ReadyReader(threading.Thread):
    """Read the one byte proving namespace setup reached the target boundary."""

    def __init__(self, fd: int):
        super().__init__(daemon=True)
        self.fd = fd
        self.marker = b""

    def run(self) -> None:
        try:
            self.marker = os.read(self.fd, 1)
        except OSError:
            self.marker = b""
        finally:
            try:
                os.close(self.fd)
            except OSError:
                pass


def _start_readers(process: subprocess.Popen[bytes]) -> tuple[_DigestReader, _DigestReader]:
    if process.stdout is None or process.stderr is None:  # pragma: no cover - internal invariant
        raise RuntimeError("planned command pipes were not created")
    readers = (_DigestReader(process.stdout), _DigestReader(process.stderr))
    for reader in readers:
        reader.start()
    return readers


def _finish_readers(
    readers: tuple[_DigestReader, _DigestReader], *, stderr_suffix: bytes = b"",
) -> tuple[str, str]:
    for reader in readers:
        reader.join(_PIPE_JOIN_SECONDS)
        if reader.is_alive():
            try:
                reader.stream.close()
            except OSError:
                pass
            reader.join(0.1)
    return readers[0].hexdigest(), readers[1].hexdigest(stderr_suffix)


def _timeout_message(timeout: float) -> bytes:
    return f"planned command timed out after {timeout:g} seconds".encode("utf-8")


def _technical_launch_failure(reason: str) -> ProcessEvidence:
    message = f"planned command was not launched: {reason}".encode("utf-8")
    return ProcessEvidence(
        _TECHNICAL_LAUNCH_RETURN_CODE,
        hashlib.sha256(b"").hexdigest(),
        hashlib.sha256(message).hexdigest(),
    )


def _linux_namespace_adapter(
    *, platform: str | None = None, which=None, probe=None,
) -> list[str] | None:
    """Prove one util-linux PID-namespace adapter before any target is launched."""
    platform = sys.platform if platform is None else platform
    which = shutil.which if which is None else which
    probe = subprocess.run if probe is None else probe
    if not platform.startswith("linux"):
        return None
    unshare = which("unshare")
    if not unshare:
        return None
    candidates = (
        [unshare, "--pid", "--fork", "--kill-child=KILL"],
        [
            unshare, "--user", "--map-root-user", "--pid", "--fork",
            "--kill-child=KILL",
        ],
    )
    for candidate in candidates:
        try:
            completed = probe(
                [*candidate, "--", sys.executable, "-c", "raise SystemExit(0)"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=_PROCESS_JOIN_SECONDS,
                check=False, close_fds=True,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if completed.returncode == 0:
            return candidate
    return None


def _run_posix(
    argv: list[str], *, cwd: Path, env: dict[str, str], timeout: float,
) -> ProcessEvidence:
    adapter = _linux_namespace_adapter()
    if adapter is None:
        return _technical_launch_failure(
            "Linux util-linux PID namespace with --kill-child is unavailable",
        )
    ready_read, ready_write = os.pipe()
    contained = [
        *adapter, "--", sys.executable, "-c", _LINUX_EXEC,
        str(ready_write), *argv,
    ]
    try:
        process = subprocess.Popen(
            [
                sys.executable, "-c", _LINUX_PDEATH_EXEC,
                str(os.getpid()), *contained,
            ],
            cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            close_fds=True, pass_fds=(ready_write,),
        )
    except OSError as exc:
        os.close(ready_read)
        os.close(ready_write)
        return _technical_launch_failure(str(exc))
    os.close(ready_write)
    readers = _start_readers(process)
    ready_reader = _ReadyReader(ready_read)
    ready_reader.start()
    ready_reader.join(_PROCESS_JOIN_SECONDS)
    setup_ready = not ready_reader.is_alive() and ready_reader.marker == b"R"
    timed_out = False
    try:
        if setup_ready:
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
    finally:
        # Killing only the adapter is sufficient: util-linux gives namespace PID 1
        # a parent-death SIGKILL, and the kernel then kills the whole PID namespace.
        if (timed_out or not setup_ready) and process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=_PROCESS_JOIN_SECONDS)
        except subprocess.TimeoutExpired:  # pragma: no cover - SIGKILL should be final
            process.kill()
            process.wait(timeout=_PROCESS_JOIN_SECONDS)
        ready_reader.join(_PROCESS_JOIN_SECONDS)
    stdout_digest, stderr_digest = _finish_readers(
        readers,
        stderr_suffix=(
            _timeout_message(timeout) if timed_out
            else b"planned command containment setup failed before target readiness"
            if not setup_ready else b""
        ),
    )
    return ProcessEvidence(
        125 if not setup_ready else 124 if timed_out else int(process.returncode),
        stdout_digest,
        stderr_digest,
    )


if os.name == "nt":
    from ctypes import wintypes

    class _JobBasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class _JobExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JobBasicLimitInformation),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    class _JobBasicAccountingInformation(ctypes.Structure):
        _fields_ = [
            ("TotalUserTime", ctypes.c_longlong),
            ("TotalKernelTime", ctypes.c_longlong),
            ("ThisPeriodTotalUserTime", ctypes.c_longlong),
            ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
            ("TotalPageFaultCount", wintypes.DWORD),
            ("TotalProcesses", wintypes.DWORD),
            ("ActiveProcesses", wintypes.DWORD),
            ("TotalTerminatedProcesses", wintypes.DWORD),
        ]

    class _ThreadEntry32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ThreadID", wintypes.DWORD),
            ("th32OwnerProcessID", wintypes.DWORD),
            ("tpBasePri", wintypes.LONG),
            ("tpDeltaPri", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
        ]

    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _KERNEL32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    _KERNEL32.CreateJobObjectW.restype = wintypes.HANDLE
    _KERNEL32.SetInformationJobObject.argtypes = (
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
    )
    _KERNEL32.SetInformationJobObject.restype = wintypes.BOOL
    _KERNEL32.QueryInformationJobObject.argtypes = (
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    )
    _KERNEL32.QueryInformationJobObject.restype = wintypes.BOOL
    _KERNEL32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    _KERNEL32.AssignProcessToJobObject.restype = wintypes.BOOL
    _KERNEL32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    _KERNEL32.TerminateJobObject.restype = wintypes.BOOL
    _KERNEL32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    _KERNEL32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    _KERNEL32.Thread32First.argtypes = (wintypes.HANDLE, ctypes.POINTER(_ThreadEntry32))
    _KERNEL32.Thread32First.restype = wintypes.BOOL
    _KERNEL32.Thread32Next.argtypes = (wintypes.HANDLE, ctypes.POINTER(_ThreadEntry32))
    _KERNEL32.Thread32Next.restype = wintypes.BOOL
    _KERNEL32.OpenThread.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _KERNEL32.OpenThread.restype = wintypes.HANDLE
    _KERNEL32.ResumeThread.argtypes = (wintypes.HANDLE,)
    _KERNEL32.ResumeThread.restype = wintypes.DWORD
    _KERNEL32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _KERNEL32.CloseHandle.restype = wintypes.BOOL

    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    _JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION = 1
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    _CREATE_SUSPENDED = 0x00000004
    _TH32CS_SNAPTHREAD = 0x00000004
    _THREAD_SUSPEND_RESUME = 0x0002
    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


    class _WindowsApi:
        """Small real-API boundary so assignment failure is safely testable."""

        def create_kill_job(self) -> int:
            job = _KERNEL32.CreateJobObjectW(None, None)
            if not job:
                raise ctypes.WinError(ctypes.get_last_error())
            information = _JobExtendedLimitInformation()
            information.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not _KERNEL32.SetInformationJobObject(
                job,
                _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                ctypes.byref(information),
                ctypes.sizeof(information),
            ):
                error = ctypes.get_last_error()
                _KERNEL32.CloseHandle(job)
                raise ctypes.WinError(error)
            return int(job)

        def assign_process(self, job: int, process: subprocess.Popen[bytes]) -> None:
            if not _KERNEL32.AssignProcessToJobObject(job, int(process._handle)):
                raise ctypes.WinError(ctypes.get_last_error())

        def resume_process(self, process: subprocess.Popen[bytes]) -> None:
            snapshot = _KERNEL32.CreateToolhelp32Snapshot(_TH32CS_SNAPTHREAD, 0)
            if int(snapshot) == _INVALID_HANDLE_VALUE:
                raise ctypes.WinError(ctypes.get_last_error())
            resumed = False
            try:
                entry = _ThreadEntry32()
                entry.dwSize = ctypes.sizeof(entry)
                available = bool(_KERNEL32.Thread32First(snapshot, ctypes.byref(entry)))
                while available:
                    if entry.th32OwnerProcessID == process.pid:
                        thread = _KERNEL32.OpenThread(
                            _THREAD_SUSPEND_RESUME, False, entry.th32ThreadID,
                        )
                        if thread:
                            try:
                                if _KERNEL32.ResumeThread(thread) != 0xFFFFFFFF:
                                    resumed = True
                            finally:
                                _KERNEL32.CloseHandle(thread)
                    available = bool(_KERNEL32.Thread32Next(snapshot, ctypes.byref(entry)))
            finally:
                _KERNEL32.CloseHandle(snapshot)
            if not resumed:
                raise OSError("cannot resume suspended planned command")

        def terminate_and_close_job(self, job: int) -> None:
            error: OSError | None = None
            try:
                if not _KERNEL32.TerminateJobObject(job, 1):
                    raise ctypes.WinError(ctypes.get_last_error())
                deadline = time.monotonic() + _PROCESS_JOIN_SECONDS
                while True:
                    information = _JobBasicAccountingInformation()
                    if not _KERNEL32.QueryInformationJobObject(
                        job,
                        _JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION,
                        ctypes.byref(information),
                        ctypes.sizeof(information),
                        None,
                    ):
                        raise ctypes.WinError(ctypes.get_last_error())
                    if information.ActiveProcesses == 0:
                        break
                    if time.monotonic() >= deadline:
                        raise OSError("planned command process tree did not terminate")
                    time.sleep(0.005)
            except OSError as exc:
                error = exc
            finally:
                _KERNEL32.CloseHandle(job)
            if error is not None:
                raise error


    _WINDOWS_API = _WindowsApi()


    def _run_windows(
        argv: list[str], *, cwd: Path, env: dict[str, str], timeout: float,
        _windows_api: _WindowsApi = _WINDOWS_API,
    ) -> ProcessEvidence:
        job = _windows_api.create_kill_job()
        process: subprocess.Popen[bytes] | None = None
        readers: tuple[_DigestReader, _DigestReader] | None = None
        assigned = False
        timed_out = False
        try:
            process = subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=_CREATE_SUSPENDED,
            )
            readers = _start_readers(process)
            _windows_api.assign_process(job, process)
            assigned = True
            _windows_api.resume_process(process)
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
        finally:
            # Terminate and drain the job before closing it so every descendant
            # has ended, including children left by a successful direct parent.
            operation_failed = sys.exc_info()[0] is not None
            cleanup_error: OSError | None = None
            try:
                _windows_api.terminate_and_close_job(job)
            except OSError as exc:
                cleanup_error = exc
            if process is not None:
                if not assigned and process.poll() is None:
                    # A failed assignment leaves the suspended direct process
                    # outside the Job; it still must never be allowed to run.
                    process.kill()
                try:
                    process.wait(timeout=_PROCESS_JOIN_SECONDS)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=_PROCESS_JOIN_SECONDS)
            if readers is not None and (operation_failed or cleanup_error is not None):
                # Assignment, resume, and wait errors still own live pipe-reader
                # threads. The closed job makes their pipes reach EOF before the
                # original technical error propagates.
                _finish_readers(readers)
            if cleanup_error is not None and not operation_failed:
                raise cleanup_error
        if process is None or readers is None:  # pragma: no cover - launch errors propagate
            raise RuntimeError("planned command did not start")
        stdout_digest, stderr_digest = _finish_readers(
            readers,
            stderr_suffix=_timeout_message(timeout) if timed_out else b"",
        )
        return ProcessEvidence(
            124 if timed_out else int(process.returncode), stdout_digest, stderr_digest,
        )


def run_process_tree(
    argv: list[str], *, cwd: Path, env: dict[str, str], timeout: float,
) -> ProcessEvidence:
    """Run one command and end its complete descendant lifetime before returning."""
    if os.name == "nt":
        return _run_windows(argv, cwd=cwd, env=env, timeout=timeout)
    return _run_posix(argv, cwd=cwd, env=env, timeout=timeout)
