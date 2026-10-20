import os

import pytest

from forge.forge_core.credentials import (
    CredentialStore,
    CredentialStoreUnavailableError,
    resolve_credential,
    system_credential_store,
)


class FakeCredentialBackend:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}
        self.set_calls: list[tuple[str, str, str]] = []

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.set_calls.append((service, username, password))
        self.values[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.values.pop((service, username), None)


def test_credential_store_uses_backend_without_project_persistence(tmp_path) -> None:
    # Given: a synthetic credential and an available operating-system credential backend
    backend = FakeCredentialBackend()
    store = CredentialStore(backend)

    # When: Forge stores and retrieves the provider credential
    store.set("OPENAI_API_KEY", "synthetic-openai-credential-value")
    resolved = store.get("OPENAI_API_KEY")

    # Then: only the backend receives the value and no project file is created
    assert resolved == "synthetic-openai-credential-value"
    assert backend.set_calls == [
        ("forge-ai", "OPENAI_API_KEY", "synthetic-openai-credential-value")
    ]
    assert tuple(tmp_path.iterdir()) == ()


def test_environment_credential_is_session_only_and_not_persisted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: CI supplies a credential in the process environment
    backend = FakeCredentialBackend()
    store = CredentialStore(backend)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-environment-credential")

    # When: Forge resolves the provider credential
    resolved = resolve_credential("OPENAI_API_KEY", store)

    # Then: the environment wins without being copied to secure storage
    assert resolved == "synthetic-environment-credential"
    assert backend.set_calls == []


def test_unavailable_secure_store_fails_without_plaintext_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: neither an environment value nor an operating-system keyring is available
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    store = CredentialStore(None)

    # When / Then: reads remain empty and writes fail instead of creating a plaintext fallback
    assert resolve_credential("OPENAI_API_KEY", store) is None
    with pytest.raises(CredentialStoreUnavailableError, match="secure credential store"):
        store.set("OPENAI_API_KEY", "synthetic-secret-that-must-not-be-written")


def test_credential_names_reject_non_provider_environment_keys() -> None:
    # Given: a credential name outside Forge's supported provider key registry
    store = CredentialStore(FakeCredentialBackend())

    # When / Then: the secure store rejects the unsupported namespace
    with pytest.raises(ValueError, match="Unsupported provider credential"):
        store.get("HOME")

    assert os.environ.get("HOME") is not None


def test_system_store_rejects_backend_based_on_priority_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a user-selected backend that claims high priority without being OS-backed
    class UntrustedBackend(FakeCredentialBackend):
        priority = 100

    monkeypatch.setattr("forge.forge_core.credentials.keyring.get_keyring", UntrustedBackend)

    # When / Then: priority alone cannot authorize credential persistence
    with pytest.raises(CredentialStoreUnavailableError, match="secure credential store"):
        system_credential_store().set("OPENAI_API_KEY", "synthetic-secret-not-persisted")
