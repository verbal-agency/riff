from datetime import datetime, timezone

import pytest

from riff.evidence import (
    EvidenceSubmission,
    EvidenceValidationError,
    canonicalize_url,
    content_hash,
)


def test_canonicalize_url_removes_tracking_parameters_and_fragment():
    assert canonicalize_url(
        "HTTPS://Example.COM:443/article/?utm_source=feed&id=42&gclid=abc#comments"
    ) == "https://example.com/article?id=42"


def test_canonicalize_url_keeps_meaningful_query_parameters():
    assert canonicalize_url("https://example.com/search?z=2&a=1") == "https://example.com/search?a=1&z=2"


@pytest.mark.parametrize(
    "url",
    ["", "ftp://example.com/item", "https://user:password@example.com/item"],
)
def test_canonicalize_url_rejects_unsafe_or_invalid_urls(url):
    with pytest.raises(EvidenceValidationError):
        canonicalize_url(url)


def test_submission_calculates_and_validates_hash():
    submitted = EvidenceSubmission(
        source_id="source",
        canonical_url="https://example.com/item",
        raw_content="payload",
        retrieved_at=datetime(2026, 1, 1),
    ).validate()
    assert submitted.supplied_content_hash == content_hash("payload")
    assert submitted.retrieved_at.tzinfo == timezone.utc

    with pytest.raises(EvidenceValidationError, match="does not match"):
        EvidenceSubmission(
            source_id="source",
            canonical_url="https://example.com/item",
            raw_content="payload",
            supplied_content_hash="0" * 64,
        ).validate()


def test_snapshot_submission_requires_supplied_hash():
    with pytest.raises(EvidenceValidationError, match="supplied_content_hash"):
        EvidenceSubmission(
            source_id="source",
            canonical_url="https://example.com/item",
            snapshot_ref="s3://bucket/key",
        ).validate()

