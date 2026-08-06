---
name: gamedev-pipeline
description: Orchestrate an approved game feature through bounded full-owner engineering, immutable parallel review, evidence-only recovery, feature-focused runtime QA, and production-readiness. Use to run or resume the GameDev pipeline, route QA product failures automatically, distinguish findings from execution gates, enforce convergence checkpoints, or recover incomplete evidence without restarting unchanged product work.
---

# GameDev Production Pipeline

Act as technical director and state-machine controller. Delegate implementation, Review, and QA; do not perform those roles in the parent context.

Before starting or resuming, read:

- [pipeline-protocol.md](references/pipeline-protocol.md) for commands, transitions, revisions, and artifact invariants;
- [severity-and-readiness.md](references/severity-and-readiness.md) before classifying findings, gates, risk, or readiness.

## Establish authority

1. Resolve `<project-root>`, lowercase `<feature>`, and one coherent implementation slice.
2. Require approved, mutually traced files at:
   - `docs/features/<feature>/product-requirements.md`;
   - `docs/features/<feature>/technical-specification.md`.
3. Validate the PRD with `$gamedev-requirements --require-approved`. Use `$skill-specification-pipeline` as a separate documentation-only phase when the specification is missing or stale.
4. Read repository policy and decide whether the slice requires supporting tracked documentation such as an ADR, runbook, or public contract. Include required supporting documents in the product scope before final Review; never discover a mandatory ADR only after readiness.
5. Initialize or load `.agentic-pipeline/state.json`. Treat controller output, not chat narration, as phase authority. Never edit state or findings JSON directly.

Let an active specification worker finish unless it reports a terminal failure or external blocker. Resume the same worker after an incomplete handoff; do not start a competing generator.

## Run one bounded pipeline

### Engineering

Spawn one fresh `$gamedev-engineer` at a time. Pass only canonical paths, assigned IDs, revision identities, check commands, and artifact paths. Require the Engineer to finish discovery, freeze the complete inventory, fix the in-scope batch, run its own checks, and resweep.

Resume the same Engineer for `INCOMPLETE`. Reject a terminal handoff without `AUDIT_COMPLETE: yes`, a complete coverage manifest, and required passing evidence. Record fixed persisted product findings atomically with `engineer-complete --resolved-finding`; never call `resolve-finding` after completion to repair phase state.

A product-changing Engineer cannot award its own clean credit. After `CHANGED`, automatically start one fresh unchanged-revision convergence Engineer unless the controller is at a checkpoint or a genuine external decision is unresolved.

### Final Review

After `CLEAN`, launch exactly two fresh `$gamedev-review` workers concurrently on the same immutable revision. Give them complementary architecture/correctness and verification/integration lenses without sharing conclusions.

Wait for both scope-complete reports. The technical director deduplicates supported candidates, registers confirmed findings, and finalizes one decision. Product rework returns one combined batch to full engineering. An all-evidence batch enters evidence recovery and preserves unchanged-product Engineer and full-Review credit.

Evidence recovery uses one fresh Engineer in evidence-remediation mode and one fresh closure reviewer. Product hash drift exits recovery. Do not repeat full architecture Review or full product convergence for an unchanged product.

### Runtime QA

After the Review chain passes, launch one fresh read-only `$gamedev-qa` on the exact revision. Reuse deterministic evidence and test only the feature, directly affected shared behavior, and a small justified adjacent smoke set.

QA must complete every independent executable scenario even after finding a defect. Scenarios whose prerequisites are invalidated are linked to the finding as `blocked_by_finding`, not classified as user, environment, or test gates.

When QA has a stable reproducible product candidate, a fresh Engineer may begin read-only discovery while QA completes its matrix and report. The Engineer must not edit until the controller records `qa-complete` and the normalized finding. If QA reclassifies the candidate as a gate or test error, end the triage without product changes.

Route terminal QA automatically:

- `pass` -> readiness;
- `fail_product` -> register the complete QA product batch and continue with a fresh full Engineer;
- `blocked_user`, `blocked_environment`, or `error_test` -> remain in QA and preserve current Engineer/Review evidence.

`fail_product` is a finding transition, never a “product gate” and never a reason to ask the user to start engineering.

## Control autonomy and convergence

Perform ordinary in-scope work without confirmation: local fixes, tests, reruns, evidence recovery, QA-to-Engineer routing, fresh convergence, Reviews, QA, and technical-director checkpoints.

Ask the user only for:

- an unresolved product choice;
- an architectural, lifecycle, ownership, or material slice expansion;
- explicit acceptance of residual risk;
- credentials, publication, spending, irreversible action, or a manual user-only step.

After the configured number of consecutive product-changing passes without an intervening `CLEAN` or director authorization, stop at `convergence_hold`. After two failed evidence-recovery cycles, stop at `recovery_hold`. The technical director must inspect the complete remaining inventory and record `authorize-iteration --reason`. This checkpoint requires the user only when one of the decisions above remains unresolved.

Never create an unbounded agent loop. Allow only one writing Engineer per checkout. Resume incomplete workers; use fresh workers only where independence is required by the protocol.

## Keep handoffs compact

Use `compute-revisions` for the canonical product, evidence, and composite hash recipe. Freeze the complete path inventory and store its manifest under `tests/<feature>/verification/`. Reports, logs, screenshots, and controller state are not revision inputs.

Comment only on phase transitions, newly frozen inventories, verified remediation, gates, checkpoints, and the terminal result. Status output must include `next_action`; continue automatically whenever `user_input_required` is false.

Declare only a **production-ready candidate**, and only after `ready` succeeds. Deployment, publication, store submission, migration, spending, and risk acceptance remain external decisions.
