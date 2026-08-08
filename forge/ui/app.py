import asyncio
import contextlib
from threading import Event
from time import monotonic

from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, TextArea

from forge.forge_core.agent import AgentError, AgentInterruptedError
from forge.forge_core.subagents import SUBAGENTS, SubagentError, SubagentInterruptedError
from forge.ui.approval import ApprovalScreen
from forge.ui.commands import CommandService, handle_command
from forge.ui.keyboard import KeyboardController, request_interrupt
from forge.ui.state import ForgeRuntime
from forge.ui.themes import DEFAULT_THEME, THEMES
from forge.ui.widgets import (
    STARTUP_PHASES,
    ActivityProgress,
    ConversationView,
    EftBanner,
    StartupBar,
    StatusRail,
)

APPROVAL_TIMEOUT_SECONDS = 60
EMA_ALPHA = 0.3


class ForgeApp(App[None]):
    """Full-screen terminal interface for the Forge runtime."""

    CSS_PATH = "app.tcss"
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("shift+enter", "insert_composer_newline", priority=True, show=False),
        Binding("enter", "submit_composer", priority=True, show=False),
    ]

    def __init__(self, runtime: ForgeRuntime | None = None, *, skip_startup: bool = False) -> None:
        super().__init__()
        self.runtime = runtime
        self.commands = CommandService(runtime)
        self.keyboard = KeyboardController()
        self.session_name = ""
        self._skip_startup = skip_startup
        self._current_theme = DEFAULT_THEME
        for theme in THEMES.values():
            self.register_theme(theme)
        self.theme = DEFAULT_THEME
        self._approval_decision: Event | None = None
        self._busy = False
        self._agent_started_at: float | None = None
        self._agent_max_steps: int = 0
        self._agent_current_step: int = 0
        self._eft_text = ""
        self._eft_timer = None
        self._last_step_time: float | None = None
        self._ema_step_duration: float = 0.0
        if runtime is not None:
            runtime.agent.presenter = self

    def compose(self) -> ComposeResult:
        with Horizontal(id="shell"):
            with Vertical(id="main"):
                yield EftBanner()
                yield ConversationView()
                yield ActivityProgress()
                yield TextArea(
                    "",
                    placeholder="Ask Forge or enter /help",
                    id="composer",
                    show_line_numbers=False,
                )
            yield StatusRail(id="sidebar")
        yield StartupBar()

    async def on_mount(self) -> None:
        self._eft_timer = self.set_interval(1.0, self._refresh_eft, pause=True)
        self._refresh_sidebar()
        self.query_one("#composer", TextArea).focus()
        if self._skip_startup:
            self.query_one(StartupBar).display = False
            await self._append_entry(
                "FORGE",
                "Shape code. Temper bugs. Ship stronger software.\nEnter /help for commands.",
                "forge",
            )
        else:
            shell = self.query_one("#shell", Horizontal)
            shell.display = False
            asyncio.create_task(self._boot_sequence())

    def apply_theme(self, name: str) -> None:
        if name not in THEMES:
            return
        self._current_theme = name
        self.theme = name

    async def _boot_sequence(self) -> None:
        bar = self.query_one(StartupBar)
        for i, phase in enumerate(STARTUP_PHASES, start=1):
            bar.set_phase(i, phase)
            await asyncio.sleep(0.35)
        bar.display = False
        shell = self.query_one("#shell", Horizontal)
        shell.display = True
        await self._append_entry(
            "FORGE",
            "Shape code. Temper bugs. Ship stronger software.\nEnter /help for commands.",
            "forge",
        )

    def on_resize(self, event: events.Resize) -> None:
        is_wide = event.size.width >= 72
        with contextlib.suppress(Exception):
            self.query_one("#sidebar", StatusRail).display = is_wide

    async def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            event.prevent_default()
            event.stop()
            presses = self.keyboard.record_escape()
            if presses >= 5:
                self.exit()
            elif presses == 2:
                await request_interrupt(self)
            return

        self.keyboard.reset_escape()
        composer = self.query_one("#composer", TextArea)
        if event.key not in {"up", "down"}:
            return
        if not composer.has_focus or composer.disabled:
            return
        value = self.keyboard.previous(composer.text) if event.key == "up" else self.keyboard.next()
        if value is None:
            return
        event.prevent_default()
        event.stop()
        composer.load_text(value)
        composer.cursor_location = (value.count("\n"), len(value.rsplit("\n", maxsplit=1)[-1]))

    async def action_submit_composer(self) -> None:
        focused = self.screen.focused
        if isinstance(focused, Button):
            focused.press()
            return
        composer = self.query_one("#composer", TextArea)
        if not composer.has_focus or composer.disabled:
            return
        message = composer.text.strip()
        composer.clear()
        if not message:
            return
        self.keyboard.remember(message)

        if message.startswith("/"):
            await handle_command(self, message)
            return

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
        except SubagentError as error:
            self.call_from_thread(self._append_entry, "SUBAGENT ERROR", str(error), "error")
        else:
            self.call_from_thread(
                self._append_entry,
                f"SUBAGENT {agent_name.upper()}",
                report,
                "forge",
            )
        finally:
            self.call_from_thread(self._set_busy, False)
            self.call_from_thread(self._refresh_sidebar)

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
        self.query_one("#composer", TextArea).placeholder = text

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
        )

    def _set_busy(self, busy: bool, label: str = "Working") -> None:
        self._busy = busy
        composer = self.query_one("#composer", TextArea)
        activity = self.query_one("#activity-row", ActivityProgress)
        composer.disabled = busy
        composer.placeholder = "Forge is working" if busy else "Ask Forge or enter /help"
        if busy:
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
        composer.focus()
