from __future__ import annotations

from typing import TYPE_CHECKING

from forge.forge_core.models import MODELS
from forge.forge_core.provider import ForgeProviderError
from forge.forge_core.subagents import SUBAGENTS
from forge.ui.state import ForgeRuntime, estimate_cost
from forge.ui.updates import start_update
from forge.ui.widgets import ConversationView

if TYPE_CHECKING:
    from forge.ui.app import ForgeApp


class CommandService:
    """Executes non-visual slash commands against an optional Forge runtime."""

    def __init__(self, runtime: ForgeRuntime | None) -> None:
        self.runtime = runtime

    @staticmethod
    def help_text() -> str:
        return (
            "Commands\n"
            "/help  /status  /usage  /models  /model NAME\n"
            "/files  /read FILE  /tree  /new  /sessions\n"
            "/agents  /agent NAME OBJECTIVE  /updates  /compact  /clear  /exit"
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
        runtime = self.runtime
        if runtime is None:
            return "Sessions\nNo session storage is connected."
        sessions = runtime.sessions.list_sessions()
        if not sessions:
            return "Sessions\nNo saved sessions."
        return "Sessions\n" + "\n".join(
            f"{session.id}  {session.name}  {session.total_tokens:,} tokens" for session in sessions
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
        "/agents": app.commands.agents_text,
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
    if name == "/tree":
        await app._show_command_result(app.commands.list_files(recursive=True))
        return
    if name == "/agent":
        await app._start_subagent(argument.strip())
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
    if name == "/exit":
        app.exit()
        return
    await app._show_command_result(f"Unknown command: {name}. Enter /help.")
