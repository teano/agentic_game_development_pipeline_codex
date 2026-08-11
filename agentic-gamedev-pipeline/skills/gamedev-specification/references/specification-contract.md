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

The final Proofreader and Architect confirmation must reference the same current specification SHA. The PRD must still match the initialization path/revision/hash and the specification trace. `confirm-ready` is the only transition to `spec_ready`; prose declarations do not change readiness. Emit `SPEC_READY` plus `NEXT_ACTION: $gamedev-development-plan`, then stop. The Specification stage never starts planning.
