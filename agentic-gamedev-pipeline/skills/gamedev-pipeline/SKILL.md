---
name: gamedev-pipeline
description: Explicit-invocation only. Use for `$gamedev-pipeline` or an explicitly delegated implementation stage. Implement a game feature from current approved PRD, specification and plan through bounded writers, independent checks, repairs and final integrated behavior.
---

# GameDev Implementation

Deliver the authorized feature in the actual project. Act as its orchestrator: retain original obligations, delegate product changes to a writer, obtain independent observations, return findings for repair and continue through the plan to integrated acceptance. A completed agent task or green test suite alone does not complete implementation.

## Establish authority and working facts

At entry, use the shared [project, artifact and approval procedure](references/artifacts-and-approval.md) to locate the implementation checkout and feature, find the canonical PRD/specification/plan, and verify their current versions, source bindings and approvals together. Resolve execution permissions before changes. On resumption, locate the existing implementation note and candidate evidence for this feature in the assigned checkout and reconcile them with current work. Preserve canonical paths/IDs and do not edit approved inputs for implementation convenience.

This skill owns implementation only. Missing, stale or contradictory upstream inputs need a concrete handoff to their [Requirements](../gamedev-requirements/SKILL.md), [Specification](../gamedev-specification/SKILL.md) or [Planning](../gamedev-development-plan/SKILL.md) owner, identifying the affected document, obligation and needed decision or correction. Return that issue to an existing full-cycle parent when present; use [GameDev Orchestrator](../gamedev-orchestrator/SKILL.md) for a separately requested full cycle. Do not conduct Requirements, author upstream documents or activate upstream stages from an implementation invocation. Preserve useful WIP and continue independent authorized implementation when the issue permits it.

Read plan ordering/boundaries and inspect the actual engine/toolchain, active packages and integrations, project entry points and build/run/check methods. Check the plan's concrete prerequisites against this environment. Try an appropriate permitted baseline early so environment failures become actionable work. Choose tools/stack skills from the real operation. Select the model and effort for each new Engineer, checker or specialist using the [GameDev model settings](references/agent-model-policy.md). Preserve required methods and run-specific limits.

Build a compact coverage view of all original requirements, acceptance criteria, constraints and documentation duties in the authorized scope. Include specification obligations even if the plan missed a convenient row. Link source IDs/anchors to relevant specification, planned unit(s), current implementation and evidence or outstanding work. Give workers actual relevant criterion text and locators for dependencies; a list of IDs is insufficient. Retain out-of-scope observations explicitly unverified rather than silently removing them or claiming complete product acceptance.

## Own the development loop

The implementation orchestrator owns routing, evidence decisions and escalation. Give the relevant engineer or independent checker the concrete diagnostic question alongside its existing assignment. That worker inspects the source data, runs the product or performs the detailed reproduction. The orchestrator reviews the result and its primary evidence. Its own routine checks of artifact identity, authority, candidate state and handoffs remain part of coordination.

Use real subagents for bounded product work and retain the root orchestrator across slices. Every development slice or coherent implementation unit of the approved plan requires newly created Engineer and independent QA/checker agent instances, regardless of its name. Any separate reviewer or specialist needed for that unit must also be new to it. Do not reuse earlier-unit workers. Preserve the approved plan's unit boundaries, including unstarted units; do not merge or rename units to bypass fresh teams because files are coupled, scope is small or reuse is convenient. Explicitly user-authorized plan changes remain valid. A new assignment/follow-up, renamed role or compaction in an existing agent does not create a new agent.

Start new workers without inherited root or earlier-slice transcripts (`fork_turns="none"` when using `spawn_agent`). Supply the shared handoff locators for the assigned checkout, feature, relevant artifacts and evidence area, with original criteria, current candidate/dependencies, permitted paths, boundaries, findings and ownership. Keep one writer for a shared checkout and one operator for a mutable runtime; the orchestrator owns coordination and the current note. Before transferring ownership, confirm previous writes and owned jobs have stopped or completed and mutable runtime operations are quiescent. Preserve the runtime instance and code/WIP, explicitly transferring ownership; never let two authors mutate the same scene. Independent reading may run in parallel without interference. Add a specialist only for a concrete need.

For each development slice or coherent implementation unit of the approved plan:

1. Give the slice's new implementer [Engineer instructions](../gamedev-engineer/SKILL.md), the concrete outcome, original criteria/specification passages, current integrated state, allowed resources, exclusions, checks and relevant findings. It implements, integrates and exercises the increment. Permitted technical setup and missing in-scope work belong to the task; routine engineering does not require another product plan or approval.
2. Consume its actual result/evidence, confirm writer quiescence and inspect the current candidate identity. Delegate [independent checking](../gamedev-qa/SKILL.md) to the slice's new checker, who did not author the candidate. Supply raw criteria and the actual product, without an intended verdict. Author checks are evidence to assess. A checker may combine review and runtime QA; separate them for a concrete risk.
3. Return valid findings for repair with their criterion, reproduction, expected/observed result and affected candidate. The writer fixes the cause and integrations; the checker repeats affected or explicitly required observations on the repaired state. Preserve unaffected valid evidence. Optional preferences do not become blockers without a requirement, convention or concrete defect.
4. Accept the slice only after required behavior/checks are established, update coverage and advance with a fresh team for the next slice. Keep same-slice debugging and QA repairs with its current team. Replace a lost or incapable worker after quiescence and a factual handoff, preserving WIP and the rest of the plan.

For a changed boundary, pass the applicable project rules and
[architecture criteria](references/architecture-review.md) to the writer and
checker, with the agreed owner, dependency direction, integration and paths.
Use the existing slice check on the first integrated route before dependent
work repeats it. Recheck affected boundaries on the final candidate.

If an obligation lacks planned work, retain it and organize necessary technical work within the actual permissions. Refine tasks without changing product scope. A real contradiction or required boundary change needs its responsible decision; record its actual source and never infer one from silence or a workaround.

Give each acceptance-only unit, including final integrated acceptance, a newly created independent checker who took no part in earlier slices. Do not create an idle Engineer; if repair is needed, assign a new author to that acceptance/repair unit and have its checker repeat affected verification. Final acceptance observes the whole integrated candidate, including the required user flow and cross-slice seams; slice PASS results cannot substitute for it. If the last planned unit already performs this acceptance on the current candidate, it supplies the final check without another final QA or duplicate unchanged observations. For games, observe real input, gameplay consequences and the specified outcome in the permitted runtime. Screenshots, compilation and unit tests support this evidence but cannot replace required interaction.

## Final architecture review

Once the whole feature is integrated and writers are quiescent, use one dedicated [final architecture reviewer](../gamedev-review/SKILL.md#final-architecture-review) for the feature. Reuse its recorded handle if a planned final unit or an earlier attempt already assigned it. Otherwise create it once using the final architecture reviewer role in the [model policy](references/agent-model-policy.md). This agent must be independent of the authors, slice reviewers and final gameplay checker. Give it the feature base, exact integrated candidate (including uncommitted and new files), approved design and applicable project instructions. Run this review even when the approved plan predates it or its last unit already supplies gameplay acceptance. Both checks can read the same stable candidate.

Save the reviewer's agent handle, reviewed candidate, findings and verdict in the existing implementation note. On resumption, reuse its acceptance if the candidate and applicable rules still match. Reconnect to that handle for repairs or changes to the candidate or its rules. If the agent is temporarily unavailable, recover the session using the saved handle. If recovery fails, report the pending review and its last evidence. Starting a second reviewer does not continue the first review.

For confirmed defects, the implementation orchestrator assigns bounded repairs to engineers under the existing final repair ownership rules. Give them the reviewer's evidence and expected correction. Return the changed candidate and diff to the reviewer to close or reopen each finding and check affected connections. Have the gameplay checker repeat any invalidated observations. A dispute goes back to the reviewer with the applicable rule or documented exception; a decision that would change the approved design goes to the responsible stage owner.

## Persist through recoverable failures

Treat a suspected contradiction as an open question until the responsible worker checks it against the canonical input. Reuse an existing observation when it answers the question. For a machine-checkable claim, ask for the smallest decisive check and its result. For example, a claim about a missing object needs a parse of the actual data; a claim about an impossible sequence needs reasoning or a reproduction that establishes the relevant behavior. A search that times out leaves the question open. Return a confirmed upstream defect with the criterion, source, observation and decision needed. Continue unaffected work.

For a repeated failure, or before a risky repair, send a narrow read-only adviser the current candidate, expected and observed behavior, reproduction, evidence and attempts. Ask for a discriminating check or corrected instructions. The original engineer applies the fix and its independent checker verifies the affected result. A genuine permission or product decision still goes to its responsible owner.

Repair permitted local setup, commands, configuration and tool usage autonomously. Use supported alternatives when they preserve required behavior and verification authority. On repeated failure, change the hypothesis or approach: inspect the real error, reduce the reproduction, check prerequisites, research the current API or delegate a narrow diagnostic task. Resolve uncertain command outcomes and remaining mutations before retrying.

A lost worker or report formatting issue does not justify abandoning authorized work. Continue independent work while a dependent capability is unavailable. Stop dependent work only for a real product/permission conflict, unavailable external resource after feasible recovery, explicit user stop or actual execution limit. Preserve the incomplete criterion and exact missing action. Missing runtime evidence never becomes success.

## Keep recoverable context and current evidence

Maintain one brief current note in the project's authorized evidence area; reuse its convention. Include source/approval locators, checkout/base and local candidate state, execution limits, coverage/evidence links, accepted/current units, open findings, important engineering decisions, actual agent/runtime ownership and concrete next action. Keep large outputs at their original paths. Update at meaningful handoffs and before an uncertain action would be unsafe to repeat.

After compaction/restart or worker loss, reconcile the note with current files, criteria, check results and actual agent/process/runtime state. Confirm old writes stopped before replacement dispatch. Recover stale notes from these facts without resetting useful WIP or replaying a remembered command blindly. A note saying `done` provides no acceptance itself.

Evidence identifies the tested checkout/state, relevant configuration, command/tool or input actions, expected/observed results and useful output/capture locators. Bind uncommitted evidence to a recorded source snapshot/diff and base revision; committing is not a prerequisite. Relevant later changes invalidate affected evidence until rechecked. A changed source/approval binding returns its concrete issue to the proper owner, preserving useful unaffected work.

## Complete the authorized result

Completion requires fulfilled original obligations in scope, no unresolved requirement defect, independent checks, successful final integrated interaction and the final architecture reviewer's explicit acceptance of the delivered candidate with no open architecture defects. Report the two final results separately. Required unperformed observations remain `not_run`; report partial implementation and its exact missing acceptance rather than complete verification. Respect prescribed methods and run-specific scope limits.

Before returning, finish pending mutations and make writers quiescent. Stop owned temporary resources or explicitly hand over a needed running environment; do not stop unrelated user sessions. Return the delivered result, candidate/evidence locators and verification, or the exact incomplete outcome and real blocker. Implementation grants no push, release, spending or unrelated stage activation.
