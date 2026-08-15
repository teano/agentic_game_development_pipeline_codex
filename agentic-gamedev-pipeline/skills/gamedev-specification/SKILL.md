---
name: gamedev-specification
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-specification` or an active, explicitly invoked `$gamedev-pipeline` Director delegates this stage. Converge an approved PRD through bounded architecture and independent proofreading to exact `SPEC_READY`. Do not activate for ordinary design, review, or implementation work.
---

# GameDev Specification

## Activation gate

Proceed only on the explicit activation described above. A missing/stale specification, technical question, or implementation request is not authorization. Do not activate another GameDev stage.

Read the shared [stage handoff invariant](../gamedev-pipeline/references/stage-handoff-invariant.md) and [specification-contract.md](references/specification-contract.md). The contract is canonical for artifact paths, trace shapes, worker outputs, holds, and readiness evidence.

Act as Specification Director. Own orchestration, deterministic state, hashes, budgets, handoffs, and user questions. Do not write or proofread the specification in the Director context. Use `scripts/specification_state.py` for every transition; never edit its JSON state directly.

## Establish authority

1. Resolve the project root, lowercase feature, canonical PRD, and canonical specification through the contract. Ask one path question only if ambiguity remains.
2. Require `PRD_READY` on the exact canonical approved PRD. Independently run `../gamedev-requirements/scripts/validate_product_requirements.py <prd> --require-approved` and record its exact-byte SHA-256; `init`, `accept-spec`, schema migration, and both `revise-ready` routes repeat that complete validator before mutating state or specification bytes. Legacy/malformed authority requires a controlled PRD revision and reapproval; do not activate the Requirements stage or grandfather it.
3. Initialize `.agentic-pipeline/specification-state.json` with `init --prd <resolved-prd> --spec <resolved-spec>`. Treat controller output as phase authority.
4. Assign one persistent Technical Spec Architect as the sole writer. Give every internal worker only canonical paths, exact hashes, role contract, current finding IDs, and a bounded task packet—not accumulated chat history.

If an exact `SPEC_READY` specification is bound to an earlier approved PRD and the PRD has since been freshly approved at a higher revision, use controller `revise-ready --reason <exact reason> --architect-id <fresh-id>` before editing the specification. A bound runtime normally forbids this transition; the sole exception is its exact pre-engineering `authority_recovery_hold`, supplied via matching `--recovery-token`. The transition archives prior PRD/SPEC/Proofreader/Architect readiness provenance, increments the sole specification revision, installs the new PRD trace, demotes to draft, revokes readiness, and enters `awaiting_accept`. After the revised draft bytes are ready, run `accept-spec` to persist a receipt bound to the exact PRD/spec/revision/token; `start-cycle` rejects absent or stale receipts. Then run fresh proofreading cycle(s) and `confirm-ready`; old confirmation never carries forward.

When product authority is unchanged and only the exact ready specification needs a sanctioned correction, use the same command with `--specification-only`. This route requires the exact unchanged approved PRD to pass the complete current Requirements validator before reopening and preserves its trace; it never invents a PRD revision or legitimizes a legacy invalid PRD. The same fresh Architect, runtime recovery, acceptance, proofreading, and fresh confirmation invariants apply.

## Generate only when required

If the specification is missing or stale, use exactly one bounded internal Generator; otherwise skip generation. Never run competing generators.

The Generator may optionally use `$skill-specification-pipeline` in generation mode as an internal drafting helper. Fail fast if that dependency is unavailable or returns an invalid/noncanonical draft, then fall back to local generation under the same Generator packet. Either route must preserve product meaning, trace every `PRD-REQ`, `PRD-NFR`, and `PRD-AC`, record the exact PRD path/revision/hash using the repository trace shape, leave unsupported product choices unresolved, and return one draft plus a compact coverage manifest. Neither route grants readiness.

Run `accept-spec` after validating the draft. End the Generator after acceptance; all later writes belong to the Architect.

## Converge with one writer

The Architect first inspects the draft against project rules, relevant existing patterns, platform guidance, the approved PRD, and component-relevant deferred risk evidence. It may use bounded internal read-only repository workers, but must not activate another GameDev stage or broaden product scope.

For each wave:

1. Run `start-cycle`, then assign exactly one fresh internal Proofreader.
2. Give the Proofreader immutable PRD/spec hashes. Require a complete read-only comparison and one deduplicated finding batch.
3. Run `record-proofread`. If every readiness gate passes, have the same Architect confirm the unchanged specification and run `confirm-ready`.
4. Otherwise give one deduplicated technical batch to the same Architect, complete one writing pass, then run `complete-cycle`.
5. Repeat with a fresh Proofreader. A Proofreader never edits; the Architect never awards its own clean credit.

One Architect may complete at most five Proofreader-to-response cycles. An attempted sixth enters `spec_convergence_hold`. Resume only through a recorded handoff to a distinct Architect or a user gate; preserve total waves, prior owners, findings, hashes, and budget history.

The Architect may resolve technical choices supported by project evidence. Escalate product semantics, observable outcomes, scope, ownership, system/public boundaries, or PRD contradictions to one consolidated user decision. Do not disguise them as assumptions.

## Complete the stage

Run `confirm-ready` only on the exact snapshot satisfying every readiness condition in the contract. Return:

- `SPEC_READY: yes|no`, state path, PRD/spec paths and hashes, Architect cycle count, and total waves;
- exact blocking finding/question IDs or the validated readiness evidence;
- `NEXT_ACTION: $gamedev-development-plan` when `SPEC_READY: yes`, otherwise `NEXT_ACTION: user-decision` or `NEXT_ACTION: $gamedev-specification`.

Do not activate the Development Plan stage. Stop after persisting state and returning the handoff.
