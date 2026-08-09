---
name: gamedev-pipeline
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-pipeline` by name or explicitly asks to run or resume the Agentic GameDev Pipeline. Execute an exact user-approved development plan with one writer at a time, sequential vertical slices when planned, origin-routed remediation, final convergence, immutable Review, runtime QA, and production-readiness. Do not infer activation from a game-development task, approved documents, implementation, review, testing, release work, or existing pipeline artifacts.
---

# GameDev Production Pipeline

## Activation gate

Proceed only when the current user explicitly requests `$gamedev-pipeline` by name or clearly asks to run or resume the Agentic GameDev Pipeline. The installed plugin, a game repository, approved feature documents, pipeline state, or a request to implement, review, test, or ship game work is not authorization. If this gate is not satisfied, do not initialize or resume controller state, do not invoke another GameDev mode, and continue under ordinary repository instructions and only other explicitly requested skills.

Act as technical director and state-machine controller. Delegate implementation, Review, and QA; do not perform those roles in the parent context.

Before starting or resuming, read:

- [pipeline-protocol.md](references/pipeline-protocol.md) for commands, transitions, revisions, and artifact invariants;
- [severity-and-readiness.md](references/severity-and-readiness.md) before classifying findings, gates, risk, or readiness.
- [deferred-findings.md](references/deferred-findings.md) before routing any supported problem outside current feature scope.

## Establish authority

1. Resolve `<project-root>` and lowercase `<feature>`.
2. Require approved, mutually traced files at:
   - `docs/features/<feature>/product-requirements.md`;
   - `docs/features/<feature>/technical-specification.md`;
   - `docs/features/<feature>/development-plan.md`.
3. Require `.agentic-pipeline/development-plan-state.json` to prove explicit user approval of the exact current plan SHA and its exact PRD/specification hashes. If it is missing, draft, stale, or hash-mismatched, stop and run `$gamedev-development-plan`; never derive an implementation queue from chat narration.
4. Validate the PRD with `$gamedev-requirements --require-approved`. Use `$gamedev-specification` when the specification is missing or stale. Read repository policy and decide whether the plan requires supporting tracked documentation such as an ADR, runbook, or public contract.
5. Initialize or load `.agentic-pipeline/state.json`. Treat controller output, not chat narration, as phase authority. Never edit state, findings, or deferred backlog JSON directly; only the technical director uses `scripts/deferred_findings.py` for backlog mutations.
6. Complete controller preflight in the parent context before spawning an Engineer. Prove numeric resource budgets and cross-config invariants from the approved specification. Record editor/project sync, published configuration, persistence access, multiplayer or multi-place setup, control feasibility, credentials/publication, and planned manual operator steps. Preflight is a director check, not another agent session.

Let an active specification worker finish unless it reports a terminal failure or external blocker. Resume the same worker after an incomplete handoff; do not start a competing generator.

## Run one bounded pipeline

### Engineering

Treat severity as impact, never as remediation authority. Require complete finding kind, scope relation, candidate provenance, production reachability, blocked acceptance IDs, required-invariant evidence, and exact defect evidence. Register those dimensions through the controller and use only its derived `blocking`. `production_reachability=unknown` enters bounded `finding_triage`; do not send it to an Engineer. Minor never starts a remediation wave. Upsert and canonically link every supported nonblocking out-of-scope candidate; no worker may silently discard one.

Read `mode`, ordered slice IDs, dependencies, and exact plan SHA from controller state. For `single_owner`, keep one writing owner for the complete implementation. For `sequential_slices`, spawn the Engineer for only the active slice, wait for its terminal passing result, and record a schema-1 sealed handoff manifest containing the exact base and result revisions before spawning the next slice owner. Never overlap writers, skip a dependency, or start a later slice from an unsealed revision.

Require `slice-scope-check` immediately before every Engineer edit pass. After the pass, deterministically compare its schema-1 change-manifest and diff-summary with the active approved slice: every changed product file/symbol maps to the slice plus `PRD-REQ-*`/`PRD-AC-*` and reason; shared files map to an approved touchpoint ID, symbol, and change kind; exclusions, product file/line budgets, and lifecycle/ownership/public-contract flags pass. Any unmapped or forbidden change, drive-by cleanup/refactor, material boundary change, unapproved touchpoint, or budget breach opens `scope_expansion_hold`. No edit, Review, owner transfer, iteration authorization, or next slice may proceed. Only explicit user approval plus an updated approved plan at its exact SHA and `rebaseline-scope` may resume. Preserve scope churn/history across owner changes. Smoke execution does not expand scope; modifying foreign product code does.

Every implementation slice starts in controller phase `slice_research`. The assigned Engineer first reads the canonical PRD/specification/plan, repository policy, predecessor handoff, and intended edit files, then creates one to three bounded briefs and delegates them to fresh read-only `$gamedev-research` workers. Each brief names one question, `SLICE/REQ/AC` IDs, exact base revision, seeds, allowed paths/symbols, exclusions, requested evidence, `max_files`, stop condition, and result path. Record all bundles atomically with `slice-research-complete`; use `slice-research-not-required` only when canonical documents, an exact-revision handoff, and exact edit files fully answer the implementation questions. Production edits are forbidden until the controller advances to `slice_engineering`.

Research bundles live under `tests/<feature>/research/` or the controller runtime research path and are never product, support, or evidence revision inputs. A replacement or later-slice Engineer must reuse matching exact-revision bundles and sealed handoffs; repeat broad discovery only when the question or revision changed. Researchers never expand their brief, edit project files, or spawn subagents. An out-of-brief issue is returned only as a pointer/candidate.

Store `owner_by_slice` and one `integration_owner`. Route a remediation finding to its `origin_slice` owner; group findings by route and execute those batches sequentially in development-plan dependency order. Route a cross-slice root cause to the integration owner. A slice owner may receive at most three completed remediation returns. Before a fourth return, stop at `owner_handoff_hold` and require a structured exact-revision handoff to a fresh Engineer for that same route. Owner replacement never resets convergence, scope, worker, or iteration counters.

Pass only canonical paths, the exact approved plan hash, active slice, assigned IDs, base/result revision identities, check commands, research/handoff artifact paths, and report paths. Require the owner to finish its assigned pass, run its checks, and seal the required handoff.

Resume the same Engineer for `INCOMPLETE`. Reject a terminal handoff without `AUDIT_COMPLETE: yes`, a complete coverage manifest, and required passing evidence. Record fixed persisted product findings atomically with `engineer-complete --resolved-finding`; never call `resolve-finding` after completion to repair phase state.

A product-changing owner cannot award independent clean credit. During sequential implementation, advance only to the next planned slice after sealing the current result. Start whole-feature convergence, Final Review, and QA only after every planned slice is sealed; after remediation, re-enter convergence only after every dependency-ordered batch completes.

### Read-only convergence

Launch two or three fresh read-only `$gamedev-review` workers concurrently, as configured, without sharing conclusions. Assign distinct lenses:

- persistence, lifecycle, rollback, concurrency, and recovery;
- configuration, security, resource capacity, trust, and failure atomicity;
- integration, runtime/platform behavior, client boundaries, and supporting documentation.

Workers write reports and finding candidates only. They never remediate or set `blocking`. Wait for the complete wave, register every supported candidate with all classification dimensions, and return only the controller-derived frozen blocking batch to the same engineering owner. A passing wave supplies independent clean credit. A failing wave never starts a fresh writer by itself.

The initial implementation receives one full convergence wave credited to every covered slice. A slice may receive at most two full waves across the entire run; owner replacement, `authorize-iteration`, and budget authorization never reset this counter. Local remediation goes directly to one fresh targeted-closure reviewer over the frozen findings and changed impact surface. A second full wave is legal only for an actual architecture, lifecycle, ownership, public-contract, expanded approved shared-touchpoint, or broad/high-risk change. After the hard limit, use targeted closure, defer supported nonblocking work, or open a user-approved replan/scope hold.

Every convergence and Review report includes a controller-validated component-credit manifest keyed by component product hash, contract hash, lenses, and review revision. Reuse exact valid credits; unchanged components must not be fully reread. Only relevant component product/contract drift invalidates credit. The mandatory final whole-feature Review pair reuses valid component credits and freshly audits cross-slice composition and new boundaries.

Before a positive convergence decision, the technical director must `backlog-upsert` and link every supported nonblocking `preexisting_adjacent` or `out_of_scope` candidate, then pass `backlog-scope-check`. Return introduced/worsened, changed-contract/feature-reachable, acceptance/invariant-blocking, or current-solution safety issues to current scope. A material return retains `scope_expansion_hold` until the user approves the exact updated plan.

### Final Review

After `CLEAN`, launch exactly two fresh `$gamedev-review` workers concurrently on the same immutable revision. Give them complementary architecture/correctness and verification/integration lenses without sharing conclusions.

Wait for both scope-complete reports. The technical director deduplicates supported candidates, registers confirmed findings, and finalizes one decision. Product rework returns one combined batch to the existing engineering owner. Default local remediation uses one fresh targeted closure reviewer after convergence while preserving complementary full-Review evidence. Use a new pair of full Reviews only when remediation changes architecture, lifecycle, ownership, public contract, or a broad/high-risk impact surface.

Support/evidence recovery uses one bounded remediator and one fresh closure reviewer. Runtime product hash drift exits recovery. Changes limited to derived documentation, handoff/index metadata, tests, fixtures, or harnesses preserve clean runtime and full-Review credit; do not repeat architecture Review or product convergence.

### Runtime QA

After the Review chain passes, launch one fresh read-only `$gamedev-qa` on the exact revision. Reuse deterministic evidence and test only the feature, directly affected shared behavior, and a small justified adjacent smoke set.

Before spawning QA, record a complete `qa-capability-probe` on the exact reviewed revision for Studio/editor sync, single play, mandatory Test Server server+two-client topology, stable window/control or declared human operator, logs/screenshots, persistence/DataStore, publication/place topology, and configuration/credentials. Resolve unavailable prerequisites first; never launch doomed QA. `BLOCKED_ENVIRONMENT` requires a failed exact-revision probe and minimum resume action.

QA must complete every independent executable scenario even after finding a defect. Scenarios whose prerequisites are invalidated are linked to the finding as `blocked_by_finding`, not classified as user, environment, or test gates.

When QA has a stable reproducible product candidate, the assigned engineering owner may read the canonical documents and exact edit files and prepare bounded Researcher briefs while QA completes its matrix and report; the Engineer must not begin repository-wide discovery. The owner must not edit until the controller records `qa-complete` and the normalized finding. If QA reclassifies the candidate as a gate or test error, end the triage without product changes.

Route terminal QA automatically:

- `pass` -> readiness;
- `fail_product` -> register the complete QA product batch and return it to the existing engineering owner;
- `blocked_user`, `blocked_environment`, or `error_test` -> remain in QA and preserve current Engineer/Review evidence.

`fail_product` is a finding transition, never a “product gate” and never a reason to ask the user to start engineering.

## Control autonomy and convergence

Perform ordinary in-scope work without confirmation: local fixes, tests, reruns, support/evidence recovery, QA-to-owner routing, read-only convergence, Reviews, QA, and technical-director checkpoints.

Ask the user only for:

- an unresolved product choice;
- an architectural, lifecycle, ownership, or material slice expansion;
- explicit acceptance of residual risk;
- credentials, publication, spending, irreversible action, or a manual user-only step.

After the configured number of owner changes or convergence waves without a pass, stop at `convergence_hold`. After two failed non-product recovery cycles, stop at `recovery_hold`. The technical director must inspect the complete remaining inventory and record `authorize-iteration --reason`. This checkpoint requires the user only when one of the decisions above remains unresolved.

The controller also limits unique worker identities and full-Review waves. When either budget opens a checkpoint, consolidate the remaining scope and prefer targeted closure. Extend the budget only with `authorize-budget --additional-workers ... [--additional-full-review-waves ...] --reason ...`; never hide a long chain behind reset counters.

Never create an unbounded agent loop. Allow only one writing owner per checkout. Resume incomplete or gated workers; use fresh workers only for configured read-only independence or the mandatory post-third-return handoff. Report only milestones: phase transitions, newly frozen findings, verified closure, gates, holds, and terminal result. Do not busy-poll agents or narrate unchanged status. Status must identify fresh versus reused reviewer/credit identities and report the exact plan SHA, ordered/active slices, per-slice base/result revisions and full-wave count, owners, handoffs, remediation-return counters, unique workers, convergence wave, full-Review waves, and every authorization reason.

## Keep handoffs compact

Use `compute-revisions` for the canonical runtime product, support, evidence, and composite hash recipe. Put production source, configuration, manifests, normative ADRs/contracts, and approved feature documents in `product`; derived handoff/index/operator documentation in `support`; and tests, fixtures, deterministic harnesses, and verification inputs in `evidence`. Reports, logs, screenshots, revision manifests, controller state, and `docs/engineering/deferred-findings.json` are not revision inputs.

Comment only on phase transitions, newly frozen inventories, verified remediation, gates, checkpoints, and the terminal result. Status output must include `next_action`; continue automatically whenever `user_input_required` is false.

Declare only a **production-ready candidate**, and only after `ready` succeeds. Deployment, publication, store submission, migration, spending, and risk acceptance remain external decisions.
