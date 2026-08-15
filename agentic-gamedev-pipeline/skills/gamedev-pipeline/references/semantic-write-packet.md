# Semantic write packet

This worker-owned contract applies only to a write role whose skill links it. The controller, not the worker, generates revisions, counts, manifests, and sealed handoffs.

Return exactly one JSON object with integer `schema: 1`, literal `inventory_complete: true`, exact `domain_inventory`, `changes`, and `open_assumptions` fields:

```json
{"schema":1,"inventory_complete":true,"domain_inventory":{"product":["src/feature.py"],"support":[],"evidence":["tests/test_feature.py"]},"changes":[{"path":"src/feature.py","domain":"product","symbols":["VALUE"],"reason":"assigned_goal_effect: PRD-REQ-001, PRD-AC-001 | Implement approved behavior.","change_kind":"modify","component":"feature-core","lifecycle_change":false,"ownership_change":false,"public_contract_change":false,"requirement_ids":["PRD-REQ-001"],"acceptance_ids":["PRD-AC-001"],"decision_ids":[],"touchpoint_id":null}],"open_assumptions":[]}
```

`domain_inventory` has exactly duplicate-free, non-overlapping `product`, `support`, and `evidence` path arrays and describes the complete post-pass inventory. A deleted path is absent; every other changed path is present.

Each `changes` row has exactly string `path`; enum `domain: product|support|evidence`; string arrays `symbols`, `requirement_ids`, `acceptance_ids`, `decision_ids`; non-empty strings `reason` and `component`; enum `change_kind: add|modify|delete`; booleans `lifecycle_change`, `ownership_change`, `public_contract_change`; and `touchpoint_id`, either `null` or exact `TP-NNN`. A Documentation Finisher row additionally has exactly one unique `change_id: DOC-CHG-*`; no other role may add that field. `reason` starts with `assigned_goal_effect: <sorted requirement IDs>, <sorted acceptance IDs> | ` and a non-empty direct-effect explanation.

Requirement/acceptance IDs are non-empty assigned-scope subsets; decisions are active. Each assumption has exactly non-empty `assumption_id`, `statement`, `owner`, `validation_point`, and `impact_if_false`. Assumptions must be resolved through an existing decision, finding, or gate before terminal readiness; a ready handoff has an empty array. Missing/extra fields, paths, IDs, or domains fail closed.
