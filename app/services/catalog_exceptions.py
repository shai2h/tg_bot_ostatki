from __future__ import annotations


class CatalogClientError(Exception):
    """Base error for B2B catalog client failures."""


class CatalogConfigurationError(CatalogClientError):
    """Missing or invalid client configuration (token/base URL)."""


class CatalogValidationError(CatalogClientError):
    """Backend rejected the query (HTTP 400)."""


class CatalogUnauthorizedError(CatalogClientError):
    """Backend rejected the service token (HTTP 401)."""


class CatalogRateLimitError(CatalogClientError):
    """Backend rate-limited the client (HTTP 429)."""


class CatalogUnavailableError(CatalogClientError):
    """Backend temporary failure, timeout, or connection error."""


class CatalogResponseError(CatalogClientError):
    """Response body is not usable (invalid JSON or contract)."""
