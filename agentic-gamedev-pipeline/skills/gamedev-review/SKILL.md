---
name: gamedev-review
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-review` or an active, explicitly invoked `$gamedev-pipeline` Director delegates the review phase. Independently inspect the current candidate without remediation. Do not activate for ordinary code review or implementation feedback.
---

# GameDev Independent Review

## Activation gate

Proceed only on the explicit activation described above. Read the shared [stage handoff invariant](../gamedev-pipeline/references/stage-handoff-invariant.md) and [review artifact contract](references/review-output-contract.md).

Remain read-only. `assignment.context.review_target` is the complete audit target. For a slice Review, `required_scope` contains exactly `current_slice.allowed_paths` while `candidate_changes` lists the exact paths changed by the accepted Engineering candidate. Authority, sealed `read_paths`, completed-slice paths, and untouched paths covered by a broad required-scope rule are evidence context, not independent audit scope. A finding about an introduced defect or excess complexity must be tied to `candidate_changes`; outside those paths, only missing mandatory implementation inside `required_scope` or a direct regression caused by the candidate on a supported game path or deterministic code trace is eligible. For a post-Docs `documentation_changes` Review, `candidate_changes` is both the required scope and the complete target.

A finding is valid only when current-candidate evidence shows a reachable supported game-path defect or deterministic code trace, the impact materially violates mandatory approved behavior or acceptance, and the smallest correction stays inside the target. Do not report theoretical or extremely unlikely risks, unsupported misuse, manual tampering, future-scale concerns, unrequested security hardening, style or nit preferences, optional cleanup, pre-existing unrelated issues, speculative refactors, or tests added merely for completeness. Do not search for further improvements after the bounded target is proven.

Apply KISS and YAGNI in both directions. Fail concrete target code that introduced an unnecessary abstraction, state, configuration, fallback, dependency, or lifecycle when authority does not need it and a simpler sufficient implementation exists. Never require extra layers, generality, defensive infrastructure, or hypothetical extensibility.

Stop and pass with `findings: []` as soon as mandatory behavior, directly affected integrations, and minimal sufficient complexity are verified. Return no suggestions, backlog, or optional follow-ups. Ask a question only for a direct contradiction in approved authority that changes the verdict. Return `blocked` only when a mandatory assigned input or capability is actually unavailable, never to request an improvement.

Do not edit, remediate, accept risk, alter controller state, or start another stage. Follow `assignment.artifact_schema` exactly; write only that semantic JSON to the assigned `output_path`, return that path, and stop.
