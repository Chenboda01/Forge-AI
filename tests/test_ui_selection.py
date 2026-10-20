import pytest
from textual.widgets import Input, OptionList, TextArea

from forge.forge import build_runtime
from forge.ui.app import ForgeApp
from forge.ui.command_palette import COMMANDS, CommandPaletteScreen
from forge.ui.model_select import ModelSelectScreen
from forge.ui.widgets import ConversationView


@pytest.mark.asyncio
async def test_typing_slash_opens_the_command_palette() -> None:
    # Given: a mounted Forge composer with focus
    app = ForgeApp(skip_startup=True)

    async with app.run_test(size=(120, 40)) as pilot:
        composer = app.query_one("#composer", TextArea)

        # When: the user types the palette trigger
        await pilot.press("slash")
        await pilot.pause()

        # Then: every command is listed without executing anything
        assert isinstance(app.screen, CommandPaletteScreen)
        options = app.screen.query_one("#palette-options", OptionList)
        assert options.option_count == len(COMMANDS)
        assert composer.text == "/"


@pytest.mark.asyncio
async def test_palette_filters_and_inserts_a_command() -> None:
    # Given: an open command palette
    app = ForgeApp(skip_startup=True)

    async with app.run_test(size=(120, 40)) as pilot:
        composer = app.query_one("#composer", TextArea)
        await pilot.press("slash")
        await pilot.pause()

        # When: the user filters for the model picker and selects it
        filter_input = app.screen.query_one("#palette-filter", Input)
        filter_input.value = "choose"
        await pilot.pause()
        options = app.screen.query_one("#palette-options", OptionList)
        assert options.option_count == 1
        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause()

        # Then: the command is inserted for review instead of executed
        assert not isinstance(app.screen, CommandPaletteScreen)
        assert composer.text == "/model "


@pytest.mark.asyncio
async def test_bare_model_command_opens_the_searchable_picker(monkeypatch, tmp_path) -> None:
    # Given: a connected local runtime
    monkeypatch.setenv("FORGE_MODEL", "ollama")
    runtime = build_runtime(tmp_path)
    app = ForgeApp(runtime, skip_startup=True)

    async with app.run_test(size=(120, 40)) as pilot:
        composer = app.query_one("#composer", TextArea)
        composer.text = "/model"
        await pilot.press("enter")
        await pilot.pause()

        # When: the user filters and selects a model
        assert isinstance(app.screen, ModelSelectScreen)
        filter_input = app.screen.query_one("#model-filter", Input)
        filter_input.value = "ollama-qwen"
        await pilot.pause()
        options = app.screen.query_one("#model-options", OptionList)
        assert options.option_count == 1
        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause()

        # Then: provider state changes only through the command service
        assert not isinstance(app.screen, ModelSelectScreen)
        assert runtime.provider.model.name == "Ollama Qwen Coder"
        assert (
            "Switched to Ollama Qwen Coder."
            in app.query_one("#conversation", ConversationView).transcript
        )


@pytest.mark.asyncio
async def test_model_picker_requires_a_connected_runtime() -> None:
    # Given: Forge without a model runtime
    app = ForgeApp(skip_startup=True)

    async with app.run_test(size=(100, 32)) as pilot:
        composer = app.query_one("#composer", TextArea)

        # When: the user asks for the model picker
        composer.text = "/model"
        await pilot.press("enter")
        await pilot.pause()

        # Then: Forge reports the missing runtime instead of opening a picker
        assert not isinstance(app.screen, ModelSelectScreen)
        assert (
            "No model runtime is connected."
            in app.query_one("#conversation", ConversationView).transcript
        )
