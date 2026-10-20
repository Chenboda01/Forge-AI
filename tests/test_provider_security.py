import traceback
from types import SimpleNamespace

import pytest
from openai import OpenAIError

import forge.forge_core.provider as provider_module
from forge.forge_core.provider import ForgeProvider


def test_provider_rejects_malformed_completion_response(monkeypatch) -> None:
    # Given: an untrusted provider response without a completion choice
    monkeypatch.setattr(
        provider_module,
        "completion",
        lambda **_kwargs: SimpleNamespace(choices=[], usage=None),
    )
    provider = ForgeProvider("ollama")

    # When / Then: malformed provider data is rejected at the boundary
    with pytest.raises(provider_module.InvalidProviderResponseError):
        provider.complete(
            provider_module.CompletionRequest(messages=({"role": "user", "content": "hello"},))
        )


@pytest.mark.parametrize(
    ("call_ids", "names"),
    (
        (("call-1", "call-1"), ("read_file", "read_file")),
        (("",), ("read_file",)),
        (("call-1",), ("",)),
    ),
)
def test_provider_rejects_ambiguous_tool_call_identity(
    monkeypatch, call_ids: tuple[str, ...], names: tuple[str, ...]
) -> None:
    # Given: tool calls with duplicate or blank protocol identities
    calls = [
        SimpleNamespace(
            id=call_id,
            function=SimpleNamespace(name=name, arguments="{}"),
        )
        for call_id, name in zip(call_ids, names, strict=True)
    ]
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=calls))],
        usage=None,
    )
    monkeypatch.setattr(provider_module, "completion", lambda **_kwargs: response)

    # When / Then: ambiguous calls are rejected before the workflow can execute them
    with pytest.raises(provider_module.InvalidProviderResponseError, match="tool call"):
        ForgeProvider("ollama").complete(provider_module.CompletionRequest(messages=()))


def test_provider_redacts_credentials_from_normalized_errors(monkeypatch) -> None:
    # Given: an upstream provider failure containing a synthetic credential
    secret = "sk-proj-syntheticcredential1234567890"

    class SourceError(Exception):
        pass

    def raise_provider_error(**_kwargs):
        raise SourceError(f"request rejected for {secret}")

    monkeypatch.setattr(provider_module, "APIError", SourceError)
    monkeypatch.setattr(provider_module, "completion", raise_provider_error)
    provider = ForgeProvider("ollama")

    # When: the failure crosses Forge's provider boundary
    with pytest.raises(provider_module.ProviderRequestError) as captured:
        provider.complete(provider_module.CompletionRequest(messages=()))

    # Then: terminal and persistence consumers cannot receive the raw credential
    assert secret not in str(captured.value)
    assert "[REDACTED]" in str(captured.value)
    assert secret not in "".join(traceback.format_exception(captured.value))


@pytest.mark.parametrize(
    ("alias", "base_url"),
    (
        ("openai", "http://api.example.invalid/v1"),
        ("ollama", "https://remote.example.invalid/v1"),
    ),
)
def test_provider_rejects_unsafe_or_nonlocal_endpoints(
    monkeypatch: pytest.MonkeyPatch,
    alias: str,
    base_url: str,
) -> None:
    # Given: a cloud endpoint without TLS or a local profile redirected off-device
    model = provider_module.MODELS[alias]
    if model.requires_key is not None:
        monkeypatch.setenv(model.requires_key, "test-api-key")
    configuration = provider_module.ForgeConfig(model=alias, base_url=base_url)

    # When / Then: provider construction fails before any credential can be sent
    with pytest.raises(provider_module.ForgeProviderError, match="endpoint"):
        ForgeProvider(alias, configuration=configuration)


def test_provider_revalidates_endpoint_before_switching_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a cloud profile using a remote custom endpoint
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    configuration = provider_module.ForgeConfig(
        model="openai",
        base_url="https://models.example.invalid/v1",
    )
    provider = ForgeProvider("openai", configuration=configuration)

    # When / Then: switching that endpoint to a local profile fails atomically
    with pytest.raises(provider_module.ForgeProviderError, match="endpoint"):
        provider.switch_model("ollama")
    assert provider.model is provider_module.MODELS["openai"]
    assert provider.configuration.model == "openai"


def test_provider_redacts_configured_credential_without_token_shape(monkeypatch) -> None:
    # Given: a configured credential whose value has no recognizable token prefix
    secret = "synthetic credential with spaces"

    class SourceError(Exception):
        pass

    def raise_provider_error(**_kwargs):
        raise SourceError(f"request rejected for credential {secret}")

    monkeypatch.setenv("OPENAI_API_KEY", secret)
    monkeypatch.setattr(provider_module, "APIError", SourceError)
    monkeypatch.setattr(provider_module, "completion", raise_provider_error)
    provider = ForgeProvider("openai")

    # When: the provider includes the exact configured value in an error
    with pytest.raises(provider_module.ProviderRequestError) as captured:
        provider.complete(provider_module.CompletionRequest(messages=()))

    # Then: registration at credential resolution redacts the value everywhere
    assert secret not in str(captured.value)
    assert "[REDACTED]" in str(captured.value)


def test_provider_normalizes_unmapped_upstream_sdk_errors(monkeypatch) -> None:
    # Given: LiteLLM exposes an upstream SDK failure outside Forge's named categories
    secret = "sk-proj-unmappedsyntheticcredential12345"

    def raise_upstream_error(**_kwargs):
        raise OpenAIError(f"unmapped provider failure contained {secret}")

    monkeypatch.setattr(provider_module, "completion", raise_upstream_error)

    # When: the unknown SDK category crosses Forge's provider boundary
    with pytest.raises(provider_module.ProviderRequestError) as captured:
        ForgeProvider("ollama").complete(provider_module.CompletionRequest(messages=()))

    # Then: callers receive one redacted Forge-owned error without an upstream traceback
    assert secret not in str(captured.value)
    assert "[REDACTED]" in str(captured.value)
    assert secret not in "".join(traceback.format_exception(captured.value))
