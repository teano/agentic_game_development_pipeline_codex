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

1. Match the user's language. Resolve the project root, lowercase `FEATURE` slug, exact `WORKFLOW_PATH=.agentic-pipeline/Workflows/<feature>`, and canonical PRD through the contract. Requirements creates no state there and never inspects a sibling workflow. Ask one blocking path question only when resolution remains ambiguous.
2. Read an existing PRD before interviewing. Preserve stable IDs and epistemic state; do not replace it without explicit approval.
3. For authorized file-backed work with no PRD, copy [product-requirements.md](assets/product-requirements.md), set the language, and keep `status: draft`. For discussion-only work, write no file.
4. Ground discovery strictly in the active task, the actual detected project stack, current repository instructions and conventions, the current PRD, and only the source evidence needed to ask or verify a material question. Do not run an abstract checklist, broaden discovery, or suggest patterns from a foreign stack.
5. Ask one compact round of up to five related highest-impact unanswered questions. Five is a ceiling, not a quota. If the user asks for clarification, or one prerequisite or conflict blocks the remaining decisions, resolve that first, often with one question. Each numbered question resolves one independently choosable decision; never hide several decisions behind one yes/no prompt. Preserve every prior or partial answer, do not repeat an unchanged answered question, and ask only the still-material remainder.
6. Parse each numbered answer independently. Free text applies only to its corresponding question and overrides shorthand for that question; it does not silently answer, amend, or approve another question. A request for clarification is not an answer or option selection; explain only that question and wait for its answer. For an ambiguous or contradictory answer, apply the contract's ambiguity rule only to that question, preserve unaffected answers, and ask its smallest blocking clarification before editing it.
7. Express any proposal only as a question with concise options and their tradeoffs. If a current-project-grounded expert recommendation exists, place it first. Include only useful project-relevant best-practice alternatives or materially simpler alternatives that actually apply. Never invent a recommendation or alternatives to reach an option count. Do not force mutual exclusivity when valid choices can combine or treat any displayed option as authority until the user selects it.
8. Update only affected sections under the contract. Preserve stable IDs. Repeating the stage with unchanged PRD bytes and no new user information must reproduce the same pending question round without a semantic edit, new IDs, or revision increment. Do not store transcripts, rejected ideas, or agent reasoning.

Stop discovery as soon as all material product decisions and the completeness, feasibility, and testability gate are closed. Do not continue looking for optional improvements.

## Conditional read-only lanes

Requirements sessions need not spawn subagents. Use persistent, reusable, read-only lanes only when nontrivial research or review is required or the user explicitly requests delegation. When such work is required and collaboration is available, offload it from the root context through the smallest useful set of lanes.

Allow every started lane to finish or to checkpoint and hand off under the shared stage handoff invariant. Do not cancel and restart lanes per answer. The root must consume every terminal lane result before requesting approval or reporting readiness.

The root Requirements agent alone interprets user decisions, edits the canonical PRD, and requests or records approval. Research and review results are evidence, not decision authority.

For context checkpoint and handoff behavior, follow the shared [stage handoff invariant](../gamedev-pipeline/references/stage-handoff-invariant.md) instead of restating its thresholds. A Requirements checkpoint adds only the canonical PRD path and current metadata, confirmed decisions already incorporated, pending blocking decisions, unconsumed lane results, and the exact next question or action needed to continue.

## Complete the stage

Apply the contract's semantic completeness and exact-current-revision approval gate. Run `scripts/validate_product_requirements.py <path>` before requesting approval, and use its post-approval same-byte procedure before reporting readiness.

The validator requires exact canonical list declarations: `- PRD-REQ-001: plain-text description`, `- PRD-NFR-001: plain-text description`, `- PRD-OQ-001: plain-text description`, and `- PRD-AC-ID: plain-text description` in their respective authority sections. Alternate markers, missing list markers, non-exact delimiters, bare IDs, code-wrapped IDs, and empty or Markdown-rendered descriptions are invalid inventory; references outside those sections remain non-authoritative. Migrating an already approved legacy declaration is a controlled PRD revision: reopen and increment the PRD, obtain fresh PRD approval, then reconverge and freshly approve downstream SPEC/PLAN exact hashes before runtime.

During discovery, report only concrete important new decisions, blockers, evidence, and the next material question. Do not require revision, ID, or SHA boilerplate in an interim response.

At terminal handoff, return only:

- `PRD_READY: yes|no`, canonical path, status, revision, and exact SHA-256 when ready;
- exact `FEATURE` and `WORKFLOW_PATH=.agentic-pipeline/Workflows/<feature>`;
- changed IDs and affected assumptions/questions;
- the next blocking question or reason the gate is not ready;
- `NEXT_ACTION: $gamedev-specification` when `PRD_READY: yes`, otherwise `NEXT_ACTION: user-decision` or `NEXT_ACTION: $gamedev-requirements`.

`NEXT_ACTION` is advisory routing data. Do not invoke or delegate the next stage; stop after returning the handoff.
