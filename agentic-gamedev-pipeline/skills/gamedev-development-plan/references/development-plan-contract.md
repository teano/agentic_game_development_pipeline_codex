# Development plan contract

## Canonical authority

Use only the repository-owned PRD, specification, development plan, and append-only decision ledger resolved from explicit user context, repository instructions, feature manifests/indexes, existing artifacts, and unambiguous sibling relationships. All paths must stay inside the project root. Do not create copies, symlinks, moves, or an alternate namespace for the controller. Ask the user if more than one plausible path remains. In an empty repository, recommend `docs/features/<feature>/` with the four sibling artifacts as a proposed layout and wait for confirmation.

Operational state remains at:

- `.agentic-pipeline/specification-state.json` for immutable `SPEC_READY` evidence;
- `.agentic-pipeline/development-plan-state.json` for operational planning state.

Before creating or mutating planning state, the controller runs the complete current approved Requirements validator once at the source-authority boundary and requires exact current schema-2 `SPEC_READY` path/hash evidence. Planning does not migrate schema-1 specification state or grandfather a legacy/malformed PRD or specification handoff; those require controlled upstream revision and reconvergence.

The plan frontmatter must contain the controller fields below. Preserve the repository's established trace representation; flat `source_prd_*` / `source_spec_*` fields and nested `product_authority` / `specification_authority` mappings are equivalent.

```yaml
---
document_type: development-plan
status: draft
revision: 1
feature: <feature>
mode: single_owner
writer_strategy: sequential
planning_analyst_id: <fresh-agent-id>
source_prd_path: <repository-relative-prd-path>
source_prd_revision: <revision>
source_prd_sha256: <64 lowercase hex>
source_spec_path: <repository-relative-spec-path>
source_spec_revision: <revision>
source_spec_sha256: <64 lowercase hex>
decision_ledger_path: <repository-relative-append-only-jsonl-path>
slice_count: 1
---
```

Equivalent nested trace fields are:

```yaml
product_authority:
  path: <repository-relative-prd-path>
  revision: <revision>
  sha256: <64 lowercase hex>
specification_authority:
  path: <repository-relative-spec-path>
  revision: <revision>
  sha256: <64 lowercase hex>
```

Only `single_owner` and `sequential_slices` are valid modes. `writer_strategy` is always `sequential`. It means one active write-capable lease per checkout and one writer per phase/write scope, not one Engineer identity for the lifecycle. The controller adds `approved_by` and `approved_at` only after explicit approval of the submitted draft SHA. `approved_by` records the actual safe 1–64 character actor identity: `user` for direct user approval, or the truthful agent/Director identity when current user authority explicitly delegates technical or process approval. A delegated approval must never be attributed to `user`, and it does not resolve a product choice outside that delegation.

## Analyst decision

Analyze product and technical breadth, estimated files/symbols/tests, context working set, cross-system dependencies, ownership seams, merge/conflict surface, verification cost, documentation outputs, and handoff stability. Prefer `single_owner` whenever production implementation and tightly coupled automated tests fit one bounded engineering scope without context compression.

Use `sequential_slices` only if every slice is independently understandable and produces an observable end-to-end outcome. A later slice may consume a sealed earlier handoff, but writers never overlap. Do not create layer-only slices such as backend, UI, or tests. When boundaries are inseparable, retain one integration owner and add `MILESTONE-*` checkpoints.

Preserve the specification's semantic and responsibility boundaries. Acceptance-ID membership is trace metadata, not proof that a slice implements the criterion. Wildcard paths and budgets bound authorized work; they never merge component responsibilities or replace explicit owner and boundary design.

## Required plan body

Include `Decision`, `Planning Analysis`, `Scope Boundaries`, `Decision Ledger`, `Coverage Strategy`, `Documentation Strategy`, and `Context Budget`. `Decision` must declare `Writer sequencing: one-at-a-time` and `Ownership meaning: phase-scoped write lease`. A `single_owner` plan also includes at least one `MILESTONE-*` under `Integration Milestones`.

`decision_ledger_path` and `Decision Ledger` name one repository-owned append-only JSONL path, active input `DEC-*` IDs (possibly `none`), and the planning-controller internal route for recording already accepted authority. Resolve the path through repository policy/manifests/sibling artifacts; for an empty repository propose `docs/features/<feature>/decision-ledger.jsonl` with the other sibling feature documents and wait for confirmation. A plan may depend only on active accepted entries; it cannot treat an Engineer assumption as a decision. Runtime v2 accepts only the exact authority keys `requirements`, `specification`, and `plan`; it carries accepted answers and remediation findings in controller state and never invokes a Decision Recorder or deferred-findings handler.

`Coverage Strategy` names automated and manual identity namespaces, mandatory acceptance/identity rules, automation feasibility, capability prerequisites, and verification gates. Sole runtime v2 does not create coverage manifests; legacy `manifest_path`, `planned_manifest`, and `finalized_manifest` rows may be read as advisory compatibility data but are optional and confer no controller evidence or write authority. Every `capability_prerequisites` value is a comma-separated canonical lowercase-hyphen ID (`[a-z0-9]+(?:-[a-z0-9]+)*`), never a prose label; the controller uses the exact union of global and slice IDs at preflight and QA. `Documentation Strategy` lists repository-required normative outputs before Review and derived support outputs after QA, or records the exact machine-addressable form `not_required | policy=<exact-reference>`. The corresponding slice Documentation Contract must repeat the same exact policy reference; prose such as “policy evidence” is a template placeholder, not approval evidence.

`Context Budget` contains positive numeric plan-wide ceilings for `max_authority_files`, `max_evidence_files`, `max_total_files`, `max_payload_bytes`, and `max_estimated_tokens`, plus exactly one `metric_scope: capsule_plus_referenced_files` and the deterministic estimation recipe. Every delegated role/slice may set a smaller positive budget. These fields measure capsule JSON plus referenced authority/evidence bytes only, not full system/history/tool context. Missing, repeated, or alternate metric scopes are invalid; a prose-only “bounded” statement is also invalid.

Define each `## Slice SLICE-NNN` with all of these non-empty sections:

- `### Vertical Outcome` with `End-to-end: yes` and `Observable result:`;
- `### Requirements` containing at least one `PRD-REQ-*` and one `PRD-AC-*`;
- `### Dependencies` containing `none` for the first slice or earlier `SLICE-*` IDs;
- `### Base Contract` and `### Handoff Contract`;
- `### Owned Paths` and `### Expected Paths`;
- `### Forbidden Scope`;
- `### Scope Contract` with `acceptance_ids`, `editable_paths`, structured `shared_touchpoint` rows, `excluded_components`, `excluded_paths`, `max_product_files`, `max_product_lines_changed`, and `verification_scope`;
- `### Research Briefs` with either one to three uniquely identified `RESEARCH-*` rows containing the exact runtime-authoritative `question`, `paths`, `exclusions`, `evidence`, and `stop` selectors, or the exact mutually exclusive sentinel `research_not_required | reason=<non-empty source-backed reason>`;
- `### Coverage Contract` with assigned acceptance IDs, automated/manual identity namespaces, explicitly mandatory identities or mandatory derivation IDs, automation feasibility, capability prerequisites, and amendment authorities;
- `### Documentation Contract` with normative pre-Review paths, derived post-QA support paths, decision/evidence sources, and explicit `not_required` rows when applicable;
- `### Context Capsule Budget` with all five positive numeric limits, `metric_scope: capsule_plus_referenced_files`, and bounded `authority_paths`/`evidence_paths`; after approval their deduplicated union is the pipeline controller's sealed per-slice read scope, so every entry must be a canonical project-relative exact path or terminal `dir/**` rule and must not use bare `**`, absolute/parent paths, or other glob syntax;
- `### Verification and Exit Criteria`;
- `### Rollback and Recovery`;
- `### Downstream Consumers`.

Keep paths narrow and use symbols when a shared file is broader than the slice. `Owned Paths` are the expected writes; `Expected Paths` are read/integration surfaces. Shared touchpoints must state the permitted symbol and change kind. Forbidden scope must name adjacent systems and cleanup/refactor work excluded from the slice.

The Scope Contract is machine-readable. Use comma-separated repository-relative paths; a trailing `/**` authorizes a subtree and no other glob syntax is valid. Every shared boundary is a separate row:

```text
- shared_touchpoint: TP-001 | path=src/contracts.lua | symbols=FeatureContract,FeatureConfig | allowed_change=additive fields required by PRD-AC-001 | forbidden_change=ownership, lifecycle, removals
```

Every acceptance assignment uses the same small canonical grammar in Requirements, Planning, and Runtime. The approved PRD has exactly one top-level line `## Acceptance Criteria`; every non-empty line in that section is exactly `- PRD-AC-ID: plain-text description`. IDs are literal, descriptions are visible plain text without emphasis markers, entities, escapes, or inline Markdown, and fenced, quoted, indented, commented, or HTML-block examples grant no authority. Raw `<pre>`, `<script>`, `<style>`, and `<textarea>` blocks close only at their matching end tag; comments, processing instructions, declarations, and CDATA use their own terminators; other HTML blocks are blank-terminated. Code-wrapped IDs, inline HTML/links, narrative rows, multiple IDs in one declaration, and single- or multiline range shorthand are invalid instead of being interpreted by a private Markdown renderer. `Requirements`, Scope, and Coverage name literal inventory IDs; duplicate acceptance rows inside one Requirements surface are invalid, while each slice's Scope/Coverage sets are equal. The union of all slice sets must exactly equal the approved PRD inventory. The same ID may intentionally appear in more than one sequential vertical slice when both slices contribute to the same end-to-end criterion; overlap never substitutes for covering every inventory ID. A format migration is a controlled PRD revision, not an in-place compatibility rewrite: reopen/increment/reapprove PRD, reconverge exact SPEC and PLAN authority, and obtain fresh downstream approvals before runtime.

The exact technical baseline is controller-owned and bound by revision identities, pre-edit receipts, leases, snapshots, and CAS; it is not part of the human-approved plan. `verification_scope` names tests and observations but does not authorize product writes: running a smoke test never expands scope, while changing product code owned by another component does. Every excluded component must have its concrete path represented in `excluded_paths` when such a path exists.

A planned material change uses exactly `planned_material_permission: PF-NNNN | change_type=lifecycle_change|ownership_change|public_contract_change | target_kind=editable_path|shared_touchpoint | target=<exact editable file or TP-NNN> | rationale=<non-empty rationale> | decision_authority=<DEC-*>`. It authorizes only that exact type and target when the decision remains active; missing, partial, wrong-type, wrong-target, duplicate-field, or malformed rows do not preauthorize a change.

For `sequential_slices`, use at least two slices. IDs must be ordered and unique; every slice after the first depends only on earlier slices. Base/handoff contracts state the exact revision/evidence the next writer receives. Each slice has its own research decision, coverage, documentation, context, and verification boundaries. Never invent a research brief when canonical authority, the sealed handoff, and exact edit surfaces already answer the slice; record the exact `research_not_required` sentinel and reason instead.

Every Handoff Contract requires controller-generated schema 2 fields `decision_ids`, `coverage_state`, `documentation_state`, and `open_assumptions`. The plan describes semantic inputs only. Workers do not hand-author revision/change/diff/handoff mechanics.

## State and approval

`submit` validates structure, exact source traces, mode, analyst identity, and current `SPEC_READY`, then records the draft SHA. An exact replay while awaiting approval revalidates the unchanged draft and returns the recorded result without changing plan bytes, state, history, `submitted_at`, or `updated_at`. Any edit invalidates that submission and requires resubmission.

Only after an authorized actor explicitly approves that SHA may the Director invoke `approve --approved-by <actual-actor-id>`. Direct user approval records `user`; current explicit delegation of technical/process approval records the real delegated actor. Before replacing plan bytes, the controller persists an `approval_pending` transition bound to the submitted SHA, exact approval inputs, timestamp, and reproducible approved SHA. A retry with the same inputs resumes before or after the byte replacement; a different retry or unexpected bytes fail closed. Source drift is recorded without discarding or relabeling this pending transition. With unchanged sources, `reinitialize` remains forbidden and the exact original `approve` inputs are the sole resume path. After source authority drifts and is reconverged, `reinitialize` requires a distinct fresh Analyst, verifies the exact pending transition and that plan bytes equal either its submitted SHA or deterministic approved SHA, mechanically derives the deterministic draft form when necessary, records `plan_approval_superseded_by_reinitialize` with the exact drift, captures the prior cycle in history, and records the new authority hashes. This recovery is retry-safe if interruption occurs after draft restoration. Exact replay after completed approval first revalidates exact approved bytes and current source authority, then returns as a no-op even when a normal runtime is bound; it does not require a recovery hold because it mutates nothing. Other source hash drift changes operational status to `stale`; prose cannot restore readiness. `PLAN_READY` is the stage completion token; return `NEXT_ACTION: $gamedev-pipeline` and stop rather than initializing the runtime stage.

When current PRD/SPEC authority is unchanged but an approved plan requires revision, only `revise-approved --reopened-by <director-id> --analyst-id <fresh-analyst-id> --reason <exact reason>` may reopen it. Under sole runtime v2, the command discovers the one direct schema-2 runtime JSON under `.agentic-pipeline-v2/` (default `.agentic-pipeline-v2/state.json`, with supported custom state filenames), excludes unrelated JSON, rejects multiple v2 bindings, validates the exact project root, and requires the exact canonical bound plan path/SHA. A complete canonical legacy schema-10 state/findings pair is treated as retired only when its canonical digest equals the immutable first schema-10 import digest, its deterministic import ID/generation/run ID and following public migration validate, and its same-generation findings are empty. Every immutable history record must have a non-negative integer generation plus non-empty command, result, and globally unique ID; import and migrate share the legacy generation, all later public records advance it exactly once without gaps, and the last record equals the runtime generation. With no later public reconfiguration, the derived authority, migration audit, three-key slices, and exact migrate digest must still match the v2 snapshot. After evolution, deterministic reconstruction of the imported snapshot must still reproduce the exact migrate digest, and the first well-formed `authority_scope_reconfigured` history record after migration must be generation-ordered and bind its prior authority to the derived legacy authority, the exact reconstructed three-key slices digest, and the migration-audit gate when that import route created one; later distinct reconfigurations remain valid, but a second bridge claiming the same derived legacy predecessor fails closed. The controller then validates the sole current v2 state and current approved-plan binding without comparing mutable current authority, gates, or controller-sealed read paths to the retired snapshot. That classifier is reused at initial reopen and bound continuation; missing, malformed, nonempty, mutated, mismatched, linked/reparse, incomplete, unbridged, or otherwise unproven legacy evidence fails closed. V2 has no recovery hold, and all subsequent runtime mutation is blocked by authority verification until `status` supplies the exact `init` reconfiguration. Director and Analyst must be distinct after Unicode NFKC normalization, trimming surrounding whitespace, and case folding. Freshness compares the normalized candidate against every similarly normalized Planning Analyst identity recursively stored in current state and all historical/reinitialized state shapes. It requires the current plan bytes to equal the recorded approved SHA and to contain exactly one top-level `revision:` whose value is a positive integer; normal validation enforces the same revision authority. It records the prior submission, approval, plan revision/SHA, analyst, and source hashes in append-only state history, and uses a resumable fail-closed pending transition while mechanically demoting frontmatter to `status: draft`, removing `approved_by`/`approved_at`, incrementing that sole `revision` without emitting duplicates, and installing an Analyst identity unused across all planning history. It then enters `analyzing`, clears live analysis/submission/approval state, and requires `accept-analysis` from that fresh Analyst before draft validation or submission. Editing approved bytes first, patching approval hashes, or reusing prior analysis/approval is forbidden. The new draft must validate, be submitted under its new SHA, and receive fresh approval from an actor authorized by the current user authority.

`revision:` is a typed scalar contract: exactly one top-level field whose source text is an unquoted positive ASCII decimal integer. Quoted numeric strings are invalid during validation, submission, approval, and approved-plan revision/reopen; controllers never strip YAML quotes to coerce them.

For a legacy `.agentic-pipeline/state.json` plus `findings.json` binding only, the existing pre-engineering `authority_recovery_hold` compatibility route requires its matching `--recovery-token`, unchanged hold reason, and prior approved plan SHA. Mixed legacy and v2 bindings fail closed unless the exact retired same-lineage proof above succeeds. Neither compatibility nor v2 reconfiguration carries analysis, submission, or approval forward.
