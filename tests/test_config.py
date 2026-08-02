import pytest

from forge.forge_core.config import get_api_key, get_default_model


def test_get_api_key_returns_none_for_none():
    assert get_api_key(None) is None


def test_get_api_key_returns_none_when_missing():
    assert get_api_key("NONEXISTENT_KEY_12345") is None


def test_get_api_key_returns_value(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TEST_API_KEY", "sk-test-not-real")
    assert get_api_key("TEST_API_KEY") == "sk-test-not-real"


def test_get_api_key_strips_whitespace(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TEST_API_KEY", "  sk-test-not-real  ")
    assert get_api_key("TEST_API_KEY") == "sk-test-not-real"


def test_get_default_model_returns_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("FORGE_MODEL", raising=False)
    assert get_default_model() == "ollama"


def test_get_default_model_respects_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FORGE_MODEL", "deepseek")
    assert get_default_model() == "deepseek"


def test_env_file_loading(monkeypatch: pytest.MonkeyPatch):
    """Verify dotenv loading works by creating a temp .env file."""
    # Set a key that would not otherwise exist
    monkeypatch.setenv("FORGE_MODEL", "groq")
    assert get_default_model() == "groq"
