import asyncio
import aiohttp
import logging
from datetime import datetime
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self):
        self.bot_token = settings.MONITOR_BOT_TOKEN
        self.chat_id = settings.MONITOR_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        
    async def send_message(self, message: str, parse_mode: str = "HTML") -> bool:
        """Отправка сообщения в Telegram"""
        url = f"{self.base_url}/sendMessage"
        
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        logger.info("Уведомление отправлено в Telegram")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Ошибка отправки в Telegram: {response.status} - {error_text}")
                        return False
                        
        except asyncio.TimeoutError:
            logger.error("Тайм-аут при отправке в Telegram")
            return False
        except Exception as e:
            logger.error(f"Критическая ошибка отправки в Telegram: {e}")
            return False
    
    async def send_alert(self, message: str) -> bool:
        """Отправка алерта (ошибки)"""
        timestamp = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        
        formatted_message = f"""
🚨 <b>АЛЕРТ МОНИТОРИНГА</b>

⏰ <b>Время:</b> {timestamp}
📝 <b>Сообщение:</b> {message}

#алерт #мониторинг #остатки_бот
        """.strip()
        
        return await self.send_message(formatted_message)
    
    async def send_recovery(self, message: str) -> bool:
        """Отправка уведомления о восстановлении"""
        timestamp = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        
        formatted_message = f"""
✅ <b>ВОССТАНОВЛЕНИЕ</b>

⏰ <b>Время:</b> {timestamp}
📝 <b>Сообщение:</b> {message}

#восстановление #мониторинг #остатки_бот
        """.strip()
        
        return await self.send_message(formatted_message)
    
    async def send_info(self, message: str) -> bool:
        """Отправка информационного сообщения"""
        timestamp = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        
        formatted_message = f"""
ℹ️ <b>ИНФОРМАЦИЯ</b>

⏰ <b>Время:</b> {timestamp}
📝 <b>Сообщение:</b> {message}

#информация #мониторинг #остатки_бот
        """.strip()
        
        return await self.send_message(formatted_message)
    
    async def send_startup_notification(self) -> bool:
        """Уведомление о запуске мониторинга"""
        message = """
🟢 <b>ЗАПУСК МОНИТОРИНГА</b>

Система мониторинга бота остатков запущена и готова к работе.

<b>Отслеживаемые компоненты:</b>
• API запросы от 1С
• Работа Telegram бота

#запуск #мониторинг #остатки_бот
        """.strip()
        
        return await self.send_message(message)
    
    async def send_shutdown_notification(self) -> bool:
        """Уведомление об остановке мониторинга"""
        message = """
🔴 <b>ОСТАНОВКА МОНИТОРИНГА</b>

Система мониторинга бота остатков остановлена.

#остановка #мониторинг #остатки_бот
        """.strip()
        
        return await self.send_message(message)
    
    async def test_connection(self) -> bool:
        """Тест соединения с Telegram API"""
        try:
            url = f"{self.base_url}/getMe"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        data = await response.json()
                        bot_info = data.get('result', {})
                        logger.info(f"Соединение с Telegram OK. Бот: {bot_info.get('username', 'Unknown')}")
                        return True
                    else:
                        logger.error(f"Ошибка соединения с Telegram: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"Критическая ошибка соединения с Telegram: {e}")
            return False