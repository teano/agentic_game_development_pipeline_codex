# Lifecycle projection recovery

This contract is conditional. Read it only when compact `status` reports revision-inventory drift involving a generated feature dashboard or records a lifecycle-projection reconciliation.

## Fail-closed allowlist

The controller may reconcile one lifecycle projection drift without a writer lease only to recover an `engineering` remediation state. It requires all of the following:

- no active write lease or pending Engineer completion;
- one exact active remediation batch whose IDs and route equal every open remediation-required finding;
- unchanged support and evidence identities;
- exactly one active feature manifest within the project;
- exactly one changed product path and one matching dashboard row;
- only the row's final `Updated` date changed;
- that date equals the UTC day of the manifest's RFC3339 `updatedAt`;
- a unique reverse candidate reproduces both frozen product and composite revisions.

Legacy reverse search is bounded to ten years. A second path, row/title/status/link edit, malformed or non-UTC manifest, ambiguous candidate, path/junction escape, or conflicting receipt preserves the blanket inventory-drift failure.

## Successful recovery

Reconciliation records frozen per-file revisions and a projection guard, writes an append-only SHA-bound receipt below the controller verification directory, and advances only product/composite identities. It preserves phase, owner, remediation batch/queue, findings, and historical convergence evidence.

Unused Engineer capsules on the old identity become stale. Component Review credits covering the dashboard become invalid. A pre-edit check bound to the prior identity is cleared. The next Engineer capsule must include the exact reconciliation receipt.

An exact orphan receipt left before state persistence is reusable; conflicting bytes fail closed. This is controller-only recovery: never modify feature Pause/Continue scripts or product files to bypass it.
