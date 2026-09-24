"""Platform-neutral approved QA methods and complete, assertion-level results.

This validates authority/shape/coverage, never the truth of an observation. The
controller binds the contract and results to authority, candidate and runtime;
workers do not supply those identities or obtain credit by replaying old prose.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any


class QAContractError(ValueError):
    pass


_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")


def _object(value: Any, keys: set[str], label: str, *, optional: set[str] = frozenset()) -> None:
    if not isinstance(value, dict) or not keys <= set(value) or set(value) - keys - optional:
        raise QAContractError(f"{label} requires exactly {', '.join(sorted(keys))}" +
                              (f"; optional {', '.join(sorted(optional))}" if optional else ""))


def _text(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise QAContractError(f"{label} must be a non-empty string")


def _id(value: Any, label: str) -> None:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise QAContractError(f"{label} must be an exact identifier")


def _choice(value: Any, choices: set[str], label: str) -> None:
    if not isinstance(value, str) or value not in choices:
        raise QAContractError(f"{label} must be one of: {', '.join(sorted(choices))}")


def _ids(value: Any, label: str, *, empty: bool = True) -> None:
    if not isinstance(value, list) or (not empty and not value):
        raise QAContractError(f"{label} must be a {'non-empty ' if not empty else ''}list")
    for item in value:
        _id(item, label)
    if len(value) != len(set(value)):
        raise QAContractError(f"{label} contains duplicate identifiers")


def _source(value: Any, label: str, source_paths: set[str] | None) -> None:
    _text(value, label)
    path, separator, anchor = value.partition("#")
    if (not separator or not anchor.strip() or path != path.strip() or "\\" in path
            or path.startswith("/") or ":" in path
            or any(part in {"", ".", ".."} for part in path.split("/"))
            or any(ord(char) < 32 for char in value)):
        raise QAContractError(f"{label} must be an approved repository path#anchor")
    if source_paths is not None and path not in source_paths:
        raise QAContractError(f"{label} does not refer to an approved authority path: {path}")


def contract_digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def validate_contract(
    value: Any, required_by_slice: dict[str, list[str]], *,
    source_paths: set[str] | None = None,
) -> dict[str, Any]:
    """Validate one explicit contract against the exact approved slice inventory.

    ``source_paths`` is the controller's approved PRD/SPEC/PLAN path set. An
    external legacy binding is allowed, but cannot add or remove identities.
    Explicit confirmation does not authorize invented methods or equivalence.
    """
    _object(value, {"schema", "confirm_approved_plan", "slices"}, "QA contract")
    if type(value["schema"]) is not int or value["schema"] != 1:
        raise QAContractError("QA contract schema must be 1")
    if value["confirm_approved_plan"] is not True:
        raise QAContractError("QA contract requires confirm_approved_plan: true")
    if not isinstance(required_by_slice, dict) or not required_by_slice:
        raise QAContractError("QA contract requires the non-empty approved slice inventory")
    if not isinstance(value["slices"], dict) or set(value["slices"]) != set(required_by_slice):
        raise QAContractError("QA contract slices must exactly equal the approved slice inventory")
    for slice_id, expected in required_by_slice.items():
        _id(slice_id, "QA slice ID")
        _ids(expected, f"{slice_id} approved mandatory identities", empty=False)
        _validate_slice(value["slices"][slice_id], expected, slice_id, source_paths)
    return deepcopy(value)


def _validate_slice(value: Any, expected: list[str], label: str, source_paths: set[str] | None) -> None:
    _object(value, {"identities"}, label, optional={"method_definitions"})
    method_definitions = value.get("method_definitions", {})
    if not isinstance(method_definitions, dict):
        raise QAContractError(f"{label} method_definitions must be an object")
    for reference, method in method_definitions.items():
        _id(reference, f"{label} method definition reference")
        _validate_method(method, f"{label} method definition {reference}", source_paths)
    if not isinstance(value["identities"], list):
        raise QAContractError(f"{label} identities must be a list")
    identity_ids: list[str] = []
    assertions: dict[str, dict[str, Any]] = {}
    for identity in value["identities"]:
        _object(identity, {"id", "source", "assertions"}, f"{label} identity")
        _id(identity["id"], f"{label} identity ID")
        identity_ids.append(identity["id"])
        _source(identity["source"], f"{identity['id']} source", source_paths)
        if not isinstance(identity["assertions"], list) or not identity["assertions"]:
            raise QAContractError(f"{identity['id']} assertions must be non-empty")
        for assertion in identity["assertions"]:
            _object(assertion, {"id", "expected", "methods", "applicability", "depends_on"},
                    f"{identity['id']} assertion")
            assertion_id = assertion["id"]
            _id(assertion_id, "QA assertion ID")
            if assertion_id in assertions:
                raise QAContractError(f"{label} repeats assertion ID: {assertion_id}")
            assertions[assertion_id] = assertion
            _text(assertion["expected"], f"{assertion_id} expected")
            _ids(assertion["depends_on"], f"{assertion_id} depends_on")
            applicability = assertion["applicability"]
            _object(applicability, {"kind", "condition", "evidence_types"}, f"{assertion_id} applicability")
            _choice(applicability["kind"], {"always", "conditional"}, f"{assertion_id} applicability kind")
            _text(applicability["condition"], f"{assertion_id} condition")
            _ids(applicability["evidence_types"], f"{assertion_id} applicability evidence_types",
                 empty=applicability["kind"] == "always")
            if applicability["kind"] == "always" and (applicability["condition"] != "always" or applicability["evidence_types"]):
                raise QAContractError(f"{assertion_id} always applicability requires condition always and no applicability evidence types")
            if not isinstance(assertion["methods"], list) or not assertion["methods"]:
                raise QAContractError(f"{assertion_id} requires at least one approved method")
            method_ids: list[str] = []
            for entry in assertion["methods"]:
                method = _resolve_method(entry, method_definitions, assertion_id)
                _validate_method(method, f"{assertion_id} method", source_paths)
                method_ids.append(method["id"])
            if len(method_ids) != len(set(method_ids)):
                raise QAContractError(f"{assertion_id} repeats an approved method ID")
    if len(identity_ids) != len(set(identity_ids)) or set(identity_ids) != set(expected):
        raise QAContractError(f"{label} identities must exactly equal the approved mandatory inventory")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(assertion_id: str) -> None:
        if assertion_id in visiting:
            raise QAContractError(f"{label} assertion dependencies contain a cycle at {assertion_id}")
        if assertion_id in visited:
            return
        visiting.add(assertion_id)
        for dependency in assertions[assertion_id]["depends_on"]:
            if dependency not in assertions:
                raise QAContractError(f"{assertion_id} has unknown dependency: {dependency}")
            visit(dependency)
        visiting.remove(assertion_id)
        visited.add(assertion_id)

    for assertion_id in assertions:
        visit(assertion_id)


def _validate_method(value: Any, label: str, source_paths: set[str] | None) -> None:
    _object(value, {"id", "source", "description", "capabilities", "evidence_types"}, label)
    _id(value["id"], f"{label} ID")
    _source(value["source"], f"{label} source", source_paths)
    _text(value["description"], f"{label} description")
    _ids(value["capabilities"], f"{label} capabilities")
    _ids(value["evidence_types"], f"{label} evidence_types", empty=False)


def _resolve_method(value: Any, definitions: dict[str, Any], label: str) -> Any:
    if isinstance(value, dict) and "ref" in value:
        _object(value, {"ref"}, f"{label} method reference")
        _id(value["ref"], f"{label} method reference")
        if value["ref"] not in definitions:
            raise QAContractError(f"{label} has unknown method reference: {value['ref']}")
        return definitions[value["ref"]]
    return value


def expand_slice_contract(contract_slice: dict[str, Any]) -> dict[str, Any]:
    """Return a detached flat slice for comparison; stored contracts stay compact.

    Definitions are slice-local complete methods, never further references. Their
    registry keys do not replace the approved method IDs used in worker results.
    """
    _object(contract_slice, {"identities"}, "QA slice", optional={"method_definitions"})
    identities = contract_slice["identities"]
    if not isinstance(identities, list) or any(not isinstance(item, dict) or "id" not in item for item in identities):
        raise QAContractError("QA slice identities must be a list of identity objects")
    _validate_slice(contract_slice, [item["id"] for item in identities], "QA slice", None)
    expanded = deepcopy(contract_slice)
    definitions = expanded.pop("method_definitions", {})
    for identity in expanded["identities"]:
        for assertion in identity["assertions"]:
            assertion["methods"] = [deepcopy(_resolve_method(entry, definitions, assertion["id"]))
                                    for entry in assertion["methods"]]
    return expanded


def slice_contract(contract: dict[str, Any], slice_id: str) -> dict[str, Any]:
    try:
        return deepcopy(contract["slices"][slice_id])
    except (KeyError, TypeError) as exc:
        raise QAContractError(f"QA contract lacks the assigned slice: {slice_id}") from exc


def _evidence(value: Any, required: list[str], label: str) -> None:
    if not isinstance(value, list):
        raise QAContractError(f"{label} evidence must be a list")
    types: set[str] = set()
    for item in value:
        _object(item, {"type", "ref", "observation"}, f"{label} evidence item")
        _id(item["type"], f"{label} evidence type")
        _text(item["ref"], f"{label} evidence ref")
        _text(item["observation"], f"{label} observed result")
        types.add(item["type"])
    if not set(required) <= types:
        raise QAContractError(f"{label} evidence lacks required types: {', '.join(sorted(set(required) - types))}")


def validate_results(checks: Any, contract_slice: dict[str, Any], *, outcome: str) -> list[dict[str, Any]]:
    """Require complete terminal results and only approved methods/evidence shapes.

    Every outcome reports every identity/assertion. A missing prerequisite blocks
    its declared dependants only; unrelated runnable assertions still need results.
    Returned evidence remains a worker observation, independently assessed by QA.
    """
    identities = contract_slice["identities"]
    expected = [identity["id"] for identity in identities]
    _validate_slice(contract_slice, expected, "assigned QA contract", None)
    if not isinstance(checks, list):
        raise QAContractError("QA checks must be a list")
    observed: dict[str, dict[str, Any]] = {}
    for check in checks:
        _object(check, {"id", "outcome", "evidence", "assertions"}, "QA check")
        _id(check["id"], "QA identity result ID")
        if check["id"] in observed:
            raise QAContractError(f"QA results repeat identity: {check['id']}")
        observed[check["id"]] = check
        _text(check["evidence"], f"{check['id']} evidence summary")
    if set(observed) != set(expected):
        raise QAContractError("QA results must include every assigned identity exactly once, including fail/blocked")
    result_assertions: dict[str, dict[str, Any]] = {}
    definitions: dict[str, dict[str, Any]] = {}
    for identity in identities:
        check = observed[identity["id"]]
        if not isinstance(check["assertions"], list):
            raise QAContractError(f"{identity['id']} assertion results must be a list")
        actual_ids: list[str] = []
        for result in check["assertions"]:
            _object(result, {"id", "outcome", "method_id", "environment", "evidence"},
                    f"{identity['id']} assertion result", optional={"reason"})
            _id(result["id"], "QA assertion result ID")
            _choice(result["outcome"], {"pass", "fail", "not_run", "not_applicable"},
                    f"{result['id']} outcome")
            actual_ids.append(result["id"])
            result_assertions[result["id"]] = result
        required_ids = [assertion["id"] for assertion in identity["assertions"]]
        if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != set(required_ids):
            raise QAContractError(f"{identity['id']} requires every assigned assertion exactly once")
        definitions.update({assertion["id"]: assertion for assertion in identity["assertions"]})
    for assertion_id, definition in definitions.items():
        result = result_assertions[assertion_id]
        _text(result["environment"], f"{assertion_id} actual environment/capability")
        status = result["outcome"]
        methods = {}
        for entry in definition["methods"]:
            method = _resolve_method(entry, contract_slice.get("method_definitions", {}), assertion_id)
            methods[method["id"]] = method
        if status in {"pass", "fail"}:
            if not isinstance(result["method_id"], str) or result["method_id"] not in methods:
                raise QAContractError(f"{assertion_id} must use an approved method ID")
            _evidence(result["evidence"], methods[result["method_id"]]["evidence_types"], assertion_id)
            if "reason" in result:
                raise QAContractError(f"{assertion_id} executed result cannot contain a not_run reason")
            if any(result_assertions[dependency]["outcome"] not in {"pass", "not_applicable"}
                   for dependency in definition["depends_on"]):
                raise QAContractError(f"{assertion_id} executed result has an unsatisfied approved dependency")
        elif status == "not_applicable":
            applicability = definition["applicability"]
            if applicability["kind"] != "conditional" or result["method_id"] is not None or "reason" in result:
                raise QAContractError(f"{assertion_id} not_applicable requires an approved condition and no method/reason")
            _evidence(result["evidence"], applicability["evidence_types"], assertion_id)
        else:
            if result["method_id"] is not None:
                raise QAContractError(f"{assertion_id} not_run cannot claim an executed method")
            _evidence(result["evidence"], [], assertion_id)
            reason = result.get("reason")
            _object(reason, {"kind", "detail", "refs"}, f"{assertion_id} not_run reason")
            _text(reason["detail"], f"{assertion_id} not_run detail")
            _ids(reason["refs"], f"{assertion_id} not_run references", empty=False)
            if reason["kind"] == "dependency_unsatisfied":
                if any(reference not in definition["depends_on"] or
                       result_assertions[reference]["outcome"] in {"pass", "not_applicable"}
                       for reference in reason["refs"]):
                    raise QAContractError(f"{assertion_id} not_run requires genuinely unsatisfied approved dependencies")
            elif reason["kind"] == "capability_unavailable":
                capabilities = {item for method in methods.values() for item in method["capabilities"]}
                if not set(reason["refs"]) <= capabilities or any(
                    not set(method["capabilities"]) & set(reason["refs"])
                    for method in methods.values()
                ):
                    raise QAContractError(f"{assertion_id} unavailable capabilities must prevent every approved alternative")
            elif reason["kind"] == "authority_unresolved":
                # Stable authority-question identifiers, whose actual content is
                # resolved through the existing controller decision boundary.
                pass
            elif reason["kind"] == "verification_incomplete":
                # A demonstrated gap in the delivered verification is repairable
                # work, not an executed product failure or unavailable capability.
                if set(reason["refs"]) != set(methods):
                    raise QAContractError(
                        f"{assertion_id} verification_incomplete must identify every approved method alternative"
                    )
                _evidence(result["evidence"], ["verification-gap"], assertion_id)
            else:
                raise QAContractError(
                    f"{assertion_id} not_run reason must identify an unavailable capability, dependency, authority or incomplete verification"
                )
    for identity in identities:
        check = observed[identity["id"]]
        statuses = [result["outcome"] for result in check["assertions"]]
        proof_gap = any(
            result["outcome"] == "not_run"
            and result.get("reason", {}).get("kind") == "verification_incomplete"
            for result in check["assertions"]
        )
        derived = "fail" if "fail" in statuses or proof_gap else "not_run" if "not_run" in statuses else "pass"
        if check["outcome"] != derived:
            raise QAContractError(f"{identity['id']} outcome must be {derived} from all its assertions")
    statuses = [check["outcome"] for check in checks]
    derived = "fail" if "fail" in statuses else "blocked" if "not_run" in statuses else "pass"
    if outcome != derived:
        raise QAContractError(f"QA outcome must be {derived} from the complete assigned result set")
    return deepcopy(checks)
