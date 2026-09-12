# Assignment and source delivery

Read for an issued runtime assignment. These transport commands do not change product authority, role ownership, write scope, acceptance or the controller's phase sequence. Use the existing launcher with global `--root <project-root> --feature <slug>` before the command; obtain exact flags from command help. Directors use global `--brief` before `status` and technical/mutation subcommands: it retains action/lifecycle/recovery metadata without printing the full assignment. Full public output remains available explicitly when its content is needed; do not routinely ingest it before exporting a delta.

## Prepare the working input

`access.read` is the permitted research boundary, not a request to load every file. From the approved slice/milestone and current task, identify the applicable requirement sections, changed code targets, directly affected external contracts, mandatory findings/checks and current technical decisions. Preserve general requirements that govern the target. For Review use the exact controller target; for QA retain every required identity. Uncertain relevance requires investigation, not omission. Project instructions govern selection of their own environment rules; this pipeline supplies no engine defaults.

Use `assignment-export --input <exact-project-relative-path>` for each selected starting source. Selection is separate transport metadata; the issued assignment remains unchanged and all other authorized sources remain available through `file-read`. An empty selection does not waive required inputs and does not mean the entire read scope must be loaded. Describe the selected section/requirement IDs and purpose in the self-contained handoff; do not infer product obligations from filenames or let a script invent semantic relevance.

The export returns immutable packet and delivery-response digests, a locator and size metadata. A locator is not delivered knowledge. The receiving worker must read the assignment, applicable constraints and complete required evidence before work or judgment. Keep user permissions, observed capabilities and owner/model constraints outside the immutable assignment; only actual user/stage authority supplies them.

## Read without loss

`delivery-read --digest <response_digest> --offset <offset> --limit <size>` reads the exported response in Unicode-character pages. Follow `next_offset` until `complete` is true. `--pointer /assignment/context/technical_decisions` may select one exact JSON section; its `complete` applies only to that section, not the full assignment. Use section reads to deliver required fields without replaying unrelated packet fields. The complete packet already exists at the returned immutable path; do not rewrite it or guess missing JSON from a page boundary. Read the full required semantic fields, even when they take several pages. Set both nested and outer tool-output budgets to deliver each page; do not produce huge parallel read batches or treat truncated tool output as complete. Return command text rather than serializing the whole shell-result envelope again.

`file-read --path <literal-project-relative-path>` reads a selected authorized UTF-8 source and returns its raw-byte version plus exact character range. Supply that `--version` for continuation pages and for any read intended to refer to those same bytes. If the source changes, the old version fails; obtain the current authorized source and reassess affected conclusions. Binary sources need the project's appropriate reader, not conversion of binary bytes into text tokens. The reader does not grant new file access, follow escaping links or read another workflow.

Do not reread complete unchanged content already delivered to this recipient's current context. After a fresh worker, context loss, source change or an incomplete output, retrieve what is actually missing. A packet digest proves identity, not that the model consumed its bytes.

## Update the same worker

After a sanctioned technical action, retain the physical Engineer and export with `--baseline <prior_packet_digest>` only if that same recipient actually received the complete prior packet and still has its relevant content. The delivery response describes changes and the target full-packet digest. Consume every change, including removals and changed assignment/output IDs, before continuing. The full target packet remains independently readable if reconstruction is uncertain. A fresh worker uses a full export; never pass a delta against another worker's context.

Required findings/checks, current technical decisions and operative answered questions are lossless. Their preview, hash or omitted-count marker cannot substitute for full content. Current journal data is canonical; stale or legacy truncated context must be restored from its matching authority source or reported unavailable, never treated as a complete assignment. Updating one record does not create a second journal or authorize new scope.

## Mechanical controller actions

`step --expected-generation <generation> --action-id <status.next_action.command_id>` consumes one exact public mechanical `next`, `complete` or `accept`. It reuses the controller's validations and action identity. Repeat the same action identity after an uncertain response; do not switch to a new one merely to retry. It returns compact state and assignment-export metadata rather than full history.

Before `complete`, the Director must independently establish child termination, assignment ownership and the exact returned artifact. File existence is not child-liveness evidence. A missing artifact causes a stop, not a fabricated result. A semantic question, recovery fact, ready phase or terminal state remains the Director's existing route; the helper does not answer, authorize, reconfigure, publish or waive checks. Workers do not execute `step` or controller-owned planned commands. Read [Director lifecycle](director-runtime.md) only when acting as Director.
