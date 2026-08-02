from threading import Event

from textual import events, on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Input

from forge.forge_core.agent import AgentError, AgentInterruptedError
from forge.forge_core.subagents import SUBAGENTS, SubagentError, SubagentInterruptedError
from forge.ui.approval import ApprovalScreen
from forge.ui.commands import CommandService, handle_command
from forge.ui.keyboard import KeyboardController, request_interrupt
from forge.ui.state import ForgeRuntime
from forge.ui.widgets import ActivityProgress, ConversationView, StatusRail

APPROVAL_TIMEOUT_SECONDS = 60


class ForgeApp(App[None]):
    """Full-screen terminal interface for the Forge runtime."""

    CSS_PATH = "app.tcss"
    BINDINGS = [("ctrl+q", "quit", "Quit")]

    def __init__(self, runtime: ForgeRuntime | None = None) -> None:
        super().__init__()
        self.runtime = runtime
        self.commands = CommandService(runtime)
        self.keyboard = KeyboardController()
        self.session_name = ""
        self._approval_decision: Event | None = None
        self._busy = False
        if runtime is not None:
            runtime.agent.presenter = self

    def compose(self) -> ComposeResult:
        with Horizontal(id="shell"):
            with Vertical(id="main"):
                yield ConversationView()
                yield ActivityProgress()
                yield Input(
                    placeholder="Ask Forge or enter /help",
                    id="composer",
                )
            yield StatusRail(id="sidebar")

    async def on_mount(self) -> None:
        await self._append_entry(
            "FORGE",
            "Shape code. Temper bugs. Ship stronger software.\nEnter /help for commands.",
            "forge",
        )
        self._refresh_sidebar()
        self.query_one("#composer", Input).focus()

    def on_resize(self, event: events.Resize) -> None:
        is_wide = event.size.width >= 72
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
        if event.key not in {"up", "down"}:
            return
        composer = self.query_one("#composer", Input)
        if not composer.has_focus or composer.disabled:
            return
        value = (
            self.keyboard.previous(composer.value) if event.key == "up" else self.keyboard.next()
        )
        if value is None:
            return
        event.prevent_default()
        event.stop()
        composer.value = value
        composer.cursor_position = len(value)

    @on(Input.Submitted, "#composer")
    async def submit_input(self, event: Input.Submitted) -> None:
        message = event.value.strip()
        event.input.clear()
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
        self.call_from_thread(
            self.query_one("#activity-row", ActivityProgress).set_phase,
            f"Thinking (pass {step})",
        )

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
        self.query_one("#sidebar", StatusRail).update_status(self.runtime, self.session_name)

    def _set_busy(self, busy: bool, label: str = "Working") -> None:
        self._busy = busy
        composer = self.query_one("#composer", Input)
        activity = self.query_one("#activity-row", ActivityProgress)
        composer.disabled = busy
        composer.placeholder = "Forge is working" if busy else "Ask Forge or enter /help"
        if busy:
            activity.set_working(label)
            return
        activity.set_done()
        composer.focus()
