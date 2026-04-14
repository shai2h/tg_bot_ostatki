from __future__ import annotations

import logging
from dataclasses import dataclass

from app.bot.handlers import register_handlers as register_warehouse_handlers
from app.config import settings

logger = logging.getLogger(__name__)

try:
    from obabot import create_bot
except ImportError as exc:  # pragma: no cover
    create_bot = None
    _obabot_import_error = exc
else:
    _obabot_import_error = None


@dataclass(slots=True)
class BotRuntime:
    bot: object | None
    dp: object | None
    router: object | None

    @property
    def enabled(self) -> bool:
        return self.bot is not None and self.dp is not None

    async def start_polling(self) -> None:
        if not self.enabled:
            logger.warning("Bot runtime is disabled: no tokens or obabot unavailable")
            return
        await self.dp.start_polling(self.bot)

    async def stop(self) -> None:
        if self.bot is None:
            return
        session = getattr(self.bot, "session", None)
        if session is not None:
            await session.close()


def _build_bot_with_fallbacks():
    if create_bot is None:
        raise RuntimeError(
            "obabot is required for MAX integration. Install it with `pip install obabot`."
        ) from _obabot_import_error

    candidates = [
        {"max_token": settings.MAX_TOKEN, "tg_token": settings.BOT_TOKEN},
        {"max_token": settings.MAX_TOKEN},
        {"tg_token": settings.BOT_TOKEN},
    ]

    last_error: Exception | None = None
    for kwargs in candidates:
        kwargs = {key: value for key, value in kwargs.items() if value}
        if not kwargs:
            continue
        try:
            result = create_bot(**kwargs)
            if isinstance(result, tuple) and len(result) == 3:
                return result
            if isinstance(result, tuple) and len(result) == 2:
                bot, dp = result
                return bot, dp, None
            raise RuntimeError("Unexpected create_bot() return signature")
        except TypeError as exc:
            last_error = exc

    if last_error is not None:
        raise RuntimeError("Unable to initialize obabot with the available tokens") from last_error
    return None, None, None


_runtime: BotRuntime | None = None


async def get_bot_runtime() -> BotRuntime:
    global _runtime

    if _runtime is not None:
        return _runtime

    if not settings.MAX_TOKEN and not settings.BOT_TOKEN:
        _runtime = BotRuntime(bot=None, dp=None, router=None)
        return _runtime

    bot, dp, router = _build_bot_with_fallbacks()
    if dp is not None:
        register_warehouse_handlers(dp)
    _runtime = BotRuntime(bot=bot, dp=dp, router=router)
    return _runtime
