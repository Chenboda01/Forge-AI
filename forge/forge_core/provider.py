from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from ipaddress import ip_address
from typing import Any, Protocol
from urllib.parse import urlsplit

from litellm import completion
from litellm.exceptions import (
    APIConnectionError,
    APIError,
    BadGatewayError,
    BlockedPiiEntityError,
    BudgetExceededError,
    ContextWindowExceededError,
    GuardrailRaisedException,
    InternalServerError,
    ModifyResponseException,
    SensitiveDataRouteException,
    ServiceUnavailableError,
    Timeout,
    UnsupportedParamsError,
)
from litellm.exceptions import AuthenticationError as LiteLLMAuthenticationError
from litellm.exceptions import RateLimitError as LiteLLMRateLimitError
from openai import OpenAIError as UpstreamProviderError

from .config import ForgeConfig, get_api_key
from .models import MODELS, ModelCapabilities, ModelConfig
from .provider_errors import (
    AuthenticationError,
    ContextLimitError,
    ForgeProviderError,
    InvalidProviderResponseError,
    ProviderConnectionError,
    ProviderRequestError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    RateLimitError,
    UnsupportedFeatureError,
)
from .provider_models import (
    CompletionChunk,
    CompletionRequest,
    CompletionResponse,
    ProviderHealth,
    ProviderToolCall,
    ProviderToolCallDelta,
    TokenUsage,
)
from .provider_normalization import normalize_completion_chunk, normalize_completion_response
from .redaction import redact_text

__all__ = (
    "AuthenticationError",
    "CompletionChunk",
    "CompletionRequest",
    "CompletionResponse",
    "ContextLimitError",
    "ForgeProvider",
    "ForgeProviderError",
    "InvalidProviderResponseError",
    "ProviderClient",
    "ProviderConnectionError",
    "ProviderHealth",
    "ProviderRequestError",
    "ProviderTimeoutError",
    "ProviderToolCall",
    "ProviderToolCallDelta",
    "ProviderUnavailableError",
    "RateLimitError",
    "TokenUsage",
    "UnsupportedFeatureError",
)


class ProviderClient(Protocol):
    @property
    def model_id(self) -> str: ...

    @property
    def capabilities(self) -> ModelCapabilities: ...

    def complete(self, request: CompletionRequest) -> CompletionResponse: ...

    def stream(self, request: CompletionRequest) -> Iterator[CompletionChunk]: ...

    def test_connection(self) -> ProviderHealth: ...


class ForgeProvider:
    def __init__(self, model_alias: str, *, configuration: ForgeConfig | None = None):
        self.configuration = configuration or ForgeConfig(model=model_alias)
        self.model = self._get_model(self.configuration.model)
        self._validate_endpoint(self.model, self.configuration)

    @property
    def model_id(self) -> str:
        return self.configuration.model_id or self.model.model_id

    @property
    def capabilities(self) -> ModelCapabilities:
        return self.model.capabilities

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
            raise ForgeProviderError(
                f"{required_key} is missing. Configure it in the environment or secure store."
            )
        return model

    @staticmethod
    def _validate_endpoint(model: ModelConfig, configuration: ForgeConfig) -> None:
        base_url = configuration.base_url
        if base_url is None:
            return
        try:
            endpoint = urlsplit(base_url)
            hostname = endpoint.hostname
            _ = endpoint.port
        except ValueError as error:
            raise ForgeProviderError("Provider endpoint is invalid.") from error
        if (
            endpoint.scheme not in {"http", "https"}
            or hostname is None
            or endpoint.username is not None
            or endpoint.password is not None
        ):
            raise ForgeProviderError("Provider endpoint is invalid.")
        if model.capabilities.local:
            if not _is_loopback_host(hostname):
                raise ForgeProviderError("Local provider endpoint must remain on this device.")
        elif endpoint.scheme != "https":
            raise ForgeProviderError("Remote provider endpoint must use HTTPS.")

    def switch_model(self, model_alias: str) -> None:
        model = self._get_model(model_alias)
        configuration = self.configuration.model_copy(
            update={"model": model_alias, "model_id": None}
        )
        self._validate_endpoint(model, configuration)
        self.model = model
        self.configuration = configuration

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        self._ensure_tool_calling(request)
        with _normalize_provider_errors():
            response = self._send_completion(request, stream=False)
        return normalize_completion_response(response)

    def stream(self, request: CompletionRequest) -> Iterator[CompletionChunk]:
        self._ensure_tool_calling(request)
        if not self.capabilities.streaming:
            raise UnsupportedFeatureError(f"{self.model_id} does not support streaming.")
        with _normalize_provider_errors():
            response = self._send_completion(request, stream=True)
            if not isinstance(response, Iterable):
                raise InvalidProviderResponseError("Provider did not return a streaming iterator.")
            for chunk in response:
                yield normalize_completion_chunk(chunk)

    def test_connection(self) -> ProviderHealth:
        try:
            self.complete(
                CompletionRequest(
                    messages=(
                        {
                            "role": "user",
                            "content": "Reply with OK.",
                        },
                    ),
                    temperature=0.0,
                )
            )
        except ForgeProviderError as error:
            return ProviderHealth(
                provider=self.model.provider,
                model_id=self.model_id,
                reachable=False,
                detail=str(error),
            )
        return ProviderHealth(
            provider=self.model.provider,
            model_id=self.model_id,
            reachable=True,
            detail="Connection succeeded.",
        )

    def _ensure_tool_calling(self, request: CompletionRequest) -> None:
        if request.tools and not self.capabilities.tool_calling:
            raise UnsupportedFeatureError(f"{self.model_id} does not support tool calling.")

    def _send_completion(self, request: CompletionRequest, *, stream: bool) -> Any:
        options: dict[str, Any] = {
            "model": self.model_id,
            "messages": list(request.messages),
            "tools": list(request.tools) or None,
            "tool_choice": request.tool_choice,
            "temperature": request.temperature,
            "stream": stream,
            "timeout": self.configuration.timeout_seconds,
            "num_retries": self.configuration.retry_limit,
        }
        if self.configuration.base_url is not None:
            options["api_base"] = self.configuration.base_url
        api_key = get_api_key(self.model.requires_key)
        if api_key is not None:
            options["api_key"] = api_key
        return completion(**options)


@contextmanager
def _normalize_provider_errors() -> Iterator[None]:
    try:
        yield
    except LiteLLMAuthenticationError as error:
        raise AuthenticationError(redact_text(str(error))) from None
    except LiteLLMRateLimitError as error:
        raise RateLimitError(redact_text(str(error))) from None
    except APIConnectionError as error:
        raise ProviderConnectionError(redact_text(str(error))) from None
    except Timeout as error:
        raise ProviderTimeoutError(redact_text(str(error))) from None
    except ContextWindowExceededError as error:
        raise ContextLimitError(redact_text(str(error))) from None
    except UnsupportedParamsError as error:
        raise UnsupportedFeatureError(redact_text(str(error))) from None
    except (BadGatewayError, InternalServerError, ServiceUnavailableError) as error:
        raise ProviderUnavailableError(redact_text(str(error))) from None
    except (
        APIError,
        BlockedPiiEntityError,
        BudgetExceededError,
        GuardrailRaisedException,
        ModifyResponseException,
        SensitiveDataRouteException,
    ) as error:
        raise ProviderRequestError(redact_text(str(error))) from None
    except UpstreamProviderError as error:
        raise ProviderRequestError(redact_text(str(error))) from None
    except ForgeProviderError:
        raise


def _is_loopback_host(hostname: str) -> bool:
    if hostname.casefold() == "localhost":
        return True
    try:
        return ip_address(hostname).is_loopback
    except ValueError:
        return False
