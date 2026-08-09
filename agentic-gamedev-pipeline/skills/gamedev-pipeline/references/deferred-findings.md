# Deferred findings backlog

`docs/engineering/deferred-findings.json` is the canonical tracked project backlog for supported problems that are outside the current feature and do not block its accepted behavior or required invariants. It is controller state owned by the technical director, not a feature requirement, report, or remediation queue. It is explicitly excluded from every current-feature product, support, evidence, and composite revision input.

Use `scripts/deferred_findings.py`; never edit the JSON directly. `init` creates schema 1 atomically. `backlog-upsert` (alias `defer`) creates or extends an entry. `extend`, `assign`, `reactivate`, `resolve`, and `link-duplicate` perform controlled transitions. `backlog-scope-check` must pass before positive convergence and Final Review decisions; the pipeline controller enforces the same gate.

## Identity and merge rules

`entries` is keyed by stable `DEF-*` ID. The ID is deterministically derived from the SHA-256 fingerprint of normalized `component + contract + root_cause + failure_mode + effect`. Revision, title, and a specific trigger never enter identity. The same fingerprint extends one existing entry: merge unique conditions, impacts, evidence, observers, origin features, and re-entry conditions, then append only a genuinely independent `occurrence_id`. Never create another entry because a new feature, revision, reviewer, trigger, or symptom wording found the same root cause.

Create a distinct entry only for a different root cause or an independently fixable problem. When differently fingerprinted records are later proven to be the same fix, use `link-duplicate`; do not erase either record. Rediscovery of `resolved` atomically changes it to `reopened`. Severity may increase only when the same command supplies new evidence, and every status/severity transition remains in history.

Each entry records `id`, `fingerprint`, `status`, title, component, contract, root cause, failure mode, effect, problem, violated invariant, provisional severity, reachability, owner, unique conditions/impacts/evidence, append-only occurrences, first/last seen, observers, origin features, latest current-scope context, re-entry conditions, links, and transition histories. Valid statuses are `deferred_untriaged`, `deferred_owned`, `planned`, `in_progress`, `resolved`, `reopened`, `wont_fix`, and `duplicate`.

## Scope routing

A supported nonblocking `preexisting_adjacent` or `out_of_scope` candidate must be upserted and linked as `docs/engineering/deferred-findings.json#DEF-*` before convergence can finish. No worker may silently discard it. Researchers, Engineers, and reviewers emit compact candidates; only the technical director classifies, deduplicates, and mutates the backlog.

Return a problem to current scope instead of deferring it when the candidate introduced or worsened it, the changed contract or new feature path makes its trigger reachable, it blocks an approved acceptance criterion or required invariant, or it creates a safety/data-loss/security risk for the current solution. If that return requires a material architecture, lifecycle, ownership, public-contract, slice-boundary, or file-budget change, retain `scope_expansion_hold`; resume only with the user-approved updated development plan and normal `rebaseline-scope` gate.

Specification work may read only component-relevant entries as risk evidence; backlog entries do not add requirements or product scope. Development planning may record a deferred dependency/risk but must not create a slice for it without an approved current-feature requirement or explicit user scope expansion.
