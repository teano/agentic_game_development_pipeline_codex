---
name: gamedev-requirements
description: Explicit-invocation only. Use for `$gamedev-requirements` or an explicitly authorized Requirements stage. Elicit game-feature requirements from dictation or design documents, ground them in the project and stack, and review the PRD before approval.
---

# GameDev Requirements

Produce the product requirements for the authorized feature. Preserve what the user actually decided, the source of each decision and the boundaries of delegated choice. Repository facts and expert suggestions help resolve questions; they do not become product requirements by themselves.

## Start or resume requirements

At the start, establish the project, the feature or change whose requirements are in scope, and whether the user is starting a new requirements session or continuing earlier work. Use what the user already supplied. If the target or mode is unclear, ask a short opening question before starting the interview or processing documents. State the resolved target in the first substantive exchange. Opening questions settle the session scope before the numbered product interview.

- **Continue earlier work.** If the user has no path, help find the requirements file. Search the project's feature docs, handoff records and available context for the referenced session. Use the feature name, task ID or known decisions to narrow matches. Read the candidate to verify that it covers the intended feature and prior decisions. If multiple candidates remain plausible, show the paths and what distinguishes them and ask which to use. If none can be verified, say where you looked and ask for the most useful missing clue. Once found, use the canonical file in place and resume from its decisions and pending questions. Create a new requirements file only if the user chooses to start one.
- **Start new work.** Clarify the goal and intended scope of the feature or change. Check for existing docs for that feature. If a canonical requirements file already covers the proposed work, resolve whether to continue it or collect a distinct scope before creating anything. With the target established, create a dedicated directory for the feature's artifacts using the project's feature-doc convention. Reuse an existing directory for that same feature, if present. If there is no feature-doc convention, use `docs/<feature-slug>/` with a stable name based on the agreed feature. Use the directory as the destination when writing the PRD and pass it on for later artifacts. Use the top-level `docs/` only as a parent for the new directory. A new Requirements session authorizes this directory setup unless the user limits the session to discussion or read-only work.

## Establish decision authority

While Requirements is active, treat user requests to perform product or project work as proposed requirements for later stages, even when phrased as commands such as "fix the skill" or "update the settings". Carry out such work during this stage only if the user explicitly directs you to do it now. Keep research read-only, including delegated research. Read the current document and applicable decisions before interviewing or editing. Record confirmed requirements in the PRD when authorized. Follow [artifact and approval bindings](../gamedev-pipeline/references/artifacts-and-approval.md) for canonical sources, current versions, actual decision authority and the stage handoff. Keep existing paths and IDs.

Only direct user decisions or decisions actually made by an explicitly delegated product owner enter the PRD as product authority. Preserve direct versus delegated provenance and the limits of that delegation. Permission to research, continue, avoid questions or approve technical work does not supply missing product choices. Faithful paraphrase and a mechanically equivalent observable check may clarify a confirmed decision; they must add no independently choosable behavior, threshold, platform, failure rule or exclusion.

Separate confirmed obligations from proposals, project facts and unresolved decisions. Do not fill an empty section with plausible requirements or silently adopt an old draft's unsupported content. When authority for existing text is unclear, keep the original intact and resolve the affected meaning before declaring readiness. Inspect only the current project and relevant source material needed to settle real questions. Technical implementation choices belong downstream unless the user made them an explicit constraint.

## Ground requirements in the project and stack

Use bounded read-only subagents to investigate the actual checkout, compare source proposals with current behavior, research relevant stack and external options, and review the collected requirements. Give each researcher the current feature and sources, concrete questions and read-only limits. Request findings with evidence locators and verification limits. Use the [GameDev model settings](../gamedev-pipeline/references/agent-model-policy.md) for new workers. Reuse a useful worker for related follow-up and delegate independent investigations in parallel when useful. The stage owner synthesizes findings and conducts the interview. Small known fact lookups can stay local. Use the relevant findings before presenting a source item or asking a question. Continue independent work while unrelated research is pending.

For each material request, trace the relevant behavior through current code, assets, data, settings and integrations. Identify what already works, what can be reused, the remaining change and any conflict with current behavior or confirmed decisions. Show material findings beside the affected proposal or question, with their sources and consequences. Ask only about an unresolved choice. Ordinary adaptation or a poor first implementation route is insufficient evidence of a product conflict. When a new request does conflict with a confirmed choice, show both and ask the responsible actor which behavior to preserve or amend.

Determine the actual engine, versions, installed packages, integrations and target platforms from the project. Proactively investigate alternatives when a framework, library or service could materially reduce the work or change feasibility, behavior, costs or prerequisites. Compare the existing route and applicable built-in and external options with current official documentation. Check compatibility with the project's versions and platforms, integration or migration effort, and relevant license, cost, account and access requirements. Surface the meaningful tradeoffs and recommend the best fit before asking the user to choose. Treat unverified availability as unknown. Check credible routes before declaring a capability unsupported. Leave routine technical selection for Specification when it fits within confirmed scope and permissions.

## Collect and review

Use [collection and interview](references/collection-and-interview.md) for direct dictation, processing a GDD or other source documents, and resolving open decisions. A session can use both input modes. Preserve confirmed decisions, pending items and numbering when switching modes or resuming the session.

After all supplied documents have been processed, delegate a [full review](references/implementation-readiness-review.md) of the collected requirements before starting the general question-and-answer session. Run the same full review when you reach the end of the questions in either mode. Return material findings to the interview, then check the resulting requirements again. Complete this loop before presenting the PRD for approval.

## Write a usable PRD

Use the project's established format. The optional [outline](assets/product-requirements.md) is guidance for a project without one, not a heading schema. Include the confirmed outcome and scope, functional behavior, actual quality constraints, acceptance criteria, exclusions and decision provenance relevant to this feature. Include unresolved questions only where useful and clearly separate them from obligations. No generic audience, release, risk or nonfunctional section must be invented to complete a template.

Preserve existing requirement and criterion IDs. For new obligations, use the project's convention or stable local IDs; a file/heading locator suffices when the document has no ID convention. Acceptance must identify an observable outcome and the conditions already implied by the confirmed requirement. Avoid adding numeric targets, supported variants or extra edge cases without their own product authority. Keep implementation plans, transcripts, discarded proposals and raw tool output outside the PRD. Briefly record relevant baseline/reuse and conflict evidence in the project's existing artifact or evidence convention, distinguishing satisfied behavior from the requested change; no new table or document is required.

On correction, change only the affected content, preserving the other decisions and identifiers. If an approved artifact changes, retain its previous approval/history and bind the new bytes through the shared approval procedure. Repeating a request with no new decision or source change should preserve the existing artifact and pending question rather than create new revisions or IDs.

## Finish this stage

Verify that the reviewed requirements match the complete current PRD. If the review ran from the collected text, check the written PRD against it for omissions or changed meaning. Return material changes to review before freezing the result. Resolve missing product decisions before handoff. Routine technical design and known setup steps may remain downstream.

Freeze the complete checked PRD and compute its current SHA-256. Obtain actual approval of those bytes from the responsible actor, exercising existing delegated approval only within its scope, then record the real decision outside the PRD using the shared binding procedure. Do not manufacture approval metadata or treat a reader's favorable finding as the decision.

Use the shared handoff format. Return `PRD_READY: yes|no` with the canonical PRD path/current SHA-256, existing revision if present, changed obligations and any exact unresolved decision. `yes` requires a complete usable PRD, the delegated review with material findings resolved, and actual approval of the current bytes. Give `NEXT_ACTION: $gamedev-specification` when ready, otherwise the concrete missing decision, check or Requirements correction.

Stop at the handoff. Readiness advises the next stage; only an explicitly invoked [GameDev Orchestrator](../gamedev-orchestrator/SKILL.md) parent may continue the authorized full cycle. Under that parent, work through Requirements with the user even for an existing PRD and obtain the user's actual approval of the complete current PRD; its final approval cannot be delegated in this mode. This stage grants no implementation, runtime launch, publication or additional permissions.
