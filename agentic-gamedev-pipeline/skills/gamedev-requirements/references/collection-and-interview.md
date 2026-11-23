# Collect requirements and resolve decisions

## Direct dictation

Capture the user's requests in their own terms. Preserve explicit decisions and distinguish tentative ideas, alternatives and open points. For each material item, use project and stack research to identify existing behavior, reuse, conflicts and feasibility. Surface findings that change the requested scope or decision. Carry confirmed decisions forward without asking the user to repeat them. Use the interview below for choices that affect the outcome, scope, acceptance or permissions.

## GDD and other source documents

Read all supplied documents in scope. Extract distinct statements with a concrete development impact, such as game systems, features, modules, rules, state changes, content and data requirements, integrations, configuration and testable constraints. Skip business goals, positioning, desired KPIs and other product commentary unless the source explicitly calls for corresponding development work or defines a testable constraint on the software. For example, a retention target alone supplies no telemetry, tuning or acceptance requirement.

Combine duplicate statements and retain their source locators. Treat source items fully covered by existing confirmed decisions as processed. Surface any material project difference without asking for the same decision again. Present the remaining proposals as short, faithful formulations in batches of ten, with a smaller last batch if fewer remain. Give each proposal a stable reference for replies, the relevant document and section or page, and material findings from the project or stack. Give each label one concrete meaning per proposal:

- **А** — accept the stated requirement and its development scope as presented.
- **Б** — accept a clearly stated adjustment, or take the item into a focused discussion if the adjustment still needs a decision.
- **В** — leave the item out of this PRD, or defer it when the batch explicitly says so.

These are dispositions for source proposals. Reconcile items with prior decisions and flag contradictions before seeking confirmation. If an item depends on an unresolved choice, show the concrete gap and leave the item pending until that choice is resolved, even if the user selects **А**. Resume the source batches after any focused questions needed to process a passage. Keep the other batch answers and pending items. After processing all documents, review the complete collected set for gaps before the general interview. Keep unresolved source items visible to the reviewers.

## Question-and-answer session

Number the first question **1**. Increment by one for every new question in the same Requirements session, across rounds, document-related interruptions, follow-up reviews and resumption. Keep a pending question's original number when repeating or withdrawing it. Give document items separate references, such as document and section with an item number, so source dispositions and question answers cannot collide.

Ask five independent questions per round, or fewer if fewer material decisions remain. Put a prerequisite question before any question whose options depend on its answer. Use existing decisions and delegated choices to reduce the number of questions. For each question, show the decision in one sentence, then any project evidence or consequence needed to choose. Use these labels and roles:

- **А** — the recommended option for the current project and verified stack. Explain why it fits.
- **Б** — a project-specific alternative that may work better under a stated condition. Name the required change or refactor and its tradeoff when applicable.
- **В** — a materially different approach that rethinks an assumption, boundary or solution. Explain its tradeoff and prerequisites.

Use three distinct, plausible choices for a decision that supports them. If a role has no credible option, show the actual choice with the applicable labels and explain a missing current-stack route when relevant. A free-text answer can supply a value, correction or approach that the options cannot express. Invite replies by number, for example `1 — А, 2 — В`. Retain partial answers. A request for explanation leaves the decision open. When an answer is ambiguous, ask only about the unresolved meaning. If new evidence removes the need for a pending question, mark it withdrawn and preserve independent answers.

Apply decisions within explicitly delegated authority and record the actor and scope. Ask the responsible actor about unresolved choices outside that authority. Use the answers to update the collected requirements and pending items. When there are no more material questions, start the implementation-readiness review. Continue the same numbering if its findings reopen the interview.
