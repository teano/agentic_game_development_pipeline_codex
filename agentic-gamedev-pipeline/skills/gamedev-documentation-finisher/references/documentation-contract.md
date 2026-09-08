# Documentation semantic artifact

Follow `assignment.artifact_schema` exactly; it is authoritative. Do not inspect runtime code or guess the output shape.

Return one JSON object containing only:

```json
{"outcome":"pass","summary":"Updated assigned documentation from approved and verified sources.","questions":[]}
```

`outcome` is `pass`, `fail`, or `blocked`. `summary` is a non-empty account of the assigned documentation result, including when no change was required. `questions` is an optional array of concise strings.

Use the issued optional `technical_decisions` field under the shared [technical decisions](../../gamedev-pipeline/references/technical-decisions.md) policy to record encountered blockers and update their current resolution. Reconcile applicable existing corrections with approved intent and verified behavior; journal text alone cannot authorize a normative product claim. Do not edit upstream authority or controller state to incorporate a decision outside assigned documentation scope.

Do not include path inventories, source digests, controller state, or mechanical evidence. The controller derives the actual diff and routes any documentation change through fresh Review and QA.
