# Current artifacts, authority and handoffs

Read this reference when a GameDev stage consumes an approved source, records approval or hands work to another stage. These are facts about the actual artifacts and permissions, recorded in ordinary project documents and evidence.

## Resolve the real inputs

Use the supplied project/feature, repository instructions and existing documents to locate the canonical PRD, specification and plan. Preserve existing paths, IDs, revision conventions and accepted decision sources. Do not copy documents to another namespace to obtain a favorable ready claim. For a new artifact, use the project's document convention; a sibling document is a reasonable default when the location is unambiguous and within authorized writes. Ask only if the target or permission remains materially unclear.

Read current complete obligations, relevant source sections and actual decisions. An ID inventory or summary helps retrieval but does not replace criterion text. Keep proposals, implementation observations and engineering choices separate from product authority. Stable source file/heading pointers can carry traceability where IDs are absent.

Record the canonical path and exact current SHA-256 of each artifact and consumed source; include a revision if one actually exists. Hash real bytes with an available trusted tool, for example `Get-FileHash -Algorithm SHA256 -LiteralPath <path>` or Python `hashlib.sha256(Path(path).read_bytes()).hexdigest()`. Normalize digest case for comparison. Do not guess a hash from text or put an artifact's own hash inside its approved bytes.

## Actual decisions and approval

Decision authority and approval authority are distinct. Direct user confirmation supplies only the content actually confirmed. An explicit delegation supplies only its stated decisions or approval powers, within its target and limits. Preserve the original authorization statement or trusted locator and the actual actor; never label an agent decision as a direct user decision. Silence, permission to continue, upstream readiness, a worker's success and an `approved` label alone do not approve a document.

The approving actor reads the complete current artifact and actually decides on those exact bytes. Direct user approval binds the concrete document/SHA presented to the user. A delegated actor may make and record the real approval when its existing authority covers that artifact; another routine technical approval chain is unnecessary. Permission to approve is not itself the decision. An independent reader checks meaning and sufficiency; a favorable review is approval only if that reader also has actual approval authority and exercises it explicitly.

In an explicitly invoked [GameDev Orchestrator](../../gamedev-orchestrator/SKILL.md) cycle, Requirements always works through the current scope with the user, including an existing PRD. The user must actually approve the complete current PRD before Specification, Planning, product edits or runtime work; this final Requirements approval is never delegated in that mode. The invocation and human PRD checkpoint authorize subsequent technical stages and their approval within those approved obligations and existing execution permissions, unless the user reserved an additional checkpoint. A qualified stage owner or reviewer may then exercise technical approval after reading the complete current artifact and satisfying its stage's independent reading requirements. Draft completion, a favorable review or this authority alone never supplies the actual approval. Material product amendments return to Requirements and the user for the needed current PRD revision and approval.

A new full-cycle invocation may reuse prior direct human approval only after Requirements reconciliation finds no new meaning or unresolved choice and the current user explicitly confirms that this exact unchanged PRD remains the requirements for this cycle. An old record alone is insufficient. Resuming that same confirmed cycle after compaction/restart preserves its checkpoint while current source/approval bindings remain valid; recovery does not itself require another interview or approval.

Keep the decision in the project's existing durable handoff/evidence record. If none exists, one small sibling `<artifact-name>.approval.md` is sufficient. Reuse a matching record rather than generating competing approvals. Preserve these retrievable facts in ordinary prose or a compact table:

- Project/feature, canonical approved artifact path and exact SHA-256; revision when applicable.
- Canonical consumed source paths/versions/hashes, relevant decision locators and actual approval scope.
- Real approving actor and explicit decision on that artifact/SHA.
- Original direct or delegated authority, with its statement/locator, limits and applicable conditions.

Record this only after an actual decision; a placeholder or recommended approval is not a record of consent. Creating the record does not change the frozen document. A conversation approval may be preserved with its actual quote/locator and the exact document/SHA shown there. Existing project records with these facts remain valid without a special heading or serialization.

## Consume and change sources truthfully

The consuming stage reads the explicitly identified approval and authority source, compares artifact/source hashes with current bytes and confirms the actor's actual decision and limits. Conflicting claims require reconciliation. Readiness describes this verified condition; it creates no authority or state by itself.

A changed artifact no longer has approval from its previous exact-byte record. Preserve the old record as history, assess the affected obligations and obtain applicable approval of the current content. If an approved input changed, return its concrete drift to the owning stage, assess affected downstream work and bind current inputs before declaring downstream readiness. Do not rewrite approved product sources to accommodate a convenient implementation. An unrelated technical note or local tool repair does not change product authority or automatically restart upstream stages.

Ordinary implementation task refinement can proceed within the approved obligations and permissions without editing the plan or seeking another routine technical approval. A required product amendment, permission change or actual conflict belongs to its responsible decision maker. Retain the affected obligation and continue unrelated authorized work.

## Short stage handoff

Return the stage's `PRD_READY`, `SPEC_READY` or `PLAN_READY`, project/feature, canonical artifact and source paths/versions/hashes, actual approval locator/actor, concrete outstanding matters and the next action. Include useful evidence locators and pertinent execution limits. No workflow state file or machine envelope is required.

A standalone stage stops after this result. Opening a document, receiving readiness or suggesting a next action does not authorize that stage. An explicitly invoked [GameDev Orchestrator](../../gamedev-orchestrator/SKILL.md) parent may consume each actual handoff and delegate the next authorized stage in the same root chat under its human PRD checkpoint and bounded technical delegation. GameDev Implementation does not activate upstream stages. Bounded research/review/correction tasks perform their supplied task and return, without restarting a whole stage.

Before a writer handoff, finish pending mutations and make current ownership/quiescence clear. A replacement reconciles sources, files, useful evidence and real owner/process state before resuming; it does not blindly replay an old next action. Keep brief current notes at the project's existing evidence location when recovery actually needs them. User-owned runtime sessions and unrelated projects remain outside the handoff.
