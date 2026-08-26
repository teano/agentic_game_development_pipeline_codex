# Specification contract

## Canonical artifacts

Use the one repository-owned PRD and specification resolved from current user context, repository instructions, feature manifests/indexes, and existing artifacts. Both paths must remain inside the project root. Do not create a duplicate, symlink, move, or alternate namespace to accommodate the controller. If the repository provides more than one plausible pair, ask the user. For an empty repository with no convention, recommend `docs/features/<feature>/product-requirements.md` and its sibling `technical-specification.md` as a proposal and wait for confirmation.

Keep controller state at `.agentic-pipeline/specification-state.json`. State is operational evidence, not part of the specification hash.

Preserve the repository's established trace convention. The controller accepts either flat fields:

```yaml
---
document_type: technical-specification
status: draft
revision: 1
language: Russian
source_prd_path: <repository-relative-prd-path>
source_prd_revision: 1
source_prd_sha256: <64 lowercase hex characters>
---
```

or the equivalent nested authority:

```yaml
---
document_type: technical-specification
status: draft
revision: 1
language: Russian
product_authority:
  path: <repository-relative-prd-path>
  revision: 1
  sha256: <64 lowercase hex characters>
---
```

Do not rewrite a valid repository-owned trace shape merely to prefer the other representation.

Use `status: draft` while editing and `status: approved` for the exact candidate submitted to the final Proofreader. Any semantic edit to an approved specification reopens it as a new draft revision.

## Revising specification authority

When a controller-accepted in-progress specification with an exact `accept-spec` receipt is in `reviewing` state with a completed `record-proofread` result in its active wave, and the canonical PRD receives a newly approved higher revision, use `revise-in-progress`. This route is valid only before runtime state or findings are bound. It requires unchanged canonical paths, exact controller-recorded specification and active-wave bytes, a specification trace matching the prior recorded PRD, a complete approved Requirements validation of the new PRD, a changed SHA, a strictly higher positive PRD revision approved after the current acceptance receipt, and a fresh Architect identity.

The controller uses a resumable pending transition, archives the prior PRD/specification/acceptance/Architect/wave/hold evidence with disposition `superseded_by_prd_revision`, increments the sole specification revision, updates the PRD trace, sets `status: draft`, and enters `awaiting_accept`. Archived findings and questions remain audit evidence only: they are neither current blockers nor readiness credit. The new authority requires a fresh `accept-spec` receipt, a fresh Proofreader cycle, and a fresh `confirm-ready` confirmation by the newly assigned Architect. Do not rerun `init`, delete state, or edit the JSON controller state.

### Revising an exact ready specification

`SPEC_READY` is immutable until a sanctioned revision is opened against exact current specification bytes equal to the recorded ready SHA. Use ordinary `revise-ready` when the canonical PRD has a newly approved, higher positive revision with changed exact bytes. Use explicit `revise-ready --specification-only` when the PRD path, revision, and exact bytes are unchanged and only the technical specification needs correction. Both routes require the canonical PRD to pass the complete approved Requirements validator before any pending state or specification bytes are mutated, canonical unchanged paths, the prior approved specification trace, and a fresh Architect identity not used by any earlier Architect or Proofreader. The PRD-change route additionally requires fresh higher PRD revision/approval authority. The controller atomically records a resumable pending transition, archives the prior authority/readiness/worker evidence, increments the sole unquoted positive specification `revision`, preserves or updates the existing PRD trace as appropriate, sets `status: draft`, and revokes live readiness/cycle state.

For a legacy-only runtime binding, the command is forbidden except during its exact pre-engineering `authority_recovery_hold`. Supply the matching recovery token and unchanged reason; the controller binds them to the prior ready specification SHA and rejects active writers, Engineer/product evidence, sealed/completed slices, non-hold phases, partial runtime state, and tampered token provenance. A sole valid direct v2 runtime permits only the existing `revise-ready --specification-only` route, without a token or legacy residue, when canonical v2 validation and public `status` prove the exact project/PRD/prior-specification authority, `active_assignment: null`, no open gate or question, and neither a terminal state nor checkout recovery. If any legacy runtime residue exists, the complete immutable retired schema-10 state/findings pair must be present and prove its lineage to that v2 state. Closed gates and answered questions may remain only as validated audit history. Multiple, malformed, foreign, mixed, or unproven v2 candidates fail closed. The authorization records the exact v2 state SHA, so pending replay and every later mutating Specification command fail if the bound runtime changes. Reopen ends in `awaiting_accept`, never ordinary `reviewing`; while its final history receipt, PRD, draft, runtime authorization, inputs, and lifecycle projection remain exact, a committed `revise-ready` replay is a byte-noop, and any drift or later Architect/lifecycle progress rejects it. `accept-spec` validates the exact current PRD/spec draft, rechecks bound authorization, and records path/revision/hash/time/Architect/token. `start-cycle` fails closed unless that fresh receipt matches every current value; changed bytes or a stale/absent receipt require another `accept-spec`. Every later proofread, completion, handoff, and `confirm-ready` transition revalidates the recovery authorization. At least one fresh Proofreader cycle and a fresh Architect `confirm-ready` are mandatory; no prior readiness evidence carries forward.

Specification state schema 2 persists one normalized worker-identity history. Loading schema 1 migrates it in place without discarding cycle or readiness evidence, but persists that migration only after the referenced canonical PRD passes the complete approved Requirements validator. A legacy or malformed approved PRD is not grandfathered: revise and reapprove the PRD, then reconverge exact downstream authority. Every Architect/Proofreader ownership and freshness comparison uses NFKC, surrounding-space trimming, and case folding, so case, whitespace, and full-width aliases cannot reuse a prior role identity.

## Required specification coverage

Keep stable, machine-addressable identifiers. Trace every normative technical requirement and verification case to one or more `PRD-REQ-*`, `PRD-NFR-*`, or `PRD-AC-*` IDs. Cover, when relevant:

- goals, non-goals, assumptions, dependencies, and system boundaries;
- current-state evidence and chosen project precedents;
- component ownership, public/internal contracts, data models, and invariants;
- lifecycle, concurrency, persistence, rollback, recovery, and failure behavior;
- security/trust boundaries, resource limits, configuration, and observability;
- migration, compatibility, rollout, and cleanup;
- acceptance mapping and deterministic verification strategy;
- open questions, with category and blocking status.

Coverage is semantic: for each approved behavior or invariant, state its technical realization and verification, or an explicit justified non-applicability. Repeating its source ID alone is not coverage.

For every central component, state its primary responsibility, owned state and lifecycle, dependencies, and prohibited responsibilities. A folder/module/path allocation or component list is not an ownership design.

Do not invent product behavior to fill a technical gap. Prefer the smallest design consistent with the approved PRD and established project architecture.

## Worker contracts

### Generator

Write only the initial missing/stale draft. Read the approved PRD as product authority. The bounded internal Generator may optionally use `$skill-specification-pipeline` in generation mode; if unavailable or invalid, fail fast and generate locally under the same packet. Both routes return the specification SHA, PRD coverage manifest, assumptions, and unresolved product questions. Neither route grants readiness. Stop after Director acceptance.

### Technical Spec Architect

Remain the sole writer until handoff. Resolve supported technical findings; use bounded researchers for exact repository questions instead of broad discovery. For each response, return changed IDs, evidence/rationale, unresolved escalations, checks, and the resulting SHA. Never answer a product/scope/boundary question by assumption.

The Director, not the Architect, owns the cycle counter. A completed Proofreader-to-Architect-response wave consumes one of that Architect's five cycles even when the response concludes that no edit is needed. The fifth non-ready response may complete; a sixth wave for the same identity may not start.

### Proofreader

Be fresh and read-only for one immutable PRD/spec pair. Read the entire pair, project rules, and only the repository evidence needed to validate disputed choices. Return a complete, deduplicated batch:

```text
PROOFREADER_ID
PRD_SHA256
SPEC_SHA256
COVERAGE_COMPLETE: yes|no
FINDINGS: ID | severity | category | requirement IDs | evidence | required resolution
UNRESOLVED: product | scope | boundary | ownership | public-contract
MINORS_ENGINEER_RESOLVABLE: yes|no
VERDICT: pass|revise|user-gate
```

Persist the report path plus every finding/question ID through `record-proofread`; later cycles may supersede an issue, but must not erase its history.

Use Critical for an unsafe/unimplementable core design, Major for a contradiction, missing mandatory behavior, or unverifiable acceptance path, and Minor for a local omission whose resolution cannot alter product meaning or system boundaries.

## Holds and handoffs

On an attempted sixth wave, retain the current Architect and all history but set `spec_convergence_hold`. The Director must publish remaining findings and decide explicitly between:

- `handoff-architect` with a distinct identity and a recorded rationale; or
- a user gate for unresolved product, scope, boundary, ownership, or contract authority.

Handoff gives the new Architect a compact source-backed packet: canonical paths/hashes, current spec, unresolved finding IDs, prior decisions, cycle history, and hold reason. Never summarize away rejected alternatives or reset total waves.

## Readiness evidence

`init` and every `accept-spec` first run the complete approved Requirements validator against the exact canonical PRD. Range shorthand, ambiguous or malformed acceptance declarations, a missing canonical acceptance inventory, and legacy REQ/NFR declaration rows fail before controller state, receipts, or artifact bytes are changed. The final Proofreader and Architect confirmation must reference the same current specification SHA. The PRD must still match the controller's current authority for the active convergence epoch and the specification trace. `confirm-ready` is the only transition to `spec_ready`; prose declarations do not change readiness. Emit `SPEC_READY` plus `NEXT_ACTION: $gamedev-development-plan`, then stop. The Specification stage never starts planning.
