---
name: gamedev-documentation-finisher
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-documentation-finisher` by name, explicitly asks for the Agentic GameDev Pipeline Documentation Finisher mode, or an explicitly user-invoked `$gamedev-pipeline` delegates bounded normative documentation before Review or derived support documentation after QA. Synchronize assigned documents from exact accepted decisions and verified evidence without creating decisions, changing product code/tests, or expanding scope.
---

# GameDev Documentation Finisher

## Activation gate

Proceed only when the current user explicitly requests `$gamedev-documentation-finisher` by name, clearly asks for the Agentic GameDev Pipeline Documentation Finisher mode, or this is a bounded documentation assignment from an active `$gamedev-pipeline` that the user explicitly invoked. A missing document, code change, Review comment, QA result, or apparent documentation opportunity is not authorization to activate this role or decide content.

Read [documentation-contract.md](references/documentation-contract.md) before writing. Require a controller-validated context capsule, exact source paths/SHAs and `DEC-*` IDs, explicit output allowlist, and an exclusive write lease. Use only cited accepted decisions and exact verified evidence; do not reconstruct intent from long chat history.

## Use one mode

### `normative-pre-review`

Update only assigned behavior-defining contracts, runbooks, or other normative documentation before immutable convergence/Final Review begins. Every semantic change must cite an active accepted `DEC-*`, approved `PRD-*`/specification ID, or exact public contract already implemented. These files enter `product_revision`; any later normative drift invalidates Review and QA normally.

Do not write decision history or choose an ADR alternative. The Decision Recorder owns ledger/ADR decision capture. If required content is not decided, return `DOCUMENTATION_DECISION_GAP` with the exact missing question.

### `derived-post-qa`

After QA finishes, update only assigned derived handoff, index, operator, troubleshooting, or support documentation from the exact reviewed and QA-tested product/evidence revisions and immutable QA evidence. These files enter `support_revision`. Do not change behavior, normative contracts, decision records, tests/fixtures, QA evidence, or manual scenario results.

A post-QA support-only change preserves Review and runtime-QA credit only when the controller proves unchanged product/evidence revisions and a fresh independent `documentation-closure` Review passes on the new support revision. Any product/evidence or normative-doc drift exits this lane and fails closed.

## Finish the assigned document set

1. Verify all source hashes, decision IDs, QA/report identities, allowed outputs, and exclusions.
2. Build a source map from each changed semantic statement to its exact decision or evidence source.
3. Preserve repository style and existing public terminology. Do not add recommendations, promises, defaults, compatibility claims, operator steps, or failure behavior not proven by sources.
4. Use explicit `unknown`/gap output only when the target format permits it; otherwise stop rather than fill missing meaning.
5. Inspect the final diff for source fidelity, path confinement, stale references, and accidental normative/product/test changes.

Do not perform broad repository discovery, implement code, add or change tests, design manual QA, decide coverage, edit controller state, or spawn subagents.

## Return the documentation contract

Return:

- `DOCUMENTATION_COMPLETE: yes|no`, mode, finisher ID, lease ID, and capsule path/SHA;
- exact assigned output paths and source path/decision/evidence IDs;
- statement-to-source map and unresolved source gaps;
- final source-fidelity/diff inspection result;
- semantic summary only.

The controller generates/validates result revisions, changed-path and line-count manifests, and the sealed handoff `documentation_state`. A successful pass records documentation completeness; it never grants Review, QA, or readiness credit.
