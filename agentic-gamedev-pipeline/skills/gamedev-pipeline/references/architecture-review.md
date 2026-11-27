# Design and review project boundaries

Use this baseline when a change introduces a module, a dependency between
owners, a new owner of state, a public contract or extension point, or moves
files across module boundaries. During final architecture review apply the
criteria to the whole delivered feature, including local changes within an
existing module. Scale each check to the responsibilities actually affected.

## Establish the relevant project rules

Use the assigned checkout and applicable instructions for the affected paths.
Find the relevant owner, existing contract, integration point and one
representative neighboring implementation. Project rules supply the actual
architecture, placement, terminology and checks. This baseline supplies the
engineering criteria, including when the project lacks architecture docs.
Use source and configuration as evidence of current behavior. If applicable
instructions and code disagree, name the conflict and assess its effect on the
requested change. Keep a documented, applicable project exception with its
scope and reason. Nearby legacy code alone does not establish an exception.

## Check the proposed or actual change

- **Responsibility and state.** Identify who owns each affected decision and
  write. Keep a coherent responsibility in each module. A coordinator owns
  sequencing and coordination state. A domain owner owns its rules, data and
  invariants. Follow creation, failure and cleanup where the change affects
  them. Look for a second source of truth or unrelated decisions in one facade.
- **Dependency direction.** Keep stable policy independent of specific
  consumers, extensions and replaceable infrastructure. Point source
  dependencies at the relevant contract and connect implementations at the
  established composition point. Inspect imports and package boundaries, plus
  semantic coupling through registries, events, data types and configuration.
  A runtime call through an injected contract can legitimately reach a concrete
  extension. A registry in the core with a case for each child is a different
  dependency even if the imports are acyclic.
- **Public contracts.** Prefer an existing operation when it has the correct
  owner and semantics. Give consumers capabilities appropriate to their role.
  Keep operation contracts expressed in the owner's vocabulary. A replacement
  implementation must preserve callers' guarantees for results, errors and
  lifecycle. Split interfaces or introduce an abstraction for a demonstrated
  boundary. Class size or number of interfaces alone does not establish a defect.
- **Extension.** When extensibility is part of the task, walk one representative
  next variant through registration and the normal entry point. List the code
  and configuration it would change. Check whether reusable components must
  learn the new variant's ID, type or policy. A project composition point can
  legitimately register a new implementation.
- **Placement.** Determine the owner, location and owning package or assembly
  for new or moved files. Use the project's layout and checks. If no layout is
  documented, use the neighboring example that fulfills the same role.
- **System and script decomposition.** Follow the affected production paths
  between peer systems and components, and through their internal layers. Check which
  element makes each decision and which collaborators it may call or mutate.
  Inspect changed scripts for mixed responsibilities, duplicate decisions,
  hidden dependencies and lifecycle or initialization in the wrong layer.
- **Naming and file structure.** Compare directories, filenames, symbols,
  module exports and script organization with the applicable project rules
  and terminology. Check that names communicate the real responsibility and
  that callers use the intended entry point. Explain any finding with the
  specific rule or its effect on navigation, ownership or safe extension.

## Show the evidence at the existing checkpoints

Before code, trace one relevant route from the normal entry point through the
coordinator and public contract to the state owner. Record the affected
ownership, dependencies, composition point and locations in the current
specification, plan or assignment. Include only facts that affect the change.
Use the existing independent review to challenge the route against the
project and these criteria.

On the first integrated implementation of the boundary, check the actual
route and diff before dependent work repeats the pattern. Check the affected
boundaries again in the integrated candidate. Report a finding with the path
or symbol, expected ownership or dependency, and concrete consequence. Use
the existing repair or decision path. State verified architecture and
observed product behavior separately, against the same candidate. Use a
project's static checks when available and the normal product path for
required integration evidence.
