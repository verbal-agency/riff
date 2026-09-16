"""Native Model Context Protocol transport for the Riff tool adapter.

The MCP layer is deliberately thin: tool handlers call the same stateless
``RiffToolAdapter`` used by the HTTP connector, while FastMCP owns protocol
negotiation and Streamable HTTP framing.
"""

from __future__ import annotations

import hmac
import json
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from starlette.responses import JSONResponse

from .adapter import AdapterError, RiffToolAdapter, TOOL_SCHEMAS
from .config import Settings


_MUTATING_TOOLS = {
    "record_decision",
    "create_exploration",
    "refine_exploration",
    "select_experiment",
    "approve_prd",
    "generate_prd",
    "propose_extension",
    "override_recommendation",
}


class BearerAuthMiddleware:
    """Protect only the mounted MCP transport with the adapter token."""

    def __init__(self, app: Any, token: str | None):
        self.app = app
        self.token = token

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if self.token and scope.get("type") == "http" and str(scope.get("path", "")).startswith("/mcp"):
            headers = {key.lower(): value for key, value in scope.get("headers", [])}
            expected = f"Bearer {self.token}".encode("utf-8")
            if not hmac.compare_digest(headers.get(b"authorization", b""), expected):
                await JSONResponse(
                    {"detail": "adapter authentication required"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )(scope, receive, send)
                return
        await self.app(scope, receive, send)


def _annotations(name: str) -> ToolAnnotations:
    mutating = name in _MUTATING_TOOLS
    return ToolAnnotations(
        readOnlyHint=not mutating,
        destructiveHint=mutating,
        idempotentHint=not mutating,
        openWorldHint=False,
    )


def _register_tools(server: FastMCP, settings: Settings) -> None:
    adapter = RiffToolAdapter(settings.database_url)

    def dispatch(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = adapter.call(name, arguments)
        if len(json.dumps(result, sort_keys=True, default=str)) > 30_000:
            raise AdapterError("tool result exceeded the configured response bound")
        return result

    def daily_riffs(run_date: str) -> dict[str, Any]:
        return dispatch("daily_riffs", {"run_date": run_date})

    def investigate_riff(riff_id: str) -> dict[str, Any]:
        return dispatch("investigate_riff", {"riff_id": riff_id})

    def search_riffs(query: str) -> dict[str, Any]:
        return dispatch("search_riffs", {"query": query})

    def profile_lookup(capability_id: str) -> dict[str, Any]:
        return dispatch("profile_lookup", {"capability_id": capability_id})

    def capability_lookup(capability_id: str) -> dict[str, Any]:
        return dispatch("capability_lookup", {"capability_id": capability_id})

    def record_decision(riff_id: str, decision: str, reason: str) -> dict[str, Any]:
        return dispatch("record_decision", {"riff_id": riff_id, "decision": decision, "reason": reason})

    def create_exploration(riff_id: str, confirmation_token: str) -> dict[str, Any]:
        return dispatch("create_exploration", {"riff_id": riff_id, "confirmation_token": confirmation_token})

    def get_exploration(exploration_id: str) -> dict[str, Any]:
        return dispatch("get_exploration", {"exploration_id": exploration_id})

    def refine_exploration(exploration_id: str, experiment_id: str, reason: str, confirmation_token: str) -> dict[str, Any]:
        return dispatch(
            "refine_exploration",
            {"exploration_id": exploration_id, "experiment_id": experiment_id, "reason": reason, "confirmation_token": confirmation_token},
        )

    def select_experiment(exploration_id: str, experiment_id: str, confirmation_token: str) -> dict[str, Any]:
        return dispatch(
            "select_experiment",
            {"exploration_id": exploration_id, "experiment_id": experiment_id, "confirmation_token": confirmation_token},
        )

    def approve_prd(exploration_id: str, reason: str, confirmation_token: str) -> dict[str, Any]:
        return dispatch(
            "approve_prd",
            {"exploration_id": exploration_id, "reason": reason, "confirmation_token": confirmation_token},
        )

    def generate_prd(exploration_id: str) -> dict[str, Any]:
        return dispatch("generate_prd", {"exploration_id": exploration_id})

    def get_project(project_id: str) -> dict[str, Any]:
        return dispatch("get_project", {"project_id": project_id})

    def export_project(project_id: str) -> dict[str, Any]:
        return dispatch("export_project", {"project_id": project_id})

    def operation_report(run_id: str) -> dict[str, Any]:
        return dispatch("operation_report", {"run_id": run_id})

    def list_projects() -> dict[str, Any]:
        return dispatch("list_projects", {})

    def inspect_project(project_id: str) -> dict[str, Any]:
        return dispatch("inspect_project", {"project_id": project_id})

    def match_riff_to_projects(riff_id: str) -> dict[str, Any]:
        return dispatch("match_riff_to_projects", {"riff_id": riff_id})

    def propose_extension(recommendation_id: str, confirmation_token: str) -> dict[str, Any]:
        return dispatch("propose_extension", {"recommendation_id": recommendation_id, "confirmation_token": confirmation_token})

    def override_recommendation(recommendation_id: str, disposition: str, reason: str, confirmation_token: str) -> dict[str, Any]:
        return dispatch(
            "override_recommendation",
            {"recommendation_id": recommendation_id, "disposition": disposition, "reason": reason, "confirmation_token": confirmation_token},
        )

    functions = {
        "daily_riffs": daily_riffs,
        "investigate_riff": investigate_riff,
        "search_riffs": search_riffs,
        "profile_lookup": profile_lookup,
        "capability_lookup": capability_lookup,
        "record_decision": record_decision,
        "create_exploration": create_exploration,
        "get_exploration": get_exploration,
        "refine_exploration": refine_exploration,
        "select_experiment": select_experiment,
        "approve_prd": approve_prd,
        "generate_prd": generate_prd,
        "get_project": get_project,
        "export_project": export_project,
        "operation_report": operation_report,
        "list_projects": list_projects,
        "inspect_project": inspect_project,
        "match_riff_to_projects": match_riff_to_projects,
        "propose_extension": propose_extension,
        "override_recommendation": override_recommendation,
    }
    for name, function in functions.items():
        schema = TOOL_SCHEMAS[name]
        server.add_tool(
            function,
            name=name,
            description=schema["description"],
            annotations=_annotations(name),
            structured_output=True,
        )


def create_mcp_server(settings: Settings) -> FastMCP:
    """Build a stateless Streamable HTTP MCP server for one Riff config."""

    server = FastMCP(
        "Riff",
        instructions=(
            "Riff is a bounded capability-intelligence system. Read tools are safe to repeat. "
            "Promotion tools require explicit user confirmation and durable Riff state; never invent IDs."
        ),
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        host="127.0.0.1",
        transport_security=TransportSecuritySettings(
            allowed_hosts=list(settings.mcp_allowed_hosts)
            or ["127.0.0.1:*", "localhost:*", "[::1]:*"],
            allowed_origins=list(settings.mcp_allowed_origins)
            or ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"],
        ),
    )
    _register_tools(server, settings)
    return server


def create_service_app(settings: Settings):
    """Return the normal API with the native MCP endpoint mounted at ``/mcp``."""

    from .api import create_app

    app = create_app(settings)
    server = create_mcp_server(settings)
    mcp_app = server.streamable_http_app()
    manager = server.session_manager

    @asynccontextmanager
    async def lifespan(_app: Any):
        async with manager.run():
            yield

    # Mounted Starlette applications do not automatically inherit their
    # lifespan from FastAPI, so explicitly run the SDK session manager in the
    # service lifespan.
    app.router.lifespan_context = lifespan
    app.add_middleware(BearerAuthMiddleware, token=settings.adapter_token)
    # Mount at the router root so the SDK's canonical ``/mcp`` route is used
    # without Starlette's trailing-slash redirect (ChatGPT expects the exact
    # URL supplied by the operator).
    app.mount("/", mcp_app)
    return app
