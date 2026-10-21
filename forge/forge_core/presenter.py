from typing import Protocol


class AgentLifecycle(Protocol):
    """Observability boundary for the deterministic agent turn lifecycle."""

    def turn_started(self) -> None: ...

    def waiting_for_approval(self, tool_name: str) -> None: ...

    def approval_resolved(self) -> None: ...

    def turn_finished(self) -> None: ...


class NullLifecycle:
    """Lifecycle adapter used when no external observer is present."""

    def turn_started(self) -> None:
        return None

    def waiting_for_approval(self, tool_name: str) -> None:
        return None

    def approval_resolved(self) -> None:
        return None

    def turn_finished(self) -> None:
        return None


class AgentPresenter(Protocol):
    """Trusted output and approval boundary used by the agent loop."""

    def step_started(self, step: int, maximum: int) -> None: ...

    def tool_started(self, name: str, arguments: str) -> None: ...

    def request_approval(self, name: str, arguments: str) -> bool: ...

    def tool_completed(self, name: str, result: str) -> None: ...

    def context_reduced(self, tokens_before: int, tokens_after: int) -> None: ...

    def response_completed(self, content: str) -> None: ...


class SilentPresenter:
    """Safe non-interactive presenter that denies privileged actions."""

    def step_started(self, step: int, maximum: int) -> None:
        return None

    def tool_started(self, name: str, arguments: str) -> None:
        return None

    def request_approval(self, name: str, arguments: str) -> bool:
        return False

    def tool_completed(self, name: str, result: str) -> None:
        return None

    def context_reduced(self, tokens_before: int, tokens_after: int) -> None:
        return None

    def response_completed(self, content: str) -> None:
        return None
