from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings


@dataclass(slots=True)
class ProcessMessageResult:
    reply: str
    normalized_text: str
    metadata: dict[str, Any]


def build_inline_keyboard() -> InlineKeyboardMarkup:
    docs_url = f"{settings.api_base_url}/docs"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Повторить ответ", callback_data="repeat_last")],
            [InlineKeyboardButton(text="Открыть API", url=docs_url)],
        ]
    )


def build_max_inline_keyboard() -> list[dict[str, Any]]:
    docs_url = f"{settings.api_base_url}/docs"
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    [
                        {
                            "type": "callback",
                            "text": "Повторить ответ",
                            "payload": "repeat_last",
                        }
                    ],
                    [
                        {
                            "type": "link",
                            "text": "Открыть API",
                            "url": docs_url,
                        }
                    ],
                ]
            },
        }
    ]


def render_markdown_reply(user_text: str, processed: ProcessMessageResult) -> str:
    return (
        "### Max Bot\n"
        f"**Эхо:** `{user_text}`\n\n"
        f"**FastAPI:** {processed.reply}\n"
        f"**Нормализовано:** `{processed.normalized_text}`"
    )


def render_html_reply(user_text: str, processed: ProcessMessageResult) -> str:
    return (
        "<b>Max Bot</b>\n"
        f"<b>Эхо:</b> <code>{user_text}</code>\n\n"
        f"<b>FastAPI:</b> {processed.reply}\n"
        f"<b>Нормализовано:</b> <code>{processed.normalized_text}</code>"
    )


async def call_process_message(
    text: str,
    *,
    user_id: int | str | None,
    platform: str,
) -> ProcessMessageResult:
    payload = {
        "text": text,
        "user_id": str(user_id) if user_id is not None else None,
        "platform": platform,
    }
    url = f"{settings.api_base_url}{settings.PROCESS_MESSAGE_ENDPOINT}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()

    return ProcessMessageResult(
        reply=data["reply"],
        normalized_text=data["normalized_text"],
        metadata=data.get("metadata", {}),
    )
