"""Interface-agnostic HTTP application surface for the Riff foundation."""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, status

from .config import Settings
from .db import database_ready


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

    return app


app = create_app()
