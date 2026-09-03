# Specification contract

## Canonical artifacts

Use the one repository-owned PRD and specification resolved from current user context, repository instructions, feature manifests/indexes, and existing artifacts. Both paths must remain inside the project root. Do not create a duplicate, symlink, move, or alternate namespace to accommodate the controller. If the repository provides more than one plausible pair, ask the user. For an empty repository with no convention, recommend `docs/features/<feature>/product-requirements.md` and its sibling `technical-specification.md` as a proposal and wait for confirmation.

Keep controller state and all helper/receipt/report artifacts under `.agentic-pipeline/Workflows/<feature>/`: `specification-state.json`, `helper-requests/`, `helper-results/`, `architect-receipts/`, and `proofreader-reports/`. Every controller invocation requires the same lowercase `--feature`; state binds both `feature` and `workflow_path`. A different, escaping, linked, or copied foreign workflow fails closed. State is operational evidence, not part of the specification hash. Never scan, archive, move, or delete a sibling workflow.

Preserve the repository's established trace convention. The controller accepts either flat fields:

```yaml
---
document_type: technical-specification
status: draft
revision: 1
language: Russian
source_prd_path: <repository-relative-prd-path>
source_prd_revision: 1
source_prd_sha256: <64 lowercase hex characters>
---
```

or the equivalent nested authority:

```yaml
---
document_type: technical-specification
status: draft
revision: 1
language: Russian
product_authority:
  path: <repository-relative-prd-path>
  revision: 1
  sha256: <64 lowercase hex characters>
---
```

Do not rewrite a valid repository-owned trace shape merely to prefer the other representation.

Use `status: draft` while editing and `status: approved` for the exact candidate submitted to the final Proofreader. Any semantic edit to an approved specification reopens it as a new draft revision.

## Revising specification authority

When a controller-accepted in-progress specification with an exact `accept-spec` receipt is in `reviewing` state with a completed `record-proofread` result in its active wave, and the canonical PRD receives a newly approved higher revision, use `revise-in-progress`. This route is valid only before runtime state or findings are bound. It requires unchanged canonical paths, exact controller-recorded specification and active-wave bytes, a specification trace matching the prior recorded PRD, a complete approved Requirements validation of the new PRD, a changed SHA, a strictly higher positive PRD revision approved after the current acceptance receipt, and a fresh Architect identity.

The controller uses a resumable pending transition, archives the prior PRD/specification/acceptance/Architect/wave/hold evidence with disposition `superseded_by_prd_revision`, increments the sole specification revision, updates the PRD trace, sets `status: draft`, and enters `awaiting_accept`. Archived findings and questions remain audit evidence only: they are neither current blockers nor readiness credit. The new authority requires a fresh `accept-spec` receipt, a fresh Proofreader cycle, and a fresh `confirm-ready` confirmation by the newly assigned Architect. Do not rerun `init`, delete state, or edit the JSON controller state.

### Revising an exact ready specification

`SPEC_READY` is immutable until a sanctioned revision is opened against exact current specification bytes equal to the recorded ready SHA. Use ordinary `revise-ready` when the canonical PRD has a newly approved, higher positive revision with changed exact bytes. Use explicit `revise-ready --specification-only` when the PRD path, revision, and exact bytes are unchanged and only the technical specification needs correction. Both routes require the canonical PRD to pass the complete approved Requirements validator before any pending state or specification bytes are mutated, canonical unchanged paths, the prior approved specification trace, and a fresh Architect identity not used by any earlier Architect or Proofreader. The PRD-change route additionally requires fresh higher PRD revision/approval authority. The controller atomically records a resumable pending transition, archives the prior authority/readiness/worker evidence, increments the sole unquoted positive specification `revision`, preserves or updates the existing PRD trace as appropriate, sets `status: draft`, and revokes live readiness/cycle state.

Schema-10 migration is unsupported by `git-tree-v1`. Any legacy state/findings residue fails closed with the stable instruction to archive it and run fresh Plan/`init`; no recovery token, retired import, reconstruction, or mixed-lineage bridge grants revision authority.

A sole valid direct v2 runtime provides two tokenless routes. The existing `revise-ready --specification-only` route still requires canonical v2 validation and a byte-nonmutating public `status` to prove the exact project/unchanged PRD/prior-specification authority, `active_assignment: null`, no open question, a command effect, and neither terminal state nor checkout recovery. Answered questions may remain only as validated audit history. The PRD-change route requires the newly approved higher positive PRD revision and changed exact bytes while the v2 stored authority still exactly binds the prior PRD and prior ready specification. Its byte-nonmutating public `status` must expose exactly the safe effect `next_action.kind: command`, `next_action.command: init`, and `next_action.user_input_required: false`. Because that later Pipeline `init` owns archival and reconfiguration of the superseded run, an old active assignment or open question is permitted on this PRD-change route. A non-`init` command, user-input requirement, terminal status, checkout recovery, unknown effect, or recovery token fails closed; the Specification controller creates no new retirement record, hold, or token.

For either v2 route, any schema-10 residue is the unsupported migration tombstone and requires archival plus fresh Plan/`init`. Multiple, malformed, foreign, or mixed v2 candidates fail closed. New tokenless v2 `recovery_authorization` receipts use nested schema 2 and record `revision_kind`, the exact prior runtime requirements and specification paths and SHAs, the runtime-state path, and the exact v2 state SHA. Authorization `schema` is an exact integer `1` or `2`; booleans and numeric lookalikes are invalid in both the live authorization and its archived receipt. The exact released nested schema-1 keyset (`schema`, null `token`, `reason`, `runtime_state_path`, `runtime_state_sha256`, `prior_spec_sha256`) remains compatible only for a canonical specification-only `ready_revision` pending transition or the latest canonical committed `ready_specification_revision_opened` receipt with an exact matching live authorization. It is normalized only in memory from the archived prior PRD/ready/specification authority; mixed, missing, extra, PRD-mode, ambiguous, or tampered forms fail closed without rewriting historical state or receipts. Pending completion and committed replay re-run the complete approved Requirements validator and require `new_prd` to equal the canonical live PRD path, frontmatter revision, and exact-byte SHA; a PRD-change receipt additionally requires the exact live `approved_at` and validator SHA, while a specification-only receipt has no extra PRD fields. This check occurs before any specification or controller write. `accept-spec`, every proofreading transition, and `confirm-ready` revalidate that same prior runtime binding and exact runtime bytes; they do not substitute the newly approved PRD or force a PRD-change authorization through the specification-only rules. Reopen ends in `awaiting_accept`, never ordinary `reviewing`; while its final history receipt, PRD, draft, runtime authorization, inputs, and lifecycle projection remain exact, a committed `revise-ready` replay is a byte-noop, and any drift or later Architect/lifecycle progress rejects it. `accept-spec` validates the exact current PRD/spec draft and records path/revision/hash/time/Architect/token. `start-cycle` fails closed unless that fresh receipt matches every current value; changed bytes or a stale/absent receipt require another `accept-spec`. At least one fresh Proofreader cycle and a fresh Architect `confirm-ready` are mandatory; no prior readiness evidence carries forward.

Specification state schema 2 persists one normalized worker-identity history. Loading schema 1 migrates it in place without discarding cycle or readiness evidence, but persists that migration only after the referenced canonical PRD passes the complete approved Requirements validator. A legacy or malformed approved PRD is not grandfathered: revise and reapprove the PRD, then reconverge exact downstream authority. Every Architect/Proofreader ownership and freshness comparison uses NFKC, surrounding-space trimming, and case folding, so case, whitespace, and full-width aliases cannot reuse a prior role identity.

## Scope and sufficiency invariant

This single operational invariant governs the Director, Generator, Technical Spec Architect, and Proofreader:

- The exact approved PRD is the complete product scope. Repository rules and concrete current-project evidence may clarify the smallest implementation needed for a named PRD ID or prove a necessary current integration path; they do not add product behavior, generality, non-functional obligations, or speculative future work.
- A finding is admissible only when it cites concrete current-project evidence, names the affected `PRD-REQ-*`, `PRD-NFR-*`, or `PRD-AC-*` ID and its material contradiction, missing mandatory behavior, unverifiable acceptance path, or unjustified specification complexity, and gives the smallest required resolution. Excess-complexity findings must identify the exact specification design and a simpler sufficient replacement.
- Theoretical, unlikely, low-probability, or rare risks without concrete evidence that they affect a current supported path, as well as unsupported misuse, manual tampering, future-scale concerns, optional hardening, cleanup or refactoring, style preferences, suggestions, backlog, tests merely for completeness, and searches for "what else to improve," are outside scope. Do not turn them into findings, open questions, assumptions, recommendations, or deferred work.
- Apply KISS and YAGNI in both directions: remove an abstraction, state, configuration, fallback, dependency, lifecycle, or verification burden already present when approved authority does not need it and a simpler sufficient design exists; never require another layer, defensive mechanism, generalization, or hypothetical extensibility.
- Stop and pass as soon as every mandatory PRD behavior and acceptance path has semantic coverage, every proven necessary current integration path has a minimally sufficient design, and no blocking admissible finding remains. Return no optional suggestions or backlog. Escalate only a direct authority contradiction that materially prevents the minimal design or verdict.

An Engineer-resolvable Minor may remain at `SPEC_READY` only when it is a concrete, non-blocking local implementation detail already inside the approved design, the Engineer must select it to implement a named PRD requirement, and the Engineer can resolve it without changing specification bytes, product meaning, system or public boundaries, or design complexity. It is not a specification omission, improvement, suggestion, or backlog item. Any missing mandatory behavior or design text is Major and requires Architect revision before readiness. Every other admissible finding is blocking.

The Director must place this invariant in every Generator, Architect, and Proofreader task packet, mechanically validate packet identity and required evidence shape, and route it without judging semantic sufficiency. The persistent Architect owns the pre-accept semantic decision and each fresh Proofreader owns its post-accept review verdict. The Director ends convergence as soon as their admissible evidence proves the pass condition.

## Required specification coverage

Keep stable, machine-addressable identifiers. Trace every normative technical requirement and verification case to one or more `PRD-REQ-*`, `PRD-NFR-*`, or `PRD-AC-*` IDs. A topic is relevant only when a named PRD ID requires it or concrete current-project evidence proves it is a necessary current integration path for that ID. Skip every other topic entirely; do not add boilerplate, `N/A`, recommendations, or speculative open questions. When relevant, cover only the minimum needed from:

- goals, non-goals, assumptions, dependencies, and system boundaries;
- current-state evidence and chosen project precedents;
- component ownership, public/internal contracts, data models, and invariants;
- lifecycle, concurrency, persistence, rollback, recovery, and failure behavior;
- security/trust boundaries, resource limits, configuration, and observability;
- migration, compatibility, rollout, and cleanup;
- acceptance mapping and deterministic verification strategy;
- open questions, with category and blocking status.

Coverage is semantic: for each approved behavior or invariant, state its technical realization and verification, or an explicit justified non-applicability. Repeating its source ID alone is not coverage.

For every central component, state its primary responsibility, owned state and lifecycle, dependencies, and prohibited responsibilities. A folder/module/path allocation or component list is not an ownership design.

Do not invent product behavior to fill a technical gap. Prefer the smallest design consistent with the approved PRD and the current project architecture necessary to implement it.

## Worker contracts

### Generator

Write only the initial missing/stale draft. Read the approved PRD as complete product scope and apply the scope and sufficiency invariant. The Generator MUST invoke `$skill-specification-pipeline` in `spec-generator` mode as the mandatory and only generation engine and MUST NOT bypass it. The Generator is an orchestration wrapper, not an independent local drafting path.

Before invocation, the Director runs `prepare-helper --operation generation` and gives the Generator the resulting immutable request path plus these normal external-skill inputs:

- `TARGET_OPERATION`: `new` only when the canonical specification is absent; otherwise `continue` for the controller-authorized stale canonical draft;
- `SPECIFICATION_PATH`: the exact canonical specification path, with no alternate output;
- `USER_REQUEST`: a complete generation request that must be authored entirely in the approved PRD language so the helper independently derives `USER_LANGUAGE` from the request;
- expected `USER_LANGUAGE`: the approved PRD language; the helper-derived `USER_LANGUAGE` must exactly match the approved PRD language or the run fails closed as a specification-helper integration error;
- the exact approved PRD path, revision, and SHA, the project root, and only relevant project/repository rules and concrete current-project evidence;
- the scope and sufficiency invariant as the authoritative generation and pass-filtering instruction.
- `GAMEDEV_HELPER_REQUEST_PATH`: the absolute controller request path binding the exact operation, PRD authority, canonical specification path, absent marker or input SHA, expected language, helper entrypoint/emitter fingerprints, and allowed write set.
- `GAMEDEV_SPECIFICATION_CONTROLLER_PATH`: the exact resolved absolute current GameDev `scripts/specification_state.py` path and SHA-256 already bound inside the request and used for the mandatory read-only output preflight.

The external helper retains sole ownership of its mandatory stages, passes, mode routing, and global not-applicable policy. The GameDev wrapper MUST NOT skip, duplicate, parse, normalize, or locally reimplement that topology. The scope and sufficiency invariant constrains findings and assembled specification content without changing external pass semantics.

The helper may write only the request-authorized `SPECIFICATION_PATH`, report, coverage, and result sidecar paths. It must preserve the repository's exact PRD trace/frontmatter shape and semantically cover every `PRD-REQ-*`, `PRD-NFR-*`, and `PRD-AC-*`. After its existing workflow reaches generic PASS and the specification/report/coverage bytes exist, its emitter first requires its resolved `--controller` path and SHA-256 to equal the request binding, then invokes exact command `python -B <GAMEDEV_SPECIFICATION_CONTROLLER_PATH> --project-root <project-root> preflight-helper-output --request <GAMEDEV_HELPER_REQUEST_PATH>`. That read-only command validates the exact active request, its current controller binding and external fingerprints, approved PRD bytes, changed output bytes, canonical `specification_trace`, one exact positive integer revision, `status: draft|approved`, and specification language equal to the request-bound approved PRD language. It then returns exact schema-1 envelope containing only `schema`, `controller: {path, sha256}`, `request: {id, sha256}`, and repository-relative `output_specification: {path, sha256}`. Only after validating that envelope may the helper atomically emit one helper-owned result sidecar bound to the exact request ID/SHA, operation/route, output SHA, exact write set, external fingerprints, and immutable opaque report/coverage artifact SHAs. Generation never grants readiness.

Before semantic assessment, the Director runs `record-helper-result`. The controller mechanically validates the immutable request bytes, result/request/output SHA chain, operation/route, authority/language, exact allowed writes, helper fingerprints, artifact SHAs, and one-use consumption. The Director does not author the result, parse detailed stage/pass topology or coverage content, judge semantic sufficiency, or edit the draft. The same persistent Technical Spec Architect then performs the read-only pre-accept semantic assessment.

The Architect's pre-accept result MUST include exactly one non-empty `section_applicability_inventory` bound by `assessed_spec_sha256` to the exact draft it assessed. Inventory scope is every authored top-level section plus every standalone diagram, table, hierarchy description, and footer block; frontmatter is excluded. Each row has an exact unique `locator`, a `disposition` of `retain`, `remove`, or `merge`, and a non-blank `authority_or_rationale`. A `retain` row names the exact PRD ID(s), any necessary current integration evidence, and the distinct PRD-backed behavior conveyed by that item. A `remove` or `merge` row names its exact enumerated correction ID and smallest correction. The receipt also has exact `semantic_assessment: accept|reject`. The Director mechanically rejects the receipt when the SHA is stale, the inventory is omitted or blank, a required field is blank, a locator is duplicated, or the semantic assessment is not exact; it does not judge the truth of the Architect's semantic rationale.

The Architect MUST use `reject` and an enumerated remove-or-merge correction when any inventory item is only output scaffolding rather than necessary specification content. This includes all of the following Formatter-style counterexamples:

- an absent-topic section whose only substance is `none`, `not applicable`, `no data`, or equivalent;
- a component hierarchy or diagram that duplicates another prose or diagram description without conveying distinct PRD-backed behavior;
- an empty Open Questions, Assumptions, or Risks section, including a footer carrying only the empty declaration; and
- a generic scalar "data model" table when the approved PRD requires no data, configuration, or persistence model.

These section kinds are not categorically forbidden. A section is retained when it has distinct authority, such as a Data Models section that defines a PRD-required persisted schema, an Open Questions or Risks section with a concrete unresolved blocker on a named PRD path, or a hierarchy/diagram that exposes distinct PRD-required interaction or ownership behavior. Mandatory helper stages and passes still execute and global helper policy still owns their `not applicable` eligibility; completion of a pass never requires the assembled specification to retain an empty or generic section.

For each rejection, the Architect returns one exact enumerated correction packet through the Director. Before any specification write, the Director runs `prepare-helper --operation correction` with every exact correction ID and passes the resulting `GAMEDEV_HELPER_REQUEST_PATH` to the same external `$skill-specification-pipeline`. The invocation binds `TARGET_OPERATION=continue`, the same exact `SPECIFICATION_PATH`, and a PRD-language explicit write/apply request authorizing only those corrections. The helper routes `spec-assistant -> fragment-capture`, emits its result sidecar, and the Director runs `record-helper-result` before returning the new SHA to the same persistent Architect.

Before any correction write, the current exact specification SHA must equal the Architect-assessed SHA. Any SHA drift fails closed: do not apply the packet, rebind the current SHA, and require the same Architect to reassess before issuing a replacement packet. The Director only validates these bindings and routes the packet; it does not reinterpret or expand the corrections.

Only after the Architect accepts the semantic draft, the exact helper result chain has been consumed, and no helper request remains active may the Director run `accept-spec --preaccept-receipt <in-project-json>`, end the Generator, and route to `start-cycle`. `accept-spec` requires an exact UTF-8 JSON object with `schema: 1` and no keys other than `schema`, `architect_id`, `prd_sha256`, `assessed_spec_sha256`, `semantic_assessment`, and `section_applicability_inventory`. The Architect identity must equal the controller's persistent Architect; PRD/spec hashes must match current immutable bytes; `semantic_assessment` must be exact `accept`. The controller mechanically derives locators for every `##` top-level section plus every standalone fenced diagram/hierarchy/block, a contiguous Markdown list block only when differing indentation proves actual nesting, Markdown table/image, and a final blank-separated unheaded no-content register limited to assumptions, source conflicts, risks, open questions, and additional product obligations. Ordinary flat lists, ordinary prose paragraphs, and a section's sole prose paragraph do not create extra structural locators. The non-empty inventory must cover that exact locator set once. Every row has exactly non-blank `locator`, exact `disposition: retain`, and non-blank `authority_or_rationale`. Any active helper request, missing result chain, `reject`, `remove`, `merge`, `defer`, missing/extra/duplicate/blank row, malformed/stale receipt, or identity/hash mismatch fails closed without controller-state mutation. The controller stores Architect receipt path, exact-byte SHA, and normalized inventory summary in acceptance/status and revalidates them with the helper chain before later transitions. A rejected item requires a fresh controller request, external-helper correction/result, and new Architect receipt bound to the resulting SHA. No Proofreader credit exists before acceptance. Helper unavailability, mismatched language, a violated binding/write boundary, or invalid output is a fail-closed integration error; no local fallback or Director-authored helper result is allowed.

### Controller helper challenge/result gate

`prepare-helper` is the sole request authority. It writes a canonical immutable one-use `schema: 1` request at `.agentic-pipeline/Workflows/<feature>/helper-requests/HREQ-xxxxxx.json`, records its path/SHA/ID in state, and rejects a second active request. The request binds `generation|correction`, the exact PRD path/revision/SHA, canonical specification path, exact input SHA or absent marker, expected language, exact external skill entrypoint/emitter paths and fingerprints, the exact resolved absolute current GameDev controller path and SHA-256, correction IDs when applicable, and the only allowed write paths: specification plus request-named report, coverage, and result artifacts in the same selected workflow.

Generation requests route the external helper to `spec-generator` with raw target `new` for an absent input or `continue` for an exact stale draft. Correction requests route `spec-assistant -> fragment-capture`, require one or more distinct correction IDs, and bind the exact current/prewrite SHA. For an active wave they are allowed only after a recorded Proofreader result and bind the wave input plus its still-valid acceptance.

The actual external skill owns one canonical helper result. Its deterministic emitter validates the request and current output and atomically writes generic `schema: 1` evidence bound to the exact request ID/SHA, operation/route, changed output specification SHA, exact write set, `outcome: PASS`, helper identity, and exact SHAs of its non-empty opaque report and coverage artifacts. The Director must not handcraft, overwrite, reconstruct, or normalize that result, and the controller never parses external stage/pass topology or global not-applicable decisions.

`record-helper-result` reuses the same canonical output preflight, validates current request bytes and fingerprints, result/request/output SHA chain, route, generic PASS, write boundary, PRD/language, artifact immutability, and uninterrupted input/output provenance, then consumes the request once into `helper_evidence.results` and `helper_history`. Replay, drift, an unprepared local draft, and missing/foreign/changed artifacts fail closed. Historical sidecars and artifacts remain immutable; only the final chain result must equal current specification bytes.

`reject-helper-result --request-id <id> --reason <text>` is the only compatibility recovery for a pre-preflight immutable initial-generation `PASS`. It is allowed only in unchanged `needs_generation`, before any helper credit or later workflow progress, after the controller validates the exact old request/result/report/coverage/specification chain against its recorded fingerprints and proves that the output itself fails the canonical specification-authority preflight. Only this recovery accepts the legacy initial request without a controller binding and ignores current helper fingerprint drift caused by the preflight fix; all recorded fingerprints must remain internally exact. The command changes no artifact or specification bytes, clears the active request, retains `needs_generation`, stores the current rejected output SHA as `generation_input_sha256` plus the exact trace errors, resets helper evidence to that SHA with no results, and appends one audit receipt. Exact immediate replay with the same ID and reason is a byte-noop. Wrong ID/reason, valid output, artifact/state drift, or any later progress fails closed without state writes. The next `prepare-helper --operation generation` issues the next sequential HREQ with the current controller path/SHA binding, `target_operation: continue`, and the preserved SHA input; `correction` remains forbidden until that replacement generation result is consumed.

### Technical Spec Architect

Remain persistent from assignment before generation through handoff. Before `accept-spec`, perform the read-only semantic assessment of the helper draft; do not take Proofreader credit and do not edit around the Generator/helper. Return the exact-SHA-bound section-applicability/minimality inventory and an exact correction packet for any unsupported obligation/system, output scaffolding, boilerplate, speculative OQ/risk, missing semantic coverage, or non-minimal design. After acceptance, remain the sole semantic correction owner, but route every byte-changing enumerated correction through the same bounded Generator/helper rather than writing directly. Apply the scope and sufficiency invariant, resolve only admissible technical findings, and remove already-written excess complexity. Use bounded researchers for exact repository questions instead of broad discovery. For each response, return changed IDs, evidence/rationale, unresolved escalations, checks, and the resulting SHA. Never answer a product/scope/boundary question by assumption or preserve optional complexity as a precaution.

The Director, not the Architect, owns the cycle counter. A completed Proofreader-to-Architect-response wave consumes one of that Architect's five cycles even when the response concludes that no edit is needed. The fifth non-ready response may complete; a sixth wave for the same identity may not start.

### Proofreader

Be fresh and read-only for one immutable PRD/spec pair. Apply the scope and sufficiency invariant. Read the entire pair, project rules, and only the repository evidence needed to validate PRD-required or disputed current integration choices. Stop when mandatory coverage and minimal sufficient complexity are proven; do not continue searching for improvements. Return a complete, deduplicated batch containing only admissible findings:

```text
PROOFREADER_ID
PRD_SHA256
SPEC_SHA256
COVERAGE_COMPLETE: yes|no
FINDINGS: ID | severity | category | requirement IDs | evidence | required resolution
UNRESOLVED: product | scope | boundary | ownership | public-contract
MINORS_ENGINEER_RESOLVABLE: yes|no
VERDICT: pass|revise|user-gate
```

Persist the report path plus every finding/question ID through `record-proofread`; later cycles may supersede an issue, but must not erase its history.

After `record-proofread`, any byte-changing correction must be prepared against the immutable wave input, executed by the external helper, and consumed with `record-helper-result` before `complete-cycle`. `complete-cycle` validates the old acceptance at the wave input SHA and the added correction-result chain through the current result SHA, stores those results in the closed wave, clears acceptance, and enters `awaiting_accept`. A fresh Architect preaccept plus `accept-spec` is required before a fresh Proofreader. If no edit occurred, `complete-cycle` preserves acceptance and remains `reviewing`. Edits before the read-only Proofreader result, active requests at lifecycle transitions, and `accept-spec` during an active wave remain forbidden.

Use Critical for a concretely unsafe or unimplementable mandatory core design. Use Major for a material contradiction, missing mandatory behavior or design text, or an unverifiable acceptance path; Major always requires Architect revision before readiness. Use Minor only for a concrete, non-blocking local implementation detail already inside the approved design that the Engineer must select to implement a named PRD requirement and can resolve without changing specification bytes, product meaning, system or public boundaries, or design complexity. A Minor is never an omission, improvement, suggestion, or backlog item. Severity never makes an inadmissible theoretical or optional concern valid. A pass has no blocking admissible findings, suggestions, backlog, or optional follow-ups; only these strictly bounded Engineer-resolvable Minors may remain.

## Holds and handoffs

On an attempted sixth wave, retain the current Architect and all history but set `spec_convergence_hold`. The Director must publish remaining findings and decide explicitly between:

- `handoff-architect` with a distinct identity and a recorded rationale; or
- a user gate for unresolved product, scope, boundary, ownership, or contract authority.

Handoff gives the new Architect a compact source-backed packet: canonical paths/hashes, current spec, unresolved finding IDs, prior decisions, cycle history, and hold reason. Never summarize away rejected alternatives or reset total waves.

## Readiness evidence

`init` and every `accept-spec` first run the complete approved Requirements validator against the exact canonical PRD. `accept-spec` then requires `--preaccept-receipt` and executes the controller-owned exact receipt/locator gate above before changing state. Range shorthand, ambiguous or malformed acceptance declarations, a missing canonical acceptance inventory, and legacy REQ/NFR declaration rows fail before controller state, receipts, or artifact bytes are changed. The final Proofreader and Architect confirmation must reference the same current specification SHA. The PRD must still match the controller's current authority for the active convergence epoch and the specification trace. `confirm-ready` is the only transition to `spec_ready`; prose declarations do not change readiness. Critical/Major findings, open blocking questions, incomplete coverage, and any Minor outside the strict Engineer-resolvable definition block readiness; strictly bounded Engineer-resolvable Minors do not. Emit `SPEC_READY` plus `NEXT_ACTION: $gamedev-development-plan`, then stop. The Specification stage never starts planning.
