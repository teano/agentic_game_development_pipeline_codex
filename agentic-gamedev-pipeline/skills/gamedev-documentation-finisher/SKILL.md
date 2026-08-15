---
name: gamedev-documentation-finisher
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-documentation-finisher` or an active, explicitly invoked `$gamedev-pipeline` Director delegates one bounded documentation lane. Synchronize exact normative or derived support docs from accepted sources without new decisions. Do not activate from ordinary documentation needs or review comments.
---

# GameDev Documentation Finisher

## Activation gate

Proceed only on the explicit activation described above. A missing document, code change, Review comment, QA result, or apparent opportunity is not authorization to decide or write content. Do not activate another GameDev stage.

Read the shared [stage handoff invariant](../gamedev-pipeline/references/stage-handoff-invariant.md) and [documentation-contract.md](references/documentation-contract.md). The contract is canonical for lane state, allowed sources, statement-map schema, drift, and controller mechanics.

Require a controller-validated capsule, exact source paths/SHAs and IDs, explicit output allowlist, capsule payload ceilings, and exclusive lease. Use only controller-recognized accepted decisions and exact verified evidence; do not reconstruct intent from chat history.

## Use one mode

### `normative-pre-review`

Update only assigned behavior-defining contracts/runbooks before immutable convergence/Final Review. Every changed semantic statement maps to an active accepted decision, approved requirement/specification ID, or exact implemented public contract. Missing authority returns `DOCUMENTATION_DECISION_GAP`. Normative output enters `product_revision`; later drift invalidates downstream credit.

### `derived-post-qa`

After passed QA, update only assigned handoff, index, operator, troubleshooting, or support docs from exact reviewed/QA-tested product/evidence identities and immutable evidence. Derived output enters `support_revision`; it must not change behavior, normative contracts, decisions, tests/fixtures, or QA results.

Support-only completion preserves QA credit only when product/evidence identities remain exact and a fresh documentation-closure review passes. Any product/evidence/normative drift exits this lane.

## Write exact packets

Before producing the write packet, read only the worker-owned [semantic write packet contract](../gamedev-pipeline/references/semantic-write-packet.md); the lane-specific statement-map contract remains in `documentation-contract.md`.

1. Verify sources, IDs, output allowlist, exclusions, and current lane/revisions.
2. Produce a schema-1 semantic write packet containing the complete domain inventory, exact changed paths with semantic annotations, and open assumptions. Every documentation-lane change carries one unique `DOC-CHG-*` `change_id`.
3. Produce a separate schema-1 statement source map whose statement IDs are the exact union of semantic-packet `change_id` values. A statement ID may repeat only for distinct sources of the same change; every row maps one changed path to an allowed source kind/ID/path, exact current source SHA, and exact current target SHA (or `null` for deletion). Normative sources are decision/requirement/specification/public-contract; derived sources are active decisions, closed QA manual evidence, Final Review credit manifests, or controller handoffs present in the capsule. Generic role reports and capability-probe reports are audit artifacts, not documentation authority.
4. Preserve repository style and terminology. Add no recommendation, promise, default, compatibility claim, operator step, or failure behavior absent from sources.
5. Inspect the final diff for fidelity, confinement, stale references, and accidental product/test/lane changes.

Do not perform broad discovery, implement code/tests, design QA/coverage, write decision history, edit controller state, or spawn another stage.

## Complete the stage

Return `DOCUMENTATION_COMPLETE: yes|no`, mode, finisher/lease/capsule IDs, exact outputs/source IDs, semantic packet path, statement source-map path, unresolved gaps, and final diff inspection. The controller validates both packets, computes revisions/counts, and generates `documentation_state` and the handoff.

- normative success -> `NEXT_ACTION: $gamedev-review`;
- derived success -> `NEXT_ACTION: $gamedev-review` in documentation-closure mode;
- gap/drift -> the exact decision, product, evidence, or stage route proven by the controller.

Do not execute `NEXT_ACTION`; stop after the handoff.
