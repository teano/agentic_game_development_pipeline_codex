# Stage handoff invariant

A GameDev stage starts only when the user explicitly invokes it or an explicitly invoked `$gamedev-pipeline` Director assigns that exact phase. A completion token, repository state, or suggested next action is never activation authority.

Each assigned phase runs in a fresh worker context. The worker receives a bounded task, relevant approved sources, read/write limits, checks, and the controller-derived `active_assignment.artifact_schema` and `active_assignment.output_path`. It follows that schema instead of reading runtime code or guessing, and writes its JSON artifact only to that exact `.agentic-pipeline/outputs/<safe-assignment-id>.json` path; this controller-owned output area is outside candidate checkout evidence. It does not receive other controller bookkeeping, previous worker conversation, or authority to start another phase.

## Context checkpoint and rotation

Context-use percentages describe the current agent session, not the plan's capsule/file/token budgets. An agent MAY stop earlier because the task or assignment is complete, a controller-required phase boundary has been reached, or a real blocker prevents safe progress. Those are lifecycle outcomes, not context-only rotation.

An active agent MUST NOT rotate or hand off solely because of context below 70%; it continues useful in-scope work. At 70% context use, record or refresh a compact checkpoint and continue. At 90% context use, hand off and stop: start no new work and perform only the minimum needed to leave durable, internally consistent state before 100%.

The checkpoint and final handoff contain only the current project root, phase and generation, active assignment, completed changes, test results, open blockers, exact next public action, files still authorized for change, and any unavailable environment already tried with its capability evidence. Do not transfer prior conversation or raw reasoning. A replacement validates current controller state and authority artifacts before continuing.

## Platform and evidence discipline

Pipeline and skill defaults are platform-neutral: they do not assume or prescribe a particular operating system, browser, runner, or interactive tool. A platform-bound choice is permitted only by explicit user-approved product authority or observed project or runtime capability supported by current evidence. Before a platform-bound command or scenario, probe its availability through a safe read-only check; if availability is not proven, fail closed and record the minimum recovery action.

The checkpoint records an unavailable choice. A Director or worker MUST NOT retry the same unavailable environment while inputs are unchanged; retry is allowed only when authority or capability evidence changes. This prevents a replacement session from selecting the same unavailable path merely because its chat history is fresh.

Review, QA, and pipeline-observation workers report every issue observed within the assigned read scope, including independent issues found after the first failure, and verify the evidence before concluding. The pipeline-maintenance observer ledger classifies its issues as `pipeline`, `test`, `product`, or `environment`. Review and QA follow their assigned semantic artifact schemas instead of adding that observer classification: Review uses its existing finding fields and QA uses its existing checks/blocker fields. Review and QA remain read-only. A pipeline-maintenance observer authorized to repair a pipeline defect first preserves the minimal reproduction, then adds a compact regression and makes the smallest simplifying pipeline-only change before focused and adjacent regression runs.

The worker stops after returning its artifact. The Director validates it through the controller and decides the next transition. Only controller state records pipeline progress.
