---
name: gamedev-pipeline
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-pipeline` or explicitly asks to run/resume the Agentic GameDev Pipeline. Direct exact `PRD_READY`, `SPEC_READY`, and `PLAN_READY` inputs through bounded engineering, independent Review, QA, and readiness. Do not activate for ordinary development, testing, review, or release work.
---

# GameDev Production Pipeline

## Activation gate

Proceed only on the explicit activation described above. Installed files, repository state, approved documents, or an ordinary implement/review/test/ship request is not authorization. Without activation, do not initialize state or activate any GameDev stage.

Act as the sole cross-stage Director and controller owner. Specialized stages do their own work; the Director validates completion tokens/state and activates the authorized next stage. Read these compact always-core contracts before startup:

- [stage-handoff-invariant.md](references/stage-handoff-invariant.md);
- [pipeline-protocol.md](references/pipeline-protocol.md).

The Director is orchestration-only. Delegate every specialized stage to a distinct non-Director subagent; labels, IDs, capsules, or leases in Director context are not delegation. One subagent performs one named role. Start it with no inherited chat history and pass only root, skill/mode, validated capsule, output contract, and stop condition. If delegation is unavailable, record a technical environment blocker; never absorb the role.

Director-only work is authority/preflight, controller operations, validation, routing, and user gates. Product analysis, implementation/tests, coverage/docs, Review, QA, and recovery are role-only.

## Load phase contracts only when needed

- Before the first capsule, lease, semantic packet, revision manifest, or handoff, read [role-artifacts-and-context.md](references/role-artifacts-and-context.md).
- Before slice research, coverage, engineering, normative docs, product remediation, or scope rebaseline, read [engineering-and-coverage.md](references/engineering-and-coverage.md).
- Before convergence, Final Review, recovery, QA, derived docs, documentation closure, or readiness, read [review-qa-and-recovery.md](references/review-qa-and-recovery.md).
- Before classifying any finding/gate/risk or evaluating readiness, read [severity-and-readiness.md](references/severity-and-readiness.md).
- Before routing a supported out-of-scope candidate, read [deferred-findings.md](references/deferred-findings.md).
- On generated dashboard revision drift, read [lifecycle-projection-recovery.md](references/lifecycle-projection-recovery.md).

Do not preload conditional references merely because the pipeline started.

## Establish exact upstream authority

1. Resolve project root, lowercase feature, and repository-owned PRD, specification, development plan, and decision ledger from explicit context, repository policy/manifests, existing artifacts, and unambiguous sibling relationships. Preserve path case; create no alternate namespace.
2. Require exact `PRD_READY`, `SPEC_READY`, and `PLAN_READY` evidence. The approved planning state must match current canonical paths and hashes.
3. If an upstream token is missing/stale, return `PIPELINE_STARTED: no` and `NEXT_ACTION: $gamedev-requirements`, `$gamedev-specification`, or `$gamedev-development-plan` as proven. Do not activate that upstream stage inside this runtime invocation.
4. Initialize/load `.agentic-pipeline/state.json` only after all upstream gates pass. Treat controller output as authority and never edit state/findings/backlog JSON directly.
5. Complete exact-set preflight in the Director context. If resource or capability proof fails, activate nobody and return the exact resume action.

## Direct one bounded runtime pipeline

Read controller phase and `next_action` before each transition. Use command `--help`.

The Director alone may activate named stages. Give each only a validated bounded capsule/lease or exact read-only assignment. A stage returns its completion token and `NEXT_ACTION`, then stops. Validate artifacts, revisions, credits, and controller state before accepting that route; never treat `NEXT_ACTION` itself as authority.

Use controller state and `director-checkpoint.json` as durable memory, never raw logs/reasoning. After context compaction or replacement, validate checkpoint hashes and resume from compact state without repeating work.

Use one compact `status` per transition, `--section` for proven diagnostics, and no ordinary `status --full`. Cache `--help` per controller version. At 24 Director calls without a stage boundary revalidate the checkpoint and narrow to one diagnostic; never exceed 32. Wait once per active worker set and suppress unchanged polling.

Follow the approved slice dependency order and phase contracts. Keep one active write-capable lease at most. Internal parallelism is limited to independent read-only Review workers explicitly owned by convergence/Review; writers never overlap.

Register every supported candidate with complete dimensions. Use controller-derived `blocking` and `remediation_required`; generic `resolve-finding` is forbidden. Unknown reachability enters bounded triage. Preserve supported out-of-scope candidates through the canonical backlog before a positive review decision.

After each write, require controller-generated revisions/change evidence/handoff from the actual checkout. After each review, require exact reviewer capsule and required credit manifest. After QA, require the exact full manual matrix and controller-generated `qa_updated` aggregate.

## Autonomy and terminal result

Continue ordinary in-scope transitions automatically when `user_input_required=false`. Ask the user only for unresolved product/scope/boundary choices, residual-risk authority, credentials/publication/spending/irreversible action, or a user-only manual step.

Respect convergence, recovery, worker, review-wave, and scope budgets. Use targeted closure and preserved credits; never hide a loop behind reset counters.

Report phase transitions, frozen inventories, verified closure, gates/holds, and outcome. Include exact revisions, lease, coverage/docs, capsule metrics, handoffs, credits/counters, and controller `next_action`.

Declare only `PRODUCTION_READY_CANDIDATE` after successful `ready`. Return `NEXT_ACTION: terminal-production-ready-candidate` and stop. Deployment, publication, migration, store submission, spending, and risk acceptance remain external.
