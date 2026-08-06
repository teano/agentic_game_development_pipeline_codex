#!/usr/bin/env python3
"""Deterministic state controller for the agentic GameDev pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATE_DIR = ".agentic-pipeline"
SCHEMA_VERSION = 3
CONTRACT_VERSION = "2026-08-04-review-qa-v1"
BLOCKING_SEVERITIES = {"critical", "major"}
FINDING_KINDS = {"product", "evidence"}
PASSED_REVIEW_STATUSES = {"passed", "passed_recovery"}
DEFAULT_MAX_CONSECUTIVE_PRODUCT_CHANGES = 2
QA_STATUSES = {
    "pass",
    "fail_product",
    "blocked_user",
    "blocked_environment",
    "error_test",
}
QA_GATE_STATUSES = {"blocked_user", "blocked_environment", "error_test"}


class PipelineError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def runtime_paths(project_root: str) -> tuple[Path, Path, Path]:
    root = Path(project_root).resolve()
    return root, root / STATE_DIR / "state.json", root / STATE_DIR / "findings.json"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_frontmatter(path: Path, label: str) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise PipelineError(f"{label} must contain YAML front matter: {path}")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise PipelineError(f"{label} has unterminated YAML front matter: {path}")
    result: dict[str, str] = {}
    for raw_line in parts[1].splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#") or ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        result[key.strip()] = value.strip().strip('"\'')
    return result


def require_feature_slug(feature: str) -> str:
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", feature):
        raise PipelineError(
            "feature must be a lowercase hyphen slug such as teleport-module"
        )
    return feature


def resolve_project_file(root: Path, supplied: str, label: str) -> Path:
    path = Path(supplied)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if not path.is_file():
        raise PipelineError(f"{label} does not exist: {path}")
    return path


def require_feature_documents(
    root: Path, feature: str, requirements: Path, spec: Path
) -> tuple[dict[str, str], dict[str, str]]:
    feature_dir = (root / "docs" / "features" / feature).resolve()
    expected_requirements = feature_dir / "product-requirements.md"
    expected_spec = feature_dir / "technical-specification.md"
    if requirements != expected_requirements:
        raise PipelineError(
            f"Approved product requirements must be stored at {expected_requirements}"
        )
    if spec != expected_spec:
        raise PipelineError(
            f"Approved technical specification must be stored at {expected_spec}"
        )

    requirements_meta = parse_frontmatter(requirements, "Product requirements")
    if requirements_meta.get("status") != "approved":
        raise PipelineError("product-requirements.md must have status: approved")
    if not requirements_meta.get("revision"):
        raise PipelineError("product-requirements.md must record revision")

    spec_meta = parse_frontmatter(spec, "Technical specification")
    if spec_meta.get("status") != "approved":
        raise PipelineError("technical-specification.md must have status: approved")

    relative_requirements = requirements.relative_to(root).as_posix()
    expected_trace = {
        "source_prd_path": relative_requirements,
        "source_prd_revision": requirements_meta["revision"],
        "source_prd_sha256": file_sha256(requirements),
    }
    for field, expected in expected_trace.items():
        if spec_meta.get(field) != expected:
            raise PipelineError(
                f"technical-specification.md has stale {field}: "
                f"expected {expected!r}, got {spec_meta.get(field)!r}"
            )
    return requirements_meta, spec_meta


def ensure_test_artifact_layout(root: Path, feature: str) -> Path:
    tests_root = (root / "tests" / feature).resolve()
    for child in ("verification", "reviews", "qa"):
        (tests_root / child).mkdir(parents=True, exist_ok=True)

    gitignore = root / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    active_lines = {
        line.strip()
        for line in existing.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    if "/tests/" not in active_lines:
        separator = "" if not existing or existing.endswith(("\n", "\r")) else "\n"
        gitignore.write_text(existing + separator + "/tests/\n", encoding="utf-8")
    return tests_root


def source_drift(state: dict[str, Any]) -> list[str]:
    drift: list[str] = []
    for label in ("requirements", "spec"):
        path = Path(state[f"{label}_path"])
        if not path.is_file():
            drift.append(f"{label} file is missing")
        elif file_sha256(path) != state[f"{label}_sha256"]:
            drift.append(f"{label} file changed after pipeline initialization")
    return drift


def require_sources_current(state: dict[str, Any]) -> None:
    drift = source_drift(state)
    if drift:
        raise PipelineError("; ".join(drift))


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise PipelineError(f"Missing pipeline file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"Cannot read valid JSON from {path}: {exc}") from exc


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def normalize_runtime(state: dict[str, Any], findings: dict[str, Any]) -> None:
    """Add current optional fields without invalidating schema-v3 runs."""
    state.setdefault("product_revision", state.get("revision"))
    state.setdefault("evidence_revision", state.get("revision"))
    state.setdefault("coverage_manifest", None)
    iteration = state.setdefault("iteration_control", {})
    authorizations = iteration.setdefault("authorizations", [])
    boundary_times = [
        run.get("recorded_at", "")
        for run in state.get("engineer_runs", [])
        if run.get("outcome") == "clean"
    ]
    boundary_times.extend(
        item.get("recorded_at", "")
        for item in authorizations
        if item.get("phase") == "convergence_hold"
    )
    boundary = max(boundary_times, default="")
    derived_changes = sum(
        1
        for run in state.get("engineer_runs", [])
        if run.get("outcome") in {"changed", "product_changed"}
        and run.get("recorded_at", "") > boundary
    )
    iteration.setdefault("consecutive_product_changes", derived_changes)
    iteration.setdefault(
        "max_consecutive_product_changes",
        iteration.get(
            "max_automatic_product_changes", DEFAULT_MAX_CONSECUTIVE_PRODUCT_CHANGES
        ),
    )
    iteration.pop("automatic_product_changes", None)
    iteration.pop("max_automatic_product_changes", None)
    if iteration.get("status") == "approval_required":
        iteration["status"] = "checkpoint_required"
    iteration.setdefault("status", "running")
    iteration.setdefault("reason", None)
    if (
        state.get("phase") == "convergence_hold"
        and iteration["consecutive_product_changes"]
        < iteration["max_consecutive_product_changes"]
    ):
        state["phase"] = "engineering"
        iteration["status"] = "running"
        iteration["reason"] = None
    state.setdefault("recovery", None)

    for run in state.get("engineer_runs", []):
        run.setdefault("product_revision", run.get("revision"))
        run.setdefault("evidence_revision", run.get("revision"))
        run.setdefault("change_class", "product" if run.get("outcome") == "changed" else "none")
    clean = state.get("engineer_clean")
    if clean:
        clean.setdefault("product_revision", clean.get("revision"))
        clean.setdefault("evidence_revision", clean.get("revision"))
    machine = state.get("machine_checks", {})
    machine.setdefault("product_revision", machine.get("revision"))
    machine.setdefault("evidence_revision", machine.get("revision"))
    review = state.get("review", {})
    review.setdefault("product_revision", review.get("revision"))
    review.setdefault("evidence_revision", review.get("revision"))
    review.setdefault("recovery_run", None)
    for item in findings.get("items", []):
        item.setdefault("kind", "product")


def load_runtime(project_root: str) -> tuple[Path, Path, Path, dict[str, Any], dict[str, Any]]:
    root, state_path, findings_path = runtime_paths(project_root)
    state = read_json(state_path)
    findings = read_json(findings_path)
    if state.get("schema_version") != SCHEMA_VERSION or findings.get("schema_version") != SCHEMA_VERSION:
        raise PipelineError("Unsupported pipeline state; reinitialize it for the Review workflow")
    if state.get("contract_version") != CONTRACT_VERSION:
        raise PipelineError("Pipeline contract changed after initialization; reinitialize explicitly")
    normalize_runtime(state, findings)
    return root, state_path, findings_path, state, findings


def save_runtime(
    state_path: Path,
    findings_path: Path,
    state: dict[str, Any],
    findings: dict[str, Any],
) -> None:
    state["updated_at"] = utc_now()
    write_json(state_path, state)
    write_json(findings_path, findings)


def open_blocking(findings: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in findings["items"]
        if item["status"] == "open" and item["severity"] in BLOCKING_SEVERITIES
    ]


def empty_review_state(
    required: int,
    revision: str | None = None,
    product_revision: str | None = None,
    evidence_revision: str | None = None,
) -> dict[str, Any]:
    return {
        "status": "pending",
        "revision": revision,
        "product_revision": product_revision if product_revision is not None else revision,
        "evidence_revision": evidence_revision if evidence_revision is not None else revision,
        "required": required,
        "runs": [],
        "recovery_run": None,
        "decision": None,
        "decision_report": None,
        "decision_reason": None,
    }


def empty_qa_state() -> dict[str, Any]:
    return {
        "status": "pending",
        "revision": None,
        "product_revision": None,
        "evidence_revision": None,
        "run_id": None,
        "report": None,
        "pending_scenarios": [],
        "reason": None,
    }


def invalidate_open_gates(state: dict[str, Any], reason: str) -> None:
    for gate in state.get("gates", []):
        if gate.get("status") == "open":
            gate["status"] = "invalidated"
            gate["resolved_at"] = utc_now()
            gate["resolution"] = reason


def reset_validation(
    state: dict[str, Any],
    revision: str | None = None,
    product_revision: str | None = None,
    evidence_revision: str | None = None,
) -> None:
    state["engineer_clean"] = None
    state["review"] = empty_review_state(
        state["required_reviews"], revision, product_revision, evidence_revision
    )
    state["qa"] = empty_qa_state()
    invalidate_open_gates(state, "product revision changed")


def require_current_revision(state: dict[str, Any], revision: str) -> None:
    if not state.get("revision"):
        raise PipelineError("No Engineer revision has been recorded")
    if revision != state["revision"]:
        raise PipelineError(
            f"Revision mismatch: current={state['revision']!r}, supplied={revision!r}"
        )


def require_current_identity(
    state: dict[str, Any],
    revision: str,
    product_revision: str | None = None,
    evidence_revision: str | None = None,
) -> None:
    require_current_revision(state, revision)
    if product_revision is not None and product_revision != state.get("product_revision"):
        raise PipelineError(
            "Product revision mismatch: "
            f"current={state.get('product_revision')!r}, supplied={product_revision!r}"
        )
    if evidence_revision is not None and evidence_revision != state.get("evidence_revision"):
        raise PipelineError(
            "Evidence revision mismatch: "
            f"current={state.get('evidence_revision')!r}, supplied={evidence_revision!r}"
        )


def resolve_report(root: Path, state: dict[str, Any], supplied: str, label: str) -> str:
    report = Path(supplied)
    if not report.is_absolute():
        report = root / report
    report = report.resolve()
    tests_root = Path(state["tests_path"]).resolve()
    try:
        report.relative_to(tests_root)
    except ValueError as exc:
        raise PipelineError(f"{label} must be stored under {tests_root}") from exc
    if not report.is_file():
        raise PipelineError(f"{label} does not exist: {report}")
    return str(report)


def resolve_coverage_manifest(
    root: Path,
    state: dict[str, Any],
    supplied: str,
    product_revision: str,
    evidence_revision: str,
) -> str:
    manifest_path = resolve_report(root, state, supplied, "Coverage manifest")
    manifest = read_json(Path(manifest_path))
    if manifest.get("schema_version") != 1:
        raise PipelineError("Coverage manifest must use schema_version 1")
    if manifest.get("product_revision") != product_revision:
        raise PipelineError("Coverage manifest product_revision does not match the pass")
    if manifest.get("evidence_revision") != evidence_revision:
        raise PipelineError("Coverage manifest evidence_revision does not match the pass")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        raise PipelineError("Coverage manifest must contain at least one requirement entry")
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise PipelineError("Every coverage entry must have a string id")
        entry_id = entry["id"]
        if entry_id in seen:
            raise PipelineError(f"Duplicate coverage entry: {entry_id}")
        seen.add(entry_id)
        status = entry.get("status")
        if status not in {"covered", "finding", "not_applicable"}:
            raise PipelineError(f"Coverage entry {entry_id} has invalid status")
        if status == "covered":
            if not entry.get("implementation_evidence"):
                raise PipelineError(
                    f"Covered entry {entry_id} must record implementation_evidence"
                )
            tests = entry.get("tests")
            if not isinstance(tests, list) or not tests:
                raise PipelineError(f"Covered entry {entry_id} must record exact tests")
            for test in tests:
                required = {"file", "suite", "symbol", "assertions", "execution", "evidence"}
                if not isinstance(test, dict) or any(not test.get(field) for field in required):
                    raise PipelineError(
                        f"Coverage entry {entry_id} has an incomplete exact-test record"
                    )
        elif status == "finding" and not entry.get("finding_ids"):
            raise PipelineError(f"Finding entry {entry_id} must record finding_ids")
        elif status == "not_applicable" and not entry.get("reason"):
            raise PipelineError(f"Not-applicable entry {entry_id} must record a reason")
    return manifest_path


def resolve_input_file(root: Path, supplied: str, label: str) -> tuple[Path, str]:
    path = Path(supplied)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise PipelineError(f"{label} must be inside {root}") from exc
    if not path.is_file():
        raise PipelineError(f"{label} does not exist: {path}")
    if relative == STATE_DIR or relative.startswith(f"{STATE_DIR}/"):
        raise PipelineError(f"{label} must not include controller state")
    return path, relative


def revision_for_domain(base_revision: str, records: list[dict[str, str]]) -> str:
    payload = f"base:{base_revision}\n" + "".join(
        f"{record['path']}\0{record['sha256']}\n"
        for record in sorted(records, key=lambda item: item["path"])
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cmd_compute_revisions(args: argparse.Namespace) -> int:
    root, _, _, state, _ = load_runtime(args.project_root)
    require_sources_current(state)
    domains: dict[str, list[dict[str, str]]] = {"product": [], "evidence": []}
    assigned: dict[str, str] = {}
    for domain, supplied_files in (
        ("product", args.product_file or []),
        ("evidence", args.evidence_file or []),
    ):
        for supplied in supplied_files:
            path, relative = resolve_input_file(root, supplied, f"{domain} file")
            if relative in assigned:
                previous = assigned[relative]
                if previous == domain:
                    raise PipelineError(
                        f"Revision input {relative} is duplicated in {domain}"
                    )
                raise PipelineError(
                    f"Revision input {relative} is assigned to both {previous} and {domain}"
                )
            assigned[relative] = domain
            domains[domain].append({"path": relative, "sha256": file_sha256(path)})

    product_revision = revision_for_domain(args.base_revision, domains["product"])
    evidence_revision = revision_for_domain(args.base_revision, domains["evidence"])
    revision = hashlib.sha256(
        (
            f"product:{product_revision}\n"
            f"evidence:{evidence_revision}\n"
        ).encode("utf-8")
    ).hexdigest()
    result = {
        "schema_version": 1,
        "base_revision": args.base_revision,
        "product_files": sorted(domains["product"], key=lambda item: item["path"]),
        "evidence_files": sorted(domains["evidence"], key=lambda item: item["path"]),
        "product_revision": product_revision,
        "evidence_revision": evidence_revision,
        "revision": revision,
    }
    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = root / output
        output = output.resolve()
        verification_root = Path(state["tests_path"]).resolve() / "verification"
        try:
            output_relative = output.relative_to(root).as_posix()
            output.relative_to(verification_root)
        except ValueError as exc:
            raise PipelineError(
                f"Revision manifest must be stored under {verification_root}"
            ) from exc
        if output_relative in assigned:
            raise PipelineError("Revision manifest cannot hash itself as a revision input")
        output.parent.mkdir(parents=True, exist_ok=True)
        write_json(output, result)
        result["manifest"] = str(output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def resolve_product_findings(
    findings: dict[str, Any],
    resolved_ids: set[str],
    revision: str,
    product_revision: str,
    evidence_revision: str,
) -> None:
    for finding_id in resolved_ids:
        target = next(
            (item for item in findings["items"] if item["id"] == finding_id), None
        )
        if target is None:
            raise PipelineError(f"Unknown finding ID: {finding_id}")
        if target.get("status") != "open":
            raise PipelineError(f"Finding is not open: {finding_id}")
        if target.get("kind") != "product":
            raise PipelineError(
                f"Full engineering can resolve only product findings: {finding_id}"
            )
        target["status"] = "resolved"
        target["resolved_revision"] = revision
        target["resolved_product_revision"] = product_revision
        target["resolved_evidence_revision"] = evidence_revision
        target["resolved_at"] = utc_now()


def next_action(
    state: dict[str, Any], findings: dict[str, Any] | None = None
) -> dict[str, Any]:
    phase = state.get("phase")
    if source_drift(state):
        return {
            "action": "reconcile_source_drift",
            "owner": "technical_director",
            "user_input_required": False,
        }
    if phase == "engineering":
        return {
            "action": "spawn_full_engineer",
            "owner": "technical_director",
            "user_input_required": False,
        }
    if phase in {"convergence_hold", "recovery_hold"}:
        return {
            "action": "director_checkpoint",
            "owner": "technical_director",
            "user_input_required": False,
        }
    if phase == "review":
        action = (
            "finalize_review"
            if state.get("review", {}).get("status") == "awaiting_decision"
            else "complete_parallel_reviews"
        )
        return {
            "action": action,
            "owner": "technical_director",
            "user_input_required": False,
        }
    if phase == "evidence_recovery":
        return {
            "action": "run_evidence_remediation",
            "owner": "technical_director",
            "user_input_required": False,
        }
    if phase == "recovery_review":
        return {
            "action": "run_recovery_review",
            "owner": "technical_director",
            "user_input_required": False,
        }
    if phase == "qa":
        gates = [
            gate for gate in state.get("gates", []) if gate.get("status") == "open"
        ]
        user_gate = any(gate.get("category") == "blocked_user" for gate in gates)
        return {
            "action": "resolve_qa_gate" if gates else "run_or_resume_qa",
            "owner": "user" if user_gate else "technical_director",
            "user_input_required": user_gate,
        }
    if phase == "ready":
        open_minor = [
            item
            for item in (findings or {}).get("items", [])
            if item.get("status") == "open" and item.get("severity") == "minor"
        ]
        if open_minor:
            return {
                "action": "request_residual_risk_decision",
                "owner": "user",
                "user_input_required": True,
                "finding_ids": sorted(item["id"] for item in open_minor),
            }
        return {
            "action": "run_ready",
            "owner": "technical_director",
            "user_input_required": False,
        }
    return {
        "action": "inspect_state",
        "owner": "technical_director",
        "user_input_required": False,
    }


def cmd_init(args: argparse.Namespace) -> int:
    root, state_path, findings_path = runtime_paths(args.project_root)
    if not root.is_dir():
        raise PipelineError(f"Project root does not exist: {root}")
    if state_path.exists() or findings_path.exists():
        raise PipelineError(f"Pipeline is already initialized under {state_path.parent}")
    feature = require_feature_slug(args.feature)
    if args.required_reviews != 2:
        raise PipelineError("required-reviews must be exactly 2")
    if args.max_consecutive_product_changes < 1:
        raise PipelineError("max-consecutive-product-changes must be positive")

    requirements = resolve_project_file(root, args.requirements, "Approved product requirements")
    spec = resolve_project_file(root, args.spec, "Approved technical specification")
    requirements_meta, _ = require_feature_documents(root, feature, requirements, spec)
    tests_root = ensure_test_artifact_layout(root, feature)

    now = utc_now()
    state = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "project_root": str(root),
        "feature": feature,
        "slice_id": args.slice,
        "requirements_path": str(requirements),
        "requirements_revision": requirements_meta["revision"],
        "requirements_sha256": file_sha256(requirements),
        "spec_path": str(spec),
        "spec_sha256": file_sha256(spec),
        "tests_path": str(tests_root),
        "phase": "engineering",
        "revision": None,
        "product_revision": None,
        "evidence_revision": None,
        "coverage_manifest": None,
        "last_engineer_run_id": None,
        "last_engineer_outcome": None,
        "machine_checks": {
            "status": "pending",
            "revision": None,
            "report": None,
        },
        "engineer_clean": None,
        "engineer_runs": [],
        "required_reviews": args.required_reviews,
        "review": empty_review_state(args.required_reviews),
        "review_runs": [],
        "qa": empty_qa_state(),
        "qa_runs": [],
        "gates": [],
        "iteration_control": {
            "consecutive_product_changes": 0,
            "max_consecutive_product_changes": args.max_consecutive_product_changes,
            "status": "running",
            "reason": None,
            "authorizations": [],
        },
        "recovery": None,
        "created_at": now,
        "updated_at": now,
    }
    findings = {"schema_version": SCHEMA_VERSION, "items": []}
    write_json(state_path, state)
    write_json(findings_path, findings)
    print(
        json.dumps(
            {
                "initialized": True,
                "state": str(state_path),
                "feature_docs": str(requirements.parent),
                "test_artifacts": str(tests_root),
            },
            ensure_ascii=False,
        )
    )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    _, _, _, state, findings = load_runtime(args.project_root)
    counts = {"critical": 0, "major": 0, "minor": 0}
    for item in findings["items"]:
        if item["status"] == "open":
            counts[item["severity"]] += 1
    gate_counts = {status: 0 for status in sorted(QA_GATE_STATUSES)}
    for gate in state.get("gates", []):
        if gate.get("status") == "open":
            gate_counts[gate["category"]] += 1
    result = {
        "feature": state["feature"],
        "slice": state["slice_id"],
        "revision": state["revision"],
        "product_revision": state["product_revision"],
        "evidence_revision": state["evidence_revision"],
        "phase": state["phase"],
        "last_engineer_outcome": state["last_engineer_outcome"],
        "machine_checks": state["machine_checks"],
        "engineer_clean": state["engineer_clean"],
        "review": state["review"],
        "qa": state["qa"],
        "iteration_control": state["iteration_control"],
        "recovery": state["recovery"],
        "open_findings": counts,
        "open_gates": gate_counts,
        "source_drift": source_drift(state),
        "next_action": next_action(state, findings),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_engineer_complete(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    if state["phase"] != "engineering":
        raise PipelineError("Full Engineer completion is valid only in the engineering phase")
    if not args.audit_complete:
        raise PipelineError("Engineer pass cannot complete before the full audit-remediation-resweep gate")
    if any(run["run_id"] == args.run_id for run in state["engineer_runs"]):
        raise PipelineError(f"Engineer run ID already recorded: {args.run_id}")
    if state["iteration_control"].get("status") == "checkpoint_required":
        raise PipelineError(
            "Automatic convergence circuit breaker is open; run authorize-iteration first"
        )
    report = resolve_report(root, state, args.report, "Engineer verification report")

    input_revision = state.get("revision")
    input_product_revision = state.get("product_revision")
    input_evidence_revision = state.get("evidence_revision")
    product_revision = args.product_revision or args.revision
    evidence_revision = args.evidence_revision or args.revision
    product_changed = input_product_revision != product_revision
    evidence_changed = input_evidence_revision != evidence_revision
    revision_changed = input_revision != args.revision
    if not product_changed and (revision_changed or evidence_changed):
        raise PipelineError(
            "Evidence-only changes must use evidence-remediation-complete; "
            "a full Engineer pass must not invalidate clean product evidence"
        )
    if product_changed and args.machine_checks != "pass":
        raise PipelineError(
            "A product-changing Engineer must resume until required checks pass"
        )
    if product_changed and args.production_change_scope == "none":
        raise PipelineError("A product change must be classified as local or architectural")
    if not product_changed and args.production_change_scope != "none":
        raise PipelineError("An unchanged product pass must use production-change-scope none")
    if args.production_change_scope == "architectural" and not args.scope_approval:
        raise PipelineError(
            "Architectural or lifecycle scope expansion requires --scope-approval"
        )
    coverage_manifest = resolve_coverage_manifest(
        root, state, args.coverage_manifest, product_revision, evidence_revision
    )
    resolved_ids = set(args.resolved_finding or [])
    if resolved_ids and not product_changed:
        raise PipelineError("Resolving product findings requires a changed product revision")
    if product_changed:
        reset_validation(
            state, args.revision, product_revision, evidence_revision
        )

    state["revision"] = args.revision
    state["product_revision"] = product_revision
    state["evidence_revision"] = evidence_revision
    state["coverage_manifest"] = coverage_manifest
    state["last_engineer_run_id"] = args.run_id
    state["machine_checks"] = {
        "status": args.machine_checks,
        "revision": args.revision,
        "product_revision": product_revision,
        "evidence_revision": evidence_revision,
        "report": report,
        "coverage_manifest": coverage_manifest,
    }
    resolve_product_findings(
        findings, resolved_ids, args.revision, product_revision, evidence_revision
    )

    if product_changed:
        outcome = "changed"
        iteration = state["iteration_control"]
        iteration["consecutive_product_changes"] += 1
        if (
            iteration["consecutive_product_changes"]
            >= iteration["max_consecutive_product_changes"]
        ):
            iteration["status"] = "checkpoint_required"
            iteration["reason"] = (
                "Two product-changing Engineer passes require a director checkpoint "
                "before another full convergence pass"
            )
            state["phase"] = "convergence_hold"
        else:
            iteration["status"] = "running"
            iteration["reason"] = None
            state["phase"] = "engineering"
    elif args.machine_checks != "pass" or open_blocking(findings):
        outcome = "blocked"
        reset_validation(state, args.revision, product_revision, evidence_revision)
        state["phase"] = "engineering"
    else:
        outcome = "clean"
        state["iteration_control"]["status"] = "running"
        state["iteration_control"]["reason"] = None
        state["iteration_control"]["consecutive_product_changes"] = 0
        state["engineer_clean"] = {
            "run_id": args.run_id,
            "revision": args.revision,
            "product_revision": product_revision,
            "evidence_revision": evidence_revision,
            "audit_complete": True,
            "report": report,
            "coverage_manifest": coverage_manifest,
            "recorded_at": utc_now(),
        }
        state["review"] = empty_review_state(
            state["required_reviews"],
            args.revision,
            product_revision,
            evidence_revision,
        )
        state["qa"] = empty_qa_state()
        state["phase"] = "review"

    state["last_engineer_outcome"] = outcome
    state["engineer_runs"].append(
        {
            "run_id": args.run_id,
            "input_revision": input_revision,
            "input_product_revision": input_product_revision,
            "input_evidence_revision": input_evidence_revision,
            "revision": args.revision,
            "product_revision": product_revision,
            "evidence_revision": evidence_revision,
            "change_class": "product" if product_changed else "none",
            "outcome": outcome,
            "machine_checks": args.machine_checks,
            "report": report,
            "coverage_manifest": coverage_manifest,
            "production_change_scope": args.production_change_scope,
            "production_files_changed": args.production_files_changed,
            "production_lines_changed": args.production_lines_changed,
            "scope_approval": args.scope_approval,
            "resolved_findings": sorted(resolved_ids),
            "audit_complete": True,
            "recorded_at": utc_now(),
        }
    )
    save_runtime(state_path, findings_path, state, findings)
    return cmd_status(args)


def cmd_review_complete(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    require_current_identity(
        state, args.revision, args.product_revision, args.evidence_revision
    )
    if state["phase"] != "review":
        raise PipelineError("Final reviews can complete only during the review phase")
    clean = state.get("engineer_clean")
    if (
        not clean
        or clean.get("revision") != state["revision"]
        or clean.get("product_revision") != state["product_revision"]
        or clean.get("evidence_revision") != state["evidence_revision"]
    ):
        raise PipelineError("Final reviews require a clean Engineer pass on the current revision")
    if any(run["run_id"] == args.run_id for run in state["review_runs"]):
        raise PipelineError(f"Review run ID already recorded: {args.run_id}")
    current_runs = state["review"]["runs"]
    if any(run["reviewer_id"] == args.reviewer_id for run in current_runs):
        raise PipelineError(f"Reviewer already recorded for this revision: {args.reviewer_id}")
    report = resolve_report(root, state, args.report, "Review report")

    run = {
        "run_id": args.run_id,
        "reviewer_id": args.reviewer_id,
        "revision": args.revision,
        "product_revision": state["product_revision"],
        "evidence_revision": state["evidence_revision"],
        "status": args.status,
        "report": report,
        "recorded_at": utc_now(),
    }
    current_runs.append(run)
    state["review_runs"].append(run)
    state["review"]["status"] = "running"

    if len(current_runs) >= state["required_reviews"]:
        state["review"]["status"] = "awaiting_decision"

    save_runtime(state_path, findings_path, state, findings)
    return cmd_status(args)


def cmd_review_finalize(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    require_current_revision(state, args.revision)
    review = state.get("review", {})
    if state["phase"] != "review" or review.get("status") != "awaiting_decision":
        raise PipelineError("Review decision requires both final Review reports")
    if len(review.get("runs", [])) != state["required_reviews"]:
        raise PipelineError("Review decision requires exactly two completed Review reports")
    report = resolve_report(root, state, args.report, "Aggregated Review decision report")
    reviewer_failed = any(run["status"] == "fail" for run in review["runs"])
    review_findings = [
        item
        for item in findings["items"]
        if item["status"] == "open"
        and item["source"] == "review"
        and item["revision"] == args.revision
    ]

    if args.decision == "pass":
        if review_findings:
            raise PipelineError("Cannot pass final Review while confirmed Review findings remain open")
        if reviewer_failed and not args.reason:
            raise PipelineError("Overriding a reviewer FAIL requires --reason")
        review["status"] = "passed"
        state["phase"] = "qa"
    else:
        if not review_findings:
            raise PipelineError("Rework decision requires at least one registered Review finding")
        review["status"] = "failed"
        state["qa"] = empty_qa_state()
        if args.rework_scope == "evidence":
            if any(item.get("kind") != "evidence" for item in review_findings):
                raise PipelineError(
                    "Evidence recovery requires every confirmed Review finding to use --kind evidence"
                )
            state["recovery"] = {
                "status": "awaiting_remediation",
                "base_revision": state["revision"],
                "base_product_revision": state["product_revision"],
                "base_evidence_revision": state["evidence_revision"],
                "finding_ids": [item["id"] for item in review_findings],
                "base_review_runs": list(review["runs"]),
                "remediation_runs": [],
                "verification_runs": [],
                "cycles": 0,
                "reason": args.reason,
            }
            state["phase"] = "evidence_recovery"
        else:
            state["recovery"] = None
            state["phase"] = "engineering"

    review["decision"] = args.decision
    review["decision_report"] = report
    review["decision_reason"] = args.reason
    review["decided_at"] = utc_now()
    save_runtime(state_path, findings_path, state, findings)
    return cmd_status(args)


def cmd_add_finding(args: argparse.Namespace) -> int:
    _, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    require_current_revision(state, args.revision)
    if any(item["id"] == args.id for item in findings["items"]):
        raise PipelineError(f"Finding ID already exists: {args.id}")
    valid_phases = {
        "engineer": {"engineering"},
        "review": {"review", "recovery_review"},
        "qa": {"qa"},
    }
    if state["phase"] not in valid_phases[args.source]:
        raise PipelineError(
            f"{args.source} findings cannot be registered during phase {state['phase']}"
        )
    if args.source == "qa" and args.kind != "product":
        raise PipelineError("QA may register only product findings")
    findings["items"].append(
        {
            "id": args.id,
            "source": args.source,
            "kind": args.kind,
            "severity": args.severity,
            "title": args.title,
            "evidence": args.evidence,
            "revision": args.revision,
            "status": "open",
            "created_at": utc_now(),
            "resolved_revision": None,
        }
    )
    deferred_director_decision = (
        (args.source == "review" and state["phase"] in {"review", "recovery_review"})
        or (args.source == "qa" and state["phase"] == "qa")
    )
    if args.severity in BLOCKING_SEVERITIES and not deferred_director_decision:
        state["phase"] = (
            "evidence_recovery" if args.kind == "evidence" else "engineering"
        )
    save_runtime(state_path, findings_path, state, findings)
    print(json.dumps({"added": args.id}, ensure_ascii=False))
    return 0


def cmd_resolve_finding(args: argparse.Namespace) -> int:
    _, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    require_current_revision(state, args.revision)
    target = next((item for item in findings["items"] if item["id"] == args.id), None)
    if target is None:
        raise PipelineError(f"Unknown finding ID: {args.id}")
    if target["status"] != "open":
        raise PipelineError(f"Finding is not open: {args.id}")
    target["status"] = "resolved"
    target["resolved_revision"] = args.revision
    target["resolved_at"] = utc_now()
    save_runtime(state_path, findings_path, state, findings)
    print(json.dumps({"resolved": args.id}, ensure_ascii=False))
    return 0


def cmd_accept_finding(args: argparse.Namespace) -> int:
    _, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    target = next((item for item in findings["items"] if item["id"] == args.id), None)
    if target is None:
        raise PipelineError(f"Unknown finding ID: {args.id}")
    if target["status"] != "open":
        raise PipelineError(f"Finding is not open: {args.id}")
    if target["severity"] != "minor":
        raise PipelineError("Only minor findings can be accepted as residual risk")
    target["status"] = "accepted"
    target["accepted_reason"] = args.reason
    target["approval_reference"] = args.approval_reference
    target["accepted_at"] = utc_now()
    save_runtime(state_path, findings_path, state, findings)
    print(json.dumps({"accepted": args.id}, ensure_ascii=False))
    return 0


def cmd_start_evidence_recovery(args: argparse.Namespace) -> int:
    """Convert a paused legacy Review rework into the evidence-only recovery lane."""
    _, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    require_current_revision(state, args.revision)
    review = state.get("review", {})
    if state["phase"] != "engineering" or review.get("status") != "failed":
        raise PipelineError(
            "start-evidence-recovery requires a finalized failed Review paused in engineering"
        )
    selected = set(args.finding_id or [])
    open_review = [
        item
        for item in findings["items"]
        if item["status"] == "open" and item["source"] == "review"
    ]
    if not selected or selected != {item["id"] for item in open_review}:
        raise PipelineError(
            "Supply every and only open Review finding with --finding-id"
        )
    for item in open_review:
        item["kind"] = "evidence"
    state["product_revision"] = args.product_revision
    state["evidence_revision"] = args.evidence_revision
    clean = state.get("engineer_clean")
    if clean:
        clean["product_revision"] = args.product_revision
        clean["evidence_revision"] = args.evidence_revision
    state["machine_checks"]["product_revision"] = args.product_revision
    state["machine_checks"]["evidence_revision"] = args.evidence_revision
    review["product_revision"] = args.product_revision
    review["evidence_revision"] = args.evidence_revision
    state["recovery"] = {
        "status": "awaiting_remediation",
        "base_revision": state["revision"],
        "base_product_revision": args.product_revision,
        "base_evidence_revision": args.evidence_revision,
        "finding_ids": sorted(selected),
        "base_review_runs": list(review.get("runs", [])),
        "remediation_runs": [],
        "verification_runs": [],
        "cycles": 0,
        "reason": args.reason,
    }
    state["phase"] = "evidence_recovery"
    save_runtime(state_path, findings_path, state, findings)
    return cmd_status(args)


def cmd_evidence_remediation_complete(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    recovery = state.get("recovery")
    if state["phase"] != "evidence_recovery" or not recovery:
        raise PipelineError("No evidence-only remediation is awaiting completion")
    if args.product_revision != recovery["base_product_revision"]:
        raise PipelineError(
            "Product revision changed during evidence recovery; return to full engineering"
        )
    if args.production_change_scope != "none":
        raise PipelineError("Evidence recovery must not modify production code")
    if args.machine_checks != "pass":
        raise PipelineError("Evidence recovery requires passing targeted and aggregate checks")
    if args.evidence_revision == recovery["base_evidence_revision"]:
        raise PipelineError("Evidence remediation must produce a new evidence revision")
    if any(
        run["run_id"] == args.run_id
        for run in recovery.get("remediation_runs", [])
    ):
        raise PipelineError(f"Evidence remediation run ID already recorded: {args.run_id}")

    required_ids = set(recovery["finding_ids"])
    selected_items = [
        item for item in findings["items"] if item["id"] in required_ids
    ]
    if len(selected_items) != len(required_ids) or any(
        item.get("status") != "open" or item.get("kind") != "evidence"
        for item in selected_items
    ):
        raise PipelineError("The frozen evidence-recovery batch is missing or no longer open")
    resolved_ids = set(args.resolved_finding or [])
    if resolved_ids != required_ids:
        raise PipelineError(
            "Evidence remediation must resolve the complete open evidence finding batch"
        )
    report = resolve_report(root, state, args.report, "Evidence remediation report")
    coverage_manifest = resolve_coverage_manifest(
        root,
        state,
        args.coverage_manifest,
        args.product_revision,
        args.evidence_revision,
    )
    for item in findings["items"]:
        if item["id"] in resolved_ids:
            item["status"] = "resolved"
            item["resolved_revision"] = args.revision
            item["resolved_product_revision"] = args.product_revision
            item["resolved_evidence_revision"] = args.evidence_revision
            item["resolved_at"] = utc_now()

    state["revision"] = args.revision
    state["product_revision"] = args.product_revision
    state["evidence_revision"] = args.evidence_revision
    state["coverage_manifest"] = coverage_manifest
    state["machine_checks"] = {
        "status": "pass",
        "revision": args.revision,
        "product_revision": args.product_revision,
        "evidence_revision": args.evidence_revision,
        "report": report,
        "coverage_manifest": coverage_manifest,
    }
    recovery["status"] = "awaiting_verification"
    recovery["current_revision"] = args.revision
    recovery["current_evidence_revision"] = args.evidence_revision
    recovery["remediation_runs"].append(
        {
            "run_id": args.run_id,
            "revision": args.revision,
            "product_revision": args.product_revision,
            "evidence_revision": args.evidence_revision,
            "resolved_findings": sorted(resolved_ids),
            "report": report,
            "coverage_manifest": coverage_manifest,
            "recorded_at": utc_now(),
        }
    )
    review = state["review"]
    review["status"] = "recovery_verification"
    review["revision"] = args.revision
    review["product_revision"] = args.product_revision
    review["evidence_revision"] = args.evidence_revision
    review["recovery_run"] = None
    state["qa"] = empty_qa_state()
    state["phase"] = "recovery_review"
    save_runtime(state_path, findings_path, state, findings)
    return cmd_status(args)


def cmd_recovery_review_complete(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    require_current_identity(
        state, args.revision, args.product_revision, args.evidence_revision
    )
    recovery = state.get("recovery")
    if state["phase"] != "recovery_review" or not recovery:
        raise PipelineError("No evidence recovery verification is pending")
    if any(
        run.get("reviewer_id") == args.reviewer_id
        for run in recovery.get("base_review_runs", []) + recovery.get("verification_runs", [])
    ):
        raise PipelineError("Recovery verification requires a fresh reviewer identity")
    if any(run["run_id"] == args.run_id for run in state["review_runs"]):
        raise PipelineError(f"Review run ID already recorded: {args.run_id}")
    report = resolve_report(root, state, args.report, "Recovery Review report")
    run = {
        "run_id": args.run_id,
        "reviewer_id": args.reviewer_id,
        "revision": args.revision,
        "product_revision": args.product_revision,
        "evidence_revision": args.evidence_revision,
        "status": args.status,
        "mode": "evidence_recovery",
        "report": report,
        "recorded_at": utc_now(),
    }
    recovery["verification_runs"].append(run)
    state["review_runs"].append(run)
    state["review"]["recovery_run"] = run
    if args.status == "pass":
        if open_blocking(findings):
            raise PipelineError(
                "Recovery Review cannot pass while blocking findings remain open"
            )
        state["review"]["status"] = "passed_recovery"
        state["review"]["decision"] = "pass"
        state["review"]["decision_reason"] = (
            "Product revision stayed unchanged; one fresh reviewer verified the "
            "complete normalized evidence finding batch"
        )
        recovery["status"] = "passed"
        state["qa"] = empty_qa_state()
        state["phase"] = "qa"
    else:
        open_product = [
            item
            for item in open_blocking(findings)
            if item.get("kind") == "product"
        ]
        if open_product:
            recovery["status"] = "product_defect"
            state["recovery"] = recovery
            state["phase"] = "engineering"
            save_runtime(state_path, findings_path, state, findings)
            return cmd_status(args)
        open_evidence = [
            item
            for item in findings["items"]
            if item.get("status") == "open"
            and item.get("kind") == "evidence"
            and item.get("revision") == args.revision
        ]
        if not open_evidence:
            raise PipelineError(
                "A failed recovery Review must register at least one open evidence finding"
            )
        recovery["finding_ids"] = sorted(item["id"] for item in open_evidence)
        recovery["cycles"] += 1
        recovery["status"] = "awaiting_remediation"
        state["review"]["status"] = "failed_recovery"
        if recovery["cycles"] >= 2:
            state["iteration_control"]["status"] = "checkpoint_required"
            state["iteration_control"]["reason"] = (
                "Two evidence-recovery cycles require a director checkpoint"
            )
            state["phase"] = "recovery_hold"
        else:
            state["phase"] = "evidence_recovery"
    save_runtime(state_path, findings_path, state, findings)
    return cmd_status(args)


def cmd_authorize_iteration(args: argparse.Namespace) -> int:
    _, state_path, findings_path, state, findings = load_runtime(args.project_root)
    if state["phase"] not in {"convergence_hold", "recovery_hold"}:
        raise PipelineError("No convergence or recovery circuit breaker is open")
    previous_phase = state["phase"]
    state["iteration_control"]["authorizations"].append(
        {
            "reason": args.reason,
            "phase": previous_phase,
            "recorded_at": utc_now(),
        }
    )
    state["iteration_control"]["status"] = "running"
    state["iteration_control"]["reason"] = args.reason
    if previous_phase == "convergence_hold":
        state["iteration_control"]["consecutive_product_changes"] = 0
    else:
        recovery = state.get("recovery")
        if recovery:
            recovery["cycles"] = 0
    state["phase"] = (
        "engineering" if previous_phase == "convergence_hold" else "evidence_recovery"
    )
    save_runtime(state_path, findings_path, state, findings)
    return cmd_status(args)


def resolve_qa_gates(state: dict[str, Any], revision: str, resolution: str) -> None:
    for gate in state.get("gates", []):
        if (
            gate.get("status") == "open"
            and gate.get("phase") == "qa"
            and gate.get("revision") == revision
        ):
            gate["status"] = "resolved"
            gate["resolved_at"] = utc_now()
            gate["resolution"] = resolution


def cmd_qa_complete(args: argparse.Namespace) -> int:
    root, state_path, findings_path, state, findings = load_runtime(args.project_root)
    require_sources_current(state)
    require_current_identity(
        state, args.revision, args.product_revision, args.evidence_revision
    )
    if state["phase"] != "qa":
        raise PipelineError("QA can complete only during the QA phase")
    review = state.get("review", {})
    if review.get("status") not in PASSED_REVIEW_STATUSES or review.get("revision") != args.revision:
        raise PipelineError("QA requires two passed final reviews on the current revision")
    if any(run["run_id"] == args.run_id for run in state["qa_runs"]):
        raise PipelineError(f"QA run ID already recorded: {args.run_id}")
    report = resolve_report(root, state, args.report, "QA report")
    pending = args.pending_scenario or []
    if args.status != "pass" and not args.reason:
        raise PipelineError("Non-pass QA requires --reason")
    if args.status in QA_GATE_STATUSES and not pending:
        raise PipelineError(
            "Blocked or errored QA requires --reason and at least one --pending-scenario"
        )

    qa_product_findings = [
        item
        for item in findings["items"]
        if item.get("status") == "open"
        and item.get("source") == "qa"
        and item.get("kind") == "product"
        and item.get("severity") in BLOCKING_SEVERITIES
        and item.get("revision") == args.revision
    ]
    if args.status == "fail_product" and not qa_product_findings:
        raise PipelineError(
            "FAIL_PRODUCT requires an open critical or major QA product finding "
            "on this revision"
        )
    if args.status != "fail_product" and qa_product_findings:
        raise PipelineError("Open blocking QA product findings require status fail_product")
    if args.status == "pass" and pending:
        raise PipelineError("Passing QA cannot contain pending scenarios")
    effective_status = args.status
    qa_run = {
        "run_id": args.run_id,
        "revision": args.revision,
        "product_revision": state["product_revision"],
        "evidence_revision": state["evidence_revision"],
        "status": effective_status,
        "report": report,
        "pending_scenarios": pending,
        "reason": args.reason,
        "recorded_at": utc_now(),
    }
    state["qa_runs"].append(qa_run)
    state["qa"] = {
        "status": effective_status,
        "revision": args.revision,
        "product_revision": state["product_revision"],
        "evidence_revision": state["evidence_revision"],
        "run_id": args.run_id,
        "report": report,
        "pending_scenarios": pending,
        "reason": args.reason,
    }

    if effective_status == "pass":
        resolve_qa_gates(state, args.revision, "QA completed on the same revision")
        state["phase"] = "ready"
    elif effective_status == "fail_product":
        resolve_qa_gates(state, args.revision, "QA reproduced a product defect")
        state["engineer_clean"] = None
        state["review"] = empty_review_state(
            state["required_reviews"],
            args.revision,
            state["product_revision"],
            state["evidence_revision"],
        )
        state["phase"] = "engineering"
    else:
        state["gates"].append(
            {
                "id": f"qa:{args.run_id}",
                "phase": "qa",
                "category": effective_status,
                "revision": args.revision,
                "reason": args.reason,
                "pending_scenarios": pending,
                "report": report,
                "status": "open",
                "created_at": utc_now(),
            }
        )
        state["phase"] = "qa"

    save_runtime(state_path, findings_path, state, findings)
    return cmd_status(args)


def readiness_reasons(state: dict[str, Any], findings: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    reasons.extend(source_drift(state))
    revision = state.get("revision")
    product_revision = state.get("product_revision")
    evidence_revision = state.get("evidence_revision")
    if not revision:
        reasons.append("no current revision")
    machine = state.get("machine_checks", {})
    if (
        machine.get("status") != "pass"
        or machine.get("revision") != revision
        or machine.get("product_revision") != product_revision
        or machine.get("evidence_revision") != evidence_revision
    ):
        reasons.append("machine checks have not passed on the current revision")
    if open_blocking(findings):
        reasons.append("critical or major product findings remain unresolved")
    if any(
        item["status"] == "open" and item["severity"] == "minor"
        for item in findings["items"]
    ):
        reasons.append("minor findings require resolution or explicit acceptance")
    clean = state.get("engineer_clean")
    if not clean or clean.get("product_revision") != product_revision:
        reasons.append("a clean Engineer pass has not completed on the current product revision")
    review = state.get("review", {})
    if review.get("status") not in PASSED_REVIEW_STATUSES or review.get("revision") != revision:
        reasons.append("two final reviews have not passed on the current revision")
    elif review.get("status") == "passed" and len(review.get("runs", [])) != state.get("required_reviews", 2):
        reasons.append("final review evidence is incomplete")
    elif review.get("status") == "passed" and len({run["reviewer_id"] for run in review["runs"]}) != len(review["runs"]):
        reasons.append("final reviews are not from distinct reviewers")
    elif review.get("status") == "passed_recovery":
        recovery = state.get("recovery") or {}
        if (
            recovery.get("status") != "passed"
            or len(recovery.get("base_review_runs", [])) != state.get("required_reviews", 2)
            or not review.get("recovery_run")
        ):
            reasons.append("evidence recovery review chain is incomplete")
    qa = state.get("qa", {})
    if qa.get("status") != "pass" or qa.get("revision") != revision:
        reasons.append("feature-focused runtime QA has not passed on the current revision")
    if any(gate.get("status") == "open" for gate in state.get("gates", [])):
        reasons.append("an execution, environment, or user gate remains open")
    if state.get("phase") != "ready":
        reasons.append("pipeline phase is not ready")
    return reasons


def cmd_ready(args: argparse.Namespace) -> int:
    _, _, _, state, findings = load_runtime(args.project_root)
    reasons = readiness_reasons(state, findings)
    print(json.dumps({"ready": not reasons, "reasons": reasons}, ensure_ascii=False, indent=2))
    return 0 if not reasons else 1


def add_common_project_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-root", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init")
    add_common_project_root(init)
    init.add_argument("--feature", required=True)
    init.add_argument("--requirements", required=True)
    init.add_argument("--spec", required=True)
    init.add_argument("--slice", required=True)
    init.add_argument("--required-reviews", type=int, default=2)
    init.add_argument(
        "--max-consecutive-product-changes",
        "--max-automatic-product-changes",
        dest="max_consecutive_product_changes",
        type=int,
        default=DEFAULT_MAX_CONSECUTIVE_PRODUCT_CHANGES,
    )
    init.set_defaults(handler=cmd_init)

    status = commands.add_parser("status")
    add_common_project_root(status)
    status.set_defaults(handler=cmd_status)

    revisions = commands.add_parser("compute-revisions")
    add_common_project_root(revisions)
    revisions.add_argument("--base-revision", required=True)
    revisions.add_argument("--product-file", action="append")
    revisions.add_argument("--evidence-file", action="append")
    revisions.add_argument("--output")
    revisions.set_defaults(handler=cmd_compute_revisions)

    engineer = commands.add_parser("engineer-complete")
    add_common_project_root(engineer)
    engineer.add_argument("--revision", required=True)
    engineer.add_argument("--product-revision")
    engineer.add_argument("--evidence-revision")
    engineer.add_argument("--run-id", required=True)
    engineer.add_argument("--machine-checks", choices=("pass", "fail"), required=True)
    engineer.add_argument("--report", required=True)
    engineer.add_argument("--coverage-manifest", required=True)
    engineer.add_argument(
        "--production-change-scope",
        choices=("none", "local", "architectural"),
        required=True,
    )
    engineer.add_argument("--production-files-changed", type=int, default=0)
    engineer.add_argument("--production-lines-changed", type=int, default=0)
    engineer.add_argument("--scope-approval")
    engineer.add_argument("--resolved-finding", action="append")
    engineer.add_argument(
        "--audit-complete",
        action="store_true",
        required=True,
        help="Assert that full discovery, batch remediation, checks, and scope resweep finished",
    )
    engineer.set_defaults(handler=cmd_engineer_complete)

    review = commands.add_parser("review-complete")
    add_common_project_root(review)
    review.add_argument("--revision", required=True)
    review.add_argument("--product-revision")
    review.add_argument("--evidence-revision")
    review.add_argument("--run-id", required=True)
    review.add_argument("--reviewer-id", required=True)
    review.add_argument("--status", choices=("pass", "fail"), required=True)
    review.add_argument("--report", required=True)
    review.set_defaults(handler=cmd_review_complete)

    review_finalize = commands.add_parser("review-finalize")
    add_common_project_root(review_finalize)
    review_finalize.add_argument("--revision", required=True)
    review_finalize.add_argument("--decision", choices=("pass", "rework"), required=True)
    review_finalize.add_argument("--report", required=True)
    review_finalize.add_argument("--reason")
    review_finalize.add_argument(
        "--rework-scope", choices=("product", "evidence"), default="product"
    )
    review_finalize.set_defaults(handler=cmd_review_finalize)

    add_finding = commands.add_parser("add-finding")
    add_common_project_root(add_finding)
    add_finding.add_argument("--id", required=True)
    add_finding.add_argument("--source", choices=("engineer", "review", "qa"), required=True)
    add_finding.add_argument("--kind", choices=tuple(sorted(FINDING_KINDS)), default="product")
    add_finding.add_argument("--severity", choices=("critical", "major", "minor"), required=True)
    add_finding.add_argument("--title", required=True)
    add_finding.add_argument("--evidence", required=True)
    add_finding.add_argument("--revision", required=True)
    add_finding.set_defaults(handler=cmd_add_finding)

    resolve = commands.add_parser("resolve-finding")
    add_common_project_root(resolve)
    resolve.add_argument("--id", required=True)
    resolve.add_argument("--revision", required=True)
    resolve.set_defaults(handler=cmd_resolve_finding)

    accept = commands.add_parser("accept-finding")
    add_common_project_root(accept)
    accept.add_argument("--id", required=True)
    accept.add_argument("--reason", required=True)
    accept.add_argument("--approval-reference", required=True)
    accept.set_defaults(handler=cmd_accept_finding)

    recovery_start = commands.add_parser("start-evidence-recovery")
    add_common_project_root(recovery_start)
    recovery_start.add_argument("--revision", required=True)
    recovery_start.add_argument("--product-revision", required=True)
    recovery_start.add_argument("--evidence-revision", required=True)
    recovery_start.add_argument("--finding-id", action="append", required=True)
    recovery_start.add_argument("--reason", required=True)
    recovery_start.set_defaults(handler=cmd_start_evidence_recovery)

    remediation = commands.add_parser("evidence-remediation-complete")
    add_common_project_root(remediation)
    remediation.add_argument("--revision", required=True)
    remediation.add_argument("--product-revision", required=True)
    remediation.add_argument("--evidence-revision", required=True)
    remediation.add_argument("--run-id", required=True)
    remediation.add_argument("--machine-checks", choices=("pass", "fail"), required=True)
    remediation.add_argument("--report", required=True)
    remediation.add_argument("--coverage-manifest", required=True)
    remediation.add_argument("--resolved-finding", action="append", required=True)
    remediation.add_argument(
        "--production-change-scope",
        choices=("none", "local", "architectural"),
        default="none",
    )
    remediation.set_defaults(handler=cmd_evidence_remediation_complete)

    recovery_review = commands.add_parser("recovery-review-complete")
    add_common_project_root(recovery_review)
    recovery_review.add_argument("--revision", required=True)
    recovery_review.add_argument("--product-revision", required=True)
    recovery_review.add_argument("--evidence-revision", required=True)
    recovery_review.add_argument("--run-id", required=True)
    recovery_review.add_argument("--reviewer-id", required=True)
    recovery_review.add_argument("--status", choices=("pass", "fail"), required=True)
    recovery_review.add_argument("--report", required=True)
    recovery_review.set_defaults(handler=cmd_recovery_review_complete)

    authorize = commands.add_parser("authorize-iteration")
    add_common_project_root(authorize)
    authorize.add_argument("--reason", required=True)
    authorize.set_defaults(handler=cmd_authorize_iteration)

    qa = commands.add_parser("qa-complete")
    add_common_project_root(qa)
    qa.add_argument("--revision", required=True)
    qa.add_argument("--product-revision")
    qa.add_argument("--evidence-revision")
    qa.add_argument("--run-id", required=True)
    qa.add_argument("--status", choices=tuple(sorted(QA_STATUSES)), required=True)
    qa.add_argument("--report", required=True)
    qa.add_argument("--reason")
    qa.add_argument("--pending-scenario", dest="pending_scenario", action="append")
    qa.set_defaults(handler=cmd_qa_complete)

    ready = commands.add_parser("ready")
    add_common_project_root(ready)
    ready.set_defaults(handler=cmd_ready)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except PipelineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
