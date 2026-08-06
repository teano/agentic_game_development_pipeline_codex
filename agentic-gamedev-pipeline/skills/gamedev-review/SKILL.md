---
name: gamedev-review
description: Perform one independent read-only convergence audit, one scope-complete final Review, one targeted local-product closure Review, or one support/evidence recovery closure Review on an exact game revision. Use parallel risk lenses before final Review, preserve unaffected Review credit after bounded remediation, and verify changed support/evidence without restarting unchanged runtime work.
---

# GameDev Final Review

Remain read-only with respect to product code, tests, configuration, approved documents, and pipeline state. Write only the assigned report under `tests/<feature>/reviews/<revision>/<reviewer-id>/`.

Use one mode:

- `risk-audit`: one assigned read-only convergence lens on the complete immutable candidate;
- `full`: independently review the entire assigned slice on the clean revision;
- `targeted-product-closure`: verify a frozen local product batch, its changed impact surface, and preserved complementary full-Review evidence;
- `recovery-verification`: verify only a completed support/evidence recovery batch while relying on the preserved full Reviews.

## Risk audit

Inspect the full candidate through the assigned persistence/lifecycle, config/security/capacity, or integration/runtime/docs lens. Continue until the complete lens inventory is frozen. Write findings and the report only; never remediate. Do not read sibling audit conclusions. The technical director aggregates the complete parallel wave and returns one batch to the persistent writing owner.

## Full Review

1. Read repository policy, approved feature documents, assigned acceptance IDs, exact revisions, verification report, revision manifest, and coverage manifest.
2. Reject missing, stale, or mismatched inputs as `INCOMPLETE`; do not turn them into product findings.
3. Trace every acceptance criterion and declared scope area. Continue after each defect until the candidate inventory is complete.
4. Apply the assigned deep lens while covering the full slice:
   - architecture/correctness: ownership, lifecycle, state, concurrency, trust, persistence, performance, and extensibility;
   - verification/integration: boundaries, negative/recovery behavior, coverage quality, platform constraints, regression risk, and operational safety.
5. Check repository-required supporting product documents, including ADR applicability when policy requires it.

Do not read the other reviewer's conclusions. Do not edit, request early remediation, launch Studio/game/Computer Use, or rerun the full automated suite. Run only cheap read-only diagnostics that resolve a specific question.

## Recovery verification

Read the two preserved full reports, aggregate normalized support/evidence findings, remediation diff/report, revision and coverage manifests, and affected/aggregate results. Verify every frozen finding and every changed support/evidence file. Runtime product hash drift or a reproduced product defect exits recovery to the engineering owner; do not repeat the architecture Review.

## Targeted product closure

Read both preserved full reports, the normalized local product finding batch, owner remediation diff/report, convergence reports, regressions, and the complete changed impact surface. Verify every frozen finding and induced boundary. Fail back to the same owner on a supported defect. Require a new full Review pair only when the remediation actually changed architecture, lifecycle, ownership, public contract, or a broad/high-risk surface.

## Return one contract

Return:

- `REVIEW_COMPLETE: yes|no`;
- mode, composite/product/support/evidence revisions, and reviewer ID;
- `PASS`, `FAIL`, or `INCOMPLETE`;
- inspected scope and acceptance IDs;
- verification identities checked;
- complete candidate findings with severity, exact evidence, and failure/reproduction path;
- input gaps and exclusions;
- report path.

`PASS` requires complete unchanged-revision coverage with no critical or major candidate. `FAIL` requires a reproduced or completely reasoned product/support/evidence defect. `INCOMPLETE` means the same reviewer must resume.

Do not demand duplicate proof without an approved requirement or demonstrated coverage failure. Do not classify unavailable tools or unexecuted checks as product defects, accept risk, edit controller state, declare readiness, or spawn agents.
