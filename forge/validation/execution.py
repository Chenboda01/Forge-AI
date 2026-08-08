from __future__ import annotations

import os
import selectors
import shutil
import signal
import subprocess
from collections.abc import Callable
from pathlib import Path
from time import monotonic
from typing import Final

from forge.forge_core.workspace import Workspace, WorkspaceError

from .models import (
    CommandClassification,
    CommandExecutionError,
    CommandExecutionResult,
    CommandPolicyError,
    CommandRequest,
    NetworkPolicy,
)

type Validator = Callable[[tuple[str, ...], Path], None]

EXACT_COMMANDS: Final = frozenset(
    {
        ("pyright",),
        ("ruff", "check", "."),
        ("ruff", "format", "--check", "."),
        ("cargo", "test"),
        ("cargo", "clippy"),
        ("cargo", "fmt", "--check"),
        ("npm", "test"),
        ("npm", "run", "lint"),
        ("npm", "run", "typecheck"),
        ("pnpm", "run", "test"),
        ("pnpm", "run", "lint"),
        ("pnpm", "run", "typecheck"),
        ("yarn", "run", "test"),
        ("yarn", "run", "lint"),
        ("yarn", "run", "typecheck"),
        ("bun", "run", "test"),
        ("bun", "run", "lint"),
        ("bun", "run", "typecheck"),
    }
)


def classify_command(arguments: tuple[str, ...], root: Path) -> CommandClassification:
    if not arguments:
        raise CommandPolicyError("Command argument array is empty.")
    if arguments in EXACT_COMMANDS:
        return CommandClassification.APPROVAL_REQUIRED
    if arguments[0] == "pytest":
        _validate_pytest(arguments, root)
        return CommandClassification.APPROVAL_REQUIRED
    raise CommandPolicyError(f"Command executable or arguments are not permitted: {arguments[0]}")


def _validate_pytest(arguments: tuple[str, ...], root: Path) -> None:
    if len(arguments) == 1:
        return
    if len(arguments) != 2 or arguments[1].startswith("-"):
        raise CommandPolicyError("Pytest arguments are not permitted.")
    try:
        target = Workspace(root).resolve(arguments[1])
    except WorkspaceError as error:
        raise CommandPolicyError(
            f"Pytest target is outside the workspace: {arguments[1]}"
        ) from error
    if not target.is_file() or target.suffix != ".py":
        raise CommandPolicyError(f"Pytest target is not a Python file: {arguments[1]}")


class RestrictedCommandRunner:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.runtime_home = self.root / ".forge" / "runtime-home"
        self.runtime_home.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.runtime_home.chmod(0o700)

    def run(self, request: CommandRequest) -> CommandExecutionResult:
        classification = classify_command(request.arguments, self.root)
        executable = self._resolve_executable(request.arguments[0])
        unshare = shutil.which("unshare")
        if unshare is None:
            raise CommandExecutionError("Network-isolated command execution requires unshare.")
        command = (
            unshare,
            "--user",
            "--map-root-user",
            "--net",
            "--",
            executable,
            *request.arguments[1:],
        )
        started = monotonic()
        try:
            process = subprocess.Popen(
                command,
                cwd=self.root,
                env=self._environment(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as error:
            raise CommandExecutionError(f"Could not start command: {error}") from error
        output, output_bytes, timed_out = self._capture(process, request)
        exit_code = process.wait()
        duration = monotonic() - started
        return CommandExecutionResult(
            arguments=request.arguments,
            classification=classification,
            network_policy=NetworkPolicy.DENIED,
            exit_code=exit_code,
            output=output,
            output_bytes=output_bytes,
            truncated=output_bytes > request.output_limit_bytes,
            timed_out=timed_out,
            passed=exit_code == 0 and not timed_out,
            duration_seconds=duration,
        )

    def _capture(
        self,
        process: subprocess.Popen[bytes],
        request: CommandRequest,
    ) -> tuple[str, int, bool]:
        stdout = process.stdout
        assert stdout is not None
        selector = selectors.DefaultSelector()
        selector.register(stdout, selectors.EVENT_READ)
        deadline = monotonic() + request.timeout_seconds
        retained = bytearray()
        output_bytes = 0
        timed_out = False
        stream_open = True
        while stream_open:
            remaining = deadline - monotonic()
            if remaining <= 0 and process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                timed_out = True
            events = selector.select(timeout=max(min(remaining, 0.05), 0))
            for key, _mask in events:
                chunk = os.read(key.fd, 8192)
                if not chunk:
                    selector.unregister(stdout)
                    stream_open = False
                    break
                output_bytes += len(chunk)
                available = request.output_limit_bytes - len(retained)
                if available > 0:
                    retained.extend(chunk[:available])
            if process.poll() is not None and not events:
                chunk = os.read(stdout.fileno(), 8192)
                if chunk:
                    output_bytes += len(chunk)
                    available = request.output_limit_bytes - len(retained)
                    if available > 0:
                        retained.extend(chunk[:available])
                else:
                    stream_open = False
        selector.close()
        return retained.decode("utf-8", errors="ignore"), output_bytes, timed_out

    def _resolve_executable(self, name: str) -> str:
        local = self.root / ".venv" / "bin" / name
        if local.is_file():
            return str(local)
        executable = shutil.which(name)
        if executable is None:
            raise CommandExecutionError(f"Command not found: {name}")
        return executable

    def _environment(self) -> dict[str, str]:
        cache = self.runtime_home / "cache"
        cache.mkdir(exist_ok=True, mode=0o700)
        return {
            "HOME": str(self.runtime_home),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "NO_COLOR": "1",
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "PYTHONNOUSERSITE": "1",
            "XDG_CACHE_HOME": str(cache),
        }
