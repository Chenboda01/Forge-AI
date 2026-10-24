"""Per-user, non-secret interface preferences kept outside the workspace."""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .safe_io import atomic_write_text_beneath

MAX_PREFERENCES_BYTES: Final = 64_000
UI_TABLE: Final = "ui"
KNOWN_UI_SETTINGS: Final = frozenset({"theme"})


class PreferencesError(Exception):
    """Raised when a per-user preferences file cannot be safely used."""

    def __init__(self, source: str, detail: str) -> None:
        self.source = source
        self.detail = detail
        super().__init__(source, detail)

    def __str__(self) -> str:
        return f"{self.source}: {self.detail}"


@dataclass(frozen=True, slots=True)
class UiPreferences:
    """User-level interface preferences that never affect provider routing."""

    theme: str | None = None


def get_user_preferences_path() -> Path:
    """Return the per-user preferences path, honoring XDG_CONFIG_HOME."""
    config_home = os.getenv("XDG_CONFIG_HOME")
    if config_home:
        return Path(config_home).expanduser() / "forge" / "preferences.toml"
    return Path.home() / ".config" / "forge" / "preferences.toml"


def load_preferences(path: Path | None = None) -> UiPreferences:
    """Read preferences, returning defaults when the file does not exist."""
    target = path or get_user_preferences_path()
    try:
        with target.open("rb") as stream:
            content = stream.read(MAX_PREFERENCES_BYTES + 1)
    except FileNotFoundError:
        return UiPreferences()
    except OSError as error:
        raise PreferencesError(str(target), "could not be read.") from error
    if len(content) > MAX_PREFERENCES_BYTES:
        raise PreferencesError(str(target), "is too large.")
    try:
        document = tomllib.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise PreferencesError(str(target), "invalid TOML.") from error
    return _parse_preferences(document, str(target))


def save_preferences(preferences: UiPreferences, path: Path | None = None) -> None:
    """Persist preferences atomically with owner-only permissions."""
    target = path or get_user_preferences_path()
    directory = target.parent
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as error:
        raise PreferencesError(str(target), "could not be written.") from error
    lines = [f"[{UI_TABLE}]"]
    if preferences.theme:
        lines.append(f"theme = {json.dumps(preferences.theme)}")
    try:
        atomic_write_text_beneath(directory, target, "\n".join(lines) + "\n")
    except (OSError, ValueError) as error:
        raise PreferencesError(str(target), "could not be written.") from error


def _parse_preferences(document: dict[str, object], source: str) -> UiPreferences:
    unknown_settings = sorted(set(document).difference({UI_TABLE}))
    if unknown_settings:
        raise PreferencesError(source, f"Unknown setting: {', '.join(unknown_settings)}")
    table = document.get(UI_TABLE, {})
    if not isinstance(table, dict):
        raise PreferencesError(source, f"Invalid [{UI_TABLE}] table.")
    unknown_ui_settings = sorted(set(table).difference(KNOWN_UI_SETTINGS))
    if unknown_ui_settings:
        raise PreferencesError(
            source,
            f"Unknown [{UI_TABLE}] setting: {', '.join(unknown_ui_settings)}",
        )
    theme = table.get("theme")
    if theme is None:
        return UiPreferences()
    if not isinstance(theme, str) or not theme.strip():
        raise PreferencesError(source, "Setting 'theme' must be a non-empty string.")
    return UiPreferences(theme=theme.strip())
