from pathlib import Path

import pytest

from forge.forge_core.config import (
    ConfigurationError,
    ConfigurationOverrides,
    get_user_config_path,
    load_configuration,
)
from forge.forge_core.models import DEFAULT_MODEL


def test_load_configuration_uses_default_when_sources_are_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: no command-line, project, user, or environment configuration
    monkeypatch.delenv("FORGE_MODEL", raising=False)

    # When: Forge resolves configuration
    config = load_configuration(
        project_root=tmp_path,
        user_config_path=tmp_path / "user-config.toml",
    )

    # Then: the built-in model remains selected
    assert config.model == DEFAULT_MODEL


def test_load_configuration_uses_environment_when_higher_sources_are_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: a model supplied only through the environment
    monkeypatch.setenv("FORGE_MODEL", "environment-model")

    # When: Forge resolves configuration
    config = load_configuration(
        project_root=tmp_path,
        user_config_path=tmp_path / "user-config.toml",
    )

    # Then: the environment overrides the built-in default
    assert config.model == "environment-model"


def test_load_configuration_uses_user_config_over_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: conflicting user and environment model settings
    monkeypatch.setenv("FORGE_MODEL", "environment-model")
    user_config_path = tmp_path / "user-config.toml"
    _write_toml(user_config_path, 'model = "user-model"\n')

    # When: Forge resolves configuration
    config = load_configuration(project_root=tmp_path, user_config_path=user_config_path)

    # Then: the user configuration has higher precedence
    assert config.model == "user-model"


def test_load_configuration_uses_project_execution_limits_over_user_and_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: project execution limits and trusted model routing settings
    monkeypatch.setenv("FORGE_MODEL", "environment-model")
    user_config_path = tmp_path / "user-config.toml"
    _write_toml(user_config_path, 'model = "user-model"\n')
    _write_toml(tmp_path / ".forge" / "config.toml", "timeout_seconds = 12\n")

    # When: Forge resolves configuration
    config = load_configuration(project_root=tmp_path, user_config_path=user_config_path)

    # Then: the repository tunes bounded execution without selecting a provider
    assert config.model == "user-model"
    assert config.timeout_seconds == 12


@pytest.mark.parametrize(
    ("setting", "value"),
    (
        ("model", '"project-model"'),
        ("model_id", '"openai/project-controlled"'),
        ("base_url", '"https://project-controlled.example.test/v1"'),
    ),
)
def test_load_configuration_rejects_project_control_of_provider_routing(
    tmp_path: Path,
    setting: str,
    value: str,
) -> None:
    # Given: an untrusted repository attempts to redirect provider traffic
    project_config_path = tmp_path / ".forge" / "config.toml"
    _write_toml(project_config_path, f"{setting} = {value}\n")

    # When / Then: repository-controlled routing is rejected at the config boundary
    with pytest.raises(
        ConfigurationError,
        match=f"Project provider routing setting is not permitted: {setting}",
    ):
        load_configuration(project_root=tmp_path, user_config_path=tmp_path / "user.toml")


def test_load_configuration_uses_command_line_override_over_all_other_sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: every trusted source supplies a different model
    monkeypatch.setenv("FORGE_MODEL", "environment-model")
    user_config_path = tmp_path / "user-config.toml"
    _write_toml(user_config_path, 'model = "user-model"\n')
    _write_toml(tmp_path / ".forge" / "config.toml", "timeout_seconds = 12\n")

    # When: Forge receives a command-line override
    config = load_configuration(
        ConfigurationOverrides(model="command-line-model"),
        project_root=tmp_path,
        user_config_path=user_config_path,
    )

    # Then: the command-line value wins
    assert config.model == "command-line-model"
    assert config.timeout_seconds == 12


def test_get_user_config_path_uses_xdg_config_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: an XDG configuration home
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    # When: Forge locates user configuration
    path = get_user_config_path()

    # Then: the user configuration remains in the Forge-specific directory
    assert path == tmp_path / "forge" / "config.toml"


def test_load_configuration_uses_default_xdg_user_config_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: a model stored at Forge's XDG user configuration path
    config_home = tmp_path / "config-home"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.delenv("FORGE_MODEL", raising=False)
    _write_toml(config_home / "forge" / "config.toml", 'model = "user-model"\n')

    # When: Forge resolves a project without an overriding project configuration
    config = load_configuration(project_root=tmp_path / "project")

    # Then: the default user configuration path supplies the model
    assert config.model == "user-model"


def test_load_configuration_rejects_unknown_settings_without_leaking_values(tmp_path: Path) -> None:
    # Given: project configuration containing an unsupported secret-shaped setting
    _write_toml(tmp_path / ".forge" / "config.toml", 'api_key = "sk-test-not-real"\n')

    # When: Forge parses the project configuration
    with pytest.raises(ConfigurationError) as raised:
        load_configuration(project_root=tmp_path, user_config_path=tmp_path / "user-config.toml")

    # Then: the error identifies the key but never displays its value
    assert "Unknown setting: api_key" in str(raised.value)
    assert "sk-test-not-real" not in str(raised.value)


def test_load_configuration_rejects_invalid_toml(tmp_path: Path) -> None:
    # Given: malformed project configuration
    _write_toml(tmp_path / ".forge" / "config.toml", "model = [")

    # When: Forge parses the project configuration
    with pytest.raises(ConfigurationError) as raised:
        load_configuration(project_root=tmp_path, user_config_path=tmp_path / "user-config.toml")

    # Then: the user receives a clear source-specific validation error
    assert "invalid TOML" in str(raised.value)


def test_load_configuration_identifies_the_source_of_a_blank_model(tmp_path: Path) -> None:
    # Given: trusted user configuration with a valid TOML but blank model setting
    user_config_path = tmp_path / "user-config.toml"
    _write_toml(user_config_path, 'model = ""\n')

    # When: Forge validates the selected configuration
    with pytest.raises(ConfigurationError) as raised:
        load_configuration(project_root=tmp_path, user_config_path=user_config_path)

    # Then: the validation error names the failing source without rendering a value
    assert str(user_config_path) in str(raised.value)
    assert "non-empty string" in str(raised.value)


def test_configuration_representation_does_not_include_environment_secrets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: an environment containing a provider credential
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")

    # When: Forge resolves non-secret runtime configuration
    config = load_configuration(
        project_root=tmp_path,
        user_config_path=tmp_path / "user-config.toml",
    )

    # Then: the typed configuration representation cannot expose the credential
    assert "sk-test-not-real" not in repr(config)


def test_load_configuration_uses_environment_provider_runtime_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: provider runtime settings supplied through environment variables
    monkeypatch.setenv("FORGE_MODEL", "openai")
    monkeypatch.setenv("FORGE_MODEL_ID", "openai/gpt-test")
    monkeypatch.setenv("FORGE_BASE_URL", "https://models.example.test/v1")
    monkeypatch.setenv("FORGE_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("FORGE_RETRY_LIMIT", "3")

    # When: Forge resolves configuration
    config = load_configuration(
        project_root=tmp_path,
        user_config_path=tmp_path / "user-config.toml",
    )

    # Then: the provider receives validated non-secret runtime settings
    assert config.model == "openai"
    assert config.model_id == "openai/gpt-test"
    assert config.base_url == "https://models.example.test/v1"
    assert config.timeout_seconds == 12
    assert config.retry_limit == 3


def test_load_configuration_rejects_invalid_provider_timeout(tmp_path: Path) -> None:
    # Given: a project configuration with an invalid provider timeout
    _write_toml(tmp_path / ".forge" / "config.toml", "timeout_seconds = 0\n")

    # When: Forge parses the provider settings
    with pytest.raises(ConfigurationError) as raised:
        load_configuration(project_root=tmp_path, user_config_path=tmp_path / "user-config.toml")

    # Then: the invalid setting is rejected without exposing unrelated configuration
    assert "timeout_seconds" in str(raised.value)


def test_load_configuration_rejects_external_project_config_symlink(tmp_path: Path) -> None:
    # Given: project configuration redirected outside the project root
    project = tmp_path / "project"
    outside = tmp_path / "outside.toml"
    project.mkdir()
    (project / ".forge").mkdir()
    outside.write_text('model = "external-model"\n', encoding="utf-8")
    (project / ".forge" / "config.toml").symlink_to(outside)

    # When / Then: external configuration cannot influence provider selection
    with pytest.raises(ConfigurationError, match="could not be read"):
        load_configuration(project_root=project, user_config_path=project / "missing.toml")


@pytest.mark.parametrize(
    "setting",
    (
        'model = "openai"\n',
        'model_id = "openai/attacker-controlled"\n',
        'base_url = "https://attacker.invalid/v1"\n',
    ),
)
def test_project_configuration_cannot_control_provider_routing(
    tmp_path: Path,
    setting: str,
) -> None:
    # Given: provider routing supplied by untrusted repository configuration
    _write_toml(tmp_path / ".forge" / "config.toml", setting)

    # When / Then: repository content cannot select a provider or credential destination
    with pytest.raises(ConfigurationError, match="provider routing"):
        load_configuration(project_root=tmp_path, user_config_path=tmp_path / "missing.toml")


def _write_toml(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
