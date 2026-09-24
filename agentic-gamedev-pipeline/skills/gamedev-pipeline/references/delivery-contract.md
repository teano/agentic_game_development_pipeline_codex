# Assignment and source delivery

These readers transport exact approved/native content. They do not change roles, scope, acceptance, permissions or phase order. Use the supplied launcher with global `--root <project-root> --feature <slug>` before the command; consult its command help for exact flags.

## Worker read route

Read the supplied role instructions, [assignment ownership](stage-handoff-invariant.md#one-owner-and-one-current-assignment) and this section before semantic input. Start with `dispatch.reader.bootstrap_argv` (`assignment-read --view bootstrap`). It groups complete assignment identity, task, scope, schema, checks, current slice and QA binding, with locators for the remaining context. On rework continue through [Repair input](#repair-input); an index is navigation, not delivered repair evidence.

The generated `section_argv_prefix` already ends with `--pointer`; append only the exact pointer value to read a complete selected semantic body through `--view section`. Select the coherent material needed for this role: current failures/conditions for remediation, originals/claims for Review, identities/assertions/methods for QA, and relevant current decisions. `unit_argv_prefix` remains useful for structural discovery: `--view unit` exposes direct scalar fields and child selectors; `--view index` is body-free navigation. Neither requires one call for every scalar. Do not recursively print the whole assignment, QA definition or all findings merely because they are readable.

Paged views (`bootstrap`, `work-index`, `work-item`, `check-result`, `section`) return `pipeline-delivery-page-v1`: exact `text`, offsets, content/page digests, `complete` and `continuation`, bound to packet/view/selection. Follow the returned `--continuation` with the same selection and digest until all contiguous fragments are consumed. Page text is a fragment of one selected JSON body: reconstruct it before decoding or resolving its internal references. A reference may point elsewhere in that selected body, not necessarily the same page. Verify the full selected `content_digest`; `complete:true` means only that selection's end, never whole-assignment comprehension, verdict or acceptance. `unit_complete`/`delivery_complete` do not become global credit.

Display decoded readable semantic content without serializing a shell envelope again. A script may reconstruct complete machine data and expose the selected exact fields without dumping every unrelated subtree. If output clips, recover the missing page/range, using a smaller `--limit` where needed; never skip a tail, pretend a locator was consumed or reread already retained unrelated material. Preserve the complete host result locally and surface compact session/exit metadata alongside stdout. A running outer cell resumes through `functions.wait`; an inner command through its original `write_stdin` handle. Empty output is not completion or replay permission.

Read every required source/assertion/method fully before relying on it. QA definitions may share exact method resources; retain each actually consumed unchanged definition once, with its identity. Read access is not a requirement to print every procedure for every role. Missing/corrupt/incompatible resources are errors, never empty obligations. `--view value --format json`, legacy full `--view work`, `delivery-read` and `file-read` remain machine/debug routes; do not dump their unbounded recursive bodies into model context.

Use [Check delivery](#check-delivery) after native checks and [Update the same worker](#update-the-same-worker) for continuation. A digest, export, index or successful parser proves no reading or semantic acceptance.

## Repair input

`context.required_finding_conditions` is a controller-derived roster, not a verdict or another ledger: Engineering/Documentation receive unresolved conditions; Review receives every condition of each current open finding, including resolved rows. Legacy packets must reconstruct this same inventory from complete explicit convergence or error, never silently waive it.

Read `reader.work_index_argv` (`--view work-index`) completely, then `reader.work_item_argv_prefix` with each required finding ID (`--view work-item --finding-id <id>`). The work-item prefix already ends with `--finding-id`; append only its ID value. Use `--condition-id <id>` only to select a needed condition while accounting for the rest of the roster. Consume all continuation pages of every required selection. Each work item supplies shared original finding context, exact selected original conditions and latest independent results; compare the actual rejection with the previous claim. `reader.work_argv` remains the legacy full-work compatibility route, not the ordinary repair reader. A selected item/page or roster count cannot establish whole-work completion.

An explicit `--baseline <packet_digest>` on a work-item read asserts that this physical recipient fully consumed and still retains those earlier applicable originals. Runtime checks compatible project/run/feature/role/worker, chronology and QA binding; it may replace only byte-identical original slots with `null` plus exact `retained_originals` locators. Latest independent results stay current and present. Resolve omitted originals from that actual retained content, not from a digest or memory guess. New/lost-context recipients omit the flag. An invalid/incomplete/unretained baseline requires the full current selection without it.

The work reader validates its roster/canonical pointers, not the truth of a resolution. Original finding bodies may retain already resolved conditions; do not copy those wholesale into Engineering/Documentation's narrower resolution map. Independent Review still owns closure.

## Check delivery

For a granted new logical check, prefer `check --with-delivery` under [Active checks](execution-contract.md#check-inside-active-engineering-or-qa). It commits the existing check transaction, then returns its cursor, compact delivery metadata and the first paged `check-result`. The complete selected body supplies bootstrap metadata, full `check_context.diagnostic_checks`/`machine_checks` and locators for other context. Consume every page, inspect actual failures and pending IDs, then consume other changed required context/decisions before resuming. Retain unchanged material only when this owner actually still has it.

The compound response preserves `committed`, `command_id`, `committed_generation`, current `generation`/`next_action`, `transport.status` and read-only `recovery.read_argv`/`export_argv`/`status_argv` as applicable. A presentation failure after commit is not a failed/unperformed check. Use the supplied read/export recovery at its returned binding; do not issue a new check ID, guess generation or replay a known committed mutation just to retrieve text. An advanced replay reports `cursor_advanced` without pretending the old assignment can be exported; use the current cursor and established control route. Uncertain mutation responses retain the original ID/argv under the execution contract.

The existing compact check route without `--with-delivery` remains valid: export once against an eligible same-owner full-packet baseline and consume changed required units. `--full` is deliberate debugging, not the check loop. A read/export failure never undoes a committed command.

## Prepare the working input

`access.read` is a research boundary, not a preload instruction. The specialist selects applicable source sections, code, affected external contracts and decisions while preserving governing general requirements, mandatory checks/findings, exact Review target and every QA identity. Uncertain relevance requires investigation. The Director forwards exact source/version locators without reading semantic bodies to curate relevance; project rules determine environment choices.

`assignment-export --input <exact-project-relative-path>` selects task/specialist-approved starting sources as transport metadata only. Other authorized sources remain available through `file-read`. An empty selection neither waives obligations nor requests the whole read scope. Forward specialist-supplied section/requirement IDs and purpose unchanged.

Export binds absolute root, assignment/worker, immutable packet/response digests and locators. `working_set` byte/count/token estimates and indexes aid navigation, never impose a budget or prove reading. `estimated_tokens` is bytes/4, not measured usage. When sealed slice and plan binding hold, `verification_exit_criteria` supplies plan path/raw-byte version and an optional exact section range. Read that version through the section's end; `file-read.complete` still refers to the whole source. Missing section metadata leaves the full-source route and waives nothing. Permission/approval/model sources remain actual caller authority outside the immutable assignment.

## Read without loss

Native export/assignment-issuing step supplies `dispatch` (`pipeline-dispatch-v1`) for unchanged forwarding. It binds native identity, root/cwd, separate `launcher_argv`/`controller_args`, role locator, full/delta digests/paths, scope/schema/output and action/stop boundary. Host owner, return correlation, actual permissions and bounded check grant remain caller metadata. Invocation syntax grants no command authority. The issued exact terminal-output right and product scope follow [assignment ownership](stage-handoff-invariant.md#one-owner-and-one-current-assignment); active check continuation follows [Active checks](execution-contract.md#check-inside-active-engineering-or-qa).

A v2 packet's typed references resolve exact duplicate content from its same-packet registry with stable logical pointers. The reader validates root/run/feature/binding/digests; unresolved or corrupt references fail closed. Raw `delivery-read` pages expose transport JSON, while assignment readers resolve selected semantic bodies. Full canonical content remains available for reconstruction; no preview, hash or omitted-count marker replaces required findings, checks, operative answers or decisions.

`file-read --path <literal-project-relative-path>` returns authorized UTF-8 text with raw-byte version and character range. Supply that `--version` on continuations or other reads of those exact bytes. Changed source invalidates the old version and affected conclusions. Binary sources need the project's appropriate reader. These readers grant no broader access, escaping links or another workflow.

## Update the same worker

An eligible continuing owner may use `assignment-export --baseline <prior_packet_digest>` only while retaining the complete applicable earlier content. Consume all relevant changes/removals and new assignment/output bindings before continuing. The target full `packet_digest` becomes the next baseline only after that consumption; a delta's `response_digest` is transport identity, not baseline. Old formats receive explicit full-v2 fallback. Another owner/run/root, a replacement or context loss requires full current applicable input.

Pass a known eligible baseline on the first export. A full `step --through-handoff` delivery permits one baseline export for a continuing owner; deliver only full OR delta, not both, and do not re-export for identity. `step` has no baseline flag. Baseline acknowledgment rides the next necessary [Worker return](control-return.md#worker-return), never a ping. The specialist consumes semantic content; the Director does not read it first.

Journal restoration follows [Current journal](technical-decisions.md#current-journal) when required. Changed packet identity alone does not invalidate an unchanged QA resource actually read and retained by this owner.

## Mechanical controller actions

Directors use global `--brief` for status and technical/mutation commands to retain lifecycle/recovery metadata without full assignment/history. `step --expected-generation <generation> --action-id <next_action.command_id>` consumes only the exact native mechanical `next`, `complete` or `accept`; it grants no semantic answer, recovery, publication or waiver. Use its returned cursor rather than redundant status. `result:executed` is transport success; inspect its typed outcome and bounded failure data.

Before `complete`, the Director independently establishes actual child termination/quiescence, assignment ownership and exact returned artifact. File existence is not liveness evidence. Workers never execute `step`. See [Director lifecycle](director-runtime.md) only when acting as Director.

`--through-handoff` may continue passing complete/accept/next through at most three existing transactions, stopping at the first new assignment, replay, failure, question, recovery, missing artifact or ready boundary. It never consumes the newly issued worker's output. An error can leave earlier transactions committed. Retain the original `request`; uncertain replay uses its exact ID/generation and reports the current cursor/assignment without claiming the whole chain ran. `steps` lists only actually executed transactions; replay alone does not prove this call changed nothing. Preserve required liveness before initiating complete.
