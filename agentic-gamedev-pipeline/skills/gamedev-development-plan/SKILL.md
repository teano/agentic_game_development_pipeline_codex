---
name: gamedev-development-plan
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-development-plan` by name, explicitly asks for the Agentic GameDev Pipeline development-planning mode, or an explicitly user-invoked `$gamedev-pipeline` delegates planning. Turn an approved game-feature PRD and exact SPEC_READY specification into a user-approved, hash-traced single-scope or sequential vertical-slice plan with phase-scoped writers, exact coverage/documentation contracts, and bounded context capsules. Do not infer activation from generic planning or implementation work.
---

# GameDev Development Plan

## Activation gate

Proceed only when the current user explicitly requests `$gamedev-development-plan`, clearly asks for the Agentic GameDev Pipeline development-planning mode, or an active `$gamedev-pipeline` explicitly delegates planning after the user invoked that pipeline. Approved documents, implementation readiness, or a generic planning request is not authorization.

Act as Development Plan Director: own source authority, deterministic state, delegation, and the user approval gate. Do not perform the Planning Analyst's analysis in the Director context.

Before acting, read [development-plan-contract.md](references/development-plan-contract.md). Use `scripts/development_plan_state.py` for every transition and validation; never edit its JSON state directly. Start from [development-plan.md](assets/development-plan.md) when creating the canonical plan.

## Establish authority

1. Resolve `<project-root>` and lowercase `<feature>`.
2. Resolve the repository-owned PRD, specification, development plan, and append-only decision-ledger paths from explicit user context, repository instructions, feature manifests/indexes, existing feature artifacts, and unambiguous sibling relationships. Preserve path case. Never create a copy, symlink, move, or parallel namespace to satisfy this plugin.
3. If multiple plausible paths remain, ask one concise path question. If the project is empty and defines no convention, recommend sibling `product-requirements.md`, `technical-specification.md`, `development-plan.md`, and `decision-ledger.jsonl` files under `docs/features/<feature>/` as a proposed layout and wait for confirmation.
4. Require the resolved approved PRD, approved specification, and `.agentic-pipeline/specification-state.json` whose `spec_ready` evidence exactly matches both current files and paths.
5. Initialize `.agentic-pipeline/development-plan-state.json` with `init --prd <resolved-prd> --spec <resolved-spec> --plan <resolved-plan> --decision-ledger <resolved-ledger>` and exact source hashes.
6. Spawn exactly one fresh, read-only Planning Analyst. Give it a bounded context capsule with the resolved canonical files, exact hashes, project rules, accepted decision-ledger path/IDs when present, and numeric limits. Ask it to assess solution size, complexity, context working set, integration seams, ownership, dependencies, coverage identity namespaces, and documentation outputs.
7. Record the result with `accept-analysis`. Do not reuse a prior implementation or specification worker as the Analyst.

## Choose ownership shape

Choose `single_owner` when the implementation should remain one bounded write scope because one Engineer pass can safely hold its production code and tightly coupled automated tests, or because the work has poor seams. This mode does not reserve one Engineer identity for the lifecycle. Decision Recorder, Coverage Steward, Documentation Finisher, later remediation Engineers, and recovery workers receive their own phase-scoped assignments; the controller permits at most one active write-capable lease in the checkout.

Choose `sequential_slices` only when every slice produces an observable end-to-end result, maps to PRD requirements and acceptance criteria, has a bounded context working set, and can consume a sealed handoff from an earlier slice without competing writes. Never split by backend/UI/tests or schedule parallel writers.

Read only component-relevant deferred findings as dependency/risk evidence. Record a relevant deferred dependency and its re-entry condition, but do not automatically add a slice or expand editable scope for it; that requires an approved current-feature requirement or explicit user scope expansion.

The Analyst returns a compact decision packet: mode, complexity and working-set estimate, seam/dependency analysis, rejected decompositions, risks, proposed slices/milestones, context-capsule budgets, coverage planning/finalization boundaries, and normative/derived documentation outputs. The Director challenges unsupported decomposition, then records the decision; the designated plan writer may create the draft.

## Draft and validate

Write only the resolved repository-owned development-plan path. Keep `status: draft` until the user explicitly approves the exact submitted SHA. Preserve the repository's existing flat or nested source-trace convention. Include every field required by the contract, especially the machine-readable per-slice acceptance allowlist, editable paths, structured shared touchpoints, exclusions, product file/line budgets, exact scope baseline revision, bounded research briefs, coverage identity namespace and mandatory/manual capability plan, normative/derived documentation outputs, exact numeric context-capsule budgets, verification/exit criteria, rollback/recovery, and downstream consumers.

Run `submit` only after `validate-plan` passes. Present the decision, ordering, boundaries, budgets, risks, and exact draft SHA to the user. Discuss and revise as needed; each edit requires resubmission. Do not interpret silence or approval of the PRD/specification as approval of the plan.

After an explicit user approval of the exact current draft, run `approve --approved-by user --approval-note <decision>`. The controller alone promotes the submitted draft to `approved` and records the approval evidence. Report `PLAN_READY` only from controller state.

## Stop conditions

Any PRD/spec byte change, lost PRD approval, lost `SPEC_READY`, or trace mismatch makes the plan `stale`. Stop planning/implementation and reconverge upstream artifacts, then run `reinitialize` with a distinct fresh Analyst identity. Preserve prior planning history; never delete state or patch hashes by hand.

Do not start Engineers from a draft, stale, or unapproved plan. Do not implement slices in this skill.
