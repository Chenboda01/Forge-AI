from __future__ import annotations

from dataclasses import dataclass

from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option


@dataclass(frozen=True, slots=True)
class CommandSpec:
    name: str
    description: str


COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec("/help", "Show the command list"),
    CommandSpec("/status", "Show provider, model, mode, and workspace"),
    CommandSpec("/usage", "Show token usage and estimated cost"),
    CommandSpec("/settings", "Show saved preferences and storage location"),
    CommandSpec("/models", "Open the model picker"),
    CommandSpec("/model", "Choose or switch the active model"),
    CommandSpec("/files", "List workspace files"),
    CommandSpec("/read", "Read a workspace file"),
    CommandSpec("/tree", "List workspace files recursively"),
    CommandSpec("/new", "Start a new conversation"),
    CommandSpec("/save", "Save the current conversation"),
    CommandSpec("/sessions", "List saved sessions"),
    CommandSpec("/resume", "Resume a saved session"),
    CommandSpec("/history", "Show conversation history"),
    CommandSpec("/agents", "Browse subagents and inspect their tools"),
    CommandSpec("/agent", "Delegate an objective to a subagent"),
    CommandSpec("/checkpoints", "List all patch checkpoints"),
    CommandSpec("/checkpoint", "Alias for /checkpoints"),
    CommandSpec("/undo", "Undo a checkpoint"),
    CommandSpec("/recovery", "Show recovery state"),
    CommandSpec("/recover", "Run a recovery action"),
    CommandSpec("/force-stop", "Stop Forge and decide what to revert"),
    CommandSpec("/updates", "Check for updates"),
    CommandSpec("/compact", "Reduce conversation context"),
    CommandSpec("/queue", "List or clear queued messages"),
    CommandSpec("/asn", "Estimate the steps a task needs"),
    CommandSpec("/fast", "Select a speed profile"),
    CommandSpec("/theme", "Select a theme"),
    CommandSpec("/clear", "Clear the conversation display"),
    CommandSpec("/exit", "Exit Forge"),
)


class CommandPaletteScreen(ModalScreen[str]):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False, priority=True),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="palette-dialog"):
            yield Static("Commands", id="palette-title")
            yield Static("type to filter · ↑↓ enter · esc to cancel", id="palette-subtitle")
            yield Input(placeholder="Filter commands", id="palette-filter")
            yield OptionList(id="palette-options")

    def on_mount(self) -> None:
        self._populate("")
        self.query_one("#palette-filter", Input).focus()

    @on(Input.Changed, "#palette-filter")
    def filter_commands(self, event: Input.Changed) -> None:
        self._populate(event.value)

    @on(OptionList.OptionSelected, "#palette-options")
    def select_command(self, event: OptionList.OptionSelected) -> None:
        if event.option_id is not None:
            self.dismiss(event.option_id)

    async def on_key(self, event: events.Key) -> None:
        options = self.query_one("#palette-options", OptionList)
        filter_input = self.query_one("#palette-filter", Input)
        if event.key == "down" and filter_input.has_focus and options.option_count:
            event.prevent_default()
            event.stop()
            options.focus()
            options.action_first()
            return
        if (
            event.key == "up"
            and options.has_focus
            and options.option_count
            and options.highlighted_option is options.get_option_at_index(0)
        ):
            event.prevent_default()
            event.stop()
            filter_input.focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _populate(self, query: str) -> None:
        options = self.query_one("#palette-options", OptionList)
        options.clear_options()
        needle = query.strip().lower()
        for spec in COMMANDS:
            haystack = f"{spec.name} {spec.description}".lower()
            if needle and needle not in haystack:
                continue
            options.add_option(Option(f"{spec.name:<20} {spec.description}", id=spec.name))
