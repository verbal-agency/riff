"""Read the real feeds, take model notes on each article, and write an idea digest.

This is the short path from "articles on the internet" to "things worth
building".  It reuses the existing feed runner and evidence store, then makes
two kinds of model call:

1. one small call per new article, which reads the full text and records what
   it actually says (cached in ``article_notes``);
2. one larger call over every note in the window plus the reader's profile,
   which proposes ideas and must cite the articles each idea rests on.

Citations are checked in code: an idea that cites nothing real is dropped, and
an idea resting on a single source is kept but labelled as such.
"""

from __future__ import annotations

import html
import json
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlsplit

import httpx
from psycopg.types.json import Jsonb

from .db import connection
from .evidence import SourceType
from .evidence_repository import EvidenceRepository
from .ingestion import HttpFeedFetcher
from .ingestion_repository import IngestionRepository
from .writing_ingestion import WritingIngestionRunner

DEFAULT_NOTE_MODEL = "gpt-5.4-mini"
DEFAULT_IDEA_MODEL = "gpt-5.5"
DEFAULT_MAX_ITEMS_PER_FEED = 10
MAX_ARTICLES = 120
MAX_ARTICLE_CHARS = 14_000
FULL_TEXT_BELOW_CHARS = 1_500
USER_AGENT = "Riff/0.1 personal feed reader"
# New evidence from a source that is not marked LIVE is stored as QUARANTINED,
# so only synthetic rows are excluded here; ensure_sources marks feeds LIVE.
EXCLUDED_ORIGINS = ("TEST", "FIXTURE")


class DigestError(RuntimeError):
    """The digest could not be produced."""


@dataclass(frozen=True, slots=True)
class Feed:
    source_id: str
    name: str
    endpoint: str
    max_items: int = DEFAULT_MAX_ITEMS_PER_FEED


@dataclass(frozen=True, slots=True)
class Article:
    evidence_id: str
    source_id: str
    source_name: str
    title: str
    url: str
    published_at: datetime
    text: str


@dataclass(slots=True)
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def to_dict(self) -> dict[str, int]:
        return {"calls": self.calls, "input_tokens": self.input_tokens, "output_tokens": self.output_tokens}


JsonCall = Callable[[str, str, str, str, Mapping[str, Any], int], Mapping[str, Any]]


# --------------------------------------------------------------------------
# Feeds and collection
# --------------------------------------------------------------------------

def load_feeds(path: str | Path) -> list[Feed]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("feeds"), list):
        raise DigestError(f"{path} must contain schema_version 1 and a feeds list")
    feeds = []
    for entry in payload["feeds"]:
        feeds.append(Feed(str(entry["source_id"]), str(entry["name"]), str(entry["endpoint"]), int(entry.get("max_items", DEFAULT_MAX_ITEMS_PER_FEED))))
    if not feeds:
        raise DigestError(f"{path} lists no feeds")
    return feeds


def ensure_sources(database_url: str, feeds: Sequence[Feed]) -> None:
    """Make sure every digest feed exists and is enabled, keeping existing metadata."""

    ingestion = IngestionRepository(database_url)
    evidence = EvidenceRepository(database_url)
    with connection(database_url) as conn:
        known = {str(row[0]) for row in conn.execute("SELECT source_id FROM sources WHERE source_id = ANY(%s)", ([f.source_id for f in feeds],)).fetchall()}
        configured = {str(row[0]): (str(row[1]), bool(row[2])) for row in conn.execute("SELECT source_id, endpoint, enabled FROM ingestion_source_configs WHERE source_id = ANY(%s)", ([f.source_id for f in feeds],)).fetchall()}
    for feed in feeds:
        if feed.source_id not in known:
            evidence.create_source(SourceType.TECHNICAL_WRITING, feed.name, source_id=feed.source_id)
        if feed.source_id not in configured:
            ingestion.configure_source(feed.source_id, feed.endpoint)
        elif configured[feed.source_id][0] != feed.endpoint:
            with connection(database_url) as conn:
                conn.execute("UPDATE ingestion_source_configs SET endpoint = %s, enabled = TRUE WHERE source_id = %s", (feed.endpoint, feed.source_id))
                conn.execute("UPDATE sources SET enabled = TRUE WHERE source_id = %s", (feed.source_id,))
        elif not configured[feed.source_id][1] or feed.source_id in known:
            ingestion.set_source_enabled(feed.source_id, True)
    # Listing a feed in the digest file is the approval: mark it LIVE so new
    # articles are not quarantined, and give it a root for provenance.
    with connection(database_url) as conn:
        for feed in feeds:
            parts = urlsplit(feed.endpoint)
            conn.execute(
                """UPDATE sources
                   SET data_origin = 'LIVE', origin_owner = COALESCE(origin_owner, 'digest-feeds'),
                       canonical_root = COALESCE(canonical_root, %s)
                   WHERE source_id = %s AND data_origin = 'UNCLASSIFIED'""",
                (f"{parts.scheme}://{parts.netloc}/", feed.source_id),
            )


def collect(database_url: str, feeds: Sequence[Feed], fetcher=None) -> dict[str, Any]:
    ensure_sources(database_url, feeds)
    runner = WritingIngestionRunner(IngestionRepository(database_url), EvidenceRepository(database_url), fetcher or HttpFeedFetcher())
    summary = runner.run(source_ids=[feed.source_id for feed in feeds], policy_version="digest-v1")
    with connection(database_url) as conn:
        failures = conn.execute(
            "SELECT source_id, error_code, count(*) FROM collection_item_results WHERE run_id = %s AND error_code IS NOT NULL GROUP BY 1, 2 ORDER BY 1",
            (summary.run_id,),
        ).fetchall()
    return {
        "run_id": summary.run_id,
        "status": str(getattr(summary.status, "value", summary.status)),
        "stored": summary.stored,
        "duplicates": summary.duplicates,
        "failed": summary.failed_transient + summary.failed_permanent,
        "failures": [{"source_id": str(a), "error": str(b), "count": int(c)} for a, b, c in failures],
    }


class _TextExtractor(HTMLParser):
    _BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "pre", "tr", "blockquote", "section"}
    _SKIP = {"script", "style", "svg", "noscript"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip += 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip:
            self._skip -= 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(raw: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(raw)
        parser.close()
        text = "".join(parser.parts)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def fetch_article_text(url: str, *, timeout_seconds: float = 15.0, max_bytes: int = 3_000_000) -> str:
    """Fetch the article page for feeds that only publish a one-line summary.

    Sites that refuse automated readers are respected: the caller falls back
    to whatever the feed itself provided.
    """

    try:
        response = httpx.get(url, timeout=timeout_seconds, follow_redirects=True, headers={"User-Agent": USER_AGENT})
    except httpx.HTTPError:
        return ""
    if response.status_code >= 400 or len(response.content) > max_bytes or "html" not in response.headers.get("content-type", "html"):
        return ""
    page = response.text
    for tag in ("article", "main"):
        blocks = re.findall(rf"<{tag}\b[^>]*>(.*?)</{tag}>", page, flags=re.S | re.I)
        if blocks:
            page = max(blocks, key=len)
            break
    return html_to_text(page)


def window_articles(database_url: str, feeds: Sequence[Feed], since: datetime, until: datetime) -> list[Article]:
    """Newest version of each article published in the window, capped per feed."""

    with connection(database_url) as conn:
        rows = conn.execute(
            """SELECT DISTINCT ON (si.source_item_id)
                      e.evidence_id, si.source_id, s.name, si.title, si.canonical_url,
                      COALESCE(e.published_at, e.retrieved_at), e.raw_content
               FROM evidence_versions e
               JOIN source_items si ON si.source_item_id = e.source_item_id
               JOIN sources s ON s.source_id = si.source_id
               WHERE si.source_id = ANY(%s) AND e.raw_content IS NOT NULL
                 AND COALESCE(e.published_at, e.retrieved_at) >= %s
                 AND COALESCE(e.published_at, e.retrieved_at) <= %s
                 AND e.data_origin <> ALL(%s) AND si.data_origin <> ALL(%s)
               ORDER BY si.source_item_id, e.retrieved_at DESC""",
            ([f.source_id for f in feeds], since, until, list(EXCLUDED_ORIGINS), list(EXCLUDED_ORIGINS)),
        ).fetchall()
    caps = {feed.source_id: feed.max_items for feed in feeds}
    names = {feed.source_id: feed.name for feed in feeds}
    by_source: dict[str, list[Article]] = {}
    seen_urls: set[str] = set()
    for evidence_id, source_id, source_name, title, url, at, raw in sorted(rows, key=lambda row: row[5], reverse=True):
        url = str(url)
        text = html_to_text(str(raw))
        if url in seen_urls or len(text) < 20:
            continue
        seen_urls.add(url)
        bucket = by_source.setdefault(str(source_id), [])
        if len(bucket) >= caps.get(str(source_id), DEFAULT_MAX_ITEMS_PER_FEED):
            continue
        bucket.append(Article(str(evidence_id), str(source_id), names.get(str(source_id), str(source_name)), str(title or url), url, at, text))
    articles = sorted((item for bucket in by_source.values() for item in bucket), key=lambda item: item.published_at, reverse=True)
    return articles[:MAX_ARTICLES]


# --------------------------------------------------------------------------
# Model client
# --------------------------------------------------------------------------

class OpenAIJsonClient:
    """Minimal Responses API client that returns schema-constrained JSON."""

    def __init__(self, api_key: str, *, base_url: str = "https://api.openai.com/v1", timeout_seconds: float = 240.0):
        if not (api_key or "").strip():
            raise DigestError("an OpenAI API key is required (OPENAI_API_KEY or RIFF_REASONING_API_KEY)")
        self._headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self.usage = Usage()

    def __call__(self, model: str, system: str, user: str, schema_name: str, schema: Mapping[str, Any], max_output_tokens: int) -> Mapping[str, Any]:
        payload = {
            "model": model,
            "store": False,
            "max_output_tokens": max_output_tokens,
            "input": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "text": {"format": {"type": "json_schema", "name": schema_name, "strict": True, "schema": schema}},
        }
        last_error = "unknown"
        for attempt in range(3):
            try:
                response = httpx.post(f"{self._base_url}/responses", headers=self._headers, json=payload, timeout=self._timeout)
            except httpx.HTTPError as exc:
                last_error = type(exc).__name__
                time.sleep(2 * (attempt + 1))
                continue
            if response.status_code == 429 or response.status_code >= 500:
                last_error = f"HTTP {response.status_code}"
                time.sleep(4 * (attempt + 1))
                continue
            if response.status_code >= 400:
                raise DigestError(f"model request rejected ({response.status_code}): {_error_message(response)}")
            body = response.json()
            usage = body.get("usage") or {}
            self.usage.calls += 1
            self.usage.input_tokens += int(usage.get("input_tokens", 0))
            self.usage.output_tokens += int(usage.get("output_tokens", 0))
            if body.get("status") == "incomplete":
                raise DigestError(f"model response incomplete: {(body.get('incomplete_details') or {}).get('reason', 'unknown')}")
            text = _output_text(body)
            if not text:
                raise DigestError("model returned no text")
            return json.loads(text)
        raise DigestError(f"model request failed after retries: {last_error}")


def _error_message(response: httpx.Response) -> str:
    try:
        return str((response.json().get("error") or {}).get("message", ""))[:300]
    except ValueError:
        return response.text[:300]


def _output_text(body: Mapping[str, Any]) -> str | None:
    if isinstance(body.get("output_text"), str):
        return body["output_text"]
    for item in body.get("output", []):
        for content in (item.get("content") or []) if isinstance(item, Mapping) else []:
            if isinstance(content, Mapping) and content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return content["text"]
    return None


def _object(properties: Mapping[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": dict(properties), "required": list(properties), "additionalProperties": False}


_STRINGS = {"type": "array", "items": {"type": "string"}}

NOTE_SCHEMA = _object({
    "summary": {"type": "string"},
    "whats_new": {"type": "string"},
    "claims": _STRINGS,
    "techniques": _STRINGS,
    "build_hooks": _STRINGS,
    "substance": {"type": "integer"},
})

NOTE_SYSTEM = (
    "You take reading notes for a working AI engineer. Read the article and record only what it actually says. "
    "summary: 2-3 plain sentences. whats_new: the single thing here that was not common knowledge before, or 'nothing new'. "
    "claims: up to 5 specific, checkable claims or results, with numbers when given. "
    "techniques: named methods, tools, patterns or architectures the article uses or describes. "
    "build_hooks: up to 3 concrete things a practitioner could build, test or measure because of this article. "
    "substance: 0 = announcement, link or personal note with no technical content; 1 = light; 2 = solid; 3 = unusually deep or novel. "
    "Do not pad. Empty lists are fine."
)

IDEAS_SCHEMA = _object({
    "collisions": {"type": "array", "items": _object({"title": {"type": "string"}, "what_they_share": {"type": "string"}, "question": {"type": "string"}, "sources": _STRINGS})},
    "themes": {"type": "array", "items": _object({"title": {"type": "string"}, "what_is_happening": {"type": "string"}, "sources": _STRINGS})},
    "ideas": {"type": "array", "items": _object({
        "title": {"type": "string"},
        "pitch": {"type": "string"},
        "connection": {"type": "string"},
        "why_now": {"type": "string"},
        "why_you": {"type": "string"},
        "first_step": {"type": "string"},
        "artifact": {"type": "string"},
        "biggest_risk": {"type": "string"},
        "sources": _STRINGS,
    })},
})

IDEAS_SYSTEM = (
    "You are a curious, well-read collaborator with a taste for odd juxtapositions. You are given reading notes on recent technical writing, "
    "each with a key like A7, and a note from the person you are writing for. Your job is to let the material collide and see what new thing falls out.\n\n"
    "Work in three passes.\n"
    "collisions: 3-5 pairings of notes that have no obvious business together. For each, say what the two have in common underneath, and ask the "
    "question the pairing raises. These do not have to be useful. They have to be true to the notes and not something either author would have said.\n"
    "ideas: 4-6 things to build. Prefer ideas that grew out of a collision. A good idea either attacks a problem that was out of reach until "
    "something in the notes changed, or makes something strange that would actually run. It names a specific thing that could exist, and rests on a "
    "mechanism or result stated in the notes. A bad idea: 'learn X', 'explore Y', a restatement of one article, a benchmark or scorecard reached for "
    "by default, or anything that would have been equally possible a year ago.\n"
    "themes: 2-4 places where several sources are circling the same shift.\n\n"
    "Idea fields: pitch = what to build, in two or three concrete sentences. connection = which notes combine and what the combination reveals. "
    "why_now = what was not possible before and what in the notes makes it possible. why_you = why this would be interesting to this reader, using only what their note says "
    "(never attribute tastes or history it does not state), or say plainly if it is a stretch. first_step = something doable in one sitting. artifact = what exists at the end. "
    "biggest_risk = the most likely reason this goes nowhere. "
    "sources = the note keys it rests on; cite only keys you were given, and only ones that really support it.\n\n"
    "Be playful in what you connect and exact in what you claim: never invent a result, a number or a source. Plain language, no hype. "
    "If the notes are thin, return fewer items rather than weak ones. Do not repeat ideas listed as already proposed. "
    "threads_pulled lists conversations the reader chose to wander into recently and what they said there: lean toward what they kept pulling on "
    "and carry it somewhere new, without repeating it back to them."
)


# --------------------------------------------------------------------------
# Notes and synthesis
# --------------------------------------------------------------------------

def take_notes(database_url: str, articles: Sequence[Article], call: JsonCall, model: str, *, workers: int = 6, fetch_text: Callable[[str], str] = fetch_article_text) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Return a note per evidence id, calling the model only for uncached articles."""

    ids = [article.evidence_id for article in articles]
    with connection(database_url) as conn:
        notes = {str(row[0]): dict(row[1]) for row in conn.execute("SELECT evidence_id, note FROM article_notes WHERE evidence_id = ANY(%s)", (ids,)).fetchall()}
    pending = [article for article in articles if article.evidence_id not in notes]
    errors: list[str] = []

    def one(article: Article) -> tuple[Article, Mapping[str, Any] | None, str | None]:
        text = article.text
        if len(text) < FULL_TEXT_BELOW_CHARS:
            fetched = fetch_text(article.url)
            if len(fetched) > len(text):
                text = fetched
        user = f"Source: {article.source_name}\nTitle: {article.title}\nURL: {article.url}\n\n{text[:MAX_ARTICLE_CHARS]}"
        try:
            return article, call(model, NOTE_SYSTEM, user, "article_note", NOTE_SCHEMA, 4000), None
        except Exception as exc:  # one bad article must not sink the digest
            return article, None, f"{article.title[:60]}: {exc}"

    if pending:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(one, pending))
        with connection(database_url) as conn:
            for article, note, error in results:
                if note is None:
                    errors.append(error or "unknown")
                    continue
                notes[article.evidence_id] = dict(note)
                conn.execute(
                    "INSERT INTO article_notes (evidence_id, model, note) VALUES (%s, %s, %s) ON CONFLICT (evidence_id) DO UPDATE SET model = EXCLUDED.model, note = EXCLUDED.note",
                    (article.evidence_id, model, Jsonb(dict(note))),
                )
    return notes, errors


def previous_idea_titles(database_url: str, *, limit: int = 5) -> list[str]:
    with connection(database_url) as conn:
        rows = conn.execute("SELECT payload FROM digests ORDER BY run_date DESC, created_at DESC LIMIT %s", (limit,)).fetchall()
    return [str(idea.get("title")) for (payload,) in rows for idea in (payload or {}).get("ideas", []) if idea.get("title")]


def synthesize(articles: Sequence[Article], notes: Mapping[str, Mapping[str, Any]], profile: str, call: JsonCall, model: str, *, already_proposed: Sequence[str] = (), threads: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    keyed = [(f"A{index}", article) for index, article in enumerate((a for a in articles if int(notes.get(a.evidence_id, {}).get("substance", 0)) >= 1), start=1)]
    if not keyed:
        return {"collisions": [], "themes": [], "ideas": [], "keys": {}}
    packet = [
        {"key": key, "source": article.source_name, "title": article.title, "date": article.published_at.date().isoformat(), **{name: notes[article.evidence_id].get(name) for name in ("summary", "whats_new", "claims", "techniques", "build_hooks", "substance")}}
        for key, article in keyed
    ]
    user = json.dumps({"profile": profile, "already_proposed": list(already_proposed), "threads_pulled": list(threads), "notes": packet}, ensure_ascii=False)
    raw = call(model, IDEAS_SYSTEM, user, "idea_digest", IDEAS_SCHEMA, 20000)
    by_key = dict(keyed)

    def resolve(keys: Any) -> list[str]:
        return list(dict.fromkeys(str(key).strip() for key in (keys or []) if str(key).strip() in by_key))

    themes = [{**theme, "sources": resolve(theme.get("sources"))} for theme in raw.get("themes", [])]
    collisions = [{**item, "sources": resolve(item.get("sources"))} for item in raw.get("collisions", [])]
    ideas = []
    for idea in raw.get("ideas", []):
        sources = resolve(idea.get("sources"))
        if not sources:
            continue  # an idea that cites nothing real is not grounded
        independent = len({by_key[key].source_id for key in sources})
        ideas.append({**idea, "sources": sources, "independent_sources": independent, "single_source": independent < 2})
    ideas.sort(key=lambda idea: idea["single_source"])
    keys = {key: {"evidence_id": a.evidence_id, "source": a.source_name, "title": a.title, "url": a.url, "date": a.published_at.date().isoformat()} for key, a in keyed}
    # A collision needs two real notes to collide.
    return {"collisions": [item for item in collisions if len(item["sources"]) >= 2], "themes": [theme for theme in themes if theme["sources"]], "ideas": ideas, "keys": keys}


def render_markdown(run_date: date, since: datetime, result: Mapping[str, Any], articles: Sequence[Article], notes: Mapping[str, Mapping[str, Any]]) -> str:
    keys = result.get("keys", {})

    def cite(sources: Sequence[str]) -> str:
        return "\n".join(f"  - [{keys[key]['source']} — {keys[key]['title']}]({keys[key]['url']})" for key in sources if key in keys)

    lines = [f"# Riff digest — {run_date.isoformat()}", "", f"{len(articles)} articles read from {len({a.source_id for a in articles})} sources, {since.date().isoformat()} to {run_date.isoformat()}.", ""]
    if not result.get("ideas"):
        lines += ["No idea cleared the bar this run. See what was read below.", ""]
    if result.get("ideas"):
        lines += ["## Ideas", ""]
        for number, idea in enumerate(result["ideas"], start=1):
            label = " *(single source)*" if idea["single_source"] else ""
            lines += [
                f"### {number}. {idea['title']}{label}", "", idea["pitch"], "",
                f"- **Connection:** {idea['connection']}", f"- **Why now:** {idea['why_now']}", f"- **Why you:** {idea['why_you']}",
                f"- **First step:** {idea['first_step']}", f"- **Artifact:** {idea['artifact']}", f"- **Biggest risk:** {idea['biggest_risk']}",
                "- **Sources:**", cite(idea["sources"]), "",
            ]
    if result.get("collisions"):
        lines += ["## Collisions", ""]
        for item in result["collisions"]:
            lines += [f"### {item['title']}", "", item["what_they_share"], "", f"**{item['question']}**", "", cite(item["sources"]), ""]
    if result.get("themes"):
        lines += ["## Themes", ""]
        for theme in result["themes"]:
            lines += [f"### {theme['title']}", "", theme["what_is_happening"], "", cite(theme["sources"]), ""]
    lines += ["## What was read", ""]
    for article in articles:
        note = notes.get(article.evidence_id, {})
        summary = str(note.get("summary", "")).strip() or "(no note)"
        lines.append(f"- **{article.source_name}** — [{article.title}]({article.url}) ({article.published_at.date().isoformat()}): {summary}")
    return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def run_digest(
    database_url: str,
    *,
    call: JsonCall,
    feeds: Sequence[Feed],
    profile: str,
    run_date: date | None = None,
    days: int = 7,
    do_collect: bool = True,
    note_model: str = DEFAULT_NOTE_MODEL,
    idea_model: str = DEFAULT_IDEA_MODEL,
    out_dir: str | Path | None = "digests",
    fetcher=None,
) -> dict[str, Any]:
    run_date = run_date or datetime.now(timezone.utc).date()
    until = datetime.combine(run_date, dtime.max, tzinfo=timezone.utc)
    since = datetime.combine(run_date - timedelta(days=days), dtime.min, tzinfo=timezone.utc)
    collection = collect(database_url, feeds, fetcher) if do_collect else None
    articles = window_articles(database_url, feeds, since, until)
    notes, note_errors = take_notes(database_url, articles, call, note_model)
    articles = [article for article in articles if article.evidence_id in notes]
    from .riffing import pulled_threads  # imported here: riffing builds on this module

    result = synthesize(articles, notes, profile, call, idea_model, already_proposed=previous_idea_titles(database_url), threads=pulled_threads(database_url))
    markdown = render_markdown(run_date, since, result, articles, notes)
    digest_id = str(uuid.uuid4())
    with connection(database_url) as conn:
        conn.execute(
            "INSERT INTO digests (digest_id, run_date, window_start, window_end, model, article_count, payload, markdown) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (digest_id, run_date, since, until, idea_model, len(articles), Jsonb(result), markdown),
        )
    path = None
    if out_dir is not None:
        path = Path(out_dir) / f"{run_date.isoformat()}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")
    usage = getattr(call, "usage", None)
    return {
        "digest_id": digest_id,
        "run_date": run_date.isoformat(),
        "collection": collection,
        "articles": len(articles),
        "sources_with_articles": len({a.source_id for a in articles}),
        "ideas": len(result["ideas"]),
        "single_source_ideas": sum(1 for idea in result["ideas"] if idea["single_source"]),
        "themes": len(result["themes"]),
        "note_errors": note_errors,
        "usage": usage.to_dict() if isinstance(usage, Usage) else None,
        "path": str(path) if path else None,
    }


def latest_digest(database_url: str) -> dict[str, Any] | None:
    with connection(database_url) as conn:
        row = conn.execute("SELECT digest_id, run_date, article_count, payload, markdown FROM digests ORDER BY run_date DESC, created_at DESC LIMIT 1").fetchone()
    if row is None:
        return None
    return {"digest_id": str(row[0]), "run_date": row[1].isoformat(), "article_count": int(row[2]), "payload": row[3], "markdown": str(row[4])}
