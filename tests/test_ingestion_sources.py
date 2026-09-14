import json
from pathlib import Path

import pytest

from riff.source_manifest import SourceManifestError, load_manifest, validate_manifest


MANIFEST = "config/ingestion_sources.json"


def test_manifest_has_required_source_categories():
    manifest = load_manifest(MANIFEST)
    categories = {entry["source_type"] for entry in manifest["sources"]}
    assert categories == {"TECHNICAL_WRITING", "GITHUB", "JOBS"}
    assert len(manifest["sources"]) >= 5


def test_manifest_entries_are_operationally_complete():
    manifest = load_manifest(MANIFEST)
    for entry in manifest["sources"]:
        assert entry["endpoint_or_scope"]
        assert entry["fixture_plan"]
        assert entry["rate_limit_policy"]
        assert entry["retention_mode"]


def test_manifest_fixture_and_rate_policy():
    manifest = load_manifest(MANIFEST)
    assert all(entry["fixture_plan"] and entry["rate_limit_policy"] for entry in manifest["sources"])


def test_manifest_rejects_credentials(tmp_path):
    payload = json.loads(Path(MANIFEST).read_text(encoding="utf-8"))
    payload["sources"][0]["endpoint_or_scope"] = "https://user:password@example.com/feed"
    with pytest.raises(SourceManifestError, match="credential"):
        validate_manifest(payload)


def test_manifest_records_fallbacks_and_correlation_policy():
    manifest = load_manifest(MANIFEST)
    assert "syndicated" in manifest["duplicate_policy"]
    assert all(entry["fallback"] for entry in manifest["sources"])
