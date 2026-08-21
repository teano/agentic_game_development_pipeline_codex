---
name: gamedev-pipeline
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-pipeline` or explicitly asks to run/resume the Agentic GameDev Pipeline. Direct exact `PRD_READY`, `SPEC_READY`, and `PLAN_READY` inputs through bounded engineering, independent Review, QA, and readiness. Do not activate for ordinary development, testing, review, or release work.
---

# GameDev Production Pipeline

## Activation gate

Proceed only on the explicit activation described above. Installed files, repository state, approved documents, or an ordinary implement/review/test/ship request is not authorization. Without activation, do not initialize state or activate any GameDev stage.

Act as the sole cross-stage Director and controller owner. Read these compact always-core contracts before startup:

- [stage-handoff-invariant.md](references/stage-handoff-invariant.md);
- [pipeline-protocol.md](references/pipeline-protocol.md).

The Director is orchestration-only. Perform authority, preflight, controller, validation, routing, hold, and user-gate mechanics directly. Delegate every specialized implementation, research, writing, remediation, Review, and QA assignment to a real non-Director worker; never absorb that work when delegation is unavailable.

Start every phase assignment in a new session with no inherited Director or worker chat history (`fork_turns: none` or equivalent). Pass only root, skill/mode, controller-validated capsule or exact read-only assignment, worker-owned output contract, and stop condition. The controller may preserve one logical non-writer verifier ID across Review, QA, and documentation closure, but each phase still uses a fresh isolated session and capsule. An Engineer or writer ID is never that verifier.

Director-only mechanics need no worker: briefing, accepted no-research/coverage transitions, capsule/lease preparation, owner transfer, state/checkpoint validation, and hold/resume records. Activate Research only for approved `RESEARCH-*` briefs and Documentation Finisher only for a real documentation delta.

## Load phase contracts only when needed

- Before slice research, coverage, engineering, normative docs, product remediation, or scope rebaseline, read [engineering-and-coverage.md](references/engineering-and-coverage.md).
- Before convergence, Final Review, recovery, QA, derived docs, documentation closure, or readiness, read [review-qa-and-recovery.md](references/review-qa-and-recovery.md).
- Before classifying a finding/gate/risk or evaluating readiness, read [severity-and-readiness.md](references/severity-and-readiness.md).
- Before routing a supported out-of-scope candidate, read [deferred-findings.md](references/deferred-findings.md).
- Only when compact status reports generated dashboard revision drift, read [lifecycle-projection-recovery.md](references/lifecycle-projection-recovery.md).

Do not preload conditional references or worker-owned schema references merely because the pipeline started or a capsule is needed. Exact controller syntax comes from the current command's `--help`.

## Establish authority and direct one runtime

1. Resolve the project root, lowercase feature, and one repository-owned PRD/specification/plan/ledger chain. Preserve path case and create no alternate namespace.
2. Require exact current `PRD_READY`, `SPEC_READY`, and `PLAN_READY`. If one is absent or stale, return `PIPELINE_STARTED: no` and the proven upstream `NEXT_ACTION`; do not run that upstream stage inside this activation.
3. Initialize/load runtime state only after upstream gates pass. Treat controller output as authority; never edit state/findings/backlog JSON directly.
4. Complete exact-set preflight before any specialized runtime stage. If a resource/capability proof fails, activate nobody and return the controller's exact minimum resume action.
5. Before every transition, read one compact status containing phase, authority/revision summary, active hold/lease/owner, and deterministic `next_action`. Use a targeted `--section` only for a proven diagnostic; ordinary `status --full` is forbidden.
6. Validate each capsule/receipt/completion and the resulting controller state before the next assignment. A worker `NEXT_ACTION` is advisory; controller state is authority.

Use state plus `director-checkpoint.json` as durable memory, never raw logs or reasoning. After compaction/replacement, validate checkpoint hashes and resume from compact state without repeating work. Cache command help by controller version. Use at most one compact status per transition, wait once per active worker set, and suppress unchanged polling.

Keep at most one write lease active. Follow approved slice order and the controller-required single convergence assignment and single Final Review assignment; never add workers to repeat an already covered lens. Register supported candidates with complete dimensions and use controller-derived routing. After every write, Review, or QA completion, accept only current controller-generated revisions, manifests, credits, aggregates, and handoffs.

## Holds, autonomy, and terminal result

Every hold is controller state, not a stage. Report its reason, owner, user-input flag, resume phase, and exact minimum resume command/action. Resume only that recorded source phase; do not restart upstream planning or completed slices without a real authority/scope change.

Continue ordinary in-scope transitions when `user_input_required=false`. Ask the user only for unresolved product/scope/boundary choices, residual-risk authority, credentials/publication/spending/irreversible action, or a user-only manual step. A conversational stop performs no lifecycle controller mutation.

Respect controller worker/review/convergence/recovery budgets and circuit breakers. Report phase transitions, current revisions, active lease/hold, frozen inventories, verified closure, capsule metrics, credits, gates, and controller `next_action`.

Name every intermediate result by its exact controller gate state; implementation, Review, or QA success is not general readiness.

Declare only `PRODUCTION_READY_CANDIDATE` after successful `ready`. Return `NEXT_ACTION: terminal-production-ready-candidate` and stop. Deployment, publication, migration, store submission, spending, and risk acceptance remain external.
