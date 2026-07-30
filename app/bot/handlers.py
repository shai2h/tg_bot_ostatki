from __future__ import annotations

import logging
import os
import re
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

import pandas as pd
from aiogram import F
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from openpyxl import load_workbook
from openpyxl.styles import PatternFill
from sqlalchemy import select

from app.bot.utils import format_stock_quantity
from app.config import settings
from app.db.database import async_session_maker
from app.services.catalog_client import search_products as b2b_search_products
from app.services.catalog_exceptions import (
    CatalogClientError,
    CatalogConfigurationError,
    CatalogRateLimitError,
    CatalogResponseError,
    CatalogUnauthorizedError,
    CatalogUnavailableError,
    CatalogValidationError,
)
from app.services.catalog_models import CatalogProduct, CatalogSearchResponse
from app.services.search import (
    find_products_by_text as find_products_by_query,
    fuzzy_find_products,
    get_user_query_history,
    log_user_query,
)
from app.warehouse_stock.models import OstatkiMeta, WarehouseStocks

logger = logging.getLogger(__name__)


_HTML_TAG_RE = re.compile(r"</?(?:b|strong|i|em|u|s|code|pre|a)(?:\s+[^>]*)?>", re.IGNORECASE)
PRICE_LIST_URL = "https://rosholod.org/price-lists/OstatkiPoStolbcam.xls"
PRICE_LIST_TEXT = (
    "\u0410\u043a\u0442\u0443\u0430\u043b\u044c\u043d\u044b\u0439 "
    "\u043f\u0440\u0430\u0439\u0441 \u043c\u043e\u0436\u043d\u043e "
    "\u0441\u043a\u0430\u0447\u0430\u0442\u044c \u043f\u043e "
    f"\u0441\u0441\u044b\u043b\u043a\u0435:\n{PRICE_LIST_URL}"
)
PRICE_LIST_BUTTON_TEXT = "\u0421\u043a\u0430\u0447\u0430\u0442\u044c \u043f\u0440\u0430\u0439\u0441"


def _price_list_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=PRICE_LIST_BUTTON_TEXT,
                    url=PRICE_LIST_URL,
                )
            ]
        ]
    )


def _url_button_keyboard(text: str, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, url=url)]]
    )


def _normalize_query(query: str) -> str:
    return " ".join(query.strip().split())


def _format_retail_price_line(product: CatalogProduct) -> str | None:
    display = (product.retail_price_display or "").strip()
    if display:
        return f"Розничная цена: {display}"

    if product.retail_price is None:
        return None

    try:
        value = Decimal(product.retail_price)
    except (InvalidOperation, TypeError, ValueError):
        return None

    sign = "-" if value < 0 else ""
    absolute = abs(value)
    quantized = f"{absolute:.2f}"
    integer_part, _, fraction = quantized.partition(".")
    grouped = f"{int(integer_part):,}".replace(",", " ")
    if fraction.rstrip("0"):
        formatted = f"{grouped},{fraction.rstrip('0')}"
    else:
        formatted = grouped
    return f"Розничная цена: {sign}{formatted} ₽"


def _append_optional_field(lines: list[str], label: str, value: str | None) -> None:
    if value is None:
        return
    text = str(value).strip()
    if not text:
        return
    lines.append(f"{label}: {text}")


def _format_exact_product_card(product: CatalogProduct) -> str:
    lines = ["✅ Товар найден", "", product.title]
    _append_optional_field(lines, "Код", product.code)
    _append_optional_field(lines, "Артикул", product.article)
    _append_optional_field(lines, "Бренд", product.brand)
    _append_optional_field(lines, "Категория", product.category)
    price_line = _format_retail_price_line(product)
    if price_line:
        lines.append(price_line)

    lines.append("")
    lines.append("Наличие:")
    if product.warehouses:
        for warehouse in product.warehouses:
            label = (warehouse.label or "").strip()
            name = (warehouse.name or "").strip()
            if name and label:
                lines.append(f"• {name} — {label}")
            elif name:
                lines.append(f"• {name}")
            elif label:
                lines.append(f"• {label}")
    else:
        label = (product.availability.label if product.availability else None) or ""
        label = label.strip()
        if label:
            lines.append(f"• {label}")

    return "\n".join(lines).strip()


def _format_compact_product_card(index: int, product: CatalogProduct) -> str:
    lines = [f"{index}. {product.title}", ""]
    _append_optional_field(lines, "Код", product.code)
    _append_optional_field(lines, "Артикул", product.article)
    _append_optional_field(lines, "Бренд", product.brand)
    _append_optional_field(lines, "Категория", product.category)
    price_line = _format_retail_price_line(product)
    if price_line:
        lines.append(price_line)

    availability_label = ""
    if product.availability and product.availability.label:
        availability_label = product.availability.label.strip()
    if availability_label:
        lines.append(f"Наличие: {availability_label}")

    return "\n".join(lines).strip()


def _record_b2b_fallback() -> None:
    try:
        from app.observability.prometheus_metrics import b2b_catalog_search_fallback_total

        b2b_catalog_search_fallback_total.inc()
    except Exception:  # pragma: no cover
        logger.debug("B2B fallback metric skipped", exc_info=True)


def _is_max_event(event: Message | CallbackQuery) -> bool:
    return getattr(event, "platform", "") == "max"


def _plain_text_for_max(text: str) -> str:
    text = text.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    return _HTML_TAG_RE.sub("", text)


async def _answer(message: Message, text: str, **kwargs) -> None:
    if _is_max_event(message):
        text = _plain_text_for_max(text)
        kwargs.pop("parse_mode", None)
    await message.answer(text, **kwargs)


async def _answer_document(message: Message, document: FSInputFile, **kwargs) -> None:
    caption = kwargs.get("caption")
    if caption and _is_max_event(message):
        kwargs["caption"] = _plain_text_for_max(caption)
    await message.answer_document(document, **kwargs)


def _main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="Инструкция"),
                KeyboardButton(text=PRICE_LIST_BUTTON_TEXT),
                KeyboardButton(text="История запросов"),
            ]
        ],
        resize_keyboard=True,
    )


def _main_menu_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Инструкция", callback_data="menu:instruction")],
            [InlineKeyboardButton(text=PRICE_LIST_BUTTON_TEXT, url=PRICE_LIST_URL)],
            [InlineKeyboardButton(text="История запросов", callback_data="menu:history")],
        ]
    )


async def _get_last_updated_label() -> str:
    async with async_session_maker() as session:
        result = await session.execute(select(OstatkiMeta.last_updated).limit(1))
        updated_at = result.scalar()

    if not updated_at:
        return "неизвестно"

    return updated_at.astimezone(ZoneInfo("Europe/Moscow")).strftime("%d.%m.%Y %H:%M:%S")


def register_handlers(router) -> None:
    @router.message(Command("start"))
    async def handle_start(message: Message) -> None:
        await _answer(
            message,
            "<b>Добро пожаловать в бот остатков!</b>\n\n"
            "Введите название товара или артикул, и я покажу актуальные остатки по складам.\n\n"
            "Команды в меню:\n"
            "• <b>Инструкция</b>\n"
            f"• <b>{PRICE_LIST_BUTTON_TEXT}</b>\n"
            "• <b>История запросов</b>",
            reply_markup=_main_menu_inline_keyboard() if _is_max_event(message) else _main_menu_keyboard(),
        )

    @router.message(F.text.casefold() == "инструкция")
    async def handle_instruction(message: Message) -> None:
        await _send_instruction(message)

    @router.message(F.text.casefold() == "полный отчет xlsx")
    @router.message(F.text.casefold() == "\u0441\u043a\u0430\u0447\u0430\u0442\u044c \u043f\u0440\u0430\u0439\u0441")
    async def handle_full_report(message: Message) -> None:
        await _answer(message, PRICE_LIST_TEXT, reply_markup=_price_list_keyboard())
        return

        # Legacy XLSX generation is intentionally kept below for possible reuse.
        # It is disabled because the current flow sends a static price-list link.
        async with async_session_maker() as session:
            result = await session.execute(WarehouseStocks.__table__.select())
            rows = result.fetchall()

        if not rows:
            await _answer(message, "Нет данных для отчета.")
            return

        all_cities = sorted({row.sklad for row in rows})
        grouped: dict[tuple, dict[str, str]] = {}

        for row in rows:
            key = (row.vid, row.name, row.price, row.brend, row.kod, row.articul)
            grouped.setdefault(key, {city: "" for city in all_cities})
            grouped[key][row.sklad] = format_stock_quantity(row.ostatok)

        data = []
        for key, city_stocks in grouped.items():
            row_data = {
                "Вид номенклатуры": key[0],
                "Наименование": key[1],
                "Розничная цена (₽)": key[2],
                "Бренд": key[3],
                "Код": key[4],
                "Артикул": key[5],
            }
            row_data.update(city_stocks)
            data.append(row_data)

        latest_date = await _get_last_updated_label()
        safe_date = latest_date.replace(":", "-").replace(" ", "_")
        file_path = f"report_{safe_date}.xlsx"

        try:
            pd.DataFrame(data).to_excel(file_path, index=False)

            wb = load_workbook(file_path)
            ws = wb.active
            ws["A1"] = f"Актуальность остатков: {latest_date}"
            fill = PatternFill(start_color="FFFACD", end_color="FFFACD", fill_type="solid")

            for col in ws.iter_cols(min_row=1, max_row=1):
                header = col[0].value
                col_letter = col[0].column_letter
                if header in ["Вид номенклатуры", "Наименование", "Бренд"]:
                    ws.column_dimensions[col_letter].width = 40
                elif header in ["Код", "Артикул"]:
                    ws.column_dimensions[col_letter].width = 20
                elif str(header).startswith("Розничная"):
                    ws.column_dimensions[col_letter].width = 18
                else:
                    ws.column_dimensions[col_letter].width = 15
                    col[0].fill = fill

            wb.save(file_path)
            await _answer_document(
                message,
                FSInputFile(file_path),
                caption="Полный отчет по складам",
            )
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

    @router.message(F.text.casefold() == "история запросов")
    async def handle_history_request(message: Message) -> None:
        user_id = message.from_user.id
        history = await get_user_query_history(user_id)
        if not history:
            await _answer(message, "История пуста.")
            return

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=query, callback_data=f"history:{query}")]
                for query in history[:5]
            ]
        )
        await _answer(message, "Выберите запрос из истории:", reply_markup=keyboard)

    @router.callback_query(F.data.startswith("history:"))
    async def handle_history_callback(callback: CallbackQuery) -> None:
        query = callback.data.replace("history:", "", 1)
        await callback.answer("Ищу...")
        await _send_search_results(callback.message, callback.from_user.id, query)

    @router.callback_query(F.data == "menu:instruction")
    async def handle_menu_instruction(callback: CallbackQuery) -> None:
        await callback.answer()
        await _send_instruction(callback.message, reply_markup=_main_menu_inline_keyboard())

    @router.callback_query(F.data == "menu:history")
    async def handle_menu_history(callback: CallbackQuery) -> None:
        await callback.answer()
        history = await get_user_query_history(callback.from_user.id)
        if not history:
            await _answer(callback.message, "История пуста.", reply_markup=_main_menu_inline_keyboard())
            return

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=query, callback_data=f"history:{query}")]
                for query in history[:5]
            ]
        )
        await _answer(callback.message, "Выберите запрос из истории:", reply_markup=keyboard)

    @router.callback_query(F.data == "menu:report")
    async def handle_menu_report(callback: CallbackQuery) -> None:
        await callback.answer()
        await handle_full_report(callback.message)

    @router.message(F.text)
    async def handle_user_query(message: Message) -> None:
        await _send_search_results(message, message.from_user.id, message.text.strip())


async def _send_search_results(message: Message, user_id: int, query: str) -> None:
    await log_user_query(user_id, query)
    normalized_query = _normalize_query(query)

    if settings.B2B_CATALOG_SEARCH_ENABLED:
        try:
            response = await b2b_search_products(normalized_query, limit=5)
            await _send_b2b_search_results(message, normalized_query, response)
            return
        except CatalogValidationError:
            await _answer(
                message,
                "Введите не менее 3 символов: название, код или артикул товара.",
            )
            return
        except (
            CatalogConfigurationError,
            CatalogUnauthorizedError,
            CatalogRateLimitError,
            CatalogUnavailableError,
            CatalogResponseError,
            CatalogClientError,
        ) as exc:
            _record_b2b_fallback()
            logger.warning(
                "B2B search fallback to local search_source=local_fallback "
                "query_length=%s error_type=%s",
                len(normalized_query),
                type(exc).__name__,
            )
            try:
                await _send_local_search_results(
                    message,
                    query,
                    search_source="local_fallback",
                )
            except Exception:
                logger.exception(
                    "Local search fallback failed search_source=local_fallback "
                    "query_length=%s",
                    len(normalized_query),
                )
                await _answer(
                    message,
                    "Сервис поиска временно недоступен. Попробуйте ещё раз немного позже.",
                )
            return

    await _send_local_search_results(message, query, search_source="local")


async def _send_b2b_search_results(
    message: Message,
    query: str,
    response: CatalogSearchResponse,
) -> None:
    products = response.products[:5]

    if not products:
        keyboard = None
        if response.catalog_search_url:
            keyboard = _url_button_keyboard(
                "Открыть поиск в каталоге",
                response.catalog_search_url,
            )
        await _answer(
            message,
            (
                f"По запросу «{query}» ничего не найдено.\n\n"
                "Проверьте код, артикул или попробуйте часть названия."
            ),
            reply_markup=keyboard,
        )
        return

    if response.exact_match:
        product = products[0]
        keyboard = None
        if product.product_url:
            keyboard = _url_button_keyboard("Открыть товар", product.product_url)
        await _answer(message, _format_exact_product_card(product), reply_markup=keyboard)
        return

    if len(products) == 1:
        intro = f"Найдено товаров: 1."
    elif len(products) < 5:
        intro = (
            f"По запросу «{query}» найдено несколько товаров.\n"
            f"Найдено товаров: {len(products)}."
        )
    else:
        intro = (
            f"По запросу «{query}» найдено несколько товаров.\n"
            "Показываю первые 5."
        )
    await _answer(message, intro)

    for index, product in enumerate(products, start=1):
        keyboard = None
        if product.product_url:
            keyboard = _url_button_keyboard("Открыть товар", product.product_url)
        await _answer(
            message,
            _format_compact_product_card(index, product),
            reply_markup=keyboard,
        )

    if response.catalog_search_url:
        await _answer(
            message,
            "Показать всё в каталоге",
            reply_markup=_url_button_keyboard(
                "Показать всё в каталоге",
                response.catalog_search_url,
            ),
        )


async def _send_local_search_results(
    message: Message,
    query: str,
    *,
    search_source: str,
) -> None:
    logger.info(
        "Local catalog search started search_source=%s query_length=%s",
        search_source,
        len(query),
    )
    items = await find_products_by_query(query)

    if items:
        latest_date = await _get_last_updated_label()
        logger.info(
            "Local catalog search ok search_source=%s result_count=%s",
            search_source,
            len(items),
        )

        if len(items) > 20:
            file_name = f"Результаты_{query.replace(' ', '_')}.txt"
            try:
                lines = []
                for product in items.values():
                    text = (
                        f"{product['name']}\n"
                        f"  Вид: {product['vid']}\n"
                        f"  Бренд: {product['brend']}\n"
                        f"  Артикул: {product['articul']}\n"
                        f"  Код: {product['kod']}\n"
                        f"  Цена: {product['price']} ₽\n"
                        "  Наличие:\n"
                    )
                    for stock in product["stocks"]:
                        text += f"    - {stock['sklad']}: {format_stock_quantity(stock['ostatok'])}\n"
                    text += "\n"
                    lines.append(text)

                with open(file_name, "w", encoding="utf-8") as file:
                    file.write("".join(lines))

                await _answer_document(
                    message,
                    FSInputFile(file_name),
                    caption=f"Найдено {len(items)} товаров по запросу: {query}",
                )
            finally:
                if os.path.exists(file_name):
                    os.remove(file_name)
            return

        for product in items.values():
            sklad_lines = "\n".join(
                f"• {stock['sklad']}: <b>{format_stock_quantity(stock['ostatok'])}</b>"
                for stock in product["stocks"]
            )
            text = (
                f"📦 <b>{product['name']} | {product['kod']}</b>\n"
                f"🏷️ <b>Бренд:</b> {product['brend']}\n"
                f"📌 <b>Вид:</b> {product['vid']}\n"
                f"🔖 <b>Артикул:</b> {product['articul'] or '-'}\n"
                f"💰 <b>Цена:</b> {product['price']} ₽\n\n"
                f"🚚 <b>Остатки по складам:</b>\n{sklad_lines}\n\n"
                f"🕒 <i>Актуально на: {latest_date}</i> по МСК"
            )
            await _answer(message, text)
        return

    fuzzy_results = await fuzzy_find_products(query)
    filtered = [result for result in fuzzy_results if result["score"] > 70]

    if not filtered:
        logger.info(
            "Local catalog search empty search_source=%s query_length=%s",
            search_source,
            len(query),
        )
        await _answer(message, "Товар не найден. Попробуйте уточнить запрос.")
        return

    logger.info(
        "Local catalog fuzzy ok search_source=%s result_count=%s",
        search_source,
        len(filtered[:5]),
    )
    text = f"Товар <code>{query}</code> не найден, но найдены похожие позиции:\n\n"
    for result in filtered[:5]:
        score = int(result["score"])
        text += (
            f"📦 <b>{result['name']}</b>\n"
            f"• Код: {result['kod']}\n"
            f"• Бренд: {result['brend']} | Вид: {result['vid']}\n"
            f"• Цена: {result['price']} ₽ | Наличие: {format_stock_quantity(result['ostatok'])} | "
            f"Склад: {result['sklad']}\n"
            f"📈 Совпадение: {score}%\n\n"
        )

    await _answer(message, text)


async def _send_instruction(message: Message, **kwargs) -> None:
    text = (
        "<b>Инструкция по использованию</b>\n\n"
        "Введите <b>название товара</b> или <b>артикул</b>, например:\n"
        "<code>CM-107</code>\n"
        "<code>ОМ-350</code>\n\n"
        "Можно искать по конкретному складу, указав город перед товаром:\n"
        "<code>Москва CM-107</code>\n"
        "<code>Екатеринбург ОМ-350</code>\n\n"
        "История запросов хранит последние обращения и позволяет быстро повторить поиск."
    )
    await _answer(message, text, **kwargs)
