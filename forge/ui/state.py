from dataclasses import dataclass
from pathlib import Path
from typing import Final

from ..forge_core.agent import ForgeAgent
from ..forge_core.provider import ForgeProvider
from ..forge_core.sessions import SessionManager
from ..forge_core.subagents import SubagentRunner

PRICING: Final[dict[str, tuple[float, float]]] = {
    "deepseek/deepseek-chat": (0.27, 1.10),
    "deepseek/deepseek-reasoner": (0.55, 2.19),
    "openai/gpt-5": (1.25, 10.00),
    "anthropic/claude-sonnet-4-5": (3.00, 15.00),
    "gemini/gemini-2.5-flash": (0.15, 0.60),
}


@dataclass(frozen=True, slots=True)
class ForgeRuntime:
    """Mutable runtime services grouped behind one UI dependency."""

    provider: ForgeProvider
    agent: ForgeAgent
    subagents: SubagentRunner
    sessions: SessionManager
    workspace: Path
    version: str


def estimate_cost(agent: ForgeAgent) -> float | None:
    pricing = PRICING.get(agent.model_id)
    if pricing is None:
        return None
    input_price, output_price = pricing
    input_cost = agent.input_tokens / 1_000_000 * input_price
    output_cost = agent.output_tokens / 1_000_000 * output_price
    return input_cost + output_cost
