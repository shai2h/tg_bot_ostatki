import asyncio
import logging
from datetime import datetime

import httpx

from app.bot.max_client import MAX_API_BASE_URL
from app.config import settings

logger = logging.getLogger(__name__)


class MaxMonitorNotifier:
    def __init__(self):
        self.bot_token = settings.MONITOR_BOT_TOKEN
        self.chat_id = settings.MONITOR_CHAT_ID

    def _missing_settings(self) -> list[str]:
        missing = []
        if not self.bot_token:
            missing.append("MONITOR_BOT_TOKEN")
        if not self.chat_id:
            missing.append("MONITOR_CHAT_ID")
        return missing

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self.bot_token or "",
            "Content-Type": "application/json",
        }

    async def send_message(self, message: str, parse_mode: str = "HTML") -> bool:
        missing = self._missing_settings()
        if missing:
            logger.warning(
                "MAX monitoring notification is skipped: %s is not configured",
                ", ".join(missing),
            )
            return False

        body = {
            "text": message,
            "format": "html" if parse_mode.upper() == "HTML" else "markdown",
        }

        try:
            async with httpx.AsyncClient(base_url=MAX_API_BASE_URL, timeout=10.0) as client:
                response = await client.post(
                    "/messages",
                    headers=self._headers(),
                    params={"chat_id": self.chat_id},
                    json=body,
                )

            if 200 <= response.status_code < 300:
                logger.info("Monitoring notification sent to MAX")
                return True

            logger.error(
                "MAX monitoring notification failed: status=%s body=%s",
                response.status_code,
                response.text,
            )
            return False
        except (asyncio.TimeoutError, httpx.TimeoutException):
            logger.error("Timeout while sending monitoring notification to MAX")
            return False
        except Exception:
            logger.exception("Unexpected error while sending monitoring notification to MAX")
            return False

    async def send_alert(self, message: str) -> bool:
        timestamp = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        formatted_message = f"""
<b>BOT-OSTATKI ALERT</b>

<b>Time:</b> {timestamp}
<b>Message:</b> {message}

#ostatki_bot
        """.strip()

        return await self.send_message(formatted_message)

    async def send_recovery(self, message: str) -> bool:
        timestamp = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        formatted_message = f"""
<b>BOT-OSTATKI RECOVERED</b>

<b>Time:</b> {timestamp}
<b>Message:</b> {message}

#ostatki_bot
        """.strip()

        return await self.send_message(formatted_message)

    async def send_info(self, message: str) -> bool:
        timestamp = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        formatted_message = f"""
<b>BOT-OSTATKI INFO</b>

<b>Time:</b> {timestamp}
<b>Message:</b> {message}

#ostatki_bot
        """.strip()

        return await self.send_message(formatted_message)

    async def send_startup_notification(self) -> bool:
        message = """
<b>BOT-OSTATKI MONITORING STARTED</b>

Monitoring for the stock bot is running.

<b>Components:</b>
- 1C API updates
- bot availability

#ostatki_bot
        """.strip()

        return await self.send_message(message)

    async def send_shutdown_notification(self) -> bool:
        message = """
<b>BOT-OSTATKI MONITORING STOPPED</b>

Monitoring for the stock bot has stopped.

#ostatki_bot
        """.strip()

        return await self.send_message(message)

    async def test_connection(self) -> bool:
        return await self.send_info("MAX monitoring notification test")
