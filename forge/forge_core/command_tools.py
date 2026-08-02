from __future__ import annotations

import json
import shlex
import subprocess
from typing import Final

from .tools import Tool, ToolError, ToolRegistry
from .workspace import Workspace

ALLOWED_EXECUTABLES: Final = frozenset({"pytest", "pyright", "ruff"})


def _run_read_only_command(arguments: list[str], workspace: Workspace) -> str:
    try:
        result = subprocess.run(
            arguments,
            cwd=workspace.root,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except FileNotFoundError as error:
        raise ToolError(f"Command not found: {arguments[0]}") from error
    if result.returncode != 0:
        raise ToolError(result.stderr.strip() or f"Command exited with {result.returncode}")
    return result.stdout.strip()


def _parse_validation_command(command: str) -> list[str]:
    try:
        arguments = shlex.split(command)
    except ValueError as error:
        raise ToolError(f"Command could not be parsed: {error}") from error
    if not arguments:
        raise ToolError("Command is empty.")
    if arguments[0] not in ALLOWED_EXECUTABLES:
        raise ToolError(f"Command executable is not permitted: {arguments[0]}")
    return arguments


def register_command_tools(registry: ToolRegistry, workspace: Workspace) -> None:
    def git_status() -> str:
        return _run_read_only_command(["git", "status", "--short"], workspace)

    def git_diff() -> str:
        output = _run_read_only_command(["git", "diff"], workspace)
        return output or "No unstaged changes."

    def run_command(command: str) -> str:
        arguments = _parse_validation_command(command)
        result = subprocess.run(
            arguments,
            cwd=workspace.root,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        output = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
        return json.dumps(
            {"exit_code": result.returncode, "output": output[:30_000]},
            indent=2,
        )

    registry.register(
        Tool(
            name="git_status",
            description="Show the current Git working-tree status.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            handler=git_status,
        )
    )
    registry.register(
        Tool(
            name="git_diff",
            description="Show unstaged Git changes.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            handler=git_diff,
        )
    )
    registry.register(
        Tool(
            name="run_command",
            description="Run an approved validation command inside the project.",
            parameters={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
                "additionalProperties": False,
            },
            handler=run_command,
            requires_approval=True,
        )
    )
