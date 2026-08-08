from pathlib import Path

from rich.console import Console

from .checkpoints import CheckpointManager
from .forge_core.agent import ForgeAgent
from .forge_core.config import get_default_model
from .forge_core.delegation import register_delegation_tool
from .forge_core.provider import ForgeProvider, ForgeProviderError
from .forge_core.sessions import SessionManager
from .forge_core.subagents import SubagentRunner
from .forge_core.tools import create_tool_registry
from .forge_core.workspace import Workspace
from .recovery import RecoveryManager
from .ui.app import ForgeApp
from .ui.state import ForgeRuntime
from .version import __version__

FORGE_VERSION = __version__


def build_runtime(workspace_root: Path | None = None) -> ForgeRuntime:
    """Build the primary agent and isolated subagent runtime for Textual."""
    workspace_path = (workspace_root or Path.cwd()).resolve()
    provider = ForgeProvider(get_default_model())
    workspace = Workspace(workspace_path)
    tools = create_tool_registry(workspace)
    subagents = SubagentRunner(tools, provider)
    register_delegation_tool(tools, subagents)
    agent = ForgeAgent(
        provider=provider,
        tools=tools,
    )
    return ForgeRuntime(
        provider=provider,
        agent=agent,
        subagents=subagents,
        sessions=SessionManager(workspace_path),
        checkpoints=CheckpointManager(workspace),
        recovery=RecoveryManager(workspace_path),
        workspace=workspace_path,
        version=FORGE_VERSION,
    )


def main() -> None:
    try:
        runtime = build_runtime()
    except ForgeProviderError as error:
        Console(stderr=True).print(f"[red]Forge could not start:[/red] {error}")
        return
    ForgeApp(runtime).run()


if __name__ == "__main__":
    main()
