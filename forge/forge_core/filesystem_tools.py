from __future__ import annotations

import subprocess
from typing import Final

from .tools import Tool, ToolError, ToolRegistry
from .workspace import Workspace

IGNORED_PARTS: Final = frozenset({".git", ".venv", "__pycache__", "node_modules", ".forge"})


def register_filesystem_tools(registry: ToolRegistry, workspace: Workspace) -> None:
    def list_files(path: str = ".", recursive: bool = False) -> str:
        directory = workspace.resolve(path)
        if not directory.exists():
            raise ToolError(f"Path does not exist: {path}")
        if not directory.is_dir():
            raise ToolError(f"Not a directory: {path}")

        if recursive:
            paths = [
                item
                for item in directory.rglob("*")
                if not any(part in IGNORED_PARTS for part in item.parts)
            ]
        else:
            paths = [item for item in directory.iterdir() if item.name not in IGNORED_PARTS]

        lines: list[str] = []
        for item in sorted(paths):
            relative = item.relative_to(workspace.root)
            lines.append(f"{relative}/" if item.is_dir() else str(relative))
        return "\n".join(lines) or "Directory is empty."

    def read_file(path: str, start_line: int = 1, end_line: int | None = None) -> str:
        file_path = workspace.resolve(path)
        if not file_path.exists():
            raise ToolError(f"File does not exist: {path}")
        if not file_path.is_file():
            raise ToolError(f"Not a file: {path}")
        if file_path.stat().st_size > 1_000_000:
            raise ToolError("File is larger than 1 MB.")

        try:
            lines = file_path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError as error:
            raise ToolError("Forge cannot read this binary file.") from error

        start = max(start_line - 1, 0)
        stop = end_line if end_line is not None else len(lines)
        selected = lines[start:stop]
        numbered = [
            f"{line_number:4} | {line}"
            for line_number, line in enumerate(selected, start=start + 1)
        ]
        return "\n".join(numbered) or "No content in this range."

    def search_files(query: str, path: str = ".") -> str:
        directory = workspace.resolve(path)
        if not directory.exists():
            raise ToolError(f"Path does not exist: {path}")

        command = [
            "rg",
            "--line-number",
            "--hidden",
            "--glob",
            "!.git/**",
            "--glob",
            "!.venv/**",
            "--glob",
            "!node_modules/**",
            "--glob",
            "!.forge/**",
            query,
            str(directory),
        ]
        try:
            result = subprocess.run(
                command,
                cwd=workspace.root,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except FileNotFoundError as error:
            raise ToolError(
                "ripgrep is not installed. Install it with your package manager."
            ) from error

        if result.returncode == 1:
            return "No matches found."
        if result.returncode != 0:
            raise ToolError(result.stderr.strip())
        return result.stdout.strip()[:30_000]

    def write_file(path: str, content: str) -> str:
        file_path = workspace.resolve(path)
        if len(content.encode("utf-8")) > 1_000_000:
            raise ToolError("File content exceeds 1 MB limit.")

        file_path.parent.mkdir(parents=True, exist_ok=True)
        existed_before = file_path.exists()
        file_path.write_text(content, encoding="utf-8")
        action = "Updated" if existed_before else "Created"
        relative = file_path.relative_to(workspace.root)
        return f"{action} {relative}"

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
        )
    )
    registry.register(
        Tool(
            name="write_file",
            description=(
                "Create or completely replace a text file. "
                "Use only after examining relevant existing files."
            ),
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
                "additionalProperties": False,
            },
            handler=write_file,
            requires_approval=True,
        )
    )
