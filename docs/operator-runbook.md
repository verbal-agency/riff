# Riff operator runbook

## Simplest way to use Riff locally

Two commands, each in its own terminal, from the repository root. Docker
Desktop must be installed; both scripts read `.env` themselves.

```sh
./scripts/riff-digest
```

Starts Docker and Postgres if needed, fetches every source in
`config/digest_feeds.json`, and writes today's digest to `digests/<date>.md`.
It needs `OPENAI_API_KEY` in `.env`. Run it once a day, or install the daily
07:30 job with `./scripts/riff-schedule` (`--remove` undoes it).

```sh
./scripts/riff-up
```

Starts the API and stays in the foreground. Then open
<http://127.0.0.1:8000/riff> to read the digest and riff with it. Stop it with
`Ctrl-C`.

What to edit:

- `config/profile.md` — who the digest is written for.
- `config/digest_feeds.json` — RSS feeds, index pages for sites without feeds,
  and GitHub pull requests to watch.

If something looks wrong:

- No digest on the page: run `./scripts/riff-digest` first.
- `digest error: an OpenAI API key is required`: add `OPENAI_API_KEY` to `.env`.
- A source is missing from the digest: the JSON printed by `riff-digest` lists
  per-source failures under `collection.failures`.
- `address already in use`: the API is already running; just open the page.

### Riffing from an MCP client

The same API serves MCP at `http://127.0.0.1:8000/mcp` (Streamable HTTP), so a
client such as Claude or ChatGPT can riff with the digest directly. With
`./scripts/riff-up` running, add it to Claude Code with:

```sh
claude mcp add --transport http riff http://127.0.0.1:8000/mcp
```

A client that is not on this machine needs a public HTTPS address and the
hostname allowlisted; see "Connect ChatGPT Developer Mode through MCP" below.

The digest tools call no model. The connected model does the riffing; Riff
supplies the material and keeps the record:

- `digest_latest`, `riff_profile` — what to riff on, and for whom.
- `article_search`, `article_wander`, `article_read` — real articles, notes and
  watched pull requests from the store.
- `riff_threads`, `riff_thread` — read saved threads.
- `riff_record`, `riff_sketch` — save an exchange or a sketch. Saved threads
  appear on the `/riff` page and steer the next digest.

`/mcp` also still serves the older worker tools described below.

Everything from here down documents the original worker pipeline (fixtures,
replay, provider smokes, ChatGPT MCP). You do not need it for the digest.

## Start the local stack

From the repository root, run this one command:

```sh
./scripts/riff-up
```

It starts Postgres with Docker Compose, applies migrations, checks worker readiness, and starts the API in the foreground. Stop the API with `Ctrl-C`; Postgres remains running for the next run. This command does not start ngrok or configure a ChatGPT connector because the public tunnel hostname changes and must be added to the MCP host allowlist.

This is the shortest path from a fresh local checkout to a useful Riff run.
Commands that keep a server or tunnel alive belong in their own terminal. Riff
does not source `.env` automatically, so source it in every terminal that runs
Riff commands.

## 1. Start Postgres and verify the local database

```sh
uv sync --all-groups
[ -f .env ] || cp .env.example .env  # first run only; never commit .env
docker compose up -d postgres
set -a; source .env; set +a
uv run riff migrate
uv run riff worker readiness
```

Expected result: readiness returns JSON. It may report `EMPTY`, `DISABLED`, or
`REVIEW_REQUIRED`; that is a data-readiness result, not a server failure.

## 2. Run a no-cost local smoke

This path uses only committed fixture data and a deterministic provider. It is
the first test to run after setup:

```sh
set -a; source .env; set +a
uv run riff worker --fixture tests/fixtures/riffs/daily_inputs.json --date 2026-10-27 --policy-version local-fixture-20261027 --resume
```

For the live-shaped reasoning path without a model call, replay persisted LIVE
evidence through the recorded provider fixture:

```sh
set -a; source .env; set +a
RIFF_REASONING_PROVIDER=recorded \
RIFF_REASONING_FIXTURE=tests/fixtures/reasoning/g42-recorded.json \
uv run riff worker --replay-live --date 2026-10-27 \
  --policy-version g42-recorded-20261027 --resume
```

Inspect the JSON report fields `status`, `outcome_classification`, `stages`,
`reasoning`, `provider_gate`, and `publication_gate`. `EMPTY` or
`VALID_EMPTY` is a successful bounded outcome when the evidence does not meet
the publication threshold; it is not a fabricated recommendation.

## 3. Run the bounded real-provider smoke

Only do this when you intentionally want to spend one model call. Put the key
in `.env` as `OPENAI_API_KEY` (or `RIFF_REASONING_API_KEY`); never paste it into
the command or commit it.

```sh
set -a; source .env; set +a
RIFF_REASONING_PROVIDER=openai \
RIFF_REASONING_MODEL=gpt-4o-mini \
RIFF_REASONING_MAX_CALLS=1 \
RIFF_REASONING_MAX_COST_USD=0.50 \
uv run riff worker --replay-live --limit 20 --date 2026-10-27 \
  --policy-version riff-g42-openai-smoke-20261027 --resume
```

The worker may still return `EMPTY` without calling the provider when the live
evidence gate is insufficient. That is intentional. The report tells you
whether `reasoning.calls` is `0` or `1`, plus model, context-policy version,
input fingerprint, token estimates, and cost estimate. Capture a report for
later inspection with `| tee /tmp/riff-g42-run.json`.

## 4. Start the local API

Use a separate terminal because the API stays in the foreground:

```sh
set -a; source .env; set +a
uv run riff migrate
uv run riff api --host 127.0.0.1 --port 8000
```

In another terminal:

```sh
curl -fsS http://127.0.0.1:8000/health/live
curl -fsS http://127.0.0.1:8000/health/ready
curl -fsS http://127.0.0.1:8000/adapter/tools
```

To inspect a worker report, copy its `run_id` from the worker JSON and run:

```sh
curl -fsS http://127.0.0.1:8000/operations/<run_id>
```

## 5. Connect ChatGPT Developer Mode through MCP

Riff uses Streamable HTTP at `/mcp`. It does **not** use `/sse`.

Start the tunnel in a separate terminal:

```sh
ngrok http 8000
```

Copy the HTTPS hostname from ngrok. Stop the API with `Ctrl-C`, then restart
it with the hostname allowlisted. Replace the example hostname with the current
one; ngrok URLs can change each time:

```sh
set -a; source .env; set +a
export RIFF_MCP_ALLOWED_HOSTS='YOUR-NGROK-HOST.ngrok-free.app'
export RIFF_MCP_ALLOWED_ORIGINS='https://chatgpt.com'
uv run riff api --host 127.0.0.1 --port 8000
```

Verify the tunnel before opening ChatGPT:

```sh
curl -fsS https://YOUR-NGROK-HOST.ngrok-free.app/health/live
```

In ChatGPT Developer Mode, add the complete server URL:

```text
https://YOUR-NGROK-HOST.ngrok-free.app/mcp
```

Refresh the app after changing the tunnel URL or tool metadata. Then ask the
connected Riff app:

> Read the latest daily result and the worker operation report I provide. Summarize the recommendation, cited receipts, uncertainty/counterevidence, provider/model telemetry, and whether the result was published or valid-empty. Do not mutate anything.

For a specific worker report, include the `run_id` from the terminal output. The
MCP app should call `operation_report` for that ID and `daily_riffs` for the
associated date. Keep the first connected check read-only.

## 6. Inspect source health before blaming reasoning

```sh
set -a; source .env; set +a
uv run riff data-quality live-sources --limit 50
uv run riff data-quality audit --limit 50
uv run riff worker readiness
```

If the result is `EMPTY`, check whether there are trusted LIVE receipts and at
least two independent provenance roots. Do not enable or delete sources just to
force a recommendation.

## Troubleshooting

- `RIFF_DATABASE_URL is required`: run `set -a; source .env; set +a` in that
  terminal, then retry.
- `address already in use`: keep the existing API, or choose another port and
  use the same port in `ngrok http <port>`.
- `/sse` returns 404 or 406: that route is not Riff's transport. Use `/mcp` and
  the Streamable HTTP connector.
- MCP returns `421 Misdirected Request`: add the current ngrok hostname to
  `RIFF_MCP_ALLOWED_HOSTS`, restart the API, and reconnect the `/mcp` URL.
- ngrok returns `404`: confirm the API is listening on the port ngrok forwards
  to and that ChatGPT uses the full `/mcp` suffix.
- No daily Riff is present: run the worker and inspect its report; a valid
  `EMPTY` result means the evidence gate held, not that the process crashed.
- A terminal command appears stuck: the API, ngrok, and worker are foreground
  processes. Open another terminal for the next command; do not start a second
  API on the same port.
