from fastapi.testclient import TestClient

from riff.api import create_app
from riff.config import Settings
from riff.riffs import DailyResult
from datetime import date


def test_live_health_does_not_need_database(monkeypatch):
    def fail_if_called(_url):
        raise AssertionError("live health must not query the database")

    monkeypatch.setattr("riff.api.database_ready", fail_if_called)
    client = TestClient(create_app())
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "riff"}


def test_ready_health_reports_database_unavailable(monkeypatch):
    monkeypatch.setattr("riff.api.database_ready", lambda _url: False)
    settings = Settings("postgresql://user:password@localhost:5432/riff")
    response = TestClient(create_app(settings)).get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "database is not ready"}


def test_ready_health_reports_database_ready(monkeypatch):
    monkeypatch.setattr("riff.api.database_ready", lambda _url: True)
    settings = Settings("postgresql://user:password@localhost:5432/riff")
    response = TestClient(create_app(settings)).get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ready"}


def test_daily_riff_endpoint_returns_persisted_result_without_reasoning(monkeypatch):
    expected = DailyResult("run-1", date(2026, 9, 14), "riff-policy-v1", "fingerprint", "EMPTY", "No candidate met the quality threshold.", ())
    monkeypatch.setattr("riff.api.RiffRepository.daily_result", lambda _self, _date: expected)
    settings = Settings("postgresql://user:password@localhost:5432/riff")
    response = TestClient(create_app(settings)).get("/riffs/daily/2026-09-14")
    assert response.status_code == 200
    assert response.json()["daily_run_id"] == "run-1"
    assert response.json()["riffs"] == []
