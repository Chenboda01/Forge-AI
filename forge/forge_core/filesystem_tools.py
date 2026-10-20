from __future__ import annotations

import os
import shutil
import subprocess
from contextlib import ExitStack
from pathlib import Path
from typing import Final

from .safe_io import SafeReadError, open_read_file_beneath
from .tools import Permission, RiskLevel, Tool, ToolError, ToolRegistry
from .workspace import Workspace, WorkspaceError

MAX_SEARCH_FILES: Final = 64
SEARCH_ENVIRONMENT: Final = {
    "HOME": "/nonexistent",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "NO_COLOR": "1",
    "PATH": os.defpath,
}


def register_filesystem_tools(registry: ToolRegistry, workspace: Workspace) -> None:
    def list_files(path: str = ".", recursive: bool = False) -> str:
        directory = workspace.resolve_for_context(path)
        if not directory.exists():
            raise ToolError(f"Path does not exist: {path}")
        if not directory.is_dir():
            raise ToolError(f"Not a directory: {path}")

        lines: list[str] = []
        paths = directory.rglob("*") if recursive else directory.iterdir()
        for item in sorted(paths):
            relative = item.relative_to(workspace.root)
            try:
                visible_item = workspace.resolve_for_context(str(relative))
            except WorkspaceError:
                continue
            lines.append(f"{relative}/" if visible_item.is_dir() else str(relative))
        return "\n".join(lines) or "Directory is empty."

    def read_file(path: str, start_line: int = 1, end_line: int | None = None) -> str:
        lines = workspace.read_text(path).splitlines()

        start = max(start_line - 1, 0)
        stop = end_line if end_line is not None else len(lines)
        selected = lines[start:stop]
        numbered = [
            f"{line_number:4} | {line}"
            for line_number, line in enumerate(selected, start=start + 1)
        ]
        return "\n".join(numbered) or "No content in this range."

    def search_files(query: str, path: str = ".") -> str:
        directory = workspace.resolve_for_context(path)
        if not directory.exists():
            raise ToolError(f"Path does not exist: {path}")

        candidates = _context_files(workspace, directory)
        if not candidates:
            return "No matches found."
        if len(candidates) > MAX_SEARCH_FILES:
            raise ToolError(
                f"Search includes more than {MAX_SEARCH_FILES} files; request a narrower path."
            )
        ripgrep = shutil.which("rg", path=os.defpath)
        if ripgrep is None:
            raise ToolError("ripgrep is not installed in a trusted system location.")

        with ExitStack() as stack:
            descriptors: list[int] = []
            aliases: dict[str, str] = {}
            for candidate in candidates:
                try:
                    descriptor = open_read_file_beneath(workspace.root, candidate)
                except SafeReadError:
                    continue
                stack.callback(os.close, descriptor)
                descriptor_path = f"/proc/self/fd/{descriptor}"
                descriptors.append(descriptor)
                aliases[descriptor_path] = str(candidate.relative_to(workspace.root))
            if not descriptors:
                return "No matches found."
            command = [
                ripgrep,
                "--line-number",
                "--with-filename",
                "--max-columns=500",
                "--max-count=20",
                query,
                *aliases,
            ]
            try:
                result = subprocess.run(
                    command,
                    cwd=workspace.root,
                    capture_output=True,
                    env=SEARCH_ENVIRONMENT,
                    text=True,
                    timeout=10,
                    check=False,
                    pass_fds=tuple(descriptors),
                )
            except FileNotFoundError as error:
                raise ToolError("Trusted ripgrep executable became unavailable.") from error

        if result.returncode == 1:
            return "No matches found."
        if result.returncode != 0:
            raise ToolError(result.stderr.strip())
        return _restore_search_paths(result.stdout.strip(), aliases)

    registry.register(
        Tool(
            name="list_files",
            description="List files and directories inside the current Forge project.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path relative to the project root.",
                        "default": ".",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "Whether to list files recursively.",
                        "default": False,
                    },
                },
                "additionalProperties": False,
            },
            handler=list_files,
            permission=Permission.READ_FILES,
            risk_level=RiskLevel.READ_ONLY,
            timeout_seconds=10,
            max_output_bytes=30_000,
        )
    )
    registry.register(
        Tool(
            name="read_file",
            description="Read all or part of a UTF-8 text file.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to the project root."},
                    "start_line": {"type": "integer", "minimum": 1, "default": 1},
                    "end_line": {
                        "type": ["integer", "null"],
                        "minimum": 1,
                        "default": None,
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=read_file,
            permission=Permission.READ_FILES,
            risk_level=RiskLevel.READ_ONLY,
            timeout_seconds=10,
            max_output_bytes=30_000,
        )
    )
    registry.register(
        Tool(
            name="search_files",
            description="Search project files using a text or regex query.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "path": {"type": "string", "default": "."},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            handler=search_files,
            permission=Permission.SEARCH_FILES,
            risk_level=RiskLevel.READ_ONLY,
            timeout_seconds=10,
            max_output_bytes=30_000,
        )
    )


def _context_files(workspace: Workspace, path: Path) -> list[Path]:
    if path.is_file():
        return [path]

    files: list[Path] = []
    for item in path.rglob("*"):
        relative = item.relative_to(workspace.root)
        try:
            visible_item = workspace.resolve_for_context(str(relative))
        except WorkspaceError:
            continue
        if visible_item.is_file():
            files.append(visible_item)
    return files


def _restore_search_paths(output: str, aliases: dict[str, str]) -> str:
    lines: list[str] = []
    for line in output.splitlines():
        source, separator, match = line.partition(":")
        lines.append(f"{aliases.get(source, source)}{separator}{match}")
    return "\n".join(lines)
