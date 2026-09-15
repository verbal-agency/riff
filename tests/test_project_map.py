import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from psycopg.types.json import Jsonb

from riff.db import connection, migrate
from riff.evidence import SourceType
from riff.evidence_repository import EvidenceRepository
from riff.github_ingestion import GitHubIngestionRunner, GitHubResponse
from riff.ingestion_repository import IngestionRepository
from riff.project_map import ProjectInventory, ProjectMapError, ProjectMapRepository, _build_summary


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "github"


def _load(name: str):
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


class FixtureFetcher:
    def __init__(self, repository):
        self.repository = repository

    def fetch(self, path, *, params=None):
        page = int((params or {}).get("page", 1))
        if path.endswith("/releases"):
            return GitHubResponse(_load("releases-page-1.json") if page == 1 else [], {})
        if path.endswith("/issues"):
            return GitHubResponse(_load("issues-page-1.json") if page == 1 else [], {})
        if path.endswith("/contents/README.md"):
            return GitHubResponse(_load("readme-v1.json"), {})
        return GitHubResponse(self.repository, {})


def test_project_summary_parser_is_bounded_and_labels_unknowns():
    inventory = ProjectInventory("p-1", "42", "Demo", None, "ACTIVE", "PUBLIC", "APPROVED", "user", datetime(2026, 9, 15, tzinfo=timezone.utc))
    repo = ("42", "acme", "demo", "https://github.com/acme/demo", 4, {"description": "A workflow runtime"})
    artifacts = [
        {"evidence_id": "e-1", "provider_artifact_id": "repo:42", "artifact_type": "REPOSITORY", "canonical_url": repo[3], "author_login": None, "observed_at": datetime(2026, 9, 15, tzinfo=timezone.utc), "metadata": {}, "title": None, "content": "", "content_hash": "a" * 64},
        {"evidence_id": "e-2", "provider_artifact_id": "issue:1", "artifact_type": "ISSUE", "canonical_url": "https://github.com/acme/demo/issues/1", "author_login": "operator", "observed_at": datetime(2026, 9, 14, tzinfo=timezone.utc), "metadata": {"state": "open"}, "title": "Add checkpoint replay", "content": "x" * 100000, "content_hash": "b" * 64},
    ]
    summary = _build_summary(inventory, repo, artifacts, [])
    assert summary["purpose"]["status"] == "OBSERVED"
    assert summary["extension_seams"][0]["value"] == "Add checkpoint replay"
    assert {item["value"] for item in summary["unknowns"]} == {"ci_configuration", "implementation_depth"}
    assert all("evidence_ids" in claim and "parser_version" in claim for claim in summary["claims"])


@pytest.fixture()
def database_url():
    value = os.environ.get("RIFF_DATABASE_URL")
    if not value:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    migrate(value)
    return value


@pytest.mark.postgres
def test_project_inventory_snapshot_refresh_and_archive(database_url):
    source_id = f"g26-project-{uuid.uuid4().hex[:10]}"
    provider_id = str(700000 + int(uuid.uuid4().int % 900000))
    evidence = EvidenceRepository(database_url)
    ingestion = IngestionRepository(database_url)
    source = evidence.create_source(SourceType.GITHUB, "g26 project fixture", source_id=source_id)
    ingestion.configure_source(source.source_id, "https://api.github.com/repos/acme/riff-demo", cursor_kind="github:releases")
    payload = _load("repository.json") | {"id": int(provider_id), "full_name": f"acme/riff-{provider_id}", "html_url": f"https://github.com/acme/riff-{provider_id}"}
    GitHubIngestionRunner(ingestion, evidence, FixtureFetcher(payload), page_size=2).run(source_ids=[source_id])
    projects = ProjectMapRepository(database_url)
    project = projects.onboard(provider_id, display_name="Riff runtime", reviewed_by="operator")
    first = projects.refresh(project.project_id, retrieved_at=datetime(2026, 9, 15, tzinfo=timezone.utc))
    assert first.version == 1
    assert first.summary["purpose"]["value"] == "A durable agent runtime"
    assert first.summary["purpose"]["evidence_ids"]
    assert first.summary["activity"][0]["value"] == 2
    assert first.summary["extension_seams"][0]["value"] == "Replay after worker restart"
    assert all("evidence_ids" in claim and "parser_version" in claim for claim in first.summary["claims"])
    repeat = projects.refresh(project.project_id, retrieved_at=datetime(2026, 9, 16, tzinfo=timezone.utc))
    assert repeat.snapshot_id == first.snapshot_id
    with connection(database_url) as conn:
        conn.execute("UPDATE github_repositories SET metadata = metadata || %s WHERE provider_repository_id = %s", (Jsonb({"description": "A changed runtime"}), provider_id))
    changed = projects.refresh(project.project_id, retrieved_at=datetime(2026, 9, 17, tzinfo=timezone.utc))
    assert changed.version == 2 and changed.previous_snapshot_id == first.snapshot_id
    inspection = projects.inspect(project.project_id)
    assert inspection["latest_snapshot"]["snapshot_id"] == changed.snapshot_id
    assert [item["version"] for item in inspection["snapshot_history"]] == [1, 2]
    archived = projects.archive(project.project_id, reviewed_by="operator")
    assert archived.status == "ARCHIVED"
    with pytest.raises(ProjectMapError, match="archived"):
        projects.refresh(project.project_id)
