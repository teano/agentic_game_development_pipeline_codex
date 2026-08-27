---
name: gamedev-pipeline
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-pipeline` or explicitly asks to run or resume the Agentic GameDev Pipeline. Direct approved requirements, specification, and plan inputs through a bounded seven-phase production run. Do not activate for ordinary development, testing, review, or release work.
---

# GameDev Production Pipeline

## Activation

Proceed only on the explicit activation described above. Act as the orchestration-only Director: operate the controller and delegate specialized work, but do not perform a worker phase in the Director context.

Read the shared [stage handoff invariant](references/stage-handoff-invariant.md) and [pipeline-protocol.md](references/pipeline-protocol.md) before starting. Give each worker only its task, relevant approved context, read/write boundary, checks to satisfy, and linked semantic-artifact contract. Use a fresh worker session for every assignment and preserve unrelated project changes.

## Runtime

There is one runtime and one state file format. The launcher is `scripts/pipeline_state.py`, which directly runs `pipeline_v2.cli`; it contains no legacy handlers. From the bundle root use:

```text
python skills/gamedev-pipeline/scripts/pipeline_state.py --help
```

From this skill directory use:

```text
python scripts/pipeline_state.py --help
```

Place the optional global `--state PATH` before the command. The default is `.agentic-pipeline-v2/state.json` under the current directory. A custom state filename is allowed only as a direct `.json` child of the exact project root's `.agentic-pipeline-v2` directory; external, nested, symlinked, or reparse-point state paths fail before mutation. Read the exact syntax for the current operation from `COMMAND --help`.

The phases are exactly:

```text
plan -> slice -> engineering -> review -> qa -> docs -> ready
```

The commands are exactly `init`, `status`, `next`, `complete`, `answer`, `resume`, `accept`, `migrate`, and `ready`.

## Direct the run

1. Before `init`, require current approved requirements, specification, and development plan files. Pass them under the exact keys `requirements`, `specification`, and `plan`. Also pass one or more ordered JSON slice records with exactly `id`, `allowed_paths`, and `planned_commands`; callers never provide `read_paths`. The controller parses each approved plan slice's Context Capsule `authority_paths` plus `evidence_paths`, validates and deduplicates them, and stores the resulting fourth `read_paths` field. The run ID is one compact ASCII identifier, not a path: it starts and ends alphanumeric, contains at most 64 letters, digits, dots, underscores, or hyphens, and contains no separator.
2. Read `status` and execute its single `next_action`. It derives the command ID, expected generation, assignment identity, task, paths, checks, and recovery reason. `next` may omit assignment ID, worker, and task; if supplied for compatibility, all three must be byte-equal to the controller defaults. An exact lost-response replay is checked against its recorded generation before current-generation defaults, so both the omitted and exact explicit identity forms are byte-noops. Every phase's access and checks are controller-derived again when `next` executes, so omitted or caller-authored scope cannot narrow or broaden the worker packet. Engineering, Review, and QA can read authority plus each completed/current slice's `allowed_paths` and sealed `read_paths`; future slices remain excluded. Engineering can write only the current slice's `allowed_paths`. Planning, slicing, Review, and QA are read-only.
3. Have the worker follow `active_assignment.artifact_schema` exactly and write only that semantic JSON to `active_assignment.output_path`; it must not inspect runtime code to guess the shape, run checks absent from the assignment, or rerun the assigned planned-command argv itself. On `complete`, the controller runs each read-only assignment's planned commands only against the canonical live checkout under a strict non-mutation contract. Those commands MUST NOT change project or candidate bytes; the controller redirects temporary and cache data to bounded excluded scratch and cleans it, including Windows read-only entries, without traversing links. Immediately after each planned process tree ends, the controller inventories and diffs the candidate before starting the next command. Drift fails closed before any later command and without a state commit; there is no automatic rollback, so the forbidden live mutation remains dirty for recovery. Commands stop at the first non-zero result; only the exact all-pass list or the exact prefix ending in that first failure is valid evidence. The controller MUST NOT create a full or partial project/candidate copy for read-only checks by materialization, clone, snapshot, worktree, hard-link tree, reflink, block clone, or copy-on-write checkout. A Slicer may return revised three-key slice records derived from the current approved plan; the controller rejects caller-authored `read_paths`, re-seals them from the plan, and adopts the records on `accept`. Run `complete` with no artifact override, or pass only that exact path; the controller independently reads it and verifies authority, checkout scope, and planned checks. A non-zero check is stored with digests plus a redacted, path-normalized, byte-bounded stderr excerpt. Explicit worker `fail`/`blocked` keeps the ordinary worker-result gate; worker `pass` remains unchanged but receives a separate controller-result gate, no candidate or phase credit, and a fresh retry after `resume`. Exact replay never reruns checks.
4. Use `accept` only after a passing artifact with no unresolved question or blocked outcome. For a question, the Director follows `next_action.decision_policy`, records the safest reversible authority-consistent assumption, and continues without user bookkeeping. After a Review/QA `fail`, `resume` preserves the gate and candidate base, invalidates engineering and downstream credit, and routes to writable engineering remediation followed by fresh Review and QA.
5. Every ordered slice completes Engineering, fresh Review, and fresh QA before the next slice starts. Documentation begins only after the final slice. A documentation change returns to independent Review and QA.
6. When a sanctioned upstream controller changes approved authority, execute the exact `init` returned by `status.next_action`. Status observes authority and the whole checkout under the state lock; the action ID binds the exact observed authority paths/bytes and retained slices, and execution revalidates that binding under the same lock. Sole runtime v2 has no `authority_recovery_hold`: after byte drift, every other public mutation fails closed, and every replay fails closed, until this reconfiguration. `init` restarts at planning, clears live credit, and preserves the prior candidate/history plus one non-credit checkout baseline as audit context. If work is active, the controller first proves its checkout diff is within the old assignment and archives the interruption; pre-existing foreign changes make status return the non-mutating terminal recovery fact `checkout_recovery_required` instead of an unusable `init`. The ensuing Slicer semantic artifact supplies any revised scope and must cover interrupted Engineering paths.
7. Use `ready` only in the terminal phase. It verifies the live checkout and proof that every approved slice completed before declaring readiness.

`migrate` is a one-way schema-10 data import into an empty v2 state path. Supply fresh v2 slice records. Migration canonicalizes the existing physical project root and requires its derived run ID to satisfy the same safe identifier contract before state mutation. It normally starts at `plan`; a legacy candidate is audit/base context only and receives no v2 Engineering, Review, or QA credit. One exact compatibility case preserves already-completed Plan/Slice credit: a first-slice `scope_expansion_hold` in implementation with an active Engineer lease whose lease/worker IDs are concrete, its immutable snapshot and owner-bound passed pre-edit proof, no prior Engineer run or completion marker, and stored ordered slice IDs, active slice, plan digest, every slice's approved editable paths, lease paths, and hold candidate paths matching the supplied v2 slices. That case starts at `engineering`, seals Plan/Slice credit against the live checkout, retains the legacy lease/hold only in the closed migration audit, and derives a fresh v2 worker. A missing snapshot, malformed identity, or any other mismatch restarts at `plan` without trusted legacy candidate credit. The controller seals the live checkout during migration, and status, mutation, and exact migration replay reject later drift. It never calls a legacy handler or resumes a copied worker assignment.

## Terminal result

Continue safe in-scope transitions without asking the user. Ask only for an unresolved product or scope choice, credentials, spending, publication, irreversible action, or another inherently user-owned step.

Declare `PRODUCTION_READY_CANDIDATE` only after `ready` succeeds. Deployment, publication, store submission, spending, migration of production data, and risk acceptance remain external.
