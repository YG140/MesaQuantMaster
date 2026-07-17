class MarketProviderError(RuntimeError):
    """Base error for normalized market provider failures."""


class MarketProviderUnavailableError(MarketProviderError):
    """Provider is temporarily unavailable or unreachable."""


class MarketAssetNotFoundError(MarketProviderError):
    """The requested asset was not found by the provider."""


class MarketAuthenticationError(MarketProviderError):
    """Provider authentication is missing or invalid."""


class MarketPermissionError(MarketProviderError):
    """The configured token cannot access the requested resource."""


class MarketRateLimitError(MarketProviderError):
    """Provider request quota was reached."""


class MarketInvalidResponseError(MarketProviderError):
    """Provider returned malformed or unsupported data."""
