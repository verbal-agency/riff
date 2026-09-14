# Technical-writing ingestion sources

The reviewed source plan lives in
[`config/ingestion_sources.json`](../config/ingestion_sources.json). The
collector registry lives in
[`config/technical_sources.json`](../config/technical_sources.json). The plan
records why a source is allowed and how it will be replayed; the registry is the
minimal syncable configuration consumed by `riff source sync`.

## G16 RSS/Atom inventory

All new feeds are disabled until the operator completes the terms and retention
review. `PENDING_REVIEW` is an explicit state, not permission to fetch live.

| Source | Endpoint | Root/class | Notes |
|---|---|---|---|
| OpenAI News | `https://openai.com/news/rss.xml` | `openai.com` / lab announcement | Research, releases, safety, company news |
| Google DeepMind Blog | `https://deepmind.google/blog/rss.xml` | `deepmind.google` / lab research | Research, models, safety |
| Google Research Blog | `https://research.google/blog/rss/` | `research.google` / lab research | Research and systems engineering |
| Hugging Face Blog | `https://huggingface.co/blog/feed.xml` | `huggingface.co` / open-source ecosystem | Supports GUID permalink fallback |
| arXiv cs.AI | `https://rss.arxiv.org/rss/cs.AI` | `arxiv.org` / research papers | Paper versions share one lineage |
| arXiv cs.LG | `https://rss.arxiv.org/rss/cs.LG` | `arxiv.org` / research papers | Paper versions share one lineage |
| arXiv cs.CL | `https://rss.arxiv.org/rss/cs.CL` | `arxiv.org` / research papers | Paper versions share one lineage |
| arXiv stat.ML | `https://rss.arxiv.org/rss/stat.ML` | `arxiv.org` / research papers | Paper versions share one lineage |
| Berkeley AI Research | `https://bair.berkeley.edu/blog/feed.xml` | `bair.berkeley.edu` / university research | Research and engineering |
| MIT News — AI | `https://news.mit.edu/topic/mitartificial-intelligence2-rss.xml` | `news.mit.edu` / university research | AI-tagged institutional research |
| AWS Machine Learning | `https://aws.amazon.com/blogs/machine-learning/feed/` | `aws.amazon.com` / production engineering | Engineering and case studies |
| OpenTelemetry | `https://opentelemetry.io/blog/index.xml` | `opentelemetry.io` / open-source standards | Releases, standards, engineering |
| NIST Taking Measure | `https://www.nist.gov/blogs/taking-measure/rss.xml` | `nist.gov` / standards and policy | Measurement and trustworthy technology |

The previous Google AI broad-tag entry remains a separately marked candidate;
it is intentionally not part of the initial enabled set because broad vendor
tags can contain unrelated consumer material. Tier 2 candidates such as Mistral,
The Gradient, TechCrunch AI, IEEE Spectrum, O'Reilly Radar, NVIDIA, Microsoft
Research, and Databricks remain `PENDING_REVIEW` until their current endpoint,
content quality, and retention terms are verified.

## Enablement checklist

For each source, the operator should:

1. Confirm the feed responds successfully and has a non-empty RSS or Atom
   document. Record the check date and final URL.
2. Confirm the source's terms and permitted retention mode. Keep the source
   disabled if this is unresolved.
3. Capture one representative response as a fixture, plus malformed, duplicate,
   and unchanged-rerun cases where the feed has a known quirk.
4. Verify canonical URL, GUID/native ID, title, author, publication date, and
   source root extraction. Hugging Face entries may require the GUID as the
   canonical article link.
5. Set the request bound, cache behavior, retry-after handling, maximum body
   size, and fallback state in the registry.
6. Run `uv run riff source sync --registry config/technical_sources.json` only
   after the review. Enable individual sources explicitly with
   `uv run riff source enable --source-id <source-id>`.

Engineer-authored feeds use the separate
`config/engineer_rss_selections.json` bridge. Validate and preview selections
with `riff source engineer-rss`; only a selection with confirmed permission,
reviewer/date, and `collection_decision=ENABLE` may be projected into this
registry. The projection preserves engineer identity and correlation metadata
for the existing RSS runner and never auto-enables a pending roster entry.

## Correlation and retention rules

- Canonical URL and native ID deduplication happen within a source; content
  hashes identify unchanged versus revised versions.
- Syndicated copies retain their root source and do not count as independent
  confirmation. Google Research, Google DeepMind, and Google AI are correlated
  under their organizational roots.
- arXiv revisions (`v1`, `v2`, and later) are versions of one paper, not new
  independent signals.
- Feed volume, publication frequency, stars, or popularity are context only and
  never constitute a capability signal by themselves.
- When full article retention is not permitted, retain the canonical URL,
  metadata, and snapshot reference only.
- Tests use recorded fixtures and never require a live network or credential.

## Fixture/replay matrix

| Case | Expected result |
|---|---|
| RSS 2.0 item with GUID/link | Store one normalized evidence item |
| Atom entry with relative alternate link | Resolve against final feed URL |
| GUID-only permalink | Use GUID as canonical article link when marked permalink |
| Missing link/date/title | Quarantine or use bounded fallback without corrupting cursor |
| Wrong feed MIME type | Parse only when the body is valid XML and the source is explicitly allowed |
| Duplicate syndicated URL | Correlate/deduplicate; do not increase independence |
| Same feed rerun | Store zero duplicate evidence versions and preserve cursor |
| 429/5xx response | Record retryable failure and preserve prior cursor |
| 4xx/invalid XML/oversized body | Record permanent failure and keep source reviewable |
