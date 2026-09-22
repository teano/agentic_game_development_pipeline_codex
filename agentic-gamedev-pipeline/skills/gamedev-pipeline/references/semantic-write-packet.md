# Engineering semantic artifact

Follow `assignment.artifact_schema` exactly; it is authoritative. Do not inspect runtime code or guess the output shape.

Passing shape; replace placeholders with actual assigned evidence and use the shared artifact correction rule for every outcome:

```json
{"outcome":"pass","summary":"<Actual result>; <test/scenario locator> asserts <decisive behavior at the claimed boundary>."}
```

State the actual assigned result in `summary`. For grouped closure claims, name the decisive test/scenario locator and assertion; disclose when the operation being claimed was substituted. Distinguish phase-authorized deferred evidence. Use the issued schema for allowed outcomes and optional fields.

For remediation, keep the compact finding ID → actual change/proof mapping in these existing fields. Account for every concrete condition of each current finding and preserve already verified scenarios; partial correction remains an open failure. Cite the actual evidence at the claimed boundary, without inventing receipts, adding fields or creating a separate ledger.

Follow [technical decisions](technical-decisions.md) for unexpected situations. Submit every encountered blocker and its current resolution through the issued `technical_decisions` field or sanctioned public action. An update replaces the same decision ID; do not create supersession chains. Explain the specific source correction and evidence without inventing command receipts. A resolved technical obstacle may accompany `pass`; unresolved acceptance evidence does not become passing evidence because it is logged.

Do not include changed-path listings, tree OIDs, digest values, command output, mechanical checkout evidence, or controller state in the terminal semantic artifact. The separate active technical-action request uses the exact controller-provided assignment and observed-tree binding required by [pipeline protocol](pipeline-protocol.md#technical-action-interface); it never invents that evidence. The controller derives the actual Git-tree delta and runs the current slice's planned checks independently.
