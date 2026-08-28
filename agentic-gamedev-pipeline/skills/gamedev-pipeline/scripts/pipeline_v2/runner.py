"""Imperative controller shell around the pure reducer."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import tempfile
import time
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .checkout import authority_items, authority_items_equal, canonical_project_root, diff, inventory, inventory_digest, path_identity, safe_path, verify_authority, violations
from .model import (
    PHASES,
    PipelineError,
    assignment_identity,
    assignment_output_path,
    candidate_record_valid,
    canonical_command,
    current_candidate,
    default_assignment,
    digest,
    is_digest,
    is_generation,
    is_strict_integer,
    reconfiguration_action,
    safe_identifier,
    slice_records,
    slices_are_read_sealed,
    status_view,
    validate_state,
)
from .process_tree import run_process_tree
from .reducer import _newer_nonpassing_engineering_inventory
from .transaction import StateStore


TECHNICAL_FAILURE_RETURN_CODE = 125
STDERR_EXCERPT_BYTES = 4096

_SENSITIVE_ENV_NAME = re.compile(
    r"(?:api_?key|apikey|token|secret|password|passwd|credential|authorization|bearer|private_?key|access_?key|(?:^|_)pat(?:_|$)|database_?url|dsn)",
    re.IGNORECASE,
)
_SECRET_PATTERNS = (
    re.compile(r"\b([a-z][a-z0-9+.-]*://)([^/\s@]+)@", re.IGNORECASE),
    re.compile(r"\b(bearer)(\s+)([^\s,;]+)", re.IGNORECASE),
    re.compile(
        r"\b(api[-_ ]?key|password|passwd|access[-_ ]?token|refresh[-_ ]?token|token|secret)"
        r"(\s*[:=]\s*)([^\s,;]+)",
        re.IGNORECASE,
    ),
)

_PLAN_CONTRACT_PATH = Path(__file__).resolve().parents[4] / "scripts" / "development_plan_contract.py"
_PLAN_CONTRACT_SPEC = importlib.util.spec_from_file_location(
    "gamedev_pipeline_development_plan_contract", _PLAN_CONTRACT_PATH,
)
if _PLAN_CONTRACT_SPEC is None or _PLAN_CONTRACT_SPEC.loader is None:
    raise RuntimeError("Cannot load the shared development-plan contract")
_PLAN_CONTRACT = importlib.util.module_from_spec(_PLAN_CONTRACT_SPEC)
_PLAN_CONTRACT_SPEC.loader.exec_module(_PLAN_CONTRACT)


def _require_expected_generation(value: Any) -> None:
    if value is not None and not is_strict_integer(value):
        raise PipelineError("expected generation must be an integer")


def _caller_slices(value: Any) -> list[dict[str, Any]]:
    return slice_records(value, sealed=False)


def _unsealed_projection(value: Any) -> list[dict[str, Any]]:
    records = slice_records(value)
    return [
        {key: deepcopy(item[key]) for key in ("id", "allowed_paths", "planned_commands")}
        for item in records
    ]


def seal_slices_from_approved_plan(
    root: Path, plan_path: str, slices: Any,
) -> list[dict[str, Any]]:
    """Bind caller-authored write slices to controller-parsed approved read scopes."""
    caller = _caller_slices(slices)
    plan = safe_path(root, plan_path, "approved development plan", strict=True)
    try:
        read_by_id = _PLAN_CONTRACT.parse_slice_read_paths(
            plan.read_text(encoding="utf-8"), label=str(plan_path),
        )
    except (OSError, UnicodeError, _PLAN_CONTRACT.PlanContractError) as exc:
        raise PipelineError(f"cannot seal approved plan read scopes: {exc}") from exc
    caller_ids = [item["id"] for item in caller]
    plan_ids = list(read_by_id)
    missing = [slice_id for slice_id in caller_ids if slice_id not in read_by_id]
    unknown = [slice_id for slice_id in plan_ids if slice_id not in caller_ids]
    if missing or unknown or plan_ids != caller_ids:
        raise PipelineError(
            "approved plan slice IDs must exactly match caller slices in order: "
            f"missing={missing} unknown={unknown}"
        )
    return [
        {**item, "read_paths": deepcopy(read_by_id[item["id"]])}
        for item in caller
    ]


def _stream_digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _process_environment() -> dict[str, str]:
    """Keep Node/npm's optional compile cache out of the candidate checkout."""
    environment = os.environ.copy()
    environment["NODE_DISABLE_COMPILE_CACHE"] = "1"
    environment.pop("NODE_COMPILE_CACHE", None)
    return environment


def _lexically_contained(root: Path, candidate: str | Path) -> bool:
    root_value = os.path.normcase(os.path.abspath(root))
    candidate_value = os.path.normcase(os.path.abspath(candidate))
    try:
        return os.path.commonpath((root_value, candidate_value)) == root_value
    except (OSError, ValueError):
        return False


def _remove_read_only_temp(path: Path, label: str) -> None:
    verified_scratch = Path(os.path.abspath(path))

    def retry_read_only(function, failed_path, exc_info) -> None:
        failed = Path(os.path.abspath(failed_path))
        if not _lexically_contained(verified_scratch, failed):
            raise exc_info[1]
        try:
            failed_stat = failed.lstat()
        except OSError:
            raise exc_info[1]
        if failed.is_symlink() or bool(
            getattr(failed_stat, "st_file_attributes", 0) & 0x400
        ):
            raise exc_info[1]
        os.chmod(failed, stat.S_IREAD | stat.S_IWRITE)
        function(failed_path)

    for attempt in range(6):
        try:
            shutil.rmtree(path, onerror=retry_read_only if os.name == "nt" else None)
            return
        except FileNotFoundError:
            return
        except OSError as exc:
            if attempt == 5:
                raise PipelineError(f"cannot clean {label}: {exc}") from exc
            time.sleep(0.05 * (attempt + 1))


def _replace_literal(value: str, literal: str, replacement: str) -> tuple[str, bool]:
    if not literal:
        return value, False
    updated, count = re.subn(
        re.escape(literal), lambda _match: replacement, value, flags=re.IGNORECASE,
    )
    return updated, count > 0


def _stderr_excerpt(
    raw: bytes, *, raw_truncated: bool, environment: dict[str, str],
    project_root: Path, scratch_root: Path | None,
) -> dict[str, Any]:
    """Return one redacted, path-normalized, byte-bounded failure tail."""
    text = raw.decode("utf-8", errors="replace")
    redacted = False
    sensitive_values = sorted(
        {
            value for name, value in environment.items()
            if value and _SENSITIVE_ENV_NAME.search(name)
        },
        key=len,
        reverse=True,
    )
    for secret in sensitive_values:
        text, replaced = _replace_literal(text, secret, "[REDACTED]")
        redacted = redacted or replaced
    for pattern in _SECRET_PATTERNS:
        text, count = pattern.subn(
            lambda match: (
                f"{match.group(1)}[REDACTED]@"
                if "://" in match.group(1)
                else f"{match.group(1)}{match.group(2)}[REDACTED]"
            ),
            text,
        )
        redacted = redacted or count > 0
    roots = []
    if scratch_root is not None:
        roots.append((str(Path(os.path.abspath(scratch_root))), "[SCRATCH_ROOT]"))
    roots.append((str(Path(os.path.abspath(project_root))), "[PROJECT_ROOT]"))
    for root_value, replacement in roots:
        for spelling in dict.fromkeys((root_value, root_value.replace("\\", "/"))):
            text, _ = _replace_literal(text, spelling, replacement)
    encoded = text.encode("utf-8")
    truncated = raw_truncated or len(encoded) > STDERR_EXCERPT_BYTES
    if len(encoded) > STDERR_EXCERPT_BYTES:
        encoded = encoded[-STDERR_EXCERPT_BYTES:]
        text = encoded.decode("utf-8", errors="ignore")
    return {
        "stderr_excerpt": text,
        "stderr_excerpt_truncated": truncated,
        "stderr_excerpt_redacted": redacted,
    }


@contextmanager
def _read_only_process_environment(root: Path):
    """Confine read-only command temp/cache data without copying candidate bytes."""
    scratch_root = safe_path(root, ".agentic-pipeline-v2/read-only-temp", "read-only temp root")
    if scratch_root.exists():
        _remove_read_only_temp(scratch_root, "stale read-only command temp")
    try:
        scratch_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PipelineError(f"cannot create read-only temp root: {exc}") from exc
    scratch_root = safe_path(root, scratch_root, "read-only temp root", strict=True)
    if not scratch_root.is_dir():
        raise PipelineError("read-only temp root is not a directory")
    try:
        temporary = Path(tempfile.mkdtemp(prefix="command-", dir=scratch_root))
    except OSError as exc:
        raise PipelineError(f"cannot create read-only command temp: {exc}") from exc
    try:
        scratch = safe_path(root, temporary, "read-only command temp", strict=True)
        environment = _process_environment()
        value = str(scratch)
        for name in (
            "TEMP", "TMP", "TMPDIR", "XDG_CACHE_HOME", "NPM_CONFIG_CACHE",
            "npm_config_cache", "YARN_CACHE_FOLDER", "PIP_CACHE_DIR",
        ):
            environment[name] = value
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        yield environment
    finally:
        _remove_read_only_temp(scratch_root, "read-only temp root")


class Controller:
    def __init__(self, store: StateStore, *, timeout: float = 600.0):
        self.store = store
        self.timeout = timeout

    def _loaded(self, state: dict[str, Any] | None = None) -> tuple[dict[str, Any], Path]:
        state = self.store.load() if state is None else state
        validate_state(state)
        root = canonical_project_root(state["project_root"])
        self.store.validate_project_location(root)
        verify_authority(root, state["authority"])
        if not slices_are_read_sealed(state):
            raise PipelineError(
                "controller read scope is not sealed; run status and execute its init reconfiguration"
            )
        return state, root

    def _preflight_existing_store_location(self) -> None:
        """Reject split-brain state paths before creating a transaction lock."""
        state = self.store.load()
        validate_state(state)
        root = canonical_project_root(state["project_root"])
        self.store.validate_project_location(root)

    @staticmethod
    def _candidate_inventory(state: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any] | None:
        for record in state["artifacts"].values():
            if not isinstance(record, dict):
                continue
            if record.get("candidate") != candidate and record.get("candidate_binding") != candidate:
                continue
            controller = record.get("controller")
            observed = controller.get("inventory") if isinstance(controller, dict) else None
            if isinstance(observed, dict) and inventory_digest(observed) == candidate["checkout_sha256"]:
                return observed
        return None

    @staticmethod
    def _remediation_candidate(state: dict[str, Any]) -> dict[str, Any] | None:
        if state.get("phase") != "engineering" or state.get("active_assignment") is not None:
            return None
        retained = current_candidate(state)
        retained_generation = (
            retained.get("generation", -1) if isinstance(retained, dict) else -1
        )
        last_completed_slice_generation = max(
            (
                item["generation"] for item in state["history"]
                if isinstance(item.get("completed_slice_id"), str)
                and is_generation(item.get("generation"))
            ),
            default=-1,
        )
        candidates = [
            (item["candidate_base"]["generation"], key, item["candidate_base"])
            for key, item in state["gates"].items()
            if isinstance(item, dict) and item.get("status") == "closed"
            and item.get("kind") in {"worker_result", "controller_result"}
            and item.get("reason") == "fail"
            and item.get("phase") in {"review", "qa"}
            and candidate_record_valid(
                item.get("candidate_base"), state["authority"]["digest"],
            )
            and item["candidate_base"]["generation"]
            > max(last_completed_slice_generation, retained_generation)
        ]
        return max(candidates, default=(0, "", None))[-1]

    @staticmethod
    def _latest_controller_inventory(
        state: dict[str, Any],
    ) -> tuple[int, dict[str, Any] | None, str | None]:
        completed_generation = {
            item["assignment_id"]: item["generation"]
            for item in state["history"]
            if isinstance(item.get("assignment_id"), str)
            and is_generation(item.get("generation"))
        }
        observed = []
        for phase in ("plan", "slice", "engineering", "review", "qa", "docs", "ready"):
            record = state["artifacts"].get(phase)
            controller = record.get("controller") if isinstance(record, dict) else None
            checkout = controller.get("inventory") if isinstance(controller, dict) else None
            if isinstance(checkout, dict):
                generation = completed_generation.get(record.get("assignment_id"), -1)
                observed.append((generation, phase, checkout, controller.get("authority_digest")))
        latest = max(observed, default=(-1, "", None, None))
        return latest[0], latest[-2], latest[-1]

    def _checkout_drift(
        self, state: dict[str, Any], current: dict[str, Any], *, ignore_authority: bool = False,
    ) -> list[str]:
        authority_paths = {
            path_identity(item["path"]) for item in state["authority"]["items"].values()
        }
        active = state["active_assignment"]
        if active is not None:
            changes = diff(active["base"]["inventory"], current)
            if ignore_authority:
                changes = [
                    item for item in changes
                    if path_identity(item["path"]) not in authority_paths
                ]
            return violations(changes, active["access"]["write"])

        remediation_candidate = self._remediation_candidate(state)
        candidate = remediation_candidate or current_candidate(state)
        expected = self._candidate_inventory(state, candidate) if candidate is not None else None
        expected_authority = candidate.get("authority_digest") if candidate is not None else None
        newer_engineering = (
            _newer_nonpassing_engineering_inventory(state, remediation_candidate)
            if remediation_candidate is not None else None
        )
        if newer_engineering is not None:
            expected = newer_engineering
            expected_authority = state["authority"]["digest"]
        elif expected is None and remediation_candidate is None:
            latest_generation, latest_inventory, latest_authority = (
                self._latest_controller_inventory(state)
            )
            candidate_generation = (
                candidate["generation"]
                if candidate_record_valid(candidate, state["authority"]["digest"])
                else -1
            )
            if candidate is None or latest_generation > candidate_generation:
                expected = latest_inventory
                expected_authority = latest_authority
        if expected is not None:
            changes = diff(expected, current)
            if ignore_authority or expected_authority != state["authority"]["digest"]:
                changes = [
                    item for item in changes
                    if path_identity(item["path"]) not in authority_paths
                ]
            return [item["path"] for item in changes]
        if (
            candidate is not None and not ignore_authority
            and candidate.get("checkout_sha256") != inventory_digest(current)
        ):
            return ["<checkout>"]
        return []

    def _verify_live_checkout(
        self, state: dict[str, Any], root: Path,
    ) -> dict[str, dict[str, Any]]:
        current = inventory(root)
        drift = self._checkout_drift(state, current)
        if drift:
            if state["active_assignment"] is not None:
                raise PipelineError(f"candidate changed forbidden paths: {drift}")
            raise PipelineError(f"live checkout drifted from controller evidence: {drift}")
        return current

    def status(self) -> dict[str, Any]:
        """Return an executable action or a terminal recovery fact from one lock-bound observation."""
        self._preflight_existing_store_location()
        with self.store.transaction():
            state = self.store.load()
            validate_state(state)
            root = canonical_project_root(state["project_root"])
            self.store.validate_project_location(root)
            paths = {
                name: item["path"] for name, item in state["authority"]["items"].items()
            }
            observed = authority_items(root, paths)
            authority_changed = not authority_items_equal(
                observed, state["authority"]["items"],
            )
            scope_changed = not slices_are_read_sealed(state)
            proposed_slices = None
            if authority_changed or scope_changed:
                proposed_slices = seal_slices_from_approved_plan(
                    root, observed["plan"]["path"],
                    _unsealed_projection(state["slices"]),
                )
                scope_changed = proposed_slices != state["slices"]
            current = inventory(root)
            drift = self._checkout_drift(
                state, current, ignore_authority=authority_changed,
            )
            view = status_view(state)
            if drift:
                view["next_action"] = {
                    "kind": "terminal", "result": "checkout_recovery_required",
                    "reason": f"restore or reconcile checkout drift before mutation: {drift}",
                }
            elif authority_changed or scope_changed:
                view["next_action"] = reconfiguration_action(
                    state, observed, proposed_slices,
                    checkout_sha256=inventory_digest(current),
                )
            return view

    def next(self, *, command_id: str, assignment: dict[str, Any] | None = None, expected_generation: int | None = None) -> dict[str, Any]:
        _require_expected_generation(expected_generation)
        self._preflight_existing_store_location()
        with self.store.transaction():
            state, root = self._loaded()
            snapshot = self._verify_live_checkout(state, root)
            supplied = {} if assignment is None else canonical_command(assignment)
            prior = next(
                (item for item in state["history"] if item.get("id") == command_id),
                None,
            )
            if prior is not None:
                if prior.get("command") != "next":
                    # Preserve the common command-ID conflict path.
                    self.store._replay_locked({
                        "name": "next", "id": command_id, "assignment": {},
                    })
                issuance_generation = prior["generation"] - 1
                phase = next((
                    candidate for candidate in PHASES[:-1]
                    if command_id == (
                        f"next-{candidate}-g{issuance_generation}-"
                        f"{digest([state['run_id'], issuance_generation, candidate, 'next'])[:10]}"
                    )
                ), None)
                if phase is None:
                    raise PipelineError("recorded next command identity is malformed")
                historical = assignment_identity(
                    state["run_id"], issuance_generation, phase,
                )
                for field in ("id", "worker_id", "task"):
                    if field in supplied and supplied[field] != historical[field]:
                        raise PipelineError(
                            f"assignment {field} is controller-derived and must match the recorded next command"
                        )
                historical_spec = deepcopy(historical)
                if "context" in supplied and phase != "review":
                    historical_spec["context"] = supplied["context"]
                replay = self.store._replay_locked({
                    "name": "next", "id": command_id,
                    "assignment": historical_spec,
                })
                if replay is not None:
                    return replay
            current_action = status_view(state)["next_action"]
            if (
                current_action.get("command") != "next"
                or command_id != current_action.get("command_id")
            ):
                raise PipelineError(
                    "command ID is controller-derived and must match status.next_action"
                )
            canonical = default_assignment(state)
            for field in ("id", "worker_id", "task"):
                if field in supplied and supplied[field] != canonical[field]:
                    raise PipelineError(
                        f"assignment {field} is controller-derived and must match status.next_action"
                    )
            canonical_spec = {
                field: canonical[field] for field in ("id", "worker_id", "task")
            }
            if (
                state["phase"] == "review" and "context" in supplied
                and supplied["context"] != canonical["context"]
            ):
                raise PipelineError(
                    "review target is controller-derived and must match status.next_action"
                )
            if "context" in supplied and state["phase"] != "review":
                canonical_spec["context"] = supplied["context"]
            intent = {"name": "next", "id": command_id, "assignment": canonical_spec}
            command = {
                **intent,
                "expected_generation": state["generation"] if expected_generation is None else expected_generation,
                "controller_base": {"inventory": snapshot, "checkout_sha256": inventory_digest(snapshot)},
            }
            return self.store._dispatch_locked(command)

    def reconfigure(self, command: dict[str, Any]) -> dict[str, Any]:
        """Apply init to an existing run, deriving any active-work interruption proof."""
        _require_expected_generation(command.get("expected_generation"))
        safe_identifier(command.get("run_id"))
        proposed_root = canonical_project_root(command["project_root"])
        self.store.validate_project_location(proposed_root)
        with self.store.transaction():
            state = self.store.load(required=False)
            value = deepcopy(command)
            supplied_paths = value.pop("authority_paths", None)
            root = canonical_project_root(value["project_root"])
            value["project_root"] = str(root)
            if supplied_paths is not None:
                value["authority"] = {"items": authority_items(root, supplied_paths)}
            proposed_items = value.get("authority", {}).get("items", {})
            if not isinstance(proposed_items, dict) or "plan" not in proposed_items:
                raise PipelineError("init requires controller-resolved authority paths")
            if state is None:
                value["slices"] = seal_slices_from_approved_plan(
                    root, proposed_items["plan"]["path"], value.get("slices"),
                )
            else:
                base_slices = _unsealed_projection(state["slices"])
                proposed_slices = seal_slices_from_approved_plan(
                    root, proposed_items["plan"]["path"], base_slices,
                )
                supplied_slices = value.get("slices")
                if supplied_slices not in (base_slices, proposed_slices):
                    raise PipelineError(
                        "init slices must match the controller-projected status action"
                    )
                value["slices"] = proposed_slices
            current = inventory(root)
            if state is not None:
                validate_state(state)
                authority_changed = not authority_items_equal(
                    value.get("authority", {}).get("items", {}),
                    state["authority"]["items"],
                )
                drift = self._checkout_drift(
                    state, current, ignore_authority=authority_changed,
                )
                if drift:
                    if state.get("active_assignment") is not None:
                        raise PipelineError(f"candidate changed forbidden paths: {drift}")
                    raise PipelineError(f"live checkout drifted from controller evidence: {drift}")
                scope_changed = value["slices"] != state["slices"]
                if authority_changed or scope_changed:
                    expected = reconfiguration_action(
                        state, value["authority"]["items"], value.get("slices"),
                        checkout_sha256=inventory_digest(current),
                    )
                    if value.get("id") != expected["command_id"]:
                        raise PipelineError(
                            "stale approved authority or scope reconfiguration action; run status again"
                        )
            value["controller_base"] = {
                "inventory": current, "checkout_sha256": inventory_digest(current),
            }
            if state is not None and state.get("active_assignment") is not None:
                active = state["active_assignment"]
                authority_paths = {
                    path_identity(item["path"])
                    for item in state["authority"]["items"].values()
                }
                changes = [
                    item for item in diff(active["base"]["inventory"], current)
                    if path_identity(item["path"]) not in authority_paths
                ]
                value["controller_interrupt"] = {
                    "inventory": current,
                    "checkout_sha256": inventory_digest(current),
                    "diff": changes,
                    "violations": violations(changes, active["access"]["write"]),
                }
            return self.store._dispatch_locked(value)

    def migrate(self, command: dict[str, Any]) -> dict[str, Any]:
        """Import or replay migration only against its lock-bound live checkout."""
        _require_expected_generation(command.get("expected_generation"))
        value = canonical_command(command)
        imported = value.get("imported")
        validate_state(imported)
        _caller_slices(imported["slices"])
        proposed_root = canonical_project_root(imported["project_root"])
        imported["project_root"] = str(proposed_root)
        validate_state(imported)
        existing = self.store.load(required=False)
        if existing is None:
            self.store.validate_project_location(proposed_root)
        else:
            self._preflight_existing_store_location()
        with self.store.transaction():
            state = self.store.load(required=False)
            if state is None:
                root = canonical_project_root(imported["project_root"])
                verify_authority(root, imported["authority"])
                imported["slices"] = seal_slices_from_approved_plan(
                    root, imported["authority"]["items"]["plan"]["path"],
                    imported["slices"],
                )
                value["imported"] = imported
                current = inventory(root)
            else:
                state, root = self._loaded(state)
                current = self._verify_live_checkout(state, root)
                imported["slices"] = seal_slices_from_approved_plan(
                    proposed_root, imported["authority"]["items"]["plan"]["path"],
                    imported["slices"],
                )
                value["imported"] = imported
                replay = self.store._replay_locked(value)
                if replay is not None:
                    return replay
            value["controller_base"] = {
                "inventory": current, "checkout_sha256": inventory_digest(current),
            }
            return self.store._dispatch_locked(value)

    def transition(self, command: dict[str, Any]) -> dict[str, Any]:
        """Run a non-I/O transition only while its bound authority is still exact."""
        _require_expected_generation(command.get("expected_generation"))
        command = canonical_command(command)
        self._preflight_existing_store_location()
        with self.store.transaction():
            state, root = self._loaded()
            self._verify_live_checkout(state, root)
            replay = self.store._replay_locked(command)
            if replay is not None:
                return replay
            return self.store._dispatch_locked(deepcopy(command))

    def complete(self, *, command_id: str, artifact_path: Path | None = None, expected_generation: int | None = None) -> dict[str, Any]:
        _require_expected_generation(expected_generation)
        self._preflight_existing_store_location()
        with self.store.transaction():
            state, root = self._loaded()
            self._verify_live_checkout(state, root)
            active = state["active_assignment"]
            if active is None:
                prior = next((item for item in state["history"] if item.get("id") == command_id and item.get("command") == "complete"), None)
                if prior is None:
                    raise PipelineError("there is no active assignment")
                assignment_id = prior.get("assignment_id")
                assignment_phase = prior.get("phase")
            else:
                assignment_id = active["id"]
                assignment_phase = active["phase"]
            assigned_relative = assignment_output_path(assignment_id)
            assigned = safe_path(root, assigned_relative, "assigned artifact", strict=True)
            supplied = assigned if artifact_path is None else safe_path(root, artifact_path, "artifact path", strict=True)
            if supplied != assigned:
                raise PipelineError(f"complete accepts only the assigned artifact path {assigned_relative!r}")
            try:
                artifact = json.loads(assigned.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise PipelineError(f"cannot read assigned JSON artifact: {exc}") from exc
            if not isinstance(artifact, dict):
                raise PipelineError("assigned JSON artifact must be an object")
            if assignment_phase == "slice" and "slices" in artifact:
                artifact = deepcopy(artifact)
                artifact["slices"] = seal_slices_from_approved_plan(
                    root, state["authority"]["items"]["plan"]["path"],
                    artifact["slices"],
                )
            intent = {"name": "complete", "id": command_id, "artifact": artifact}
            command = {
                **intent,
                "expected_generation": state["generation"] if expected_generation is None else expected_generation,
            }
            checked = self.store._preflight_locked(state, command)
            if isinstance(checked, dict):
                return checked
            if active is None:  # pragma: no cover - conflicting replay is reported above
                raise PipelineError("there is no active assignment")
            results = []

            def run_checks(
                checkout: Path, environment: dict[str, str],
            ) -> None:
                for argv in active["commands"]:
                    try:
                        executable = shutil.which(argv[0]) if os.name == "nt" else None
                        execution_argv = [executable, *argv[1:]] if executable else argv
                        result = run_process_tree(
                            execution_argv, cwd=checkout, env=environment,
                            timeout=self.timeout,
                        )
                        command_result = {
                            "argv": argv, "returncode": result.returncode,
                            "stdout_sha256": result.stdout_sha256,
                            "stderr_sha256": result.stderr_sha256,
                        }
                        if result.returncode != 0:
                            command_result.update(_stderr_excerpt(
                                result.stderr_tail,
                                raw_truncated=result.stderr_tail_truncated,
                                environment=environment,
                                project_root=root,
                                scratch_root=Path(environment["TEMP"]),
                            ))
                    except OSError as exc:
                        raw_error = str(exc).encode("utf-8", errors="replace")
                        command_result = {
                            "argv": argv, "returncode": TECHNICAL_FAILURE_RETURN_CODE,
                            "stdout_sha256": _stream_digest(b""),
                            "stderr_sha256": _stream_digest(raw_error),
                        }
                        command_result.update(_stderr_excerpt(
                            raw_error,
                            raw_truncated=False,
                            environment=environment,
                            project_root=root,
                            scratch_root=Path(environment["TEMP"]),
                        ))
                    results.append(command_result)
                    command_inventory = inventory(checkout)
                    command_changes = diff(active["base"]["inventory"], command_inventory)
                    forbidden = violations(command_changes, active["access"]["write"])
                    if forbidden:
                        raise PipelineError(f"candidate changed forbidden paths: {forbidden}")
                    if command_result["returncode"] != 0:
                        break

            if active["commands"]:
                with _read_only_process_environment(root) as environment:
                    run_checks(
                        root, environment,
                    )
            else:
                run_checks(root, _process_environment())
            verify_authority(root, state["authority"])
            current = inventory(root)
            changes = diff(active["base"]["inventory"], current)
            evidence = {
                "authority_digest": state["authority"]["digest"],
                "base_checkout_sha256": active["base"]["checkout_sha256"],
                "current_checkout_sha256": inventory_digest(current),
                "inventory": current,
                "diff": changes,
                "diff_sha256": digest(changes),
                "violations": violations(changes, active["access"]["write"]),
                "commands": results,
            }
            command["controller"] = evidence
            return self.store._dispatch_prechecked_locked(checked, command)

    def ready(self, *, command_id: str, expected_generation: int | None = None) -> dict[str, Any]:
        _require_expected_generation(expected_generation)
        intent = {"name": "ready", "id": command_id}
        self._preflight_existing_store_location()
        with self.store.transaction():
            state, root = self._loaded()
            current = self._verify_live_checkout(state, root)
            replay = self.store._replay_locked(intent)
            if replay is not None:
                return replay
            command = {
                **intent,
                "expected_generation": state["generation"] if expected_generation is None else expected_generation,
                "controller": {"inventory": current, "checkout_sha256": inventory_digest(current)},
            }
            return self.store._dispatch_locked(command)
