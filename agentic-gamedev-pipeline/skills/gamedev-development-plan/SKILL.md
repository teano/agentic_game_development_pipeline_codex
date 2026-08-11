---
name: gamedev-development-plan
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-development-plan` or an active, explicitly invoked `$gamedev-pipeline` Director delegates this stage. Convert exact `PRD_READY` and `SPEC_READY` inputs into a user-approved hash-traced `PLAN_READY`. Do not activate for ordinary planning or implementation work.
---

# GameDev Development Plan

## Activation gate

Proceed only on the explicit activation described above. Approved documents, apparent implementation readiness, or a generic planning request is not authorization. Do not activate another GameDev stage.

Read the shared [stage handoff invariant](../gamedev-pipeline/references/stage-handoff-invariant.md) and [development-plan-contract.md](references/development-plan-contract.md). The contract is canonical for paths, schema, slice semantics, context ceilings, approval, and staleness.

Act as Development Plan Director: own source authority, deterministic state, internal delegation, and the user approval gate. Do not perform the Planning Analyst's analysis in the Director context. Use `scripts/development_plan_state.py` for every transition; never edit its JSON state directly. Start from [development-plan.md](assets/development-plan.md) when creating the canonical plan.

## Establish authority

1. Resolve the project root, lowercase feature, canonical PRD, specification, plan, and append-only decision ledger through the contract. Ask one path question only if ambiguity remains.
2. Require exact `PRD_READY` and `SPEC_READY` evidence whose paths and hashes match the current files. Do not activate upstream stages; return a handoff to the missing/stale stage instead.
3. Initialize `.agentic-pipeline/development-plan-state.json` with the resolved paths and exact source hashes.
4. Assign exactly one fresh internal read-only Planning Analyst with bounded canonical inputs. Do not reuse an implementation or specification worker.
5. Record the result with `accept-analysis`.

## Choose ownership shape

Use `single_owner` when production work and tightly coupled automated tests form one bounded write scope or have poor seams. It does not reserve one Engineer identity for the lifecycle.

Use `sequential_slices` only when every slice yields an observable end-to-end result, maps to approved requirements/acceptance, has a bounded working set, and consumes a sealed earlier handoff without competing writes. Never split by backend/UI/tests or plan parallel writers.

Read only component-relevant deferred findings as dependency/risk evidence. They do not add scope. The Analyst returns a compact decision packet with mode, complexity/working-set estimate, seams/dependencies, rejected decompositions, risks, slices/milestones, context ceilings, coverage boundaries, documentation outputs, and whether each slice needs bounded research.

For each slice, use either one or more exact `RESEARCH-*` briefs or `research_not_required | reason=<exact source-backed reason>`. Never add a fake brief merely to satisfy structure.

## Draft, approve, and complete

Write only the canonical plan path and use the contract/template fields. Keep `status: draft` until the user explicitly approves the exact submitted SHA.

Run `validate-plan`, then `submit`. Present decision, ordering, boundaries, ceilings, risks, and exact draft SHA. Every edit requires resubmission. Silence or upstream approval is not plan approval.

After explicit approval of the exact current draft, run `approve --approved-by user --approval-note <decision>`. Only controller state may report `PLAN_READY`.

Any PRD/spec byte drift, lost approval, lost `SPEC_READY`, or trace mismatch makes the plan stale. Preserve history and use `reinitialize` with a distinct fresh Analyst after upstream reconvergence. Never delete state or patch hashes manually.

Return:

- `PLAN_READY: yes|no`, canonical path, mode, submitted/approved SHA, and source paths/hashes;
- exact unresolved approval, source, scope, or validation gate;
- `NEXT_ACTION: $gamedev-pipeline` when `PLAN_READY: yes`; otherwise `NEXT_ACTION: user-decision`, `$gamedev-requirements`, `$gamedev-specification`, or `$gamedev-development-plan` as proven by state.

Do not initialize the runtime pipeline or start an Engineer. Stop after persisting planning state and returning the handoff.
