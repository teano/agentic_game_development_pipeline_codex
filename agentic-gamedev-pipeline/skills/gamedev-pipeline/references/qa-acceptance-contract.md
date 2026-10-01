# QA acceptance contract

Use the generated assignment reader for the resolved logical `context.qa_contract.definition` and its identity/assertion/method units. Resolve a shared method selector to the approved method object and use its semantic `id`; a transport key such as `METHOD-*` is not that ID. Transport references are not missing criteria and must not be copied into semantic result fields. Read each required shared method once; preserve its full operative wording.

One authority-bound contract defines the assertions, approved methods and required evidence for every mandatory QA identity. Engineering, Review and QA receive the same slice definition through `assignment.context.qa_contract`; use that definition without independently strengthening or weakening it. Capabilities and evidence types are project-defined identifiers: this contract requires no particular platform, device, browser, engine, instrumentation or extra test.

## Source and binding

For new plans, author one `## QA Acceptance Contract` section containing exactly one `json` fence with the manifest below. Keep the exact `mandatory_identity_ids` in each existing Coverage Contract; the manifest's slice and identity sets must equal that inventory. The manifest holds method details once; other sections reference its assertion/method IDs.

For an existing approved plan, an explicitly supplied `init --qa-contract <manifest.json>` can bind the same schema to the unchanged approved PRD/SPEC/PLAN. `confirm_approved_plan: true` asserts faithful extraction of existing authority, not permission to add a test, waive a case, invent equivalence or resolve an ambiguous product decision. Every identity and method cites an approved path plus anchor. Unresolved source wording uses the existing bounded authority clarification route; material acceptance changes require the owning stage's approval. A missing contract remains `unresolved` and cannot grant method-verified QA PASS. Never regenerate approved requirements, specification or plan merely to fill runtime metadata.

A supplied manifest must be workflow-local. Binding/changing it requires no active worker and no unresolved question. At an unchanged current Engineering candidate, binding preserves that implementation and archives previous Review/QA results, then issues fresh Review. It cannot alter the definitions of already completed slices while retaining their acceptance. A changed approved plan follows normal reconvergence. An identical contract is retained across runtime maintenance; altered source authority requires a fresh explicit extraction (or its embedded definition). A matching embedded definition cannot be overridden by an external manifest.

The controller owns the authority/contract digest, slice binding and the candidate/runtime binding of accepted results. Workers neither author those identities nor copy old digests into their output. Current evidence and old observations are separate: recovery may deliver history to avoid rediscovery, but a prior manual observation is not a new passing result. A manual result needs current environment and method revalidation; exact planned-machine-check reuse remains controller-owned.

## Active authority during normalization

Normalize from the approved source documents together with actual current user/delegated execution permissions. Preserve the actor, exact permission scope and source locator in the normalization proof. A report claiming an override is insufficient if the bound method descriptions or capabilities still contradict it. Every permitted alternative needs its own coherent prerequisites; capabilities within one method are conjunctive, while listed methods are alternatives. Keep unrelated mandatory methods, evidence and outcomes intact.

Before binding, compare every intentional method/prerequisite change with that authority and check both accepted and unavailable-alternative cases. Keep operative permission/exception text in the canonical definition; deduplicate exact text or link verified resources instead of shortening away its meaning. Shape validation, assertion counts and equality to an already lossy draft do not establish semantic equivalence to the source. An authorized method alternative never overrides an actual tool/security denial; use only a permitted materially safer action and retain unverified requirements truthfully.

## Producer feasibility

Before Engineering, the existing Planning/recipe owner establishes for each evidence-producing method who can run it, its actual available channel/result, durable capture, candidate/environment binding and independent reading. Probe the channel's ability to produce that evidence, not the feature before it exists. A listed capability, renamed build receipt or declaration alone is not this proof. Preserve methods and thresholds; changing an approved method still follows its authority route.

Deliver those actual locators in the existing bound method/probe and setup artifacts so QA can [agree the execution route](#agree-the-execution-route) without rediscovering unrelated environment details. The producer/channel must match the selected approved method before execution. A mismatch uses the existing responsible owner, not product Engineering or blanket unavailability. A first actual invocation/result with durable independent readability proves that channel route; it is not a rehearsal of the full QA matrix or proof of a later product target.

Schema 1 methods may include one `producer` and `require_assessment: true`:

- Controller execution: `{"kind":"controller_check","check_ids":["exact-sealed-recipe-id"]}`. Those exact checks must actually produce the method's required evidence. `bound-machine-receipt` and `controller-check-receipt` require this mapping to sealed current-slice recipes; an unrelated build cannot stand in for a scenario execution.
- Tool/manual channel: `{"kind":"tool","channel":"exact-available-channel","probe_ref":"execution-evidence:feature-channel-probe"}` (or `kind:"manual"`). The common immutable execution record contains the actual probe invocation, stable environment, original response, input binding and independent raw-result locator. No CLI command is required for a tool/manual method.

Use [Artifact and execution record I/O](execution-contract.md#artifact-and-execution-record-io). To avoid a plan-hash cycle, choose the stable probe record ID/reference in the draft, approve those exact plan bytes, then let the existing recipe owner perform and capture the actual preflight against the approved sources before Engineering. The reserved reference is not evidence until that record exists and validates. Do not edit the plan after capturing its probe or treat an older preapproval observation as current proof; source changes need a current bound probe under a new actual invocation ID and the ordinary binding route.

The controller exposes `context.verification_feasibility` to the existing roles and rejects incompatible receipt/producer bindings before Engineering, including the confirmation shortcut. Feasibility respects approved alternatives: one viable method can satisfy an assertion; an unavailable optional alternative remains diagnostic rather than blocking that method. Tool/manual probes are checked for integrity, source/channel binding and input stability, not semantic truth. Legacy methods without producer metadata remain readable as explicitly unverified feasibility; they gain no implied probe or acceptance credit. Shared `method_definitions` keep repeated producer/method details canonical. A preflight record can establish channel availability but never count as an executed product assertion.

## Manifest

```json
{
  "schema": 1,
  "confirm_approved_plan": true,
  "slices": {
    "SLICE-001": {
      "identities": [{
        "id": "MANUAL-FEATURE-RUNTIME",
        "source": "docs/feature/development-plan.md#verification-and-exit-criteria",
        "assertions": [{
          "id": "runtime-reset",
          "expected": "The approved reset action restores the initial usable state.",
          "methods": [{
            "id": "runtime-input",
            "source": "docs/feature/development-plan.md#verification-and-exit-criteria",
            "description": "Perform the approved reset input through the real integration and observe its resulting state.",
            "capabilities": ["runtime-interaction"],
            "evidence_types": ["input-observation", "result-observation"],
            "producer": {"kind": "tool", "channel": "approved-runtime-channel", "probe_ref": "execution-evidence:feature-channel-probe"},
            "require_assessment": true
          }],
          "applicability": {"kind": "always", "condition": "always", "evidence_types": []},
          "depends_on": []
        }]
      }]
    }
  }
}
```

All identities and all assertions within an identity are conjunctive requirements. Name every independently mandatory case separately; do not merge five required scenarios into one broad claim. Assertion IDs are unique within a slice. `depends_on` references those exact assertion IDs, is acyclic and means successful prerequisite results are necessary for execution. Add dependencies only when approved execution actually requires them.

An assertion's `methods` are explicitly approved alternatives; satisfying one method requires all its `evidence_types`. Two methods that must both execute are two assertions, not alternatives. Method IDs are stable within their assertion, not native check command IDs. Method `capabilities` identify actual prerequisites; an empty list means no declared unavailable capability can excuse that method. Concrete commands, approved observations and acceptance thresholds belong in method descriptions, copied without reinterpretation from the cited authority. No inference from similar implementations grants a new alternative.

Schema 1 also permits a slice-local `method_definitions` object to store repeated, identical method objects once. For example, the slice above may move its method to:

```json
"method_definitions": {
  "shared-reset": {
    "id": "runtime-input",
    "source": "docs/feature/development-plan.md#verification-and-exit-criteria",
    "description": "Perform the approved reset input through the real integration and observe its resulting state.",
    "capabilities": ["runtime-interaction"],
    "evidence_types": ["input-observation", "result-observation"],
    "producer": {"kind": "tool", "channel": "approved-runtime-channel", "probe_ref": "execution-evidence:feature-channel-probe"},
    "require_assessment": true
  }
}
```

Its assertion then uses `"methods": [{"ref": "shared-reset"}]`. Inline methods and references may coexist. A reference has exactly one `ref` key naming an exact identifier defined in that same slice; definitions must be complete method objects and cannot reference other definitions. Every definition, including unused ones, receives the same shape and approved-source validation as an inline method. Resolved method IDs must remain unique within each assertion. Results still report the method's `id` (`runtime-input`), never the registry key (`shared-reset`).

This representation changes no identity, assertion, dependency, applicability condition, method, capability or evidence requirement. Keep every independently mandatory case. Validation and assignment retain the compact form; result validation resolves references locally, including all alternatives when checking unavailable capabilities. `expand_slice_contract` provides a detached flat representation for lossless comparison. The contract digest binds the supplied representation, so converting an already bound contract follows the existing binding/change rules.

`applicability.kind: always` uses exactly `condition: always` and empty applicability evidence types. `conditional` records the approved condition and non-empty evidence types required to establish inapplicability. Absence of a defect, implementation symmetry or an unexercised branch does not prove an approved condition false.

## Independent assessment before serialization

QA assesses facts before a helper formats them. Start with the observable criterion in the approved source, establish method suitability and applicability, obtain the actual case/proof and current execution/environment binding, then compare its decisive observation with that criterion. Inspect what the cited test actually does and what the record actually ran. An action's success or a changed object does not establish its required appearance, state or effect. Contradictory expected/observed data excludes PASS; insufficient evidence remains unverified. A serializer copies assessed facts and never infers outcomes or observation text from an AUTO prefix, capabilities, test names, assertion IDs or green aggregates.

Use the [incremental cycle](#incremental-assessment) to turn each actual scenario or coherent case group into saved assessments while its evidence is available. Capturing cases without assessing their rows creates pending QA work, not Engineering defects.

One real shared execution record may support several IDs only after independently mapping its exact cases/observations to each assertion and permitted method. Keep common launch/binding/environment facts in that record once. If an outcome changes, reconcile method, environment, reason and evidence together; a PASS row must not retain old not_run prose. Reusing exact text/locators is allowed; a template sentence claiming every named case executed is not. [Evidence sufficiency](interaction-evidence.md#evidence-sufficiency) governs composed proof and unreachable conditional-policy outputs. A conditional no-callback scenario, when its approved applicability evidence proves there are no deferred callbacks, is `not_applicable`, never an executed pass. An always-applicable policy/reachability check may still pass through its approved composed proof; do not conflate the two.

A green suite with an absent mandatory case remains unproven. First retrieve actual existing proof and use permitted available checks; an inspected repairable test/evidence gap across all approved methods uses `verification_incomplete` below and the existing Engineering repair route. Distinguish that gap from an unavailable evidence-producing method, an external observation still awaited, a real capability denial and missing authority. An external remainder is not another Engineering task; mixed results retain every unverified obligation while routing only their repairable part. Do not relabel an external wait as missing capability or claim a missing case executed.

An unfinished observation review, untried available method or unmapped captured case remains with QA. A claimed Engineering gap must identify the actually inspected/attempted method, bound raw or source evidence, exact missing obligation and concrete repair target. Repeated wording is allowed for the same independently assessed cause; repetition neither proves nor disproves its truth. Contract/method definition IDs describe obligations and cannot serve as evidence that their execution or an actionable gap was observed.

Construction may reuse exact common method text, environments, observations or blocker reasons by local references, then materialize the existing canonical schema before validation/publication. Preserve exact wording, per-assertion applicability/method assessment and complete inventories. Reject unresolved or dangling construction references. No extra published registry, inherited policy, semantic compression or replacement method is authorized. A repeated genuine browser/tool denial can share one exact reason during construction; materialized affected rows remain `not_run`, and an independently available alternative must still be assessed.

## Agree the execution route

After preparing the actual group and before its first product action, select an approved method against the full obligations and alternatives. Confirm its actual producer, candidate target/resource, required capabilities, evidence capture/read route and governing permissions in this QA worker's current context. Use the supplied stable locators first; a parent's available tool, preflight success or session-local handle does not establish this worker's route or the current product invocation. A preflight resource is not the product target. Existing bound evidence still needs method/candidate/environment assessment; its presence alone does not authorize an action.

Use only APIs supported by the tool's current returned documentation. Where discovery is needed, inspect the relevant exposed channel and use its actual returned resource/instance IDs; do not infer a selectable instance from a tool name, inherited alias or another actor's inventory. Resolve stable locators into this worker's own supported handles, then consume their initial state/documentation before dependent actions. An unavailable alias or unexposed instance establishes that route's present limitation, not a global security prohibition or a successful preflight. This is targeted route agreement, not environment-wide discovery or another full matrix rehearsal.

If the prepared producer and actual available route differ, use [Environment actions](interaction-evidence.md#environment-actions) and the existing responsible owner's [technical assessment](technical-decisions.md#resolve-before-escalating) before switching. An already permitted compatible route may resolve unavailable transport; it cannot change the approved method or waive a prescribed resource, platform compatibility, offline behavior or evidence requirement. Preserve every actual security/policy denial with its stated outcome and scope across tools and later runs; never obtain that denied outcome through another surface or transport. Inspect permitted approved alternatives without bypassing the denial. If no sufficient permitted route remains, keep the affected obligations unverified with the exact prerequisite/recovery action under [Complete terminal results](#complete-terminal-results), while continuing independent available groups.

## Incremental assessment

Use this cycle inside the current QA assignment. Saved assertions are evaluated; absent IDs are pending assessment, not `not_run`. Prepend the supplied launcher and exact global root/feature arguments to the command suffixes below. Keep their issued assignment and packet binding.

1. **Restore metadata and select pending work.** With the current assignment/candidate binding restored by the worker read route, `qa-draft --assignment-id <id>` creates or resumes the working artifact; `qa-read --assignment-id <id>` returns revision, binding and assessed/pending counts per identity. Run `reader.qa_index.exec_command` and consume its exact `id`, `source`, `assertion_ids` inventory before selecting an actual scenario/proof/blocker group. When an identity is coherent, use its one `prepare` handle: the native helper expands its exact `--identity-id` to the ordered assertions. For another coherent subset, take the exact returned `assertion_ids` into repeated `--assertion-id`; do not combine selectors. Grouping is semantic, without row/time/token quotas. Selected `qa-read --identity-id` restores saved rows and exact pending IDs when needed. Inventory is navigation; the next step reads the obligations.
2. **Prepare and read.** Execute that group's preparation through [Host command presentation](delivery-contract.md#host-command-presentation). Normal `qa-prepare` saves editable input at its generated bound `ReadOutputs` destination; ordinary presentation separately saves the complete native reading context and supplies guarded body pages. The prepared value's `saved_record_request` locates the editable input, not the context envelope. Consume every required page and operative field before selecting a method. Complete `obligations` supply expectations, applicability, dependencies, sources and every approved alternative; `producer_context` connects actual producer/evidence locators through `method_refs`. Saved bytes and selected-body completion do not establish consumption or assessment. Exact duplicate method definitions may be shared once; their IDs alone do not supply their meaning. An explicit `--method-id` remains available when already selected, but does not hide alternatives. A single approved method can be filled mechanically; multiple alternatives require QA's actual selection. This replaces preliminary `qa-assertion` and separate prepare-to-save calls.
3. **Agree the actual method and route.** Follow [Agree the execution route](#agree-the-execution-route) for the selected method, actual producer, same-worker context/resource and permissions before the first product action. Keep the approved alternatives and every prescribed requirement intact. A resolved route continues to step 4; a genuine obstacle takes the named technical/classification route while independent groups continue. A complete approved procedure and known permitted target/tool let QA construct the actual invocation; a product script is not a prerequisite.
4. **Obtain the actual evidence.** Use bound `context.machine_checks` and the chosen method's actual channel, target, resource and probe/receipt locators. Retrieve existing records before requesting new execution. Missing applicable controller evidence follows [active checks](execution-contract.md#check-inside-active-engineering-or-qa) under the exact grant or Director relay. Authorized tool/manual actions follow [Environment actions](interaction-evidence.md#environment-actions); preserve the actual candidate and before/result/after records under [Preserve execution evidence](interaction-evidence.md#preserve-execution-evidence). Capture real execution through [Artifact and execution record I/O](execution-contract.md#artifact-and-execution-record-io): the prepared begin request carries channel/assignment, while QA supplies the actual request, environment, input paths and invocation ID before execution. Continue only with the complete actual result and required current binding.
5. **Compare each assertion against the whole proof.** Independently assess the actual case and decisive observations under [Independent assessment](#independent-assessment-before-serialization) and [Evidence sufficiency](interaction-evidence.md#evidence-sufficiency). Inspect test bodies, material premises at action time and decisive assertions for automated evidence, and actual images for visual evidence. Credit sufficient complementary execution/source/composed proof before identifying a remaining mandatory gap; a locally weak assertion alone does not establish global insufficiency. Fill the prepared request with each evaluated assertion's accurate actual observation, comparison and evidence observation, selecting outcome/reason where required. Shared method/environment and exact evidence provenance may appear once; shared fields never provide observed text, comparison or outcomes. Use the actual source reader's binding for source proof and the record's actual native/caller provenance for execution proof. Ambiguous provenance stays explicit per row; do not relabel origins or copy definition IDs as evidence. Apply [Complete terminal results](#complete-terminal-results) for not_run/NA and assess every alternative before declaring all unavailable. Unmapped captured cases and unfinished comparison return here with this QA owner; only the contract's concrete inspected repairable defect/gap goes to Engineering.
6. **Save the finished group.** Submit `qa-record --assignment-id <id> --source <group.json>` immediately, before beginning the next group. The helper fills exact approved expected text and unambiguous service metadata, expands the compact request into strict canonical rows, validates it atomically and returns the current revision/binding/counts and changed IDs. Retain that revision for the next update. An encountered obstacle requires the existing technical assessment and [Current journal](technical-decisions.md#current-journal) update through `technical_decisions`: update the same stable ID and preserve omitted entries. A decision-only checkpoint leaves pending assertions pending. Decisions survive draft/read/finalize through the existing journal consumer; they grant no method equivalence or acceptance.
7. **Continue or finish the full inventory.** Return to step 1 for pending natural groups. When every issued ID is evaluated, `qa-finalize --assignment-id <id> --expected-revision <revision>` derives complete identity/terminal aggregates and writes the issued artifact, including fail or blocked inventories. Follow the [QA artifact contract](../../gamedev-qa/references/qa-output-contract.md) and [terminal artifact boundary](stage-handoff-invariant.md#terminal-artifact-boundary). Pending assessment returns `valid:false` to this same QA owner and resumes the cycle; it is not an Engineering defect. Structural finalization grants neither semantic truth nor native phase PASS.

These command suffixes create/restore progress. Use the issued assignment and supplied launcher/root/feature:

```console
qa-draft --assignment-id qa-bound
qa-read --assignment-id qa-bound
```

Next consume `reader.qa_index`, choose the actual coherent group and run its `prepare` handle. Read the returned full obligations/producers, agree the actual route, obtain and assess the real evidence, then fill the file located by `saved_record_request`. Use that returned path and the actual revision in these suffixes:

```console
qa-record --assignment-id qa-bound --source <saved-record-request-path>
qa-finalize --assignment-id qa-bound --expected-revision 1
```

The prepared request keeps its generated `binding` and `expected_revision`. `request_status` distinguishes a new/identical request from a preserved edited file; inspect that retained file under the current binding before continuing. Explicit output/pointer and JSON-envelope readers remain compatibility routes. Request `shared` may hold `method_id`, actual `environment`, and evidence provenance `{type,ref,source?}`; each assessment still supplies its own evidence `type`/`observation` and `assessment.observed`/`comparison`. Conflicting or ambiguous shared provenance requires exact per-row provenance. Source readers supply original `evidence_origin`, not the saved envelope's file origin. For an issued/prepared receipt's `execution_evidence: execution-evidence:<record-id>`, use `evidence-read --record-id <record-id> --format text --present`; an optional `#observation` fragment is not part of the record ID. The receipt's `execution_record_digest` and `source_locator` retain its binding. A `check --with-delivery` result additionally supplies a ready `read` handle; use it when present and consume its required pages. Reuse the existing record instead of running a new check to obtain a reader or searching receipt folders. Inspect the real referenced content. Preparation never chooses outcomes or establishes sufficient evidence. Keep complete raw evidence outside the candidate. Selected `qa-read`, `qa-prepare` and `evidence-read --pointer` remain available for restoration; ordinary current/next handles restore the same captured context, while [transport recovery](delivery-contract.md#transport-recovery-and-compatibility) covers unavailable handles or older callers.

After host/context interruption, restore the current binding and `qa-read` before another action, then consume the pending group's required sources/methods. The working binding survives a diagnostic cursor advance on unchanged assignment/authority/contract/candidate; generation alone is not its identity. Reuse genuinely retained compatible observations, never historical PASS or lost-context baselines/session handles. Changed candidate/authority follows the existing restoration/error route.

## Complete terminal results

Follow the issued artifact schema. A bound QA result contains every assigned identity and every assertion exactly once for **pass, fail and blocked**. Retain the existing identity `{id,outcome,evidence}` summary and add `assertions`. Each assertion is:

```json
{
  "id": "runtime-reset",
  "outcome": "pass",
  "method_id": "runtime-input",
  "environment": "Actual assigned session, relevant runtime configuration and available input capability.",
  "assessment": {
    "expected": "The approved reset action restores the initial usable state.",
    "observed": "After the reset input, the observed initial state is usable.",
    "comparison": "matches"
  },
  "evidence": [
    {"type": "input-observation", "ref": "exact-observation-locator", "observation": "The approved reset input was performed through the actual integration."},
    {"type": "result-observation", "ref": "exact-result-locator", "observation": "The observed initial state is usable after reset."}
  ]
}
```

`pass` and `fail` name one approved `method_id`, actual environment, and evidence of every required type, each with an exact retrievable `ref` and concrete `observation`. A generic success exit or assertion label cannot stand in for the required observation. A partially attempted method that lacks its required evidence stays `not_run`; retain its observations without claiming a completed failure method.

For the selected `controller_check` method, durable references must cover all its declared `check_ids` and match the controller-owned execution/result history; a copied provenance label is not a native receipt. Failed or incomplete native execution cannot support PASS. Tool/manual references retain caller-captured provenance and must match that method's declared channel. These binding checks complement, rather than replace, the expected/observed assessment.

An `assessment` copies the exact approved `expected`, states the actual decisive `observed` result and uses `comparison: matches|contradicts|insufficient`. A method with `require_assessment:true` requires it for its executed result; new plans use that explicit comparison. Legacy results may omit the field, but whenever supplied it is validated: PASS requires `matches`, executed fail requires `contradicts`, and not_run requires `insufficient`. This detects contradictory declared rows; it cannot establish that the supplied observation is true or correctly interpreted. Independent QA still performs the comparison.

`not_applicable` uses `method_id: null`, the actual environment and all approved applicability evidence. It is allowed only for an approved conditional assertion. It contributes to an identity's pass only after QA independently verifies that proof.

`not_run` uses `method_id: null`, environment, an evidence list (empty only when nothing was observed), and `reason: {kind,detail,refs}`. `detail` states the concrete observed obstacle or proof gap and `refs` is a non-empty list of exact identifiers:

- `capability_unavailable`: refs are declared capability IDs; they must prevent every approved alternative, not merely the preferred method.
- `dependency_unsatisfied`: refs are explicitly declared dependencies whose actual outcomes are not `pass`/`not_applicable`.
- `authority_unresolved`: refs identify the existing authority question; use the established authority boundary to resolve it.
- `verification_incomplete`: refs name every exact approved alternative method ID for this assertion. `detail` explains a concrete inspected test/proof gap, with `verification-gap` evidence of the actual missing obligation. Current submissions require `reason.repair: {owner:"engineering", target, missing_obligation, attempted_method_ids, evidence_refs}`: one exact authorized project-relative repair target, the specific missing test/proof, actual inspected/attempted semantic method IDs and current bound execution/source references. `qa-record` may derive omitted `evidence_refs` from those actual gap evidence rows. The method stays null because the required proof is incomplete. Unperformed QA mapping, a definition ID used as evidence or an available untried method cannot supply this repair claim. Historical artifacts remain readable, not newly actionable by that fact.
- `method_unavailable`: refs name every exact approved alternative method ID; `method-gap` evidence identifies why the available channel cannot produce, retain or independently expose the required evidence. This is a method/prerequisite boundary, not a repairable missing test or permission to weaken the method.
- `external_wait`: refs identify the pending external prerequisite/action; `external-prerequisite` evidence states the actual performer, required observation and remaining action. If execution was postponed, cite the real user/delegated authority and its scope. The criterion remains mandatory/not_run; a user's future check is not performed evidence and is not automatically a missing capability.

Complete independent available assertions before returning. An unavailable capability blocks only affected assertions and their declared dependants. Lack of time, a locally chosen effort limit or an untried approved alternative is not a reason to omit a scenario or mark it blocked.

For permitted source inspection/invariant proof, an evidence row may add `source: {path,sha256,start_line?,end_line?}` copied from the actual source reader; a span supplies both line fields. `qa-record` derives an omitted `ref` as `candidate-source:<path>@<sha256>#Lx-Ly` (without the suffix when no span). Direct terminal rows use that exact canonical reference. The helper verifies current candidate membership, read scope, original-file hash and span; it does not prove the prose observation. Do not require a capture or product run solely to wrap valid source evidence. Execution evidence continues to use its actual bound record/channel; neither kind may be relabelled as the other.

An identity derives `fail` if any assertion fails or contains `not_run` with `verification_incomplete`; otherwise it derives `not_run` for any unexecuted assertion, then `pass`. The terminal artifact derives `fail`, then `blocked`, then `pass`. Failed execution or a repairable proof gap follows existing Engineering remediation with the complete mixed inventory preserved. Pure external/method/capability/dependency/authority not_run yields blocked, not another Engineering task. After the repairable part is fixed, any such remainder still prevents acceptance. Use the existing bound recovery only after the actual prerequisite changes; do not omit or relabel it to simplify the verdict.

During remediation, `qa_previous_observations` carries only historical unresolved assertion rows for the same authority, contract and slice, with the original source locator and candidate binding. Engineering and Review must address/reassess that exact remainder after candidate changes; it grants no current execution or old PASS credit, and the next QA still evaluates the complete current contract. A later QA supersedes the older residual.

The controller validates exact inventories, approved method selection, required evidence fields, applicability/dependency structure, aggregate outcomes and binding. It cannot prove the truth of screenshots, telemetry or free-text observations. Independent QA remains responsible for genuine execution and evidence assessment; structural validation is not a substitute for that work.
