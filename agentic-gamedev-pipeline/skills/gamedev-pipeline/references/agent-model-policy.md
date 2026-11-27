# GameDev model selection

Resolve `model` and `reasoning_effort` separately for every new agent. Use the first applicable value for each field:

1. The user's explicit instruction for this run, within its stated scope.
2. An applicable project instruction, such as `AGENTS.md`.
3. The rule for the actual operation in the current stage.
4. The role default.

A model-only override leaves effort to the next matching rule. Apply the most specific instruction within one source. A stage owner who delegates a task keeps the owner's settings. Pass applicable overrides and their scope to the next owner.

## Action rules

During Implementation the orchestrator chooses a worker for the outcome, the judgement it needs and the consequence of a mistake. Keep related routine steps with the current worker. Use an available script for deterministic operations. Choose the following settings when issuing an assignment.

| Implementation operation | Model | Reasoning effort |
| --- | --- | --- |
| Run a known CLI build or test recipe, collect specified logs, verify hashes or tabulate results with a fixed rule | `gpt-6-luna` | `low` |
| Apply a verified example to bounded data, localization, configuration or repeatable test cases | `gpt-6-luna` | `medium` |
| Implement game logic against a defined contract, design its tests, or independently review code and invariants | `gpt-6.2-sol` | `medium` |
| Implement a specified layout or 3D operation, operate the editor or browser, or check observable behavior and visual fidelity against a reference | `gpt-6.1-terra` | `medium` |
| Capture specified views through the editor or UI with a known procedure | `gpt-6.1-terra` | `low` |
| Diagnose an unresolved integration, migration, race or other consequential failure; independently assess a concrete risk of data loss | `gpt-6.2-sol` | `high` |
| Resolve an open art-direction decision, unusually complex spatial problem or cross-system question that needs specialist judgement | `gpt-6.2-astra` | `high` |

For mixed work, route by the decision that determines success. A specified HUD over a finished gameplay API can stay with one Terra worker. A new state contract and its tests belong with a Sol engineer. For combined review and QA, choose Sol when the decisive question is correctness of code or data, or Terra when it is the observed player flow. Final acceptance of a defined playable flow uses a fresh independent Terra checker; route a materially different risk by the table. Retain all required observations.

Reserve `xhigh` during Implementation for an identified difficult question that warrants more reasoning. Describe the question and why the lower setting is insufficient. If a selected default model is unavailable, use an available model capable of the assignment and record the substitution. Preserve explicit user and project constraints.

Outside Implementation, stage owners and independent readers use the stage defaults below. An upstream visual author or visual design reviewer uses `gpt-6.2-astra` by default. For any upstream assignment that resolves to `gpt-6.2-astra` and would take `high` from its role, keep the upstream `xhigh` setting. Explicit user, project or action effort takes precedence. For image or 3D work, the selected model operates the available tool. The tool controls its own backend.

## Role defaults

| Assignment | Model | Reasoning effort |
| --- | --- | --- |
| Full-cycle orchestrator | `gpt-6.2-astra` | `xhigh` |
| Requirements owner and PRD interview | `gpt-6.2-sol` | `high` |
| Research to locate a known fact | `gpt-6.2-sol` | `low` |
| Research to trace behavior, feasibility or conflicting sources | `gpt-6.2-sol` | `high` |
| Technical specification and architecture | `gpt-6.2-astra` | `xhigh` |
| Development plan | `gpt-6.2-sol` | `high` |
| Implementation orchestrator | `gpt-6.2-sol` | `high` |
| Implementation engineer or independent code reviewer | `gpt-6.2-sol` | `medium` |
| Independent gameplay QA and final integrated acceptance | `gpt-6.1-terra` | `medium` |
| Documentation from verified results | `gpt-6-luna` | `medium` |

These are recommended starting settings for a user-started chat. A running owner keeps its actual selection. On an authorized `spawn_agent` call pass `fork_turns="none"`, `model` and `reasoning_effort` as tool arguments. Record the decision in the existing implementation note at dispatch. Reuse the same author and checker for same-slice repairs. Add a read-only adviser only for a specific diagnostic or design question; return the actionable result to the original team.
