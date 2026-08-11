# Role artifacts and bounded context

This file is the normative cross-role schema contract. Role-specific semantic rules live in the corresponding skill references. The controller generates and validates all mechanical envelopes.

## Exclusive write leases

`single_owner` is a planning shape, not a lifetime worker identity. It means the implementation queue has one active implementation scope rather than multiple sequential slices. All modes use phase-scoped exclusive leases:

```json
{
  "lease_id": "LEASE-*",
  "phase": "decision_recording|slice_engineering|normative_documentation|derived_documentation|evidence_recovery",
  "write_scope": "exact controller-owned scope ID",
  "role": "decision_recorder|engineer|documentation_finisher|recovery_remediator",
  "worker_id": "worker ID",
  "base_revision": "exact composite revision",
  "allowed_paths": [],
  "allowed_symbols": [],
  "exclusions": [],
  "status": "active|released|revoked"
}
```

At most one write-capable lease may be active in a checkout, and at most one writer may own a phase/write scope. Review, QA, Research, and Coverage Steward roles remain read-only to product/support/evidence inputs and may write only their isolated reports. Changing phase, role, owner, scope, or base revision requires releasing/revoking the prior lease and issuing a new one. Owner transfer preserves all hashes, findings, counters, decisions, coverage state, documentation state, and scope history.

An Engineer is not the lifecycle owner. The controller may assign a different Engineer for a later approved slice or after a required structured transfer. Origin-route and integration-route rules still apply, but identity persistence never authorizes overlapping writers.

## Context capsule schema 1

Every delegated specialized role receives one controller-generated capsule, not inherited chat history:

```json
{
  "schema": 1,
  "capsule_id": "CAP-*",
  "role": "engineer|researcher|decision_recorder|coverage_steward|documentation_finisher|reviewer|qa",
  "phase": "exact phase",
  "worker_id": "worker ID",
  "plan_sha256": "exact approved plan SHA",
  "revisions": {
    "revision": "composite",
    "product_revision": "product",
    "support_revision": "support",
    "evidence_revision": "evidence"
  },
  "authority": [
    {"path": "repository-relative path", "sha256": "64 lowercase hex", "ids": []}
  ],
  "decision_ids": [],
  "finding_ids": [],
  "coverage_identity_ids": [],
  "evidence": [
    {"path": "report/evidence path", "sha256": "64 lowercase hex", "ids": []}
  ],
  "allowed_paths": [],
  "allowed_symbols": [],
  "exclusions": [],
  "commands": [],
  "output_paths": [],
  "stop_condition": "deterministic stop",
  "budget": {
    "max_authority_files": 0,
    "max_evidence_files": 0,
    "max_total_files": 0,
    "max_payload_bytes": 0,
    "max_estimated_tokens": 0
  },
  "metrics": {
    "authority_files": 0,
    "evidence_files": 0,
    "total_files": 0,
    "payload_bytes": 0,
    "estimated_tokens": 0
  },
  "capsule_sha256": "controller digest"
}
```

Every maximum is positive and comes from the approved plan or a recorded budget authorization. `total_files` is the deduplicated union of authority/evidence files. `payload_bytes` is the UTF-8 byte length of controller-canonical capsule JSON with `metrics` and `capsule_sha256` omitted plus the exact byte lengths of every referenced authority/evidence file. `estimated_tokens = ceil(payload_bytes / 4)`. The controller records this recipe and all observed sizes; allowed-but-unread path families do not enter metrics until a new capsule explicitly adds a file. The controller rejects a capsule when any metric exceeds its maximum, a referenced path/SHA/ID is stale or absent, output scopes overlap an active writer, a role receives unnecessary authority, or the capsule embeds chat transcripts/raw reasoning. The phase cannot spawn until `context-capsule-check` passes. Budget authorization is append-only and never resets prior metrics.

User authority is the only non-file authority form and is encoded as `{"path":"not_applicable","sha256":"<controller receipt digest>","ids":["<authority-id>"]}`. Before capsule creation, a separate lease-free `user-authority-accept` checkpoint must already have appended the exact authority ID, explicit approval reference, statement, digest, receipt path/SHA, and timestamp to controller state. The controller records the assertion but does not authenticate the human. Capsule creation and a Decision Recorder packet may cite only that immutable prior receipt; neither operation can self-issue or alter user authority.

`capsule_sha256` is SHA-256 of controller-canonical JSON with the `capsule_sha256` field omitted. The same omit-self rule defines `handoff_sha256` below; neither digest is self-referential.

## Controller-generated handoff schema 2

Workers return short semantic packets. The controller inspects the actual checkout, computes domain revisions, classifies changed paths, validates the active lease and scope, and generates the sealed handoff:

Every write-capable completion command that changes checkout inputs uses this exact semantic packet schema before the controller generates mechanical artifacts:

```json
{
  "schema": 1,
  "inventory_complete": true,
  "domain_inventory": {
    "product": [],
    "support": [],
    "evidence": []
  },
  "changes": [],
  "open_assumptions": []
}
```

The three domain arrays are the complete post-pass repository-relative revision inventory. Each `changes[]` row identifies one actually changed path, its domain, semantic reason, requirement/acceptance/decision IDs, scope or slice ID, symbols, change kind, and touchpoint where applicable. The controller rejects missing or extra changed paths, duplicate or cross-domain inventory entries, incomplete inventories, invalid plan mappings, or worker-supplied revision hashes and mechanical counts. `open_assumptions` uses the schema-2 handoff assumption shape below. A role-specific contract may narrow the allowed domains and require additional semantic fields, but may not omit this envelope.

```json
{
  "schema": 2,
  "handoff_id": "HANDOFF-*",
  "phase": "exact source phase",
  "writer_role": "role",
  "writer_id": "worker ID",
  "lease_id": "LEASE-*|no_write",
  "slice_id": "SLICE-NNN",
  "base_revisions": {},
  "result_revisions": {},
  "change_manifest_path": "controller artifact",
  "diff_summary_path": "controller artifact",
  "semantic_report_path": "worker report",
  "decision_ids": ["DEC-001"],
  "coverage_state": {
    "manifest_path": "path",
    "manifest_sha256": "sha",
    "ac_mapped": false,
    "identities_registered": "complete|mismatch|gaps|pending",
    "automated": "pending|passed|failed|blocked",
    "manual": "pending|passed|failed|deferred"
  },
  "documentation_state": {
    "normative": "pending|required_complete|not_required|gap",
    "derived": "pending|required_complete|not_required|gap"
  },
  "open_assumptions": [
    {"assumption_id": "ASM-*", "statement": "text", "owner": "role/user", "validation_point": "phase", "impact_if_false": "text"}
  ],
  "generated_at": "controller timestamp",
  "handoff_sha256": "controller digest"
}
```

`decision_ids`, `coverage_state`, `documentation_state`, and `open_assumptions` are always present, even when empty/pending. Decision IDs must exist and be active in the exact ledger. Assumptions never substitute for an accepted decision, mandatory coverage identity, or gate. The controller rejects worker-authored base/result hashes, change counts, revision manifests, or sealed-handoff mechanics as phase evidence.

`lease_id: no_write` is the only non-lease sentinel. It is valid only for a controller-generated handoff from a command that performs no checkout write: `documentation-not-required` or an owner transfer with no active pass to revoke. Such a command must not acquire a ceremonial write lease. Every handoff generated by a writing pass requires the exact released `LEASE-*` identity.

## Controller-generated change and revision evidence

The controller, not an Engineer, enumerates the actual diff and emits the canonical change manifest, diff summary, revision manifest, and handoff envelope. It validates every changed product path/symbol against the approved Scope Contract, touchpoint, requirements, acceptance IDs, exclusions, and budgets. Semantic mappings that cannot be derived deterministically require a bounded worker annotation, but the controller verifies it against the plan and actual diff before inclusion.

The existing product/support/evidence domain recipe remains exact and fail-closed. Reports, logs, screenshots, context capsules, coverage manifests, change/diff/revision/handoff manifests, controller state, and the deferred-findings backlog are excluded from all three revision inputs.
