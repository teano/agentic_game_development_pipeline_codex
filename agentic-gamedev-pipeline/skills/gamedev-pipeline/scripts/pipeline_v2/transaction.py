"""Atomic state-file transactions with CAS and command replay."""

from __future__ import annotations

import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .checkout import safe_path
from .model import (
    PIPELINE_STATE_FILENAME,
    PipelineError,
    canonical_command,
    feature_slug,
    validate_state,
    workflow_relative_path,
)
from .reducer import (
    _precondition_proof,
    _reduce_prechecked,
    reduce,
    replayed,
    transaction_precondition,
)


class _LockedPrecondition:
    """One-use proof that an exact snapshot was checked under this store's lock."""

    __slots__ = ("command", "lock_token", "proof", "state", "store", "used")

    def __init__(
        self, store: StateStore, lock_token: object, state: dict[str, Any],
        command: dict[str, Any], proof: object,
    ):
        self.store = store
        self.lock_token = lock_token
        self.state = state
        self.command = command
        self.proof = proof
        self.used = False


class StateStore:
    def __init__(self, path: Path):
        self.path = Path(os.path.abspath(path))
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self._lock_token: object | None = None

    def validate_project_location(self, project_root: Path, feature: str) -> None:
        """Require the exact state path owned by one selected feature."""
        root = safe_path(Path(project_root), None, "project root", strict=True)
        feature = feature_slug(feature)
        directory = safe_path(
            root, workflow_relative_path(feature), "feature workflow directory"
        )
        candidate = safe_path(root, self.path, "v2 state path")
        if candidate != directory / PIPELINE_STATE_FILENAME:
            raise PipelineError(
                "pipeline state path must equal "
                "<project-root>/.agentic-pipeline/Workflows/<feature>/pipeline-state.json"
            )

    def load(self, *, required: bool = True) -> dict[str, Any] | None:
        safe_path(self.path.parent, self.path.name, "state file")
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            if required:
                raise PipelineError(f"state file does not exist: {self.path}")
            return None
        except (OSError, json.JSONDecodeError) as exc:
            raise PipelineError(f"cannot read state: {exc}") from exc
        if not isinstance(value, dict):
            raise PipelineError("state file must contain an object")
        return value

    @contextmanager
    def _lock(self, timeout: float = 5.0) -> Iterator[None]:
        safe_path(self.path.parent, None, "state directory")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        safe_path(self.path.parent, self.lock_path.name, "state lock")
        deadline = time.monotonic() + timeout
        descriptor = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        locked = False
        while not locked:
            try:
                if os.name == "nt":
                    import msvcrt
                    if os.fstat(descriptor).st_size == 0:
                        os.write(descriptor, b"0")
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError:
                if time.monotonic() >= deadline:
                    os.close(descriptor)
                    raise ConflictError("state transaction lock is busy")
                time.sleep(0.02)
        try:
            lock_token = object()
            self._lock_token = lock_token
            yield
        finally:
            if self._lock_token is lock_token:
                self._lock_token = None
            try:
                if os.name == "nt":
                    import msvcrt
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Hold the crash-released native lock across controller side effects."""
        with self._lock():
            yield

    def _write(self, state: dict[str, Any]) -> None:
        safe_path(self.path.parent, self.path.name, "state file")
        descriptor, temporary = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(state, stream, ensure_ascii=False, sort_keys=True, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            try:
                Path(temporary).unlink()
            except FileNotFoundError:
                pass

    def dispatch(self, command: dict[str, Any]) -> dict[str, Any]:
        command = canonical_command(command)
        if command.get("name") in {"next", "complete", "ready"}:
            raise PipelineError(f"{command['name']} is controller-only")
        with self._lock():
            return self._dispatch_locked(command)

    def _dispatch_locked(self, command: dict[str, Any]) -> dict[str, Any]:
        current = self.load(required=False)
        next_state = reduce(current, command)
        if next_state != current:
            self._write(next_state)
        return next_state

    def _replay_locked(self, command: dict[str, Any]) -> dict[str, Any] | None:
        current = self.load(required=False)
        if current is not None:
            validate_state(current)
            if replayed(current, command):
                return current
        return None

    def _preflight_locked(
        self, state: dict[str, Any], command: dict[str, Any],
    ) -> dict[str, Any] | _LockedPrecondition:
        """Check one exact snapshot while the caller holds this store's lock."""
        if self._lock_token is None:
            raise PipelineError("transaction precondition requires the state lock")
        proof = _precondition_proof(state, command)
        if proof is None:
            return state
        return _LockedPrecondition(self, self._lock_token, state, command, proof)

    def _dispatch_prechecked_locked(
        self, checked: _LockedPrecondition, command: dict[str, Any],
    ) -> dict[str, Any]:
        """Commit from the checked snapshot, never from state bytes replaced mid-flight."""
        if (
            checked.used or checked.store is not self or checked.command is not command
            or self._lock_token is None or checked.lock_token is not self._lock_token
        ):
            raise PipelineError("checked state commit requires its active transaction lock")
        checked.used = True
        next_state = _reduce_prechecked(checked.state, command, checked.proof)
        if next_state != checked.state:
            self._write(next_state)
        return next_state


# Local alias keeps the module API small while avoiding a circular import above.
from .model import ConflictError  # noqa: E402
