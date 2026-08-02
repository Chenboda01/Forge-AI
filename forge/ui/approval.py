from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ApprovalScreen(ModalScreen[bool]):
    """Trusted modal for one exact approval-required tool request."""

    def __init__(self, tool_name: str, arguments: str) -> None:
        super().__init__()
        self.tool_name = tool_name
        self.arguments = arguments

    def compose(self) -> ComposeResult:
        with Vertical(id="approval-dialog"):
            yield Static("Approval required", id="approval-title")
            yield Static(f"Tool: {self.tool_name}\n\n{self.arguments}", id="approval-body")
            with Horizontal(id="approval-actions"):
                yield Button("Deny", id="deny", variant="error")
                yield Button("Approve once", id="approve", variant="success")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "approve")
