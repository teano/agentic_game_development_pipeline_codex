# Severity and readiness

## Finding classification

Severity is impact only. It never decides remediation by itself. Every reviewer, Engineer, and QA worker returns complete evidence plus these independent dimensions; the controller normalizes them, rejects incompatible combinations, and derives `blocking`:

- `finding_kind`: `product`, `evidence`, `support`, or `hardening`;
- `severity`: `critical`, `major`, or `minor`;
- `scope_relation`: `candidate_introduced`, `current_feature_path`, `required_shared_contract`, `preexisting_adjacent`, or `out_of_scope`;
- `introduced_by_candidate`: explicit boolean provenance;
- `production_reachability`: `normal`, `supported_failure_path`, `theoretical`, `unsupported_configuration`, or `unknown`;
- `blocks_acceptance_ids`: exact approved `PRD-AC-*` IDs, possibly empty;
- `violates_required_invariant`: explicit boolean plus exact invariant evidence when true;
- `blocks_required_support_contract`: explicit boolean valid only for `support`, plus `required_support_contract_evidence` naming an exact approved derived-support path;
- `coverage_identity_ids`: exact finalized identity bindings when the source is QA;
- exact reproduction/evidence and revision;
- canonical `deferred_reference` for every supported classified nonblocking `preexisting_adjacent` or `out_of_scope` issue, written only after Director atomic upsert to `docs/engineering/deferred-findings.json`.

The controller computes `blocking=true` only when all three clauses are true. Severity is not an input to this formula:

```text
scope_relation in {candidate_introduced, current_feature_path, required_shared_contract}
AND production_reachability in {normal, supported_failure_path}
AND (blocks_acceptance_ids is non-empty OR violates_required_invariant=true)
```

`introduced_by_candidate` remains a separate provenance fact. `scope_relation=candidate_introduced` requires it to be true; a `preexisting_adjacent` issue cannot claim it. No reviewer may set `blocking`, set `remediation_required`, or request remediation directly.

The controller derives `remediation_required=true` for every product-blocking finding and for a `support` finding that blocks an exact approved derived-support path. The support case remains `blocking=false`, but Review/readiness route it through non-product recovery.

When `production_reachability=unknown`, store `blocking=false`, enter bounded `finding_triage`, and do not start Engineer remediation. Triage answers only whether the path is normal, a supported failure path, theoretical, or an unsupported configuration, records exact evidence, recomputes blocking, and resumes the paused phase.

Kinds:

- `product`: wrong production behavior, contract, configuration, integration, or source;
- `evidence`: required proof can miss a real defect;
- `support`: stale derived handoff/index/guidance while product contracts remain correct;
- `hardening`: defense beyond approved behavior or supported configuration.

Severity:

- `critical`: compromise/data loss/corruption, unsafe action, core-flow blocker, or release-breaking failure;
- `major`: wrong core behavior, material violation/regression, missing supported failure handling, serious performance breach, or qualifying evidence failure;
- `minor`: bounded defect/risk with safe workaround and no invalid core flow.

Critical claims identify blocked acceptance or an evidenced required invariant; missing evidence alone is never Critical.

`evidence` is Major only if another core proof is absent, the current test can miss a real defect, and `blocks_acceptance_ids` names that criterion; otherwise it is Minor/support. Duplicate evidence, stale provenance, cosmetic diagnostics, and format preferences do not block automatically.

Preexisting/out-of-scope defects, hardening, theoretical/unsupported paths, cosmetics, stale provenance, and duplicate evidence never auto-block. Support/hardening cannot block acceptance or product invariants; only support may block an exact support contract. Minor cannot block acceptance/invariants and never starts remediation alone.

Unavailable tools/permissions/credentials/publication/manual actions and unexecuted scenarios are gates, not findings. Fix only the frozen `remediation_required` batch. Keep introduced/worsened, contract/feature-reachable, acceptance/invariant-blocking, and safety-impact issues in current scope. Preserve supported nonblocking external issues through `backlog-upsert`; material plan change uses `scope_expansion_hold`.

## Gate classification

- `blocked_user`: a user-controlled permission, credential, publication, or manual step is required;
- `blocked_environment`: a required runtime, client, device, service, or tool is unavailable;
- `error_test`: setup, harness, automation, or observation failed before product behavior could be judged.

Each gate records the exact product/evidence revision, pending registered manual identity IDs, completed reusable evidence, reason, and minimum resume action. Mixed QA gates preserve every category/identity while the controller derives one deterministic overall status. Gates have no product severity. Only `blocked_user` inherently requires user input.

Before QA spawn, the controller requires a complete capability probe on the exact reviewed revision for the prerequisites of the registered manual identities. Engine/editor, topology, persistence, credentials, operator control, and evidence-capture capabilities are required only when an approved identity cites them. Known unavailable capability means no QA spawn. `blocked_environment` and `error_test` require the recorded failed probe plus a minimum resume action; they cannot be inferred from an unexecuted scenario.

## Production-ready candidate

Require all of the following:

- exact-current approved PRD/spec/plan, no source drift, and append-only ledger with active referenced decisions and required ADRs (or plan-proven `not_required`);
- exact-set preflight for plan plus platform capabilities, with none unexpected/unavailable, and no open gate hiding mandatory execution;
- passed capsule budgets with preserved file/byte/token metrics; worker/review budgets remain within limits or have explicit Director authorization;
- no active/overlapping lease and complete append-only lease history;
- required normative docs before Review and derived support after QA, or exact policy `not_required` evidence;
- independent `implementation_state=pass`;
- current schema-2 coverage: all acceptance IDs mapped, expected=actual identities, mandatory registration exact, no gap, mandatory automation passed;
- one passed controller-required convergence Review on the current product; at most two append-only full waves per slice, with local remediation closed by fresh targeted Review unless a recorded material trigger requires a full wave;
- valid component credits keyed by product/contract hashes, lenses, and review revision; reuse unchanged components and record Final Review composition/new-boundary coverage;
- one passed Final Review on current identities with its exact capsule/credit manifest, then either targeted product closure or support/evidence recovery Review preserving the accepted same-product credit lineage and finalized coverage continuity;
- exact-product/evidence capability probe and runtime QA pass; every mandatory manual identity executed/passed, none deferred/blocked;
- if post-QA derived support changed, unchanged QA product/evidence plus fresh documentation-closure Review on current support;
- terminal schema-2 handoff with exact decisions, coverage, docs, and an empty `open_assumptions` list; every prior assumption is already resolved through an existing decision, finding, or gate route;
- no open `remediation_required` finding; every Minor is closed or accepted by prior immutable receipt bound to finding, revision, and reason;
- `feature_verification_state=pass` on current product/support/evidence with exact QA/support-closure credits;
- controller phase `ready` and successful `ready` command.

This verdict is a production-ready candidate, not authorization to publish, deploy, migrate, spend, submit, or accept risk.
