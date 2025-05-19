# bot/main.py
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.enums.parse_mode import ParseMode
from aiogram.client.default import DefaultBotProperties
from app.config import settings
from app.bot.handlers import register_handlers

bot = Bot(
    token=settings.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()
register_handlers(dp)

async def main():
    await dp.start_polling(bot)