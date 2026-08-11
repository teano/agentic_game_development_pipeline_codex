# Decision ledger contract

## Authority and write discipline

The repository-owned decision ledger is an append-only normative product artifact. The controller resolves its path, records it in state, and grants one exclusive write lease. A recorder receives a bounded context capsule containing exact authority paths and SHA-256 values, accepted decision IDs, output paths, exclusions, and the permitted mode. Long chat history, raw reasoning, and implied consensus are invalid authority.

Only these authority forms can support an entry:

- an explicit user decision with a controller-owned immutable receipt created by an earlier, separate lease-free `user-authority-accept` checkpoint;
- an approved PRD, specification, or development plan at its exact path/SHA and exact section/ID;
- a controller-recorded resolution whose source authority is itself exact and accepted.

An implementation choice discovered by an Engineer, an option preferred by a reviewer, or prose inferred from code is not accepted authority. Return `DECISION_INPUT_INCOMPLETE` instead of choosing.

The user-acceptance checkpoint requires a stable authority ID, explicit approval reference, and exact accepted statement. It records the caller's approval assertion but does not authenticate the human. Its digest and receipt path/SHA are append-only controller state. Capsule creation and the Recorder semantic packet may only cite this prior authority ID/digest and cannot create or revise it. Recording is restricted to pre-implementation boundaries (`preflight`, `slice_research`, or `slice_coverage_planning`); a later decision must return for explicit replan/reinitialization rather than invalidating completed downstream state in place.

## Schema 1 semantic packet and ledger entry

The recorder prepares a semantic packet. Each item contains exactly:

```json
{
  "schema": 1,
  "decision_id": "DEC-001",
  "status": "accepted",
  "statement": "accepted decision, without added scope",
  "rationale": "supplied rationale or not_supplied",
  "consequences": ["supplied consequence"],
  "scope_ids": ["PRD-REQ-001", "PRD-AC-001", "SLICE-001"],
  "authority": {
    "kind": "user|prd|specification|development_plan|controller_resolution",
    "reference": "stable authority reference or explicit approval reference",
    "path": "repository-relative path or not_applicable",
    "sha256": "64 lowercase hex or controller user-decision digest",
    "section_or_id": "exact section, requirement, acceptance, decision, or prior user-authority ID"
  },
  "supersedes": []
}
```

`decision_id`, `statement`, and authority fields are non-empty. `supersedes` may name only existing active `DEC-*` entries and never erases them. A correction is a new accepted decision ID. Duplicate IDs, changed payloads for an existing ID, or unsupported fields fail closed.

After validation, the controller atomically appends a JSONL ledger entry by adding mechanical fields: `sequence`, `recorded_at`, `recorder_id`, `prior_ledger_sha256`, and `input_product_revision`. The recorder never invents or hand-maintains these fields. The controller rejects reordered, deleted, or modified prior bytes, then records the resulting ledger SHA and result product revision in controller state and the append receipt (not inside the product-domain ledger, avoiding a self-referential hash).

## ADR synchronization

An ADR synchronization assignment names exact ADR paths/sections and source `DEC-*` IDs. Every changed normative statement maps to at least one active decision ID. Preserve repository format. When the ledger lacks a needed rationale, alternative, consequence, lifecycle rule, or scope choice, write `not_supplied` only where the format permits; otherwise stop and request an accepted decision. ADR synchronization cannot introduce a new decision, reinterpret a superseded entry, or alter implementation artifacts.

The controller generates the mechanical change/diff/revision manifest after the recorder's semantic diff inspection. Normative ADR drift invalidates downstream product evidence under ordinary product-revision rules.
