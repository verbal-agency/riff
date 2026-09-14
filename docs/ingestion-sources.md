# Initial ingestion-source plan

The reviewed source manifest is [config/ingestion_sources.json](../config/ingestion_sources.json). It is intentionally separate from the adapter-specific registries: the manifest records why a source is allowed and how it will be replayed, while G02–G04 configuration controls collection.

Current status:

- OpenAI News and Google AI Blog are source-owned feed candidates, pending a
  terms/retention review before live enablement.
- LangGraph and Temporal's Python SDK are explicit read-only GitHub scopes,
  pending the same review and credential/rate-limit check.
- `tests/fixtures/jobs/initial.json` is the permitted user-provided job input
  for offline dogfooding; no job-site scraping is implied.

Before enabling a pending source, record the review date, access method, storage
permission, request ceiling, and fixture capture. Never add tokens or passwords
to the manifest. Syndicated or reposted artifacts must retain their root source
and cannot count as independent confirmation.
