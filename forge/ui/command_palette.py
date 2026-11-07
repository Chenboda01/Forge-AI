from __future__ import annotations

from dataclasses import dataclass

from rich.text import Text
from textual.widgets import OptionList
from textual.widgets.option_list import Option

COMMAND_COLORS: tuple[str, ...] = (
    "dark_orange",
    "hot_pink",
    "spring_green3",
    "green_yellow",
    "magenta",
    "red1",
    "grey62",
)


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


class CommandSuggest(OptionList):
    """Inline command suggestions shown directly above the composer."""

    DEFAULT_CSS = """
    CommandSuggest {
        display: none;
        width: 100%;
        height: auto;
        max-height: 8;
        padding: 0 1;
        border: round $accent-primary;
        background: $surface-elevated;
    }
    """

    def update_query(self, query: str) -> bool:
        raw = query.lstrip("/").lower()
        needle = raw.strip()
        self.clear_options()
        if any(character.isspace() for character in raw):
            self.display = False
            return False
        matches = [
            spec
            for spec in COMMANDS
            if not needle or spec.name.lstrip("/").lower().startswith(needle)
        ]
        for spec in matches:
            color = COMMAND_COLORS[COMMANDS.index(spec) % len(COMMAND_COLORS)]
            prompt = Text(spec.name, style=f"bold {color}")
            prompt.append("  ")
            prompt.append(spec.description, style="dim")
            self.add_option(Option(prompt, id=spec.name))
        self.display = bool(matches)
        if matches:
            self.highlighted = 0
        return bool(matches)

    def selected_command(self) -> str | None:
        if self.highlighted is None:
            return None
        option = self.get_option_at_index(self.highlighted)
        return option.id
