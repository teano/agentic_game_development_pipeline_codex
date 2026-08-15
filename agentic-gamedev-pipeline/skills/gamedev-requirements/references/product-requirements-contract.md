# Product requirements contract

## Canonical location

The repository owns the PRD location and namespace. Resolve one path from explicit user context, repository instructions, feature manifests/indexes, existing feature artifacts, or an unambiguous sibling specification. Keep it inside `<project-root>`, preserve path case, and maintain exactly one canonical PRD. Never duplicate, symlink, move, or rename project documents solely to satisfy this skill bundle.

If the repository is empty and defines no layout, recommend `<project-root>/docs/features/<feature>/product-requirements.md` with a sibling `technical-specification.md` as a proposed default. Do not create the proposed layout until the user confirms it. Keep canonical documents version-controlled and runtime evidence in the repository-defined evidence area.

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

An identifier is declared only by an exact literal list row in its canonical
section: `- PRD-REQ-001: plain-text description` under Functional Requirements,
`- PRD-NFR-001: plain-text description` under Quality Requirements, or
`- PRD-OQ-001: plain-text description` under Open Questions. The `- ` marker,
literal ID, `: ` delimiter, and non-empty plain-text description are mandatory;
indentation, alternate/numbered markers, bare IDs, code-wrapped IDs, empty
descriptions, GFM emphasis/strikethrough or other inline Markdown, and prose
beginning with the ID are invalid inventory rows.
References outside the canonical section do not declare or duplicate the
identifier. Blocking status is read only from a canonical `PRD-OQ-*`
declaration.

The one structural exact `## Acceptance Criteria` H2 is the sole acceptance-authority inventory. Declare every criterion as one literal list row in exact `- PRD-AC-ID: plain-text description` form. Code-wrapped IDs, hidden declarations, duplicate IDs, and range shorthand are invalid authority. References outside this section do not declare acceptance IDs. Legacy declaration grammar changes remain a controlled PRD revision requiring PRD reapproval and downstream hash reconvergence.

Mark a blocking open question in its description, for example
`- PRD-OQ-001: [blocking] choose the launch platform`. An approved PRD may
contain only non-blocking open questions.

## Content boundary

Record what the product must achieve and what observable behavior proves it. Exclude implementation plans, class structures, speculative architecture, agent activity, raw interview transcripts, and discarded ideas unless they become an explicit constraint or non-goal.

## Approval and changes

- Keep the file in `draft` until the user explicitly approves it.
- Validate before and after approval.
- Record the exact-byte SHA-256 at handoff time; do not embed a self-referential hash inside the PRD.
- Reopen an approved PRD before any semantic edit by incrementing `revision`, setting `status: draft`, and clearing `approved_at`.
- Treat every technical specification built from an older PRD hash as stale.
- Emit `PRD_READY` only after explicit user approval and successful `--require-approved` validation on the same bytes. Return `NEXT_ACTION: $gamedev-specification` and stop; the Requirements stage never starts specification work.
