class ForgeProviderError(Exception):
    """Base error for model selection and normalized provider failures."""


class AuthenticationError(ForgeProviderError):
    """Raised when a provider rejects configured credentials."""


class RateLimitError(ForgeProviderError):
    """Raised when a provider rejects a request due to rate limits."""


class ProviderConnectionError(ForgeProviderError):
    """Raised when Forge cannot connect to the selected provider."""


class ProviderTimeoutError(ForgeProviderError):
    """Raised when the selected provider exceeds its request timeout."""


class UnsupportedFeatureError(ForgeProviderError):
    """Raised when the selected model does not declare a requested feature."""


class InvalidProviderResponseError(ForgeProviderError):
    """Raised when an untrusted provider response cannot be normalized."""


class ContextLimitError(ForgeProviderError):
    """Raised when the provider rejects an oversized context."""


class ProviderUnavailableError(ForgeProviderError):
    """Raised when the selected provider reports that it is unavailable."""


class ProviderRequestError(ForgeProviderError):
    """Raised for a normalized provider failure without a narrower category."""
