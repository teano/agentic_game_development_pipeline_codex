# Severity and readiness

## Finding classification

Classify kind and severity independently.

Kinds:

- `product`: production behavior, contract, configuration, integration, or runtime source is wrong;
- `evidence`: required tests, fixtures, assertions, measurements, cleanup guarantees, or coverage cannot protect approved behavior.

Severity:

- `critical`: security compromise, data loss, unrecoverable corruption, unsafe external action, crash/hard blocker in a core flow, or release-breaking requirement failure;
- `major`: incorrect core behavior, material requirement violation, likely regression, missing important failure handling, serious performance breach, or evidence that demonstrably cannot protect an important behavior;
- `minor`: bounded defect or maintainability risk that does not invalidate a core flow and has a safe workaround.

Do not create a finding for unavailable tools, permissions, credentials, publication, manual actions, unrelated noise, or an unexecuted scenario. Record those as gates. Do not demand a preferred duplicate evidence format unless approved sources require it or existing proof misses an important failure.

Fix ordinary in-scope defects in the owning Engineer pass. Persist only unresolved defects, Review/QA findings awaiting engineering, and minor risks awaiting explicit acceptance.

## Gate classification

- `blocked_user`: a user-controlled permission, credential, publication, or manual step is required;
- `blocked_environment`: a required runtime, client, device, service, or tool is unavailable;
- `error_test`: setup, harness, automation, or observation failed before product behavior could be judged.

Each gate records the exact revision, pending scenario IDs, completed reusable evidence, reason, and minimum resume action. Gates have no product severity. Only `blocked_user` inherently requires user input.

## Production-ready candidate

Require all of the following:

- current approved PRD and traced technical specification;
- every repository-required supporting product document, including an ADR when policy requires one;
- no source drift;
- current-revision passing machine/engine verification and complete coverage manifest;
- one fresh scope-complete `CLEAN` Engineer on the current product revision;
- two distinct passed full Reviews on the current identities, or their preserved same-product reports plus one passed recovery reviewer;
- feature-focused runtime QA `pass` on the current revision;
- no unresolved critical/major finding;
- no unaccepted minor finding;
- no open gate hiding a mandatory scenario;
- controller phase `ready` and successful `ready` command.

This verdict is a production-ready candidate, not authorization to publish, deploy, migrate, spend, submit, or accept risk.
