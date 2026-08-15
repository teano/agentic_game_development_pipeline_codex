# QA output contract

Return the schema-2 manual execution envelope on the exact current revisions. It has exactly integer `schema: 2`, `revision`, `product_revision`, `support_revision`, `evidence_revision`, and `manual_execution`.

Every registered manual identity appears exactly once. Each row has exactly string `identity_id`; booleans `executed` and `deferred`; boolean-or-null `passed`; string-or-null `blocked_by_finding`; object-or-null `qa_evidence`, exactly `{path,sha256}`; enum-or-null `gate: blocked_user|blocked_environment|error_test`; and string-or-null `minimum_resume_action`.

Every row is exactly one exhaustive outcome. Executed rows require boolean pass and immutable evidence. Deferred rows are unexecuted/null-pass, require gate and resume action, and forbid evidence/finding. Product-finding-blocked rows are unexecuted/non-deferred and otherwise null. A non-deferred row forbids both gate and resume action; an unexecuted row with neither deferral nor finding is invalid.

The worker returns this envelope and evidence artifacts. The controller validates the supplied status, records the immutable run, and generates the `qa_updated` aggregate; QA never persists controller state itself.
