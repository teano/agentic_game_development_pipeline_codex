# Development plan contract

## Canonical authority

Use only:

- `docs/features/<feature>/product-requirements.md`;
- `docs/features/<feature>/technical-specification.md`;
- `docs/features/<feature>/development-plan.md`;
- `.agentic-pipeline/specification-state.json` for immutable `SPEC_READY` evidence;
- `.agentic-pipeline/development-plan-state.json` for operational planning state.

The plan frontmatter must contain:

```yaml
---
document_type: development-plan
status: draft
revision: 1
feature: <feature>
mode: single_owner
writer_strategy: sequential
planning_analyst_id: <fresh-agent-id>
source_prd_path: docs/features/<feature>/product-requirements.md
source_prd_revision: <revision>
source_prd_sha256: <64 lowercase hex>
source_spec_path: docs/features/<feature>/technical-specification.md
source_spec_revision: <revision>
source_spec_sha256: <64 lowercase hex>
slice_count: 1
---
```

Only `single_owner` and `sequential_slices` are valid modes. `writer_strategy` is always `sequential`. The controller adds `approved_by` and `approved_at` only after explicit approval of the submitted draft SHA.

## Analyst decision

Analyze product and technical breadth, estimated files/symbols/tests, context working set, cross-system dependencies, ownership seams, merge/conflict surface, verification cost, and handoff stability. Prefer `single_owner` whenever one Engineer can finish without context compression.

Use `sequential_slices` only if every slice is independently understandable and produces an observable end-to-end outcome. A later slice may consume a sealed earlier handoff, but writers never overlap. Do not create layer-only slices such as backend, UI, or tests. When boundaries are inseparable, retain one integration owner and add `MILESTONE-*` checkpoints.

## Required plan body

Include `Decision`, `Planning Analysis`, `Scope Boundaries`, and `Context Budget`. `Decision` must declare `Writer sequencing: one-at-a-time`. A `single_owner` plan also includes at least one `MILESTONE-*` under `Integration Milestones`.

Define each `## Slice SLICE-NNN` with all of these non-empty sections:

- `### Vertical Outcome` with `End-to-end: yes` and `Observable result:`;
- `### Requirements` containing at least one `PRD-REQ-*` and one `PRD-AC-*`;
- `### Dependencies` containing `none` for the first slice or earlier `SLICE-*` IDs;
- `### Base Contract` and `### Handoff Contract`;
- `### Owned Paths` and `### Expected Paths`;
- `### Forbidden Scope`;
- `### Scope Contract` with `acceptance_ids`, `editable_paths`, structured `shared_touchpoint` rows, `excluded_components`, `excluded_paths`, `max_product_files`, `max_product_lines_changed`, `verification_scope`, and `scope_baseline_revision`;
- `### Research Briefs` with one or more `RESEARCH-*` rows containing `question`, `paths`, `exclusions`, `evidence`, and `stop`;
- `### Verification and Exit Criteria`;
- `### Rollback and Recovery`;
- `### Downstream Consumers`.

Keep paths narrow and use symbols when a shared file is broader than the slice. `Owned Paths` are the expected writes; `Expected Paths` are read/integration surfaces. Shared touchpoints must state the permitted symbol and change kind. Forbidden scope must name adjacent systems and cleanup/refactor work excluded from the slice.

The Scope Contract is machine-readable. Use comma-separated repository-relative paths; a trailing `/**` authorizes a subtree and no other glob syntax is valid. Every shared boundary is a separate row:

```text
- shared_touchpoint: TP-001 | path=src/contracts.lua | symbols=FeatureContract,FeatureConfig | allowed_change=additive fields required by PRD-AC-001 | forbidden_change=ownership, lifecycle, removals
```

`scope_baseline_revision` is the exact repository revision against which the first product diff is measured. `verification_scope` names tests and observations but does not authorize product writes: running a smoke test never expands scope, while changing product code owned by another component does. Every excluded component must have its concrete path represented in `excluded_paths` when such a path exists.

For `sequential_slices`, use at least two slices. IDs must be ordered and unique; every slice after the first depends only on earlier slices. Base/handoff contracts state the exact revision/evidence the next writer receives. Each slice has its own research and verification boundaries.

## State and approval

`submit` validates structure, exact source traces, mode, analyst identity, and current `SPEC_READY`, then records the draft SHA. Any edit invalidates that submission and requires resubmission.

Only after the user explicitly approves that SHA may the Director invoke `approve`. The controller changes only approval metadata and records the resulting approved hash. Source hash drift changes operational status to `stale`; prose cannot restore readiness. After upstream reconvergence, `reinitialize` requires a distinct fresh Analyst, captures the prior cycle in history, and records the new exact hashes.
