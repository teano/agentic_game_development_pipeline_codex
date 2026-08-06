---
name: gamedev-pipeline
description: Orchestrate an approved game feature through resource and runtime preflight, one persistent engineering owner, parallel read-only convergence, immutable Review, targeted recovery, feature-focused runtime QA, and production-readiness. Use to run or resume the GameDev pipeline, route findings without serial worker churn, distinguish findings from execution gates, enforce worker and Review budgets, or recover support and evidence without restarting unchanged runtime work.
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
6. Complete controller preflight in the parent context before spawning an Engineer. Prove numeric resource budgets and cross-config invariants from the approved specification. Record editor/project sync, published configuration, persistence access, multiplayer or multi-place setup, control feasibility, credentials/publication, and planned manual operator steps. Preflight is a director check, not another agent session.

Let an active specification worker finish unless it reports a terminal failure or external blocker. Resume the same worker after an incomplete handoff; do not start a competing generator.

## Run one bounded pipeline

### Engineering

Spawn one `$gamedev-engineer` as the writing owner. Reuse that owner for implementation and every product remediation batch. Transfer ownership only through the explicit controller handoff with a recorded reason. Pass only canonical paths, assigned IDs, revision identities, check commands, and artifact paths. Require the owner to finish discovery, freeze the complete inventory, fix the in-scope batch, run its own checks, and resweep.

Resume the same Engineer for `INCOMPLETE`. Reject a terminal handoff without `AUDIT_COMPLETE: yes`, a complete coverage manifest, and required passing evidence. Record fixed persisted product findings atomically with `engineer-complete --resolved-finding`; never call `resolve-finding` after completion to repair phase state.

A product-changing owner cannot award independent clean credit. After `CHANGED`, do not spawn another writer. Enter one parallel read-only convergence wave on the exact revision.

### Read-only convergence

Launch two or three fresh read-only `$gamedev-review` workers concurrently, as configured, without sharing conclusions. Assign distinct lenses:

- persistence, lifecycle, rollback, concurrency, and recovery;
- configuration, security, resource capacity, trust, and failure atomicity;
- integration, runtime/platform behavior, client boundaries, and supporting documentation.

Workers write reports and findings only. They never remediate. Wait for the complete wave and aggregate every supported finding before returning one frozen batch to the same engineering owner. A passing wave supplies independent clean credit. A failing wave never starts a fresh writer by itself.

### Final Review

After `CLEAN`, launch exactly two fresh `$gamedev-review` workers concurrently on the same immutable revision. Give them complementary architecture/correctness and verification/integration lenses without sharing conclusions.

Wait for both scope-complete reports. The technical director deduplicates supported candidates, registers confirmed findings, and finalizes one decision. Product rework returns one combined batch to the existing engineering owner. Default local remediation uses one fresh targeted closure reviewer after convergence while preserving complementary full-Review evidence. Use a new pair of full Reviews only when remediation changes architecture, lifecycle, ownership, public contract, or a broad/high-risk impact surface.

Support/evidence recovery uses one bounded remediator and one fresh closure reviewer. Runtime product hash drift exits recovery. Changes limited to derived documentation, handoff/index metadata, tests, fixtures, or harnesses preserve clean runtime and full-Review credit; do not repeat architecture Review or product convergence.

### Runtime QA

After the Review chain passes, launch one fresh read-only `$gamedev-qa` on the exact revision. Reuse deterministic evidence and test only the feature, directly affected shared behavior, and a small justified adjacent smoke set.

Before spawning QA, inspect the preflight capability matrix again. Resolve unavailable prerequisites first. If ordinary player control is known to require a human, use the planned operator path instead of launching an automation worker that cannot execute the scenario.

QA must complete every independent executable scenario even after finding a defect. Scenarios whose prerequisites are invalidated are linked to the finding as `blocked_by_finding`, not classified as user, environment, or test gates.

When QA has a stable reproducible product candidate, the assigned engineering owner may begin read-only discovery while QA completes its matrix and report. The owner must not edit until the controller records `qa-complete` and the normalized finding. If QA reclassifies the candidate as a gate or test error, end the triage without product changes.

Route terminal QA automatically:

- `pass` -> readiness;
- `fail_product` -> register the complete QA product batch and return it to the existing engineering owner;
- `blocked_user`, `blocked_environment`, or `error_test` -> remain in QA and preserve current Engineer/Review evidence.

`fail_product` is a finding transition, never a “product gate” and never a reason to ask the user to start engineering.

## Control autonomy and convergence

Perform ordinary in-scope work without confirmation: local fixes, tests, reruns, support/evidence recovery, QA-to-owner routing, read-only convergence, Reviews, QA, and technical-director checkpoints.

Ask the user only for:

- an unresolved product choice;
- an architectural, lifecycle, ownership, or material slice expansion;
- explicit acceptance of residual risk;
- credentials, publication, spending, irreversible action, or a manual user-only step.

After the configured number of owner changes or convergence waves without a pass, stop at `convergence_hold`. After two failed non-product recovery cycles, stop at `recovery_hold`. The technical director must inspect the complete remaining inventory and record `authorize-iteration --reason`. This checkpoint requires the user only when one of the decisions above remains unresolved.

The controller also limits unique worker identities and full-Review waves. When either budget opens a checkpoint, consolidate the remaining scope and prefer targeted closure. Extend the budget only with `authorize-budget --additional-workers ... [--additional-full-review-waves ...] --reason ...`; never hide a long chain behind reset counters.

Never create an unbounded agent loop. Allow only one writing owner per checkout. Resume incomplete or gated workers; use fresh workers only for configured read-only independence. Status must report unique workers, reused owners, convergence wave, full-Review waves, and the reason for every authorization.

## Keep handoffs compact

Use `compute-revisions` for the canonical runtime product, support, evidence, and composite hash recipe. Put production source, configuration, manifests, normative ADRs/contracts, and approved feature documents in `product`; derived handoff/index/operator documentation in `support`; and tests, fixtures, deterministic harnesses, and verification inputs in `evidence`. Reports, logs, screenshots, revision manifests, and controller state are not revision inputs.

Comment only on phase transitions, newly frozen inventories, verified remediation, gates, checkpoints, and the terminal result. Status output must include `next_action`; continue automatically whenever `user_input_required` is false.

Declare only a **production-ready candidate**, and only after `ready` succeeds. Deployment, publication, store submission, migration, spending, and risk acceptance remain external decisions.
