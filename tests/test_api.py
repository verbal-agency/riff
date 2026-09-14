from fastapi.testclient import TestClient

from riff.api import create_app
from riff.config import Settings


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

