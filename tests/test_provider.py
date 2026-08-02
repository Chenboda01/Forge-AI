from types import SimpleNamespace

import pytest

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


def test_provider_rejects_malformed_completion_response(monkeypatch) -> None:
    # Given: an untrusted provider response without a completion choice
    monkeypatch.setattr(
        provider_module,
        "completion",
        lambda **_kwargs: SimpleNamespace(choices=[], usage=None),
    )
    provider = ForgeProvider("ollama")
    request_type = provider_module.CompletionRequest
    error_type = provider_module.InvalidProviderResponseError

    # When / Then: malformed provider data is rejected at the boundary
    with pytest.raises(error_type):
        provider.complete(request_type(messages=({"role": "user", "content": "hello"},)))
