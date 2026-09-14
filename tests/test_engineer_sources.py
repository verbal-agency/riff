import json
from pathlib import Path

import pytest

from riff.engineer_sources import EngineerSourceManifestError, load_manifest, validate_manifest


ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "config" / "engineer_sources.json"
CASES = ROOT / "tests" / "fixtures" / "engineer_sources" / "attribution_cases.json"


def test_engineer_manifest_contains_bounded_cross_theme_roster():
    manifest = load_manifest(MANIFEST)
    assert len(manifest["sources"]) >= 12
    themes = {theme for source in manifest["sources"] for theme in source["themes"]}
    assert {"workflow runtime", "agent frameworks", "observability", "AI evaluation", "distributed systems"} <= themes
    assert all(source["enabled"] is False for source in manifest["sources"])


def test_engineer_manifest_records_a_source_decision_for_every_person():
    manifest = load_manifest(MANIFEST)
    assert {source["machine_readable_status"] for source in manifest["sources"]} >= {"NATIVE_RSS", "PENDING_REVIEW", "NONE_FOUND"}
    for source in manifest["sources"]:
        assert source["canonical_url"].startswith("https://")
        assert source["fixture_plan"].startswith("engineer_sources/")
        assert (ROOT / "tests" / "fixtures" / source["fixture_plan"]).exists()
        assert source["correlation_group"]
        assert source["fallback"]


def test_engineer_attribution_fixture_covers_ambiguity_and_correlation_cases():
    payload = json.loads(CASES.read_text(encoding="utf-8"))
    expected = {case["expected"] for case in payload["cases"]}
    assert {"ACCEPT", "CORRELATE_EMPLOYER", "RETAIN_COAUTHOR_RELATION", "CORRELATE_SYNDICATION", "QUARANTINE_ATTRIBUTION"} <= expected
    assert len(payload["cases"]) >= 3


def test_engineer_manifest_rejects_enabled_or_credentialed_source(tmp_path):
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    payload["sources"][0]["enabled"] = True
    with pytest.raises(EngineerSourceManifestError, match="disabled"):
        validate_manifest(payload)
    payload["sources"][0]["enabled"] = False
    payload["sources"][0]["endpoint_or_scope"] = "https://user:password@example.com/feed"
    with pytest.raises(EngineerSourceManifestError, match="credential"):
        validate_manifest(payload)
