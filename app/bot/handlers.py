from __future__ import annotations

import os
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
from app.db.database import async_session_maker
from app.services.search import (
    find_products_by_text as find_products_by_query,
    fuzzy_find_products,
    get_user_query_history,
    log_user_query,
)
from app.warehouse_stock.models import OstatkiMeta, WarehouseStocks


def _main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="Инструкция"),
                KeyboardButton(text="Полный отчет XLSX"),
                KeyboardButton(text="История запросов"),
            ]
        ],
        resize_keyboard=True,
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
        await message.answer(
            "<b>Добро пожаловать в бот остатков!</b>\n\n"
            "Введите название товара или артикул, и я покажу актуальные остатки по складам.\n\n"
            "Команды в меню:\n"
            "• <b>Инструкция</b>\n"
            "• <b>Полный отчет XLSX</b>\n"
            "• <b>История запросов</b>",
            reply_markup=_main_menu_keyboard(),
        )

    @router.message(F.text.casefold() == "инструкция")
    async def handle_instruction(message: Message) -> None:
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
        await message.answer(text)

    @router.message(F.text.casefold() == "полный отчет xlsx")
    async def handle_full_report(message: Message) -> None:
        async with async_session_maker() as session:
            result = await session.execute(WarehouseStocks.__table__.select())
            rows = result.fetchall()

        if not rows:
            await message.answer("Нет данных для отчета.")
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
            await message.answer_document(
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
            await message.answer("История пуста.")
            return

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=query, callback_data=f"history:{query}")]
                for query in history[:5]
            ]
        )
        await message.answer("Выберите запрос из истории:", reply_markup=keyboard)

    @router.callback_query(F.data.startswith("history:"))
    async def handle_history_callback(callback: CallbackQuery) -> None:
        query = callback.data.replace("history:", "", 1)
        await callback.answer("Ищу...")
        await _send_search_results(callback.message, callback.from_user.id, query)

    @router.message(F.text)
    async def handle_user_query(message: Message) -> None:
        await _send_search_results(message, message.from_user.id, message.text.strip())


async def _send_search_results(message: Message, user_id: int, query: str) -> None:
    await log_user_query(user_id, query)
    items = await find_products_by_query(query)

    if items:
        latest_date = await _get_last_updated_label()

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

                await message.answer_document(
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
            await message.answer(text)
        return

    fuzzy_results = await fuzzy_find_products(query)
    filtered = [result for result in fuzzy_results if result["score"] > 70]

    if not filtered:
        await message.answer("Товар не найден. Попробуйте уточнить запрос.")
        return

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

    await message.answer(text)
