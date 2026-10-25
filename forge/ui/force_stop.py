from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from forge.checkpoints import CheckpointError

if TYPE_CHECKING:
    from forge.checkpoints import CheckpointRecord

    from .state import ForgeRuntime

CHOICE_KEEP = "keep"
CHOICE_CURRENT = "current"
CHOICE_ALL = "all"

_OPTIONS: tuple[tuple[str, str], ...] = (
    (CHOICE_KEEP, "Keep changes"),
    (CHOICE_CURRENT, "Revert this edit"),
    (CHOICE_ALL, "Revert everything"),
)

_QUESTIONS: dict[str, str] = {
    CHOICE_KEEP: "Stop Forge and keep the changes already made?",
    CHOICE_CURRENT: "Stop Forge and revert only the edit in progress?",
    CHOICE_ALL: "Stop Forge and revert every change from this task?",
}

_DETAILS: dict[str, str] = {
    CHOICE_KEEP: "Every patch already applied during this task stays in the workspace.",
    CHOICE_CURRENT: (
        "Restores the newest patch checkpoint from this task. "
        "Earlier edits, including files changed before this one, stay untouched."
    ),
    CHOICE_ALL: (
        "Restores every patch checkpoint created during this task, newest first, "
        "returning files to how they were when the task started."
    ),
}


class ForceStopScreen(ModalScreen[str]):
    """Ask what to do with the work in flight before stopping Forge."""

    BINDINGS = [
        Binding("left", "focus_previous", "Left", show=False, priority=True),
        Binding("right", "focus_next", "Right", show=False, priority=True),
        Binding("escape", "cancel", "Cancel", show=False, priority=True),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="force-dialog"):
            yield Static("Force stop", id="force-title")
            yield Static("← → choose · enter confirm · esc cancel", id="force-subtitle")
            with Horizontal(id="force-options"):
                for choice, label in _OPTIONS:
                    yield Button(label, id=f"force-{choice}")
            yield Static(_QUESTIONS[CHOICE_KEEP], id="force-question")
            yield Static(_DETAILS[CHOICE_KEEP], id="force-detail")

    def on_mount(self) -> None:
        self._select(CHOICE_KEEP)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id is not None:
            self.dismiss(button_id.removeprefix("force-"))

    def action_focus_previous(self) -> None:
        self._move(-1)

    def action_focus_next(self) -> None:
        self._move(1)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _move(self, delta: int) -> None:
        focused = self.focused
        ids = [f"force-{choice}" for choice, _label in _OPTIONS]
        index = ids.index(focused.id) if focused is not None and focused.id in ids else 0
        self._select(_OPTIONS[(index + delta) % len(_OPTIONS)][0])

    def _select(self, choice: str) -> None:
        self.query_one(f"#force-{choice}", Button).focus()
        self.query_one("#force-question", Static).update(_QUESTIONS[choice])
        self.query_one("#force-detail", Static).update(_DETAILS[choice])


def checkpoint_baseline(runtime: ForgeRuntime | None) -> frozenset[str] | None:
    """Capture checkpoint IDs that existed before the current task started."""
    if runtime is None:
        return None
    checkpoints = getattr(runtime, "checkpoints", None)
    if checkpoints is None:
        return None
    try:
        return frozenset(record.id for record in checkpoints.list_checkpoints())
    except (CheckpointError, OSError):
        return None


def turn_checkpoints(
    runtime: ForgeRuntime,
    baseline: frozenset[str],
) -> tuple[CheckpointRecord, ...]:
    """Return checkpoints created after the task baseline, newest first."""
    return tuple(
        record for record in runtime.checkpoints.list_checkpoints() if record.id not in baseline
    )


def turn_checkpoint_ids(
    runtime: ForgeRuntime,
    baseline: frozenset[str],
) -> tuple[str, ...]:
    """Return IDs of checkpoints created after the task baseline, newest first."""
    return tuple(record.id for record in turn_checkpoints(runtime, baseline))


def revert_force_stop(
    runtime: ForgeRuntime | None,
    checkpoint_ids: tuple[str, ...] | None,
    choice: str,
) -> str:
    """Revert the selected scope after an interrupted task and describe the result."""
    if choice == CHOICE_KEEP:
        return "Force stop: Forge stopped; changes kept."
    if choice not in (CHOICE_CURRENT, CHOICE_ALL):
        raise ValueError(f"Unknown force-stop choice: {choice}")
    if runtime is None or checkpoint_ids is None:
        return "Force stop: checkpoint storage is unavailable; no changes were reverted."
    if not checkpoint_ids:
        return "Force stop: no edits were applied during this task, so there is nothing to revert."
    selected = checkpoint_ids[:1] if choice == CHOICE_CURRENT else checkpoint_ids
    restored: list[CheckpointRecord] = []
    try:
        for checkpoint_id in selected:
            restored.append(runtime.checkpoints.undo(checkpoint_id))
    except (CheckpointError, OSError) as error:
        return (
            f"Force stop: revert failed after {len(restored)} checkpoint(s): {error}. "
            "Run /checkpoints to inspect the remaining state."
        )
    files = len({file.path for record in restored for file in record.files})
    if choice == CHOICE_CURRENT:
        return (
            f"Force stop: reverted the current edit "
            f"({restored[0].id}, {files} file(s)). Earlier changes were kept."
        )
    return (
        f"Force stop: reverted {len(restored)} edit(s) from this task ({files} file(s) restored)."
    )
