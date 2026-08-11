# Engineering and coverage phases

Read this reference only before slice research, coverage, engineering, normative documentation, or product remediation.

## Slice research and coverage planning

For each active slice, the Director first activates `$gamedev-engineer` in `research-briefing` mode without a write lease. The Engineer returns either one to three exact briefs plus `NEXT_ACTION: $gamedev-research`, or exact `research_not_required` evidence plus `NEXT_ACTION: $gamedev-coverage-steward`. The Engineer never activates those stages.

The Director activates each bounded Research stage, validates every exact-revision result bundle, and records `slice-research-complete`; alternatively it records `slice-research-not-required` with the non-empty source-backed reason. Research reports are excluded from product/support/evidence identities.

Next activate a fresh Coverage Steward in `plan-before-engineering`. Accept only a schema-2 planned manifest with every assigned acceptance criterion mapped or explicitly gapped, complete expected identities, a separately explicit mandatory set, exact coordinates/prerequisites, and owning slice.

No product edit is legal before accepted research decision, accepted coverage plan, current `slice-scope-check`, validated Engineer capsule, and exclusive lease.

## Engineering and scope

`single_owner` means one approved implementation scope, not one lifetime Engineer. All write-capable roles use phase-scoped exclusive leases; at most one may be active in the checkout. Every return or owner transfer preserves revisions, findings, decisions, coverage/documentation state, scope history, and all counters.

The Scope Contract is an allowlist. The controller compares the actual diff with editable paths/symbols, structured shared touchpoints, exclusions, acceptance/decision mappings, domain inventory, and product file/line ceilings. Unmapped/forbidden work, drive-by cleanup, budget breach, or material lifecycle/ownership/public-contract/slice-boundary change enters `scope_expansion_hold`. Resume only after an exact updated approved plan, explicit user scope approval, `rebaseline-scope`, and fresh scope check.

An Engineer returns bounded semantic annotations and final diff inspection; the controller authors revisions, change/diff manifests, and sealed handoff. `ENGINEERING_PASS` covers assigned product/root-cause work, tightly coupled automated tests, targeted checks, and final diff inspection. Manual QA/DataStore/operator/publication work may remain pending.

Route remediation to origin slice or integration scope in plan dependency order. Every return gets a new lease. A fourth route return requires a fresh Engineer and controller-generated exact-revision transfer.

## Coverage finalization and implementation completion

After every code freeze, activate a fresh Coverage Steward in `finalize-after-code-freeze`. Require exact expected/actual identity equality, separate mandatory-set equality, all assigned acceptance IDs mapped, no gap, and mandatory automated execution pass. Controlled amendments remain append-only and require exact accepted authority.

The final feature aggregate establishes `implementation_state=pass` when all slices and mandatory automated identities pass; manual identities may remain pending. It does not establish feature verification.

After implementation completion, activate Documentation Finisher in `normative-pre-review` when exact plan outputs are required, or use `documentation-not-required` with the exact approved `policy=<reference>`. Normative docs are product inputs and must be frozen before convergence.

## Capsules and payload ceilings

Before each specialized stage, create and validate a schema-1 capsule under `role-artifacts-and-context.md`. A stage may choose positive ceilings smaller than or equal to the approved plan ceilings; it may never exceed them. `max_total_files` must cover each authority/evidence file ceiling.

Controller telemetry measures only capsule JSON plus referenced authority/evidence bytes. It is `capsule_payload` telemetry, not total prompt/system context. Track static skill/reference bundles separately in CI.

## Completion routes

Every specialized stage returns its completion token and `NEXT_ACTION`, then stops. The Director validates state before activating the next stage. No stage-produced token authorizes the next stage by itself.
