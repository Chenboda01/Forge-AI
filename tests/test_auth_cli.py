from __future__ import annotations

from typer.testing import CliRunner

import forge.cli as cli_module
from forge.forge_core.credentials import CREDENTIAL_SERVICE, CredentialStore

runner = CliRunner()
SECRET = "sk-test-not-real"


class MemoryBackend:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.values.pop((service, username), None)


def _install_store(monkeypatch, backend: MemoryBackend | None) -> CredentialStore:
    store = CredentialStore(backend)
    monkeypatch.setattr(cli_module, "system_credential_store", lambda: store)
    return store


def test_auth_login_stores_the_secret_without_echoing_it(monkeypatch) -> None:
    # Given: an available keyring and no environment credential
    backend = MemoryBackend()
    _install_store(monkeypatch, backend)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # When: the user authenticates with the hidden prompt
    result = runner.invoke(cli_module.app, ["auth", "login", "openai"], input=f"{SECRET}\n")

    # Then: the credential is stored and never rendered
    assert result.exit_code == 0
    assert backend.values[(CREDENTIAL_SERVICE, "OPENAI_API_KEY")] == SECRET
    assert SECRET not in result.output
    assert "Stored OPENAI_API_KEY" in result.output


def test_auth_login_prompts_for_a_provider_when_omitted(monkeypatch) -> None:
    # Given: an available keyring and an interactive provider list
    backend = MemoryBackend()
    _install_store(monkeypatch, backend)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # When: the user selects the second provider and enters the key
    result = runner.invoke(
        cli_module.app,
        ["auth", "login"],
        input=f"2\n{SECRET}\n",
    )

    # Then: the numbered selection resolves to OpenAI and is stored
    assert result.exit_code == 0
    assert backend.values[(CREDENTIAL_SERVICE, "OPENAI_API_KEY")] == SECRET
    assert SECRET not in result.output


def test_auth_login_rejects_an_unknown_provider(monkeypatch) -> None:
    _install_store(monkeypatch, MemoryBackend())

    # When: the provider id is not in the catalog
    result = runner.invoke(cli_module.app, ["auth", "login", "does-not-exist"])

    # Then: Forge fails closed and lists the supported providers
    assert result.exit_code == 1
    assert "Unknown provider" in result.output
    assert "openai" in result.output


def test_auth_login_asks_before_accepting_a_typo_correction(monkeypatch) -> None:
    # Given: an interactive terminal and a misspelled provider
    backend = MemoryBackend()
    _install_store(monkeypatch, backend)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(cli_module, "is_interactive_terminal", lambda: True)

    # When: the user confirms the suggested provider and enters the key
    result = runner.invoke(
        cli_module.app,
        ["auth", "login", "antropic"],
        input=f"y\n{SECRET}\n",
    )

    # Then: the correction is used and the secret is not echoed
    assert result.exit_code == 0
    assert "Did you mean 'anthropic'?" in result.output
    assert backend.values[(CREDENTIAL_SERVICE, "ANTHROPIC_API_KEY")] == SECRET
    assert SECRET not in result.output


def test_auth_login_suggests_a_correction_without_a_terminal(monkeypatch) -> None:
    _install_store(monkeypatch, MemoryBackend())

    # When: a misspelled provider is given non-interactively
    result = runner.invoke(cli_module.app, ["auth", "login", "antropic"])

    # Then: Forge suggests the closest provider and still fails closed
    assert result.exit_code == 1
    assert "Did you mean 'anthropic'?" in result.output
    assert "Available providers:" in result.output


def test_auth_login_skips_local_providers(monkeypatch) -> None:
    _install_store(monkeypatch, MemoryBackend())

    # When: the user selects a local provider
    result = runner.invoke(cli_module.app, ["auth", "login", "ollama"])

    # Then: no credential prompt or storage is attempted
    assert result.exit_code == 0
    assert "does not require an API key" in result.output


def test_auth_list_reports_status_without_revealing_secrets(monkeypatch) -> None:
    # Given: one configured keyring credential and a missing environment credential
    backend = MemoryBackend()
    backend.set_password(CREDENTIAL_SERVICE, "OPENAI_API_KEY", SECRET)
    _install_store(monkeypatch, backend)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    # When: the user lists credential status
    result = runner.invoke(cli_module.app, ["auth", "list"])

    # Then: status is reported without the secret value
    assert result.exit_code == 0
    assert "openai: OpenAI (configured)" in result.output
    assert "anthropic: Anthropic (missing ANTHROPIC_API_KEY)" in result.output
    assert "ollama: Ollama (local)" in result.output
    assert SECRET not in result.output


def test_auth_logout_removes_the_stored_secret(monkeypatch) -> None:
    # Given: a stored provider credential
    backend = MemoryBackend()
    backend.set_password(CREDENTIAL_SERVICE, "OPENAI_API_KEY", SECRET)
    _install_store(monkeypatch, backend)

    # When: the user logs the provider out
    result = runner.invoke(cli_module.app, ["auth", "logout", "openai"])

    # Then: the keyring entry is removed without echoing the value
    assert result.exit_code == 0
    assert backend.values == {}
    assert SECRET not in result.output
    assert "Removed OPENAI_API_KEY" in result.output


def test_auth_login_fails_closed_without_a_secure_store(monkeypatch) -> None:
    # Given: an unavailable secure credential store
    _install_store(monkeypatch, None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # When: the user tries to store a credential
    result = runner.invoke(cli_module.app, ["auth", "login", "openai"], input=f"{SECRET}\n")

    # Then: Forge refuses to persist a plaintext fallback
    assert result.exit_code == 1
    assert "secure operating-system keyring" in result.output
    assert SECRET not in result.output
