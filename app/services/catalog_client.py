from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from pydantic import ValidationError

from app.config import settings
from app.services.catalog_exceptions import (
    CatalogClientError,
    CatalogConfigurationError,
    CatalogRateLimitError,
    CatalogResponseError,
    CatalogUnauthorizedError,
    CatalogUnavailableError,
    CatalogValidationError,
)
from app.services.catalog_models import CatalogSearchResponse

logger = logging.getLogger(__name__)

SEARCH_PATH = "/api/v1/internal/max-bot/products/search/"
DEFAULT_LIMIT = 5


def _safe_error_message(exc: BaseException) -> str:
    text = str(exc)
    token = (settings.MAX_BOT_INTERNAL_API_TOKEN or "").strip()
    if token and token in text:
        text = text.replace(token, "***")
    return text


def _record_metrics(
    *,
    ok: bool,
    duration_seconds: float,
    error_type: str | None = None,
) -> None:
    try:
        from app.observability import prometheus_metrics as metrics

        metrics.b2b_catalog_search_requests_total.inc()
        metrics.b2b_catalog_search_duration_seconds.observe(duration_seconds)
        if not ok and error_type:
            metrics.b2b_catalog_search_errors_total.labels(error_type=error_type).inc()
    except Exception:  # pragma: no cover - metrics must never break search
        logger.debug("B2B catalog metrics update skipped", exc_info=True)


def _ensure_configuration() -> tuple[str, str]:
    base_url = (settings.B2B_CATALOG_API_BASE_URL or "").strip().rstrip("/")
    token = (settings.MAX_BOT_INTERNAL_API_TOKEN or "").strip()
    if not base_url:
        raise CatalogConfigurationError("B2B catalog API base URL is not configured")
    if not token:
        raise CatalogConfigurationError("B2B catalog API token is not configured")
    return base_url, token


def _map_http_error(status_code: int) -> CatalogClientError:
    if status_code == 400:
        return CatalogValidationError("B2B catalog rejected the search query")
    if status_code == 401:
        return CatalogUnauthorizedError("B2B catalog authentication failed")
    if status_code == 429:
        return CatalogRateLimitError("B2B catalog rate limit exceeded")
    if status_code >= 500:
        return CatalogUnavailableError("B2B catalog service unavailable")
    return CatalogResponseError(f"B2B catalog unexpected status code={status_code}")


async def _perform_request(
    client: httpx.AsyncClient,
    *,
    url: str,
    headers: dict[str, str],
    params: dict[str, Any],
) -> httpx.Response:
    try:
        return await client.get(url, headers=headers, params=params)
    except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError):
        # One short retry for transient network/timeout issues only.
        return await client.get(url, headers=headers, params=params)


async def search_products(query: str, *, limit: int = DEFAULT_LIMIT) -> CatalogSearchResponse:
    """Search products via dealer platform internal MAX-bot endpoint.

    Always sends only ``q`` and ``limit``. Never sends ``warehouse``.
    """
    started = time.perf_counter()
    query_length = len(query)
    status_code: int | None = None
    error_type: str | None = None

    try:
        base_url, token = _ensure_configuration()
        url = f"{base_url}{SEARCH_PATH}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        params = {"q": query, "limit": limit}
        timeout = httpx.Timeout(settings.B2B_CATALOG_API_TIMEOUT_SECONDS)

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await _perform_request(
                    client,
                    url=url,
                    headers=headers,
                    params=params,
                )
            except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as exc:
                error_type = "unavailable"
                raise CatalogUnavailableError("B2B catalog request failed") from exc

        status_code = response.status_code
        if status_code != 200:
            mapped = _map_http_error(status_code)
            error_type = type(mapped).__name__
            if isinstance(mapped, CatalogUnauthorizedError):
                logger.error("B2B catalog authentication failed status_code=%s", status_code)
            raise mapped

        try:
            payload = response.json()
        except (ValueError, TypeError) as exc:
            error_type = "response"
            raise CatalogResponseError("B2B catalog returned invalid JSON") from exc

        try:
            parsed = CatalogSearchResponse.model_validate(payload)
        except ValidationError as exc:
            error_type = "response"
            raise CatalogResponseError("B2B catalog response contract mismatch") from exc

        duration = time.perf_counter() - started
        _record_metrics(ok=True, duration_seconds=duration)
        logger.info(
            "B2B catalog search ok search_source=b2b_api query_length=%s "
            "result_count=%s exact_match=%s has_more=%s latency_ms=%s status_code=%s",
            query_length,
            len(parsed.products),
            parsed.exact_match,
            parsed.has_more,
            int(duration * 1000),
            status_code,
        )
        return parsed

    except CatalogClientError as exc:
        duration = time.perf_counter() - started
        if error_type is None:
            error_type = type(exc).__name__
        _record_metrics(ok=False, duration_seconds=duration, error_type=error_type)
        logger.warning(
            "B2B catalog search failed search_source=b2b_api query_length=%s "
            "latency_ms=%s status_code=%s error_type=%s error=%s",
            query_length,
            int(duration * 1000),
            status_code,
            error_type,
            _safe_error_message(exc),
        )
        raise
