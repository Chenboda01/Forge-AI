from __future__ import annotations

from dataclasses import dataclass

from forge.forge_core.subagents import SUBAGENTS


@dataclass(slots=True)
class SubagentState:
    status: str = "idle"
    runs: int = 0
    last_report: str = ""
    objective: str = ""
    current_tool: str = ""


class SubagentSession:
    """Per-session state for the registered read-only subagents."""

    def __init__(self) -> None:
        self.generation = 0
        self.started = 0
        self._states: dict[str, SubagentState] = {}
        self.reset()

    def reset(self) -> None:
        self.generation += 1
        self.started = 0
        self._states = {name: SubagentState() for name in SUBAGENTS}

    def state(self, name: str) -> SubagentState:
        return self._states[name]

    def begin(self, name: str, objective: str = "") -> None:
        state = self._states[name]
        self.started += 1
        state.status = "working"
        state.objective = objective
        state.current_tool = ""

    def record_tool(self, name: str, tool_name: str) -> None:
        state = self._states[name]
        if state.status == "working":
            state.current_tool = tool_name

    def complete(self, name: str, report: str) -> None:
        state = self._states[name]
        state.status = "idle"
        state.runs += 1
        state.last_report = report
        state.current_tool = ""

    def fail(self, name: str, message: str) -> None:
        state = self._states[name]
        state.status = "error"
        state.runs += 1
        state.last_report = message
        state.current_tool = ""

    def cancel(self, name: str) -> None:
        state = self._states[name]
        state.status = "idle"
        state.current_tool = ""

    def ready_count(self) -> int:
        return sum(1 for state in self._states.values() if state.status == "idle")
