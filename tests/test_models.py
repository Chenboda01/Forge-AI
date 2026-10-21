from dataclasses import FrozenInstanceError

import pytest

import forge.forge_core.models as models_module
from forge.forge_core.models import DEFAULT_MODEL, MODELS, ModelConfig


def test_model_config_is_immutable():
    model = ModelConfig(name="Test", model_id="test/model", provider="Test")
    with pytest.raises(FrozenInstanceError):
        model.name = "Changed"  # type: ignore[misc]


def test_model_config_optional_key():
    model = ModelConfig(name="Local", model_id="local/model", provider="Local")
    assert model.requires_key is None


def test_model_config_requires_key():
    model = ModelConfig(
        name="Cloud", model_id="cloud/model", provider="Cloud", requires_key="API_KEY"
    )
    assert model.requires_key == "API_KEY"


def test_models_registry_has_expected_keys():
    assert "ollama" in MODELS
    assert "deepseek" in MODELS
    assert "openai" in MODELS
    assert "claude" in MODELS
    assert "gemini" in MODELS


def test_ollama_does_not_require_key():
    assert MODELS["ollama"].requires_key is None
    assert MODELS["ollama-qwen"].requires_key is None


def test_deepseek_requires_key():
    assert MODELS["deepseek"].requires_key == "DEEPSEEK_API_KEY"


def test_deepseek_profiles_target_current_models():
    # Given: the DeepSeek aliases
    # When: their model identifiers are inspected
    # Then: they target the current V4.1 Flash and V4 Pro APIs
    assert MODELS["deepseek"].model_id == "deepseek/deepseek-flash"
    assert MODELS["deepseek-pro"].model_id == "deepseek/deepseek-v4-pro"


def test_registry_includes_current_frontier_aliases():
    # Given: the model registry
    # When: current frontier aliases are resolved
    # Then: each alias points at its provider model
    assert MODELS["openai-mini"].model_id == "openai/gpt-5-mini"
    assert MODELS["openai-nano"].model_id == "openai/gpt-5-nano"
    assert MODELS["gemini-pro"].model_id == "gemini/gemini-2.5-pro"
    assert MODELS["xai"].model_id == "xai/grok-4"


def test_default_model_is_ollama():
    assert DEFAULT_MODEL == "ollama"


def test_all_models_have_required_fields():
    for alias, model in MODELS.items():
        assert model.name, f"Model {alias} has no name"
        assert model.model_id, f"Model {alias} has no model_id"
        assert model.provider, f"Model {alias} has no provider"


def test_models_declare_capabilities() -> None:
    # Given: every model Forge can select
    # When: their capability declarations are inspected
    # Then: each model has an owned immutable capability value
    assert all(
        isinstance(model.capabilities, models_module.ModelCapabilities) for model in MODELS.values()
    )
    assert MODELS["ollama"].capabilities.local is True
