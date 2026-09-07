# GameDev agent model policy

Use these explicit defaults for a new stage session or an already authorized fresh role dispatch. An explicit user model or effort choice takes precedence within its stated scope, including a higher requested setting. Preserve applicable owner/model constraints from the parent. A user's Director selection alone does not select every child model. These are agent execution settings, not game requirements, approved product authority, or controller artifact fields.

## Stage sessions

The user selects these settings when starting the corresponding task. A skill cannot change the model or effort of its current Director through prose. Keep an existing task's actual selection; do not restart it just to apply a default.

| User-started stage | Model | Effort |
| --- | --- | --- |
| `$gamedev-requirements` | `gpt-6-astra` | `low` |
| `$gamedev-specification` | `gpt-6-astra` | `low` |
| `$gamedev-development-plan` | `gpt-6-astra` | `low` |
| `$gamedev-pipeline` implementation Director | `gpt-5.6-terra` | `xhigh` |

When an invoked Director is authorized to delegate an upstream stage and no owner is already assigned, use that stage's row for its new Director. Return corrections to an existing stage owner through the parent as required by the handoff invariant.

## Delegated roles

Choose the row for the actual assigned work. Rows do not create roles, activate optional work, or grant delegation authority.

| Existing role | Model | Effort | Workload |
| --- | --- | --- | --- |
| Requirements bounded research agent | `gpt-5.6-terra` | `high` | Ground questions and constraints in the current project and stack. |
| Requirements semantic review agent | `gpt-6-astra` | `low` | Check confirmed meaning, contradictions and mandatory coverage. |
| Technical Spec Architect | `gpt-6-astra` | `low` | Own semantic assessment, minimal design and correction decisions. |
| Specification Generator/helper | `gpt-6-astra` | `low` | Generate or correct technical specification text from exact authority. |
| Specification Proofreader | `gpt-6-astra` | `low` | Independently compare exact specification bytes with approved scope. |
| Specification helper semantic review or post-fix verification worker, when its existing route delegates one | `gpt-6-astra` | `low` | Independently check helper output against the exact request; use the Proofreader setting. |
| Specification repository-research helper | `gpt-5.6-terra` | `high` | Answer a bounded project-evidence question. |
| Development Plan Planning Analyst | `gpt-6-astra` | `low` | Analyze coupling, seams, dependencies, context budgets and coverage. |
| Runtime Plan (`planner`) | `gpt-6-astra` | `low` | Confirm approved intent and unresolved product decisions. |
| Runtime Slice (`slicer`) | `gpt-5.6-terra` | `high` | Confirm bounded approved scope and retained-path coverage. |
| Engineering (`engineer`) | `gpt-5.6-terra` | `xhigh` | Implement the assigned game slice and coupled tests. |
| Review (`reviewer`), including post-Docs Review | `gpt-6-astra` | `low` | Independently inspect mandatory behavior, supported paths and sufficient complexity. |
| QA (`qa`) | `gpt-5.6-terra` | `high` | Execute assigned player/editor acceptance and report bound evidence. |
| Docs (`documentation_finisher`) | `gpt-5.6-terra` | `medium` | Synchronize bounded documentation with approved and verified sources. |
| Explicit standalone Coverage Advisory | `gpt-5.6-terra` | `high` | Inspect supplied source-to-identity mappings; it is not a runtime assignment. |

`ready` is a terminal runtime phase without a worker. Research briefs are context for existing roles, not automatically dispatched researchers. The policy adds no Decision Recorder, coverage executor, or other retired role.

## Dispatch and continuation

For every new collaboration worker, supply `fork_turns: "none"`, `model`, and `reasoning_effort` as actual `spawn_agent` arguments, using the effective row or explicit override. For example, a default Engineering dispatch contains:

```json
{"task_name":"engineering_slice","fork_turns":"none","model":"gpt-5.6-terra","reasoning_effort":"xhigh","message":"<self-contained authorized Engineering packet>"}
```

The name and message above are placeholders for the actual assignment. Include effective settings and their override scope in the bounded handoff, outside any immutable helper request or runtime assignment payload. Do not modify controller-owned IDs, semantic tasks, schemas, state or approval hashes to carry model settings. A full-history fork inherits the parent and cannot apply explicit model overrides.

When an explicitly user-authorized Codex task creation uses app tools, pass `model` only if the user explicitly selected that model for the task; otherwise omit it so the task uses the user's configured default, as the tool requires. Pass `thinking` only for an applicable explicit user effort choice; otherwise omit it. The stage-session recommendations above do not themselves constitute user selections. Do not create visible tasks for internal stage workers. For a message to an existing task, preserve its current settings unless the user explicitly requests a change; a skill cannot switch its current Director through prose.

`followup_task` and `send_message` do not switch an existing collaboration agent's model or effort. Keep persistent owners and same-worker artifact-format corrections on their existing selection. Apply defaults again only at a fresh assignment or turnover already required by that role's lifecycle. Preserve the effective settings and explicit override scope in the existing checkpoint. Never replace an active worker, create a duplicate owner, restart completed work or reinitialize controller state merely to apply this policy.

Failures, blockers, context pressure, and difficult findings do not automatically raise effort or select a more expensive model. Follow the existing recovery or upstream route with the applicable role setting. If a requested model/effort or explicit selection mechanism is unavailable, disclose the exact limitation before the affected dispatch; do not silently substitute, inherit, or claim that a prompt changed the model. Ask for a different selection only when it is needed to continue that dispatch.
