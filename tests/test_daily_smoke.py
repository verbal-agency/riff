import json
import os
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from riff.api import create_app
from riff.config import Settings
from riff.daily import load_fixture, run_fixture
from riff.db import connection, migrate


FIXTURE = "tests/fixtures/riffs/daily_inputs.json"


def test_daily_fixture_is_bounded_and_schema_versioned():
    fixture = load_fixture(FIXTURE)
    assert fixture.policy_version == "riff-policy-v1"
    assert len(fixture.candidates) == 3


def test_daily_fixture_rejects_unknown_receipt(tmp_path):
    payload = json.loads(Path(FIXTURE).read_text(encoding="utf-8"))
    payload["candidates"][0]["receipt_ids"] = ["not-in-fixture"]
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown fixture receipt"):
        load_fixture(path)


@pytest.fixture()
def database_url():
    value = os.environ.get("RIFF_DATABASE_URL")
    if not value:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    migrate(value)
    with connection(value) as conn:
        conn.execute("DELETE FROM riff_citations")
        conn.execute("DELETE FROM riffs")
        conn.execute("DELETE FROM riff_contexts")
        conn.execute("DELETE FROM daily_riff_runs")
    return value


@pytest.mark.postgres
def test_daily_smoke_zero_one_three(database_url):
    fixture = load_fixture(FIXTURE)
    assert run_fixture(database_url, fixture)["published_count"] == 3
    one = replace(fixture, run_date=date(2026, 9, 15), candidates=fixture.candidates[:1])
    assert run_fixture(database_url, one)["published_count"] == 1
    zero = replace(fixture, run_date=date(2026, 9, 16), candidates=tuple(replace(item, score=0.1) for item in fixture.candidates))
    output = run_fixture(database_url, zero)
    assert output["published_count"] == 0 and output["status"] == "EMPTY"


@pytest.mark.postgres
def test_daily_smoke_duplicate_is_cached(database_url):
    fixture = load_fixture(FIXTURE)
    first = run_fixture(database_url, fixture)
    second = run_fixture(database_url, fixture)
    assert first["cached"] is False
    assert second["cached"] is True and second["provider_calls"] == 0
    with connection(database_url) as conn:
        assert conn.execute("SELECT count(*) FROM daily_riff_runs").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM riffs").fetchone()[0] == 3


@pytest.mark.postgres
def test_daily_smoke_result_matches_api(database_url):
    fixture = load_fixture(FIXTURE)
    output = run_fixture(database_url, fixture)
    response = TestClient(create_app(Settings(database_url))).get("/riffs/daily/2026-09-14")
    assert response.status_code == 200
    assert response.json()["daily_run_id"] == output["run_id"]
    assert len(response.json()["riffs"]) == 3
