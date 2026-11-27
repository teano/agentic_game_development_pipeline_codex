---
name: gamedev-review
description: Explicit-invocation only. Review an implementation candidate independently against the assigned original requirements and concrete regression risks. Use for `$gamedev-review` or a delegated implementation review.
---

# GameDev Independent Review

Use the [independent checker procedure](../gamedev-qa/SKILL.md) for the issued target and permissions. Inspect original criteria, the actual changes and their proof; return actionable evidenced defects for repair without product edits. A code-only review establishes only its inspected scope. Full implementation acceptance additionally requires the assigned runtime observations and final integrated interaction.

For a development slice the implementation orchestrator can use one checker for review and runtime QA, or issue a separate review for a concrete risk. The final architecture review has its own independent reviewer.

For a changed boundary, use the project's applicable rules and the
[architecture review baseline](../gamedev-pipeline/references/architecture-review.md)
to inspect the real route and diff.

## Final architecture review

Review the entire integrated feature against the [pipeline architecture criteria](../gamedev-pipeline/references/architecture-review.md) and the project's applicable rules, including nested instructions for affected paths. Compare the feature base with the delivered tree. Inspect new files, moves and the surrounding callers, state owners and composition points needed to understand the change. Use the relevant project conventions and approved design even if individual slices passed. Keep product files read-only.

Report the candidate identity, rules applied, and either acceptance or findings to the implementation orchestrator. For each defect identify the file or symbol, the applicable rule or violated responsibility, the concrete consequence and what would resolve it. Keep optional improvements separate. Use existing gameplay evidence when relevant; the gameplay checker owns the integrated playthrough. On follow-up, use your prior findings and the intervening diff, inspect the actual repairs and affected integrations, and give a new verdict on that candidate. The orchestrator assigns the engineers who make the changes.
