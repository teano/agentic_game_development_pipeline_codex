# QA acceptance contract

Use the generated assignment reader for the resolved logical `context.qa_contract.definition` and its identity/assertion/method units. Transport references are not missing criteria and must not be copied into semantic result fields. Read each required shared method once; preserve its full operative wording.

One authority-bound contract defines the assertions, approved methods and required evidence for every mandatory QA identity. Engineering, Review and QA receive the same slice definition through `assignment.context.qa_contract`; use that definition without independently strengthening or weakening it. Capabilities and evidence types are project-defined identifiers: this contract requires no particular platform, device, browser, engine, instrumentation or extra test.

## Source and binding

For new plans, author one `## QA Acceptance Contract` section containing exactly one `json` fence with the manifest below. Keep the exact `mandatory_identity_ids` in each existing Coverage Contract; the manifest's slice and identity sets must equal that inventory. The manifest holds method details once; other sections reference its assertion/method IDs.

For an existing approved plan, an explicitly supplied `init --qa-contract <manifest.json>` can bind the same schema to the unchanged approved PRD/SPEC/PLAN. `confirm_approved_plan: true` asserts faithful extraction of existing authority, not permission to add a test, waive a case, invent equivalence or resolve an ambiguous product decision. Every identity and method cites an approved path plus anchor. Unresolved source wording uses the existing bounded authority clarification route; material acceptance changes require the owning stage's approval. A missing contract remains `unresolved` and cannot grant method-verified QA PASS. Never regenerate approved requirements, specification or plan merely to fill runtime metadata.

A supplied manifest must be workflow-local. Binding/changing it requires no active worker and no unresolved question. At an unchanged current Engineering candidate, binding preserves that implementation and archives previous Review/QA results, then issues fresh Review. It cannot alter the definitions of already completed slices while retaining their acceptance. A changed approved plan follows normal reconvergence. An identical contract is retained across runtime maintenance; altered source authority requires a fresh explicit extraction (or its embedded definition). A matching embedded definition cannot be overridden by an external manifest.

The controller owns the authority/contract digest, slice binding and the candidate/runtime binding of accepted results. Workers neither author those identities nor copy old digests into their output. Current evidence and old observations are separate: recovery may deliver history to avoid rediscovery, but a prior manual observation is not a new passing result. A manual result needs current environment and method revalidation; exact planned-machine-check reuse remains controller-owned.

## Active authority during normalization

Normalize from the approved source documents together with actual current user/delegated execution permissions. Preserve the actor, exact permission scope and source locator in the normalization proof. A report claiming an override is insufficient if the bound method descriptions or capabilities still contradict it. Every permitted alternative needs its own coherent prerequisites; capabilities within one method are conjunctive, while listed methods are alternatives. Keep unrelated mandatory methods, evidence and outcomes intact.

Before binding, compare every intentional method/prerequisite change with that authority and check both accepted and unavailable-alternative cases. Keep operative permission/exception text in the canonical definition; deduplicate exact text or link verified resources instead of shortening away its meaning. Shape validation, assertion counts and equality to an already lossy draft do not establish semantic equivalence to the source. An authorized method alternative never overrides an actual tool/security denial; use only a permitted materially safer action and retain unverified requirements truthfully.

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
            "evidence_types": ["input-observation", "result-observation"]
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
    "evidence_types": ["input-observation", "result-observation"]
  }
}
```

Its assertion then uses `"methods": [{"ref": "shared-reset"}]`. Inline methods and references may coexist. A reference has exactly one `ref` key naming an exact identifier defined in that same slice; definitions must be complete method objects and cannot reference other definitions. Every definition, including unused ones, receives the same shape and approved-source validation as an inline method. Resolved method IDs must remain unique within each assertion. Results still report the method's `id` (`runtime-input`), never the registry key (`shared-reset`).

This representation changes no identity, assertion, dependency, applicability condition, method, capability or evidence requirement. Keep every independently mandatory case. Validation and assignment retain the compact form; result validation resolves references locally, including all alternatives when checking unavailable capabilities. `expand_slice_contract` provides a detached flat representation for lossless comparison. The contract digest binds the supplied representation, so converting an already bound contract follows the existing binding/change rules.

`applicability.kind: always` uses exactly `condition: always` and empty applicability evidence types. `conditional` records the approved condition and non-empty evidence types required to establish inapplicability. Absence of a defect, implementation symmetry or an unexercised branch does not prove an approved condition false.

## Independent assessment before serialization

QA assesses facts before a helper formats them. For every assertion, establish the approved applicability, actual inspected case or proof locator, current execution/environment binding, expected result and concrete observation. Inspect what the cited test actually does and what the receipt actually ran. A serializer may copy that assessed row; it must not infer an outcome or invent observation text from an AUTO prefix, method capabilities, test name, assertion ID or green suite aggregate.

One real shared observation may support several IDs only after independently mapping its decisive facts to each assertion and permitted method. Reusing exact text/locators in construction is allowed; a template sentence claiming every named case executed is not. [Evidence sufficiency](interaction-evidence.md#evidence-sufficiency) governs composed proof and unreachable conditional-policy outputs. A conditional no-callback scenario, when its approved applicability evidence proves there are no deferred callbacks, is `not_applicable`, never an executed pass. An always-applicable policy/reachability check may still pass through its approved composed proof; do not conflate the two.

A green suite with an absent mandatory case remains unproven. First retrieve actual existing proof and use permitted available checks; if a concrete required proof gap remains across all approved methods, report `not_run` with `verification_incomplete` below. This yields failed acceptance and the existing Engineering repair route without claiming the missing case executed. Do not invent a capability denial, authority question or new outcome enum to fit the row.

Construction may reuse exact common method text, environments, observations or blocker reasons by local references, then materialize the existing canonical schema before validation/publication. Preserve exact wording, per-assertion applicability/method assessment and complete inventories. Reject unresolved or dangling construction references. No extra published registry, inherited policy, semantic compression or replacement method is authorized. A repeated genuine browser/tool denial can share one exact reason during construction; materialized affected rows remain `not_run`, and an independently available alternative must still be assessed.

## Complete terminal results

Follow the issued artifact schema. A bound QA result contains every assigned identity and every assertion exactly once for **pass, fail and blocked**. Retain the existing identity `{id,outcome,evidence}` summary and add `assertions`. Each assertion is:

```json
{
  "id": "runtime-reset",
  "outcome": "pass",
  "method_id": "runtime-input",
  "environment": "Actual assigned session, relevant runtime configuration and available input capability.",
  "evidence": [
    {"type": "input-observation", "ref": "exact-observation-locator", "observation": "The approved reset input was performed through the actual integration."},
    {"type": "result-observation", "ref": "exact-result-locator", "observation": "The observed initial state is usable after reset."}
  ]
}
```

`pass` and `fail` name one approved `method_id`, actual environment, and evidence of every required type, each with an exact retrievable `ref` and concrete `observation`. A generic success exit or assertion label cannot stand in for the required observation. A partially attempted method that lacks its required evidence stays `not_run`; retain its observations without claiming a completed failure method.

`not_applicable` uses `method_id: null`, the actual environment and all approved applicability evidence. It is allowed only for an approved conditional assertion. It contributes to an identity's pass only after QA independently verifies that proof.

`not_run` uses `method_id: null`, environment, an evidence list (empty only when nothing was observed), and `reason: {kind,detail,refs}`. `detail` states the concrete observed obstacle or proof gap and `refs` is a non-empty list of exact identifiers:

- `capability_unavailable`: refs are declared capability IDs; they must prevent every approved alternative, not merely the preferred method.
- `dependency_unsatisfied`: refs are explicitly declared dependencies whose actual outcomes are not `pass`/`not_applicable`.
- `authority_unresolved`: refs identify the existing authority question; use the established authority boundary to resolve it.
- `verification_incomplete`: refs name every exact approved alternative method ID for this assertion, with no unknown or omitted alternative. `detail` explains the concrete remaining proof gap after inspecting those methods. Include non-empty evidence with a `verification-gap` record whose exact inspected `ref` and factual `observation` establish what required case/proof is absent. This is an unexecuted/unproved acceptance obligation, not a claimed executed product failure; `method_id` stays null. Use it for a repairable evidence/test gap, never to bypass an available untried method or disguise an actual security denial.

Complete independent available assertions before returning. An unavailable capability blocks only affected assertions and their declared dependants. Lack of time, a locally chosen effort limit or an untried approved alternative is not a reason to omit a scenario or mark it blocked.

An identity derives `fail` if any assertion fails or contains `not_run` with `verification_incomplete`; otherwise it derives `not_run` for any unexecuted assertion, then `pass`. The terminal artifact derives `fail`, then `blocked`, then `pass`. Failed execution or a concrete repairable proof gap follows existing Engineering remediation while unrelated unavailable results remain intact. Once that gap is repaired, a remaining capability/dependency/authority `not_run` still prevents acceptance and yields blocked. Never omit it to simplify the verdict.

The controller validates exact inventories, approved method selection, required evidence fields, applicability/dependency structure, aggregate outcomes and binding. It cannot prove the truth of screenshots, telemetry or free-text observations. Independent QA remains responsible for genuine execution and evidence assessment; structural validation is not a substitute for that work.
