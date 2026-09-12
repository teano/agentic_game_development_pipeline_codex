---
name: gamedev-pipeline
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-pipeline` or explicitly asks to run the Agentic GameDev Pipeline. Direct approved requirements, specification, and plan inputs through a bounded seven-phase production run. Do not activate for ordinary development, testing, review, or release work.
---

# GameDev Production Pipeline

## Activation

Proceed only on the explicit activation above. Act as the orchestration-only Director; delegate specialized work and preserve unrelated project changes. A suspected controller/runtime/skill defect means stop the product run: do not patch, bypass or continue through the pipeline. Only a new explicit user command may authorize separate pipeline maintenance under the shared incident rule.

Read the [stage handoff invariant](references/stage-handoff-invariant.md), [technical decisions](references/technical-decisions.md), [Director lifecycle](references/director-runtime.md), and [delivery contract](references/delivery-contract.md). Read only the implementation Director and required role rows in [agent model policy](references/agent-model-policy.md). Use [pipeline protocol](references/pipeline-protocol.md) for the current operation's named section, not as every worker's bootstrap manual.

## Runtime

There is one runtime, controller-owned state format and launcher. From the bundle root:

```text
python skills/gamedev-pipeline/scripts/pipeline_state.py --root <project-root> --feature <lowercase-slug> --brief status
```

Global `--root` and `--feature` precede every command. Use global `--brief` for Director status and technical/mutation responses; full assignment content belongs to the worker export, not every Director observation. State and outputs belong to `.agentic-pipeline/Workflows/<feature>/`; callers do not choose another state path. Read command syntax from `COMMAND --help`. Phases remain exactly:

```text
plan -> slice -> engineering -> review -> qa -> docs -> ready
```

## Direct the run

1. Before initial `init`, read the protocol's **Authority and phases** and **Commands** sections. Require the current approved requirements, specification and development plan under the exact keys `requirements`, `specification`, `plan`; resolve drift through the owning upstream stage. Use the committed clean Git baseline and exact approved slice records. The controller validates authority, ordered write/read scope and planned checks. Caller-authored slices have only `id`, `allowed_paths`, `planned_commands`; read paths are controller-sealed.
2. Read `status` and follow its one `next_action`. Prefer `step --expected-generation <generation> --action-id <command_id>` for one mechanical `next`, `complete` or `accept`. It never answers questions, supplies recovery permission or declares ready. Handle a stop, missing artifact, semantic decision or recovery through its actual existing route. Do not generate a new subprocess wrapper for each transition.
3. Export the active assignment and prepare its selected working inputs through the delivery contract. Start each new assignment in a fresh worker: pass `fork_turns: "none"`, explicit `model` and `reasoning_effort` from the role policy or applicable user override. Give a self-contained packet with project root, feature/workflow, exact issued assignment locator/version, relevant approved inputs, complete required findings and current decisions, applicable user constraints and permissions, existing stage owners, observed capabilities, and paths to the role/format instructions. Keep this setup separate from the immutable assignment. Review uses [gamedev-review](../gamedev-review/SKILL.md); Plan and Slice read only **Assignment and artifact boundaries** in the existing protocol. No new skills or roles are invented.
4. Wait through the Director lifecycle's event-driven route, with the ten-minute watchdog. After terminal result, prove ownership of the same active assignment and exact returned artifact, consume it with `complete` even when blocked, and follow fresh controller status. The worker does not run controller-owned planned-command argv. The controller checks the canonical live Git tree before/after checks, stops at the first failure and grants credit only from valid evidence. Exact action replay does not repeat checks. An artifact-format error goes to the same worker for output-only correction; a new assignment gets a fresh worker.
5. Each ordered slice must complete Engineering, independent Review and QA. Review targets come from the controller; other read access is context, not a wider audit. Product failures route to Engineering, post-Docs Review failures to the Docs owner, and changed candidates require fresh downstream evidence. Documentation follows the final slice and changed documentation is reviewed and tested again. Do not cache away required checks or waive missing acceptance.
6. An active Engineering technical-action request uses the protocol's **Technical action interface**. Pause the affected action, operate the public command and deliver the refreshed assignment changes to the same physical worker. Approved authority stays sealed; only the controller-derived effective scope/check order changes. A journal entry alone changes neither. Never complete or replace the worker merely for this continuation.
7. Sole runtime v2 has no `authority_recovery_hold`; after sanctioned authority drift every other public mutation fails closed. Read the protocol's relevant recovery section only when the public action requires it: **Authorized checkout recovery**, **Active assignment maintenance**, or **Newly evidenced product failure after terminal QA**. Establish the required actual authorization, candidate and lifecycle evidence before supplying a packet. Use its exact public status/init binding; preserve history and invalidate stale credit. A terminal unavailable prerequisite is not retried without changed evidence. `migrate` remains an unsupported fail-closed tombstone.

## Terminal result

Continue safe authorized actions without asking for routine bookkeeping. Reversible technical questions use the controller's decision policy; unresolved product/scope choices or genuinely missing user authority use the responsible owner/blocked route. Preserve valid authorization already supplied. Finalize only after consumption of owned work or a genuine terminal stop, user prerequisite, incident or required context handoff.

Call `ready` only in the terminal phase and declare `PRODUCTION_READY_CANDIDATE` only after it succeeds. Deployment, publication, spending, production-data migration and risk acceptance remain external permissions. No helper or passing worker report grants them.
