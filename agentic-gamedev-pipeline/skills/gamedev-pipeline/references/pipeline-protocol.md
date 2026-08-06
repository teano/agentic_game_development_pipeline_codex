# Pipeline protocol

This file is the normative state, command, revision, and artifact contract. Role behavior belongs in the corresponding skill; severity and readiness policy belongs in `severity-and-readiness.md`.

## State machine

```text
preflight -> engineering
engineering -> convergence | convergence_hold
convergence -> review | engineering | convergence_hold
review -> engineering | evidence_recovery | qa
engineering -> convergence -> closure_review -> qa | engineering
evidence_recovery -> recovery_review -> qa | evidence_recovery | recovery_hold | engineering
recovery_hold -> evidence_recovery
review -> qa -> ready | engineering | qa
```

| Current state | Recorded result | Next state | Required next action |
|---|---|---|---|
| `preflight` | Resource proof passes | `engineering` | Spawn one persistent writing owner |
| `preflight` | Resource proof fails | `preflight` | Reconcile specification budgets; spawn nobody |
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

`next_action.user_input_required` is authoritative for user involvement. A director checkpoint is internal unless an unresolved product, scope, credential, external-action, or user-only decision exists. At `ready`, an open minor finding yields `request_residual_risk_decision`; only the user may accept that risk.

`worker_budget` counts unique worker identities, not resumed turns by the same owner or QA worker. The default ceiling is 14 unique workers and two full-Review waves. A budget checkpoint blocks another spawn but never blocks aggregation of reports already completed.

## Commands

```text
pipeline_state.py init --project-root <root> --feature <slug> --requirements docs/features/<slug>/product-requirements.md --spec docs/features/<slug>/technical-specification.md --slice <id> [--required-convergence-audits 2|3] [--max-workers <n>] [--max-full-review-waves <n>]
pipeline_state.py preflight-complete --project-root <root> --run-id <id> --resource-budget-check pass|fail --capability <name>=available|not_required|planned_manual|blocked_user|blocked_environment|error_test ... --report <report>
pipeline_state.py status --project-root <root>
pipeline_state.py compute-revisions --project-root <root> --base-revision <git-or-manifest-id> [--product-file <path> ...] [--support-file <path> ...] [--evidence-file <path> ...] [--output tests/<slug>/verification/<manifest>.json]
pipeline_state.py engineer-complete --project-root <root> --revision <all> --product-revision <product> --support-revision <support> --evidence-revision <evidence> --run-id <id> --owner-id <persistent-owner> --machine-checks pass --coverage-manifest <coverage.json> --production-change-scope none|local|architectural [--resolved-finding <id> ...] --report <report> --audit-complete
pipeline_state.py transfer-engineering-owner --project-root <root> --from-owner <id> --to-owner <id> --reason <explicit-handoff>
pipeline_state.py convergence-audit-complete --project-root <root> --revision <all> --run-id <id> --reviewer-id <fresh-id> --lens persistence-lifecycle|config-security-capacity|integration-runtime-docs --status pass|fail --report <report>
pipeline_state.py convergence-finalize --project-root <root> --revision <all> --decision pass|rework --report <aggregate>
pipeline_state.py review-complete --project-root <root> --revision <all> --product-revision <product> --support-revision <support> --evidence-revision <evidence> --run-id <id> --reviewer-id <id> --status pass|fail --report <report>
pipeline_state.py review-finalize --project-root <root> --revision <all> --decision pass|rework [--rework-scope product|support|evidence|recovery] [--revalidation targeted|full] --report <aggregate> [--reason <text>]
pipeline_state.py closure-review-complete --project-root <root> --revision <all> --run-id <id> --reviewer-id <fresh-id> --status pass|fail --report <report>
pipeline_state.py add-finding --project-root <root> --id <id> --source engineer|convergence|review|qa --kind product|support|evidence --severity critical|major|minor --title <text> --evidence <text> --revision <all>
pipeline_state.py start-evidence-recovery --project-root <root> --revision <all> --product-revision <product> --support-revision <support> --evidence-revision <evidence> --finding-id <id>... --reason <text>
pipeline_state.py recovery-remediation-complete --project-root <root> --revision <new-all> --product-revision <same-product> --support-revision <support> --evidence-revision <evidence> --run-id <id> --worker-id <id> --machine-checks pass --coverage-manifest <coverage.json> --resolved-finding <id>... --production-change-scope none --report <report>
pipeline_state.py recovery-review-complete --project-root <root> --revision <all> --product-revision <product> --support-revision <support> --evidence-revision <evidence> --run-id <id> --reviewer-id <fresh-id> --status pass|fail --report <report>
pipeline_state.py authorize-iteration --project-root <root> --reason <director-decision>
pipeline_state.py authorize-budget --project-root <root> --additional-workers <n> [--additional-full-review-waves <n>] --reason <consolidated-need>
pipeline_state.py qa-complete --project-root <root> --revision <all> --product-revision <product> --support-revision <support> --evidence-revision <evidence> --run-id <id> --worker-id <id> --status pass|fail_product|blocked_user|blocked_environment|error_test --report <report> [--reason <text>] [--pending-scenario <id> ...]
pipeline_state.py accept-finding --project-root <root> --id <minor-id> --reason <approved-risk> --approval-reference <user-decision>
pipeline_state.py ready --project-root <root>
```

`resolve-finding` is a phase-preserving administrative compatibility command. Product remediation closes the complete normalized mixed batch atomically through `engineer-complete --resolved-finding`; non-product remediation uses `recovery-remediation-complete --resolved-finding`. `evidence-remediation-complete` remains a CLI alias for compatibility.

## Revision identities

- `product_revision`: runtime source, manifests, configuration, approved feature documents, normative ADRs/contracts, and other behavior-defining product documents.
- `support_revision`: derived handoff/index/operator documentation and non-normative project metadata whose correction does not change runtime or public behavior.
- `evidence_revision`: tests, fixtures, deterministic harnesses, and verification inputs.
- `revision`: SHA-256 of the product/support/evidence identity tuple.

Use `compute-revisions`; do not invent a hash recipe in a worker. Its domain hash is SHA-256 of UTF-8 `base:<base_revision>\n` followed by ordinal-sorted `<repo-relative-path>\0<exact-byte-sha256>\n`. The composite hash is SHA-256 of `product:<product_revision>\nsupport:<support_revision>\nevidence:<evidence_revision>\n`.

Freeze the complete domain path inventory before completion. A path belongs to exactly one of product, support, or evidence. Exclude reports, logs, screenshots, coverage/revision manifests, and `.agentic-pipeline/` state.

Reset rules:

- product change invalidates convergence, Review, QA, and open-gate evidence;
- support-only change preserves clean runtime and full Reviews, but requires focused recovery verification and fresh QA;
- evidence-only change preserves clean product and completed full Reviews, but requires recovery verification and fresh QA;
- report-only change invalidates neither identity;
- PRD/spec drift stops progress until explicitly reconciled;
- a passed parallel convergence wave or convergence authorization resets the consecutive product-change counter;
- a recovery authorization resets the failed-recovery counter.

## Findings and gates

A finding is an evidence-backed defect. A gate is only an unavailable user action, environment, tool, service, setup, automation, or observation path. There is no “product gate.”

- QA `fail_product` requires a registered current-revision critical or major QA product finding.
- QA may register only product findings.
- Non-pass QA requires a reason; gate results also require pending scenario IDs.
- Passing QA cannot contain pending scenarios.
- A scenario invalidated by a product finding is `blocked_by_finding`, not a gate.

## Artifacts and identities

- Track canonical feature and repository-required supporting product documents.
- Ignore `/tests/`; store verification, Review, QA, revision manifests, logs, and captures under `tests/<feature>/`.
- Keep controller state in `.agentic-pipeline/`; mutate it only through `pipeline_state.py`.
- Reuse one engineering owner ID across product passes and one QA worker ID across gated resumes. Use unique run IDs and fresh distinct identities for convergence, full Review, targeted closure, and recovery Review.
- Pass workers paths, IDs, revisions, commands, and output locations; do not pass long chat history or raw reasoning.

Every terminal Engineer/recovery-remediation pass requires a schema-1 coverage manifest. Each unique entry is exactly one of:

- `covered`: non-empty implementation evidence and exact test records containing `file`, `suite`, `symbol`, `assertions`, `execution`, and `evidence`;
- `finding`: normalized `finding_ids`;
- `not_applicable`: explicit `reason`.

The manifest records matching product, support, and evidence revisions. The technical director must also compare its IDs with every approved acceptance/evidence row; mere schema validity is not complete coverage.
