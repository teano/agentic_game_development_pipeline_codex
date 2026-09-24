---
name: gamedev-review
description: Explicit-invocation only. Use for `$gamedev-review` or delegated independent Review of a production candidate. Inspect the bounded target without remediation; do not activate for ordinary review.
---

# GameDev Independent Review

Apply [assignment ownership and event routing](../gamedev-pipeline/references/stage-handoff-invariant.md#one-owner-and-one-current-assignment), then the [worker read route](../gamedev-pipeline/references/delivery-contract.md#worker-read-route). Load only named sections for encountered events. A supplied `control_binding` uses [Worker return](../gamedev-pipeline/references/control-return.md#worker-return); bounded caller work does not restart a stage. Standalone calls keep their public result.

Remain independent from Engineering and QA and read-only to the product. `context.review_target` defines the target; read access does not enlarge it. The [Review artifact contract](references/review-output-contract.md) owns finding eligibility, condition decomposition, complete first-pass batching, remediation and verdict rules. For product work, inspect source-bound QA obligations/methods relevant to that target and their faithful extraction from the cited approved sources; for `documentation_changes`, inspect only the issued documentation target.

Separate behavior coverage from prescribed execution evidence. Use existing `context.machine_checks` without executing controller-owned argv; an empty `assignment.checks` does not erase supplied evidence. Seek a missing exact locator through its existing owner before asking for new execution. Apply [Evidence sufficiency](../gamedev-pipeline/references/interaction-evidence.md#evidence-sufficiency), including permitted composed proof and source-grounded applicability. Do not require impossible execution, optional strengthening or a preferred implementation.

Before the first substantive verdict, finish the available target and affected mandatory obligations, then return actual current findings in one batch. On rework, consume [Repair input](../gamedev-pipeline/references/delivery-contract.md#repair-input), verify the latest rejection against the claimed correction, and inspect changes, affected integrations and genuinely unfinished first-pass scope. Preserve unchanged valid observations, including resolved condition rows required by Review's roster. Engineering's `addressed` is a claim, never independent resolution.

A verdict-changing source/applicability ambiguity uses the existing nonterminal clarification route before a verdict. A demonstrated defect with an authority-preserving correction is fail; only a real unavailable prerequisite or undelegated decision can require blocked. A limited tool denial leaves unrelated permitted inspection available. Technical journal text grants neither validity nor acceptance.

For a bounded caller task resolving an [unchanged Engineering failure](../gamedev-pipeline/references/execution-contract.md#resolve-an-unchanged-failed-attempt), provide the requested condition-bound source evidence, clarification/counterexample or actual missing prerequisite. Credit existing tests and permitted composed proof first. This answer is not a native Review verdict and resolves no findings; write only its exact authorized packet.

For native Review, publish the issued schema-bound result under the [terminal artifact boundary](../gamedev-pipeline/references/stage-handoff-invariant.md#terminal-artifact-boundary) and stop. Pass completes this assigned Review only, without final QA, product edits, risk acceptance or a new role.
