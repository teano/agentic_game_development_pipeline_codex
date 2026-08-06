---
name: gamedev-qa
description: Perform independent feature-focused runtime QA on an exactly reviewed game revision. Use after the final Review chain to exercise real player flows through the browser, game client, editor play mode, or Computer Use; complete all independent executable scenarios, distinguish product defects from user/environment/test gates, and return reusable evidence without editing or rerunning the full automated suite.
---

# GameDev Runtime QA

Remain read-only with respect to product code, tests, configuration, requirements, specifications, and pipeline state. Write only QA evidence under `tests/<feature>/qa/<revision>/<run-id>/`.

## Build the runtime matrix

1. Read the approved feature documents, exact composite/product/support/evidence revisions, verification report, coverage manifest, and complete Review chain.
2. Read the controller preflight capability matrix. Do not begin while a required editor connection, published configuration, persistence service, place topology, credential, or control path is recorded unavailable. Use a planned manual operator immediately when preflight says automation cannot perform the required player action.
3. Reuse passing deterministic/build evidence; do not rerun the full automated or project-wide integration suite.
4. Derive scenarios for primary player flows, negative/repeated/interrupted/recovery/boundary behavior, resolved findings, directly affected shared systems, and a small justified adjacent smoke set.
5. State exclusions. Do not expand into unrelated features or a project-wide manual tour.

## Exercise the real game

1. Attach to the exact built revision and record environment identity.
2. Run a short harmless control-feasibility probe before a long scenario.
3. Use ordinary player-visible controls. A project test affordance may shorten setup but must not bypass accepted behavior.
4. Capture steps, expected/actual behavior, logs, timestamps, screenshots or recordings when available, and exact reproduction conditions.

Continue after every defect through all independent scenarios that remain safe and trustworthy. Do not terminate on the first failure. When one finding invalidates another scenario's prerequisite, record `blocked_by_finding: <id>`; do not misclassify it as a gate or separate defect.

After a stable product reproduction, send the technical director a compact provisional candidate containing ID, severity, requirement/scenario, revision, setup, expected/actual behavior, evidence, and reproducibility. The assigned engineering owner may begin read-only discovery, but QA keeps ownership of the remaining matrix and final classification.

## Classify outcomes

Scenario results:

- `PASS`: executed and matched expected behavior;
- `FAIL_PRODUCT`: executed and reproduced a product defect;
- `BLOCKED_USER`: requires a user permission, credential, publication, or manual step;
- `BLOCKED_ENVIRONMENT`: required client, tool, service, device, or runtime is unavailable;
- `ERROR_TEST`: setup, harness, automation, or observation failed before product behavior could be judged;
- `SKIPPED` / `NOT_APPLICABLE`: deliberately excluded with a scope reason;
- `BLOCKED_BY_FINDING`: a recorded product defect invalidated the scenario prerequisite.

Unexecuted behavior is never a product failure. Unrelated asset or service noise is only an observation unless it originates in scope or prevents a mandatory scenario.

Overall result:

- `PASS`: all mandatory scenarios have current-revision evidence and no blocking product failure;
- `FAIL_PRODUCT`: at least one mandatory scenario reproduced a critical or major product defect;
- `BLOCKED_USER`, `BLOCKED_ENVIRONMENT`, or `ERROR_TEST`: only that gate class prevents completion.

For mixed non-product gates, choose the result that owns the minimum resume action and list every pending scenario. A product failure remains `FAIL_PRODUCT`; causally blocked scenarios link to its finding.

## Return the QA contract

Return the complete compact matrix, normalized product candidates, exclusions, gate details, and report path. Each gate records completed reusable evidence, exact pending scenario IDs, reason, and minimum resume action.

Do not fix the product, waive risk, rerun unrelated suites, edit controller state, or declare readiness. `FAIL_PRODUCT` returns automatically to the persistent engineering owner; other non-pass outcomes resume the same QA worker whenever possible.
