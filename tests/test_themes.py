import pytest
from textual.widgets import Static, TextArea

from forge.forge_core.preferences import UiPreferences, load_preferences
from forge.ui.app import ForgeApp
from forge.ui.theme_select import ThemeSelectScreen
from forge.ui.themes import DEFAULT_THEME, THEMES


@pytest.mark.asyncio
async def test_additional_themes_are_registered_and_applicable(tmp_path) -> None:
    # Given: the expanded set of readable Forge palettes
    expected = {"solarized", "matrix", "dusk", "high-contrast"}
    app = ForgeApp(skip_startup=True, preferences_path=tmp_path / "preferences.toml")

    async with app.run_test(size=(100, 32)) as pilot:
        # When: a high-contrast palette is selected
        app.apply_theme("high-contrast")
        await pilot.pause()

        # Then: every new palette is available and the selection reaches Textual
        assert expected <= THEMES.keys()
        assert app.active_theme == "high-contrast"
        assert str(app.screen.styles.background) == "Color(0, 0, 0)"


@pytest.mark.asyncio
async def test_theme_choice_is_saved_for_the_operating_system_user(tmp_path) -> None:
    # Given: a user with no saved preferences
    preferences_path = tmp_path / "config" / "preferences.toml"
    app = ForgeApp(skip_startup=True, preferences_path=preferences_path)

    async with app.run_test(size=(100, 32)) as pilot:
        composer = app.query_one("#composer", TextArea)
        composer.text = "/theme"
        await pilot.press("enter")
        await pilot.pause()

        # When: the user moves from the active theme to cyber
        await pilot.press("down", "enter")
        await pilot.pause()

        # Then: the palette and header reflect the choice immediately
        assert app.active_theme == "cyber"
        header = app.query_one("#header-right", Static).render().plain
        assert "cyber" in header

    # Then: a new Forge process restores the saved theme for this user
    assert load_preferences(preferences_path) == UiPreferences(theme="cyber")
    restored = ForgeApp(skip_startup=True, preferences_path=preferences_path)
    assert restored.active_theme == "cyber"
    assert restored.theme == "cyber"


@pytest.mark.asyncio
async def test_theme_picker_focuses_the_saved_theme(tmp_path) -> None:
    # Given: a user whose saved theme is ocean
    preferences_path = tmp_path / "preferences.toml"
    preferences_path.write_text('[ui]\ntheme = "ocean"\n', encoding="utf-8")
    app = ForgeApp(skip_startup=True, preferences_path=preferences_path)

    async with app.run_test(size=(100, 32)) as pilot:
        composer = app.query_one("#composer", TextArea)

        # When: the theme picker opens
        composer.text = "/theme"
        await pilot.press("enter")
        await pilot.pause()

        # Then: the saved theme is focused instead of the built-in default
        assert isinstance(app.screen, ThemeSelectScreen)
        assert app.screen.focused is not None
        assert app.screen.focused.id == "theme-ocean"


def test_unknown_saved_theme_falls_back_to_default(tmp_path) -> None:
    # Given: preferences naming a theme that this build no longer ships
    preferences_path = tmp_path / "preferences.toml"
    preferences_path.write_text('[ui]\ntheme = "missing"\n', encoding="utf-8")

    # When: Forge starts
    app = ForgeApp(skip_startup=True, preferences_path=preferences_path)

    # Then: the default palette is used safely
    assert app.active_theme == DEFAULT_THEME
