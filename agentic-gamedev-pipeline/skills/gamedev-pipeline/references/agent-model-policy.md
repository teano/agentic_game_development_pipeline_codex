# GameDev model selection

For each new agent, resolve `model` and `reasoning_effort` separately. Use the first applicable value for each field in this order:

1. The user's explicit instruction for this run, within its stated scope.
2. An applicable model-selection instruction in the game's project instructions (such as `AGENTS.md`).
3. A matching pipeline action rule below.
4. The role default for this assignment.

Match the work the agent will actually perform. Within one source, prefer the more specific matching instruction. For a mixed assignment, use the action that determines the requested result. For example, laying out a HUD and wiring its buttons includes visual authoring. Fixing a button callback and opening the HUD to verify it is a behavior change. A coordinator planning or delegating a visual task keeps the coordinator settings. Pass applicable instructions and their scope to the next owner, who resolves settings for its own workers.

## Action rules

Edit this table for pipeline-wide preferences. Add a row describing the action and the fields it overrides. A dash leaves that field to the next applicable rule or role default. When the selected model is `gpt-6.2-astra` and the effort comes from a role default of `high`, use `xhigh`. An effort explicitly set by the user, project or action rule takes precedence.

| Action | Model | Reasoning effort |
| --- | --- | --- |
| Create or revise UI layouts, artwork or generated images, 3D models or scenes, fonts, color palettes, or other visual assets and styling | `gpt-6.2-astra` | — |
| Judge visual quality, such as typography, composition, colors or layout fidelity | `gpt-6.2-astra` | — |

For image generation and 3D work, the selected model operates the available image or 3D tool. The tool determines its own rendering or generation backend.

## Role defaults

For a user-started chat these are recommended starting settings. A running chat or worker retains its actual selection.

| Assignment | Model | Reasoning effort |
| --- | --- | --- |
| Full-cycle orchestrator | `gpt-6.2-astra` | `xhigh` |
| Requirements owner and PRD interview | `gpt-6.2-sol` | `high` |
| Research to locate a known fact | `gpt-6.2-sol` | `low` |
| Research to trace behavior, feasibility or conflicting sources | `gpt-6.2-sol` | `high` |
| Technical specification and architecture | `gpt-6.2-astra` | `xhigh` |
| Development plan | `gpt-6.2-sol` | `high` |
| Implementation orchestrator | `gpt-6.2-sol` | `high` |
| Engineer implementing a bounded slice | `gpt-6.2-sol` | `high` |
| Engineer handling a save migration, race condition or cross-system failure | `gpt-6.2-astra` | `xhigh` |
| Independent code review | `gpt-6.2-astra` | `xhigh` |
| Code review where a defect could cause data loss | `gpt-6.2-astra` | `xhigh` |
| QA executing a defined scenario | `gpt-6.2-sol` | `medium` |
| QA primarily operating the Editor or UI to check observable behavior | `gpt-6.1-terra` | `medium` |
| Final integrated acceptance of the whole feature | `gpt-6.2-astra` | `xhigh` |
| Documentation from verified results | `gpt-6.2-sol` | `medium` |

For a stage helper writing or independently reading a PRD, specification or plan, use the corresponding stage setting. Use the research rows for bounded investigations. When the same checker owns code review and slice QA, use the review setting. For final integrated acceptance, use the final acceptance setting even when the scenario includes visual checks.

On an authorized `spawn_agent` call, pass `fork_turns="none"`, `model` and `reasoning_effort` as tool arguments. Relay any user override that also applies to later dispatches. A follow-up to an existing owner keeps its actual settings, including for same-slice repairs and rechecks. These defaults apply within the GameDev Pipeline and do not add workers or stages.
