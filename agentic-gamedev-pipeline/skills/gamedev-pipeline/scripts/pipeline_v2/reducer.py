"""Pure command reducer. It performs no filesystem or process I/O."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .checkout import authority_items_equal, matches, path_identity, violations as diff_violations
from .legacy_gen53 import SCHEMA10_UNSUPPORTED_MESSAGE
from .model import (
    ConflictError,
    NEXT_PHASE,
    PHASES,
    ROLES,
    PipelineError,
    all_slices_completed,
    artifact_schema,
    assignment_output_path,
    candidate_record_valid,
    canonical_command,
    command_intent_digest,
    compact_assignment_context,
    current_candidate,
    current_slice,
    default_assignment,
    digest,
    is_digest,
    is_generation,
    is_git_oid,
    is_strict_integer,
    literal_paths_valid,
    new_state,
    passing_artifact,
    pending,
    slice_records,
    slices_are_read_sealed,
    validate_state,
)

COMMANDS = {"init", "status", "next", "complete", "answer", "accept", "migrate", "ready"}
WORKER_FORBIDDEN_KEYS = {
    "authority_digest", "base_checkout_sha256", "current_checkout_sha256", "checkout",
    "controller", "diff", "diff_sha256", "inventory", "commands", "tests", "receipts",
    "base_tree_oid", "candidate_tree_oid", "changed_paths", "pipeline_runtime_digest",
    "returncode", "stdout_sha256", "stderr_sha256", "stderr_excerpt",
    "stderr_excerpt_truncated", "stderr_excerpt_redacted",
}


def _require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PipelineError(f"{label} is required")
    return value.strip()


def _require_expected_generation(command: dict[str, Any]) -> None:
    value = command.get("expected_generation")
    if value is not None and not is_strict_integer(value):
        raise PipelineError("expected generation must be an integer")


def _contains_forbidden(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in WORKER_FORBIDDEN_KEYS:
                return key
            found = _contains_forbidden(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _contains_forbidden(child)
            if found:
                return found
    return None


def _worker_artifact(value: Any, phase: str, role: str) -> dict[str, Any]:
    schema = artifact_schema(phase, role)
    allowed = set(schema["allowed_keys"])
    required = set(schema["required_keys"])
    if (
        not isinstance(value, dict) or not required <= set(value) or not set(value) <= allowed
        or value.get("outcome") not in schema["outcome_enum"]
    ):
        raise PipelineError(f"{phase} worker artifact must use only {sorted(allowed)} and require {sorted(required)}")
    if phase in {"plan", "slice", "engineering", "docs"}:
        _require_text(value.get("summary"), "summary")
    if phase == "slice" and "slices" in value:
        value = deepcopy(value)
        value["slices"] = slice_records(value["slices"])
    for key in ("assumptions", "checks"):
        if key in value and not isinstance(value[key], list):
            raise PipelineError(f"worker {key} must be a list")
    for key in ("assumptions", "checks"):
        if key in value and any(not isinstance(item, str) or not item.strip() for item in value[key]):
            raise PipelineError(f"worker {key} must contain non-empty strings")
    if phase == "review":
        findings = value.get("findings")
        if not isinstance(findings, list) or any(
            not isinstance(item, dict) or set(item) != {"text", "severity", "kind"}
            or any(not isinstance(item[key], str) or not item[key].strip() for key in item)
            for item in findings
        ):
            raise PipelineError("review findings must be objects with text, severity, and kind")
        if value["outcome"] == "pass" and findings:
            raise PipelineError("passing Review requires no findings")
        if value["outcome"] == "fail" and not findings:
            raise PipelineError("failed Review requires at least one finding")
    if phase == "qa":
        checks = value.get("checks")
        if not isinstance(checks, list):
            raise PipelineError("QA checks are required")
        if value["outcome"] != "blocked" and not checks:
            raise PipelineError("QA pass/fail requires at least one check")
    if value["outcome"] == "blocked":
        _require_text(value.get("blocker"), "blocker")
        _require_text(value.get("required_action"), "required action")
    elif "blocker" in value or "required_action" in value:
        raise PipelineError("blocker and required_action are valid only when blocked")
    questions = value.get("questions", [])
    if not isinstance(questions, list) or any(
        not isinstance(item, str) or not item.strip() for item in questions
    ):
        raise PipelineError("worker questions must be non-empty strings")
    return value


def _validate_controller(
    state: dict[str, Any], active: dict[str, Any], artifact: dict[str, Any], evidence: Any,
) -> dict[str, Any] | None:
    required = {
        "authority_digest", "pipeline_runtime_digest", "base_tree_oid",
        "candidate_tree_oid", "changed_paths", "violations", "commands",
    }
    if not isinstance(evidence, dict) or set(evidence) != required:
        raise PipelineError("complete requires the exact controller evidence shape")
    if evidence["authority_digest"] != state["authority"]["digest"]:
        raise PipelineError("controller evidence used stale authority")
    if evidence["pipeline_runtime_digest"] != state["pipeline_runtime_digest"]:
        raise PipelineError("controller evidence used a different pipeline runtime")
    base = active["base"]
    if evidence["base_tree_oid"] != base.get("candidate_tree_oid"):
        raise PipelineError("controller evidence used the wrong Git candidate base")
    if not is_git_oid(evidence["candidate_tree_oid"]):
        raise PipelineError("controller evidence has a malformed Git candidate tree")
    paths = evidence["changed_paths"]
    if not literal_paths_valid(paths):
        raise PipelineError("controller changed_paths are malformed")
    diff_base = _engineering_candidate_diff_base(state, active)
    if (diff_base == evidence["candidate_tree_oid"]) != (not paths):
        raise PipelineError("controller tree identity and changed_paths disagree")
    expected_violations = diff_violations(paths, active["access"]["write"])
    if not isinstance(evidence["violations"], list) or evidence["violations"] != expected_violations or expected_violations:
        raise PipelineError(f"candidate changed forbidden paths: {expected_violations}")
    results = evidence["commands"]
    if (
        not isinstance(results, list) or any(not isinstance(item, dict) for item in results)
        or len(results) > len(active["commands"])
        or [item.get("argv") for item in results]
        != active["commands"][:len(results)]
    ):
        raise PipelineError("controller command evidence is not an exact planned prefix")
    base_result = {"argv", "returncode", "stdout_sha256", "stderr_sha256"}
    excerpt_result = base_result | {
        "stderr_excerpt", "stderr_excerpt_truncated", "stderr_excerpt_redacted",
    }
    for item in results:
        if (
            type(item.get("returncode")) is not int
            or not is_digest(item.get("stdout_sha256"))
            or not is_digest(item.get("stderr_sha256"))
        ):
            raise PipelineError("malformed controller command result")
        keys = set(item)
        if item["returncode"] == 0:
            if keys != base_result:
                raise PipelineError("successful controller command persisted failure-only evidence")
        elif keys != base_result and keys != excerpt_result:
            raise PipelineError("malformed controller command result")
        elif keys == excerpt_result and (
            not isinstance(item["stderr_excerpt"], str)
            or len(item["stderr_excerpt"].encode("utf-8")) > 4096
            or type(item["stderr_excerpt_truncated"]) is not bool
            or type(item["stderr_excerpt_redacted"]) is not bool
        ):
            raise PipelineError("malformed controller stderr excerpt")
    failures = [
        (index, item)
        for index, item in enumerate(results, 1)
        if item["returncode"] != 0
    ]
    if failures:
        if len(failures) != 1 or failures[0][0] != len(results):
            raise PipelineError("controller command evidence continued after the first failure")
    elif artifact["outcome"] != "blocked" and len(results) != len(active["commands"]):
        raise PipelineError("controller command evidence truncated a successful plan")
    if artifact["outcome"] == "blocked" and results:
        raise PipelineError("blocked worker evidence cannot contain command receipts")
    if (
        artifact["outcome"] != "blocked"
        and active["phase"] in {"engineering", "qa"} and not results
    ):
        raise PipelineError(f"{active['phase']} requires controller-run checks")
    if not active["access"]["write"] and paths:
        raise PipelineError("a read-only assignment changed the Git candidate")
    bound = active["capsule"].get("candidate")
    if active["phase"] in {"review", "qa"}:
        if (
            not isinstance(bound, dict) or bound != current_candidate(state)
            or bound.get("candidate_tree_oid") != evidence["candidate_tree_oid"]
        ):
            raise PipelineError("Review/QA is not bound to the current candidate")
    if not failures:
        return None
    index, failed = failures[0]
    return {"index": index, **deepcopy(failed)}


def _record(
    state: dict[str, Any], command: dict[str, Any], result: str,
    *, completed_actor: dict[str, str] | None = None,
) -> dict[str, Any]:
    state["generation"] += 1
    entry = {
        "id": command["id"], "command": command["name"], "command_digest": command_intent_digest(command),
        "generation": state["generation"], "result": result,
    }
    if completed_actor:
        entry.update(completed_actor)
    state["history"].append(entry)
    validate_state(state)
    return state


def replayed(state: dict[str, Any], command: dict[str, Any]) -> bool:
    _require_expected_generation(command)
    for item in state["history"]:
        if item.get("id") == command.get("id"):
            if item.get("command_digest") != command_intent_digest(command):
                raise ConflictError("command ID was already used for different input")
            return True
    return False


def transaction_precondition(state: dict[str, Any] | None, command: dict[str, Any]) -> bool:
    """Validate replay/CAS before a command performs controller side effects."""
    _require_expected_generation(command)
    if state is None:
        raise PipelineError("pipeline is not initialized")
    validate_state(state)
    if not slices_are_read_sealed(state):
        raise PipelineError(
            "controller read scope is not sealed; only status/init reconfiguration is allowed"
        )
    _require_text(command.get("id"), "command id")
    if replayed(state, command):
        return True
    if command.get("expected_generation") != state["generation"]:
        raise ConflictError("stale generation")
    return False


def _proof_protocol():
    key = object()

    class Proof:
        __slots__ = ("command", "command_digest", "expected_generation", "state", "state_digest", "used")

        def __init__(self, proof_key: object, state: dict[str, Any], command: dict[str, Any]):
            if proof_key is not key:
                raise PipelineError("invalid transaction precondition proof")
            self.state = state
            self.state_digest = digest(state)
            self.command = command
            self.command_digest = command_intent_digest(command)
            self.expected_generation = command.get("expected_generation")
            self.used = False

    def mint(state: dict[str, Any], command: dict[str, Any]) -> object | None:
        """Validate before minting an opaque capability for these exact inputs."""
        canonical_command(command)
        if transaction_precondition(state, command):
            return None
        return Proof(key, state, command)

    def consume(proof: object, state: dict[str, Any] | None, command: dict[str, Any]) -> None:
        if not isinstance(proof, Proof) or (
            proof.used or state is not proof.state or command is not proof.command
            or digest(state) != proof.state_digest
            or command_intent_digest(command) != proof.command_digest
            or command.get("expected_generation") != proof.expected_generation
        ):
            raise PipelineError("transaction precondition proof does not match the checked snapshot")
        proof.used = True

    return mint, consume


_precondition_proof, _consume_precondition_proof = _proof_protocol()
del _proof_protocol


def _latest_remediation_candidate(state: dict[str, Any]) -> dict[str, Any] | None:
    """Return the newest artifact-bound, noncredit candidate for Engineering."""
    if state.get("phase") != "engineering" or state.get("active_assignment") is not None:
        return None
    last_completed_slice_generation = max(
        (
            item["generation"] for item in state["history"]
            if isinstance(item.get("completed_slice_id"), str)
            and is_generation(item.get("generation"))
        ),
        default=-1,
    )
    candidates: list[tuple[int, int, dict[str, Any]]] = []
    for phase in ("engineering", "review", "qa"):
        item = state["artifacts"].get(phase)
        worker = item.get("worker") if isinstance(item, dict) else None
        candidate = (
            item.get("candidate") if phase == "engineering" and isinstance(item, dict)
            else item.get("candidate_binding") if isinstance(item, dict) else None
        )
        noncredit = (
            phase == "engineering"
            and isinstance(worker, dict)
            and (
                worker.get("outcome") != "pass"
                or isinstance(item.get("controller_failure"), dict)
            )
        ) or (
            phase in {"review", "qa"}
            and isinstance(worker, dict)
            and (
                worker.get("outcome") == "fail"
                or isinstance(item.get("controller_failure"), dict)
            )
        )
        if (
            noncredit
            and
            candidate_record_valid(
                candidate, state["authority"]["digest"],
                state["pipeline_runtime_digest"],
            )
            and candidate["generation"] > last_completed_slice_generation
        ):
            candidates.append((candidate["generation"], PHASES.index(phase), candidate))
    if not candidates:
        return None
    return deepcopy(max(candidates, key=lambda value: (value[0], value[1]))[2])


def _verification_failure_context(
    state: dict[str, Any], candidate: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Project only deterministic verification evidence, never remediation prose."""
    if not isinstance(candidate, dict):
        return None
    failures = []
    for phase in ("review", "qa"):
        record = state["artifacts"].get(phase)
        worker = record.get("worker") if isinstance(record, dict) else None
        if (
            isinstance(worker, dict)
            and record.get("candidate_binding") == candidate
            and (
                worker.get("outcome") == "fail"
                or isinstance(record.get("controller_failure"), dict)
            )
        ):
            item = {
                "phase": phase, "candidate": deepcopy(candidate),
                "outcome": worker.get("outcome"),
            }
            if phase == "review":
                item["findings"] = deepcopy(worker.get("findings", []))
            else:
                item["checks"] = deepcopy(worker.get("checks", []))
            if isinstance(record.get("controller_failure"), dict):
                item["controller_failure"] = deepcopy(record["controller_failure"])
            failures.append((candidate["generation"], PHASES.index(phase), item))
    return max(failures, default=(0, 0, None))[-1]


def _engineering_candidate_diff_base(
    state: dict[str, Any], active: dict[str, Any],
) -> str:
    """Keep accepted Engineering deltas cumulative across nonpassing retries."""
    execution_base = active["base"]["candidate_tree_oid"]
    if active.get("phase") != "engineering":
        return execution_base
    binding = active.get("capsule", {}).get("candidate")
    last_completed_slice_generation = max(
        (
            item["generation"] for item in state["history"]
            if isinstance(item.get("completed_slice_id"), str)
            and is_generation(item.get("generation"))
        ),
        default=-1,
    )
    if (
        candidate_record_valid(
            binding, state["authority"]["digest"], state["pipeline_runtime_digest"],
        )
        and binding["generation"] > last_completed_slice_generation
    ):
        return binding["base_tree_oid"]
    return execution_base


def _validate_interrupted_assignment(state: dict[str, Any], evidence: Any) -> dict[str, Any]:
    active = state["active_assignment"]
    required = {"base_tree_oid", "candidate_tree_oid", "changed_paths", "violations"}
    if active is None or not isinstance(evidence, dict) or set(evidence) != required:
        raise PipelineError("active reconfiguration requires controller interruption evidence")
    if (
        evidence["base_tree_oid"] != active["base"]["candidate_tree_oid"]
        or not is_git_oid(evidence["candidate_tree_oid"])
        or not literal_paths_valid(evidence["changed_paths"])
    ):
        raise PipelineError("interrupted Git candidate evidence is invalid")
    expected_violations = diff_violations(
        evidence["changed_paths"], active["access"]["write"],
    )
    if evidence["violations"] != expected_violations or expected_violations:
        raise PipelineError(f"interrupted assignment changed forbidden paths: {expected_violations}")
    return {
        "paths": deepcopy(evidence["changed_paths"])
        if active["phase"] == "engineering" else [],
        "after_candidate_tree_oid": evidence["candidate_tree_oid"],
        "changed_paths": deepcopy(evidence["changed_paths"]),
    }


def _interrupted_paths(state: dict[str, Any]) -> list[str]:
    for item in reversed(state["history"]):
        if item.get("command") == "init" and item.get("result") == "authority_scope_reconfigured":
            prior = item.get("prior", {})
            paths = prior.get("interrupted_paths", []) if isinstance(prior, dict) else []
            return paths if isinstance(paths, list) else []
    return []


def _controller_checkout_baseline(
    authority_digest: str, pipeline_runtime_digest: str, value: Any,
) -> dict[str, Any] | None:
    """Represent an init observation with the ordinary non-passing artifact shape."""
    if value is None:
        return None
    required = {"base_tree_oid", "candidate_tree_oid", "changed_paths"}
    if (
        not isinstance(value, dict) or set(value) != required
        or not is_git_oid(value.get("base_tree_oid"))
        or value.get("candidate_tree_oid") != value.get("base_tree_oid")
        or value.get("changed_paths") != []
    ):
        raise PipelineError("controller Git candidate base is malformed")
    return {
        "assignment_id": "controller-checkout-baseline",
        "worker": {
            "outcome": "blocked",
            "summary": "Controller-owned checkout baseline; no phase credit.",
            "blocker": "Plan has not completed for this authority epoch.",
            "required_action": "Issue a fresh Plan worker assignment.",
        },
        "controller": {
            "authority_digest": authority_digest,
            "pipeline_runtime_digest": pipeline_runtime_digest,
            "base_tree_oid": value["base_tree_oid"],
            "candidate_tree_oid": value["candidate_tree_oid"],
            "changed_paths": [], "violations": [], "commands": [],
        },
        "candidate_binding": None,
    }


def _retained_candidate_evidence(
    state: dict[str, Any], authority_digest: str,
) -> dict[str, Any]:
    """Keep the latest accepted candidate record as non-credit audit evidence."""
    candidate = current_candidate(state)
    if candidate is None:
        return {}
    for phase in ("docs", "engineering"):
        record = state["artifacts"].get(phase)
        if isinstance(record, dict) and record.get("candidate") == candidate:
            retained = deepcopy(record)
            if candidate["authority_digest"] != authority_digest:
                retained.pop("candidate")
            return {phase: retained}
    return {}


def reduce(state: dict[str, Any] | None, command: dict[str, Any]) -> dict[str, Any]:
    """Public reducer entrypoint; replay/CAS validation cannot be bypassed."""
    return _reduce_command(state, command, None)


def _reduce_prechecked(
    state: dict[str, Any], command: dict[str, Any], proof: object,
) -> dict[str, Any]:
    """Reduce one exact snapshot after its store transaction checked replay/CAS."""
    return _reduce_command(state, command, proof)


def _reduce_command(
    state: dict[str, Any] | None, command: dict[str, Any], proof: object | None,
) -> dict[str, Any]:
    """Return the next state for one of the eight commands."""
    if not isinstance(command, dict) or command.get("name") not in COMMANDS:
        raise PipelineError("unknown command")
    _require_expected_generation(command)
    name = command["name"]
    if name == "status":
        if state is None:
            raise PipelineError("pipeline is not initialized")
        validate_state(state)
        return deepcopy(state)
    if name == "migrate":
        raise PipelineError(SCHEMA10_UNSUPPORTED_MESSAGE)
    if name == "init":
        _require_text(command.get("id"), "command id")
        if state is not None:
            validate_state(state)
            if replayed(state, command):
                return deepcopy(state)
            if command.get("expected_generation") != state["generation"]:
                raise ConflictError("stale generation")
            if (
                command.get("run_id") != state["run_id"]
                or not isinstance(command.get("project_root"), str)
                or path_identity(command["project_root"])
                != path_identity(state["project_root"])
            ):
                raise PipelineError("reconfiguration cannot change the run ID or project root")
            interruption = None
            if state["active_assignment"] is not None:
                interruption = _validate_interrupted_assignment(state, command.get("controller_interrupt"))
            proposed = new_state(
                run_id=command["run_id"], project_root=command["project_root"],
                authority=command["authority"], slices=command.get("slices", []),
                base_tree_oid=command["controller_base"]["candidate_tree_oid"],
                pipeline_runtime_digest=command["pipeline_runtime_digest"],
            )
            if (
                authority_items_equal(
                    proposed["authority"]["items"], state["authority"]["items"],
                )
                and proposed["slices"] == state["slices"]
            ):
                raise PipelineError("reconfiguration did not change authority or scope")
            baseline = _controller_checkout_baseline(
                proposed["authority"]["digest"], proposed["pipeline_runtime_digest"],
                command.get("controller_base"),
            )
            work = deepcopy(state)
            audit_candidate = _latest_remediation_candidate(state) or current_candidate(state)
            prior = {
                "phase": state["phase"],
                "authority_digest": state["authority"]["digest"],
                "slices_digest": digest(state["slices"]),
                "candidate": audit_candidate,
                "artifact_phases": sorted(state["artifacts"]),
                "question_ids": sorted(state["questions"]),
            }
            active = state["active_assignment"]
            if active is not None:
                prior["interrupted_assignment"] = {
                    "id": active["id"], "phase": active["phase"], "role": active["role"],
                    "worker_id": active["worker_id"], "task": active["task"],
                    "access": deepcopy(active["access"]),
                    "base_tree_oid": active["base"]["candidate_tree_oid"],
                    "candidate": deepcopy(active["capsule"].get("candidate")),
                    "after_candidate_tree_oid": interruption["after_candidate_tree_oid"],
                    "changed_paths": interruption["changed_paths"],
                }
                prior["interrupted_paths"] = interruption["paths"]
            if pending(state["questions"]):
                prior["open_questions"] = {
                    key: deepcopy(state["questions"][key]) for key in pending(state["questions"])
                }
            retained_artifacts = _retained_candidate_evidence(
                state, proposed["authority"]["digest"],
            )
            if baseline is not None:
                retained_artifacts["plan"] = baseline
            work.update({
                "authority": proposed["authority"], "phase": "plan",
                "checkout_model": proposed["checkout_model"],
                "base_tree_oid": proposed["base_tree_oid"],
                "pipeline_runtime_digest": proposed["pipeline_runtime_digest"],
                "active_assignment": None, "slices": proposed["slices"],
                "artifacts": retained_artifacts,
                "questions": {},
            })
            work = _record(work, command, "authority_scope_reconfigured")
            work["history"][-1]["prior"] = prior
            validate_state(work)
            return work
        value = new_state(
            run_id=command["run_id"], project_root=command["project_root"],
            authority=command["authority"], slices=command.get("slices", []),
            base_tree_oid=command["controller_base"]["candidate_tree_oid"],
            pipeline_runtime_digest=command["pipeline_runtime_digest"],
        )
        baseline = _controller_checkout_baseline(
            value["authority"]["digest"], value["pipeline_runtime_digest"],
            command.get("controller_base"),
        )
        if baseline is not None:
            value["artifacts"]["plan"] = baseline
        value["history"].append({"id": command["id"], "command": name, "command_digest": command_intent_digest(command), "generation": 0, "result": "initialized"})
        validate_state(value)
        return value

    if not slices_are_read_sealed(state):
        raise PipelineError(
            "controller read scope is not sealed; only status/init reconfiguration is allowed"
        )
    if proof is None:
        if transaction_precondition(state, command):
            return deepcopy(state)
    else:
        _consume_precondition_proof(proof, state, command)
    assert state is not None
    work = deepcopy(state)

    if name == "next":
        if work["phase"] == "ready" or work["active_assignment"] is not None:
            raise PipelineError("no next assignment is available")
        if pending(work["questions"]):
            raise PipelineError("questions must be resolved first")
        current_record = work["artifacts"].get(work["phase"])
        current_worker = current_record.get("worker") if isinstance(current_record, dict) else None
        if (
            isinstance(current_worker, dict) and current_worker.get("outcome") == "blocked"
            and current_record.get("assignment_id") != "controller-checkout-baseline"
        ):
            raise PipelineError("blocked is terminal; archive this run and perform a fresh init")
        spec = command.get("assignment")
        if not isinstance(spec, dict):
            raise PipelineError("assignment is required")
        if "artifact_schema" in spec:
            raise PipelineError("assignment artifact_schema is controller-derived")
        phase = work["phase"]
        canonical = default_assignment(work)
        for field in ("id", "worker_id", "task"):
            if spec.get(field) != canonical[field]:
                raise PipelineError(
                    f"assignment {field} is controller-derived and must match status.next_action"
                )
        worker_id = canonical["worker_id"]
        completed_ids = {
            item["actor_id"].strip().casefold()
            for item in work["history"] if isinstance(item.get("actor_id"), str)
        }
        if worker_id.strip().casefold() in completed_ids:
            raise PipelineError("worker ID must name a fresh session; completed actor IDs cannot be reused")
        read = deepcopy(canonical["access"]["read"])
        write = deepcopy(canonical["access"]["write"])
        commands = deepcopy(canonical["checks"])
        if phase == "engineering" and not write:
            raise PipelineError("engineering must have write access")
        if phase in {"plan", "slice", "review", "qa"} and write:
            raise PipelineError(f"{phase} assignments are read-only")
        authority_paths = [item["path"] for item in work["authority"]["items"].values()]
        if any(matches(path, rule) for path in authority_paths for rule in write):
            raise PipelineError("authority files cannot be writable assignment paths")
        if phase in {"engineering", "qa"} and not commands:
            raise PipelineError(f"{phase} requires planned controller commands")
        base = command.get("controller_base")
        if (
            not isinstance(base, dict) or set(base) != {"candidate_tree_oid"}
            or not is_git_oid(base["candidate_tree_oid"])
        ):
            raise PipelineError("next requires a controller-derived Git candidate base")
        candidate = current_candidate(work)
        if phase == "engineering":
            remediation_candidate = _latest_remediation_candidate(work)
            candidate = remediation_candidate or candidate
        engineering_base_tree = candidate.get("candidate_tree_oid") if candidate is not None else None
        if (
            phase == "engineering" and candidate is not None
            and engineering_base_tree != base["candidate_tree_oid"]
        ):
            raise PipelineError("engineering Git candidate drifted from its retained base")
        if phase in {"review", "qa"} and candidate is None:
            raise PipelineError(f"{phase} requires an engineering candidate")
        if (
            phase in {"review", "qa"}
            and candidate.get("candidate_tree_oid") != base["candidate_tree_oid"]
        ):
            raise PipelineError(f"{phase} Git tree drifted from the current candidate")
        context = spec.get("context", {})
        if not isinstance(context, dict):
            raise PipelineError("assignment context must be an object")
        if phase == "review" and context not in ({}, canonical["context"]):
            raise PipelineError(
                "review target is controller-derived and must match status.next_action"
            )
        context = deepcopy(context)
        context["current_slice"] = current_slice(work)
        if phase == "review":
            context["review_target"] = deepcopy(canonical["context"]["review_target"])
        verification_failure = _verification_failure_context(work, candidate)
        if verification_failure is not None:
            context["verification_failure"] = verification_failure
        context["decisions"] = [
            {"id": key, "phase": item["phase"], "prompt": item["prompt"], "answer": item["answer"]}
            for key, item in sorted(work["questions"].items())
            if item.get("status") == "answered"
        ]
        context = compact_assignment_context(context, candidate)
        assignment_id = canonical["id"]
        work["active_assignment"] = {
            "id": assignment_id,
            "phase": phase,
            "role": ROLES[phase],
            "worker_id": worker_id,
            "task": canonical["task"],
            "access": {"read": read, "write": write},
            "capsule": {"authority_digest": work["authority"]["digest"], "candidate": candidate, "context": context},
            "base": deepcopy(base),
            "commands": commands,
            "output_path": assignment_output_path(assignment_id),
            "artifact_schema": artifact_schema(phase, ROLES[phase]),
            "status": "active",
        }
        return _record(work, command, assignment_id)

    if name == "complete":
        active = work["active_assignment"]
        if active is None:
            raise PipelineError("there is no active assignment")
        artifact = _worker_artifact(command.get("artifact"), active["phase"], active["role"])
        forbidden = _contains_forbidden(artifact)
        if forbidden:
            raise PipelineError(f"worker artifact contains controller-owned field {forbidden!r}")
        controller_failure = _validate_controller(
            work, active, artifact, command.get("controller"),
        )
        failure_capsule = None
        if controller_failure is not None:
            failure_capsule = {
                "command_index": controller_failure["index"],
                "returncode": controller_failure["returncode"],
                "stdout_sha256": controller_failure["stdout_sha256"],
                "stderr_sha256": controller_failure["stderr_sha256"],
                "unexecuted_count": len(active["commands"]) - controller_failure["index"],
            }
            for key in (
                "stderr_excerpt", "stderr_excerpt_truncated", "stderr_excerpt_redacted",
            ):
                if key in controller_failure:
                    failure_capsule[key] = deepcopy(controller_failure[key])
        evidence = deepcopy(command["controller"])
        questions = artifact.get("questions", [])
        record = {"assignment_id": active["id"], "worker": deepcopy(artifact), "controller": evidence}
        record["candidate_binding"] = deepcopy(active["capsule"].get("candidate"))
        if active["phase"] == "engineering" or (
            active["phase"] == "docs" and evidence["changed_paths"]
            and artifact["outcome"] == "pass" and controller_failure is None
        ):
            record["candidate"] = {
                "base_tree_oid": _engineering_candidate_diff_base(work, active),
                "candidate_tree_oid": evidence["candidate_tree_oid"],
                "changed_paths": deepcopy(evidence["changed_paths"]),
                "authority_digest": work["authority"]["digest"],
                "pipeline_runtime_digest": work["pipeline_runtime_digest"],
                "generation": work["generation"] + 1,
            }
        if failure_capsule is not None:
            record["controller_failure"] = failure_capsule
        work["artifacts"][active["phase"]] = record
        for index, prompt in enumerate(questions if artifact["outcome"] == "pass" else [], 1):
            question_id = f"question-{work['generation'] + 1}-{index}"
            work["questions"][question_id] = {
                "status": "open",
                "phase": active["phase"],
                "prompt": _require_text(prompt, "question"),
            }
        if active["phase"] == "engineering":
            for stale in ("review", "qa", "docs", "ready"):
                work["artifacts"].pop(stale, None)
        elif active["phase"] == "docs" and evidence["changed_paths"]:
            for stale in ("review", "qa", "ready"):
                work["artifacts"].pop(stale, None)
        if (
            active["phase"] in {"review", "qa"}
            and artifact["outcome"] != "blocked"
            and (artifact["outcome"] == "fail" or controller_failure is not None)
        ):
            failed_phase = active["phase"]
            for stale in ("engineering", "review", "qa", "docs", "ready"):
                if stale != failed_phase:
                    work["artifacts"].pop(stale, None)
            work["phase"] = "engineering"
        work["active_assignment"] = None
        return _record(work, command, active["id"], completed_actor={
            "actor_id": active["worker_id"], "phase": active["phase"],
            "assignment_id": active["id"],
        })

    if name == "answer":
        question_id = _require_text(command.get("question_id"), "question id")
        item = work["questions"].get(question_id)
        if not item or item["status"] != "open":
            raise PipelineError("question is not open")
        item.update({"status": "answered", "answer": _require_text(command.get("answer"), "answer")})
        phase = item["phase"]
        if work["active_assignment"] is not None and work["active_assignment"].get("phase") == phase:
            work["active_assignment"] = None
        work["phase"] = phase
        return _record(work, command, question_id)

    if name == "accept":
        phase = work["phase"]
        if work["active_assignment"] is not None or pending(work["questions"]):
            raise PipelineError("cannot accept with active work or questions")
        record = passing_artifact(work, phase)
        if record is None:
            raise PipelineError("current phase has no passing artifact")
        if phase in {"review", "qa"} and record.get("candidate_binding") != current_candidate(work):
            raise PipelineError("current candidate changed after Review/QA")
        if phase == "slice":
            proposed_slices = slice_records(
                record["worker"].get("slices", work["slices"]), sealed=True,
            )
            proposed_rules = [rule for item in proposed_slices for rule in item["allowed_paths"]]
            uncovered = [
                path for path in _interrupted_paths(work)
                if not any(matches(path, rule) for rule in proposed_rules)
            ]
            if uncovered:
                raise PipelineError(f"revised slices do not cover interrupted Engineering paths: {uncovered}")
            work["slices"] = proposed_slices
        if phase not in NEXT_PHASE:
            raise PipelineError("ready has no acceptance transition")
        candidate = current_candidate(work)
        if phase == "docs" and record.get("candidate") is not None:
            work["phase"] = "review"
        elif (
            phase == "qa" and isinstance(work["artifacts"].get("docs"), dict)
            and work["artifacts"]["docs"].get("worker", {}).get("outcome") == "pass"
            and work["artifacts"]["docs"].get("candidate") == candidate
        ):
            work["phase"] = "ready"
        elif phase == "qa":
            completed_slice = current_slice(work)
            completed_index = next(
                index for index, item in enumerate(work["slices"])
                if item["id"] == completed_slice["id"]
            )
            if completed_index + 1 < len(work["slices"]):
                work["phase"] = "engineering"
                for stale in ("review", "qa", "docs", "ready"):
                    work["artifacts"].pop(stale, None)
            else:
                work["phase"] = "docs"
            result = _record(work, command, work["phase"])
            result["history"][-1]["completed_slice_id"] = completed_slice["id"]
            validate_state(result)
            return result
        else:
            work["phase"] = NEXT_PHASE[phase]
        return _record(work, command, work["phase"])

    if name == "ready":
        if work["phase"] != "ready" or work["active_assignment"] is not None:
            raise PipelineError("pipeline has not reached ready")
        if pending(work["questions"]):
            raise PipelineError("ready is blocked")
        if not all_slices_completed(work):
            raise PipelineError("ready requires Engineering, Review, and QA for every approved slice")
        candidate = current_candidate(work)
        controller = command.get("controller")
        if (
            not isinstance(controller, dict)
            or set(controller) != {"candidate_tree_oid", "pipeline_runtime_digest"}
            or not is_git_oid(controller.get("candidate_tree_oid"))
            or controller.get("pipeline_runtime_digest") != work["pipeline_runtime_digest"]
        ):
            raise PipelineError("ready requires the live Git candidate tree")
        if (
            candidate is None
            or candidate.get("candidate_tree_oid") != controller["candidate_tree_oid"]
        ):
            raise PipelineError("live Git tree is not the current candidate")
        for phase in PHASES[:-1]:
            record = work["artifacts"].get(phase)
            if not isinstance(record, dict) or record.get("worker", {}).get("outcome") != "pass":
                raise PipelineError(f"ready requires accepted {phase} evidence")
        for phase in ("review", "qa"):
            if work["artifacts"][phase].get("candidate_binding") != candidate:
                raise PipelineError(f"{phase} is stale for the current candidate")
        work["artifacts"]["ready"] = {
            "candidate": candidate, "authority_digest": work["authority"]["digest"],
            "controller": deepcopy(controller),
        }
        return _record(work, command, "production_ready_candidate")

    raise AssertionError(name)
