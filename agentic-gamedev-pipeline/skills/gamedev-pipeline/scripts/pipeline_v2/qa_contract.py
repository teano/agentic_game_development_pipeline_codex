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
    def __init__(self, message, *, path=""):
        super().__init__(message)
        self.path = path


def _at(path, action):
    """Attach an exact field pointer while retaining the canonical validator."""
    try:
        return action()
    except QAContractError as exc:
        if not exc.path:
            exc.path = path
        raise


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
    _object(value, {"id", "source", "description", "capabilities", "evidence_types"}, label,
            optional={"producer", "require_assessment"})
    _id(value["id"], f"{label} ID")
    _source(value["source"], f"{label} source", source_paths)
    _text(value["description"], f"{label} description")
    _ids(value["capabilities"], f"{label} capabilities")
    _ids(value["evidence_types"], f"{label} evidence_types", empty=False)
    if "require_assessment" in value and type(value["require_assessment"]) is not bool:
        raise QAContractError(f"{label} require_assessment must be boolean")
    if "producer" in value:
        producer = value["producer"]
        if not isinstance(producer, dict):
            raise QAContractError(f"{label} producer must be an object")
        _choice(producer.get("kind"), {"controller_check", "tool", "manual"}, f"{label} producer kind")
        if producer["kind"] == "controller_check":
            _object(producer, {"kind", "check_ids"}, f"{label} producer")
            _ids(producer["check_ids"], f"{label} producer check_ids", empty=False)
        else:
            _object(producer, {"kind", "channel", "probe_ref"}, f"{label} producer")
            _text(producer["channel"], f"{label} producer channel")
            reference = producer["probe_ref"]
            if not isinstance(reference, str) or not reference.startswith("execution-evidence:"):
                raise QAContractError(f"{label} producer probe_ref must reference durable execution-evidence")
            _id(reference.partition(":")[2], f"{label} producer probe record")


def producer_feasibility(contract_slice: dict[str, Any], recipes: list[dict[str, Any]]) -> dict[str, Any]:
    """Check declared routes, not arbitrary semantic equivalence or availability.

    Canonical machine receipts need exact sealed command producers. A manual or
    tool observation needs no CLI command. Historical undeclared observation
    methods remain readable and explicitly unverified, never 'proved feasible'.
    The imperative boundary separately verifies external probe bytes/bindings.
    """
    definition = expand_slice_contract(contract_slice)
    checks = {item["id"] for item in recipes}
    errors, unverified, probe_groups = [], [], []
    for identity in definition["identities"]:
        for assertion in identity["assertions"]:
            rejected, probes, unknown = [], [], []
            controller_route = False
            for method in assertion["methods"]:
                producer = method.get("producer")
                receipt_required = bool(set(method["evidence_types"]) & {"bound-machine-receipt", "controller-check-receipt"})
                if producer is None:
                    (rejected if receipt_required else unknown).append({"method_id": method["id"],
                        "detail": "No explicit producer is bound to this method; no feasibility credit."})
                elif producer["kind"] == "controller_check":
                    missing = set(producer["check_ids"]) - checks
                    if missing:
                        rejected.append({"method_id": method["id"], "detail": "Producer check IDs are not sealed for this slice: " + ", ".join(sorted(missing))})
                    else:
                        controller_route = True
                elif receipt_required:
                    rejected.append({"method_id": method["id"], "detail": "A controller receipt requires a controller_check producer, not a tool/manual observation."})
                else:
                    probes.append({"method_id": method["id"], **deepcopy(producer)})
            if controller_route:
                continue
            if unknown:
                for row in unknown:
                    if row not in unverified:
                        unverified.append(row)
            elif probes:
                existing = next((group for group in probe_groups if group["alternatives"] == probes), None)
                if existing:
                    existing["assertion_ids"].append(assertion["id"])
                else:
                    probe_groups.append({"assertion_ids": [assertion["id"]], "alternatives": probes})
            else:
                for row in rejected:
                    if row not in errors:
                        errors.append(row)
    return {"status": "incompatible" if errors else "legacy_unverified" if unverified else "declared",
            "errors": errors, "unverified_methods": unverified, "probes": probe_groups,
            "semantic_credit": False, "executed_acceptance_credit": False}


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


def resolve_assertion_selection(contract_slice, assertion_ids=None, *, identity_id=None):
    """Expand one exact identity or preserve one explicit assertion subset."""
    identities = contract_slice["identities"]
    if identity_id is not None:
        if assertion_ids not in (None, []):
            raise QAContractError("identity-id and assertion-id selections are mutually exclusive", path="/identity_id")
        _at("/identity_id", lambda: _id(identity_id, "QA identity selector"))
        matches = [item for item in identities if item["id"] == identity_id]
        if len(matches) != 1:
            raise QAContractError("identity-id must name exactly one approved QA identity", path="/identity_id")
        return [row["id"] for row in matches[0]["assertions"]]
    _at("/assertion_ids", lambda: _ids(assertion_ids, "exact approved assertion IDs", empty=False))
    available = {row["id"] for item in identities for row in item["assertions"]}
    if set(assertion_ids) - available:
        raise QAContractError("selection contains unknown exact approved assertion IDs", path="/assertion_ids")
    return list(assertion_ids)


def selected_contract(contract_slice, assertion_ids):
    """Lossless selected obligations, sharing only byte-equivalent full methods.

    Dependencies retain their exact IDs even when their rows are outside this
    selection. This is a reader projection, not a new independently valid slice.
    """
    _ids(assertion_ids, "selected assertions", empty=False)
    expanded = expand_slice_contract(contract_slice)
    available = {row["id"] for identity in expanded["identities"] for row in identity["assertions"]}
    if set(assertion_ids) - available:
        raise QAContractError("selection contains unknown approved assertion IDs")
    result = {"identities": [], "method_definitions": {}}
    for identity in expanded["identities"]:
        rows = []
        for assertion in identity["assertions"]:
            if assertion["id"] not in assertion_ids:
                continue
            row = deepcopy(assertion)
            row["methods"] = []
            for method in assertion["methods"]:
                key = "method-" + contract_digest(method)
                result["method_definitions"].setdefault(key, deepcopy(method))
                if result["method_definitions"][key] != method:
                    raise QAContractError("selected method digest collision")
                row["methods"].append({"ref": key})
            rows.append(row)
        if rows:
            result["identities"].append({**deepcopy(identity), "assertions": rows})
    return result


def _evidence(value: Any, required: list[str], label: str) -> None:
    if not isinstance(value, list):
        raise QAContractError(f"{label} evidence must be a list", path="/evidence")
    types: set[str] = set()
    for index, item in enumerate(value):
        path = f"/evidence/{index}"
        _at(path, lambda: _object(item, {"type", "ref", "observation"}, f"{label} evidence item", optional={"source"}))
        _at(path + "/type", lambda: _id(item["type"], f"{label} evidence type"))
        _at(path + "/ref", lambda: _text(item["ref"], f"{label} evidence ref"))
        _at(path + "/observation", lambda: _text(item["observation"], f"{label} observed result"))
        if item["ref"].startswith("candidate-source:") and "source" not in item:
            raise QAContractError(f"{label} candidate-source reference requires exact source-reader metadata")
        if "source" in item:
            _at(path + "/source", lambda: source_reference(item["source"]))
            if item["ref"] != source_reference(item["source"]):
                if item["ref"].startswith("execution-evidence:"):
                    raise QAContractError(f"{label} execution-record ref cannot also be a candidate-source reference; "
                                          "preserve both proof origins as separate evidence items", path=path + "/ref")
                raise QAContractError(f"{label} source reference must match its exact source metadata", path=path + "/ref")
        types.add(item["type"])
    if not set(required) <= types:
        raise QAContractError(f"{label} evidence lacks required types: {', '.join(sorted(set(required) - types))}", path="/evidence")


def source_reference(source):
    """Canonical locator using existing source-reader metadata, not a registry."""
    from .model import is_digest, normalize_literal_path
    _object(source, {"path", "sha256"}, "QA source", optional={"start_line", "end_line"})
    if not isinstance(source["path"], str) or normalize_literal_path(source["path"]) != source["path"] or "*" in source["path"]:
        raise QAContractError("QA source requires an exact project-relative path")
    if not is_digest(source["sha256"]):
        raise QAContractError("QA source requires the full original file SHA256")
    if ("start_line" in source) != ("end_line" in source):
        raise QAContractError("QA source span requires both start_line and end_line")
    suffix = ""
    if "start_line" in source:
        if type(source["start_line"]) is not int or type(source["end_line"]) is not int or not 1 <= source["start_line"] <= source["end_line"]:
            raise QAContractError("QA source line span must be positive and ordered")
        suffix = f"#L{source['start_line']}-L{source['end_line']}"
    return f"candidate-source:{source['path']}@{source['sha256']}" + suffix


def resolve_method_id(contract_slice, assertion_id, selector):
    definitions = contract_slice.get("method_definitions", {})
    assertion = next((row for identity in contract_slice["identities"] for row in identity["assertions"] if row["id"] == assertion_id), None)
    if assertion is None:
        raise QAContractError(f"unknown QA assertion: {assertion_id}")
    matches = {method["id"] for entry in assertion["methods"]
               for method in [_resolve_method(entry, definitions, assertion_id)]
               if selector == method["id"] or (isinstance(entry, dict) and entry.get("ref") == selector)}
    if len(matches) != 1:
        raise QAContractError(f"{assertion_id} method selector must identify one approved method")
    return next(iter(matches))


def _validate_repair(result, methods):
    from .model import normalize_literal_path
    repair = result["reason"].get("repair")
    _object(repair, {"owner", "target", "missing_obligation", "attempted_method_ids", "evidence_refs"},
            f"{result['id']} concrete Engineering repair (unfinished QA assessment stays with QA)")
    if repair["owner"] != "engineering":
        raise QAContractError("verification_incomplete requires a concrete Engineering repair; unfinished QA stays pending")
    _text(repair["target"], "repair target")
    if normalize_literal_path(repair["target"]) != repair["target"] or "*" in repair["target"]:
        raise QAContractError("repair target must be one exact project-relative path")
    _text(repair["missing_obligation"], "specific missing test/proof obligation")
    _ids(repair["attempted_method_ids"], "attempted approved methods", empty=False)
    if not set(repair["attempted_method_ids"]) <= set(methods):
        raise QAContractError("repair attempted methods must belong to this assertion")
    refs = repair["evidence_refs"]
    if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) for ref in refs) or len(refs) != len(set(refs)):
        raise QAContractError("repair requires exact concrete evidence_refs")
    available = {item["ref"] for item in result["evidence"] if item["type"] == "verification-gap"
                 and (item["ref"].startswith("execution-evidence:") or "source" in item)}
    if not set(refs) <= available:
        raise QAContractError("repair evidence_refs must name actual bound execution or candidate-source gap evidence, not method IDs")
    if "assessment" not in result:
        raise QAContractError("a repairable verification gap requires the completed QA assessment")


def _validate_assertion_result(result, definition, result_assertions, method_definitions, *, strict_gaps=False):
    assertion_id = definition["id"]
    _at("/environment", lambda: _text(result["environment"], f"{assertion_id} actual environment/capability"))
    status = result["outcome"]
    methods = {}
    for entry in definition["methods"]:
        method = _resolve_method(entry, method_definitions, assertion_id)
        methods[method["id"]] = method
    if status in {"pass", "fail"}:
        if not isinstance(result["method_id"], str) or result["method_id"] not in methods:
            raise QAContractError(f"{assertion_id} must use an approved method ID", path="/method_id")
        _evidence(result["evidence"], methods[result["method_id"]]["evidence_types"], assertion_id)
        if methods[result["method_id"]].get("require_assessment") and "assessment" not in result:
            raise QAContractError(f"{assertion_id} requires an explicit expected/observed assessment")
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
        _at("/reason", lambda: _object(reason, {"kind", "detail", "refs"}, f"{assertion_id} not_run reason", optional={"repair"}))
        if "repair" in reason and reason.get("kind") != "verification_incomplete":
            raise QAContractError("Engineering repair details belong only to verification_incomplete")
        _at("/reason/detail", lambda: _text(reason["detail"], f"{assertion_id} not_run detail"))
        _at("/reason/refs", lambda: _ids(reason["refs"], f"{assertion_id} not_run references", empty=False))
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
            if strict_gaps or "repair" in reason:
                _validate_repair(result, methods)
        elif reason["kind"] == "method_unavailable":
            if set(reason["refs"]) != set(methods):
                raise QAContractError(f"{assertion_id} method_unavailable must identify every approved method alternative")
            _evidence(result["evidence"], ["method-gap"], assertion_id)
        elif reason["kind"] == "external_wait":
            # A pending external action is not a product failure or a waived
            # requirement. Its actor/action/authority remain explicit evidence.
            _evidence(result["evidence"], ["external-prerequisite"], assertion_id)
        else:
            raise QAContractError(
                f"{assertion_id} not_run reason must identify capability, dependency, authority, incomplete verification, unavailable method or external wait"
            )
    if "assessment" in result:
        assessment = result["assessment"]
        _at("/assessment", lambda: _object(assessment, {"expected", "observed", "comparison"}, f"{assertion_id} assessment"))
        if assessment["expected"] != definition["expected"]:
            raise QAContractError(f"{assertion_id} assessment expected must equal the approved assertion", path="/assessment/expected")
        _at("/assessment/observed", lambda: _text(assessment["observed"], f"{assertion_id} actual observation"))
        _at("/assessment/comparison", lambda: _choice(assessment["comparison"], {"matches", "contradicts", "insufficient"}, f"{assertion_id} comparison"))
        if status == "pass" and assessment["comparison"] != "matches":
            raise QAContractError(f"{assertion_id} contradictory or insufficient observation cannot PASS")
        if status == "fail" and assessment["comparison"] != "contradicts":
            raise QAContractError(f"{assertion_id} executed failure requires a contradictory observation")
        if status == "not_run" and assessment["comparison"] != "insufficient":
            raise QAContractError(f"{assertion_id} not_run cannot claim a completed semantic comparison")


def validate_results(checks: Any, contract_slice: dict[str, Any], *, outcome: str, strict_gaps=False) -> list[dict[str, Any]]:
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
                    f"{identity['id']} assertion result", optional={"reason", "assessment"})
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
        _validate_assertion_result(result_assertions[assertion_id], definition, result_assertions,
                                   contract_slice.get("method_definitions", {}), strict_gaps=strict_gaps)
    for identity in identities:
        check = observed[identity["id"]]
        derived = identity_outcome(check["assertions"])
        if check["outcome"] != derived:
            raise QAContractError(f"{identity['id']} outcome must be {derived} from all its assertions")
    derived = terminal_outcome(checks)
    if outcome != derived:
        raise QAContractError(f"QA outcome must be {derived} from the complete assigned result set")
    return deepcopy(checks)


def identity_outcome(assertions):
    statuses = [result["outcome"] for result in assertions]
    repairable = any(result["outcome"] == "not_run" and result.get("reason", {}).get("kind") == "verification_incomplete" for result in assertions)
    return "fail" if "fail" in statuses or repairable else "not_run" if "not_run" in statuses else "pass"


def terminal_outcome(checks):
    statuses = [check["outcome"] for check in checks]
    return "fail" if "fail" in statuses else "blocked" if "not_run" in statuses else "pass"


def result_errors(checks, contract_slice, *, strict_gaps=False):
    """Independent assertion authoring diagnostics using the acceptance validators."""
    definitions = {row["id"]: row for identity in contract_slice["identities"] for row in identity["assertions"]}
    rows = {}
    for check in checks if isinstance(checks, list) else []:
        if isinstance(check, dict) and isinstance(check.get("assertions"), list):
            for row in check["assertions"]:
                if isinstance(row, dict) and isinstance(row.get("id"), str):
                    rows[row["id"]] = row
    errors = []
    for i, check in enumerate(checks if isinstance(checks, list) else []):
        if not isinstance(check, dict) or not isinstance(check.get("assertions"), list):
            continue
        for j, row in enumerate(check["assertions"]):
            path = f"/checks/{i}/assertions/{j}"
            def attempt(action, suffix=""):
                try:
                    action()
                except (ValueError, KeyError, TypeError) as exc:
                    item = {"path": path + (getattr(exc, "path", "") or suffix), "message": str(exc)}
                    if item not in errors:
                        errors.append(item)
            attempt(lambda: _object(row, {"id", "outcome", "method_id", "environment", "evidence"},
                                    path, optional={"reason", "assessment"}))
            if not isinstance(row, dict):
                continue
            attempt(lambda: _evidence(row.get("evidence"), [], path), "/evidence")
            definition = definitions.get(row.get("id")) if isinstance(row.get("id"), str) else None
            if definition is not None:
                attempt(lambda: _validate_assertion_result(row, definition, rows, contract_slice.get("method_definitions", {}), strict_gaps=strict_gaps))
    return errors
