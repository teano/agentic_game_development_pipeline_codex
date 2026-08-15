# Documentation contract

## State model

The controller tracks two independent documentation dimensions:

```json
{
  "normative": {
    "status": "pending|required_complete|not_required|gap",
    "product_revision": "exact product revision",
    "paths": [],
    "decision_ids": [],
    "report_path": "path",
    "report_sha256": "64 lowercase hex",
    "source_map_path": "path",
    "source_map_sha256": "64 lowercase hex"
  },
  "derived": {
    "status": "pending|required_complete|not_required|gap",
    "support_revision": "exact support revision",
    "paths": [],
    "source_evidence_ids": [],
    "report_path": "path",
    "report_sha256": "64 lowercase hex",
    "source_map_path": "path",
    "source_map_sha256": "64 lowercase hex",
    "closure_review_id": "id or pending"
  }
}
```

The controller may record `not_required` only from the approved plan's Documentation Contract and repository policy. A worker cannot waive an assigned document.

## Normative pre-Review mode

Normative outputs define behavior, contracts, lifecycle, compatibility, configuration, or required operation. They are product-domain inputs. The context capsule lists exact allowed paths, active decision IDs, approved requirement/specification IDs, implemented contract evidence, exclusions, and output/report paths.

Every changed semantic statement must map to one or more active accepted sources. A decision ledger entry cannot be silently reinterpreted. Missing or contradictory authority returns `DOCUMENTATION_DECISION_GAP`; the Finisher makes no choice. Completion must occur before convergence/Final Review freeze. Later normative drift is product drift and invalidates convergence, Review, QA, and derived-doc closure.

Decision ledger and ADR decision capture remain owned by the Decision Recorder. The Finisher may reference them, not add alternatives or decision rationale.

## Derived post-QA mode

Derived outputs summarize an already reviewed and QA-observed result for handoff, indexes, operators, or support. They are support-domain inputs. Worker-authorable sources are limited to exact active `DEC-*` records, the closed QA manual-execution envelope, validated Review component-credit manifests, and controller handoffs named by path/SHA in the capsule. Generic QA, capability-probe, and Review reports are audit-only and never source authority.

Derived completion happens after QA so the documents can cite actual operator paths and observed evidence. It may not rewrite QA evidence or turn a deferred/manual gate into a pass. Each operator step must identify its source scenario/capability evidence; each troubleshooting claim must identify its finding or observed failure path.

The controller accepts post-QA completion without rerunning runtime QA only when all conditions hold:

- current `product_revision` and `evidence_revision` exactly equal the revisions covered by passed QA;
- changed paths are all registered support paths and no normative file changed;
- the controller-generated diff class is `support_only`;
- one fresh read-only `documentation-closure` reviewer verifies every changed support statement against exact sources;
- no mandatory manual identity is pending, failed, blocked, or deferred.

Otherwise fail closed to the ordinary invalidation route. The new composite revision remains exact: readiness uses current product/support/evidence identities, QA credit keyed to unchanged product/evidence identities, and documentation-closure credit keyed to the current support revision.

## Controller-owned mechanics

The Finisher returns two separate inputs:

1. the worker-owned schema-1 semantic write packet linked from `SKILL.md`, with complete domain inventory, exact changed-path annotations, one unique `DOC-CHG-*` `change_id` per change, and open assumptions;
2. this exact schema-1 statement source map:

```json
{
  "schema": 1,
  "mode": "normative_pre_review|derived_post_qa",
  "statements": [
    {
      "statement_id": "DOC-CHG-001",
      "path": "one actually changed allowed output",
      "source_kind": "lane-allowed kind",
      "source_id": "controller-recognized ID",
      "source_path": "exact controller-recognized source",
      "source_sha256": "current 64 lowercase hex",
      "target_sha256": "exact current changed artifact SHA, or null for deletion"
    }
  ]
}
```

The set of `statement_id` values must exactly equal the semantic packet's `change_id` set, and every row must name that change's exact path and current target SHA. One change ID may repeat only to cite distinct sources; duplicate source mappings are invalid. Normative source kinds are `decision`, `requirement`, `specification`, and `public_contract`; derived source kinds are `decision`, `qa`, `review`, and `controller_handoff`. `qa` means the closed manual-execution envelope, not the generic QA report. Source ID/path/SHA must match exact capsule evidence and controller-known authority for the lane. A stale or unrecognized source fails closed without state mutation.

The controller validates both packets, computes revisions, enumerates changed paths/symbols/lines, classifies domain drift, records the source-map path/SHA, and generates the handoff `documentation_state`. A worker-authored revision hash, change count, or sealed manifest is advisory and cannot satisfy a gate.
