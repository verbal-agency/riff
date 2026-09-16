import json
import os
from pathlib import Path

import pytest

from riff.adapter import AdapterError, RiffToolAdapter, USER_CONFIRMATION_TOKEN
from riff.db import connection, migrate
from riff.github_account import AccountScope, FixtureAccountFetcher, GitHubAccountError, GitHubAccountRepository


FIXTURE = Path(__file__).parent / "fixtures" / "github" / "account" / "account-v1.json"


def _payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_fetcher_replays_pages_without_network():
    fetcher = FixtureAccountFetcher(_payload())
    assert fetcher.fetch("/user").data["login"] == "seth-miller"
    assert len(fetcher.fetch("/user/repos", params={"page": 1}).data) == 4
    assert fetcher.fetch("/user/repos", params={"page": 2}).data == []
    assert fetcher.calls == [("/user", 1), ("/user/repos", 1), ("/user/repos", 2)]


@pytest.fixture()
def database_url():
    value = os.environ.get("RIFF_DATABASE_URL")
    if not value:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    migrate(value)
    with connection(value) as conn:
        conn.execute("UPDATE github_project_inventory SET account_observation_id = NULL, account_selection_id = NULL WHERE account_observation_id IS NOT NULL OR account_selection_id IS NOT NULL")
        conn.execute("DELETE FROM github_account_repository_selections")
        conn.execute("DELETE FROM github_account_observation_repositories")
        conn.execute("DELETE FROM github_account_observation_events")
        conn.execute("DELETE FROM github_account_observations")
        conn.execute("DELETE FROM github_project_inventory WHERE account_observation_id IS NOT NULL")
    return value


@pytest.mark.postgres
def test_account_observation_is_bounded_idempotent_and_token_safe(database_url):
    repository = GitHubAccountRepository(database_url)
    first = repository.observe(FixtureAccountFetcher(_payload()), consented_at=None)
    repeat = repository.observe(FixtureAccountFetcher(_payload()))
    assert first.observation_id == repeat.observation_id
    assert first.scope == AccountScope.PUBLIC_METADATA
    assert first.status == "ACTIVE"
    candidates = repository.repositories(first.observation_id)
    assert len(candidates) == 3  # one stable identity, plus two explicitly omitted entries
    riff = next(item for item in candidates if item["provider_repository_id"] == "4242")
    assert riff["full_name"] == "verbal-agency/riff-core"
    assert "verbal-agency/riff" in riff["aliases"]
    assert all("token" not in json.dumps(item, default=str).lower() for item in candidates)
    assert next(item for item in candidates if item["provider_repository_id"] == "4243")["availability"] == "OMITTED"
    assert next(item for item in candidates if item["provider_repository_id"] == "4244")["uncertainty"]["reason"] == "inaccessible"
    with connection(database_url) as conn:
        assert conn.execute("SELECT count(*) FROM github_account_observations").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM github_account_observation_repositories").fetchone()[0] == 3
    restarted = GitHubAccountRepository(database_url)
    assert restarted.get(first.observation_id).provider_account_id == "9001"


@pytest.mark.postgres
def test_selection_requires_confirmation_and_onboards_only_selected_repository(database_url):
    repository = GitHubAccountRepository(database_url)
    observation = repository.observe(FixtureAccountFetcher(_payload()))
    proposed = repository.propose_selection(observation.observation_id, "riff")
    assert proposed["status"] == "PROPOSED"
    with connection(database_url) as conn:
        assert conn.execute("SELECT count(*) FROM github_project_inventory WHERE account_observation_id = %s", (observation.observation_id,)).fetchone()[0] == 0
    adapter = RiffToolAdapter(database_url)
    with pytest.raises(AdapterError, match="confirmation"):
        adapter.call("github_account_onboard", {"observation_id": observation.observation_id, "repository": "riff"})
    onboarded = adapter.call("github_account_onboard", {"repository": "riff", "confirmation_token": USER_CONFIRMATION_TOKEN})["result"]
    assert onboarded["status"] == "ONBOARDED"
    with connection(database_url) as conn:
        row = conn.execute("SELECT account_observation_id, account_selection_id FROM github_project_inventory WHERE provider_repository_id = '4242'").fetchone()
        assert row[0] == observation.observation_id
        assert row[1] == onboarded["selection_id"]
        assert conn.execute("SELECT count(*) FROM github_project_inventory WHERE account_observation_id = %s", (observation.observation_id,)).fetchone()[0] == 1


@pytest.mark.postgres
def test_ambiguous_and_revoked_references_are_bounded_and_auditable(database_url):
    repository = GitHubAccountRepository(database_url)
    observation = repository.observe(FixtureAccountFetcher(_payload()))
    with pytest.raises(GitHubAccountError, match="ambiguous"):
        repository.propose_selection(observation.observation_id, "verbal-agency")
    revoked = repository.revoke(observation.observation_id)
    assert revoked.status == "REVOKED"
    # A revoked account cannot select, while its observation and repository
    # history remain available for audit.
    assert repository.repositories(observation.observation_id)
    with pytest.raises(GitHubAccountError, match="revoked"):
        repository.propose_selection(observation.observation_id, "riff")
    status = repository.status()
    assert status["observation"]["status"] == "REVOKED"
    assert any(event["event_type"] == "REVOKED" for event in status["events"])


@pytest.mark.postgres
def test_scope_narrowing_is_append_only_and_blocks_selection(database_url):
    repository = GitHubAccountRepository(database_url)
    observation = repository.observe(FixtureAccountFetcher(_payload()), scope=AccountScope.PUBLIC_METADATA_AND_ACTIVITY)
    narrowed = repository.narrow_scope(observation.observation_id)
    assert narrowed.status == "SCOPE_NARROWED"
    assert narrowed.scope == AccountScope.PUBLIC_METADATA
    with pytest.raises(GitHubAccountError, match="cannot be observed again"):
        repository.observe(FixtureAccountFetcher(_payload()), scope=AccountScope.PUBLIC_METADATA)
    with pytest.raises(GitHubAccountError, match="scope-narrowed"):
        repository.propose_selection(observation.observation_id, "riff")
    assert any(event["event_type"] == "SCOPE_NARROWED" for event in repository.status()["events"])
