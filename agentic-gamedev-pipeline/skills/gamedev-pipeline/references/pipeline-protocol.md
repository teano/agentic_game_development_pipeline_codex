# Pipeline core protocol

This is the compact always-loaded Director contract. Phase semantics stay in conditional references; worker schemas stay with workers; exact CLI syntax stays in each command's `--help`.

## Authority and startup summary

`PRD_READY -> SPEC_READY -> PLAN_READY -> runtime pipeline` is mandatory. A missing or stale upstream token ends startup with the exact upstream `NEXT_ACTION`; the Director never runs an upstream stage inside the current runtime activation.

Treat controller state and output—not narration—as phase authority. Initialize runtime only from the exact approved plan and its current planning-state proof. Never edit controller JSON, invent a receipt, or infer authority from chat history.

On resume, validate `director-checkpoint.json` against canonical state/findings hashes, then use one compact status. The Director needs only the current authority/revision summary, phase, `next_action`, active slice, hold, lease/owner, bounded active IDs/counts, and user-input flag. Use a targeted status section for a proven diagnostic and `status --full` only for explicit offline audit.

## Role and transition rules

The Director performs controller mechanics and never substitutes itself for a specialized role. Every phase assignment starts in a fresh no-history session with one exact capsule or bounded read-only assignment. A logical non-writer verifier ID may be retained across sequential verification phases, but its prior conversation is never retained or supplied.

Mechanical no-research and coverage transitions remain controller-owned. Every writing completion supplies its worker-owned semantic packet; the controller validates checkout scope and generates revisions/manifests/handoff. Every Review or QA completion supplies its exact current capsule and structured worker output. Generic human-readable predecessor Review reports are not Final Review or QA input authority.

Use the controller-required single convergence assignment and single Final Review assignment. Targeted product closure, support/evidence recovery Review, QA, and documentation closure are separate exact-capsule phases, not additional full Review waves.

Core phase order is:

```text
preflight -> slice_research -> slice_coverage_planning -> slice_engineering
slice_engineering -> slice_coverage_finalization -> next slice | implementation_complete
implementation_complete -> normative_documentation -> convergence -> review
review/closure/recovery_review -> qa | controller-routed remediation
qa -> derived_documentation | controller-routed product remediation | exact QA resume gate
derived_documentation -> documentation_review -> ready
```

## Holds and user authority

A hold preserves its source phase and completed work. Its compact route must name the exact resume action, owner, user-input flag, reason, and resume phase. Authority/scope rebaseline, migration, budget authorization, and circuit-breaker release are controller operations, never worker calls.

Continue only the controller's deterministic route. Ask the user only when `user_input_required=true` or the action is inherently user-owned. Completion tokens and worker `NEXT_ACTION` values are routing evidence, never activation authority.

`ready` declares only a production-ready candidate. It never authorizes publication, deployment, migration, spending, submission, or risk acceptance.
