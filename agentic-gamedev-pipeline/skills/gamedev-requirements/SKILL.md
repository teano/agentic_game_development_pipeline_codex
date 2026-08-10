---
name: gamedev-requirements
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-requirements` by name, explicitly asks for the Agentic GameDev Pipeline requirements mode, or an explicitly user-invoked `$gamedev-pipeline` delegates PRD validation. Interview for and maintain one canonical game-feature PRD before specification or implementation. Do not infer activation from missing, incomplete, or contradictory requirements or from a generic request to plan a game feature.
---

# GameDev Requirements

## Activation gate

Proceed only when the current user explicitly requests `$gamedev-requirements` by name, clearly asks for the Agentic GameDev Pipeline requirements mode, or this is a delegated PRD-validation step from an active `$gamedev-pipeline` that the user explicitly invoked. Missing requirements, ambiguity, a game-design discussion, or the presence of a feature document is not authorization. If this gate is not satisfied, do not create, validate, approve, or hand off a pipeline PRD; continue under ordinary instructions and only other explicitly requested skills.

Act as product requirements facilitator. Keep product decisions separate from technical design and implementation.

Before creating, approving, or structurally editing a PRD, read [product-requirements-contract.md](references/product-requirements-contract.md).

## Resolve the canonical document

1. Match the user's language and infer the project root and lowercase feature slug. Ask one blocking question only when either is unsafe to infer.
2. Resolve the repository-owned PRD path from, in order: an explicit current-user path; repository instructions and feature manifests/indexes; an existing PRD; or the sibling of an unambiguous feature specification. Preserve spelling and case. Never create a copy, symlink, move, or parallel namespace merely to fit this plugin.
3. If several plausible paths remain, ask the user one concise path question. If the project is empty and has no convention to infer, recommend `docs/features/<feature>/product-requirements.md` plus a sibling `technical-specification.md`, explain that it is only a proposed layout, and wait for confirmation before creating it.
4. Read an existing PRD before interviewing. Preserve its stable IDs and epistemic state; do not replace it without explicit approval.
5. For authorized file-backed work with a resolved path and no PRD, copy [product-requirements.md](assets/product-requirements.md), set the language, and keep `status: draft`. For discussion-only requests, do not write files.

## Resolve product decisions progressively

Ask one highest-impact unanswered question at a time and reuse existing answers. Cover only relevant areas:

- player/product outcome, audience, and use context;
- core loop, progression, content scope, and non-goals;
- release level, platforms, engine, input, distribution, and connectivity;
- observable states, failures, saving, recovery, and determinism;
- UX, accessibility, localization, and measurable quality constraints;
- dependencies, integrations, data sensitivity, operations, assumptions, and risks;
- acceptance criteria verifiable from a build.

Separate confirmed requirements, proposals, assumptions, open questions, risks, and exclusions. Surface contradictions before writing normative text. Keep architecture out unless the user confirms it as a product or delivery constraint.

Update only affected sections. Never renumber stable IDs for presentation. Do not store transcripts, rejected ideas, or agent reasoning.

Before semantically changing an approved PRD, increment `revision` once, set `status: draft`, and clear `approved_at`. Further edits in that draft keep the same revision.

## Approve and hand off

Recommend approval only when outcome, core loop, release target, blocking scope/platform choices, and observable acceptance criteria are stable; remaining questions must be explicitly non-blocking. Approval always requires the user's explicit decision.

Run `scripts/validate_product_requirements.py <path>` before approval. Resolve errors, set approved metadata, rerun with `--require-approved`, and report the exact-byte SHA-256.

When the user requests a technical specification:

1. Require the valid approved PRD.
2. Resolve the repository-owned target specification path by the same rules, normally as the PRD's project-defined sibling; ask only if it remains ambiguous.
3. Invoke `$skill-specification-pipeline` with only the resolved PRD path, revision, SHA-256, resolved target specification path, and instruction to treat the PRD as product authority.
4. Require the specification to record PRD path, revision, and SHA-256 using the repository's existing trace shape.
5. Keep unsupported technical choices as assumptions or open questions; do not invent product requirements.

A later semantic PRD change makes the traced specification stale. Update and re-review it before implementation. Keep both canonical documents tracked; keep runtime evidence under `tests/<feature>/`.

Return only changed IDs, affected assumptions/questions, PRD status/revision, and the next blocking question.
