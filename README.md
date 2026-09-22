# Agentic Game Development Skills

Explicit-only Codex skills for an authorized, reproducible game-development cycle. The runtime controls exact authority, one writer, independent Review/QA and real verification evidence; it does not replace product decisions or grant publication permission.

## Entry points

Use `$gamedev-requirements`, `$gamedev-specification`, `$gamedev-development-plan` for their individual stages, or explicitly request `$gamedev-pipeline` for the intended full-cycle scope. A full-cycle Director consumes each stage's real `PRD_READY`, `SPEC_READY`, `PLAN_READY` before production. Stage workers stop at their own handoff; tokens do not activate stages themselves.

The [authority contract](agentic-gamedev-pipeline/skills/gamedev-pipeline/references/authority-contract.md) preserves direct user decisions and explicit scoped delegation. It distinguishes product choice, exact-revision approval, run-state recovery and shared-pipeline maintenance. A delegated actor is recorded truthfully; there is no blanket autoapproval or forged user consent. A genuine runtime incident pauses product work; do not patch or bypass guards without applicable separate maintenance authority.

## Production cycle

```text
plan -> slice -> engineering -> review -> qa -> docs -> ready
```

One stable Engineer owns related implementation and remediation in its slice. Assignments remain distinct; independent Reviewer and QA have separate role aliases. Active controller checks return bounded compiler/test feedback while that Engineer is quiescent, without ending its assignment or granting semantic PASS. Independent Review retains stable finding IDs; QA proves each required identity through its actual path. New workers receive a bounded current packet rather than inherited conversation. Status questions do not end the run.

Start with the launcher's current help:

```text
python agentic-gamedev-pipeline/skills/gamedev-pipeline/scripts/pipeline_state.py --help
```

Global `--root`, `--feature` and optional `--brief` precede the command. State lives only in `.agentic-pipeline/Workflows/<feature>/`. `init` binds the exact approved `requirements`, `specification`, `plan` and ordered three-key caller slices; read scope is controller-derived. The optional verification manifest seals runnable recipes, dependencies, timeouts and conservative reuse categories once. No-op Plan/Slice confirmation is opt-in and guarded, not a substitute for approved upstream artifacts.

Use [Director lifecycle](agentic-gamedev-pipeline/skills/gamedev-pipeline/references/director-runtime.md), [delivery](agentic-gamedev-pipeline/skills/gamedev-pipeline/references/delivery-contract.md) and the relevant [execution/recovery](agentic-gamedev-pipeline/skills/gamedev-pipeline/references/execution-contract.md) route. `step` returns a typed outcome and next action; `check`, `rotate-owner`, `read-admit`, `recover-capability`, `reconcile` and `pin-runtime` retain their specific guards. The [protocol](agentic-gamedev-pipeline/skills/gamedev-pipeline/references/pipeline-protocol.md) documents exact boundaries and legacy-compatible recovery. Command help is authoritative for flags.

Candidate, authority, runtime, executable and environment bindings determine deterministic receipt reuse. Unknown dependencies rerun conservatively. Diagnostic-only journal observations do not waive semantic changes or counterevidence. Historical workflow evidence is provenance, not new product write permission. Product checks run on the canonical live checkout; immutable pinning copies only the pipeline bundle. Schema-10 `migrate` remains a fail-closed tombstone.

`ready` validates the integrated candidate and all required slices, then declares `PRODUCTION_READY_CANDIDATE`. Unexecuted mandatory manual/device checks remain unverified. Ready does not authorize deployment, publication, spending or risk acceptance. Missing host capacity is reported honestly; pipeline code cannot promise to free stuck host slots.

## Validation

```text
python agentic-gamedev-pipeline/scripts/test_skills.py
```

Instruction contracts check discoverability, schema examples and behavioral exercise integrity. The independent role exercises are separate evidence of instruction understanding; static phrase checks are not that evidence. Record actual outcomes and limitations in the run's audit.
