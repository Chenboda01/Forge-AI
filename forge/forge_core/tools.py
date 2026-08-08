from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .workspace import Workspace, WorkspaceError


@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., str]
    requires_approval: bool = False

    def as_llm_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolError(Exception):
    """Raised when Forge cannot execute a tool."""


class ToolRegistrationError(ToolError, ValueError):
    """Raised when a tool name is registered more than once."""


class ToolRegistry:
    def __init__(self, workspace: Workspace | None = None):
        self.workspace = workspace
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ToolRegistrationError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolError(f"Unknown tool: {name}")
        return tool

    def definitions(self) -> list[dict[str, Any]]:
        return [tool.as_llm_tool() for tool in self._tools.values()]

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        tool = self.get(name)
        try:
            return tool.handler(**arguments)
        except TypeError as error:
            raise ToolError(f"Invalid arguments for {name}: {error}") from error
        except WorkspaceError as error:
            raise ToolError(str(error)) from error

    def only(self, allowed_names: tuple[str, ...]) -> ToolRegistry:
        filtered = ToolRegistry(workspace=self.workspace)
        for name in allowed_names:
            tool = self._tools.get(name)
            if tool is not None:
                filtered.register(tool)
        return filtered


def create_tool_registry(workspace: Workspace) -> ToolRegistry:
    from .command_tools import register_command_tools
    from .filesystem_tools import register_filesystem_tools
    from .patch_tools import register_patch_tools
    from .validation_tools import register_validation_tools

    registry = ToolRegistry(workspace)
    register_filesystem_tools(registry, workspace)
    register_command_tools(registry, workspace)
    register_patch_tools(registry, workspace)
    register_validation_tools(registry, workspace)
    return registry
