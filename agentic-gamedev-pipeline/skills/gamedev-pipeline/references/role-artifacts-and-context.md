# Delegated role context contract

This is an audit/reference contract for delegated context. It is not Director startup material and contains no worker output schemas. Each worker reads only the output contract linked from its own skill; the controller validates mechanical envelopes.

## Isolation and logical identity

Every phase assignment starts in a new session with no inherited Director or prior worker chat history (`fork_turns: none` or equivalent). Its initial cross-stage input is exactly root, skill/mode, one controller-validated capsule or bounded read-only assignment, the worker-owned output contract, and a deterministic stop condition.

The controller may preserve one logical independent non-writer verifier ID across convergence Review, Final Review, QA, and documentation closure. Logical identity reuse never means conversation reuse. Each phase receives a fresh isolated session and capsule. An Engineer or any writer identity is never that verifier.

Generic human-readable predecessor Review reports are audit artifacts, not capsule evidence for Final Review or QA. Those phases receive only the exact current handoff, validated component-credit manifests, finalized coverage, capability proof, and phase-specific evidence required by their worker contract. A worker never reads sibling conclusions.

## Exclusive write leases

`single_owner` is a planning shape, not a lifetime worker identity. Decision Recorder, Engineer, Documentation Finisher, and Recovery Remediator use phase-scoped exclusive leases; only one writer/lease may be active. Review, QA, and Research are input-read-only. Mechanical research/coverage transitions are Director/controller work and use no ceremonial lease.

Every writer lease binds exact phase, role, worker, scope, base revision, allowed paths/symbols, exclusions, and status. A phase/role/owner/scope/base change requires a new lease. Transfer preserves revisions, findings, counters, decisions, coverage/docs, and scope history.

## Context capsule and telemetry

Every capsule-bearing role receives one controller-generated closed-schema capsule with exact role/phase/worker, approved plan/revisions, authority/evidence path+SHA+ID rows, assigned IDs, read or write boundaries, commands where allowed, output paths, stop condition, budget, observed metrics, and digest. Optional Research uses its separate bounded brief/result bundle; after acceptance, the exact bundle path/SHA and `brief_id` selector become Engineer evidence.

Capsules are phase-minimal. Final Review and QA omit predecessor human conclusions. Derived Documentation receives the closed QA manual-execution envelope, finalized coverage, current authority, and only other exact evidence admitted by its source-map contract; generic QA/probe reports are not authority. Read-only assignments keep writer allowlists empty: their inspection scope is derived from the assigned manifests, hashes, and selectors and never grants write permission. Missing, extra, stale, or cross-phase inputs fail closed.

Each budget has positive `max_authority_files`, `max_evidence_files`, `max_total_files`, `max_payload_bytes`, and `max_estimated_tokens`. Metrics count canonical capsule JSON plus direct authority/evidence file bytes; `estimated_tokens=ceil(payload_bytes/4)`. Skills/references, system instructions, history, tools, and project files opened on demand are excluded, so these metrics are never reported as total agent context.

The controller creates and validates the capsule before activation and revalidates it at completion. A separate capsule check is diagnostic for drift, not an obligatory post-create call. User authority is valid only through a prior immutable controller receipt; a capsule cannot create it.

## Controller-generated evidence

Workers return only their short semantic/verification artifacts. The controller inspects the actual checkout, validates scope and revisions, and generates change, diff, revision, coverage, documentation, credit, and handoff evidence. Workers never hand-author controller hashes, counts, or sealed envelopes.

A handoff digest seals the handoff object itself. Its change/diff/semantic path fields are navigation and audit metadata, not transitive byte authority. Downstream gates use current controller state and separately hash-bound capsule evidence; they never infer a referenced artifact SHA from the handoff digest.

Generated reports, logs, captures, capsules, coverage manifests, controller state, handoffs, and deferred backlog are excluded from product/support/evidence revision inputs. Product/support/evidence inventories and every fail-closed state transition remain controller-owned.
