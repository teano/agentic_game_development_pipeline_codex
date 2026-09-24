---
name: gamedev-requirements
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-requirements` or an active, explicitly invoked `$gamedev-pipeline` Director delegates this stage. Produce and validate one canonical game-feature PRD and `PRD_READY`. Do not activate for ordinary requirements discussion or generic planning.
---

# GameDev Requirements

When the caller supplies `control_binding`, first apply the shared [control-return contract](../gamedev-pipeline/references/control-return.md). Keep semantic JSON and native stage handoffs unchanged; wrap only the requested return. A bounded caller task performs only its stated existing-role work, without automatic stage restart or approval. Standalone user calls retain their existing public result.

## Activation gate

Proceed only on the explicit activation described above. Missing requirements, ambiguity, a game-design discussion, or an existing feature document is not authorization. Do not activate another GameDev stage.

Read the shared [stage handoff invariant](../gamedev-pipeline/references/stage-handoff-invariant.md). Act as product requirements facilitator; keep product decisions separate from technical design and implementation.

Read the shared [technical decisions contract](../gamedev-pipeline/references/technical-decisions.md) on initial entry, repeated discovery, upstream return, and context recovery. Resolve only the selected feature's current journal through its public controller view. Give the root and each bounded research/review lane the relevant current records and source binding; refresh those inputs when reusing a lane after a record changes. Journal situations and checks are feasibility evidence for material questions, not product decisions. Never copy an Engineering choice, workaround, or technical override into product authority merely because it worked. Require direct confirmation of that exact product content or an actual decision by the explicitly delegated product owner under the shared authority contract. A changed technical record alone causes no PRD edit, new ID, revision increment, or stage activation.

When a journal blocker requires a product decision or the approved technology cannot achieve the product goal, preserve the user's selected route: an explicitly authorized local amendment with its exact affected content, or return to the named owning stage for structural revision. Do not turn the local option into an automatic full-stage rewind. When canonical PRD bytes must change, the Requirements owner still uses the normal current-revision approval gate. On handoff, include only relevant current records, unresolved user choices, their provenance and the exact chosen route, never superseded record text.

Read the Requirements rows and dispatch rules in the shared [agent model policy](../gamedev-pipeline/references/agent-model-policy.md). Apply its role defaults only where no explicit user or scoped parent override exists; session-start guidance does not change the running session's model.

Before creating, approving, or structurally editing a PRD, read [product-requirements-contract.md](references/product-requirements-contract.md). It is the canonical path, schema, content-boundary, and approval contract; do not restate or override it here.

## Resolve product decisions

First establish direct-confirmation or explicitly delegated decision/approval mode under the shared authority contract. The interview steps below apply to material choices still owned by the user. In a valid autonomous delegation, make and record the scoped decisions instead of asking those questions; retain exact-revision validation and the actual approver identity. A no-questions preference alone supplies no missing authority. Under delegated autonomy, choose the smallest release scope that satisfies the requested outcome. Assess verification cost when selecting defaults: additional platforms, input combinations and numeric quality thresholds need a product reason, not generic completeness. Preserve explicit user requirements; later verification difficulty does not silently waive approved scope.

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

For each initial or legitimately replaced lane, resolve its model and reasoning effort from that policy and call `spawn_agent(..., fork_turns="none", model=<resolved-model>, reasoning_effort=<resolved-effort>)`. Without an override, use `model="gpt-6-sol", reasoning_effort="high"` for bounded repository research and `model="gpt-6-sol", reasoning_effort="high"` for semantic requirements review. Give it a bounded source-backed packet with the resolved pair and applicable overrides. Reuse the same lane with `followup_task`, which retains its model and effort; do not invent model parameters on that tool or replace a lane solely to apply a default. Preserve the assigned pair and override scope through checkpoint, handoff, and recovery.

Allow every started lane to finish or to checkpoint and hand off under the shared stage handoff invariant. Do not cancel and restart lanes per answer. The root must consume every terminal lane result before requesting approval or reporting readiness.

The root Requirements agent alone interprets user decisions, edits the canonical PRD, and requests or records approval. Research and review results are evidence, not decision authority.

For context checkpoint and handoff behavior, follow the shared [stage handoff invariant](../gamedev-pipeline/references/stage-handoff-invariant.md) and its useful-working-set policy. A Requirements checkpoint adds only the canonical PRD path and current metadata, confirmed decisions already incorporated, pending blocking decisions, unconsumed lane results, and the exact next question or action needed to continue.

## Complete the stage

Apply the contract's semantic completeness and exact-current-revision approval gate. Run `scripts/validate_product_requirements.py <path>` before requesting approval, and use its post-approval same-byte procedure before reporting readiness.

The validator requires exact canonical list declarations: `- PRD-REQ-001: plain-text description`, `- PRD-NFR-001: plain-text description`, `- PRD-OQ-001: plain-text description`, and `- PRD-AC-ID: plain-text description` in their respective authority sections. Alternate markers, missing list markers, non-exact delimiters, bare IDs, code-wrapped IDs, and empty or Markdown-rendered descriptions are invalid inventory; references outside those sections remain non-authoritative. Migrating an already approved legacy declaration is a controlled PRD revision: reopen and increment the PRD, obtain fresh PRD approval, then reconverge and freshly approve downstream SPEC/PLAN exact hashes before runtime.

During discovery, report only concrete important new decisions, blockers, evidence, and the next material question. Do not require revision, ID, or SHA boilerplate in an interim response.

At terminal handoff, return these existing fields unchanged, as `task_result.payload` when a caller binding is supplied or directly for a standalone call:

- `PRD_READY: yes|no`, canonical path, status, revision, and exact SHA-256 when ready;
- exact `FEATURE` and `WORKFLOW_PATH=.agentic-pipeline/Workflows/<feature>`;
- changed IDs and affected assumptions/questions;
- the next blocking question or reason the gate is not ready;
- `NEXT_ACTION: $gamedev-specification` when `PRD_READY: yes`, otherwise `NEXT_ACTION: user-decision` or `NEXT_ACTION: $gamedev-requirements`.

`NEXT_ACTION` is advisory routing data. Do not invoke or delegate the next stage; stop after returning the handoff.
