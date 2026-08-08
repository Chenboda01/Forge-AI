from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from .themes import THEMES

_NAMES = list(THEMES)


class ThemeSelectScreen(ModalScreen[str]):
    BINDINGS = [
        Binding("up", "focus_previous", "Up", show=False, priority=True),
        Binding("down", "focus_next", "Down", show=False, priority=True),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="theme-dialog"):
            yield Static("Select theme", id="theme-title")
            yield Static("↑↓ enter · esc to cancel", id="theme-subtitle")
            for name in _NAMES:
                yield Button(f" {name} ", id=f"theme-{name}", variant="default")

    def on_mount(self) -> None:
        self.query_one("#theme-ember", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id is not None:
            self.dismiss(button_id.removeprefix("theme-"))

    def action_focus_previous(self) -> None:
        self._move(-1)

    def action_focus_next(self) -> None:
        self._move(1)

    def _move(self, delta: int) -> None:
        focused = self.focused
        ids = [f"theme-{n}" for n in _NAMES]
        idx = ids.index(focused.id) if focused is not None and focused.id in ids else 0
        new_idx = (idx + delta) % len(ids)
        self.query_one(f"#{ids[new_idx]}", Button).focus()
