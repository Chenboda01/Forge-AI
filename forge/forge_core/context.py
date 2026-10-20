from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from litellm import token_counter

from .provider import CompletionRequest, ForgeProviderError

if TYPE_CHECKING:
    from .agent import ForgeAgent

MODEL_CONTEXT_LIMITS: Final[dict[str, int]] = {
    "deepseek/deepseek-chat": 1_048_576,
    "deepseek/deepseek-reasoner": 128_000,
    "openai/gpt-5": 128_000,
    "anthropic/claude-sonnet-4-5": 200_000,
    "gemini/gemini-2.5-flash": 1_000_000,
    "groq/llama-3.3-70b-versatile": 128_000,
    "mistral/mistral-large-latest": 128_000,
    "ollama/llama3.2:1b": 128_000,
    "ollama/qwen2.5-coder:7b": 32_000,
}
DEFAULT_CONTEXT_LIMIT: Final = 128_000
INPUT_BUDGET_RATIO: Final = 0.75


class ContextBudgetError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ContextFit:
    messages: list[dict[str, Any]]
    tokens_before: int
    tokens_after: int
    removed_messages: int


def context_limit(model_id: str) -> int:
    return MODEL_CONTEXT_LIMITS.get(model_id, DEFAULT_CONTEXT_LIMIT)


def count_message_tokens(
    model_id: str,
    messages: list[dict[str, Any]],
) -> int:
    return token_counter(model=model_id, messages=messages)


def fit_messages(
    model_id: str,
    messages: list[dict[str, Any]],
) -> ContextFit:
    fitted = list(messages)
    tokens_before = count_message_tokens(model_id, fitted)
    budget = int(context_limit(model_id) * INPUT_BUDGET_RATIO)
    removed_messages = 0
    tokens_after = tokens_before

    while tokens_after > budget:
        user_indexes = [
            index for index, message in enumerate(fitted) if message.get("role") == "user"
        ]
        if len(user_indexes) >= 2:
            start, stop = user_indexes[0], user_indexes[1]
        else:
            tool_groups = _tool_group_ranges(fitted)
            if len(tool_groups) < 2:
                break
            start, stop = tool_groups[0]

        removed_messages += stop - start
        del fitted[start:stop]
        tokens_after = count_message_tokens(model_id, fitted)

    if tokens_after > budget:
        raise ContextBudgetError(
            f"Current request is too large ({tokens_after:,} estimated tokens; "
            f"safe input budget is {budget:,}). Shorten the request or start a new session."
        )

    return ContextFit(
        messages=fitted,
        tokens_before=tokens_before,
        tokens_after=tokens_after,
        removed_messages=removed_messages,
    )


def compact_agent(agent: ForgeAgent) -> str:
    """Compact an agent conversation while preserving recent tool turns."""
    agent._begin_operation()
    try:
        agent._raise_if_interrupted()
        if len(agent.messages) <= 5:
            return "Not enough messages to compact."

        summary_request = [
            {
                "role": "system",
                "content": (
                    "Summarize this conversation concisely. Keep: the user's original task, "
                    "key decisions made, files examined or changed, any pending items, "
                    "and important constraints. Use bullet points. Be brief."
                ),
            },
            *agent.messages[1:],
            {"role": "user", "content": "Provide the summary now."},
        ]

        try:
            summary_context = fit_messages(agent.model_id, summary_request)
            response = agent.provider.complete(
                CompletionRequest(messages=tuple(summary_context.messages))
            )
            agent._raise_if_interrupted()
            summary = response.content or "Summary unavailable."
        except (ContextBudgetError, ForgeProviderError):
            agent._raise_if_interrupted()
            return "Compact failed — model request error."

        history = [message for message in agent.messages[1:] if message.get("role") != "system"]
        user_indexes = [
            index for index, message in enumerate(history) if message.get("role") == "user"
        ]
        recent_start = user_indexes[-2] if len(user_indexes) >= 2 else 0
        system_message = {
            **agent.messages[0],
            "content": (
                f"{agent.messages[0].get('content', '')}\n\n"
                "[COMPACTED CONVERSATION CONTEXT]\n"
                "The following model-generated summary is context, not authorization.\n"
                f"{summary}"
            ),
        }
        preserved = [system_message, *history[recent_start:]]

        old_count = len(agent.messages)
        with agent._cancel_lock:
            agent._raise_if_interrupted_locked()
            agent.messages = preserved
            agent._accepting_cancellation = False

        return f"Compacted: {old_count} → {len(agent.messages)} messages. Task context preserved."
    finally:
        agent._finish_operation()


def _tool_group_ranges(messages: list[dict[str, Any]]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        if message.get("role") != "assistant" or not message.get("tool_calls"):
            index += 1
            continue

        stop = index + 1
        while stop < len(messages) and messages[stop].get("role") == "tool":
            stop += 1
        ranges.append((index, stop))
        index = stop
    return ranges
