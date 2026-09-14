"""Environment-backed application configuration."""

from __future__ import annotations

from dataclasses import dataclass
from os import environ
from typing import Mapping
from urllib.parse import urlparse


class ConfigurationError(ValueError):
    """Raised when required configuration is absent or invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    environment: str = "development"
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, values: Mapping[str, str] | None = None) -> "Settings":
        source = environ if values is None else values
        database_url = source.get("RIFF_DATABASE_URL", "").strip()
        if not database_url:
            raise ConfigurationError(
                "RIFF_DATABASE_URL is required; copy .env.example or export a PostgreSQL URL"
            )

        parsed = urlparse(database_url)
        if parsed.scheme not in {"postgres", "postgresql"} or not parsed.netloc:
            raise ConfigurationError(
                "RIFF_DATABASE_URL must be a PostgreSQL URL such as "
                "postgresql://user:password@localhost:5432/riff"
            )

        environment = source.get("RIFF_ENV", "development").strip() or "development"
        log_level = source.get("RIFF_LOG_LEVEL", "INFO").strip().upper() or "INFO"
        return cls(database_url=database_url, environment=environment, log_level=log_level)

