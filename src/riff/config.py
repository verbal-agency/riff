"""Environment-backed application configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
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
    adapter_token: str | None = None
    mcp_allowed_hosts: tuple[str, ...] = ()
    mcp_allowed_origins: tuple[str, ...] = ()
    worker_lease_seconds: int = 15 * 60
    reasoning_provider: str = "deterministic"
    reasoning_model: str = "auto"
    reasoning_api_key: str | None = field(default=None, repr=False)
    reasoning_base_url: str = "https://api.openai.com/v1"
    reasoning_context_policy: str = "riff-context-v1"
    reasoning_fixture_path: str | None = None
    reasoning_max_calls: int = 5
    reasoning_max_input_tokens: int = 12_000
    reasoning_max_output_tokens: int = 6_000
    reasoning_max_cost_usd: float = 1.0
    reasoning_timeout_seconds: float = 60.0
    reasoning_input_cost_per_1k: float = 0.0
    reasoning_output_cost_per_1k: float = 0.0

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
        raw_worker_lease_seconds = source.get("RIFF_WORKER_LEASE_SECONDS", "900").strip()
        try:
            worker_lease_seconds = int(raw_worker_lease_seconds)
        except ValueError as exc:
            raise ConfigurationError("RIFF_WORKER_LEASE_SECONDS must be an integer between 1 and 86400") from exc
        if not 1 <= worker_lease_seconds <= 86_400:
            raise ConfigurationError("RIFF_WORKER_LEASE_SECONDS must be between 1 and 86400")
        log_level = source.get("RIFF_LOG_LEVEL", "INFO").strip().upper() or "INFO"
        adapter_token = source.get("RIFF_ADAPTER_TOKEN", "").strip() or None
        allowed_hosts = tuple(item.strip() for item in source.get("RIFF_MCP_ALLOWED_HOSTS", "").split(",") if item.strip())
        allowed_origins = tuple(item.strip() for item in source.get("RIFF_MCP_ALLOWED_ORIGINS", "").split(",") if item.strip())
        reasoning_provider = source.get("RIFF_REASONING_PROVIDER", "deterministic").strip().lower() or "deterministic"
        if reasoning_provider not in {"deterministic", "recorded", "openai"}:
            raise ConfigurationError("RIFF_REASONING_PROVIDER must be deterministic, recorded, or openai")
        reasoning_api_key = (source.get("RIFF_REASONING_API_KEY") or source.get("OPENAI_API_KEY") or source.get("OPEN_AI_API_KEY") or "").strip() or None
        if reasoning_provider == "openai" and not reasoning_api_key:
            raise ConfigurationError("OPENAI_API_KEY (or RIFF_REASONING_API_KEY) is required for openai reasoning")
        reasoning_fixture_path = source.get("RIFF_REASONING_FIXTURE", "").strip() or None
        try:
            reasoning_max_calls = int(source.get("RIFF_REASONING_MAX_CALLS", "5"))
            reasoning_max_input_tokens = int(source.get("RIFF_REASONING_MAX_INPUT_TOKENS", "12000"))
            reasoning_max_output_tokens = int(source.get("RIFF_REASONING_MAX_OUTPUT_TOKENS", "6000"))
            reasoning_max_cost_usd = float(source.get("RIFF_REASONING_MAX_COST_USD", "1.0"))
            reasoning_timeout_seconds = float(source.get("RIFF_REASONING_TIMEOUT_SECONDS", "60"))
            reasoning_input_cost_per_1k = float(source.get("RIFF_REASONING_INPUT_COST_PER_1K", "0"))
            reasoning_output_cost_per_1k = float(source.get("RIFF_REASONING_OUTPUT_COST_PER_1K", "0"))
        except ValueError as exc:
            raise ConfigurationError("reasoning budgets must be numeric") from exc
        if not 1 <= reasoning_max_calls <= 20 or not 1 <= reasoning_max_input_tokens <= 1_000_000 or not 1 <= reasoning_max_output_tokens <= 1_000_000 or reasoning_max_cost_usd < 0 or not 0.1 <= reasoning_timeout_seconds <= 600 or reasoning_input_cost_per_1k < 0 or reasoning_output_cost_per_1k < 0:
            raise ConfigurationError("reasoning budgets are outside their allowed bounds")
        return cls(
            database_url=database_url,
            environment=environment,
            log_level=log_level,
            adapter_token=adapter_token,
            mcp_allowed_hosts=allowed_hosts,
            mcp_allowed_origins=allowed_origins,
            worker_lease_seconds=worker_lease_seconds,
            reasoning_provider=reasoning_provider,
            reasoning_model=source.get("RIFF_REASONING_MODEL", "gpt-4o-mini" if reasoning_provider == "openai" else "auto").strip() or ("gpt-4o-mini" if reasoning_provider == "openai" else "deterministic-riff-v1"),
            reasoning_api_key=reasoning_api_key,
            reasoning_base_url=source.get("RIFF_REASONING_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/") or "https://api.openai.com/v1",
            reasoning_context_policy=source.get("RIFF_REASONING_CONTEXT_POLICY", "riff-context-v1").strip() or "riff-context-v1",
            reasoning_fixture_path=reasoning_fixture_path,
            reasoning_max_calls=reasoning_max_calls,
            reasoning_max_input_tokens=reasoning_max_input_tokens,
            reasoning_max_output_tokens=reasoning_max_output_tokens,
            reasoning_max_cost_usd=reasoning_max_cost_usd,
            reasoning_timeout_seconds=reasoning_timeout_seconds,
            reasoning_input_cost_per_1k=reasoning_input_cost_per_1k,
            reasoning_output_cost_per_1k=reasoning_output_cost_per_1k,
        )
