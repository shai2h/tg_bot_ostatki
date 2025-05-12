import asyncio
from aiogram import Bot, Dispatcher
from aiogram.enums.parse_mode import ParseMode
from bot.handlers import register_handlers
from dotenv import load_dotenv
import os
from api.ostatki import router as ostatki_router


app.include_router(ostatki_router)

load_dotenv()

bot = Bot(token=os.getenv("BOT_TOKEN"), parse_mode=ParseMode.HTML)
dp = Dispatcher()

register_handlers(dp)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())


# bot/handlers.py
from aiogram import Router, F
from aiogram.types import Message
from services.product_search import get_product_response
from utils.alert import send_alert

router = Router()

def register_handlers(dp):
    dp.include_router(router)

@router.message(F.text)
async def handle_query(message: Message):
    try:
        response = await get_product_response(message.text)
        if len(response) > 4096:
            file_name = f"{message.text.upper()}_НАЛИЧИЕ.txt".replace(" ", "_")
            with open(file_name, "w", encoding="utf-8") as f:
                f.write(response)
            await message.answer_document(open(file_name, "rb"))
        else:
            await message.answer(response)
    except Exception as e:
        await send_alert(f"Ошибка при обработке запроса: {e}")
        await message.answer("\U0001F6D1 Произошла ошибка, повторите позже")