"""Explicit Review conditions and independent, lossless rework closure.

This checks coverage and identity, not the truth of prose evidence. Historical
findings become one full-text condition; arbitrary prose is never auto-split.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json


def _error(message):
    from .model import PipelineError
    raise PipelineError(message)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def validate_findings(findings, *, require_conditions=True):
    """Validate shape; return canonical copies with stable generated IDs."""
    if not isinstance(findings, list):
        _error("Review findings must be a list")
    result, used = [], set()
    for finding in findings:
        if (not isinstance(finding, dict)
                or not {"text", "severity", "kind"} <= set(finding)
                or set(finding) - {"id", "text", "severity", "kind", "conditions"}
                or any(not _text(finding.get(key)) for key in ("text", "severity", "kind"))
                or ("id" in finding and not _text(finding["id"]))):
            _error("Review findings require text, severity, kind, optional id, and explicit conditions")
        item = deepcopy(finding)
        if "conditions" not in item:
            if require_conditions:
                _error("new Review findings require explicit conditions; use one full-text condition for a simple finding")
            item["conditions"] = [{"id": "C1", "text": item["text"]}]
        conditions = item["conditions"]
        if (not isinstance(conditions, list) or not conditions
                or any(not isinstance(row, dict) or set(row) != {"id", "text"}
                       or not _text(row.get("id")) or not _text(row.get("text")) for row in conditions)
                or len({row["id"] for row in conditions}) != len(conditions)):
            _error("finding conditions require unique non-empty id and text rows")
        generated = "id" not in item
        if generated:
            raw = json.dumps(finding, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
            item["id"] = "F-" + hashlib.sha256(raw).hexdigest()[:16]
        base, suffix = item["id"], 2
        while item["id"] in used:
            if not generated:
                _error("duplicate Review finding ID; assign a distinct ID to each operative finding")
            item["id"] = f"{base}-{suffix}"
            suffix += 1
        used.add(item["id"])
        result.append(item)
    return result


def validate_resolutions(values, phase):
    """Validate explicit claims; only Review can independently resolve."""
    allowed = {"resolved", "unresolved"} if phase == "review" else {"addressed", "unresolved"}
    if not isinstance(values, list):
        _error("finding_resolutions must be a list")
    used = set()
    for row in values:
        if (not isinstance(row, dict)
                or set(row) != {"finding_id", "condition_id", "status", "evidence"}
                or any(not _text(row.get(key)) for key in ("finding_id", "condition_id", "evidence"))
                or not _text(row.get("status")) or row["status"] not in allowed):
            _error(f"{phase} finding_resolutions require finding_id, condition_id, status {sorted(allowed)}, and evidence")
        key = (row["finding_id"], row["condition_id"])
        if key in used:
            _error("duplicate finding condition resolution")
        used.add(key)
    return deepcopy(values)


def normalized_record(previous):
    """Upgrade only the existing findings metadata, without granting closure."""
    record = deepcopy(previous or {"open": {}, "resolved": [], "repeat_count": 0})
    retained = record.setdefault("retained", {})
    statuses = record.setdefault("condition_status", {})
    for identity, item in list(record.get("open", {}).items()):
        canonical = validate_findings([{**item, "id": identity}], require_conditions=False)[0]
        record["open"][identity] = canonical
        retained.setdefault(identity, deepcopy(canonical))
        per_condition = statuses.setdefault(identity, {})
        for condition in canonical["conditions"]:
            per_condition.setdefault(condition["id"], {"status": "unresolved", "evidence": "Original Review condition remains open."})
    return record


def current_record(state):
    from .execution import owner_key
    return normalized_record(state.get("execution", {}).get("findings", {}).get(owner_key(state, "review")))


def required_conditions(record, phase):
    """Review reaffirms all conditions of open findings; repair maps open ones."""
    result = set()
    for identity, finding in record["open"].items():
        statuses = record["condition_status"][identity]
        for condition in finding["conditions"]:
            if phase == "review" or statuses[condition["id"]]["status"] != "resolved":
                result.add((identity, condition["id"]))
    return result


def required_condition_roster(record, phase):
    """Locate exact assigned pairs in existing convergence; never copy their text."""
    record = normalized_record(record)
    required = required_conditions(record, phase)
    result = []

    def escaped(value):
        return value.replace("~", "~0").replace("/", "~1")

    for finding_id in sorted(record["open"]):
        for index, condition in enumerate(record["open"][finding_id]["conditions"]):
            condition_id = condition["id"]
            if (finding_id, condition_id) in required:
                result.append({
                    "finding_id": finding_id, "condition_id": condition_id,
                    "original_condition_pointer": f"/assignment/context/convergence/open/{escaped(finding_id)}/conditions/{index}",
                    "latest_independent_result_pointer": f"/assignment/context/convergence/condition_status/{escaped(finding_id)}/{escaped(condition_id)}",
                })
    return result


def _coverage(record, phase, resolutions):
    expected = required_conditions(record, phase)
    actual = {(row["finding_id"], row["condition_id"]) for row in resolutions}
    if actual != expected:
        missing, extra = sorted(expected - actual), sorted(actual - expected)
        _error(f"{phase} finding_resolutions must cover the exact assigned conditions; missing={missing}, unexpected={extra}")


def prepare_review_update(previous, findings, resolutions=None, *, outcome=None, require_conditions=False):
    """Pure transition. Absence from the new finding list never closes an ID."""
    record = normalized_record(previous)
    before = {identity: {key: row["status"] for key, row in record["condition_status"][identity].items()}
              for identity in record["open"]}
    incoming = validate_findings(findings, require_conditions=require_conditions)
    rows = validate_resolutions([] if resolutions is None else resolutions, "review")
    if outcome is not None or resolutions is not None:
        _coverage(record, "review", rows)
    for row in rows:
        record["condition_status"][row["finding_id"]][row["condition_id"]] = {
            "status": row["status"], "evidence": row["evidence"]}
    for item in incoming:
        identity = item["id"]
        previous_item = record["retained"].get(identity)
        if previous_item:
            old = {row["id"]: row["text"] for row in previous_item["conditions"]}
            new = {row["id"]: row["text"] for row in item["conditions"]}
            if any(new.get(key) != text for key, text in old.items()):
                _error("a repeated finding must retain every original condition ID and text; report condition results in finding_resolutions")
        was_closed = identity in record.get("resolved", []) and identity not in record["open"]
        record["retained"][identity] = deepcopy(item)
        statuses = record["condition_status"].setdefault(identity, {})
        for condition in item["conditions"]:
            if was_closed or condition["id"] not in statuses:
                statuses[condition["id"]] = {"status": "unresolved", "evidence": item["text"]}
    current = {identity: deepcopy(item) for identity, item in record["retained"].items()
               if any(row["status"] != "resolved" for row in record["condition_status"].get(identity, {}).values())}
    if outcome == "pass" and current:
        _error("Review pass cannot leave any unresolved finding condition")
    if outcome == "fail" and not current:
        _error("failed Review requires a new finding or an unresolved original condition")
    record["open"] = current
    record["resolved"] = list(dict.fromkeys(record.get("resolved", [])
        + sorted(set(record["retained"]) - set(current))))
    record["resolved"] = [identity for identity in record["resolved"] if identity not in current]
    after = {identity: {key: row["status"] for key, row in record["condition_status"][identity].items()} for identity in current}
    record["repeat_count"] = record.get("repeat_count", 0) + 1 if current and before == after else 0
    record.pop("engineering_resolutions", None)
    return record


def validate_artifact(state, phase, artifact):
    """Context validation before controller checks or any acceptance mutation."""
    if phase not in {"engineering", "docs", "review"}:
        return
    record = current_record(state)
    rows = validate_resolutions(artifact.get("finding_resolutions", []), phase)
    if phase == "review":
        context = (state.get("active_assignment") or {}).get("capsule", {}).get("context", {})
        prepare_review_update(record, artifact["findings"], rows, outcome=artifact["outcome"],
                              require_conditions=context.get("acceptance_contract_version") == 1)
    else:
        _coverage(record, phase, rows)
        if artifact["outcome"] == "pass" and any(row["status"] != "addressed" for row in rows):
            _error(f"{phase} pass requires an addressed change/proof for every unresolved finding condition")


def record_repair_claims(state, phase, artifact):
    """Keep Engineer/Docs evidence for Review without resolving any condition."""
    from .execution import metadata, owner_key
    validate_artifact(state, phase, artifact)
    if phase in {"engineering", "docs"}:
        key = owner_key(state, "review")
        if key in metadata(state)["findings"]:
            metadata(state)["findings"][key]["engineering_resolutions"] = deepcopy(artifact.get("finding_resolutions", []))
