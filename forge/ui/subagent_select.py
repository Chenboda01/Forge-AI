from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from forge.forge_core.subagents import SUBAGENTS


class SubagentSelectScreen(ModalScreen[str]):
    """Browse registered read-only subagents, their tools, and limits."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False, priority=True),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="agents-dialog"):
            yield Static("Subagents", id="agents-title")
            yield Static(
                "↑↓ inspect · enter prepare delegation · esc to cancel",
                id="agents-subtitle",
            )
            with Horizontal(id="agents-body"):
                yield OptionList(id="agents-options")
                yield Static(id="agents-detail")

    def on_mount(self) -> None:
        options = self.query_one("#agents-options", OptionList)
        for name, spec in SUBAGENTS.items():
            options.add_option(Option(f"{name:<10} {spec.max_steps} steps", id=name))
        options.focus()
        options.action_first()
        first_name = next(iter(SUBAGENTS), "")
        if first_name:
            self._show_detail(first_name)

    @on(OptionList.OptionHighlighted, "#agents-options")
    def show_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_id is not None:
            self._show_detail(event.option_id)

    @on(OptionList.OptionSelected, "#agents-options")
    def select_agent(self, event: OptionList.OptionSelected) -> None:
        if event.option_id is not None:
            self.dismiss(event.option_id)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _show_detail(self, name: str) -> None:
        spec = SUBAGENTS.get(name)
        if spec is None:
            return
        tools = "\n".join(f"  · {tool}" for tool in spec.allowed_tools)
        detail = "\n".join(
            (
                spec.name.upper(),
                "",
                spec.description,
                "",
                "Tools",
                tools,
                "",
                "Step limit",
                f"  {spec.max_steps}",
                "",
                "Invoke",
                f"  /agent {spec.name} OBJECTIVE",
                f"  @{spec.name} OBJECTIVE",
            )
        )
        self.query_one("#agents-detail", Static).update(detail)
