# Current artifacts, authority and handoffs

Read this reference to locate the project and artifacts, consume an approved source, record approval or hand off work. Bounded workers use the project and artifact locators relevant to their assignment.

## Resolve the real inputs

Identify the game project, its actual checkout or workspace, and the feature before choosing inputs or writing. Use the request, attached workspace and prior handoff as leads. Verify the root against project instructions and relevant engine or project files. Check the active revision and relevant local changes where version control applies. If several checkouts exist, use the one assigned to the work and verify where artifact paths resolve. Preserve existing user work.

Use explicit paths and recent handoffs as search leads. Follow repository documentation conventions, feature indexes, links between artifacts, approval records and existing evidence. When a path is missing, search the intended project by feature name, task ID, document title or known obligation. Open plausible candidates. Compare their scope, source links and approval records to identify the canonical PRD, specification and plan for this feature. A matching filename or newer modification time alone does not identify the current artifact. Ask for the smallest clarification only after the available evidence leaves material ambiguity. Show the relevant checkout or candidate paths and what distinguishes them. If an input is absent or stale, identify the missing artifact or binding and the responsible stage.

Use the dedicated feature directory established by Requirements for new specification and plan files unless the project or user specifies a different destination for that artifact. If the handoff omits the folder, resolve it from the located PRD and feature docs. For a legacy feature without a dedicated directory, follow the project's document convention. An authorized sibling of the verified input is a fallback when the destination is unambiguous. Reuse any existing canonical artifact in place, including a current draft when resuming work. Preserve paths, IDs, revision conventions and accepted decision sources. Do not create a duplicate artifact or infer approval from its location.

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

Return the stage's `PRD_READY`, `SPEC_READY` or `PLAN_READY`, project root/checkout, feature name or ID, established feature directory if present, canonical artifact and source paths/versions/hashes, actual approval locator/actor, concrete outstanding matters and the next action. Include useful evidence locators and pertinent execution limits. For a bounded worker, pass the same locators as relevant to its assignment, with the applicable source passages, candidate identity and permitted output paths. No workflow state file or machine envelope is required.

A standalone stage stops after this result. Opening a document, receiving readiness or suggesting a next action does not authorize that stage. An explicitly invoked [GameDev Orchestrator](../../gamedev-orchestrator/SKILL.md) parent may consume each actual handoff and delegate the next authorized stage in the same root chat under its human PRD checkpoint and bounded technical delegation. GameDev Implementation does not activate upstream stages. Bounded research/review/correction tasks perform their supplied task and return, without restarting a whole stage.

Before a writer handoff, finish pending mutations and make current ownership/quiescence clear. A replacement reconciles sources, files, useful evidence and real owner/process state before resuming; it does not blindly replay an old next action. Keep brief current notes at the project's existing evidence location when recovery actually needs them. User-owned runtime sessions and unrelated projects remain outside the handoff.
