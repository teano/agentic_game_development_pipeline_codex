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
- exact reproduction/evidence and revision;
- canonical `deferred_reference` for every supported classified nonblocking `preexisting_adjacent` or `out_of_scope` issue, written only after Director atomic upsert to `docs/engineering/deferred-findings.json`.

The controller computes `blocking=true` only when all three clauses are true. Severity is not an input to this formula:

```text
scope_relation in {candidate_introduced, current_feature_path, required_shared_contract}
AND production_reachability in {normal, supported_failure_path}
AND (blocks_acceptance_ids is non-empty OR violates_required_invariant=true)
```

`introduced_by_candidate` remains a separate provenance fact. `scope_relation=candidate_introduced` requires it to be true; a `preexisting_adjacent` issue cannot claim it. No reviewer may set `blocking` or request remediation directly.

When `production_reachability=unknown`, store `blocking=false`, enter bounded `finding_triage`, and do not start Engineer remediation. Triage answers only whether the path is normal, a supported failure path, theoretical, or an unsupported configuration, records exact evidence, recomputes blocking, and resumes the paused phase.

Kinds:

- `product`: production behavior, contract, configuration, integration, or runtime source is wrong;
- `evidence`: the current required test/fixture/assertion can let a real product defect pass undetected;
- `support`: derived handoff, index, operator guidance, or non-normative metadata is stale while runtime behavior and public contracts remain unchanged;
- `hardening`: defensive improvement beyond approved behavior, including theoretical robustness or an unsupported configuration.

Severity:

- `critical`: security compromise, data loss, unrecoverable corruption, unsafe external action, crash/hard blocker in a core flow, or release-breaking requirement failure;
- `major`: incorrect core behavior, material requirement violation, likely regression, missing important supported failure handling, serious performance breach, or qualifying evidence failure;
- `minor`: bounded defect or maintainability risk that does not invalidate a core flow and has a safe workaround.

Critical safety, corruption, or data-loss claims must identify a blocked approved acceptance criterion or the exact required invariant; an invariant claim requires supporting evidence. Missing evidence is never Critical by itself.

An `evidence` finding may be Major only when all are proven: another required proof for a core acceptance criterion is absent; the exact current test can miss a real product defect; and `blocks_acceptance_ids` names that approved criterion. Otherwise classify it Minor or `support`. Duplicate preferred evidence, stale provenance, cosmetic diagnostics, and evidence-format preferences do not block automatically.

The following never block automatically: preexisting adjacent or out-of-scope defects, defensive hardening, theoretical paths, unsupported configurations, cosmetic issues, stale provenance, or duplicate evidence. Support/hardening findings cannot claim blocked acceptance IDs or a required invariant. A Minor classification likewise cannot claim a blocked approved acceptance criterion or required invariant; the controller rejects that incompatible combination, so Minor findings never start a remediation wave by themselves.

Do not create a finding for unavailable tools, permissions, credentials, publication, manual actions, unrelated noise, or an unexecuted scenario. Record those as gates. Fix only controller-classified blocking findings in the current remediation batch. Preserve every supported nonblocking out-of-scope issue through Director `backlog-upsert`; convergence cannot pass until all canonical links resolve. Return introduced/worsened, changed-contract/feature-reachable, acceptance/invariant-blocking, or safety-impact issues to current scope, using `scope_expansion_hold` when the approved plan must materially change.

## Gate classification

- `blocked_user`: a user-controlled permission, credential, publication, or manual step is required;
- `blocked_environment`: a required runtime, client, device, service, or tool is unavailable;
- `error_test`: setup, harness, automation, or observation failed before product behavior could be judged.

Each gate records the exact product/evidence revision, pending registered manual identity IDs, completed reusable evidence, reason, and minimum resume action. Gates have no product severity. Only `blocked_user` inherently requires user input.

Before QA spawn, the controller requires a complete capability probe on the exact reviewed revision: Studio/editor sync, single play, mandatory Test Server server plus two clients, stable window/control or declared human operator, logging/screenshots, persistence/DataStore, publication/place topology, and configuration/credentials. Known unavailable capability means no QA spawn. `blocked_environment` and `error_test` require the recorded failed probe plus a minimum resume action; they cannot be inferred from an unexecuted scenario.

## Production-ready candidate

Require all of the following:

- current approved PRD, traced technical specification, and approved development plan;
- current append-only decision ledger (possibly zero-entry) with every referenced `DEC-*` active and exact, plus every policy-required ADR or plan-proven ADR `not_required`;
- passed resource-budget preflight and a recorded runtime capability/manual-operator plan;
- passed schema-1 context budget gates with preserved file/byte/token metrics for every specialized worker;
- no active/overlapping write lease and a complete append-only lease history;
- every repository-required normative product document completed before Review and current derived support document completed after QA, or exact plan/policy evidence that each class is not required;
- no source drift;
- `implementation_state=pass` independently of `feature_verification_state`;
- a current schema-2 coverage manifest with every approved acceptance ID mapped, exact expected/actual identity set equality, separate exact mandatory-set registration equality, no coverage gap, and every mandatory automated identity executed/passed;
- one passed parallel read-only convergence wave on the current product revision;
- no slice has exceeded two append-only full convergence waves; local remediation is closed by one fresh targeted reviewer unless an allowed material full-wave trigger is recorded;
- valid component Review credits keyed by component product hash, contract hash, lenses, and review revision, with unchanged components reused and Final Review composition/new-boundary coverage recorded;
- two distinct passed full Reviews on the current identities, their preserved reports plus one passed targeted local-product closure reviewer, or their preserved same-product reports plus one passed support/evidence recovery reviewer;
- a passed exact-product/evidence QA capability probe and feature-focused runtime QA `pass` with every mandatory manual identity executed/passed and none deferred/blocked;
- when derived support changed after QA, unchanged exact QA product/evidence identities plus one fresh passed `documentation-closure` Review on the current support revision;
- a controller-generated schema-2 terminal handoff containing exact `decision_ids`, `coverage_state`, `documentation_state`, and `open_assumptions`;
- no open controller-classified blocking finding;
- no unaccepted minor finding;
- no open gate hiding a mandatory scenario;
- no unavailable required preflight capability;
- worker and full-Review budgets either remain within their configured limits or have an explicit director authorization;
- `feature_verification_state=pass` on the current product/support/evidence identities and preserved exact QA/support-closure credits;
- controller phase `ready` and successful `ready` command.

This verdict is a production-ready candidate, not authorization to publish, deploy, migrate, spend, submit, or accept risk.
