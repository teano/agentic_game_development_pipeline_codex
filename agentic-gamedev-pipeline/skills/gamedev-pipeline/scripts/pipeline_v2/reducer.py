"""Pure command reducer. It performs no filesystem or process I/O."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from .technical_decisions import journal_digest, journal_reference, validate_entry, semantic_journal_digest
from .execution import metadata, owner_key, finding_updates, convergence_context, record_finding_resolutions

from .checkout import authority_items_equal, matches, path_identity, violations as diff_violations
from .legacy_gen53 import SCHEMA10_UNSUPPORTED_MESSAGE
from .model import (
    ConflictError,
    NEXT_PHASE,
    PHASES,
    ROLES,
    PipelineError,
    WorkerArtifactValidationError,
    all_slices_completed,
    artifact_schema,
    assignment_identity,
    assignment_output_path,
    candidate_record_valid,
    canonical_command,
    command_intent_digest,
    completed_slice_ids,
    compact_assignment_context,
    answered_decisions,
    required_assignment_context,
    current_candidate,
    current_slice,
    default_assignment,
    documentation_not_required_after_qa,
    effective_slice,
    digest,
    is_digest,
    is_generation,
    is_git_oid,
    is_strict_integer,
    literal_paths_valid,
    new_state,
    passing_artifact,
    pending,
    qa_coverage_complete,
    qa_credit_complete,
    retained_engineering_paths,
    required_qa_identity_ids,
    review_journal_changed,
    slice_records,
    slices_are_read_sealed,
    terminal_blocked_context,
    validate_capability_recovery,
    qa_contract_context,
    validate_state,
)

COMMANDS = {"init", "status", "next", "complete", "answer", "accept", "migrate", "ready", "technical-observe", "technical-decision", "check", "rotate-owner", "read-admit", "recover-capability", "reconcile"}
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


def _bind_qa_contract(state: dict[str, Any], contract: Any) -> None:
    if contract is not None:
        metadata(state)["qa_contract"] = deepcopy(contract)
        metadata(state)["qa_contract_binding"] = {
            "authority_digest": state["authority"]["digest"], "contract_digest": digest(contract),
        }


def _restore_blocker_journal(work: dict[str, Any], prior: dict[str, Any]) -> None:
    journal_change = prior.get("capability_blocker_journal")
    if journal_change is not None:
        if (not isinstance(journal_change, dict) or set(journal_change) != {"id", "entry", "previous"}
                or not isinstance(journal_change["id"], str) or not isinstance(journal_change["entry"], dict)):
            raise PipelineError("invalid controller blocker journal recovery record")
        try:
            for entry in (journal_change["entry"], journal_change["previous"]):
                if entry is not None:
                    validate_entry(entry, sealed=True)
                    if entry["id"] != journal_change["id"]:
                        raise ValueError("controller blocker journal identity changed")
        except ValueError as exc:
            raise PipelineError(str(exc)) from exc
        journal = work.get("technical_decisions", {})
        if journal.get(journal_change["id"]) != journal_change["entry"]:
            raise PipelineError("controller blocker journal changed; capability recovery cannot undo semantic decisions")
        if journal_change["previous"] is None:
            journal.pop(journal_change["id"])
        else:
            journal[journal_change["id"]] = deepcopy(journal_change["previous"])


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


def _worker_artifact(
    value: Any, phase: str, role: str, required_identity_ids: list[str] | None = None, *, state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        result = _validate_worker_artifact(value, phase, role, required_identity_ids)
        if state is not None:
            from .finding_contract import validate_artifact
            validate_artifact(state, phase, result)
            if phase == "qa":
                from .qa_contract import validate_results
                contract = qa_contract_context(state)
                issued = state["active_assignment"]["capsule"]["context"].get("qa_contract")
                if issued != contract:
                    raise PipelineError("QA assignment contract no longer matches sealed authority")
                if contract["status"] != "bound":
                    if result["outcome"] != "blocked":
                        raise PipelineError("QA contract is unresolved; bind approved methods before PASS")
                else:
                    try:
                        validate_results(result["checks"], contract["definition"], outcome=result["outcome"])
                    except ValueError as exc:
                        raise PipelineError(str(exc)) from exc
        return result
    except PipelineError as exc:
        raise WorkerArtifactValidationError(str(exc)) from exc


def _validate_worker_artifact(
    value: Any, phase: str, role: str, required_identity_ids: list[str] | None = None,
) -> dict[str, Any]:
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
    if "technical_decisions" in value:
        entries = value["technical_decisions"]
        if not isinstance(entries, list):
            raise PipelineError("technical_decisions must be a list")
        try:
            for entry in entries:
                validate_entry(entry)
        except ValueError as exc:
            raise PipelineError(str(exc)) from exc
        if len({entry["id"] for entry in entries}) != len(entries):
            raise PipelineError("duplicate technical decision ID in artifact")
    for key in ("assumptions", "checks"):
        if key in value and not isinstance(value[key], list):
            raise PipelineError(f"worker {key} must be a list")
    for key in ("assumptions",):
        if key in value and any(not isinstance(item, str) or not item.strip() for item in value[key]):
            raise PipelineError(f"worker {key} must contain non-empty strings")
    if "finding_resolutions" in value:
        from .finding_contract import validate_resolutions
        validate_resolutions(value["finding_resolutions"], phase)
    if phase == "review":
        from .finding_contract import validate_findings
        validate_findings(value.get("findings"), require_conditions=False)
        if value["outcome"] == "pass" and value["findings"]:
            raise PipelineError("passing Review requires no findings")
        if value["outcome"] == "fail" and not value["findings"] and not any(
            row.get("status") == "unresolved" for row in value.get("finding_resolutions", []) if isinstance(row, dict)
        ):
            raise PipelineError("failed Review requires at least one finding or unresolved prior condition")
    if phase == "qa":
        checks = value.get("checks")
        if not isinstance(checks, list) or any(
            not isinstance(item, dict) or not {"id", "outcome", "evidence"} <= set(item) or set(item) - {"id", "outcome", "evidence", "assertions"}
            or not isinstance(item.get("id"), str) or not item["id"].strip()
            or item.get("outcome") not in {"pass", "fail", "not_run"}
            or not isinstance(item.get("evidence"), str) or not item["evidence"].strip()
            for item in checks
        ):
            raise PipelineError("QA checks require exact id, outcome (pass|fail|not_run), and non-empty execution evidence")
        identities = [item["id"] for item in checks]
        if len(identities) != len(set(identities)):
            raise PipelineError("QA checks contain duplicate identity IDs")
        if value["outcome"] != "blocked" and not checks:
            raise PipelineError("QA pass/fail requires at least one check")
        if required_identity_ids is not None:
            if set(identities) - set(required_identity_ids):
                raise PipelineError("QA checks contain identities outside the approved assignment")
            if value["outcome"] == "pass" and (
                set(identities) != set(required_identity_ids)
                or any(item["outcome"] != "pass" for item in checks)
            ):
                raise PipelineError("QA pass requires the exact mandatory identity set with every outcome pass")
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
    if questions and value["outcome"] != "pass":
        raise PipelineError("questions are for passing technical clarifications only; use blocker/required_action for authority conflicts")
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
        metadata_keys = {"duration_ms", "check_id", "execution_reason", "source_receipt"}
        keys = set(item) - metadata_keys
        stdout_keys = {"stdout_excerpt", "stdout_excerpt_truncated", "stdout_excerpt_redacted"}
        if keys & stdout_keys:
            if not stdout_keys <= keys or item["returncode"] == 0:
                raise PipelineError("malformed controller stdout excerpt")
            if (not isinstance(item["stdout_excerpt"], str) or len(item["stdout_excerpt"].encode("utf-8")) > 4096
                    or type(item["stdout_excerpt_truncated"]) is not bool or type(item["stdout_excerpt_redacted"]) is not bool):
                raise PipelineError("malformed controller stdout excerpt")
            keys -= stdout_keys
        if "duration_ms" in item and (type(item["duration_ms"]) is not int or item["duration_ms"] < 0):
            raise PipelineError("malformed command duration")
        for key in ("check_id", "execution_reason", "source_receipt"):
            if key in item and (not isinstance(item[key], str) or not item[key]):
                raise PipelineError("malformed command telemetry")
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
    elif artifact["outcome"] == "pass" and len(results) != len(active["commands"]):
        raise PipelineError("controller command evidence truncated a successful plan")
    if artifact["outcome"] == "blocked" and results:
        raise PipelineError("blocked worker evidence cannot contain command receipts")
    if (
        artifact["outcome"] == "pass"
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
    if command["name"] == "next":
        entry["issued_identity"] = {key: command["assignment"][key] for key in ("id", "worker_id", "task")}
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
    """Return the newest artifact-bound, noncredit candidate for its existing writer."""
    if state.get("phase") not in {"engineering", "docs"} or state.get("active_assignment") is not None:
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
    owner = state["phase"]
    for phase in (owner, "review", "qa"):
        item = state["artifacts"].get(phase)
        worker = item.get("worker") if isinstance(item, dict) else None
        candidate = (
            item.get("candidate") if phase == owner and isinstance(item, dict)
            else item.get("candidate_binding") if isinstance(item, dict) else None
        )
        noncredit = (
            phase == owner
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
    for phase in ("engineering", "review", "qa"):
        record = state["artifacts"].get(phase)
        worker = record.get("worker") if isinstance(record, dict) else None
        if (
            isinstance(worker, dict)
            and record.get("candidate" if phase == "engineering" else "candidate_binding") == candidate
            and (
                worker.get("outcome") == "fail"
                or isinstance(record.get("controller_failure"), dict)
            )
        ):
            item = {
                "phase": phase, "candidate": deepcopy(candidate),
                "outcome": worker.get("outcome"),
            }
            if phase == "engineering":
                item["summary"] = worker.get("summary", "Engineering checks failed")
            elif phase == "review":
                item["findings"] = deepcopy(worker.get("findings", []))
            else:
                item["checks"] = deepcopy(worker.get("checks", []))
            if isinstance(record.get("review_target"), dict):
                item["review_target"] = deepcopy(record["review_target"])
            if isinstance(record.get("controller_failure"), dict):
                item["controller_failure"] = deepcopy(record["controller_failure"])
            diagnostic = record.get("diagnostic_checks")
            if isinstance(diagnostic, dict) and diagnostic.get("candidate_tree_oid") == candidate["candidate_tree_oid"]:
                item["diagnostic_checks"] = deepcopy(diagnostic)
            failures.append((candidate["generation"], PHASES.index(phase), item))
    return max(failures, default=(0, 0, None))[-1]


def _engineering_candidate_diff_base(
    state: dict[str, Any], active: dict[str, Any],
) -> str:
    """Keep accepted Engineering deltas cumulative across nonpassing retries."""
    execution_base = active["base"]["candidate_tree_oid"]
    if active.get("phase") not in {"engineering", "docs"}:
        return execution_base
    binding = active.get("capsule", {}).get("candidate")
    failure = active.get("capsule", {}).get("context", {}).get("verification_failure", {})
    documentation_origin = failure.get("review_target", {}).get("kind") == "documentation_changes"
    if active["phase"] == "engineering" and documentation_origin:
        # Product QA failed after Docs: the reviewed Docs bytes are the execution
        # baseline, not product changes that the Engineer must rewrite.
        return execution_base
    if active["phase"] == "docs":
        prior_docs = state["artifacts"].get("docs", {})
        if binding is not None and (prior_docs.get("candidate") == binding or documentation_origin):
            return binding["base_tree_oid"]
        return execution_base
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


def _retained_candidate_evidence(state: dict[str, Any]) -> dict[str, Any]:
    """Keep the latest accepted candidate record as non-credit audit evidence."""
    candidate = current_candidate(state)
    if candidate is None:
        return {}
    for phase in ("docs", "engineering"):
        record = state["artifacts"].get(phase)
        if isinstance(record, dict) and record.get("candidate") == candidate:
            retained = deepcopy(record)
            retained.pop("candidate")
            return {phase: retained}
    return {}


def _confirm_approved_plan(state: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    """Record controller confirmation only; product verification remains open."""
    epoch = state["generation"]
    for phase in ("plan", "slice"):
        identity = f"approved-{phase}-{state['authority']['digest'][:16]}-g{epoch}"
        state["artifacts"][phase] = {
            "assignment_id": identity,
            "worker": {"outcome": "pass", "summary": "Exact approved authority and sealed scope confirmed by controller."},
            "controller": deepcopy(baseline["controller"]),
            "candidate_binding": None,
            "technical_journal_digest": journal_digest(state.get("technical_decisions", {})),
            "semantic_journal_digest": semantic_journal_digest(state.get("technical_decisions", {})),
        }
        state = _record(state, {"name": "confirm-approved", "id": identity}, phase,
                        completed_actor={"actor_id": "controller", "phase": phase, "assignment_id": identity})
    state["phase"] = "engineering"
    return state


def _runtime_rebind_can_confirm(state: dict[str, Any]) -> bool:
    if pending(state["questions"]) or terminal_blocked_context(state) is not None:
        return False
    if state["phase"] not in {"plan", "slice"}:
        return True
    if (state["phase"] != "plan"
            or state["artifacts"].get("plan", {}).get("assignment_id") != "controller-checkout-baseline"):
        return False
    # An older runtime may already have reset an idle downstream run to Plan.
    # Follow only unchanged-authority/scope resets back to that boundary; a
    # genuine upstream replan or interrupted worker must still be resolved.
    for event in reversed(state["history"]):
        if event.get("command") == "complete" and event.get("phase") in {"plan", "slice"}:
            return False
        if event.get("command") != "init" or event.get("result") != "authority_scope_reconfigured":
            continue
        prior = event.get("prior", {})
        if (prior.get("authority_digest") != state["authority"]["digest"]
                or prior.get("slices_digest") != digest(state["slices"])
                or prior.get("open_questions") or prior.get("interrupted_assignment")
                or prior.get("approved_plan_reuse_allowed") is False):
            return False
        if prior.get("phase") != "plan":
            return prior.get("phase") in {"engineering", "review", "qa", "docs", "ready"}
    return False


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
                or command.get("feature") != state["feature"]
                or command.get("workflow_path") != state["workflow_path"]
                or not isinstance(command.get("project_root"), str)
                or path_identity(command["project_root"])
                != path_identity(state["project_root"])
            ):
                raise PipelineError("reconfiguration cannot change the run ID or project root")
            if command.get("product_failure") is not None:
                if state["phase"] != "qa" or terminal_blocked_context(state) is None:
                    raise PipelineError("product failure requires terminal QA")
                packet = command["product_failure"]
                work = deepcopy(state)
                original = deepcopy(state["artifacts"])
                record = deepcopy(original["qa"])
                try:
                    record["worker"] = _worker_artifact({"outcome": "fail", "checks": packet["checks"]}, "qa", "qa")
                except WorkerArtifactValidationError as exc:
                    raise PipelineError(str(exc)) from exc
                record.pop("controller_failure", None)
                # Rebind only noncredit remediation evidence; original QA remains in history.
                record["candidate_binding"]["pipeline_runtime_digest"] = command["pipeline_runtime_digest"]
                record["candidate_binding"]["generation"] = state["generation"] + 1
                work["pipeline_runtime_digest"] = command["pipeline_runtime_digest"]
                for stale in ("engineering", "review", "qa", "docs", "ready"):
                    work["artifacts"].pop(stale, None)
                work["artifacts"]["qa"] = record
                work["phase"] = "engineering"
                work = _record(work, command, "qa_product_failure")
                work["history"][-1].update({"product_failure": deepcopy(packet), "prior_artifacts": original})
                return work
            interruption = None
            if state["active_assignment"] is not None:
                interruption = _validate_interrupted_assignment(state, command.get("controller_interrupt"))
            proposed = new_state(
                run_id=command["run_id"], feature=command["feature"],
                workflow_path=command["workflow_path"],
                project_root=command["project_root"],
                authority=command["authority"], slices=command.get("slices", []),
                base_tree_oid=command["controller_base"]["candidate_tree_oid"],
                pipeline_runtime_digest=command["pipeline_runtime_digest"],
            )
            unchanged_authority_scope = (
                authority_items_equal(
                    proposed["authority"]["items"], state["authority"]["items"],
                )
                and proposed["slices"] == state["slices"]
            )
            unchanged_bindings = (unchanged_authority_scope
                                  and proposed["pipeline_runtime_digest"] == state["pipeline_runtime_digest"])
            contract_changed = command.get("qa_contract") != state.get("execution", {}).get("qa_contract")
            if unchanged_bindings and contract_changed:
                if state["active_assignment"] is not None or pending(state["questions"]):
                    raise PipelineError("QA contract binding requires an idle assignment and resolved questions")
                if command.get("qa_contract") is None:
                    raise PipelineError("QA contract cannot be removed from unchanged authority")
                old_definitions = state.get("execution", {}).get("qa_contract", {}).get("slices", {})
                for completed_id in completed_slice_ids(state):
                    if old_definitions.get(completed_id) != command["qa_contract"]["slices"].get(completed_id):
                        raise PipelineError("QA contract changes completed slices; use approved reconvergence before reusing their acceptance")
                candidate = current_candidate(state)
                if candidate is not None and command["controller_base"]["candidate_tree_oid"] != candidate["candidate_tree_oid"]:
                    raise PipelineError("QA contract binding cannot admit product drift")
                work = deepcopy(state)
                prior_artifacts = deepcopy({key: work["artifacts"][key] for key in ("review", "qa", "docs", "ready") if key in work["artifacts"]})
                prior_contract = deepcopy(state.get("execution", {}).get("qa_contract"))
                _bind_qa_contract(work, command["qa_contract"])
                prior_qa = prior_artifacts.get("qa", {})
                if (prior_qa.get("qa_contract") or {}).get("status") == "unresolved":
                    _restore_blocker_journal(work, prior_qa)
                if candidate is not None and state["phase"] in {"review", "qa", "docs", "ready"}:
                    # Reassess the normalized methods independently; retain the
                    # implementation and current product tree, never old QA credit.
                    for key in ("review", "qa", "docs", "ready"):
                        work["artifacts"].pop(key, None)
                    engineering = work["artifacts"].get("engineering", {}).get("candidate")
                    if engineering != candidate:
                        raise PipelineError("QA contract rebinding after documentation changes requires the normal approved reconvergence route")
                    work["phase"] = "review"
                work = _record(work, command, "qa_contract_bound")
                work["history"][-1].update({"prior_artifacts": prior_artifacts, "prior_qa_contract": prior_contract})
                validate_state(work)
                return work
            runtime_rebind = (unchanged_authority_scope and not unchanged_bindings
                              and state["active_assignment"] is None
                              and slices_are_read_sealed(state)
                              and command.get("maintenance") is None and command.get("recovery") is None)
            if unchanged_bindings and terminal_blocked_context(state) is None:
                raise PipelineError("reconfiguration did not change authority, scope, or runtime")
            if (unchanged_bindings and terminal_blocked_context(state) is not None
                    and command.get("recovery") is None
                    and proposed["base_tree_oid"] == state["artifacts"][state["phase"]].get("controller", {}).get("candidate_tree_oid")):
                raise PipelineError("unchanged blocked bindings require recover-capability with fresh prerequisite evidence")
            baseline = _controller_checkout_baseline(
                proposed["authority"]["digest"], proposed["pipeline_runtime_digest"],
                command.get("controller_base"),
            )
            work = deepcopy(state)
            audit_candidate = _latest_remediation_candidate(state) or current_candidate(state)
            if command.get("maintenance") is not None:
                audit_candidate = audit_candidate or deepcopy(state["active_assignment"]["capsule"].get("candidate"))
            prior = {
                "phase": state["phase"],
                "authority_digest": state["authority"]["digest"],
                "slices_digest": digest(state["slices"]),
                "candidate": audit_candidate,
                "artifact_phases": sorted(state["artifacts"]),
                "question_ids": sorted(state["questions"]),
            }
            if runtime_rebind:
                prior["runtime_rebind"] = True
                prior["approved_plan_reuse_allowed"] = _runtime_rebind_can_confirm(state)
                prior["product_evidence"] = deepcopy({
                    phase: record for phase, record in state["artifacts"].items()
                    if phase in {"engineering", "review", "qa", "docs"}
                })
                failures = [failure for record in prior["product_evidence"].values()
                            if (failure := _verification_failure_context(
                                state, record.get("candidate") or record.get("candidate_binding"))) is not None]
                if failures:
                    prior["verification_failure"] = max(
                        failures, key=lambda item: (item["candidate"]["generation"], PHASES.index(item["phase"])))
                elif audit_candidate is None:
                    for event in reversed(state["history"]):
                        previous = event.get("prior", {})
                        if event.get("command") != "init":
                            continue
                        failure = previous.get("verification_failure")
                        if (previous.get("runtime_rebind")
                                and previous.get("authority_digest") == state["authority"]["digest"]
                                and previous.get("slices_digest") == digest(state["slices"])
                                and isinstance(failure, dict)
                                and failure["candidate"]["candidate_tree_oid"] == proposed["base_tree_oid"]):
                            prior["verification_failure"] = deepcopy(failure)
                        break
            if command.get("recovery") is not None:
                prior["recovery"] = deepcopy(command["recovery"])
            active = state["active_assignment"]
            if command.get("maintenance") is not None:
                prior["maintenance"] = deepcopy(command["maintenance"])
                failure = _verification_failure_context(state, active["capsule"].get("candidate"))
                if failure is not None:
                    prior["verification_failure"] = failure
                    prior["verification_artifact"] = deepcopy(state["artifacts"][failure["phase"]])
            if active is not None:
                prior["interrupted_assignment"] = {
                    "id": active["id"], "phase": active["phase"], "role": active["role"],
                    "worker_id": active["worker_id"], "task": active["task"],
                    "access": deepcopy(active["access"]),
                    "base_tree_oid": active["base"]["candidate_tree_oid"],
                    "candidate": deepcopy(active["capsule"].get("candidate")),
                    **({"context": deepcopy(active["capsule"]["context"])} if command.get("maintenance") is not None else {}),
                    "after_candidate_tree_oid": interruption["after_candidate_tree_oid"],
                    "changed_paths": interruption["changed_paths"],
                }
                prior["interrupted_paths"] = interruption["paths"]
            if pending(state["questions"]):
                prior["open_questions"] = {
                    key: deepcopy(state["questions"][key]) for key in pending(state["questions"])
                }
            retained_artifacts = _retained_candidate_evidence(state)
            if baseline is not None:
                retained_artifacts["plan"] = baseline
            work.update({
                "authority": proposed["authority"], "phase": "plan",
                "checkout_model": proposed["checkout_model"],
                "base_tree_oid": proposed["base_tree_oid"],
                "pipeline_runtime_digest": proposed["pipeline_runtime_digest"],
                "active_assignment": None, "slices": proposed["slices"],
                "artifacts": retained_artifacts,
                "questions": deepcopy(state["questions"]) if runtime_rebind else {},
            })
            unresolved_review_paths = sorted({path for paths in state.get("execution", {}).get("review_obligations", {}).values() for path in paths})
            work.pop("execution", None)
            if command.get("verification") is not None:
                metadata(work)["verification"] = deepcopy(command["verification"])
            _bind_qa_contract(work, command.get("qa_contract"))
            if runtime_rebind:
                for key in ("findings", "read_admissions"):
                    metadata(work)[key] = deepcopy(state.get("execution", {}).get(key, {}))
            if unresolved_review_paths:
                # This is an outstanding read/verification obligation, not old
                # product credit. Keep its original packet in history and bind
                # it to the fresh epoch's first verification boundary.
                metadata(work)["review_obligations"] = {work["slices"][0]["id"]: unresolved_review_paths}
            work = _record(work, command, "authority_scope_reconfigured")
            work["history"][-1]["prior"] = prior
            if (runtime_rebind and _runtime_rebind_can_confirm(state)
                    and command.get("verification", {}).get("confirm_approved_plan")):
                work = _confirm_approved_plan(work, baseline)
            validate_state(work)
            return work
        value = new_state(
            run_id=command["run_id"], feature=command["feature"],
            workflow_path=command["workflow_path"],
            project_root=command["project_root"],
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
        if command.get("verification") is not None:
            metadata(value)["verification"] = deepcopy(command["verification"])
            if command["verification"].get("confirm_approved_plan"):
                value = _confirm_approved_plan(value, baseline)
        _bind_qa_contract(value, command.get("qa_contract"))
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

    if name == "check":
        active = work["active_assignment"]
        observed = command.get("controller", {})
        if (active is None or active["phase"] not in {"engineering", "qa"}
                or observed.get("assignment_id") != active["id"]
                or not is_git_oid(observed.get("candidate_tree_oid"))):
            raise PipelineError("diagnostic check requires the exact active Engineering or QA lease")
        metadata(work)["receipts"].update(deepcopy(command.get("controller_receipts", {})))
        active["capsule"]["context"]["diagnostic_checks"] = deepcopy(observed)
        active["capsule"]["context"]["machine_checks"] = deepcopy(command["controller_machine_checks"])
        return _record(work, command, "diagnostic_checks_completed")

    if name == "rotate-owner":
        if work["active_assignment"] is not None:
            raise PipelineError("owner rotation requires an idle assignment boundary")
        _require_text(command.get("reason"), "rotation reason")
        metadata(work)["owners"].pop(owner_key(work), None)
        return _record(work, command, "owner_retired")

    if name == "read-admit":
        active = work["active_assignment"]
        if active is None:
            raise PipelineError("read admission requires an active assignment")
        path = command.get("controller", {}).get("path")
        if not isinstance(path, str) or not path:
            raise PipelineError("read admission requires a validated exact source")
        admitted = metadata(work)["read_admissions"].setdefault(owner_key(work, "shared"), [])
        if path not in admitted:
            admitted.append(path)
        active["access"]["read"] = list(dict.fromkeys(active["access"]["read"] + [path]))
        return _record(work, command, "read_dependency_admitted")

    if name == "recover-capability":
        validate_capability_recovery(work, command)
        phase = work["phase"]
        prior = deepcopy(work["artifacts"][phase])
        _restore_blocker_journal(work, prior)
        restored = work["artifacts"][phase]
        restored["worker"]["outcome"] = "fail"
        restored["worker"].pop("blocker", None)
        restored["worker"].pop("required_action", None)
        restored.pop("capability_blocker_journal", None)
        archived = {phase: prior}
        # Match the existing QA acceptance route for actual semantic changes.
        # Pure capability restoration restores the prior journal and stays in QA.
        if phase == "qa" and review_journal_changed(work):
            work["phase"] = "review"
            previous_review = work["artifacts"].pop("review", None)
            if previous_review is not None:
                archived["review"] = previous_review
        result = _record(work, command, "capability_restored")
        result["history"][-1]["prior_artifacts"] = archived
        result["history"][-1]["evidence"] = deepcopy(command["evidence"])
        result["history"][-1]["resume_phase"] = work["phase"]
        return result

    if name == "reconcile":
        if work["active_assignment"] is not None:
            raise PipelineError("checkout reconcile requires an idle assignment boundary")
        from .no_progress import no_progress_hold
        if no_progress_hold(work) is not None:
            relevant = default_assignment(work)["access"]["read"]
            if not any(not diff_violations([row["path"]], relevant) for row in command["packet"]["paths"]):
                raise PipelineError("no-progress hold cannot be cleared by unrelated external changes; resolve the bound work basis")
        observed = command["controller"]
        prior = deepcopy(work["artifacts"])
        candidate = {"base_tree_oid": observed["candidate_tree_oid"],
                     "candidate_tree_oid": observed["candidate_tree_oid"], "changed_paths": [],
                     "authority_digest": work["authority"]["digest"],
                     "pipeline_runtime_digest": work["pipeline_runtime_digest"],
                     "generation": work["generation"] + 1}
        work["artifacts"] = {key: item for key, item in prior.items() if key in {"plan", "slice"}}
        work["artifacts"]["engineering"] = {
            "assignment_id": "reconciled-external-baseline", "candidate": candidate,
            "worker": {"outcome": "fail", "summary": "External changes admitted; fresh product verification is required."},
            "controller": {"authority_digest": work["authority"]["digest"],
                           "pipeline_runtime_digest": work["pipeline_runtime_digest"],
                           "base_tree_oid": observed["candidate_tree_oid"], "candidate_tree_oid": observed["candidate_tree_oid"],
                           "changed_paths": [], "violations": [], "commands": []}}
        work["phase"] = "engineering"
        metadata(work)["receipts"] = {}
        metadata(work)["reconciled_tree"] = observed["candidate_tree_oid"]
        selected_id = work["slices"][min(len(observed["retained_prefix"]), len(work["slices"]) - 1)]["id"]
        obligations = metadata(work).setdefault("review_obligations", {})
        obligations[selected_id] = sorted(set(obligations.get(selected_id, [])) | {item["path"] for item in command["packet"]["paths"]})
        # Record the prefix before validation, since it establishes current_slice.
        work["generation"] += 1
        work["history"].append({"id": command["id"], "command": name,
                                "command_digest": command_intent_digest(command), "generation": work["generation"],
                                "assignment_id": "reconciled-external-baseline",
                                "result": "external_changes_reconciled", "retained_prefix": observed["retained_prefix"],
                                "prior_artifacts": prior, "packet": deepcopy(command["packet"])})
        validate_state(work)
        return work

    if name in {"technical-observe", "technical-decision"}:
        active = work["active_assignment"]
        if active is None or active["phase"] != "engineering" or command.get("controller", {}).get("assignment_id") != active["id"]:
            raise PipelineError("technical action requires the current Engineering assignment")
        if name == "technical-observe":
            observed = command.get("controller")
            if not isinstance(observed, dict) or set(observed) != {"tree", "action", "assignment_id"} or not is_git_oid(observed["tree"]):
                raise PipelineError("technical observation requires controller tree evidence")
            _require_text(observed["action"], "technical action description")
            active["technical_observation"] = {"id": command["id"], **deepcopy(observed)}
        else:
            entry = command.get("controller", {}).get("entry")
            try:
                validate_entry(entry, sealed=True)
            except ValueError as exc:
                raise PipelineError(str(exc)) from exc
            work.setdefault("technical_decisions", {})[entry["id"]] = deepcopy(entry)
            canonical = default_assignment(work)
            active["access"] = deepcopy(canonical["access"])
            active["commands"] = deepcopy(canonical["checks"])
            active["capsule"]["context"]["current_slice"] = current_slice(work)
            active["capsule"]["context"]["technical_journal"] = journal_reference(work)
            active["capsule"]["context"]["technical_decisions"] = list(work["technical_decisions"].values())
            active["capsule"]["context"] = required_assignment_context(work, active)
            active["id"] = assignment_identity(work["run_id"], work["generation"] + 1, "engineering")["id"]
            active["output_path"] = assignment_output_path(active["id"], work["feature"])
            active.pop("technical_observation", None)
            for stale in ("review", "qa", "docs", "ready"):
                work["artifacts"].pop(stale, None)
        return _record(work, command, command["id"])

    if name == "next":
        if work["phase"] == "ready" or work["active_assignment"] is not None:
            raise PipelineError("no next assignment is available")
        from .no_progress import no_progress_hold
        if no_progress_hold(work) is not None:
            raise PipelineError("no-progress hold forbids unchanged Engineering redispatch; submit the bound specialist resolution through answer")
        if pending(work["questions"]):
            raise PipelineError("questions must be resolved first")
        current_record = work["artifacts"].get(work["phase"])
        current_worker = current_record.get("worker") if isinstance(current_record, dict) else None
        if (
            isinstance(current_worker, dict) and current_worker.get("outcome") == "blocked"
            and current_record.get("assignment_id") != "controller-checkout-baseline"
        ):
            raise PipelineError("blocked is terminal; resolve the prerequisite and use status-bound recover-capability with fresh evidence")
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
        expected_owner = metadata(work)["owners"].get(owner_key(work))
        if worker_id.strip().casefold() in completed_ids and worker_id != expected_owner:
            raise PipelineError("worker ID belongs to another completed role or slice")
        metadata(work)["owners"][owner_key(work)] = worker_id
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
        if phase in {"engineering", "docs"}:
            remediation_candidate = _latest_remediation_candidate(work)
            candidate = remediation_candidate or candidate
        engineering_base_tree = candidate.get("candidate_tree_oid") if candidate is not None else None
        if (
            phase in {"engineering", "docs"} and candidate is not None
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
        if phase == "qa" and context not in ({}, canonical["context"]):
            raise PipelineError("QA required identities are controller-derived")
        context = deepcopy(context)
        for field in ("acceptance_contract_version", "qa_contract", "qa_previous_observations"):
            if field in canonical.get("context", {}):
                context[field] = deepcopy(canonical["context"][field])
            else:
                context.pop(field, None)
        context["current_slice"] = current_slice(work)
        context["technical_journal"] = journal_reference(work)
        context["technical_decisions"] = list(work.get("technical_decisions", {}).values())
        if "capability_recovery" in canonical.get("context", {}):
            context["capability_recovery"] = deepcopy(canonical["context"]["capability_recovery"])
        if phase == "review":
            context["review_target"] = deepcopy(canonical["context"]["review_target"])
            if "required_identity_ids" in canonical["context"]:
                context["required_identity_ids"] = deepcopy(canonical["context"]["required_identity_ids"])
        if phase == "qa":
            expected_context = canonical["context"]
            context.update(deepcopy(expected_context))
            context["machine_checks"] = deepcopy(command.get("controller_machine_checks", {
                "checks": [], "pending_check_ids": [f"command-{index + 1}" for index in range(len(commands))],
                "grants_manual_acceptance": False,
            }))
            prior_target = work["artifacts"].get("review", {}).get("review_target")
            if isinstance(prior_target, dict):
                context["review_target"] = deepcopy(prior_target)
        verification_failure = _verification_failure_context(work, candidate)
        if verification_failure is not None:
            context["verification_failure"] = verification_failure
        context["decisions"] = answered_decisions(work)
        context = compact_assignment_context(context, candidate, canonical_input=True)
        convergence = convergence_context(work)
        if convergence:
            context["convergence"] = convergence
        if phase == "engineering" and candidate is None:
            for item in reversed(work["history"]):
                prior = item.get("prior", {})
                if prior.get("runtime_rebind"):
                    if (prior.get("authority_digest") == work["authority"]["digest"]
                            and prior.get("slices_digest") == digest(work["slices"])
                            and isinstance(prior.get("verification_failure"), dict)):
                        context["verification_failure"] = deepcopy(prior["verification_failure"])
                    break
                maintenance = prior.get("maintenance")
                if not isinstance(maintenance, dict):
                    continue
                if (maintenance["candidate_tree_oid"] == base["candidate_tree_oid"]
                        and maintenance["authority_digest"] == work["authority"]["digest"]
                        and maintenance["slice_digest"] == digest(current_slice(work))
                        and isinstance(prior.get("verification_failure"), dict)):
                    # Historical source binding is evidence, never current phase credit.
                    context["verification_failure"] = deepcopy(prior["verification_failure"])
                break
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
            "output_path": assignment_output_path(assignment_id, work["feature"]),
            "artifact_schema": artifact_schema(phase, ROLES[phase]),
            "status": "active",
        }
        return _record(work, command, assignment_id)

    if name == "complete":
        active = work["active_assignment"]
        if active is None:
            raise PipelineError("there is no active assignment")
        required_assignment_context(work, active)
        required_ids = (
            default_assignment(work)["context"]["required_identity_ids"]
            if active["phase"] == "qa" else None
        )
        if required_ids is not None and active["capsule"]["context"].get("required_identity_ids") != required_ids:
            raise PipelineError("QA assignment identities no longer match approved authority")
        artifact = _worker_artifact(command.get("artifact"), active["phase"], active["role"], required_ids, state=work)
        if active["capsule"]["context"].get("technical_journal", {}).get("sha256", journal_digest({})) != journal_digest(work.get("technical_decisions", {})):
            raise PipelineError("assignment technical journal is stale")
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
                "stdout_excerpt", "stdout_excerpt_truncated", "stdout_excerpt_redacted",
            ):
                if key in controller_failure:
                    failure_capsule[key] = deepcopy(controller_failure[key])
        evidence = deepcopy(command["controller"])
        metadata(work)["receipts"].update(deepcopy(command.get("controller_receipts", {})))
        for entry in artifact.get("technical_decisions", []):
            entry = deepcopy(entry)
            previous = work.get("technical_decisions", {}).get(entry["id"], {})
            if "execution" in previous:
                entry["execution"] = deepcopy(previous["execution"])
            work.setdefault("technical_decisions", {})[entry["id"]] = entry
        blocker_journal = None
        if artifact["outcome"] == "blocked" and not artifact.get("technical_decisions"):
            blocker_id = f"TD-BLOCK-{digest(current_slice(work)['id'])[:10]}-{active['phase']}"
            previous_blocker = deepcopy(work.get("technical_decisions", {}).get(blocker_id))
            work.setdefault("technical_decisions", {})[blocker_id] = {
                "id": blocker_id, "situation": artifact["blocker"],
                "decision": "Unresolved: " + artifact["required_action"], "basis": artifact.get("summary", artifact["blocker"]),
                "checks": [], "downstream": "Unresolved prerequisite; no passing credit. Resume only after the recorded prerequisite is resolved.",
            }
            if previous_blocker is not None and "execution" in previous_blocker:
                work["technical_decisions"][blocker_id]["execution"] = deepcopy(previous_blocker["execution"])
            blocker_journal = {"id": blocker_id, "previous": previous_blocker,
                               "entry": deepcopy(work["technical_decisions"][blocker_id])}
        questions = artifact.get("questions", [])
        if active["phase"] == "review":
            artifact = deepcopy(artifact)
            artifact["findings"] = finding_updates(work, artifact["findings"], artifact.get("finding_resolutions", []), outcome=artifact["outcome"])
        elif active["phase"] in {"engineering", "docs"}:
            record_finding_resolutions(work, active["phase"], artifact)
        record = {"assignment_id": active["id"], "worker": deepcopy(artifact), "controller": evidence}
        if blocker_journal is not None:
            record["capability_blocker_journal"] = blocker_journal
        diagnostic = active["capsule"]["context"].get("diagnostic_checks")
        if isinstance(diagnostic, dict):
            record["diagnostic_checks"] = deepcopy(diagnostic)
        record["technical_journal_digest"] = journal_digest(work.get("technical_decisions", {}))
        record["semantic_journal_digest"] = semantic_journal_digest(work.get("technical_decisions", {}))
        record["verification_environment"] = command.get("controller_environment")
        record["candidate_binding"] = deepcopy(active["capsule"].get("candidate"))
        if required_ids is not None:
            record["required_identity_ids"] = deepcopy(required_ids)
            record["qa_contract"] = deepcopy(active["capsule"]["context"].get("qa_contract"))
        review_scope = active["capsule"]["context"].get("review_target")
        if active["phase"] in {"review", "qa"} and isinstance(review_scope, dict):
            record["review_target"] = deepcopy(review_scope)
        docs_rework = active["phase"] == "docs" and (
            work["artifacts"].get("docs", {}).get("candidate") == record["candidate_binding"]
            and record["candidate_binding"] is not None
        )
        if active["phase"] == "engineering" or (
            active["phase"] == "docs" and (evidence["changed_paths"] or docs_rework)
        ):
            record["candidate"] = {
                "base_tree_oid": _engineering_candidate_diff_base(work, active),
                "candidate_tree_oid": evidence["candidate_tree_oid"],
                "changed_paths": deepcopy(evidence["changed_paths"]),
                "authority_digest": work["authority"]["digest"],
                "pipeline_runtime_digest": work["pipeline_runtime_digest"],
                "generation": work["generation"] + 1,
            }
            if docs_rework:
                prior_docs = work["artifacts"].get("docs", {})
                record["review_paths"] = sorted(set(
                    prior_docs.get("review_paths", [])
                    + prior_docs.get("candidate", {}).get("changed_paths", [])
                    + evidence["changed_paths"]
                ))
        if failure_capsule is not None:
            record["controller_failure"] = failure_capsule
        if active["phase"] == "docs" and evidence["changed_paths"]:
            pure = set(work.get("execution", {}).get("verification", {}).get("pure_documentation_paths", []))
            original_qa = work["artifacts"].get("qa")
            if (pure and set(evidence["changed_paths"]) <= pure and qa_credit_complete(original_qa)
                    and original_qa.get("candidate_binding") == record["candidate_binding"]
                    and original_qa.get("semantic_journal_digest", original_qa.get("technical_journal_digest")) == record["semantic_journal_digest"]):
                record["reusable_qa"] = deepcopy(original_qa)
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
        elif active["phase"] == "docs" and record.get("candidate") is not None:
            for stale in ("review", "qa", "ready"):
                work["artifacts"].pop(stale, None)
        if (
            active["phase"] in {"review", "qa"}
            and artifact["outcome"] != "blocked"
            and (artifact["outcome"] == "fail" or controller_failure is not None)
        ):
            failed_phase = active["phase"]
            docs_failure = (
                failed_phase == "review"
                and record.get("review_target", {}).get("kind") == "documentation_changes"
            )
            stale_phases = ("qa", "ready") if docs_failure else ("engineering", "review", "qa", "docs", "ready")
            for stale in stale_phases:
                if stale != failed_phase:
                    work["artifacts"].pop(stale, None)
            work["phase"] = "docs" if docs_failure else "engineering"
        work["active_assignment"] = None
        return _record(work, command, active["id"], completed_actor={
            "actor_id": active["worker_id"], "phase": active["phase"],
            "assignment_id": active["id"],
        })

    if name == "answer":
        from .no_progress import no_progress_hold, record_resolution
        hold = no_progress_hold(work)
        if hold is not None or "resolution" in command:
            question_id = record_resolution(work, command)
            return _record(work, command, question_id)
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
        if phase == "qa" and record.get("required_identity_ids") != required_qa_identity_ids(work):
            raise PipelineError("QA evidence does not cover the approved mandatory identities")
        if phase == "slice":
            proposed_slices = slice_records(
                record["worker"].get("slices", work["slices"]), sealed=True,
            )
            # Retained history is automatically readable evidence. Requiring its
            # paths as new writer permissions contradicts an exact approved plan.
            # Every subsequent write still uses that plan's scope; Review keeps
            # retained changes that belong to its current implementation target.
            work["slices"] = proposed_slices
        if phase not in NEXT_PHASE:
            raise PipelineError("ready has no acceptance transition")
        candidate = current_candidate(work)
        review_record = work["artifacts"].get("review", {})
        if (phase == "review" and command.get("controller", {}).get("pure_documentation_qa") is True
                and work["artifacts"].get("docs", {}).get("candidate") == candidate):
            original = work["artifacts"]["docs"].get("reusable_qa")
            if original and original.get("semantic_journal_digest", original.get("technical_journal_digest")) == semantic_journal_digest(work.get("technical_decisions", {})):
                reused = deepcopy(original)
                reused["reused_from"] = {"assignment_id": original["assignment_id"], "candidate_binding": original["candidate_binding"],
                                       "reason": "approved pure-documentation delta; product inputs and verification environment unchanged"}
                reused["candidate_binding"] = deepcopy(candidate)
                reused["controller"]["base_tree_oid"] = candidate["candidate_tree_oid"]
                reused["controller"]["candidate_tree_oid"] = candidate["candidate_tree_oid"]
                reused["controller"]["changed_paths"] = []
                work["artifacts"]["qa"] = reused
                work["phase"] = "ready"
                return _record(work, command, "pure_documentation_verified")
        if phase in {"qa", "docs"} and review_journal_changed(work):
            work["phase"] = "review"
            work["artifacts"].pop("review", None)
        elif phase == "docs" and record.get("candidate") is not None:
            work["phase"] = "review"
        elif (
            phase == "qa" and isinstance(work["artifacts"].get("docs"), dict)
            and work["artifacts"]["docs"].get("worker", {}).get("outcome") == "pass"
            and work["artifacts"]["docs"].get("candidate") == candidate
        ):
            work["phase"] = "ready"
        elif phase == "qa":
            completed_slice = current_slice(work)
            closed_obligations = work.get("execution", {}).get("review_obligations", {}).pop(completed_slice["id"], [])
            closed_review_id = work["artifacts"].get("review", {}).get("assignment_id")
            completed_index = next(
                index for index, item in enumerate(work["slices"])
                if item["id"] == completed_slice["id"]
            )
            if completed_index + 1 < len(work["slices"]):
                work["phase"] = "engineering"
                for stale in ("review", "qa", "docs", "ready"):
                    work["artifacts"].pop(stale, None)
            else:
                no_docs_work = (
                    "docs" not in work["artifacts"]
                    and documentation_not_required_after_qa(work)
                )
                work["phase"] = "ready" if no_docs_work else "docs"
            result = _record(
                work, command,
                "documentation_not_required" if work["phase"] == "ready" else work["phase"],
            )
            if closed_obligations:
                result["history"][-1]["review_obligations_closed"] = {
                    "paths": closed_obligations, "candidate": deepcopy(candidate),
                    "review_assignment_id": closed_review_id,
                    "qa_assignment_id": record["assignment_id"],
                }
            if completed_slice["id"] not in completed_slice_ids(work):
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
            if phase == "docs" and record is None and documentation_not_required_after_qa(work):
                continue
            if not isinstance(record, dict) or record.get("worker", {}).get("outcome") != "pass":
                raise PipelineError(f"ready requires accepted {phase} evidence")
        for phase in ("review", "qa"):
            if work["artifacts"][phase].get("semantic_journal_digest", work["artifacts"][phase].get("technical_journal_digest", journal_digest({}))) != semantic_journal_digest(work.get("technical_decisions", {})):
                raise PipelineError(f"{phase} is stale for the current technical journal")
            if work["artifacts"][phase].get("candidate_binding") != candidate:
                raise PipelineError(f"{phase} is stale for the current candidate")
        if (
            not qa_credit_complete(work["artifacts"]["qa"])
            or work["artifacts"]["qa"].get("required_identity_ids") != required_qa_identity_ids(work)
        ):
            raise PipelineError("ready requires exact mandatory QA result coverage")
        work["artifacts"]["ready"] = {
            "candidate": candidate, "authority_digest": work["authority"]["digest"],
            "controller": deepcopy(controller),
        }
        return _record(work, command, "production_ready_candidate")

    raise AssertionError(name)
