"""Bounded HTTP connector for the provider-neutral Riff tool adapter."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping
from urllib.parse import urlparse

import httpx


class ConnectorError(ValueError):
    """A connector request or response could not be handled safely."""

    def __init__(self, message: str, *, code: str = "CONNECTOR_ERROR"):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ConnectorConfig:
    """Configuration for one Riff adapter origin.

    HTTP is accepted for loopback dogfooding only. Deployments should use an
    HTTPS origin and inject the bearer token through the environment.
    """

    base_url: str
    bearer_token: str | None = None
    timeout_seconds: float = 10.0
    max_response_bytes: int = 1_000_000

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ConnectorError("connector URL must be an HTTP(S) origin", code="INVALID_CONFIG")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ConnectorError("connector URL must not contain credentials, query, or fragment", code="INVALID_CONFIG")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ConnectorError("connector timeout must be positive", code="INVALID_CONFIG")
        if self.max_response_bytes < 256:
            raise ConnectorError("connector response bound is too small", code="INVALID_CONFIG")
        if self.bearer_token is not None and not self.bearer_token.strip():
            raise ConnectorError("connector bearer token cannot be blank", code="INVALID_CONFIG")


class HttpToolAdapter:
    """Implement ``ToolAdapter`` by calling Riff's existing HTTP endpoints.

    The client does not retry requests. In particular, mutation calls are sent
    at most once so a transient disconnect cannot duplicate a durable action.
    """

    def __init__(self, config: ConnectorConfig, *, client: httpx.Client | None = None):
        self.config = config
        self._client = client or httpx.Client(
            base_url=config.base_url.rstrip("/"),
            timeout=config.timeout_seconds,
            follow_redirects=False,
            headers=self._headers(config),
        )
        if client is not None:
            client.headers.update(self._headers(config))
        self._owns_client = client is None

    @staticmethod
    def _headers(config: ConnectorConfig) -> dict[str, str]:
        if config.bearer_token:
            return {"Authorization": f"Bearer {config.bearer_token}"}
        return {}

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "HttpToolAdapter":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def list_tools(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/adapter/tools")
        if payload.get("protocol") != "riff-tools-v1":
            raise ConnectorError("adapter protocol is unsupported", code="UNSUPPORTED_PROTOCOL")
        tools = payload.get("tools")
        if not isinstance(tools, list) or not tools:
            raise ConnectorError("adapter returned no tools", code="INVALID_RESPONSE")
        normalized: list[dict[str, Any]] = []
        for tool in tools:
            if not isinstance(tool, Mapping):
                raise ConnectorError("adapter returned an invalid tool definition", code="INVALID_RESPONSE")
            name = str(tool.get("name", "")).strip()
            description = str(tool.get("description", "")).strip()
            required = tool.get("required")
            if not name or not description or not isinstance(required, list):
                raise ConnectorError("adapter returned an invalid tool definition", code="INVALID_RESPONSE")
            normalized.append({"name": name, "description": description, "required": [str(item) for item in required]})
        return normalized

    def call(self, name: str, arguments: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if not name.strip():
            raise ConnectorError("tool name cannot be blank", code="INVALID_REQUEST")
        if any(part in name for part in ("/", "\\", "..")):
            raise ConnectorError("tool name contains an invalid path", code="INVALID_REQUEST")
        payload = self._request("POST", f"/adapter/tools/{name}", json=dict(arguments or {}))
        if not isinstance(payload, dict):
            raise ConnectorError("adapter returned an invalid tool result", code="INVALID_RESPONSE")
        return payload

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._client.request(method, path, **kwargs)
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > self.config.max_response_bytes:
                raise ConnectorError("adapter response exceeded the configured bound", code="RESPONSE_TOO_LARGE")
            body = response.content
            if len(body) > self.config.max_response_bytes:
                raise ConnectorError("adapter response exceeded the configured bound", code="RESPONSE_TOO_LARGE")
        except ConnectorError:
            raise
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ConnectorError("adapter connection failed", code="CONNECTOR_UNAVAILABLE") from exc
        except httpx.HTTPError as exc:
            raise ConnectorError("adapter HTTP request failed", code="CONNECTOR_HTTP_ERROR") from exc
        except (TypeError, ValueError) as exc:
            raise ConnectorError("adapter response was invalid", code="INVALID_RESPONSE") from exc

        if response.status_code < 200 or response.status_code >= 300:
            # Do not copy provider response bodies into traces: they may
            # contain credentials, private evidence, or raw prompts.
            raise ConnectorError(
                f"adapter request failed with HTTP {response.status_code}",
                code=f"HTTP_{response.status_code}",
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ConnectorError("adapter response was not JSON", code="INVALID_RESPONSE") from exc
        if not isinstance(payload, dict):
            raise ConnectorError("adapter response must be an object", code="INVALID_RESPONSE")
        return payload
