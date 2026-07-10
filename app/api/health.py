from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select
from starlette.responses import JSONResponse

from app.bot.health import bot_health
from app.config import settings
from app.db.database import async_session_maker
from app.services.ostatki_sync import count_warehouse_stock_rows, ping_database
from app.warehouse_stock.models import OstatkiMeta

router = APIRouter(tags=["health"])


class LiveHealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadyHealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    database: Literal["ok"] = "ok"


class OneCHealthResponse(BaseModel):
    status: Literal["ok", "stale", "missing"]
    last_updated: datetime | None = None
    seconds_since_update: int | None = None
    row_count: int | None = None
    stale_after_seconds: int


class BotHealthResponse(BaseModel):
    runtime_running: bool
    mode: str
    handlers_registered: bool
    last_incoming_event_at: str | None = None
    last_successful_send_at: str | None = None
    last_error: str | None = None


@router.get("/health/live", response_model=LiveHealthResponse)
async def health_live() -> LiveHealthResponse:
    return LiveHealthResponse()


@router.get("/health/ready", response_model=ReadyHealthResponse)
async def health_ready() -> ReadyHealthResponse | JSONResponse:
    try:
        async with async_session_maker() as session:
            await ping_database(session)
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "database": "unavailable"},
        )
    return ReadyHealthResponse()


@router.get("/health/1c", response_model=OneCHealthResponse)
async def health_one_c() -> OneCHealthResponse:
    stale_after = settings.ONE_C_STALE_AFTER_SECONDS
    async with async_session_maker() as session:
        result = await session.execute(
            select(OstatkiMeta.last_updated).where(OstatkiMeta.id == 1)
        )
        last_updated = result.scalar_one_or_none()
        row_count = await count_warehouse_stock_rows(session)

    if last_updated is None:
        return OneCHealthResponse(
            status="missing",
            last_updated=None,
            seconds_since_update=None,
            row_count=row_count,
            stale_after_seconds=stale_after,
        )

    now = datetime.now(timezone.utc)
    if last_updated.tzinfo is None:
        last_updated_utc = last_updated.replace(tzinfo=timezone.utc)
    else:
        last_updated_utc = last_updated.astimezone(timezone.utc)

    seconds_since = int((now - last_updated_utc).total_seconds())
    status: Literal["ok", "stale"] = (
        "stale" if seconds_since > stale_after else "ok"
    )

    return OneCHealthResponse(
        status=status,
        last_updated=last_updated,
        seconds_since_update=seconds_since,
        row_count=row_count,
        stale_after_seconds=stale_after,
    )


@router.get("/health/bot", response_model=BotHealthResponse)
async def health_bot() -> BotHealthResponse:
    snapshot = bot_health.snapshot()
    return BotHealthResponse(**snapshot)
