# Role artifacts and bounded context

This is the cross-role schema contract. Role semantics live in their skill references; the controller validates mechanical envelopes.

## Contents

- Exclusive write leases
- Context capsule schema 1 and capsule-payload telemetry
- Controller-generated handoff schema 2
- Controller-generated change and revision evidence

## Exclusive write leases

`single_owner` is a planning shape, not a lifetime worker identity. It means the implementation queue has one active implementation scope rather than multiple sequential slices. All modes use phase-scoped exclusive leases:

```json
{
  "lease_id": "LEASE-*", "phase": "exact write phase",
  "write_scope": "scope ID", "role": "write role", "worker_id": "worker",
  "base_revision": "composite", "allowed_paths": [],
  "allowed_symbols": [], "exclusions": [], "status": "active|released|revoked"
}
```

Only one write lease/writer may be active. Write roles are Decision Recorder, Engineer, Documentation Finisher, and Recovery Remediator in their exact phases; Review, QA, Research, and Coverage are input-read-only. Any phase/role/owner/scope/base change requires a new lease. Transfer preserves hashes, findings, counters, decisions, coverage/docs, and scope history.

An Engineer is not the lifecycle owner. The controller may assign a different Engineer for a later approved slice or after a required structured transfer. Origin-route and integration-route rules still apply, but identity persistence never authorizes overlapping writers.

## Context capsule schema 1 and capsule-payload telemetry

Every delegated specialized role receives one controller-generated capsule, not inherited chat history:

```json
{
  "schema": 1,
  "capsule_id": "CAP-*",
  "role": "exact role", "phase": "exact phase", "worker_id": "worker ID",
  "plan_sha256": "approved plan SHA", "revisions": {},
  "authority": [], "evidence": [],
  "decision_ids": [], "finding_ids": [], "coverage_identity_ids": [],
  "allowed_paths": [], "allowed_symbols": [], "exclusions": [],
  "commands": [], "output_paths": [], "stop_condition": "deterministic stop",
  "budget": {}, "metrics": {},
  "capsule_sha256": "controller digest"
}
```

`revisions` contains exact composite/product/support/evidence identities. Each authority/evidence row is `{path,sha256,ids}`. `budget` contains positive `max_authority_files`, `max_evidence_files`, `max_total_files`, `max_payload_bytes`, and `max_estimated_tokens`; `metrics` contains the corresponding observed counts/bytes/tokens.

For a Director-delegated stage, `worker_id` identifies a real non-Director subagent task, not a persona label chosen by the Director. The Director identity and `worker_id` must differ. Start the worker with no inherited chat turns (`fork_turns: none` or the runtime-equivalent); the capsule and bounded task packet are its complete cross-stage input. Full-history forks are forbidden for production roles. If the runtime cannot create an isolated subagent, do not activate the stage.

Every maximum is positive, within plan ceilings, and may be narrower. `max_total_files` covers each file ceiling. `total_files` deduplicates authority/evidence. `payload_bytes` is canonical capsule JSON without `metrics`/digest plus referenced file bytes; `estimated_tokens=ceil(payload_bytes/4)`. Its scope is `capsule_plus_referenced_files`.

Capsules are exact minimal packets. Authority is current PRD/spec/plan, active ledger, and Recorder's prior receipt. Evidence is phase-specific: coverage; Reviewer predecessor handoff/reports/credits; QA handoff/current Review/probe (prior QA only on resume); documentation review also QA/manual and derived report/map. Missing/extra paths, SHAs, or IDs fail closed.

IDs are exact for PRD/decisions, findings, and phase coverage. Writers have bounded paths; readers forbid writes/exclusions; only check roles allow commands.

The metric excludes skills/references, metadata, system/AGENTS instructions, history, and tools. Never report it as total agent context. Workers receive no Director history. CI verifies structural progressive disclosure and explicit always/conditional routing; dynamic context is not file-measurable.

The controller records recipe/sizes and counts only included files. It rejects exceeded plan/capsule ceilings, stale/absent references, overlapping output scope, excess authority, or embedded transcripts/reasoning. Activation requires `context-capsule-check`; budget authorization is append-only.

User authority is the sole non-file form: `{"path":"not_applicable","sha256":"receipt digest","ids":["authority-id"]}`. Before capsule creation, lease-free `user-authority-accept` appends ID, approval reference, statement, digest, receipt path/SHA, and time. It records but cannot authenticate the human. Capsules/Recorder cite that immutable receipt and cannot self-issue authority.

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

Domain arrays are the complete post-pass inventory. Each change names actual path/domain/reason, requirement/acceptance/decision IDs, scope, symbols, kind, and applicable touchpoint. Missing/extra paths, duplicate/cross-domain entries, incomplete inventory, invalid plan mapping, and worker hashes/counts fail. Role contracts may narrow but not omit this envelope.

```json
{
  "schema": 2,
  "handoff_id": "HANDOFF-*",
  "phase": "source phase", "writer_role": "role", "writer_id": "worker",
  "lease_id": "LEASE-*|no_write", "slice_id": "SLICE-NNN",
  "base_revisions": {}, "result_revisions": {},
  "change_manifest_path": "path", "diff_summary_path": "path",
  "semantic_report_path": "path",
  "decision_ids": ["DEC-001"],
  "coverage_state": {}, "documentation_state": {}, "open_assumptions": [],
  "generated_at": "timestamp", "handoff_sha256": "controller digest"
}
```

The four trailing state fields are always present. Coverage records manifest path/SHA, AC mapping, registration, automated, and manual states. Documentation records normative/derived state. Assumptions are `{assumption_id,statement,owner,validation_point,impact_if_false}` and never replace decisions, coverage, or gates. Decision IDs must be active. Worker-authored revisions/counts/sealed mechanics are rejected.

`lease_id: no_write` is the only non-lease sentinel. It is valid only for a controller-generated handoff from a command that performs no checkout write: `documentation-not-required` or an owner transfer with no active pass to revoke. Such a command must not acquire a ceremonial write lease. Every handoff generated by a writing pass requires the exact released `LEASE-*` identity.

## Controller-generated change and revision evidence

The controller enumerates the diff and emits change, diff, revision, and handoff artifacts. It validates changed paths/symbols against scope, touchpoints, requirement/acceptance IDs, exclusions, and budgets. Non-derivable semantic mappings require bounded worker annotation verified against plan and diff.

The existing product/support/evidence domain recipe remains exact and fail-closed. Reports, logs, screenshots, context capsules, coverage manifests, change/diff/revision/handoff manifests, controller state, and the deferred-findings backlog are excluded from all three revision inputs.
