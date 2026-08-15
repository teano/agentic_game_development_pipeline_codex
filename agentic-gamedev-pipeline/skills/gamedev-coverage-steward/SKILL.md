---
name: gamedev-coverage-steward
description: Explicit-invocation only. Use only when the user explicitly requests `$gamedev-coverage-steward` for a standalone advisory review of supplied coverage data. Inspect exact automated/manual identity mappings without editing product, tests, artifacts, or controller state. Do not activate for pipeline runtime, ordinary testing, QA, or coverage execution.
---

# GameDev Coverage Advisory

## Activation gate

Proceed only on direct explicit user invocation. Pipeline runtime coverage is controller-owned; this skill has no pipeline assignment, capsule, worker, state, or handoff authority. A request to add tests, run QA, review code, improve coverage, or complete a runtime transition is not authorization. Do not activate another GameDev stage.

Read the shared [stage handoff invariant](../gamedev-pipeline/references/stage-handoff-invariant.md) and [coverage-contract.md](references/coverage-contract.md). The contract is canonical for schema 2, identity equality, amendments, execution dimensions, and implementation/verification eligibility.

Remain read-only. Inspect only coverage data and exact source references supplied or explicitly authorized by the user. Do not persist or mutate coverage artifacts.

## Review supplied coverage

- For planned data, inspect acceptance-to-identity mappings, expected and mandatory sets, coordinates, assertions/observations, prerequisites, and ownership.
- For finalized data, inspect expected/actual equality, mandatory-set equality, acceptance mappings, automated results, gaps, and the manual matrix.
- Report missing authority or evidence as an advisory gap; do not invent behavior, amend registrations, or route runtime work.

Return `COVERAGE_COMPLETE: yes|no`, inspected inputs, mapping/set results, gaps, prerequisites, exclusions, and `NEXT_ACTION: terminal-advisory-coverage`. Do not implement/change tests, execute QA, set product `blocking`, waive identities, edit controller state, or spawn another stage. Stop.
