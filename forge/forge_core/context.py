from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from litellm import token_counter

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
