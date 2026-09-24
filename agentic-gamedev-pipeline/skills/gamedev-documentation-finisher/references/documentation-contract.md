# Documentation semantic artifact

Follow `assignment.artifact_schema` exactly; it is authoritative. Do not inspect runtime code or guess the output shape.

Return one JSON object following the issued schema. Minimal ordinary passing example:

```json
{"outcome":"pass","summary":"Updated assigned documentation from approved and verified sources.","questions":[]}
```

`outcome` is `pass`, `fail`, or `blocked`. `summary` is a non-empty account of the assigned documentation result, including when no change was required. `questions` is an optional array of concise strings.

On documentation rework, consume [Repair input](../../gamedev-pipeline/references/delivery-contract.md#repair-input) for the exact unresolved-only roster, full originals and latest independent results. Return one `finding_resolutions` row per required pair, using `addressed|unresolved` and actual documentation correction/source evidence. Do not add already-resolved conditions, invent status values, or copy product Engineering/QA duties. Pass requires all assigned conditions addressed; independent Review owns resolution. On blocked, include the issued `blocker` and `required_action` fields.

Use the issued optional `technical_decisions` field under the shared [Current journal](../../gamedev-pipeline/references/technical-decisions.md#current-journal) policy to record encountered blockers and update their current resolution. Reconcile applicable existing corrections with approved intent and verified behavior; journal text alone cannot authorize a normative product claim. Do not edit upstream authority or controller state to incorporate a decision outside assigned documentation scope.

Do not include path inventories, source digests, controller state, or mechanical evidence. The controller derives the actual diff and retains bounded documentation Review. Only explicitly sealed pure-documentation paths with unchanged product dependencies may reuse current deterministic evidence; changed acceptance/runtime inputs require affected QA. A file extension or the writer's claim cannot waive verification.
