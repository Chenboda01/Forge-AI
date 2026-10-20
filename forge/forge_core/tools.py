from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from time import monotonic
from typing import Any, Final

from jsonschema import Draft202012Validator, SchemaError, ValidationError

from .redaction import redact_text
from .workspace import Workspace, WorkspaceError

DEFAULT_TOOL_TIMEOUT_SECONDS: Final = 10.0
DEFAULT_TOOL_OUTPUT_BYTES: Final = 30_000
MAX_TOOL_ERROR_BYTES: Final = 4_000
logger = logging.getLogger("forge.tools")


class Permission(StrEnum):
    READ_FILES = "read_files"
    SEARCH_FILES = "search_files"
    GIT_READ = "git_read"
    WRITE_FILES = "write_files"
    PROPOSE_PATCH = "propose_patch"
    APPLY_PATCH = "apply_patch"
    RUN_COMMANDS = "run_commands"
    DELEGATE = "delegate"


class RiskLevel(StrEnum):
    READ_ONLY = "read_only"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKED = "blocked"


class ToolStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PERMISSION_DENIED = "permission_denied"


@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., str]
    requires_approval: bool = False
    permission: Permission = Permission.READ_FILES
    risk_level: RiskLevel = RiskLevel.READ_ONLY
    modifies_workspace: bool = False
    network_access: bool = False
    timeout_seconds: float = DEFAULT_TOOL_TIMEOUT_SECONDS
    max_output_bytes: int = DEFAULT_TOOL_OUTPUT_BYTES

    def as_llm_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass(frozen=True, slots=True)
class ToolResult:
    tool_name: str
    status: ToolStatus
    output: str = ""
    error: str | None = None
    output_bytes: int = 0
    truncated: bool = False
    duration_seconds: float = 0.0

    def render(self) -> str:
        if self.status is ToolStatus.SUCCEEDED:
            rendered = self.output
        else:
            rendered = f"Tool error: {self.error or 'Tool execution failed.'}"
        if not self.truncated:
            return rendered
        retained_bytes = len(self.output.encode("utf-8"))
        return (
            f"{rendered}\n"
            f"[Tool output truncated: retained {retained_bytes} of {self.output_bytes} bytes; "
            "request a narrower result.]"
        )


class ToolError(Exception):
    """Raised when Forge cannot execute a tool."""


class ToolRegistrationError(ToolError, ValueError):
    """Raised when a tool name is registered more than once."""


class ToolRegistry:
    def __init__(
        self,
        workspace: Workspace | None = None,
        *,
        allowed_names: frozenset[str] | None = None,
        allowed_permissions: frozenset[Permission] | None = None,
    ):
        self.workspace = workspace
        self._allowed_names = allowed_names
        self._allowed_permissions = allowed_permissions
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ToolRegistrationError(f"Tool already registered: {tool.name}")
        if tool.timeout_seconds <= 0:
            raise ToolRegistrationError(f"Tool timeout must be positive: {tool.name}")
        if tool.max_output_bytes <= 0:
            raise ToolRegistrationError(f"Tool output limit must be positive: {tool.name}")
        try:
            Draft202012Validator.check_schema(tool.parameters)
        except SchemaError as error:
            raise ToolRegistrationError(f"Tool schema is invalid: {tool.name}") from error
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolError(f"Unknown tool: {name}")
        return tool

    def definitions(self) -> list[dict[str, Any]]:
        return [tool.as_llm_tool() for tool in self._tools.values() if self._is_allowed(tool)]

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        result = self.execute_result(name, arguments)
        if result.status is not ToolStatus.SUCCEEDED:
            raise ToolError(result.error or result.render())
        return result.render()

    def execute_result(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        tool = self.get(name)
        started = monotonic()
        if not self._is_allowed(tool):
            result = ToolResult(
                tool_name=name,
                status=ToolStatus.PERMISSION_DENIED,
                error=f"Permission denied for tool: {name}",
                duration_seconds=monotonic() - started,
            )
            self._log_result(result)
            return result
        try:
            Draft202012Validator(tool.parameters).validate(arguments)
            raw_output = tool.handler(**arguments)
            if not isinstance(raw_output, str):
                raise TypeError("Tool handler returned a non-text result.")
        except ValidationError as error:
            result = ToolResult(
                tool_name=name,
                status=ToolStatus.FAILED,
                error=_safe_error(f"Invalid arguments for {name}: {error.message}"),
                duration_seconds=monotonic() - started,
            )
        except (
            OSError,
            RuntimeError,
            TimeoutError,
            TypeError,
            ValueError,
            ToolError,
            WorkspaceError,
        ) as error:
            result = ToolResult(
                tool_name=name,
                status=ToolStatus.FAILED,
                error=_safe_error(str(error)),
                duration_seconds=monotonic() - started,
            )
        else:
            output = redact_text(raw_output)
            output_bytes = len(output.encode("utf-8"))
            retained = _truncate(output, tool.max_output_bytes)
            result = ToolResult(
                tool_name=name,
                status=ToolStatus.SUCCEEDED,
                output=retained,
                output_bytes=output_bytes,
                truncated=output_bytes > tool.max_output_bytes,
                duration_seconds=monotonic() - started,
            )
        self._log_result(result)
        return result

    def only(self, allowed_names: tuple[str, ...]) -> ToolRegistry:
        filtered = ToolRegistry(
            workspace=self.workspace,
            allowed_names=frozenset(allowed_names),
            allowed_permissions=self._allowed_permissions,
        )
        for tool in self._tools.values():
            filtered.register(tool)
        return filtered

    def for_permissions(self, allowed_permissions: frozenset[Permission]) -> ToolRegistry:
        filtered = ToolRegistry(
            workspace=self.workspace,
            allowed_names=self._allowed_names,
            allowed_permissions=allowed_permissions,
        )
        for tool in self._tools.values():
            filtered.register(tool)
        return filtered

    def read_only(self) -> ToolRegistry:
        """Return a registry containing only non-mutating local tools."""
        filtered = ToolRegistry(workspace=self.workspace)
        for tool in self._tools.values():
            if (
                self._is_allowed(tool)
                and tool.risk_level is RiskLevel.READ_ONLY
                and not tool.modifies_workspace
                and not tool.network_access
            ):
                filtered.register(tool)
        return filtered

    def _is_allowed(self, tool: Tool) -> bool:
        name_allowed = self._allowed_names is None or tool.name in self._allowed_names
        permission_allowed = (
            self._allowed_permissions is None or tool.permission in self._allowed_permissions
        )
        return name_allowed and permission_allowed

    @staticmethod
    def _log_result(result: ToolResult) -> None:
        extra = {
            "forge_tool_name": result.tool_name,
            "forge_tool_status": result.status.value,
            "forge_tool_output_bytes": result.output_bytes,
            "forge_tool_truncated": result.truncated,
            "forge_tool_duration_seconds": result.duration_seconds,
        }
        if result.status is ToolStatus.SUCCEEDED:
            logger.info("tool execution completed", extra=extra)
        else:
            logger.warning("tool execution failed", extra=extra)


def _safe_error(error: str) -> str:
    return redact_text(error)[:MAX_TOOL_ERROR_BYTES]


def _truncate(output: str, limit: int) -> str:
    encoded = output.encode("utf-8")
    if len(encoded) <= limit:
        return output
    return encoded[:limit].decode("utf-8", errors="ignore")


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
