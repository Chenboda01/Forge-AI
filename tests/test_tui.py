import shlex
from importlib import import_module
from importlib.util import find_spec
from time import monotonic

import pytest
from textual import events
from textual.widgets import ProgressBar, Static, TextArea

import forge.forge_core.updates as updates_core
import forge.ui.app as app_module
import forge.ui.commands as commands_module
from forge.forge import build_runtime
from forge.ui.app import ForgeApp
from forge.ui.approval import ApprovalScreen
from forge.ui.commands import CommandService
from forge.ui.state import estimate_cost
from forge.ui.theme_select import ThemeSelectScreen
from forge.ui.widgets import ConversationView


def test_textual_app_has_dedicated_ui_module() -> None:
    # Given: the installed Forge package
    # When: the Textual application boundary is resolved
    spec = find_spec("forge.ui.app")

    # Then: the UI is isolated from the agent and CLI modules
    assert spec is not None


def test_textual_app_exposes_forge_app() -> None:
    # Given: the dedicated UI module
    module = import_module("forge.ui.app")

    # When: its application entry point is resolved
    app_type = getattr(module, "ForgeApp", None)

    # Then: callers have a concrete Textual application to launch
    assert app_type is not None


@pytest.mark.asyncio
async def test_sidebar_is_fixed_to_full_terminal_height() -> None:
    # Given: a wide terminal running Forge
    app = ForgeApp(skip_startup=True)

    # When: the first frame is laid out
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        conversation = app.query_one("#conversation")
        sidebar = app.query_one("#sidebar")
        composer = app.query_one("#composer", TextArea)

        # Then: the rail is a narrow fixed column and the composer stays at the bottom
        assert sidebar.region.y == 0
        assert sidebar.region.height == 40
        assert sidebar.region.x > conversation.region.x
        assert sidebar.region.width <= 32
        assert composer.region.bottom == 40


@pytest.mark.asyncio
async def test_help_command_stays_inside_conversation() -> None:
    # Given: a mounted Forge composer
    app = ForgeApp(skip_startup=True)

    async with app.run_test(size=(100, 32)) as pilot:
        composer = app.query_one("#composer", TextArea)

        # When: the user submits a local command
        composer.text = "/help"
        await pilot.press("enter")
        await pilot.pause()

        # Then: input clears and command output is mounted in the conversation
        assert composer.text == ""
        assert "Commands" in app.query_one("#conversation", ConversationView).transcript


@pytest.mark.asyncio
async def test_theme_choice_accepts_arrows_and_enter() -> None:
    app = ForgeApp(skip_startup=True)

    async with app.run_test(size=(100, 32)) as pilot:
        composer = app.query_one("#composer", TextArea)
        composer.text = "/theme"
        await pilot.press("enter")
        await pilot.pause()

        assert isinstance(app.screen, ThemeSelectScreen)

        await pilot.press("down")
        assert app.screen.focused is not None
        assert app.screen.focused.id == "theme-cyber"
        await pilot.press("enter")
        await pilot.pause()

        assert not isinstance(app.screen, ThemeSelectScreen)
        assert app._current_theme == "cyber"
        assert str(app.screen.styles.background) == "Color(10, 10, 20)"


@pytest.mark.asyncio
async def test_multiline_paste_submits_one_complete_message() -> None:
    # Given: a focused Forge composer and a pasted multiline request
    app = ForgeApp(skip_startup=True)

    async with app.run_test(size=(100, 32)) as pilot:
        app.post_message(events.Paste("first line\nsecond line"))
        await pilot.pause()

        # When: the user sends the pasted request
        await pilot.press("enter")
        await pilot.pause()

        # Then: Forge records all pasted lines as one user message
        transcript = app.query_one("#conversation", ConversationView).transcript
        assert "YOU\nfirst line\nsecond line" in transcript


@pytest.mark.asyncio
async def test_shift_enter_inserts_composer_newline_without_submitting() -> None:
    # Given: a focused multiline composer with existing text
    app = ForgeApp(skip_startup=True)

    async with app.run_test(size=(100, 32)) as pilot:
        composer = app.query_one("#composer", TextArea)
        composer.text = "first line"
        composer.cursor_location = (0, len(composer.text))

        # When: the user presses Shift+Enter
        await pilot.press("shift+enter")
        await pilot.pause()

        # Then: the composer gains a newline without submitting a message
        assert composer.text == "first line\n"


@pytest.mark.asyncio
async def test_updates_command_starts_trusted_update_flow(monkeypatch) -> None:
    # Given: a mounted Forge composer and observable update coordinator
    app = ForgeApp(skip_startup=True)
    started: list[ForgeApp] = []
    monkeypatch.setattr(commands_module, "start_update", started.append)

    async with app.run_test(size=(100, 32)) as pilot:
        composer = app.query_one("#composer", TextArea)

        # When: the user explicitly requests an update check
        composer.text = "/updates"
        await pilot.press("enter")
        await pilot.pause()

        # Then: command routing enters the trusted update flow exactly once
        assert started == [app]


@pytest.mark.asyncio
async def test_current_update_check_reports_without_approval(monkeypatch) -> None:
    # Given: PyPI reports the version already running in Forge
    monkeypatch.setattr(updates_core, "fetch_latest_version", lambda: "0.2.1")
    app = ForgeApp(skip_startup=True)

    async with app.run_test(size=(100, 32)) as pilot:
        composer = app.query_one("#composer", TextArea)

        # When: the user runs the update check
        composer.text = "/updates"
        await pilot.press("enter")
        await pilot.pause()

        # Then: Forge reports current status without opening approval
        assert not isinstance(app.screen, ApprovalScreen)
        assert "already up to date" in app.query_one("#conversation", ConversationView).transcript


@pytest.mark.asyncio
async def test_release_source_url_is_configured() -> None:
    # Given: the official Forge release source and Pages fallback
    primary = updates_core.RELEASE_SOURCE_URL
    fallback = updates_core.RELEASE_SOURCE_FALLBACK

    # When: inspecting the update module constants
    # Then: both the raw source and Pages fallback are wired in
    assert "raw.githubusercontent.com/Chenboda01/Forge-AI" in primary
    assert "chenboda01.github.io/Forge-AI/releases.json" in fallback


@pytest.mark.asyncio
async def test_approved_update_installs_and_requests_restart(monkeypatch) -> None:
    installs: list[str] = []
    monkeypatch.setattr(updates_core, "fetch_latest_version", lambda: "5.0.1")
    monkeypatch.setattr(updates_core, "reinstall_version", installs.append)
    app = ForgeApp(skip_startup=True)

    async with app.run_test(size=(100, 32)) as pilot:
        composer = app.query_one("#composer", TextArea)

        composer.text = "/updates"
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, ApprovalScreen)
        assert shlex.join(updates_core.update_command("5.0.1")) in app.screen.arguments
        assert "releases.json" in app.screen.arguments
        await pilot.click("#approve")
        await pilot.pause()

        assert installs == ["5.0.1"]
        assert "Restart Forge" in app.query_one("#conversation", ConversationView).transcript


@pytest.mark.asyncio
async def test_narrow_terminal_prioritizes_conversation() -> None:
    # Given: a narrow terminal running Forge
    app = ForgeApp(skip_startup=True)

    # When: the shell lays out below the rail breakpoint
    async with app.run_test(size=(60, 24)) as pilot:
        await pilot.pause()
        sidebar = app.query_one("#sidebar")
        composer = app.query_one("#composer", TextArea)
        progress = app.query_one("#agent-progress", ProgressBar)

        # Then: the rail yields all width while the composer remains fixed
        assert sidebar.display is False
        assert progress.show_percentage is False
        assert composer.region.width == 60
        assert composer.region.bottom == 24


@pytest.mark.asyncio
async def test_agents_command_lists_restored_roles() -> None:
    # Given: a mounted Forge composer
    app = ForgeApp(skip_startup=True)

    async with app.run_test(size=(100, 32)) as pilot:
        composer = app.query_one("#composer", TextArea)

        # When: the user asks for available agents
        composer.text = "/agents"
        await pilot.press("enter")
        await pilot.pause()

        # Then: both restored read-only roles are visible
        transcript = app.query_one("#conversation", ConversationView).transcript
        assert "explore" in transcript
        assert "reviewer" in transcript


@pytest.mark.asyncio
async def test_progress_bar_reports_working_and_done() -> None:
    # Given: the fixed activity row
    app = ForgeApp(skip_startup=True)

    async with app.run_test(size=(100, 32)):
        progress = app.query_one("#agent-progress", ProgressBar)
        label = app.query_one("#activity-label", Static)

        # When: generation starts without a knowable duration
        app._set_busy(True)

        # Then: the bar animates indeterminately instead of claiming a fake percentage
        assert progress.total is None
        assert progress.percentage is None
        assert "Working" in label.render().plain

        # When: generation actually completes
        app._set_busy(False)

        # Then: completion becomes explicit only at the terminal state
        assert progress.total == 1
        assert progress.progress == 1
        assert "Done" in label.render().plain


@pytest.mark.asyncio
async def test_refresh_eft_updates_visible_activity_row() -> None:
    # Given: an active agent run with enough history to estimate remaining time
    app = ForgeApp(skip_startup=True)

    async with app.run_test(size=(100, 32)):
        app._set_busy(True)
        app._agent_started_at = monotonic() - 12
        app._agent_current_step = 3
        app._agent_max_steps = 15

        # When: Forge refreshes the EFT display
        app._refresh_eft()

        # Then: the visible activity row, composer, and sidebar advertise the estimate
        banner = app.query_one("#eft-banner", Static)
        label = app.query_one("#activity-label", Static)
        composer = app.query_one("#composer", TextArea)
        sidebar = app.query_one("#sidebar-content", Static)
        assert "EFT" in banner.render().plain
        assert "EFT" in label.render().plain
        assert "EFT" in str(composer.placeholder)
        assert "EFT" in sidebar.render().plain


@pytest.mark.asyncio
async def test_arrow_keys_navigate_input_history_and_restore_draft() -> None:
    # Given: two submitted terminal commands and a current draft
    app = ForgeApp(skip_startup=True)
    async with app.run_test(size=(100, 32)) as pilot:
        composer = app.query_one("#composer", TextArea)
        composer.text = "/help"
        await pilot.press("enter")
        composer.text = "/status"
        await pilot.press("enter")
        composer.text = "draft"

        # When / Then: Up walks older entries and Down returns through the draft
        await pilot.press("up")
        assert composer.text == "/status"
        await pilot.press("up")
        assert composer.text == "/help"
        await pilot.press("down")
        assert composer.text == "/status"
        await pilot.press("down")
        assert composer.text == "draft"


@pytest.mark.asyncio
async def test_double_escape_requests_interrupt(monkeypatch, tmp_path) -> None:
    # Given: a busy runtime with observable cancellation boundaries
    monkeypatch.setenv("FORGE_MODEL", "ollama")
    runtime = build_runtime(tmp_path)
    cancelled: list[str] = []
    monkeypatch.setattr(runtime.agent, "cancel", lambda: cancelled.append("agent"), raising=False)
    monkeypatch.setattr(
        runtime.subagents,
        "cancel",
        lambda: cancelled.append("subagent"),
        raising=False,
    )
    app = ForgeApp(runtime, skip_startup=True)

    async with app.run_test(size=(100, 32)) as pilot:
        app._set_busy(True)

        # When: Escape is pressed twice consecutively
        await pilot.press("escape", "escape")
        await pilot.pause()

        # Then: active runtimes receive a cooperative interrupt request
        assert cancelled == ["agent", "subagent"]
        assert "Interrupt requested" in app.query_one("#conversation", ConversationView).transcript


@pytest.mark.asyncio
async def test_five_escape_presses_exit() -> None:
    # Given: a running Forge application
    app = ForgeApp(skip_startup=True)
    async with app.run_test(size=(100, 32)) as pilot:
        assert app.is_running

        # When: Escape is pressed five times consecutively
        await pilot.press("escape", "escape", "escape", "escape", "escape")
        await pilot.pause()

        # Then: Forge exits like the /exit command
        assert not app.is_running


def test_unknown_model_cost_is_unavailable(monkeypatch, tmp_path) -> None:
    # Given: a configured model without verified pricing data
    monkeypatch.setenv("FORGE_MODEL", "ollama")
    runtime = build_runtime(tmp_path)

    # When: cost is calculated and rendered for the user
    cost = estimate_cost(runtime.agent)
    usage = CommandService(runtime).usage_text()

    # Then: Forge does not misrepresent unknown cost as zero
    assert cost is None
    assert "unavailable" in usage.lower()
    assert "$0.0000" not in usage


def test_approval_timeout_is_bounded(monkeypatch) -> None:
    # Given: an unanswered approval request and an observable event timeout
    class RecordingEvent:
        timeout: float | None = None

        def set(self) -> None:
            return None

        def wait(self, timeout: float | None = None) -> bool:
            RecordingEvent.timeout = timeout
            return False

    monkeypatch.setattr(app_module, "Event", RecordingEvent)
    app = ForgeApp(skip_startup=True)
    monkeypatch.setattr(app, "call_from_thread", lambda *_args: None)

    # When: Forge waits for the trusted interface
    app.request_approval("write_file", "{}")

    # Then: the pending request expires within one minute
    assert RecordingEvent.timeout is not None
    assert RecordingEvent.timeout <= 60
