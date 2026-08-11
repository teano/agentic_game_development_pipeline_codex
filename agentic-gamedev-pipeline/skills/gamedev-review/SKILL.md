---
name: gamedev-review
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-review` by name, explicitly asks for the Agentic GameDev Pipeline Review mode, or an explicitly user-invoked `$gamedev-pipeline` delegates an immutable review assignment. Perform one independent read-only convergence audit, scope-complete Final Review, targeted product closure, support/evidence recovery closure, or post-QA derived-documentation closure on exact revisions. Do not infer activation from ordinary code review or audit work.
---

# GameDev Independent Review

## Activation gate

Proceed only when the current user explicitly requests `$gamedev-review` by name, clearly asks for the Agentic GameDev Pipeline Review mode, or this is a review assignment delegated by an active `$gamedev-pipeline` that the user explicitly invoked. Ordinary review, audit, verification, or game-development feedback is not authorization.

Remain immutable with respect to product code, tests, configuration, approved documents, decision records, coverage artifacts, support documents, and pipeline state. Write only the assigned report under `tests/<feature>/reviews/<revision>/<reviewer-id>/`. Require a controller-validated bounded context capsule with exact paths/SHAs/IDs/evidence and no sibling conclusions or long chat history.

Use one mode:

- `risk-audit`: one assigned read-only convergence lens on the complete immutable product candidate;
- `full`: one member of the mandatory independent Final Review pair;
- `targeted-product-closure`: verify a frozen local product remediation and induced boundaries;
- `recovery-verification`: verify a bounded support/evidence recovery while relying on preserved product Reviews;
- `documentation-closure`: after QA, verify only derived support changes against immutable sources while proving unchanged product/evidence.

Every mode receives a controller-validated component-credit manifest. Reuse an exact component product hash + contract hash + lens credit; a fresh full reread is forbidden. Overall composite drift alone does not invalidate product credit. Only relevant product/contract drift invalidates it.

## Convergence and Final Review

For `risk-audit`, inspect only the assigned persistence/lifecycle, config/security/capacity, or integration/runtime/docs lens, invalidated components, and new composition boundaries. Never read sibling reports or remediate.

For `full`:

1. Verify repository policy, approved feature documents, active decision ledger/ADRs, exact revisions, controller-generated revision/change/diff/handoff manifests, schema-2 finalized coverage manifest, and `documentation_state.normative` complete/not-required.
2. Reject stale, missing, hash-mismatched, over-budget, or controller-unvalidated mechanics as `INCOMPLETE`; do not turn an input gap into a product finding.
3. Check Scope Contract mapping and inspect every assigned acceptance criterion. Reuse valid component credits, then freshly audit cross-slice composition and new boundaries.
4. Apply the assigned architecture/correctness or verification/integration lens. Treat Coverage Steward semantics as an input, but report an evidence candidate when exact code/test facts show it can miss accepted behavior.
5. Verify normative documentation matches active accepted decisions. Do not invent the missing decision or write documentation.

Do not read the other reviewer's conclusions. Do not edit, request early remediation, launch runtime/Computer Use, or rerun full green suites. Run only cheap read-only diagnostics for a specific question. Finish the complete inventory before returning.

## Closure modes

For `targeted-product-closure`, verify only the frozen findings, changed components, induced boundaries, and preserved complementary credits. Request a new full wave only for an actual architecture, lifecycle, ownership, public-contract, expanded shared-touchpoint, or broad/high-risk change.

For `recovery-verification`, verify every frozen support/evidence finding and changed input. Runtime product drift or a reproduced product defect exits recovery; do not repeat architecture Review.

For `documentation-closure`, require passed QA plus exact QA product/evidence revisions equal to current product/evidence revisions. Inspect every changed support statement against named decision, normative, controller, Review, QA, or capability evidence. Fail any new decision, normative claim, rewritten QA result, unsupported operator step, stale reference, or non-support drift. This one fresh reviewer grants only current-support closure credit; it never rewrites or replaces independent Final Review/QA credit.

## Return one contract

Return:

- `REVIEW_COMPLETE: yes|no`, mode, reviewer/capsule IDs, and exact input revisions;
- `PASS`, `FAIL`, or `INCOMPLETE`;
- inspected scope, acceptance/decision/coverage/documentation IDs, exclusions, and context metrics;
- controller manifest/credit identities checked and fresh/reused/invalidated credits;
- complete candidate findings with all classification dimensions and exact revision evidence;
- compact supported deferred candidates for Director upsert;
- source gaps and report path;
- for Final Review, explicit cross-slice composition/new-boundary coverage;
- for documentation closure, exact changed support paths, source mappings, unchanged product/evidence proof, and current support revision.

Never set `blocking`, edit/deduplicate deferred findings, prescribe an Engineer wave, decide missing behavior, accept risk, edit controller state, declare readiness, or spawn agents. `PASS` requires immutable scope-complete work with no candidate that the controller can classify blocking. `FAIL` requires complete evidence/dimensions. `INCOMPLETE` resumes the same reviewer.
