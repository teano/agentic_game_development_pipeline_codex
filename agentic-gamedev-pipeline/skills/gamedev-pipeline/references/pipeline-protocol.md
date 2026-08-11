# Pipeline core protocol

This is the compact always-loaded Director contract. Phase details live in direct conditional references from `SKILL.md`; exact CLI syntax lives in each controller command's `--help`.

## Authority and stage order

`PRD_READY -> SPEC_READY -> PLAN_READY -> runtime pipeline` is mandatory. A missing/stale upstream token ends startup with `NEXT_ACTION` naming that stage; the Director does not run an upstream stage inside the current runtime activation.

Only the explicitly invoked `$gamedev-pipeline` Director or the current user may activate a named stage. Specialized stages persist completion and return `NEXT_ACTION`, then stop. Read `stage-handoff-invariant.md` for the canonical cross-stage rule.

Runtime initialization requires the canonical approved plan plus `.agentic-pipeline/development-plan-state.json` proving exact user-approved plan SHA and exact PRD/spec paths/hashes. The plan supplies one decision-ledger path, `writer_strategy: sequential`, and `single_owner|sequential_slices`. `init` validates or atomically creates the zero-entry ledger at that exact path and computes baseline identities.

Treat `.agentic-pipeline/state.json` and controller output—not narration—as phase authority. Never edit controller JSON directly.

## Exact preflight

Before any specialized runtime stage, the Director completes `preflight-complete` in its own context. The capability proof must exactly cover the closed union of approved plan prerequisites and controller platform minimums; missing and unexpected names both fail. Record each as `available|not_required|planned_manual|blocked_user|blocked_environment|error_test` plus exact report and resume data.

Preflight advances only when the resource budget passes and no capability has a blocking status. Otherwise it remains `preflight`; activate no worker. A later exact-revision QA probe revalidates execution capability and does not replace preflight.

## Core state flow

```text
approved plan -> preflight
preflight -> slice_research -> slice_coverage_planning -> slice_engineering
slice_engineering -> slice_coverage_finalization -> next slice | implementation_complete
implementation_complete -> normative_documentation -> convergence -> review
review/closure/recovery_review -> qa | routed remediation
qa -> derived_documentation | routed product remediation | qa resume gate
derived_documentation -> documentation_review -> ready
```

`scope_expansion_hold`, `finding_triage`, `convergence_hold`, and `recovery_hold` pause their recorded source phase and resume only through their exact controller command/evidence. `implementation_state` and `feature_verification_state` are independent; pending manual execution never makes a completed Engineer pass incomplete.

Preflight and QA probe the same exact capability set: the fixed platform minimum plus every canonical lowercase-hyphen `capability_prerequisites` ID in the approved global/slice plan contracts. A blocked capability must have one `--minimum-resume-action '<capability>=<owner>|<user_input_required>|<action>'`. `blocked_user` requires `user|true`; `blocked_environment` and `error_test` require `technical_director|false`. The controller persists proof version, exact required-ID set/digest, and resume-contract completeness. A loaded downstream state without the current exact proof enters `preflight_migration_hold`; run only `reinitialize-preflight`, then a fresh exact `preflight-complete`, before resuming its recorded phase. Compact status returns one deterministic blocker plus a bounded ID summary; use `status --section preflight` or `status --full` for complete maps.

Decision recording is legal only from `preflight`, `slice_research`, or `slice_coverage_planning`. A prior `user-authority-accept` receipt must exist before a recorder capsule. A later decision requires explicit upstream replan/reinitialization; it never applies ordinary in-place invalidation.

## Canonical command lookup

Use `python scripts/pipeline_state.py <command> --help` immediately before each mutation. Do not rely on a copied full signature. Phase routing uses these command families:

| Purpose | Commands |
|---|---|
| startup/preflight | `init`, `preflight-complete`, `reinitialize-preflight`, `status` |
| authority/decisions | `user-authority-accept`, `decision-record-complete` |
| capsules/leases | `context-capsule-create`, `context-capsule-check`, `acquire-write-lease`, `release-write-lease` |
| slices/coverage | `slice-research-complete`, `slice-research-not-required`, `coverage-plan-complete`, `slice-scope-check`, `engineer-complete`, `coverage-finalize` |
| revisions/docs | `compute-revisions`, `documentation-complete`, `documentation-not-required` |
| convergence/review | `convergence-audit-complete`, `convergence-finalize`, `review-complete`, `review-finalize`, `closure-review-complete` |
| findings/recovery | `add-finding`, `triage-finding`, `recovery-remediation-complete`, `recovery-review-complete` |
| QA/readiness | `qa-capability-probe`, `qa-complete`, `documentation-review-complete`, `accept-finding`, `ready` |
| holds/budgets | `rebaseline-scope`, `transfer-engineering-owner`, `authorize-iteration`, `authorize-budget` |

Generic `resolve-finding` is fail-closed and non-mutating. Product findings close atomically through the exact `engineer-complete --resolved-finding` batch; support/evidence recovery closes through `recovery-remediation-complete --resolved-finding`. Residual Minor acceptance requires an exact prior user-authority receipt bound to finding ID, revision, and reason.

## Revision and completion invariants

The controller computes product/support/evidence identities and composite revision from the complete frozen domain inventory. Product includes runtime/config/manifests, approved feature documents, decision ledger, and normative contracts. Support includes derived handoff/index/operator docs. Evidence includes tests/fixtures/deterministic inputs. Reports, logs, captures, capsules, controller state, coverage/manifests/handoffs, and deferred backlog are excluded.

Every writing completion supplies the exact semantic packet required by the current `--help`; the controller validates the checkout, scope, inventories, paths, revisions, counts, and handoff. Every review completion supplies an exact reviewer capsule; convergence/full/closure commands also supply their required component-credit manifest, and recovery review always supplies both capsule and credit manifest.

After every stage completion, validate controller state and route only its `NEXT_ACTION`. Continue automatically only when `user_input_required=false`. Declare only a production-ready candidate after `ready`; publication, deployment, migration, spending, and risk acceptance remain external.
