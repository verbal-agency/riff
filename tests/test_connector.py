import httpx
import pytest
from fastapi.testclient import TestClient
import json
import os

from riff.api import create_app
from riff.config import Settings
from riff.connector import ConnectorConfig, ConnectorError, HttpToolAdapter
from riff.daily import load_fixture, run_fixture
from riff.db import connection, migrate
from riff.decisions import DecisionRepository
from riff.chat_loop import ChatToolLoop, ModelResponse, ModelToolCall
from riff.chat_loop import ToolLoopPolicy


TOOLS = [{"name": "daily_riffs", "description": "Read daily Riffs.", "required": ["run_date"]}]


def test_http_connector_discovers_and_calls_tools_without_retrying_mutations():
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        assert request.headers.get("authorization") == "Bearer secret"
        if request.method == "GET":
            return httpx.Response(200, json={"protocol": "riff-tools-v1", "tools": TOOLS}, request=request)
        return httpx.Response(200, json={"tool": "record_decision", "result": {"decision_id": "decision-1"}}, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://riff.example")
    adapter = HttpToolAdapter(ConnectorConfig("https://riff.example", bearer_token="secret"), client=client)
    assert adapter.list_tools() == TOOLS
    result = adapter.call("record_decision", {"riff_id": "riff-1", "decision": "REJECT", "reason": "not now"})
    assert result["result"]["decision_id"] == "decision-1"
    assert calls == [("GET", "/adapter/tools"), ("POST", "/adapter/tools/record_decision")]
    assert client.headers["authorization"] == "Bearer secret"
    client.close()


def test_http_connector_rejects_unsupported_protocol():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"protocol": "other-v1", "tools": TOOLS}, request=request)

    with HttpToolAdapter(
        ConnectorConfig("https://riff.example"),
        client=httpx.Client(transport=httpx.MockTransport(handler), base_url="https://riff.example"),
    ) as adapter:
        with pytest.raises(ConnectorError, match="unsupported") as error:
            adapter.list_tools()
    assert error.value.code == "UNSUPPORTED_PROTOCOL"


def test_http_connector_rejects_path_like_tool_names_without_network_call():
    client = httpx.Client(transport=httpx.MockTransport(lambda request: pytest.fail("network call was made")), base_url="https://riff.example")
    with HttpToolAdapter(ConnectorConfig("https://riff.example"), client=client) as adapter:
        with pytest.raises(ConnectorError, match="invalid path") as error:
            adapter.call("../secret", {})
    assert error.value.code == "INVALID_REQUEST"


def test_http_connector_bounds_responses_and_sanitizes_http_errors():
    def oversized(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 300, headers={"content-length": "300"}, request=request)

    with HttpToolAdapter(
        ConnectorConfig("https://riff.example", max_response_bytes=256),
        client=httpx.Client(transport=httpx.MockTransport(oversized), base_url="https://riff.example"),
    ) as adapter:
        with pytest.raises(ConnectorError, match="exceeded") as error:
            adapter.list_tools()
    assert error.value.code == "RESPONSE_TOO_LARGE"

    def unauthorized(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, content=b"password=should-not-appear", request=request)

    with HttpToolAdapter(
        ConnectorConfig("https://riff.example"),
        client=httpx.Client(transport=httpx.MockTransport(unauthorized), base_url="https://riff.example"),
    ) as adapter:
        with pytest.raises(ConnectorError) as error:
            adapter.list_tools()
    assert error.value.code == "HTTP_401"
    assert "password" not in str(error.value)


def test_adapter_bearer_auth_is_optional_for_local_and_enforced_when_configured():
    settings = Settings("postgresql://user:password@localhost:5432/riff", adapter_token="adapter-secret")
    client = TestClient(create_app(settings))
    assert client.get("/adapter/tools").status_code == 401
    assert client.get("/adapter/tools", headers={"Authorization": "Bearer wrong"}).status_code == 401
    response = client.get("/adapter/tools", headers={"Authorization": "Bearer adapter-secret"})
    assert response.status_code == 200
    assert response.json()["protocol"] == "riff-tools-v1"


class _FastApiTransport(httpx.BaseTransport):
    def __init__(self, app):
        self._client = TestClient(app)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = self._client.request(
            request.method,
            request.url.path,
            headers=dict(request.headers),
            content=request.content,
        )
        return httpx.Response(
            response.status_code,
            headers=dict(response.headers),
            content=response.content,
            request=request,
        )


class _PromoteModel:
    """Deterministic model that threads durable IDs through every tool turn."""

    def __init__(self, riff_id: str):
        self.riff_id = riff_id
        self.exploration_id: str | None = None
        self.experiment_id: str | None = None
        self.project_id: str | None = None
        self.step = 0

    def complete(self, messages, tools):
        self.step += 1
        if self.step == 1:
            return ModelResponse(tool_calls=(ModelToolCall("daily", "daily_riffs", {"run_date": "2026-09-14"}),))
        if self.step == 2:
            return ModelResponse(tool_calls=(ModelToolCall("inspect", "investigate_riff", {"riff_id": self.riff_id}),))
        if self.step == 3:
            return ModelResponse(tool_calls=(ModelToolCall("decision", "record_decision", {"riff_id": self.riff_id, "decision": "APPROVE_EXPLORATION", "reason": "User wants a bounded experiment."}),))
        if self.step == 4:
            return ModelResponse(tool_calls=(ModelToolCall("explore", "create_exploration", {"riff_id": self.riff_id, "confirmation_token": "model-token"}),))
        if self.step == 5:
            payload = json.loads(messages[-1]["content"])["result"]
            self.exploration_id = payload["exploration_id"]
            self.experiment_id = payload["possible_experiments"][0]["experiment_id"]
            return ModelResponse(tool_calls=(ModelToolCall("select", "select_experiment", {"exploration_id": self.exploration_id, "experiment_id": self.experiment_id, "confirmation_token": "model-token"}),))
        if self.step == 6:
            return ModelResponse(tool_calls=(ModelToolCall("approve", "approve_prd", {"exploration_id": self.exploration_id, "reason": "User approves this project.", "confirmation_token": "model-token"}),))
        if self.step == 7:
            return ModelResponse(tool_calls=(ModelToolCall("generate", "generate_prd", {"exploration_id": self.exploration_id}),))
        if self.step == 8:
            payload = json.loads(messages[-1]["content"])["result"]
            self.project_id = payload["project_id"]
            return ModelResponse(tool_calls=(ModelToolCall("export", "export_project", {"project_id": self.project_id}),))
        return ModelResponse(content="The evidence was inspected, approved, and exported with durable Riff IDs.")


@pytest.fixture()
def persisted_graph():
    database_url = os.environ.get("RIFF_DATABASE_URL")
    if not database_url:
        pytest.skip("set RIFF_DATABASE_URL to run Postgres integration tests")
    migrate(database_url)
    with connection(database_url) as conn:
        conn.execute("UPDATE explorations SET selected_experiment_id = NULL")
        for table in ("project_versions", "project_goals", "projects", "prd_approvals", "exploration_events", "exploration_versions", "exploration_experiments", "explorations", "riff_resurface_events", "riff_status_history", "riff_decisions", "riff_citations", "riffs", "riff_contexts", "daily_riff_runs"):
            conn.execute(f"DELETE FROM {table}")
    run_fixture(database_url, load_fixture("tests/fixtures/riffs/daily_inputs.json"))
    with connection(database_url) as conn:
        riff_id = str(conn.execute("SELECT riff_id FROM riffs ORDER BY rank LIMIT 1").fetchone()[0])
    yield database_url, riff_id
    with connection(database_url) as conn:
        conn.execute("UPDATE explorations SET selected_experiment_id = NULL")
        for table in ("project_versions", "project_goals", "projects", "prd_approvals", "exploration_events", "exploration_versions", "exploration_experiments", "explorations", "riff_resurface_events", "riff_status_history", "riff_decisions", "riff_citations", "riffs", "riff_contexts", "daily_riff_runs"):
            conn.execute(f"DELETE FROM {table}")


@pytest.mark.postgres
def test_http_connector_runs_read_promote_export_against_persisted_postgres(persisted_graph):
    database_url, riff_id = persisted_graph
    from riff.api import create_app
    from riff.config import Settings

    app = create_app(Settings(database_url, adapter_token="connector-secret"))
    http = httpx.Client(transport=_FastApiTransport(app), base_url="http://riff.test")
    model = _PromoteModel(riff_id)
    with HttpToolAdapter(ConnectorConfig("http://riff.test", bearer_token="connector-secret"), client=http) as adapter:
        result = ChatToolLoop(
            model,
            adapter,
            policy=ToolLoopPolicy(max_turns=10),
            confirmation_provider=lambda _name, _args: "USER_CONFIRMED",
        ).run("Inspect today's Riff, approve a bounded exploration, and export the project.")
        assert result.status == "SUCCEEDED"
        assert [item.name for item in result.trace] == ["daily_riffs", "investigate_riff", "record_decision", "create_exploration", "select_experiment", "approve_prd", "generate_prd", "export_project"]
        assert model.exploration_id and model.project_id
        assert result.trace[1].result["result"].get("profile_slice") is None
        assert result.trace[-1].result["result"]["project_id"] == model.project_id
        assert adapter.call("get_project", {"project_id": model.project_id})["result"]["project_id"] == model.project_id
    with connection(database_url) as conn:
        assert conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM prd_approvals").fetchone()[0] == 1
