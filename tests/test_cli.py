from pathlib import Path
from typing import NoReturn

from typer.testing import CliRunner

import forge.cli as cli_module
from forge.forge import build_runtime as build_test_runtime
from forge.forge_core.agent import AgentMode
from forge.forge_core.config import ForgeConfig
from forge.forge_core.provider import ForgeProviderError, ProviderHealth
from forge.ui.state import ForgeRuntime

runner = CliRunner()


def test_help_lists_supported_commands() -> None:
    # Given: the Forge command-line application
    # When: a user asks for command help
    result = runner.invoke(cli_module.app, ["--help"])

    # Then: the supported command surface is visible and successful
    assert result.exit_code == 0
    assert "doctor" in result.output
    assert "chat" in result.output
    assert "╭" not in result.output


def test_version_reports_release_without_starting_runtime(monkeypatch) -> None:
    # Given: a runtime builder that must not be used for version output
    monkeypatch.setattr(cli_module, "build_runtime", _unexpected_runtime)

    # When: a user asks for Forge's version
    result = runner.invoke(cli_module.app, ["--version"])

    # Then: the release version is emitted without provider initialization
    assert result.exit_code == 0
    assert "5.0.0" in result.output


def test_doctor_reports_project_directory(monkeypatch, tmp_path: Path) -> None:
    # Given: a project directory and a non-interactive terminal
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli_module, "is_interactive_terminal", lambda: False)

    # When: a user runs the diagnostics command
    result = runner.invoke(cli_module.app, ["doctor"])

    # Then: Forge reports its project context with a plain-text fallback
    assert result.exit_code == 0
    assert "Forge Doctor" in result.output
    assert f"Project directory: {tmp_path.resolve()}" in result.output
    assert "Terminal: plain-text" in result.output


def test_chat_reports_plain_text_fallback_without_interactive_terminal(monkeypatch) -> None:
    # Given: a terminal that cannot support the Textual interface
    monkeypatch.setattr(cli_module, "is_interactive_terminal", lambda: False)
    monkeypatch.setattr(cli_module, "build_runtime", _unexpected_runtime)

    # When: a user starts chat
    result = runner.invoke(cli_module.app, ["chat"])

    # Then: Forge returns a useful plain-text error without starting a provider
    assert result.exit_code == 1
    assert "interactive terminal" in result.output


def test_chat_uses_model_override_from_command_line(monkeypatch) -> None:
    # Given: an interactive terminal and a command-line model override
    monkeypatch.setattr(cli_module, "is_interactive_terminal", lambda: True)

    # When: the override names an unknown model
    result = runner.invoke(cli_module.app, ["chat", "--model", "command-line-model"])

    # Then: the parsed override reaches model selection rather than being ignored
    assert result.exit_code == 1
    assert "Unknown model 'command-line-model'" in result.output


def test_chat_routes_explicit_build_mode_to_runtime(monkeypatch) -> None:
    # Given: an interactive terminal and a runtime builder recording the selected mode
    captured: dict[str, object] = {}
    runtime = object()

    def record_runtime(
        *, configuration: ForgeConfig, mode: AgentMode, lifecycle: object = None
    ) -> object:
        captured["configuration"] = configuration
        captured["mode"] = mode
        captured["lifecycle"] = lifecycle
        return runtime

    class RecordingApp:
        def __init__(self, received_runtime: object) -> None:
            captured["runtime"] = received_runtime

        def run(self) -> None:
            return None

    monkeypatch.setattr(cli_module, "is_interactive_terminal", lambda: True)
    monkeypatch.setattr(cli_module, "build_runtime", record_runtime)
    monkeypatch.setattr(cli_module, "ForgeApp", RecordingApp)

    # When: the user explicitly selects mutation-capable operation
    result = runner.invoke(cli_module.app, ["chat", "--mode", "build"])

    # Then: BUILD reaches runtime composition and is not inferred from model output
    assert result.exit_code == 0
    assert captured["mode"] is AgentMode.BUILD
    assert captured["runtime"] is runtime


def test_chat_passes_and_releases_the_herdr_reporter(monkeypatch) -> None:
    # Given: a Herdr pane reporter and a runtime that records its lifecycle adapter
    captured: dict[str, object] = {}

    class FakeReporter:
        released = False
        reported_idle = False

        def report_idle(self) -> None:
            self.reported_idle = True

        def release(self) -> None:
            self.released = True

    reporter = FakeReporter()

    class FakeHerdrReporter:
        @classmethod
        def from_environment(cls) -> FakeReporter:
            return reporter

    def record_runtime(
        *, configuration: ForgeConfig, mode: AgentMode, lifecycle: object = None
    ) -> object:
        captured["lifecycle"] = lifecycle
        return object()

    class RecordingApp:
        def __init__(self, received_runtime: object) -> None:
            return None

        def run(self) -> None:
            return None

    monkeypatch.setattr(cli_module, "is_interactive_terminal", lambda: True)
    monkeypatch.setattr(cli_module, "HerdrReporter", FakeHerdrReporter)
    monkeypatch.setattr(cli_module, "build_runtime", record_runtime)
    monkeypatch.setattr(cli_module, "ForgeApp", RecordingApp)

    # When: the agent runs in a Herdr pane
    result = runner.invoke(cli_module.app, ["chat"])

    # Then: the reporter observes the runtime and is released when Forge exits
    assert result.exit_code == 0
    assert captured["lifecycle"] is reporter
    assert reporter.reported_idle is True
    assert reporter.released is True


def test_chat_reports_expected_provider_configuration_errors(monkeypatch) -> None:
    # Given: an interactive terminal with an invalid provider configuration
    monkeypatch.setattr(cli_module, "is_interactive_terminal", lambda: True)
    monkeypatch.setattr(cli_module, "build_runtime", _provider_error)

    # When: a user starts chat
    result = runner.invoke(cli_module.app, ["chat"])

    # Then: Forge reports the expected error without a traceback
    assert result.exit_code == 1
    assert "Forge could not start: model is unavailable" in result.output
    assert "Traceback" not in result.output


def test_chat_returns_interrupt_exit_code(monkeypatch, tmp_path: Path) -> None:
    # Given: an interactive terminal and a Textual app interrupted by Ctrl+C
    monkeypatch.setenv("FORGE_MODEL", "ollama")
    runtime = build_test_runtime(tmp_path)
    monkeypatch.setattr(cli_module, "is_interactive_terminal", lambda: True)
    monkeypatch.setattr(cli_module, "build_runtime", lambda configuration, **_kwargs: runtime)
    monkeypatch.setattr(cli_module, "ForgeApp", _InterruptingApp)

    # When: a user starts chat and interrupts it
    result = runner.invoke(cli_module.app, ["chat"])

    # Then: Forge exits predictably without exposing a traceback
    assert result.exit_code == 130
    assert "Forge interrupted." in result.output
    assert "Traceback" not in result.output


def test_providers_and_models_do_not_render_configured_api_keys(monkeypatch) -> None:
    # Given: a configured cloud-provider credential
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")

    # When: a user lists providers and models
    providers_result = runner.invoke(cli_module.app, ["providers"])
    models_result = runner.invoke(cli_module.app, ["models"])

    # Then: both command surfaces are usable without revealing the credential
    assert providers_result.exit_code == 0
    assert models_result.exit_code == 0
    assert "openai" in providers_result.output
    assert "openai" in models_result.output
    assert "sk-test-not-real" not in providers_result.output
    assert "sk-test-not-real" not in models_result.output


def test_provider_test_reports_a_successful_mocked_connection(monkeypatch) -> None:
    # Given: a provider connection test with an injected successful result
    monkeypatch.setattr(cli_module, "ForgeProvider", _HealthyProvider)

    # When: a user tests the Ollama provider
    result = runner.invoke(cli_module.app, ["provider", "test", "ollama"])

    # Then: the command returns an explicit success result without a traceback
    assert result.exit_code == 0
    assert "Provider test: Local" in result.output
    assert "reachable" in result.output
    assert "Traceback" not in result.output


def _unexpected_runtime() -> NoReturn:
    raise AssertionError("The CLI command must not build a runtime.")


def _provider_error(configuration: ForgeConfig, **_kwargs: object) -> NoReturn:
    raise ForgeProviderError("model is unavailable")


class _InterruptingApp:
    def __init__(self, runtime: ForgeRuntime) -> None:
        self.runtime = runtime

    def run(self) -> NoReturn:
        raise KeyboardInterrupt


class _HealthyProvider:
    def __init__(self, _model: str, **_kwargs) -> None:
        pass

    def test_connection(self) -> ProviderHealth:
        return ProviderHealth(
            provider="Local",
            model_id="ollama/llama3.2:1b",
            reachable=True,
            detail="Connection succeeded.",
        )
