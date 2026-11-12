import os
import uuid
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

from riff import riffing
from riff.api import create_app
from riff.config import Settings
from riff.digest import Feed, run_digest
from riff.ingestion import FeedResponse

FEED = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>t</title>
<entry><id>{tag}-1</id><title>{title}</title><link href="https://{tag}.example/1"/>
<updated>2026-11-0{day}T00:00:00Z</updated><content type="html">&lt;p&gt;{body}&lt;/p&gt;</content></entry></feed>"""


def test_shelf_keys_are_stable_and_unknown_citations_are_dropped():
    shelf = riffing.Shelf()
    first = shelf.key_for({"evidence_id": "e1", "source": "A", "title": "One", "url": "u1", "date": None})
    second = shelf.key_for({"evidence_id": "e2", "source": "B", "title": "Two", "url": "u2", "date": None})
    assert (first, second) == ("S1", "S2")
    assert riffing.Shelf(shelf.entries).key_for({"evidence_id": "e1"}) == "S1"
    assert [item["title"] for item in shelf.cited(["S2", "S9", "S2"])] == ["Two"]


@pytest.mark.postgres
def test_riff_thread_searches_the_store_wanders_distills_and_feeds_the_digest(tmp_path, monkeypatch):
    database_url = os.environ.get("RIFF_DATABASE_URL")
    if not database_url:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    word = f"zebrafish{uuid.uuid4().hex[:6]}"
    tags = [f"riffing-{uuid.uuid4().hex[:8]}" for _ in range(4)]
    feeds = [Feed(tag, tag, f"https://{tag}.example/feed") for tag in tags]
    titles = dict(zip(tags, ["Clocks", "Maps", f"A note on {word}", "Rivers"]))
    days = dict(zip(tags, [4, 3, 2, 1]))  # newest first, so the digest keys them A1..A4 in this order
    bodies = dict(zip(tags, ["clock words " * 150, "map words " * 150, f"{word} hatcheries " * 150, "river words " * 150]))

    class Fetcher:
        def fetch(self, endpoint):
            tag = endpoint.split("//")[1].split(".")[0]
            return FeedResponse(body=FEED.format(tag=tag, title=titles[tag], body=bodies[tag], day=days[tag]).encode(), fetched_at=datetime.now(timezone.utc), final_url=endpoint)

    seen = []

    def call(model, system, user, name, schema, max_tokens):
        seen.append((name, user))
        if name == "article_note":
            return {"summary": "s", "whats_new": "w", "claims": [], "techniques": [], "build_hooks": [], "substance": 2}
        if name == "idea_digest":
            return {"collisions": [{"title": "Clocks meet maps", "what_they_share": "s", "question": "q?", "sources": ["A1", "A2"]}], "themes": [], "ideas": []}
        if name == "riff_sketch":
            return {"title": "Zebra Clock", "sketch": "## What it is\nA thing.", "sources": ["S1", "S77"]}
        return {"reply": "a reply", "sources": ["S1", "S3", "S99"], "tangents": ["deeper", "sideways", "build", "extra"]}

    # The collision cites the first two; the third is found by search and the fourth only by wandering.
    run_digest(database_url, call=call, feeds=feeds, profile="p", run_date=date(2026, 11, 5), days=7, out_dir=None, fetcher=Fetcher())
    feeds_file = tmp_path / "feeds.json"
    feeds_file.write_text('{"schema_version": 1, "feeds": [%s]}' % ",".join('{"source_id": "%s", "name": "%s", "endpoint": "%s"}' % (f.source_id, f.name, f.endpoint) for f in feeds))
    monkeypatch.setenv("RIFF_DIGEST_FEEDS", str(feeds_file))
    monkeypatch.chdir(tmp_path)

    app = create_app(Settings(database_url=database_url))
    app.state.riff_call = call
    client = TestClient(app)

    assert "<title>Riff | Verbal Agency</title>" in client.get("/riff").text
    state = client.get("/riff/api/state").json()
    assert state["digest"]["payload"]["collisions"][0]["title"] == "Clocks meet maps"

    thread = client.post("/riff/api/threads", json={"kind": "collision", "index": 0}).json()
    assert thread["title"] == "Clocks meet maps" and thread["seed"]["source_keys"] == ["S1", "S2"]
    opening = thread["messages"][-1]
    assert opening["role"] == "riff" and opening["tangents"] == ["deeper", "sideways", "build"]
    assert [source["key"] for source in opening["sources"]] == ["S1"]  # S3 and S99 were not on the shelf yet

    url = f"/riff/api/threads/{thread['thread_id']}"
    assert client.post(url + "/messages", json={"text": ""}).status_code == 400
    thread = client.post(url + "/messages", json={"text": f"what about {word}?"}).json()
    assert [message["role"] for message in thread["messages"]] == ["riff", "you", "riff"]
    assert f"A note on {word}" in seen[-1][1]  # search put the unrelated article on the shelf
    assert [source["title"] for source in thread["messages"][-1]["sources"]] == ["Clocks", f"A note on {word}"]

    thread = client.post(url + "/messages", json={"wander": True}).json()
    assert '"wander": true' in seen[-1][1] and '"stray": true' in seen[-1][1] and "Rivers" in seen[-1][1]

    sketched = client.post(url + "/distill", json={}).json()
    assert sketched["sketch"].startswith("# Zebra Clock") and "[riffing-" in sketched["sketch"] and "S77" not in sketched["sketch"]
    assert (tmp_path / sketched["path"]).exists()
    assert client.get("/riff/api/state").json()["threads"][0]["distilled"] is True
    assert client.get("/riff/api/threads/nope").status_code == 404

    pulled = riffing.pulled_threads(database_url)
    mine = next(item for item in pulled if item["started_from"] == "Clocks meet maps" and f"what about {word}?" in item["they_said"])
    assert mine["distilled_into_a_sketch"] is True
    run_digest(database_url, call=call, feeds=feeds[:2], profile="p", run_date=date(2026, 11, 5), days=7, out_dir=None, do_collect=False)
    assert f"what about {word}?" in next(user for name, user in reversed(seen) if name == "idea_digest")


@pytest.mark.postgres
def test_mcp_tools_supply_material_and_keep_the_record(tmp_path, monkeypatch):
    database_url = os.environ.get("RIFF_DATABASE_URL")
    if not database_url:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    from riff.mcp_server import create_service_app

    word = f"axolotl{uuid.uuid4().hex[:6]}"
    tags = [f"mcp-{uuid.uuid4().hex[:8]}" for _ in range(2)]
    feeds = [Feed(tag, tag, f"https://{tag}.example/feed") for tag in tags]
    titles = dict(zip(tags, ["Tides", f"On {word}"]))
    bodies = dict(zip(tags, ["tide words " * 150, f"{word} regrows limbs " * 150]))

    class Fetcher:
        def fetch(self, endpoint):
            tag = endpoint.split("//")[1].split(".")[0]
            return FeedResponse(body=FEED.format(tag=tag, title=titles[tag], body=bodies[tag], day=3).encode(), fetched_at=datetime.now(timezone.utc), final_url=endpoint)

    def call(model, system, user, name, schema, max_tokens):
        if name == "article_note":
            return {"summary": "s", "whats_new": "w", "claims": [], "techniques": [], "build_hooks": [], "substance": 2}
        return {"collisions": [{"title": "Tides meet limbs", "what_they_share": "s", "question": "q?", "sources": ["A1", "A2"]}], "themes": [], "ideas": []}

    run_digest(database_url, call=call, feeds=feeds, profile="p", run_date=date(2026, 11, 5), days=7, out_dir=None, fetcher=Fetcher())
    feeds_file = tmp_path / "feeds.json"
    feeds_file.write_text('{"schema_version": 1, "feeds": [%s]}' % ",".join('{"source_id": "%s", "name": "%s", "endpoint": "%s"}' % (f.source_id, f.name, f.endpoint) for f in feeds))
    (tmp_path / "profile.md").write_text("Stay curious.")
    monkeypatch.setenv("RIFF_DIGEST_FEEDS", str(feeds_file))
    monkeypatch.setenv("RIFF_PROFILE", str(tmp_path / "profile.md"))
    monkeypatch.chdir(tmp_path)

    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    with TestClient(create_service_app(Settings(database_url=database_url)), base_url="http://localhost:8000") as client:
        def tool(name, **arguments):
            result = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}).json()["result"]
            return result["isError"], result.get("structuredContent")

        assert tool("riff_profile")[1]["profile"] == "Stay curious."
        latest = tool("digest_latest")[1]
        collision = latest["collisions"][0]
        assert collision["title"] == "Tides meet limbs" and {latest["articles"][key]["title"] for key in collision["sources"]} == set(titles.values())

        found = tool("article_search", query=f"does {word} matter")[1]["articles"]
        assert [article["title"] for article in found] == [f"On {word}"] and "note" in found[0]
        evidence_id = found[0]["evidence_id"]
        assert word in tool("article_read", evidence_id=evidence_id)[1]["text"]
        assert all(article["stray"] for article in tool("article_wander", count=2)[1]["articles"])

        assert tool("riff_record", you_said="hi", reply="")[0] is True  # both sides are required
        saved = tool("riff_record", title="Limb tides", you_said=f"what if {word} kept time?", reply="Then the tide table is a body.", evidence_ids=[evidence_id, "not-real"])[1]
        assert saved["exchanges"] == 1 and saved["sources_recorded"] == 1
        again = tool("riff_record", thread_id=saved["thread_id"], you_said="go on", reply="A clock that regrows.")[1]
        assert again["exchanges"] == 2 and again["title"] == "Limb tides"

        sketched = tool("riff_sketch", thread_id=saved["thread_id"], title="Regrowing Clock", sketch="## What it is\\nA clock.", evidence_ids=[evidence_id])[1]
        assert (tmp_path / sketched["path"]).read_text().startswith("# Regrowing Clock")
        thread = tool("riff_thread", thread_id=saved["thread_id"])[1]
        assert [message["role"] for message in thread["messages"]] == ["you", "riff", "you", "riff"]
        assert thread["messages"][1]["sources"][0]["title"] == f"On {word}" and f"[mcp-" in thread["sketch"]
        assert tool("riff_threads")[1]["threads"][0]["distilled"] is True

    # What was said over MCP reaches the next digest like any other thread.
    assert any(f"what if {word} kept time?" in item["they_said"] for item in riffing.pulled_threads(database_url))
