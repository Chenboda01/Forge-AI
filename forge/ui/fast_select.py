from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

_VARIANTS: list[tuple[str, int, str]] = [
    ("low", 50, "Most precise — 50 steps"),
    ("mid", 35, "Balanced — 35 steps"),
    ("high", 20, "Fast — 20 steps"),
    ("xhigh", 10, "Extra fast — 10 steps"),
    ("max", 5, "Maximum speed — 5 steps"),
]

_IDS = [f"fast-{v[0]}" for v in _VARIANTS]


class FastSelectScreen(ModalScreen[str]):
    BINDINGS = [
        Binding("up", "focus_previous", "Up", show=False, priority=True),
        Binding("down", "focus_next", "Down", show=False, priority=True),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="fast-dialog"):
            yield Static("Select speed", id="fast-title")
            yield Static("↑↓ enter · esc to cancel", id="fast-subtitle")
            for variant, _steps, desc in _VARIANTS:
                yield Button(f"{variant:<6} {desc}", id=f"fast-{variant}", variant="default")

    def on_mount(self) -> None:
        self.query_one(f"#{_IDS[2]}", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id is not None:
            self.dismiss(button_id.removeprefix("fast-"))

    def action_focus_previous(self) -> None:
        self._move(-1)

    def action_focus_next(self) -> None:
        self._move(1)

    def _move(self, delta: int) -> None:
        focused = self.focused
        idx = _IDS.index(focused.id) if focused is not None and focused.id in _IDS else 0
        new_idx = (idx + delta) % len(_IDS)
        self.query_one(f"#{_IDS[new_idx]}", Button).focus()
