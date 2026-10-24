import stat
from pathlib import Path

import pytest

from forge.forge_core.preferences import (
    PreferencesError,
    UiPreferences,
    get_user_preferences_path,
    load_preferences,
    save_preferences,
)


def test_preferences_path_uses_xdg_config_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: an XDG configuration home
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    # When: Forge locates per-user preferences
    path = get_user_preferences_path()

    # Then: preferences stay in the Forge-specific directory outside any workspace
    assert path == tmp_path / "forge" / "preferences.toml"


def test_missing_preferences_return_defaults(tmp_path: Path) -> None:
    # Given: a user who has never saved interface preferences
    # When: Forge loads the missing file
    preferences = load_preferences(tmp_path / "missing.toml")

    # Then: built-in defaults apply without creating state
    assert preferences == UiPreferences()


def test_saved_preferences_round_trip_with_owner_only_permissions(tmp_path: Path) -> None:
    # Given: a nested per-user preferences location
    target = tmp_path / "config" / "preferences.toml"

    # When: Forge saves a theme choice
    save_preferences(UiPreferences(theme="cyber"), target)

    # Then: the file is private, deterministic, and readable back
    assert load_preferences(target) == UiPreferences(theme="cyber")
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert 'theme = "cyber"' in target.read_text(encoding="utf-8")


def test_preferences_reject_unknown_top_level_settings(tmp_path: Path) -> None:
    # Given: a preferences file that tries to set provider routing
    target = tmp_path / "preferences.toml"
    target.write_text('model = "openai"\n[ui]\ntheme = "cyber"\n', encoding="utf-8")

    # When / Then: only interface preferences are accepted
    with pytest.raises(PreferencesError) as raised:
        load_preferences(target)
    assert "Unknown setting: model" in str(raised.value)


def test_preferences_reject_unknown_ui_settings(tmp_path: Path) -> None:
    # Given: a preferences file with an unsupported interface setting
    target = tmp_path / "preferences.toml"
    target.write_text('[ui]\ntheme = "cyber"\nfont = "mono"\n', encoding="utf-8")

    # When / Then: the source and key are reported without echoing values
    with pytest.raises(PreferencesError) as raised:
        load_preferences(target)
    assert "Unknown [ui] setting: font" in str(raised.value)
    assert "mono" not in str(raised.value)


def test_preferences_reject_invalid_toml(tmp_path: Path) -> None:
    # Given: malformed preferences
    target = tmp_path / "preferences.toml"
    target.write_text("[ui\n", encoding="utf-8")

    # When / Then: Forge fails closed with a source-specific error
    with pytest.raises(PreferencesError, match="invalid TOML"):
        load_preferences(target)


def test_preferences_reject_blank_theme(tmp_path: Path) -> None:
    # Given: a blank saved theme
    target = tmp_path / "preferences.toml"
    target.write_text('[ui]\ntheme = "  "\n', encoding="utf-8")

    # When / Then: the value is rejected instead of being silently applied
    with pytest.raises(PreferencesError, match="non-empty"):
        load_preferences(target)
