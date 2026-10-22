import json

import httpx
import pytest

from riff.config import ConfigurationError, Settings
from riff.reasoning import BoundedReasoningProvider, OpenAIReasoningProvider, RecordedReasoningProvider, ReasoningLimits
from riff.riffs import DeterministicReasoningProvider, RiffContext, ReasoningProviderError


def _context():
    return RiffContext(
        "candidate-1", "durable-agent-execution", 0.8, "TREND_CANDIDATE",
        "Independent evidence describes resumable workflows.", ("daily-r1",),
        ({"receipt_id": "daily-r1", "summary": "Recovery is described."},), (), (),
        "SIGNALING_GAP", ("Temporal",),
    )


def test_recorded_provider_loads_schema_versioned_response(tmp_path):
    path = tmp_path / "reasoning.json"
    path.write_text(json.dumps({"schema_version": 1, "provider_version": "fixture-v1", "model": "fixture-model", "responses": {"default": {"recommendation": "x"}}}), encoding="utf-8")
    provider = RecordedReasoningProvider.from_path(path)
    assert provider.version == "fixture-v1"
    assert provider.generate(_context())["recommendation"] == "x"


def test_bounded_provider_records_fingerprint_usage_and_reuses_call():
    provider = BoundedReasoningProvider(DeterministicReasoningProvider(), model="test-model", limits=ReasoningLimits(max_calls=1, max_input_tokens=10000, max_output_tokens=10000))
    first = provider.generate(_context())
    second = provider.generate(_context())
    telemetry = provider.telemetry()
    assert first == second
    assert telemetry["calls"] == 1 and telemetry["cache_hits"] == 1
    assert telemetry["last_input_fingerprint"]
    assert telemetry["model"] == "test-model"


def test_bounded_provider_stops_before_second_distinct_call():
    provider = BoundedReasoningProvider(DeterministicReasoningProvider(), limits=ReasoningLimits(max_calls=1, max_input_tokens=10000, max_output_tokens=10000))
    provider.generate(_context())
    other = RiffContext("candidate-2", "other", 0.8, "TREND_CANDIDATE", "Other evidence.", ("daily-r1",), ({"receipt_id": "daily-r1", "summary": "Recovery is described."},), (), (), "UNKNOWN", ())
    with pytest.raises(ReasoningProviderError, match="call budget"):
        provider.generate(other)


def test_reasoning_configuration_is_bounded_and_provider_selectable():
    settings = Settings.from_env({
        "RIFF_DATABASE_URL": "postgresql://user:secret@localhost:5432/riff",
        "RIFF_REASONING_PROVIDER": "recorded",
        "RIFF_REASONING_FIXTURE": "tests/fixtures/reasoning/g42-recorded.json",
        "RIFF_REASONING_MAX_CALLS": "3",
    })
    assert settings.reasoning_provider == "recorded"
    assert settings.reasoning_max_calls == 3
    with pytest.raises(ConfigurationError, match="reasoning budgets"):
        Settings.from_env({"RIFF_DATABASE_URL": "postgresql://user:secret@localhost:5432/riff", "RIFF_REASONING_MAX_CALLS": "0"})


def _openai_draft():
    return {
        "observation": "Independent teams describe resumable workflows.",
        "hypothesis": "Resumable workflows may be a durable capability shift.",
        "why_now": "Recent evidence makes this worth reviewing.",
        "why_it_matters": "Reliable recovery changes how agent work is operated.",
        "user_relevance": "This is a signaling gap to investigate.",
        "underlying_capability": "durable-agent-execution",
        "recommendation": "Build a small resumability artifact.",
        "confidence": 0.7,
        "strongest_counterargument": "The evidence may reflect temporary vendor attention rather than durable demand.",
        "alternative_explanation": "A short release cycle could explain the observed concentration.",
        "falsification_conditions": ["Independent sources stop reporting this capability."],
        "associated_technologies": ["Temporal"],
        "supporting_receipt_ids": ["daily-r1"],
        "counter_receipt_ids": [],
        "citations": [{"receipt_id": "daily-r1", "claim_type": "OBSERVATION", "statement": "Recovery is described."}],
    }


def test_openai_provider_uses_responses_structured_output_without_exposing_key():
    seen = {}

    def handler(request):
        seen["authorization"] = request.headers["authorization"]
        seen["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(_openai_draft())}]}],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAIReasoningProvider("test-secret", "gpt-4o-mini", client=client)
    result = provider.generate(_context())

    assert result["supporting_receipt_ids"] == ["daily-r1"]
    assert seen["authorization"] == "Bearer test-secret"
    assert seen["payload"]["store"] is False
    assert seen["payload"]["text"]["format"]["strict"] is True
    assert "test-secret" not in json.dumps(seen["payload"])


def test_openai_configuration_accepts_standard_and_legacy_local_key_names():
    for key_name in ("OPENAI_API_KEY", "OPEN_AI_API_KEY"):
        settings = Settings.from_env({
            "RIFF_DATABASE_URL": "postgresql://user:secret@localhost:5432/riff",
            "RIFF_REASONING_PROVIDER": "openai",
            key_name: "test-secret",
        })
        assert settings.reasoning_provider == "openai"
        assert settings.reasoning_api_key == "test-secret"
        assert settings.reasoning_model == "gpt-4o-mini"
