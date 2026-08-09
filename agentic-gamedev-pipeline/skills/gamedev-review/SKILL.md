---
name: gamedev-review
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-review` by name, explicitly asks for the Agentic GameDev Pipeline Review mode, or an explicitly user-invoked `$gamedev-pipeline` delegates a review assignment. Perform one independent read-only convergence audit, scope-complete final Review, targeted local-product closure Review, or support/evidence recovery closure Review on an exact game revision. Do not infer activation from generic code review, audit, verification, or game-development work.
---

# GameDev Final Review

## Activation gate

Proceed only when the current user explicitly requests `$gamedev-review` by name, clearly asks for the Agentic GameDev Pipeline Review mode, or this is a review assignment delegated by an active `$gamedev-pipeline` that the user explicitly invoked. A request for ordinary code review, audit, verification, or game-development feedback is not authorization. If this gate is not satisfied, do not emit pipeline Review contracts or create pipeline review artifacts; continue under ordinary review instructions and only other explicitly requested skills.

Remain read-only with respect to product code, tests, configuration, approved documents, and pipeline state. Write only the assigned report under `tests/<feature>/reviews/<revision>/<reviewer-id>/`.

Use one mode:

- `risk-audit`: one assigned read-only convergence lens on the complete immutable candidate;
- `full`: independently review the entire assigned slice on the clean revision;
- `targeted-product-closure`: verify a frozen local product batch, its changed impact surface, and preserved complementary full-Review evidence;
- `recovery-verification`: verify only a completed support/evidence recovery batch while relying on the preserved full Reviews.

Every mode receives a component-credit manifest path. For each component record its product hash, contract hash, exact lens set, review revision, and `fresh` or `reused` mode. If a valid credit already has the same component product hash, contract hash, and lenses, reuse it; a full reread is forbidden. Revision drift alone does not invalidate credit. Only affected component product-hash or contract-hash drift invalidates that credit.

## Risk audit

Inspect the assigned slice/component inventory through the assigned persistence/lifecycle, config/security/capacity, or integration/runtime/docs lens. Reuse valid component credits and inspect only invalidated components plus newly composed boundaries. Write findings and the report only; never remediate. Do not read sibling audit conclusions. The technical director aggregates the complete wave and returns one frozen blocking batch to the persistent writing owner.

## Full Review

1. Read repository policy, approved feature documents, assigned acceptance IDs, exact revisions, verification report, revision manifest, and coverage manifest.
2. Read the approved slice Scope Contract, controller scope history/churn, verified change-manifest, and diff-summary. Reject stale or missing scope artifacts as `INCOMPLETE`. Fail an unmapped product file/symbol, forbidden component, unapproved shared touchpoint, drive-by cleanup/refactor, material lifecycle/ownership/public-contract change, or budget breach that the controller did not already hold.
3. Reject missing, stale, or mismatched inputs as `INCOMPLETE`; do not turn them into product findings.
4. This is the mandatory final whole-feature pair after all slices. Reuse valid per-component credits, trace every acceptance criterion, and freshly audit cross-slice composition and every new boundary. Continue after each defect until the candidate inventory is complete.
5. Apply the assigned deep lens while covering the full slice:
   - architecture/correctness: ownership, lifecycle, state, concurrency, trust, persistence, performance, and extensibility;
   - verification/integration: boundaries, negative/recovery behavior, coverage quality, platform constraints, regression risk, and operational safety.
6. Check repository-required supporting product documents, including ADR applicability when policy requires it.

Do not read the other reviewer's conclusions. Do not edit, request early remediation, launch Studio/game/Computer Use, or rerun the full automated suite. Run only cheap read-only diagnostics that resolve a specific question.

## Recovery verification

Read the two preserved full reports, aggregate normalized support/evidence findings, remediation diff/report, revision and coverage manifests, and affected/aggregate results. Verify every frozen finding and every changed support/evidence file. Runtime product hash drift or a reproduced product defect exits recovery to the engineering owner; do not repeat the architecture Review.

## Targeted product closure

Read the preserved applicable reports/credits, frozen local product finding batch, owner remediation diff/report, regressions, and the complete changed impact surface. Be one fresh identity independent of the writer and base wave. Verify only frozen findings, changed components, and induced boundaries; do not repeat the full audit. Minor, hardening, deferred, and controller-nonblocking candidates never start remediation. Require a new full convergence wave only for actual architecture, lifecycle, ownership, public-contract, expanded approved shared-touchpoint, or broad/high-risk change.

## Return one contract

Return:

- `REVIEW_COMPLETE: yes|no`;
- mode, composite/product/support/evidence revisions, and reviewer ID;
- `PASS`, `FAIL`, or `INCOMPLETE`;
- inspected scope and acceptance IDs;
- verification identities checked;
- scope contract SHA/baseline, change-manifest/diff-summary identities, mapped touchpoints, budget use, and scope-churn checked;
- complete candidate findings with `finding_kind`, severity, `scope_relation`, `introduced_by_candidate`, `production_reachability`, exact approved `blocks_acceptance_ids`, required-invariant boolean/evidence, exact revision evidence, and failure/reproduction path;
- for every supported nonblocking out-of-scope candidate, the component, contract, root cause, failure mode, effect, conditions, impacts, evidence, and independent occurrence identity needed for Director `backlog-upsert`;
- input gaps and exclusions;
- report path.
- component-credit manifest path, fresh/reused credit IDs, invalidated component hashes/contracts, and for Final Review explicit cross-slice composition/new-boundary coverage.

Never set `blocking`, edit/deduplicate the deferred backlog, or prescribe an Engineer wave. The controller derives blocking and only the technical director upserts supported deferred candidates. Use unknown reachability only for a bounded triage question. Evidence Major requires proof that no other mandatory core-acceptance evidence exists and that the current test can miss a real product defect; otherwise use Minor or `support`. `PASS` requires complete unchanged-revision coverage with no controller-blocking candidate. `FAIL` requires a candidate whose complete dimensions allow the controller to block. `INCOMPLETE` means the same reviewer must resume.

Do not demand duplicate proof without an approved requirement or demonstrated coverage failure. Do not classify unavailable tools or unexecuted checks as product defects, accept risk, edit controller state, declare readiness, or spawn agents.
