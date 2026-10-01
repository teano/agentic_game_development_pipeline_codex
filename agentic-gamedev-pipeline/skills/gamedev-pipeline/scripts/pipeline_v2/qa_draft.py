"""One incremental QA working artifact; terminal output is its projection.

Missing rows are pending QA assessment, never inferred not_run or test failures.
This module records assessments; it does not execute tests or infer their truth.
"""
from collections import Counter
from copy import deepcopy
from pathlib import Path

from .artifact_io import read_json, write_json
from .model import PipelineError, assignment_output_path, canonical_bytes, qa_contract_context
from .qa_contract import (QAContractError, _object, _choice, _evidence, _at, _validate_assertion_result, expand_slice_contract,
                          identity_outcome, terminal_outcome, resolve_method_id, source_reference, selected_contract,
                          resolve_assertion_selection, _text)
from .technical_decisions import validate_entries


FORMAT = "pipeline-qa-working-v1"


def _decisions(entries):
    try:
        return validate_entries(entries)
    except ValueError as exc:
        raise QAContractError(str(exc), path="/technical_decisions") from exc


def working_path(state, root):
    from .checkout import safe_path
    relative = assignment_output_path(state["active_assignment"], state["feature"])
    return safe_path(root, relative[:-5] + ".working.json", "assigned QA working artifact")


def _context(state, binding):
    active = state.get("active_assignment") or {}
    if active.get("phase") != "qa" or active.get("id") != binding.get("assignment_id"):
        raise PipelineError("incremental assessment requires the exact issued QA assignment")
    contract = qa_contract_context(state)
    if contract["status"] != "bound" or active["capsule"]["context"].get("qa_contract") != contract:
        raise PipelineError("incremental QA requires the unchanged issued acceptance contract")
    return contract["definition"], {**deepcopy(binding), "qa_contract_binding": deepcopy(contract["binding"])}


def load(state, root, binding, *, create=False):
    definition, bound = _context(state, binding)
    path = working_path(state, root)
    exists = path.exists()
    draft = read_json(path) if exists else {"format": FORMAT, "binding": bound, "revision": 0, "assessments": {}}
    if (not isinstance(draft, dict) or set(draft) - {"technical_decisions"} != {"format", "binding", "revision", "assessments"}
            or draft["format"] != FORMAT or draft["binding"] != bound
            or type(draft["revision"]) is not int or draft["revision"] < 0 or not isinstance(draft["assessments"], dict)):
        raise PipelineError("QA working artifact does not match the current assignment/candidate/authority/runtime/contract")
    if "technical_decisions" in draft:
        _decisions(draft["technical_decisions"])
    definitions = {row["id"] for identity in definition["identities"] for row in identity["assertions"]}
    if not set(draft["assessments"]) <= definitions:
        raise PipelineError("QA working artifact contains assertions outside the issued inventory")
    if create and not exists:
        write_json(path, draft)
        exists = True
    return draft, definition, path, exists


def view(draft, definition, path, exists, *, identity_id=None, assertion_id=None):
    if identity_id is not None and assertion_id is not None:
        raise PipelineError("select either identity_id or assertion_id")
    identities = definition["identities"]
    all_ids = [row["id"] for identity in identities for row in identity["assertions"]]
    if identity_id is not None and identity_id not in {i["id"] for i in identities}:
        raise PipelineError("unknown assigned QA identity")
    if assertion_id is not None and assertion_id not in all_ids:
        raise PipelineError("unknown assigned QA assertion")
    rows = draft["assessments"]
    result = {"format": FORMAT, "exists": exists, "working_path": str(path), "binding": deepcopy(draft["binding"]),
              "revision": draft["revision"], "total": len(all_ids), "assessed": len(rows), "pending": len(all_ids) - len(rows),
              "semantic_credit": False, "tests_executed": False,
              "identities": [{"id": identity["id"], "total": len(identity["assertions"]),
                               "assessed": sum(row["id"] in rows for row in identity["assertions"]),
                               "pending": sum(row["id"] not in rows for row in identity["assertions"])} for identity in identities]}
    if "technical_decisions" in draft:
        result["technical_decisions"] = deepcopy(draft["technical_decisions"])
    if identity_id is not None or assertion_id is not None:
        selected = [row["id"] for identity in identities if identity_id is None or identity["id"] == identity_id
                    for row in identity["assertions"] if assertion_id is None or row["id"] == assertion_id]
        result.update(selection={"identity_id": identity_id, "assertion_id": assertion_id}, selection_complete=True,
                      assessments=[deepcopy(rows[key]) for key in selected if key in rows],
                      pending_assertion_ids=[key for key in selected if key not in rows])
    return result


def _normalize(row, definition, contract_slice):
    row = deepcopy(row)
    if not isinstance(row, dict) or not isinstance(row.get("assessment"), dict):
        raise PipelineError("a completed QA row requires actual observed/comparison assessment; unassessed work stays pending")
    row["assessment"].setdefault("expected", definition["expected"])
    if "outcome" not in row:
        comparison = row["assessment"].get("comparison")
        if comparison in {"matches", "contradicts"}:
            row["outcome"] = "pass" if comparison == "matches" else "fail"
        elif comparison == "insufficient" and "reason" in row:
            row["outcome"] = "not_run"
    methods = definition["methods"]
    if row.get("outcome") in {"not_run", "not_applicable"}:
        row.setdefault("method_id", None)
    elif "method_id" not in row and len(methods) == 1:
        row["method_id"] = methods[0]["id"]
    if row.get("method_id") is not None:
        row["method_id"] = _at("/method_id", lambda: resolve_method_id(contract_slice, row["id"], row["method_id"]))
    for index, evidence in enumerate(row.get("evidence", []) if isinstance(row.get("evidence"), list) else []):
        if isinstance(evidence, dict) and "source" in evidence and evidence.get("ref") is None:
            evidence["ref"] = _at(f"/evidence/{index}/source", lambda: source_reference(evidence["source"]))
    # Validate nested evidence before deriving concrete repair references from it.
    _evidence(row.get("evidence"), [], row["id"])
    reason = row.get("reason")
    if isinstance(reason, dict) and reason.get("kind") in {"verification_incomplete", "method_unavailable"}:
        reason.setdefault("refs", [method["id"] for method in methods])
        reason["refs"] = [resolve_method_id(contract_slice, row["id"], ref) for ref in reason["refs"]]
        repair = reason.get("repair")
        if isinstance(repair, dict):
            if isinstance(repair.get("attempted_method_ids"), list):
                repair["attempted_method_ids"] = [resolve_method_id(contract_slice, row["id"], ref) for ref in repair["attempted_method_ids"]]
            repair.setdefault("evidence_refs", [e["ref"] for e in row.get("evidence", []) if e.get("type") == "verification-gap"
                                               and (e.get("ref", "").startswith("execution-evidence:") or "source" in e)])
    return row


def prepare(draft, definition, assertion_ids=None, method_id=None, *, identity_id=None):
    """Editable existing record input, never a selected outcome or observation."""
    assertion_ids = resolve_assertion_selection(definition, assertion_ids, identity_id=identity_id)
    if method_id is not None and (not isinstance(method_id, str) or not method_id):
        raise PipelineError("method_id must explicitly select the approved method for every selected assertion")
    expanded = expand_slice_contract(definition)
    available = {row["id"]: (identity, row) for identity in expanded["identities"] for row in identity["assertions"]}
    prepared, assessments = [], []
    for key in assertion_ids:
        if key not in available:
            raise PipelineError(f"unknown assigned QA assertion: {key}")
        identity, row = available[key]
        saved = draft["assessments"].get(key)
        selector = method_id if method_id is not None else saved.get("method_id") if saved else None
        selected_id = (resolve_method_id(definition, key, selector) if selector is not None else
                       row["methods"][0]["id"] if len(row["methods"]) == 1 else None)
        method = next((item for item in row["methods"] if item["id"] == selected_id), None)
        if saved and saved.get("method_id") not in {None, selected_id}:
            raise PipelineError(f"{key} already records a different method; read its current assessment before explicit reassessment")
        assessments.append(deepcopy(saved) if saved else {
            "id": key, "method_id": selected_id, "environment": None,
            "evidence": [{"type": kind, "ref": None, "observation": None} for kind in (method or {}).get("evidence_types", [])],
            "assessment": {"observed": None, "comparison": None},
        })
        prepared.append({"assertion_id": key, "identity_id": identity["id"],
            "assessment_status": "recorded" if saved else "pending",
            "method_id": selected_id})
    return {"binding": deepcopy(draft["binding"]), "revision": draft["revision"],
            "obligations": selected_contract(definition, assertion_ids),
            "prepared_methods": prepared,
            "record_request": {"binding": deepcopy(draft["binding"]), "expected_revision": draft["revision"], "assessments": assessments},
            "semantic_credit": False, "tests_executed": False,
            "required_action": "Read the complete obligations and all method alternatives in this response. Select an approved method where unselected, follow its producer, and fill actual environment, per-assertion evidence observations and comparison before qa-record. Null fields and prepared metadata are not assessments."}


def compact_prepared_request(request):
    """Remove repeated authoring metadata; never compact a restored assessment."""
    rows = request["assessments"]
    if len(rows) < 2 or any(row["assessment"].get("observed") is not None for row in rows):
        return
    shared = {}
    for field in ("method_id", "environment"):
        if all(row.get(field) == rows[0].get(field) for row in rows) and (field == "environment" or rows[0].get(field) is not None):
            shared[field] = rows[0].get(field)
            for row in rows:
                row.pop(field, None)
    origins = []
    for item in rows[0]["evidence"]:
        if not item.get("ref"):
            continue
        kind = item["type"]
        selected = [[e for e in row["evidence"] if e["type"] == kind] for row in rows]
        origin = {key: deepcopy(item[key]) for key in ("type", "ref", "source") if key in item}
        if all(len(group) == 1 and {key: group[0].get(key) for key in origin} == origin for group in selected):
            origins.append(origin)
            for group in selected:
                group[0].pop("ref", None)
                group[0].pop("source", None)
    if origins:
        shared["evidence"] = origins
    if shared:
        request["shared"] = shared


def controller_check_prerequisite(check_ids, receipts):
    missing = set(check_ids) - {row["id"] for row in receipts}
    return {"status": "check_required" if missing else "receipts_available",
            "pending_check_ids": sorted(missing),
            "detail": "Use the assigned controller check for missing receipts; never run its argv as a worker. Assess the actual assertions, not the aggregate verdict."}


def bind_prepared_receipts(result, contexts):
    """Bind canonical receipt metadata; leave every observation/comparison empty."""
    methods = result["obligations"]["method_definitions"]
    row_methods = {row["id"]: row["methods"] for identity in result["obligations"]["identities"] for row in identity["assertions"]}
    native = {row["id"]: row for context in contexts for row in context.get("receipts", [])}
    for prepared, row in zip(result["prepared_methods"], result["record_request"]["assessments"]):
        method = next((methods[ref["ref"]] for ref in row_methods[row["id"]]
                       if methods[ref["ref"]]["id"] == prepared["method_id"]), {})
        producer = method.get("producer", {})
        if prepared["assessment_status"] == "recorded" or producer.get("kind") != "controller_check":
            continue
        row["evidence"] = [dict(item, ref=native.get(check_id, {}).get("execution_evidence"))
            for item in row["evidence"] for check_id in (
                producer["check_ids"] if item["type"] in {"bound-machine-receipt", "controller-check-receipt"} else [None])]
    compact_prepared_request(result["record_request"])


def _shared_input(draft, request):
    if "binding" in request and request["binding"] != draft["binding"]:
        raise QAContractError("QA request binding differs from the current draft", path="/binding")
    shared = request.get("shared", {})
    if "shared" in request and "binding" not in request:
        raise QAContractError("compact shared input requires the exact prepared draft binding", path="/binding")
    _at("/shared", lambda: _object(shared, set(), "shared QA metadata", optional={"method_id", "environment", "evidence"}))
    for field in ("method_id", "environment"):
        if field in shared:
            _at("/shared/" + field, lambda: _text(shared[field], "shared " + field))
    if "evidence" in shared:
        if not isinstance(shared["evidence"], list):
            raise QAContractError("shared evidence must be a list", path="/shared/evidence")
        for index, item in enumerate(shared["evidence"]):
            def validate_origin():
                _object(item, {"type", "ref"}, "shared evidence origin", optional={"source"})
                _evidence([{**item, "observation": "Metadata shape validation only."}], [], "shared origin")
            try:
                validate_origin()
            except QAContractError as exc:
                suffix = exc.path.removeprefix("/evidence/0")
                exc.path = f"/shared/evidence/{index}" + suffix
                raise
    return shared


def _expand_shared(row, shared, definition):
    row = deepcopy(row)
    if not isinstance(row, dict):
        return row
    for field in ("environment", "method_id"):
        if field not in shared:
            continue
        expected = shared[field]
        if field == "method_id":
            expected = _at("/method_id", lambda: resolve_method_id(definition, row.get("id"), expected))
        assessment = row.get("assessment")
        if field == "method_id" and (row.get("outcome") in {"not_run", "not_applicable"}
                or (isinstance(assessment, dict) and assessment.get("comparison") == "insufficient" and "reason" in row)):
            continue  # A nonexecution assessment never acquires an executed method.
        if field == "method_id":
            if row.get(field) is not None:
                row[field] = _at("/method_id", lambda: resolve_method_id(definition, row.get("id"), row[field]))
        if field in row and row[field] != expected:
            raise QAContractError("explicit row conflicts with shared " + field, path="/" + field)
        row[field] = deepcopy(expected)
    if isinstance(row.get("evidence"), list):
        for index, item in enumerate(row["evidence"]):
            if not isinstance(item, dict):
                continue
            origins = [origin for origin in shared.get("evidence", []) if origin["type"] == item.get("type")]
            explicit = {key: item[key] for key in ("ref", "source") if key in item}
            if not origins:
                continue
            if len(origins) != 1:
                if not explicit:
                    raise QAContractError("ambiguous shared evidence type requires an explicit origin", path=f"/evidence/{index}")
                matches = [{key: origin[key] for key in ("ref", "source") if key in origin} for origin in origins]
                if explicit not in matches:
                    raise QAContractError("explicit evidence origin conflicts with shared origins", path=f"/evidence/{index}")
                continue
            origin = {key: origins[0][key] for key in ("ref", "source") if key in origins[0]}
            if explicit and explicit != origin:
                raise QAContractError("explicit evidence origin conflicts with shared origin; do not combine proof origins", path=f"/evidence/{index}")
            item.update(deepcopy(origin))
    return row


def prepare_update(draft, contract_slice, request):
    _object(request, {"expected_revision", "assessments"}, "QA group record", optional={"technical_decisions", "binding", "shared"})
    shared = _shared_input(draft, request)
    if type(request["expected_revision"]) is not int or request["expected_revision"] < 0:
        raise PipelineError("expected_revision must be a non-negative draft revision")
    decisions = _decisions(request["technical_decisions"]) if "technical_decisions" in request else []
    if not isinstance(request["assessments"], list) or not (request["assessments"] or decisions):
        raise PipelineError("QA group record requires a non-empty assessed group or technical decision update")
    expanded = expand_slice_contract(contract_slice)
    definitions = {row["id"]: row for identity in expanded["identities"] for row in identity["assertions"]}
    changed, errors, positions = {}, [], {}
    for index, row in enumerate(request["assessments"]):
        try:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str) or row["id"] not in definitions:
                raise PipelineError("unknown assigned QA assertion")
            if row["id"] in changed:
                raise PipelineError("group repeats an assertion")
            positions[row["id"]] = index
            changed[row["id"]] = _normalize(_expand_shared(row, shared, contract_slice), definitions[row["id"]], contract_slice)
        except (ValueError, KeyError, TypeError) as exc:
            errors.append({"path": f"/assessments/{index}" + getattr(exc, "path", ""), "message": str(exc)})
    combined = {**draft["assessments"], **changed}
    dependencies = {key: combined.get(key, {"outcome": "pending"}) for key in definitions}
    for key, row in combined.items():
        try:
            _object(row, {"id", "outcome", "method_id", "environment", "evidence", "assessment"}, "completed QA row", optional={"reason"})
            if row["id"] != key:
                raise PipelineError("QA row ID differs from its inventory key")
            _choice(row["outcome"], {"pass", "fail", "not_run", "not_applicable"}, key + " outcome")
            _validate_assertion_result(row, definitions[key], dependencies, {}, strict_gaps=True)
            if row.get("reason", {}).get("kind") == "dependency_unsatisfied" and any(dep not in combined for dep in row["reason"]["refs"]):
                raise PipelineError("pending QA assessment is not a completed dependency verdict")
        except (ValueError, KeyError, TypeError) as exc:
            prefix = f"/assessments/{positions[key]}" if key in positions else f"/stored_assessments/{key}"
            errors.append({"path": prefix + getattr(exc, "path", ""), "message": str(exc)})
    if errors:
        return None, errors, changed
    updated = {**deepcopy(draft), "assessments": combined}
    if "technical_decisions" in request:
        # Like terminal journal consumption, update stable IDs without erasing
        # entries saved by another group. No request grants execution authority.
        retained = {entry["id"]: entry for entry in _decisions(draft.get("technical_decisions", []))}
        retained.update({entry["id"]: entry for entry in decisions})
        updated["technical_decisions"] = list(retained.values())
    identical = updated == draft
    if request["expected_revision"] != draft["revision"] and not (identical and request["expected_revision"] <= draft["revision"]):
        raise PipelineError("stale QA draft revision; read current draft and preserve its assessed groups")
    updated["revision"] = draft["revision"] + (0 if identical else 1)
    return updated, [], changed


def assemble(draft, definition):
    rows = draft["assessments"]
    missing = [row["id"] for identity in definition["identities"] for row in identity["assertions"] if row["id"] not in rows]
    if missing:
        raise PipelineError("QA assessment remains pending; continue the same QA working artifact before terminal assembly")
    checks = []
    for identity in definition["identities"]:
        assertions = [deepcopy(rows[row["id"]]) for row in identity["assertions"]]
        checks.append({"id": identity["id"], "outcome": identity_outcome(assertions),
                       "evidence": "Recorded assertion assessments: " + ", ".join(f"{row['id']}={row['outcome']}" for row in assertions),
                       "assertions": assertions})
    outcome = terminal_outcome(checks)
    artifact = {"outcome": outcome, "checks": checks}
    if "technical_decisions" in draft:
        artifact["technical_decisions"] = _decisions(draft["technical_decisions"])
    if outcome == "blocked":
        outstanding = [row for row in rows.values() if row["outcome"] == "not_run"]
        reasons = Counter(row["reason"]["kind"] for row in outstanding)
        categories = ", ".join(f"{kind}={count}" for kind, count in sorted(reasons.items()))
        artifact["blocker"] = (f"QA has {len(outstanding)} unresolved assertions out of {len(rows)} ({categories}). "
                               "Full reasons and evidence are in checks[].assertions[].")
        artifact["required_action"] = ("Use checks[].assertions[] to resolve each not_run reason according to its "
                                       "recorded evidence and references, then reassess those approved assertions.")
    return artifact


def validate_projection(state, root, binding, artifact):
    if not working_path(state, root).exists():
        return
    draft, definition, _, _ = load(state, root, binding)
    if canonical_bytes(assemble(draft, definition)) != canonical_bytes(artifact):
        raise PipelineError("terminal artifact differs from the current QA working assessments; finalize that draft before submission")
