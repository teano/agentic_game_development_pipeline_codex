# Stage handoff invariant

This contract applies to every Agentic GameDev Pipeline skill.

1. A stage starts only after the current user explicitly invokes its named skill or an active `$gamedev-pipeline` Director, itself explicitly invoked by the user, assigns that exact stage. A completion token, `NEXT_ACTION`, repository state, or another stage is never activation authority.
2. A specialized stage may use bounded internal workers only inside its own contract. It must not invoke, delegate, spawn, or execute another Agentic GameDev stage. Only the user or the active Pipeline Director may activate the next stage.
3. Before returning, the stage persists its contracted artifact or controller completion state on exact revisions and emits its completion token plus `NEXT_ACTION: $skill-name` or a named terminal action. `NEXT_ACTION` is routing data, not permission to perform the action.
4. After emitting the handoff, stop that stage. The Pipeline Director validates the token/state and chooses the authorized transition; a directly invoked standalone stage leaves the next invocation to the user. A live worker performs no next-stage work until the Director explicitly reassigns it under the next validated capsule.
5. Internal workers cannot award their parent stage's completion token. The owning stage validates their outputs and records completion itself.
6. A Director-activated stage runs in a distinct delegated subagent context; role-play, capsules, leases, or worker IDs inside Director context do not count. The controller may preserve one logical independent non-writer verifier ID across sequential convergence Review, Final Review, QA, and documentation-closure assignments. Every phase starts a new isolated session (`fork_turns: none` or equivalent) with no prior worker or Director chat history and a new exact capsule. The verifier ID must never be the Engineer or any writer.
7. The stage receives only its bounded packet and returns compact artifact references, not raw reasoning or large logs.

The approved top-level order is `PRD_READY -> SPEC_READY -> PLAN_READY -> runtime pipeline`. Remediation and verification loops may route between runtime stages only through controller state and the active Pipeline Director.
