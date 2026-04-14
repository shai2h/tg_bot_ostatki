from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from starlette.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.ostatki import router as ostatki_router
from app.bot.main import get_bot_runtime
from app.bot.max_client import answer_callback, ensure_webhook_subscription, resolve_webhook_recipient, send_message
from app.bot.shared import call_process_message, render_markdown_reply
from app.config import settings

logger = logging.getLogger(__name__)


class ProcessMessageRequest(BaseModel):
    text: str
    user_id: str | None = None
    platform: str = "max"


class MaxWebhookMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path != settings.webhook_path:
            return await call_next(request)

        if settings.MAX_WEBHOOK_SECRET:
            provided_secret = request.headers.get("X-Max-Bot-Api-Secret")
            if provided_secret != settings.MAX_WEBHOOK_SECRET:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Invalid MAX webhook secret"},
                )

        return await call_next(request)


async def _handle_start_event(update: dict[str, Any]) -> None:
    recipient = resolve_webhook_recipient(update)
    text = (
        "### Max Bot\n"
        "**Бот подключён по webhook.**\n\n"
        "Отправьте текст, и я отвечу эхом вместе с результатом `/process_message`."
    )
    await send_message(recipient, text)


async def _handle_message_event(update: dict[str, Any]) -> None:
    message = update.get("message") or update.get("payload", {}).get("message") or {}
    user_text = ((message.get("body") or {}).get("text") or "").strip()
    if not user_text:
        return

    processed = await call_process_message(
        user_text,
        user_id=(message.get("sender") or {}).get("user_id"),
        platform="max",
    )
    reply_text = render_markdown_reply(user_text, processed)
    await send_message(resolve_webhook_recipient(update), reply_text)


async def _handle_callback_event(update: dict[str, Any]) -> None:
    callback = update.get("callback") or update.get("payload") or {}
    callback_id = callback.get("callback_id") or update.get("callback_id")
    if not callback_id:
        raise HTTPException(status_code=400, detail="callback_id is required")

    payload = callback.get("payload") or "repeat_last"
    processed = await call_process_message(
        payload,
        user_id=((callback.get("message") or {}).get("sender") or {}).get("user_id"),
        platform="max-callback",
    )
    reply_text = render_markdown_reply(payload, processed)
    await answer_callback(callback_id, reply_text)


async def dispatch_max_webhook(update: dict[str, Any]) -> None:
    update_type = update.get("update_type") or update.get("type") or update.get("event")
    if update_type == "bot_started":
        await _handle_start_event(update)
        return
    if update_type == "message_callback":
        await _handle_callback_event(update)
        return
    if update_type == "message_created":
        await _handle_message_event(update)
        return

    logger.info("Skipping unsupported MAX update type: %s", update_type)


@asynccontextmanager
async def lifespan(_: FastAPI):
    runtime = None
    polling_task: asyncio.Task | None = None

    if settings.BOT_RUN_MODE == "polling":
        runtime = await get_bot_runtime()
        if runtime.enabled:
            polling_task = asyncio.create_task(runtime.start_polling())
    elif settings.BOT_RUN_MODE == "webhook":
        try:
            await ensure_webhook_subscription()
        except Exception:
            logger.exception("Failed to register MAX webhook subscription")

    try:
        yield
    finally:
        if polling_task is not None:
            polling_task.cancel()
            try:
                await polling_task
            except asyncio.CancelledError:
                pass
        if runtime is not None:
            await runtime.stop()


app = FastAPI(
    title="Остатки API + MAX Bot",
    description="FastAPI-приложение с интеграцией Max через obabot и webhook.",
    version="2.0.0",
    lifespan=lifespan,
)
app.add_middleware(MaxWebhookMiddleware)
app.include_router(ostatki_router)


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/process_message")
async def process_message(payload: ProcessMessageRequest) -> dict[str, Any]:
    normalized_text = " ".join(payload.text.strip().split())
    return {
        "reply": (
            f"FastAPI обработал сообщение от {payload.platform} "
            f"в {datetime.now(timezone.utc).isoformat()}"
        ),
        "normalized_text": normalized_text.lower(),
        "metadata": {
            "length": len(normalized_text),
            "user_id": payload.user_id,
            "platform": payload.platform,
        },
    }


@app.post("/webhook")
async def max_webhook(request: Request) -> dict[str, bool]:
    payload = await request.json()
    await dispatch_max_webhook(payload)
    return {"ok": True}
