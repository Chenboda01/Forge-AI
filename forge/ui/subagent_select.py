from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Checkbox, Input, OptionList, Static
from textual.widgets.option_list import Option

from forge.forge_core.subagents import SUBAGENTS
from forge.ui.subagent_session import SubagentSession


class SubagentSelectScreen(ModalScreen[tuple[str, str] | None]):
    """Browse session-scoped subagents and optionally talk to one."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False, priority=True),
        Binding("left", "previous_agent", "Previous", show=False),
        Binding("right", "next_agent", "Next", show=False),
        Binding("t", "toggle_talk", "Talk", show=False),
    ]

    def __init__(self, session: SubagentSession | None = None) -> None:
        super().__init__()
        self.session = session or SubagentSession()
        self._current = next(iter(SUBAGENTS), "")

    def compose(self) -> ComposeResult:
        with Vertical(id="agents-dialog"):
            yield Static(
                f"Subagents · session {self.session.generation}",
                id="agents-title",
            )
            yield Static(
                "←→ switch · ↑↓ inspect · t talk · enter message · esc close",
                id="agents-subtitle",
            )
            with Horizontal(id="agents-body"):
                yield OptionList(id="agents-options")
                yield Static(id="agents-detail")
            with Horizontal(id="agents-talk-row"):
                yield Checkbox("Talk to this agent", id="agents-talk")
                yield Static("off · space or t toggles", id="agents-talk-hint")
            with Vertical(id="agents-prompt-box"):
                yield Static("MESSAGE", id="agents-prompt-label")
                yield Input(
                    placeholder="Type a message, then press Enter",
                    id="agents-prompt",
                )

    def on_mount(self) -> None:
        options = self.query_one("#agents-options", OptionList)
        for name, spec in SUBAGENTS.items():
            state = self.session.state(name)
            options.add_option(
                Option(f"{name:<10} {state.status:<8} {spec.max_steps} steps", id=name)
            )
        options.focus()
        options.action_first()
        if self._current:
            self._show_detail(self._current)
        self.query_one("#agents-prompt-box", Vertical).display = False

    @on(OptionList.OptionHighlighted, "#agents-options")
    def show_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_id is not None:
            self._current = event.option_id
            self._show_detail(event.option_id)

    @on(OptionList.OptionSelected, "#agents-options")
    def select_agent(self, event: OptionList.OptionSelected) -> None:
        if event.option_id is not None:
            self._activate(event.option_id)

    @on(Checkbox.Changed, "#agents-talk")
    def toggle_talk(self, event: Checkbox.Changed) -> None:
        prompt = self.query_one("#agents-prompt", Input)
        box = self.query_one("#agents-prompt-box", Vertical)
        hint = self.query_one("#agents-talk-hint", Static)
        if event.value:
            box.display = True
            hint.update("on · type below, Enter sends")
            prompt.focus()
            return
        prompt.value = ""
        hint.update("off · space or t toggles")
        self.query_one("#agents-options", OptionList).focus()
        box.display = False

    @on(Input.Submitted, "#agents-prompt")
    def submit_prompt(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if text and self._current:
            self.dismiss((self._current, text))

    def action_previous_agent(self) -> None:
        options = self.query_one("#agents-options", OptionList)
        options.focus()
        options.action_cursor_up()

    def action_next_agent(self) -> None:
        options = self.query_one("#agents-options", OptionList)
        options.focus()
        options.action_cursor_down()

    def action_toggle_talk(self) -> None:
        if isinstance(self.focused, Input):
            return
        talk = self.query_one("#agents-talk", Checkbox)
        talk.value = not talk.value

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _activate(self, name: str) -> None:
        talk = self.query_one("#agents-talk", Checkbox)
        if not talk.value:
            talk.value = True
            return
        prompt = self.query_one("#agents-prompt", Input)
        text = prompt.value.strip()
        if not text:
            prompt.focus()
            return
        self.dismiss((name, text))

    def _show_detail(self, name: str) -> None:
        spec = SUBAGENTS.get(name)
        if spec is None:
            return
        state = self.session.state(name)
        tools = "\n".join(f"  · {tool}" for tool in spec.allowed_tools)
        report = state.last_report.strip() or "None yet."
        detail = "\n".join(
            (
                spec.name.upper(),
                "",
                spec.description,
                "",
                "Status",
                f"  {state.status}",
                f"  {state.runs} run(s) this session",
                "",
                "Task",
                f"  {state.objective or 'None yet.'}",
                "",
                "Current tool",
                f"  {state.current_tool or ('Thinking' if state.status == 'working' else 'None')}",
                "",
                "Tools",
                tools,
                "",
                "Step limit",
                f"  {spec.max_steps}",
                "",
                "Last report",
                report,
                "",
                "Invoke",
                f"  /agent {spec.name} OBJECTIVE",
                f"  @{spec.name} OBJECTIVE",
            )
        )
        self.query_one("#agents-detail", Static).update(detail)
        self.query_one("#agents-prompt-label", Static).update(f"MESSAGE {spec.name.upper()}")
