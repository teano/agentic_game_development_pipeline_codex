"""Small execution metadata carried by the existing controller state.

Receipts are evidence, never semantic acceptance. Legacy states have no metadata
and conservatively execute their commands without reuse.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def metadata(state):
    return state.setdefault("execution", {"version": 1, "owners": {}, "receipts": {},
                                           "read_admissions": {}, "findings": {}})


def owner_key(state, phase=None):
    from .model import current_slice
    return f"{state['authority']['digest']}:{current_slice(state)['id']}:{phase or state['phase']}"


def validate_metadata(value, *, error_type=None, digest_validator=None):
    if error_type is None or digest_validator is None:
        from .model import PipelineError, is_digest
        error_type, digest_validator = PipelineError, is_digest
    PipelineError, is_digest = error_type, digest_validator
    required = {"version", "owners", "receipts", "read_admissions", "findings"}
    optional = {"verification", "rotation", "reconciled_tree", "review_obligations", "qa_contract", "qa_contract_binding"}
    if (not isinstance(value, dict) or not required <= set(value)
            or set(value) - required - optional or value["version"] != 1):
        raise PipelineError("execution metadata must use version 1")
    for key in required - {"version"}:
        if not isinstance(value[key], dict):
            raise PipelineError(f"execution {key} must be an object")
    if ("qa_contract" in value) != ("qa_contract_binding" in value):
        raise PipelineError("QA contract and binding must be present together")
    if "qa_contract" in value:
        binding = value["qa_contract_binding"]
        if (not isinstance(value["qa_contract"], dict) or not isinstance(binding, dict)
                or set(binding) != {"authority_digest", "contract_digest"}
                or any(not is_digest(binding[key]) for key in binding)
                or binding["contract_digest"] != _digest(value["qa_contract"])):
            raise PipelineError("QA contract binding must contain valid authority and exact contract digests")
    for key, receipt in value["receipts"].items():
        if (not is_digest(key) or not isinstance(receipt, dict)
                or receipt.get("binding") != key or not isinstance(receipt.get("result"), dict)
                or receipt["result"].get("returncode") != 0):
            raise PipelineError("execution receipt must be bound successful controller evidence")


def seal_verification(value, slices):
    from .model import PipelineError, normalize_literal_path
    if not isinstance(value, dict) or set(value) != {"version", "slices", "pure_documentation_paths", "confirm_approved_plan"}:
        raise PipelineError("verification requires version, slices, pure_documentation_paths, confirm_approved_plan")
    if value["version"] != 1 or type(value["confirm_approved_plan"]) is not bool or not isinstance(value["slices"], dict):
        raise PipelineError("invalid verification manifest version or confirmation")
    if set(value["slices"]) != {item["id"] for item in slices}:
        raise PipelineError("verification recipes must cover exactly the approved slices")
    for selected in slices:
        recipes = value["slices"][selected["id"]]
        if not isinstance(recipes, list) or [r.get("argv") for r in recipes if isinstance(r, dict)] != selected["planned_commands"]:
            raise PipelineError("verification argv must exactly match the sealed planned command order")
        ids = set()
        argv_semantics = {}
        for recipe in recipes:
            if (not isinstance(recipe, dict) or not {"id", "argv", "kind", "timeout_seconds", "independent"} <= set(recipe)
                    or set(recipe) - {"id", "argv", "kind", "timeout_seconds", "independent", "input_paths"}
                    or not isinstance(recipe["id"], str) or not recipe["id"].strip() or recipe["id"] in ids
                    or recipe["kind"] not in {"deterministic", "environment"}
                    or type(recipe["timeout_seconds"]) not in {int, float}
                    or not 0 < recipe["timeout_seconds"] <= 86400
                    or type(recipe["independent"]) is not bool):
                raise PipelineError("malformed verification recipe")
            ids.add(recipe["id"])
            argv_key = _digest(recipe["argv"])
            semantics = {key: value for key, value in recipe.items() if key != "id"}
            if argv_key in argv_semantics and argv_semantics[argv_key] != semantics:
                raise PipelineError("duplicate verification argv cannot have different execution semantics")
            argv_semantics[argv_key] = semantics
            if "input_paths" in recipe:
                paths = recipe["input_paths"]
                if (not isinstance(paths, list) or any(not isinstance(path, str) or not path or "*" in path for path in paths)
                        or len(paths) != len(set(paths))):
                    raise PipelineError("recipe input_paths must declare exact extra dependency files, without wildcards or duplicates")
                for path in paths:
                    if not Path(path).is_absolute() and normalize_literal_path(path) != path:
                        raise PipelineError("recipe input path is not canonical")
    paths = value["pure_documentation_paths"]
    if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths) or len(paths) != len(set(paths)):
        raise PipelineError("pure documentation paths must be duplicate-free exact paths")
    for path in paths:
        if normalize_literal_path(path) != path or "*" in path:
            raise PipelineError("pure documentation paths must be exact project-relative paths")
    return deepcopy(value)


def recipe_for(state, argv, index, default_timeout):
    from .model import current_slice
    selected = current_slice(state)
    recipes = state.get("execution", {}).get("verification", {}).get("slices", {}).get(selected["id"], [])
    matches = [recipe for recipe in recipes if recipe["argv"] == argv]
    occurrence = sum(previous == argv for previous in selected["planned_commands"][:index])
    if occurrence < len(matches):
        return matches[occurrence]
    return {"id": f"command-{index + 1}", "argv": argv, "kind": "environment",
            "timeout_seconds": default_timeout, "independent": False}


def dependency_binding(state, recipe):
    """Hash declared literal dependencies; no implicit inventory or hermetic claim.

An absent declaration means unknown input closure and disables reuse. An empty
list explicitly asserts that only candidate/executable/environment are read;
the recipe owner and independent reviewer must substantiate that assertion.
"""
    from .checkout import file_sha256, safe_path
    if "input_paths" not in recipe:
        return None
    result = []
    for supplied in recipe["input_paths"]:
        path = Path(supplied)
        if not path.is_absolute():
            path = safe_path(Path(state["project_root"]), supplied, "declared check dependency", strict=False)
        if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
            return None
        try:
            result.append([str(path.resolve()), file_sha256(path)])
        except (OSError, ValueError):
            return None
    return _digest(result)


def receipt_binding(state, tree, recipe, environment):
    """Conservative input closure: full candidate, executable bytes, all env.

Only an explicitly deterministic recipe is reusable. No environment value is
persisted, and a missing executable never receives a reusable identity.
"""
    from .checkout import file_sha256
    executable = shutil.which(recipe["argv"][0])
    dependencies = dependency_binding(state, recipe)
    if recipe["kind"] != "deterministic" or executable is None or dependencies is None:
        return None
    try:
        executable_hash = file_sha256(Path(executable))
    except OSError:
        return None
    return _digest({"candidate": tree, "authority": state["authority"]["digest"],
                    "runtime": state["pipeline_runtime_digest"], "recipe": recipe,
                    "executable": os.path.normcase(str(Path(executable).resolve())),
                    "executable_sha256": executable_hash, "environment": _digest(environment), "dependencies": dependencies})


def execution_environment():
    """Use the same effective environment for execution and receipt eligibility."""
    environment = os.environ.copy()
    environment["NODE_DISABLE_COMPILE_CACHE"] = "1"
    environment.pop("NODE_COMPILE_CACHE", None)
    return environment


def machine_check_row(result, locator, receipt_id):
    return {"id": result["check_id"], "outcome": "pass" if result["returncode"] == 0 else "fail",
            "source_locator": locator, "receipt_id": receipt_id, "receipt_sha256": _digest(result),
            "returncode": result["returncode"], "stdout_sha256": result["stdout_sha256"],
            "stderr_sha256": result["stderr_sha256"]}


def machine_check_inputs(state, tree, environment, default_timeout=600):
    """Project currently applicable canonical receipts without executing a check.

    Review and QA share the same conservative receipt eligibility; source locators
    identify provenance and never grant access to controller state.
    """
    from .model import current_slice
    rows, pending = [], []
    for index, argv in enumerate(current_slice(state)["planned_commands"]):
        recipe = recipe_for(state, argv, index, default_timeout)
        binding = receipt_binding(state, tree, recipe, environment)
        receipt = state.get("execution", {}).get("receipts", {}).get(binding)
        if receipt is None:
            pending.append(recipe["id"])
        else:
            locator = f"{state['workflow_path']}/pipeline-state.json#/execution/receipts/{binding}"
            rows.append(machine_check_row(receipt["result"], locator, receipt["id"]))
    return {"candidate_tree_oid": tree, "authority_digest": state["authority"]["digest"],
            "pipeline_runtime_digest": state["pipeline_runtime_digest"], "checks": rows,
            "pending_check_ids": pending, "grants_manual_acceptance": False,
            "grants_semantic_credit": False}


def verification_environment(commands, environment, *, state=None):
    from .checkout import file_sha256
    tools = []
    dependencies = []
    for index, argv in enumerate(commands):
        if state is None:
            return None
        recipe = recipe_for(state, argv, index, 600)
        bound = dependency_binding(state, recipe)
        if bound is None or recipe["kind"] != "deterministic":
            return None
        dependencies.append(bound)
        executable = shutil.which(argv[0])
        if executable is None:
            return None
        try:
            tools.append([str(Path(executable).resolve()), file_sha256(Path(executable))])
        except OSError:
            return None
    return _digest([tools, dependencies, environment])


def finding_updates(state, findings, resolutions=None, *, outcome=None):
    """Apply independent per-condition Review results without implicit closure."""
    from .model import current_slice
    from .finding_contract import prepare_review_update
    store = metadata(state)["findings"]
    key = owner_key(state, "review")
    updated = prepare_review_update(store.get(key), findings, resolutions, outcome=outcome)
    updated["slice_id"] = current_slice(state)["id"]
    store[key] = updated
    return list(deepcopy(updated["open"]).values())


def record_finding_resolutions(state, phase, artifact):
    from .finding_contract import record_repair_claims
    record_repair_claims(state, phase, artifact)


def convergence_context(state):
    from .finding_contract import normalized_record
    value = state.get("execution", {}).get("findings", {}).get(owner_key(state, "review"))
    if not value:
        return None
    value = normalized_record(value)
    # Retain closed originals in state; deliver current originals only once.
    value.pop("retained", None)
    value["condition_status"] = {key: rows for key, rows in value["condition_status"].items() if key in value["open"]}
    return {**value, "requires_cause_analysis": value["repeat_count"] >= 2}


def classify_error(error):
    """Public error taxonomy; never retries product/authority failures silently."""
    text = str(error)
    lower = text.lower()
    if getattr(error, "worker_artifact_validation", False):
        return {"error": text, "category": "artifact_format", "retryable": False,
                "required_action": "Correct only the same owned output artifact truthfully and resubmit."}
    if "no-progress" in lower:
        return {"error": text, "category": "no_progress", "retryable": False,
                "required_action": "Read current status and route the bound resolution to the responsible specialist; do not redispatch unchanged work."}
    rules = [
        (("stale", "generation", "already used", "lock is busy"), "stale_action", True, "Read current status; replay the original identity after an uncertain response."),
        (("runtime changed", "manifest file", "controller evidence", "proof"), "runtime_incident", False, "Stop product work and use separately authorized runtime maintenance."),
        (("authority", "scope", "forbidden paths", "checkout drift", "policy"), "authority_or_scope", False, "Use the bound technical, reconcile, or owning upstream authority route."),
        (("capability", "unavailable", "cannot launch", "containment", "executable"), "capability", False, "Establish a permitted capability alternative or the exact missing prerequisite."),
    ]
    for words, category, retryable, action in rules:
        if any(word in lower for word in words):
            return {"error": text, "category": category, "retryable": retryable, "required_action": action}
    return {"error": text, "category": "invalid_request", "retryable": False,
            "required_action": "Inspect the command help and the current issued contract."}
