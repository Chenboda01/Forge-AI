import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import Field, ValidationError, field_validator
from pydantic_core import PydanticCustomError
from pydantic_settings import BaseSettings, SettingsConfigDict

from .credentials import resolve_credential
from .models import DEFAULT_MODEL
from .safe_io import SafeReadError, read_bytes_beneath

PROJECT_CONFIG_PATH: Final = Path(".forge") / "config.toml"
MODEL_SETTING: Final = "model"
MODEL_ID_SETTING: Final = "model_id"
BASE_URL_SETTING: Final = "base_url"
TIMEOUT_SETTING: Final = "timeout_seconds"
RETRY_LIMIT_SETTING: Final = "retry_limit"
MAX_CONFIG_BYTES: Final = 1_000_000
KNOWN_SETTINGS: Final = frozenset(
    {
        MODEL_SETTING,
        MODEL_ID_SETTING,
        BASE_URL_SETTING,
        TIMEOUT_SETTING,
        RETRY_LIMIT_SETTING,
    }
)
PROJECT_SETTINGS: Final = frozenset({TIMEOUT_SETTING, RETRY_LIMIT_SETTING})


class ConfigurationError(Exception):
    """Raised when a configuration source cannot be safely used."""

    def __init__(self, source: str, detail: str) -> None:
        self.source = source
        self.detail = detail
        super().__init__(source, detail)

    def __str__(self) -> str:
        return f"{self.source}: {self.detail}"


@dataclass(frozen=True, slots=True)
class ConfigurationOverrides:
    model: str | None = None
    model_id: str | None = None
    base_url: str | None = None
    timeout_seconds: int | str | None = None
    retry_limit: int | str | None = None


class ForgeConfig(BaseSettings):
    """Validated non-secret runtime configuration."""

    model_config = SettingsConfigDict(
        env_prefix="FORGE_",
        env_file=None,
        extra="forbid",
        frozen=True,
    )

    model: str
    model_id: str | None = None
    base_url: str | None = None
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    retry_limit: int = Field(default=0, ge=0, le=5)

    @field_validator(MODEL_SETTING)
    @classmethod
    def normalize_model(cls, value: str) -> str:
        model = value.strip()
        if model:
            return model
        raise PydanticCustomError("blank_model", "model must not be blank")

    @field_validator(MODEL_ID_SETTING, BASE_URL_SETTING)
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if text:
            return text
        raise PydanticCustomError("blank_text", "must not be blank")


def get_user_config_path() -> Path:
    config_home = os.getenv("XDG_CONFIG_HOME")
    if config_home:
        return Path(config_home).expanduser() / "forge" / "config.toml"
    return Path.home() / ".config" / "forge" / "config.toml"


def load_configuration(
    command_line: ConfigurationOverrides | None = None,
    *,
    project_root: Path | None = None,
    user_config_path: Path | None = None,
) -> ForgeConfig:
    """Resolve non-secret configuration in documented source-precedence order."""
    command_line_overrides = command_line or ConfigurationOverrides()
    resolved_project_root = (project_root or Path.cwd()).resolve()
    resolved_user_config_path = user_config_path or get_user_config_path()
    user_overrides = _load_toml_overrides(resolved_user_config_path)
    project_config_path = resolved_project_root / PROJECT_CONFIG_PATH
    project_overrides = _load_toml_overrides(
        project_config_path,
        trusted_root=resolved_project_root,
        allowed_settings=PROJECT_SETTINGS,
    )
    environment_overrides = ConfigurationOverrides(
        model=os.getenv("FORGE_MODEL"),
        model_id=os.getenv("FORGE_MODEL_ID"),
        base_url=os.getenv("FORGE_BASE_URL"),
        timeout_seconds=os.getenv("FORGE_TIMEOUT_SECONDS"),
        retry_limit=os.getenv("FORGE_RETRY_LIMIT"),
    )
    sources = (
        (command_line_overrides, "command-line options"),
        (project_overrides, str(project_config_path)),
        (user_overrides, str(resolved_user_config_path)),
        (environment_overrides, "environment"),
    )
    model, model_source = _resolve_setting(
        DEFAULT_MODEL, tuple((item.model, source) for item, source in sources)
    )
    model_id, model_id_source = _resolve_setting(
        None, tuple((item.model_id, source) for item, source in sources)
    )
    base_url, base_url_source = _resolve_setting(
        None, tuple((item.base_url, source) for item, source in sources)
    )
    timeout_seconds, timeout_source = _resolve_setting(
        30, tuple((item.timeout_seconds, source) for item, source in sources)
    )
    retry_limit, retry_limit_source = _resolve_setting(
        0, tuple((item.retry_limit, source) for item, source in sources)
    )
    setting_sources = {
        MODEL_SETTING: model_source,
        MODEL_ID_SETTING: model_id_source,
        BASE_URL_SETTING: base_url_source,
        TIMEOUT_SETTING: timeout_source,
        RETRY_LIMIT_SETTING: retry_limit_source,
    }
    try:
        return ForgeConfig.model_validate(
            {
                "model": model,
                "model_id": model_id,
                "base_url": base_url,
                "timeout_seconds": timeout_seconds,
                "retry_limit": retry_limit,
            }
        )
    except ValidationError as error:
        setting = _validation_setting(error)
        detail = (
            "Setting 'model' must be a non-empty string."
            if setting == MODEL_SETTING
            else f"Invalid setting: {setting}."
        )
        raise ConfigurationError(
            setting_sources.get(setting, "provider configuration"), detail
        ) from error


def _resolve_setting(
    default: str | int | None,
    values: tuple[tuple[str | int | None, str], ...],
) -> tuple[str | int | None, str]:
    for value, source in values:
        if value is not None:
            return value, source
    return default, "built-in defaults"


def _validation_setting(error: ValidationError) -> str:
    details = error.errors()
    if details:
        location = details[0].get("loc")
        if isinstance(location, tuple) and location and isinstance(location[0], str):
            return location[0]
    return "provider configuration"


def _load_toml_overrides(
    path: Path,
    *,
    trusted_root: Path | None = None,
    allowed_settings: frozenset[str] = KNOWN_SETTINGS,
) -> ConfigurationOverrides:
    try:
        if trusted_root is None:
            with path.open("rb") as stream:
                settings = tomllib.load(stream)
        else:
            settings = tomllib.loads(
                read_bytes_beneath(trusted_root, path, max_bytes=MAX_CONFIG_BYTES).decode("utf-8")
            )
    except FileNotFoundError:
        return ConfigurationOverrides()
    except SafeReadError as error:
        if error.missing:
            return ConfigurationOverrides()
        raise ConfigurationError(str(path), "could not be read.") from error
    except UnicodeDecodeError as error:
        raise ConfigurationError(str(path), "could not be read.") from error
    except tomllib.TOMLDecodeError as error:
        raise ConfigurationError(str(path), "invalid TOML.") from error
    except OSError as error:
        raise ConfigurationError(str(path), "could not be read.") from error

    unknown_settings = sorted(set(settings).difference(KNOWN_SETTINGS))
    if unknown_settings:
        raise ConfigurationError(str(path), f"Unknown setting: {', '.join(unknown_settings)}")
    prohibited_settings = sorted(set(settings).difference(allowed_settings))
    if prohibited_settings:
        raise ConfigurationError(
            str(path),
            f"Project provider routing setting is not permitted: {', '.join(prohibited_settings)}",
        )
    return ConfigurationOverrides(
        model=settings.get(MODEL_SETTING),
        model_id=settings.get(MODEL_ID_SETTING),
        base_url=settings.get(BASE_URL_SETTING),
        timeout_seconds=settings.get(TIMEOUT_SETTING),
        retry_limit=settings.get(RETRY_LIMIT_SETTING),
    )


def get_api_key(variable_name: str | None) -> str | None:
    return resolve_credential(variable_name)


def get_default_model() -> str:
    return load_configuration().model
