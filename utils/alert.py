"""
Для оповещений об ошибках
В телеграмм забикса
"""

from aiogram import Bot
import os

alert_bot = Bot(token=os.getenv("ТОКЕН"))
channel_id = os.getenv("ID канала")

async def send_alert(text: str):
    await alert_bot.send_message(chat_id=channel_id, text=text)