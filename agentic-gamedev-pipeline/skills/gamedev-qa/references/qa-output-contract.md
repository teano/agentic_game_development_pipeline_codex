# QA semantic artifact

Follow `assignment.artifact_schema` exactly; it is authoritative. Do not inspect runtime code or guess the output shape.

Minimal passing example; use the shared artifact correction rule for every outcome:

```json
{"outcome":"pass","checks":[{"id":"MANUAL-FEATURE-RUNTIME","outcome":"pass","evidence":"Assigned user action through the actual integration: expected result observed."}]}
```

Use the exact `assignment.context.required_identity_ids` derived from the approved plan's existing `mandatory_identity_ids`. Return one `{id,outcome,evidence}` result per assigned identity, distinguishing the actual user/integration path, checks with substitutes, and unexecuted mandatory scenarios. Scenario outcomes are `pass`, `fail`, or `not_run`. A passing artifact requires the exact required set once and every outcome `pass`; missing, unknown, repeated, failed, and unexecuted mandatory results cannot grant credit. The example illustrates one identity only; it does not replace the issued set. A blocked result may retain partial observations with `checks: []` when nothing could execute.

Apply [technical decisions](../../gamedev-pipeline/references/technical-decisions.md) to relevant current entries and verify claimed consequences through the assigned scenarios. Submit every encountered blocker, including one resolved with a permitted technical alternative, through the issued `technical_decisions` field. Update an incorrect entry in place under its same ID. The journal cannot waive required identities, alter acceptance, or make unexecuted evidence pass. Technical correction remains an Engineering responsibility when persistent candidate changes are required; QA stays read-only to product files.

The approved plan defines each identity's scenario, method, and expected result. Evidence states the environment, actual steps/result, and a useful observation or exact evidence location. Do not claim an automated identity passed merely because its name exists: use its actual execution evidence. Controller receipts independently decide whether planned machine checks passed. Never run their argv again merely to populate the report. Passing internal tests do not close an unverified production path. Return `fail` for reproduced product/test failures and reserve `blocked` for missing external prerequisites or unresolved authority conflicts. A `questions` field is only for a reversible technical clarification consistent with approved authority and only with `outcome: pass`; put an authority conflict and required upstream decision in `blocker`/`required_action` instead.

The controller validates exact coverage and candidate binding; it does not prove the truth of an observation. Real production-path evidence remains required. QA product acceptance or planned-command failure returns to Engineering, including after Docs. Documentation-specific Review findings return to the existing Docs owner; QA does not infer a writer from failure prose.

Do not include Git tree OIDs, command digests, or controller state. The controller runs assigned machine checks independently.
