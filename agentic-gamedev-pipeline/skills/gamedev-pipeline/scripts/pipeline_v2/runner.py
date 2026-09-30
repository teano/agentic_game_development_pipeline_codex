"""Imperative controller shell around the pure reducer."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import time
from copy import deepcopy
from pathlib import Path
from typing import Any
from .technical_decisions import validate_entry
from .model import seal_qa_contract
from .execution import (metadata, owner_key, recipe_for, receipt_binding, seal_verification,
                        verification_environment, execution_environment, machine_check_row, machine_check_inputs, executable_identity)

from .checkout import (
    authority_items,
    authority_items_equal,
    candidate_tree_oid,
    canonical_project_root,
    changed_paths,
    path_identity,
    pipeline_runtime_digest,
    repository_policy_changed,
    require_clean_head,
    safe_path,
    verify_authority,
    violations,
)
from .legacy_gen53 import SCHEMA10_UNSUPPORTED_MESSAGE
from .model import (
    PHASES,
    PipelineError,
    WorkerArtifactValidationError,
    assignment_identity,
    assignment_output_path,
    canonical_command,
    current_candidate,
    current_slice,
    default_assignment,
    digest,
    feature_slug,
    is_digest,
    is_generation,
    is_git_oid,
    is_strict_integer,
    normalize_literal_path,
    literal_paths_valid,
    reconfiguration_action,
    safe_identifier,
    slice_records,
    slices_are_read_sealed,
    status_view,
    terminal_blocked_context,
    validate_capability_recovery,
    validate_state,
    workflow_relative_path,
)
from .process_tree import run_process_tree
from .reducer import (
    _engineering_candidate_diff_base,
    _worker_artifact,
)
from .transaction import StateStore


TECHNICAL_FAILURE_RETURN_CODE = 125
STDERR_EXCERPT_BYTES = 4096

_SENSITIVE_ENV_NAME = re.compile(
    r"(?:api_?key|apikey|token|secret|password|passwd|credential|authorization|bearer|private_?key|access_?key|(?:^|_)pat(?:_|$)|database_?url|dsn)",
    re.IGNORECASE,
)
_SECRET_PATTERNS = (
    re.compile(r"\b([a-z][a-z0-9+.-]*://)([^/\s@]+)@", re.IGNORECASE),
    re.compile(r"\b(bearer)(\s+)([^\s,;]+)", re.IGNORECASE),
    re.compile(
        r"\b(api[-_ ]?key|password|passwd|access[-_ ]?token|refresh[-_ ]?token|token|secret)"
        r"(\s*[:=]\s*)([^\s,;]+)",
        re.IGNORECASE,
    ),
)

_PLAN_CONTRACT_PATH = Path(__file__).resolve().parents[4] / "scripts" / "development_plan_contract.py"
_PLAN_CONTRACT_SPEC = importlib.util.spec_from_file_location(
    "gamedev_pipeline_development_plan_contract", _PLAN_CONTRACT_PATH,
)
if _PLAN_CONTRACT_SPEC is None or _PLAN_CONTRACT_SPEC.loader is None:
    raise RuntimeError("Cannot load the shared development-plan contract")
_PLAN_CONTRACT = importlib.util.module_from_spec(_PLAN_CONTRACT_SPEC)
_PLAN_CONTRACT_SPEC.loader.exec_module(_PLAN_CONTRACT)

_PLAN_AUTHORITY_PATH = (
    Path(__file__).resolve().parents[3]
    / "gamedev-development-plan" / "scripts" / "development_plan_state.py"
)
_PLAN_AUTHORITY_SPEC = importlib.util.spec_from_file_location(
    "gamedev_pipeline_plan_authority", _PLAN_AUTHORITY_PATH,
)
if _PLAN_AUTHORITY_SPEC is None or _PLAN_AUTHORITY_SPEC.loader is None:
    raise RuntimeError("Cannot load the existing Planning authority validator")
_PLAN_AUTHORITY = importlib.util.module_from_spec(_PLAN_AUTHORITY_SPEC)
_PLAN_AUTHORITY_SPEC.loader.exec_module(_PLAN_AUTHORITY)


def _require_expected_generation(value: Any) -> None:
    if value is not None and not is_strict_integer(value):
        raise PipelineError("expected generation must be an integer")


def _caller_slices(value: Any) -> list[dict[str, Any]]:
    return slice_records(value, sealed=False)


def _unsealed_projection(value: Any) -> list[dict[str, Any]]:
    records = slice_records(value)
    return [
        {key: deepcopy(item[key]) for key in ("id", "allowed_paths", "planned_commands")}
        for item in records
    ]


def seal_slices_from_approved_plan(
    root: Path, plan_path: str, slices: Any, feature: str,
    *, rebind_stored_paths: bool = False,
) -> list[dict[str, Any]]:
    """Seal exact caller scope, or reproject stored scope during reconfiguration."""
    caller = _caller_slices(slices)
    plan = safe_path(root, plan_path, "approved development plan", strict=True)
    try:
        plan_text = plan.read_text(encoding="utf-8")
        contracts_by_id = _PLAN_CONTRACT.parse_slice_path_contracts(
            plan_text, label=str(plan_path), include_qa=True,
        )
    except (OSError, UnicodeError, _PLAN_CONTRACT.PlanContractError) as exc:
        raise PipelineError(f"cannot seal approved plan read scopes: {exc}") from exc
    frontmatter = re.match(r"\A---\n(.*?)\n---(?:\n|\Z)", plan_text, re.S)
    bound_features = (
        re.findall(r"(?m)^feature:\s*(\S+)\s*$", frontmatter.group(1))
        if frontmatter is not None
        else []
    )
    if bound_features != [feature_slug(feature)]:
        raise PipelineError("approved plan feature does not match selected workflow")
    caller_ids = [item["id"] for item in caller]
    plan_ids = list(contracts_by_id)
    missing = [slice_id for slice_id in caller_ids if slice_id not in contracts_by_id]
    unknown = [slice_id for slice_id in plan_ids if slice_id not in caller_ids]
    if missing or unknown or plan_ids != caller_ids:
        raise PipelineError(
            "approved plan slice IDs must exactly match caller slices in order: "
            f"missing={missing} unknown={unknown}"
        )
    sealed: list[dict[str, Any]] = []
    for item in caller:
        contract = contracts_by_id[item["id"]]
        if not rebind_stored_paths and item["allowed_paths"] != contract["write_paths"]:
            raise PipelineError(
                "caller allowed_paths must exactly equal approved plan write_paths "
                f"in order for {item['id']}"
            )
        sealed.append({
            **item, "allowed_paths": deepcopy(contract["write_paths"]),
            "read_paths": deepcopy(contract["read_paths"]),
        })
    return sealed


def _stream_digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _process_environment() -> dict[str, str]:
    """Keep Node/npm's optional compile cache out of the candidate checkout."""
    return execution_environment()


def _replace_literal(value: str, literal: str, replacement: str) -> tuple[str, bool]:
    if not literal:
        return value, False
    updated, count = re.subn(
        re.escape(literal), lambda _match: replacement, value, flags=re.IGNORECASE,
    )
    return updated, count > 0


def _stderr_excerpt(
    raw: bytes, *, raw_truncated: bool, environment: dict[str, str],
    project_root: Path,
) -> dict[str, Any]:
    """Return one redacted, path-normalized, byte-bounded failure tail."""
    text = raw.decode("utf-8", errors="replace")
    redacted = False
    sensitive_values = sorted(
        {
            value for name, value in environment.items()
            if value and _SENSITIVE_ENV_NAME.search(name)
        },
        key=len,
        reverse=True,
    )
    for secret in sensitive_values:
        text, replaced = _replace_literal(text, secret, "[REDACTED]")
        redacted = redacted or replaced
    for pattern in _SECRET_PATTERNS:
        text, count = pattern.subn(
            lambda match: (
                f"{match.group(1)}[REDACTED]@"
                if "://" in match.group(1)
                else f"{match.group(1)}{match.group(2)}[REDACTED]"
            ),
            text,
        )
        redacted = redacted or count > 0
    roots = [(str(Path(os.path.abspath(project_root))), "[PROJECT_ROOT]")]
    for root_value, replacement in roots:
        for spelling in dict.fromkeys((root_value, root_value.replace("\\", "/"))):
            text, _ = _replace_literal(text, spelling, replacement)
    encoded = text.encode("utf-8")
    truncated = raw_truncated or len(encoded) > STDERR_EXCERPT_BYTES
    if len(encoded) > STDERR_EXCERPT_BYTES:
        encoded = encoded[-STDERR_EXCERPT_BYTES:]
        text = encoded.decode("utf-8", errors="ignore")
    return {
        "stderr_excerpt": text,
        "stderr_excerpt_truncated": truncated,
        "stderr_excerpt_redacted": redacted,
    }


class Controller:
    def __init__(self, store: StateStore, *, timeout: float = 600.0):
        self.store = store
        self.timeout = timeout

    @staticmethod
    def _evidence_binding(state, root, tree=None):
        active = state.get("active_assignment")
        if not isinstance(active, dict):
            raise PipelineError("product execution capture requires the current active assignment")
        return {"kind": "assignment", "project_root": str(root), "feature": state["feature"],
                "run_id": state["run_id"], "assignment_id": active["id"], "phase": active["phase"],
                "slice_id": current_slice(state)["id"], "authority_digest": state["authority"]["digest"],
                "pipeline_runtime_digest": state["pipeline_runtime_digest"],
                "candidate_tree_oid": tree or candidate_tree_oid(root)}

    def _preflight_evidence_binding(self, request):
        if (not isinstance(request.get("project_root"), str) or not request["project_root"].strip()
                or not isinstance(request.get("authority_paths"), dict)):
            raise PipelineError("preflight evidence requires exact project_root, feature and authority_paths")
        root = canonical_project_root(request.get("project_root"))
        feature = feature_slug(request.get("feature"))
        self.store.validate_project_location(root, feature)
        paths = request.get("authority_paths")
        from .model import authority_record
        authority = authority_record(authority_items(root, paths))
        return root, feature, {"kind": "preflight", "project_root": str(root), "feature": feature,
                              "authority_digest": authority["digest"], "authority_paths": paths,
                              "pipeline_runtime_digest": pipeline_runtime_digest(),
                              "candidate_tree_oid": candidate_tree_oid(root)}

    def evidence_begin(self, request):
        from .execution_evidence import begin
        if not isinstance(request, dict):
            raise PipelineError("evidence request must be an object")
        with self.store.transaction():
            if request.get("preflight") is True:
                if "assignment_id" in request:
                    raise PipelineError("preflight capture cannot invent a native assignment id")
                root, feature, binding = self._preflight_evidence_binding(request)
            else:
                state, root = self._loaded()
                self._verify_live_checkout(state, root)
                feature, binding = state["feature"], self._evidence_binding(state, root)
                if request.get("assignment_id") != binding["assignment_id"]:
                    raise PipelineError("evidence begin requires the exact current assignment_id")
            return begin(root, feature, request, binding)

    def _evidence_location(self):
        # StateStore is already fixed by the public root/feature selector. A
        # pre-init probe uses the same canonical location without inventing state.
        directory = self.store.path.parent
        feature = feature_slug(directory.name)
        root = canonical_project_root(directory.parent.parent.parent)
        self.store.validate_project_location(root, feature)
        return root, feature

    def evidence_record(self, record_id, result_path, environment):
        from .execution_evidence import _directory, capture
        from .artifact_io import read_json
        with self.store.transaction():
            root, feature = self._evidence_location()
            request = read_json(_directory(root, feature, record_id) / "request.json")
            prior = request["binding"]
            if prior.get("kind") == "preflight":
                _, _, binding = self._preflight_evidence_binding(prior)
            else:
                state, root = self._loaded()
                binding = self._evidence_binding(state, root)
            return capture(root, feature, record_id, result_path, environment, binding)

    def evidence_read(self, record_id, *, raw_file=None):
        from .execution_evidence import read
        root, feature = self._evidence_location()
        result = read(root, feature, record_id, allow_incomplete=True)
        if raw_file is None:
            return result
        record = result.get("record", {})
        files = [record["raw"]] if "raw" in record else record.get("streams", [])
        item = next((row for row in files if row.get("file") == raw_file and row.get("available", True)), None)
        if item is None:
            raise PipelineError("raw-file must name one available file in this exact execution record")
        from .artifact_io import contained_path
        path = contained_path(Path(result["path"]).parent, Path(result["path"]).parent / raw_file)
        try:
            raw = path.read_bytes()
            if len(raw) != item["bytes"] or hashlib.sha256(raw).hexdigest() != item["sha256"]:
                raise PipelineError("execution raw result changed while selecting its contents")
            value = raw.decode("utf-8")
        except UnicodeError as exc:
            raise PipelineError(f"recorded binary bytes require their original file reader: {path}") from exc
        try:
            value = json.loads(value)
        except ValueError:
            pass  # Exact decoded text, not a guessed JSON schema.
        return {"record_id": record_id, "ref": result["ref"], "path": result["path"], "record_digest": record["digest"],
                "provenance": record["provenance"], "raw": {**item, "path": str(path)},
                "value": value, "semantic_credit": False}

    def _artifact_errors(self, state, root, value):
        from .artifact_io import validation_errors
        errors = validation_errors(state, value)
        if not errors:
            from .execution_evidence import validate_references
            try:
                binding = self._evidence_binding(state, root)
                validate_references(root, state["feature"], value, binding, state=state)
                if state["active_assignment"]["phase"] == "qa":
                    from .qa_draft import validate_projection
                    validate_projection(state, root, binding, value)
            except (ValueError, OSError) as exc:
                errors.append({"path": "/checks", "message": str(exc)})
        return errors

    def _qa_working_context(self, assignment_id):
        state, root = self._loaded()
        active = state.get("active_assignment") or {}
        if active.get("phase") != "qa" or active.get("id") != assignment_id:
            raise PipelineError("QA working operation requires the exact current QA assignment_id")
        self._verify_live_checkout(state, root)
        return state, root, self._evidence_binding(state, root)

    def qa_draft(self, assignment_id, *, identity_id=None, assertion_id=None):
        from .qa_draft import load, view
        with self.store.transaction():
            state, root, binding = self._qa_working_context(assignment_id)
            return view(*load(state, root, binding, create=True), identity_id=identity_id, assertion_id=assertion_id)

    def qa_read(self, assignment_id, *, identity_id=None, assertion_id=None):
        from .qa_draft import load, view
        state, root, binding = self._qa_working_context(assignment_id)
        return view(*load(state, root, binding), identity_id=identity_id, assertion_id=assertion_id)

    def qa_prepare(self, assignment_id, assertion_ids=None, method_id=None, *, identity_id=None):
        from .qa_draft import load, prepare, compact_prepared_request
        from .execution_evidence import read_producer_probe, validate_issued_native_receipt
        state, root, binding = self._qa_working_context(assignment_id)
        draft, definition, path, exists = load(state, root, binding)
        try:
            result = prepare(draft, definition, assertion_ids, method_id, identity_id=identity_id)
        except ValueError as exc:
            if isinstance(exc, PipelineError):
                raise
            error = PipelineError(str(exc))
            error.path = getattr(exc, "path", "") or "/method_id"
            raise error from exc
        result["working_path"] = str(path)
        result["evidence_destination"] = str(root / state["workflow_path"] / "Evidence")
        methods = result["obligations"]["method_definitions"]
        row_methods = {row["id"]: row["methods"] for identity in result["obligations"]["identities"] for row in identity["assertions"]}
        contexts = {}
        alternatives = [(row["assertion_id"], reference["ref"], methods[reference["ref"]])
                        for row in result["prepared_methods"] for reference in row_methods[row["assertion_id"]]]
        for assertion_id, method_ref, method in alternatives:
            producer = method.get("producer")
            key = digest(producer)
            if key in contexts:
                if assertion_id not in contexts[key]["assertion_ids"]:
                    contexts[key]["assertion_ids"].append(assertion_id)
                if method_ref not in contexts[key]["method_refs"]:
                    contexts[key]["method_refs"].append(method_ref)
                continue
            context = {"assertion_ids": [assertion_id], "method_refs": [method_ref], "producer": producer,
                       "semantic_credit": False}
            contexts[key] = context
            if producer is None:
                context["prerequisite"] = {"status": "not_declared", "detail": "No execution producer is declared. Follow the complete approved method source; no channel or invocation is inferred."}
            elif producer["kind"] == "controller_check":
                context["provenance"] = "controller-process-execution"
                recipes = [recipe_for(state, argv, index, self.timeout)
                           for index, argv in enumerate(current_slice(state)["planned_commands"])]
                context["checks"] = [recipe for recipe in recipes if recipe["id"] in producer["check_ids"]]
                try:
                    machine = state["active_assignment"]["capsule"]["context"].get("machine_checks")
                    if machine is None:
                        # Legacy capsules without an issued observation retain conservative lookup.
                        machine = machine_check_inputs(state, binding["candidate_tree_oid"], execution_environment(), self.timeout)
                    else:
                        if any(machine.get(key) != binding[key] for key in (
                                "candidate_tree_oid", "authority_digest", "pipeline_runtime_digest")):
                            raise PipelineError("issued machine checks do not bind this QA candidate/authority/runtime")
                        for receipt in machine["checks"]:
                            if receipt["id"] in producer["check_ids"]:
                                recipe = next((item for item in context["checks"] if item["id"] == receipt["id"]), None)
                                validate_issued_native_receipt(root, state["feature"], receipt, binding, state, recipe)
                    context["receipts"] = [row for row in machine["checks"] if row["id"] in producer["check_ids"]]
                    missing = set(producer["check_ids"]) - {row["id"] for row in context["receipts"]}
                    context["prerequisite"] = {"status": "check_required" if missing else "receipts_available",
                        "pending_check_ids": sorted(missing), "detail": "Use the assigned controller check for missing receipts; never run its argv as a worker. Assess the actual assertions, not the aggregate verdict."}
                except (PipelineError, OSError, KeyError, TypeError) as exc:
                    context["receipts"] = []
                    context["prerequisite"] = {"status": "unresolved", "detail": str(exc)}
            else:
                context["provenance"] = "caller-captured-original-result"
                record_id = producer["probe_ref"].partition(":")[2]
                context["probe_reader"] = ["evidence-read", "--record-id", record_id]
                context["product_invocation"] = None
                context["evidence_begin_request"] = {"record_id": None, "assignment_id": assignment_id,
                    "invocation": {"channel": producer["channel"], "request": None}, "environment": None, "input_paths": None}
                try:
                    probe = read_producer_probe(root, state["feature"], producer, binding)
                    record = probe["record"]
                    context["probe"] = {"ref": probe["ref"], "path": probe["path"], "digest": record["digest"],
                        "provenance": record["provenance"], "request_locator": probe["path"] + "#/before/invocation",
                        "environment_locator": probe["path"] + "#/before/environment", "resources": record["before"]["inputs"],
                        "raw_result": {**record["raw"], "path": str(Path(probe["path"]).parent / record["raw"]["file"])}}
                    context["prerequisite"] = {"status": "probe_bound", "detail": "This record proves only a prior channel probe. Its fixture request is not a product invocation or current product observation. Follow the approved method source and honor actual permission or capability failures."}
                except (PipelineError, OSError, KeyError, TypeError) as exc:
                    context["prerequisite"] = {"status": "unresolved", "detail": str(exc)}
        result["producer_context"] = list(contexts.values())
        # Canonical native refs are service data; observation/comparison remain empty.
        native = {row["id"]: row for context in contexts.values() for row in context.get("receipts", [])}
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
        return {key: result[key] for key in ("binding", "revision", "working_path", "evidence_destination", "producer_context",
                "obligations", "prepared_methods", "record_request", "semantic_credit", "tests_executed", "required_action")}

    def qa_record(self, assignment_id, request):
        from .qa_draft import load, view, prepare_update
        from .artifact_io import write_json
        from .execution_evidence import validate_references
        from .checkout import matches
        with self.store.transaction():
            state, root, binding = self._qa_working_context(assignment_id)
            draft, definition, path, exists = load(state, root, binding)
            changed = {}
            def acknowledgment(value, present):
                return {key: item for key, item in view(value, definition, path, present).items()
                        if key not in {"identities", "technical_decisions"}}
            try:
                updated, errors, changed = prepare_update(draft, definition, request)
                if not errors:
                    for row in changed.values():
                        repair = row.get("reason", {}).get("repair")
                        if repair and not any(matches(repair["target"], rule) for rule in current_slice(state)["allowed_paths"]):
                            raise PipelineError("QA repair target is outside the approved Engineering write scope")
                    validate_references(root, state["feature"], {"checks": [{"assertions": list(changed.values())}]}, binding, state=state)
            except (ValueError, KeyError, TypeError, OSError) as exc:
                error_path = getattr(exc, "path", "") or "/assessments"
                prefix = "/checks/0/assertions/"
                if error_path.startswith(prefix):
                    index, _, suffix = error_path[len(prefix):].partition("/")
                    identifier = list(changed)[int(index)]
                    position = next(i for i, row in enumerate(request["assessments"]) if row.get("id") == identifier)
                    error_path = f"/assessments/{position}" + ("/" + suffix if suffix else "")
                updated, errors = None, [{"path": error_path, "message": str(exc)}]
            if errors:
                return {**acknowledgment(draft, exists), "valid": False, "errors": errors,
                        "required_action": "Continue/correct the same QA assessment group; no Engineering repair or execution credit was issued."}
            self._verify_live_checkout(state, root)
            if not exists or updated != draft:
                write_json(path, updated)
            return {**acknowledgment(updated, True), "valid": True, "errors": [],
                    "changed_assertion_ids": [key for key in changed if draft["assessments"].get(key) != updated["assessments"][key]],
                    "terminal_requires_finalize": True}

    def qa_finalize(self, assignment_id, expected_revision):
        from .qa_draft import load, view, assemble
        from .artifact_io import write_json
        with self.store.transaction():
            state, root, binding = self._qa_working_context(assignment_id)
            draft, definition, path, exists = load(state, root, binding)
            metadata = view(draft, definition, path, exists)
            if type(expected_revision) is not int or expected_revision != draft["revision"]:
                raise PipelineError("stale QA draft revision; read current draft before finalization")
            if metadata["pending"]:
                return {**metadata, "valid": False, "errors": [{"path": "/assessments", "message": "QA assessment remains pending; it is not a not_run verdict or Engineering gap."}],
                        "required_action": "Continue the same QA working artifact for the remaining assertion groups."}
            artifact = assemble(draft, definition)
            errors = self._artifact_errors(state, root, artifact)
            if errors:
                return {**metadata, "valid": False, "errors": errors}
            self._verify_live_checkout(state, root)
            output = safe_path(root, assignment_output_path(state["active_assignment"], state["feature"]), "assigned QA terminal artifact")
            write_json(output, artifact)
            raw = output.read_bytes()
            return {**metadata, "valid": True, "errors": [], "outcome": artifact["outcome"],
                    "path": str(output), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}

    def artifact_validate(self, source, assignment_id=None):
        from .artifact_io import read_json
        state, root = self._loaded()
        if assignment_id is not None and assignment_id != (state.get("active_assignment") or {}).get("id"):
            raise PipelineError("artifact assignment_id is not the current issued assignment")
        value = read_json(source)
        self._verify_live_checkout(state, root)
        errors = self._artifact_errors(state, root, value)
        return {"valid": not errors, "errors": errors, "assignment_id": state["active_assignment"]["id"],
                "semantic_credit": False, "tests_executed": False}

    def artifact_write(self, source, assignment_id=None):
        from .artifact_io import read_json, write_json
        with self.store.transaction():
            state, root = self._loaded()
            if not assignment_id or assignment_id != (state.get("active_assignment") or {}).get("id"):
                raise PipelineError("artifact write requires the exact current assignment_id")
            value = read_json(source)
            self._verify_live_checkout(state, root)
            errors = self._artifact_errors(state, root, value)
            report = {"valid": not errors, "errors": errors, "assignment_id": state["active_assignment"]["id"],
                      "semantic_credit": False, "tests_executed": False}
            if errors:
                return report
            output = safe_path(root, assignment_output_path(state["active_assignment"], state["feature"]), "assigned artifact")
            write_json(output, value)
            raw = output.read_bytes()
            return {**report, "path": str(output), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}

    @staticmethod
    def _verify_producer_probes(state, root):
        from .model import require_verification_feasibility, verification_feasibility
        from .execution_evidence import read_producer_probe
        require_verification_feasibility(state)
        for group in verification_feasibility(state)["probes"]:
            failures = []
            for producer in group["alternatives"]:
                try:
                    read_producer_probe(root, state["feature"], producer, {
                        "project_root": str(root), "feature": state["feature"],
                        "authority_digest": state["authority"]["digest"], "pipeline_runtime_digest": state["pipeline_runtime_digest"]})
                    break
                except (PipelineError, OSError, KeyError, TypeError) as exc:
                    failures.append(f"{producer['method_id']}: {exc}")
            else:
                raise PipelineError("all approved producer alternatives are unavailable before Engineering; resolve owning method prerequisite: " + "; ".join(failures))

    def _loaded(self, state: dict[str, Any] | None = None) -> tuple[dict[str, Any], Path]:
        state = self.store.load() if state is None else state
        validate_state(state)
        root = canonical_project_root(state["project_root"])
        self.store.validate_project_location(root, state["feature"])
        if pipeline_runtime_digest() != state["pipeline_runtime_digest"]:
            raise PipelineError(
                "pipeline runtime changed during the run; stop and perform a fresh init"
            )
        verify_authority(root, state["authority"])
        if not slices_are_read_sealed(state):
            raise PipelineError(
                "controller read scope is not sealed; run status and execute its init reconfiguration"
            )
        return state, root

    def _preflight_existing_store_location(self) -> None:
        """Reject split-brain state paths before creating a transaction lock."""
        state = self.store.load()
        validate_state(state)
        root = canonical_project_root(state["project_root"])
        self.store.validate_project_location(root, state["feature"])

    @staticmethod
    def _latest_controller_tree(state: dict[str, Any]) -> str | None:
        completed_generation = {
            item["assignment_id"]: item["generation"]
            for item in state["history"]
            if isinstance(item.get("assignment_id"), str)
            and is_generation(item.get("generation"))
        }
        epoch_generation = max(
            (
                item["generation"] for item in state["history"]
                if item.get("command") == "init" and is_generation(item.get("generation"))
            ),
            default=-1,
        )
        observed: list[tuple[int, int, str]] = []
        for phase in ("plan", "slice", "engineering", "review", "qa", "docs", "ready"):
            record = state["artifacts"].get(phase)
            controller = record.get("controller") if isinstance(record, dict) else None
            tree = controller.get("candidate_tree_oid") if isinstance(controller, dict) else None
            if is_git_oid(tree):
                generation = completed_generation.get(
                    record.get("assignment_id"),
                    epoch_generation if record.get("assignment_id") == "controller-checkout-baseline" else -1,
                )
                observed.append((generation, PHASES.index(phase), tree))
        return max(observed, default=(-1, -1, None))[-1]

    def _checkout_drift(
        self, state: dict[str, Any], root: Path, current: str,
        *, ignore_authority: bool = False,
    ) -> list[str]:
        authority_paths = {
            path_identity(item["path"]) for item in state["authority"]["items"].values()
        }
        active = state["active_assignment"]
        if active is not None:
            changes = changed_paths(root, active["base"]["candidate_tree_oid"], current)
            if ignore_authority:
                changes = [
                    path for path in changes
                    if path_identity(path) not in authority_paths
                ]
            return violations(changes, active["access"]["write"])
        expected = self._latest_controller_tree(state)
        if expected is None:
            candidate = current_candidate(state)
            expected = candidate.get("candidate_tree_oid") if isinstance(candidate, dict) else None
        if expected is None or expected == current:
            return []
        changes = changed_paths(root, expected, current)
        if ignore_authority:
            changes = [path for path in changes if path_identity(path) not in authority_paths]
        return changes

    @staticmethod
    def _can_admit_early_blocked_baseline(
        state: dict[str, Any], root: Path, current: str,
        observed_authority: dict[str, dict[str, str]],
    ) -> bool:
        """Admit a committed prerequisite baseline only before the first product work."""
        if (
            state["phase"] != "engineering"
            or terminal_blocked_context(state) is None
            or set(state["artifacts"]) != {"plan", "slice", "engineering"}
            or sum(item.get("command") == "init" for item in state["history"]) != 1
            or sum(
                item.get("command") == "complete" and item.get("phase") == "engineering"
                for item in state["history"]
            ) != 1
        ):
            return False
        for record in state["artifacts"].values():
            controller = record.get("controller", {})
            if (
                record.get("controller_failure") is not None
                or controller.get("base_tree_oid") != state["base_tree_oid"]
                or controller.get("candidate_tree_oid") != state["base_tree_oid"]
                or controller.get("changed_paths") != []
                or controller.get("violations") != []
            ):
                return False
        try:
            _PLAN_AUTHORITY.require_approved_authority_chain(
                root, {name: item["path"] for name, item in observed_authority.items()},
            )
            return require_clean_head(root) == current
        except (
            PipelineError, _PLAN_AUTHORITY.DevelopmentPlanError,
            OSError, UnicodeError, KeyError,
        ):
            return False

    def _validate_recovery_packet(self, state, root, current, observed, packet):
        """Validate explicit Director authorization without inferring ownership from a diff."""
        keys = {"run_id", "feature", "generation", "base_tree_oid", "candidate_tree_oid", "authority_digest", "paths"}
        if not isinstance(packet, dict) or set(packet) != keys:
            raise PipelineError("recovery packet has an invalid shape")
        record = state["artifacts"].get("engineering", {})
        evidence = record.get("controller", {})
        if (state["active_assignment"] is not None or state["phase"] != "engineering"
                or terminal_blocked_context(state) is None
                or record.get("worker", {}).get("outcome") != "blocked"
                or record.get("controller_failure") is not None
                or evidence.get("violations") != []):
            raise PipelineError("recovery requires idle blocked Engineering with valid controller evidence")
        required_evidence = {"authority_digest", "pipeline_runtime_digest", "base_tree_oid",
                             "candidate_tree_oid", "changed_paths", "violations", "commands"}
        if (set(evidence) != required_evidence
                or evidence["authority_digest"] != state["authority"]["digest"]
                or evidence["pipeline_runtime_digest"] != state["pipeline_runtime_digest"]
                or not is_git_oid(evidence["base_tree_oid"])
                or not is_git_oid(evidence["candidate_tree_oid"])
                or not literal_paths_valid(evidence["changed_paths"])
                or evidence["commands"] != []
                or self._latest_controller_tree(state) != evidence["candidate_tree_oid"]
                or violations(evidence["changed_paths"], current_slice(state)["allowed_paths"])):
            raise PipelineError("recovery requires complete valid blocked Engineering controller evidence")
        if not authority_items_equal(observed, state["authority"]["items"]):
            raise PipelineError("recovery cannot adopt authority drift")
        _PLAN_AUTHORITY.require_approved_authority_chain(
            root, {name: item["path"] for name, item in observed.items()},
        )
        expected = {"run_id": state["run_id"], "feature": state["feature"],
                    "generation": state["generation"], "base_tree_oid": self._latest_controller_tree(state),
                    "candidate_tree_oid": current, "authority_digest": state["authority"]["digest"]}
        if any(packet.get(key) != value for key, value in expected.items()) or type(packet["generation"]) is not int:
            raise PipelineError("stale recovery packet binding; read status again")
        drift = self._checkout_drift(state, root, current)
        paths = packet["paths"]
        if not isinstance(paths, list) or not paths or any(not isinstance(item, dict) for item in paths):
            raise PipelineError("recovery requires exact path authorizations")
        if [item.get("path") for item in paths] != drift:
            raise PipelineError("recovery paths must exactly match observed checkout drift")
        scope = current_slice(state)["allowed_paths"]
        for item in paths:
            if set(item) != {"path", "kind", "authorization", "provenance"} or any(
                    not isinstance(item.get(key), str) or not item[key].strip()
                    for key in ("authorization", "provenance")):
                raise PipelineError("recovery requires per-path authorization and provenance")
            kind = "external_prerequisite" if violations([item["path"]], scope) else "retained_engineering"
            if item.get("kind") != kind:
                raise PipelineError("recovery path classification disagrees with approved Engineering scope")
        return deepcopy(packet)

    def _maintenance_binding(self, state, root, current, observed, runtime_digest):
        active = state["active_assignment"]
        if active is None or active["phase"] != "engineering":
            raise PipelineError("maintenance requires an active Engineering assignment")
        if runtime_digest == state["pipeline_runtime_digest"]:
            raise PipelineError("maintenance requires changed runtime bytes")
        if (not authority_items_equal(observed, state["authority"]["items"])
                or not slices_are_read_sealed(state)):
            raise PipelineError("maintenance cannot change approved authority or scope")
        drift = self._checkout_drift(state, root, current)
        if drift:
            raise PipelineError("maintenance cannot adopt foreign active changes: " + ", ".join(drift))
        if repository_policy_changed(root, state["base_tree_oid"], current):
            raise PipelineError("maintenance cannot change repository policy")
        output = safe_path(root, assignment_output_path(active, state["feature"]), "active output", strict=False)
        if output.exists():
            raise PipelineError("maintenance cannot discard an existing worker output")
        return {"run_id": state["run_id"], "feature": state["feature"],
                "generation": state["generation"], "assignment_id": active["id"],
                "candidate_tree_oid": current, "authority_digest": state["authority"]["digest"],
                "slice_digest": digest(current_slice(state)),
                "previous_runtime_digest": state["pipeline_runtime_digest"],
                "runtime_digest": runtime_digest}

    def _validate_maintenance_packet(self, state, root, current, observed, runtime_digest, packet):
        binding = self._maintenance_binding(state, root, current, observed, runtime_digest)
        if (not isinstance(packet, dict) or set(packet) != set(binding) | {"authorization", "quiescence"}
                or type(packet.get("generation")) is not int
                or any(packet.get(key) != value for key, value in binding.items())
                or any(not isinstance(packet.get(key), str) or not packet[key].strip()
                       for key in ("authorization", "quiescence"))):
            raise PipelineError("stale or incomplete maintenance authorization packet; read status --maintenance again")
        return deepcopy(packet)

    def _product_failure_binding(self, state, root, current, observed, runtime_digest):
        record = state["artifacts"].get("qa", {})
        candidate = record.get("candidate_binding") or {}
        if (state["phase"] != "qa" or terminal_blocked_context(state) is None
                or state["active_assignment"] is not None
                or candidate.get("candidate_tree_oid") != current
                or not authority_items_equal(observed, state["authority"]["items"])
                or self._checkout_drift(state, root, current)
                or repository_policy_changed(root, state["base_tree_oid"], current)):
            raise PipelineError("product failure requires unchanged terminal QA candidate and authority")
        return {"run_id": state["run_id"], "feature": state["feature"], "generation": state["generation"],
                "qa_assignment_id": record["assignment_id"], "candidate_tree_oid": current,
                "authority_digest": state["authority"]["digest"], "slice_digest": digest(current_slice(state)),
                "runtime_digest": runtime_digest}

    def _product_failure_evidence(self, state, root, packet):
        path = packet.get("evidence_path")
        if not isinstance(path, str) or not path.startswith(state["workflow_path"] + "/"):
            raise PipelineError("product failure evidence must be workflow-local")
        raw = safe_path(root, path, "product failure evidence", strict=True).read_bytes()
        if not raw.strip() or hashlib.sha256(raw).hexdigest() != packet.get("evidence_sha256"):
            raise PipelineError("product failure evidence is missing or stale")

    def _validate_product_failure(self, state, root, current, observed, runtime_digest, packet):
        binding = self._product_failure_binding(state, root, current, observed, runtime_digest)
        if (not isinstance(packet, dict) or set(packet) != set(binding) | {"authorization", "evidence_path", "evidence_sha256", "checks"}
                or type(packet.get("generation")) is not int
                or any(packet.get(key) != value for key, value in binding.items())
                or not isinstance(packet.get("authorization"), str) or not packet["authorization"].strip()):
            raise PipelineError("product failure requires exact binding and explicit authorization")
        self._product_failure_evidence(state, root, packet)
        try:
            worker = _worker_artifact({"outcome": "fail", "checks": packet["checks"]}, "qa", "qa")
        except WorkerArtifactValidationError as exc:
            raise PipelineError(str(exc)) from exc
        allowed = state["artifacts"]["qa"].get("required_identity_ids", [])
        if not worker["checks"] or any(item["outcome"] != "fail" or item["id"] not in allowed for item in worker["checks"]):
            raise PipelineError("product failure requires newly evidenced failed approved QA identities")
        return deepcopy(packet)

    def _verify_live_checkout(
        self, state: dict[str, Any], root: Path,
    ) -> str:
        current = candidate_tree_oid(root)
        policy = repository_policy_changed(root, state["base_tree_oid"], current)
        if policy:
            raise PipelineError(
                "repository policy changed during the run; perform a fresh init: "
                + ", ".join(policy)
            )
        drift = self._checkout_drift(state, root, current)
        if drift:
            if state["active_assignment"] is not None:
                raise PipelineError(f"candidate changed forbidden paths: {drift}")
            raise PipelineError(f"live checkout drifted from controller evidence: {drift}")
        return current

    def status(self, *, recovery: dict[str, Any] | None = None, maintenance: dict[str, Any] | None = None, product_failure: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return an executable action or a terminal recovery fact from one lock-bound observation."""
        self._preflight_existing_store_location()
        with self.store.transaction():
            state = self.store.load()
            validate_state(state)
            root = canonical_project_root(state["project_root"])
            self.store.validate_project_location(root, state["feature"])
            runtime_digest = pipeline_runtime_digest()
            runtime_changed = runtime_digest != state["pipeline_runtime_digest"]
            if runtime_changed and state["active_assignment"] is not None and maintenance is None:
                raise PipelineError(
                    "pipeline runtime changed during the run; stop and perform a fresh init"
                )
            paths = {
                name: item["path"] for name, item in state["authority"]["items"].items()
            }
            observed = authority_items(root, paths)
            authority_changed = not authority_items_equal(
                observed, state["authority"]["items"],
            )
            scope_changed = not slices_are_read_sealed(state)
            terminal_recovery = terminal_blocked_context(state)
            proposed_slices = None
            if authority_changed or scope_changed or runtime_changed:
                proposed_slices = seal_slices_from_approved_plan(
                    root, observed["plan"]["path"],
                    _unsealed_projection(state["slices"]),
                    state["feature"], rebind_stored_paths=True,
                )
                scope_changed = proposed_slices != state["slices"]
            current = candidate_tree_oid(root)
            policy = repository_policy_changed(root, state["base_tree_oid"], current)
            drift = self._checkout_drift(
                state, root, current, ignore_authority=authority_changed,
            )
            if product_failure is not None:
                if maintenance is not None or recovery is not None:
                    raise PipelineError("product failure cannot be combined with other recovery packets")
                binding = self._product_failure_binding(state, root, current, observed, runtime_digest)
                if proposed_slices is not None and proposed_slices != state["slices"]:
                    raise PipelineError("product failure cannot change scope")
                if product_failure == {}:
                    view = status_view(state)
                    view["next_action"] = {"kind": "terminal", "result": "product_failure_evidence_required",
                                           "product_failure_binding": binding}
                    return view
                product_failure = self._validate_product_failure(state, root, current, observed, runtime_digest, product_failure)
            if maintenance is not None:
                if recovery is not None:
                    raise PipelineError("maintenance and checkout recovery cannot be combined")
                binding = self._maintenance_binding(state, root, current, observed, runtime_digest)
                if proposed_slices is not None and proposed_slices != state["slices"]:
                    raise PipelineError("maintenance cannot change approved scope")
                if maintenance == {}:
                    view = status_view(state)
                    view["next_action"] = {"kind": "terminal", "result": "maintenance_authorization_required",
                        "maintenance_binding": binding,
                        "reason": "stop the worker; provide exact maintenance authorization and quiescence evidence"}
                    return view
                maintenance = self._validate_maintenance_packet(state, root, current, observed, runtime_digest, maintenance)
            admit_baseline = (
                self._can_admit_early_blocked_baseline(state, root, current, observed)
                if drift and not policy else False
            )
            if recovery is not None:
                if policy:
                    raise PipelineError("recovery cannot adopt repository policy drift")
                recovery = self._validate_recovery_packet(state, root, current, observed, recovery)
            view = status_view(state)
            if state["active_assignment"] is not None and state["phase"] == "engineering":
                view["technical_actions"] = {
                    "observed_tree_oid": current, "expected_generation": state["generation"],
                    "observation": "technical-observe", "decision": "technical-decision",
                }
            if policy:
                view["next_action"] = {
                    "kind": "terminal", "result": "fresh_init_required",
                    "reason": "repository policy changed: " + ", ".join(policy),
                }
            elif drift and not admit_baseline and recovery is None:
                view["next_action"] = {
                    "kind": "terminal", "result": "checkout_recovery_required",
                    "reason": f"restore or reconcile checkout drift before mutation: {drift}",
                    "recovery_binding": {"run_id": state["run_id"], "feature": state["feature"],
                        "generation": state["generation"], "base_tree_oid": self._latest_controller_tree(state),
                        "candidate_tree_oid": current, "authority_digest": state["authority"]["digest"],
                        "changed_paths": drift},
                }
            elif (
                authority_changed or scope_changed or runtime_changed
                or recovery is not None or maintenance is not None or product_failure is not None
                or admit_baseline
            ):
                action = reconfiguration_action(
                    state, observed, proposed_slices,
                    candidate_tree_oid=current,
                    pipeline_runtime_digest=runtime_digest, recovery=recovery, maintenance=maintenance, product_failure=product_failure,
                )
                if terminal_recovery is not None:
                    action.update({
                        **terminal_recovery,
                        "reason": (
                            "execute this exact init only after authority or capability evidence resolves "
                            "the recorded prerequisite under the shared stage-handoff invariant; "
                            "restart at plan and preserve terminal history"
                        ),
                        "user_input_required": True,
                    })
                    if admit_baseline:
                        action["reason"] += (
                            "; accept this committed prerequisite baseline only after explicit "
                            "authorization: the first blocked Engineering attempt recorded no product changes"
                        )
                if product_failure is not None:
                    action["reason"] = "record newly evidenced product failure and return terminal QA to Engineering without QA credit"
                view["next_action"] = action
            return view

    def next(self, *, command_id: str, assignment: dict[str, Any] | None = None, expected_generation: int | None = None) -> dict[str, Any]:
        _require_expected_generation(expected_generation)
        self._preflight_existing_store_location()
        with self.store.transaction():
            state, root = self._loaded()
            snapshot = self._verify_live_checkout(state, root)
            supplied = {} if assignment is None else canonical_command(assignment)
            prior = next(
                (item for item in state["history"] if item.get("id") == command_id),
                None,
            )
            if prior is not None:
                if prior.get("command") != "next":
                    # Preserve the common command-ID conflict path.
                    self.store._replay_locked({
                        "name": "next", "id": command_id, "assignment": {},
                    })
                issuance_generation = prior["generation"] - 1
                phase = next((
                    candidate for candidate in PHASES[:-1]
                    if command_id == (
                        f"next-{candidate}-g{issuance_generation}-"
                        f"{digest([state['run_id'], issuance_generation, candidate, 'next'])[:10]}"
                    )
                ), None)
                if phase is None:
                    raise PipelineError("recorded next command identity is malformed")
                historical = assignment_identity(
                    state["run_id"], issuance_generation, phase,
                )
                issued = prior.get("issued_identity")
                if isinstance(issued, dict):
                    historical = deepcopy(issued)
                else:
                    # Compatibility for a persisted assignment issued before
                    # owner aliases were recorded in next receipts.
                    active = state.get("active_assignment")
                    if isinstance(active, dict) and active.get("id") == historical["id"]:
                        historical["worker_id"] = active["worker_id"]
                    for event in state["history"]:
                        if event.get("assignment_id") == historical["id"] and isinstance(event.get("actor_id"), str):
                            historical["worker_id"] = event["actor_id"]
                for field in ("id", "worker_id", "task"):
                    if field in supplied and supplied[field] != historical[field]:
                        raise PipelineError(
                            f"assignment {field} is controller-derived and must match the recorded next command"
                        )
                historical_spec = deepcopy(historical)
                if "context" in supplied and phase != "review":
                    historical_spec["context"] = supplied["context"]
                replay = self.store._replay_locked({
                    "name": "next", "id": command_id,
                    "assignment": historical_spec,
                })
                if replay is not None:
                    return replay
            current_action = status_view(state)["next_action"]
            if current_action.get("result") == "no_progress_resolution_required":
                raise PipelineError("no-progress hold forbids unchanged Engineering redispatch; submit the bound specialist resolution through answer")
            if (
                current_action.get("command") != "next"
                or command_id != current_action.get("command_id")
            ):
                raise PipelineError(
                    "command ID is controller-derived and must match status.next_action"
                )
            canonical = default_assignment(state)
            for field in ("id", "worker_id", "task"):
                if field in supplied and supplied[field] != canonical[field]:
                    raise PipelineError(
                        f"assignment {field} is controller-derived and must match status.next_action"
                    )
            canonical_spec = {
                field: canonical[field] for field in ("id", "worker_id", "task")
            }
            if (
                state["phase"] == "review" and "context" in supplied
                and supplied["context"] != canonical["context"]
            ):
                raise PipelineError(
                    "review target is controller-derived and must match status.next_action"
                )
            if "context" in supplied and state["phase"] != "review":
                canonical_spec["context"] = supplied["context"]
            intent = {"name": "next", "id": command_id, "assignment": canonical_spec}
            command = {
                **intent,
                "expected_generation": state["generation"] if expected_generation is None else expected_generation,
                "controller_base": {"candidate_tree_oid": snapshot},
            }
            if state["phase"] == "qa":
                command["controller_machine_checks"] = self._machine_check_inputs(state, snapshot)
            if state["phase"] == "engineering":
                self._verify_producer_probes(state, root)
            return self.store._dispatch_locked(command)

    def reconfigure(self, command: dict[str, Any]) -> dict[str, Any]:
        """Apply init to an existing run, deriving any active-work interruption proof."""
        _require_expected_generation(command.get("expected_generation"))
        safe_identifier(command.get("run_id"))
        feature = feature_slug(command.get("feature"))
        if command.get("workflow_path") != workflow_relative_path(feature):
            raise PipelineError("init workflow_path does not match feature")
        proposed_root = canonical_project_root(command["project_root"])
        self.store.validate_project_location(proposed_root, feature)
        with self.store.transaction():
            state = self.store.load(required=False)
            value = deepcopy(command)
            recovery = value.get("recovery")
            maintenance = value.get("maintenance")
            product_failure = value.get("product_failure")
            if product_failure is not None and (maintenance is not None or recovery is not None):
                raise PipelineError("product failure cannot be combined with other recovery packets")
            if maintenance is not None and recovery is not None:
                raise PipelineError("maintenance and checkout recovery cannot be combined")
            supplied_paths = value.pop("authority_paths", None)
            root = canonical_project_root(value["project_root"])
            value["project_root"] = str(root)
            runtime_digest = pipeline_runtime_digest()
            if state is not None:
                validate_state(state)
                if runtime_digest != state["pipeline_runtime_digest"] and state["active_assignment"] is not None and maintenance is None:
                    raise PipelineError(
                        "pipeline runtime changed during the run; stop and perform a fresh init"
                    )
                if supplied_paths is not None:
                    expected_paths = {
                        name: item["path"]
                        for name, item in state["authority"]["items"].items()
                    }
                    if (
                        not isinstance(supplied_paths, dict)
                        or set(supplied_paths) != set(expected_paths)
                        or any(
                            not isinstance(supplied_paths[name], str)
                            or path_identity(supplied_paths[name])
                            != path_identity(expected_paths[name])
                            for name in expected_paths
                        )
                    ):
                        raise PipelineError(
                            "stale approved authority reconfiguration action; run status again"
                        )
            if supplied_paths is not None:
                value["authority"] = {"items": authority_items(root, supplied_paths)}
            proposed_items = value.get("authority", {}).get("items", {})
            if not isinstance(proposed_items, dict) or "plan" not in proposed_items:
                raise PipelineError("init requires controller-resolved authority paths")
            try:
                _PLAN_AUTHORITY.require_approved_authority_chain(
                    root, {name: item["path"] for name, item in proposed_items.items()},
                )
            except (_PLAN_AUTHORITY.DevelopmentPlanError, OSError, UnicodeError, KeyError) as error:
                raise PipelineError(
                    "approved authority chain is not ready; reconverge requirements, "
                    f"specification, and plan before init: {error}"
                ) from error
            if state is None and product_failure is not None:
                raise PipelineError("product failure requires an existing terminal QA")
            if state is None and maintenance is not None:
                raise PipelineError("maintenance requires an existing active run")
            if state is None and recovery is not None:
                raise PipelineError("recovery requires an existing blocked run")
            if state is None:
                value["slices"] = seal_slices_from_approved_plan(
                    root, proposed_items["plan"]["path"], value.get("slices"),
                    feature,
                )
            else:
                base_slices = _unsealed_projection(state["slices"])
                proposed_slices = seal_slices_from_approved_plan(
                    root, proposed_items["plan"]["path"], base_slices,
                    feature, rebind_stored_paths=True,
                )
                supplied_slices = value.get("slices")
                if supplied_slices not in (_unsealed_projection(proposed_slices), proposed_slices):
                    raise PipelineError(
                        "init slices must match the controller-projected status action"
                    )
                value["slices"] = proposed_slices
            supplied_contract = value.get("qa_contract")
            if supplied_contract is None and state is not None and authority_items_equal(proposed_items, state["authority"]["items"]):
                supplied_contract = state.get("execution", {}).get("qa_contract")
            contract = seal_qa_contract(root, proposed_items, value["slices"], supplied_contract)
            if contract is not None:
                value["qa_contract"] = contract
            contract_changed = state is not None and contract != state.get("execution", {}).get("qa_contract")
            if contract_changed and state["active_assignment"] is not None:
                raise PipelineError("QA contract cannot change during an active assignment; finish or use authorized maintenance first")
            current = require_clean_head(root) if state is None else candidate_tree_oid(root)
            admit_baseline = False
            if state is not None:
                policy = repository_policy_changed(root, state["base_tree_oid"], current)
                if policy:
                    raise PipelineError(
                        "repository policy changed during the run; perform a fresh init: "
                        + ", ".join(policy)
                    )
                authority_changed = not authority_items_equal(
                    value.get("authority", {}).get("items", {}),
                    state["authority"]["items"],
                )
                drift = self._checkout_drift(
                    state, root, current, ignore_authority=authority_changed,
                )
                if drift:
                    admit_baseline = self._can_admit_early_blocked_baseline(
                        state, root, current, value["authority"]["items"],
                    )
                if product_failure is not None:
                    prior = next((item for item in state["history"] if item.get("id") == value.get("id")), None)
                    if prior is not None:
                        if (prior.get("product_failure") != product_failure
                                or current != product_failure.get("candidate_tree_oid")
                                or runtime_digest != product_failure.get("runtime_digest")
                                or authority_changed or digest(current_slice(state)) != product_failure.get("slice_digest")):
                            raise PipelineError("stale product failure replay")
                        self._product_failure_evidence(state, root, product_failure)
                    else:
                        self._validate_product_failure(state, root, current, value["authority"]["items"], runtime_digest, product_failure)
                    if value["slices"] != state["slices"]:
                        raise PipelineError("product failure cannot change scope")
                if maintenance is not None:
                    prior = next((item for item in state["history"] if item.get("id") == value.get("id")), None)
                    if prior is not None:
                        if (prior.get("prior", {}).get("maintenance") != maintenance
                                or current != maintenance.get("candidate_tree_oid")
                                or runtime_digest != maintenance.get("runtime_digest")
                                or authority_changed or value["slices"] != state["slices"]):
                            raise PipelineError("stale maintenance replay")
                        output = safe_path(root, assignment_output_path(maintenance["assignment_id"], feature), "retired output", strict=False)
                        if output.exists():
                            raise PipelineError("maintenance cannot discard an existing worker output")
                    else:
                        self._validate_maintenance_packet(state, root, current, value["authority"]["items"], runtime_digest, maintenance)
                        if value["slices"] != state["slices"]:
                            raise PipelineError("maintenance cannot change approved scope")
                if recovery is not None:
                    prior = next((item for item in state["history"] if item.get("id") == value.get("id")), None)
                    if prior is not None:
                        if (prior.get("prior", {}).get("recovery") != recovery
                                or current != recovery.get("candidate_tree_oid")
                                or authority_changed or runtime_digest != state["pipeline_runtime_digest"]):
                            raise PipelineError("stale recovery replay")
                    else:
                        self._validate_recovery_packet(state, root, current, value["authority"]["items"], recovery)
                if drift and not admit_baseline and recovery is None:
                    if state.get("active_assignment") is not None:
                        raise PipelineError(f"candidate changed forbidden paths: {drift}")
                    raise PipelineError(f"live checkout drifted from controller evidence: {drift}")
                scope_changed = value["slices"] != state["slices"]
                terminal_recovery = terminal_blocked_context(state)
                if (terminal_recovery is not None and not authority_changed and not scope_changed
                        and runtime_digest == state["pipeline_runtime_digest"]
                        and recovery is None and not admit_baseline and product_failure is None and not contract_changed):
                    raise PipelineError("unchanged blocked bindings require recover-capability with fresh prerequisite evidence")
                if (
                    authority_changed or scope_changed
                    or runtime_digest != state["pipeline_runtime_digest"]
                    or (terminal_recovery is not None and not contract_changed)
                ):
                    expected = reconfiguration_action(
                        state, value["authority"]["items"], value.get("slices"),
                        candidate_tree_oid=current,
                        pipeline_runtime_digest=runtime_digest, recovery=recovery, maintenance=maintenance, product_failure=product_failure,
                    )
                    if value.get("id") != expected["command_id"]:
                        raise PipelineError(
                            "stale approved authority or scope reconfiguration action; run status again"
                        )
            value["pipeline_runtime_digest"] = runtime_digest
            value["controller_base"] = {
                "base_tree_oid": current,
                "candidate_tree_oid": current,
                "changed_paths": [],
            }
            if state is not None and state.get("active_assignment") is not None:
                active = state["active_assignment"]
                authority_paths = {
                    path_identity(item["path"])
                    for item in state["authority"]["items"].values()
                }
                changes = [
                    path for path in changed_paths(
                        root, active["base"]["candidate_tree_oid"], current,
                    )
                    if path_identity(path) not in authority_paths
                ]
                value["controller_interrupt"] = {
                    "base_tree_oid": active["base"]["candidate_tree_oid"],
                    "candidate_tree_oid": current,
                    "changed_paths": changes,
                    "violations": violations(changes, active["access"]["write"]),
                }
            if admit_baseline and require_clean_head(root) != current:
                raise PipelineError("committed prerequisite baseline changed; run status again")
            if maintenance is not None:
                output = safe_path(root, assignment_output_path(maintenance["assignment_id"], feature), "retired output", strict=False)
                if output.exists():
                    raise PipelineError("maintenance cannot discard an existing worker output")
            if product_failure is not None:
                self._product_failure_evidence(state, root, product_failure)
            if (recovery is not None or maintenance is not None or product_failure is not None) and candidate_tree_oid(root) != current:
                raise PipelineError("recovery checkout changed; read status again")
            verification = value.get("verification")
            if verification is None and state is not None:
                verification = state.get("execution", {}).get("verification")
            if verification is not None:
                value["verification"] = seal_verification(verification, value["slices"])
            if value.get("verification", {}).get("confirm_approved_plan"):
                from .model import authority_record
                # Init commands carry resolved items; the reducer's new_state
                # derives their digest. Use that same canonical authority in
                # this pre-dispatch preview, rather than a raw command shape.
                preview = {**value, "authority": authority_record(proposed_items),
                           "history": [], "artifacts": {}, "execution": {
                    "qa_contract": value.get("qa_contract"), "verification": value.get("verification", {})}}
                self._verify_producer_probes(preview, root)
            return self.store._dispatch_locked(value)

    def migrate(self, command: dict[str, Any]) -> dict[str, Any]:
        """Retain the public entry point as an explicit schema-10 tombstone."""
        raise PipelineError(SCHEMA10_UNSUPPORTED_MESSAGE)

    def transition(self, command: dict[str, Any]) -> dict[str, Any]:
        """Run a non-I/O transition only while its bound authority is still exact."""
        _require_expected_generation(command.get("expected_generation"))
        command = canonical_command(command)
        self._preflight_existing_store_location()
        with self.store.transaction():
            state, root = self._loaded()
            self._verify_live_checkout(state, root)
            replay = self.store._replay_locked(command)
            if replay is not None:
                return replay
            if command.get("name") == "accept" and state["phase"] == "slice":
                self._verify_producer_probes(state, root)
            if command.get("name") == "answer" and "resolution" in command:
                from .no_progress import verify_resolution_sources
                command["controller"] = {"resolution_sources": verify_resolution_sources(state, root, command)}
            if command.get("name") == "accept" and state["phase"] == "review":
                original = state["artifacts"].get("docs", {}).get("reusable_qa")
                if original is not None:
                    current_environment = verification_environment(current_slice(state)["planned_commands"], _process_environment(), state=state)
                    command["controller"] = {"pure_documentation_qa": current_environment is not None
                                              and current_environment == original.get("verification_environment")}
            return self.store._dispatch_locked(deepcopy(command))

    def read_status(self) -> dict[str, Any]:
        """Bound source reads validate state/access without a full checkout scan.

        Read access grants no credit. The source reader separately checks exact
        bytes/version; every mutation and terminal gate retains full guards.
        """
        self._preflight_existing_store_location()
        with self.store.transaction():
            state = self.store.load()
            validate_state(state)
            self.store.validate_project_location(canonical_project_root(state["project_root"]), state["feature"])
            return status_view(state)

    @staticmethod
    def _machine_check_row(result, locator, receipt_id):
        return machine_check_row(result, locator, receipt_id)

    def _machine_check_inputs(self, state, tree):
        """Publish only currently applicable canonical machine receipts to QA."""
        return machine_check_inputs(state, tree, _process_environment(), self.timeout)

    def control_action(self, name: str, *, command_id: str, expected_generation: int, **payload):
        """Bounded execution commands share the existing lock/CAS/reducer path."""
        if name not in {"check", "rotate-owner", "read-admit", "recover-capability", "reconcile"}:
            raise PipelineError("unknown execution action")
        _require_expected_generation(expected_generation)
        command = {"name": name, "id": command_id, "expected_generation": expected_generation, **deepcopy(payload)}
        self._preflight_existing_store_location()
        with self.store.transaction():
            state, root = self._loaded()
            current = candidate_tree_oid(root)
            if repository_policy_changed(root, state["base_tree_oid"], current):
                raise PipelineError("execution action cannot adopt repository policy drift")
            checked = self.store._preflight_locked(state, command)
            if isinstance(checked, dict):
                self._verify_live_checkout(state, root)
                return checked
            active = state["active_assignment"]
            if name != "reconcile":
                self._verify_live_checkout(state, root)
            if name == "check":
                if (active is None or active["phase"] not in {"engineering", "qa"} or payload.get("assignment_id") != active["id"]
                        or not isinstance(payload.get("quiescence"), str) or not payload["quiescence"].strip()):
                    raise PipelineError("check requires exact active Engineering/QA assignment and factual writer/session quiescence")
                if safe_path(root, active["output_path"], "worker output").exists():
                    raise PipelineError("terminal worker output exists; consume it before another diagnostic check")
                results, receipts = self._execute_checks(state, root, active, command_id,
                                                         collect_independent=bool(payload.get("collect_independent")))
                command["controller"] = {"assignment_id": active["id"], "candidate_tree_oid": current,
                                         "results": results, "grants_semantic_credit": False}
                command["controller_receipts"] = receipts
                rows = [self._machine_check_row(result,
                        f"{state['workflow_path']}/pipeline-state.json#/active_assignment/capsule/context/diagnostic_checks/results/{index}",
                        digest([command_id, index, result])) for index, result in enumerate(results)]
                command["controller_machine_checks"] = {
                    "candidate_tree_oid": current, "authority_digest": state["authority"]["digest"],
                    "pipeline_runtime_digest": state["pipeline_runtime_digest"], "checks": rows,
                    "pending_check_ids": [recipe_for(state, argv, index, self.timeout)["id"]
                                         for index, argv in enumerate(active["commands"]) if index >= len(results)],
                    "grants_manual_acceptance": False,
                }
            elif name == "read-admit":
                path = payload.get("path")
                if (active is None or not isinstance(path, str) or normalize_literal_path(path) != path
                        or "*" in path or not isinstance(payload.get("reason"), str) or not payload["reason"].strip()):
                    raise PipelineError("read admission requires an exact source and dependency reason")
                if any(part.casefold() in {".git", ".agentic-pipeline", ".agentic-pipeline-v2"} for part in path.split("/")):
                    raise PipelineError("read admission cannot access controller or foreign workflow paths")
                if not safe_path(root, path, "read dependency", strict=True).is_file():
                    raise PipelineError("read dependency must be an existing file")
                command["controller"] = {"path": path}
            elif name == "recover-capability":
                validate_capability_recovery(state, command)
            elif name == "reconcile":
                if active is not None:
                    raise PipelineError("external reconcile requires an idle assignment boundary")
                packet = payload.get("packet")
                binding = {"run_id": state["run_id"], "feature": state["feature"], "generation": state["generation"],
                           "candidate_tree_oid": current, "authority_digest": state["authority"]["digest"]}
                if (not isinstance(packet, dict) or set(packet) != set(binding) | {"paths"}
                        or any(packet.get(key) != value for key, value in binding.items())):
                    raise PipelineError("stale or malformed external reconcile binding")
                drift = self._checkout_drift(state, root, current)
                paths = packet["paths"]
                if (not isinstance(paths, list) or not drift
                        or [item.get("path") for item in paths if isinstance(item, dict)] != drift):
                    raise PipelineError("reconcile must enumerate exactly the observed external paths")
                from .no_progress import no_progress_hold
                if no_progress_hold(state) is not None:
                    relevant = default_assignment(state)["access"]["read"]
                    if not any(not violations([path], relevant) for path in drift):
                        raise PipelineError("no-progress hold cannot be cleared by unrelated external changes; resolve the bound work basis")
                for item in paths:
                    if set(item) != {"path", "authorization", "provenance"} or any(not isinstance(v, str) or not v.strip() for v in item.values()):
                        raise PipelineError("reconcile needs exact per-path authorization and provenance")
                from .model import completed_slice_ids
                completed = completed_slice_ids(state)
                affected = []
                for index, selected in enumerate(state["slices"]):
                    rules = selected["allowed_paths"] + selected.get("read_paths", [])
                    if any(not violations([path], rules) for path in drift):
                        affected.append(index)
                # Unmapped global inputs invalidate every slice conservatively.
                all_rules = [rule for item in state["slices"] for rule in item["allowed_paths"] + item.get("read_paths", [])]
                first = min(affected) if affected and not violations(drift, all_rules) else 0
                command["controller"] = {"candidate_tree_oid": current, "retained_prefix": completed[:first]}
            elif name == "rotate-owner":
                if active is not None or not isinstance(payload.get("reason"), str) or not payload["reason"].strip():
                    raise PipelineError("owner rotation requires idle state and durable handoff reason")
            verify_authority(root, state["authority"])
            if candidate_tree_oid(root) != current:
                raise PipelineError("candidate changed while executing the bound action")
            return self.store._dispatch_prechecked_locked(checked, command)

    def _execute_checks(self, state, root, active, action_id, *, collect_independent=False):
        from .execution_evidence import (_directory, input_snapshot, native_record, read,
                                         native_attempt, finish_native_attempt)
        results, new_receipts = [], {}
        environment = _process_environment()
        failed = False
        for index, argv in enumerate(active["commands"]):
            recipe = recipe_for(state, argv, index, self.timeout)
            if failed and not (collect_independent and recipe["independent"]):
                break
            before = candidate_tree_oid(root)
            binding = receipt_binding(state, before, recipe, environment)
            executable_before = executable_identity(argv, root=root, environment=environment)
            receipt = state.get("execution", {}).get("receipts", {}).get(binding)
            if receipt is not None:
                result = deepcopy(receipt["result"])
                result.update({"duration_ms": 0, "execution_reason": "unchanged_deterministic_inputs",
                               "source_receipt": receipt["id"]})
            else:
                record_id = "check-" + digest([state["run_id"], active["id"], action_id, index])[:40]
                directory = _directory(root, state["feature"], record_id)
                record_binding = self._evidence_binding(state, root, before)
                inputs_before = input_snapshot(root, recipe.get("input_paths", []))
                invocation = {"argv": argv, "check_id": recipe["id"], "action_id": action_id}
                stable_environment = {"process_environment_sha256": digest(environment),
                                      "input_closure_declared": "input_paths" in recipe, "executable": executable_before}
                attempt_request = {"binding": record_binding, "invocation": invocation, "recipe": recipe,
                                   "environment": stable_environment, "inputs": inputs_before, "reusable_binding": binding}
                result = native_attempt(root, state["feature"], record_id, attempt_request)
                if result is None:
                    started = time.monotonic()
                    stream_digests, capture_error = None, None
                    try:
                        execution_argv = [executable_before["path"], *argv[1:]] if executable_before else argv
                        process = run_process_tree(execution_argv, cwd=root, env=environment,
                                                   timeout=recipe["timeout_seconds"],
                                                   stdout_path=directory / "stdout.bin", stderr_path=directory / "stderr.bin")
                        capture_error = getattr(process, "capture_error", None)
                        if not all((directory / (name + ".bin")).is_file() for name in ("stdout", "stderr")):
                            capture_error = capture_error or "process returned without complete raw capture files"
                        stream_digests = {"stdout": process.stdout_sha256,
                                          "stderr": getattr(process, "stderr_raw_sha256", None) or process.stderr_sha256}
                        result = {"argv": argv, "returncode": TECHNICAL_FAILURE_RETURN_CODE if capture_error else process.returncode,
                                  "stdout_sha256": process.stdout_sha256, "stderr_sha256": process.stderr_sha256}
                        if capture_error:
                            result["process_returncode"] = process.returncode
                        if result["returncode"] != 0:
                            diagnostic = process.stderr_tail
                            if capture_error:
                                diagnostic += ("\nRaw capture failed after process execution: " + capture_error).encode("utf-8")
                            result.update(_stderr_excerpt(diagnostic, raw_truncated=process.stderr_tail_truncated,
                                                          environment=environment, project_root=root))
                            stdout = _stderr_excerpt(getattr(process, "stdout_tail", b""),
                                                      raw_truncated=getattr(process, "stdout_tail_truncated", False),
                                                      environment=environment, project_root=root)
                            result.update({key.replace("stderr", "stdout"): value for key, value in stdout.items()})
                    except OSError as exc:
                        capture_error = str(exc)
                        raw = capture_error.encode("utf-8", errors="replace")
                        result = {"argv": argv, "returncode": TECHNICAL_FAILURE_RETURN_CODE,
                                  "stdout_sha256": _stream_digest(b""), "stderr_sha256": _stream_digest(raw)}
                        result.update(_stderr_excerpt(raw, raw_truncated=False, environment=environment, project_root=root))
                    result.update({"duration_ms": max(0, int((time.monotonic() - started) * 1000)),
                                   "check_id": recipe["id"],
                                   "execution_reason": "environment_sensitive" if binding is None else "new_input_binding"})
                    # Sink failures are completed technical outcomes. Preserve
                    # the attempted action before any capture/state publication
                    # failure; exact retries recover or stop, never re-execute.
                    result["execution_evidence"] = native_record(root, state["feature"], record_id,
                        invocation=invocation, binding=record_binding, after_binding=self._evidence_binding(state, root),
                        environment=stable_environment, inputs_before=inputs_before,
                        after_environment={**stable_environment, "executable": executable_identity(argv, root=root, environment=environment)},
                        inputs_after=input_snapshot(root, recipe.get("input_paths", []), missing_ok=True),
                        result=result, stream_digests=stream_digests, capture_error=capture_error)
                    result["execution_record_digest"] = read(root, state["feature"], record_id)["record"]["digest"]
                    finish_native_attempt(root, state["feature"], record_id, result)
            result["check_id"] = recipe["id"]
            after = candidate_tree_oid(root)
            policy = repository_policy_changed(root, state["base_tree_oid"], after)
            if policy:
                raise PipelineError("planned command changed repository policy; perform a fresh init: " + ", ".join(policy))
            if after != before:
                raise PipelineError("planned command changed the Git candidate: " + ", ".join(changed_paths(root, before, after)))
            if executable_identity(argv, root=root, environment=environment) != executable_before:
                raise PipelineError("verification executable changed during the recorded command; do not replay that action against different executable bytes")
            if binding is not None and receipt_binding(state, after, recipe, environment) != binding:
                raise PipelineError("verification dependencies changed during the planned command; use a new action only after resolving the recorded input change")
            results.append(result)
            if result["returncode"] == 0 and binding is not None:
                new_receipts[binding] = {"binding": binding, "id": digest([action_id, index, binding]),
                                         "result": deepcopy(result), "candidate_tree_oid": before}
            if result["returncode"] != 0:
                failed = True
                if result["returncode"] in {124, TECHNICAL_FAILURE_RETURN_CODE} or not recipe["independent"]:
                    break
        return results, new_receipts

    def complete(self, *, command_id: str, artifact_path: Path | None = None, expected_generation: int | None = None) -> dict[str, Any]:
        _require_expected_generation(expected_generation)
        self._preflight_existing_store_location()
        with self.store.transaction():
            state, root = self._loaded()
            self._verify_live_checkout(state, root)
            active = state["active_assignment"]
            if active is None:
                prior = next((item for item in state["history"] if item.get("id") == command_id and item.get("command") == "complete"), None)
                if prior is None:
                    raise PipelineError("there is no active assignment")
                assignment_id = prior.get("assignment_id")
                assignment_phase = prior.get("phase")
            else:
                assignment_id = active["id"]
                assignment_phase = active["phase"]
            assigned_relative = assignment_output_path(assignment_id, state["feature"])
            assigned = safe_path(root, assigned_relative, "assigned artifact", strict=True)
            supplied = assigned if artifact_path is None else safe_path(root, artifact_path, "artifact path", strict=True)
            if supplied != assigned:
                raise PipelineError(f"complete accepts only the assigned artifact path {assigned_relative!r}")
            try:
                artifact = json.loads(assigned.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise PipelineError(f"cannot read assigned JSON artifact: {exc}") from exc
            if not isinstance(artifact, dict):
                raise PipelineError("assigned JSON artifact must be an object")
            if assignment_phase == "slice" and "slices" in artifact:
                artifact = deepcopy(artifact)
                artifact["slices"] = seal_slices_from_approved_plan(
                    root, state["authority"]["items"]["plan"]["path"],
                    artifact["slices"],
                    state["feature"],
                )
            intent = {"name": "complete", "id": command_id, "artifact": artifact}
            command = {
                **intent,
                "expected_generation": state["generation"] if expected_generation is None else expected_generation,
            }
            checked = self.store._preflight_locked(state, command)
            if isinstance(checked, dict):
                return checked
            if active is None:  # pragma: no cover - conflicting replay is reported above
                raise PipelineError("there is no active assignment")
            required_ids = (
                default_assignment(state)["context"]["required_identity_ids"]
                if active["phase"] == "qa" else None
            )
            if required_ids is not None and active["capsule"]["context"].get("required_identity_ids") != required_ids:
                raise PipelineError("QA assignment identities no longer match approved authority")
            artifact = _worker_artifact(artifact, active["phase"], active["role"], required_ids, state=state)
            from .execution_evidence import validate_references
            try:
                binding = self._evidence_binding(state, root)
                validate_references(root, state["feature"], artifact, binding, state=state)
                if active["phase"] == "qa":
                    from .qa_draft import validate_projection
                    validate_projection(state, root, binding, artifact)
            except (ValueError, OSError) as exc:
                raise WorkerArtifactValidationError(str(exc)) from exc
            results = []

            new_receipts = {}
            if artifact["outcome"] == "pass":
                results, new_receipts = self._execute_checks(state, root, active, command_id)
            command["controller_receipts"] = new_receipts
            command["controller_environment"] = verification_environment(active["commands"], _process_environment(), state=state)
            verify_authority(root, state["authority"])
            current = candidate_tree_oid(root)
            policy = repository_policy_changed(root, state["base_tree_oid"], current)
            if policy:
                raise PipelineError(
                    "repository policy changed during the run; perform a fresh init: "
                    + ", ".join(policy)
                )
            changes = changed_paths(
                root, _engineering_candidate_diff_base(state, active), current,
            )
            evidence = {
                "authority_digest": state["authority"]["digest"],
                "pipeline_runtime_digest": state["pipeline_runtime_digest"],
                "base_tree_oid": active["base"]["candidate_tree_oid"],
                "candidate_tree_oid": current,
                "changed_paths": changes,
                "violations": violations(changes, active["access"]["write"]),
                "commands": results,
            }
            command["controller"] = evidence
            return self.store._dispatch_prechecked_locked(checked, command)

    def ready(self, *, command_id: str, expected_generation: int | None = None) -> dict[str, Any]:
        _require_expected_generation(expected_generation)
        intent = {"name": "ready", "id": command_id}
        self._preflight_existing_store_location()
        with self.store.transaction():
            state, root = self._loaded()
            current = self._verify_live_checkout(state, root)
            replay = self.store._replay_locked(intent)
            if replay is not None:
                return replay
            command = {
                **intent,
                "expected_generation": state["generation"] if expected_generation is None else expected_generation,
                "controller": {
                    "candidate_tree_oid": current,
                    "pipeline_runtime_digest": state["pipeline_runtime_digest"],
                },
            }
            return self.store._dispatch_locked(command)

    def technical_action(self, *, command_id: str, expected_generation: int,
                         action: str | None = None, packet: dict[str, Any] | None = None) -> dict[str, Any]:
        """Observe a sole-writer action or apply a precise technical amendment.

        An observation is captured before editor work. Reconciliation admits only
        exact foreign paths appearing since that observation, never earlier drift.
        Semantic necessity remains subject to independent Review and QA.
        """
        self._preflight_existing_store_location()
        with self.store.transaction():
            state, root = self._loaded()
            name = "technical-observe" if action is not None else "technical-decision"
            intent = {"name": name, "id": command_id, "packet": deepcopy(packet), "action": action}
            command = {**intent, "expected_generation": expected_generation}
            checked = self.store._preflight_locked(state, command)
            current = candidate_tree_oid(root)
            if repository_policy_changed(root, state["base_tree_oid"], current):
                raise PipelineError("technical action cannot change repository policy")
            if isinstance(checked, dict):
                self._verify_live_checkout(state, root)
                return checked
            active = state["active_assignment"]
            if active is None or active["phase"] != "engineering":
                raise PipelineError("technical action requires the current Engineering assignment")
            if action is not None:
                if not isinstance(action, str) or not action.strip():
                    raise PipelineError("technical observation requires an action description")
                self._verify_live_checkout(state, root)
                command["controller"] = {"tree": current, "action": action}
            else:
                if not isinstance(packet, dict) or not {"assignment_id", "observed_tree_oid", "entry"} <= set(packet) or set(packet) - {"assignment_id", "observed_tree_oid", "entry", "additional_paths", "command_order", "observation_id"}:
                    raise PipelineError("malformed technical decision packet")
                if packet["assignment_id"] != active["id"] or packet["observed_tree_oid"] != current:
                    raise PipelineError("technical packet assignment or observed tree is stale")
                try:
                    entry = validate_entry(packet["entry"])
                except ValueError as exc:
                    raise PipelineError(str(exc)) from exc
                previous = state.get("technical_decisions", {}).get(entry["id"], {}).get("execution", {})
                if previous and (previous["slice_id"] != current_slice(state)["id"] or previous["authority"] != state["authority"]["digest"]):
                    previous = {}  # Reassess this same situation; never inherit a stale execution grant.
                paths = packet.get("additional_paths", previous.get("additional_paths", []))
                if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
                    raise PipelineError("additional_paths must contain exact project-relative files")
                if len(paths) != len(set(paths)):
                    raise PipelineError("additional_paths contains duplicates")
                authority = {path_identity(item["path"]) for item in state["authority"]["items"].values()}
                for path in paths:
                    if normalize_literal_path(path) != path or "*" in path or path_identity(path) in authority:
                        raise PipelineError("technical amendment cannot grant authority or wildcard paths")
                    parts = path.replace("\\", "/").split("/")
                    if any(part.casefold() in {".git", ".agentic-pipeline", ".agentic-pipeline-v2", ".gitignore", ".gitattributes", ".gitmodules", "agents.md"} for part in parts):
                        raise PipelineError("technical amendment cannot grant control or policy paths")
                    target = safe_path(root, path, "technical additional path")
                    if target.is_dir():
                        raise PipelineError("technical amendment requires exact files, not directories")
                order = packet.get("command_order", previous.get("command_order", []))
                if order:
                    if not isinstance(order, list) or sorted(json.dumps(item, sort_keys=True) for item in order) != sorted(json.dumps(item, sort_keys=True) for item in active["commands"]):
                        raise PipelineError("command_order must be a permutation preserving every mandatory check")
                elif "command_order" in packet:
                    raise PipelineError("command_order cannot remove mandatory checks")
                foreign = self._checkout_drift(state, root, current)
                if foreign:
                    observation = active.get("technical_observation", {})
                    if packet.get("observation_id") != observation.get("id") or not observation:
                        raise PipelineError("foreign paths require a controller observation captured before the action")
                    since = changed_paths(root, observation["tree"], current)
                    if set(foreign) - set(paths) or set(foreign) - set(since):
                        raise PipelineError("reconciliation must cover the exact observed foreign paths")
                    # An unmentioned foreign change must never be adopted through a wider overlay.
                    if set(violations(since, active["access"]["write"])) != set(foreign):
                        raise PipelineError("reconciliation contains unrelated or previously owned foreign changes")
                entry["execution"] = {"slice_id": current_slice(state)["id"], "authority": state["authority"]["digest"],
                                      "additional_paths": paths, "command_order": order}
                projected = deepcopy(state)
                projected.setdefault("technical_decisions", {})[entry["id"]] = entry
                allowed = default_assignment(projected)["access"]["write"]
                all_changes = changed_paths(root, _engineering_candidate_diff_base(state, active), current)
                if violations(all_changes, allowed):
                    raise PipelineError("technical amendment leaves changed paths outside the effective scope")
                command["controller"] = {"entry": entry}
            command["controller"]["assignment_id"] = active["id"]
            return self.store._dispatch_prechecked_locked(checked, command)
