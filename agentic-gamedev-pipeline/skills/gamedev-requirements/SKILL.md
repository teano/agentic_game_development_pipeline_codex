---
name: gamedev-requirements
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-requirements` or an active, explicitly invoked `$gamedev-pipeline` Director delegates this stage. Produce and validate one canonical game-feature PRD and `PRD_READY`. Do not activate for ordinary requirements discussion or generic planning.
---

# GameDev Requirements

## Activation gate

Proceed only on the explicit activation described above. Missing requirements, ambiguity, a game-design discussion, or an existing feature document is not authorization. Do not activate another GameDev stage.

Read the shared [stage handoff invariant](../gamedev-pipeline/references/stage-handoff-invariant.md). Act as product requirements facilitator; keep product decisions separate from technical design and implementation.

Before creating, approving, or structurally editing a PRD, read [product-requirements-contract.md](references/product-requirements-contract.md). It is the canonical path, schema, content-boundary, and approval contract; do not restate or override it here.

## Resolve product decisions

1. Match the user's language. Resolve the project root, lowercase feature slug, and canonical PRD through the contract. Ask one blocking path question only when resolution remains ambiguous.
2. Read an existing PRD before interviewing. Preserve stable IDs and epistemic state; do not replace it without explicit approval.
3. For authorized file-backed work with no PRD, copy [product-requirements.md](assets/product-requirements.md), set the language, and keep `status: draft`. For discussion-only work, write no file.
4. Ask one compact round of one to five related highest-impact unanswered questions. Group them under the product decision they resolve, preserve and reuse every prior or partial answer, and do not repeat an unchanged answered question. The user may answer any subset or reply free-form; the next round asks only the still-material remainder. Cover only relevant outcome, audience, core loop, scope/non-goals, release/platform constraints, observable states/failures/recovery, UX/quality constraints, integrations/operations, risks, and build-verifiable acceptance.
5. When alternatives would materially help a decision, offer two or three concise options with their tradeoffs. Ground every option in supplied user intent, the existing PRD, or inspected repository/product evidence and name that grounding. Label options as proposals, allow a free-form alternative, and do not invent product facts, constraints, preferences, or a recommended solution merely to fill the set.
6. Separate confirmed requirements, proposals, assumptions, open questions, risks, and exclusions. An unanswered question or unaccepted proposal never becomes a confirmed requirement. Surface contradictions before normative edits; keep architecture out unless the user confirms it as a product or delivery constraint.
7. Update only affected sections. Preserve stable IDs. Repeating the stage with unchanged PRD bytes and no new user information must reproduce the same pending question round without a semantic edit, new IDs, or revision increment. Do not store transcripts, rejected ideas, or agent reasoning.

Before a semantic edit to an approved PRD, increment `revision` once, set `status: draft`, and clear `approved_at`. Further edits in that draft keep the same revision.

## Complete the stage

Recommend approval only when the product outcome, core loop, release target, blocking scope/platform choices, and observable acceptance criteria are stable. Remaining questions must be explicitly non-blocking. Only the user may approve.

Run `scripts/validate_product_requirements.py <path>` before approval. After explicit approval, set approved metadata, rerun with `--require-approved`, and record the exact-byte SHA-256. A later semantic PRD change invalidates downstream trace credit.

The validator requires exact canonical list declarations: `- PRD-REQ-001: plain-text description`, `- PRD-NFR-001: plain-text description`, `- PRD-OQ-001: plain-text description`, and `- PRD-AC-ID: plain-text description` in their respective authority sections. Alternate markers, missing list markers, non-exact delimiters, bare IDs, code-wrapped IDs, and empty or Markdown-rendered descriptions are invalid inventory; references outside those sections remain non-authoritative. Migrating an already approved legacy declaration is a controlled PRD revision: reopen and increment the PRD, obtain fresh PRD approval, then reconverge and freshly approve downstream SPEC/PLAN exact hashes before runtime.

Return only:

- `PRD_READY: yes|no`, canonical path, status, revision, and exact SHA-256 when ready;
- changed IDs and affected assumptions/questions;
- the next blocking question or reason the gate is not ready;
- `NEXT_ACTION: $gamedev-specification` when `PRD_READY: yes`, otherwise `NEXT_ACTION: user-decision` or `NEXT_ACTION: $gamedev-requirements`.

`NEXT_ACTION` is advisory routing data. Do not invoke or delegate the next stage; stop after returning the handoff.
