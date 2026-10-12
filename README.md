# Agentic Game Development Skills

Bundle version: [0.22.1](agentic-gamedev-pipeline/VERSION).

Explicit-only Codex skills for a complete authorized feature: Requirements → Specification → Planning → Implementation. Each stage uses the actual project, preserves original decisions/IDs and returns current source and approval bindings. Existing project formats are sufficient; the bundle requires no workflow controller or external specification service.

Invoke [gamedev-requirements](agentic-gamedev-pipeline/skills/gamedev-requirements/SKILL.md) to turn confirmed product decisions into a canonical PRD with observable acceptance. [gamedev-specification](agentic-gamedev-pipeline/skills/gamedev-specification/SKILL.md) designs the smallest sufficient implementation from that approved PRD and project evidence. [gamedev-development-plan](agentic-gamedev-pipeline/skills/gamedev-development-plan/SKILL.md) organizes coherent increments, full obligation coverage, checks and final integrated acceptance.

Each standalone stage stops after its handoff. `PRD_READY`, `SPEC_READY` and `PLAN_READY` describe verified artifact readiness; they grant no next-stage permission. An explicitly authorized full-cycle parent may consume those handoffs and delegate the next stage. Actual direct/delegated decisions and approvals remain within their original scope, recorded through [artifact and approval bindings](agentic-gamedev-pipeline/skills/gamedev-pipeline/references/artifacts-and-approval.md).

## Implementation

[gamedev-pipeline](agentic-gamedev-pipeline/skills/gamedev-pipeline/SKILL.md) orchestrates the authorized product work: every development slice gets a newly created bounded [Engineer](agentic-gamedev-pipeline/skills/gamedev-engineer/SKILL.md) to implement and repair and a new [Independent Checker](agentic-gamedev-pipeline/skills/gamedev-qa/SKILL.md) to observe the actual candidate; findings return for repair/rechecking within the same slice team. A separate new independent checker, uninvolved in earlier slices, observes final integrated behavior once. If the last planned unit already performs this acceptance, it supplies the final check. [Review](agentic-gamedev-pipeline/skills/gamedev-review/SKILL.md) and [Documentation](agentic-gamedev-pipeline/skills/gamedev-documentation-finisher/SKILL.md) are optional specialists for concrete tasks. The orchestrator owns coverage and a brief recoverable note.

Ordinary permitted engineering/setup recovery proceeds within the task. Real product contradictions or permission changes go to their responsible decision maker. A green automated suite alone does not prove a playable feature; required interaction is observed in the actual permitted runtime. Unperformed observations remain `not_run`. The workflow grants no push, release, spending or unrelated stage activation.

## Breaking version

This version replaces the previous controller workflow throughout the bundle. Its runtime/state code, operational parsers, native envelopes, alternative contracts, suites and historical guides are removed from the current source. Git history retains prior versions. Existing product documents and decision semantics remain valuable inputs, but previous operational states supply no authority for this workflow; current artifacts and actual approval records do. This change does not migrate project state, relink installations or resume production runs.

## Validation

Run `python agentic-gamedev-pipeline/scripts/test_skills.py` for current package integrity: skill discovery metadata, explicit-only invocation, local reference resolution and supporting-document reachability. The tests use PyYAML, also used by Codex skill-creator's syntax validator. These deterministic checks do not establish document meaning, actual consent or product acceptance.

Use the installed skill-creator's `quick_validate.py` for changed skill syntax. Independently forward-test the four stages with realistic raw inputs in an isolated workspace: preserve original obligations, bind real approvals, start useful work, repair findings and observe the final integrated flow. Production execution and external actions require their own actual authorization.
