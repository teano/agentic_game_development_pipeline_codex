# Engineering semantic artifact

Follow `assignment.artifact_schema` exactly; it is authoritative. Do not inspect runtime code or guess the output shape.

Minimal passing example; use the shared artifact correction rule for every outcome:

```json
{"outcome":"pass","summary":"Implemented the assigned behavior and coupled tests."}
```

State the actual assigned result in `summary`, including any difference between tests with substitutes and verification of the reported production path. Use the issued schema for allowed outcomes and optional fields.

Do not include changed-path listings, tree OIDs, digest values, command output, mechanical checkout evidence, or controller state. The controller derives the actual Git-tree delta and runs the current slice's planned checks independently.
