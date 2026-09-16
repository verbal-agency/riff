import os
import uuid
from pathlib import Path

import pytest

from riff.data_governance import GovernanceError, ORIGINS, cleanup_apply, cleanup_preview, origin_report
from riff.db import connection, migrate
from riff.recommendations import RecommendationRepository


def test_origin_contract_includes_unclassified_and_non_live_classes():
    assert ORIGINS == {"LIVE", "FIXTURE", "TEST", "QUARANTINED", "UNCLASSIFIED"}


def test_cleanup_requires_owner_and_confirmation():
    with pytest.raises(GovernanceError):
        cleanup_preview("postgresql://invalid", origin="FIXTURE", owner="")


@pytest.mark.postgres
def test_owned_project_cleanup_is_repeatable_and_keeps_repository(requires_postgres):
    database_url = requires_postgres
    migrate(database_url)
    owner = "g35-test-" + uuid.uuid4().hex[:10]
    project_id = owner + "-project"
    with connection(database_url) as conn:
        row = conn.execute("SELECT provider_repository_id FROM github_repositories r WHERE NOT EXISTS (SELECT 1 FROM github_project_inventory i WHERE i.provider_repository_id=r.provider_repository_id) LIMIT 1").fetchone()
        if row is None:
            pytest.skip("no unassigned GitHub repository available")
        provider_id = row[0]
        conn.execute("INSERT INTO github_project_inventory (project_id,provider_repository_id,display_name,status,visibility,review_status,reviewed_by,reviewed_at,data_origin,origin_owner) VALUES (%s,%s,%s,'ACTIVE','PUBLIC','APPROVED','g35-test',now(),'TEST',%s)", (project_id, provider_id, "G35 test project", owner))
    assert project_id not in {item["project_id"] for item in RecommendationRepository(database_url).list_projects()}
    assert project_id in {item["project_id"] for item in RecommendationRepository(database_url).list_projects(include_non_live=True)}
    preview = cleanup_preview(database_url, origin="TEST", owner=owner)
    assert preview["plan"]["project_count"] == 1
    applied = cleanup_apply(database_url, origin="TEST", owner=owner, confirmation="CLEANUP")
    assert applied["deleted"]["projects"] == 1
    second = cleanup_preview(database_url, origin="TEST", owner=owner)
    assert second["plan"]["project_count"] == 0
    with connection(database_url) as conn:
        assert conn.execute("SELECT 1 FROM github_repositories WHERE provider_repository_id=%s", (provider_id,)).fetchone() is not None


@pytest.fixture()
def requires_postgres():
    database_url = os.environ.get("RIFF_DATABASE_URL")
    if not database_url:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    return database_url
