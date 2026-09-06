# Review semantic artifact

Follow `assignment.artifact_schema` exactly; it is authoritative. Do not inspect runtime code or guess the output shape.

Minimal failing example; use the shared artifact correction rule for every outcome:

```json
{"outcome":"fail","findings":[{"text":"src/state.py permits an invalid transition; reject it before mutation.","severity":"high","kind":"correctness"}]}
```

Put location, evidence, impact, and smallest correction in each finding's `text`; field requirements come from the issued schema. A failed Review requires at least one finding.

Every finding must be confined to `assignment.context.review_target` and demonstrate all of the following:

- concrete current-candidate evidence;
- a reachable supported game path or deterministic code trace;
- material violation of mandatory approved behavior or acceptance, or concrete target complexity that KISS/YAGNI rejects;
- a smallest sufficient correction inside the target.

Read-access authority, sealed `read_paths`, completed-slice paths, and untouched paths covered by a broad rule are evidence context rather than extra audit scope. For `current_slice_implementation`, `required_scope` equals `context.current_slice.allowed_paths` and `candidate_changes` is the accepted Engineering diff path list plus retained Engineering paths from reconfiguration history within that scope. An introduced defect or excess-complexity finding must identify a path in `candidate_changes`; outside those paths, only missing mandatory implementation inside `required_scope` or a direct regression caused by the candidate is eligible. For `documentation_changes`, `candidate_changes` is both the required scope and the whole target.

Reject concrete unnecessary abstraction, state, configuration, fallback, dependency, or lifecycle introduced by the target when authority does not need it and a simpler sufficient implementation exists. Never demand more layers, generality, defensive infrastructure, hypothetical extensibility, optional cleanup, refactoring preference, style changes, unrequested security hardening, or tests merely for completeness. Unsupported misuse, manual tampering, future scale, theoretical or extremely unlikely risks, and pre-existing unrelated issues are not findings.

Pass requires an empty finding list and no suggestions or backlog. `questions` is valid only with `outcome: pass` for a reversible technical clarification consistent with approved authority. An authority contradiction affecting product behavior or scope is `blocked`: state the conflict and the exact upstream decision in `blocker`/`required_action`. Also use `blocked` when a mandatory assigned input or capability is actually unavailable. Do not attach `questions` to `fail` or `blocked`.

The controller routes a failed `documentation_changes` Review back to the existing Documentation Finisher with approved documentation write paths, followed by fresh Review and QA. A failed `current_slice_implementation` Review returns to Engineering. This routing uses the issued target, never words in findings. Do not include Git tree OIDs, process results, or controller state.
