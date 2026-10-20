from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    tool_calling: bool = False
    streaming: bool = False
    vision: bool = False
    reasoning: bool = False
    structured_output: bool = False
    local: bool = False


@dataclass(frozen=True)
class ModelConfig:
    name: str
    model_id: str
    provider: str
    requires_key: str | None = None
    capabilities: ModelCapabilities = ModelCapabilities()


MODELS: dict[str, ModelConfig] = {
    # OpenAI
    "openai": ModelConfig(
        name="OpenAI",
        model_id="openai/gpt-5",
        provider="OpenAI",
        requires_key="OPENAI_API_KEY",
        capabilities=ModelCapabilities(
            tool_calling=True,
            streaming=True,
            vision=True,
            reasoning=True,
            structured_output=True,
        ),
    ),
    # DeepSeek
    "deepseek": ModelConfig(
        name="DeepSeek",
        model_id="deepseek/deepseek-chat",
        provider="DeepSeek",
        requires_key="DEEPSEEK_API_KEY",
        capabilities=ModelCapabilities(
            tool_calling=True,
            streaming=True,
            structured_output=True,
        ),
    ),
    "deepseek-reasoner": ModelConfig(
        name="DeepSeek Reasoner",
        model_id="deepseek/deepseek-reasoner",
        provider="DeepSeek",
        requires_key="DEEPSEEK_API_KEY",
        capabilities=ModelCapabilities(
            streaming=True,
            reasoning=True,
        ),
    ),
    # Anthropic
    "claude": ModelConfig(
        name="Claude",
        model_id="anthropic/claude-sonnet-4-5",
        provider="Anthropic",
        requires_key="ANTHROPIC_API_KEY",
        capabilities=ModelCapabilities(
            tool_calling=True,
            streaming=True,
            vision=True,
            reasoning=True,
            structured_output=True,
        ),
    ),
    # Google
    "gemini": ModelConfig(
        name="Gemini",
        model_id="gemini/gemini-2.5-flash",
        provider="Google",
        requires_key="GEMINI_API_KEY",
        capabilities=ModelCapabilities(
            tool_calling=True,
            streaming=True,
            vision=True,
            reasoning=True,
            structured_output=True,
        ),
    ),
    # OpenRouter
    "openrouter": ModelConfig(
        name="OpenRouter",
        model_id="openrouter/openai/gpt-4.1",
        provider="OpenRouter",
        requires_key="OPENROUTER_API_KEY",
        capabilities=ModelCapabilities(
            tool_calling=True,
            streaming=True,
            vision=True,
            structured_output=True,
        ),
    ),
    # Groq
    "groq": ModelConfig(
        name="Groq",
        model_id="groq/llama-3.3-70b-versatile",
        provider="Groq",
        requires_key="GROQ_API_KEY",
        capabilities=ModelCapabilities(
            tool_calling=True,
            streaming=True,
            structured_output=True,
        ),
    ),
    # Mistral
    "mistral": ModelConfig(
        name="Mistral",
        model_id="mistral/mistral-large-latest",
        provider="Mistral",
        requires_key="MISTRAL_API_KEY",
        capabilities=ModelCapabilities(
            tool_calling=True,
            streaming=True,
            structured_output=True,
        ),
    ),
    # xAI
    "xai": ModelConfig(
        name="Grok",
        model_id="xai/grok-2-latest",
        provider="xAI",
        requires_key="XAI_API_KEY",
        capabilities=ModelCapabilities(
            tool_calling=True,
            streaming=True,
            vision=True,
            reasoning=True,
            structured_output=True,
        ),
    ),
    # MiniMax
    "minimax": ModelConfig(
        name="MiniMax",
        model_id="minimax/MiniMax-M2.1",
        provider="MiniMax",
        requires_key="MINIMAX_API_KEY",
        capabilities=ModelCapabilities(
            tool_calling=True,
            streaming=True,
            reasoning=True,
        ),
    ),
    # Moonshot
    "moonshot": ModelConfig(
        name="Kimi",
        model_id="moonshot/moonshot-v1-8k",
        provider="Moonshot",
        requires_key="MOONSHOT_API_KEY",
        capabilities=ModelCapabilities(
            tool_calling=True,
            streaming=True,
            structured_output=True,
        ),
    ),
    # Qwen via DashScope
    "qwen": ModelConfig(
        name="Qwen Coder",
        model_id="dashscope/qwen2.5-coder-32b-instruct",
        provider="Qwen",
        requires_key="DASHSCOPE_API_KEY",
        capabilities=ModelCapabilities(
            tool_calling=True,
            streaming=True,
            structured_output=True,
        ),
    ),
    # Together AI
    "together": ModelConfig(
        name="Together Llama",
        model_id="together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo",
        provider="Together AI",
        requires_key="TOGETHER_API_KEY",
        capabilities=ModelCapabilities(
            tool_calling=True,
            streaming=True,
            structured_output=True,
        ),
    ),
    # Anyscale
    "anyscale": ModelConfig(
        name="Anyscale Llama",
        model_id="anyscale/meta-llama/Llama-3-70b-chat-hf",
        provider="Anyscale",
        requires_key="ANYSCALE_API_KEY",
        capabilities=ModelCapabilities(
            tool_calling=True,
            streaming=True,
        ),
    ),
    # Fireworks AI
    "fireworks": ModelConfig(
        name="Fireworks Llama",
        model_id="fireworks_ai/accounts/fireworks/models/llama-v3p1-70b-instruct",
        provider="Fireworks AI",
        requires_key="FIREWORKS_API_KEY",
        capabilities=ModelCapabilities(
            tool_calling=True,
            streaming=True,
            structured_output=True,
        ),
    ),
    # Cohere
    "cohere": ModelConfig(
        name="Command R+",
        model_id="cohere/command-r-plus",
        provider="Cohere",
        requires_key="COHERE_API_KEY",
        capabilities=ModelCapabilities(
            tool_calling=True,
            streaming=True,
            structured_output=True,
        ),
    ),
    # Amazon Bedrock
    "bedrock": ModelConfig(
        name="Bedrock Claude",
        model_id="bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
        provider="Amazon Bedrock",
        requires_key="AWS_ACCESS_KEY_ID",
        capabilities=ModelCapabilities(
            tool_calling=True,
            streaming=True,
            vision=True,
        ),
    ),
    # Azure OpenAI
    "azure": ModelConfig(
        name="Azure OpenAI",
        model_id="azure/gpt-4o",
        provider="Azure OpenAI",
        requires_key="AZURE_API_KEY",
        capabilities=ModelCapabilities(
            tool_calling=True,
            streaming=True,
            vision=True,
            reasoning=True,
            structured_output=True,
        ),
    ),
    # Cloudflare Workers AI
    "cloudflare": ModelConfig(
        name="Cloudflare Workers AI",
        model_id="cloudflare/@cf/meta/llama-3.1-8b-instruct",
        provider="Cloudflare",
        requires_key="CLOUDFLARE_API_TOKEN",
        capabilities=ModelCapabilities(
            streaming=True,
        ),
    ),
    # GitHub Models
    "github": ModelConfig(
        name="GitHub Models",
        model_id="github/gpt-4o",
        provider="GitHub",
        requires_key="GITHUB_TOKEN",
        capabilities=ModelCapabilities(
            tool_calling=True,
            streaming=True,
            vision=True,
            structured_output=True,
        ),
    ),
    # Local models
    "ollama": ModelConfig(
        name="Ollama",
        model_id="ollama/llama3.2:1b",
        provider="Local",
        capabilities=ModelCapabilities(
            tool_calling=True,
            streaming=True,
            structured_output=True,
            local=True,
        ),
    ),
    "ollama-qwen": ModelConfig(
        name="Ollama Qwen Coder",
        model_id="ollama/qwen2.5-coder:7b",
        provider="Local",
        capabilities=ModelCapabilities(
            tool_calling=True,
            streaming=True,
            structured_output=True,
            local=True,
        ),
    ),
    "lm-studio": ModelConfig(
        name="LM Studio",
        model_id="lm_studio/qwen2.5-coder-7b-instruct",
        provider="Local",
        capabilities=ModelCapabilities(
            tool_calling=True,
            streaming=True,
            structured_output=True,
            local=True,
        ),
    ),
    "vllm": ModelConfig(
        name="vLLM",
        model_id="hosted_vllm/local-model",
        provider="Local",
        capabilities=ModelCapabilities(
            tool_calling=True,
            streaming=True,
            structured_output=True,
            local=True,
        ),
    ),
}

DEFAULT_MODEL = "ollama"
