---
name: gamedev-documentation-finisher
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-documentation-finisher` or an active, explicitly invoked `$gamedev-pipeline` Director delegates the documentation phase. Update assigned documentation from approved and verified sources without inventing behavior. Do not activate for ordinary documentation work.
---

# GameDev Documentation Finisher

## Activation gate

Proceed only on the explicit activation described above. Read the shared [stage handoff invariant](../gamedev-pipeline/references/stage-handoff-invariant.md) and [documentation artifact contract](references/documentation-contract.md).

Edit only the assigned documentation paths. Ground normative statements in approved requirements, specification, plan, and implemented public behavior. Ground derived instructions in the reviewed and tested candidate. Preserve repository terminology and add no unsupported promise, default, compatibility claim, or operator step.

Inspect the final diff for source fidelity, scope, stale references, and accidental product or test changes. If no documentation change is required, say so in a passing summary and leave the checkout unchanged. If authority is missing or contradictory, return `blocked` with one concise question.

Do not implement code or tests, change product decisions, edit controller state, perform Review or QA, or start another stage. Follow `assignment.artifact_schema` exactly; write only that semantic JSON to the assigned `output_path`, return that path, and stop.
