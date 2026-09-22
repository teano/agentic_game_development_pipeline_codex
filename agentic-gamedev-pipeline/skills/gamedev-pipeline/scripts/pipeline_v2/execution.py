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
    optional = {"verification", "rotation", "reconciled_tree", "review_obligations"}
    if (not isinstance(value, dict) or not required <= set(value)
            or set(value) - required - optional or value["version"] != 1):
        raise PipelineError("execution metadata must use version 1")
    for key in required - {"version"}:
        if not isinstance(value[key], dict):
            raise PipelineError(f"execution {key} must be an object")
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


def finding_updates(state, findings):
    """Stable identities, explicit resolution, and a bounded no-progress signal."""
    from .model import current_slice
    store = metadata(state)["findings"]
    key = owner_key(state, "review")
    previous = store.get(key, {"open": {}, "resolved": [], "repeat_count": 0})
    current = {}
    for finding in findings:
        item = deepcopy(finding)
        generated = "id" not in item
        base = item.setdefault("id", "F-" + _digest({k: v for k, v in item.items() if k != "id"})[:16])
        identity = base
        suffix = 2
        while identity in current:
            if not generated:
                from .model import PipelineError
                raise PipelineError("duplicate Review finding ID; assign a distinct ID to each operative finding")
            identity = f"{base}-{suffix}"
            suffix += 1
        item["id"] = identity
        current[identity] = item
    resolved = list(dict.fromkeys(previous.get("resolved", []) + sorted(set(previous["open"]) - set(current))))
    same = bool(current) and current == previous["open"]
    store[key] = {"slice_id": current_slice(state)["id"], "open": current, "resolved": resolved,
                  "repeat_count": previous.get("repeat_count", 0) + 1 if same else 0}
    return list(current.values())


def convergence_context(state):
    value = state.get("execution", {}).get("findings", {}).get(owner_key(state, "review"))
    if not value:
        return None
    return {**deepcopy(value), "requires_cause_analysis": value["repeat_count"] >= 2}


def classify_error(error):
    """Public error taxonomy; never retries product/authority failures silently."""
    text = str(error)
    lower = text.lower()
    if getattr(error, "worker_artifact_validation", False):
        return {"error": text, "category": "artifact_format", "retryable": False,
                "required_action": "Correct only the same owned output artifact truthfully and resubmit."}
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
