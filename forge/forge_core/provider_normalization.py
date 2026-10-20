from typing import Any

from .provider_errors import InvalidProviderResponseError
from .provider_models import (
    CompletionChunk,
    CompletionResponse,
    ProviderToolCall,
    ProviderToolCallDelta,
    TokenUsage,
)


def normalize_completion_response(response: Any) -> CompletionResponse:
    choices = getattr(response, "choices", None)
    if not isinstance(choices, list) or not choices:
        raise InvalidProviderResponseError("Provider response contained no completion choice.")
    choice = choices[0]
    message = getattr(choice, "message", None)
    if message is None:
        raise InvalidProviderResponseError("Provider response contained no assistant message.")

    content = getattr(message, "content", None)
    if content is not None and not isinstance(content, str):
        raise InvalidProviderResponseError("Provider response content was not text.")
    tool_calls = _normalize_tool_calls(getattr(message, "tool_calls", None))
    if not content and not tool_calls:
        raise InvalidProviderResponseError("Provider returned neither text nor tool calls.")
    return CompletionResponse(
        content=content,
        tool_calls=tool_calls,
        usage=normalize_token_usage(getattr(response, "usage", None)),
        finish_reason=_normalize_finish_reason(getattr(choice, "finish_reason", None)),
    )


def normalize_completion_chunk(chunk: Any) -> CompletionChunk:
    choices = getattr(chunk, "choices", None)
    if not isinstance(choices, list) or not choices:
        raise InvalidProviderResponseError("Provider stream chunk contained no completion choice.")
    choice = choices[0]
    delta = getattr(choice, "delta", None)
    if delta is None:
        raise InvalidProviderResponseError("Provider stream chunk contained no assistant delta.")

    content = getattr(delta, "content", None)
    if content is not None and not isinstance(content, str):
        raise InvalidProviderResponseError("Provider stream content was not text.")
    return CompletionChunk(
        content=content,
        tool_call_deltas=_normalize_tool_call_deltas(getattr(delta, "tool_calls", None)),
        usage=_normalize_optional_usage(getattr(chunk, "usage", None)),
        finish_reason=_normalize_finish_reason(getattr(choice, "finish_reason", None)),
    )


def normalize_token_usage(usage: Any) -> TokenUsage:
    if usage is None:
        return TokenUsage(input_tokens=0, output_tokens=0)
    return TokenUsage(
        input_tokens=_normalize_token_count(getattr(usage, "prompt_tokens", None), "input"),
        output_tokens=_normalize_token_count(getattr(usage, "completion_tokens", None), "output"),
    )


def _normalize_tool_calls(raw_tool_calls: Any) -> tuple[ProviderToolCall, ...]:
    if raw_tool_calls is None:
        return ()
    if not isinstance(raw_tool_calls, list):
        raise InvalidProviderResponseError("Provider response tool calls were malformed.")

    tool_calls: list[ProviderToolCall] = []
    call_ids: set[str] = set()
    for raw_call in raw_tool_calls:
        function = getattr(raw_call, "function", None)
        call_id = getattr(raw_call, "id", None)
        name = getattr(function, "name", None)
        arguments = getattr(function, "arguments", None)
        if (
            not isinstance(call_id, str)
            or not call_id.strip()
            or not isinstance(name, str)
            or not name.strip()
            or not isinstance(arguments, str)
        ):
            raise InvalidProviderResponseError("Provider returned a malformed tool call.")
        if call_id in call_ids:
            raise InvalidProviderResponseError("Provider returned a duplicate tool call ID.")
        call_ids.add(call_id)
        tool_calls.append(ProviderToolCall(id=call_id, name=name, arguments=arguments))
    return tuple(tool_calls)


def _normalize_tool_call_deltas(raw_tool_calls: Any) -> tuple[ProviderToolCallDelta, ...]:
    if raw_tool_calls is None:
        return ()
    if not isinstance(raw_tool_calls, list):
        raise InvalidProviderResponseError("Provider stream tool calls were malformed.")

    tool_call_deltas: list[ProviderToolCallDelta] = []
    for raw_call in raw_tool_calls:
        function = getattr(raw_call, "function", None)
        index = getattr(raw_call, "index", None)
        call_id = getattr(raw_call, "id", None)
        name = getattr(function, "name", None)
        arguments = getattr(function, "arguments", None)
        if type(index) is not int or index < 0:
            raise InvalidProviderResponseError("Provider stream tool-call index was malformed.")
        if call_id is not None and not isinstance(call_id, str):
            raise InvalidProviderResponseError("Provider stream tool-call ID was malformed.")
        if name is not None and not isinstance(name, str):
            raise InvalidProviderResponseError("Provider stream tool-call name was malformed.")
        if arguments is not None and not isinstance(arguments, str):
            raise InvalidProviderResponseError(
                "Provider stream tool-call arguments were malformed."
            )
        if call_id is None and name is None and arguments is None:
            raise InvalidProviderResponseError("Provider stream tool-call delta was empty.")
        tool_call_deltas.append(
            ProviderToolCallDelta(
                index=index,
                id=call_id,
                name=name,
                arguments=arguments,
            )
        )
    return tuple(tool_call_deltas)


def _normalize_optional_usage(usage: Any) -> TokenUsage | None:
    if usage is None:
        return None
    return normalize_token_usage(usage)


def _normalize_token_count(value: Any, field: str) -> int:
    if value is None:
        return 0
    if type(value) is int and value >= 0:
        return value
    raise InvalidProviderResponseError(f"Provider {field} token count was malformed.")


def _normalize_finish_reason(value: Any) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise InvalidProviderResponseError("Provider finish reason was malformed.")
