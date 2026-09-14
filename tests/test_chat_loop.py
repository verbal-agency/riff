import json
from pathlib import Path

import pytest

from riff.adapter import TOOL_SCHEMAS
from riff.chat_loop import (
    ChatLoopError,
    ChatToolLoop,
    FixtureToolAdapter,
    ModelToolCall,
    ModelResponse,
    ScriptedModelClient,
    ToolLoopPolicy,
    load_chat_fixture,
    model_tool_definitions,
)
from riff.cli import main


FIXTURE = Path(__file__).parent / "fixtures" / "chat" / "tool-loop-v1.json"


def test_tool_definitions_are_typed_and_annotate_mutations():
    fixture = load_chat_fixture(str(FIXTURE))
    definitions = model_tool_definitions(fixture["tools"])
    assert {item["name"] for item in definitions} == set(TOOL_SCHEMAS)
    daily = next(item for item in definitions if item["name"] == "daily_riffs")
    create = next(item for item in definitions if item["name"] == "create_exploration")
    assert daily["parameters"]["required"] == ["run_date"]
    assert daily["annotations"] == {"mutating": False, "requires_explicit_confirmation": False}
    assert create["annotations"] == {"mutating": True, "requires_explicit_confirmation": True}


def test_daily_tool_loop_returns_final_model_text_and_trace():
    fixture = load_chat_fixture(str(FIXTURE))
    scenario = next(item for item in fixture["scenarios"] if item["id"] == "daily")
    model = ScriptedModelClient(scenario["turns"])
    adapter = FixtureToolAdapter(fixture["tools"], scenario["adapter_results"])
    result = ChatToolLoop(model, adapter).run(scenario["user_message"], system_prompt=fixture["system_prompt"])
    assert result.status == "SUCCEEDED"
    assert result.tool_calls == 1 and result.turns == 2
    assert result.trace[0].name == "daily_riffs"
    assert adapter.calls[0]["arguments"] == {"run_date": "2026-09-14"}
    assert model.calls[1]["messages"][-1]["role"] == "tool"


def test_investigation_follow_up_returns_only_fixture_provenance_slice():
    fixture = load_chat_fixture(str(FIXTURE))
    scenario = next(item for item in fixture["scenarios"] if item["id"] == "investigate")
    model = ScriptedModelClient(scenario["turns"])
    adapter = FixtureToolAdapter(fixture["tools"], scenario["adapter_results"])
    result = ChatToolLoop(model, adapter).run(scenario["user_message"])
    assert result.status == "SUCCEEDED"
    assert result.trace[0].name == "investigate_riff"
    bounded = result.trace[0].result["result"]
    assert set(bounded) == {"riff_id", "strongest_evidence", "counterevidence", "provenance"}
    assert bounded["provenance"]["supporting_receipt_ids"] == ["receipt-1"]


def test_model_supplied_confirmation_token_is_not_trusted():
    fixture = load_chat_fixture(str(FIXTURE))
    scenario = next(item for item in fixture["scenarios"] if item["id"] == "confirmation-required")
    adapter = FixtureToolAdapter(fixture["tools"], scenario["adapter_results"])
    result = ChatToolLoop(ScriptedModelClient(scenario["turns"]), adapter).run(scenario["user_message"])
    assert result.trace[0].result["error"]["code"] == "CONFIRMATION_REQUIRED"
    assert adapter.calls == []


def test_explicit_confirmation_provider_overrides_model_token():
    fixture = load_chat_fixture(str(FIXTURE))
    scenario = next(item for item in fixture["scenarios"] if item["id"] == "confirmed-exploration")
    adapter = FixtureToolAdapter(fixture["tools"], scenario["adapter_results"])
    result = ChatToolLoop(
        ScriptedModelClient(scenario["turns"]),
        adapter,
        confirmation_provider=lambda _name, _args: "USER_CONFIRMED",
    ).run(scenario["user_message"])
    assert result.status == "SUCCEEDED"
    assert adapter.calls[0]["arguments"]["confirmation_token"] == "USER_CONFIRMED"


def test_unknown_and_invalid_tools_are_returned_as_bounded_tool_errors():
    tools = [{"name": "daily_riffs", "description": "Read daily Riffs.", "required": ("run_date",)}]
    model = ScriptedModelClient(
        [
            {"tool_calls": [{"call_id": "bad-1", "name": "missing", "arguments": {}}]},
            {"tool_calls": [{"call_id": "bad-2", "name": "daily_riffs", "arguments": {}}]},
            {"content": "I could not complete that request because the tool calls were invalid."},
        ]
    )
    adapter = FixtureToolAdapter(tools, {})
    result = ChatToolLoop(model, adapter).run("Try the tools.")
    assert [item.result["error"]["code"] for item in result.trace] == ["UNKNOWN_TOOL", "INVALID_ARGUMENTS"]
    assert adapter.calls == []


def test_adapter_failures_are_returned_as_deterministic_tool_errors():
    tools = [{"name": "daily_riffs", "description": "Read daily Riffs.", "required": ("run_date",)}]
    model = ScriptedModelClient(
        [
            {"tool_calls": [{"name": "daily_riffs", "arguments": {"run_date": "2026-09-14"}}]},
            {"content": "The adapter could not provide the requested result."},
        ]
    )
    adapter = FixtureToolAdapter(tools, {})
    result = ChatToolLoop(model, adapter).run("Read today's Riffs.")
    assert result.trace[0].result["error"]["code"] == "CHATLOOPERROR"


def test_tool_loop_enforces_turn_and_result_bounds():
    tools = [{"name": "daily_riffs", "description": "Read daily Riffs.", "required": ("run_date",)}]
    model = ScriptedModelClient(
        [
            {"tool_calls": [{"name": "daily_riffs", "arguments": {"run_date": "2026-09-14"}}]},
            {"tool_calls": [{"name": "daily_riffs", "arguments": {"run_date": "2026-09-14"}}]},
        ]
    )
    adapter = FixtureToolAdapter(tools, {"daily_riffs": {"result": "x" * 1000}})
    with pytest.raises(ChatLoopError, match="turn budget"):
        ChatToolLoop(model, adapter, policy=ToolLoopPolicy(max_turns=2, max_result_chars=256)).run("Loop.")
    assert adapter.calls == [
        {"name": "daily_riffs", "arguments": {"run_date": "2026-09-14"}},
        {"name": "daily_riffs", "arguments": {"run_date": "2026-09-14"}},
    ]


def test_tool_loop_reports_deterministic_timeout_code():
    now = [0.0]

    class SlowModel:
        def complete(self, messages, tools):
            now[0] = 2.0
            return ModelResponse(content="too late")

    with pytest.raises(ChatLoopError, match="timeout") as error:
        ChatToolLoop(
            SlowModel(),
            FixtureToolAdapter([], {}),
            policy=ToolLoopPolicy(max_seconds=1),
            clock=lambda: now[0],
        ).run("Wait.")
    assert error.value.code == "TIMEOUT"


def test_tool_loop_rejects_model_refusal_and_oversized_response():
    tools = []
    adapter = FixtureToolAdapter(tools, {})
    refusal = ScriptedModelClient([{"content": "No.", "finish_reason": "refusal"}])
    with pytest.raises(ChatLoopError, match="No") as error:
        ChatToolLoop(refusal, adapter).run("Do something unsafe.")
    assert error.value.code == "MODEL_REFUSAL"

    oversized = ScriptedModelClient([{"content": "x" * 257}])
    with pytest.raises(ChatLoopError, match="response exceeded") as error:
        ChatToolLoop(
            oversized,
            adapter,
            policy=ToolLoopPolicy(max_message_chars=256),
        ).run("Say it.")
    assert error.value.code == "RESPONSE_BUDGET_EXHAUSTED"


def test_chat_replay_cli_is_offline_and_prints_trace(capsys):
    assert main(["chat", "replay", "--file", str(FIXTURE), "--scenario", "daily"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["fixture_id"] == "chat-tool-loop-v1"
    assert output["scenario"] == "daily"
    assert output["trace"][0]["name"] == "daily_riffs"
