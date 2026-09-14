"""Interface-agnostic HTTP application surface for the Riff foundation."""

from __future__ import annotations

from datetime import date
from dataclasses import asdict

from fastapi import Depends, FastAPI, HTTPException, status

from .config import Settings
from .db import database_ready
from .riffs import RiffRepository
from .decisions import DecisionRepository, DecisionError
from .explorations import ExplorationRepository, ExplorationError


def get_settings() -> Settings:
    return Settings.from_env()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the API without connecting to external systems."""

    app = FastAPI(title="Riff", version="0.1.0")
    configured_settings = settings

    def resolve_settings() -> Settings:
        return configured_settings or get_settings()

    @app.get("/health/live", tags=["health"])
    def live() -> dict[str, str]:
        return {"status": "ok", "service": "riff"}

    @app.get("/health/ready", tags=["health"])
    def ready(
        effective_settings: Settings = Depends(resolve_settings),
    ) -> dict[str, str]:
        if not database_ready(effective_settings.database_url):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="database is not ready",
            )
        return {"status": "ok", "database": "ready"}

    @app.get("/riffs/daily/{run_date}", tags=["riffs"])
    def daily_riffs(
        run_date: date,
        effective_settings: Settings = Depends(resolve_settings),
    ) -> dict:
        """Return the stable, persisted daily result; this endpoint never calls a model."""
        repository = RiffRepository(effective_settings.database_url)
        result = repository.daily_result(run_date)
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="daily Riff result not found")
        return result.to_dict()

    @app.get("/riffs/{riff_id}/investigation", tags=["riffs"])
    def investigate_riff(
        riff_id: str,
        effective_settings: Settings = Depends(resolve_settings),
    ) -> dict:
        try:
            return asdict(DecisionRepository(effective_settings.database_url).investigation(riff_id))
        except DecisionError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.post("/riffs/{riff_id}/decisions", tags=["riffs"])
    def decide_riff(
        riff_id: str,
        payload: dict,
        effective_settings: Settings = Depends(resolve_settings),
    ) -> dict:
        try:
            decision = DecisionRepository(effective_settings.database_url).record_decision(
                riff_id,
                str(payload.get("decision", "")),
                str(payload.get("reason", "")),
                actor=str(payload.get("actor", "user")),
                actor_kind=str(payload.get("actor_kind", "USER")),
                structured_reason=payload.get("structured_reason"),
                policy_version=str(payload.get("policy_version", "decision-policy-v1")),
            )
            return asdict(decision)
        except DecisionError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @app.post("/riffs/{riff_id}/explorations", tags=["explorations"])
    def create_exploration(
        riff_id: str,
        payload: dict,
        effective_settings: Settings = Depends(resolve_settings),
    ) -> dict:
        try:
            return ExplorationRepository(effective_settings.database_url).create(
                riff_id,
                actor=str(payload.get("actor", "user")),
                overlarge=bool(payload.get("overlarge", False)),
            ).to_dict()
        except ExplorationError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @app.get("/explorations/{exploration_id}", tags=["explorations"])
    def get_exploration(
        exploration_id: str,
        effective_settings: Settings = Depends(resolve_settings),
    ) -> dict:
        try:
            return ExplorationRepository(effective_settings.database_url).get(exploration_id).to_dict()
        except ExplorationError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    @app.post("/explorations/{exploration_id}/refine", tags=["explorations"])
    def refine_exploration(
        exploration_id: str,
        payload: dict,
        effective_settings: Settings = Depends(resolve_settings),
    ) -> dict:
        try:
            return ExplorationRepository(effective_settings.database_url).refine(
                exploration_id,
                str(payload.get("experiment_id", "")),
                str(payload.get("reason", "")),
                actor=str(payload.get("actor", "user")),
                actor_kind=str(payload.get("actor_kind", "USER")),
            ).to_dict()
        except ExplorationError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @app.post("/explorations/{exploration_id}/select", tags=["explorations"])
    def select_experiment(
        exploration_id: str,
        payload: dict,
        effective_settings: Settings = Depends(resolve_settings),
    ) -> dict:
        try:
            return ExplorationRepository(effective_settings.database_url).select_experiment(
                exploration_id,
                str(payload.get("experiment_id", "")),
                actor=str(payload.get("actor", "user")),
                actor_kind=str(payload.get("actor_kind", "USER")),
            ).to_dict()
        except ExplorationError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return app


app = create_app()
