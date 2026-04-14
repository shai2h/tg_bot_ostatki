from __future__ import annotations

from typing import Any

import httpx

from app.bot.shared import build_max_inline_keyboard
from app.config import settings


MAX_API_BASE_URL = "https://platform-api.max.ru"


def _headers() -> dict[str, str]:
    if not settings.MAX_TOKEN:
        raise RuntimeError("MAX_TOKEN is not configured")
    return {
        "Authorization": settings.MAX_TOKEN,
        "Content-Type": "application/json",
    }


def _resolve_recipient(message: dict[str, Any]) -> dict[str, Any]:
    recipient = message.get("recipient") or {}
    sender = message.get("sender") or {}

    if recipient.get("chat_id") is not None:
        return {"chat_id": recipient["chat_id"]}
    if recipient.get("user_id") is not None:
        return {"user_id": recipient["user_id"]}
    if sender.get("user_id") is not None:
        return {"user_id": sender["user_id"]}

    chat_id = message.get("chat_id")
    user_id = message.get("user_id")
    if chat_id is not None:
        return {"chat_id": chat_id}
    if user_id is not None:
        return {"user_id": user_id}

    raise ValueError("Cannot resolve MAX recipient from webhook payload")


async def send_message(
    recipient: dict[str, Any],
    text: str,
    *,
    markdown: bool = True,
) -> dict[str, Any]:
    body = {
        "text": text,
        "format": "markdown" if markdown else "html",
        "attachments": build_max_inline_keyboard(),
    }

    async with httpx.AsyncClient(base_url=MAX_API_BASE_URL, timeout=10.0) as client:
        response = await client.post(
            "/messages",
            headers=_headers(),
            params=recipient,
            json=body,
        )
        response.raise_for_status()
        return response.json()


async def answer_callback(callback_id: str, text: str) -> dict[str, Any]:
    body = {
        "notification": "Ответ обновлён",
        "message": {
            "text": text,
            "format": "markdown",
            "attachments": build_max_inline_keyboard(),
        },
    }

    async with httpx.AsyncClient(base_url=MAX_API_BASE_URL, timeout=10.0) as client:
        response = await client.post(
            "/answers",
            headers=_headers(),
            params={"callback_id": callback_id},
            json=body,
        )
        response.raise_for_status()
        return response.json()


async def ensure_webhook_subscription() -> dict[str, Any] | None:
    if not settings.MAX_TOKEN or not settings.MAX_WEBHOOK_URL:
        return None

    body = {
        "url": settings.MAX_WEBHOOK_URL,
        "update_types": ["message_created", "bot_started", "message_callback"],
    }
    if settings.MAX_WEBHOOK_SECRET:
        body["secret"] = settings.MAX_WEBHOOK_SECRET

    async with httpx.AsyncClient(base_url=MAX_API_BASE_URL, timeout=10.0) as client:
        response = await client.post(
            "/subscriptions",
            headers=_headers(),
            json=body,
        )
        response.raise_for_status()
        return response.json()


def resolve_webhook_recipient(update: dict[str, Any]) -> dict[str, Any]:
    message = (
        update.get("message")
        or update.get("payload", {}).get("message")
        or update.get("callback", {}).get("message")
        or {}
    )
    if message:
        return _resolve_recipient(message)

    if update.get("chat_id") is not None:
        return {"chat_id": update["chat_id"]}

    user = update.get("user") or {}
    if user.get("user_id") is not None:
        return {"user_id": user["user_id"]}

    raise ValueError("Cannot resolve MAX recipient from webhook update")
