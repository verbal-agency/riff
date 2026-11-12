"""Riff with the digest: a conversation that wanders through the article store.

A thread starts from a collision, idea or theme in a digest (or from nothing).
Every turn, the model is handed a small "shelf" of real articles: the ones the
thread started from, ones found by searching the whole store for what was just
said, and, when asked to wander, a couple pulled at random.  It answers, cites
what it used, and offers three directions to go next.  A thread can be
distilled into a one-page sketch, and the threads you pull on are fed into the
next digest.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from psycopg.types.json import Jsonb

from .db import connection
from .digest import EXCLUDED_ORIGINS, JsonCall, _STRINGS, _object, html_to_text, latest_digest

DEFAULT_RIFF_MODEL = "gpt-5.5"
SEARCH_HITS = 5
STRAYS = 2
HISTORY_TURNS = 16
EXCERPT_CHARS = 1_800
KINDS = {"collision": "collisions", "idea": "ideas", "theme": "themes"}


class RiffingError(RuntimeError):
    """A riffing request could not be completed."""


TURN_SCHEMA = _object({"reply": {"type": "string"}, "sources": _STRINGS, "tangents": _STRINGS})

TURN_SYSTEM = (
    "You are riffing with one person about ideas, the way two curious friends do at a whiteboard. This is play with real material, not a report.\n\n"
    "You get: a note about who they are; the seed the conversation started from; the conversation so far; and a shelf of real articles, each with a key "
    "like S3. Some shelf items were found by searching for what they just said. Items marked stray were pulled at random and have nothing to do with "
    "the conversation: when strays are present, force one of them into the idea and see what it does.\n\n"
    "How to riff: build on what they said rather than evaluating it. Bring in one thing from the shelf they have not seen yet and say what it does to "
    "the idea. Prefer the unexpected connection to the sensible one. Make it concrete: a mechanism, an object, a first move. Disagree when something "
    "would not work, and say why. If they ask a direct question, answer it first.\n\n"
    "Be exact about the material: anything you say an article says must come from the shelf, and you list its key in sources. Your own speculation is "
    "welcome, and should read as yours. Never invent a result, a number or a source.\n\n"
    "reply: under 170 words, plain language, no headings or bullet lists, no flattery, and do not end by asking what they think. "
    "sources: shelf keys you actually drew on. "
    "tangents: exactly three short lines, written as things they might say next: one that goes deeper, one that swerves sideways into something "
    "unrelated on the shelf, one that turns it into something to build this week. Write each as a plain sentence in their voice, with no label such as 'Go deeper:' in front. "
    "When opening is true there is no message from them yet: open with the most interesting or strangest thing about the seed."
)

SKETCH_SCHEMA = _object({"title": {"type": "string"}, "sketch": {"type": "string"}, "sources": _STRINGS})

SKETCH_SYSTEM = (
    "You are given a wandering conversation about an idea and the shelf of articles it drew on. Write down the thing that emerged, as a one-page sketch "
    "in Markdown that someone could start from tomorrow. Use these sections, each a short paragraph or a few lines: '## What it is', "
    "'## What could not be done before', '## How it works', '## First hour', '## Open questions'. Stay faithful to the conversation: keep what was "
    "strange about it, and do not tidy it into something more sensible than what was actually said. If the conversation did not arrive anywhere, say "
    "so and sketch the most promising thread. title: a short name for the thing. sources: shelf keys the sketch rests on. Never invent sources."
)


# --------------------------------------------------------------------------
# The shelf: real articles the conversation can draw on
# --------------------------------------------------------------------------

_ARTICLE_COLUMNS = """e.evidence_id, s.name, si.title, si.canonical_url,
                      COALESCE(e.published_at, e.retrieved_at), n.note, left(e.raw_content, 12000)"""
_ARTICLE_JOINS = """FROM evidence_versions e
               JOIN source_items si ON si.source_item_id = e.source_item_id
               JOIN sources s ON s.source_id = si.source_id
               LEFT JOIN article_notes n ON n.evidence_id = e.evidence_id"""


def _item(row: Sequence[Any]) -> dict[str, Any]:
    evidence_id, source, title, url, at, note, raw = row
    item: dict[str, Any] = {"evidence_id": str(evidence_id), "source": str(source).split(" — ")[0], "title": str(title or url), "url": str(url), "date": at.date().isoformat() if at else None}
    if note:
        item["note"] = {name: note.get(name) for name in ("summary", "whats_new", "claims", "techniques", "build_hooks")}
    else:
        item["excerpt"] = html_to_text(str(raw or ""))[:EXCERPT_CHARS]
    return item


def _search_terms(conn, text: str) -> list[str]:
    row = conn.execute("SELECT array_agg(lexeme) FROM unnest(to_tsvector('english', %s))", (text[:2000],)).fetchone()
    return [term for term in (row[0] or []) if len(term) > 3 and term.isalnum()][:14]


def search_articles(database_url: str, source_ids: Sequence[str], text: str, *, limit: int = SEARCH_HITS, exclude: Sequence[str] = ()) -> list[dict[str, Any]]:
    """Find stored articles about what was just said, across the whole store."""

    with connection(database_url) as conn:
        terms = _search_terms(conn, text)
        if not terms:
            return []
        rows = conn.execute(
            f"""SELECT DISTINCT ON (si.source_item_id) {_ARTICLE_COLUMNS}, ts_rank(e.search_vector, q, 1)
               {_ARTICLE_JOINS}, to_tsquery('english', %s) q
               WHERE si.source_id = ANY(%s) AND e.search_vector @@ q AND e.raw_content IS NOT NULL
                 AND e.data_origin <> ALL(%s) AND e.evidence_id <> ALL(%s)
               ORDER BY si.source_item_id, e.retrieved_at DESC""",
            (" | ".join(terms), list(source_ids), list(EXCLUDED_ORIGINS), list(exclude)),
        ).fetchall()
    seen: set[str] = set()
    hits = []
    for row in sorted(rows, key=lambda row: row[7], reverse=True):
        if row[3] in seen:
            continue
        seen.add(row[3])
        hits.append(_item(row[:7]))
        if len(hits) >= limit:
            break
    return hits


def stray_articles(database_url: str, source_ids: Sequence[str], *, limit: int = STRAYS, exclude: Sequence[str] = ()) -> list[dict[str, Any]]:
    """Pull articles at random: the point is that they are unrelated."""

    with connection(database_url) as conn:
        rows = conn.execute(
            f"""SELECT {_ARTICLE_COLUMNS} {_ARTICLE_JOINS}
               WHERE si.source_id = ANY(%s) AND length(e.raw_content) > 1500
                 AND e.data_origin <> ALL(%s) AND e.evidence_id <> ALL(%s)
               ORDER BY random() LIMIT %s""",
            (list(source_ids), list(EXCLUDED_ORIGINS), list(exclude), limit),
        ).fetchall()
    return [_item(row) | {"stray": True} for row in rows]


def articles_by_id(database_url: str, evidence_ids: Sequence[str]) -> list[dict[str, Any]]:
    if not evidence_ids:
        return []
    with connection(database_url) as conn:
        rows = conn.execute(f"SELECT {_ARTICLE_COLUMNS} {_ARTICLE_JOINS} WHERE e.evidence_id = ANY(%s)", (list(evidence_ids),)).fetchall()
    by_id = {str(row[0]): _item(row) for row in rows}
    return [by_id[evidence_id] for evidence_id in evidence_ids if evidence_id in by_id]


class Shelf:
    """Stable S-keys for a thread, so citations keep meaning the same article."""

    def __init__(self, stored: Mapping[str, Mapping[str, Any]] | None = None):
        self.entries: dict[str, dict[str, Any]] = {key: dict(value) for key, value in (stored or {}).items()}

    def key_for(self, item: Mapping[str, Any]) -> str:
        for key, entry in self.entries.items():
            if entry["evidence_id"] == item["evidence_id"]:
                return key
        key = f"S{len(self.entries) + 1}"
        self.entries[key] = {name: item.get(name) for name in ("evidence_id", "source", "title", "url", "date")}
        return key

    def cited(self, keys: Any) -> list[dict[str, Any]]:
        return [{"key": key, **self.entries[key]} for key in dict.fromkeys(str(k).strip() for k in (keys or [])) if key in self.entries]


# --------------------------------------------------------------------------
# Threads
# --------------------------------------------------------------------------

def _thread_row(row: Sequence[Any]) -> dict[str, Any]:
    return {"thread_id": str(row[0]), "kind": str(row[1]), "title": str(row[2]), "seed": row[3], "shelf": row[4], "sketch": row[5], "updated_at": row[6].isoformat()}


def list_threads(database_url: str, *, limit: int = 30) -> list[dict[str, Any]]:
    with connection(database_url) as conn:
        rows = conn.execute(
            """SELECT t.thread_id, t.kind, t.title, t.sketch IS NOT NULL, t.updated_at,
                      (SELECT count(*) FROM riff_messages m WHERE m.thread_id = t.thread_id AND m.role = 'you')
               FROM riff_threads t ORDER BY t.updated_at DESC LIMIT %s""",
            (limit,),
        ).fetchall()
    return [{"thread_id": str(a), "kind": str(b), "title": str(c), "distilled": bool(d), "updated_at": e.isoformat(), "your_turns": int(f)} for a, b, c, d, e, f in rows]


def get_thread(database_url: str, thread_id: str) -> dict[str, Any]:
    with connection(database_url) as conn:
        row = conn.execute("SELECT thread_id, kind, title, seed, shelf, sketch, updated_at FROM riff_threads WHERE thread_id = %s", (thread_id,)).fetchone()
        if row is None:
            raise RiffingError("unknown thread")
        messages = conn.execute("SELECT role, content, sources, tangents FROM riff_messages WHERE thread_id = %s ORDER BY message_id", (thread_id,)).fetchall()
    thread = _thread_row(row)
    thread["messages"] = [{"role": str(a), "content": str(b), "sources": c or [], "tangents": d or []} for a, b, c, d in messages]
    return thread


def start_thread(database_url: str, *, call: JsonCall, source_ids: Sequence[str], profile: str, kind: str, index: int | None = None, text: str | None = None, model: str = DEFAULT_RIFF_MODEL) -> dict[str, Any]:
    """Create a thread from a digest item (or free text) and make the opening move."""

    digest_id = None
    seed_ids: list[str] = []
    if kind == "free":
        text = (text or "").strip()
        if not text:
            raise RiffingError("say something to start from")
        title, seed = (text[:80] + "…" if len(text) > 80 else text), {"kind": "free"}
    elif kind in KINDS:
        digest = latest_digest(database_url)
        items = (digest or {}).get("payload", {}).get(KINDS[kind], [])
        if digest is None or index is None or not 0 <= index < len(items):
            raise RiffingError("that digest item does not exist")
        item, keys = items[index], digest["payload"].get("keys", {})
        digest_id, title = digest["digest_id"], str(item["title"])
        seed = {"kind": kind, **{name: value for name, value in item.items() if name not in {"sources", "independent_sources", "single_source"}}}
        seed_ids = [keys[key]["evidence_id"] for key in item.get("sources", []) if key in keys]
    else:
        raise RiffingError("kind must be collision, idea, theme or free")

    shelf = Shelf()
    seed["source_keys"] = [shelf.key_for(article) for article in articles_by_id(database_url, seed_ids)]
    thread_id = str(uuid.uuid4())
    with connection(database_url) as conn:
        conn.execute(
            "INSERT INTO riff_threads (thread_id, digest_id, kind, title, seed, shelf) VALUES (%s, %s, %s, %s, %s, %s)",
            (thread_id, digest_id, kind, title, Jsonb(seed), Jsonb(shelf.entries)),
        )
    take_turn(database_url, thread_id, call=call, source_ids=source_ids, profile=profile, text=text if kind == "free" else None, model=model)
    return get_thread(database_url, thread_id)


def take_turn(database_url: str, thread_id: str, *, call: JsonCall, source_ids: Sequence[str], profile: str, text: str | None, wander: bool = False, model: str = DEFAULT_RIFF_MODEL) -> dict[str, Any]:
    """Add the reader's message (if any), build the shelf, and get the reply."""

    thread = get_thread(database_url, thread_id)
    text = (text or "").strip() or None
    if text is None and thread["messages"] and not wander:
        raise RiffingError("say something, or ask to wander")
    shelf = Shelf(thread["shelf"])
    seed_keys = list(thread["seed"].get("source_keys", []))
    cited_keys = [source["key"] for message in thread["messages"] for source in message["sources"]]
    carried = list(dict.fromkeys(seed_keys + cited_keys[-6:]))
    on_shelf = articles_by_id(database_url, [shelf.entries[key]["evidence_id"] for key in carried if key in shelf.entries])
    have = [item["evidence_id"] for item in on_shelf]
    query = text or " ".join(str(value) for value in thread["seed"].values() if isinstance(value, str))
    found = search_articles(database_url, source_ids, query, exclude=have)
    strays = stray_articles(database_url, source_ids, exclude=have + [item["evidence_id"] for item in found]) if wander else []
    packet = [{"key": shelf.key_for(item), **{name: value for name, value in item.items() if name != "evidence_id"}} for item in on_shelf + found + strays]

    history = [{"who": message["role"], "said": message["content"]} for message in thread["messages"][-HISTORY_TURNS:]]
    user = json.dumps({
        "about_them": profile,
        "seed": {name: value for name, value in thread["seed"].items() if name != "source_keys"} | {"title": thread["title"], "shelf_keys": seed_keys},
        "conversation": history,
        "they_just_said": text,
        "opening": not thread["messages"] and text is None,
        "wander": bool(strays),
        "shelf": packet,
    }, ensure_ascii=False)
    raw = call(model, TURN_SYSTEM, user, "riff_turn", TURN_SCHEMA, 12000)
    reply = str(raw.get("reply", "")).strip()
    if not reply:
        raise RiffingError("the model returned an empty reply")
    tangents = [str(item).strip() for item in raw.get("tangents", []) if str(item).strip()][:3]
    with connection(database_url) as conn:
        if text is not None:
            conn.execute("INSERT INTO riff_messages (thread_id, role, content) VALUES (%s, 'you', %s)", (thread_id, text))
        elif wander:
            conn.execute("INSERT INTO riff_messages (thread_id, role, content) VALUES (%s, 'you', %s)", (thread_id, "(wander: throw something unrelated in)"))
        conn.execute(
            "INSERT INTO riff_messages (thread_id, role, content, sources, tangents) VALUES (%s, 'riff', %s, %s, %s)",
            (thread_id, reply, Jsonb(shelf.cited(raw.get("sources"))), Jsonb(tangents)),
        )
        conn.execute("UPDATE riff_threads SET shelf = %s, updated_at = now() WHERE thread_id = %s", (Jsonb(shelf.entries), thread_id))
    return get_thread(database_url, thread_id)


def distill(database_url: str, thread_id: str, *, call: JsonCall, model: str = DEFAULT_RIFF_MODEL, out_dir: str | Path | None = "digests/threads") -> dict[str, Any]:
    """Write down what the conversation arrived at."""

    thread = get_thread(database_url, thread_id)
    if not any(message["role"] == "you" for message in thread["messages"]):
        raise RiffingError("there is nothing to distill yet; riff first")
    shelf = Shelf(thread["shelf"])
    used = list(dict.fromkeys(source["key"] for message in thread["messages"] for source in message["sources"]))
    articles = articles_by_id(database_url, [shelf.entries[key]["evidence_id"] for key in used])
    user = json.dumps({
        "started_from": thread["title"],
        "conversation": [{"who": message["role"], "said": message["content"]} for message in thread["messages"]],
        "shelf": [{"key": shelf.key_for(item), **{name: value for name, value in item.items() if name != "evidence_id"}} for item in articles],
    }, ensure_ascii=False)
    raw = call(model, SKETCH_SYSTEM, user, "riff_sketch", SKETCH_SCHEMA, 12000)
    title = str(raw.get("title", "")).strip() or thread["title"]
    return _store_sketch(database_url, thread, title, str(raw.get("sketch", "")), shelf.cited(raw.get("sources")), out_dir)


def _store_sketch(database_url: str, thread: Mapping[str, Any], title: str, body: str, sources: Sequence[Mapping[str, Any]], out_dir: str | Path | None) -> dict[str, Any]:
    lines = [f"# {title}", "", f"Distilled {datetime.now(timezone.utc).date().isoformat()} from a riff that started at: {thread['title']}", "", body.strip(), ""]
    if sources:
        lines += ["## Sources", ""] + [f"- [{source['source']} — {source['title']}]({source['url']})" for source in sources] + [""]
    sketch = "\n".join(lines)
    with connection(database_url) as conn:
        conn.execute("UPDATE riff_threads SET sketch = %s, updated_at = now() WHERE thread_id = %s", (sketch, thread["thread_id"]))
    path = None
    if out_dir is not None:
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "sketch"
        path = Path(out_dir) / f"{datetime.now(timezone.utc).date().isoformat()}-{slug}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(sketch, encoding="utf-8")
    return get_thread(database_url, thread["thread_id"]) | {"path": str(path) if path else None}


# --------------------------------------------------------------------------
# For an outside model riffing over MCP: Riff supplies material and keeps the record
# --------------------------------------------------------------------------

def digest_for_reading(database_url: str) -> dict[str, Any]:
    """The latest digest with each item's sources resolved to real articles."""

    digest = latest_digest(database_url)
    if digest is None:
        raise RiffingError("no digest yet; run: riff digest run")
    payload, keys = digest["payload"], digest["payload"].get("keys", {})

    # Sources stay as keys into one shared article list: repeating each article
    # under every item that cites it would double the size of the result.
    sections = {name: [{field: value for field, value in item.items() if field not in {"independent_sources"}} for item in payload.get(name, [])] for name in ("collisions", "ideas", "themes")}
    cited = {key for items in sections.values() for item in items for key in item.get("sources", [])}
    return {"run_date": digest["run_date"], "articles_read": digest["article_count"], **sections, "articles": {key: keys[key] for key in sorted(cited, key=lambda key: int(key[1:])) if key in keys}}


def read_article(database_url: str, evidence_id: str, *, max_chars: int = 12_000) -> dict[str, Any]:
    with connection(database_url) as conn:
        row = conn.execute(f"SELECT {_ARTICLE_COLUMNS}, e.raw_content {_ARTICLE_JOINS} WHERE e.evidence_id = %s", (evidence_id,)).fetchone()
    if row is None:
        raise RiffingError("unknown article")
    text = html_to_text(str(row[7] or ""))
    return {name: value for name, value in _item(row[:7]).items() if name != "excerpt"} | {"text": text[:max_chars], "truncated": len(text) > max_chars}


def record_exchange(database_url: str, *, title: str, you_said: str, reply: str, evidence_ids: Sequence[str] = (), thread_id: str | None = None) -> dict[str, Any]:
    """Save one exchange from a conversation held elsewhere, so it shows up in Riff and shapes the next digest."""

    you_said, reply = you_said.strip(), reply.strip()
    if not you_said or not reply:
        raise RiffingError("both sides of the exchange are required")
    if thread_id:
        thread = get_thread(database_url, thread_id)
    else:
        if not title.strip():
            raise RiffingError("a title is required to start a thread")
        thread_id = str(uuid.uuid4())
        with connection(database_url) as conn:
            conn.execute("INSERT INTO riff_threads (thread_id, kind, title, seed) VALUES (%s, 'free', %s, %s)", (thread_id, title.strip()[:200], Jsonb({"kind": "free", "via": "mcp"})))
        thread = get_thread(database_url, thread_id)
    shelf = Shelf(thread["shelf"])
    keys = [shelf.key_for(article) for article in articles_by_id(database_url, list(dict.fromkeys(evidence_ids)))]
    with connection(database_url) as conn:
        conn.execute("INSERT INTO riff_messages (thread_id, role, content) VALUES (%s, 'you', %s)", (thread_id, you_said[:4000]))
        conn.execute("INSERT INTO riff_messages (thread_id, role, content, sources) VALUES (%s, 'riff', %s, %s)", (thread_id, reply[:8000], Jsonb(shelf.cited(keys))))
        conn.execute("UPDATE riff_threads SET shelf = %s, updated_at = now() WHERE thread_id = %s", (Jsonb(shelf.entries), thread_id))
    return {"thread_id": thread_id, "title": thread["title"], "exchanges": sum(1 for message in get_thread(database_url, thread_id)["messages"] if message["role"] == "you"), "sources_recorded": len(keys)}


def save_sketch(database_url: str, thread_id: str, *, title: str, sketch: str, evidence_ids: Sequence[str] = (), out_dir: str | Path | None = "digests/threads") -> dict[str, Any]:
    """Store a sketch written elsewhere against a thread."""

    if not sketch.strip():
        raise RiffingError("the sketch is empty")
    thread = get_thread(database_url, thread_id)
    shelf = Shelf(thread["shelf"])
    keys = [shelf.key_for(article) for article in articles_by_id(database_url, list(dict.fromkeys(evidence_ids)))]
    with connection(database_url) as conn:
        conn.execute("UPDATE riff_threads SET shelf = %s WHERE thread_id = %s", (Jsonb(shelf.entries), thread_id))
    saved = _store_sketch(database_url, thread, title.strip() or thread["title"], sketch, shelf.cited(keys), out_dir)
    return {"thread_id": thread_id, "title": saved["title"], "path": saved["path"], "sources_recorded": len(keys)}


def pulled_threads(database_url: str, *, days: int = 21, limit: int = 8) -> list[dict[str, Any]]:
    """What the reader chose to wander into recently; the next digest leans toward it."""

    with connection(database_url) as conn:
        rows = conn.execute(
            """SELECT t.title, t.sketch IS NOT NULL,
                      ARRAY(SELECT left(m.content, 280) FROM riff_messages m
                            WHERE m.thread_id = t.thread_id AND m.role = 'you' AND m.content NOT LIKE '(wander:%%'
                            ORDER BY m.message_id DESC LIMIT 3)
               FROM riff_threads t
               WHERE t.updated_at >= now() - make_interval(days => %s)
                 AND EXISTS (SELECT 1 FROM riff_messages m WHERE m.thread_id = t.thread_id AND m.role = 'you')
               ORDER BY t.updated_at DESC LIMIT %s""",
            (days, limit),
        ).fetchall()
    return [{"started_from": str(title), "distilled_into_a_sketch": bool(distilled), "they_said": list(reversed(said))} for title, distilled, said in rows]
