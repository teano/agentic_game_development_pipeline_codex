# Pipeline protocol

This file is the normative state, command, revision, and artifact contract. Role behavior belongs in the corresponding skill; severity and readiness policy belongs in `severity-and-readiness.md`.

## State machine

```text
approved-plan -> preflight -> slice_research -> slice_engineering
slice_engineering(slice N) -> slice_research(slice N+1) | convergence
slice_engineering | engineering -> scope_expansion_hold
scope_expansion_hold -> updated-approved-plan + user-approval + rebaseline -> prior engineering phase
any finding-producing phase -> finding_triage -> paused finding-producing phase
engineering -> convergence | convergence_hold
convergence -> review | engineering | convergence_hold
review -> engineering | evidence_recovery | qa
engineering -> convergence -> closure_review -> qa | engineering
evidence_recovery -> recovery_review -> qa | evidence_recovery | recovery_hold | engineering
recovery_hold -> evidence_recovery
review -> qa -> ready | engineering | qa
```

`approved-plan` is a hard prerequisite, not a mutable pipeline phase. Initialization validates the canonical `development-plan.md` and `.agentic-pipeline/development-plan-state.json`: status `approved`, exact current approved SHA, exact PRD/spec hashes, `writer_strategy: sequential`, and mode `single_owner` or `sequential_slices`.

Full convergence accounting is per slice and append-only. The initial whole-candidate wave credits every covered slice once. `full_convergence_waves` has a hard maximum of `2`; owner transfer, iteration authorization, and worker-budget authorization cannot reset or extend it. A local blocking remediation transitions `engineering -> closure_review` without another full wave. `convergence-finalize --revalidation full` is accepted only with `--full-wave-trigger architecture|lifecycle|ownership|public_contract|expanded_shared_touchpoint|high_risk_surface`. Exhaustion permits only targeted closure, deferred nonblocking backlog routing, or a user-approved replan/scope hold.

Every convergence/Final Review/targeted-closure completion supplies a schema-1 component-credit manifest. Credits are keyed by component, component product hash, contract hash, lens set, and review revision. An exact valid product+contract+lens credit must be reused; a fresh reread is rejected. Overall revision drift alone preserves credit. Final whole-feature Review still requires two fresh reviewer identities, reuses valid component credits, and freshly records cross-slice composition and new-boundary coverage.

| Current state | Recorded result | Next state | Required next action |
|---|---|---|---|
| `preflight` | Resource proof passes | `slice_research` | Assigned Engineer creates 1–3 bounded briefs or records `research_not_required` |
| `preflight` | Resource proof fails | `preflight` | Reconcile specification budgets; spawn nobody |
| `slice_research` | 1–3 exact-revision bundles accepted | `slice_engineering` | Assigned Engineer reuses bundles and may begin production edits |
| `slice_research` | Explicit `research_not_required` accepted | `slice_engineering` | Engineer uses canonical documents, handoff, and exact edit files only |
| `slice_engineering` or `engineering` | Current `slice-scope-check` passes | same phase | Assigned Engineer may edit only the approved allowlist |
| `slice_engineering` or `engineering` | Scope comparison fails | `scope_expansion_hold` | Stop edits/review/next slice; obtain user approval of an updated exact-SHA plan and rebaseline |
| `scope_expansion_hold` | Updated exact approved plan plus explicit user scope approval | recorded prior engineering phase | Run `rebaseline-scope`, then a fresh `slice-scope-check` |
| finding-producing phase | Finding has `production_reachability=unknown` | `finding_triage` | Director performs one bounded reachability triage; do not start remediation |
| `finding_triage` | Reachability classified with evidence | recorded paused phase | Controller recomputes blocking and resumes aggregation or the existing owner |
| `slice_engineering` | Slice owner passes and another slice remains | `slice_research` | Seal the slice, activate its successor, and research only the new boundary |
| `slice_engineering` | Final slice owner passes | `convergence` | Whole-feature read-only convergence |
| `engineering` | Owner `CHANGED` below limit | `convergence` | Two or three parallel read-only risk audits |
| `engineering` | Owner `CHANGED` reaches limit | `convergence_hold` | Director checkpoint, then audit current revision |
| `convergence` | Aggregate pass | `review` or `closure_review` | Full Review pair or targeted local closure |
| `convergence` | Aggregate rework below limit | `engineering` | Same owner receives one frozen batch |
| `convergence` | Aggregate rework reaches limit | `convergence_hold` | Director consolidation checkpoint |
| `convergence_hold` | Director authorization | recorded resume phase | Resume audit or same owner, never a new writer by default |
| `review` | Aggregate local product rework | `engineering` | Same owner, then convergence and one targeted closure reviewer |
| `review` | Aggregate architectural/broad rework | `engineering` | Same owner, then convergence and a new full Review pair |
| `review` | Aggregate support/evidence rework | `evidence_recovery` | One non-product remediator |
| `review` | Aggregate pass | `qa` | Fresh runtime QA |
| `closure_review` | Pass | `qa` | Fresh runtime QA |
| `closure_review` | Product fail | `engineering` | Same writing owner |
| `evidence_recovery` | Support/evidence remediation completes | `recovery_review` | Fresh closure reviewer |
| `recovery_review` | Pass | `qa` | Fresh runtime QA |
| `recovery_review` | Reproduced product defect | `engineering` | Fresh full Engineer |
| `recovery_review` | Evidence failure below limit | `evidence_recovery` | Resume bounded recovery |
| `recovery_review` | Evidence failure reaches limit | `recovery_hold` | Director checkpoint |
| `recovery_hold` | Director authorization | `evidence_recovery` | Resume the frozen evidence batch |
| `qa` | `pass` | `ready` | Run `ready` |
| `qa` | `fail_product` | `engineering` | Existing writing owner; no user confirmation |
| `qa` | user/environment/test gate | `qa` | Resolve only the recorded pending scenarios |

For `sequential_slices`, `slice_research` and `slice_engineering` apply to the active slice only. A passing Engineer result must provide a schema-1 sealed handoff manifest on the slice's exact base/result revisions. The controller then activates only the next dependency-ordered slice in `slice_research`. After the final slice, it starts whole-feature convergence. Final Review and QA are invalid until all slices are sealed. At every point, `engineering_owner_id` names the only permitted writer.

Findings store `finding_kind`, severity, scope/provenance/reachability/acceptance/invariant dimensions, controller-derived `blocking`, `origin_slice`, and `remediation_route`. Reviewers supply dimensions and evidence but never set blocking. The controller queues only blocking findings; Minor never creates a remediation batch by itself. The controller groups the frozen blocking product batch by route, orders slice batches by approved-plan dependency order, and runs them serially. `--cross-slice-root-cause` routes to `integration_owner`. A route owner may complete three remediation returns; a fourth opens `owner_handoff_hold`. Only `transfer-engineering-owner` with a structured exact-revision handoff manifest to a fresh owner resumes that route. Owner changes preserve all global wave, scope, iteration, and worker counters.

`next_action.user_input_required` is authoritative for user involvement. A director checkpoint is internal unless an unresolved product, scope, credential, external-action, or user-only decision exists. At `ready`, an open minor finding yields `request_residual_risk_decision`; only the user may accept that risk.

`worker_budget` counts unique worker identities, not resumed turns by the same owner or QA worker. The default ceiling is 14 unique workers and two full-Review waves. A budget checkpoint blocks another spawn but never blocks aggregation of reports already completed.

## Commands

```text
pipeline_state.py init --project-root <root> --feature <slug> --requirements <resolved-repository-prd-path> --spec <resolved-repository-spec-path> --plan <resolved-repository-plan-path> --plan-sha256 <exact-approved-sha> --base-revision <exact-revision> [--integration-owner <id>] [--required-convergence-audits 2|3] [--max-workers <n>] [--max-full-review-waves <n>]
pipeline_state.py preflight-complete --project-root <root> --run-id <id> --resource-budget-check pass|fail --capability <name>=available|not_required|planned_manual|blocked_user|blocked_environment|error_test ... --report <report>
pipeline_state.py status --project-root <root>
pipeline_state.py slice-research-complete --project-root <root> --slice-id SLICE-NNN --base-revision <exact-active-revision> --owner-id <assigned-engineer> --bundle tests/<slug>/research/<bundle>.json [--bundle ... up to 3]
pipeline_state.py slice-research-not-required --project-root <root> --slice-id SLICE-NNN --base-revision <exact-active-revision> --owner-id <assigned-engineer> --reason <why-no-wide-discovery-is-needed>
pipeline_state.py slice-scope-check --project-root <root> --slice-id SLICE-NNN --base-revision <exact-current-revision> --owner-id <assigned-engineer>
pipeline_state.py compute-revisions --project-root <root> --base-revision <git-or-manifest-id> [--product-file <path> ...] [--support-file <path> ...] [--evidence-file <path> ...] [--output tests/<slug>/verification/<manifest>.json]
pipeline_state.py engineer-complete --project-root <root> --revision <all> --product-revision <product> --support-revision <support> --evidence-revision <evidence> --run-id <id> --owner-id <persistent-owner> --slice-id SLICE-NNN --change-manifest <changes.json> --diff-summary <diff.json> [--base-revision <exact-predecessor> --handoff-manifest <sealed.json>] --machine-checks pass --coverage-manifest <coverage.json> --production-change-scope none|local|architectural [--scope-approval <exact-rebaseline-user-approval>] [--resolved-finding <id> ...] --report <report> --audit-complete
pipeline_state.py rebaseline-scope --project-root <root> --plan-sha256 <updated-exact-approved-sha> --user-scope-approval <explicit-user-decision-reference>
pipeline_state.py transfer-engineering-owner --project-root <root> --from-owner <id> --to-owner <fresh-id> --reason <explicit-handoff> [--slice-id SLICE-NNN] --handoff-manifest <sealed-owner-handoff.json>
pipeline_state.py convergence-audit-complete --project-root <root> --revision <all> --run-id <id> --reviewer-id <fresh-id> --lens persistence-lifecycle|config-security-capacity|integration-runtime-docs --status pass|fail --report <report> --credit-manifest <credits.json>
pipeline_state.py convergence-finalize --project-root <root> --revision <all> --decision pass|rework [--revalidation targeted|full] [--full-wave-trigger <material-trigger>] --report <aggregate>
pipeline_state.py review-complete --project-root <root> --revision <all> --product-revision <product> --support-revision <support> --evidence-revision <evidence> --run-id <id> --reviewer-id <id> --status pass|fail --report <report> --credit-manifest <credits.json>
pipeline_state.py review-finalize --project-root <root> --revision <all> --decision pass|rework [--rework-scope product|support|evidence|recovery] [--revalidation targeted|full] [--full-wave-trigger <material-trigger>] --report <aggregate> [--reason <text>]
pipeline_state.py closure-review-complete --project-root <root> --revision <all> --run-id <id> --reviewer-id <fresh-id> --status pass|fail --report <report> --credit-manifest <credits.json>
pipeline_state.py add-finding --project-root <root> --id <id> --source engineer|convergence|review|qa --finding-kind product|evidence|support|hardening --severity critical|major|minor --scope-relation candidate_introduced|current_feature_path|required_shared_contract|preexisting_adjacent|out_of_scope --introduced-by-candidate true|false --production-reachability normal|supported_failure_path|theoretical|unsupported_configuration|unknown [--blocks-acceptance-id PRD-AC-NNN ...] --violates-required-invariant true|false [--required-invariant-evidence <exact-proof>] --mandatory-core-acceptance-evidence-missing true|false --test-can-miss-product-defect true|false [--deferred-reference <pending-reference>] --title <text> --evidence <text> --revision <all> [--origin-slice SLICE-NNN | --cross-slice-root-cause]
pipeline_state.py triage-finding --project-root <root> --id <id> --production-reachability normal|supported_failure_path|theoretical|unsupported_configuration --evidence <bounded-proof> [--deferred-reference <pending-reference>]
deferred_findings.py backlog-upsert --project-root <root> --component <name> --contract <contract> --root-cause <cause> --failure-mode <mode> --effect <effect> --title <title> --problem <problem> --violated-invariant <invariant-or-none> --provisional-severity minor|major|critical --reachability normal|supported_failure_path|theoretical|unsupported_configuration|unknown --occurrence-id <worker:local-id> --observed-by <worker> --origin-feature <feature> [--condition <condition> ...] [--impact <impact> ...] [--evidence <evidence> ...] [--reentry-condition <condition> ...]
deferred_findings.py extend|assign|reactivate|resolve|link-duplicate ...
deferred_findings.py backlog-scope-check --project-root <root> --revision <revision> [--source convergence|review|engineer|qa ...]
pipeline_state.py start-evidence-recovery --project-root <root> --revision <all> --product-revision <product> --support-revision <support> --evidence-revision <evidence> --finding-id <id>... --reason <text>
pipeline_state.py recovery-remediation-complete --project-root <root> --revision <new-all> --product-revision <same-product> --support-revision <support> --evidence-revision <evidence> --run-id <id> --worker-id <id> --machine-checks pass --coverage-manifest <coverage.json> --resolved-finding <id>... --production-change-scope none --report <report>
pipeline_state.py recovery-review-complete --project-root <root> --revision <all> --product-revision <product> --support-revision <support> --evidence-revision <evidence> --run-id <id> --reviewer-id <fresh-id> --status pass|fail --report <report>
pipeline_state.py authorize-iteration --project-root <root> --reason <director-decision>
pipeline_state.py authorize-budget --project-root <root> --additional-workers <n> [--additional-full-review-waves <n>] --reason <consolidated-need>
pipeline_state.py qa-capability-probe --project-root <root> --revision <all> --probe-id <id> --capability <name=status>... [--minimum-resume-action <name=action> ...] --report <report>
pipeline_state.py qa-complete --project-root <root> --revision <all> --product-revision <product> --support-revision <support> --evidence-revision <evidence> --run-id <id> --worker-id <id> --status pass|fail_product|blocked_user|blocked_environment|error_test --report <report> [--reason <text>] [--pending-scenario <id> ...]
pipeline_state.py accept-finding --project-root <root> --id <minor-id> --reason <approved-risk> --approval-reference <user-decision>
pipeline_state.py ready --project-root <root>
```

Schema 8 is the current complete classification and scope-control schema. The controller rejects pre-v8 state and requires explicit reinitialization; it never guesses missing scope, reachability, acceptance, invariant, evidence-major, ownership, or scope-contract facts. `--kind` remains a deprecated deterministic CLI alias for `--finding-kind`; findings are persisted only with `finding_kind`. `start-evidence-recovery` accepts only findings already normalized as `evidence` or `support`, never converts a product finding by inference. `resolve-finding` is a phase-preserving administrative compatibility command. Product remediation closes the complete normalized blocking batch atomically through `engineer-complete --resolved-finding`; non-product remediation uses `recovery-remediation-complete --resolved-finding`. `evidence-remediation-complete` remains a CLI alias for compatibility.

## Revision identities

- `product_revision`: runtime source, manifests, configuration, approved feature documents, normative ADRs/contracts, and other behavior-defining product documents.
- `support_revision`: derived handoff/index/operator documentation and non-normative project metadata whose correction does not change runtime or public behavior.
- `evidence_revision`: tests, fixtures, deterministic harnesses, and verification inputs.
- `revision`: SHA-256 of the product/support/evidence identity tuple.

Use `compute-revisions`; do not invent a hash recipe in a worker. Its domain hash is SHA-256 of UTF-8 `base:<base_revision>\n` followed by ordinal-sorted `<repo-relative-path>\0<exact-byte-sha256>\n`. The composite hash is SHA-256 of `product:<product_revision>\nsupport:<support_revision>\nevidence:<evidence_revision>\n`.

Freeze the complete domain path inventory before completion. A path belongs to exactly one of product, support, or evidence. Exclude reports, logs, screenshots, coverage/revision manifests, `.agentic-pipeline/` state, and the tracked controller-managed `docs/engineering/deferred-findings.json`. `compute-revisions` rejects the backlog path in every domain.

Reset rules:

- product change invalidates convergence, Review, QA, and open-gate evidence;
- support-only change preserves clean runtime and full Reviews, but requires focused recovery verification and fresh QA;
- evidence-only change preserves clean product and completed full Reviews, but requires recovery verification and fresh QA;
- report-only change invalidates neither identity;
- PRD/spec drift stops progress until explicitly reconciled;
- development-plan or approval-evidence drift stops progress until the plan is re-approved on its exact SHA;
- a passed parallel convergence wave or convergence authorization resets the consecutive product-change counter;
- a recovery authorization resets the failed-recovery counter.

## Findings and gates

A finding is an evidence-backed defect. A gate is only an unavailable user action, environment, tool, service, setup, automation, or observation path. There is no “product gate.”

- QA `fail_product` requires a registered current-revision controller-classified blocking QA product finding.
- QA may register only product findings.
- Non-pass QA requires a reason; gate results also require pending scenario IDs.
- Passing QA cannot contain pending scenarios.
- A scenario invalidated by a product finding is `blocked_by_finding`, not a gate.
- `production_reachability=unknown` opens `finding_triage`; it never sends work directly to an Engineer.
- Every supported nonblocking `preexisting_adjacent` or `out_of_scope` finding must be atomically upserted into `docs/engineering/deferred-findings.json` and carry its canonical `#DEF-*` reference before positive convergence or Final Review finalization. The director is the only backlog writer; workers emit candidates. Fingerprints exclude revision/title/specific trigger and merge unique conditions, impacts, evidence, and independent occurrences. Resolved rediscovery reopens; severity escalation requires new evidence.
- Return the issue to current scope when candidate work introduced/worsened it, changed contract/feature reachability exposes it, it blocks acceptance/invariant, or it presents a current-solution safety risk. A material return requires the existing `scope_expansion_hold`, explicit user-approved updated plan, and `rebaseline-scope`.

## Artifacts and identities

- Track canonical feature and repository-required supporting product documents.
- Treat the approved development plan as queue authority. State records its path/hash, mode, ordered slices, active slice, per-slice base/result identities and status, `owner_by_slice`, `integration_owner`, handoff manifests, remediation queue, and per-owner remediation-return counters.
- Each slice state records its machine-readable Scope Contract, current pre-edit check, scope churn, and append-only scope history. Global scope history/churn and rebaseline history persist across owner changes. Neither `authorize-iteration` nor `transfer-engineering-owner` clears `scope_expansion_hold`.
- Ignore `/tests/`; store verification, Review, QA, revision manifests, logs, and captures under `tests/<feature>/`.
- Store bounded research bundles under `tests/<feature>/research/` (or the controller-assigned runtime research path). Research bundles are reports, never product, support, or evidence revision inputs.
- Each schema-1 research bundle contains `brief` and `result`. The brief records `brief_id`, question, active `slice_id`, related `requirement_ids`, exact `base_revision`, `seed_paths`, `allowed_paths`, `allowed_symbols`, `exclusions`, `requested_evidence`, positive `max_files`, `stop_condition`, and its own `output_path`. The result records the same brief/base identity, fresh `researcher_id`, canonical `brief_sha256`, status, inspected paths/symbols, owners/contracts/precedents, lifecycle/integration risks, minimal edit/reuse points, unresolved questions, and pointer-only out-of-brief candidates. Raw dumps are invalid.
- Keep controller state in `.agentic-pipeline/`; mutate it only through `pipeline_state.py`.
- Reuse each slice owner ID for that slice's product passes and its first three remediation returns; use the integration owner for cross-slice root causes and one QA worker ID across gated resumes. Use unique run IDs and fresh distinct identities for convergence, full Review, targeted closure, and recovery Review.
- Pass workers paths, IDs, revisions, commands, and output locations; do not pass long chat history or raw reasoning.

Every terminal Engineer/recovery-remediation pass requires a schema-1 coverage manifest. Each unique entry is exactly one of:

- `covered`: non-empty implementation evidence and exact test records containing `file`, `suite`, `symbol`, `assertions`, `execution`, and `evidence`;
- `finding`: normalized `finding_ids`;
- `not_applicable`: explicit `reason`.

The manifest records matching product, support, and evidence revisions. The technical director must also compare its IDs with every approved acceptance/evidence row; mere schema validity is not complete coverage.

Every terminal Engineer pass also supplies schema-1 change-manifest and diff-summary artifacts. The change manifest has exact `slice_id`, `owner_id`, base/result revisions, and `change_manifest[]`; every entry has `path`, `symbols`, `slice_id`, `requirement_ids`, `acceptance_ids`, `reason`, `change_kind`, and `touchpoint_id` when the path is shared. The diff summary has exact slice/base/result identities and `product_files[]`; every entry has `path`, `symbols`, non-negative `lines_changed`, `component`, `change_kind`, and boolean `lifecycle_change`, `ownership_change`, and `public_contract_change`. The product path sets must match exactly. A sealed slice handoff embeds the verified `change_manifest` list.

The controller compares the current pass diff against the approved slice allowlists, exclusions, touchpoint symbols/change kinds, and budgets. A smoke test listed in verification evidence never authorizes a product path. Unmapped files/symbols, excluded paths/components, drive-by cleanup/refactor, material lifecycle/ownership/public-contract changes, unapproved shared touchpoints, mismatched counts, or budget breach persist `scope_expansion_hold` before the candidate revision is accepted. A material change is accepted only when its `--scope-approval` exactly matches the user approval recorded by the latest same-base, same-plan `rebaseline-scope`; a handoff or unrelated approval string cannot authorize it.
