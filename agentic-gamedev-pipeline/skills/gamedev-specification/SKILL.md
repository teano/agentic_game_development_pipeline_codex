---
name: gamedev-specification
description: Explicit-invocation only. Use only for `$gamedev-specification` or a delegated Specification stage of an explicitly invoked pipeline. Converge an exact approved PRD through bounded architecture and independent proofreading to SPEC_READY; do not activate for ordinary design.
---

# GameDev Specification

When the caller supplies `control_binding`, first apply the shared [control-return contract](../gamedev-pipeline/references/control-return.md). Keep semantic JSON and native stage handoffs unchanged; wrap only the requested return. A bounded caller task performs only its stated existing-role work, without automatic stage restart or approval. Standalone user calls retain their existing public result.

## Activation gate

Act as Specification Director, owning orchestration and evidence rather than specification authoring or semantic review. Read the shared [stage handoff invariant](../gamedev-pipeline/references/stage-handoff-invariant.md), [technical decisions](../gamedev-pipeline/references/technical-decisions.md), and the relevant [model policy](../gamedev-pipeline/references/agent-model-policy.md) rows. Preserve applicable user/parent model settings and current source/delegation provenance. A stage completion token never activates another stage on its own.

The [specification contract](references/specification-contract.md) is the single detailed schema and operation policy. On entry read its **Canonical artifacts**, **Scope and sufficiency invariant**, **Required specification coverage** and **Readiness evidence**. Read the named worker or recovery section when that operation is needed; do not resend the whole manual or duplicate its rules in every prompt.

## Establish exact sources and owners

Require exact approved `PRD_READY` bytes and run the complete Requirements validator with `--require-approved`. Bind project, feature, canonical PRD/specification and source hashes through `scripts/specification_state.py --feature <slug>`; command help supplies exact flags. No controller-state edits or sibling workflow discovery. Product delegation is applied by the proper upstream owner, never substituted for a valid approved PRD.

Use `technical-decisions-context` on initial entry and source change. Deliver relevant complete current records and binding to each affected reader. A journal explains technical execution, not new product obligations. Unfinished journal/source drift follows the contract's refresh/revision route; unchanged inputs do not justify starting over.

Assign one persistent Technical Spec Architect. The Generator is the bounded wrapper for the actual external `$skill-specification-pipeline`, which owns its required generation/correction passes. The Director never writes the specification, helper result or semantic acceptance. Each independent Proofreader is distinct from the Architect/authoring owner and uses fresh current input; reuse Architect and eligible bounded research lanes. New physical workers use `fork_turns: "none"` and the effective model/effort. Give each only its named contract section, exact sources, findings and decisions.

## Generate and converge

For a missing/stale specification, follow **Worker contracts → Generator** and **Controller helper challenge/result gate**. Use `prepare-helper --operation generation`, invoke the actual request-bound external helper, and consume its immutable result with `record-helper-result`. Pass `GAMEDEV_HELPER_REQUEST_PATH` and the exact request-bound `GAMEDEV_SPECIFICATION_CONTROLLER_PATH`; the contract owns the remaining source/language/route fields and emitter preflight. Never locally replace helper stages or fabricate the result sidecar.

The Architect assesses the exact draft, including section applicability/minimality, and supplies the contract's bound preaccept receipt. Use `accept-spec --preaccept-receipt`; a good-looking draft or Director opinion grants no acceptance. On rejection, the Architect returns one complete eligible correction packet. Corrections use the actual helper's `continue`/fragment-capture route with prepared request and consumed result, never untracked local rewriting.

After acceptance, use **Proofreader** and **Holds and handoffs**: start the independent wave, read its actual report through `record-proofread`, and let the Architect own required correction decisions. For the unchanged final wave with all readiness conditions satisfied, the active Architect calls `confirm-ready` directly while that wave is active; it closes the wave itself. Do not call `complete-cycle` first. Use `complete-cycle` when closing an iteration that still needs another acceptance/review wave; consume any prepared helper correction before that command. Changed bytes require fresh Architect preaccept/acceptance and current independent proofreading. Preserve finding IDs and source evidence, include all admissible defects in one pass, and stop optional improvement searches. The scope and sufficiency invariant belongs to the canonical contract: exact mandatory PRD behavior, smallest sufficient design, no unsupported obligations or complexity.

Use **Revising specification authority** only for a real source amendment and **Holds and handoffs** for ownership/context changes. Quiesce affected activity and preserve exact receipts before the sanctioned transition. A format-only unconsumed report correction stays with its assigned worker; it does not create a new wave. No stale helper, review or Architect result becomes fresh credit.

## Complete the stage

Only `confirm-ready` establishes `SPEC_READY` from the contract's exact current source, Architect and Proofreader evidence. Report the canonical path, ready hash, feature/workflow and actual remaining blocker when any; return `NEXT_ACTION: $gamedev-development-plan` only as a handoff. With a caller binding, this unchanged handoff is `task_result.payload`; standalone calls return it directly. Stop at this stage boundary. An already authorized full-cycle parent may consume it and continue Planning; this worker does not start that stage.
