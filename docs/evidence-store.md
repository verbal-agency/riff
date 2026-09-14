# G01 evidence-store contract

G01 stores the source identity and raw evidence history needed for every later argument. Product tables are in migration `002_evidence_store.sql`; IDs are application-generated text UUIDs so the schema requires no Postgres extensions.

## Identity and immutability

`sources` identify a configured evidence origin. A `source_item` identifies one provider-native artifact. When a provider supplies `native_id`, that ID is the stronger identity and two distinct native IDs may share a normalized URL. URL-only items are unique within a source. URL normalization lowercases scheme/host, removes default ports and fragments, removes common tracking parameters, and sorts the remaining query parameters without removing meaningful values.

`evidence_versions` are immutable snapshots keyed by `(source_item_id, content_hash)`. Inline content is hashed with SHA-256; snapshot-backed submissions must provide a validated hash. A changed hash creates a new version and a `VERSION_OF` edge. `retrievals` record every successful retrieval attempt, including duplicate observations, without creating independent evidence versions.

## Provenance

`provenance_edges` use typed foreign-key columns rather than a polymorphic unvalidated ID pair. `DISCOVERED_THROUGH` and `CONTENT_EQUIVALENT` connect source items; `VERSION_OF` connects evidence versions. Database checks reject unknown relationships and edges with the wrong entity kind or missing target. A discovery page therefore remains visible while its linked original artifact remains the root evidence.

## Retrieval and privacy

Repository reads return metadata and stable IDs by default. Raw inline content is included only when `include_raw=True`; snapshot references remain available for explicit retrieval. This goal has no network or model side effects, and routine logs contain event metadata rather than payloads.

