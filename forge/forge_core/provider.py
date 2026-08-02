from dataclasses import dataclass
from typing import Any, Protocol

from litellm import completion
from litellm.exceptions import (
    APIConnectionError,
    APIError,
    AuthenticationError,
    BlockedPiiEntityError,
    BudgetExceededError,
    ContextWindowExceededError,
    GuardrailRaisedException,
    ModifyResponseException,
    RateLimitError,
    SensitiveDataRouteException,
    Timeout,
)

from .config import get_api_key
from .models import MODELS, ModelConfig
from .redaction import redact_text


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
class CompletionResponse:
    content: str | None
    tool_calls: tuple[ProviderToolCall, ...]
    input_tokens: int
    output_tokens: int
    finish_reason: str | None

    @property
    def assistant_message(self) -> dict[str, Any]:
        message: dict[str, Any] = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            message["tool_calls"] = [call.as_message_value() for call in self.tool_calls]
        return message


class ProviderClient(Protocol):
    @property
    def model_id(self) -> str: ...

    def complete(self, request: CompletionRequest) -> CompletionResponse: ...


class ForgeProviderError(Exception):
    """Base error for model selection and normalized provider failures."""


class ProviderAuthenticationError(ForgeProviderError):
    """Raised when a provider rejects configured credentials."""


class ProviderRateLimitError(ForgeProviderError):
    """Raised when a provider rejects a request due to rate limits."""


class ProviderConnectionError(ForgeProviderError):
    """Raised when Forge cannot connect to the selected provider."""


class ProviderTimeoutError(ForgeProviderError):
    """Raised when the selected provider exceeds its request timeout."""


class ProviderContextLimitError(ForgeProviderError):
    """Raised when the provider rejects an oversized context."""


class ProviderRequestError(ForgeProviderError):
    """Raised for a normalized provider failure without a narrower category."""


class InvalidProviderResponseError(ForgeProviderError):
    """Raised when an untrusted provider response cannot be normalized."""


class ForgeProvider:
    def __init__(self, model_alias: str):
        self.model = self._get_model(model_alias)

    @property
    def model_id(self) -> str:
        return self.model.model_id

    @staticmethod
    def _get_model(model_alias: str) -> ModelConfig:
        model = MODELS.get(model_alias)
        if model is None:
            available = ", ".join(sorted(MODELS))
            raise ForgeProviderError(
                f"Unknown model '{model_alias}'. Available models: {available}"
            )
        required_key = model.requires_key
        if required_key and not get_api_key(required_key):
            raise ForgeProviderError(f"{required_key} is missing. Add it to your .env file.")
        return model

    def switch_model(self, model_alias: str) -> None:
        self.model = self._get_model(model_alias)

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        try:
            response = completion(
                model=self.model_id,
                messages=list(request.messages),
                tools=list(request.tools) or None,
                tool_choice=request.tool_choice,
                temperature=request.temperature,
            )
        except AuthenticationError as error:
            raise ProviderAuthenticationError(redact_text(str(error))) from error
        except RateLimitError as error:
            raise ProviderRateLimitError(redact_text(str(error))) from error
        except APIConnectionError as error:
            raise ProviderConnectionError(redact_text(str(error))) from error
        except Timeout as error:
            raise ProviderTimeoutError(redact_text(str(error))) from error
        except ContextWindowExceededError as error:
            raise ProviderContextLimitError(redact_text(str(error))) from error
        except (
            APIError,
            BlockedPiiEntityError,
            BudgetExceededError,
            GuardrailRaisedException,
            ModifyResponseException,
            SensitiveDataRouteException,
        ) as error:
            raise ProviderRequestError(redact_text(str(error))) from error
        return self._normalize_response(response)

    @staticmethod
    def _normalize_response(response: Any) -> CompletionResponse:
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
        raw_tool_calls = getattr(message, "tool_calls", None) or []
        if not isinstance(raw_tool_calls, list):
            raise InvalidProviderResponseError("Provider response tool calls were malformed.")

        tool_calls: list[ProviderToolCall] = []
        for raw_call in raw_tool_calls:
            function = getattr(raw_call, "function", None)
            call_id = getattr(raw_call, "id", None)
            name = getattr(function, "name", None)
            arguments = getattr(function, "arguments", None)
            if (
                not isinstance(call_id, str)
                or not isinstance(name, str)
                or not isinstance(arguments, str)
            ):
                raise InvalidProviderResponseError("Provider returned a malformed tool call.")
            tool_calls.append(ProviderToolCall(call_id, name, arguments))

        if not content and not tool_calls:
            raise InvalidProviderResponseError("Provider returned neither text nor tool calls.")
        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", 0)
        completion_tokens = getattr(usage, "completion_tokens", 0)
        finish_reason = getattr(choice, "finish_reason", None)
        return CompletionResponse(
            content=content,
            tool_calls=tuple(tool_calls),
            input_tokens=prompt_tokens if isinstance(prompt_tokens, int) else 0,
            output_tokens=completion_tokens if isinstance(completion_tokens, int) else 0,
            finish_reason=finish_reason if isinstance(finish_reason, str) else None,
        )
