"""Provider-neutral conversational tool loop for the Riff adapter."""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field
import re
from typing import Any, Callable, Mapping, Protocol, Sequence


class ChatLoopError(ValueError):
    """The model/tool conversation cannot continue safely."""

    def __init__(self, message: str, *, code: str = "CHAT_LOOP_ERROR"):
        super().__init__(message)
        self.code = code


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

NATURAL_LANGUAGE_INSTRUCTIONS = (
    "Speak in plain language. Keep stable IDs and tool names internal; use labels such as 'the top Riff' or "
    "'the public artifact experiment'. Resolve a reference only when one bounded match exists, ask for clarification "
    "when it is ambiguous or stale, and describe any mutation before requesting explicit user confirmation."
)


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
    usage: Mapping[str, int] | None = None


@dataclass(frozen=True, slots=True)
class ToolLoopPolicy:
    max_turns: int = 8
    max_tool_calls: int = 12
    max_result_chars: int = 30_000
    max_message_chars: int = 40_000
    max_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.max_turns < 1 or self.max_tool_calls < 1:
            raise ValueError("tool-loop bounds must be positive")
        if self.max_result_chars < 256 or self.max_message_chars < 256:
            raise ValueError("tool-loop character bounds are too small")
        if not math.isfinite(self.max_seconds) or self.max_seconds <= 0:
            raise ValueError("tool-loop timeout must be a finite positive number")


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
    usage: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "final_text": self.final_text,
            "tool_calls": self.tool_calls,
            "turns": self.turns,
            "trace": [asdict(item) for item in self.trace],
            "usage": dict(self.usage),
        }


class ConversationContext:
    """Ephemeral, bounded aliases for one conversational session.

    Canonical IDs remain in the adapter/database and in the audit trace.  The
    model-facing context uses labels such as ``the top Riff`` instead.
    """

    _FIELD_KINDS = {
        "riff_id": "riff", "evidence_id": "evidence", "exploration_id": "exploration",
        "experiment_id": "experiment", "project_id": "project", "run_id": "run",
        "recommendation_id": "recommendation", "opportunity_id": "opportunity",
        "candidate_id": "candidate", "source_id": "source", "goal_version_id": "goal",
    }

    def __init__(self, *, max_bindings: int = 64):
        self.max_bindings = max_bindings
        self._aliases: dict[str, dict[str, set[str]]] = {}
        self._labels: dict[tuple[str, str], str] = {}

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

    def bind(self, kind: str, identifier: str, *labels: str) -> str:
        identifier = str(identifier).strip()
        if not identifier:
            return ""
        clean = [self._normalize(label) for label in labels if str(label).strip()]
        if not clean:
            clean = [f"{kind} {len(self._aliases.get(kind, {})) + 1}"]
        bucket = self._aliases.setdefault(kind, {})
        for label in clean:
            bucket.setdefault(label, set()).add(identifier)
        preferred = next(
            (str(label) for label in labels if any(token in str(label).lower() for token in ("top", "current", "selected", "strongest"))),
            labels[0] if labels else clean[0],
        )
        existing = self._labels.get((kind, identifier))
        if existing is None or ("top" in preferred.lower() and "top" not in existing.lower()) or (
            "selected" in preferred.lower() and "selected" not in existing.lower()
        ):
            self._labels[(kind, identifier)] = preferred
        return self.label(kind, identifier)

    def label(self, kind: str, identifier: str) -> str:
        return self._labels.get((kind, identifier), f"{kind} {identifier[:8]}")

    def resolve(self, kind: str, reference: str) -> str:
        reference = str(reference).strip()
        if not reference:
            return reference
        if reference in {item_id for values in self._aliases.get(kind, {}).values() for item_id in values}:
            return reference
        matches = self._aliases.get(kind, {}).get(self._normalize(reference), set())
        if len(matches) == 1:
            return next(iter(matches))
        if len(matches) > 1:
            choices = sorted(self.label(kind, item) for item in matches)
            raise ChatLoopError(
                f"reference '{reference}' matches multiple {kind}s: {', '.join(choices)}",
                code="AMBIGUOUS_REFERENCE",
            )
        # Preserve backwards compatibility for explicit stable IDs. Natural
        # language references must be bound or are rejected as stale.
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", reference) and " " not in reference:
            return reference
        raise ChatLoopError(f"no current {kind} matches '{reference}'", code="STALE_REFERENCE")

    def recover(self, kind: str, identifier: str, label: str) -> str:
        """Rebind an explicit persisted ID after restart without writing state."""
        return self.bind(kind, identifier, label)

    def observe(self, result: Mapping[str, Any]) -> None:
        payload = result.get("result", result) if isinstance(result, Mapping) else result
        if isinstance(payload, Mapping):
            self._observe_mapping(payload, root=True)

    def _observe_mapping(self, payload: Mapping[str, Any], *, root: bool = False) -> None:
        if root:
            for field, kind in self._FIELD_KINDS.items():
                value = payload.get(field)
                if isinstance(value, str) and value.strip():
                    labels = [f"this {kind}", f"the {kind}"]
                    if kind == "riff":
                        labels.extend(["this Riff", "the current Riff"])
                    self.bind(kind, value, *labels)
        for field, value in payload.items():
            if not isinstance(value, list) or not value:
                continue
            if field == "riffs":
                self._observe_items("riff", value, "Riff")
            elif field in {"candidates", "execution_candidates"}:
                self._observe_items("candidate", value, "candidate")
            elif field in {"experiments", "experiment_options"}:
                self._observe_items("experiment", value, "experiment")
            elif field in {"projects", "recommendations"}:
                self._observe_items(field.rstrip("s"), value, field.rstrip("s"))
            elif field == "goals":
                self._observe_items("goal", value, "goal")
            elif field in {"strongest_evidence", "counterevidence", "evidence"}:
                self._observe_items("evidence", value, field.replace("_", " "))
            elif field.endswith("_ids"):
                kind = self._FIELD_KINDS.get(field[:-1] + "id")
                if kind:
                    for index, item in enumerate(value, 1):
                        if isinstance(item, str):
                            self.bind(kind, item, f"{kind} {index}")
            for item in value:
                if isinstance(item, Mapping):
                    self._observe_mapping(item, root=False)

    def _observe_items(self, kind: str, items: list[Any], noun: str) -> None:
        for index, item in enumerate(items, 1):
            if not isinstance(item, Mapping):
                continue
            field = "goal_version_id" if kind == "goal" else f"{kind}_id"
            identifier = item.get(field)
            if not isinstance(identifier, str):
                continue
            labels = [f"{noun} {index}"]
            if index == 1:
                labels.extend([f"the top {noun}", f"the first {noun}"])
            for key in ("underlying_capability", "title", "name", "thesis", "boundary", "disposition"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    labels.append(value)
            self.bind(kind, identifier, *labels)


class NaturalLanguageRenderer:
    """Render bounded tool results for the model while keeping IDs auditable."""

    _PRIVATE_KEYS = {"private", "private_evidence", "full_profile", "raw_profile", "raw_content", "credentials", "token"}

    def render(self, tool_name: str, result: Mapping[str, Any], context: ConversationContext) -> dict[str, Any]:
        payload = result.get("result", result) if isinstance(result, Mapping) else result
        rendered = self._clean(payload, context)
        summary = self._summary(tool_name, rendered)
        return {"summary": summary, "data": rendered}

    def _clean(self, value: Any, context: ConversationContext, *, parent_key: str = "") -> Any:
        if isinstance(value, Mapping):
            output: dict[str, Any] = {}
            for key, item in value.items():
                key_text = str(key)
                if key_text.lower() in self._PRIVATE_KEYS or key_text.lower().endswith("_token"):
                    continue
                if key_text.endswith("_id") and isinstance(item, str):
                    kind = ConversationContext._FIELD_KINDS.get(key_text)
                    output["handle"] = context.label(kind, item) if kind else "record"
                    continue
                if key_text.endswith("_ids"):
                    continue
                output[key_text] = self._clean(item, context, parent_key=key_text)
            return output
        if isinstance(value, list):
            return [self._clean(item, context, parent_key=parent_key) for item in value]
        return value

    @staticmethod
    def _summary(tool_name: str, data: Any) -> str:
        if isinstance(data, Mapping) and data.get("error"):
            error = data["error"]
            return str(error.get("message", "Riff could not complete that request")) if isinstance(error, Mapping) else "Riff could not complete that request"
        return f"{tool_name.replace('_', ' ').capitalize()} result is ready for follow-up."


MUTATING_TOOLS = {
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
    "github_project_goal_decision",
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
        clock: Callable[[], float] = time.monotonic,
        conversation_context: ConversationContext | None = None,
        renderer: NaturalLanguageRenderer | None = None,
    ):
        self.model = model
        self.adapter = adapter
        self.policy = policy or ToolLoopPolicy()
        self.confirmation_provider = confirmation_provider
        self.clock = clock
        self.conversation_context = conversation_context or ConversationContext()
        self.renderer = renderer or NaturalLanguageRenderer()

    def run(self, user_message: str, *, system_prompt: str | None = None) -> ChatLoopResult:
        if not user_message.strip():
            raise ChatLoopError("user message cannot be empty")
        messages: list[dict[str, Any]] = []
        if system_prompt and system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt.strip()})
        messages.append({"role": "user", "content": user_message.strip()})
        return self.run_messages(messages)[0]

    def run_messages(self, messages: list[dict[str, Any]]) -> tuple[ChatLoopResult, list[dict[str, Any]]]:
        """Continue a bounded conversation using an existing message list."""
        tools = model_tool_definitions(self.adapter.list_tools())
        by_name = {item["name"]: item for item in tools}
        trace: list[ToolTrace] = []
        total_calls = 0
        usage = {"model_turns": 0, "estimated_input_tokens": 0, "estimated_output_tokens": 0, "provider_input_tokens": 0, "provider_output_tokens": 0}
        deadline = self.clock() + self.policy.max_seconds

        for turn in range(1, self.policy.max_turns + 1):
            self._check_deadline(deadline)
            _compact_context(messages, self.policy.max_message_chars)
            if _encoded_chars(messages) > self.policy.max_message_chars:
                raise ChatLoopError(
                    "model context exceeded the configured bound",
                    code="CONTEXT_BUDGET_EXHAUSTED",
                )
            response = self.model.complete(tuple(messages), tuple(tools))
            self._check_deadline(deadline)
            if not isinstance(response, ModelResponse):
                raise ChatLoopError("model client returned an invalid response", code="INVALID_MODEL_RESPONSE")
            usage["model_turns"] += 1
            usage["estimated_input_tokens"] += _estimate_tokens(_encoded_chars(messages))
            usage["estimated_output_tokens"] += _estimate_tokens(len(response.content or ""))
            if isinstance(response.usage, Mapping):
                usage["provider_input_tokens"] += int(response.usage.get("input_tokens", response.usage.get("prompt_tokens", 0)) or 0)
                usage["provider_output_tokens"] += int(response.usage.get("output_tokens", response.usage.get("completion_tokens", 0)) or 0)
            if response.finish_reason.lower() in {"refusal", "error"}:
                raise ChatLoopError(
                    (response.content or "model declined the request").strip(),
                    code="MODEL_REFUSAL",
                )
            if response.content and len(response.content) > self.policy.max_message_chars:
                raise ChatLoopError(
                    "model response exceeded the configured bound",
                    code="RESPONSE_BUDGET_EXHAUSTED",
                )
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
                return ChatLoopResult("SUCCEEDED", final_text, total_calls, turn, tuple(trace), usage), messages

            for call in calls:
                total_calls += 1
                if total_calls > self.policy.max_tool_calls:
                    raise ChatLoopError("tool-call budget exhausted", code="TOOL_CALL_BUDGET_EXHAUSTED")
                if call.name not in by_name:
                    result = {"error": {"code": "UNKNOWN_TOOL", "message": f"unknown tool: {call.name}"}}
                else:
                    result = self._invoke(call, by_name[call.name])
                self._check_deadline(deadline)
                bounded = _bounded_result(result, self.policy.max_result_chars)
                trace.append(ToolTrace(call.call_id, call.name, dict(call.arguments), bounded))
                self.conversation_context.observe(bounded)
                rendered = self.renderer.render(call.name, bounded, self.conversation_context)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.call_id,
                        "content": json.dumps(rendered, sort_keys=True, default=str),
                    }
                )
        raise ChatLoopError("turn budget exhausted", code="TURN_BUDGET_EXHAUSTED")

    def _check_deadline(self, deadline: float) -> None:
        if self.clock() > deadline:
            raise ChatLoopError("tool-loop timeout", code="TIMEOUT")

    def _invoke(self, call: ModelToolCall, definition: Mapping[str, Any]) -> dict[str, Any]:
        args = dict(call.arguments)
        if not isinstance(args, Mapping):
            return {"error": {"code": "INVALID_ARGUMENTS", "message": "tool arguments must be an object"}}
        required = definition["parameters"].get("required", [])
        missing = [name for name in required if not str(args.get(name, "")).strip()]
        if missing:
            return {"error": {"code": "INVALID_ARGUMENTS", "message": f"missing required arguments: {', '.join(missing)}"}}
        for field, kind in ConversationContext._FIELD_KINDS.items():
            if field in args and str(args[field]).strip():
                try:
                    args[field] = self.conversation_context.resolve(kind, str(args[field]))
                except ChatLoopError as exc:
                    return {"error": {"code": exc.code, "message": str(exc)}}
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


class ConversationSession:
    """Multi-turn natural-language session with disposable context."""

    def __init__(
        self,
        model: ModelClient,
        adapter: ToolAdapter,
        *,
        system_prompt: str | None = None,
        policy: ToolLoopPolicy | None = None,
        confirmation_provider: ConfirmationProvider | None = None,
    ):
        self.context = ConversationContext()
        self.messages: list[dict[str, Any]] = []
        if system_prompt and system_prompt.strip():
            self.messages.append({"role": "system", "content": system_prompt.strip()})
        self.loop = ChatToolLoop(
            model,
            adapter,
            policy=policy,
            confirmation_provider=confirmation_provider,
            conversation_context=self.context,
        )

    def turn(self, user_message: str) -> ChatLoopResult:
        if not user_message.strip():
            raise ChatLoopError("user message cannot be empty")
        self.messages.append({"role": "user", "content": user_message.strip()})
        result, self.messages = self.loop.run_messages(self.messages)
        return result

    def recover(self, kind: str, identifier: str, label: str) -> str:
        return self.context.recover(kind, identifier, label)


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


def _encoded_chars(messages: Sequence[Mapping[str, Any]]) -> int:
    return len(json.dumps(list(messages), sort_keys=True, default=str))


def _estimate_tokens(chars: int) -> int:
    """Deterministic fallback for providers that omit token usage."""
    return max(1, (int(chars) + 3) // 4)


def _compact_context(messages: list[dict[str, Any]], limit: int) -> None:
    """Compact old tool payloads while preserving the conversation protocol.

    Tool results are already bounded individually, but a multi-step promotion
    can still exceed the cumulative model-context budget. Replace the oldest
    result bodies with an auditable marker first; assistant tool calls and
    correlation IDs remain intact, and the most recent results stay available
    to the model. If the remaining protocol envelope itself is too large, the
    caller still raises ``CONTEXT_BUDGET_EXHAUSTED``.
    """

    if _encoded_chars(messages) <= limit:
        return
    for index, message in enumerate(messages):
        if message.get("role") != "tool":
            continue
        content = message.get("content")
        if not isinstance(content, str) or content.startswith("[Riff tool result compacted"):
            continue
        messages[index] = {
            **message,
            "content": f"[Riff tool result compacted; original_chars={len(content)}]",
        }
        if _encoded_chars(messages) <= limit:
            return


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
            usage=turn.get("usage") if isinstance(turn.get("usage"), Mapping) else None,
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
