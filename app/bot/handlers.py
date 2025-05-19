from aiogram import Router, F
from aiogram.types import Message
from app.services.search import find_products_by_query, log_user_query, get_user_query_history

router = Router()

def register_handlers(dp):
    dp.include_router(router)

@router.message(F.text)
async def handle_user_query(message: Message):
    query = message.text.strip()
    user_id = message.from_user.id

    await log_user_query(user_id, query)

    if query.lower() == "история":
        history = await get_user_query_history(user_id)
        if not history:
            await message.answer("\U0001F4DD История пуста.")
            return
        response = "\U0001F4D1 <b>История ваших запросов:</b>\n"
        for q in history:
            response += f"• {q}\n"
        await message.answer(response)
        return

    items = await find_products_by_query(query)
    if not items:
        await message.answer("\U0001F6D1 Товар не найден. Попробуйте уточнить запрос.")
        return

    for kod, product in items.items():
        text = (
            f"\U0001F537 <b>{product['name']}</b>\n"
            f"🔹 Вид: {product['vid']}\n"
            f"🔹 Бренд: {product['brend']}\n"
            f"🔹 Артикул: {product['articul']}\n"
            f"🔹 Код: {product['kod']}\n"
            f"🔹 Цена: {product['price']} ₽\n"
            f"\n\U0001F69A Наличие по складам:\n"
        )
        for stock in product['stocks']:
            text += f"🔸 {stock['sklad']}: {stock['ostatok']}\n"

        await message.answer(text)
