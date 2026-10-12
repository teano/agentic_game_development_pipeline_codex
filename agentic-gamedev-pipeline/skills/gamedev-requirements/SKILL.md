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

## Research before asking

Delegate substantive repository/GDD/source comparison and stack or feasibility investigation to bounded read-only subagents. The stage owner conducts the interview and synthesizes results; small known fact lookups and use of already available context can stay local. Give researchers the actual sources, concrete uncertainty and boundaries; request useful findings with evidence locators and limits. Reuse a useful lane for related follow-up, honor current user/parent model settings and do not impose a roster or spawn per question. Consume the relevant findings before asking their question; unrelated pending research need not delay independent questions. Research and review do not grant product approval.

Before each question, reconcile the requested change with accepted decisions, prior answers and relevant current architecture, code/configuration, versions and integrations. Do not ask again about known facts, accepted answers or already implemented behavior, or relabel the baseline as new work. Technical coupling, necessary adaptation or an unsuitable first implementation approach alone is not a product conflict; preserve confirmed observable behavior through ordinary technical means when the request does not contradict it. Revisit an existing decision only when a new requirement actually conflicts with it. Show the concrete conflict and consequences to its responsible decision maker; a deliberate amendment is valid, so neither veto it nor silently preserve the old choice. Track conflicts between new requirements too, rather than accepting incompatible obligations. If research shows a pending question is unnecessary, explicitly withdraw it while preserving independent answers and adding no new exclusion.

Check feasible routes before declaring a capability unsupported or asking for a scope change. Distinguish a demonstrated limit from an inconclusive probe; static compatibility is not runtime verification. Keep this research proportional to the product decision rather than designing the full specification early.

## Resolve material product choices

Ask only what is needed to make the requested outcome, scope and observable acceptance clear. By default, use up to five numbered questions, each about one independently answerable decision; never pad a round to five. A directly requested batch or interview format overrides this default. Use plain concrete terms and explain necessary notation before relying on it.

Where options help, use stable lettered choices with these roles:

- **A — recommended first:** a feasible option grounded in the actual project's architecture and current stack. Briefly explain why it fits and the supporting evidence, without claiming unperformed runtime checks.
- **B — optional:** a demonstrably better approach when the existing approach is unsuitable; name the bounded refactor and its tradeoff.
- **C — optional:** a distinct external alternative or other method when useful; state its actual prerequisites and impact.

Omit unnecessary alternatives without shifting the remaining letter roles. Do not invent a refactor, dependency or filler to create three options. If research supports no feasible current-stack option, expose that concrete gap and the real decision instead of inventing a recommended A. Use an open answer for a genuine value or clarification that options cannot faithfully represent; preserve free-text answers and any local free-text priority. Do not turn routine engineering details into product questions unless they change approved scope, meaning or permissions.

Preserve partial answers; a request for explanation is not an answer, and one answer does not silently resolve another decision. A short confirmation binds a single unambiguous proposal; bundled or contradictory content needs the smallest clarification. When the user delegated product decisions, make the actual choices within that scope, record their provenance and explain any material tradeoff in the resulting artifact. Do not ask the user again for already delegated routine choices. A real unresolved contradiction outside that authority still needs its responsible decision. Continue independent work while awaiting it.

## Write a usable PRD

Use the project's established format. The optional [outline](assets/product-requirements.md) is guidance for a project without one, not a heading schema. Include the confirmed outcome and scope, functional behavior, actual quality constraints, acceptance criteria, exclusions and decision provenance relevant to this feature. Include unresolved questions only where useful and clearly separate them from obligations. No generic audience, release, risk or nonfunctional section must be invented to complete a template.

Preserve existing requirement and criterion IDs. For new obligations, use the project's convention or stable local IDs; a file/heading locator suffices when the document has no ID convention. Acceptance must identify an observable outcome and the conditions already implied by the confirmed requirement. Avoid adding numeric targets, supported variants or extra edge cases without their own product authority. Keep implementation plans, transcripts, discarded proposals and raw tool output outside the PRD. Briefly record relevant baseline/reuse and conflict evidence in the project's existing artifact or evidence convention, distinguishing satisfied behavior from the requested change; no new table or document is required.

On correction, change only the affected content, preserving the other decisions and identifiers. If an approved artifact changes, retain its previous approval/history and bind the new bytes through the shared approval procedure. Repeating a request with no new decision or source change should preserve the existing artifact and pending question rather than create new revisions or IDs.

## Finish this stage

Read the complete PRD against the actual decisions and relevant research. Actively check material requirements for already implemented or reusable behavior, conflicts with other confirmed choices, current-stack feasibility and sufficient product meaning to distinguish success from failure. Resolve concrete missing product decisions before declaring readiness; do not leave Specification to invent them from GDD or assumed best practice. Routine technical design and setup may remain downstream. Confirm that every authorized obligation and exclusion survived and no unsupported proposal acquired authority. For a complex or risky PRD, use a read-only semantic check distinct from its author when it adds meaningful confidence, reusing a useful lane. A syntax check cannot establish these facts or user consent.

Freeze the complete checked PRD and compute its current SHA-256. Obtain actual approval of those bytes from the responsible actor, exercising existing delegated approval only within its scope, then record the real decision outside the PRD using the shared binding procedure. Do not manufacture approval metadata or treat a reader's favorable finding as the decision.

Return `PRD_READY: yes|no`, project/feature, canonical PRD path and current SHA-256, existing revision if present, approval locator/actor, changed obligations and any exact unresolved decision. `yes` requires a complete usable PRD and actual approval of those current bytes. Give `NEXT_ACTION: $gamedev-specification` when ready, otherwise the concrete missing decision or Requirements correction.

Stop at the handoff. Readiness advises the next stage; only an already authorized full-cycle parent may activate it. This stage grants no implementation, runtime launch, publication or additional permissions.
