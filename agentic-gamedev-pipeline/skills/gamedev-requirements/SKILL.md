---
name: gamedev-requirements
description: Explicit-invocation only. Use for `$gamedev-requirements` or an explicitly authorized Requirements stage. Turn confirmed game-feature decisions into a canonical PRD with observable criteria and actual approval; do not activate for ordinary product discussion.
---

# GameDev Requirements

Produce the product requirements for the authorized feature. Preserve what the user actually decided, the source of each decision and the boundaries of delegated choice. Repository facts and expert suggestions help resolve questions; they do not become product requirements by themselves.

## Establish scope and authority

Resolve the actual project, selected feature, existing PRD and allowed document work from the task and project conventions. Read the current document and applicable decisions before interviewing or editing. Follow [artifact and approval bindings](../gamedev-pipeline/references/artifacts-and-approval.md) for canonical sources, current versions, actual decision authority and the stage handoff. Keep existing paths and IDs. A discussion-only request does not authorize creating project artifacts.

Only direct user decisions or decisions actually made by an explicitly delegated product owner enter the PRD as product authority. Preserve direct versus delegated provenance and the limits of that delegation. Permission to research, continue, avoid questions or approve technical work does not supply missing product choices. Faithful paraphrase and a mechanically equivalent observable check may clarify a confirmed decision; they must add no independently choosable behavior, threshold, platform, failure rule or exclusion.

Separate confirmed obligations from proposals, project facts and unresolved decisions. Do not fill an empty section with plausible requirements or silently adopt an old draft's unsupported content. When authority for existing text is unclear, keep the original intact and resolve the affected meaning before declaring readiness. Inspect only the current project and relevant source material needed to settle real questions. Technical implementation choices belong downstream unless the user made them an explicit constraint.

## Resolve material product choices

Ask only the questions needed to make the requested outcome, scope and observable acceptance clear. Use a compact round of independently answerable questions with useful options and a project-grounded recommendation when available. Preserve partial answers; a request for explanation is not an answer, and one answer does not silently resolve another decision. A short confirmation binds a single unambiguous proposal; bundled or contradictory content needs the smallest clarification.

When the user delegated product decisions, make the actual choices within that scope, record their provenance and explain any material tradeoff in the resulting artifact. Do not ask the user again for already delegated routine choices. A real unresolved contradiction outside that authority still needs its responsible decision. Continue independent work while awaiting it.

Use bounded read-only research or an independent semantic read when it can resolve a concrete uncertainty or expose an omission. Supply the actual source material and question; consume its result as evidence. Research and review do not grant product approval. Reuse a useful lane for related follow-up and honor current user/parent model settings rather than imposing a roster.

## Write a usable PRD

Use the project's established format. The optional [outline](assets/product-requirements.md) is guidance for a project without one, not a heading schema. Include the confirmed outcome and scope, functional behavior, actual quality constraints, acceptance criteria, exclusions and decision provenance relevant to this feature. Include unresolved questions only where useful and clearly separate them from obligations. No generic audience, release, risk or nonfunctional section must be invented to complete a template.

Preserve existing requirement and criterion IDs. For new obligations, use the project's convention or stable local IDs; a file/heading locator suffices when the document has no ID convention. Acceptance must identify an observable outcome and the conditions already implied by the confirmed requirement. Avoid adding numeric targets, supported variants or extra edge cases without their own product authority. Keep implementation plans, transcripts, discarded proposals and raw tool output outside the PRD.

On correction, change only the affected content, preserving the other decisions and identifiers. If an approved artifact changes, retain its previous approval/history and bind the new bytes through the shared approval procedure. Repeating a request with no new decision or source change should preserve the existing artifact and pending question rather than create new revisions or IDs.

## Finish this stage

Read the complete PRD against the actual decisions. Confirm that every authorized product obligation and exclusion survived, the criteria can distinguish success from failure, no blocking product contradiction remains and no unsupported proposal acquired authority. A syntax check cannot establish these facts or user consent.

Freeze the complete checked PRD and compute its current SHA-256. Obtain actual approval of those bytes from the responsible actor, exercising existing delegated approval only within its scope, then record the real decision outside the PRD using the shared binding procedure. Do not manufacture approval metadata or treat a reader's favorable finding as the decision.

Return `PRD_READY: yes|no`, project/feature, canonical PRD path and current SHA-256, existing revision if present, approval locator/actor, changed obligations and any exact unresolved decision. `yes` requires a complete usable PRD and actual approval of those current bytes. Give `NEXT_ACTION: $gamedev-specification` when ready, otherwise the concrete missing decision or Requirements correction.

Stop at the handoff. Readiness advises the next stage; only an already authorized full-cycle parent may activate it. This stage grants no implementation, runtime launch, publication or additional permissions.
