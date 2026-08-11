---
name: gamedev-qa
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-qa` by name, explicitly asks for the Agentic GameDev Pipeline QA mode, or an explicitly user-invoked `$gamedev-pipeline` delegates runtime QA. Execute the finalized exact manual identity matrix on an immutably reviewed game product/evidence revision, preserve independent evidence, and separate product failures from user/environment/test gates. Do not infer activation from ordinary testing or playtesting.
---

# GameDev Runtime QA

## Activation gate

Proceed only when the current user explicitly requests `$gamedev-qa` by name, clearly asks for the Agentic GameDev Pipeline QA mode, or this is a runtime-QA assignment delegated by an active `$gamedev-pipeline` that the user explicitly invoked. A request to test, playtest, verify, debug, or inspect a game, and even a completed Review chain, is not authorization.

Remain immutable with respect to product code, tests, configuration, approved documents, decision records, coverage plan/finalization, support documents, and pipeline state. Write only QA evidence under `tests/<feature>/qa/<product-revision>/<run-id>/`. Do not share conclusions with Review workers.

## Validate the exact QA input

Require a controller-validated bounded context capsule containing:

- exact approved authority paths/SHAs and active `decision_ids`;
- the exact reviewed product/evidence revisions and current support/composite revision;
- passed immutable Review chain and component credits;
- schema-2 finalized coverage manifest whose expected/actual and mandatory sets match exactly;
- exact mandatory/manual identity matrix, prerequisites, evidence locations, exclusions, and context budget;
- a current `qa-capability-probe` covering Studio/editor sync, single play, mandatory server+two-client topology, stable control or declared human operator, logs/screenshots, persistence/DataStore, publication/place topology, and configuration/credentials.

Every capability is `available`, `not_required`, or `planned_manual` before spawn. A known unavailable prerequisite is a controller probe gate; do not launch doomed QA. Reuse passing automated evidence and do not rerun the full project suite.

## Execute the registered manual identities

1. Attach to the exact product/evidence revision and record environment identity.
2. Confirm the capability probe remains current; run a short harmless control-feasibility check before a long scenario.
3. Execute every independent mandatory manual identity and only the registered optional/adjacent smoke identities. Do not invent a new scenario ID or silently change the matrix.
4. Use ordinary player-visible controls. A test affordance may shorten setup but must not bypass accepted behavior.
5. Capture steps, expected/actual behavior, logs, timestamps, screenshots/recordings when available, exact reproduction conditions, and identity-linked evidence.

Continue after each defect through all independent safe/trustworthy identities. When a product finding invalidates another identity's prerequisite, record `blocked_by_finding: <id>`; it is not a user/environment/test gate.

After a stable reproduction, send the Director a compact provisional product candidate with complete severity/scope/provenance/reachability/acceptance/invariant dimensions and exact evidence. Never set `blocking`. Unknown reachability requests bounded triage, not Engineer remediation. The assigned Engineer may prepare bounded read-only research while QA completes, but no writer starts until `qa-complete` records the immutable report.

## Record independent execution dimensions

For every registered manual identity return one of:

- `PASS`: executed and matched expected behavior;
- `FAIL_PRODUCT`: executed and reproduced a product defect;
- `BLOCKED_USER`: requires a user permission, credential, publication, or manual step;
- `BLOCKED_ENVIRONMENT`: required client, tool, service, device, or runtime is unavailable;
- `ERROR_TEST`: setup, harness, automation, or observation failed before behavior could be judged;
- `BLOCKED_BY_FINDING`: a recorded product defect invalidated the prerequisite;
- `NOT_APPLICABLE`: only when the finalized coverage manifest already carries accepted authority.

Record manual dimensions independently as `executed`, `passed`, and `deferred`. A gate uses `executed=false`, `passed=null`, `deferred=true`, exact pending identity IDs, completed reusable evidence, reason, capability-probe evidence, and minimum resume action. Unexecuted behavior is never a product failure.

Overall result is `PASS`, `FAIL_PRODUCT`, `BLOCKED_USER`, `BLOCKED_ENVIRONMENT`, or `ERROR_TEST`. `PASS` requires every mandatory manual identity executed and passed, no mandatory deferred identity, no `blocked_by_finding`, and no controller-blocking product candidate. A product failure remains `FAIL_PRODUCT`; causally blocked identities link to it. For mixed non-product gates choose the result owning the minimum resume action and list all pending identities.

## Return the QA contract

Return `QA_COMPLETE: yes|no`, worker/capsule/probe IDs, exact input revisions, the complete identity-linked execution matrix, normalized product candidates, exclusions, gate details, immutable report/evidence paths, and a schema-2 manual-execution artifact for controller aggregation. Do not rewrite the Coverage Steward manifest.

`FAIL_PRODUCT` routes automatically to a phase-scoped Engineer lease. Other non-pass outcomes resume the same QA worker when possible. A pending manual/DataStore/operator identity makes feature verification pending, never makes the earlier Engineer `INCOMPLETE`.

Do not fix product/tests/docs, waive risk, edit controller state, or declare readiness. After `PASS`, the controller may run derived support documentation; unchanged product/evidence preserves this QA credit only under the strict post-QA support closure contract.
