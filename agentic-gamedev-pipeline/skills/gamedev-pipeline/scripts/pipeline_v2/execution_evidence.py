"""Durable raw execution records, outside the checked candidate.

External capture preserves caller-supplied bytes and explicit provenance; it is
not a controller attestation that a remote tool ran, nor an acceptance verdict.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any

from .artifact_io import contained_path, read_json, write_bytes_immutable, write_json
from .model import PipelineError, canonical_bytes, digest, safe_identifier, workflow_relative_path


PREFIX = "execution-evidence:"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _field_error(path, message):
    error = PipelineError(message)
    error.path = path
    return error


def _directory(root, feature, record_id):
    safe_identifier(record_id, "execution record id")
    directory = Path(root) / workflow_relative_path(feature) / "Evidence"
    return contained_path(directory, directory / record_id)


def input_snapshot(root: Path, paths: list[str], *, missing_ok=False) -> list[dict[str, Any]]:
    if not isinstance(paths, list) or any(not isinstance(p, str) or not p.strip() for p in paths) or len(paths) != len(set(paths)):
        raise _field_error("/input_paths", "evidence input_paths must be unique exact file paths")
    result = []
    for index, name in enumerate(paths):
        path = Path(name)
        if not path.is_absolute():
            path = Path(root) / path
        try:
            raw = path.read_bytes()
        except OSError as exc:
            if missing_ok:
                result.append({"path": str(path.resolve()), "unavailable": str(exc)})
                continue
            raise _field_error(f"/input_paths/{index}", f"cannot capture declared execution input {name} (resolved {path}): {exc}") from exc
        result.append({"path": str(path.resolve()), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
    return result


def begin(root: Path, feature: str, request: dict[str, Any], binding: dict[str, Any]) -> dict[str, Any]:
    required = {"record_id", "invocation", "environment", "input_paths"}
    optional = {"preflight", "project_root", "feature", "authority_paths", "assignment_id"}
    if not isinstance(request, dict):
        raise _field_error("", "evidence request must be an object")
    missing, unexpected = sorted(required - request.keys()), sorted(request.keys() - required - optional)
    if missing or unexpected:
        key = (missing or unexpected)[0]
        raise _field_error("/" + key, f"evidence request missing fields: {missing}; unexpected fields: {unexpected}")
    for key in ("invocation", "environment"):
        if not isinstance(request[key], dict) or not request[key]:
            raise _field_error("/" + key, f"evidence {key} must describe the actual {key}")
    directory = _directory(root, feature, request["record_id"])
    payload = {"schema": 1, "record_id": request["record_id"], "binding": deepcopy(binding),
               "invocation": deepcopy(request["invocation"]), "environment": deepcopy(request["environment"]),
               "input_paths": deepcopy(request["input_paths"]), "inputs": input_snapshot(root, request["input_paths"])}
    path = directory / "request.json"
    if path.exists():
        previous = read_json(path)
        if {k: v for k, v in previous.items() if k != "started_at"} != payload:
            raise PipelineError("execution record id already binds a different invocation or input state")
    else:
        payload["started_at"] = _now()
        write_json(path, payload)
    return {"record_id": request["record_id"], "request_path": str(path), "binding": binding,
            "semantic_credit": False, "next": "Capture the original result bytes immediately, then evidence-record with the same record id."}


def capture(root: Path, feature: str, record_id: str, result_path: Path,
            environment: dict[str, Any], binding: dict[str, Any]) -> dict[str, Any]:
    directory = _directory(root, feature, record_id)
    request = read_json(directory / "request.json")
    if not isinstance(environment, dict) or not environment:
        raise PipelineError("post-execution environment must be a non-empty object")
    try:
        raw = Path(result_path).read_bytes()
    except OSError as exc:
        raise PipelineError(f"cannot read original execution result: {exc}") from exc
    raw_digest = hashlib.sha256(raw).hexdigest()
    record_path = directory / "record.json"
    if record_path.exists():
        existing = read(root, feature, record_id)
        if (existing["record"]["raw"]["sha256"] != raw_digest or
                existing["record"]["after"]["environment"] != environment or
                existing["record"]["after"]["binding"] != binding):
            raise PipelineError("execution record is immutable; a different result needs its own invocation id")
        return existing
    after_inputs = input_snapshot(root, request["input_paths"], missing_ok=True)
    stable = request["binding"] == binding and request["environment"] == environment and request["inputs"] == after_inputs
    record = {"schema": 1, "record_id": record_id, "provenance": "caller-captured-original-result",
              "before": request, "after": {"binding": deepcopy(binding), "environment": deepcopy(environment), "inputs": after_inputs},
              "raw": {"file": "result.bin", "sha256": raw_digest, "bytes": len(raw)},
              "inputs_unchanged": stable, "capture_complete": True, "finished_at": _now(), "semantic_credit": False}
    record["digest"] = digest(record)
    capture_path = contained_path(directory, directory / "capture.json")
    if capture_path.exists():
        original = read_json(capture_path)
        if (original.get("raw") != record["raw"] or original.get("after") != record["after"]
                or original.get("before") != request):
            raise PipelineError("immutable capture already binds a different raw result or observed input state")
        record = original
    else:
        write_bytes_immutable(capture_path, canonical_bytes(record))
    write_bytes_immutable(contained_path(directory, directory / "result.bin"), raw)
    write_json(record_path, record)
    return read(root, feature, record_id)


def read(root: Path, feature: str, record_id: str, *, allow_incomplete=False) -> dict[str, Any]:
    directory = _directory(root, feature, record_id)
    record_path = directory / "record.json"
    if not record_path.exists() and (directory / "attempt.json").exists():
        if allow_incomplete:
            return {"record_id": record_id, "ref": PREFIX + record_id, "path": str(directory / "attempt.json"),
                    "attempt": read_json(directory / "attempt.json"), "capture_complete": False,
                    "semantic_credit": False, "recovery": "Inspect the original attempt and streams; do not re-execute the same action."}
        raise PipelineError(f"execution capture is incomplete; read the original attempt without re-execution: {directory / 'attempt.json'}")
    record = read_json(record_path)
    if (not isinstance(record, dict) or record.get("schema") != 1 or record.get("record_id") != record_id or
            record.get("digest") != digest({k: v for k, v in record.items() if k != "digest"})):
        raise PipelineError("execution record metadata digest is invalid")
    for item in ([record["raw"]] if "raw" in record else record.get("streams", [])):
        if item.get("available") is False and not record.get("capture_complete"):
            continue
        raw_path = contained_path(directory, directory / item["file"])
        raw = raw_path.read_bytes()
        if len(raw) != item["bytes"] or hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise PipelineError("execution raw result bytes do not match the preserved digest")
    return {"record_id": record_id, "ref": PREFIX + record_id, "path": str(record_path),
            "record": record, "semantic_credit": False}


def read_producer_probe(root, feature, producer, binding):
    """Verify existing channel-probe provenance/binding, not product capability."""
    result = read(root, feature, producer["probe_ref"][len(PREFIX):])
    record = result["record"]
    before = record["before"]
    inputs = before["inputs"]
    if (before["binding"].get("kind") != "preflight"
            or record.get("provenance") != "caller-captured-original-result"
            or not record.get("capture_complete") or not record["inputs_unchanged"]
            or any(before["binding"].get(key) != binding.get(key) for key in (
                "project_root", "feature", "authority_digest", "pipeline_runtime_digest"))
            or input_snapshot(root, [row["path"] for row in inputs], missing_ok=True) != inputs
            or before["invocation"].get("channel") != producer["channel"]):
        raise PipelineError("producer probe does not bind the declared channel and current approved sources/runtime/inputs")
    return result


def _controller_anchor(record, record_id, anchors):
    if record.get("provenance") != "controller-process-execution":
        raise PipelineError("caller-captured results cannot be relabelled as controller receipts")
    invocation = record["before"]["invocation"]
    anchor = next((row for row in anchors if row.get("ref") == PREFIX + record_id
                   and row.get("digest") == record["digest"]), None)
    if (anchor is None or anchor.get("check_id") != invocation.get("check_id")
            or anchor.get("argv_sha256") != digest(invocation.get("argv"))
            or anchor.get("returncode") != record.get("result", {}).get("returncode")):
        raise PipelineError("native execution record lacks matching controller-owned attestation")
    return anchor


def _validate_record_binding(root, record, binding):
    before = record["before"]["binding"]
    if before.get("kind") == "preflight":
        raise PipelineError("producer preflight evidence cannot count as executed acceptance")
    if not record.get("capture_complete") or not record["inputs_unchanged"] or any(before.get(k) != binding.get(k) for k in (
            "project_root", "feature", "authority_digest", "pipeline_runtime_digest", "candidate_tree_oid")):
        raise PipelineError("execution evidence does not bind unchanged inputs of this candidate")
    inputs = record["after"]["inputs"]
    if input_snapshot(root, [row["path"] for row in inputs], missing_ok=True) != inputs:
        raise PipelineError("declared execution inputs changed after the captured result")


def validate_issued_native_receipt(root, feature, row, binding, state, recipe):
    """Check an issued observation, without treating a reader's env as execution."""
    ref = row.get("execution_evidence")
    if not isinstance(ref, str) or not ref.startswith(PREFIX):
        raise PipelineError("issued native observation has no durable execution record")
    record_id = ref[len(PREFIX):].split("#", 1)[0]
    record = read(root, feature, record_id)["record"]
    _validate_record_binding(root, record, binding)
    anchors = [item for event in state.get("history", []) for item in event.get("execution_records", [])]
    anchor = _controller_anchor(record, record_id, anchors)
    if (row.get("execution_record_digest") != record["digest"] or row.get("id") != anchor["check_id"]
            or row.get("returncode") != anchor["returncode"]
            or row.get("outcome") != ("pass" if anchor["returncode"] == 0 else "fail")):
        raise PipelineError("issued native observation differs from its controller-owned record")
    attempt = read_json(_directory(root, feature, record_id) / "attempt.json")
    request = attempt.get("request", {})
    if (attempt.get("status") != "finished" or request.get("recipe") != recipe
            or any(request.get(key) != value for key, value in record["before"].items())
            or attempt.get("result", {}).get("execution_record_digest") != record["digest"]):
        raise PipelineError("issued native observation does not match its original finished recipe/input attempt")


def _candidate_source(root, source, binding, state):
    from .checkout import _git, matches, safe_path
    from .qa_contract import source_reference
    source_reference(source)
    active = (state or {}).get("active_assignment") or {}
    if not any(matches(source["path"], rule) for rule in active.get("access", {}).get("read", [])):
        raise PipelineError("QA source evidence is outside the issued read scope")
    # Membership in the bound Git tree excludes ignored working/controller data.
    _git(root, ["cat-file", "-e", f"{binding['candidate_tree_oid']}:{source['path']}"], label="candidate QA source")
    raw = safe_path(root, source["path"], "QA source evidence", strict=True).read_bytes()
    if hashlib.sha256(raw).hexdigest() != source["sha256"]:
        raise PipelineError("QA source bytes differ from the referenced source-reader hash")
    if "end_line" in source:
        if source["end_line"] > len(raw.decode("utf-8").splitlines()):
            raise PipelineError("QA source span exceeds the actual source file")


def validate_references(root: Path, feature: str, artifact: dict[str, Any], binding: dict[str, Any],
                        *, state=None, contract_slice=None) -> None:
    location = [""]
    try:
        _validate_references(root, feature, artifact, binding, state=state, contract_slice=contract_slice, location=location)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        if not getattr(exc, "path", None):
            exc.path = location[0]
        raise


def _validate_references(root, feature, artifact, binding, *, state, contract_slice, location):
    """Bind new durable refs to the selected method and controller-owned history.

    Historical plain-text source refs remain readable. Their mere shape does not
    acquire the trust of a native execution record, nor do producer probes count.
    """
    from .qa_contract import expand_slice_contract
    if contract_slice is None and state is not None:
        from .model import qa_contract_context
        context = qa_contract_context(state)
        if context.get("status") == "bound":
            contract_slice = context["definition"]
    definitions = {}
    if contract_slice is not None:
        definitions = {row["id"]: row for check in expand_slice_contract(contract_slice)["identities"] for row in check["assertions"]}
    anchors = [row for event in (state or {}).get("history", []) for row in event.get("execution_records", [])]
    canonical_receipts = {"bound-machine-receipt", "controller-check-receipt"}
    verified_sources = set()
    for check_index, check in enumerate(artifact.get("checks", [])):
        if not isinstance(check, dict):
            continue
        for assertion_index, assertion in enumerate(check.get("assertions", [])):
            assertion_path = f"/checks/{check_index}/assertions/{assertion_index}"
            location[0] = assertion_path
            executed = assertion.get("outcome") in {"pass", "fail"}
            repair_claim = assertion.get("reason", {}).get("kind") == "verification_incomplete" and "repair" in assertion.get("reason", {})
            credit_bearing = executed or assertion.get("outcome") == "not_applicable" or repair_claim
            definition = definitions.get(assertion.get("id"))
            method = next((m for m in (definition or {}).get("methods", []) if m["id"] == assertion.get("method_id")), None)
            producer = (method or {}).get("producer")
            covered_checks, matching_records = set(), 0
            for evidence_index, item in enumerate(assertion.get("evidence", [])):
                location[0] = assertion_path + f"/evidence/{evidence_index}/ref"
                ref = item.get("ref", "")
                if "source" in item:
                    location[0] = assertion_path + f"/evidence/{evidence_index}/source"
                    if credit_bearing:
                        if not repair_claim and (item.get("type") in canonical_receipts or
                                (executed and producer and item.get("type") in method["evidence_types"])):
                            raise PipelineError("candidate source context cannot replace the selected method's required execution-producer evidence")
                        key = digest(item["source"])
                        if key not in verified_sources:
                            _candidate_source(root, item["source"], binding, state)
                            verified_sources.add(key)
                    continue
                if not isinstance(ref, str) or not ref.startswith(PREFIX):
                    continue
                record_id = ref[len(PREFIX):].split("#", 1)[0]
                record = read(root, feature, record_id)["record"]
                if not credit_bearing:
                    continue
                _validate_record_binding(root, record, binding)
                if repair_claim:
                    continue  # Bound diagnostic proof of a gap, not method execution.
                if not executed:
                    if (definition is None or definition["applicability"]["kind"] != "conditional"
                            or assertion.get("method_id") is not None):
                        raise PipelineError("durable applicability evidence requires the approved condition and no executed method")
                    if item.get("type") in canonical_receipts:
                        anchor = _controller_anchor(record, record_id, anchors)
                        if anchor["returncode"] != 0:
                            raise PipelineError("failed native execution cannot support not_applicable acceptance credit")
                    continue
                if method is None:
                    raise PipelineError("durable acceptance evidence requires the selected approved method contract")
                native_required = item.get("type") in canonical_receipts or (producer or {}).get("kind") == "controller_check"
                if native_required:
                    if not producer or producer["kind"] != "controller_check":
                        raise PipelineError("fresh controller receipt evidence requires an explicit approved check producer")
                    anchor = _controller_anchor(record, record_id, anchors)
                    if anchor["check_id"] not in producer["check_ids"]:
                        raise PipelineError("execution record belongs to a different approved controller check")
                    if assertion["outcome"] == "pass" and anchor["returncode"] != 0:
                        raise PipelineError("failed native execution cannot support QA PASS")
                    covered_checks.add(anchor["check_id"])
                elif producer and producer["kind"] in {"tool", "manual"}:
                    if (record.get("provenance") != "caller-captured-original-result"
                            or record["before"]["invocation"].get("channel") != producer["channel"]):
                        raise PipelineError("execution evidence does not match the selected tool/manual producer channel: "
                                            f"{assertion['id']} / {method['id']}: observed {record['before']['invocation'].get('channel')!r}, approved {producer['channel']!r}")
                matching_records += 1
            if executed and producer:
                location[0] = assertion_path + "/evidence"
                if producer["kind"] == "controller_check" and covered_checks != set(producer["check_ids"]):
                    raise PipelineError("selected controller method requires durable evidence for every declared check_id")
                if producer["kind"] in {"tool", "manual"} and not matching_records:
                    raise PipelineError("selected tool/manual method requires its original durable result")


def native_record(root, feature, record_id, *, invocation, binding, environment,
                  inputs_before, inputs_after, after_binding, result, stream_digests=None, capture_error=None,
                  after_environment=None):
    """Seal bytes already streamed by the actual controller process execution."""
    directory = _directory(root, feature, record_id)
    after_environment = environment if after_environment is None else after_environment
    streams = []
    for name in ("stdout", "stderr"):
        path = directory / (name + ".bin")
        if not path.is_file():
            capture_error = capture_error or "raw capture file is unavailable"
            streams.append({"file": path.name, "available": False})
            continue
        raw = path.read_bytes()
        sha256 = hashlib.sha256(raw).hexdigest()
        if stream_digests is not None and sha256 != stream_digests[name] and not capture_error:
            raise PipelineError("raw process capture differs from the actual stream digest; command already executed, do not infer successful capture")
        streams.append({"file": path.name, "sha256": sha256, "bytes": len(raw),
                        **({"process_sha256": stream_digests[name]} if stream_digests else {})})
    record = {"schema": 1, "record_id": record_id, "provenance": "controller-process-execution",
              "before": {"binding": binding, "invocation": invocation, "environment": environment, "inputs": inputs_before},
              "after": {"binding": after_binding, "environment": after_environment, "inputs": inputs_after},
              "streams": streams, "result": deepcopy(result), "finished_at": _now(),
              "inputs_unchanged": binding == after_binding and inputs_before == inputs_after and environment == after_environment,
              "capture_complete": stream_digests is not None and not capture_error,
              **({"capture_error": capture_error} if capture_error else {}),
              "semantic_credit": False}
    record["digest"] = digest(record)
    write_json(directory / "record.json", record)
    return PREFIX + record_id


def native_attempt(root, feature, record_id, request):
    """Durable side-effect boundary: an uncertain started invocation never reruns."""
    directory = _directory(root, feature, record_id)
    path = directory / "attempt.json"
    if path.exists():
        prior = read_json(path)
        if prior.get("request") != request:
            raise PipelineError(f"check attempt identity already binds different inputs: {path}")
        if prior.get("status") == "finished":
            result = deepcopy(prior["result"])
            if "execution_evidence" in result:
                record = read(root, feature, record_id)["record"]
                if result.get("execution_record_digest") != record["digest"]:
                    raise PipelineError("completed execution record changed; do not rerun the original action")
            return result
        raise PipelineError(f"check attempt already started; execution/capture needs read-only recovery, never rerun the same action: {path}")
    write_bytes_immutable(path, canonical_bytes({"schema": 1, "status": "started", "request": request, "started_at": _now()}))
    return None


def finish_native_attempt(root, feature, record_id, result):
    path = _directory(root, feature, record_id) / "attempt.json"
    prior = read_json(path)
    prior.update(status="finished", result=deepcopy(result), finished_at=_now())
    write_json(path, prior)
