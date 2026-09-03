# Stage handoff invariant

A GameDev stage starts only when the user explicitly invokes it or an explicitly invoked `$gamedev-pipeline` Director assigns that exact phase. A completion token, repository state, or suggested next action is never activation authority.

Each assigned phase runs in a fresh worker context. The worker receives a bounded task, relevant approved sources, read/write limits, checks, and the controller-derived `active_assignment.artifact_schema` and `active_assignment.output_path`. It follows that schema instead of reading runtime code or guessing, and writes its JSON artifact only to that exact `.agentic-pipeline/outputs/<safe-assignment-id>.json` path; this controller-owned output area is outside candidate checkout evidence. It does not receive other controller bookkeeping, previous worker conversation, or authority to start another phase. The worker is the sole product mutation owner during the assignment, stops before returning its artifact, never runs controller-owned planned commands, and never starts or controls an interactive, background, long-lived, callback-driven, service, or already-running external mutator.

## Context checkpoint and rotation

Context-use percentages describe the current agent session, not the plan's capsule/file/token budgets. An agent MAY stop earlier because the task or assignment is complete, a controller-required phase boundary has been reached, or a real blocker prevents safe progress. Those are lifecycle outcomes, not context-only rotation.

An active agent MUST NOT rotate or hand off solely because of context below 70%; it continues useful in-scope work. At 70% context use, record or refresh a compact checkpoint and continue. At 90% context use, hand off and stop: start no new work and perform only the minimum needed to leave durable, internally consistent state before 100%.

The checkpoint and final handoff contain only the current project root, phase and generation, active assignment, completed changes, test results, open blockers, exact next public action, files still authorized for change, and any unavailable environment already tried with its capability evidence. Do not transfer prior conversation or raw reasoning. A replacement validates current controller state and authority artifacts before continuing.

## Platform and evidence discipline

Pipeline and skill defaults are platform-neutral: they do not assume or prescribe a particular operating system, browser, runner, or interactive tool. A platform-bound choice is permitted only by explicit user-approved product authority or observed project or runtime capability supported by current evidence. Before a platform-bound command or scenario, probe its availability through a safe read-only check; if availability is not proven, fail closed and record the minimum recovery action.

An unavailable environment is a terminal `blocked` result with `user_input_required=true`, not a retry state. Workers and Directors MUST NOT retry the same unavailable environment. Archive the run and use a fresh `init` only after authority or capability evidence changes.

Pipeline-observation workers report every issue observed within their assigned observation scope, including independent issues found after the first failure, and verify the evidence before concluding. The pipeline-maintenance observer ledger classifies its issues as `pipeline`, `test`, `product`, or `environment`. Review and QA instead stop at their bounded stage contracts: Review reports only findings eligible under its controller-derived `review_target`, while QA records only assigned acceptance checks and a real blocker when applicable. Review and QA remain read-only. After a new explicit user command starts a separate pipeline-maintenance task, its observer first preserves the minimal reproduction, then adds a compact regression and makes the smallest simplifying pipeline-only change before focused and adjacent regression runs.

The worker stops after returning its artifact. The Director validates it through the controller and decides the next transition. Only controller state records pipeline progress.

## Controller incident stop

If any Director or worker suspects a defect in the pipeline controller, runtime, skill, protocol, or controller-owned state transition, it MUST immediately stop the product run. It reports the failing public action, phase/generation, bounded and redacted error evidence, observed versus expected behavior, candidate impact, and the exact recovery prerequisite. It MUST NOT edit, patch, bypass, monkeypatch, locally replace, or continue through the pipeline implementation, instructions, state, or checks.

Product-run authority never grants pipeline-maintenance authority. Pipeline maintenance may begin only as a separate task after a new explicit user command that names that maintenance work. Until then the run remains stopped; no worker assignment or product lifecycle transition may continue on a locally altered pipeline.
