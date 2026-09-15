import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import httpx

from riff.db import connection, migrate
from riff.evidence import SourceType
from riff.evidence_repository import EvidenceRepository
from riff.github_discovery import (
    FixtureDiscoveryFetcher,
    approve_candidates,
    discover,
    load_policy,
    promote_candidates,
)
from riff.github_ingestion import (
    GitHubPermanentError,
    GitHubIngestionRunner,
    GitHubRateLimitError,
    GitHubResponse,
    HttpGitHubFetcher,
)
from riff.ingestion_repository import IngestionRepository, RunStatus


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "github"


def _load(name: str):
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


class FixtureFetcher:
    def __init__(self, *, repository="repository.json", releases=None, readme="readme-v1.json", fail_once=None):
        self.repository = repository
        self.releases = releases or ["releases-page-1.json", "releases-page-2.json"]
        self.readme = readme
        self.fail_once = fail_once
        self.calls = []

    def fetch(self, path, *, params=None):
        page = int((params or {}).get("page", 1))
        self.calls.append((path, page))
        if self.fail_once == (path, page):
            self.fail_once = None
            raise GitHubRateLimitError("rate limited", reset_at="1778419200")
        if path.endswith("/releases"):
            filename = self.releases[page - 1] if page <= len(self.releases) else "issues-page-2.json"
            return GitHubResponse(_load(filename), {})
        if path.endswith("/issues"):
            filename = "issues-page-1.json" if page == 1 else "issues-page-2.json"
            return GitHubResponse(_load(filename), {})
        if path.endswith("/contents/README.md"):
            return GitHubResponse(_load(self.readme), {})
        return GitHubResponse(_load(self.repository), {})


@pytest.fixture()
def repositories():
    database_url = os.environ.get("RIFF_DATABASE_URL")
    if not database_url:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    migrate(database_url)
    ingestion = IngestionRepository(database_url)
    evidence = EvidenceRepository(database_url)
    source = evidence.create_source(SourceType.GITHUB, "fixture-github")
    ingestion.configure_source(source.source_id, "https://api.github.com/repos/acme/riff-demo", cursor_kind="github:releases")
    return database_url, ingestion, evidence, source


def _runner(ingestion, evidence, fetcher, **kwargs):
    return GitHubIngestionRunner(ingestion, evidence, fetcher, page_size=2, **kwargs)


def _text(value):
    return value.decode() if isinstance(value, bytes) else value


def test_http_fetcher_classifies_rate_limit_without_leaking_token():
    seen = {}

    def handler(request):
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(429, headers={"X-RateLimit-Reset": "1778419200"}, json={"message": "slow down"})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.github.com")
    fetcher = HttpGitHubFetcher(token="secret-token", client=client)
    with pytest.raises(GitHubRateLimitError) as error:
        fetcher.fetch("/repos/acme/riff-demo")
    assert seen["authorization"] == "Bearer secret-token"
    assert "secret-token" not in str(error.value)
    assert error.value.reset_at == "1778419200"


def test_http_fetcher_rejects_malformed_json_and_auth_failures():
    malformed = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"not-json")),
        base_url="https://api.github.com",
    )
    with pytest.raises(GitHubPermanentError, match="malformed JSON"):
        HttpGitHubFetcher(client=malformed).fetch("/repos/acme/riff-demo")

    unauthorized = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(401, json={"message": "bad credentials"})),
        base_url="https://api.github.com",
    )
    with pytest.raises(GitHubPermanentError, match="401"):
        HttpGitHubFetcher(client=unauthorized).fetch("/repos/acme/riff-demo")


@pytest.mark.postgres
def test_promoted_fixture_scope_reuses_g03_pipeline(repositories):
    database_url, ingestion, evidence, _ = repositories
    discovery_fixture = FIXTURE_DIR / "discovery" / "seed-responses-v1.json"
    policy = load_policy(
        {
            "schema_version": 1,
            "policy_id": "g25-integration-policy",
            "query_terms": ["durable execution"],
            "seed_source_ids": ["github-langgraph"],
            "capability_terms": ["durable execution"],
            "repository_seeds": ["acme/riff-runtime"],
            "max_queries": 1,
            "max_pages_per_query": 2,
            "max_candidates_per_query": 6,
            "max_requests": 4,
            "max_contributor_expansion": 0,
            "retry_limit": 1,
            "stop_rules": {"root_concentration_threshold": 0.25},
            "review_required": True,
            "enabled": False,
        }
    )
    queue = discover(
        policy,
        FixtureDiscoveryFetcher(discovery_fixture),
        fixture_id="g25-seed-inputs-v1",
    )
    approve_candidates(queue, ["repo:4242"])
    promoted = promote_candidates(
        queue,
        ["repo:4242"],
        confirmation="PROMOTE",
        config={"schema_version": 1, "sources": []},
    )
    entry = promoted["config"]["sources"][0]
    promoted_fixture = _load("discovery/promoted-scope-v1.json")
    assert entry == promoted_fixture["registry_entry"]
    assert entry["enabled"] is False
    assert entry["discovery_run_id"] == queue["run_id"]
    assert entry["provider_repository_id"] == "4242"
    # Keep repeated runs isolated from prior shared-development test data while
    # preserving the promoted registry shape and provenance assertions.
    source_id = f"{entry['source_id']}-test-{uuid.uuid4().hex[:12]}"

    source = evidence.create_source(
        SourceType.GITHUB,
        entry["name"],
        enabled=True,  # Explicit fixture-only opt-in for this integration proof.
        source_id=source_id,
    )
    configured = ingestion.configure_source(
        source.source_id,
        entry["endpoint"],
        enabled=True,
        cursor_kind="github:releases",
        metadata={
            "discovery_run_id": entry["discovery_run_id"],
            "discovered_by": entry["discovered_by"],
            "provider_repository_id": entry["provider_repository_id"],
            "correlation_metadata": entry["correlation_metadata"],
            "uncertainty": entry["uncertainty"],
        },
    )
    first = _runner(ingestion, evidence, FixtureFetcher()).run(
        source_ids=[configured.source_id],
        source_type=SourceType.GITHUB,
    )
    repeat = _runner(ingestion, evidence, FixtureFetcher()).run(
        source_ids=[configured.source_id],
        source_type=SourceType.GITHUB,
    )

    assert first.status == RunStatus.SUCCEEDED
    assert first.stored == 6
    assert repeat.status == RunStatus.SUCCEEDED
    assert repeat.stored == 0
    assert repeat.duplicates == 6
    records = evidence.search(source_id=configured.source_id, github_repository_id="4242")
    assert len(records) == 6
    with connection(database_url) as conn:
        source_metadata = conn.execute(
            "SELECT metadata FROM ingestion_source_configs WHERE source_id = %s",
            (configured.source_id,),
        ).fetchone()[0]
        retrieval_metadata = conn.execute(
            "SELECT r.metadata FROM retrievals r "
            "JOIN evidence_versions e ON e.evidence_id = r.evidence_id "
            "JOIN source_items si ON si.source_item_id = e.source_item_id "
            "WHERE si.source_id = %s AND si.native_id = '101' "
            "ORDER BY r.retrieved_at DESC LIMIT 1",
            (configured.source_id,),
        ).fetchone()[0]
    assert source_metadata["discovery_run_id"] == queue["run_id"]
    assert retrieval_metadata["discovery_run_id"] == queue["run_id"]
    assert retrieval_metadata["discovered_by"] == entry["discovered_by"]


@pytest.mark.postgres
def test_github_three_passes(repositories):
    _, ingestion, evidence, source = repositories
    first = _runner(ingestion, evidence, FixtureFetcher()).run(source_ids=[source.source_id])
    unchanged = _runner(ingestion, evidence, FixtureFetcher()).run(source_ids=[source.source_id])
    incremented = _runner(
        ingestion,
        evidence,
        FixtureFetcher(releases=["releases-new-page-1.json", "releases-page-2.json"], readme="readme-v2.json"),
    ).run(source_ids=[source.source_id])

    assert first.status == RunStatus.SUCCEEDED
    assert first.stored == 6  # repository, three releases, one issue, one README
    assert unchanged.status == RunStatus.SUCCEEDED
    assert unchanged.stored == 0
    assert incremented.status == RunStatus.SUCCEEDED
    assert incremented.stored == 2  # new release and README version
    assert evidence.source_item_count(source.source_id) == 8


@pytest.mark.postgres
def test_repository_rename_preserves_identity(repositories):
    database_url, ingestion, evidence, source = repositories
    _runner(ingestion, evidence, FixtureFetcher()).run(source_ids=[source.source_id])
    _runner(ingestion, evidence, FixtureFetcher(repository="repository-renamed.json", releases=["issues-page-2.json"], readme="readme-v1.json")).run(
        source_ids=[source.source_id]
    )
    with connection(database_url) as conn:
        row = conn.execute(
            "SELECT provider_repository_id, owner_login, name, canonical_url "
            "FROM github_repositories WHERE provider_repository_id = '4242'"
        ).fetchone()
        aliases = conn.execute(
            "SELECT canonical_url FROM github_repository_aliases "
            "WHERE provider_repository_id = '4242' ORDER BY canonical_url"
        ).fetchall()
    assert tuple(_text(item) for item in row) == ("4242", "newco", "riff-runtime", "https://github.com/newco/riff-runtime")
    assert {_text(item[0]) for item in aliases} == {
        "https://github.com/acme/riff-demo",
        "https://github.com/newco/riff-runtime",
    }


@pytest.mark.postgres
def test_rate_limit_preserves_cursor_until_retry(repositories):
    _, ingestion, evidence, source = repositories
    first = _runner(ingestion, evidence, FixtureFetcher(fail_once=("/repos/acme/riff-demo/releases", 2))).run(
        source_ids=[source.source_id]
    )
    assert first.status == RunStatus.PARTIAL
    assert ingestion.get_cursor(source.source_id, "github:releases") == '{"page":1}'

    retry = _runner(ingestion, evidence, FixtureFetcher()).run(source_ids=[source.source_id])
    assert retry.status == RunStatus.SUCCEEDED
    assert retry.stored == 1  # the durable page-two release
    assert ingestion.get_cursor(source.source_id, "github:releases") == '{"page":2}'


@pytest.mark.postgres
def test_mid_page_termination_replays_without_missing_items(repositories):
    database_url, ingestion, evidence, source = repositories
    class TerminatingEvidence:
        def __init__(self, delegate):
            self.delegate = delegate
            self.calls = 0

        def ingest(self, submission):
            result = self.delegate.ingest(submission)
            self.calls += 1
            if self.calls == 2:  # repository metadata, then first release in page one
                raise KeyboardInterrupt("simulated process termination")
            return result

    with pytest.raises(KeyboardInterrupt):
        _runner(ingestion, TerminatingEvidence(evidence), FixtureFetcher()).run(source_ids=[source.source_id])
    assert ingestion.get_cursor(source.source_id, "github:releases") is None
    retry = _runner(ingestion, evidence, FixtureFetcher()).run(source_ids=[source.source_id])
    assert retry.status == RunStatus.SUCCEEDED
    with connection(database_url) as conn:
        assert conn.execute(
            "SELECT count(*) FROM github_artifacts WHERE source_id = %s AND artifact_type = 'RELEASE'",
            (source.source_id,),
        ).fetchone()[0] == 3


@pytest.mark.postgres
def test_related_repository_flags_are_retained(repositories):
    database_url, ingestion, evidence, source = repositories
    runner = _runner(
        ingestion,
        evidence,
        FixtureFetcher(repository="repository-fork-bot.json", releases=["releases-fork-bot.json"], readme="readme-v1.json"),
    )
    runner.run(source_ids=[source.source_id])
    with connection(database_url) as conn:
        row = conn.execute(
            "SELECT is_fork, is_mirror, organization_login FROM github_repositories "
            "WHERE provider_repository_id = '5252'"
        ).fetchone()
        artifact = conn.execute(
            "SELECT author_login, author_type "
            "FROM github_artifacts WHERE provider_repository_id = '5252' AND artifact_type = 'RELEASE'"
        ).fetchone()
    assert (row[0], row[1], _text(row[2])) == (True, True, "acme")
    assert tuple(_text(item) for item in artifact) == ("dependabot[bot]", "Bot")


@pytest.mark.postgres
def test_oversized_artifact_is_truncated_and_referenced(repositories):
    database_url, ingestion, evidence, source = repositories
    runner = _runner(ingestion, evidence, FixtureFetcher(), content_limit=80)
    runner.run(source_ids=[source.source_id])
    with connection(database_url) as conn:
        row = conn.execute(
            "SELECT length(e.raw_content), e.snapshot_ref, ga.bounded "
            "FROM evidence_versions e JOIN github_artifacts ga ON ga.evidence_id = e.evidence_id "
            "WHERE ga.source_id = %s AND ga.artifact_type = 'RELEASE' ORDER BY ga.observed_at LIMIT 1",
            (source.source_id,),
        ).fetchone()
    assert row[0] <= 80
    assert row[1] is not None
    assert row[2] is True


@pytest.mark.postgres
def test_github_artifacts_are_traceable_and_searchable(repositories):
    _, ingestion, evidence, source = repositories
    _runner(ingestion, evidence, FixtureFetcher()).run(source_ids=[source.source_id])
    releases = evidence.search(source_id=source.source_id, github_repository_id="4242", github_artifact_type="RELEASE")
    org = evidence.search(source_id=source.source_id, github_organization="acme", published_after=datetime(2026, 9, 9, tzinfo=timezone.utc))
    assert len(releases) == 3
    assert releases[0].source_id == source.source_id
    assert any(item.native_id == "101" for item in releases)
    assert len(org) >= 4
