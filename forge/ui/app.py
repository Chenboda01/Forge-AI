import asyncio
import contextlib
from collections import deque
from pathlib import Path
from threading import Event
from time import monotonic

from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.timer import Timer
from textual.widgets import Button, Input, OptionList, TextArea

from forge.forge_core.agent import AgentError, AgentInterruptedError
from forge.forge_core.preferences import (
    PreferencesError,
    UiPreferences,
    get_user_preferences_path,
    load_preferences,
    save_preferences,
)
from forge.forge_core.subagents import SUBAGENTS, SubagentError, SubagentInterruptedError
from forge.ui.approval import ApprovalScreen
from forge.ui.clipboard import copy_to_clipboard as copy_system_clipboard
from forge.ui.command_palette import COMMANDS, CommandSuggest
from forge.ui.commands import CommandService, handle_command
from forge.ui.force_stop import (
    CHOICE_KEEP,
    ForceStopScreen,
    checkpoint_baseline,
    revert_force_stop,
    turn_checkpoint_ids,
)
from forge.ui.keyboard import KeyboardController, request_interrupt
from forge.ui.state import ForgeRuntime
from forge.ui.subagent_select import SubagentSelectScreen
from forge.ui.subagent_session import SubagentSession
from forge.ui.themes import DEFAULT_THEME, THEMES
from forge.ui.widgets import (
    STARTUP_PHASES,
    ActivityProgress,
    ConversationView,
    EftBanner,
    FooterBar,
    HeaderBar,
    StartupBar,
    StatusRail,
)

APPROVAL_TIMEOUT_SECONDS = 60
EMA_ALPHA = 0.3
FORCE_STOP_TIMEOUT_SECONDS = 15.0
LOGO_HOLD_SECONDS = 1.2
STARTUP_PHASE_SECONDS = 0.35
MAX_QUEUED_MESSAGES = 20

IMMEDIATE_COMMANDS = frozenset(
    {
        "/agents",
        "/checkpoint",
        "/checkpoints",
        "/exit",
        "/force-stop",
        "/help",
        "/history",
        "/queue",
        "/sessions",
        "/settings",
        "/status",
        "/usage",
    }
)


async def _startup_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


class ForgeApp(App[None]):
    """Full-screen terminal interface for the Forge runtime."""

    CSS_PATH = "app.tcss"
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+x", "open_agents", show=False, priority=True),
        Binding("shift+enter", "insert_composer_newline", priority=True, show=False),
        Binding("enter", "submit_composer", priority=True, show=False),
    ]

    def __init__(
        self,
        runtime: ForgeRuntime | None = None,
        *,
        skip_startup: bool = False,
        preferences_path: Path | None = None,
    ) -> None:
        super().__init__()
        self.runtime = runtime
        self.commands = CommandService(runtime)
        self.keyboard = KeyboardController()
        self.session_name = ""
        self._skip_startup = skip_startup
        self._preferences_path = preferences_path or get_user_preferences_path()
        self._preferences_error = ""
        initial_theme = DEFAULT_THEME
        try:
            preferences = load_preferences(self._preferences_path)
        except (PreferencesError, OSError) as error:
            self._preferences_error = str(error)
        else:
            saved_theme = preferences.theme
            if saved_theme is not None:
                if saved_theme in THEMES:
                    initial_theme = saved_theme
                else:
                    self._preferences_error = (
                        f"Unknown saved theme '{saved_theme}'; using {DEFAULT_THEME}."
                    )
        self._current_theme = initial_theme
        for theme in THEMES.values():
            self.register_theme(theme)
        self.theme = initial_theme
        self._approval_decision: Event | None = None
        self._busy = False
        self._turn_checkpoint_baseline: frozenset[str] | None = None
        self._active_subagent: str | None = None
        self._queued_messages: deque[str] = deque()
        self._agent_started_at: float | None = None
        self._agent_max_steps: int = 0
        self._agent_current_step: int = 0
        self._eft_text = ""
        self._eft_timer = None
        self._last_step_time: float | None = None
        self._ema_step_duration: float = 0.0
        self._selection_text = ""
        self._selection_timer: Timer | None = None
        self.subagent_session = SubagentSession()
        if runtime is not None:
            runtime.agent.presenter = self
            runtime.subagents.activity = self

    async def action_open_agents(self) -> None:
        if len(self.screen_stack) != 1:
            return
        await self.open_subagent_browser()

    async def open_subagent_browser(self) -> None:
        def selected(request: tuple[str, str] | None) -> None:
            composer = self.query_one("#composer", TextArea)
            if request is None:
                if len(self.screen_stack) == 1:
                    composer.focus()
                return
            agent_name, prompt = request
            asyncio.create_task(self._start_subagent(f"{agent_name} {prompt}"))

        await self.push_screen(
            SubagentSelectScreen(self.subagent_session),
            callback=selected,
        )

    async def force_stop(self) -> None:
        """Cancel the active run, wait for its edit to settle, then ask what to revert."""
        if not self._busy:
            await self._append_entry("SYSTEM", "Force stop\nForge is not working.", "notice")
            return
        composer = self.query_one("#composer", TextArea)
        composer.disabled = True
        cleared = len(self._queued_messages)
        self._queued_messages.clear()
        self._refresh_sidebar()
        note = "Force stop requested. Waiting for the current edit to finish safely..."
        if cleared:
            note += f" Discarded {cleared} queued message(s)."
        await request_interrupt(self, note=note)
        if not await self._wait_for_agent_idle(FORCE_STOP_TIMEOUT_SECONDS):
            composer.disabled = False
            await self._append_entry(
                "SYSTEM",
                "Force stop: Forge is still stopping; nothing was reverted. Try /force-stop again.",
                "error",
            )
            return
        checkpoint_ids = (
            turn_checkpoint_ids(self.runtime, self._turn_checkpoint_baseline)
            if self.runtime is not None and self._turn_checkpoint_baseline is not None
            else None
        )

        def selected(choice: str | None) -> None:
            self._force_stop_selected(choice, checkpoint_ids)

        await self.push_screen(ForceStopScreen(), callback=selected)

    def _force_stop_selected(
        self,
        choice: str | None,
        checkpoint_ids: tuple[str, ...] | None,
    ) -> None:
        self.keyboard.reset_escape()
        asyncio.create_task(self._finish_force_stop(choice, checkpoint_ids))

    async def _finish_force_stop(
        self,
        choice: str | None,
        checkpoint_ids: tuple[str, ...] | None,
    ) -> None:
        composer = self.query_one("#composer", TextArea)
        try:
            if choice is None:
                await self._append_entry("SYSTEM", "Force stop cancelled. Changes kept.", "notice")
                return
            if choice == CHOICE_KEEP:
                await self._append_entry(
                    "SYSTEM", "Force stop: Forge stopped; changes kept.", "notice"
                )
                return
            result = revert_force_stop(self.runtime, checkpoint_ids, choice)
            await self._append_entry("SYSTEM", result, "notice")
        finally:
            composer.disabled = False
            if len(self.screen_stack) == 1:
                composer.focus()
            self._refresh_sidebar()

    async def _wait_for_agent_idle(self, timeout: float) -> bool:
        deadline = monotonic() + timeout
        while self._busy and monotonic() < deadline:
            await asyncio.sleep(0.05)
        return not self._busy

    def compose(self) -> ComposeResult:
        with Vertical(id="shell"):
            yield HeaderBar()
            with Horizontal(id="body"):
                with Vertical(id="main"):
                    yield EftBanner()
                    yield ConversationView()
                    yield ActivityProgress()
                    yield CommandSuggest()
                    yield TextArea(
                        "",
                        placeholder="Ask Forge or enter /help",
                        id="composer",
                        show_line_numbers=False,
                    )
                yield StatusRail(id="sidebar")
            yield FooterBar()
        yield StartupBar()

    async def on_mount(self) -> None:
        self._eft_timer = self.set_interval(1.0, self._refresh_eft, pause=True)
        self.set_interval(0.2, self._poll_selection)
        self._refresh_sidebar()
        self.query_one("#composer", TextArea).focus()
        if self._skip_startup:
            self.query_one(StartupBar).display = False
            await self._append_entry(
                "FORGE",
                "Shape code. Temper bugs. Ship stronger software.\nEnter /help for commands.",
                "forge",
            )
            await self._report_preferences_error()
        else:
            shell = self.query_one("#shell", Vertical)
            shell.display = False
            asyncio.create_task(self._boot_sequence())

    @property
    def preferences_path(self) -> Path:
        return self._preferences_path

    def _poll_selection(self) -> None:
        text = self.screen.get_selected_text() or ""
        if text == self._selection_text:
            return
        self._selection_text = text
        if self._selection_timer is not None:
            self._selection_timer.stop()
            self._selection_timer = None
        if text:
            self._selection_timer = self.set_timer(0.25, lambda: self._copy_selection(text))

    def _copy_selection(self, text: str) -> None:
        if text != self._selection_text:
            return
        if copy_system_clipboard(text):
            self.notify("Copied to clipboard successful [green]✓[/green]", timeout=2)
        else:
            self.notify(
                "Copied to clipboard unsuccessful [red]✗[/red]",
                severity="error",
                timeout=3,
            )

    @property
    def active_theme(self) -> str:
        return self._current_theme

    def apply_theme(self, name: str, *, persist: bool = True) -> str | None:
        """Apply a theme and persist it for this operating-system user."""
        if name not in THEMES:
            return None
        self._current_theme = name
        self.theme = name
        if self.is_running:
            self._refresh_sidebar()
        if not persist:
            return None
        try:
            save_preferences(UiPreferences(theme=name), self._preferences_path)
        except (PreferencesError, OSError) as error:
            return str(error)
        return None

    async def _report_preferences_error(self) -> None:
        if self._preferences_error:
            await self._append_entry("SYSTEM", f"Preferences: {self._preferences_error}", "error")

    async def _boot_sequence(self) -> None:
        bar = self.query_one(StartupBar)
        await _startup_sleep(LOGO_HOLD_SECONDS)
        bar.set_loading_visible(True)
        for i, phase in enumerate(STARTUP_PHASES, start=1):
            bar.set_phase(i, phase)
            await _startup_sleep(STARTUP_PHASE_SECONDS)
        bar.display = False
        shell = self.query_one("#shell", Vertical)
        shell.display = True
        await self._append_entry(
            "FORGE",
            "Shape code. Temper bugs. Ship stronger software.\nEnter /help for commands.",
            "forge",
        )
        await self._report_preferences_error()

    def on_resize(self, event: events.Resize) -> None:
        is_wide = event.size.width >= 72
        with contextlib.suppress(Exception):
            self.query_one("#sidebar", StatusRail).display = is_wide
            self.query_one("#header-right").display = is_wide
            self.query_one("#footer-right").display = is_wide

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id != "composer":
            return
        suggest = self.query_one(CommandSuggest)
        text = event.text_area.text
        if not text.startswith("/") or text.strip() in {spec.name for spec in COMMANDS}:
            suggest.display = False
            return
        suggest.update_query(text)

    def _insert_suggestion(self, *, force: bool = False) -> bool:
        suggest = self.query_one(CommandSuggest)
        if not suggest.display:
            return False
        composer = self.query_one("#composer", TextArea)
        if not force and composer.text.strip() in {spec.name for spec in COMMANDS}:
            return False
        command = suggest.selected_command()
        if command is None:
            return False
        suggest.display = False
        composer.load_text(f"{command} ")
        composer.focus()
        composer.cursor_location = (0, len(composer.text))
        return True

    async def on_key(self, event: events.Key) -> None:
        suggest = self.query_one(CommandSuggest)
        if event.key in {"up", "down"} and suggest.display:
            event.prevent_default()
            event.stop()
            if event.key == "up":
                suggest.action_cursor_up()
            else:
                suggest.action_cursor_down()
            return
        if event.key == "tab" and self._insert_suggestion(force=True):
            event.prevent_default()
            event.stop()
            return
        if event.key == "escape":
            if suggest.display:
                suggest.display = False
                event.prevent_default()
                event.stop()
                return
            event.prevent_default()
            event.stop()
            presses = self.keyboard.record_escape()
            if presses >= 5:
                self.exit()
            elif presses == 2:
                await request_interrupt(self)
            return

        self.keyboard.reset_escape()
        if event.key not in {"up", "down"}:
            return
        composer = self.query_one("#composer", TextArea)
        if len(self.screen_stack) != 1 or self.focused is not composer or composer.disabled:
            return
        value = self.keyboard.previous(composer.text) if event.key == "up" else self.keyboard.next()
        if value is None:
            return
        event.prevent_default()
        event.stop()
        composer.load_text(value)
        composer.cursor_location = (value.count("\n"), len(value.rsplit("\n", maxsplit=1)[-1]))

    async def action_submit_composer(self) -> None:
        if self._insert_suggestion():
            return
        focused = self.screen.focused
        if isinstance(focused, Button):
            focused.press()
            return
        if isinstance(focused, Input):
            await focused.action_submit()
            return
        if isinstance(focused, OptionList):
            focused.action_select()
            return
        composer = self.query_one("#composer", TextArea)
        if not composer.has_focus or composer.disabled:
            return
        message = composer.text.strip()
        composer.clear()
        if not message:
            return

        if self._busy and not self._is_immediate(message):
            if not await self._enqueue_message(message):
                composer.load_text(message)
                return
            self.keyboard.remember(message)
            return
        self.keyboard.remember(message)
        await self._submit_message(message)

    @staticmethod
    def _is_immediate(message: str) -> bool:
        if not message.startswith("/"):
            return False
        return message.split(maxsplit=1)[0].lower() in IMMEDIATE_COMMANDS

    async def _submit_message(self, message: str, *, echo: bool = True) -> None:
        if message.startswith("/"):
            await handle_command(self, message)
            return
        if echo:
            await self._append_entry("YOU", message, "user")
        if message.startswith("@"):
            await self._start_subagent(message[1:])
            return
        if self.runtime is None:
            await self._append_entry("FORGE", "No model runtime is connected.", "error")
            return

        if not self.session_name:
            self.session_name = self.runtime.sessions._auto_name(
                [{"role": "user", "content": message}]
            )
            self._refresh_sidebar()
        self._set_busy(True)
        self.run_agent(message)

    async def _enqueue_message(self, message: str) -> bool:
        if len(self._queued_messages) >= MAX_QUEUED_MESSAGES:
            await self._append_entry(
                "SYSTEM",
                f"Queue is full ({MAX_QUEUED_MESSAGES} messages). Wait for Forge to finish.",
                "error",
            )
            return False
        self._queued_messages.append(message)
        await self._append_entry("QUEUED", message, "queued")
        self._refresh_sidebar()
        return True

    def queue_text(self) -> str:
        if not self._queued_messages:
            return (
                "Queue\nNo queued messages.\nPress Enter while Forge is working to queue a message."
            )
        lines = ["Queue", f"{len(self._queued_messages)} pending"]
        for position, message in enumerate(self._queued_messages, start=1):
            preview = " ".join(message.split())
            if len(preview) > 100:
                preview = preview[:97] + "..."
            lines.append(f"{position}. {preview}")
        lines.append("Run /queue clear to remove all queued messages.")
        return "\n".join(lines)

    def clear_queue(self) -> str:
        count = len(self._queued_messages)
        self._queued_messages.clear()
        self._refresh_sidebar()
        if count == 0:
            return "Queue\nNo queued messages."
        return f"Queue\nCleared {count} queued message(s)."

    def _schedule_queue_drain(self) -> None:
        if self._queued_messages and not self._busy:
            self.set_timer(0.01, self._drain_next_queued)

    def _drain_next_queued(self) -> None:
        if self._busy or not self._queued_messages or not self.is_running:
            return
        if not self.query("#sidebar"):
            return
        message = self._queued_messages.popleft()
        self._refresh_sidebar()
        asyncio.create_task(self._run_queued(message))

    async def _run_queued(self, message: str) -> None:
        await self._submit_message(message, echo=False)
        if not self._busy:
            self._schedule_queue_drain()

    def action_insert_composer_newline(self) -> None:
        composer = self.query_one("#composer", TextArea)
        if composer.has_focus and not composer.disabled:
            composer.insert("\n")

    async def _show_command_result(self, output: str) -> None:
        await self._append_entry("SYSTEM", output, "notice")
        self._refresh_sidebar()

    async def _start_subagent(self, request: str) -> None:
        parts = request.split(maxsplit=1)
        if len(parts) != 2 or not parts[1].strip():
            await self._show_command_result("Usage: /agent NAME OBJECTIVE or @NAME OBJECTIVE")
            return
        agent_name, objective = parts[0].lower(), parts[1].strip()
        if agent_name not in SUBAGENTS:
            available = ", ".join(sorted(SUBAGENTS))
            await self._show_command_result(
                f"Unknown agent: {agent_name}. Available agents: {available}"
            )
            return
        if self.runtime is None:
            await self._show_command_result("No model runtime is connected.")
            return
        await self._append_entry(
            "FORGE",
            f"Delegating to {agent_name}: {objective}",
            "notice",
        )
        self._active_subagent = agent_name
        self.subagent_session.begin(agent_name, objective)
        self._set_busy(True, label=f"{agent_name} working")
        self.run_subagent(agent_name, objective)

    @work(thread=True, exclusive=True, group="agent")
    def run_agent(self, message: str) -> None:
        runtime = self.runtime
        if runtime is None:
            return
        try:
            runtime.agent.run(message)
        except AgentInterruptedError:
            self.call_from_thread(self._append_entry, "SYSTEM", "Interrupted.", "notice")
        except AgentError as error:
            self.call_from_thread(self._append_entry, "FORGE ERROR", str(error), "error")
        finally:
            self.call_from_thread(self._set_busy, False)
            self.call_from_thread(self._refresh_sidebar)

    @work(thread=True, exclusive=True, group="agent")
    def run_subagent(self, agent_name: str, objective: str) -> None:
        runtime = self.runtime
        if runtime is None:
            return
        try:
            report = runtime.subagents.run(agent_name=agent_name, objective=objective)
        except SubagentInterruptedError:
            self.call_from_thread(self._append_entry, "SYSTEM", "Interrupted.", "notice")
            self.call_from_thread(self.subagent_session.cancel, agent_name)
        except SubagentError as error:
            self.call_from_thread(self._append_entry, "SUBAGENT ERROR", str(error), "error")
            self.call_from_thread(self.subagent_session.fail, agent_name, str(error))
        else:
            self.call_from_thread(
                self._append_entry,
                f"SUBAGENT {agent_name.upper()}",
                report,
                "forge",
            )
            self.call_from_thread(self.subagent_session.complete, agent_name, report)
        finally:
            self.call_from_thread(self._complete_subagent)

    def _complete_subagent(self) -> None:
        self._active_subagent = None
        self._set_busy(False)

    def subagent_tool_started(self, agent_name: str, tool_name: str, arguments: str) -> None:
        self.call_from_thread(self.subagent_session.record_tool, agent_name, tool_name)
        self.call_from_thread(
            self.query_one("#activity-row", ActivityProgress).set_phase,
            f"{agent_name} · {tool_name}",
        )
        self.call_from_thread(
            self._append_entry,
            f"{agent_name.upper()} TOOL {tool_name}",
            arguments[:2_000],
            "tool",
        )

    def subagent_tool_completed(self, agent_name: str, tool_name: str, result: str) -> None:
        self.call_from_thread(
            self.query_one("#activity-row", ActivityProgress).set_phase,
            f"{agent_name} working",
        )
        self.call_from_thread(
            self._append_entry,
            f"{agent_name.upper()} TOOL {tool_name} COMPLETE",
            result[:4_000],
            "tool",
        )

    @work(thread=True, exclusive=True, group="agent")
    def compact_conversation(self) -> None:
        runtime = self.runtime
        if runtime is None:
            return
        try:
            result = runtime.agent.compact()
        except AgentInterruptedError:
            self.call_from_thread(self._append_entry, "SYSTEM", "Interrupted.", "notice")
        else:
            self.call_from_thread(self._append_entry, "SYSTEM", result, "notice")
        self.call_from_thread(self._set_busy, False)
        self.call_from_thread(self._refresh_sidebar)

    def step_started(self, step: int, maximum: int) -> None:
        now = monotonic()
        if self._agent_started_at is None:
            self._agent_started_at = now
        if self._last_step_time is not None:
            step_duration = now - self._last_step_time
            if self._ema_step_duration <= 0:
                self._ema_step_duration = step_duration
            else:
                self._ema_step_duration = (
                    EMA_ALPHA * step_duration + (1 - EMA_ALPHA) * self._ema_step_duration
                )
        self._last_step_time = now
        self._agent_current_step = step
        self._agent_max_steps = maximum
        try:
            self.call_from_thread(self._refresh_eft)
        except RuntimeError:
            self._refresh_eft()

    def _show_eft(self, text: str) -> None:
        self.query_one("#composer", TextArea).placeholder = f"{text} · Enter queues"

    def _refresh_eft(self) -> None:
        if not self._busy or self._agent_started_at is None:
            self._eft_text = ""
            self.query_one("#eft-banner", EftBanner).set_text("Waiting")
            return
        step = self._agent_current_step
        maximum = self._agent_max_steps
        if step > 1:
            if self._ema_step_duration > 0:
                remaining_steps = maximum - step + 1
                remaining = self._ema_step_duration * remaining_steps
            else:
                elapsed = monotonic() - self._agent_started_at
                remaining = (elapsed / (step - 1)) * (maximum - step + 1) if elapsed > 0.5 else 0
            if remaining > 0:
                remaining = min(remaining, 600)
                text = f"Thinking · step {step}/{maximum} · EFT {remaining:.0f}s"
            else:
                text = f"Thinking · step {step}/{maximum} · EFT --"
        else:
            text = f"Thinking · step {step}/{maximum} · EFT --"
        self._eft_text = text
        self._show_phase(text)
        self._show_eft(text)
        self.query_one("#eft-banner", EftBanner).set_text(text)
        self._refresh_sidebar()

    def _show_phase(self, label: str) -> None:
        self.query_one("#activity-row", ActivityProgress).set_phase(label)

    def tool_started(self, name: str, arguments: str) -> None:
        self.call_from_thread(
            self.query_one("#activity-row", ActivityProgress).set_phase,
            f"Running {name}",
        )
        self.call_from_thread(self._append_entry, f"TOOL {name}", arguments, "tool")

    def request_approval(self, name: str, arguments: str) -> bool:
        decision = Event()
        self._approval_decision = decision
        approved = False

        def record(result: bool | None) -> None:
            nonlocal approved
            approved = result is True
            decision.set()

        self.call_from_thread(self.push_screen, ApprovalScreen(name, arguments), record)
        try:
            decision.wait(timeout=APPROVAL_TIMEOUT_SECONDS)
            return approved
        finally:
            self._approval_decision = None

    def tool_completed(self, name: str, result: str) -> None:
        self.call_from_thread(
            self.query_one("#activity-row", ActivityProgress).set_phase,
            "Thinking",
        )
        self.call_from_thread(
            self._append_entry,
            f"TOOL {name} COMPLETE",
            result[:4_000],
            "tool",
        )

    def context_reduced(self, tokens_before: int, tokens_after: int) -> None:
        self.call_from_thread(
            self.query_one("#activity-row", ActivityProgress).set_phase,
            "Context reduced",
        )
        self.call_from_thread(
            self._append_entry,
            "SYSTEM",
            f"Context reduced from {tokens_before:,} to {tokens_after:,} estimated tokens.",
            "notice",
        )

    def response_completed(self, content: str) -> None:
        self.call_from_thread(
            self.query_one("#activity-row", ActivityProgress).set_phase,
            "Finalizing",
        )
        self.call_from_thread(self._append_entry, "FORGE", content, "forge")

    async def _append_entry(self, label: str, body: str, kind: str) -> None:
        await self.query_one("#conversation", ConversationView).append_entry(label, body, kind)

    def _refresh_sidebar(self) -> None:
        self.query_one("#sidebar", StatusRail).update_status(
            self.runtime,
            self.session_name,
            self._eft_text,
            len(self._queued_messages),
            agents_ready=self.subagent_session.ready_count(),
            agents_used=self.subagent_session.started > 0,
            active_subagent=self._active_subagent or "",
        )
        self.query_one("#header", HeaderBar).update_status(
            self.runtime,
            self.session_name,
            self._current_theme,
        )
        self.query_one("#footer", FooterBar).update_status(self.runtime, len(self._queued_messages))

    def _set_busy(self, busy: bool, label: str = "Working") -> None:
        self._busy = busy
        composer = self.query_one("#composer", TextArea)
        activity = self.query_one("#activity-row", ActivityProgress)
        composer.placeholder = (
            "Forge is working · Enter queues a message" if busy else "Ask Forge or enter /help"
        )
        composer.set_class(busy, "busy")
        if busy:
            self._turn_checkpoint_baseline = checkpoint_baseline(self.runtime)
            self._agent_started_at = None
            self._agent_current_step = 0
            self._agent_max_steps = 0
            self._last_step_time = None
            self._ema_step_duration = 0.0
            self._eft_text = ""
            self.query_one("#eft-banner", EftBanner).set_text("Waiting")
            activity.set_working(label)
            if self._eft_timer is not None:
                self._eft_timer.resume()
            self._refresh_sidebar()
            return
        self._agent_started_at = None
        self._eft_text = ""
        self.query_one("#eft-banner", EftBanner).set_text("Waiting")
        if self._eft_timer is not None:
            self._eft_timer.pause()
        activity.set_done()
        self._refresh_sidebar()
        self._schedule_queue_drain()
        if len(self.screen_stack) == 1:
            composer.focus()
