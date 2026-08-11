# Coverage contract

## Schema 2

A coverage manifest separates mapping, registration, automated execution, and manual execution. It records:

```json
{
  "schema": 2,
  "feature": "feature-slug",
  "slice_id": "SLICE-001",
  "mode": "planned|finalized|qa_updated",
  "authority": {
    "plan_path": "path",
    "plan_sha256": "64 lowercase hex",
    "prd_path": "path",
    "prd_sha256": "64 lowercase hex",
    "spec_path": "path",
    "spec_sha256": "64 lowercase hex"
  },
  "revisions": {
    "revision": "exact composite",
    "product_revision": "exact product",
    "support_revision": "exact support",
    "evidence_revision": "exact evidence"
  },
  "ac_mappings": [],
  "expected_identities": [],
  "actual_identities": [],
  "mandatory_expected_identity_ids": [],
  "mandatory_actual_identity_ids": [],
  "automated_execution": [],
  "manual_execution": [],
  "amendments": [],
  "gaps": [],
  "summary": {}
}
```

Every `ac_mappings[]` row has exactly `acceptance_id`, `status: mapped|gap|not_applicable`, `identity_ids`, and `authority_id`. `authority_id` is `null` for `mapped` or `gap`. `not_applicable` requires `identity_ids: []` and an `authority_id` naming an active accepted `DEC-*` ledger entry; prose alone is invalid. This explicit field resolves the otherwise unverifiable requirement to authorize a `not_applicable` row without adding the acceptance criterion to coverage. `mapped` requires at least one registered identity.

Every expected or actual identity has:

- globally unique `identity_id`;
- `kind: automated|manual`;
- explicit `mandatory: true|false`;
- owning `slice_id`, `requirement_ids`, and `acceptance_ids`;
- exact coordinates:
  - automated: repository-relative `file`, `suite`, `symbol`, and `case`;
  - manual: stable `scenario_id`, topology, setup, action, observation, and evidence kind;
- planned assertion/observation and capability prerequisites.

Identity comparison uses exact, case-sensitive IDs after duplicate rejection. A finalized manifest requires:

```text
set(expected_identity_ids) == set(actual_identity_ids)
set(mandatory_expected_identity_ids) == set(mandatory_actual_identity_ids)
mandatory_expected_identity_ids == IDs explicitly marked mandatory in expected_identities
mandatory_actual_identity_ids == IDs explicitly marked mandatory in actual_identities
```

This is registration equality, not execution success. Extra actual identities are as invalid as missing ones until a controlled amendment updates the expected set. Amendments are append-only and cite an accepted `DEC-*`, normalized finding ID, or approved scope-rebaseline reference assigned to the current Steward capsule plus before/after set digests. The controller revalidates every historical amendment's exact schema, unique ID, authority and full hash-chain prefix. For newly appended amendments, the union of `affected_acceptance_ids` must equal the controller-derived semantic planned-to-final AC change set in both directions; a broader, narrower, reordered-only, or unauthorised change fails closed.

## Independent execution dimensions

Each automated execution row names an actual automated identity and records `executed: true|false`, `passed: true|false|null`, exact command, result/evidence path, and evidence SHA. `passed=true` requires `executed=true`. A mandatory automated identity must be executed and pass for implementation completion.

QA returns every actual manual identity exactly once. Each row records `executed: true|false`, `passed: true|false|null`, `deferred: true|false`, `blocked_by_finding: finding-id|null`, immutable QA evidence path/SHA, and gate/resume data. `deferred=true` requires `executed=false`, one of `blocked_user|blocked_environment|error_test`, the matching failed capability probe category, and a minimum resume action. A scenario blocked by a product finding is unexecuted/non-deferred and cites an open blocking QA finding bound to that identity.

Every failed identity binds to an exact-current QA product finding through `coverage_identity_ids`. Mandatory failure requires an open blocking finding. An optional failure may remain compatible with aggregate pass only through an accepted nonblocking Minor exact-revision QA finding. Mixed external gates retain every category and deferred identity while the controller derives one deterministic overall status.

The summary contains these independent fields:

```json
{
  "ac_mapped": true,
  "identities_registered": "complete|mismatch|gaps",
  "expected_count": 0,
  "actual_count": 0,
  "mandatory_expected_count": 0,
  "mandatory_actual_count": 0,
  "automated": "pending|passed|failed|blocked",
  "manual": "pending|passed|failed|deferred",
  "implementation_eligible": false,
  "feature_verification_eligible": false
}
```

`implementation_eligible=true` requires all assigned acceptance IDs mapped, exact expected/actual and mandatory-set equality, no unresolved coverage gap, and every mandatory automated identity executed and passed. Mandatory manual identities may remain pending. `feature_verification_eligible=true` additionally requires every mandatory manual identity executed and passed, no mandatory `blocked_by_finding`, and no mandatory deferred scenario. Accepted nonblocking optional failures remain explicit evidence and do not silently become passes.

Coverage manifests, reports, and execution indexes are controller evidence artifacts and are excluded from product/support/evidence revision inputs. Tests and fixtures themselves remain `evidence_revision` inputs. QA appends immutable manual execution evidence; the controller produces the `qa_updated` aggregate without rewriting the Steward's finalized artifact.
