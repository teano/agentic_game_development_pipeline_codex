# Review requirements as an implementer

The stage owner delegates the full review to read-only subagents. Use at least one reviewer who did not author the text under review. Give reviewers the complete current requirements or assign bounded portions with explicit coverage and a pass over cross-system interactions. Include the current checkout, confirmed decisions, source locators, pending items and research evidence. Have reviewers inspect primary sources and return concrete findings. Reuse them for affected follow-up. If delegated review cannot run, report the missing check and continue available read-only work.

## Walk through the implementation

For each material requirement and acceptance criterion, reviewers should act as if they are about to implement and verify it in this checkout. Trace at least one credible route from the actual entry point through the affected systems, data and configuration to the observable result. Show existing behavior and reuse points, the missing development work and where the route would stop or force an unapproved choice. Make enough of the route explicit to expose dependencies. Leave detailed design, implementation and runtime launch to their authorized stages.

Check:

- **Meaning and coverage.** Compare against the user's decisions and relevant source passages. Look for omissions, new unsupported obligations, ambiguity, contradictions between requirements and unspecified behavior that would change acceptance. Walk representative normal and failure or edge cases where they expose a real gap.
- **Fit with the current project.** Verify affected code, settings, assets, integrations and targets. Check existing behavior and conflicts with other features or established constraints. A reusable subsystem may cover only part of the requirement.
- **Dependencies and access.** Identify packages, versions, supported APIs and platforms, external services, provisioning, license or cost, accounts, roles, entitlements, credentials, data and environments where the route needs them. Check installed packages in project manifests or equivalent evidence. Use official sources for compatibility and service prerequisites. Verify project-specific availability through authorized read-only evidence where possible. Distinguish what is present, what needs setup and what is unknown or unavailable. An installable package or documented service does not establish project access. Keep secrets out of findings. Do not install, provision, request credentials, spend funds or perform runtime tests as part of this review.
- **Verification path.** Identify how an implementer would observe each acceptance outcome and what access, device, test data or environment that requires. Record the limits of static checks and unperformed tests.

## Resolve findings and close the loop

For each material finding, return the affected requirement or criterion, the primary evidence locator, the concrete implementation or verification consequence, and the decision, correction or prerequisite needed. Identify viable alternatives when they change the user's choice. Name the responsible actor or exact access needed when known. Flag missing information as unknown and state how it can be checked.

The stage owner checks coverage and reconciles findings across reviewers. Correct the text where the existing authority is sufficient. Return only unresolved choices about behavior, scope, permission or material prerequisites to the interview. Record known setup and ordinary technical choices for handoff when they have a credible resolution within existing scope and permissions. A missing prerequisite that could invalidate delivery or acceptance needs a concrete resolution before readiness. Keep review evidence in existing project conventions or the stage context.

After answers or material corrections, review the affected content and its interactions again. Retain still-valid evidence for unaffected requirements. Complete the review cycle only when the full current set is covered and material findings are resolved. A favorable review establishes readiness for the approval decision. Approval still follows the shared artifact binding procedure.
