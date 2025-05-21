import os
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, FSInputFile
from app.services.search import find_products_by_query, log_user_query, get_user_query_history
from app.db.database import async_session_maker

from app.warehouse_stock.models import WarehouseStocks

import pandas as pd

from openpyxl import load_workbook
from openpyxl.styles import PatternFill

from app.services.search import fuzzy_find_products
from app.services.search import find_products_by_text as find_products_by_query 

from collections import defaultdict

from app.bot.utils import format_stock_quantity


router = Router()

def register_handlers(dp):
    dp.include_router(router)


# Показываем главное меню
@router.message(F.text.lower() == "/start")
async def handle_start(message: Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Инструкция"), KeyboardButton(text="Полный отчет XLSX"), KeyboardButton(text="История запросов")]
        ],
        resize_keyboard=True
    )
    await message.answer(
    "<b>👋 Добро пожаловать в бота остатков!</b>\n\n"
    "🔍 Просто введите <b>название товара</b> или <b>артикул</b> — и я покажу актуальные остатки по складам.\n\n"
    "📖 Нажмите <b>Инструкция</b>, чтобы узнать как искать по складам, просматривать историю запросов и примеры ввода.\n\n"
    "📊 Кнопка <b>Полный отчет XLSX</b> — скачайте сводку остатков по всем складам в формате Excel.\n\n"
    "📌 Также доступна кнопка <b>История</b> — для быстрого доступа к последним запросам.",
    reply_markup=keyboard
)



@router.message(F.text.lower() == "инструкция")
async def handle_instruction(message: Message):
    text = (
        "<b>📌 Инструкция по использованию:</b>\n\n"
        "🔍 Введите <b>название товара</b> или <b>артикул</b>, например:\n"
        "<i>CM-107</i> или <i>ОМ-350</i>\n\n"
        "🏙️ Можно искать <b>по конкретному складу</b>. Просто добавьте название города перед товаром:\n"
        "<code>Москва CM-107</code>\n"
        "<code>Екатеринбург ОМ-350</code>\n\n"
        "📖 Бот поддерживает <b>историю запросов</b>. Нажмите кнопку <b>История</b>, чтобы увидеть последние 5 запросов и выбрать повторно.\n\n"
        "<b>🏬 Список доступных складов:</b>\n"
        "Владивосток, Волжск, Екатеринбург, Краснодар, Москва (ЦФО),\n"
        "Нижний Новгород, Новосибирск, Омск, Пермь, Пятигорск,\n"
        "Ростов-на Дону, Санкт-Петербург, Симферополь, Ставрополь,\n"
        "Тюмень, Уфа, Хабаровск, Челябинск, Ярославль\n\n"
        "✅ Ввод можно делать строчными/заглавными — это не имеет значения.\n"
        "⛔️ Обратите внимание на пробелы и точное написание, например:\n"
        "<code>CM107</code> ≠ <code>CM-107</code>\n"
    )
    await message.answer(text)


@router.message(F.text.lower() == "полный отчет xlsx")
async def handle_full_report(message: Message):
    async with async_session_maker() as session:
        result = await session.execute(WarehouseStocks.__table__.select())
        rows = result.fetchall()

        if not rows:
            await message.answer("Нет данных для отчета.")
            return

        records = []
        all_cities = set()

        for row in rows:
            all_cities.add(row.sklad)

        all_cities = sorted(all_cities)

        grouped = {}
        for row in rows:
            key = (row.vid, row.name, row.price, row.brend, row.kod, row.articul)
            if key not in grouped:
                grouped[key] = {city: "" for city in all_cities}
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

        df = pd.DataFrame(data)
        datetime_now = datetime.now().strftime("%d-%m-%Y_%H-%M-%S")
        file_path = f"report_{datetime_now}.xlsx"
        df.to_excel(file_path, index=False)

        # Настройка стилей через openpyxl
        wb = load_workbook(file_path)
        ws = wb.active
        fill = PatternFill(start_color="FFFACD", end_color="FFFACD", fill_type="solid")

        for col in ws.iter_cols(min_row=1, max_row=1):
            header = col[0].value
            col_letter = col[0].column_letter
            if header in ["Вид номенклатуры", "Наименование", "Бренд"]:
                ws.column_dimensions[col_letter].width = 30
            elif header in ["Код", "Артикул"]:
                ws.column_dimensions[col_letter].width = 20
            elif header.startswith("Розничная"):
                ws.column_dimensions[col_letter].width = 18
            else:
                ws.column_dimensions[col_letter].width = 15
                col[0].fill = fill

        wb.save(file_path)
        await message.answer_document(FSInputFile(file_path), caption="📊 Полный отчет по складам")
        
        if os.path.exists(file_path):
            os.remove(file_path)


@router.message(F.text.lower() == "история запросов")
async def handle_history_request(message: Message):
    user_id = message.from_user.id
    history = await get_user_query_history(user_id)
    if not history:
        await message.answer("\U0001F4DD История пуста.")
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=q, callback_data=f"history:{q}")]
            for q in history[:5]
        ]
    )
    await message.answer("\U0001F4D1 <b>Выберите из истории:</b>", reply_markup=keyboard)


@router.callback_query(F.data.startswith("history:"))
async def handle_history_callback(callback: CallbackQuery):
    query = callback.data.replace("history:", "")
    user_id = callback.from_user.id
    await log_user_query(user_id, query)

    await callback.answer("\u23F3 Поиск...", show_alert=False)

    items = await find_products_by_query(query)
    if not items:
        await callback.message.answer("\U0001F6D1 Товар не найден. Попробуйте уточнить запрос.")
        return

    all_dates = [s['updated_at'] for p in items.values() for s in p['stocks'] if s.get('updated_at')]
    latest_date = max(all_dates).strftime("%d.%m.%Y %H:%M:%S") if all_dates else "неизвестно"


    for kod, product in items.items():
        text = (
            f"📦 <b>{product['name']}</b>\n"
            f"▫️ Вид: {product['vid']}\n"
            f"▫️ Бренд: {product['brend']}\n"
            f"▫️ Артикул: {product['articul']}\n"
            f"▫️ Код: {product['kod']}\n"
            f"▫️ Цена: {product['price']} ₽\n\n"
            f"<b>🚚 Наличие по складам:</b>\n"
        )
        for stock in product['stocks']:
            text += f"   ▫️ {stock['sklad']}: {format_stock_quantity(stock['ostatok'])}\n"


        text += f"\n📅 Актуально на: <i>{latest_date}</i> по МСК"
        await callback.message.answer(text)


@router.message(F.text)
async def handle_user_query(message: Message):
    query = message.text.strip()
    user_id = message.from_user.id

 # обычный
    await log_user_query(user_id, query)
    items = await find_products_by_query(query)

    if items:
        all_dates = [s['updated_at'] for p in items.values() for s in p['stocks'] if s.get('updated_at')]
        latest_date = max(all_dates).strftime("%d.%m.%Y %H:%M:%S") if all_dates else "неизвестно"

        for kod, product in items.items():
            sklad_lines = "\n".join(
                [f"   └ {s['sklad']}: <b>{format_stock_quantity(s['ostatok'])}</b>" for s in product["stocks"]]
            )

            text = (
                f"📦 <b>{product['name']} | {product['kod']}</b>\n"
                f"🏷️ <b>Бренд:</b> {product['brend']}\n"
                f"📌 <b>Вид:</b> {product['vid']}\n"
                f"🔖 <b>Артикул:</b> {product['articul'] or '-'}\n"
                f"💰 <b>Цена:</b> {product['price']} ₽\n\n"
                f"📦 <b>Остатки по складам:</b>\n{sklad_lines}\n\n"
                f"📅 <i>Актуально на: {latest_date}</i> по МСК"
            )
            # Если слишком много результатов — выгружаем в TXT
        if len(items) > 20:
            file_name = f"Результаты_{query.replace(' ', '_')}.txt"
            lines = []

            for kod, product in items.items():
                text = (
                    f"{product['name']}\n"
                    f"  Вид: {product['vid']}\n"
                    f"  Бренд: {product['brend']}\n"
                    f"  Артикул: {product['articul']}\n"
                    f"  Код: {product['kod']}\n"
                    f"  Цена: {product['price']} ₽\n"
                    f"  Наличие:\n"
                )
                for stock in product['stocks']:
                    text += f"    - {stock['sklad']}: {format_stock_quantity(stock['ostatok'])}\n"
                text += "\n"
                lines.append(text)

            with open(file_name, "w", encoding="utf-8") as f:
                f.write("".join(lines))

            await message.answer_document(FSInputFile(file_name), caption=f"📦 Найдено {len(items)} товаров по запросу: {query}")
            if os.path.exists(file_name):
                os.remove(file_name)
            return
        else:
            all_dates = [s['updated_at'] for p in items.values() for s in p['stocks'] if s.get('updated_at')]
            latest_date = max(all_dates).strftime("%d.%m.%Y %H:%M:%S") if all_dates else "неизвестно"


            for kod, product in items.items():
                text = (
                    f"📦 <b>{product['name']}</b>\n"
                    f"▫️ Вид: {product['vid']}\n"
                    f"▫️ Бренд: {product['brend']}\n"
                    f"▫️ Артикул: {product['articul']}\n"
                    f"▫️ Код: {product['kod']}\n"
                    f"▫️ Цена: {product['price']} ₽\n\n"
                    f"<b>🚚 Наличие по складам:</b>\n"
                )
                for stock in product['stocks']:
                    text += f"    - {stock['sklad']}: {format_stock_quantity(stock['ostatok'])}\n"

                text += f"\n📅 Актуально на: <i>{latest_date}</i> по МСК"
                await message.answer(text)
            return

    # fuzzy fallback
    fuzzy_results = await fuzzy_find_products(query)
    filtered = [r for r in fuzzy_results if r["score"] > 70]

    if not filtered:
        await message.answer("🔍 Товар не найден. Попробуйте уточнить запрос.")
        return

    text = f"🔍 Товар <code>{query}</code> не найден, но найдены похожие:\n\n"
    for result in filtered[:5]:
        score = int(result["score"])
        block = (
            f"📦 <b>{result['name']}</b>\n"
            f"▫️ Код: {result['kod']}\n"
            f"▫️ Бренд: {result['brend']} | Вид: {result['vid']}\n"
            f"▫️ Цена: {result['price']} ₽ | Наличие: {format_stock_quantity(result['ostatok'])} | Склад: {result['sklad']}\n"
            f"📈 Совпадение: {score}%\n\n"
        )
        text += block

    await message.answer(text)

    


