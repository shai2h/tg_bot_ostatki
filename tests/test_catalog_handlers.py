from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import InlineKeyboardMarkup

from app.bot.handlers import (
    _format_compact_product_card,
    _format_exact_product_card,
    _send_search_results,
)
from app.services.catalog_exceptions import (
    CatalogUnauthorizedError,
    CatalogUnavailableError,
    CatalogValidationError,
)
from app.services.catalog_models import (
    CatalogAvailability,
    CatalogProduct,
    CatalogSearchResponse,
    CatalogWarehouseAvailability,
)


def _product(**overrides) -> CatalogProduct:
    data = {
        "price_id": 12345,
        "product_id": "uuid-1",
        "title": "Шкаф холодильный CM107-S (R290)",
        "code": "ЦБ-Ц0033789",
        "article": "1001170d",
        "brand": "Полаир",
        "category": "Холодильный шкаф",
        "image": "https://rosholod.org/media/example.jpg",
        "retail_price": Decimal("107258.00"),
        "retail_price_display": "107 258 ₽",
        "availability": CatalogAvailability(status="many", label="Много"),
        "warehouses": [
            CatalogWarehouseAvailability(name="Москва", status="many", label="Много"),
            CatalogWarehouseAvailability(name="Казань", status="few", label="Немного"),
        ],
        "product_url": "https://rosholod.org/catalog/12345",
    }
    data.update(overrides)
    return CatalogProduct.model_validate(data)


class FakeMessage:
    def __init__(self) -> None:
        self.answers: list[tuple[str, dict]] = []
        self.platform = "max"
        self.from_user = SimpleNamespace(id=42)

    async def answer(self, text: str, **kwargs):
        self.answers.append((text, kwargs))
        return None


@pytest.mark.asyncio
async def test_feature_flag_false_keeps_local_path() -> None:
    message = FakeMessage()
    with (
        patch("app.bot.handlers.settings.B2B_CATALOG_SEARCH_ENABLED", False),
        patch("app.bot.handlers.log_user_query", new=AsyncMock()) as log_mock,
        patch(
            "app.bot.handlers._send_local_search_results",
            new=AsyncMock(),
        ) as local_mock,
        patch(
            "app.bot.handlers.b2b_search_products",
            new=AsyncMock(),
        ) as b2b_mock,
    ):
        await _send_search_results(message, 42, "CM107")

    log_mock.assert_awaited_once_with(42, "CM107")
    local_mock.assert_awaited_once()
    assert local_mock.await_args.kwargs["search_source"] == "local"
    b2b_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_feature_flag_true_calls_b2b_api() -> None:
    message = FakeMessage()
    response = CatalogSearchResponse(
        query="CM107",
        count=1,
        has_more=False,
        exact_match=True,
        catalog_search_url="https://rosholod.org/catalog?search=CM107",
        products=[_product()],
    )
    with (
        patch("app.bot.handlers.settings.B2B_CATALOG_SEARCH_ENABLED", True),
        patch("app.bot.handlers.log_user_query", new=AsyncMock()),
        patch(
            "app.bot.handlers.b2b_search_products",
            new=AsyncMock(return_value=response),
        ) as b2b_mock,
        patch(
            "app.bot.handlers._send_local_search_results",
            new=AsyncMock(),
        ) as local_mock,
    ):
        await _send_search_results(message, 42, "CM107")

    b2b_mock.assert_awaited_once_with("CM107", limit=5)
    local_mock.assert_not_awaited()
    assert "Товар найден" in message.answers[0][0]
    assert "Розничная цена: 107 258 ₽" in message.answers[0][0]
    assert "many" not in message.answers[0][0]
    assert "42" not in message.answers[0][0]
    markup = message.answers[0][1]["reply_markup"]
    assert isinstance(markup, InlineKeyboardMarkup)
    assert markup.inline_keyboard[0][0].url == "https://rosholod.org/catalog/12345"


@pytest.mark.asyncio
async def test_exact_match_does_not_call_local_search() -> None:
    message = FakeMessage()
    response = CatalogSearchResponse(
        query="CM107",
        count=1,
        exact_match=True,
        products=[_product()],
        catalog_search_url="https://rosholod.org/catalog?search=CM107",
    )
    with (
        patch("app.bot.handlers.settings.B2B_CATALOG_SEARCH_ENABLED", True),
        patch("app.bot.handlers.log_user_query", new=AsyncMock()),
        patch("app.bot.handlers.b2b_search_products", new=AsyncMock(return_value=response)),
        patch("app.bot.handlers._send_local_search_results", new=AsyncMock()) as local_mock,
        patch("app.bot.handlers.find_products_by_query", new=AsyncMock()) as find_mock,
        patch("app.bot.handlers.fuzzy_find_products", new=AsyncMock()) as fuzzy_mock,
    ):
        await _send_search_results(message, 42, "CM107")

    local_mock.assert_not_awaited()
    find_mock.assert_not_awaited()
    fuzzy_mock.assert_not_awaited()
    assert len(message.answers) == 1


@pytest.mark.asyncio
async def test_multiple_results_limited_to_five() -> None:
    message = FakeMessage()
    products = [
        _product(
            title=f"Товар {idx}",
            product_url=f"https://rosholod.org/catalog/{idx}",
            retail_price_display=f"{1000 + idx} ₽",
        )
        for idx in range(1, 8)
    ]
    response = CatalogSearchResponse(
        query="CM107",
        count=7,
        has_more=True,
        exact_match=False,
        catalog_search_url="https://rosholod.org/catalog?search=CM107",
        products=products,
    )
    with (
        patch("app.bot.handlers.settings.B2B_CATALOG_SEARCH_ENABLED", True),
        patch("app.bot.handlers.log_user_query", new=AsyncMock()),
        patch("app.bot.handlers.b2b_search_products", new=AsyncMock(return_value=response)),
    ):
        await _send_search_results(message, 42, "CM107")

    assert "Показываю первые 5." in message.answers[0][0]
    product_answers = message.answers[1:6]
    assert len(product_answers) == 5
    for idx, (text, kwargs) in enumerate(product_answers, start=1):
        assert text.startswith(f"{idx}. Товар {idx}")
        assert "Розничная цена:" in text
        assert kwargs["reply_markup"].inline_keyboard[0][0].url.endswith(f"/{idx}")
    assert message.answers[-1][1]["reply_markup"].inline_keyboard[0][0].url.endswith(
        "search=CM107"
    )


@pytest.mark.asyncio
async def test_empty_b2b_result_no_fallback() -> None:
    message = FakeMessage()
    response = CatalogSearchResponse(
        query="zzz",
        count=0,
        exact_match=False,
        catalog_search_url="https://rosholod.org/catalog?search=zzz",
        products=[],
    )
    with (
        patch("app.bot.handlers.settings.B2B_CATALOG_SEARCH_ENABLED", True),
        patch("app.bot.handlers.log_user_query", new=AsyncMock()),
        patch("app.bot.handlers.b2b_search_products", new=AsyncMock(return_value=response)),
        patch("app.bot.handlers._send_local_search_results", new=AsyncMock()) as local_mock,
        patch("app.bot.handlers.fuzzy_find_products", new=AsyncMock()) as fuzzy_mock,
    ):
        await _send_search_results(message, 42, "zzz")

    local_mock.assert_not_awaited()
    fuzzy_mock.assert_not_awaited()
    assert "ничего не найдено" in message.answers[0][0]
    assert message.answers[0][1]["reply_markup"].inline_keyboard[0][0].text == (
        "Открыть поиск в каталоге"
    )


@pytest.mark.asyncio
async def test_validation_error_shows_min_length_message() -> None:
    message = FakeMessage()
    with (
        patch("app.bot.handlers.settings.B2B_CATALOG_SEARCH_ENABLED", True),
        patch("app.bot.handlers.log_user_query", new=AsyncMock()),
        patch(
            "app.bot.handlers.b2b_search_products",
            new=AsyncMock(side_effect=CatalogValidationError("bad")),
        ),
        patch("app.bot.handlers._send_local_search_results", new=AsyncMock()) as local_mock,
    ):
        await _send_search_results(message, 42, "ab")

    local_mock.assert_not_awaited()
    assert "не менее 3 символов" in message.answers[0][0]
    assert "400" not in message.answers[0][0]


@pytest.mark.asyncio
async def test_timeout_triggers_local_fallback() -> None:
    message = FakeMessage()
    with (
        patch("app.bot.handlers.settings.B2B_CATALOG_SEARCH_ENABLED", True),
        patch("app.bot.handlers.log_user_query", new=AsyncMock()),
        patch(
            "app.bot.handlers.b2b_search_products",
            new=AsyncMock(side_effect=CatalogUnavailableError("timeout")),
        ),
        patch(
            "app.bot.handlers._send_local_search_results",
            new=AsyncMock(),
        ) as local_mock,
        patch("app.bot.handlers._record_b2b_fallback") as fallback_metric,
    ):
        await _send_search_results(message, 42, "CM107")

    local_mock.assert_awaited_once()
    assert local_mock.await_args.kwargs["search_source"] == "local_fallback"
    fallback_metric.assert_called_once()


@pytest.mark.asyncio
async def test_unauthorized_allows_fallback_and_logs_without_token(caplog: pytest.LogCaptureFixture) -> None:
    message = FakeMessage()
    with (
        patch("app.bot.handlers.settings.B2B_CATALOG_SEARCH_ENABLED", True),
        patch("app.bot.handlers.log_user_query", new=AsyncMock()),
        patch(
            "app.bot.handlers.b2b_search_products",
            new=AsyncMock(side_effect=CatalogUnauthorizedError("B2B catalog authentication failed")),
        ),
        patch("app.bot.handlers._send_local_search_results", new=AsyncMock()) as local_mock,
        patch("app.bot.handlers.settings.MAX_BOT_INTERNAL_API_TOKEN", "super-secret-token"),
        caplog.at_level("WARNING"),
    ):
        await _send_search_results(message, 42, "CM107")

    local_mock.assert_awaited_once()
    assert "super-secret-token" not in caplog.text


@pytest.mark.asyncio
async def test_both_paths_fail_safe_message() -> None:
    message = FakeMessage()
    with (
        patch("app.bot.handlers.settings.B2B_CATALOG_SEARCH_ENABLED", True),
        patch("app.bot.handlers.log_user_query", new=AsyncMock()),
        patch(
            "app.bot.handlers.b2b_search_products",
            new=AsyncMock(side_effect=CatalogUnavailableError("down")),
        ),
        patch(
            "app.bot.handlers._send_local_search_results",
            new=AsyncMock(side_effect=RuntimeError("db down")),
        ),
    ):
        await _send_search_results(message, 42, "CM107")

    assert "временно недоступен" in message.answers[0][0]
    assert "traceback" not in message.answers[0][0].lower()


def test_exact_card_uses_labels_and_retail_price_only() -> None:
    text = _format_exact_product_card(_product())
    assert "Розничная цена: 107 258 ₽" in text
    assert "Москва — Много" in text
    assert "Казань — Немного" in text
    assert "many" not in text
    assert "107258" not in text.replace("107 258", "")


def test_compact_card_uses_availability_label() -> None:
    text = _format_compact_product_card(1, _product())
    assert "Наличие: Много" in text
    assert "Москва" not in text


def test_price_fallback_without_display() -> None:
    product = _product(retail_price_display=None, retail_price=Decimal("163846.00"))
    text = _format_exact_product_card(product)
    assert "Розничная цена: 163 846 ₽" in text


def test_missing_brand_line_omitted() -> None:
    text = _format_exact_product_card(_product(brand=None))
    assert "Бренд:" not in text
