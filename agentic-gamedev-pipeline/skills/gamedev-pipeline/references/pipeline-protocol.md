# Pipeline protocol

This file is the normative state, command, revision, and artifact contract. Role behavior belongs in the corresponding skill; severity and readiness policy belongs in `severity-and-readiness.md`.

## State machine

```text
engineering -> convergence_hold -> engineering
engineering -> review
review -> engineering | evidence_recovery
evidence_recovery -> recovery_review -> qa | evidence_recovery | recovery_hold | engineering
recovery_hold -> evidence_recovery
review -> qa -> ready | engineering | qa
```

| Current state | Recorded result | Next state | Required next action |
|---|---|---|---|
| `engineering` | Engineer `CHANGED` below limit | `engineering` | Fresh convergence Engineer |
| `engineering` | Engineer `CHANGED` reaches limit | `convergence_hold` | Director checkpoint |
| `convergence_hold` | Director authorization | `engineering` | Fresh convergence Engineer |
| `engineering` | Engineer `CLEAN` | `review` | Two parallel full Reviews |
| `review` | Aggregate product rework | `engineering` | Fresh full Engineer with one batch |
| `review` | Aggregate evidence-only rework | `evidence_recovery` | One evidence-remediation Engineer |
| `review` | Aggregate pass | `qa` | Fresh runtime QA |
| `evidence_recovery` | Evidence remediation completes | `recovery_review` | Fresh closure reviewer |
| `recovery_review` | Pass | `qa` | Fresh runtime QA |
| `recovery_review` | Reproduced product defect | `engineering` | Fresh full Engineer |
| `recovery_review` | Evidence failure below limit | `evidence_recovery` | Resume bounded recovery |
| `recovery_review` | Evidence failure reaches limit | `recovery_hold` | Director checkpoint |
| `recovery_hold` | Director authorization | `evidence_recovery` | Resume the frozen evidence batch |
| `qa` | `pass` | `ready` | Run `ready` |
| `qa` | `fail_product` | `engineering` | Fresh full Engineer; no user confirmation |
| `qa` | user/environment/test gate | `qa` | Resolve only the recorded pending scenarios |

`next_action.user_input_required` is authoritative for user involvement. A director checkpoint is internal unless an unresolved product, scope, credential, external-action, or user-only decision exists. At `ready`, an open minor finding yields `request_residual_risk_decision`; only the user may accept that risk.

## Commands

```text
pipeline_state.py init --project-root <root> --feature <slug> --requirements docs/features/<slug>/product-requirements.md --spec docs/features/<slug>/technical-specification.md --slice <id>
pipeline_state.py status --project-root <root>
pipeline_state.py compute-revisions --project-root <root> --base-revision <git-or-manifest-id> [--product-file <path> ...] [--evidence-file <path> ...] [--output tests/<slug>/verification/<manifest>.json]
pipeline_state.py engineer-complete --project-root <root> --revision <all> --product-revision <product> --evidence-revision <evidence> --run-id <id> --machine-checks pass --coverage-manifest <coverage.json> --production-change-scope none|local|architectural [--resolved-finding <id> ...] --report <report> --audit-complete
pipeline_state.py review-complete --project-root <root> --revision <all> --product-revision <product> --evidence-revision <evidence> --run-id <id> --reviewer-id <id> --status pass|fail --report <report>
pipeline_state.py review-finalize --project-root <root> --revision <all> --decision pass|rework [--rework-scope product|evidence] --report <aggregate> [--reason <text>]
pipeline_state.py add-finding --project-root <root> --id <id> --source engineer|review|qa --kind product|evidence --severity critical|major|minor --title <text> --evidence <text> --revision <all>
pipeline_state.py start-evidence-recovery --project-root <root> --revision <all> --product-revision <product> --evidence-revision <evidence> --finding-id <id>... --reason <text>
pipeline_state.py evidence-remediation-complete --project-root <root> --revision <new-all> --product-revision <same-product> --evidence-revision <new-evidence> --run-id <id> --machine-checks pass --coverage-manifest <coverage.json> --resolved-finding <id>... --production-change-scope none --report <report>
pipeline_state.py recovery-review-complete --project-root <root> --revision <all> --product-revision <product> --evidence-revision <evidence> --run-id <id> --reviewer-id <fresh-id> --status pass|fail --report <report>
pipeline_state.py authorize-iteration --project-root <root> --reason <director-decision>
pipeline_state.py qa-complete --project-root <root> --revision <all> --product-revision <product> --evidence-revision <evidence> --run-id <id> --status pass|fail_product|blocked_user|blocked_environment|error_test --report <report> [--reason <text>] [--pending-scenario <id> ...]
pipeline_state.py accept-finding --project-root <root> --id <minor-id> --reason <approved-risk> --approval-reference <user-decision>
pipeline_state.py ready --project-root <root>
```

`resolve-finding` is a phase-preserving administrative compatibility command. Product remediation must close persisted findings atomically through `engineer-complete --resolved-finding`; evidence remediation uses `evidence-remediation-complete --resolved-finding`.

## Revision identities

- `product_revision`: production source, manifests, configuration, approved feature documents, and repository-required supporting product documents.
- `evidence_revision`: tests, fixtures, deterministic harnesses, and verification inputs.
- `revision`: SHA-256 of the product/evidence identity pair.

Use `compute-revisions`; do not invent a hash recipe in a worker. Its domain hash is SHA-256 of UTF-8 `base:<base_revision>\n` followed by ordinal-sorted `<repo-relative-path>\0<exact-byte-sha256>\n`. The composite hash is SHA-256 of `product:<product_revision>\nevidence:<evidence_revision>\n`.

Freeze the complete domain path inventory before completion. A path cannot belong to both domains. Exclude reports, logs, screenshots, coverage/revision manifests, and `.agentic-pipeline/` state.

Reset rules:

- product change invalidates clean Engineer, Review, QA, and open-gate evidence;
- evidence-only change preserves clean product and completed full Reviews, but requires recovery verification and fresh QA;
- report-only change invalidates neither identity;
- PRD/spec drift stops progress until explicitly reconciled;
- `CLEAN` or a convergence authorization resets the consecutive product-change counter;
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
- Use unique Engineer/QA run IDs and distinct reviewer IDs.
- Pass workers paths, IDs, revisions, commands, and output locations; do not pass long chat history or raw reasoning.

Every terminal Engineer/evidence-remediation pass requires a schema-1 coverage manifest. Each unique entry is exactly one of:

- `covered`: non-empty implementation evidence and exact test records containing `file`, `suite`, `symbol`, `assertions`, `execution`, and `evidence`;
- `finding`: normalized `finding_ids`;
- `not_applicable`: explicit `reason`.

The manifest records matching product and evidence revisions. The technical director must also compare its IDs with every approved acceptance/evidence row; mere schema validity is not complete coverage.
