# Review semantic artifact

Follow `assignment.artifact_schema` exactly; it is authoritative. Do not inspect runtime code or guess the output shape.

Return one JSON object containing only:

```json
{"outcome":"fail","findings":[{"text":"src/state.py permits an invalid transition; reject it before mutation.","severity":"high","kind":"correctness"}],"questions":[]}
```

`outcome` is `pass`, `fail`, or `blocked`. `findings` is required. Every finding has exactly three non-empty strings: `text`, `severity`, and `kind`; put location, evidence, impact, and smallest correction in `text`. A failed Review requires at least one finding. `questions` is an optional array of concise strings.

Pass requires an empty finding list. Do not include SHA values, checkout inventory, process results, or controller state.
