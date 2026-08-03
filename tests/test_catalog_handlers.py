from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.types import InlineKeyboardMarkup

from app.bot.handlers import (
    WELCOME_TEXT,
    _format_compact_product_card,
    _format_exact_product_card,
    _send_search_results,
)
from app.bot.user_guards import UserInteractionGuard, user_guards
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
            CatalogWarehouseAvailability(city="Москва", status="many", label="Много"),
            CatalogWarehouseAvailability(city="Казань", status="few", label="Немного"),
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


@pytest.fixture(autouse=True)
def reset_user_guards() -> None:
    user_guards._users.clear()
    user_guards._seen_messages.clear()
    user_guards._seen_callbacks.clear()
    yield
    user_guards._users.clear()
    user_guards._seen_messages.clear()
    user_guards._seen_callbacks.clear()


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
    assert "🧺" in message.answers[0][0]
    assert "▶️ Цена: 107 258 ₽" in message.answers[0][0]
    assert "many" not in message.answers[0][0]
    markup = message.answers[0][1]["reply_markup"]
    assert isinstance(markup, InlineKeyboardMarkup)
    assert markup.inline_keyboard[0][0].text == "Открыть карточку товара"
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
        assert text.startswith(f"🧺 {idx}. Товар {idx}")
        assert "▶️ Цена:" in text
        assert kwargs["reply_markup"].inline_keyboard[0][0].url.endswith(f"/{idx}")
    catalog_text, catalog_kwargs = message.answers[-1]
    assert catalog_text == "🌐 Посмотреть полный каталог товаров"
    assert catalog_kwargs["reply_markup"].inline_keyboard[0][0].text == "Открыть каталог"


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
    assert message.answers[0][1]["reply_markup"].inline_keyboard[0][0].text == "Открыть каталог"


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
async def test_unauthorized_allows_fallback_and_logs_without_token(
    caplog: pytest.LogCaptureFixture,
) -> None:
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


@pytest.mark.asyncio
async def test_spam_guard_blocks_parallel_search() -> None:
    message = FakeMessage()
    assert user_guards.begin_search(42) is None
    with (
        patch("app.bot.handlers.settings.B2B_CATALOG_SEARCH_ENABLED", True),
        patch("app.bot.handlers.log_user_query", new=AsyncMock()) as log_mock,
        patch("app.bot.handlers.b2b_search_products", new=AsyncMock()) as b2b_mock,
    ):
        await _send_search_results(message, 42, "CM107")

    log_mock.assert_not_awaited()
    b2b_mock.assert_not_awaited()
    assert "предыдущий поиск" in message.answers[0][0]


def test_exact_card_uses_labels_and_retail_price_only() -> None:
    text = _format_exact_product_card(_product())
    assert text.startswith("🧺 Шкаф холодильный")
    assert "▶️ Цена: 107 258 ₽" in text
    assert "🟢 Москва — Много" in text
    assert "🟠 Казань — Немного" in text
    assert "•" not in text
    assert "many" not in text


def test_compact_card_uses_city_warehouses_before_availability_label() -> None:
    text = _format_compact_product_card(1, _product())
    assert text.startswith("🧺 1. ")
    assert "🟢 Москва — Много" in text
    assert "🟠 Казань — Немного" in text
    assert "•" not in text
    assert "🟢 Наличие: Много" not in text


def test_compact_card_shows_no_stock_message_without_warehouses() -> None:
    text = _format_compact_product_card(1, _product(warehouses=[]))
    assert "⚪ На складах пока нет доступного остатка." in text
    assert "Наличие уточняется" not in text


def test_warehouse_name_is_temporary_fallback_without_city() -> None:
    product = _product(
        warehouses=[
            CatalogWarehouseAvailability(name="Legacy city", status="available", label="В наличии")
        ]
    )
    text = _format_exact_product_card(product)
    assert "🟡 Legacy city — В наличии" in text


def test_status_emoji_mapping_for_all_warehouse_statuses() -> None:
    product = _product(
        warehouses=[
            CatalogWarehouseAvailability(city="Краснодар", status="many", label="Много"),
            CatalogWarehouseAvailability(city="Ростов-на-Дону", status="available", label="В наличии"),
            CatalogWarehouseAvailability(city="Хабаровск", status="few", label="Немного"),
            CatalogWarehouseAvailability(city="None", status="none", label="Нет в наличии"),
            CatalogWarehouseAvailability(city="Unknown", status="unknown", label="Наличие уточняется"),
        ]
    )

    text = _format_exact_product_card(product)

    assert "🟢 Краснодар — Много" in text
    assert "🟡 Ростов-на-Дону — В наличии" in text
    assert "🟠 Хабаровск — Немного" in text
    assert "None — 🔴 Нет в наличии" not in text
    assert "Unknown — ⚪ Наличие уточняется" not in text
    assert "None" not in text
    assert "Unknown" not in text
    assert "•" not in text
    assert "Наличие уточняется" not in text
    assert "many" not in text
    assert "available" not in text
    assert "few" not in text
    assert "none" not in text


def test_no_positive_warehouse_statuses_show_no_stock_message() -> None:
    product = _product(
        warehouses=[
            CatalogWarehouseAvailability(city="None", status="none", label="Нет в наличии"),
            CatalogWarehouseAvailability(city="Unknown", status="unknown", label="Наличие уточняется"),
        ]
    )

    text = _format_exact_product_card(product)

    assert "⚪ На складах пока нет доступного остатка." in text
    assert "Нет в наличии" not in text
    assert "Наличие уточняется" not in text


def test_price_fallback_without_display() -> None:
    product = _product(retail_price_display=None, retail_price=Decimal("163846.00"))
    text = _format_exact_product_card(product)
    assert "▶️ Цена: 163 846 ₽" in text


def test_missing_brand_line_omitted() -> None:
    text = _format_exact_product_card(_product(brand=None))
    assert "Бренд:" not in text


def test_welcome_text_mentions_dealer_platform() -> None:
    assert "Добро пожаловать" in WELCOME_TEXT
    assert "rosholod.org" in WELCOME_TEXT


def test_start_debounce_skips_duplicate() -> None:
    guard = UserInteractionGuard(start_debounce_seconds=3.0)
    assert guard.should_skip_duplicate_start(7) is False
    assert guard.should_skip_duplicate_start(7) is True


def test_bot_authored_message_is_detected() -> None:
    from app.bot.user_guards import is_message_from_bot

    bot = SimpleNamespace(id=1001)
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=1001, is_bot=False),
        _bot=bot,
        chat=SimpleNamespace(id=55),
        message_id="mid-1",
    )
    assert is_message_from_bot(message) is True

    user_message = SimpleNamespace(
        from_user=SimpleNamespace(id=42, is_bot=False),
        _bot=bot,
        chat=SimpleNamespace(id=55),
        message_id="mid-2",
    )
    assert is_message_from_bot(user_message) is False


@pytest.mark.asyncio
async def test_bot_echo_does_not_start_search() -> None:
    from app.bot.handlers import _accept_inbound_message

    bot = SimpleNamespace(id=1001)
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=1001, is_bot=False),
        _bot=bot,
        chat=SimpleNamespace(id=55),
        message_id="bot-card-1",
        text="🧺 Товар",
        platform="max",
    )
    assert _accept_inbound_message(message) is False

    with (
        patch("app.bot.handlers.settings.B2B_CATALOG_SEARCH_ENABLED", True),
        patch("app.bot.handlers.log_user_query", new=AsyncMock()) as log_mock,
        patch("app.bot.handlers.b2b_search_products", new=AsyncMock()) as b2b_mock,
    ):
        # Simulate catch-all path guard: ignored before search.
        if _accept_inbound_message(message):
            await _send_search_results(message, 1001, message.text)

    log_mock.assert_not_awaited()
    b2b_mock.assert_not_awaited()


def test_message_dedupe_skips_second_delivery() -> None:
    guard = UserInteractionGuard()
    assert guard.should_skip_duplicate_message("chat:1") is False
    assert guard.should_skip_duplicate_message("chat:1") is True
    assert guard.should_skip_duplicate_callback("cb:1") is False
    assert guard.should_skip_duplicate_callback("cb:1") is True
