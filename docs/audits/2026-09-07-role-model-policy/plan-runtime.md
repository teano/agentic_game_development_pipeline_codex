# PLAN and runtime model policy proposal

Read-only inventory of implementation sources at v0.16.0. This file is a proposal, not activation of a GameDev stage. No applicable AGENTS.md was found in the repository or ancestor directories.

## Verified roles and proposed defaults

| Entry or role | Model | Effort | Existing workload |
| --- | --- | --- | --- |
| Development Plan Director, user-started stage | `gpt-5.6-sol` | `high` | Own authority, plan drafting, deterministic controller transitions and exact approval; delegate analytical decomposition. |
| Planning Analyst | `gpt-5.6-sol` | `high` | Fresh read-only analysis of coupling, scope, seams, dependencies, context budgets, coverage and documentation. |
| Runtime Director, user-started implementation stage | `gpt-5.6-terra` | `xhigh` | Preserve the user's established startup selection; issue bounded assignments, consume controller results and route recovery. |
| Runtime Plan / `planner` | `gpt-5.6-sol` | `high` | Confirm approved authority and distinguish unresolved product decisions from reversible technical matters. |
| Runtime Slice / `slicer` | `gpt-5.6-terra` | `high` | Confirm approved decomposition, exact scope and retained implementation-path coverage after reconfiguration. |
| Engineering / `engineer` | `gpt-5.6-terra` | `xhigh` | Implement a bounded game slice, coupled tests and editor changes within exact write paths. |
| Review / `reviewer` | `gpt-5.6-sol` | `high` | Independent semantic code review, reachable game paths, mandatory behavior and minimal sufficient complexity. No measured need for a higher default. Same profile for post-Docs Review; review target remains controller-owned. |
| QA / `qa` | `gpt-5.6-terra` | `high` | Perform assigned real player/editor acceptance scenarios, track identity completeness and distinguish missing environment from product failure. |
| Docs / `documentation_finisher` | `gpt-5.6-terra` | `medium` | Bounded documentation edits with fidelity to several approved and verified sources. |
| Standalone Coverage Advisory | `gpt-5.6-terra` | `high` | Explicit-only source-to-identity mapping analysis; not a runtime worker. |

The exact model/effort pairs above are available in the current collaboration tool metadata. Role fit is a workload-based policy judgment, not a model benchmark. No need for default Astra, max effort, or inherited root settings. Luna could handle simpler documentation formatting, but the actual Docs contract requires cross-source fidelity; Terra medium is a bounded default without adding a second dispatch classification.

`pipeline_v2/model.py` defines exactly six worker roles in `ROLES` (lines 30-37), with semantic tasks in `_PHASE_TASKS` (lines 816-823). `ready` is a seventh phase, not a worker: `assignment_identity` rejects it. Coverage Steward is standalone advisory and explicitly has no pipeline assignment. Development Planning does not use Decision Recorder or deferred-findings agents. Research briefs are semantic context for existing workers, not extra automatically dispatched roles.

## Dispatch, continued work and recovery

- Apply explicit defaults in real tool arguments. For collaboration use `spawn_agent` with `fork_turns: "none"`, `model` and `reasoning_effort`; the packet must be self-contained. Full-history forks cannot select a different model.
- A current user-started Director cannot switch its own model through instructions. Document the four user startup choices separately; preserve the user's current selection and report a material mismatch without pretending a switch happened. This lane preserves Sol high for PLAN and Terra xhigh for runtime.
- Explicit user model/effort choices override defaults, including a more capable or more expensive requested choice. Preserve their actual scope in the relevant handoff; a Director startup choice alone is not an override for every child.
- Reuse only where the existing lifecycle permits it. Planning init/reinitialize/revise-approved require a fresh Analyst. Every runtime assignment requires a fresh worker; role defaults apply again. A same-assignment artifact-format repair goes to the same worker, preserving its selection.
- `followup_task` cannot change an existing collaboration agent's model/effort. Preserve the existing owner and selection; report a requested selection mismatch honestly and apply a changed selection at the next existing permitted fresh dispatch or turnover. Do not replace an owner, create duplicate owners or restart product work solely to apply defaults.
- Upstream recovery preserves an already assigned stage owner and user constraints, routed through the parent. If delegation is authorized and no owner exists, dispatch that upstream Director using its own stage default, not the runtime root's model.
- Context turnover carries the effective model/effort and explicit override scope in its existing checkpoint. Rotation does not raise effort or select a more expensive model. A blocked/failed result follows the existing controller route; no automatic escalation ladder.
- If a required model/effort or tool override is unavailable, report the exact dispatch limitation and obtain a replacement selection; do not silently inherit, downgrade, or claim that prose applied the requested model.

## Smallest implementation surface and ownership

Root/shared-policy owner: one shared policy section in `skills/gamedev-pipeline/references/stage-handoff-invariant.md` or one directly linked short reference. Keep actual model assignment out of controller schema and artifacts. This inventory found no runtime code that spawns a model: `model.py` emits the semantic worker packet and the Director owns tool dispatch. No deterministic runtime emitter change is necessary.

This lane can own `skills/gamedev-development-plan/SKILL.md`, `skills/gamedev-pipeline/SKILL.md`, `skills/gamedev-pipeline/references/pipeline-protocol.md` (only if the dispatch wording needs alignment), and brief links in Engineer/Review/QA/Docs/Coverage skills if the shared invariant link is insufficient. Prefer wiring the two Director entrypoints to shared policy and preserving existing worker links; avoid repeating the whole table in every skill. Root owns shared invariant, README/four-stage startup table and cross-lane reconciliation. No controller, schema, global config or product changes proposed.

## Verification

Review actual spawn/reuse/rotation/upstream/repair routes against the shared explicit-argument rule. Check six runtime roles plus Planning Analyst and standalone advisory classification. Verify Markdown references and `git diff --check`. Use existing focused skill checks if their scope applies; do not invent phrase-lock tests or run real GameDev stages for this instruction-only change. Controller regressions are unnecessary unless code is changed.
