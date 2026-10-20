"""Static provider catalog used by authentication and provider selection.

This module deliberately contains no network or credential access. It only
describes which providers Forge knows how to authenticate and route. The
catalog is intentionally small and explicit; adding a provider here does not
grant it any runtime authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

AuthKind = Literal["api_key", "local", "custom"]


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    """A provider Forge can authenticate against."""

    id: str
    label: str
    env_var: str | None
    auth: AuthKind
    description: str
    default_base_url: str | None = None
    notes: str = ""


PROVIDERS: Final[dict[str, ProviderConfig]] = {
    "anthropic": ProviderConfig(
        id="anthropic",
        label="Anthropic",
        env_var="ANTHROPIC_API_KEY",
        auth="api_key",
        description="Claude Sonnet, Haiku, and Opus models.",
    ),
    "openai": ProviderConfig(
        id="openai",
        label="OpenAI",
        env_var="OPENAI_API_KEY",
        auth="api_key",
        description="GPT and reasoning models served by OpenAI.",
    ),
    "google": ProviderConfig(
        id="google",
        label="Google Gemini",
        env_var="GEMINI_API_KEY",
        auth="api_key",
        description="Gemini models served by Google AI Studio.",
    ),
    "xai": ProviderConfig(
        id="xai",
        label="xAI",
        env_var="XAI_API_KEY",
        auth="api_key",
        description="Grok models served by xAI.",
    ),
    "deepseek": ProviderConfig(
        id="deepseek",
        label="DeepSeek",
        env_var="DEEPSEEK_API_KEY",
        auth="api_key",
        description="DeepSeek chat and reasoning models.",
    ),
    "minimax": ProviderConfig(
        id="minimax",
        label="MiniMax",
        env_var="MINIMAX_API_KEY",
        auth="api_key",
        description="MiniMax chat and reasoning models.",
    ),
    "moonshot": ProviderConfig(
        id="moonshot",
        label="Moonshot",
        env_var="MOONSHOT_API_KEY",
        auth="api_key",
        description="Kimi models served by Moonshot AI.",
    ),
    "dashscope": ProviderConfig(
        id="dashscope",
        label="Qwen (DashScope)",
        env_var="DASHSCOPE_API_KEY",
        auth="api_key",
        description="Qwen models served through Alibaba DashScope.",
    ),
    "openrouter": ProviderConfig(
        id="openrouter",
        label="OpenRouter",
        env_var="OPENROUTER_API_KEY",
        auth="api_key",
        description="Aggregated access to many upstream providers.",
    ),
    "together": ProviderConfig(
        id="together",
        label="Together AI",
        env_var="TOGETHER_API_KEY",
        auth="api_key",
        description="Open models hosted by Together AI.",
    ),
    "groq": ProviderConfig(
        id="groq",
        label="Groq",
        env_var="GROQ_API_KEY",
        auth="api_key",
        description="Low-latency open models served by Groq.",
    ),
    "anyscale": ProviderConfig(
        id="anyscale",
        label="Anyscale",
        env_var="ANYSCALE_API_KEY",
        auth="api_key",
        description="Open models served by Anyscale Endpoints.",
    ),
    "fireworks": ProviderConfig(
        id="fireworks",
        label="Fireworks AI",
        env_var="FIREWORKS_API_KEY",
        auth="api_key",
        description="Open models served by Fireworks AI.",
    ),
    "bedrock": ProviderConfig(
        id="bedrock",
        label="Amazon Bedrock",
        env_var="AWS_ACCESS_KEY_ID",
        auth="api_key",
        description="Models served through Amazon Bedrock.",
        notes="Bedrock also requires an AWS secret key, region, and model access.",
    ),
    "azure": ProviderConfig(
        id="azure",
        label="Azure OpenAI",
        env_var="AZURE_API_KEY",
        auth="api_key",
        description="OpenAI models deployed in an Azure subscription.",
        notes="Azure also requires a deployment base URL and API version.",
    ),
    "cloudflare": ProviderConfig(
        id="cloudflare",
        label="Cloudflare Workers AI",
        env_var="CLOUDFLARE_API_TOKEN",
        auth="api_key",
        description="Models served through Cloudflare Workers AI.",
        notes="Cloudflare also requires an account identifier.",
    ),
    "github": ProviderConfig(
        id="github",
        label="GitHub Models",
        env_var="GITHUB_TOKEN",
        auth="api_key",
        description="Models served through GitHub Models.",
    ),
    "cohere": ProviderConfig(
        id="cohere",
        label="Cohere",
        env_var="COHERE_API_KEY",
        auth="api_key",
        description="Command models served by Cohere.",
    ),
    "mistral": ProviderConfig(
        id="mistral",
        label="Mistral AI",
        env_var="MISTRAL_API_KEY",
        auth="api_key",
        description="Mistral and Codestral models.",
    ),
    "ollama": ProviderConfig(
        id="ollama",
        label="Ollama",
        env_var=None,
        auth="local",
        description="Models served by a local Ollama daemon.",
        default_base_url="http://localhost:11434",
    ),
    "lm-studio": ProviderConfig(
        id="lm-studio",
        label="LM Studio",
        env_var=None,
        auth="local",
        description="Models served by a local LM Studio server.",
        default_base_url="http://localhost:1234/v1",
    ),
    "vllm": ProviderConfig(
        id="vllm",
        label="vLLM",
        env_var=None,
        auth="local",
        description="Models served by a local vLLM OpenAI-compatible server.",
        default_base_url="http://localhost:8000/v1",
    ),
    "opencode-go": ProviderConfig(
        id="opencode-go",
        label="OpenCode Go",
        env_var="OPENCODE_API_KEY",
        auth="api_key",
        description="OpenCode's hosted model proxy.",
        notes="Requires a custom endpoint supplied through FORGE_BASE_URL.",
    ),
    "custom": ProviderConfig(
        id="custom",
        label="Other / custom",
        env_var="FORGE_CUSTOM_API_KEY",
        auth="custom",
        description="Any OpenAI-compatible endpoint.",
        notes="Requires FORGE_BASE_URL and FORGE_MODEL_ID to be configured.",
    ),
}


def provider_credentials() -> frozenset[str]:
    """Credential names the catalog is allowed to store."""
    return frozenset(
        provider.env_var for provider in PROVIDERS.values() if provider.env_var is not None
    )


def provider_for_env(variable_name: str) -> ProviderConfig | None:
    """Return the catalog entry that owns a credential name."""
    for provider in PROVIDERS.values():
        if provider.env_var == variable_name:
            return provider
    return None


def provider_by_id(identifier: str) -> ProviderConfig | None:
    """Resolve a provider id case-insensitively."""
    return PROVIDERS.get(identifier.strip().lower().replace("_", "-"))
