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
    "create_opportunity_context",
    "riff_execution_candidate",
    "select_execution_direction",
    "github_account_onboard",
    "github_monitor_watch",
    "github_monitor_disable",
    "github_search_review",
    "github_guidance_feedback",
    "github_project_goal_decision",
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

    def alternate_riffs(riff_id: str) -> dict[str, Any]:
        return dispatch("alternate_riffs", {"riff_id": riff_id})

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

    def map_riff_to_scenario(riff_id: str, scenario: str) -> dict[str, Any]:
        return dispatch("map_riff_to_scenario", {"riff_id": riff_id, "scenario": scenario})

    def github_account_status() -> dict[str, Any]:
        return dispatch("github_account_status", {})

    def github_account_repositories(observation_id: str = "", limit: int = 50) -> dict[str, Any]:
        arguments: dict[str, Any] = {"limit": limit}
        if observation_id:
            arguments["observation_id"] = observation_id
        return dispatch("github_account_repositories", arguments)

    def github_account_onboard(repository: str, confirmation_token: str, observation_id: str = "") -> dict[str, Any]:
        arguments: dict[str, Any] = {"repository": repository, "confirmation_token": confirmation_token}
        if observation_id:
            arguments["observation_id"] = observation_id
        return dispatch("github_account_onboard", arguments)

    def github_monitor_status() -> dict[str, Any]:
        return dispatch("github_monitor_status", {})

    def github_monitor_watch(repository: str, confirmation_token: str, cadence_seconds: int = 86400) -> dict[str, Any]:
        return dispatch("github_monitor_watch", {"repository": repository, "confirmation_token": confirmation_token, "cadence_seconds": cadence_seconds})

    def github_monitor_disable(watch_id: str, confirmation_token: str) -> dict[str, Any]:
        return dispatch("github_monitor_disable", {"watch_id": watch_id, "confirmation_token": confirmation_token})

    def github_search(query: str, limit: int = 20) -> dict[str, Any]:
        return dispatch("github_search", {"query": query, "limit": limit})

    def github_search_review(candidate_id: str, disposition: str, confirmation_token: str) -> dict[str, Any]:
        return dispatch("github_search_review", {"candidate_id": candidate_id, "disposition": disposition, "confirmation_token": confirmation_token})

    def github_guidance(project: str, profile: dict[str, Any] | None = None, decisions: list[dict[str, Any]] | None = None, opportunity: dict[str, Any] | None = None) -> dict[str, Any]:
        return dispatch("github_guidance", {"project": project, "profile": profile, "decisions": decisions or [], "opportunity": opportunity})

    def github_memory_audit(project: str, limit: int = 10) -> dict[str, Any]:
        return dispatch("github_memory_audit", {"project": project, "limit": limit})

    def github_guidance_feedback(guidance_id: str, decision: str, reason: str, confirmation_token: str, correction: dict[str, Any] | None = None) -> dict[str, Any]:
        return dispatch("github_guidance_feedback", {"guidance_id": guidance_id, "decision": decision, "reason": reason, "confirmation_token": confirmation_token, "correction": correction or {}})

    def github_project_goals(project: str) -> dict[str, Any]:
        return dispatch("github_project_goals", {"project": project})

    def github_goal_guidance(project: str, goal: str, profile: dict[str, Any] | None = None, decisions: list[dict[str, Any]] | None = None, opportunity: dict[str, Any] | None = None) -> dict[str, Any]:
        return dispatch("github_goal_guidance", {"project": project, "goal": goal, "profile": profile, "decisions": decisions or [], "opportunity": opportunity})

    def github_project_goal_decision(goal_version_id: str, event_type: str, reason: str, confirmation_token: str) -> dict[str, Any]:
        return dispatch("github_project_goal_decision", {"goal_version_id": goal_version_id, "event_type": event_type, "reason": reason, "confirmation_token": confirmation_token})

    def riff_context_packet(query: str, limit: int = 5, char_budget: int = 8000, page: int = 0, project: str | dict[str, Any] = "", goal: str | dict[str, Any] = "", seen_evidence_ids: list[str] | None = None) -> dict[str, Any]:
        return dispatch("riff_context_packet", {"query": query, "limit": limit, "char_budget": char_budget, "page": page, "project": project, "goal": goal, "seen_evidence_ids": seen_evidence_ids or []})

    def propose_extension(recommendation_id: str, confirmation_token: str) -> dict[str, Any]:
        return dispatch("propose_extension", {"recommendation_id": recommendation_id, "confirmation_token": confirmation_token})

    def override_recommendation(recommendation_id: str, disposition: str, reason: str, confirmation_token: str) -> dict[str, Any]:
        return dispatch(
            "override_recommendation",
            {"recommendation_id": recommendation_id, "disposition": disposition, "reason": reason, "confirmation_token": confirmation_token},
        )

    def create_opportunity_context(source_url: str, payload: str) -> dict[str, Any]:
        return dispatch("create_opportunity_context", {"source_url": source_url, "payload": payload})

    def inspect_opportunity(opportunity_id: str) -> dict[str, Any]:
        return dispatch("inspect_opportunity", {"opportunity_id": opportunity_id})

    def list_execution_candidates(opportunity_id: str) -> dict[str, Any]:
        return dispatch("list_execution_candidates", {"opportunity_id": opportunity_id})

    def riff_execution_candidate(candidate_id: str, operation: str, opportunity_id: str, other_candidate_id: str = "", constraint: str = "") -> dict[str, Any]:
        return dispatch("riff_execution_candidate", {"candidate_id": candidate_id, "operation": operation, "opportunity_id": opportunity_id, "other_candidate_id": other_candidate_id, "constraint": constraint})

    def compare_execution_candidates(opportunity_id: str) -> dict[str, Any]:
        return dispatch("compare_execution_candidates", {"opportunity_id": opportunity_id})

    def select_execution_direction(opportunity_id: str, candidate_id: str, reason: str, confirmation_token: str) -> dict[str, Any]:
        return dispatch("select_execution_direction", {"opportunity_id": opportunity_id, "candidate_id": candidate_id, "reason": reason, "confirmation_token": confirmation_token})

    functions = {
        "daily_riffs": daily_riffs,
        "alternate_riffs": alternate_riffs,
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
        "map_riff_to_scenario": map_riff_to_scenario,
        "github_account_status": github_account_status,
        "github_account_repositories": github_account_repositories,
        "github_account_onboard": github_account_onboard,
        "github_monitor_status": github_monitor_status,
        "github_monitor_watch": github_monitor_watch,
        "github_monitor_disable": github_monitor_disable,
        "github_search": github_search,
        "github_search_review": github_search_review,
        "github_guidance": github_guidance,
        "github_memory_audit": github_memory_audit,
        "github_guidance_feedback": github_guidance_feedback,
        "github_project_goals": github_project_goals,
        "github_goal_guidance": github_goal_guidance,
        "github_project_goal_decision": github_project_goal_decision,
        "riff_context_packet": riff_context_packet,
        "propose_extension": propose_extension,
        "override_recommendation": override_recommendation,
        "create_opportunity_context": create_opportunity_context,
        "inspect_opportunity": inspect_opportunity,
        "list_execution_candidates": list_execution_candidates,
        "riff_execution_candidate": riff_execution_candidate,
        "compare_execution_candidates": compare_execution_candidates,
        "select_execution_direction": select_execution_direction,
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
            "Promotion tools require explicit user confirmation and durable Riff state; never invent IDs. "
            "Keep stable IDs and tool names internal to the conversation, use prior results to resolve follow-up "
            "references, and ask for clarification rather than guessing an ambiguous or stale reference."
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
