# Engineering semantic artifact

Follow `assignment.artifact_schema` exactly; it is authoritative. Do not inspect runtime code or guess the output shape.

Return one JSON object containing only:

```json
{"outcome":"pass","summary":"Implemented the assigned behavior and coupled tests.","assumptions":[],"questions":[]}
```

`outcome` is `pass`, `fail`, or `blocked`. `summary` is a non-empty statement of the assigned result. `assumptions` and `questions` are optional arrays of concise strings. Omit them when empty.

Do not include changed-path listings, tree OIDs, digest values, command output, mechanical checkout evidence, or controller state. The controller derives the actual Git-tree delta and runs the current slice's planned checks independently.
