from pathlib import Path

from .checkpoints import CheckpointError, CheckpointManager
from .forge_core.agent import AgentMode, ForgeAgent
from .forge_core.config import ConfigurationError, ForgeConfig, load_configuration
from .forge_core.delegation import register_delegation_tool
from .forge_core.instructions import load_project_instructions
from .forge_core.presenter import AgentLifecycle
from .forge_core.provider import ForgeProvider
from .forge_core.safe_io import SafeWriteError
from .forge_core.sessions import SessionManager
from .forge_core.subagents import SubagentRunner
from .forge_core.tools import create_tool_registry
from .forge_core.workspace import Workspace, WorkspaceError
from .patches import PatchApplicationError
from .recovery import RecoveryError, RecoveryManager
from .sessions import SessionStorageError
from .ui.state import ForgeRuntime
from .validation import CommandExecutionError
from .version import __version__

FORGE_VERSION = __version__


class ForgeRuntimeError(Exception):
    """Raised when Forge cannot establish its local runtime boundaries."""


def build_runtime(
    workspace_root: Path | None = None,
    configuration: ForgeConfig | None = None,
    *,
    mode: AgentMode = AgentMode.ASK,
    working_directory: Path | None = None,
    lifecycle: AgentLifecycle | None = None,
) -> ForgeRuntime:
    """Build the primary agent and isolated subagent runtime for Textual."""
    try:
        workspace = Workspace(workspace_root)
        workspace_path = workspace.root
        resolved_configuration = configuration or load_configuration(project_root=workspace_path)
    except (ConfigurationError, WorkspaceError) as error:
        raise ForgeRuntimeError(f"Forge runtime state is unavailable: {error}") from error
    provider = ForgeProvider(resolved_configuration.model, configuration=resolved_configuration)
    instruction_start = working_directory or (
        Path.cwd() if workspace_root is None else workspace_path
    )
    project_instructions = load_project_instructions(
        instruction_start,
        repository_root=workspace_path,
    )
    try:
        tools = create_tool_registry(workspace)
        subagents = SubagentRunner(
            tools,
            provider,
            project_instructions,
            lifecycle=lifecycle,
        )
        register_delegation_tool(tools, subagents)
        agent = ForgeAgent(
            provider=provider,
            tools=tools,
            mode=mode,
            project_instructions=project_instructions,
            lifecycle=lifecycle,
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
            project_instructions=project_instructions,
        )
    except (
        CheckpointError,
        CommandExecutionError,
        PatchApplicationError,
        RecoveryError,
        SafeWriteError,
        SessionStorageError,
    ) as error:
        raise ForgeRuntimeError(f"Forge runtime state is unavailable: {error}") from error


def main() -> None:
    from .cli import main as cli_main

    cli_main()


if __name__ == "__main__":
    main()
