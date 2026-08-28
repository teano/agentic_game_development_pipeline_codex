"""Pure command reducer. It performs no filesystem or process I/O."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .checkout import diff as checkout_diff
from .checkout import authority_items_equal, inventory_digest, matches, path_identity, violations as diff_violations
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
    is_strict_integer,
    new_state,
    normalize_rule,
    passing_artifact,
    pending,
    slice_records,
    slices_are_read_sealed,
    validate_state,
)

COMMANDS = {"init", "status", "next", "complete", "answer", "resume", "accept", "migrate", "ready"}
WORKER_FORBIDDEN_KEYS = {
    "authority_digest", "base_checkout_sha256", "current_checkout_sha256", "checkout",
    "controller", "diff", "diff_sha256", "inventory", "commands", "tests", "receipts",
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


def _command_list(value: Any) -> list[list[str]]:
    if not isinstance(value, list):
        raise PipelineError("commands must be a list of argv lists")
    clean = []
    for argv in value:
        if not isinstance(argv, list) or not argv or any(not isinstance(x, str) or not x for x in argv):
            raise PipelineError("each planned command must be a non-empty argv list")
        clean.append(list(argv))
    return clean


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


def _inventory(value: Any, label: str) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        raise PipelineError(f"{label} inventory is malformed")
    for path, item in value.items():
        if (
            not isinstance(path, str) or not path or not isinstance(item, dict)
            or set(item) != {"kind", "sha256", "size"}
            or item["kind"] not in {"file", "legacy"}
            or not is_digest(item["sha256"])
            or (item["size"] is not None and (type(item["size"]) is not int or item["size"] < 0))
        ):
            raise PipelineError(f"{label} inventory is malformed")
        if normalize_rule(path) != path:
            raise PipelineError(f"{label} inventory paths must be canonical")
    return value


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
        elif value.get("blocker") is not None:
            raise PipelineError("blocker is valid only for blocked QA")
    questions = value.get("questions", [])
    if not isinstance(questions, list) or any(
        not isinstance(item, str) or not item.strip() for item in questions
    ):
        raise PipelineError("worker questions must be non-empty strings")
    return value


def _validate_controller(
    state: dict[str, Any], active: dict[str, Any], evidence: Any,
) -> dict[str, Any] | None:
    required = {
        "authority_digest", "base_checkout_sha256", "current_checkout_sha256",
        "inventory", "diff", "diff_sha256", "violations", "commands",
    }
    if not isinstance(evidence, dict) or set(evidence) != required:
        raise PipelineError("complete requires the exact controller evidence shape")
    if evidence["authority_digest"] != state["authority"]["digest"]:
        raise PipelineError("controller evidence used stale authority")
    base = active["base"]
    if evidence["base_checkout_sha256"] != base.get("checkout_sha256"):
        raise PipelineError("controller evidence used the wrong checkout base")
    _inventory(evidence["inventory"], "controller")
    if not is_digest(evidence["current_checkout_sha256"]) or evidence["current_checkout_sha256"] != inventory_digest(evidence["inventory"]):
        raise PipelineError("current checkout digest is invalid")
    expected_diff = checkout_diff(base["inventory"], evidence["inventory"])
    if not isinstance(evidence["diff"], list) or evidence["diff"] != expected_diff or not is_digest(evidence["diff_sha256"]) or evidence["diff_sha256"] != digest(expected_diff):
        raise PipelineError("controller diff is not derived from its inventories")
    expected_violations = diff_violations(expected_diff, active["access"]["write"])
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
    elif len(results) != len(active["commands"]):
        raise PipelineError("controller command evidence truncated a successful plan")
    if active["phase"] in {"engineering", "qa"} and not results:
        raise PipelineError(f"{active['phase']} requires controller-run checks")
    if not active["access"]["write"] and expected_diff:
        raise PipelineError("a read-only assignment changed the checkout")
    bound = active["capsule"].get("candidate")
    if active["phase"] in {"review", "qa"}:
        if not isinstance(bound, dict) or bound != current_candidate(state) or bound.get("checkout_sha256") != evidence["current_checkout_sha256"]:
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
    candidates = []
    for gate_id, item in state["gates"].items():
        candidate = item.get("candidate_base") if isinstance(item, dict) else None
        if (
            candidate_record_valid(candidate, state["authority"]["digest"])
            and candidate["generation"]
            > max(last_completed_slice_generation, retained_generation)
            and item.get("status") == "closed"
            and item.get("kind") in {"worker_result", "controller_result"}
            and item.get("reason") == "fail"
            and item.get("phase") in {"review", "qa"}
        ):
            candidates.append((candidate["generation"], gate_id, candidate))
    if not candidates:
        return None
    return deepcopy(max(candidates, key=lambda value: (value[0], value[1]))[2])


def _newer_nonpassing_engineering_inventory(
    state: dict[str, Any], candidate: dict[str, Any],
) -> dict[str, Any] | None:
    if state.get("phase") != "engineering" or state.get("active_assignment") is not None:
        return None
    record = state["artifacts"].get("engineering")
    worker = record.get("worker") if isinstance(record, dict) else None
    controller = record.get("controller") if isinstance(record, dict) else None
    assignment_id = record.get("assignment_id") if isinstance(record, dict) else None
    checkout = controller.get("inventory") if isinstance(controller, dict) else None
    commands = controller.get("commands") if isinstance(controller, dict) else None
    failures = [
        (index, item)
        for index, item in enumerate(commands, 1)
        if isinstance(item, dict) and type(item.get("returncode")) is int
        and item["returncode"] != 0
    ] if isinstance(commands, list) else []
    controller_gate = (
        state["gates"].get(f"{assignment_id}-controller-result")
        if isinstance(assignment_id, str) else None
    )
    controller_nonpassing = (
        isinstance(worker, dict) and worker.get("outcome") == "pass"
        and len(failures) == 1 and failures[0][0] == len(commands)
        and isinstance(controller_gate, dict)
        and controller_gate.get("kind") == "controller_result"
        and controller_gate.get("phase") == "engineering"
        and controller_gate.get("reason") == "fail"
        and controller_gate.get("command_index") == failures[0][0]
        and controller_gate.get("returncode") == failures[0][1]["returncode"]
    )
    if (
        not isinstance(worker, dict)
        or (
            worker.get("outcome") not in {"blocked", "fail"}
            and not controller_nonpassing
        )
        or record.get("candidate_binding") != candidate
        or not isinstance(assignment_id, str)
        or not isinstance(controller, dict)
        or controller.get("authority_digest") != state["authority"]["digest"]
    ):
        return None
    try:
        _inventory(checkout, "nonpassing engineering")
    except PipelineError:
        return None
    if (
        not is_digest(controller.get("current_checkout_sha256"))
        or controller["current_checkout_sha256"] != inventory_digest(checkout)
    ):
        return None
    completed_generation = max(
        (
            item["generation"] for item in state["history"]
            if item.get("command") == "complete"
            and item.get("assignment_id") == assignment_id
            and item.get("phase") == "engineering"
            and item.get("result") == assignment_id
            and is_generation(item.get("generation"))
        ),
        default=-1,
    )
    if not candidate_record_valid(candidate, state["authority"]["digest"]):
        return None
    candidate_generation = candidate["generation"]
    last_completed_slice_generation = max(
        (
            item["generation"] for item in state["history"]
            if isinstance(item.get("completed_slice_id"), str)
            and is_generation(item.get("generation"))
        ),
        default=-1,
    )
    if (
        completed_generation <= max(candidate_generation, last_completed_slice_generation)
    ):
        return None
    return checkout


def _validate_interrupted_assignment(state: dict[str, Any], evidence: Any) -> dict[str, Any]:
    active = state["active_assignment"]
    required = {"inventory", "checkout_sha256", "diff", "violations"}
    if active is None or not isinstance(evidence, dict) or set(evidence) != required:
        raise PipelineError("active reconfiguration requires controller interruption evidence")
    current = _inventory(evidence["inventory"], "interrupted checkout")
    if inventory_digest(current) != evidence["checkout_sha256"]:
        raise PipelineError("interrupted checkout digest is invalid")
    authority_paths = {item["path"] for item in state["authority"]["items"].values()}
    expected = [
        item for item in checkout_diff(active["base"]["inventory"], current)
        if item["path"] not in authority_paths
    ]
    expected_violations = diff_violations(expected, active["access"]["write"])
    if evidence["diff"] != expected or evidence["violations"] != expected_violations or expected_violations:
        raise PipelineError(f"interrupted assignment changed forbidden paths: {expected_violations}")
    return {
        "paths": [item["path"] for item in expected]
        if active["phase"] == "engineering" else [],
        "after_checkout_sha256": evidence["checkout_sha256"],
        "diff_sha256": digest(expected),
        "changes": [
            {"path": item["path"], "kind": item["kind"]} for item in expected
        ],
    }


def _interrupted_paths(state: dict[str, Any]) -> list[str]:
    for item in reversed(state["history"]):
        if item.get("command") == "init" and item.get("result") == "authority_scope_reconfigured":
            prior = item.get("prior", {})
            paths = prior.get("interrupted_paths", []) if isinstance(prior, dict) else []
            return paths if isinstance(paths, list) else []
    return []


def _controller_checkout_baseline(
    authority_digest: str, value: Any,
) -> dict[str, Any] | None:
    """Represent an init observation with the ordinary non-passing artifact shape."""
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"inventory", "checkout_sha256"}:
        raise PipelineError("controller checkout base is malformed")
    checkout = _inventory(value["inventory"], "controller checkout base")
    checkout_sha256 = value["checkout_sha256"]
    if not is_digest(checkout_sha256) or checkout_sha256 != inventory_digest(checkout):
        raise PipelineError("controller checkout base digest is invalid")
    return {
        "assignment_id": "controller-checkout-baseline",
        "worker": {
            "outcome": "blocked",
            "summary": "Controller-owned checkout baseline; no phase credit.",
        },
        "controller": {
            "authority_digest": authority_digest,
            "base_checkout_sha256": checkout_sha256,
            "current_checkout_sha256": checkout_sha256,
            "inventory": deepcopy(checkout),
            "diff": [], "diff_sha256": digest([]), "violations": [], "commands": [],
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
    """Return the next state for one of the nine commands."""
    if not isinstance(command, dict) or command.get("name") not in COMMANDS:
        raise PipelineError("unknown command")
    _require_expected_generation(command)
    name = command["name"]
    if name == "status":
        if state is None:
            raise PipelineError("pipeline is not initialized")
        validate_state(state)
        return deepcopy(state)
    if name in {"init", "migrate"}:
        _require_text(command.get("id"), "command id")
        if state is not None:
            validate_state(state)
            if replayed(state, command):
                return deepcopy(state)
            if name != "init":
                raise ConflictError("pipeline is already initialized")
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
            )
            if (
                authority_items_equal(
                    proposed["authority"]["items"], state["authority"]["items"],
                )
                and proposed["slices"] == state["slices"]
            ):
                raise PipelineError("reconfiguration did not change authority or scope")
            baseline = _controller_checkout_baseline(
                proposed["authority"]["digest"], command.get("controller_base"),
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
                "gate_ids": sorted(state["gates"]),
            }
            active = state["active_assignment"]
            if active is not None:
                prior["interrupted_assignment"] = {
                    "id": active["id"], "phase": active["phase"], "role": active["role"],
                    "worker_id": active["worker_id"], "task": active["task"],
                    "access": deepcopy(active["access"]),
                    "base_checkout_sha256": active["base"]["checkout_sha256"],
                    "candidate": deepcopy(active["capsule"].get("candidate")),
                    "after_checkout_sha256": interruption["after_checkout_sha256"],
                    "diff_sha256": interruption["diff_sha256"],
                    "changes": interruption["changes"],
                }
                prior["interrupted_paths"] = interruption["paths"]
            if pending(state["questions"]):
                prior["open_questions"] = {
                    key: deepcopy(state["questions"][key]) for key in pending(state["questions"])
                }
            if pending(state["gates"]):
                prior["open_gates"] = {
                    key: deepcopy(state["gates"][key]) for key in pending(state["gates"])
                }
            retained_artifacts = _retained_candidate_evidence(
                state, proposed["authority"]["digest"],
            )
            if baseline is not None:
                retained_artifacts["plan"] = baseline
            work.update({
                "authority": proposed["authority"], "phase": "plan",
                "active_assignment": None, "slices": proposed["slices"],
                "artifacts": retained_artifacts,
                "questions": {}, "gates": {},
            })
            work = _record(work, command, "authority_scope_reconfigured")
            work["history"][-1]["prior"] = prior
            validate_state(work)
            return work
        if name == "init":
            value = new_state(
                run_id=command["run_id"], project_root=command["project_root"],
                authority=command["authority"], slices=command.get("slices", []),
            )
            baseline = _controller_checkout_baseline(
                value["authority"]["digest"], command.get("controller_base"),
            )
            if baseline is not None:
                value["artifacts"]["plan"] = baseline
            value["history"].append({"id": command["id"], "command": name, "command_digest": command_intent_digest(command), "generation": 0, "result": "initialized"})
            validate_state(value)
            return value
        value = deepcopy(command.get("imported"))
        validate_state(value)
        baseline = _controller_checkout_baseline(
            value["authority"]["digest"], command.get("controller_base"),
        )
        if baseline is not None:
            audit = value["gates"].get("migration-audit")
            resume_engineering = (
                value["phase"] == "engineering"
                and isinstance(audit, dict)
                and audit.get("resolution") == "resume_first_slice_engineering"
            )
            if resume_engineering:
                for phase in ("plan", "slice"):
                    credit = deepcopy(baseline)
                    credit["assignment_id"] = f"legacy-{phase}-credit"
                    credit["worker"] = {
                        "outcome": "pass",
                        "summary": f"Approved schema-10 {phase} credit preserved by migration.",
                    }
                    value["artifacts"][phase] = credit
            else:
                value["artifacts"]["plan"] = baseline
        value["history"].append({"id": command["id"], "command": name, "command_digest": command_intent_digest(command), "generation": value["generation"], "result": "migrated"})
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
        if pending(work["questions"]) or pending(work["gates"]):
            raise PipelineError("questions or gates must be resolved first")
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
        if phase in {"engineering", "docs"} and not write:
            raise PipelineError(f"{phase} must have write access")
        if phase in {"plan", "slice", "review", "qa"} and write:
            raise PipelineError(f"{phase} assignments are read-only")
        authority_paths = [item["path"] for item in work["authority"]["items"].values()]
        if any(matches(path, rule) for path in authority_paths for rule in write):
            raise PipelineError("authority files cannot be writable assignment paths")
        if phase in {"engineering", "qa"} and not commands:
            raise PipelineError(f"{phase} requires planned controller commands")
        base = command.get("controller_base")
        if not isinstance(base, dict) or set(base) != {"inventory", "checkout_sha256"}:
            raise PipelineError("next requires a controller-derived checkout base")
        _inventory(base["inventory"], "checkout base")
        if inventory_digest(base["inventory"]) != base["checkout_sha256"]:
            raise PipelineError("checkout base digest is invalid")
        candidate = current_candidate(work)
        engineering_inventory = None
        if phase == "engineering":
            remediation_candidate = _latest_remediation_candidate(work)
            candidate = remediation_candidate or candidate
            engineering_inventory = (
                _newer_nonpassing_engineering_inventory(work, remediation_candidate)
                if remediation_candidate is not None else None
            )
        engineering_base_sha256 = (
            inventory_digest(engineering_inventory)
            if engineering_inventory is not None else candidate.get("checkout_sha256")
            if candidate is not None else None
        )
        if (
            phase == "engineering" and candidate is not None
            and engineering_base_sha256 != base["checkout_sha256"]
        ):
            raise PipelineError("engineering checkout drifted from its retained candidate base")
        if phase in {"review", "qa"} and candidate is None:
            raise PipelineError(f"{phase} requires an engineering candidate")
        if phase in {"review", "qa"} and candidate.get("checkout_sha256") != base["checkout_sha256"]:
            raise PipelineError(f"{phase} checkout drifted from the current candidate")
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
        context["remediation"] = [
            {"gate_id": key, **deepcopy(item)}
            for key, item in sorted(work["gates"].items())
            if item.get("status") == "closed"
            and item.get("kind") in {"worker_result", "controller_result"}
        ]
        context["migration_audit"] = [
            {"gate_id": key, **deepcopy(item)} for key, item in sorted(work["gates"].items())
            if item.get("status") == "closed" and item.get("kind") == "migration_audit"
        ]
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
            work, active, command.get("controller"),
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
        if (
            (
                active["phase"] == "engineering"
                and artifact["outcome"] == "pass"
            )
            or (active["phase"] == "docs" and evidence["diff"])
        ) and controller_failure is None:
            record["candidate"] = {
                "checkout_sha256": evidence["current_checkout_sha256"],
                "diff_sha256": evidence["diff_sha256"],
                "authority_digest": work["authority"]["digest"],
                "generation": work["generation"] + 1,
            }
        work["artifacts"][active["phase"]] = record
        for index, prompt in enumerate(questions, 1):
            question_id = f"question-{work['generation'] + 1}-{index}"
            work["questions"][question_id] = {
                "status": "open",
                "phase": active["phase"],
                "prompt": _require_text(prompt, "question"),
            }
        if artifact["outcome"] != "pass":
            gate_id = f"{active['id']}-result"
            gate = {
                "status": "open", "phase": active["phase"], "kind": "worker_result",
                "reason": artifact["outcome"], "worker_artifact": deepcopy(artifact),
                "candidate_base": deepcopy(active["capsule"].get("candidate")),
                "slice_id": current_slice(work)["id"],
            }
            if failure_capsule is not None:
                gate["controller_failure"] = failure_capsule
            work["gates"][gate_id] = gate
        elif controller_failure is not None:
            gate_id = f"{active['id']}-controller-result"
            work["gates"][gate_id] = {
                "status": "open", "phase": active["phase"],
                "kind": "controller_result", "reason": "fail",
                "command_index": controller_failure["index"],
                "returncode": controller_failure["returncode"],
                "controller_failure": failure_capsule,
                "candidate_base": deepcopy(active["capsule"].get("candidate")),
                "slice_id": current_slice(work)["id"],
            }
        if active["phase"] == "engineering":
            for stale in ("review", "qa", "docs", "ready"):
                work["artifacts"].pop(stale, None)
        elif active["phase"] == "docs" and evidence["diff"]:
            for stale in ("review", "qa", "ready"):
                work["artifacts"].pop(stale, None)
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

    if name == "resume":
        gate_id = _require_text(command.get("gate_id"), "gate id")
        item = work["gates"].get(gate_id)
        if not item or item["status"] != "open":
            raise PipelineError("gate is not open")
        if item["kind"] == "migration_command_plan":
            active = work["active_assignment"]
            if active is None:
                raise PipelineError("migrated assignment is missing")
            active["commands"] = _command_list(command.get("commands"))
            if active["phase"] in {"engineering", "qa"} and not active["commands"]:
                raise PipelineError("migration resume requires controller commands")
        else:
            source_phase = item["phase"]
            if (
                item.get("reason") == "fail"
                and source_phase in {"review", "qa"}
                and item.get("kind") in {"worker_result", "controller_result"}
            ):
                candidate = item.get("candidate_base")
                if not isinstance(candidate, dict):
                    raise PipelineError("failed verification gate lost its candidate base")
                for stale in ("review", "qa", "docs", "ready"):
                    work["artifacts"].pop(stale, None)
                work["phase"] = "engineering"
            else:
                work["phase"] = source_phase
        item.update({"status": "closed", "resolution": _require_text(command.get("resolution"), "resolution")})
        return _record(work, command, gate_id)

    if name == "accept":
        phase = work["phase"]
        if work["active_assignment"] is not None or pending(work["questions"]) or pending(work["gates"]):
            raise PipelineError("cannot accept with active work, questions, or gates")
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
        if pending(work["questions"]) or pending(work["gates"]):
            raise PipelineError("ready is blocked")
        if not all_slices_completed(work):
            raise PipelineError("ready requires Engineering, Review, and QA for every approved slice")
        candidate = current_candidate(work)
        controller = command.get("controller")
        if not isinstance(controller, dict) or set(controller) != {"inventory", "checkout_sha256"}:
            raise PipelineError("ready requires live controller inventory")
        _inventory(controller["inventory"], "ready controller")
        if not is_digest(controller["checkout_sha256"]) or controller["checkout_sha256"] != inventory_digest(controller["inventory"]):
            raise PipelineError("ready controller inventory is malformed")
        if candidate is None or candidate.get("checkout_sha256") != controller["checkout_sha256"]:
            raise PipelineError("live checkout is not the current candidate")
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
