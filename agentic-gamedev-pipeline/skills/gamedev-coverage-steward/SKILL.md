---
name: gamedev-coverage-steward
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-coverage-steward` or an active, explicitly invoked `$gamedev-pipeline` Director delegates exact coverage planning or finalization. Register and validate exact automated/manual identities without editing product or tests. Do not activate for ordinary testing, QA, or coverage work.
---

# GameDev Test Coverage Steward

## Activation gate

Proceed only on the explicit activation described above. A request to add tests, run QA, review code, or improve coverage is not authorization. Do not activate another GameDev stage.

Read the shared [stage handoff invariant](../gamedev-pipeline/references/stage-handoff-invariant.md) and [coverage-contract.md](references/coverage-contract.md). The contract is canonical for schema 2, identity equality, amendments, execution dimensions, and implementation/verification eligibility.

Accept only a controller-validated capsule with exact authority, IDs, revisions, allowed evidence/output paths, and capsule payload ceilings. Remain read-only to product source, configuration, tests, fixtures, approved documents, decisions, and controller state. Write only the assigned coverage artifact/report.

## Use one mode

### `plan-before-engineering`

Map every assigned approved acceptance ID to exact planned automated/manual identities. Register the complete expected set, explicit mandatory set, coordinates, assertions/observations, prerequisites, and owning slice. Return gaps instead of inventing behavior; a missing product choice needs accepted authority, not a coverage convention.

### `finalize-after-code-freeze`

Read the frozen plan and actual registrations at exact identities. Validate sorted unique expected/actual equality, separate mandatory-set equality, acceptance mappings, planned proof adequacy, automated results, gaps, and the exact manual matrix. Accept an amendment only under the authority/hash-chain rules in the contract. Manual work remains pending until QA records its independent dimensions.

## Complete the stage

Return `COVERAGE_COMPLETE: yes|no`, mode, steward/capsule IDs, exact revisions, schema-2 manifest path/SHA, mapping and identity-set results, automated/manual dimensions, gaps, pending identities/prerequisites, amendment authorities, and exclusions.

- successful planning -> `NEXT_ACTION: $gamedev-engineer`;
- successful finalization -> `NEXT_ACTION: $gamedev-documentation-finisher` when normative docs are required, otherwise `NEXT_ACTION: $gamedev-review`;
- incomplete/gap -> `NEXT_ACTION` names the same stage, exact decision, or exact remediation owner required by the controller.

Do not implement/change tests, execute QA, set product `blocking`, waive mandatory identities, edit controller state, or spawn another stage. Do not execute `NEXT_ACTION`; stop.
