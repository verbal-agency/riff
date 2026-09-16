import json

from fastapi.testclient import TestClient

from riff.adapter import RiffToolAdapter
from riff.config import Settings
from riff.mcp_server import create_service_app


def _headers(token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _request(method: str, request_id: int = 1, **params: object) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}


def test_mcp_requires_bearer_token_and_preserves_other_api_routes():
    app = create_service_app(Settings("postgresql://riff:secret@localhost/riff", adapter_token="mcp-secret"))
    with TestClient(app, base_url="http://localhost:8000") as client:
        assert client.post("/mcp", headers=_headers()).status_code == 401
        assert client.get("/health/live").status_code == 200


def test_mcp_initialize_and_list_tools_expose_complete_catalog():
    app = create_service_app(Settings("postgresql://riff:secret@localhost/riff"))
    with TestClient(app, base_url="http://localhost:8000") as client:
        initialized = client.post(
            "/mcp",
            headers=_headers(),
            json=_request(
                "initialize",
                protocolVersion="2025-06-18",
                capabilities={},
                clientInfo={"name": "pytest", "version": "1"},
            ),
        )
        assert initialized.status_code == 200
        assert initialized.json()["result"]["serverInfo"]["name"] == "Riff"

        listed = client.post("/mcp", headers=_headers(), json=_request("tools/list"))
        assert listed.status_code == 200
        tools = listed.json()["result"]["tools"]
        assert {item["name"] for item in tools} == {
            "daily_riffs",
            "alternate_riffs",
            "investigate_riff",
            "search_riffs",
            "profile_lookup",
            "capability_lookup",
            "record_decision",
            "create_exploration",
            "get_exploration",
            "refine_exploration",
            "select_experiment",
            "approve_prd",
            "generate_prd",
            "get_project",
            "export_project",
            "operation_report",
            "list_projects",
            "inspect_project",
            "match_riff_to_projects",
            "map_riff_to_scenario",
            "propose_extension",
            "override_recommendation",
            "create_opportunity_context",
            "inspect_opportunity",
            "list_execution_candidates",
            "riff_execution_candidate",
            "compare_execution_candidates",
            "select_execution_direction",
        }
        by_name = {item["name"]: item for item in tools}
        assert by_name["daily_riffs"]["annotations"]["readOnlyHint"] is True
        assert by_name["create_exploration"]["annotations"]["readOnlyHint"] is False
        assert "confirmation_token" in by_name["create_exploration"]["inputSchema"]["required"]


def test_mcp_calls_reuse_adapter_and_missing_confirmation_is_non_mutating(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_call(self: RiffToolAdapter, name: str, arguments: dict[str, object]):
        calls.append((name, arguments))
        return {"tool": name, "result": {"riff_id": "riff-1"}}

    monkeypatch.setattr(RiffToolAdapter, "call", fake_call)
    app = create_service_app(Settings("postgresql://riff:secret@localhost/riff"))
    with TestClient(app, base_url="http://localhost:8000") as client:
        read = client.post(
            "/mcp",
            headers=_headers(),
            json=_request("tools/call", name="daily_riffs", arguments={"run_date": "2026-09-14"}),
        )
        assert read.status_code == 200
        assert read.json()["result"]["structuredContent"]["result"]["riff_id"] == "riff-1"

        missing = client.post(
            "/mcp",
            headers=_headers(),
            json=_request("tools/call", name="create_exploration", arguments={"riff_id": "riff-1"}),
        )
        assert missing.status_code == 200
        assert missing.json()["result"]["isError"] is True
        assert calls == [("daily_riffs", {"run_date": "2026-09-14"})]

        confirmed = client.post(
            "/mcp",
            headers=_headers(),
            json=_request(
                "tools/call",
                name="create_exploration",
                arguments={"riff_id": "riff-1", "confirmation_token": "USER_CONFIRMED"},
            ),
        )
        assert confirmed.json()["result"]["isError"] is False
        assert calls[-1] == ("create_exploration", {"riff_id": "riff-1", "confirmation_token": "USER_CONFIRMED"})


def test_mcp_unknown_tool_returns_typed_error_without_adapter_call(monkeypatch):
    monkeypatch.setattr(RiffToolAdapter, "call", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("adapter called")))
    app = create_service_app(Settings("postgresql://riff:secret@localhost/riff"))
    with TestClient(app, base_url="http://localhost:8000") as client:
        response = client.post(
            "/mcp",
            headers=_headers(),
            json=_request("tools/call", name="not_a_riff_tool", arguments={}),
        )
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["isError"] is True
    assert "not_a_riff_tool" in json.dumps(result)


def test_mcp_bounds_oversized_adapter_results(monkeypatch):
    def oversized(self: RiffToolAdapter, name: str, arguments: dict[str, object]):
        return {"tool": name, "result": {"raw": "x" * 31_000}}

    monkeypatch.setattr(RiffToolAdapter, "call", oversized)
    app = create_service_app(Settings("postgresql://riff:secret@localhost/riff"))
    with TestClient(app, base_url="http://localhost:8000") as client:
        response = client.post(
            "/mcp",
            headers=_headers(),
            json=_request("tools/call", name="daily_riffs", arguments={"run_date": "2026-09-14"}),
        )
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["isError"] is True
    assert "response bound" in json.dumps(result)
