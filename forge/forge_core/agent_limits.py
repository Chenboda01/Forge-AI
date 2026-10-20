from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Final

from .provider_models import ProviderToolCall

DEFAULT_MAX_STEPS: Final = 20
MAX_MAX_STEPS: Final = 300
DEFAULT_MAX_TOOL_CALLS: Final = 50
MAX_MAX_TOOL_CALLS: Final = 50
DEFAULT_MAX_REPEATED_TOOL_CALLS: Final = 3
MAX_MAX_REPEATED_TOOL_CALLS: Final = 3


class AgentLimitError(Exception):
    """Raised when a model-loop limit is invalid or exhausted."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class ToolCallState:
    """Immutable per-run accounting for model tool calls."""

    used: int = 0
    repeated: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True, slots=True)
class AgentLimits:
    """Bounded deterministic limits for one primary-agent run."""

    max_steps: int
    max_tool_calls: int
    max_repeated_tool_calls: int

    def validate(self) -> None:
        """Reject limits that exceed the workflow's hard bounds."""
        if not 1 <= self.max_steps <= MAX_MAX_STEPS:
            raise AgentLimitError("max_steps must be between 1 and 300.")
        if not 1 <= self.max_tool_calls <= MAX_MAX_TOOL_CALLS:
            raise AgentLimitError("max_tool_calls must be between 1 and 50.")
        if not 1 <= self.max_repeated_tool_calls <= MAX_MAX_REPEATED_TOOL_CALLS:
            raise AgentLimitError("max_repeated_tool_calls must be between 1 and 3.")

    def reserve_tool_calls(
        self,
        tool_calls: tuple[ProviderToolCall, ...],
        state: ToolCallState,
    ) -> ToolCallState:
        """Reserve a complete provider tool-call batch or raise."""
        requested = state.used + len(tool_calls)
        if requested > self.max_tool_calls:
            raise AgentLimitError(f"Forge reached its {self.max_tool_calls}-tool-call limit.")

        updated = dict(state.repeated)
        for tool_call in tool_calls:
            fingerprint = _tool_call_fingerprint(tool_call)
            count = updated.get(fingerprint, 0) + 1
            if count > self.max_repeated_tool_calls:
                raise AgentLimitError(
                    f"Forge reached its repeated tool-call limit for '{tool_call.name}'."
                )
            updated[fingerprint] = count
        return ToolCallState(requested, tuple(updated.items()))


def _tool_call_fingerprint(tool_call: ProviderToolCall) -> str:
    raw_arguments = tool_call.arguments or "{}"
    try:
        parsed_arguments = json.loads(raw_arguments)
    except json.JSONDecodeError:
        canonical_arguments = raw_arguments
    else:
        canonical_arguments = json.dumps(
            parsed_arguments,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    return f"{tool_call.name}\x00{canonical_arguments}"
