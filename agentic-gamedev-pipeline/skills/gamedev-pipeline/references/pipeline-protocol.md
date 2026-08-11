# Pipeline protocol

This file is the normative state, command, revision, and artifact contract. Role behavior belongs in the corresponding skill; severity and readiness policy belongs in `severity-and-readiness.md`.

## State machine

```text
approved-plan -> preflight -> slice_research -> slice_coverage_planning -> slice_engineering
slice_engineering -> slice_coverage_finalization
slice_coverage_finalization(slice N) -> slice_research(slice N+1) | implementation_complete
implementation_complete -> normative_documentation -> convergence
slice_engineering | engineering -> scope_expansion_hold
scope_expansion_hold -> updated-approved-plan + user-approval + rebaseline -> prior engineering phase
any finding-producing phase -> finding_triage -> paused finding-producing phase
engineering -> coverage_finalization -> convergence | convergence_hold
convergence -> review | engineering | convergence_hold
review -> engineering | evidence_recovery | qa
engineering -> coverage_finalization -> convergence -> closure_review -> qa | engineering
evidence_recovery -> recovery_review -> qa | evidence_recovery | recovery_hold | engineering
recovery_hold -> evidence_recovery
review -> qa -> derived_documentation
derived_documentation -> documentation_review | ready
qa -> engineering | qa
any safe non-review writer boundary -> decision_recording -> recorded prior phase
```

`approved-plan` is a hard prerequisite, not a mutable pipeline phase. Initialization validates the canonical `development-plan.md` and `.agentic-pipeline/development-plan-state.json`: status `approved`, exact current approved SHA, exact PRD/spec hashes, one resolved append-only decision-ledger path, `writer_strategy: sequential`, and mode `single_owner` or `sequential_slices`. `init` validates an existing ledger byte-for-byte or atomically creates a zero-entry file at the exact approved path, then computes the baseline product revision; the ledger is never optional or silently relocated.

`single_owner` means one approved implementation write scope, not one Engineer identity for the feature lifecycle. Every write-capable role receives a phase-scoped exclusive lease. At most one write-capable lease may be active in the checkout and at most one writer may own a phase/write scope. Decision Recorder, Engineer, Documentation Finisher, and bounded recovery/remediation workers may therefore be different identities without violating `single_owner`; they never overlap. Read [role-artifacts-and-context.md](role-artifacts-and-context.md) for the normative lease, context capsule, and handoff schemas.

Full convergence accounting is per slice and append-only. The initial whole-candidate wave credits every covered slice once. `full_convergence_waves` has a hard maximum of `2`; owner transfer, iteration authorization, and worker-budget authorization cannot reset or extend it. A local blocking remediation transitions `engineering -> closure_review` without another full wave. `convergence-finalize --revalidation full` is accepted only with `--full-wave-trigger architecture|lifecycle|ownership|public_contract|expanded_shared_touchpoint|high_risk_surface`. Exhaustion permits only targeted closure, deferred nonblocking backlog routing, or a user-approved replan/scope hold.

Every convergence/Final Review/targeted-closure completion supplies a schema-1 component-credit manifest. Credits are keyed by component, component product hash, contract hash, lens set, and review revision. An exact valid product+contract+lens credit must be reused; a fresh reread is rejected. Overall revision drift alone preserves credit. Final whole-feature Review still requires two fresh reviewer identities, reuses valid component credits, and freshly records cross-slice composition and new-boundary coverage.

| Current state | Recorded result | Next state | Required next action |
|---|---|---|---|
| `preflight` | Resource proof passes | `slice_research` | Assigned Engineer creates 1–3 bounded briefs or records `research_not_required` |
| `preflight` | Resource proof fails | `preflight` | Reconcile specification budgets; spawn nobody |
| `slice_research` | 1–3 exact-revision bundles accepted | `slice_coverage_planning` | Fresh Coverage Steward registers expected exact automated/manual identities |
| `slice_research` | Explicit `research_not_required` accepted | `slice_coverage_planning` | Steward uses canonical documents, handoff, and exact scope only |
| `slice_coverage_planning` | Schema-2 planned manifest accepted | `slice_engineering` | Issue the exclusive Engineer lease and current scope check |
| `slice_engineering` or `engineering` | Current `slice-scope-check` passes | same phase | Assigned Engineer may edit only the approved allowlist |
| `slice_engineering` or `engineering` | Scope comparison fails | `scope_expansion_hold` | Stop edits/review/next slice; obtain user approval of an updated exact-SHA plan and rebaseline |
| `scope_expansion_hold` | Updated exact approved plan plus explicit user scope approval | recorded prior engineering phase | Run `rebaseline-scope`, then a fresh `slice-scope-check` |
| finding-producing phase | Finding has `production_reachability=unknown` | `finding_triage` | Director performs one bounded reachability triage; do not start remediation |
| `finding_triage` | Reachability classified with evidence | recorded paused phase | Controller recomputes blocking and resumes aggregation or the existing owner |
| `slice_engineering` | `ENGINEERING_PASS` | `slice_coverage_finalization` | Release Engineer lease; Steward validates exact sets and automated evidence |
| `slice_coverage_finalization` | Implementation-eligible and another slice remains | `slice_research` | Controller generates/seals schema-2 handoff and activates successor |
| `slice_coverage_finalization` | Final slice implementation-eligible | `implementation_complete` | Record engineering pass with manual QA normally pending |
| `implementation_complete` | Normative docs required/none | `normative_documentation` | Finisher updates exact normative paths or controller records not-required |
| `normative_documentation` | Complete on current product revision | `convergence` | Two or three parallel read-only risk audits |
| `engineering` | Remediation `ENGINEERING_PASS` below limit | `coverage_finalization` | Re-finalize exact coverage before convergence/closure |
| `coverage_finalization` | Implementation-eligible | `convergence` | Two or three parallel read-only risk audits or targeted closure route |
| `engineering` | Remediation `ENGINEERING_PASS` reaches limit | `convergence_hold` | Director checkpoint, then audit current revision |
| `convergence` | Aggregate pass | `review` or `closure_review` | Full Review pair or targeted local closure |
| `convergence` | Aggregate rework below limit | `engineering` | One origin/integration-routed Engineer lease receives the frozen batch |
| `convergence` | Aggregate rework reaches limit | `convergence_hold` | Director consolidation checkpoint |
| `convergence_hold` | Director authorization | recorded resume phase | Resume audit or issue one exact routed writer lease |
| `review` | Aggregate local product rework | `engineering` | One routed Engineer lease, coverage re-finalization, then targeted closure |
| `review` | Aggregate architectural/broad rework | `engineering` | One routed Engineer lease, re-finalization, convergence, and new full Review pair |
| `review` | Aggregate support/evidence rework | `evidence_recovery` | One non-product remediator |
| `review` | Aggregate pass | `qa` | Fresh runtime QA |
| `closure_review` | Pass | `qa` | Fresh runtime QA |
| `closure_review` | Product fail | `engineering` | Origin-routed Engineer under a new exclusive lease |
| `evidence_recovery` | Support/evidence remediation completes | `recovery_review` | Fresh closure reviewer |
| `recovery_review` | Pass | `qa` | Fresh runtime QA |
| `recovery_review` | Reproduced product defect | `engineering` | Fresh full Engineer |
| `recovery_review` | Evidence failure below limit | `evidence_recovery` | Resume bounded recovery |
| `recovery_review` | Evidence failure reaches limit | `recovery_hold` | Director checkpoint |
| `recovery_hold` | Director authorization | `evidence_recovery` | Resume the frozen evidence batch |
| `qa` | `pass` | `derived_documentation` | Finish exact derived support outputs from immutable QA evidence or record not-required |
| `qa` | `fail_product` | `engineering` | Origin-routed Engineer under a new exclusive lease; no user confirmation |
| `qa` | user/environment/test gate | `qa` | Resolve only the recorded pending manual identities |
| `derived_documentation` | Support-only completion | `documentation_review` | Fresh immutable documentation-closure reviewer |
| `derived_documentation` | Plan/policy-proven `not_required` | `ready` | Set feature verification pass and run `ready` |
| `documentation_review` | Pass with unchanged QA product/evidence | `ready` | Run `ready` on current composite revision |
| `documentation_review` | Product/evidence/normative drift or unsupported claim | prior invalidation route | Fail closed; never preserve stale credit |

For `sequential_slices`, research, coverage planning, engineering, and coverage finalization apply to the active slice only. A passing Engineer returns a short semantic packet; after Steward finalization the controller generates the schema-2 change/diff/revision/handoff artifacts on exact base/result revisions. The controller then activates only the next dependency-ordered slice. Final Review and QA are invalid until every slice handoff is sealed, normative documentation is complete/not-required, and `implementation_state=pass`. `active_write_lease`, not `engineering_owner_id`, is the sole current writing authority.

`implementation_state` and `feature_verification_state` are independent. `implementation_state=pass` requires every approved slice engineering pass, exact coverage registration equality, all mandatory automated identities executed/passed, and code freeze. Manual runtime/DataStore/operator identities may be pending. `feature_verification_state=pass` additionally requires immutable Review, all mandatory manual identities executed/passed in QA, current derived documentation closure, and readiness gates. Pending manual work never changes an Engineer result to `INCOMPLETE`.

Findings store `finding_kind`, severity, scope/provenance/reachability/acceptance/invariant dimensions, controller-derived `blocking`, `origin_slice`, and `remediation_route`. Reviewers supply dimensions and evidence but never set blocking. The controller queues only blocking findings; Minor never creates a remediation batch by itself. It groups the frozen blocking product batch by route, orders slice batches by approved-plan dependency order, and runs them serially. `--cross-slice-root-cause` routes to the integration scope. Prefer the prior route Engineer when its capsule remains bounded and current, but `single_owner` does not require lifetime identity reuse. Every return gets a new exclusive lease; any transfer consumes a controller-generated schema-2 exact-revision handoff. A route identity may complete three remediation returns; a fourth requires a fresh Engineer. Owner changes preserve all decisions, coverage/docs state, revisions, findings, wave/scope/iteration/worker counters, and scope history.

`next_action.user_input_required` is authoritative for user involvement. A director checkpoint is internal unless an unresolved product, scope, credential, external-action, or user-only decision exists. At `ready`, an open minor finding yields `request_residual_risk_decision`; only the user may accept that risk.

`worker_budget` counts unique worker identities, not resumed turns by the same owner or QA worker. The default ceiling is 14 unique workers and two full-Review waves. A budget checkpoint blocks another spawn but never blocks aggregation of reports already completed.

## Commands

```text
pipeline_state.py init --project-root <root> --feature <slug> --requirements <prd> --spec <spec> --plan <plan> --plan-sha256 <exact-approved-sha> --base-revision <exact-revision> [--decision-ledger <repository-path>] [--integration-owner <id>] [--required-convergence-audits 2|3] [--max-workers <n>] [--max-full-review-waves <n>]
pipeline_state.py preflight-complete --project-root <root> --run-id <id> --resource-budget-check pass|fail --capability <name>=available|not_required|planned_manual|blocked_user|blocked_environment|error_test ... --report <report>
pipeline_state.py status --project-root <root>
pipeline_state.py user-authority-accept --project-root <root> --authority-id <stable-id> --approval-reference <explicit-checkpoint-reference> --statement <exact-accepted-statement>
pipeline_state.py context-capsule-create --project-root <root> --role engineer|researcher|decision_recorder|coverage_steward|documentation_finisher|reviewer|qa --phase <phase> --worker-id <id> --plan-sha256 <exact> --revision <exact> --authority <path=sha256:IDs>... --evidence <path=sha256:IDs>... [--decision-id DEC-NNN ...] [--finding-id <id> ...] [--coverage-identity-id <id> ...] [--allowed-path <path> ...] [--allowed-symbol <symbol> ...] [--exclusion <value> ...] [--command <exact> ...] --output-path <path>... --stop-condition <text> --max-authority-files <n> --max-evidence-files <n> --max-total-files <n> --max-payload-bytes <n> --max-estimated-tokens <n> --output <capsule.json>
pipeline_state.py context-capsule-check --project-root <root> --capsule <capsule.json>
pipeline_state.py acquire-write-lease --project-root <root> --role decision_recorder|engineer|documentation_finisher|recovery_remediator --phase <phase> --write-scope <scope-id> --worker-id <id> --capsule <validated-capsule.json>
pipeline_state.py release-write-lease --project-root <root> --lease-id <LEASE-ID> --result complete|incomplete|blocked|revoked --reason <text>
pipeline_state.py decision-record-complete --project-root <root> --recorder-id <id> --lease-id <id> --capsule <capsule.json> --semantic-packet <packet.json> [--adr-path <path> ...] --report <report>
pipeline_state.py slice-research-complete --project-root <root> --slice-id SLICE-NNN --base-revision <exact-active-revision> --owner-id <assigned-engineer> --bundle tests/<slug>/research/<bundle>.json [--bundle ... up to 3]
pipeline_state.py slice-research-not-required --project-root <root> --slice-id SLICE-NNN --base-revision <exact-active-revision> --owner-id <assigned-engineer> --reason <why-no-wide-discovery-is-needed>
pipeline_state.py coverage-plan-complete --project-root <root> --slice-id SLICE-NNN --steward-id <fresh-id> --capsule <capsule.json> --coverage-manifest <schema-2-planned.json> --report <report>
pipeline_state.py slice-scope-check --project-root <root> --slice-id SLICE-NNN --base-revision <exact-current-revision> --owner-id <assigned-engineer>
pipeline_state.py compute-revisions --project-root <root> --base-revision <git-or-manifest-id> [--product-file <path> ...] [--support-file <path> ...] [--evidence-file <path> ...] [--output tests/<slug>/verification/<manifest>.json]
pipeline_state.py engineer-complete --project-root <root> --run-id <id> --owner-id <id> --lease-id <id> --capsule <capsule.json> --slice-id SLICE-NNN --engineering-status pass --machine-checks pass --diff-inspection pass --semantic-handoff <semantic.json> [--scope-approval <exact-rebaseline-user-approval>] [--resolved-finding <id> ...] --report <report>
pipeline_state.py coverage-finalize --project-root <root> --scope-id <SLICE-NNN|feature> --steward-id <fresh-id> --capsule <capsule.json> --coverage-manifest <schema-2-finalized.json> --expected-actual-equality pass --mandatory-registration pass --automated-execution pass --report <report>
pipeline_state.py rebaseline-scope --project-root <root> --plan-sha256 <updated-exact-approved-sha> --user-scope-approval <explicit-user-decision-reference>
pipeline_state.py transfer-engineering-owner --project-root <root> --from-owner <id> --to-owner <fresh-id> --reason <explicit-handoff> [--slice-id SLICE-NNN]
pipeline_state.py documentation-complete --project-root <root> --mode normative_pre_review|derived_post_qa --worker-id <id> --lease-id <id> --capsule <capsule.json> --source-map <semantic-source-map.json> --report <report>
pipeline_state.py documentation-not-required --project-root <root> --mode normative_pre_review|derived_post_qa --plan-sha256 <exact> --policy-evidence <exact-reference>
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
pipeline_state.py recovery-remediation-complete --project-root <root> --run-id <id> --worker-id <id> --lease-id <id> --capsule <capsule.json> --machine-checks pass --semantic-report <semantic.json> --resolved-finding <id>... --report <report>
pipeline_state.py recovery-review-complete --project-root <root> --revision <all> --product-revision <product> --support-revision <support> --evidence-revision <evidence> --run-id <id> --reviewer-id <fresh-id> --status pass|fail --report <report>
pipeline_state.py authorize-iteration --project-root <root> --reason <director-decision>
pipeline_state.py authorize-budget --project-root <root> --additional-workers <n> [--additional-full-review-waves <n>] --reason <consolidated-need>
pipeline_state.py qa-capability-probe --project-root <root> --revision <all> --probe-id <id> --capability <name=status>... [--minimum-resume-action <name=action> ...] --report <report>
pipeline_state.py qa-complete --project-root <root> --revision <all> --product-revision <product> --support-revision <support> --evidence-revision <evidence> --run-id <id> --worker-id <id> --capsule <capsule.json> --status pass|fail_product|blocked_user|blocked_environment|error_test --manual-execution <schema-2-execution.json> --report <report> [--reason <text>] [--pending-identity <id> ...]
pipeline_state.py documentation-review-complete --project-root <root> --revision <current-all> --product-revision <qa-product> --support-revision <current-support> --evidence-revision <qa-evidence> --run-id <id> --reviewer-id <fresh-id> --capsule <capsule.json> --status pass|fail --report <report>
pipeline_state.py accept-finding --project-root <root> --id <minor-id> --reason <approved-risk> --approval-reference <user-decision>
pipeline_state.py ready --project-root <root>
```

Schema 9 is the current complete classification, scope, role, and verification schema. The controller rejects pre-v9 state and requires explicit reinitialization; it never guesses missing scope, reachability, acceptance, invariant, evidence-major, lease, decision, coverage, documentation, context, or handoff facts. State adds `implementation_state`, `feature_verification_state`, `active_write_lease`, append-only `write_lease_history`, `decision_ledger`, per-scope `coverage`, `documentation`, append-only `context_capsules`, and schema-2 `handoffs`. `--kind` remains a deprecated deterministic alias for `--finding-kind`; findings persist only as `finding_kind`. Product remediation closes the normalized blocking batch through `engineer-complete --resolved-finding`; non-product remediation uses `recovery-remediation-complete --resolved-finding`.

The new top-level state shapes are exact:

```json
{
  "implementation_state": {"status": "pending|in_progress|pass|invalidated", "revision": "exact or null", "coverage_manifest": "path or null"},
  "feature_verification_state": {"status": "pending|pass|invalidated", "product_revision": "exact or null", "support_revision": "exact or null", "evidence_revision": "exact or null"},
  "active_write_lease": null,
  "write_lease_history": [],
  "decision_ledger": {"path": "repository-relative JSONL", "sha256": "64 lowercase hex", "entry_count": 0, "active_decision_ids": [], "superseded_decision_ids": []},
  "user_authorities": [],
  "coverage": {"SLICE-001": {"planned_manifest": "path or null", "finalized_manifest": "path or null", "state": {}}},
  "documentation": {"normative": {}, "derived": {}},
  "context_capsules": [],
  "handoffs": []
}
```

`active_write_lease` is either `null` or the complete schema-1 lease from `role-artifacts-and-context.md`; histories are append-only. `implementation_state.status=pass` and `feature_verification_state.status=pass` are never inferred from phase names. Every referenced artifact carries a controller-validated path/SHA and exact revision binding.

`engineer-complete`, `decision-record-complete`, `documentation-complete`, `recovery-remediation-complete`, and `transfer-engineering-owner` generate and validate the canonical current revisions, change manifest, diff summary, and schema-2 handoff from controller state plus the actual checkout. Worker-supplied revision hashes/counts/manifests cannot satisfy these commands. Every command uses the active lease base revision as compare-and-swap authority and fails closed on drift, overlap, stale capsule, unexpected path/domain, or scope mismatch.

Write-capable completion commands accept only the exact schema-1 semantic packet defined in `role-artifacts-and-context.md`: a complete post-pass domain inventory, exact semantic annotations for every actual changed path, and structured open assumptions. This bounded input is not a mechanical manifest: the controller verifies it against the checkout and plan, then computes all revisions, counts, manifests, and handoffs itself. An incomplete inventory or any actual/declared path mismatch fails closed.

A successful role-complete command atomically releases its active lease and appends it to `write_lease_history`; callers do not invoke `release-write-lease` afterward. Use `release-write-lease` only for an incomplete, blocked, or revoked pass that performed no unaccepted drift. If the checkout changed before an incomplete/blocked release, the controller retains the lease/hold until it classifies or restores the exact bounded pass without destructive reset.

## Revision identities

- `product_revision`: runtime source, manifests, configuration, approved feature documents, normative ADRs/contracts, and other behavior-defining product documents.
- `support_revision`: derived handoff/index/operator documentation and non-normative project metadata whose correction does not change runtime or public behavior.
- `evidence_revision`: tests, fixtures, deterministic harnesses, and verification inputs.
- `revision`: SHA-256 of the product/support/evidence identity tuple.

Use `compute-revisions`; do not invent a hash recipe in a worker. Its domain hash is SHA-256 of UTF-8 `base:<base_revision>\n` followed by ordinal-sorted `<repo-relative-path>\0<exact-byte-sha256>\n`. The composite hash is SHA-256 of `product:<product_revision>\nsupport:<support_revision>\nevidence:<evidence_revision>\n`.

Freeze the complete domain path inventory before completion. A path belongs to exactly one of product, support, or evidence. Exclude reports, logs, screenshots, coverage/revision manifests, `.agentic-pipeline/` state, and the tracked controller-managed `docs/engineering/deferred-findings.json`. `compute-revisions` rejects the backlog path in every domain.

Reset rules:

- product change invalidates convergence, Review, QA, and open-gate evidence;
- support-only change before QA preserves clean runtime and full Reviews, but requires focused recovery verification and fresh QA;
- derived support-only change after passed QA preserves QA only when product/evidence identities remain exactly equal to the QA-covered identities and one fresh `documentation-closure` reviewer passes on the current support revision; otherwise use ordinary invalidation;
- evidence-only change preserves clean product and completed full Reviews, but requires recovery verification and fresh QA;
- report-only change invalidates neither identity;
- PRD/spec drift stops progress until explicitly reconciled;
- development-plan or approval-evidence drift stops progress until the plan is re-approved on its exact SHA;
- a passed parallel convergence wave or convergence authorization resets the consecutive product-change counter;
- a recovery authorization resets the failed-recovery counter.

Final Review rework routing is derived from the registered blocking `finding_kind` batch before state mutation: product findings route to product revalidation, while evidence/support findings route to evidence recovery. A caller-supplied conflicting `--rework-scope` fails closed. Recovery identities and inventory hashes are always derived from the current checkout by the controller; no legacy transition accepts caller-provided product/support/evidence hashes.

## Findings and gates

A finding is an evidence-backed defect. A gate is only an unavailable user action, environment, tool, service, setup, automation, or observation path. There is no “product gate.”

- QA `fail_product` requires a registered current-revision controller-classified blocking QA product finding.
- QA may register only product findings.
- Non-pass QA requires a reason; gate results also require pending registered manual identity IDs.
- Passing QA cannot contain pending mandatory identities.
- A registered identity invalidated by a product finding is `blocked_by_finding`, not a gate.
- `production_reachability=unknown` opens `finding_triage`; it never sends work directly to an Engineer.
- Every supported nonblocking `preexisting_adjacent` or `out_of_scope` finding must be atomically upserted into `docs/engineering/deferred-findings.json` and carry its canonical `#DEF-*` reference before positive convergence or Final Review finalization. The director is the only backlog writer; workers emit candidates. Fingerprints exclude revision/title/specific trigger and merge unique conditions, impacts, evidence, and independent occurrences. Resolved rediscovery reopens; severity escalation requires new evidence.
- Return the issue to current scope when candidate work introduced/worsened it, changed contract/feature reachability exposes it, it blocks acceptance/invariant, or it presents a current-solution safety risk. A material return requires the existing `scope_expansion_hold`, explicit user-approved updated plan, and `rebaseline-scope`.

## Artifacts and identities

- Track canonical feature and repository-required supporting product documents.
- Treat the approved development plan as queue authority. State records its path/hash, mode, ordered slices, active slice, per-slice base/result identities and status, phase/write-scope leases, integration route, handoff manifests, remediation queue, and per-owner remediation-return counters. `single_owner` records one implementation scope, not a lifetime worker identity.
- Each slice state records its machine-readable Scope Contract, current pre-edit check, scope churn, and append-only scope history. Global scope history/churn and rebaseline history persist across owner changes. Neither `authorize-iteration` nor `transfer-engineering-owner` clears `scope_expansion_hold`.
- Ignore `/tests/`; store verification, Review, QA, revision manifests, logs, and captures under `tests/<feature>/`.
- Store bounded research bundles under `tests/<feature>/research/` (or the controller-assigned runtime research path). Research bundles are reports, never product, support, or evidence revision inputs.
- Each schema-1 research bundle contains `brief` and `result`. The brief records `brief_id`, question, active `slice_id`, related `requirement_ids`, exact `base_revision`, `seed_paths`, `allowed_paths`, `allowed_symbols`, `exclusions`, `requested_evidence`, positive `max_files`, `stop_condition`, and its own `output_path`. The result records the same brief/base identity, fresh `researcher_id`, canonical `brief_sha256`, status, inspected paths/symbols, owners/contracts/precedents, lifecycle/integration risks, minimal edit/reuse points, unresolved questions, and pointer-only out-of-brief candidates. Raw dumps are invalid.
- Keep controller state in `.agentic-pipeline/`; mutate it only through `pipeline_state.py`.
- Prefer an exact-current route Engineer for bounded remediation and use one QA worker ID across gated resumes. A fresh Engineer may take a later phase/slice only through a controller-generated exact-revision handoff; the fourth return is a mandatory transfer. Use unique run IDs and fresh distinct identities for convergence, full Review, targeted closure, and recovery/documentation Review.
- Pass every specialized worker a schema-1 bounded context capsule with exact paths/SHAs/IDs/evidence and numeric limits. Do not pass long chat history, transcripts, or raw reasoning. The context budget gate must pass before spawn and state preserves actual file/byte/token metrics.

The append-only repository decision ledger is a product input. The Decision Recorder may record only accepted authority. User authority requires a separate lease-free `user-authority-accept` checkpoint before any recorder capsule: the caller supplies a stable authority ID, explicit approval reference, and exact statement, and the controller writes an immutable append-only receipt/digest. This checkpoint records an asserted approval but does not authenticate the human. Capsule creation and Decision Recorder packets can only cite the prior receipt; they never mint authority. Decision recording is accepted only at `preflight`, `slice_research`, or `slice_coverage_planning`; a later decision attempt fails closed and requires explicit replan/reinitialization, so downstream implementation/verification state cannot remain inconsistently invalidated. The controller generates sequence/timestamps/hashes and rejects mutation/reordering/deletion of prior entries. Normative ADR synchronization cites active decision IDs and completes before Review.

Every engineering scope requires a schema-2 Coverage Steward plan before editing and finalization after code freeze. Coverage keeps these dimensions independent:

- acceptance criteria mapped or exact gaps;
- expected exact identities registered versus actual exact identities registered;
- expected mandatory identities versus separately registered actual mandatory identities;
- automated identities executed and passed;
- manual identities executed and passed or explicitly deferred with a gate.

Finalization requires case-sensitive exact set equality for all expected/actual IDs and separately for mandatory IDs. Extra actual identities fail as strictly as missing ones until an append-only controlled amendment cites an accepted decision, normalized finding, or approved rebaseline assigned to the current Steward capsule. The controller validates the complete historical amendment prefix/schema/unique IDs/hash chain, and the union of newly affected acceptance IDs must equal the controller-derived semantic planned-to-final AC change set exactly. `implementation_state=pass` requires mapped ACs, equality, mandatory registration, no coverage gap, and all mandatory automated identities executed/passed; mandatory manual identities may remain pending. `feature_verification_state=pass` additionally requires all mandatory manual identities executed/passed and none deferred/blocked. At readiness, terminal handoff `coverage_state` must equal the freshly validated current feature aggregate, not merely exist. Read the Coverage Steward contract for schema 2.

Every writing pass produces controller-generated change-manifest and diff-summary artifacts. The change manifest has exact phase/scope/role/worker/lease IDs, base/result revisions, and `change_manifest[]`; every product entry has `path`, `symbols`, slice/scope ID, requirement/acceptance/decision IDs, validated semantic reason, change kind, and `touchpoint_id` for a shared file. The diff summary has exact phase/base/result identities and domain path sets; product entries record symbols, non-negative lines changed, component, change kind, and lifecycle/ownership/public-contract booleans. Actual path sets must match the controller-observed diff exactly. Workers return bounded semantic annotations and final diff inspection, not these mechanical artifacts.

The controller compares the current pass diff against approved allowlists, exclusions, touchpoint symbols/change kinds, domain inventory, and budgets. A smoke test never authorizes a product path. Unmapped files/symbols, excluded paths/components, drive-by cleanup/refactor, material lifecycle/ownership/public-contract changes, unapproved shared touchpoints, mismatched sets/counts, or budget breach persist `scope_expansion_hold` before the candidate revision is accepted. A material change is accepted only when its `--scope-approval` exactly matches the latest same-base, same-plan `rebaseline-scope`; a handoff or unrelated approval cannot authorize it.

Every controller-generated schema-2 handoff always includes active `decision_ids`, structured `coverage_state`, structured `documentation_state`, and `open_assumptions` with owner/validation point/impact. It also contains generated base/result identities and canonical change/diff paths. Missing fields fail closed; an assumption cannot replace authority, coverage, or a gate.

`documentation-not-required` accepts only an approved global and per-slice contract written as `not_required | policy=<exact-reference>` and an argument exactly equal to that reference. Placeholder prose or a caller-invented reference fails closed.
