# Development plan contract

## Canonical authority

Use only the repository-owned PRD, specification, development plan, and append-only decision ledger resolved from explicit user context, repository instructions, feature manifests/indexes, existing artifacts, and unambiguous sibling relationships. All paths must stay inside the project root. Do not create copies, symlinks, moves, or an alternate namespace for the controller. Ask the user if more than one plausible path remains. In an empty repository, recommend `docs/features/<feature>/` with the four sibling artifacts as a proposed layout and wait for confirmation.

Operational state remains at:

- `.agentic-pipeline/specification-state.json` for immutable `SPEC_READY` evidence;
- `.agentic-pipeline/development-plan-state.json` for operational planning state.

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

Only `single_owner` and `sequential_slices` are valid modes. `writer_strategy` is always `sequential`. It means one active write-capable lease per checkout and one writer per phase/write scope, not one Engineer identity for the lifecycle. The controller adds `approved_by` and `approved_at` only after explicit approval of the submitted draft SHA.

## Analyst decision

Analyze product and technical breadth, estimated files/symbols/tests, context working set, cross-system dependencies, ownership seams, merge/conflict surface, verification cost, documentation outputs, and handoff stability. Prefer `single_owner` whenever production implementation and tightly coupled automated tests fit one bounded engineering scope without context compression.

Use `sequential_slices` only if every slice is independently understandable and produces an observable end-to-end outcome. A later slice may consume a sealed earlier handoff, but writers never overlap. Do not create layer-only slices such as backend, UI, or tests. When boundaries are inseparable, retain one integration owner and add `MILESTONE-*` checkpoints.

## Required plan body

Include `Decision`, `Planning Analysis`, `Scope Boundaries`, `Decision Ledger`, `Coverage Strategy`, `Documentation Strategy`, and `Context Budget`. `Decision` must declare `Writer sequencing: one-at-a-time` and `Ownership meaning: phase-scoped write lease`. A `single_owner` plan also includes at least one `MILESTONE-*` under `Integration Milestones`.

`decision_ledger_path` and `Decision Ledger` name one repository-owned append-only JSONL path, active input `DEC-*` IDs (possibly `none`), and the Director route for recording a new accepted decision. Resolve the path through repository policy/manifests/sibling artifacts; for an empty repository propose `docs/features/<feature>/decision-ledger.jsonl` with the other sibling feature documents and wait for confirmation. A plan may depend only on active accepted entries; it cannot treat an Engineer assumption as a decision.

`Coverage Strategy` names the schema-2 output locations, automated and manual identity namespaces, mandatory acceptance/identity rules, automation feasibility, capability prerequisites, and Steward planning/finalization gates. Every `capability_prerequisites` value is a comma-separated canonical lowercase-hyphen ID (`[a-z0-9]+(?:-[a-z0-9]+)*`), never a prose label; the controller uses the exact union of global and slice IDs at preflight and QA. `Documentation Strategy` lists repository-required normative outputs before Review and derived support outputs after QA, or records the exact machine-addressable form `not_required | policy=<exact-reference>`. The corresponding slice Documentation Contract must repeat the same exact policy reference; prose such as “policy evidence” is a template placeholder, not approval evidence.

`Context Budget` contains positive numeric plan-wide ceilings for `max_authority_files`, `max_evidence_files`, `max_total_files`, `max_payload_bytes`, and `max_estimated_tokens`, plus exactly one `metric_scope: capsule_plus_referenced_files` and the deterministic estimation recipe. Every delegated role/slice may set a smaller positive budget. These fields measure capsule JSON plus referenced authority/evidence bytes only, not full system/history/tool context. Missing, repeated, or alternate metric scopes are invalid; a prose-only “bounded” statement is also invalid.

Define each `## Slice SLICE-NNN` with all of these non-empty sections:

- `### Vertical Outcome` with `End-to-end: yes` and `Observable result:`;
- `### Requirements` containing at least one `PRD-REQ-*` and one `PRD-AC-*`;
- `### Dependencies` containing `none` for the first slice or earlier `SLICE-*` IDs;
- `### Base Contract` and `### Handoff Contract`;
- `### Owned Paths` and `### Expected Paths`;
- `### Forbidden Scope`;
- `### Scope Contract` with `acceptance_ids`, `editable_paths`, structured `shared_touchpoint` rows, `excluded_components`, `excluded_paths`, `max_product_files`, `max_product_lines_changed`, `verification_scope`, and `scope_baseline_revision`;
- `### Research Briefs` with either one or more `RESEARCH-*` rows containing `question`, `paths`, `exclusions`, `evidence`, and `stop`, or the exact mutually exclusive sentinel `research_not_required | reason=<non-empty source-backed reason>`;
- `### Coverage Contract` with assigned acceptance IDs, automated/manual identity namespaces, explicitly mandatory identities or mandatory derivation IDs, automation feasibility, capability prerequisites, planning/finalization output paths, and amendment authorities;
- `### Documentation Contract` with normative pre-Review paths, derived post-QA support paths, decision/evidence sources, and explicit `not_required` rows when applicable;
- `### Context Capsule Budget` with all five positive numeric limits, `metric_scope: capsule_plus_referenced_files`, and bounded authority/evidence path families;
- `### Verification and Exit Criteria`;
- `### Rollback and Recovery`;
- `### Downstream Consumers`.

Keep paths narrow and use symbols when a shared file is broader than the slice. `Owned Paths` are the expected writes; `Expected Paths` are read/integration surfaces. Shared touchpoints must state the permitted symbol and change kind. Forbidden scope must name adjacent systems and cleanup/refactor work excluded from the slice.

The Scope Contract is machine-readable. Use comma-separated repository-relative paths; a trailing `/**` authorizes a subtree and no other glob syntax is valid. Every shared boundary is a separate row:

```text
- shared_touchpoint: TP-001 | path=src/contracts.lua | symbols=FeatureContract,FeatureConfig | allowed_change=additive fields required by PRD-AC-001 | forbidden_change=ownership, lifecycle, removals
```

`scope_baseline_revision` is the exact repository revision against which the first product diff is measured. `verification_scope` names tests and observations but does not authorize product writes: running a smoke test never expands scope, while changing product code owned by another component does. Every excluded component must have its concrete path represented in `excluded_paths` when such a path exists.

For `sequential_slices`, use at least two slices. IDs must be ordered and unique; every slice after the first depends only on earlier slices. Base/handoff contracts state the exact revision/evidence the next writer receives. Each slice has its own research decision, coverage, documentation, context, and verification boundaries. Never invent a research brief when canonical authority, the sealed handoff, and exact edit surfaces already answer the slice; record the exact `research_not_required` sentinel and reason instead.

Every Handoff Contract requires controller-generated schema 2 fields `decision_ids`, `coverage_state`, `documentation_state`, and `open_assumptions`. The plan describes semantic inputs only. Workers do not hand-author revision/change/diff/handoff mechanics.

## State and approval

`submit` validates structure, exact source traces, mode, analyst identity, and current `SPEC_READY`, then records the draft SHA. Any edit invalidates that submission and requires resubmission.

Only after the user explicitly approves that SHA may the Director invoke `approve`. The controller changes only approval metadata and records the resulting approved hash. Source hash drift changes operational status to `stale`; prose cannot restore readiness. After upstream reconvergence, `reinitialize` requires a distinct fresh Analyst, captures the prior cycle in history, and records the new exact hashes. `PLAN_READY` is the stage completion token; return `NEXT_ACTION: $gamedev-pipeline` and stop rather than initializing the runtime stage.
