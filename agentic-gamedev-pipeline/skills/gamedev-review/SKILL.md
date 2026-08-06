---
name: gamedev-review
description: Perform one independent scope-complete read-only final Review or one focused evidence-recovery closure Review on an exact game revision. Use after CLEAN for two parallel full Reviews, or after evidence-only remediation to verify the normalized batch, changed evidence, aggregate result, coverage manifest, and unchanged product hash before runtime QA.
---

# GameDev Final Review

Remain read-only with respect to product code, tests, configuration, approved documents, and pipeline state. Write only the assigned report under `tests/<feature>/reviews/<revision>/<reviewer-id>/`.

Use one mode:

- `full`: independently review the entire assigned slice on the clean revision;
- `recovery-verification`: verify only a completed evidence-recovery batch while relying on the preserved full Reviews.

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

Read the two preserved full reports, aggregate normalized evidence findings, remediation diff/report, revision and coverage manifests, and affected/aggregate results. Verify every frozen finding and every changed evidence file. Product hash drift or a reproduced product defect exits recovery to full engineering; do not repeat the architecture Review.

## Return one contract

Return:

- `REVIEW_COMPLETE: yes|no`;
- mode, revision, and reviewer ID;
- `PASS`, `FAIL`, or `INCOMPLETE`;
- inspected scope and acceptance IDs;
- verification identities checked;
- complete candidate findings with severity, exact evidence, and failure/reproduction path;
- input gaps and exclusions;
- report path.

`PASS` requires complete unchanged-revision coverage with no critical or major candidate. `FAIL` requires a reproduced or completely reasoned product/evidence defect. `INCOMPLETE` means the same reviewer must resume.

Do not demand duplicate proof without an approved requirement or demonstrated coverage failure. Do not classify unavailable tools or unexecuted checks as product defects, accept risk, edit controller state, declare readiness, or spawn agents.
