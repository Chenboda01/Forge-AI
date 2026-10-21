from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Callable, Sequence
from threading import Condition, Thread, current_thread

from .presenter import AgentLifecycle

HERDR_SOURCE = "forge"
HERDR_AGENT = "forge"
REPORT_TIMEOUT_SECONDS = 1.5

CommandRunner = Callable[[Sequence[str]], None]


def _run_command(command: Sequence[str]) -> None:
    subprocess.run(
        list(command),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=REPORT_TIMEOUT_SECONDS,
        check=False,
    )


class HerdrReporter(AgentLifecycle):
    """Best-effort lifecycle reporter for a Forge process running inside Herdr."""

    def __init__(
        self,
        bin_path: str,
        pane_id: str,
        *,
        source: str = HERDR_SOURCE,
        agent: str = HERDR_AGENT,
        runner: CommandRunner | None = None,
    ) -> None:
        self._bin_path = bin_path
        self._pane_id = pane_id
        self._source = source
        self._agent = agent
        self._runner = runner or _run_command
        self._condition = Condition()
        self._pending: tuple[str, str | None, int] | None = None
        self._worker: Thread | None = None
        self._closed = False
        self._active_turns = 0
        self._last_seq = time.time_ns()

    @classmethod
    def from_environment(cls) -> HerdrReporter | None:
        """Return a reporter only inside a Herdr pane; otherwise do nothing."""
        if os.environ.get("HERDR_ENV") != "1":
            return None
        pane_id = os.environ.get("HERDR_PANE_ID")
        if not pane_id:
            return None
        bin_path = os.environ.get("HERDR_BIN_PATH") or shutil.which("herdr")
        if not bin_path:
            return None
        return cls(bin_path, pane_id)

    @property
    def pane_id(self) -> str:
        return self._pane_id

    def report_idle(self) -> None:
        """Publish the ready state when Forge starts, before the first turn."""
        with self._condition:
            if self._closed or self._active_turns > 0:
                return
            self._queue_locked("idle", None)

    def turn_started(self) -> None:
        with self._condition:
            if self._closed:
                return
            self._active_turns += 1
            if self._active_turns == 1:
                self._queue_locked("working", None)

    def waiting_for_approval(self, tool_name: str) -> None:
        with self._condition:
            if self._closed or self._active_turns == 0:
                return
            self._queue_locked("blocked", f"Waiting for approval: {tool_name}")

    def approval_resolved(self) -> None:
        with self._condition:
            if self._closed or self._active_turns == 0:
                return
            self._queue_locked("working", None)

    def turn_finished(self) -> None:
        with self._condition:
            if self._closed or self._active_turns == 0:
                return
            self._active_turns -= 1
            if self._active_turns == 0:
                self._queue_locked("idle", None)

    def release(self) -> None:
        """Clear Forge's agent state from the pane when the process exits."""
        with self._condition:
            if self._closed:
                return
            self._closed = True
            self._pending = None
            self._condition.notify_all()
            worker = self._worker
        if worker is not None and worker is not current_thread():
            worker.join(timeout=REPORT_TIMEOUT_SECONDS)
        with self._condition:
            seq = self._next_seq_locked()
        self._send(
            [
                self._bin_path,
                "pane",
                "release-agent",
                self._pane_id,
                "--source",
                self._source,
                "--agent",
                self._agent,
                "--seq",
                str(seq),
            ]
        )

    def _queue_locked(self, state: str, message: str | None) -> None:
        self._pending = (state, message, self._next_seq_locked())
        if self._worker is None:
            self._worker = Thread(target=self._drain, name="forge-herdr", daemon=True)
            self._worker.start()
        else:
            self._condition.notify()

    def _next_seq_locked(self) -> int:
        seq = time.time_ns()
        if seq <= self._last_seq:
            seq = self._last_seq + 1
        self._last_seq = seq
        return seq

    def _drain(self) -> None:
        while True:
            with self._condition:
                while self._pending is None and not self._closed:
                    self._condition.wait()
                if self._pending is None:
                    self._worker = None
                    return
                state, message, seq = self._pending
                self._pending = None
            command = [
                self._bin_path,
                "pane",
                "report-agent",
                self._pane_id,
                "--source",
                self._source,
                "--agent",
                self._agent,
                "--state",
                state,
                "--seq",
                str(seq),
            ]
            if message:
                command.extend(("--message", message))
            self._send(command)
            with self._condition:
                if self._pending is None:
                    self._worker = None
                    return

    def _send(self, command: list[str]) -> None:
        try:
            self._runner(command)
        except (OSError, subprocess.SubprocessError, ValueError):
            return None
