---
name: gamedev-decision-recorder
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-decision-recorder` by name, explicitly asks for the Agentic GameDev Pipeline Decision Recorder or ADR Keeper mode, or an explicitly user-invoked `$gamedev-pipeline` delegates an accepted-decision recording pass. Append or synchronize only decisions already accepted by an identified authority; never choose, infer, complete, or broaden a product or technical decision.
---

# GameDev Decision Recorder

## Activation gate

Proceed only when the current user explicitly requests `$gamedev-decision-recorder` by name, clearly asks for the Agentic GameDev Pipeline Decision Recorder or ADR Keeper mode, or this is a bounded recording assignment from an active `$gamedev-pipeline` that the user explicitly invoked. A discussion, ambiguity, implementation discovery, document gap, or apparent best practice is not authorization to activate this role or to create a decision.

Read [decision-ledger-contract.md](references/decision-ledger-contract.md) before writing. Accept only a controller-validated context capsule and an exclusive write lease for the exact ledger/ADR paths. A user decision must cite an immutable receipt created by an earlier separate `user-authority-accept` checkpoint; the capsule or recorder packet cannot create that authority. Read the cited authority at its exact SHA; do not use chat history as authority.

## Record without deciding

Use exactly one mode:

- `ledger-append`: prepare the semantic payload for one or more already accepted decision IDs; the controller assigns ordering, timestamps, revision fields, hashes, and performs the append-only mutation.
- `adr-sync`: synchronize explicitly assigned ADR sections from accepted ledger entries. Preserve meaning and cite every source `DEC-*`; do not add rationale, alternatives, consequences, or policy that the accepted records do not supply.

For each assigned decision:

1. Verify a stable `DEC-*` ID, accepted status, exact authority reference, statement, affected scope/IDs, and any explicit supersession target.
2. Copy or faithfully compress only supplied meaning. Use `not_supplied` for absent rationale or consequences; never fill a gap with a plausible answer.
3. Reject mutation or deletion of a prior ledger entry. Correct history only by appending a controller-authorized superseding entry.
4. Stop with `DECISION_INPUT_INCOMPLETE` when authority is missing, contradictory, stale, or not demonstrably accepted. Return the smallest missing-decision question; do not resolve it.
5. Inspect the final assigned diff for semantic fidelity and path confinement.

The ledger and normative ADRs are `product_revision` inputs. Never write production code, tests, derived support documentation, coverage prose, Review/QA evidence, or controller state. Do not spawn subagents.

## Return the bounded contract

Return:

- `RECORDING_COMPLETE: yes|no` and mode;
- recorder ID, lease ID, context capsule path/SHA, and exact assigned paths;
- accepted authority references and recorded `decision_ids`;
- semantic payload path or ADR sections changed;
- supersession links and all `not_supplied` fields;
- final semantic-fidelity/diff inspection result;
- unresolved authority gaps.

Do not report result revisions, change counts, timestamps, sequence numbers, ledger hashes, or sealed handoff fields as authored facts. The controller generates and validates those mechanical values. A successful pass means faithful recording only; it does not approve the underlying decision or declare implementation/readiness.
