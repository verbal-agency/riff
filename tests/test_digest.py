import os
import uuid
from datetime import date, datetime, timezone

import pytest

from riff.digest import Article, Feed, html_to_text, render_markdown, run_digest, synthesize
from riff.ingestion import FeedResponse


def _article(n: int, source: str) -> Article:
    return Article(f"ev-{n}", source, source.title(), f"Post {n}", f"https://{source}.example/{n}", datetime(2026, 11, n, tzinfo=timezone.utc), "body " * 100)


def _idea(title: str, sources: list[str]) -> dict:
    return {"title": title, "pitch": "p", "connection": "c", "why_now": "n", "why_you": "y", "first_step": "f", "artifact": "a", "biggest_risk": "r", "sources": sources}


def test_html_to_text_drops_markup_and_scripts():
    assert html_to_text("<p>Hello <b>world</b></p><script>x()</script><p>Next &amp; last</p>") == "Hello world\n\nNext & last"


def test_synthesize_checks_citations_and_labels_single_source_ideas():
    articles = [_article(1, "alpha"), _article(2, "beta"), _article(3, "alpha"), _article(4, "gamma")]
    notes = {a.evidence_id: {"summary": "s", "substance": 2} for a in articles}
    notes["ev-4"]["substance"] = 0  # announcements never reach the idea prompt
    seen = {}

    def call(model, system, user, name, schema, max_tokens):
        seen["user"] = user
        return {
            "collisions": [{"title": "pair", "what_they_share": "s", "question": "q?", "sources": ["A1", "A2"]}, {"title": "lonely", "what_they_share": "s", "question": "q?", "sources": ["A1", "Z9"]}],
            "themes": [{"title": "T", "what_is_happening": "w", "sources": ["A1", "A9"]}],
            "ideas": [_idea("one feed", ["A1", "A3"]), _idea("two feeds", ["A1", "A2"]), _idea("invented", ["A9", "Z1"])],
        }

    result = synthesize(articles, notes, "profile", call, "m")

    assert [idea["title"] for idea in result["ideas"]] == ["two feeds", "one feed"]
    assert [idea["single_source"] for idea in result["ideas"]] == [False, True]
    assert result["themes"][0]["sources"] == ["A1"]
    assert [item["title"] for item in result["collisions"]] == ["pair"]
    assert set(result["keys"]) == {"A1", "A2", "A3"} and "Post 4" not in seen["user"]

    markdown = render_markdown(date(2026, 11, 5), datetime(2026, 10, 29, tzinfo=timezone.utc), result, articles, notes)
    assert "### 2. one feed *(single source)*" in markdown
    assert "[Beta — Post 2](https://beta.example/2)" in markdown
    assert "## Collisions" in markdown and "**q?**" in markdown


FEED = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>t</title>
<entry><id>{tag}-1</id><title>Checkpointing agents</title><link href="https://{tag}.example/1"/>
<updated>2026-11-03T00:00:00Z</updated><content type="html">&lt;p&gt;{body}&lt;/p&gt;</content></entry></feed>"""


@pytest.mark.postgres
def test_run_digest_collects_notes_once_and_persists(tmp_path):
    database_url = os.environ.get("RIFF_DATABASE_URL")
    if not database_url:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    tags = [f"digest-{uuid.uuid4().hex[:8]}" for _ in range(2)]
    feeds = [Feed(tag, tag, f"https://{tag}.example/feed") for tag in tags]

    class Fetcher:
        def fetch(self, endpoint):
            tag = endpoint.split("//")[1].split(".")[0]
            return FeedResponse(body=FEED.format(tag=tag, body="durable words " * 40).encode(), fetched_at=datetime.now(timezone.utc), final_url=endpoint)

    calls = []

    def call(model, system, user, name, schema, max_tokens):
        calls.append(name)
        if name == "article_note":
            return {"summary": "s", "whats_new": "w", "claims": [], "techniques": [], "build_hooks": [], "substance": 2}
        return {"themes": [], "ideas": [_idea("combine", ["A1", "A2"])]}

    kwargs = dict(call=call, feeds=feeds, profile="p", run_date=date(2026, 11, 5), days=7, out_dir=tmp_path, fetcher=Fetcher())
    first = run_digest(database_url, **kwargs)
    second = run_digest(database_url, **kwargs)

    assert first["articles"] == 2 and first["ideas"] == 1 and first["single_source_ideas"] == 0
    assert calls.count("article_note") == 2  # the second run reuses cached notes
    assert second["articles"] == 2
    assert "combine" in (tmp_path / "2026-11-05.md").read_text()
