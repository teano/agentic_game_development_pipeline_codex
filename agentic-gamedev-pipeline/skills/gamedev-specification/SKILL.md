---
name: gamedev-specification
description: Explicit-invocation only. Use for `$gamedev-specification` or an explicitly authorized Specification stage. Design a project-grounded, sufficient technical specification from approved requirements, check its coverage and bind its actual approval; do not activate for ordinary design.
---

# GameDev Specification

Describe how the confirmed feature can be implemented in the actual project. Preserve every original obligation and explicit constraint while choosing the smallest sufficient technical design. Specification does not create new product requirements or implement the feature.

## Read authority and project evidence

At entry, use the shared [project, artifact and approval procedure](../gamedev-pipeline/references/artifacts-and-approval.md) to resolve the checkout and feature, find the canonical PRD and verify its current approval. Locate any existing specification or draft before writing. For a new specification, use the resolved feature directory and project convention. An incomplete or stale PRD needs its specific Requirements correction. Use current technical evidence to inform the design within the approved requirements.

Read the complete requirements, acceptance criteria, constraints and exclusions. Preserve existing IDs/anchors or stable file/heading locators. Inspect the actual code/assets/data, extension points, conventions and available verification methods needed to design this feature. Check relevant engine and package versions, enabled integrations, supported targets and feasibility findings from Requirements against the current project. Use bounded repository research or current authoritative API documentation where a concrete uncertainty changes the design. Record observed facts separately from selected engineering details and unresolved questions. Do not invent existing APIs, commands, ownership or capability.

Choose routine technical details within the authorized scope. Return a material product gap or contradiction to Requirements and its responsible user or delegated product owner; do not fill it from GDD, assumed best practice or a convenient design. A required permission change also needs its responsible actor. Retain the affected obligation and continue independent design within confirmed product meaning. Technical setup or recoverable method uncertainty may be implementation work when its question, dependency and expected resolution are clear. Do not launch the product runtime or change product source/assets as a specification step unless the task separately authorizes that action.

## Author the sufficient design

For a new module, changed state owner, cross-module link or public boundary,
trace the design against the [architecture review baseline](../gamedev-pipeline/references/architecture-review.md).
Record the relevant ownership, direction, composition and placement. Have the
independent reader challenge those decisions before approving the specification.

Use the project's specification format and one author for the canonical file. The stage owner may author directly or delegate bounded authoring; another writer starts only after ownership is safely transferred. Give delegated work the actual criterion text, relevant project evidence, existing design state and concrete write boundaries. Select settings for new authors, researchers and independent readers using the [GameDev model settings](../gamedev-pipeline/references/agent-model-policy.md).

Make the following clear where they matter to this feature:

- Observable behavior, its original requirement/criterion sources and the production path that supplies it.
- Responsibilities and extension points, data/state changes, interfaces and integration seams that must agree.
- Important invariants, lifecycle/failure/repeat behavior actually required by sources or necessary for those integrations.
- At a consequential seam, give the worker a concrete example that distinguishes the intended behavior, such as an older save, a callback arriving after its window closes, or a reference view for an approved pose.
- How each original obligation and real constraint is achieved and observed, including documentation duties and cross-cutting requirements.
- Genuine prerequisites, technical uncertainty and explicit exclusions; separate selected technical choices from product decisions still needed.

Scale detail to the actual risk. A small feature can use a short design; risky interfaces may need exact signatures, data examples or state transitions. Avoid an exhaustive class list, generic architecture, compulsory empty sections or a second PRD. Technical consequences may explain how a confirmed requirement will work; they must not add independently choosable product semantics. Preserve an explicitly required interface or method rather than replacing it for convenience.

## Check and correct the current artifact

Compare the complete draft with the actual PRD and project: every obligation is covered, exclusions survive, interfaces are plausible, responsibilities fit and an implementer can understand the approach. For a substantial or consequential design, obtain an independent read by someone who did not author it; also perform any independent review explicitly required by the task. Give the reader raw criteria, relevant project facts and current specification, without an intended verdict.

Return concrete defects to the author with source locator, affected passage and expected correction. Resolve missing coverage, contradictions and unsupported complexity; optional preferences are not blockers without a requirement, convention or demonstrated defect. Reuse the author for related corrections. The independent reader rechecks affected content on the changed draft, preserving unaffected valid observations. Do not silently omit a finding, fabricate review credit or accept a different document than the one inspected.

Ordinary technical recovery, research and correction stay within this stage's authorization. Change the hypothesis or method when an attempt fails repeatedly. Ask only for a real unresolved product/permission decision or an unavailable external prerequisite after feasible recovery, keeping the precise outstanding item visible.

## Finish this stage

Freeze the checked specification, compute its SHA-256 and obtain actual approval within the shared authority procedure. Preserve current PRD bindings and useful independent findings/evidence. If approval is not delegated, present the complete concrete document and exact SHA for the responsible user's decision. Favorable author/reviewer reports alone do not provide that approval.

Use the shared handoff format. Return `SPEC_READY: yes|no` with the canonical specification and PRD paths/versions/hashes, actual check locators and remaining defects or decisions. `yes` requires current approved inputs, sufficient complete design, required independent checking and actual approval of these bytes. Give `NEXT_ACTION: $gamedev-development-plan` when ready, otherwise the specific owning-stage correction or missing decision.

Stop at the handoff. An explicitly invoked [GameDev Orchestrator](../gamedev-orchestrator/SKILL.md) parent may continue Planning after verifying this actual approval. Its human-approved PRD checkpoint supplies bounded technical delegation, so exercise applicable approval without another routine user checkpoint; honor any additional checkpoint the user reserved. A standalone stage keeps the ordinary approval procedure and stops. This stage itself grants no implementation, publication or additional permissions.
