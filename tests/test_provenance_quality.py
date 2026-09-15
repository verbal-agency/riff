from riff.provenance import POLICY_VERSION, assess_provenance


def receipt(receipt_id, *, url="https://example.com/article", source_type="TECHNICAL_WRITING", **metadata):
    content_hash = metadata.pop("content_hash", f"{receipt_id}-hash")
    return {
        "receipt_id": receipt_id,
        "title": "A sourced report",
        "canonical_url": url,
        "content_hash": content_hash,
        "source_metadata": {"source_type": source_type, **metadata},
    }


def test_fixture_only_evidence_is_explicitly_limited():
    quality = assess_provenance([receipt("fixture", url="https://fixture.riff.local/evidence/fixture", fixture=True)], candidate_score=0.95, generated_confidence=0.95)
    assert quality.state == "FIXTURE_ONLY"
    assert quality.evidence_quality < 0.1
    assert quality.epistemic_confidence <= 0.2
    assert quality.promotion_allowed is False
    assert any("synthetic" in item for item in quality.limitations)
    assert "not supported by production evidence" in quality.summary["interpretation"]


def test_single_source_does_not_win_by_receipt_count():
    items = [receipt(str(index), url=f"https://one.example/article-{index}", source_id="one") for index in range(4)]
    quality = assess_provenance(items, candidate_score=0.95, generated_confidence=0.95)
    assert quality.state == "SINGLE_SOURCE"
    assert quality.summary["independent_root_count"] == 1
    assert quality.epistemic_confidence <= 0.55


def test_independent_roots_and_source_diversity_raise_quality_but_keep_unknowns():
    items = [
        receipt("a", url="https://a.example/a", source_type="TECHNICAL_WRITING", organization="A", author="Ada"),
        receipt("b", url="https://b.example/b", source_type="GITHUB", organization="B", author="Bea"),
    ]
    quality = assess_provenance(items, candidate_score=0.9, generated_confidence=0.9)
    assert quality.state == "SUPPORTED"
    assert quality.summary["independent_root_count"] == 2
    assert quality.summary["source_type_count"] == 2
    assert quality.evidence_quality >= 0.7
    assert quality.policy_version == POLICY_VERSION


def test_counterevidence_and_duplicate_content_are_visible():
    support = [receipt("a", url="https://a.example/a", content_hash="same")]
    support.append(receipt("b", url="https://b.example/b", content_hash="same"))
    counter = [receipt("c", url="https://c.example/c", source_type="JOBS")]
    quality = assess_provenance(support, counter, candidate_score=0.9, generated_confidence=0.9)
    assert quality.state == "CONTRADICTORY"
    assert quality.summary["duplicate_content_count"] == 1
    assert quality.summary["counterevidence_count"] == 1
    assert quality.promotion_allowed is False
