# Stage handoff invariant

A stage starts only on explicit user activation or an assignment from an explicitly invoked Director whose task covers it. Readiness and proposed actions create no authority. Preserve delegated permissions, source/owner/model bindings and unrelated user work; an upstream correction returns through its parent, never a competing writer. A real authority uncertainty follows the applicable [authority contract](authority-contract.md) section.

## One owner and one current assignment

For an issued production assignment, bind its exact absolute `project_root`, owner/assignment IDs, scope, schema and output before file work. Resolve relative product/source/output paths and shell cwd under that root; preserve absolute runtime/SKILL locators separately. Missing/conflicting root requires bounded clarification. A historical URL, example or inherited cwd cannot choose another checkout. An in-scope greenfield file is to be created there, not a reason to choose another root.

The controller owns assignment identity, `worker_id`, access, checks and schema. Physical owner identity is separate: retain the same Engineer within a coherent slice and its related remediation; an accepted next-slice boundary follows [Working-set checkpoint and rotation](#working-set-checkpoint-and-rotation). Engineering, Review and QA are independent from each other. A new physical worker has no inherited conversation; retain only a same-owner fully consumed applicable baseline under [delivery continuity](delivery-contract.md#update-the-same-worker).

One worker holds at most one active write lease. Other actors do not mutate its checkout concurrently. Planned argv remain controller-owned. The issued assignment separately authorizes its exact terminal `output_path`, even for read-only Review/QA; this grants no other product, controller-state, history or Delivery write and no controller command. Actual filesystem/tool denials keep their existing capability route.

Requirements, Specification and Planning use their own stage artifacts/lifecycle, never production `active_assignment`/`complete`. A bounded caller task performs only its stated existing-role work. With `control_binding`, read [Worker return](control-return.md#worker-return); without it, retain the standalone public result.

### Event-specific instruction route

Read the named sections when their event applies, retaining unchanged instructions already consumed. These links expose the actual governing policy; neither this index nor an input digest substitutes for it.

| Event | Authoritative section |
| --- | --- |
| Assigned repair conditions | [Repair input](delivery-contract.md#repair-input) |
| Relevant current technical entries, or `requires_current_journal_read:true` | [Current journal](technical-decisions.md#current-journal) and the applicable row in [Role responsibilities](technical-decisions.md#role-responsibilities) |
| Unexpected error, incidental change, inconsistent technical instruction or blocker | [Resolve before escalating](technical-decisions.md#resolve-before-escalating), then [Current journal](technical-decisions.md#current-journal) for its actual resolution |
| Engineering/QA needs planned-machine feedback | [Active checks](execution-contract.md#check-inside-active-engineering-or-qa); no execution grant follows from reading it |
| Environment/tool interaction | [Environment actions](interaction-evidence.md#environment-actions) and [Permission and capability boundaries](interaction-evidence.md#permission-and-capability-boundaries) |
| Behavior/evidence or applicability assessment | [Evidence sufficiency](interaction-evidence.md#evidence-sufficiency); QA result construction additionally uses [Independent assessment](qa-acceptance-contract.md#independent-assessment-before-serialization) |
| Execution result or local argument/reader/serializer failure | [Preserve execution evidence](interaction-evidence.md#preserve-execution-evidence) and [Local tool recovery](interaction-evidence.md#local-tool-recovery) |
| Capturing execution proof or formatting the issued artifact | [Artifact and execution record I/O](execution-contract.md#artifact-and-execution-record-io); only authorized workflow outputs, no candidate/state mutation |
| Waiting for a bound answer, check relay, capability or user decision | [Await a bound response](control-return.md#await-a-bound-response), for every role |
| Terminal output or its returned correction | [Terminal artifact boundary](#terminal-artifact-boundary) plus the issued role's artifact contract |
| Actual context loss or justified idle turnover | [Working-set checkpoint and rotation](#working-set-checkpoint-and-rotation) |
| Suspected pipeline/controller defect | [Evidence, artifacts and incidents](#evidence-artifacts-and-incidents) |

## Working-set checkpoint and rotation

Retain the same Engineer through a slice's coherent work and related repairs. A genuinely accepted behavioral slice boundary normally starts the next slice with a fresh physical Engineer. Continue the previous Engineer across that boundary only when the approved plan's delivery/handoff instructions already bind a concrete continuity reason to those slices, or explicit applicable user authority supplies it. A matching role name, new assignment ID or inherited conversation is not that reason. The Director follows this source-bound choice and the native accepted-slice transition mechanically, not a judgment of token count or product semantics.

Transfer only after actual termination/quiescence, consumed prior output and no active write/check grant. Keep the controller-issued identity/accounting. A newly issued logical owner for the next accepted slice needs no extra `rotate-owner`; exceptional idle replacement within unfinished work uses that existing public route after a truthful result. Lost/truncated material or repeated reconstruction may justify such recovery, but telemetry is evidence, never a threshold. Do not manufacture PASS or impose file/time/token quotas to reach a boundary.

A factual checkpoint takes current authority paths/revisions/hashes, native phase/generation/action, assignment/owner and candidate binding from actual sources. Include changes after the last checked candidate, local versus externally published state, current applicable proof and its limits, open conditions/decisions, pending child/result/action and remaining authorized work. Mark unknown external state as unknown. Link the exact artifacts; do not copy history or restore old hashes/PASS as current. A new owner receives full current relevant input, stable tool/session locators and unresolved obligations, never another owner's retained baseline or session-local handles. Finishing a worker assignment does not end the Director's authorized full cycle.

## Terminal artifact boundary

Follow the issued `assignment.artifact_schema`, including required/allowed keys and shapes. Omit empty optional fields. `blocked` needs `blocker` and `required_action`; `questions` is only for reversible, non-verdict-changing technical clarification on pass. Use [file-backed artifact I/O](execution-contract.md#artifact-and-execution-record-io) for structural validation and UTF-8 serialization from an authorized staging file. Native `complete` retains its guards; the Director checks identity/lifecycle, not a duplicate schema validator. Formatting validation never supplies missing observations or semantic acceptance.

Finish all intended writes and required current-candidate checks, then write the exact terminal artifact as the last owned write and stop activity. Do not edit the product, run another check or delete the output to reopen work. A returned artifact-format correction permits truthful correction of that output only; substantive missing work or a late product issue follows its existing role/control route. No fabricated evidence/PASS and no replacement owner for formatting. A later assignment supplies fresh bindings.

An informative check result is not terminal: the active grant's lifecycle and required pauses are governed by [Active checks](execution-contract.md#check-inside-active-engineering-or-qa), and event wrapping by [Worker return](control-return.md#worker-return). Host completion alone grants neither native completion nor phase PASS. The Director must account for live children and consume terminal results through [Director lifecycle](director-runtime.md); a status question is steering, not abandonment.

## Evidence, artifacts and incidents

Use the named evidence and artifact sections above. Slicer caller records still contain only `id`, `allowed_paths`, `planned_commands`; sealed read access is controller-owned.

Preserve factual public error categories: stale action, malformed artifact, product failure, missing capability, authority/scope conflict and runtime incident. A suspected runtime/invariant defect pauses affected product transitions. Workers must not edit, patch, bypass or replace the pipeline under product-only authority. Follow [maintenance observation](maintenance-observation.md) only under applicable separate authority, including a valid prior delegation; otherwise return the real blocker. A speculative incident grants no retry or framework repair.
