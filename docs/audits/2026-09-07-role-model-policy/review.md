# Independent role model policy review

Verdict: PASS after one bounded correction. No unresolved material findings in the seven changed instruction files. This review does not certify model quality, active agent settings, or game readiness.

## Scope and evidence

Reviewed the frozen Requirements and Specification entrypoints, Specification contract, Development Plan entrypoint, runtime entrypoint, shared handoff invariant, and new shared agent model policy. Exact final SHA-256 values and static results are in [review-evidence.json](review-evidence.json). The final policy SHA-256 is `202704d595b8874919565aae80f829de3baddfe4a93ed1ed7d093c85f8a138b5`.

Read the OpenAI Docs skill and followed the higher-priority local/tool-metadata-first requirement. Available tool declarations in this review session are authoritative for callable model identifiers, effort combinations, fork restrictions, and argument names. No pricing or benchmark conclusion is made.

- All four stage entrypoints directly link to the shared policy. Engineer, Review, QA, Docs, and standalone Coverage Advisory reach it through their existing required handoff invariant. All nine routes resolve to existing files.
- Parsed `pipeline_v2/model.py` using Python AST: its six actual role aliases each occur in exactly one policy row. The existing `assignment_identity` explicitly rejects `ready`; the new policy preserves that boundary. Coverage Advisory remains explicit-only and outside runtime assignments.
- All 19 startup/role table rows use combinations supported by current callable metadata. Internal `spawn_agent` dispatch specifies `fork_turns: "none"`, `model`, and `reasoning_effort`; the Engineering JSON example uses actual supported argument names. `followup_task` and `send_message` expose no model-switch fields.
- Requirements research/review remain optional persistent lanes. Specification Architect persistence, fresh Proofreader identities, helper ownership, and controller-authorized turnover remain intact. Planning preserves fresh Analyst requirements. Runtime preserves fresh assignment workers and same-worker output-format repairs.
- Explicit user choices and scoped parent constraints retain their provenance and scope. An existing Director model or a configured UI/global default alone does not select child models. Stage startup recommendations do not claim to switch the running Director.
- External helper semantic review, post-fix verification, research, correction, and recovery carry the effective pair in a supplemental execution packet. No immutable helper request/result field, helper topology, external skill file, or extra review wave is added.
- Recovery and context turnover do not introduce an automatic expensive fallback, duplicate owner, replacement authority, or controller reinitialization merely to apply model defaults.
- The combined tracked source diff contains six Markdown instruction files plus the new shared policy. Controller code, schemas, game projects, global settings, and external helper implementation are unchanged. Final `git diff --check` passes. Author-reported focused checks were 5 Requirements instruction tests, 10 invariant tests, and four entrypoint skill validations; these existing checks were not redundantly rerun by this reviewer.

## Resolved finding

R1 (P2): the draft app-task paragraph required an explicit role-default `model` for every user-authorized new task. Actual `create_thread` metadata instead requires omitting `model` unless the user explicitly selected that model. The author corrected only that paragraph: new task overrides now follow actual explicit user choices, stage recommendations are not user choices, and existing task settings are preserved. Independent reread and final byte comparison confirm the correction; internal collaboration role pins remain intact.

## Existing-run contract impact

Read-only evaluation of the current `pipeline_runtime_digest()` and the same fixed manifest with HEAD bytes gives:

- HEAD: `85bea71dee8a50134046d22a29c0f112cbb63a0fe7c69aea82a0e9073ee89017`
- Worktree: `9ef024daf6dfe5dd4af94d3066da5665379ff0d3096adeb151a262a0647d73af`

The changed runtime SKILL and invariant already belong to that manifest, so adopting these bytes changes the runtime binding. Existing `runner.py` guards reject a mismatched loaded binding and an active assignment under a changed runtime; ordinary existing recovery rules still govern any later operator-authorized continuation. No running game was inspected, stopped, migrated, reinitialized, or resumed during this review.

The new model-policy reference itself is outside the fixed production manifest. These model execution settings are instruction-level defaults rather than new controller authority or recorded proof of effective model selection. Adding backend enforcement or a new manifest entry is outside this bounded change.

## Limits

Static routing and callable metadata prove that the instructions are reachable and the specified pairs can be requested. No new role worker was launched for a model experiment, no paid benchmark was run, and no effective model/effort telemetry was verified. Quality and cost suitability remain workload-based judgments, not measured regressions or improvements.
