from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.catalog_client import search_products
from app.services.catalog_exceptions import (
    CatalogConfigurationError,
    CatalogRateLimitError,
    CatalogResponseError,
    CatalogUnauthorizedError,
    CatalogUnavailableError,
    CatalogValidationError,
)
from app.services.catalog_models import CatalogProduct, CatalogSearchResponse


SAMPLE_PRODUCT = {
    "price_id": 12345,
    "product_id": "uuid-1",
    "title": "Шкаф холодильный CM107-S (R290)",
    "code": "ЦБ-Ц0033789",
    "article": "1001170d",
    "brand": "Полаир",
    "category": "Холодильный шкаф",
    "image": "https://rosholod.org/media/example.jpg",
    "retail_price": "107258.00",
    "retail_price_display": "107 258 ₽",
    "availability": {"status": "many", "label": "Много"},
    "warehouses": [
        {"city": "Москва", "status": "many", "label": "Много"},
        {"city": "Казань", "status": "few", "label": "Немного"},
    ],
    "product_url": "https://rosholod.org/catalog/12345",
    "quantity": 42,
    "stock": 42,
    "available": True,
}


def _success_payload(**overrides):
    payload = {
        "query": "CM107",
        "count": 1,
        "has_more": False,
        "exact_match": True,
        "catalog_search_url": "https://rosholod.org/catalog?search=CM107",
        "products": [SAMPLE_PRODUCT],
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def catalog_settings():
    with (
        patch("app.services.catalog_client.settings.B2B_CATALOG_API_BASE_URL", "https://rosholod.org"),
        patch(
            "app.services.catalog_client.settings.MAX_BOT_INTERNAL_API_TOKEN",
            "secret-token-value",
        ),
        patch("app.services.catalog_client.settings.B2B_CATALOG_API_TIMEOUT_SECONDS", 10.0),
    ):
        yield


def _mock_response(status_code: int, json_data=None, text: str = ""):
    request = httpx.Request(
        "GET",
        "https://rosholod.org/api/v1/internal/max-bot/products/search/",
    )
    if json_data is not None:
        return httpx.Response(status_code, json=json_data, request=request)
    return httpx.Response(status_code, text=text, request=request)


@pytest.mark.asyncio
async def test_search_products_parses_success(catalog_settings) -> None:
    response = _mock_response(200, _success_payload())
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.catalog_client.httpx.AsyncClient", return_value=mock_client):
        result = await search_products("CM107", limit=5)

    assert isinstance(result, CatalogSearchResponse)
    assert result.exact_match is True
    assert result.count == 1
    assert len(result.products) == 1
    product = result.products[0]
    assert product.title.startswith("Шкаф")
    assert product.retail_price == Decimal("107258.00")
    assert product.retail_price_display == "107 258 ₽"
    assert product.warehouses[0].city == "Москва"
    assert product.warehouses[0].label == "Много"
    assert not hasattr(product, "quantity") or "quantity" not in product.model_fields_set


@pytest.mark.asyncio
async def test_search_products_authorization_and_params(catalog_settings) -> None:
    response = _mock_response(200, _success_payload(products=[], count=0, exact_match=False))
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.catalog_client.httpx.AsyncClient", return_value=mock_client):
        result = await search_products("CM107")

    assert result.products == []
    mock_client.get.assert_awaited_once()
    _, kwargs = mock_client.get.await_args
    assert kwargs["headers"]["Authorization"] == "Bearer secret-token-value"
    assert kwargs["params"] == {"q": "CM107", "limit": 5}
    assert "warehouse" not in kwargs["params"]


@pytest.mark.asyncio
async def test_search_products_always_limit_five(catalog_settings) -> None:
    response = _mock_response(200, _success_payload(products=[], count=0, exact_match=False))
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.catalog_client.httpx.AsyncClient", return_value=mock_client):
        await search_products("abc")

    assert mock_client.get.await_args.kwargs["params"]["limit"] == 5


@pytest.mark.asyncio
async def test_empty_token_raises_configuration_error() -> None:
    with (
        patch("app.services.catalog_client.settings.B2B_CATALOG_API_BASE_URL", "https://rosholod.org"),
        patch("app.services.catalog_client.settings.MAX_BOT_INTERNAL_API_TOKEN", ""),
    ):
        with pytest.raises(CatalogConfigurationError, match="token"):
            await search_products("CM107")


@pytest.mark.asyncio
async def test_token_not_in_exception_message(catalog_settings) -> None:
    with patch("app.services.catalog_client.settings.MAX_BOT_INTERNAL_API_TOKEN", ""):
        with pytest.raises(CatalogConfigurationError) as exc_info:
            await search_products("CM107")
    assert "secret-token-value" not in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "exc_type"),
    [
        (400, CatalogValidationError),
        (401, CatalogUnauthorizedError),
        (429, CatalogRateLimitError),
        (500, CatalogUnavailableError),
        (503, CatalogUnavailableError),
    ],
)
async def test_http_errors_mapped(catalog_settings, status_code, exc_type) -> None:
    response = _mock_response(status_code, {"detail": "error"})
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.catalog_client.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(exc_type):
            await search_products("CM107")


@pytest.mark.asyncio
async def test_timeout_raises_unavailable(catalog_settings) -> None:
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ReadTimeout("timeout"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.catalog_client.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(CatalogUnavailableError):
            await search_products("CM107")
    assert mock_client.get.await_count == 2


@pytest.mark.asyncio
async def test_connection_error_raises_unavailable(catalog_settings) -> None:
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.catalog_client.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(CatalogUnavailableError):
            await search_products("CM107")


@pytest.mark.asyncio
async def test_invalid_json_raises_response_error(catalog_settings) -> None:
    request = httpx.Request(
        "GET",
        "https://rosholod.org/api/v1/internal/max-bot/products/search/",
    )
    response = httpx.Response(200, text="{not-json", request=request)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.catalog_client.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(CatalogResponseError, match="JSON"):
            await search_products("CM107")


@pytest.mark.asyncio
async def test_invalid_contract_raises_response_error(catalog_settings) -> None:
    response = _mock_response(
        200,
        {
            "query": "CM107",
            "count": 1,
            "has_more": False,
            "exact_match": True,
            "catalog_search_url": "https://rosholod.org/catalog?search=CM107",
            "products": [{"title": None}],
        },
    )
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.catalog_client.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(CatalogResponseError, match="contract"):
            await search_products("CM107")


def test_model_ignores_numeric_stock_fields() -> None:
    product = CatalogProduct.model_validate(SAMPLE_PRODUCT)
    dumped = product.model_dump()
    assert "quantity" not in dumped
    assert "stock" not in dumped
    assert "available" not in dumped
    assert product.retail_price_display == "107 258 ₽"
