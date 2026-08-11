---
name: gamedev-decision-recorder
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-decision-recorder` or an active, explicitly invoked `$gamedev-pipeline` Director delegates one accepted-decision pass. Record only receipt-backed accepted decisions without choosing or extending them. Do not activate from ambiguity, implementation discovery, or document gaps.
---

# GameDev Decision Recorder

## Activation gate

Proceed only on the explicit activation described above. A discussion, apparent best practice, ambiguity, implementation discovery, or missing document is not authorization to create a decision. Do not activate another GameDev stage.

Read the shared [stage handoff invariant](../gamedev-pipeline/references/stage-handoff-invariant.md) and [decision-ledger-contract.md](references/decision-ledger-contract.md). The contract is canonical for authority receipts, semantic packet schema, append-only behavior, ADR synchronization, and legal recording phases.

Accept only a controller-validated capsule and exclusive lease for exact ledger/ADR paths. A user decision must cite a prior immutable `user-authority-accept` receipt whose statement, approval reference, digest, path, and SHA match exactly. Neither the capsule nor recorder packet may create authority. Use no chat history as authority.

Decision recording is legal only during `preflight`, `slice_research`, or `slice_coverage_planning`. A later decision returns `DECISION_REPLAN_REQUIRED`; it does not invalidate downstream state in place.

## Record without deciding

Use one mode:

- `ledger-append`: prepare schema-1 semantic payloads for already accepted decision IDs; the controller owns ordering, timestamps, hashes, and append mutation;
- `adr-sync`: update only assigned ADR sections from active ledger entries and cite every source `DEC-*`.

For each decision, verify stable ID, accepted status, exact authority, statement, affected IDs/scope, and any supersession target. Copy or faithfully compress supplied meaning. Use `not_supplied` for absent rationale/consequences; never fill a gap. Prior entries are immutable; corrections append a controller-authorized superseding entry. Inspect the final assigned diff for semantic fidelity and confinement.

Stop with `DECISION_INPUT_INCOMPLETE` for missing, contradictory, stale, or unaccepted authority. Return only the smallest missing-decision question.

The ledger and normative ADRs are product inputs. Never write production code/tests, derived support docs, coverage prose, Review/QA evidence, or controller state. Do not spawn subagents.

## Complete the stage

Return `RECORDING_COMPLETE: yes|no`, mode, recorder/lease/capsule IDs, assigned paths, authority references, decision IDs, payload/ADR changes, supersession links, `not_supplied` fields, fidelity inspection, and unresolved authority gaps. The controller alone authors revisions, counts, sequence/timestamps, ledger hashes, and sealed handoff fields.

On success return `NEXT_ACTION: $gamedev-pipeline` for Director validation/resume. On an authority or late-phase gate, return the exact `NEXT_ACTION: user-decision`, `$gamedev-requirements`, `$gamedev-specification`, or `$gamedev-development-plan` required to re-establish authority. Do not execute it; stop.
