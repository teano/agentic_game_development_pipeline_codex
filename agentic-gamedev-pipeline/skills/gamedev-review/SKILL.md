---
name: gamedev-review
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-review` or an active, explicitly invoked `$gamedev-pipeline` Director delegates one immutable review assignment. Produce independent exact-revision findings and component credit without remediation. Do not activate for ordinary code review, audit, or implementation feedback.
---

# GameDev Independent Review

## Activation gate

Proceed only on the explicit activation described above. Ordinary review, audit, verification, or game-development feedback is not authorization. Do not activate another GameDev stage.

Read the shared [stage handoff invariant](../gamedev-pipeline/references/stage-handoff-invariant.md). Remain immutable to product, evidence, support, approved documents, decisions, coverage, and controller state. Write only the assigned isolated report/credit artifact.

Every mode requires a controller-validated reviewer capsule with exact revisions, paths/SHAs/IDs/evidence, read boundary, output paths, and capsule payload ceilings. Before work, read only [review-output-contract.md](references/review-output-contract.md). Every completion requires its exact component-credit manifest, including recovery verification. The reviewer must be independent of every Engineer/writer. A logical verifier ID may be reused later, but every phase starts in a fresh no-history session with a new capsule. Never use sibling conclusions or unbounded chat history.

## Use one mode

- `risk-audit`: one assigned convergence lens;
- `full`: the controller-required independent Final Review assignment;
- `targeted-product-closure`: verify a frozen local product remediation and induced boundaries;
- `recovery-verification`: verify frozen support/evidence recovery, its finalized coverage aggregate, and unchanged product identity;
- `documentation-closure`: verify derived support changes against immutable post-QA sources.

Reuse an exact component product hash + contract hash + lens credit. Overall composite drift alone does not invalidate product credit; relevant product/contract drift does. Freshly inspect invalidated components, assigned boundaries, and required composition only.

For `full`, inspect the cumulative current candidate and verify repository policy, approved feature documents, active decisions, exact revisions, controller manifests/handoffs, finalized coverage, normative documentation state, Scope Contract, semantic preservation, central-component responsibility boundaries, assigned acceptance criteria, and the assigned architecture/correctness or verification/integration lens. An integration criterion needs evidence through a real supported end-to-end path; evidence that bypasses the supported entry/integration path, replaces production composition with a synthetic fixture, or derives its oracle from implementation logic is supplementary only. Responsibility concentration introduced by or on the current feature path is an architecture/correctness candidate finding, not theoretical hardening merely because no runtime failure was reproduced. Input mechanics gaps are `INCOMPLETE`, not product findings.

For closure modes, inspect only frozen findings, changed components/inputs, induced boundaries, and preserved complementary credits. Recovery verification requires exact capsule and credit manifest plus current finalized coverage continuity. Documentation closure requires passed QA, unchanged product/evidence identities, exact statement source mappings, current support revision, the worker-owned documentation-closure report schema, and `review_mode: documentation_closure` credit.

Do not read sibling conclusions, edit, request early remediation, use runtime/Computer Use, rerun broad green suites, set `blocking`/`remediation_required`, mutate deferred findings, prescribe a writer wave, decide behavior, accept risk, edit state, or spawn another stage.

## Complete the stage

Return `REVIEW_COMPLETE: yes|no`, mode, reviewer/capsule IDs, exact revisions, `PASS|FAIL|INCOMPLETE`, inspected IDs/scope/exclusions, context payload metrics, credit identities/status, complete candidate findings with exact evidence/dimensions, source gaps, report path, and mode-specific composition/support proof.

The generic human-readable report is audit-only: it cannot authorize documentation, decisions, or findings. Register every candidate finding through the Director/controller `add-finding` boundary; only validated component credit and the mode-specific structured closure receipt are authoritative artifacts.

A required support-contract defect is a `support` candidate with the exact approved support path evidence; the controller may derive `remediation_required=true` without product `blocking`.

- `PASS` -> `NEXT_ACTION: $gamedev-qa` for completed Final Review/recovery closure, or the Director-provided next review/finalization action for convergence/documentation closure;
- `FAIL` -> `NEXT_ACTION: $gamedev-engineer` for product work or the Director's bounded recovery action for support/evidence work;
- `INCOMPLETE` -> `NEXT_ACTION: $gamedev-review` with the same reviewer when its capsule remains exact.

Do not execute `NEXT_ACTION`; stop after returning the complete inventory.
