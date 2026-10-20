from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict

from forge.validation import (
    CommandExecutionError,
    CommandPolicyError,
    CommandRequest,
    RestrictedCommandRunner,
    ValidationResultStore,
)

from .tools import Permission, RiskLevel, Tool, ToolError, ToolRegistry
from .workspace import Workspace


def _run_read_only_command(arguments: list[str], workspace: Workspace) -> str:
    environment = {
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_PAGER": "cat",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": str(workspace.root / ".forge" / "runtime-home"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.defpath,
    }
    try:
        result = subprocess.run(
            arguments,
            cwd=workspace.root,
            capture_output=True,
            env=environment,
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
        return _run_read_only_command(
            [
                "git",
                "--no-pager",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.hooksPath=/dev/null",
                "status",
                "--short",
            ],
            workspace,
        )

    def git_diff() -> str:
        output = _run_read_only_command(
            [
                "git",
                "--no-pager",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.hooksPath=/dev/null",
                "diff",
                "--no-ext-diff",
                "--no-textconv",
            ],
            workspace,
        )
        return output or "No unstaged changes."

    def git_log(max_count: int = 20, path: str | None = None) -> str:
        arguments = [
            "git",
            "--no-pager",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.hooksPath=/dev/null",
            "log",
            "--no-ext-diff",
            "--no-decorate",
            f"--max-count={max_count}",
            "--format=%h %s",
            "--",
        ]
        if path is not None:
            target = workspace.resolve_for_context(path)
            if not target.exists():
                raise ToolError(f"Path does not exist: {path}")
            arguments.append(str(target.relative_to(workspace.root)))
        return _run_read_only_command(arguments, workspace) or "No commits found."

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
            permission=Permission.GIT_READ,
            risk_level=RiskLevel.READ_ONLY,
            timeout_seconds=20,
            max_output_bytes=30_000,
        )
    )
    registry.register(
        Tool(
            name="git_diff",
            description="Show unstaged Git changes.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            handler=git_diff,
            permission=Permission.GIT_READ,
            risk_level=RiskLevel.READ_ONLY,
            timeout_seconds=20,
            max_output_bytes=30_000,
        )
    )
    registry.register(
        Tool(
            name="git_log",
            description="Show recent Git commit subjects for the workspace or a relative path.",
            parameters={
                "type": "object",
                "properties": {
                    "max_count": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                    "path": {
                        "type": ["string", "null"],
                        "description": "Optional path relative to the project root.",
                        "default": None,
                    },
                },
                "additionalProperties": False,
            },
            handler=git_log,
            permission=Permission.GIT_READ,
            risk_level=RiskLevel.READ_ONLY,
            timeout_seconds=20,
            max_output_bytes=30_000,
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
            permission=Permission.RUN_COMMANDS,
            risk_level=RiskLevel.MEDIUM,
            modifies_workspace=True,
            timeout_seconds=60,
            max_output_bytes=30_000,
        )
    )
