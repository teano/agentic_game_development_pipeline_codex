# Product requirements contract

## Canonical location

Use `<project-root>/docs/features/<feature>/product-requirements.md`, where `<feature>` is a lowercase hyphenated slug. Maintain one canonical PRD and one traced `technical-specification.md` per feature directory. Keep both documents version-controlled; do not store runtime test evidence beside them.

## Frontmatter

Use exactly these machine-readable keys:

```yaml
---
document_type: product-requirements
status: draft
revision: 1
language: Russian
approved_at: null
---
```

- `status` is `draft` or `approved`.
- `revision` is a positive integer. Increment it once when reopening an approved PRD.
- `language` names the natural language used in human-facing content.
- `approved_at` is `null` for drafts and an ISO-8601 UTC timestamp for approved revisions.

## Required structure

```text
# Product Requirements
## Product Outcome
## Target Audience
## Core Gameplay Loop
## Release Target
## Scope
### In Scope
### Out of Scope
## Functional Requirements
## Quality Requirements
## Acceptance Criteria
## Assumptions
## Open Questions
## Risks
```

Use stable identifiers:

- `PRD-REQ-001` for functional product requirements;
- `PRD-NFR-001` for measurable quality requirements;
- `PRD-AC-001` for acceptance criteria;
- `PRD-OQ-001` for open questions.

Mark a blocking open question with `[blocking]` on the same line as its `PRD-OQ-*` ID. An approved PRD may contain only non-blocking open questions.

## Content boundary

Record what the product must achieve and what observable behavior proves it. Exclude implementation plans, class structures, speculative architecture, agent activity, raw interview transcripts, and discarded ideas unless they become an explicit constraint or non-goal.

## Approval and changes

- Keep the file in `draft` until the user explicitly approves it.
- Validate before and after approval.
- Record the exact-byte SHA-256 at handoff time; do not embed a self-referential hash inside the PRD.
- Reopen an approved PRD before any semantic edit by incrementing `revision`, setting `status: draft`, and clearing `approved_at`.
- Treat every technical specification built from an older PRD hash as stale.
