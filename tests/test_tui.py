import asyncio
import shlex
from importlib import import_module
from importlib.util import find_spec
from threading import Event
from time import monotonic
from types import SimpleNamespace
from typing import cast

import pytest
from textual import events
from textual.widgets import OptionList, ProgressBar, Static, TextArea

import forge.forge_core.updates as updates_core
import forge.ui.app as app_module
import forge.ui.commands as commands_module
from forge.forge import build_runtime
from forge.forge_core.agent import ForgeAgent
from forge.ui.app import ForgeApp
from forge.ui.approval import ApprovalScreen
from forge.ui.commands import CommandService
from forge.ui.state import estimate_cost
from forge.ui.subagent_select import SubagentSelectScreen
from forge.ui.theme_select import ThemeSelectScreen
from forge.ui.widgets import STARTUP_PHASES, ConversationView, StartupBar


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
        header = app.query_one("#header")
        footer = app.query_one("#footer")

        # Then: the rail fills the body while chrome frames the fixed composer
        assert sidebar.region.y == header.region.bottom
        assert sidebar.region.bottom == footer.region.y
        assert sidebar.region.x > conversation.region.x
        assert sidebar.region.width <= 32
        assert composer.region.bottom == footer.region.y


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
async def test_theme_choice_accepts_arrows_and_enter(tmp_path) -> None:
    app = ForgeApp(skip_startup=True, preferences_path=tmp_path / "preferences.toml")

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
        assert app.active_theme == "cyber"
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
async def test_composer_queues_messages_while_agent_is_working(monkeypatch, tmp_path) -> None:
    # Given: an agent run that stays active until released
    monkeypatch.setenv("FORGE_MODEL", "ollama")
    runtime = build_runtime(tmp_path)
    calls: list[str] = []
    release = Event()

    def fake_run(message: str) -> None:
        calls.append(message)
        if message == "first":
            release.wait(timeout=5)

    monkeypatch.setattr(runtime.agent, "run", fake_run)
    app = ForgeApp(runtime, skip_startup=True)

    async with app.run_test(size=(100, 32)) as pilot:
        composer = app.query_one("#composer", TextArea)
        composer.text = "first"
        await pilot.press("enter")
        await pilot.pause()

        # When: the user types and submits a second message mid-run
        assert app._busy
        assert not composer.disabled
        composer.text = "second"
        await pilot.press("enter")
        await pilot.pause()

        # Then: the message is queued, visible, and counted
        assert list(app._queued_messages) == ["second"]
        transcript = app.query_one("#conversation", ConversationView).transcript
        assert "QUEUED\nsecond" in transcript
        sidebar = str(app.query_one("#sidebar-content", Static).content)
        assert "Queue\n1 pending" in sidebar
        footer = app.query_one("#footer-right", Static).render().plain
        assert "1 queued" in footer

        # When: the active run finishes
        release.set()
        for _ in range(50):
            await pilot.pause()
            if calls == ["first", "second"]:
                break

        # Then: the queue drains automatically and stays empty
        assert calls == ["first", "second"]
        assert not app._queued_messages


@pytest.mark.asyncio
async def test_queue_command_lists_and_clears_pending_messages() -> None:
    # Given: a busy Forge with one queued message
    app = ForgeApp(skip_startup=True)

    async with app.run_test(size=(100, 32)) as pilot:
        app._set_busy(True)
        composer = app.query_one("#composer", TextArea)
        composer.text = "queued task"
        await pilot.press("enter")
        await pilot.pause()

        # When: the user inspects the queue
        composer.text = "/queue"
        await pilot.press("enter")
        await pilot.pause()

        # Then: pending work is visible while the agent keeps running
        transcript = app.query_one("#conversation", ConversationView).transcript
        assert "1 pending" in transcript
        assert "1. queued task" in transcript
        assert app._busy

        # When: the user clears the queue
        composer.text = "/queue clear"
        await pilot.press("enter")
        await pilot.pause()

        # Then: queued work is discarded without stopping the active run
        assert not app._queued_messages
        assert (
            "Cleared 1 queued message(s)."
            in app.query_one("#conversation", ConversationView).transcript
        )
        app._set_busy(False)


@pytest.mark.asyncio
async def test_read_only_commands_bypass_the_queue_while_busy() -> None:
    # Given: a busy Forge with an empty queue
    app = ForgeApp(skip_startup=True)

    async with app.run_test(size=(100, 32)) as pilot:
        app._set_busy(True)

        # When: the user asks for help without waiting
        composer = app.query_one("#composer", TextArea)
        composer.text = "/help"
        await pilot.press("enter")
        await pilot.pause()

        # Then: the read-only command runs immediately instead of queueing
        transcript = app.query_one("#conversation", ConversationView).transcript
        assert "Commands" in transcript
        assert not app._queued_messages
        app._set_busy(False)


@pytest.mark.asyncio
async def test_state_changing_command_is_queued_while_busy() -> None:
    # Given: a busy Forge
    app = ForgeApp(skip_startup=True)

    async with app.run_test(size=(100, 32)) as pilot:
        app._set_busy(True)

        # When: the user submits a command that mutates runtime state
        composer = app.query_one("#composer", TextArea)
        composer.text = "/save"
        await pilot.press("enter")
        await pilot.pause()

        # Then: it waits for the active run instead of executing mid-step
        assert list(app._queued_messages) == ["/save"]
        app.clear_queue()
        app._set_busy(False)


@pytest.mark.asyncio
async def test_conversation_preserves_scroll_when_reader_is_not_at_bottom() -> None:
    # Given: a conversation scrolled above the tail
    app = ForgeApp(skip_startup=True)

    async with app.run_test(size=(100, 20)) as pilot:
        conversation = app.query_one("#conversation", ConversationView)
        for index in range(30):
            await conversation.append_entry("FORGE", f"line {index}", "forge")
        await pilot.pause()
        conversation.scroll_home(animate=False)
        await pilot.pause()
        assert not conversation.is_vertical_scroll_end
        before = conversation.scroll_offset.y

        # When: new output arrives while the user is reading
        await conversation.append_entry("FORGE", "reading stays put", "forge")
        await pilot.pause()

        # Then: the viewport does not jump to the bottom
        assert conversation.scroll_offset.y == before

        # When: the user is at the tail instead
        conversation.scroll_end(animate=False)
        await pilot.pause()
        await conversation.append_entry("FORGE", "follow the tail", "forge")
        await pilot.pause()

        # Then: new output keeps following the tail
        assert conversation.is_vertical_scroll_end


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
        footer = app.query_one("#footer")

        # Then: the rail yields all width while the composer remains fixed
        assert sidebar.display is False
        assert progress.show_percentage is False
        assert composer.region.width == 60
        assert composer.region.bottom == footer.region.y


@pytest.mark.asyncio
async def test_connected_runtime_renders_status_chrome(monkeypatch, tmp_path) -> None:
    # Given: a connected local runtime
    monkeypatch.setenv("FORGE_MODEL", "ollama")
    runtime = build_runtime(tmp_path)
    app = ForgeApp(runtime, skip_startup=True)

    # When: the status chrome is mounted
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        header = app.query_one("#header-right", Static).render().plain
        left = app.query_one("#header-left", Static).render().plain
        footer = app.query_one("#footer-left", Static).render().plain

        # Then: the active mode/model, saved theme, and primary keyboard hint are visible
        assert runtime.agent.mode.value in header
        assert runtime.agent.model_id.rsplit("/", maxsplit=1)[-1] in header
        assert app.active_theme in header
        assert "\u25c6 FORGE " in left
        assert "enter send" in footer
        sidebar = str(app.query_one("#sidebar-content", Static).content)
        assert "Agents\n2 ready" in sidebar


@pytest.mark.asyncio
async def test_agents_command_opens_browser_with_details(tmp_path) -> None:
    # Given: a mounted Forge composer
    app = ForgeApp(skip_startup=True, preferences_path=tmp_path / "preferences.toml")

    async with app.run_test(size=(100, 32)) as pilot:
        composer = app.query_one("#composer", TextArea)

        # When: the user opens the subagent browser
        composer.text = "/agents"
        await pilot.press("enter")
        await pilot.pause()

        # Then: both restored read-only roles and the active role's tools are visible
        assert isinstance(app.screen, SubagentSelectScreen)
        options = app.screen.query_one("#agents-options", OptionList)
        assert options.option_count == 2
        assert options.get_option_at_index(0).id == "explore"
        assert options.get_option_at_index(1).id == "reviewer"
        detail = str(app.screen.query_one("#agents-detail", Static).content)
        assert "EXPLORE" in detail
        assert "read_file" in detail
        assert "Step limit" in detail

        # When: the user selects the highlighted role
        await pilot.press("enter")
        await pilot.pause()

        # Then: the composer is prepared for an explicit delegation
        assert not isinstance(app.screen, SubagentSelectScreen)
        assert composer.text == "/agent explore "
        assert "Subagent explore" in app.query_one("#conversation", ConversationView).transcript


@pytest.mark.asyncio
async def test_agents_command_shows_named_role_details(tmp_path) -> None:
    # Given: a mounted Forge composer
    app = ForgeApp(skip_startup=True, preferences_path=tmp_path / "preferences.toml")

    async with app.run_test(size=(100, 32)) as pilot:
        composer = app.query_one("#composer", TextArea)

        # When: the user requests one named subagent without opening the browser
        composer.text = "/agents reviewer"
        await pilot.press("enter")
        await pilot.pause()

        # Then: the trusted UI shows tools, limits, and invocation forms
        transcript = app.query_one("#conversation", ConversationView).transcript
        assert "Subagent reviewer" in transcript
        assert "git_diff" in transcript
        assert "Step limit" in transcript
        assert "/agent reviewer OBJECTIVE" in transcript


@pytest.mark.asyncio
async def test_settings_command_reports_user_preferences(tmp_path) -> None:
    # Given: a user with an explicit preferences location
    preferences_path = tmp_path / "preferences.toml"
    app = ForgeApp(skip_startup=True, preferences_path=preferences_path)

    async with app.run_test(size=(100, 32)) as pilot:
        composer = app.query_one("#composer", TextArea)

        # When: the user inspects settings
        composer.text = "/settings"
        await pilot.press("enter")
        await pilot.pause()

        # Then: the storage location, theme, and user scope are explicit
        transcript = app.query_one("#conversation", ConversationView).transcript
        assert "Settings" in transcript
        assert str(preferences_path) in transcript
        assert "Theme: ember" in transcript
        assert "per operating-system user" in transcript


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


def _cost_agent(model_id: str, *, local: bool = False) -> ForgeAgent:
    return cast(
        ForgeAgent,
        SimpleNamespace(
            model_id=model_id,
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            provider=SimpleNamespace(capabilities=SimpleNamespace(local=local)),
        ),
    )


def test_local_model_cost_is_zero(monkeypatch, tmp_path) -> None:
    # Given: a local model with no API billing
    monkeypatch.setenv("FORGE_MODEL", "ollama")
    runtime = build_runtime(tmp_path)

    # When: cost is calculated and rendered for the user
    cost = estimate_cost(runtime.agent)
    usage = CommandService(runtime).usage_text()

    # Then: Forge reports a real zero instead of an unavailable price
    assert cost == 0.0
    assert "$0.0000" in usage
    assert "unavailable" not in usage.lower()


@pytest.mark.asyncio
async def test_sidebar_shows_local_cost_as_zero(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FORGE_MODEL", "ollama")
    runtime = build_runtime(tmp_path)
    app = ForgeApp(runtime, skip_startup=True)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        content = str(app.query_one("#sidebar-content", Static).content)

        assert "Cost\n$0.0000" in content
        assert "Unavailable" not in content


def test_mapped_cloud_model_cost_is_estimated() -> None:
    # Given: a cloud model with a published per-token price
    agent = _cost_agent("deepseek/deepseek-flash")

    # When: one million input and output tokens are priced
    cost = estimate_cost(agent)

    # Then: Forge returns a positive estimate
    assert cost is not None
    assert cost > 0


def test_unmapped_model_cost_is_unavailable() -> None:
    # Given: a cloud model without a published price table entry
    agent = _cost_agent("custom/unmapped-model")

    # When: cost is calculated for the user
    cost = estimate_cost(agent)

    # Then: Forge does not misrepresent unknown cost as zero
    assert cost is None


@pytest.mark.asyncio
async def test_startup_holds_logo_before_showing_loading_bar(monkeypatch) -> None:
    # Given: a controllable startup clock
    sleeps: list[float] = []
    release_logo = asyncio.Event()

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) == 1:
            await release_logo.wait()
        else:
            await asyncio.sleep(0)

    monkeypatch.setattr(app_module, "_startup_sleep", fake_sleep)
    app = ForgeApp()

    # When: the application mounts while the logo hold is still in progress
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        bar = app.query_one(StartupBar)

        # Then: only the logo and tagline are visible
        assert bar.display
        assert app.query_one("#startup-emblem").display
        assert app.query_one("#startup-logo").display
        assert app.query_one("#startup-tagline").display
        assert not app.query_one("#startup-phase").display
        assert not app.query_one("#startup-progress").display
        assert sleeps == [app_module.LOGO_HOLD_SECONDS]

        # When: the logo hold completes
        release_logo.set()
        for _ in range(10):
            await pilot.pause()

        # Then: the loading bar ran after the hold and the shell replaced the splash
        assert not bar.display
        assert app.query_one("#shell").display
        assert sleeps[0] == app_module.LOGO_HOLD_SECONDS
        assert sleeps[1:] == [app_module.STARTUP_PHASE_SECONDS] * len(STARTUP_PHASES)


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
    app.request_approval("apply_patch", "{}")

    # Then: the pending request expires within one minute
    assert RecordingEvent.timeout is not None
    assert RecordingEvent.timeout <= 60
