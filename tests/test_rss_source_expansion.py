import json
from datetime import datetime, timezone
from pathlib import Path

from riff.ingestion import parse_feed
from riff.source_manifest import load_manifest


ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "config" / "ingestion_sources.json"
REGISTRY = ROOT / "config" / "technical_sources.json"
FIXTURES = ROOT / "tests" / "fixtures" / "feeds" / "g16"


def test_g16_registry_contains_secret_free_pending_tier_one_sources():
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    sources = registry["sources"]
    expected = {
        "writing-openai-news",
        "writing-google-deepmind",
        "writing-google-research",
        "writing-huggingface",
        "writing-arxiv-cs-ai",
        "writing-arxiv-cs-lg",
        "writing-arxiv-cs-cl",
        "writing-arxiv-stat-ml",
        "writing-bair",
        "writing-mit-ai",
        "writing-aws-ml",
        "writing-opentelemetry",
        "writing-nist-taking-measure",
    }
    assert {source["source_id"] for source in sources} >= expected
    g16_sources = [source for source in sources if source["source_id"] in expected]
    assert len(g16_sources) == len(expected)
    assert all(source["source_type"] == "TECHNICAL_WRITING" for source in g16_sources)
    assert all(source["enabled"] is False for source in g16_sources)
    assert all(source["permission_status"] == "PENDING_REVIEW" for source in g16_sources)
    assert all(source["endpoint"].startswith(("https://", "http://")) for source in g16_sources)
    assert all(source["fixture_plan"].startswith("g16/") for source in g16_sources)


def test_g16_reviewed_manifest_inventory_matches_registry():
    manifest = load_manifest(MANIFEST)
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    inventory = manifest["rss_inventory"]
    g16_inventory = [source for source in inventory if source["source_id"].startswith("writing-") and source["source_id"] in {
        "writing-openai-news",
        "writing-google-deepmind",
        "writing-google-research",
        "writing-huggingface",
        "writing-arxiv-cs-ai",
        "writing-arxiv-cs-lg",
        "writing-arxiv-cs-cl",
        "writing-arxiv-stat-ml",
        "writing-bair",
        "writing-mit-ai",
        "writing-aws-ml",
        "writing-opentelemetry",
        "writing-nist-taking-measure",
    }]
    assert len(g16_inventory) == 13
    registry_by_id = {source["source_id"]: source for source in registry["sources"]}
    for source in g16_inventory:
        configured = registry_by_id[source["source_id"]]
        assert configured["endpoint"] == source["endpoint"]
        assert configured["source_root"] == source["source_root"]
        assert configured["source_class"] == source["artifact_class"]
        assert configured["permission_status"] == source["permission_status"]


def test_g16_manifest_rejects_incomplete_rss_inventory(tmp_path):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["rss_inventory"][0].pop("owner")
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    from riff.source_manifest import SourceManifestError

    try:
        load_manifest(path)
    except SourceManifestError as exc:
        assert "owner" in str(exc)
    else:
        raise AssertionError("incomplete RSS inventory was accepted")


def test_g16_feed_fixtures_cover_rss_atom_guid_and_paper_versions():
    fetched_at = datetime(2026, 9, 14, tzinfo=timezone.utc)
    standard = parse_feed((FIXTURES / "rss-standard.xml").read_bytes(), fetched_at=fetched_at)
    assert [entry.native_id for entry in standard] == ["g16-standard-1", "g16-standard-2"]

    guid_only = parse_feed((FIXTURES / "rss-guid-only.xml").read_bytes(), fetched_at=fetched_at)
    assert guid_only[0].native_id == "https://fixture.riff.local/g16/guid-only"
    assert guid_only[0].link == "https://fixture.riff.local/g16/guid-only"

    papers = parse_feed((FIXTURES / "rss-paper.xml").read_bytes(), fetched_at=fetched_at)
    assert [entry.native_id for entry in papers] == [
        "oai:arXiv.org:2609.00001v1",
        "oai:arXiv.org:2609.00001v2",
    ]
    assert [entry.link for entry in papers] == [
        "https://arxiv.org/abs/2609.00001v1",
        "https://arxiv.org/abs/2609.00001v2",
    ]

    atom = parse_feed(
        (FIXTURES / "atom-opentelemetry.xml").read_bytes(),
        fetched_at=fetched_at,
        base_url="https://opentelemetry.io/blog/index.xml",
    )
    assert atom[0].link == "https://opentelemetry.io/g16/otel-retries"


def test_g16_noisy_feed_remains_parseable_for_downstream_filtering():
    entries = parse_feed((FIXTURES / "rss-noisy.xml").read_bytes(), fetched_at=datetime.now(timezone.utc))
    assert len(entries) == 2
    assert "consumer" in (entries[0].content or "")
    assert "correlated" in (entries[1].content or "")


def test_g16_xml_body_is_parseable_when_provider_mime_is_wrong():
    entries = parse_feed(
        (FIXTURES / "rss-wrong-content-type.xml").read_bytes(),
        fetched_at=datetime.now(timezone.utc),
    )
    assert entries[0].native_id == "g16-mime-1"
