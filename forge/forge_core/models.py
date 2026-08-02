from dataclasses import dataclass


@dataclass(frozen=True)
class ModelConfig:
    name: str
    model_id: str
    provider: str
    requires_key: str | None = None


MODELS: dict[str, ModelConfig] = {
    # OpenAI
    "openai": ModelConfig(
        name="OpenAI",
        model_id="openai/gpt-5",
        provider="OpenAI",
        requires_key="OPENAI_API_KEY",
    ),
    # DeepSeek
    "deepseek": ModelConfig(
        name="DeepSeek",
        model_id="deepseek/deepseek-chat",
        provider="DeepSeek",
        requires_key="DEEPSEEK_API_KEY",
    ),
    "deepseek-reasoner": ModelConfig(
        name="DeepSeek Reasoner",
        model_id="deepseek/deepseek-reasoner",
        provider="DeepSeek",
        requires_key="DEEPSEEK_API_KEY",
    ),
    # Anthropic
    "claude": ModelConfig(
        name="Claude",
        model_id="anthropic/claude-sonnet-4-5",
        provider="Anthropic",
        requires_key="ANTHROPIC_API_KEY",
    ),
    # Google
    "gemini": ModelConfig(
        name="Gemini",
        model_id="gemini/gemini-2.5-flash",
        provider="Google",
        requires_key="GEMINI_API_KEY",
    ),
    # OpenRouter
    "openrouter": ModelConfig(
        name="OpenRouter",
        model_id="openrouter/openai/gpt-4.1",
        provider="OpenRouter",
        requires_key="OPENROUTER_API_KEY",
    ),
    # Groq
    "groq": ModelConfig(
        name="Groq",
        model_id="groq/llama-3.3-70b-versatile",
        provider="Groq",
        requires_key="GROQ_API_KEY",
    ),
    # Mistral
    "mistral": ModelConfig(
        name="Mistral",
        model_id="mistral/mistral-large-latest",
        provider="Mistral",
        requires_key="MISTRAL_API_KEY",
    ),
    # Local models
    "ollama": ModelConfig(
        name="Ollama",
        model_id="ollama/llama3.2:1b",
        provider="Local",
    ),
    "ollama-qwen": ModelConfig(
        name="Ollama Qwen Coder",
        model_id="ollama/qwen2.5-coder:7b",
        provider="Local",
    ),
}

DEFAULT_MODEL = "ollama"
