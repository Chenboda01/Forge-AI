from collections.abc import Callable
from time import monotonic
from typing import TYPE_CHECKING, Final

from forge.ui.widgets import ActivityProgress

if TYPE_CHECKING:
    from forge.ui.app import ForgeApp

ESCAPE_SEQUENCE_SECONDS: Final = 1.25


class KeyboardController:
    __slots__ = (
        "_draft",
        "_clock",
        "_escape_count",
        "_escape_started_at",
        "_history",
        "_history_index",
    )

    def __init__(self, clock: Callable[[], float] = monotonic) -> None:
        self._clock = clock
        self._history: list[str] = []
        self._history_index: int | None = None
        self._draft = ""
        self._escape_count = 0
        self._escape_started_at = 0.0

    def remember(self, value: str) -> None:
        self._history.append(value)
        self._history_index = None
        self._draft = ""

    def previous(self, current: str) -> str | None:
        if not self._history:
            return None
        if self._history_index is None:
            self._draft = current
            self._history_index = len(self._history) - 1
        elif self._history_index > 0:
            self._history_index -= 1
        return self._history[self._history_index]

    def next(self) -> str | None:
        if self._history_index is None:
            return None
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            return self._history[self._history_index]
        self._history_index = None
        return self._draft

    def record_escape(self) -> int:
        now = self._clock()
        if self._escape_count == 0 or now - self._escape_started_at > ESCAPE_SEQUENCE_SECONDS:
            self._escape_count = 0
            self._escape_started_at = now
        self._escape_count += 1
        return self._escape_count

    def reset_escape(self) -> None:
        self._escape_count = 0
        self._escape_started_at = 0.0


async def request_interrupt(app: ForgeApp) -> None:
    if not app._busy:
        return
    runtime = app.runtime
    if runtime is not None:
        runtime.agent.cancel()
        runtime.subagents.cancel()
    if app._approval_decision is not None:
        app._approval_decision.set()
        if len(app.screen_stack) > 1:
            app.pop_screen()
    app.query_one("#activity-row", ActivityProgress).set_phase("Stopping")
    await app._append_entry(
        "SYSTEM",
        "Interrupt requested. Waiting for the current operation to stop safely.",
        "notice",
    )
