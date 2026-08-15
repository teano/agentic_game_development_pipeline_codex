# Review output contract

Read only for the assigned Review mode. The generic human-readable report is audit-only; authoritative output is the exact component-credit manifest, any mode-specific closure report, and candidate findings registered separately by the Director.

## Component-credit manifest schema 1

The envelope contains integer `schema_version: 1`, exact current `revision`, `reviewer_id`, command-specific `review_mode`, and a non-empty `components` array. Modes are `full_convergence`, `final_whole_feature_review`, `targeted_closure`, `recovery_verification`, and `documentation_closure`.

Each component contains exact non-empty `component`; current-inventory `product_paths` and `contract_paths`; controller inventory `product_hash` and `contract_hash`; one or more lenses from `persistence-lifecycle|config-security-capacity|integration-runtime-docs`; `mode: fresh|reused`; and `source_credit_id` (`null` for fresh, exact prior `RC-*` for reused).

Final whole-feature Review additionally requires `composition_audit: true` and `new_boundaries_audited`; other modes omit both. Final Review performs its own inspection from current authority/handoff and accepted credit identities. It never reads or summarizes predecessor human conclusions.

## Documentation closure report schema 1

Documentation closure also returns exactly integer `schema: 1`; literal `review_mode: documentation_closure`; exact `run_id`, `reviewer_id`, `status: pass|fail`; current composite/product/support/evidence revisions; sorted `changed_support_paths`; exact statement-source-map path/SHA; unique `inspected_statement_ids` covering every distinct `DOC-CHG-*` change ID once; and `source_gaps`.

Pass requires no source gaps; fail requires at least one. The report, capsule, and component-credit manifest bind one idempotent request. Product credit may be reused only on matching product/contract hashes; documentation closure grants support closure only.
