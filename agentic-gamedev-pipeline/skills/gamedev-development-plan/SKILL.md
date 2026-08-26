---
name: gamedev-development-plan
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-development-plan` or an active, explicitly invoked `$gamedev-pipeline` Director delegates this stage. Convert exact `PRD_READY` and `SPEC_READY` inputs into an approval-bound, hash-traced `PLAN_READY`. Do not activate for ordinary planning or implementation work.
---

# GameDev Development Plan

## Activation gate

Proceed only on the explicit activation described above. Approved documents, apparent implementation readiness, or a generic planning request is not authorization. Do not activate another GameDev stage.

Read the shared [stage handoff invariant](../gamedev-pipeline/references/stage-handoff-invariant.md) and [development-plan-contract.md](references/development-plan-contract.md). The contract is canonical for paths, schema, slice semantics, context ceilings, approval, and staleness.

Act as Development Plan Director: own source authority, deterministic state, internal delegation, and the approval gate. Do not perform the Planning Analyst's analysis in the Director context. Use `scripts/development_plan_state.py` for every transition; never edit its JSON state directly. Start from [development-plan.md](assets/development-plan.md) when creating the canonical plan.

## Establish authority

1. Resolve the project root, lowercase feature, canonical PRD, specification, plan, and append-only decision ledger through the contract. Ask one path question only if ambiguity remains.
2. Require the exact PRD to pass the complete current approved Requirements validator and require current schema-2 `SPEC_READY` evidence whose paths and hashes match the files. Planning never migrates legacy specification state or grandfathers malformed authority; return a controlled upstream revision/reconvergence handoff instead.
3. Initialize `.agentic-pipeline/development-plan-state.json` with the resolved paths and exact source hashes.
4. Assign exactly one fresh internal read-only Planning Analyst with bounded canonical inputs. Do not reuse an implementation or specification worker.
5. Record the result with `accept-analysis`.

## Choose ownership shape

Use `single_owner` when production work and tightly coupled automated tests form one bounded write scope or have poor seams. It does not reserve one Engineer identity for the lifecycle.

Use `sequential_slices` only when every slice yields an observable end-to-end result, maps to approved requirements/acceptance, has a bounded working set, and consumes a sealed earlier handoff without competing writes. Never split by backend/UI/tests or plan parallel writers.

Read only controller-provided closed remediation gates and accepted answers as dependency/risk context. They do not add scope. Pipeline v2 keeps findings, answers, and completed actor IDs inside controller state; planning does not invoke a Decision Recorder or deferred-findings handler. The Analyst returns a compact decision packet with mode, complexity/working-set estimate, seams/dependencies, rejected decompositions, risks, slices/milestones, context ceilings, coverage boundaries, documentation outputs, and whether each slice needs bounded research.

For each slice, use either one to three exact `RESEARCH-*` briefs or `research_not_required | reason=<exact source-backed reason>`. Brief IDs and content selectors are runtime authority and must be unique. Never add a fake brief merely to satisfy structure.

## Draft, approve, and complete

Write only the canonical plan path and use the contract/template fields. Keep `status: draft` until an authorized actor explicitly approves the exact submitted SHA. The user may approve directly or explicitly delegate technical/process approval to an agent; record the real actor and never relabel delegated approval as `user`. Delegation does not cover an unresolved product choice that remains user-owned.

Run `validate-plan`, then `submit`. Validation requires the exact union of all slice acceptance sets to cover the complete approved PRD inventory; cross-slice overlap is allowed only when each named slice genuinely contributes to that end-to-end criterion. Present decision, ordering, boundaries, ceilings, risks, and exact draft SHA. Every edit requires resubmission. Silence or upstream approval is not plan approval.

After approval of the exact current draft, run `approve --approved-by <actual-actor-id> --approval-note <authority-and-decision>`. The actor ID is one safe 1–64 character identity. The controller persists a resumable approval transition before replacing plan bytes; retry an interrupted command with the exact same inputs. With unchanged sources, only that exact retry may finish a pending approval. If source authority drifts and is reconverged, `reinitialize` verifies the pending transition and exact submitted-or-deterministically-approved plan bytes, derives the deterministic draft form when necessary, records the superseded approval in history, and continues with a fresh Analyst. Completed exact approval replay is a source-revalidated no-op even after normal runtime binding. Only controller state may report `PLAN_READY`.

If an already approved plan itself needs correction while PRD/SPEC authority remains current, run `revise-approved --reopened-by <director-id> --analyst-id <fresh-analyst-id> --reason <exact reason>` before editing it. With sole runtime v2 bound, the controller discovers the one direct schema-2 runtime JSON under `.agentic-pipeline-v2/`, rejects multiple bindings, verifies its exact project root and bound plan path/SHA, and uses no recovery token. A complete canonical legacy schema-10 state/findings pair may coexist only when its immutable import record, deterministic run lineage, following public migration, generation, and empty findings prove that it is the retired source of that sole v2 state. Its public history must use unique non-empty IDs and advance without gaps from the import/migrate generation through the current runtime generation. Before any public v2 reconfiguration, authority, migration audit, slices, and migrate digest must still match that exact snapshot; afterward, the same deterministic import reconstruction must still validate the migrate digest, and the first valid immutable `authority_scope_reconfigured` history record must bridge from the derived legacy authority and the exact reconstructed three-key slice digest, while the sole current v2 state remains canonically valid and bound to the current approved plan. Every incomplete, altered, linked, foreign, unbridged, or otherwise unproven mixed binding fails closed. The same classifier protects initial reopen and every bound continuation. Every v2 mutation then fails closed until the Director executes the exact `status.next_action` `init` reconfiguration. The legacy `authority_recovery_hold` token remains accepted only for an actual legacy-only binding. Neither route carries approval forward. Director and Analyst identities must remain distinct after NFKC, surrounding-whitespace, and case normalization. Freshness applies the same normalization to the candidate and every Planning Analyst identity recursively retained in current state and all history/reinitialization shapes. This verifies the exact approved bytes, including exactly one positive-integer top-level `revision`, archives their submission/approval/source provenance, increments the plan revision without duplicating the field, removes approval metadata, installs the fresh Analyst identity, and returns to `analyzing`. Record that Analyst's fresh decision with `accept-analysis` before editing/submitting the revised draft. The revised plan must pass validation, receive a new `submit`, and receive fresh approval under the same current authority; prior analysis and approval never carry forward.

Any PRD/spec byte drift, lost approval, lost `SPEC_READY`, or trace mismatch makes the plan stale. Preserve history and use `reinitialize` with a distinct fresh Analyst after upstream reconvergence. Never delete state or patch hashes manually.

Return:

- `PLAN_READY: yes|no`, canonical path, mode, submitted/approved SHA, and source paths/hashes;
- exact unresolved approval, source, scope, or validation gate;
- `NEXT_ACTION: $gamedev-pipeline` when `PLAN_READY: yes`; otherwise `NEXT_ACTION: user-decision`, `$gamedev-requirements`, `$gamedev-specification`, or `$gamedev-development-plan` as proven by state.

Do not initialize the runtime pipeline or start an Engineer. Stop after persisting planning state and returning the handoff.

For a focused local regression with per-test progress, run `python -B -m unittest discover agentic-gamedev-pipeline/skills/gamedev-development-plan/scripts -p "test_*.py" -v` from the bundle repository root.
