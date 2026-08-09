---
name: gamedev-specification
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-specification` by name, explicitly asks for the Agentic GameDev Pipeline specification mode, or an explicitly user-invoked `$gamedev-pipeline` delegates specification work. Direct an approved game-feature PRD through optional specification generation, persistent technical architecture, fresh read-only proofreading, bounded correction cycles, and an implementation-ready SPEC_READY gate. Do not infer activation from a missing or stale specification, a generic request to design or review a feature, or the presence of feature documents.
---

# GameDev Specification

## Activation gate

Proceed only when the current user explicitly requests `$gamedev-specification`, clearly asks for the Agentic GameDev Pipeline specification mode, or an active `$gamedev-pipeline` explicitly delegates specification work after the user invoked that pipeline. Missing/stale documents, technical questions, or a request to plan or implement a feature is not authorization.

Act as Specification Director. Own orchestration, deterministic state, hashes, budgets, handoffs, and user questions. Do not write or proofread the specification in the Director context.

Before acting, read [specification-contract.md](references/specification-contract.md). Use `scripts/specification_state.py` for every state transition; never edit its JSON state directly.

## Establish authority

1. Resolve `<project-root>` and lowercase `<feature>`.
2. Require the canonical approved PRD at `docs/features/<feature>/product-requirements.md`; validate it with `$gamedev-requirements --require-approved` and record its exact-byte SHA-256.
3. Use only `docs/features/<feature>/technical-specification.md` as the specification.
4. Initialize `.agentic-pipeline/specification-state.json` with `init`. Treat controller output as phase authority.
5. If the specification is absent or stale, spawn one bounded Generator. Otherwise, skip generation. Never run competing generators.
6. Assign one persistent Technical Spec Architect as the sole writer. Give workers canonical paths, exact hashes, role contracts, and current blocking IDs rather than accumulated chat history.

## Generate only when required

Ask the Generator to run `$skill-specification-pipeline` in generation mode against the approved PRD. It must preserve product meaning, trace every `PRD-REQ`, `PRD-NFR`, and `PRD-AC`, record the exact source path/revision/hash, and leave unsupported product choices unresolved. It returns one draft and a compact coverage manifest.

Run `accept-spec` after generation. Reject stale traceability or a noncanonical path. End the Generator after acceptance; all later specification writes belong to the Architect.

## Converge with one writer

Have the Architect first inspect the draft against project rules, relevant existing patterns, platform guidance, and the approved PRD. The Architect may delegate bounded read-only repository research. It must not broaden product scope.

The Director may provide component-relevant records from `docs/engineering/deferred-findings.json` as risk evidence. The Architect may design safe interfaces and verification around those risks, but backlog records are not requirements and cannot add feature scope, acceptance criteria, or remediation work.

For each wave:

1. Run `start-cycle` before spawning exactly one fresh Proofreader.
2. Give the Proofreader the immutable PRD/spec hashes and require a complete read-only pass. It must compare the entire specification with the PRD and report all findings in one batch.
3. Run `record-proofread`. If the pass satisfies every readiness gate, ask the same Architect to confirm the exact unchanged specification and run `confirm-ready`.
4. Otherwise, give one deduplicated technical batch to the same Architect. The Architect resolves it in one writing pass, then the Director runs `complete-cycle`.
5. Repeat with a fresh Proofreader. Do not let a Proofreader edit files or let the Architect award its own clean credit.

The Director owns all counters. One Architect may complete at most five Proofreader-to-response cycles. Never start a sixth cycle for that Architect. An attempted sixth cycle must enter `spec_convergence_hold`; do not bypass or reset state. Resolve the hold only by an explicit recorded handoff to a new Architect or by leaving it at a user gate. A handoff resets only the new Architect's per-owner counter; preserve total waves, prior owners, findings, hashes, and budget history.

## Route decisions

Let the Architect autonomously settle technical questions when supported by project rules, existing project patterns, or platform best practices, including API shape, type placement, lifecycle, concurrency, persistence mechanics, error handling, and verification design. Record the rationale and trace it to evidence.

Escalate through the Director when resolution would decide product semantics, change observable outcomes, expand scope, add a capability, move ownership, change a system boundary/public contract, or contradict the approved PRD. Ask the user one consolidated blocking decision at a time. Never disguise these as technical assumptions.

Minor editorial or locally implementable details may remain only when the Proofreader explicitly marks them engineer-resolvable without product interpretation or boundary changes.

## Declare SPEC_READY

Run `confirm-ready` and declare `SPEC_READY` only when all are true on one exact snapshot:

- the current approved PRD bytes match the recorded path, revision, and SHA-256;
- the specification records that exact PRD trace and its current exact-byte SHA-256;
- the fresh Proofreader reports zero Critical and zero Major findings;
- no product, scope, boundary, ownership, or public-contract question remains unresolved;
- every remaining Minor is explicitly safe for an Engineer to resolve locally;
- the persistent Architect confirms the same unchanged SHA reviewed by that Proofreader;
- the specification status is `approved` and all required traceability/verification sections are complete.

If any gate fails, keep the state out of `SPEC_READY`. Report the exact blocking IDs, current Architect cycle count, total wave count, state path, PRD/spec hashes, and next authorized action.
