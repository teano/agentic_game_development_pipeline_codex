---
name: gamedev-pipeline
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-pipeline` or explicitly asks to run the Agentic GameDev Pipeline. Direct approved requirements, specification, and plan inputs through a bounded seven-phase production run. Do not activate for ordinary development, testing, review, or release work.
---

# GameDev Production Pipeline

## Activation

Proceed only on the explicit activation described above. Act as the orchestration-only Director: operate the controller and delegate specialized work, but do not perform a worker phase in the Director context.

If a controller, runtime, skill, protocol, or state-transition defect is suspected, stop the product run immediately and follow the stage-handoff invariant's Controller incident stop. Report the problem in bounded redacted detail and do not modify, patch, bypass, or continue through the pipeline. Only a new explicit user command may authorize a separate pipeline-maintenance task.

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

The commands are exactly `init`, `status`, `next`, `complete`, `answer`, `accept`, `migrate`, and `ready`.

## Direct the run

1. Before `init`, require current approved requirements, specification, and development plan files. Pass them under the exact keys `requirements`, `specification`, and `plan`. Also pass one or more ordered JSON slice records with exactly `id`, `allowed_paths`, and `planned_commands`; callers never provide `read_paths`. The controller parses each approved plan slice's Context Capsule `authority_paths` plus `evidence_paths`, validates and deduplicates them, and stores the resulting fourth `read_paths` field. The run ID is one compact ASCII identifier, not a path: it starts and ends alphanumeric, contains at most 64 letters, digits, dots, underscores, or hyphens, and contains no separator.
2. Read `status` and execute its single `next_action`. It derives the command ID, expected generation, assignment identity, task, paths, checks, Review target, and recovery reason. `next` may omit assignment ID, worker, and task; if supplied for compatibility, all three must be byte-equal to the controller defaults. An exact lost-response replay is checked against its recorded generation before current-generation defaults, so both the omitted and exact explicit identity forms are byte-noops. Every phase's access and checks are controller-derived again when `next` executes, so omitted or caller-authored scope cannot narrow or broaden the worker packet. Engineering, Review, and QA can read authority plus each completed/current slice's `allowed_paths` and sealed `read_paths`; future slices remain excluded. A post-Docs Review additionally reads its exact changed Docs target paths. For Review, all non-target read access is evidence context only: `context.review_target.required_scope` equals the current slice's `allowed_paths` and `candidate_changes` lists exact accepted Engineering diff paths, or exact changed Docs paths after Documentation. Introduced-defect and excess-complexity findings bind to `candidate_changes`; outside them only missing mandatory implementation or a proven direct regression is eligible. Engineering can write only the current slice's `allowed_paths`. Planning, slicing, Review, and QA are read-only.
3. Have the worker follow `active_assignment.artifact_schema` exactly and write only that semantic JSON to `active_assignment.output_path`; it must not inspect runtime code to guess the shape, run checks absent from the assignment, or rerun the assigned planned-command argv itself. A worker must not start or control an interactive, background, long-lived, callback-driven, service, or already-running external mutator. Git is the sole candidate source of truth. Initial `init` requires the exact Git root, a committed clean baseline, and tracked authority files. The controller records tree OIDs and exact tracked plus new non-ignored changed paths; ignored editor/cache/log files are outside pipeline control and receive no engine-specific rules. Each planned command runs synchronously under the controller against the canonical live checkout and MUST leave its Git candidate tree unchanged. The controller compares the tree before and after every command, fails closed before later commands, and never copies or rolls back candidate bytes. Changes to `.gitignore`, `.gitattributes`, or `.gitmodules` require fresh `init`. Commands stop at the first non-zero result; only the exact all-pass list or the exact prefix ending in that first failure is valid evidence. A Slicer may return revised three-key slice records derived from the current approved plan; the controller rejects caller-authored `read_paths`, re-seals them from the plan, and adopts the records on `accept`. Run `complete` with no artifact override, or pass only that exact path; the controller independently reads it and verifies authority, Git scope, runtime digest, and planned checks. A non-zero check is stored with digests plus a redacted, path-normalized, byte-bounded stderr excerpt. A blocked artifact requires non-empty `blocker` and `required_action`; after artifact/live-tree/CAS preflight it runs no planned commands, stores `commands: []`, grants no candidate or phase credit, and terminates the run with `user_input_required=true`. Archive that state and run a fresh `init` only after the prerequisite changes. Exact replay never reruns checks.
4. Use `accept` only after a passing artifact with no unresolved question or blocked outcome. For a question, the Director follows `next_action.decision_policy`, records the safest reversible authority-consistent assumption, and continues without user bookkeeping. A Review/QA `fail` atomically invalidates engineering and downstream credit and routes directly to writable Engineering with only the bound candidate and deterministic finding/check evidence; no blocker, required action, or caller-authored remediation prose is copied. A failed Engineering/controller attempt remains in Engineering as non-credit candidate evidence.
5. Every ordered slice completes Engineering, fresh Review, and fresh QA before the next slice starts. Documentation begins only after the final slice. A documentation change returns to independent Review and QA.
6. Sole runtime v2 has no `authority_recovery_hold`. When a sanctioned upstream controller changes approved authority, execute the exact `init` returned by `status.next_action`; every other public mutation fails closed. Status observes authority and the live Git candidate tree under the state lock; the action ID binds the exact observed authority paths/bytes, tree OID, and retained slices. `init` restarts at planning, clears live credit, and preserves audit history plus a non-credit Git-tree baseline. If work is active, the controller first proves changed paths stay within the old assignment and archives the interruption; foreign changes return `checkout_recovery_required`. The ensuing Slicer must cover interrupted Engineering paths.
7. Use `ready` only in the terminal phase. It verifies the live Git candidate tree, fixed runtime digest, and proof that every approved slice completed before declaring readiness.

`migrate` is a retained fail-closed tombstone. Schema-10 migration is unsupported by `git-tree-v1`; archive legacy state/findings and run fresh Plan/`init`. It never imports, reconstructs, or resumes legacy state.

## Terminal result

Continue safe in-scope transitions without asking the user. Ask only for an unresolved product or scope choice, credentials, spending, publication, irreversible action, or another inherently user-owned step.

Declare `PRODUCTION_READY_CANDIDATE` only after `ready` succeeds. Deployment, publication, store submission, spending, migration of production data, and risk acceptance remain external.
