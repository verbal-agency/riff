# G06 — Separate and reversibly normalize capabilities and technologies

**Status:** Complete
**Depends on:** G05  
**Unlocks:** G07, G08  
**PRD references:** Sections 8.3, 11–12, 24.2–24.3

## Outcome

Riff maintains an inspectable capability graph that groups synonymous evidence candidates without collapsing distinct engineering abilities, while keeping concrete technologies and their relationships separate.

## User-visible proof

Given fixture phrases such as “checkpoint recovery,” “resumable agents,” and “workflow replay,” Riff can suggest or establish a relationship to durable agent execution, while “agent memory” remains distinct unless evidence justifies a relationship.

## Inputs

- Versioned G05 receipts containing candidate capability and technology terms.
- Labeled synonym, adjacency, framework-fragmentation, and over-merge cases.

## Scope

- Define capability, technology, concept, pattern, alias, relationship, and candidate-mapping records.
- Preserve candidate text and evidence provenance for every proposed mapping.
- Represent match confidence and status such as proposed, accepted, rejected, or superseded.
- Support merge, split, alias, and remap operations without rewriting source receipts or losing history.
- Seed only the minimal ontology needed by fixtures/dogfood; do not create a grand taxonomy upfront.
- Add normalization evaluation cases for synonym grouping, adjacent concepts, framework fragmentation, and over-merging.
- Expose application operations to inspect a capability and its concepts, patterns, technologies, evidence, and mapping rationale.

## Non-goals

- User proficiency, trend ranking, autonomous irreversible taxonomy edits, or a graph database.
- Equating a technology mention with evidence of the underlying capability.

## Required properties

- Capabilities are phrased as transferable abilities, not product names.
- Technologies can relate to multiple capabilities and vice versa.
- Low-confidence mappings remain candidates; they do not silently alter canonical counts.
- Every accepted relationship is reversible and auditable.
- Normalization is stable under repeated runs over unchanged receipts.

## Deliverables

- Relational capability/technology graph schema and migrations.
- Candidate-mapping and review/decision operations.
- Normalization implementation behind a replaceable deterministic/model-assisted boundary.
- Labeled positive, negative, ambiguous, merge, and split fixtures with evaluation report.

## Acceptance criteria

- [x] The checkpoint/replay/recovery fixture maps to a coherent durable-execution capability at the expected confidence/status.
- [x] Agent memory and workflow persistence are not automatically merged in the negative fixture.
- [x] Multiple frameworks implementing one bounded pattern strengthen one capability candidate without becoming separate capability nodes solely because names differ.
- [x] A reviewer can accept, reject, remap, split, and undo a mapping while all original receipt provenance remains intact.
- [x] Technology-to-capability relationships are many-to-many and queryable in both directions.
- [x] Reprocessing unchanged candidates does not create duplicate nodes or relationships.
- [x] The evaluation report presents under-merging and over-merging separately and includes the exact failing cases.

## Verification evidence

Demonstrate the PRD's durable-execution and agent-memory examples plus at least one ambiguous technology/capability fixture. Show graph state before, after, and after undoing a mapping decision.

## Implementation latitude

Relational adjacency tables are sufficient. Semantic retrieval may use Postgres/pgvector only if justified by observed normalization needs; deterministic aliases and constrained model reasoning should be considered first.

## Execution contract (satisfied in this cycle)

### Expected implementation surface

Extend `src/riff` with capability and technology domain records, relational
candidate mappings, reversible review operations, and a deterministic
normalization service over G05 receipts. Add the next numbered migration,
focused tests under `tests/`, labeled fixtures under
`tests/fixtures/capabilities/`, and a field-level evaluation command/report.
Document the operator inspection and review path in `README.md` and
`docs/architecture.md`, and add an ADR for any new persistence or normalization
invariant. Equivalent paths are acceptable when the completion report names
them.

### Canonical domain and persistence contract

Use stable IDs and preserve the originating receipt candidate text and span
provenance. Keep technologies separate from transferable capabilities.

| Concept | Required fields | Invariants |
|---|---|---|
| Capability | `capability_id`, `name`, `status`, `created_at` | Names describe transferable abilities, not products or vendors. |
| Technology | `technology_id`, `name`, `kind`, `status` | A technology may relate to many capabilities and is never evidence of proficiency by itself. |
| Candidate mapping | `mapping_id`, `receipt_id`, `candidate_text`, `entity_type`, `entity_id`, `confidence`, `status`, `rationale` | Original receipt and candidate text remain immutable; proposed/accepted/rejected/superseded are explicit states. |
| Relationship | `relationship_id`, `capability_id`, `technology_id`, `relationship_type`, `confidence`, `status`, `mapping_id` | Many-to-many in both directions; every accepted edge is reversible and auditable. |
| Review decision | `decision_id`, `mapping_id`, `action`, `actor`, `created_at`, `reason` | Accept, reject, remap, split, and undo append history rather than rewriting receipts. |

### Deterministic behavior matrix

| Input condition | Required result |
|---|---|
| “checkpoint recovery”, “resumable agents”, and “workflow replay” | Map to one durable-execution capability at the expected confidence/status. |
| “agent memory” versus workflow persistence | Remain distinct in the negative fixture unless an explicit reviewed mapping exists. |
| Several frameworks expressing one bounded pattern | Strengthen one capability candidate; do not create framework-named capability nodes solely from aliases. |
| Accept, reject, remap, split, then undo | Expose the current graph and complete decision history while preserving receipt provenance. |
| Repeated normalization of unchanged receipts | No duplicate nodes, mappings, or relationships. |
| Ambiguous or low-confidence candidate | Keep it proposed/uncertain; do not alter canonical counts silently. |

### Authority and side-effect boundaries

This goal may read local G05 receipts and mutate only capability/technology and
review state. It must not rewrite raw evidence or receipts, infer user
proficiency, rank trends, construct Riffs, publish output, or call an external
provider directly. Any model-assisted normalization must be behind an injected,
replaceable boundary; normal tests use deterministic fakes or recorded
responses and no paid API or live network.

### Offline fixtures and state controls

Provide positive synonym, adjacent-concept, framework-fragmentation,
over-merge, ambiguous, merge, split, remap, and undo fixtures. Verify mapping
confidence/status, bidirectional technology relationships, idempotent repeated
runs, provenance retention, and the exact before/after/undo graph state. Keep
per-item and total-call limits explicit.

### Criterion-to-test/artifact map

| G06 criterion | Required proof artifact |
|---|---|
| Durable-execution mapping | Positive normalization fixture/test |
| Agent-memory separation | Negative fixture/test |
| Framework fragmentation | Multi-framework fixture/test |
| Reversible review operations | Review lifecycle integration test |
| Technology many-to-many | Bidirectional query test |
| Idempotent reprocessing | Repeated-run test |
| Under/over-merging report | Evaluation command with exact failing cases |

## Cycle verification (2026-09-14)

- `.venv/bin/python -m pytest` — **26 passed, 38 skipped** (offline suite).
- Isolated Postgres with migration `007_capability_model.sql`, then
  `.venv/bin/python -m pytest -m postgres` — **38 passed**.
- `.venv/bin/python -m riff capability evaluate --file tests/fixtures/capabilities/normalization.json`
  — six cases; under-merging and over-merging are reported separately with
  exact failing case IDs and missing/extra groups.
- `git diff --check` and `.venv/bin/python -m compileall -q src tests` pass.
- Integration tests demonstrate durable-execution alias grouping, negative
  separation, framework fragmentation, reversible review lifecycle,
  many-to-many technology links, provenance retention, and cached reruns.
