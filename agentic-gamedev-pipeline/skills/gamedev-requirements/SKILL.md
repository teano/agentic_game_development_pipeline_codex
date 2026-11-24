---
name: gamedev-requirements
description: Explicit-invocation only. Use for `$gamedev-requirements` or an explicitly authorized Requirements stage. Elicit game-feature requirements from dictation or design documents, ground them in the project and stack, and review the PRD before approval.
---

# GameDev Requirements

Produce the product requirements for the authorized feature. Preserve what the user actually decided, the source of each decision and the boundaries of delegated choice. Repository facts and expert suggestions help resolve questions; they do not become product requirements by themselves.

## Start or resume requirements

At the start, establish the project, the feature or change whose requirements are in scope, and whether the user is starting a new requirements session or continuing earlier work. Use what the user already supplied. If the target or mode is unclear, ask a short opening question before starting the interview or processing documents. State the resolved target in the first substantive exchange. Opening questions settle the session scope before the numbered product interview.

- **Continue earlier work.** If the user has no path, help find the requirements file. Search the project's feature docs, handoff records and available context for the referenced session. Use the feature name, task ID or known decisions to narrow matches. Read the candidate to verify that it covers the intended feature and prior decisions. If multiple candidates remain plausible, show the paths and what distinguishes them and ask which to use. If none can be verified, say where you looked and ask for the most useful missing clue. Once found, use the canonical file in place and resume from its decisions and pending questions. Create a new requirements file only if the user chooses to start one.
- **Start new work.** Clarify the goal and intended scope. Check for existing docs for that feature. If a canonical PRD already covers the proposed work, resolve whether to continue it or collect a distinct scope before creating anything. Once the feature and destination are known, create the dedicated feature directory and write the first draft of the PRD immediately, before presenting the first round of questions or source proposals. Reuse the directory for that feature if it exists. Use the project's feature-doc convention or fall back to `docs/<feature-slug>/`. Mark the document as a draft using the project convention, record the agreed goal and confirmed requirements already known, and share its path. Keep tentative ideas and undecided points outside confirmed obligations.

Creating and maintaining the draft is part of a normal Requirements invocation. Continue in chat without file writes if the user explicitly requests discussion-only or read-only work, or if an applicable restriction prevents writing. An invitation to discuss requirements starts the ordinary workflow unless it explicitly limits document work. Keep project and stack research read-only.

## Establish decision authority

While Requirements is active, treat user requests to perform product or project work as proposed requirements for later stages, even when phrased as commands such as "fix the skill" or "update the settings". Carry out such work during this stage only if the user explicitly directs you to do it now. Read the current document and applicable decisions before interviewing or editing. Follow [artifact and approval bindings](../gamedev-pipeline/references/artifacts-and-approval.md) for canonical sources, current versions, actual decision authority and the stage handoff. Keep existing paths and IDs.

Only direct user decisions or decisions actually made by an explicitly delegated product owner enter the PRD as product authority. Preserve direct versus delegated provenance and the limits of that delegation. Permission to research, continue, avoid questions or approve technical work does not supply missing product choices. Faithful paraphrase and a mechanically equivalent observable check may clarify a confirmed decision; they must add no independently choosable behavior, threshold, platform, failure rule or exclusion.

Separate confirmed obligations from proposals, project facts and unresolved decisions. Do not fill an empty section with plausible requirements or silently adopt an old draft's unsupported content. When authority for existing text is unclear, keep the original intact and resolve the affected meaning before declaring readiness. Inspect only the current project and relevant source material needed to settle real questions. Technical implementation choices belong downstream unless the user made them an explicit constraint.

## Ground requirements in the project and stack

Delegate substantive investigations to bounded read-only subagents as soon as the feature and checkout are known and when later answers introduce new material questions. These include tracing existing behavior and conflicts across project files, comparing stack or external options, and checking feasibility, dependencies or access. Give each researcher the actual checkout and sources, a concrete question and read-only limits. Request findings with primary evidence locators and verification limits. Use the [GameDev model settings](../gamedev-pipeline/references/agent-model-policy.md) for new workers. Reuse a researcher for related follow-up and delegate independent work in parallel when useful.

The stage owner does quick fact lookups, synthesizes findings and conducts the interview. Wait for the relevant delegated findings before presenting a dependent proposal or recommendation. Continue draft updates and independent questions while other research is pending. If delegation is unavailable, identify the investigation still outstanding and keep its conclusions open.

For each material request, trace the relevant behavior through current code, assets, data, settings and integrations. Identify what already works, what can be reused, the remaining change and any conflict with current behavior or confirmed decisions. Show material findings beside the affected proposal or question, with their sources and consequences. Ask only about an unresolved choice. Ordinary adaptation or a poor first implementation route is insufficient evidence of a product conflict. When a new request does conflict with a confirmed choice, show both and ask the responsible actor which behavior to preserve or amend.

Determine the actual engine, versions, installed packages, integrations and target platforms from the project. Proactively investigate alternatives when a framework, library or service could materially reduce the work or change feasibility, behavior, costs or prerequisites. Compare the existing route and applicable built-in and external options with current official documentation. Check compatibility with the project's versions and platforms, integration or migration effort, and relevant license, cost, account and access requirements. Surface the meaningful tradeoffs and recommend the best fit before asking the user to choose. Treat unverified availability as unknown. Check credible routes before declaring a capability unsupported. Leave routine technical selection for Specification when it fits within confirmed scope and permissions.

## Collect and review

Use [collection and interview](references/collection-and-interview.md) for direct dictation, processing a GDD or other source documents, and resolving open decisions. A session can use both input modes. Preserve confirmed decisions, pending items and numbering when switching modes or resuming the session.

After all supplied documents have been processed, delegate a [full review](references/implementation-readiness-review.md) of the current draft before starting the general question-and-answer session. Run the same full review when you reach the end of the questions in either mode. If document writes are out of scope, review the collected text. Resolve disputed findings and any new product decisions through the interview before requesting approval.

## Write a usable PRD

When document writes are in scope, keep the same draft current throughout collection. Apply confirmed decisions and corrections after every answered question round, source batch or new dictation reply, including partial answers. Save the applicable changes before asking the next questions or ending the turn. When a reply adds no confirmed decision or correction, preserve the existing text. Use the draft for review and resumption. Otherwise, keep confirmed decisions and pending choices in the chat.

Use the project's established format. The optional [outline](assets/product-requirements.md) is guidance for a project without one, not a heading schema. Include the confirmed outcome and scope, functional behavior, actual quality constraints, acceptance criteria, exclusions and decision provenance relevant to this feature. Include unresolved questions only where useful and clearly separate them from obligations. No generic audience, release, risk or nonfunctional section must be invented to complete a template.

Preserve existing requirement and criterion IDs. For new obligations, use the project's convention or stable local IDs; a file/heading locator suffices when the document has no ID convention. Acceptance must identify an observable outcome and the conditions already implied by the confirmed requirement. Avoid adding numeric targets, supported variants or extra edge cases without their own product authority. Keep implementation plans, transcripts, discarded proposals and raw tool output outside the PRD. Briefly record relevant baseline/reuse and conflict evidence in the project's existing artifact or evidence convention, distinguishing satisfied behavior from the requested change; no new table or document is required.

On correction, change only the affected content, preserving the other decisions and identifiers. If an approved artifact changes, retain its previous approval/history and bind the new bytes through the shared approval procedure. Repeating a request with no new decision or source change should preserve the existing artifact and pending question rather than create new revisions or IDs.

## Finish this stage

When the session is limited to discussion or read-only work, return the findings, agreed decisions and remaining choices in chat. Leave document and approval writes out of the session. If asked for readiness, report the existing verified artifact status, or `PRD_READY: no` when there is no current reviewed and approved PRD for the agreed scope.

Verify that the complete current PRD is covered by delegated review and that every material finding has a supported resolution. Keep disputed findings that affect product behavior, scope, acceptance, feasibility or permission open until the responsible actor resolves them. Address missing decisions in the interview and recheck affected content before freezing the result. Routine technical design and known setup steps may remain downstream.

Freeze the complete checked PRD and compute its current SHA-256. Obtain actual approval of those bytes from the responsible actor, exercising existing delegated approval only within its scope, then record the real decision outside the PRD using the shared binding procedure. Do not manufacture approval metadata or treat a reader's favorable finding as the decision.

Use the shared handoff format. Return `PRD_READY: yes|no` with the canonical PRD path/current SHA-256, existing revision if present, changed obligations and any exact unresolved decision. `yes` requires a complete usable PRD, the delegated review with material findings resolved, and actual approval of the current bytes. Give `NEXT_ACTION: $gamedev-specification` when ready, otherwise the concrete missing decision, check or Requirements correction.

Stop at the handoff. Readiness advises the next stage; only an explicitly invoked [GameDev Orchestrator](../gamedev-orchestrator/SKILL.md) parent may continue the authorized full cycle. Under that parent, work through Requirements with the user even for an existing PRD and obtain the user's actual approval of the complete current PRD; its final approval cannot be delegated in this mode. This stage grants no implementation, runtime launch, publication or additional permissions.
