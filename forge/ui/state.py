from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from litellm import get_model_info

from ..checkpoints import CheckpointManager
from ..forge_core.agent import ForgeAgent
from ..forge_core.instructions import ProjectInstructions
from ..forge_core.provider import ForgeProvider
from ..forge_core.sessions import SessionManager
from ..forge_core.subagents import SubagentRunner
from ..recovery import RecoveryManager


@dataclass(frozen=True, slots=True)
class ForgeRuntime:
    """Mutable runtime services grouped behind one UI dependency."""

    provider: ForgeProvider
    agent: ForgeAgent
    subagents: SubagentRunner
    sessions: SessionManager
    checkpoints: CheckpointManager
    recovery: RecoveryManager
    workspace: Path
    version: str
    project_instructions: ProjectInstructions
    eft_text: str = ""


@lru_cache(maxsize=64)
def _token_prices(model_id: str) -> tuple[float, float] | None:
    try:
        info = get_model_info(model_id)
    except Exception:
        # LiteLLM raises a bare Exception for models outside its price table.
        return None
    input_price = info.get("input_cost_per_token")
    output_price = info.get("output_cost_per_token")
    if input_price is None or output_price is None:
        return None
    return input_price, output_price


def estimate_cost(agent: ForgeAgent) -> float | None:
    """Estimate the session cost in USD from provider-reported token usage."""
    capabilities = getattr(getattr(agent, "provider", None), "capabilities", None)
    if capabilities is not None and capabilities.local:
        return 0.0
    pricing = _token_prices(agent.model_id)
    if pricing is None:
        return None
    input_price, output_price = pricing
    return agent.input_tokens * input_price + agent.output_tokens * output_price
