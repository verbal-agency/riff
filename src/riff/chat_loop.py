"""Provider-neutral conversational tool loop for the Riff adapter."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Mapping, Protocol, Sequence


class ChatLoopError(ValueError):
    """The model/tool conversation cannot continue safely."""


class ConfirmationRequired(ChatLoopError):
    """A mutating tool needs an explicit user confirmation."""

    def __init__(self, tool_name: str):
        super().__init__(f"explicit user confirmation is required for {tool_name}")
        self.tool_name = tool_name


class ModelClient(Protocol):
    """Small boundary implemented by a ChatGPT/model provider client."""

    def complete(
        self,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
    ) -> "ModelResponse":
        """Return one model turn without calling Riff directly."""


class ToolAdapter(Protocol):
    """The Riff adapter surface consumed by the loop."""

    def list_tools(self) -> list[dict[str, Any]]:
        ...

    def call(self, name: str, arguments: Mapping[str, Any] | None = None) -> dict[str, Any]:
        ...


ConfirmationProvider = Callable[[str, Mapping[str, Any]], str | None]


@dataclass(frozen=True, slots=True)
class ModelToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ModelResponse:
    content: str | None = None
    tool_calls: tuple[ModelToolCall, ...] = ()
    finish_reason: str = "stop"


@dataclass(frozen=True, slots=True)
class ToolLoopPolicy:
    max_turns: int = 8
    max_tool_calls: int = 12
    max_result_chars: int = 30_000
    max_message_chars: int = 40_000

    def __post_init__(self) -> None:
        if self.max_turns < 1 or self.max_tool_calls < 1:
            raise ValueError("tool-loop bounds must be positive")
        if self.max_result_chars < 256 or self.max_message_chars < 256:
            raise ValueError("tool-loop character bounds are too small")


@dataclass(frozen=True, slots=True)
class ToolTrace:
    call_id: str
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ChatLoopResult:
    status: str
    final_text: str
    tool_calls: int
    turns: int
    trace: tuple[ToolTrace, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "final_text": self.final_text,
            "tool_calls": self.tool_calls,
            "turns": self.turns,
            "trace": [asdict(item) for item in self.trace],
        }


MUTATING_TOOLS = {
    "record_decision",
    "create_exploration",
    "refine_exploration",
    "select_experiment",
    "approve_prd",
    "generate_prd",
}


def model_tool_definitions(tools: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Convert the compact Riff catalog into provider-neutral function tools."""

    definitions: list[dict[str, Any]] = []
    for item in tools:
        name = str(item.get("name", "")).strip()
        description = str(item.get("description", "")).strip()
        required = item.get("required", ())
        if not name or not description or not isinstance(required, (list, tuple)):
            raise ChatLoopError("adapter returned an invalid tool definition")
        required_names = [str(value) for value in required]
        properties = {
            field: {"type": "string", "description": f"Riff {field} argument"}
            for field in required_names
        }
        definitions.append(
            {
                "type": "function",
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required_names,
                    "additionalProperties": True,
                },
                "annotations": {
                    "mutating": name in MUTATING_TOOLS,
                    "requires_explicit_confirmation": "confirmation_token" in required_names,
                },
            }
        )
    return definitions


class ChatToolLoop:
    """Run bounded model turns against a typed Riff adapter."""

    def __init__(
        self,
        model: ModelClient,
        adapter: ToolAdapter,
        *,
        policy: ToolLoopPolicy | None = None,
        confirmation_provider: ConfirmationProvider | None = None,
    ):
        self.model = model
        self.adapter = adapter
        self.policy = policy or ToolLoopPolicy()
        self.confirmation_provider = confirmation_provider

    def run(self, user_message: str, *, system_prompt: str | None = None) -> ChatLoopResult:
        if not user_message.strip():
            raise ChatLoopError("user message cannot be empty")
        messages: list[dict[str, Any]] = []
        if system_prompt and system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt.strip()})
        messages.append({"role": "user", "content": user_message.strip()})
        tools = model_tool_definitions(self.adapter.list_tools())
        by_name = {item["name"]: item for item in tools}
        trace: list[ToolTrace] = []
        total_calls = 0

        for turn in range(1, self.policy.max_turns + 1):
            response = self.model.complete(tuple(messages), tuple(tools))
            if not isinstance(response, ModelResponse):
                raise ChatLoopError("model client returned an invalid response")
            calls = tuple(response.tool_calls)
            assistant: dict[str, Any] = {"role": "assistant", "content": response.content or ""}
            if calls:
                assistant["tool_calls"] = [
                    {"id": call.call_id, "name": call.name, "arguments": call.arguments}
                    for call in calls
                ]
            messages.append(assistant)
            if not calls:
                final_text = (response.content or "").strip()
                if not final_text:
                    raise ChatLoopError("model stopped without a final response")
                return ChatLoopResult("SUCCEEDED", final_text, total_calls, turn, tuple(trace))

            for call in calls:
                total_calls += 1
                if total_calls > self.policy.max_tool_calls:
                    raise ChatLoopError("tool-call budget exhausted")
                if call.name not in by_name:
                    result = {"error": {"code": "UNKNOWN_TOOL", "message": f"unknown tool: {call.name}"}}
                else:
                    result = self._invoke(call, by_name[call.name])
                bounded = _bounded_result(result, self.policy.max_result_chars)
                trace.append(ToolTrace(call.call_id, call.name, dict(call.arguments), bounded))
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.call_id,
                        "content": json.dumps(bounded, sort_keys=True, default=str),
                    }
                )
        raise ChatLoopError("turn budget exhausted")

    def _invoke(self, call: ModelToolCall, definition: Mapping[str, Any]) -> dict[str, Any]:
        args = call.arguments
        if not isinstance(args, Mapping):
            return {"error": {"code": "INVALID_ARGUMENTS", "message": "tool arguments must be an object"}}
        required = definition["parameters"].get("required", [])
        missing = [name for name in required if not str(args.get(name, "")).strip()]
        if missing:
            return {"error": {"code": "INVALID_ARGUMENTS", "message": f"missing required arguments: {', '.join(missing)}"}}
        requires_confirmation = bool(definition["annotations"].get("requires_explicit_confirmation"))
        if requires_confirmation:
            token = self.confirmation_provider(call.name, args) if self.confirmation_provider else None
            if token != "USER_CONFIRMED":
                return {"error": {"code": "CONFIRMATION_REQUIRED", "message": f"explicit user confirmation is required for {call.name}"}}
            # Never trust a token emitted by the model; inject only the token
            # supplied by the outer user-confirmation boundary.
            args = {**dict(args), "confirmation_token": token}
        try:
            result = self.adapter.call(call.name, args)
            return result if isinstance(result, dict) else {"result": result}
        except Exception as exc:  # adapter errors are returned to the model as data
            return {"error": {"code": type(exc).__name__.upper(), "message": str(exc)}}


def _bounded_result(result: Mapping[str, Any], limit: int) -> dict[str, Any]:
    encoded = json.dumps(dict(result), sort_keys=True, default=str)
    if len(encoded) <= limit:
        return dict(result)
    return {
        "error": {
            "code": "RESULT_TRUNCATED",
            "message": "tool result exceeded the configured context bound",
            "original_chars": len(encoded),
        }
    }


class ScriptedModelClient:
    """Deterministic model fake used by local replay and tests."""

    def __init__(self, turns: Sequence[Mapping[str, Any]]):
        self._turns = list(turns)
        self.calls: list[dict[str, Any]] = []

    def complete(
        self,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]],
    ) -> ModelResponse:
        index = len(self.calls)
        if index >= len(self._turns):
            raise ChatLoopError("scripted model has no remaining turn")
        turn = self._turns[index]
        self.calls.append({"messages": list(messages), "tools": list(tools)})
        raw_calls = turn.get("tool_calls", [])
        if not isinstance(raw_calls, list):
            raise ChatLoopError("scripted tool_calls must be a list")
        calls = tuple(
            ModelToolCall(
                call_id=str(item.get("call_id") or f"call-{index + 1}-{offset + 1}"),
                name=str(item.get("name", "")),
                arguments=dict(item.get("arguments", {})),
            )
            for offset, item in enumerate(raw_calls)
            if isinstance(item, Mapping)
        )
        return ModelResponse(
            content=str(turn["content"]) if turn.get("content") is not None else None,
            tool_calls=calls,
            finish_reason=str(turn.get("finish_reason", "tool_calls" if calls else "stop")),
        )


class FixtureToolAdapter:
    """Offline adapter that replays bounded tool results from a fixture."""

    def __init__(self, tools: Sequence[Mapping[str, Any]], results: Mapping[str, Any]):
        self._tools = [dict(item) for item in tools]
        self._results = dict(results)
        self.calls: list[dict[str, Any]] = []

    def list_tools(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._tools]

    def call(self, name: str, arguments: Mapping[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append({"name": name, "arguments": dict(arguments or {})})
        if name not in self._results:
            raise ChatLoopError(f"fixture has no result for tool: {name}")
        result = self._results[name]
        return dict(result) if isinstance(result, Mapping) else {"result": result}


def load_chat_fixture(path: str) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ChatLoopError("chat fixture could not be read") from exc
    if not isinstance(payload, Mapping) or payload.get("schema_version") != 1:
        raise ChatLoopError("chat fixture requires schema_version 1")
    tools = payload.get("tools")
    scenarios = payload.get("scenarios")
    if not isinstance(tools, list) or not tools or not isinstance(scenarios, list) or not scenarios:
        raise ChatLoopError("chat fixture requires tools and scenarios")
    for scenario in scenarios:
        if not isinstance(scenario, Mapping) or not scenario.get("id") or not isinstance(scenario.get("turns"), list):
            raise ChatLoopError("chat fixture scenarios require id and turns")
        if not isinstance(scenario.get("adapter_results", {}), Mapping):
            raise ChatLoopError("chat fixture adapter_results must be an object")
    return dict(payload)
