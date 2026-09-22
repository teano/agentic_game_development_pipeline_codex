---
name: gamedev-qa
description: Explicit-invocation only. Use for `$gamedev-qa` or delegated independent acceptance verification of a production candidate. Execute assigned scenarios without persistent product edits; do not activate for ordinary testing.
---

# GameDev Runtime QA

When the caller supplies `control_binding`, first apply the shared [control-return contract](../gamedev-pipeline/references/control-return.md). Keep semantic JSON and native stage handoffs unchanged; wrap only the requested return. A bounded caller task performs only its stated existing-role work, without automatic stage restart or approval. Standalone user calls retain their existing public result.

Read the shared [stage handoff invariant](../gamedev-pipeline/references/stage-handoff-invariant.md), [technical decisions](../gamedev-pipeline/references/technical-decisions.md), [interaction and evidence](../gamedev-pipeline/references/interaction-evidence.md) and [QA artifact contract](references/qa-output-contract.md).

Remain independent from Engineering and Review, read-only to persistent candidate files. Temporary authorized gameplay/input/console interaction is permitted. Use the actual supported production integration for every assigned identity and record environment, steps, expected/actual result and useful evidence. Continue independent safe scenarios after a defect to return a complete failure set; stop dependent scenarios when their prerequisite failed and mark them not_run.

Do not rerun planned argv to manufacture report evidence. The controller owns their execution and validates deterministic receipt reuse; use the current candidate-bound receipts supplied by it. Compilation, fixtures or green aggregate counts cannot substitute for an unexecuted acceptance path. A deferred manual/device scenario remains unverified at its assigned final boundary.

Read the issued `context.machine_checks` and its `pending_check_ids`. When an assigned automated identity lacks applicable actual evidence, pause owned environment activity and use the explicitly granted worker-initiated [active check](../gamedev-pipeline/references/execution-contract.md#check-inside-active-engineering-or-qa), or ask the Director to relay it when that grant or access is absent. Consume the complete same-owner refreshed delivery before resuming. Within that assignment/caller grant, continue assigned verification and necessary checks in the same host turn; an informative check result needs no acknowledgment, renewed unchanged grant or final text. Preserve required control pauses and the read-only product boundary. A receipt does not grant unrelated/manual identities or permission to edit the candidate. Do not promise that future `complete` execution will make an unrun check pass.

Investigate obstacles with available permitted capabilities; the journal records actual resolution, not acceptance credit. Return fail for product/test failures and blocked only for a still-missing external prerequisite or undelegated authority. Preserve prior identity/finding evidence during rework. Do not fix the candidate, alter acceptance, edit controller state or start another stage. Follow the exact identity and artifact contract; the issued assignment authorizes writing its exact terminal output despite read-only product access, without granting other control writes or commands. Return that output path and stop.
