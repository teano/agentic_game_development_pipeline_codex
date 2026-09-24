"""An unchanged failed attempt needs a new, bound semantic work basis.

This does not judge a repair or resolve Review findings. It only prevents blind
redispatch, and validates the provenance of an explicit specialist resolution.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path


def _pairs(state):
    from .finding_contract import current_record, required_conditions
    record = current_record(state)
    return [{"finding_id": finding, "condition_id": condition}
            for finding, condition in sorted(required_conditions(record, "engineering"))]


def validate_source_identities(packet, sources):
    from .model import PipelineError, is_digest, is_git_oid
    if (not isinstance(sources, list) or len(sources) != len(packet["evidence"])
            or any(not isinstance(source, str) or not (
                source.startswith("git_blob:") and is_git_oid(source.removeprefix("git_blob:"))
                or source.startswith("authority_sha256:") and is_digest(source.removeprefix("authority_sha256:"))) for source in sources)):
        raise PipelineError("no-progress resolution requires controller-owned canonical source identities")


def assessment_identity(packet, sources):
    """Deduplicate substantive fields, never claim to compare their meaning."""
    from .model import digest
    validate_source_identities(packet, sources)
    text = lambda value: value.strip()
    return digest({"affected_conditions": sorted(packet["affected_conditions"], key=lambda pair: (pair["finding_id"], pair["condition_id"])),
                   "answer": text(packet["answer"]),
                   "evidence": sorted({(source, text(row["observation"])) for row, source in zip(packet["evidence"], sources)})})


def no_progress_hold(state):
    """Project a hold from current controller facts, including older states."""
    from .model import current_slice, digest, is_git_oid
    from .checkout import path_identity
    if state.get("phase") != "engineering" or state.get("active_assignment") is not None:
        return None
    record = state.get("artifacts", {}).get("engineering", {})
    worker, controller = record.get("worker", {}), record.get("controller", {})
    identity = record.get("assignment_id")
    if (not identity or identity in {"controller-checkout-baseline", "reconciled-external-baseline"}
            or not (worker.get("outcome") == "fail" or record.get("controller_failure"))
            or worker.get("outcome") == "blocked"
            or not is_git_oid(controller.get("candidate_tree_oid"))
            # This is the assignment-entry tree, not candidate.base_tree_oid,
            # which deliberately remains the cumulative slice diff baseline.
            or controller.get("base_tree_oid") != controller["candidate_tree_oid"]
            or controller.get("authority_digest") != state["authority"]["digest"]
            or controller.get("pipeline_runtime_digest") != state["pipeline_runtime_digest"]):
        return None
    # Existing factual capability recovery already grants one new attempt.
    for event in reversed(state["history"]):
        if (event.get("command") == "recover-capability"
                and event.get("evidence", {}).get("binding", {}).get("assignment_id") == identity
                and event.get("prior_artifacts", {}).get("engineering", {}).get("worker", {}).get("outcome") == "blocked"):
            return None
    from .finding_contract import current_record
    findings = current_record(state)
    pairs = _pairs(state)
    conditions = [{**pair, "text": next(row["text"] for row in findings["open"][pair["finding_id"]]["conditions"]
                                      if row["id"] == pair["condition_id"])} for pair in pairs]
    basis = {"project_root": path_identity(state["project_root"]),
             "candidate_tree_oid": controller["candidate_tree_oid"],
             "authority_digest": state["authority"]["digest"],
             "pipeline_runtime_digest": state["pipeline_runtime_digest"],
             "slice_digest": digest(current_slice(state)), "conditions": conditions}
    binding = {"run_id": state["run_id"], "feature": state["feature"],
               "assignment_id": identity, "work_basis_digest": digest(basis),
               **{key: value for key, value in basis.items() if key != "conditions"}}
    question_id = "no-progress-" + identity
    answered = state.get("questions", {}).get(question_id, {})
    if (answered.get("status") == "answered"
            and answered.get("resolution", {}).get("binding") == binding):
        validate_source_identities(answered["resolution"], answered.get("resolution_sources"))
        return None
    return {"question_id": question_id, "binding": binding, "affected_conditions": pairs,
            "prior_assessments": [deepcopy(question["resolution"]) for question in state["questions"].values()
                                  if question.get("resolution", {}).get("binding", {}).get("work_basis_digest") == binding["work_basis_digest"]],
            "unresolved_work": {
                "findings": [{key: deepcopy(findings["open"][identity][key]) for key in ("id", "text", "kind", "severity")}
                             for identity in sorted({pair["finding_id"] for pair in pairs})],
                "conditions": [{**condition, "independent_result": deepcopy(findings["condition_status"][condition["finding_id"]][condition["condition_id"]])}
                               for condition in conditions],
            },
            "prompt": ("Engineering completed a failed attempt without changing its assignment-entry candidate. "
                       "Explain the exact unresolved cause using a new, evidenced clarification, counterexample, "
                       "or resolved prerequisite before another attempt. An answer grants no acceptance or finding closure."),
            "failure": {"summary": worker.get("summary"),
                        "finding_resolutions": deepcopy(worker.get("finding_resolutions", [])),
                        "controller_failure": deepcopy(record.get("controller_failure"))}}


def resolution_action(state, hold):
    from .model import _action_id
    from .execution import owner_key
    resolver_phase = "review" if hold["affected_conditions"] else "engineering"
    return {"kind": "controller_decision", "route": "controller_decision", "command": "answer",
            "command_id": _action_id(state, "answer"), "expected_generation": state["generation"],
            "question_id": hold["question_id"], "prompt": hold["prompt"],
            "result": "no_progress_resolution_required", "user_input_required": False,
            "resolver_role": "review" if hold["affected_conditions"] else "engineer",
            "resolver_worker_id": state.get("execution", {}).get("owners", {}).get(owner_key(state, resolver_phase)),
            "no_progress_binding": deepcopy(hold["binding"]),
            "affected_conditions": deepcopy(hold["affected_conditions"]),
            "unresolved_work": deepcopy(hold["unresolved_work"]),
            "prior_assessments": deepcopy(hold["prior_assessments"]),
            "failure": deepcopy(hold["failure"]),
            "decision_policy": "Route to the responsible specialist; Director must not decide semantics or waive findings.",
            "resolution_schema": {
                "required_keys": ["binding", "kind", "affected_conditions", "evidence", "answer"],
                "binding": "exact no_progress_binding from this action",
                "kind": "clarification|counterexample|prerequisite",
                "affected_conditions": "exact non-empty subset of listed finding_id/condition_id pairs, or [] when none",
                "evidence": "non-empty [{path, sha256, observation}] of controller-bound current source files supporting the affected conditions",
                "answer": "established fact, residual, next permitted correction, and material difference from or unsupported claim in prior assessments; no new product authority or acceptance",
            }, "recovery": "Use answer --resolution with a workflow-local JSON packet; unchanged retry and --text cannot release this hold."}


def validate_resolution_record(packet):
    """Keep optional persisted question metadata well formed across old states."""
    from .model import PipelineError, is_digest, is_git_oid, normalize_literal_path
    from .checkout import path_identity
    keys = {"binding", "kind", "affected_conditions", "evidence", "answer"}
    binding_keys = {"project_root", "run_id", "feature", "assignment_id", "work_basis_digest", "candidate_tree_oid",
                    "authority_digest", "pipeline_runtime_digest", "slice_digest"}
    if (not isinstance(packet, dict) or set(packet) != keys
            or not isinstance(packet["binding"], dict) or set(packet["binding"]) != binding_keys
            or any(not isinstance(value, str) or not value.strip() for value in packet["binding"].values())
            or any(not is_digest(packet["binding"][key]) for key in ("work_basis_digest", "authority_digest", "pipeline_runtime_digest", "slice_digest"))
            or not is_git_oid(packet["binding"]["candidate_tree_oid"])
            or not isinstance(packet["kind"], str) or packet["kind"] not in {"clarification", "counterexample", "prerequisite"}
            or not isinstance(packet["answer"], str) or not packet["answer"].strip()
            or not isinstance(packet["affected_conditions"], list)
            or any(not isinstance(pair, dict) or set(pair) != {"finding_id", "condition_id"}
                   or any(not isinstance(value, str) or not value.strip() for value in pair.values()) for pair in packet["affected_conditions"])
            or not isinstance(packet["evidence"], list) or not packet["evidence"]
            or any(not isinstance(row, dict) or set(row) != {"path", "sha256", "observation"}
                   or not isinstance(row["path"], str) or normalize_literal_path(row["path"]) != row["path"]
                   or not is_digest(row["sha256"]) or not isinstance(row["observation"], str)
                   or not row["observation"].strip() for row in packet["evidence"])):
        raise PipelineError("no-progress resolution record is malformed")
    root = packet["binding"]["project_root"]
    if not Path(root).is_absolute() or path_identity(root) != root:
        raise PipelineError("no-progress resolution project root must use canonical identity")


def validate_resolution(state, command, *, check_sources=True):
    from .model import PipelineError, _action_id, digest, is_digest, normalize_literal_path
    hold = no_progress_hold(state)
    packet = command.get("resolution")
    validate_resolution_record(packet)
    if (hold is None or command.get("question_id") != hold["question_id"]
            or command.get("id") != _action_id(state, "answer")
            or not isinstance(packet, dict)
            or set(packet) != {"binding", "kind", "affected_conditions", "evidence", "answer"}
            or packet.get("binding") != hold["binding"]
            or packet.get("kind") not in {"clarification", "counterexample", "prerequisite"}
            or not isinstance(packet.get("answer"), str) or not packet["answer"].strip()):
        raise PipelineError("no-progress resolution requires the exact current binding and a concrete specialist answer")
    pairs = packet["affected_conditions"]
    allowed = hold["affected_conditions"]
    if (not isinstance(pairs, list) or any(not isinstance(pair, dict)
            or set(pair) != {"finding_id", "condition_id"} or pair not in allowed for pair in pairs)
            or len({digest(pair) for pair in pairs}) != len(pairs)
            or bool(pairs) != bool(allowed)):
        raise PipelineError("no-progress resolution must identify exact affected unresolved condition pairs")
    evidence = packet["evidence"]
    if (not isinstance(evidence, list) or not evidence
            or any(not isinstance(row, dict) or set(row) != {"path", "sha256", "observation"}
                   or not isinstance(row["path"], str) or normalize_literal_path(row["path"]) != row["path"]
                   or not is_digest(row["sha256"]) or not isinstance(row["observation"], str)
                   or not row["observation"].strip() for row in evidence)):
        raise PipelineError("no-progress resolution needs exact source path, SHA-256 and concrete observation")
    # Same-source, same-condition clarification can be real progress. Mechanical
    # duplicate detection excludes routing/kind/path aliases and outer spacing;
    # the existing specialist assesses whether different prose adds substance.
    if not check_sources:
        return hold
    controller = command.get("controller")
    sources = controller.get("resolution_sources") if isinstance(controller, dict) else None
    previous = {assessment_identity(question["resolution"], question.get("resolution_sources"))
                for question in state["questions"].values()
                if question.get("resolution", {}).get("binding", {}).get("work_basis_digest") == hold["binding"]["work_basis_digest"]}
    if assessment_identity(packet, sources) in previous:
        raise PipelineError("no-progress resolution duplicates a prior assessment; the responsible specialist must diagnose the residual")
    return hold


def verify_resolution_sources(state, root, command):
    """I/O shell validation; unowned files and controller bookkeeping are not evidence."""
    from .checkout import _git, file_sha256, matches, path_identity, safe_path
    from .model import PipelineError, default_assignment
    validate_resolution(state, command, check_sources=False)
    rules = default_assignment(state)["access"]["read"]
    sources = []
    for row in command["resolution"]["evidence"]:
        path = row["path"]
        sealed_authority = any(path_identity(path) == path_identity(item["path"]) and row["sha256"] == item["sha256"]
                               for item in state["authority"]["items"].values())
        # Reports/receipts and their nonce wrappers are not a new work basis.
        # The resolution itself carries the specialist's clarification, citing
        # actual source bytes already bound by the current candidate/authority.
        if not sealed_authority and any(part.casefold() in {".git", ".agentic-pipeline", ".agentic-pipeline-v2"} for part in path.split("/")):
            raise PipelineError("no-progress resolution requires candidate-bound source, not workflow reports or controller bookkeeping")
        if not any(matches(path, rule) for rule in rules):
            raise PipelineError("no-progress resolution source is outside the assigned read boundary")
        source = safe_path(Path(root), path, "no-progress resolution evidence", strict=True)
        if not source.is_file() or file_sha256(source) != row["sha256"]:
            raise PipelineError("no-progress resolution source version changed; refresh the factual evidence")
        tree = command["resolution"]["binding"]["candidate_tree_oid"]
        entry = _git(Path(root), ["--literal-pathspecs", "ls-tree", "-z", tree, "--", path], label="no-progress source binding")
        rows = [item.split(b"\t", 1)[0].split() for item in entry.split(b"\0") if item]
        if len(rows) == 1 and len(rows[0]) == 3 and rows[0][1] == b"blob":
            sources.append("git_blob:" + rows[0][2].decode("ascii"))
        elif not rows and sealed_authority:
            sources.append("authority_sha256:" + row["sha256"])
        else:
            raise PipelineError("no-progress resolution requires a source file in the controller-bound candidate")
    validate_source_identities(command["resolution"], sources)
    return sources


def record_resolution(state, command):
    hold = validate_resolution(state, command)
    packet = deepcopy(command["resolution"])
    state["questions"][hold["question_id"]] = {
        "status": "answered", "phase": "engineering", "prompt": hold["prompt"],
        "answer": packet["answer"].strip(), "resolution": packet,
        "resolution_sources": deepcopy(command["controller"]["resolution_sources"]),
    }
    return hold["question_id"]
