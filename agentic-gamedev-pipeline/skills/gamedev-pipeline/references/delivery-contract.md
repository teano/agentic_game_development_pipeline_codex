# Assignment and source delivery

These readers transport exact approved/native content. They do not change roles, scope, acceptance, permissions or phase order. Use the supplied launcher with global `--root <project-root> --feature <slug>` before the command; consult its command help for exact flags.

## Worker read route

The supplied `role_instructions.exec_command` reads the assigned role. Each instruction response returns `linked_reads` matching its actual Markdown links to exact current source spans and executable handles. Use the handle for each required link through [Host command presentation](#host-command-presentation). Read [One owner and one current assignment](stage-handoff-invariant.md#one-owner-and-one-current-assignment) once, including its event-specific triggers; it establishes root, scope, independence and control return. Relevant current technical entries and `requires_current_journal_read:true` require the linked current-journal section before implementation or judgment. Retain unchanged instructions; an encountered event selects its linked section.

Run `dispatch.reader.bootstrap.exec_command` unchanged through that presentation. The generated reader assembles and renders the complete selected value with its binding, identity, task, scope, schema, checks, slice and source/context locators. Read those operative fields before file work. Supplied section/work-item prefixes remain available for selected semantic bodies; they already end with their selector flag. On repair, follow [Repair input](#repair-input).

For a bound QA definition, Engineering, Review and QA run `reader.qa_index.exec_command` and consume its exact inventory: each identity has `id`, `source`, `assertion_ids`, and one role-appropriate ready handle. Engineering and Review use `read`; QA uses `prepare` under [Incremental assessment](qa-acceptance-contract.md#incremental-assessment). That handle supplies one `--identity-id`, which the existing reader expands to all of that identity's ordered assertions. For a coherent subset, use the exact `assertion_ids` with repeated `--assertion-id`; never combine identity and assertion selectors. Grouping follows the actual scenario/proof; identity navigation does not prescribe an assessment batch. Preparation supplies complete selected obligations, all approved alternatives and producer context, so it needs no preliminary full-definition or `qa-assertion` read. The selected `identities` use `methods[].ref` to exact `method_definitions` in the same response; results use the resolved semantic `id`. Read every required expectation, applicability condition, dependency, method and evidence requirement before assessment. Retain identical method text once while it remains applicable.

Use [Read without loss](#read-without-loss) for approved/project source sections. A source locator, index, digest or successful assembly proves neither semantic reading nor acceptance. Keep required full semantic content accessible and consume missing ranges after clipping; [Transport recovery and compatibility](#transport-recovery-and-compatibility) supplies the exceptional reader details. Saving a complete body outside context does not read it.

After an active check use [Check delivery](#check-delivery); a continuing owner uses [Update the same worker](#update-the-same-worker). A new/replaced/lost-context owner consumes full current required material without another owner's baseline. Finish through the role's artifact contract and [Terminal artifact boundary](stage-handoff-invariant.md#terminal-artifact-boundary). Bounded caller tasks use their exact input/return procedure, without inventing a native assignment.

## Host command presentation

Use the actual returned handle as `handle` in this host call. Its `exec_command` already contains the safely quoted command, shell and cwd derived from native argv. The reader uses existing `--format text --assemble`: metadata followed by the decoded selected body. This call retains the complete command result and presents that selected output directly.

```javascript
const result = await tools.exec_command(handle.exec_command);
store("pipeline_host_result", { request: handle.exec_command, result });
text({ session_id: result.session_id ?? null, exit_code: result.exit_code ?? null });
text(result.output);
```

If a session is still running, continue its returned `session_id` through `write_stdin` and retain the accumulated result/chunks until terminal completion. An unfinished outer cell uses its own `functions.wait` handle. The stored request/result remains available for recovery; displaying stdout does not discard lifecycle metadata. Native mutations still require their actual grant and retained replay identity.

Run the next dependent selector only after consuming its discovery response. Native assembly verifies the selected content; an arbitrary host wrapper can still clip or re-escape it. If presentation clips, recover that missing selected content through [Transport recovery and compatibility](#transport-recovery-and-compatibility). The generated handle and this presentation do not certify semantic reading or acceptance.

## Repair input

`context.required_finding_conditions` is a controller-derived roster, not a verdict or another ledger: Engineering/Documentation receive unresolved conditions; Review receives every condition of each current open finding, including resolved rows. Legacy packets must reconstruct this same inventory from complete explicit convergence or error, never silently waive it.

Read `reader.work_index_argv` completely, then use `reader.work_item_argv_prefix` with each required finding ID. The prefix already ends with `--finding-id`; append only its ID value. Use `--condition-id <id>` only to select a needed condition while accounting for the rest of the roster. Each generated reader assembles its complete selection: shared original context, exact selected conditions and latest independent results. Compare the actual rejection with the previous claim. `reader.advanced.work_argv` retains full-work compatibility. A selected item or roster count cannot establish whole-work completion.

An explicit `--baseline <packet_digest>` on a work-item read asserts that this physical recipient fully consumed and still retains those earlier applicable originals. Runtime checks compatible project/run/feature/role/worker, chronology and QA binding; it may replace only byte-identical original slots with `null` plus exact `retained_originals` locators. Latest independent results stay current and present. Resolve omitted originals from that actual retained content, not from a digest or memory guess. New/lost-context recipients omit the flag. An invalid/incomplete/unretained baseline requires the full current selection without it.

The work reader validates its roster/canonical pointers, not the truth of a resolution. Original finding bodies may retain already resolved conditions; do not copy those wholesale into Engineering/Documentation's narrower resolution map. Independent Review still owns closure.

## Check delivery

Under the issued [active-check grant](execution-contract.md#check-inside-active-engineering-or-qa), use `check --with-delivery`. Its compact response gives the commit/result/cursor/binding and `recovery.read` handle. Run that handle through [Host command presentation](#host-command-presentation); inspect `check_context.diagnostic_checks`, `machine_checks`, actual failures and pending IDs. Use `recovery.bootstrap` for the refreshed bootstrap, then consume changed required sections before resuming. Retain only unchanged content this owner actually still has.

The result preserves `committed`, `command_id`, `committed_generation`, current `generation`/`next_action`, `transport.status` and read-only recovery argv. A presentation failure after commit recovers through those read/export arguments; it is not an unperformed check and grants no fresh check ID. `cursor_advanced` reports current state without pretending an old assignment can be exported. An uncertain mutation response retains its original request under the execution contract; an unexpected binding change returns to the Director. Legacy compact/export use is in [Transport recovery and compatibility](#transport-recovery-and-compatibility).

## Prepare the working input

`access.read` is a research boundary, not a preload instruction. The specialist selects the initial source sections/symbols for the next behavior and conditions for further reading while preserving governing general requirements, mandatory checks/findings, exact Review target and every QA identity. Uncertain relevance requires investigation. The Director forwards exact source/version locators and the specialist's input order without reading semantic bodies to curate relevance; project rules determine environment choices.

`assignment-export --input <exact-project-relative-path>` selects task/specialist-approved starting sources as transport metadata only. Other authorized sources remain available through `file-read`. An empty selection neither waives obligations nor requests the whole read scope. Forward specialist-supplied section/requirement IDs and purpose unchanged.

Export binds absolute root, assignment/worker, immutable packet/response digests and locators. `working_set` byte/count/token estimates and indexes aid navigation, never impose a budget or prove reading. `estimated_tokens` is bytes/4, not measured usage. When sealed slice and plan binding hold, `verification_exit_criteria` supplies plan path/raw-byte version and an optional exact section range. Read that version through the section's end; `file-read.complete` still refers to the whole source. Missing section metadata leaves the full-source route and waives nothing. Permission/approval/model sources remain actual caller authority outside the immutable assignment.

## Read without loss

Append the exact path to generated `reader.source_argv_prefix`, then `--section <exact-heading>` for one unique ATX Markdown heading and its nested sections. Repeated headings report their lines: select inclusive one-based `--lines <first>:<last>` instead. Out-of-range spans fail rather than clip. The source reader returns `source: {path,sha256,start_line,end_line}` and `evidence_origin: {ref,source}` derived from the actual original bytes/range. Preserve that exact origin for source evidence; the helper does not author its observation.

An instruction response's `linked_reads` associates the actual link label/href with its exact current `source` span and `exec_command`. Execute that handle for the required anchor; several labels may resolve to the same span. A missing/ambiguous anchor returns an error, not a whole-file substitute. A canonical link without an anchor retains its whole-file target. Before initialization, `file-read --instruction <role-or-gamedev-skill>` with supplied root/feature and `--format text --assemble` starts this same route. Its optional `--path` stays inside explicitly linked bundle Markdown. For example, `--instruction director --path references/director-runtime.md --section "Ordinary event map"` selects the existing route. This grants no project read scope or arbitrary bundle-code access.

Changed source invalidates old ranges and affected conclusions; after context loss reload the required exact selection rather than treating its digest as knowledge. Binary/visual sources use their appropriate reader and actual inspection, retaining locators rather than repeated full-frame dumps.

## Update the same worker

An eligible continuing owner may use `assignment-export --baseline <prior_packet_digest>` only while retaining the complete applicable earlier content. Consume all relevant changes/removals and new assignment/output bindings before continuing. The target full `packet_digest` becomes the next baseline only after that consumption; a delta's `response_digest` is transport identity, not baseline. Old formats receive explicit full-v2 fallback. Another owner/run/root, a replacement or context loss requires full current applicable input.

Pass a known eligible baseline on the first export. A full `step --through-handoff` delivery permits one baseline export for a continuing owner; deliver only full OR delta, not both, and do not re-export for identity. `step` has no baseline flag. Baseline acknowledgment rides the next necessary [Worker return](control-return.md#worker-return), never a ping. The specialist consumes semantic content; the Director does not read it first.

Journal restoration follows [Current journal](technical-decisions.md#current-journal) when required. Changed packet identity alone does not invalidate an unchanged QA resource actually read and retained by this owner.

## Transport recovery and compatibility

A v2 packet's typed references resolve exact duplicate content from its same-packet registry with stable logical pointers. The reader validates root/run/feature/binding/digests; unresolved or corrupt references fail closed. Raw `delivery-read` pages expose transport JSON, while assignment readers resolve selected semantic bodies. Full canonical content remains available for reconstruction; no preview, hash or omitted-count marker replaces required findings, checks, operative answers or decisions.

Manual source selections retain `--format text|json`, exact `--continuation`, and legacy numeric `--offset` with source `--version`. Select needed fields before display; preserve complete semantic text and original source metadata.

Use this section only when a generated read clips/fails, a retained body must be restored, or an older caller lacks generated handles. Ordinary handles select `--format text --assemble`; retained `*_argv` and explicit JSON output support machine/legacy consumers. Assembly checks contiguous pages, packet/view/selection binding and page/content digests, then supplies the decoded selection. For a large selected view, `--output <workflow/ReadOutputs/selection.json>` saves its full assembled envelope; inspect the required fields/ranges from that file. Recover the missing part of the same selection after clipping. JSON `value` is already decoded.

Low-level `assignment-read --view unit` exposes scalars/child selectors and `--view index` navigation; `--view qa-index` and `--view qa-assertion` remain exact selection readers. For `qa-assertion` select either one exact `--identity-id <id>` or repeated `--assertion-id <id>` values for a coherent subset. Unknown, repeated or mixed selectors are rejected. `--view value --format json`, legacy full `--view work`, and raw `delivery-read` serve machine/debug or older callers. They resolve no semantic acceptance. Paged `pipeline-delivery-page-v1` views retain exact text, offsets, digests and selection-bound continuation. A page is a fragment; `complete:true`, `unit_complete` and `delivery_complete` describe transport only. When manually consuming pages, preserve exact whitespace and follow the exact continuation; do not combine continuation with assembly or normalize fragments.

Preserve the complete host result locally and expose compact lifecycle metadata alongside readable output. Resume an outer `functions.exec` cell with `functions.wait`, an inner command with its retained `write_stdin` handle; empty output or outer completion is not inner completion/replay permission. Decode only after collecting the terminal result. Missing/corrupt/incompatible references are errors, not empty obligations.

A legacy check without `--with-delivery` may export once against an eligible same-owner full-packet baseline, then consume changed required content. `--full` is deliberate debugging. A read/export failure never undoes a committed command, and a known committed action is not replayed merely to recover text.

## Mechanical controller actions

Directors use global `--brief` for status and technical/mutation commands to retain lifecycle/recovery metadata without full assignment/history. `step --expected-generation <generation> --action-id <next_action.command_id>` consumes only the exact native mechanical `next`, `complete` or `accept`; it grants no semantic answer, recovery, publication or waiver. Use its returned cursor rather than redundant status. `result:executed` is transport success; inspect its typed outcome and bounded failure data.

Before `complete`, the Director independently establishes actual child termination/quiescence, assignment ownership and exact returned artifact. File existence is not liveness evidence. Workers never execute `step`. See [Director lifecycle](director-runtime.md) only when acting as Director.

`--through-handoff` may continue passing complete/accept/next through at most three existing transactions, stopping at the first new assignment, replay, failure, question, recovery, missing artifact or ready boundary. It never consumes the newly issued worker's output. An error can leave earlier transactions committed. Retain the original `request`; uncertain replay uses its exact ID/generation and reports the current cursor/assignment without claiming the whole chain ran. `steps` lists only actually executed transactions; replay alone does not prove this call changed nothing. Preserve required liveness before initiating complete.
