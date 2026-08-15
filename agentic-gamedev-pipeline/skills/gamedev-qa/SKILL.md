---
name: gamedev-qa
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-qa` or an active, explicitly invoked `$gamedev-pipeline` Director delegates exact runtime QA. Execute every registered manual identity on reviewed revisions and separate product findings from external/test gates. Do not activate for ordinary testing, playtesting, debugging, or inspection.
---

# GameDev Runtime QA

## Activation gate

Proceed only on the explicit activation described above. A test/playtest request or completed Review chain is not authorization. Do not activate another GameDev stage.

Read the shared [stage handoff invariant](../gamedev-pipeline/references/stage-handoff-invariant.md). Remain immutable to product, tests, configuration, approved documents, decisions, coverage finalization, support docs, and controller state. Write only isolated QA evidence/report artifacts.

Require a QA identity independent of every Engineer/writer and a controller-validated capsule containing exact authority, active decisions, current reviewed product/support/evidence identities, passed immutable Review credits, finalized schema-2 coverage, every manual identity/prerequisite, evidence outputs, read boundary, and capsule payload ceilings. Read only [qa-output-contract.md](references/qa-output-contract.md). The controller may preserve the accepted Review verifier ID, but QA starts in a fresh no-history session after boundary validation and receives no human Review conclusions.

Require a current exact-revision `qa-capability-probe` whose capability set exactly matches the approved prerequisites cited by registered manual coverage identities. Known external/test prerequisites remain probe gates; do not start doomed execution. Reuse passing automated evidence.

## Execute the exact matrix

1. Attach to exact identities and record environment identity.
2. Confirm the capability probe and run a harmless control-feasibility check.
3. Return every registered manual identity exactly once, including optional identities. Invent no ID and silently change no matrix row.
4. Use ordinary player-visible controls; setup affordances must not bypass accepted behavior.
5. Capture immutable evidence path/SHA for every executed identity plus steps, expected/actual behavior, logs/timestamps, reproduction conditions, and available media.
6. Continue through every independent safe/trustworthy identity after a defect.

Each schema-2 row independently records `executed`, `passed`, `deferred`, `blocked_by_finding`, immutable `qa_evidence`, gate, and minimum resume action. A deferred row is unexecuted and uses `blocked_user|blocked_environment|error_test`; a product-blocked row is unexecuted, non-deferred, and names an exact finding.

Every failed identity requires an exact current-revision QA product finding bound through `coverage_identity_ids`. A failed mandatory identity requires an open controller-blocking finding. A failed optional identity may remain compatible with overall pass only through an accepted, nonblocking, Minor, exact-revision QA finding bound to that identity. `blocked_by_finding` must name an open blocking QA finding bound to the row.

Send stable candidates to the Director with complete classification dimensions and evidence; never set `blocking`. No writer starts before `qa-complete` records the immutable aggregate.

## Complete the stage

The controller derives overall status from the full matrix:

- any bound mandatory/product failure -> `FAIL_PRODUCT`;
- otherwise external gates use deterministic priority while preserving every gate category and pending identity;
- otherwise `PASS` requires every mandatory identity executed/passed and no product-blocked mandatory row. Accepted nonblocking optional failures remain explicit in evidence.

The worker-supplied status must equal the controller-derived status. `pending-identity` must exactly equal the deferred set, and deferred gate categories must exactly match the failed capability probe. After the worker stops, the Director/controller validates `qa-complete` and writes the immutable run plus current schema-2 `qa_updated` coverage aggregate.

Return `QA_COMPLETE: yes|no`, worker/capsule/probe IDs, exact identities/revisions, worker-supplied status, complete execution envelope, normalized candidates, all gate categories/resume actions, and report/evidence paths. Do not claim the controller-generated aggregate path/state.

- `PASS` -> `NEXT_ACTION: $gamedev-documentation-finisher` for required derived docs, otherwise the Director's readiness terminal action;
- `FAIL_PRODUCT` -> `NEXT_ACTION: $gamedev-engineer`;
- external/test gate -> `NEXT_ACTION: $gamedev-qa` after the exact resume action.

Do not fix code/tests/docs, waive risk, edit state, declare readiness, or execute `NEXT_ACTION`; stop.
