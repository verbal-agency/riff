import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from riff.db import connection, migrate
from riff.evidence import (
    EvidenceSubmission,
    EvidenceValidationError,
    ProvenanceRelationship,
    SourceType,
)
from riff.evidence_repository import EvidenceRepository


@pytest.fixture()
def repository():
    database_url = os.environ.get("RIFF_DATABASE_URL")
    if not database_url:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    migrate(database_url)
    repo = EvidenceRepository(database_url)
    source = repo.create_source(SourceType.TECHNICAL_WRITING, f"test-{uuid4()}")
    return repo, source


def _submission(source_id, *, url="https://example.com/article?id=1&utm_source=test", native_id="item-1", content="first", published_day=1):
    return EvidenceSubmission(
        source_id=source_id,
        canonical_url=url,
        native_id=native_id,
        title="Example article",
        published_at=datetime(2026, 1, published_day, tzinfo=timezone.utc),
        raw_content=content,
        retrieval_metadata={"fixture": True},
    )


@pytest.mark.postgres
def test_duplicate_source_item_is_idempotent(repository):
    repo, source = repository
    first = repo.ingest(_submission(source.source_id))
    duplicate = repo.ingest(_submission(source.source_id))
    assert first.created is True
    assert duplicate.created is False
    assert duplicate.evidence_id == first.evidence_id
    assert duplicate.source_item_id == first.source_item_id
    assert repo.source_item_count(source.source_id) == 1

    with connection(repo.database_url) as conn:
        assert conn.execute(
            "select count(*) from retrievals where evidence_id = %s", (first.evidence_id,)
        ).fetchone()[0] == 2


@pytest.mark.postgres
def test_changed_content_creates_version(repository):
    repo, source = repository
    first = repo.ingest(_submission(source.source_id, content="first"))
    changed = repo.ingest(_submission(source.source_id, content="changed"))
    assert changed.created is True
    assert changed.version_of == first.evidence_id
    record = repo.get_evidence(changed.evidence_id, include_raw=True)
    assert record.raw_content == "changed"
    assert repo.get_evidence(first.evidence_id, include_raw=True).raw_content == "first"
    edges = repo.list_provenance(evidence_id=changed.evidence_id)
    assert [(edge.relationship, edge.to_id) for edge in edges] == [
        (ProvenanceRelationship.VERSION_OF, first.evidence_id)
    ]


@pytest.mark.postgres
def test_discovery_edge_preserves_root(repository):
    repo, root_source = repository
    discovery_source = repo.create_source(SourceType.DISCOVERY, f"discovery-{uuid4()}")
    root = repo.ingest(_submission(root_source.source_id, url="https://example.com/root", native_id="root", content="root"))
    discovery = repo.ingest(_submission(discovery_source.source_id, url="https://news.ycombinator.com/item?id=10", native_id="hn-10", content="link"))
    edge = repo.link_discovered_through(discovery.source_item_id, root.source_item_id)
    duplicate_edge = repo.link_discovered_through(discovery.source_item_id, root.source_item_id)
    assert edge.relationship == ProvenanceRelationship.DISCOVERED_THROUGH
    assert edge.from_id == discovery.source_item_id
    assert edge.to_id == root.source_item_id
    assert duplicate_edge.edge_id == edge.edge_id

    second_discovery = repo.ingest(_submission(discovery_source.source_id, url="https://news.ycombinator.com/item?id=11", native_id="hn-11", content="same link"))
    repo.link_discovered_through(second_discovery.source_item_id, root.source_item_id)
    assert len(repo.list_provenance(source_item_id=root.source_item_id)) == 2


@pytest.mark.postgres
def test_retrieve_by_id_and_search_metadata(repository):
    repo, source = repository
    evidence = repo.ingest(_submission(source.source_id, content="durable workflow recovery", published_day=3))
    record = repo.get_evidence(evidence.evidence_id)
    assert record.canonical_url == "https://example.com/article?id=1"
    assert record.raw_content is None
    assert record.content_hash
    assert repo.get_evidence(evidence.evidence_id, include_raw=True).raw_content == "durable workflow recovery"
    found = repo.search(source_type=SourceType.TECHNICAL_WRITING, text="recovery", published_after=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert any(item.evidence_id == evidence.evidence_id for item in found)


@pytest.mark.postgres
def test_url_variants_do_not_merge_distinct_native_items(repository):
    repo, source = repository
    first = repo.ingest(_submission(source.source_id, native_id="provider-a", content="a"))
    second = repo.ingest(_submission(source.source_id, native_id="provider-b", content="b"))
    assert first.source_item_id != second.source_item_id
    assert repo.source_item_count(source.source_id) == 2


@pytest.mark.postgres
def test_evidence_constraints_and_transaction_rollback(repository):
    repo, source = repository
    before = repo.source_item_count(source.source_id)
    with pytest.raises(EvidenceValidationError):
        repo.ingest(
            EvidenceSubmission(
                source_id=source.source_id,
                canonical_url="https://example.com/malformed",
                native_id="bad",
            )
        )
    assert repo.source_item_count(source.source_id) == before

    with connection(repo.database_url) as conn:
        with pytest.raises(Exception):
            conn.execute(
                "INSERT INTO provenance_edges (edge_id, relationship, from_source_item_id, to_source_item_id) "
                "VALUES ('bad-edge', 'VERSION_OF', 'missing', 'missing')"
            )
    with connection(repo.database_url) as conn:
        assert conn.execute("select count(*) from provenance_edges where edge_id = 'bad-edge'").fetchone()[0] == 0
