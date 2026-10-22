"""Provider selection and bounded telemetry for live Riff reasoning."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import httpx

from .riffs import DeterministicReasoningProvider, ReasoningProvider, ReasoningProviderError, RiffContext


@dataclass(frozen=True, slots=True)
class ReasoningLimits:
    max_calls: int = 5
    max_input_tokens: int = 12_000
    max_output_tokens: int = 6_000
    max_cost_usd: float = 1.0
    timeout_seconds: float = 60.0


class RecordedReasoningProvider:
    """Deterministic provider backed by a reviewed response fixture."""

    def __init__(self, payload: Mapping[str, Any]):
        if payload.get("schema_version") != 1:
            raise ValueError("reasoning fixture requires schema_version 1")
        self.version = str(payload.get("provider_version", "recorded-riff-v1"))
        self.model = str(payload.get("model", self.version))
        responses = payload.get("responses")
        if not isinstance(responses, Mapping):
            raise ValueError("reasoning fixture responses must be an object")
        self._responses = dict(responses)

    @classmethod
    def from_path(cls, path: str | Path) -> "RecordedReasoningProvider":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def generate(self, context: RiffContext) -> Mapping[str, Any]:
        output = self._responses.get(context.candidate_id) or self._responses.get(context.capability_id) or self._responses.get("default")
        if not isinstance(output, Mapping):
            raise ReasoningProviderError(f"recorded response missing for {context.candidate_id}")
        return dict(output)


class OpenAIReasoningProvider:
    """Call the OpenAI Responses API for one structured Riff draft.

    The provider only proposes a draft. Riff still validates receipt citations,
    provenance, confidence, and publication eligibility before persistence.
    """

    version = "openai-responses-v1"

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 60.0,
        client: httpx.Client | None = None,
    ):
        if not api_key.strip():
            raise ValueError("OpenAI API key is required")
        if not model.strip():
            raise ValueError("OpenAI reasoning model is required")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def generate(self, context: RiffContext) -> Mapping[str, Any]:
        payload = {
            "model": self.model,
            "store": False,
            "max_output_tokens": 2400,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "You produce one evidence-backed Riff draft. Use only the supplied context. "
                        "Do not invent evidence, receipt IDs, companies, or technologies. "
                        "Keep counterarguments genuine and distinguish observation, hypothesis, and recommendation."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(_context_payload(context), sort_keys=True, ensure_ascii=False),
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "riff_draft",
                    "strict": True,
                    "schema": _riff_draft_schema(),
                }
            },
        }
        try:
            response = self._client.post(
                f"{self.base_url}/responses",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        except httpx.TimeoutException as exc:
            raise ReasoningProviderError("OpenAI reasoning request timed out") from exc
        except httpx.HTTPError as exc:
            raise ReasoningProviderError(
                f"OpenAI reasoning request failed: {exc.__class__.__name__}"
            ) from exc
        except ValueError as exc:
            raise ReasoningProviderError("OpenAI reasoning response was not valid JSON") from exc

        if body.get("status") == "incomplete":
            reason = ((body.get("incomplete_details") or {}).get("reason") or "unknown")
            raise ReasoningProviderError(f"OpenAI reasoning response incomplete: {reason}")
        output_text = _response_text(body)
        if not output_text:
            raise ReasoningProviderError(
                "OpenAI reasoning response contained no structured output"
            )
        try:
            output = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise ReasoningProviderError(
                "OpenAI reasoning structured output was not valid JSON"
            ) from exc
        if not isinstance(output, Mapping):
            raise ReasoningProviderError(
                "OpenAI reasoning structured output was not an object"
            )
        return dict(output)


@dataclass(slots=True)
class ReasoningTelemetry:
    provider: str
    model: str
    context_policy_version: str
    calls: int = 0
    cache_hits: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    last_input_fingerprint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "context_policy_version": self.context_policy_version,
            "calls": self.calls,
            "cache_hits": self.cache_hits,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 8),
            "last_input_fingerprint": self.last_input_fingerprint,
        }


class BoundedReasoningProvider:
    """Apply call, token, timeout, and cost limits around a provider."""

    def __init__(self, provider: ReasoningProvider, *, model: str | None = None, context_policy_version: str = "riff-context-v1", limits: ReasoningLimits | None = None, input_cost_per_1k: float = 0.0, output_cost_per_1k: float = 0.0):
        self.provider = provider
        self.version = str(getattr(provider, "version", "unknown"))
        self.model = model or str(getattr(provider, "model", self.version))
        self.context_policy_version = context_policy_version
        self.limits = limits or ReasoningLimits()
        self.input_cost_per_1k = max(0.0, input_cost_per_1k)
        self.output_cost_per_1k = max(0.0, output_cost_per_1k)
        self._cache: dict[str, Mapping[str, Any]] = {}
        self._telemetry = ReasoningTelemetry(self.version, self.model, context_policy_version)

    def generate(self, context: RiffContext) -> Mapping[str, Any]:
        fingerprint = _context_fingerprint(context)
        self._telemetry.last_input_fingerprint = fingerprint
        if fingerprint in self._cache:
            self._telemetry.cache_hits += 1
            return dict(self._cache[fingerprint])
        if self._telemetry.calls >= self.limits.max_calls:
            raise ReasoningProviderError("reasoning call budget exhausted")
        input_tokens = _estimate_tokens(context)
        if self._telemetry.input_tokens + input_tokens > self.limits.max_input_tokens:
            raise ReasoningProviderError("reasoning input-token budget exhausted")
        started = time.monotonic()
        output = self.provider.generate(context)
        elapsed = time.monotonic() - started
        if elapsed > self.limits.timeout_seconds:
            raise ReasoningProviderError("reasoning provider timed out")
        if not isinstance(output, Mapping):
            raise ReasoningProviderError("reasoning provider returned a non-object")
        output_tokens = _estimate_tokens(output)
        if self._telemetry.output_tokens + output_tokens > self.limits.max_output_tokens:
            raise ReasoningProviderError("reasoning output-token budget exhausted")
        cost = (input_tokens * self.input_cost_per_1k + output_tokens * self.output_cost_per_1k) / 1000
        if self._telemetry.estimated_cost_usd + cost > self.limits.max_cost_usd:
            raise ReasoningProviderError("reasoning cost budget exhausted")
        self._cache[fingerprint] = dict(output)
        self._telemetry.calls += 1
        self._telemetry.input_tokens += input_tokens
        self._telemetry.output_tokens += output_tokens
        self._telemetry.estimated_cost_usd += cost
        return dict(output)

    def telemetry(self, *, input_fingerprint: str | None = None) -> dict[str, Any]:
        result = self._telemetry.to_dict()
        if input_fingerprint:
            result["input_fingerprint"] = input_fingerprint
        return result


def build_reasoning_provider(settings) -> BoundedReasoningProvider:
    provider_name = settings.reasoning_provider
    if provider_name == "deterministic":
        provider: ReasoningProvider = DeterministicReasoningProvider()
    elif provider_name == "recorded":
        if not settings.reasoning_fixture_path:
            raise ValueError("RIFF_REASONING_FIXTURE is required for recorded reasoning")
        provider = RecordedReasoningProvider.from_path(settings.reasoning_fixture_path)
    elif provider_name == "openai":
        provider = OpenAIReasoningProvider(
            settings.reasoning_api_key or "",
            settings.reasoning_model,
            base_url=settings.reasoning_base_url,
            timeout_seconds=settings.reasoning_timeout_seconds,
        )
    else:
        raise ValueError(f"unsupported reasoning provider: {provider_name}")
    return BoundedReasoningProvider(
        provider,
        model=None if settings.reasoning_model in {"", "auto"} else settings.reasoning_model,
        context_policy_version=settings.reasoning_context_policy,
        limits=ReasoningLimits(settings.reasoning_max_calls, settings.reasoning_max_input_tokens, settings.reasoning_max_output_tokens, settings.reasoning_max_cost_usd, settings.reasoning_timeout_seconds),
        input_cost_per_1k=settings.reasoning_input_cost_per_1k,
        output_cost_per_1k=settings.reasoning_output_cost_per_1k,
    )


def _estimate_tokens(value: Any) -> int:
    return max(1, (len(json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)) + 3) // 4)


def _context_fingerprint(context: RiffContext) -> str:
    payload = {"candidate_id": context.candidate_id, "capability_id": context.capability_id, "score": context.score, "classification": context.classification, "observation": context.observation, "receipt_ids": context.receipt_ids, "receipt_summaries": context.receipt_summaries, "profile_slice": context.profile_slice, "decision_ids": context.decision_ids, "profile_state": context.profile_state, "associated_technologies": context.associated_technologies}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _context_payload(context: RiffContext) -> dict[str, Any]:
    return {
        "candidate_id": context.candidate_id,
        "capability_id": context.capability_id,
        "candidate_score": context.score,
        "classification": context.classification,
        "observation": context.observation,
        "receipt_ids": list(context.receipt_ids),
        "receipt_summaries": list(context.receipt_summaries),
        "profile_slice": list(context.profile_slice),
        "decision_ids": list(context.decision_ids),
        "profile_state": context.profile_state,
        "associated_technologies": list(context.associated_technologies),
    }


def _response_text(body: Mapping[str, Any]) -> str | None:
    output_text = body.get("output_text")
    if isinstance(output_text, str):
        return output_text
    for item in body.get("output", []):
        if not isinstance(item, Mapping):
            continue
        for content in item.get("content", []):
            if not isinstance(content, Mapping):
                continue
            if content.get("type") == "refusal":
                raise ReasoningProviderError("OpenAI reasoning request was refused")
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return content["text"]
    return None


def _riff_draft_schema() -> dict[str, Any]:
    string_fields = {
        name: {"type": "string"}
        for name in (
            "observation",
            "hypothesis",
            "why_now",
            "why_it_matters",
            "user_relevance",
            "underlying_capability",
            "recommendation",
            "strongest_counterargument",
            "alternative_explanation",
        )
    }
    return {
        "type": "object",
        "properties": {
            **string_fields,
            "confidence": {"type": "number"},
            "falsification_conditions": {"type": "array", "items": {"type": "string"}},
            "associated_technologies": {"type": "array", "items": {"type": "string"}},
            "supporting_receipt_ids": {"type": "array", "items": {"type": "string"}},
            "counter_receipt_ids": {"type": "array", "items": {"type": "string"}},
            "citations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "receipt_id": {"type": "string"},
                        "claim_type": {"type": "string"},
                        "statement": {"type": "string"},
                    },
                    "required": ["receipt_id", "claim_type", "statement"],
                    "additionalProperties": False,
                },
            },
        },
        "required": [
            *string_fields,
            "confidence",
            "falsification_conditions",
            "associated_technologies",
            "supporting_receipt_ids",
            "counter_receipt_ids",
            "citations",
        ],
        "additionalProperties": False,
    }
