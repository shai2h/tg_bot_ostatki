from __future__ import annotations

import logging
from dataclasses import dataclass

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.bot.handlers import register_handlers as register_warehouse_handlers
from app.bot.health import bot_health
from app.config import settings

logger = logging.getLogger(__name__)

try:
    from obabot import create_bot
except ImportError as exc:  # pragma: no cover
    create_bot = None
    _obabot_import_error = exc
else:
    _obabot_import_error = None


class BotHealthMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        if isinstance(event, (Message, CallbackQuery)):
            bot_health.record_incoming()
        try:
            result = await handler(event, data)
            if isinstance(event, (Message, CallbackQuery)):
                bot_health.record_successful_send()
            return result
        except Exception as exc:
            bot_health.record_error(exc)
            raise


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
        logger.info("Bot polling loop started mode=polling")
        try:
            await self.dp.start_polling(self.bot)
        except Exception as exc:
            bot_health.record_error(exc)
            logger.exception("Bot polling loop failed")
            raise

    async def stop(self) -> None:
        if self.bot is None:
            return
        session = getattr(self.bot, "session", None)
        if session is not None:
            await session.close()
        bot_health.mark_runtime_stopped()
        logger.info("Bot runtime stopped")


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


def _try_register_middleware_on_observer(
    observer: object,
    middleware: BotHealthMiddleware,
    *,
    observer_name: str,
    owner_label: str,
) -> bool:
    middleware_method = getattr(observer, "middleware", None)
    if not callable(middleware_method):
        return False

    middleware_method(middleware)
    logger.info(
        "Health middleware registered on %s.%s (%s)",
        owner_label,
        observer_name,
        type(observer).__name__,
    )
    return True


def _register_health_middleware(dp: object | None, router: object | None = None) -> None:
    middleware = BotHealthMiddleware()
    registered = False

    if router is not None:
        for observer_name in ("message", "callback_query"):
            observer = getattr(router, observer_name, None)
            if observer is not None and _try_register_middleware_on_observer(
                observer,
                middleware,
                observer_name=observer_name,
                owner_label="router",
            ):
                registered = True

    if not registered and dp is not None:
        for observer_name in ("message", "callback_query"):
            observer = getattr(dp, observer_name, None)
            if observer is not None and _try_register_middleware_on_observer(
                observer,
                middleware,
                observer_name=observer_name,
                owner_label="dispatcher",
            ):
                registered = True

    if not registered:
        logger.warning(
            "Health middleware was not registered: dispatcher type=%s, router type=%s "
            "do not expose observer.middleware API",
            type(dp).__name__ if dp is not None else "None",
            type(router).__name__ if router is not None else "None",
        )


async def get_bot_runtime() -> BotRuntime:
    global _runtime

    if _runtime is not None:
        return _runtime

    if not settings.MAX_TOKEN and not settings.BOT_TOKEN:
        _runtime = BotRuntime(bot=None, dp=None, router=None)
        return _runtime

    bot, dp, router = _build_bot_with_fallbacks()
    handlers_registered = False
    if router is not None:
        register_warehouse_handlers(router)
        handlers_registered = True
    elif dp is not None:
        logger.warning("obabot router is missing; warehouse handlers were not registered")

    if dp is not None or router is not None:
        _register_health_middleware(dp, router)

    _runtime = BotRuntime(bot=bot, dp=dp, router=router)
    bot_health.mark_runtime_started(
        settings.BOT_RUN_MODE,
        handlers_registered=handlers_registered,
    )
    return _runtime
