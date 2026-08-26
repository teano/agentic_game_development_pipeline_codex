---
name: gamedev-requirements
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-requirements` or an active, explicitly invoked `$gamedev-pipeline` Director delegates this stage. Produce and validate one canonical game-feature PRD and `PRD_READY`. Do not activate for ordinary requirements discussion or generic planning.
---

# GameDev Requirements

## Activation gate

Proceed only on the explicit activation described above. Missing requirements, ambiguity, a game-design discussion, or an existing feature document is not authorization. Do not activate another GameDev stage.

Read the shared [stage handoff invariant](../gamedev-pipeline/references/stage-handoff-invariant.md). Act as product requirements facilitator; keep product decisions separate from technical design and implementation.

Before creating, approving, or structurally editing a PRD, read [product-requirements-contract.md](references/product-requirements-contract.md). It is the canonical path, schema, content-boundary, and approval contract; do not restate or override it here.

## Explicit-confirmation gate

The PRD is a record of user-confirmed product decisions, not an agent-authored design draft. Except for required frontmatter, headings, stable IDs, and faithful wording/placement of confirmed content, write nothing semantic that the user has not explicitly confirmed.

Treat a statement as confirmed only when the user:

- states the decision directly;
- selects one clearly bounded option;
- answers `yes`/equivalent to exactly one immediately preceding, explicitly worded proposal; or
- explicitly approves the exact current PRD revision.

Repository evidence, common practice, feasibility analysis, an existing draft line, agent reasoning, silence, or permission to continue are not confirmation. A short `yes` after a message containing multiple independently choosable proposals is ambiguous and authorizes no semantic edit; split the bundle into separate questions.

Before every semantic PRD write, perform an internal sentence-level confirmation audit. Each added or changed statement must map to the exact user statement or selected option that supports it. The mapping may justify a faithful paraphrase or a mechanically equivalent acceptance check, but never an added default, owner, API, type list, lifecycle rule, failure behavior, edge case, validation rule, limit, platform mapping, implementation detail, or other independently choosable consequence. If any part lacks support, leave it out of the PRD and ask the user.

Agent-originated proposals, assumptions, open questions, risks, exclusions, examples, and candidate acceptance criteria stay in chat until the user explicitly confirms that exact content for the PRD. The required `Assumptions`, `Open Questions`, and `Risks` sections may remain empty. Labels such as `proposal`, `assumption`, `risk`, `optional`, or `PRD-OQ-*` never substitute for confirmation.

## Resolve product decisions

1. Match the user's language. Resolve the project root, lowercase feature slug, and canonical PRD through the contract. Ask one blocking path question only when resolution remains ambiguous.
2. Read an existing PRD before interviewing. Preserve stable IDs and epistemic state; do not replace it without explicit approval.
3. For authorized file-backed work with no PRD, copy [product-requirements.md](assets/product-requirements.md), set the language, and keep `status: draft`. For discussion-only work, write no file.
4. Ask one compact round of one to five related highest-impact unanswered questions. Each numbered question resolves one independently choosable decision; never hide several decisions behind one yes/no prompt. Preserve and reuse every prior or partial answer, and do not repeat an unchanged answered question. The user may answer any subset or reply free-form; the next round asks only the still-material remainder. Cover only relevant outcome, audience, core loop, scope/non-goals, release/platform constraints, observable states/failures/recovery, UX/quality constraints, integrations/operations, risks, and build-verifiable acceptance.
5. Whenever the agent has a proposal or recommendation, express it only as a question with two or three concise, mutually exclusive options and their tradeoffs. Put a grounded recommendation first when one exists, label it as a proposal, allow a free-form alternative, and state what evidence supports it. Do not invent an option, product fact, constraint, preference, or recommendation merely to fill the set. Do not write any option to the PRD before the user selects it.
6. Separate confirmed requirements from all unconfirmed material in chat, not by storing agent-created uncertainty in the PRD. An unanswered question, unaccepted proposal, inferred risk, assumed exclusion, or suggested acceptance criterion remains outside the artifact. Surface contradictions before normative edits; keep architecture out unless the user confirms it as a product or delivery constraint.
7. Update only affected sections. Preserve stable IDs. Repeating the stage with unchanged PRD bytes and no new user information must reproduce the same pending question round without a semantic edit, new IDs, or revision increment. Do not store transcripts, rejected ideas, or agent reasoning.

Before a semantic edit to an approved PRD, increment `revision` once, set `status: draft`, and clear `approved_at`. Further edits in that draft keep the same revision.

## Complete the stage

Recommend approval only when the product outcome, core loop, release target, blocking scope/platform choices, and observable acceptance criteria are stable. Remaining questions must be explicitly non-blocking. Only the user may approve.

Run `scripts/validate_product_requirements.py <path>` before approval. After explicit approval, set approved metadata, rerun with `--require-approved`, and record the exact-byte SHA-256. A later semantic PRD change invalidates downstream trace credit.

The validator checks structure, not user consent. Before validation and again before approval, rerun the explicit-confirmation audit over every semantic line. If provenance is missing or one confirmation was expanded into additional decisions, keep `PRD_READY: no`, remove the unsupported additions from the proposed edit, and ask the next bounded option question.

The validator requires exact canonical list declarations: `- PRD-REQ-001: plain-text description`, `- PRD-NFR-001: plain-text description`, `- PRD-OQ-001: plain-text description`, and `- PRD-AC-ID: plain-text description` in their respective authority sections. Alternate markers, missing list markers, non-exact delimiters, bare IDs, code-wrapped IDs, and empty or Markdown-rendered descriptions are invalid inventory; references outside those sections remain non-authoritative. Migrating an already approved legacy declaration is a controlled PRD revision: reopen and increment the PRD, obtain fresh PRD approval, then reconverge and freshly approve downstream SPEC/PLAN exact hashes before runtime.

Return only:

- `PRD_READY: yes|no`, canonical path, status, revision, and exact SHA-256 when ready;
- changed IDs and affected assumptions/questions;
- the next blocking question or reason the gate is not ready;
- `NEXT_ACTION: $gamedev-specification` when `PRD_READY: yes`, otherwise `NEXT_ACTION: user-decision` or `NEXT_ACTION: $gamedev-requirements`.

`NEXT_ACTION` is advisory routing data. Do not invoke or delegate the next stage; stop after returning the handoff.
