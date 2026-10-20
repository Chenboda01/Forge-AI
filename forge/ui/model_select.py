from __future__ import annotations

from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from forge.forge_core.config import get_api_key
from forge.forge_core.models import MODELS, ModelConfig


class ModelSelectScreen(ModalScreen[str]):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False, priority=True),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="model-dialog"):
            yield Static("Select model", id="model-title")
            yield Static("type to filter · ↑↓ enter · esc to cancel", id="model-subtitle")
            yield Input(placeholder="Filter models", id="model-filter")
            yield OptionList(id="model-options")

    def on_mount(self) -> None:
        self._populate("")
        self.query_one("#model-filter", Input).focus()

    @on(Input.Changed, "#model-filter")
    def filter_models(self, event: Input.Changed) -> None:
        self._populate(event.value)

    @on(OptionList.OptionSelected, "#model-options")
    def select_model(self, event: OptionList.OptionSelected) -> None:
        if event.option_id is not None:
            self.dismiss(event.option_id)

    async def on_key(self, event: events.Key) -> None:
        options = self.query_one("#model-options", OptionList)
        filter_input = self.query_one("#model-filter", Input)
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
        options = self.query_one("#model-options", OptionList)
        options.clear_options()
        needle = query.strip().lower()
        for alias, model in MODELS.items():
            haystack = f"{alias} {model.name} {model.provider} {model.model_id}".lower()
            if needle and needle not in haystack:
                continue
            options.add_option(Option(self._label(alias, model), id=alias))

    @staticmethod
    def _label(alias: str, model: ModelConfig) -> str:
        if model.requires_key is None:
            status = "local"
        elif get_api_key(model.requires_key) is not None:
            status = "ready"
        else:
            status = f"needs {model.requires_key}"
        return f"{alias:<16} {model.provider:<16} {status}"
