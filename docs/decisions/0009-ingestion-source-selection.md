# ADR 0009: initial concrete ingestion-source plan

## Context

G09a made the daily Riff path runnable from a local fixture, but dogfooding
needs a reproducible source set with known access and retention boundaries. The
source registry was previously empty, so a later operator could accidentally
substitute popularity-driven or non-permitted inputs.

## Decision

The initial plan names two source-owned technical-writing feeds (OpenAI News
and Google AI Blog), two explicit public GitHub repository scopes (LangGraph and
the Temporal Python SDK), and a user-provided, schema-versioned job export. The
writing and GitHub entries remain `PENDING_REVIEW` until their live retention
terms are checked; they may not be enabled implicitly. The job fixture is
`USER_PROVIDED` and is the permitted offline path. Every entry carries a bounded
request policy, expected artifacts, identity fields, fixture plan, retention
mode, fallback, and duplicate/syndication policy.

## Consequences

Dogfood inputs are explicit and reviewable, while unavailable permissions remain
visible instead of silently replaced. The plan supports the existing G02–G04
adapters without embedding credentials or committing to scraping. A dated
operator review is required before enabling any pending live source.

Source references: [OpenAI News](https://openai.com/news/), [Google AI](https://blog.google/innovation-and-ai/technology/ai/), [LangGraph](https://github.com/langchain-ai/langgraph), and [Temporal Python SDK](https://github.com/temporalio/sdk-python).
