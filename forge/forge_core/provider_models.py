from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CompletionRequest:
    messages: tuple[dict[str, Any], ...]
    tools: tuple[dict[str, Any], ...] = ()
    tool_choice: str | None = None
    temperature: float = 0.1


@dataclass(frozen=True, slots=True)
class ProviderToolCall:
    id: str
    name: str
    arguments: str

    def as_message_value(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.arguments},
        }


@dataclass(frozen=True, slots=True)
class ProviderToolCallDelta:
    index: int
    id: str | None
    name: str | None
    arguments: str | None


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class CompletionResponse:
    content: str | None
    tool_calls: tuple[ProviderToolCall, ...]
    usage: TokenUsage
    finish_reason: str | None

    @property
    def input_tokens(self) -> int:
        return self.usage.input_tokens

    @property
    def output_tokens(self) -> int:
        return self.usage.output_tokens

    @property
    def assistant_message(self) -> dict[str, Any]:
        message: dict[str, Any] = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            message["tool_calls"] = [call.as_message_value() for call in self.tool_calls]
        return message


@dataclass(frozen=True, slots=True)
class CompletionChunk:
    content: str | None = None
    tool_call_deltas: tuple[ProviderToolCallDelta, ...] = ()
    usage: TokenUsage | None = None
    finish_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    provider: str
    model_id: str
    reachable: bool | None
    detail: str | None = None
