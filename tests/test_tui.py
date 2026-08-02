import shlex
from importlib import import_module
from importlib.util import find_spec

import pytest
from textual.widgets import Input, ProgressBar, Static

import forge.forge_core.updates as updates_core
import forge.ui.app as app_module
import forge.ui.commands as commands_module
from forge.forge import build_runtime
from forge.ui.app import ForgeApp
from forge.ui.approval import ApprovalScreen
from forge.ui.commands import CommandService
from forge.ui.state import estimate_cost
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
    app = ForgeApp()

    # When: the first frame is laid out
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        conversation = app.query_one("#conversation")
        sidebar = app.query_one("#sidebar")
        composer = app.query_one("#composer", Input)

        # Then: the rail is a narrow fixed column and the composer stays at the bottom
        assert sidebar.region.y == 0
        assert sidebar.region.height == 40
        assert sidebar.region.x > conversation.region.x
        assert sidebar.region.width <= 32
        assert composer.region.bottom == 40


@pytest.mark.asyncio
async def test_help_command_stays_inside_conversation() -> None:
    # Given: a mounted Forge composer
    app = ForgeApp()

    async with app.run_test(size=(100, 32)) as pilot:
        composer = app.query_one("#composer", Input)

        # When: the user submits a local command
        composer.value = "/help"
        await pilot.press("enter")
        await pilot.pause()

        # Then: input clears and command output is mounted in the conversation
        assert composer.value == ""
        assert "Commands" in app.query_one("#conversation", ConversationView).transcript


@pytest.mark.asyncio
async def test_updates_command_starts_trusted_update_flow(monkeypatch) -> None:
    # Given: a mounted Forge composer and observable update coordinator
    app = ForgeApp()
    started: list[ForgeApp] = []
    monkeypatch.setattr(commands_module, "start_update", started.append)

    async with app.run_test(size=(100, 32)) as pilot:
        composer = app.query_one("#composer", Input)

        # When: the user explicitly requests an update check
        composer.value = "/updates"
        await pilot.press("enter")
        await pilot.pause()

        # Then: command routing enters the trusted update flow exactly once
        assert started == [app]


@pytest.mark.asyncio
async def test_current_update_check_reports_without_approval(monkeypatch) -> None:
    # Given: PyPI reports the version already running in Forge
    monkeypatch.setattr(updates_core, "fetch_latest_version", lambda: "0.2.1")
    app = ForgeApp()

    async with app.run_test(size=(100, 32)) as pilot:
        composer = app.query_one("#composer", Input)

        # When: the user runs the update check
        composer.value = "/updates"
        await pilot.press("enter")
        await pilot.pause()

        # Then: Forge reports current status without opening approval
        assert not isinstance(app.screen, ApprovalScreen)
        assert "already up to date" in app.query_one("#conversation", ConversationView).transcript


@pytest.mark.asyncio
async def test_unconfigured_update_source_fails_closed() -> None:
    # Given: Forge has no configured official release source
    app = ForgeApp()

    async with app.run_test(size=(100, 32)) as pilot:
        composer = app.query_one("#composer", Input)

        # When: the user requests an update check
        composer.value = "/updates"
        await pilot.press("enter")
        await pilot.pause()

        # Then: Forge reports the blocker without requesting installation approval
        assert not isinstance(app.screen, ApprovalScreen)
        assert (
            "no official release source"
            in app.query_one("#conversation", ConversationView).transcript
        )


@pytest.mark.asyncio
async def test_approved_update_installs_and_requests_restart(monkeypatch) -> None:
    # Given: PyPI reports a newer version and installation is safely recorded
    installs: list[str] = []
    monkeypatch.setattr(updates_core, "fetch_latest_version", lambda: "0.2.2")
    monkeypatch.setattr(updates_core, "reinstall_version", installs.append)
    app = ForgeApp()

    async with app.run_test(size=(100, 32)) as pilot:
        composer = app.query_one("#composer", Input)

        # When: the user checks, reviews the exact request, and approves once
        composer.value = "/updates"
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, ApprovalScreen)
        assert shlex.join(updates_core.update_command("0.2.2")) in app.screen.arguments
        await pilot.click("#approve")
        await pilot.pause()

        # Then: only that release is installed and Forge requires a restart
        assert installs == ["0.2.2"]
        assert "Restart Forge" in app.query_one("#conversation", ConversationView).transcript


@pytest.mark.asyncio
async def test_narrow_terminal_prioritizes_conversation() -> None:
    # Given: a narrow terminal running Forge
    app = ForgeApp()

    # When: the shell lays out below the rail breakpoint
    async with app.run_test(size=(60, 24)) as pilot:
        await pilot.pause()
        sidebar = app.query_one("#sidebar")
        composer = app.query_one("#composer", Input)
        progress = app.query_one("#agent-progress", ProgressBar)

        # Then: the rail yields all width while the composer remains fixed
        assert sidebar.display is False
        assert progress.show_percentage is False
        assert composer.region.width == 60
        assert composer.region.bottom == 24


@pytest.mark.asyncio
async def test_agents_command_lists_restored_roles() -> None:
    # Given: a mounted Forge composer
    app = ForgeApp()

    async with app.run_test(size=(100, 32)) as pilot:
        composer = app.query_one("#composer", Input)

        # When: the user asks for available agents
        composer.value = "/agents"
        await pilot.press("enter")
        await pilot.pause()

        # Then: both restored read-only roles are visible
        transcript = app.query_one("#conversation", ConversationView).transcript
        assert "explore" in transcript
        assert "reviewer" in transcript


@pytest.mark.asyncio
async def test_progress_bar_reports_working_and_done() -> None:
    # Given: the fixed activity row
    app = ForgeApp()

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
async def test_arrow_keys_navigate_input_history_and_restore_draft() -> None:
    # Given: two submitted terminal commands and a current draft
    app = ForgeApp()
    async with app.run_test(size=(100, 32)) as pilot:
        composer = app.query_one("#composer", Input)
        composer.value = "/help"
        await pilot.press("enter")
        composer.value = "/status"
        await pilot.press("enter")
        composer.value = "draft"

        # When / Then: Up walks older entries and Down returns through the draft
        await pilot.press("up")
        assert composer.value == "/status"
        await pilot.press("up")
        assert composer.value == "/help"
        await pilot.press("down")
        assert composer.value == "/status"
        await pilot.press("down")
        assert composer.value == "draft"


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
    app = ForgeApp(runtime)

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
    app = ForgeApp()
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
    app = ForgeApp()
    monkeypatch.setattr(app, "call_from_thread", lambda *_args: None)

    # When: Forge waits for the trusted interface
    app.request_approval("write_file", "{}")

    # Then: the pending request expires within one minute
    assert RecordingEvent.timeout is not None
    assert RecordingEvent.timeout <= 60
