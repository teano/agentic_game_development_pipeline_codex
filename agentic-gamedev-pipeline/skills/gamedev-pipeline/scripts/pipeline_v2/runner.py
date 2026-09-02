"""Imperative controller shell around the pure reducer."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any

from .checkout import (
    authority_items,
    authority_items_equal,
    candidate_tree_oid,
    canonical_project_root,
    changed_paths,
    path_identity,
    pipeline_runtime_digest,
    repository_policy_changed,
    require_clean_head,
    safe_path,
    verify_authority,
    violations,
)
from .legacy_gen53 import SCHEMA10_UNSUPPORTED_MESSAGE
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
    is_git_oid,
    is_strict_integer,
    reconfiguration_action,
    safe_identifier,
    slice_records,
    slices_are_read_sealed,
    status_view,
    validate_state,
)
from .process_tree import run_process_tree
from .reducer import (
    _engineering_candidate_diff_base,
    _newer_nonpassing_engineering_tree,
    _worker_artifact,
)
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


def _replace_literal(value: str, literal: str, replacement: str) -> tuple[str, bool]:
    if not literal:
        return value, False
    updated, count = re.subn(
        re.escape(literal), lambda _match: replacement, value, flags=re.IGNORECASE,
    )
    return updated, count > 0


def _stderr_excerpt(
    raw: bytes, *, raw_truncated: bool, environment: dict[str, str],
    project_root: Path,
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
    roots = [(str(Path(os.path.abspath(project_root))), "[PROJECT_ROOT]")]
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


class Controller:
    def __init__(self, store: StateStore, *, timeout: float = 600.0):
        self.store = store
        self.timeout = timeout

    def _loaded(self, state: dict[str, Any] | None = None) -> tuple[dict[str, Any], Path]:
        state = self.store.load() if state is None else state
        validate_state(state)
        root = canonical_project_root(state["project_root"])
        self.store.validate_project_location(root)
        if pipeline_runtime_digest() != state["pipeline_runtime_digest"]:
            raise PipelineError(
                "pipeline runtime changed during the run; stop and perform a fresh init"
            )
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
                state["pipeline_runtime_digest"],
            )
            and item["candidate_base"]["generation"]
            > max(last_completed_slice_generation, retained_generation)
        ]
        return max(candidates, default=(0, "", None))[-1]

    @staticmethod
    def _latest_controller_tree(state: dict[str, Any]) -> str | None:
        completed_generation = {
            item["assignment_id"]: item["generation"]
            for item in state["history"]
            if isinstance(item.get("assignment_id"), str)
            and is_generation(item.get("generation"))
        }
        epoch_generation = max(
            (
                item["generation"] for item in state["history"]
                if item.get("command") == "init" and is_generation(item.get("generation"))
            ),
            default=-1,
        )
        observed: list[tuple[int, int, str]] = []
        for phase in ("plan", "slice", "engineering", "review", "qa", "docs", "ready"):
            record = state["artifacts"].get(phase)
            controller = record.get("controller") if isinstance(record, dict) else None
            tree = controller.get("candidate_tree_oid") if isinstance(controller, dict) else None
            if is_git_oid(tree):
                generation = completed_generation.get(
                    record.get("assignment_id"),
                    epoch_generation if record.get("assignment_id") == "controller-checkout-baseline" else -1,
                )
                observed.append((generation, PHASES.index(phase), tree))
        return max(observed, default=(-1, -1, None))[-1]

    def _checkout_drift(
        self, state: dict[str, Any], root: Path, current: str,
        *, ignore_authority: bool = False,
    ) -> list[str]:
        authority_paths = {
            path_identity(item["path"]) for item in state["authority"]["items"].values()
        }
        active = state["active_assignment"]
        if active is not None:
            changes = changed_paths(root, active["base"]["candidate_tree_oid"], current)
            if ignore_authority:
                changes = [
                    path for path in changes
                    if path_identity(path) not in authority_paths
                ]
            return violations(changes, active["access"]["write"])
        remediation = self._remediation_candidate(state)
        expected = (
            _newer_nonpassing_engineering_tree(state, remediation)
            if isinstance(remediation, dict) else None
        )
        if expected is None and isinstance(remediation, dict):
            expected = remediation["candidate_tree_oid"]
        if expected is None:
            expected = self._latest_controller_tree(state)
        if expected is None:
            candidate = current_candidate(state)
            expected = candidate.get("candidate_tree_oid") if isinstance(candidate, dict) else None
        if expected is None or expected == current:
            return []
        changes = changed_paths(root, expected, current)
        if ignore_authority:
            changes = [path for path in changes if path_identity(path) not in authority_paths]
        return changes

    def _verify_live_checkout(
        self, state: dict[str, Any], root: Path,
    ) -> str:
        current = candidate_tree_oid(root)
        policy = repository_policy_changed(root, state["base_tree_oid"], current)
        if policy:
            raise PipelineError(
                "repository policy changed during the run; perform a fresh init: "
                + ", ".join(policy)
            )
        drift = self._checkout_drift(state, root, current)
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
            if pipeline_runtime_digest() != state["pipeline_runtime_digest"]:
                raise PipelineError(
                    "pipeline runtime changed during the run; stop and perform a fresh init"
                )
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
            current = candidate_tree_oid(root)
            policy = repository_policy_changed(root, state["base_tree_oid"], current)
            drift = self._checkout_drift(
                state, root, current, ignore_authority=authority_changed,
            )
            view = status_view(state)
            if policy:
                view["next_action"] = {
                    "kind": "terminal", "result": "fresh_init_required",
                    "reason": "repository policy changed: " + ", ".join(policy),
                }
            elif drift:
                view["next_action"] = {
                    "kind": "terminal", "result": "checkout_recovery_required",
                    "reason": f"restore or reconcile checkout drift before mutation: {drift}",
                }
            elif authority_changed or scope_changed:
                view["next_action"] = reconfiguration_action(
                    state, observed, proposed_slices,
                    candidate_tree_oid=current,
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
                "controller_base": {"candidate_tree_oid": snapshot},
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
            runtime_digest = pipeline_runtime_digest()
            if state is not None:
                validate_state(state)
                if runtime_digest != state["pipeline_runtime_digest"]:
                    raise PipelineError(
                        "pipeline runtime changed during the run; stop and perform a fresh init"
                    )
                if supplied_paths is not None:
                    expected_paths = {
                        name: item["path"]
                        for name, item in state["authority"]["items"].items()
                    }
                    if (
                        not isinstance(supplied_paths, dict)
                        or set(supplied_paths) != set(expected_paths)
                        or any(
                            not isinstance(supplied_paths[name], str)
                            or path_identity(supplied_paths[name])
                            != path_identity(expected_paths[name])
                            for name in expected_paths
                        )
                    ):
                        raise PipelineError(
                            "stale approved authority reconfiguration action; run status again"
                        )
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
            current = require_clean_head(root) if state is None else candidate_tree_oid(root)
            if state is not None:
                policy = repository_policy_changed(root, state["base_tree_oid"], current)
                if policy:
                    raise PipelineError(
                        "repository policy changed during the run; perform a fresh init: "
                        + ", ".join(policy)
                    )
                authority_changed = not authority_items_equal(
                    value.get("authority", {}).get("items", {}),
                    state["authority"]["items"],
                )
                drift = self._checkout_drift(
                    state, root, current, ignore_authority=authority_changed,
                )
                if drift:
                    if state.get("active_assignment") is not None:
                        raise PipelineError(f"candidate changed forbidden paths: {drift}")
                    raise PipelineError(f"live checkout drifted from controller evidence: {drift}")
                scope_changed = value["slices"] != state["slices"]
                if authority_changed or scope_changed:
                    expected = reconfiguration_action(
                        state, value["authority"]["items"], value.get("slices"),
                        candidate_tree_oid=current,
                    )
                    if value.get("id") != expected["command_id"]:
                        raise PipelineError(
                            "stale approved authority or scope reconfiguration action; run status again"
                        )
            value["pipeline_runtime_digest"] = runtime_digest
            value["controller_base"] = {
                "base_tree_oid": current,
                "candidate_tree_oid": current,
                "changed_paths": [],
            }
            if state is not None and state.get("active_assignment") is not None:
                active = state["active_assignment"]
                authority_paths = {
                    path_identity(item["path"])
                    for item in state["authority"]["items"].values()
                }
                changes = [
                    path for path in changed_paths(
                        root, active["base"]["candidate_tree_oid"], current,
                    )
                    if path_identity(path) not in authority_paths
                ]
                value["controller_interrupt"] = {
                    "base_tree_oid": active["base"]["candidate_tree_oid"],
                    "candidate_tree_oid": current,
                    "changed_paths": changes,
                    "violations": violations(changes, active["access"]["write"]),
                }
            return self.store._dispatch_locked(value)

    def migrate(self, command: dict[str, Any]) -> dict[str, Any]:
        """Retain the public entry point as an explicit schema-10 tombstone."""
        raise PipelineError(SCHEMA10_UNSUPPORTED_MESSAGE)

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
            artifact = _worker_artifact(artifact, active["phase"], active["role"])
            results = []

            def run_checks(
                checkout: Path, environment: dict[str, str],
            ) -> None:
                for argv in active["commands"]:
                    before_command = candidate_tree_oid(checkout)
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
                        ))
                    results.append(command_result)
                    after_command = candidate_tree_oid(checkout)
                    policy = repository_policy_changed(
                        checkout, state["base_tree_oid"], after_command,
                    )
                    if policy:
                        raise PipelineError(
                            "planned command changed repository policy; perform a fresh init: "
                            + ", ".join(policy)
                        )
                    if after_command != before_command:
                        command_changes = changed_paths(
                            checkout, before_command, after_command,
                        )
                        raise PipelineError(
                            "planned command changed the Git candidate: "
                            + ", ".join(command_changes)
                        )
                    if command_result["returncode"] != 0:
                        break

            if artifact["outcome"] != "blocked":
                run_checks(root, _process_environment())
            verify_authority(root, state["authority"])
            current = candidate_tree_oid(root)
            policy = repository_policy_changed(root, state["base_tree_oid"], current)
            if policy:
                raise PipelineError(
                    "repository policy changed during the run; perform a fresh init: "
                    + ", ".join(policy)
                )
            changes = changed_paths(
                root, _engineering_candidate_diff_base(state, active), current,
            )
            evidence = {
                "authority_digest": state["authority"]["digest"],
                "pipeline_runtime_digest": state["pipeline_runtime_digest"],
                "base_tree_oid": active["base"]["candidate_tree_oid"],
                "candidate_tree_oid": current,
                "changed_paths": changes,
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
                "controller": {
                    "candidate_tree_oid": current,
                    "pipeline_runtime_digest": state["pipeline_runtime_digest"],
                },
            }
            return self.store._dispatch_locked(command)
