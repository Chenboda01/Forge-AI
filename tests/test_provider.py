from dataclasses import replace
from types import SimpleNamespace

import pytest

import forge.forge_core.models as models_module
import forge.forge_core.provider as provider_module
from forge.forge_core.provider import ForgeProvider


def test_provider_normalizes_content_tool_calls_and_usage(monkeypatch) -> None:
    # Given: a LiteLLM-shaped response containing one tool request and usage
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="call-1",
                            function=SimpleNamespace(
                                name="read_file",
                                arguments='{"path": "README.md"}',
                            ),
                        )
                    ],
                )
            )
        ],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=7),
    )
    monkeypatch.setattr(provider_module, "completion", lambda **_kwargs: response)
    provider = ForgeProvider("ollama")
    request_type = provider_module.CompletionRequest

    # When: the SDK response crosses the provider boundary
    result = provider.complete(
        request_type(
            messages=({"role": "user", "content": "inspect"},),
            tools=(),
        )
    )

    # Then: consumers receive only normalized Forge-owned values
    assert result.content is None
    assert result.tool_calls[0].id == "call-1"
    assert result.tool_calls[0].name == "read_file"
    assert result.input_tokens == 12
    assert result.output_tokens == 7
    assert result.assistant_message["tool_calls"][0]["function"]["name"] == "read_file"


def test_provider_normalizes_owned_token_usage(monkeypatch) -> None:
    # Given: a provider response with token counters
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="done", tool_calls=[]),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=9, completion_tokens=4),
    )
    monkeypatch.setattr(provider_module, "completion", lambda **_kwargs: response)
    provider = ForgeProvider("ollama")

    # When: the response crosses Forge's provider boundary
    result = provider.complete(provider_module.CompletionRequest(messages=()))

    # Then: token usage is exposed as an owned value object
    assert result.usage == provider_module.TokenUsage(input_tokens=9, output_tokens=4)
    assert result.usage.total_tokens == 13


def test_provider_normalizes_streaming_chunks(monkeypatch) -> None:
    # Given: LiteLLM-shaped stream chunks with text, completion metadata, and usage
    response = iter(
        (
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="hello", tool_calls=None),
                        finish_reason=None,
                    )
                ],
                usage=None,
            ),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content=" world", tool_calls=None),
                        finish_reason="stop",
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=7, completion_tokens=2),
            ),
        )
    )
    monkeypatch.setattr(provider_module, "completion", lambda **_kwargs: response)
    provider = ForgeProvider("ollama")

    # When: Forge streams through the provider boundary
    chunks = list(provider.stream(provider_module.CompletionRequest(messages=())))

    # Then: consumers receive normalized Forge-owned chunks rather than SDK objects
    assert [chunk.content for chunk in chunks] == ["hello", " world"]
    assert chunks[-1].finish_reason == "stop"
    assert chunks[-1].usage == provider_module.TokenUsage(input_tokens=7, output_tokens=2)


def test_provider_preserves_partial_tool_call_deltas_in_stream(monkeypatch) -> None:
    # Given: one tool call split across two standard streaming deltas
    response = iter(
        (
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    index=0,
                                    id="call-1",
                                    function=SimpleNamespace(
                                        name="read_file", arguments='{"path": '
                                    ),
                                )
                            ],
                        ),
                        finish_reason=None,
                    )
                ],
                usage=None,
            ),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    index=0,
                                    id=None,
                                    function=SimpleNamespace(name=None, arguments='"README.md"}'),
                                )
                            ],
                        ),
                        finish_reason="tool_calls",
                    )
                ],
                usage=None,
            ),
        )
    )
    monkeypatch.setattr(provider_module, "completion", lambda **_kwargs: response)
    provider = ForgeProvider("ollama")

    # When: the stream crosses Forge's provider boundary
    chunks = list(provider.stream(provider_module.CompletionRequest(messages=())))

    # Then: partial tool-call data remains typed and does not masquerade as a complete call
    assert chunks[0].tool_call_deltas == (
        provider_module.ProviderToolCallDelta(
            index=0,
            id="call-1",
            name="read_file",
            arguments='{"path": ',
        ),
    )
    assert chunks[1].tool_call_deltas == (
        provider_module.ProviderToolCallDelta(
            index=0,
            id=None,
            name=None,
            arguments='"README.md"}',
        ),
    )


def test_provider_rejects_malformed_stream_chunk(monkeypatch) -> None:
    # Given: a streaming chunk without an assistant delta
    response = iter(
        (
            SimpleNamespace(
                choices=[SimpleNamespace(delta=None, finish_reason=None)],
                usage=None,
            ),
        )
    )
    monkeypatch.setattr(provider_module, "completion", lambda **_kwargs: response)
    provider = ForgeProvider("ollama")

    # When / Then: malformed untrusted stream data is rejected at the boundary
    with pytest.raises(provider_module.InvalidProviderResponseError):
        list(provider.stream(provider_module.CompletionRequest(messages=())))


def test_provider_rejects_unavailable_streaming_capability() -> None:
    # Given: a selected model that does not declare streaming support
    provider = ForgeProvider("ollama")
    provider.model = replace(
        provider.model,
        capabilities=models_module.ModelCapabilities(
            tool_calling=True,
            streaming=False,
            vision=False,
            reasoning=False,
            structured_output=False,
            local=True,
        ),
    )

    # When / Then: Forge stops before sending an unsupported provider request
    with pytest.raises(provider_module.UnsupportedFeatureError):
        list(provider.stream(provider_module.CompletionRequest(messages=())))


def test_provider_exposes_required_normalized_errors() -> None:
    # Given: the roadmap's normalized provider error names
    error_names = (
        "AuthenticationError",
        "RateLimitError",
        "ProviderConnectionError",
        "ProviderTimeoutError",
        "UnsupportedFeatureError",
        "InvalidProviderResponseError",
        "ContextLimitError",
        "ProviderUnavailableError",
    )

    # When: the public provider boundary is inspected
    error_types = [getattr(provider_module, error_name) for error_name in error_names]

    # Then: every required error is owned by Forge's provider hierarchy
    assert all(
        issubclass(error_type, provider_module.ForgeProviderError) for error_type in error_types
    )


@pytest.mark.parametrize(
    ("source_error_name", "expected_error_name"),
    (
        ("LiteLLMAuthenticationError", "AuthenticationError"),
        ("LiteLLMRateLimitError", "RateLimitError"),
        ("APIConnectionError", "ProviderConnectionError"),
        ("Timeout", "ProviderTimeoutError"),
        ("ContextWindowExceededError", "ContextLimitError"),
        ("UnsupportedParamsError", "UnsupportedFeatureError"),
        ("ServiceUnavailableError", "ProviderUnavailableError"),
        ("APIError", "ProviderRequestError"),
    ),
)
def test_provider_normalizes_litellm_errors(
    monkeypatch, source_error_name, expected_error_name
) -> None:
    # Given: one LiteLLM failure category at the provider boundary
    class SourceError(Exception):
        pass

    def raise_source_error(**_kwargs):
        raise SourceError("provider failure")

    monkeypatch.setattr(provider_module, source_error_name, SourceError)
    monkeypatch.setattr(provider_module, "completion", raise_source_error)
    provider = ForgeProvider("ollama")

    # When / Then: Forge exposes only its own normalized error category
    with pytest.raises(getattr(provider_module, expected_error_name), match="provider failure"):
        provider.complete(provider_module.CompletionRequest(messages=()))


def test_provider_health_represents_unknown_connectivity_without_a_request() -> None:
    # Given: a provider whose network reachability was not checked
    health = provider_module.ProviderHealth(
        provider="Ollama",
        model_id="ollama/llama3.2:1b",
        reachable=None,
    )

    # When / Then: the health value preserves that uncertainty explicitly
    assert health.reachable is None
    assert health.provider == "Ollama"
