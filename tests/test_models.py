from dataclasses import FrozenInstanceError

import pytest

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


def test_default_model_is_ollama():
    assert DEFAULT_MODEL == "ollama"


def test_all_models_have_required_fields():
    for alias, model in MODELS.items():
        assert model.name, f"Model {alias} has no name"
        assert model.model_id, f"Model {alias} has no model_id"
        assert model.provider, f"Model {alias} has no provider"
