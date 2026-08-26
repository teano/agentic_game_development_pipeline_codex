# QA semantic artifact

Follow `assignment.artifact_schema` exactly; it is authoritative. Do not inspect runtime code or guess the output shape.

Return one JSON object containing only:

```json
{"outcome":"pass","checks":["acceptance scenario: pass"],"questions":[]}
```

`outcome` is `pass`, `fail`, or `blocked`. `checks` is required and lists the QA scenarios and their observed results; pass/fail requires at least one check. Do not execute controller-owned planned-command argv in the live candidate merely to populate this list. `blocker` is required only with `blocked`. `questions` is an optional array of concise strings.

Do not include SHA values, checkout inventory, command digests, or controller state. The controller runs assigned machine checks independently.
