---
name: gamedev-development-plan
description: Explicit-invocation only. Use for `$gamedev-development-plan` or an explicitly authorized Planning stage. Turn approved requirements and specification into a project-grounded plan with coherent increments, preserved obligations, meaningful verification and an approved handoff; do not activate for ordinary planning.
---

# GameDev Development Plan

Produce a useful engineering handoff for [GameDev Implementation](../gamedev-pipeline/SKILL.md). Ground it in the actual project and approved sources so an implementer can begin without your private conversation. Planning does not build the feature or start implementation.

## Establish the actual inputs

Resolve the checkout, revision and relevant local changes, selected feature, canonical PRD/specification/plan, accepted decisions and execution limits. Preserve existing paths and IDs. Follow [artifact and approval bindings](../gamedev-pipeline/references/artifacts-and-approval.md) to verify current approved PRD/SPEC and bind the resulting plan. Readiness does not activate an unrequested stage.

Read the actual requirements, acceptance criteria, relevant specification passages, constraints, documentation duties and cross-cutting obligations. For large sources, inventory them and retrieve complete relevant sections. Summaries and ID lists do not replace meaning. Keep proposals and engineering context separate from accepted product decisions.

Inspect the implementation, extension points, data/assets, tests and supported build/run methods needed to plan this change. Establish interfaces, responsibility boundaries and invariants from evidence. Inspect command/tool locators already supplied before inventing a discovery task. Distinguish inspected facts, selected engineering choices and unknowns. A recipe alone proves neither capability nor execution.

Investigate uncertainty that changes the approach or ordering; delegate bounded research when useful. Ordinary technical setup, method repair and missing command details may remain implementation work with a concrete question and expected resolution. Do not modify product source/assets or launch its runtime as a planning step unless separately authorized. A contradiction affecting product meaning or a required permission needs its responsible decision; retain the affected obligation and continue independent work.

## Write the smallest useful plan

Use the project's plan convention. The optional [outline](assets/development-plan.md) illustrates useful content, not a heading schema. Add detail at risky seams and dependencies; avoid a second specification, universal manifest or prescribed test implementation.

Explain the concrete approach using inspected project locations and interfaces. Name necessary integrations and important engineering choices with their basis. Respect specification responsibilities and explicit boundaries. Prefer extending established behavior over introducing architecture the feature does not need. Likely filenames are estimates unless they are actual user-imposed write limits.

Arrange coherent work in dependency order. A small feature may be one unit; larger features benefit from increments with a dependable behavior/interface for the next unit. Use sequential ownership for coupled files or mutable scenes. A technical enabler is a valid increment when its immediate dependent behavior and verification are clear. Arbitrary file/layer splits are insufficient handoffs. Sequential ownership limits parallel mutation; it does not permit agent reuse across slices.

For each increment, make these facts clear:

- Concrete outcome, trigger/starting state and original requirement/specification locators.
- Project areas/resources, required integrations and actual edit/read limits, exclusions or protected responsibilities.
- Dependencies/prerequisites, interfaces/state that must change together and the result consumed by later work.
- Known check/tool or input procedure, expected outcome, needed environment and restrictions. Include failure/repeat/exit behavior when the sources or integration require it.

Plan a fresh Engineer and independent QA/checker for every development slice or coherent implementation unit, regardless of its name; any separate reviewer or specialist actually needed is also new to that unit. Preserve the approved plan's unit boundaries, including unstarted units; do not merge or rename units to bypass fresh teams because files are coupled, scope is small or reuse is convenient. Explicitly user-authorized plan changes remain valid. Make compact factual handoffs and relevant primary sources sufficient for workers without inherited root/prior-slice transcripts. Transfer ownership only after previous writes/jobs and runtime operations are quiescent, preserving the runtime instance and code/WIP. Same-slice debugging and repair stay with that team.

Account for every original requirement, acceptance criterion, constraint and specification/documentation obligation in a compact mapping to work and checks. Preserve IDs/anchors or source file/heading pointers. Cross-increment criteria may map to several units but still require a complete integrated result. Retain obligations outside authorized execution scope with their missing action and owner when known.

Plan final acceptance on the whole integrated feature, including the actual user flow and seams; slice PASS results do not replace it. Each acceptance-only unit, including final acceptance, gets a new independent checker uninvolved in earlier slices. An Engineer is needed only for repair, with a new author for that acceptance/repair unit and rechecking by its checker. A last planned unit that performs final integrated acceptance supplies this check once; do not add duplicate final QA or repeat unchanged observations. Compilation, static review, mocks and unit tests support evidence but cannot replace required interaction with the real product. Preserve prescribed verification and actually approved alternatives. Describe external prerequisites and whether they block an increment or final acceptance, without assuming credentials, devices or publication permission. Missing local tools call for diagnosis/setup. Mark future checks as planned and unavailable observations as outstanding.

## Check, approve and hand off

Read the complete draft against its sources: an implementer can start, dependencies are feasible, every original obligation survives, exclusions remain and final checks observe the requested behavior. Use an independent read for complex or consequential plans when it can expose a real coverage or seam defect; perform explicitly required review. Correct valid findings without accepting optional scope expansion.

Freeze the checked plan, compute its SHA-256 and obtain actual approval using the shared authority procedure. Exercise already delegated approval when it covers this artifact. Without applicable approval, deliver the concrete complete plan and exact SHA for the responsible decision. Preserve its PRD/SPEC bindings and name the durable approval record. Do not infer approval from worker success or upstream readiness.

An unchanged approved plan can be reused after current input/approval verification. On correction, preserve prior approval/history and bind the resulting bytes. Routine implementation refinement within approved obligations can proceed without rewriting the plan. Source drift requires the concrete owning-stage correction and affected plan assessment.

Return `PLAN_READY: yes|no`, project/feature, canonical plan path/current SHA-256, PRD/SPEC paths/versions/hashes, approval locator/actor, work order and any precise outstanding defect or decision. `yes` means current approved sources, a complete usable plan and actual approval of these plan bytes. Future product checks remain planned; readiness does not claim that they ran. Give `NEXT_ACTION: $gamedev-pipeline` when ready, otherwise the specific missing decision or responsible stage correction.

Stop at this handoff. An already authorized full-cycle parent may continue Implementation; this stage itself starts no writer or product runtime and grants no publication permission.
