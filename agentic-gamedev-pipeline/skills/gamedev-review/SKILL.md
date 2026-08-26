---
name: gamedev-review
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-review` or an active, explicitly invoked `$gamedev-pipeline` Director delegates the review phase. Independently inspect the current candidate without remediation. Do not activate for ordinary code review or implementation feedback.
---

# GameDev Independent Review

## Activation gate

Proceed only on the explicit activation described above. Read the shared [stage handoff invariant](../gamedev-pipeline/references/stage-handoff-invariant.md) and [review artifact contract](references/review-output-contract.md).

Remain read-only. Independently inspect the assigned current candidate against approved behavior, repository policy, correctness, architecture boundaries, failure and recovery behavior, test quality, and affected integration paths. Do not rely on predecessor conclusions. Report actionable findings with location, impact, evidence, and the smallest justified correction; use an empty finding list only after completing the assigned inspection.

Do not edit, remediate, accept risk, alter controller state, or start another stage. Follow `assignment.artifact_schema` exactly; write only that semantic JSON to the assigned `output_path`, return that path, and stop.
