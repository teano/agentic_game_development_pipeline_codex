---
name: gamedev-qa
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-qa` by name, explicitly asks for the Agentic GameDev Pipeline QA mode, or an explicitly user-invoked `$gamedev-pipeline` delegates runtime QA. Perform independent feature-focused runtime QA on an exactly reviewed game revision. Do not infer activation from a request to test, playtest, verify, debug, or inspect a game or from a completed Review chain.
---

# GameDev Runtime QA

## Activation gate

Proceed only when the current user explicitly requests `$gamedev-qa` by name, clearly asks for the Agentic GameDev Pipeline QA mode, or this is a runtime-QA assignment delegated by an active `$gamedev-pipeline` that the user explicitly invoked. A request to test, playtest, verify, debug, or inspect a game, and even a completed Review chain, is not authorization. If this gate is not satisfied, do not create pipeline QA evidence or apply this mode's classification contract; continue under ordinary testing instructions and only other explicitly requested skills.

Remain read-only with respect to product code, tests, configuration, requirements, specifications, and pipeline state. Write only QA evidence under `tests/<feature>/qa/<revision>/<run-id>/`.

## Build the runtime matrix

1. Read the approved feature documents, exact composite/product/support/evidence revisions, verification report, coverage manifest, and complete Review chain.
2. Require a recorded `qa-capability-probe` on the exact reviewed revision before this worker is spawned. Its complete matrix covers Studio/editor sync, single play, Test Server with server plus two clients when mandatory, a stable window/control path or declared human operator, log/screenshot capture, persistence/DataStore access, publication/place topology, and configuration/credentials. Every item must be `available`, `not_required`, or `planned_manual`; otherwise do not launch doomed QA.
3. Reuse passing deterministic/build evidence; do not rerun the full automated or project-wide integration suite.
4. Derive scenarios for primary player flows, negative/repeated/interrupted/recovery/boundary behavior, resolved findings, directly affected shared systems, and a small justified adjacent smoke set.
5. State exclusions. Do not expand into unrelated features or a project-wide manual tour.

## Exercise the real game

1. Attach to the exact built revision and record environment identity.
2. Confirm the exact-revision capability probe is still current, then run only a short harmless control-feasibility check before a long scenario.
3. Use ordinary player-visible controls. A project test affordance may shorten setup but must not bypass accepted behavior.
4. Capture steps, expected/actual behavior, logs, timestamps, screenshots or recordings when available, and exact reproduction conditions.

Continue after every defect through all independent scenarios that remain safe and trustworthy. Do not terminate on the first failure. When one finding invalidates another scenario's prerequisite, record `blocked_by_finding: <id>`; do not misclassify it as a gate or separate defect.

After a stable product reproduction, send the technical director a compact provisional candidate containing ID, `finding_kind=product`, severity, scope relation, candidate provenance, production reachability, exact blocked acceptance IDs or required-invariant evidence, revision, setup, expected/actual behavior, evidence, and reproducibility. Never set `blocking`; the controller derives it. Unknown reachability requests bounded triage, not Engineer remediation. The assigned engineering owner may begin read-only discovery, but QA keeps ownership of the remaining matrix and final classification.

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
- `FAIL_PRODUCT`: at least one mandatory scenario produced a controller-classified blocking product finding;
- `BLOCKED_USER`, `BLOCKED_ENVIRONMENT`, or `ERROR_TEST`: only that gate class prevents completion.

For mixed non-product gates, choose the result that owns the minimum resume action and list every pending scenario. A product failure remains `FAIL_PRODUCT`; causally blocked scenarios link to its finding.

## Return the QA contract

Return the complete compact matrix, normalized product candidates, exclusions, gate details, and report path. Each gate records completed reusable evidence, exact pending scenario IDs, reason, failed exact-revision capability probe ID, and minimum resume action. `BLOCKED_ENVIRONMENT` is invalid without that failed probe and resume action. When a capability is already known unavailable, report the probe gate to the director without launching this QA worker.

Do not fix the product, waive risk, rerun unrelated suites, edit controller state, or declare readiness. `FAIL_PRODUCT` returns automatically to the persistent engineering owner; other non-pass outcomes resume the same QA worker whenever possible.
