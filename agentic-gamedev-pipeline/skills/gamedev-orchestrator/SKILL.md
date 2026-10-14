---
name: gamedev-orchestrator
description: Explicit-invocation only. Use for `$gamedev-orchestrator` or an explicit request for this full-cycle mode. Work through game-feature requirements with the user and obtain human PRD approval, then delegate Specification, Planning and Implementation automatically in the same chat within that scope.
---

# GameDev Orchestrator

Own the authorized full cycle in one persistent root chat: Requirements with the user, then Specification, Planning and Implementation through their stage owners. Retain the original obligations and real authority across handoffs. This entrypoint grants no activation from ordinary product discussion and does not replace any stage's procedure.

## Establish the cycle

Resolve the actual project/feature, checkout and local changes, canonical documents, existing decisions and execution limits. Follow [artifact and approval bindings](../gamedev-pipeline/references/artifacts-and-approval.md) for exact current sources, hashes, real decisions and durable records. Preserve existing paths, IDs, useful WIP and evidence conventions. Existing drafts, readiness or approvals inform this cycle but do not skip its human Requirements checkpoint.

Keep this root as the cycle coordinator. Delegate each stage to a real bounded owner using its linked skill; do not author the PRD, specification, plan or product changes in the root. Pass the user's actual decisions and questions between the Requirements owner and user without inventing answers. Keep the same root chat throughout; do not create user-owned chats, goals, automations or another workflow controller to run the cycle.

Start stage owners without inherited root/earlier-stage transcripts (`fork_turns="none"` when using `spawn_agent`). Give compact factual handoffs: scope and original authority locators, complete relevant criterion text, canonical current document/source locators, candidate and approval identities, boundaries, concrete findings, evidence and next outcome. Workers read primary sources rather than rely on summaries or ID lists. Preserve current user/parent model settings. Reuse an existing owner for its stage's corrections; replace a lost owner only after reconciling its useful work and confirming quiescence.

## Work through Requirements with the user

Always delegate [Requirements](../gamedev-requirements/SKILL.md) first. Have its owner examine the current project, sources, prior decisions and any existing PRD, then explicitly work through the intended scope with the user. Reuse confirmed decisions and usable text; do not repeat settled questions. Resolve material gaps and contradictions through the stage's grounded interview. If no new choice is needed, present the known scope and complete current PRD for the user's explicit confirmation and approval. An old approval or a request to continue cannot silently substitute for this checkpoint.

Present the complete checked PRD and exact current SHA-256 for the user's real approval. A prior direct human approval can be reused only when this user explicitly confirms that the same unchanged PRD remains the requirements for this cycle and Requirements reconciliation finds no new meaning or unresolved choice; verify its current bytes and actual approval binding. Explain that this full-cycle invocation and human checkpoint authorize technical execution and technical document approval within that PRD, after which the remaining stages proceed automatically in this chat. Preserve any additional user-reserved checkpoint. The final PRD approval in this mode belongs to the human user; do not delegate or automatically record it. No Specification, Planning, product edits or product runtime work starts before that actual approval and a verified `PRD_READY: yes` handoff.

## Continue the technical stages

After the human checkpoint, proceed without requiring separate skill invocations or routine human SPEC/PLAN approvals. The user's full-cycle invocation and approval define the technical delegation; they grant no new product choices, scope or external permissions. Give each stage owner that actual authority statement/locator and its limits.

1. Delegate [Specification](../gamedev-specification/SKILL.md) from the approved current PRD. Its owner performs the complete design, correction and required independent reading, then a qualified authorized owner or reviewer actually approves the complete current specification bytes. Verify the source/approval bindings and `SPEC_READY: yes` handoff before Planning.
2. Delegate [Planning](../gamedev-development-plan/SKILL.md) from the current approved PRD and specification. Preserve all obligations, work boundaries and meaningful integrated acceptance. Its qualified authorized owner or reviewer performs the stage's checks and actually approves the complete current plan bytes. Verify the source/approval bindings and `PLAN_READY: yes` handoff before Implementation.
3. Delegate [Implementation](../gamedev-pipeline/SKILL.md) from the current approved PRD, specification and plan, with the actual execution permissions. Its stage owner retains the implementation loop and coverage, delegates product authorship, obtains independent evidence and returns the delivered or precisely incomplete result.

Authority to approve is not approval. Require an actual actor who reads the full current artifact, satisfies the stage's required independent reading and explicitly accepts its exact bytes. A draft, worker success or favorable review alone cannot become an approval record. The root verifies real handoffs; it does not fabricate records or bypass stage owners, checks or corrections.

Keep Implementation's fresh Engineer and independent QA/checker for every development slice, its approved unit boundaries and same-slice repair team. Acceptance-only units and final integrated acceptance require a fresh independent checker uninvolved in earlier slices. If the last planned unit already supplies that acceptance on the current candidate, consume it once without duplicate final QA. Do not replace real required interaction with compilation, screenshots or slice PASS reports.

## Resolve changes and recover

Return a material product gap, contradiction or new scope to the Requirements owner and user. Obtain the needed decision, current PRD revision and human approval before dependent work resumes, then reassess affected downstream sources and evidence. A required permission change needs its responsible user's decision. Preserve unrelated useful authorized work while resolving the issue. Routine technical design, implementation refinement, local setup and recoverable failures remain delegated work within the approved obligations; they do not create another product approval checkpoint.

Use one existing brief current note/WIP at the project's evidence location for cycle recovery, extending it only when needed. Retain authority and source/approval locators, current stage/unit, candidate/evidence, remaining obligations, actual owner/runtime state and next action. Keep large output at its primary locator; do not copy transcripts or introduce parallel state documents, JSON gates, resets or a second controller. After compaction/restart, reconcile that note with actual artifacts, agent/process state and runtime before continuing. Resuming the same confirmed cycle with valid source/approval bindings preserves its human checkpoint; do not repeat the interview or request approval again merely because context was compacted or restarted.

Keep one writer for shared files and one operator for a mutable runtime. Finish pending mutations and confirm the previous owner's writes/jobs/runtime operations are quiescent before transferring ownership. Preserve needed runtime instances, code and WIP. Do not reset useful work or stop unrelated user sessions. Recover feasible technical failures through the responsible owner; stop dependent work only for a real unresolved decision/access requirement, explicit stop or actual execution limit. Missing evidence remains missing.

## Complete the cycle

Complete only when the authorized original obligations and required final integrated acceptance are established on the delivered state. Required unavailable observations remain `not_run`, with the exact incomplete outcome and missing action. Before returning, make writers quiescent and finish or explicitly hand over owned temporary resources. Report the delivered result, current artifact/approval and candidate/evidence locators, verification and any real blocker. The cycle grants no push, release, spending or unrelated external action.
