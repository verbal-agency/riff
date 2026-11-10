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


def test_page_links_and_dates_for_sites_without_a_feed():
    from riff.digest import page_links, page_title, published_date

    feed = Feed("site", "Site", "https://www.site.example/news", kind="page", link_pattern=r"^/news/[a-z0-9]+-[a-z0-9-]+$")
    index = '<a href="/news/policy">Category</a><a href="/news/second-post">2</a><a href="/news/first-post#top">1</a><a href="https://other.example/news/not-ours">x</a><a href="/news/second-post">again</a>'
    assert page_links(index, feed) == ["https://www.site.example/news/second-post", "https://www.site.example/news/first-post"]

    assert published_date('<meta property="article:published_time" content="2024-12-19T00:00:00.000Z"/>').date() == date(2024, 12, 19)
    assert published_date('<time dateTime="2024-10-01">October 2024</time>').date() == date(2024, 10, 1)
    assert published_date("<p>Jane Doe, August 2026</p>").date() == date(2026, 8, 1)
    assert published_date("<p>Apply by November 22, 2999.</p>") is None  # a future date is a deadline, not a publication date
    assert page_title('<meta property="og:title" content="A post \\ Anthropic"><title>x</title>') == "A post"


@pytest.mark.postgres
def test_collect_pages_stores_unseen_articles_once():
    database_url = os.environ.get("RIFF_DATABASE_URL")
    if not database_url:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    from riff.digest import collect, window_articles

    tag = f"pages-{uuid.uuid4().hex[:8]}"
    feed = Feed(tag, "Site", f"https://{tag}.example/", kind="page", link_pattern=r"^/essay/[a-z-]+$")
    pages = {
        f"https://{tag}.example/": '<a href="/essay/one-thing">1</a><a href="/essay/thin">2</a><a href="/about">about</a>',
        f"https://{tag}.example/essay/one-thing": '<title>One thing</title><time dateTime="2026-11-03">Nov</time><article><p>' + "collide " * 80 + "</p></article>",
        f"https://{tag}.example/essay/thin": "<article><p>too short</p></article>",
    }
    fetched = []

    def fetch(url):
        fetched.append(url)
        return pages.get(url, "")

    first = collect(database_url, [feed], page_fetcher=fetch)
    second = collect(database_url, [feed], page_fetcher=fetch)

    assert first["stored"] == 1 and second["stored"] == 0 and first["failures"] == []
    assert fetched.count(f"https://{tag}.example/essay/one-thing") == 1  # known articles are not fetched again
    articles = window_articles(database_url, [feed], datetime(2026, 11, 1, tzinfo=timezone.utc), datetime(2026, 11, 5, tzinfo=timezone.utc))
    assert [(a.title, a.published_at.date()) for a in articles] == [("One thing", date(2026, 11, 3))]


@pytest.mark.postgres
def test_pull_requests_are_snapshotted_only_when_they_change():
    database_url = os.environ.get("RIFF_DATABASE_URL")
    if not database_url:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    from riff.digest import collect, window_articles

    repo = f"owner/repo-{uuid.uuid4().hex[:8]}"
    feed = Feed(f"prs-{uuid.uuid4().hex[:8]}", "Repo pull requests", f"https://github.com/{repo}", kind="prs", pulls=(7, 8))
    pull = {"number": 7, "title": "Add events", "state": "open", "user": {"login": "ana"}, "created_at": "2026-10-01T00:00:00Z", "updated_at": "2026-11-02T00:00:00Z", "body": "Lets a client <subscribe> to events."}
    comments = [{"user": {"login": "bo"}, "created_at": "2026-11-01T00:00:00Z", "body": "What about replay?"}]
    asked = []

    def get_json(url):
        asked.append(url)
        if url.endswith("/pulls/7"):
            return pull
        if "/issues/7/comments" in url:
            return comments
        return None  # pull 8 is unavailable

    first = collect(database_url, [feed], github_json=get_json)
    assert first["stored"] == 1 and first["failures"] == [{"source_id": feed.source_id, "error": "PULL_UNAVAILABLE:8", "count": 1}]
    assert collect(database_url, [feed], github_json=get_json)["stored"] == 0  # unchanged, so no new snapshot

    pull.update(state="closed", merged_at="2026-11-04T00:00:00Z", updated_at="2026-11-04T00:00:00Z")
    comments[:] = [{"user": {"login": "cy"}, "created_at": "2026-11-04T00:00:00Z", "body": "Merging."}]
    assert collect(database_url, [feed], github_json=get_json)["stored"] == 1
    assert any(url.endswith("comments?per_page=100&since=2026-11-02T00:00:00Z") for url in asked)  # only discussion since the last snapshot

    articles = window_articles(database_url, [feed], datetime(2026, 11, 1, tzinfo=timezone.utc), datetime(2026, 11, 5, tzinfo=timezone.utc))
    assert len(articles) == 1  # the newest snapshot stands for the pull request
    article = articles[0]
    assert article.title == "PR #7: Add events" and article.url == f"https://github.com/{repo}/pull/7" and article.fetch_full is False
    assert "has been MERGED" in article.text and "<subscribe>" in article.text and "cy (2026-11-04): Merging." in article.text
    assert "What about replay?" not in article.text
