from __future__ import annotations

import json
import subprocess
from dataclasses import asdict

from forge.validation import (
    CommandExecutionError,
    CommandPolicyError,
    CommandRequest,
    RestrictedCommandRunner,
    ValidationResultStore,
)

from .tools import Tool, ToolError, ToolRegistry
from .workspace import Workspace


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


def register_command_tools(registry: ToolRegistry, workspace: Workspace) -> None:
    runner = RestrictedCommandRunner(workspace.root)
    results = ValidationResultStore(workspace.root)

    def git_status() -> str:
        return _run_read_only_command(["git", "status", "--short"], workspace)

    def git_diff() -> str:
        output = _run_read_only_command(["git", "diff"], workspace)
        return output or "No unstaged changes."

    def run_command(arguments: list[str]) -> str:
        try:
            result = runner.run(CommandRequest(tuple(arguments)))
        except (CommandExecutionError, CommandPolicyError) as error:
            record = results.record_unavailable(tuple(arguments), str(error))
            raise ToolError(f"{error} Validation record: {record.id}") from error
        record = results.record_execution(result)
        payload = asdict(result)
        payload["record_id"] = record.id
        payload["status"] = record.status
        return json.dumps(payload, indent=2)

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
                "properties": {
                    "arguments": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    }
                },
                "required": ["arguments"],
                "additionalProperties": False,
            },
            handler=run_command,
            requires_approval=True,
        )
    )
