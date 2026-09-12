# Director lifecycle

Read for ownership, waiting and consumption of an issued runtime worker. Other roles need only their own terminal artifact contract.

## Director child-result consumption

After spawning any phase worker issued by the runtime, the Director owns that exact child until its terminal result and MUST wait using the available coordination primitive. The Director MUST NOT send a final response, claim `work continues asynchronously`, or otherwise relinquish the turn while that child is live.

After the child reaches a terminal result, the Director MUST re-read public controller status, prove that the same active assignment owns the exact returned output artifact, execute that assignment's exact public controller `complete` action including for a blocked outcome, and re-read the resulting public controller status. With no child owning an active assignment and no completed child artifact remaining unconsumed, execute the resulting authorized `next_action`; an available `accept`, `next`, or Director decision is still work in this run. Finalize only on the controller's terminal result, a genuine unresolved user prerequisite, an explicit user stop, or the incident/context handoff required here. Report an assignment as issued only when it exists in `active_assignment`; a proposed assignment in `next_action` is pending.

## Event-driven waiting

While a child works and no independent authorized work remains, wait for its completion, question, blocker or error. Use `wait_agent({timeout_ms:600000})` when that coordination primitive is available. It wakes early for messages or user input; ten minutes is a watchdog maximum, not a delay before handling an event. A worker sends meaningful changes itself, not periodic progress summaries.

Only on that ten-minute watchdog inspect bounded lifecycle/last-activity evidence to establish whether the owned child is running, blocked or stalled. No message alone does not prove a stall. Do not ask for a transcript, reread instructions, resubmit a packet or restart a role merely because time passed. Keep pending questions and artifacts until resolved or consumed. The lifecycle owner performs this check; do not add a second observer or polling service. A real error or new user instruction is handled immediately under the existing role/recovery rules.

Use the public `step` helper for one exact mechanical next/complete/accept action and assignment export; see [delivery contract](delivery-contract.md). A semantic decision, recovery fact, ready phase, missing artifact or stop still requires the normal Director route. The helper never replaces child liveness evidence, user authority or candidate verification.
