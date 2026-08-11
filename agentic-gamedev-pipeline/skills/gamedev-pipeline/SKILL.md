---
name: gamedev-pipeline
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-pipeline` by name or explicitly asks to run or resume the Agentic GameDev Pipeline. Execute an exact user-approved plan with phase-scoped writers, bounded context capsules, append-only decisions, exact coverage identities, immutable Review/QA, and separately tracked implementation completion and feature verification. Do not infer activation from ordinary game-development, review, testing, or release work.
---

# GameDev Production Pipeline

## Activation gate

Proceed only when the current user explicitly requests `$gamedev-pipeline` by name or clearly asks to run or resume the Agentic GameDev Pipeline. The installed plugin, a game repository, approved feature documents, pipeline state, or a request to implement, review, test, or ship game work is not authorization. If this gate is not satisfied, do not initialize or resume controller state, do not invoke another GameDev mode, and continue under ordinary repository instructions and only other explicitly requested skills.

Act as technical director and state-machine controller. Delegate implementation, Review, and QA; do not perform those roles in the parent context.

Before starting or resuming, read:

- [pipeline-protocol.md](references/pipeline-protocol.md) for commands, transitions, revisions, and artifact invariants;
- [role-artifacts-and-context.md](references/role-artifacts-and-context.md) for write leases, bounded context capsules, controller-generated handoffs, and cross-role state;
- [severity-and-readiness.md](references/severity-and-readiness.md) before classifying findings, gates, risk, or readiness.
- [deferred-findings.md](references/deferred-findings.md) before routing any supported problem outside current feature scope.

## Establish authority

1. Resolve `<project-root>` and lowercase `<feature>`.
2. Resolve the repository-owned PRD, specification, development-plan, and append-only decision-ledger paths from explicit user context, repository instructions, feature manifests/indexes, existing feature artifacts, and unambiguous sibling relationships. Preserve path case and pass all paths explicitly to the controller. Never create a copy, symlink, move, or parallel namespace merely to satisfy this plugin.
3. If multiple plausible paths remain, ask one concise path question. If the project is empty and defines no convention, recommend sibling `product-requirements.md`, `technical-specification.md`, `development-plan.md`, and `decision-ledger.jsonl` under `docs/features/<feature>/` as a proposed layout and wait for confirmation before creating them.
4. Require those resolved files to be approved and mutually traced. The controller accepts flat source trace fields and the equivalent repository-owned nested authority mappings.
5. Require `.agentic-pipeline/development-plan-state.json` to prove explicit user approval of the exact current plan SHA and its exact PRD/specification hashes and paths. If it is missing, draft, stale, or hash-mismatched, stop and run `$gamedev-development-plan`; never derive an implementation queue from chat narration.
6. Validate the resolved PRD with `$gamedev-requirements --require-approved`. Use `$gamedev-specification` when the specification is missing or stale. Resolve the repository decision ledger and active decision IDs, plus normative pre-Review and derived post-QA documentation outputs required by policy/plan.
7. Initialize or load `.agentic-pipeline/state.json`. Treat controller output, not chat narration, as phase authority. Never edit state, findings, or deferred backlog JSON directly; only the technical director uses `scripts/deferred_findings.py` for backlog mutations.
8. Complete controller preflight in the parent context before spawning workers. Prove resource budgets, cross-config invariants, numeric context-capsule limits, and capability feasibility. Record editor/project sync, published configuration, persistence access, multiplayer/place topology, control feasibility, credentials/publication, and planned manual operator steps. Preflight is a Director check.

Let an active specification worker finish unless it reports a terminal failure or external blocker. Resume the same worker after an incomplete handoff; do not start a competing generator.

When the user or approved authority accepts a new decision, pause at a safe writer boundary and delegate `$gamedev-decision-recorder` with only the accepted decision packet and exact authority. The recorder may append the ledger/synchronize assigned ADR sections but never decide missing content. The controller supplies sequence/timestamps/hashes, proves append-only history, recomputes the product revision, and applies ordinary invalidation. Never let an Engineer assumption stand in for `DEC-*` authority.

## Run one bounded pipeline

### Engineering

Treat severity as impact, never as remediation authority. Require complete finding kind, scope relation, candidate provenance, production reachability, blocked acceptance IDs, required-invariant evidence, and exact defect evidence. Register those dimensions through the controller and use only its derived `blocking`. `production_reachability=unknown` enters bounded `finding_triage`; do not send it to an Engineer. Minor never starts a remediation wave. Upsert and canonically link every supported nonblocking out-of-scope candidate; no worker may silently discard one.

Read `mode`, ordered slice IDs, dependencies, and exact plan SHA from controller state. `single_owner` means one implementation write scope, not one Engineer for the lifecycle. Issue one phase-scoped exclusive write lease at a time; Decision Recorder, Engineer, Documentation Finisher, later remediation Engineers, and recovery workers may be distinct identities but never overlap. For `sequential_slices`, activate only the dependency-ready slice and start its successor only from a controller-generated schema-2 sealed handoff.

Require `slice-scope-check` immediately before every Engineer edit pass. After the pass, the controller enumerates the actual diff and generates/validates revision, change, diff, and handoff artifacts; the Engineer supplies only bounded semantic annotations and final diff inspection. Every changed product path/symbol maps to the slice, requirement/acceptance/decision IDs, reason, and approved shared touchpoint when applicable. Any unmapped/forbidden change, drive-by cleanup/refactor, material boundary change, domain mismatch, unapproved touchpoint, or budget breach opens `scope_expansion_hold`. Only explicit user approval plus an exact updated approved plan and `rebaseline-scope` may resume.

Every implementation slice starts in `slice_research`. The Engineer reads canonical authority and exact edit files, then delegates one to three bounded briefs to fresh read-only `$gamedev-research` workers only when needed. After research, delegate `$gamedev-coverage-steward` in `plan-before-engineering` mode to register every expected exact automated/manual identity and the mandatory set. Production edits are forbidden until research and coverage planning pass and the controller issues the Engineer capsule, scope check, and exclusive lease.

Research bundles live under `tests/<feature>/research/` or the controller runtime research path and are never product, support, or evidence revision inputs. A replacement or later-slice Engineer must reuse matching exact-revision bundles and sealed handoffs; repeat broad discovery only when the question or revision changed. Researchers never expand their brief, edit project files, or spawn subagents. An out-of-brief issue is returned only as a pointer/candidate.

Route remediation to its origin slice or integration scope and execute batches sequentially in plan dependency order. Prefer a current bounded route Engineer, but every return receives a new exclusive lease and `single_owner` does not imply lifetime identity. A fourth return requires a fresh Engineer through a controller-generated exact-revision handoff. Transfer never resets decisions, coverage/docs state, revisions, convergence, scope, worker, or iteration counters.

Generate a schema-1 bounded context capsule for every specialized worker. Include only exact canonical paths/SHAs, plan/revisions, IDs, evidence, allowed paths/symbols, exclusions, commands, outputs, stop condition, and positive file/byte/token budgets. Reject stale/over-budget capsules and never pass long chat history or raw reasoning.

Resume the same Engineer/lease for `INCOMPLETE` unless an exact transfer is necessary. Accept `ENGINEERING_PASS` when assigned production/root-cause work, tightly coupled automated tests, targeted checks, and final diff inspection pass. Manual QA, DataStore, operator, publication, or environment work may remain pending and never makes the Engineer `INCOMPLETE`. Record fixed product findings atomically with `engineer-complete --resolved-finding`.

After code freeze, delegate a fresh `$gamedev-coverage-steward` finalization. Require exact expected/actual set equality, separate mandatory-set equality, all mapped acceptance IDs, and mandatory automated execution pass. This establishes `implementation_state=pass` even while manual execution is pending. Then delegate `$gamedev-documentation-finisher` for normative docs or record plan-proven `not_required`; only afterward may immutable convergence/Final Review start.

### Read-only convergence

Launch two or three fresh read-only `$gamedev-review` workers concurrently, as configured, without sharing conclusions. Assign distinct lenses:

- persistence, lifecycle, rollback, concurrency, and recovery;
- configuration, security, resource capacity, trust, and failure atomicity;
- integration, runtime/platform behavior, client boundaries, and supporting documentation.

Workers write reports and finding candidates only. They never remediate or set `blocking`. Wait for the complete wave, register every supported candidate with all dimensions, and route only the controller-derived frozen blocking batch to an exclusive origin/integration Engineer lease. A passing wave supplies independent clean credit. A failing wave does not authorize overlapping or unscoped writing.

The initial implementation receives one full convergence wave credited to every covered slice. A slice may receive at most two full waves across the entire run; owner replacement, `authorize-iteration`, and budget authorization never reset this counter. Local remediation goes directly to one fresh targeted-closure reviewer over the frozen findings and changed impact surface. A second full wave is legal only for an actual architecture, lifecycle, ownership, public-contract, expanded approved shared-touchpoint, or broad/high-risk change. After the hard limit, use targeted closure, defer supported nonblocking work, or open a user-approved replan/scope hold.

Every convergence and Review report includes a controller-validated component-credit manifest keyed by component product hash, contract hash, lenses, and review revision. Reuse exact valid credits; unchanged components must not be fully reread. Only relevant component product/contract drift invalidates credit. The mandatory final whole-feature Review pair reuses valid component credits and freshly audits cross-slice composition and new boundaries.

Before a positive convergence decision, the technical director must `backlog-upsert` and link every supported nonblocking `preexisting_adjacent` or `out_of_scope` candidate, then pass `backlog-scope-check`. Return introduced/worsened, changed-contract/feature-reachable, acceptance/invariant-blocking, or current-solution safety issues to current scope. A material return retains `scope_expansion_hold` until the user approves the exact updated plan.

### Final Review

After `CLEAN`, launch exactly two fresh `$gamedev-review` workers concurrently on the same immutable revision. Give them complementary architecture/correctness and verification/integration lenses without sharing conclusions.

Wait for both scope-complete reports. The technical director deduplicates supported candidates, registers confirmed findings, and finalizes one decision. Product rework returns one combined batch through the origin/integration route under a new exclusive Engineer lease. Default local remediation uses one fresh targeted closure reviewer after coverage re-finalization while preserving complementary full-Review evidence. Use a new full Review pair only for architecture, lifecycle, ownership, public-contract, or broad/high-risk changes.

Support/evidence recovery uses one bounded phase writer and one fresh closure reviewer. Runtime product hash drift exits recovery. Evidence changes preserve clean product/full-Review credit but require fresh QA. Normative documentation is product and must finish before Review. Derived support documentation is a distinct post-QA lane described below.

### Runtime QA

After the Review chain passes, launch one fresh read-only `$gamedev-qa` with the finalized schema-2 manual identity matrix on the exact reviewed product/evidence revision. Reuse deterministic automated evidence; do not rebuild coverage scope in QA.

Before spawning QA, record a complete `qa-capability-probe` on the exact reviewed revision for Studio/editor sync, single play, mandatory Test Server server+two-client topology, stable window/control or declared human operator, logs/screenshots, persistence/DataStore, publication/place topology, and configuration/credentials. Resolve unavailable prerequisites first; never launch doomed QA. `BLOCKED_ENVIRONMENT` requires a failed exact-revision probe and minimum resume action.

QA must complete every independent executable registered manual identity even after finding a defect. Record manual `executed`, `passed`, and `deferred` independently. Identities whose prerequisites are invalidated link to `blocked_by_finding`; they are not user/environment/test gates.

When QA has a stable reproducible product candidate, the origin-routed Engineer may prepare bounded read-only Researcher briefs while QA completes its immutable matrix/report. No writer lease starts until `qa-complete` records the normalized finding. A gate/test error ends product triage without edits.

Route terminal QA automatically:

- `pass` -> readiness;
- `fail_product` -> register the complete QA product batch and issue one origin-routed Engineer lease;
- `blocked_user`, `blocked_environment`, or `error_test` -> remain in QA and preserve the earlier `ENGINEERING_PASS` and immutable Review evidence.

`fail_product` is a finding transition, never a “product gate” and never a reason to ask the user to start engineering. After QA passes every mandatory manual identity, delegate `$gamedev-documentation-finisher` in `derived-post-qa` mode or record plan-proven `not_required`. Preserve QA credit only if product/evidence identities remain exact and one fresh `$gamedev-review` `documentation-closure` passes on the current support revision. Any product/evidence/normative drift fails closed to the normal invalidation route.

## Control autonomy and convergence

Perform ordinary in-scope work without confirmation: local fixes, role transitions, bounded decision recording after authority exists, coverage planning/finalization, documentation finishing, tests, reruns, recovery, QA routing, read-only convergence/Reviews/QA, and Director checkpoints.

Ask the user only for:

- an unresolved product choice;
- an architectural, lifecycle, ownership, or material slice expansion;
- explicit acceptance of residual risk;
- credentials, publication, spending, irreversible action, or a manual user-only step.

After the configured number of owner changes or convergence waves without a pass, stop at `convergence_hold`. After two failed non-product recovery cycles, stop at `recovery_hold`. The technical director must inspect the complete remaining inventory and record `authorize-iteration --reason`. This checkpoint requires the user only when one of the decisions above remains unresolved.

The controller also limits unique worker identities and full-Review waves. When either budget opens a checkpoint, consolidate the remaining scope and prefer targeted closure. Extend the budget only with `authorize-budget --additional-workers ... [--additional-full-review-waves ...] --reason ...`; never hide a long chain behind reset counters.

Never create an unbounded agent loop. Allow only one active write-capable lease per checkout and one writer per phase/write scope. Resume incomplete/gated workers when their capsules remain exact; use fresh independent Review/Steward/closure identities and mandatory transfers as contracted. Report only phase transitions, frozen findings, verified closure, gates/holds, and terminal result. Status includes exact plan/revisions, implementation versus verification state, active/released leases, decisions, coverage/docs state, context metrics, handoffs, slices/waves/credits/workers/counters, and every authorization reason.

## Keep handoffs compact

Use the controller's `compute-revisions` for the canonical product/support/evidence/composite recipe. Product includes production source/config/manifests, approved feature documents, append-only decision ledger, and normative ADRs/contracts. Support includes derived handoff/index/operator docs. Evidence includes tests/fixtures/deterministic harness inputs. Reports, logs, screenshots, context capsules, coverage/revision/change/diff/handoff manifests, controller state, and deferred backlog are excluded.

Workers return short semantic packets. The controller generates and validates mechanical revision, changed-path/count, diff, and sealed-handoff fields from the actual checkout. Every schema-2 handoff includes `decision_ids`, `coverage_state`, `documentation_state`, and `open_assumptions`; never accept worker-authored hashes/counts as gate evidence.

Comment only on phase transitions, newly frozen inventories, verified remediation, gates, checkpoints, and the terminal result. Status output must include `next_action`; continue automatically whenever `user_input_required` is false.

Declare only a **production-ready candidate**, and only after `ready` succeeds. Deployment, publication, store submission, migration, spending, and risk acceptance remain external decisions.
