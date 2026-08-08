from __future__ import annotations

import re
from typing import TYPE_CHECKING

from forge.forge_core.models import MODELS
from forge.forge_core.provider import ForgeProviderError
from forge.forge_core.subagents import SUBAGENTS
from forge.ui.checkpoint_commands import checkpoint_text, undo_checkpoint
from forge.ui.fast_select import FastSelectScreen
from forge.ui.recovery_commands import recover, recovery_text
from forge.ui.session_commands import history_text, resume_session, sessions_text
from forge.ui.state import ForgeRuntime, estimate_cost
from forge.ui.theme_select import ThemeSelectScreen
from forge.ui.themes import THEMES
from forge.ui.updates import start_update
from forge.ui.widgets import ConversationView

if TYPE_CHECKING:
    from forge.ui.app import ForgeApp

_FAST_VARIANTS: dict[str, int] = {
    "low": 50,
    "mid": 35,
    "high": 20,
    "xhigh": 10,
    "max": 5,
}

_COMPLEXITY_PATTERNS: list[tuple[str, int]] = [
    (r"\b(refactor|restructure|reorganize)\b", 35),
    (r"\b(implement|build|create|develop|add)\b", 25),
    (r"\b(debug|diagnose|investigate|trace)\b", 15),
    (r"\b(fix|repair|resolve|patch)\b", 10),
    (r"\b(analyze|inspect|audit|review|examine)\b", 10),
    (r"\b(test|verify|validate|confirm)\b", 15),
    (r"\b(all|entire|every|whole|full|complete)\b", 15),
    (r"\b(system|module|pipeline|workflow|engine)\b", 15),
    (r"\b(security|auth|permission|sandbox)\b", 20),
]


def estimate_steps(task: str) -> int:
    """Heuristic step-count estimator based on task description complexity."""
    task_lower = task.lower()
    base = 10  # minimum for trivial queries
    base += len(task.split())  # word count as rough complexity proxy

    for pattern, bonus in _COMPLEXITY_PATTERNS:
        if re.search(pattern, task_lower):
            base += bonus

    return max(10, min(base, 300))


class CommandService:
    """Executes non-visual slash commands against an optional Forge runtime."""

    def __init__(self, runtime: ForgeRuntime | None) -> None:
        self.runtime = runtime

    @staticmethod
    def help_text() -> str:
        return (
            "Commands\n"
            "/help  /status  /usage  /models  /model NAME\n"
            "/files  /read FILE  /tree  /new  /sessions  /resume ID  /history\n"
            "/agents  /agent NAME OBJECTIVE  /checkpoint  /undo [ID]\n"
            "/recovery  /recover ACTION ID\n"
            "/updates  /compact\n"
            "/asn TASK  /fast [low|mid|high|xhigh|max]  /theme  /clear  /exit"
        )

    @staticmethod
    def models_text() -> str:
        return "Models\n" + "\n".join(
            f"{alias:<20} {model.model_id}" for alias, model in MODELS.items()
        )

    @staticmethod
    def agents_text() -> str:
        return "Agents\n" + "\n".join(
            f"{name:<12} {spec.description}" for name, spec in SUBAGENTS.items()
        )

    def status_text(self) -> str:
        runtime = self.runtime
        if runtime is None:
            return "Status\nModel: offline\nWorkspace: not connected"
        return (
            "Status\n"
            f"Provider: {runtime.provider.model.provider}\n"
            f"Model: {runtime.agent.model_id}\n"
            f"Workspace: {runtime.workspace}"
        )

    def usage_text(self) -> str:
        runtime = self.runtime
        if runtime is None:
            return "Usage\nNo model runtime is connected."
        agent = runtime.agent
        cost = estimate_cost(agent)
        cost_text = "unavailable" if cost is None else f"${cost:.4f}"
        return (
            "Usage\n"
            f"Input tokens: {agent.input_tokens:,}\n"
            f"Output tokens: {agent.output_tokens:,}\n"
            f"Total tokens: {agent.total_tokens:,}\n"
            f"Estimated cost: {cost_text}"
        )

    def switch_model(self, alias: str) -> str:
        runtime = self.runtime
        if runtime is None:
            return "No model runtime is connected."
        if not alias:
            return "Usage: /model NAME"
        try:
            runtime.provider.switch_model(alias)
        except ForgeProviderError as error:
            return str(error)
        return f"Switched to {runtime.provider.model.name}."

    def list_files(self, recursive: bool = False) -> str:
        runtime = self.runtime
        if runtime is None:
            return "No workspace runtime is connected."
        return runtime.agent.tools.execute("list_files", {"recursive": recursive})

    def read_file(self, path: str) -> str:
        if not path:
            return "Usage: /read FILE"
        runtime = self.runtime
        if runtime is None:
            return "No workspace runtime is connected."
        return runtime.agent.tools.execute("read_file", {"path": path})

    def new_session(self) -> str:
        runtime = self.runtime
        if runtime is None:
            return "Started a new conversation."
        if len(runtime.agent.messages) > 1:
            runtime.sessions.save(
                messages=runtime.agent.messages,
                model=runtime.agent.model_id,
                input_tokens=runtime.agent.input_tokens,
                output_tokens=runtime.agent.output_tokens,
            )
        runtime.agent.reset()
        return "Started a new conversation."

    def sessions_text(self) -> str:
        return sessions_text(self.runtime)

    def resume_session(self, session_id: str) -> str:
        return resume_session(self.runtime, session_id)

    def history_text(self) -> str:
        return history_text(self.runtime)

    def checkpoint_text(self) -> str:
        return checkpoint_text(self.runtime)

    def undo(self, checkpoint_id: str) -> str:
        return undo_checkpoint(self.runtime, checkpoint_id)

    def recovery_text(self) -> str:
        return recovery_text(self.runtime)

    def recover(self, request: str) -> str:
        return recover(self.runtime, request)

    def asn(self, task: str) -> str:
        if not task.strip():
            return "Usage: /asn TASK\nAuto-estimates the number of agent steps your task needs."
        runtime = self.runtime
        if runtime is None:
            return "No model runtime is connected."
        steps = estimate_steps(task)
        runtime.agent.max_steps = steps
        return f"Estimated {steps} steps needed. Max steps set to {steps}."

    def fast(self, variant: str) -> str:
        runtime = self.runtime
        if runtime is None:
            return "No model runtime is connected."
        steps = _FAST_VARIANTS[variant]
        runtime.agent.max_steps = steps
        return (
            f"Fast mode ({variant}) — max steps set to {steps}.\n"
            "Less precise, but faster. Use /asn to switch back."
        )


async def handle_command(app: ForgeApp, command: str) -> None:
    name, _, argument = command.partition(" ")
    name = name.lower()
    simple_commands = {
        "/help": app.commands.help_text,
        "/status": app.commands.status_text,
        "/usage": app.commands.usage_text,
        "/models": app.commands.models_text,
        "/files": app.commands.list_files,
        "/sessions": app.commands.sessions_text,
        "/history": app.commands.history_text,
        "/agents": app.commands.agents_text,
        "/checkpoint": app.commands.checkpoint_text,
        "/recovery": app.commands.recovery_text,
    }
    handler = simple_commands.get(name)
    if handler is not None:
        await app._show_command_result(handler())
        return
    if name == "/model":
        await app._show_command_result(app.commands.switch_model(argument.strip()))
        return
    if name == "/read":
        await app._show_command_result(app.commands.read_file(argument.strip()))
        return
    if name == "/resume":
        await app._show_command_result(app.commands.resume_session(argument.strip()))
        return
    if name == "/tree":
        await app._show_command_result(app.commands.list_files(recursive=True))
        return
    if name == "/agent":
        await app._start_subagent(argument.strip())
        return
    if name == "/undo":
        await app._show_command_result(app.commands.undo(argument.strip()))
        return
    if name == "/recover":
        await app._show_command_result(app.commands.recover(argument.strip()))
        return
    if name == "/new":
        output = app.commands.new_session()
        app.session_name = ""
        await app.query_one("#conversation", ConversationView).reset()
        await app._show_command_result(output)
        return
    if name == "/compact":
        if app.runtime is None:
            await app._show_command_result("No model runtime is connected.")
            return
        app._set_busy(True)
        app.compact_conversation()
        return
    if name == "/clear":
        await app.query_one("#conversation", ConversationView).reset()
        await app._show_command_result("Conversation display cleared.")
        return
    if name == "/updates":
        start_update(app)
        return
    if name in ("/asn", "/ans"):
        await app._show_command_result(app.commands.asn(argument.strip()))
        return
    if name == "/fast":
        await _fast_select(app)
        return
    if name == "/theme":
        await _theme_select(app)
        return
    if name == "/exit":
        app.exit()
        return
    await app._show_command_result(f"Unknown command: {name}. Enter /help.")


async def _fast_select(app: ForgeApp) -> None:
    screen = FastSelectScreen()

    async def selected(variant: str | None) -> None:
        if variant:
            await app._show_command_result(app.commands.fast(variant))

    await app.push_screen(screen, callback=selected)


async def _theme_select(app: ForgeApp) -> None:
    screen = ThemeSelectScreen()

    async def selected(name: str | None) -> None:
        if name and name in THEMES:
            app.apply_theme(name)
            await app._show_command_result(f"Theme set to {name}.")

    await app.push_screen(screen, callback=selected)
