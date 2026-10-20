from collections.abc import Iterable

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import ProgressBar, Static

from forge.ui.state import ForgeRuntime, estimate_cost

STARTUP_PHASES = [
    "INITIALIZING CORE",
    "SCANNING WORKSPACE",
    "LOADING TOOLCHAIN",
    "FORGE ONLINE",
]

FORGE_LOGO = (
    "███████╗ ██████╗ ██████╗  ██████╗ ███████╗\n"
    "██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝\n"
    "█████╗  ██║   ██║██████╔╝██║  ███╗█████╗  \n"
    "██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝  \n"
    "██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗\n"
    "╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝"
)

MESSAGE_PREFIXES = {
    "user": "› ",
    "tool": "· ",
    "notice": "· ",
    "error": "✗ ",
}


class StartupBar(Vertical):
    def __init__(self) -> None:
        super().__init__(id="startup-overlay")

    def compose(self) -> ComposeResult:
        yield Static(FORGE_LOGO, id="startup-logo")
        yield Static("", id="startup-spacer")
        yield Static("◇ INITIALIZING", id="startup-phase")
        yield Static("\u2591" * 30, id="startup-progress")

    def set_phase(self, phase_idx: int, label: str) -> None:
        total = len(STARTUP_PHASES)
        filled = int(phase_idx / total * 30)
        bar = "\u2588" * filled + "\u2591" * (30 - filled)
        self.query_one("#startup-phase", Static).update(f"\u25c7 {label}")
        self.query_one("#startup-progress", Static).update(bar)


class EftBanner(Static):
    def __init__(self) -> None:
        super().__init__("EFT: Waiting", id="eft-banner")

    def set_text(self, text: str) -> None:
        self.update(f"EFT: {text}")


class HeaderBar(Horizontal):
    """Full-width top chrome: wordmark, session, and active mode/model."""

    def __init__(self) -> None:
        super().__init__(id="header")

    def compose(self) -> ComposeResult:
        yield Static(id="header-left")
        yield Static(id="header-right")

    def update_status(self, runtime: ForgeRuntime | None, session_name: str) -> None:
        if runtime is None:
            mode = "offline"
            model = "offline"
            context = 0.0
            directory = ""
        else:
            mode = runtime.agent.mode.value
            model = runtime.agent.model_id.rsplit("/", maxsplit=1)[-1]
            context = runtime.agent.context_pct
            directory = runtime.workspace.name or str(runtime.workspace)

        label = session_name or "untitled"
        if directory:
            label = f"{label} \u00b7 {directory}"
        wordmark = Text()
        wordmark.append("\u25c6 FORGE", style="bold")
        wordmark.append(f"   {label}")
        self.query_one("#header-left", Static).update(wordmark)
        self.query_one("#header-right", Static).update(
            f"{mode} \u00b7 {model} \u00b7 ctx {context:.0f}%"
        )


class FooterBar(Horizontal):
    """Full-width bottom hint bar: keybindings and session usage."""

    def __init__(self) -> None:
        super().__init__(id="footer")

    def compose(self) -> ComposeResult:
        yield Static(
            "enter send \u00b7 shift+enter newline \u00b7 \u2191\u2193 history "
            "\u00b7 /help commands \u00b7 ctrl+q quit",
            id="footer-left",
        )
        yield Static(id="footer-right")

    def update_status(self, runtime: ForgeRuntime | None) -> None:
        if runtime is None:
            self.query_one("#footer-right", Static).update("offline")
            return
        cost = estimate_cost(runtime.agent)
        cost_text = "cost unavailable" if cost is None else f"${cost:.4f}"
        self.query_one("#footer-right", Static).update(
            f"{runtime.agent.total_tokens:,} tokens \u00b7 {cost_text}"
        )


class ActivityProgress(Horizontal):
    """Fixed textual and numeric progress state for active Forge work."""

    def __init__(self) -> None:
        super().__init__(id="activity-row")

    def compose(self) -> ComposeResult:
        yield Static("Ready", id="activity-label")
        yield ProgressBar(
            total=None,
            show_eta=False,
            show_percentage=False,
            id="agent-progress",
        )

    def set_working(self, label: str) -> None:
        self.query_one("#activity-label", Static).update(label)
        self.query_one("#agent-progress", ProgressBar).update(total=None, progress=0)

    def set_phase(self, label: str) -> None:
        self.query_one("#activity-label", Static).update(label)

    def set_done(self) -> None:
        self.query_one("#activity-label", Static).update("Done")
        self.query_one("#agent-progress", ProgressBar).update(total=1, progress=1)


class ConversationView(VerticalScroll):
    """Scrollable chronological record of user, Forge, and tool activity."""

    def __init__(self) -> None:
        super().__init__(id="conversation")
        self._transcript: list[str] = []

    @property
    def transcript(self) -> str:
        return "\n".join(self._transcript)

    async def append_entry(self, label: str, body: str, kind: str = "notice") -> None:
        self._transcript.append(f"{label}\n{body}")
        text = Text()
        text.append(MESSAGE_PREFIXES.get(kind, ""))
        text.append(label, style="bold")
        text.append("\n")
        text.append(body)
        await self.mount(Static(text, classes=f"message message-{kind}"))
        self.scroll_end(animate=False)

    async def reset(self) -> None:
        await self.remove_children()
        self._transcript.clear()


class StatusRail(Vertical):
    """Fixed full-height operational context for the current Forge session."""

    def compose(self) -> ComposeResult:
        yield Static(id="sidebar-content")
        yield Static(id="sidebar-spacer")
        yield Static(id="sidebar-footer")

    def update_status(
        self,
        runtime: ForgeRuntime | None,
        session_name: str,
        eft_text: str = "",
    ) -> None:
        if runtime is None:
            model = "offline"
            tokens = 0
            context = 0.0
            cost = None
            directory = "not connected"
            version = "development"
        else:
            model = runtime.agent.model_id.rsplit("/", maxsplit=1)[-1]
            tokens = runtime.agent.context_tokens
            context = runtime.agent.context_pct
            cost = estimate_cost(runtime.agent)
            directory = str(runtime.workspace)
            version = runtime.version

        filled = min(int(context / 10), 10)
        bar = "#" * filled + "-" * (10 - filled)
        cost_text = "Unavailable" if cost is None else f"${cost:.4f}"
        sections: Iterable[str] = (
            "FORGE",
            "",
            "Session",
            session_name or "Untitled",
            "",
            "EFT",
            eft_text or "Waiting",
            "",
            "Context",
            f"{tokens:,} tokens",
            f"[{bar}] {context:.0f}%",
            "",
            "Cost",
            cost_text,
            "",
            "MCP",
            "No servers",
            "",
            "Todo",
            "No active tasks",
            "",
            "Model",
            model,
        )
        self.query_one("#sidebar-content", Static).update("\n".join(sections))
        self.query_one("#sidebar-footer", Static).update(f"{directory}\nforge v{version}")
