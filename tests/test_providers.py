import pytest

from forge.forge_core.credentials import SUPPORTED_CREDENTIALS
from forge.forge_core.models import MODELS
from forge.forge_core.providers import (
    PROVIDERS,
    provider_by_id,
    provider_credentials,
    provider_for_env,
)

EXPECTED_PROVIDER_IDS = {
    "anthropic",
    "openai",
    "google",
    "xai",
    "deepseek",
    "minimax",
    "moonshot",
    "dashscope",
    "openrouter",
    "together",
    "groq",
    "anyscale",
    "fireworks",
    "bedrock",
    "azure",
    "cloudflare",
    "github",
    "cohere",
    "mistral",
    "ollama",
    "lm-studio",
    "vllm",
    "opencode-go",
    "custom",
}


def test_provider_catalog_covers_the_supported_providers() -> None:
    # Given: the static provider catalog
    # When: its identifiers are collected
    identifiers = set(PROVIDERS)

    # Then: every documented provider is present exactly once
    assert identifiers == EXPECTED_PROVIDER_IDS


def test_every_cloud_provider_credential_is_storable() -> None:
    # Given: the credential names declared by the catalog
    names = provider_credentials()

    # When: Forge decides which names a credential store may accept
    # Then: every catalog credential is supported
    assert names
    assert names <= SUPPORTED_CREDENTIALS


def test_local_providers_do_not_require_credentials() -> None:
    # Given: the local provider entries
    # When: their authentication requirements are inspected
    # Then: they declare no credential and stay on loopback defaults
    for identifier in ("ollama", "lm-studio", "vllm"):
        provider = PROVIDERS[identifier]
        assert provider.auth == "local"
        assert provider.env_var is None
        assert provider.default_base_url is not None


def test_provider_lookup_is_case_and_separator_insensitive() -> None:
    # Given: a catalog with hyphenated identifiers
    # When: callers resolve identifiers in different styles
    # Then: the same provider is returned
    assert provider_by_id("OpenAI") is PROVIDERS["openai"]
    assert provider_by_id("lm_studio") is PROVIDERS["lm-studio"]
    assert provider_by_id("  vLLM  ") is PROVIDERS["vllm"]


def test_provider_for_env_resolves_owned_credentials() -> None:
    # Given: a credential name owned by a provider
    # When: the catalog maps the environment variable back to its provider
    # Then: the provider is returned and unknown names are rejected
    assert provider_for_env("ANTHROPIC_API_KEY") is PROVIDERS["anthropic"]
    assert provider_for_env("NOT_A_FORGE_CREDENTIAL") is None


def test_model_registry_credentials_are_storable() -> None:
    # Given: the model registry
    # When: model credential requirements are compared with supported names
    # Then: no selectable cloud model references an unstorable credential
    for model in MODELS.values():
        if model.requires_key is not None:
            assert model.requires_key in SUPPORTED_CREDENTIALS


def test_model_credentials_are_declared_by_the_catalog() -> None:
    # Given: the model registry and provider catalog
    model_credentials = {
        model.requires_key for model in MODELS.values() if model.requires_key is not None
    }

    # When: model credential requirements are compared with catalog credentials
    # Then: no selectable model references a credential the catalog does not declare
    assert model_credentials
    assert model_credentials <= provider_credentials()


def test_configuration_only_providers_have_no_model_profile() -> None:
    # Given: providers that require an endpoint or custom routing
    model_credentials = {
        model.requires_key for model in MODELS.values() if model.requires_key is not None
    }

    # When: their credentials are compared with selectable models
    # Then: they remain authentication-only until routing is configured
    assert "OPENCODE_API_KEY" not in model_credentials
    assert "FORGE_CUSTOM_API_KEY" not in model_credentials


def test_catalog_provider_ids_are_unique_and_labeled() -> None:
    # Given: the catalog entries
    # When: their identity fields are inspected
    # Then: each key matches its id and carries a human label
    for identifier, provider in PROVIDERS.items():
        assert provider.id == identifier
        assert provider.label.strip()
        assert provider.description.strip()


@pytest.mark.parametrize("identifier", sorted(PROVIDERS))
def test_provider_entries_have_a_valid_auth_kind(identifier: str) -> None:
    # Given: one catalog entry
    # When: its authentication kind is inspected
    # Then: the kind is one Forge knows how to handle
    assert PROVIDERS[identifier].auth in {"api_key", "local", "custom"}
