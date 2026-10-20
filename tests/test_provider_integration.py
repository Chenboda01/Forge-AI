from types import SimpleNamespace

import pytest

import forge.forge_core.provider as provider_module
from forge.forge_core.config import ForgeConfig
from forge.forge_core.provider import ForgeProvider


@pytest.mark.parametrize(
    ("alias", "key_name", "base_url"),
    (
        ("openai", "OPENAI_API_KEY", "https://models.example.test/v1"),
        ("deepseek", "DEEPSEEK_API_KEY", "https://models.example.test/v1"),
        ("ollama", None, "http://127.0.0.1:11434/v1"),
    ),
)
def test_provider_forwards_configured_connection_options(
    monkeypatch: pytest.MonkeyPatch,
    alias: str,
    key_name: str | None,
    base_url: str,
) -> None:
    # Given: a selected provider with a configured endpoint and transport limits
    if key_name is not None:
        monkeypatch.setenv(key_name, "test-api-key")
    captured: dict[str, str | int] = {}
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=[]))],
        usage=None,
    )

    def record_completion(**kwargs):
        for name in ("model", "api_base", "api_key"):
            value = kwargs.get(name)
            if isinstance(value, str):
                captured[name] = value
        for name in ("timeout", "num_retries"):
            value = kwargs.get(name)
            if isinstance(value, int):
                captured[name] = value
        return response

    monkeypatch.setattr(provider_module, "completion", record_completion)
    config = ForgeConfig(
        model=alias,
        model_id=f"{alias}/configured-model",
        base_url=base_url,
        timeout_seconds=12,
        retry_limit=3,
    )

    # When: the provider completes a request
    provider = ForgeProvider(alias, configuration=config)
    provider.complete(provider_module.CompletionRequest(messages=()))

    # Then: LiteLLM receives only the configured non-secret connection settings
    assert captured["model"] == f"{alias}/configured-model"
    assert captured["api_base"] == base_url
    assert captured["timeout"] == 12
    assert captured["num_retries"] == 3
    if key_name is not None:
        assert captured["api_key"] == "test-api-key"
    else:
        assert "api_key" not in captured


def test_provider_health_reports_connection_failure_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an unavailable Ollama endpoint
    class SourceConnectionError(Exception):
        pass

    def raise_connection_error(**_kwargs) -> None:
        raise SourceConnectionError("connection refused")

    monkeypatch.setattr(provider_module, "APIConnectionError", SourceConnectionError)
    monkeypatch.setattr(provider_module, "completion", raise_connection_error)
    provider = ForgeProvider("ollama")

    # When: a user requests an explicit provider connection test
    health = provider.test_connection()

    # Then: Forge reports the failure as health evidence instead of crashing
    assert health.reachable is False
    assert health.provider == "Local"
    assert health.detail is not None
    assert "connection refused" in health.detail
