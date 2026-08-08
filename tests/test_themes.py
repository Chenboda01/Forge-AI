import pytest

from forge.ui.app import ForgeApp
from forge.ui.themes import THEMES


@pytest.mark.asyncio
async def test_additional_themes_are_registered_and_applicable() -> None:
    # Given: the expanded set of readable Forge palettes
    expected = {"solarized", "matrix", "dusk", "high-contrast"}
    app = ForgeApp(skip_startup=True)

    async with app.run_test(size=(100, 32)) as pilot:
        # When: a high-contrast palette is selected
        app.apply_theme("high-contrast")
        await pilot.pause()

        # Then: every new palette is available and the selection reaches Textual
        assert expected <= THEMES.keys()
        assert app._current_theme == "high-contrast"
        assert str(app.screen.styles.background) == "Color(0, 0, 0)"
