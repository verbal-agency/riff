# G49 — Organize the repository for legibility and safe navigation

**Status:** Queued
**Depends on:** G42, G48
**Unlocks:** Faster goal execution, safer maintenance, and clearer onboarding
**Canonical scenario:** `SC-REPO-LEGIBILITY-001`

## Outcome

Riff's repository has an intentional, documented layout that lets a new
contributor or implementation agent quickly find the relevant domain, entry
point, test fixture, migration, operator command, and roadmap goal. The
organization reflects the current architecture without pretending that the
application is already a collection of independent services.

## Current problem to close

The top-level repository is reasonably organized, but the Python application
internals are comparatively flat and the relationship between domains,
interfaces, migrations, tests, reports, and goals is not obvious from the
filesystem alone. This increases navigation cost and makes it easier to edit a
nearby file with the wrong ownership or miss an existing seam. The remedy is a
small, evidence-backed reorganization, not a speculative rewrite.

## Scope

- Inventory the current top-level layout and the `src/riff` modules, naming the
  ownership of each area and identifying duplicate, compatibility, or obsolete
  paths before moving anything.
- Define a lightweight package map for the existing domains and cross-cutting
  seams, such as ingestion, evidence/provenance, capabilities/signals,
  profile/projects, worker/operations, reasoning, API/MCP, and persistence.
- Move or group modules only where the boundary improves discoverability and
  does not create artificial abstractions. Preserve stable CLI, API, MCP, and
  test-facing imports through deliberate compatibility exports when needed.
- Keep migrations, fixtures, reports, decisions, goals, and operator docs
  discoverable through consistent naming and index/navigation pages. A reader
  should be able to move from a goal to its implementation and verification
  artifacts without searching the entire repository.
- Add a concise repository map to the README or architecture documentation,
  including the canonical entry points for local setup, worker execution,
  tests, migrations, data-quality operations, and MCP/API operation.
- Add structural checks or focused tests for the intended package boundaries,
  import stability, and absence of accidental duplicate implementation paths.
- Record consequential moves and any intentionally retained flat area in an
  ADR or repository-organization note so later goals do not undo the decision.

## Non-goals

- Rewriting business logic, changing product behavior, or redesigning the
  database schema.
- Splitting Riff into services, plugins, or a deep enterprise-style package
  hierarchy without a demonstrated ownership problem.
- Renaming every file for aesthetic consistency when a stable, descriptive
  name already works.
- Deleting historical reports, goals, migrations, fixtures, or evidence merely
  to make the tree look smaller.
- Expanding the scope of G42/G48 or using organization work to claim that live
  dogfooding is complete.

## Acceptance criteria

- [ ] A repository map documents the purpose and owner of each top-level
  directory and the principal `src/riff` domains, with links to the relevant
  operator docs, goals, migrations, and tests.
- [ ] A before/after inventory identifies every moved, grouped, retained-flat,
  compatibility, and obsolete path; no implementation path is removed without
  an explicit replacement or retention reason.
- [ ] The Python package has a small, coherent domain structure where useful,
  with no catch-all module growth introduced by the reorganization.
- [ ] Existing CLI commands, API/MCP routes, migration discovery, and
  documented operator commands continue to work from a clean checkout.
- [ ] Existing test imports and supported application imports remain stable or
  have documented compatibility exports and deprecation notes.
- [ ] Focused structural tests/checks catch an accidental duplicate module,
  broken package import, or undocumented top-level implementation directory.
- [ ] The full verification suite passes with no behavior-only failures caused
  by the move; any unavoidable import-order or warning changes are documented.
- [ ] A connected human can locate the implementation and verification path
  for one current goal in under five minutes using only the repository map and
  linked docs (human acceptance).

## Deliverables

- Repository map and navigation updates in `README.md` and/or
  `docs/architecture.md`.
- A bounded package reorganization with compatibility exports where required.
- A repository-organization decision record or report containing the inventory,
  rationale, retained-flat exceptions, and migration notes.
- Structural/import checks and updated test paths/fixtures where files move.
- A verification report covering clean-checkout commands, focused checks, and
  the full test suite.

## Execution contract

Start with the inventory and map before moving files. Prefer the smallest move
that makes ownership clearer, and make each move mechanically reversible. Do
not combine this goal with feature work or silently alter runtime behavior.
After each bounded move, run import and focused tests; finish with the complete
suite and the documented clean-checkout smoke commands. If a proposed package
boundary is ambiguous, retain the flat path and record it as an explicit
follow-up rather than introducing a misleading abstraction.

