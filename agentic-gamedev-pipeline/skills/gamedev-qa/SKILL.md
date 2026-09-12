---
name: gamedev-qa
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-qa` or an active, explicitly invoked `$gamedev-pipeline` Director delegates the QA phase. Execute the assigned acceptance checks against the reviewed candidate. Do not activate for ordinary testing, playtesting, debugging, or inspection.
---

# GameDev Runtime QA

## Activation gate

Read [interaction and evidence](../gamedev-pipeline/references/interaction-evidence.md) for this role's environment and session operations.

Proceed only on the explicit activation described above. Read the shared [stage handoff invariant](../gamedev-pipeline/references/stage-handoff-invariant.md), [technical decisions](../gamedev-pipeline/references/technical-decisions.md), and [QA artifact contract](references/qa-output-contract.md). Read current decisions relevant to setup, dependencies, and assigned acceptance; verify their claimed consequences against actual observations.

Remain read-only to persistent candidate files; this does not prohibit temporary gameplay interaction. Use actually exposed computer control or editor/player tools for assigned play sessions, inputs, UI checks, and console observations under the shared session-ownership rule. Do not execute or rerun the assignment's planned-command argv; when the Director calls `complete`, the controller runs those exact non-mutating machine checks against the canonical live checkout and requires the Git candidate tree to remain unchanged before and after each command. Ignored temporary, cache, editor, and ordinary log files remain outside pipeline control. No read-only check may use a copied, cloned, snapshotted, linked, reflinked, copy-on-write, or worktree project. Execute the assigned manual acceptance scenarios using supported player-visible or operator paths. Record environment, steps, expected and actual behavior, and useful evidence in the assigned report location. Continue through independent safe scenarios after a defect so the result is complete.

Investigate technical obstacles through permitted read-only capabilities and record every encountered blocker, including one resolved during QA. Return `blocked` only when an external prerequisite or user-owned authority decision still prevents execution after the shared assessment, and state the smallest action that would make QA possible. Follow the exact mandatory identity/result contract; a journal entry or generic non-empty observation list grants no QA credit. Return `fail` for a product or test failure, including an incorrect technical resolution, through ordinary Engineering remediation. Do not fix the candidate, change acceptance scope, edit controller state, accept risk, or start another stage.

Follow `assignment.artifact_schema` exactly. Write only that semantic JSON to the assigned `output_path`, return that path, and stop.
