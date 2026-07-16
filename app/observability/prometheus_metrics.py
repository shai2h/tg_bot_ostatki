"""
Prometheus pull-metrics for tg_bot_ostatki.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest
from sqlalchemy import select

from app.bot.health import bot_health
from app.config import settings
from app.db.database import async_session_maker
from app.db.health import ping_database
from app.observability.db_metrics_cache import (
    get_db_metrics_cache,
    set_db_metrics_cache,
)
from app.warehouse_stock.models import OstatkiMeta

logger = logging.getLogger(__name__)
MOSCOW_TZ = ZoneInfo("Europe/Moscow")

# ---------------------------------------------------------------------------
# Metric definitions — add more metrics here when needed
# ---------------------------------------------------------------------------

bot_up = Gauge("bot_up", "Bot runtime status")

database_up = Gauge("database_up", "Database availability")

one_c_last_successful_update_timestamp_seconds = Gauge(
    "one_c_last_successful_update_timestamp_seconds",
    "Unix timestamp of the last successfully processed 1C stock update",
)


@dataclass(frozen=True, slots=True)
class DatabasePingCache:
    database_up: int
    fetched_at: float
    one_c_last_successful_update_timestamp_seconds: float = 0.0


_db_cache_lock = asyncio.Lock()


def _apply_bot_up() -> None:
    bot_up.set(1 if bot_health.runtime_running else 0)


def _apply_database_up(snapshot: DatabasePingCache) -> None:
    database_up.set(snapshot.database_up)
    one_c_last_successful_update_timestamp_seconds.set(
        snapshot.one_c_last_successful_update_timestamp_seconds
    )


def _to_unix_timestamp(last_updated: datetime | None) -> float:
    if last_updated is None:
        return 0.0
    if last_updated.tzinfo is None:
        last_updated = last_updated.replace(tzinfo=MOSCOW_TZ)
    return last_updated.timestamp()


async def _fetch_database_up() -> DatabasePingCache:
    async with async_session_maker() as session:
        await ping_database(session)
    return DatabasePingCache(database_up=1, fetched_at=time.monotonic())


async def _fetch_one_c_last_successful_update_timestamp() -> float:
    async with async_session_maker() as session:
        result = await session.execute(
            select(OstatkiMeta.last_updated).where(OstatkiMeta.id == 1)
        )
        last_updated = result.scalar_one_or_none()
    return _to_unix_timestamp(last_updated)


async def refresh_database_up_if_needed() -> None:
    ttl = settings.METRICS_DB_CACHE_TTL_SECONDS
    now = time.monotonic()
    cached = get_db_metrics_cache()
    if isinstance(cached, DatabasePingCache) and (now - cached.fetched_at) < ttl:
        _apply_database_up(cached)
        return

    async with _db_cache_lock:
        now = time.monotonic()
        cached = get_db_metrics_cache()
        if isinstance(cached, DatabasePingCache) and (now - cached.fetched_at) < ttl:
            _apply_database_up(cached)
            return

        previous_timestamp = (
            cached.one_c_last_successful_update_timestamp_seconds
            if isinstance(cached, DatabasePingCache)
            else 0.0
        )

        try:
            database_snapshot = await _fetch_database_up()
        except Exception:
            logger.exception("Failed to refresh database_up metric")
            snapshot = DatabasePingCache(
                database_up=0,
                fetched_at=time.monotonic(),
                one_c_last_successful_update_timestamp_seconds=previous_timestamp,
            )
        else:
            try:
                one_c_timestamp = (
                    await _fetch_one_c_last_successful_update_timestamp()
                )
            except Exception:
                logger.exception(
                    "Failed to refresh "
                    "one_c_last_successful_update_timestamp_seconds metric"
                )
                one_c_timestamp = previous_timestamp

            snapshot = DatabasePingCache(
                database_up=database_snapshot.database_up,
                fetched_at=time.monotonic(),
                one_c_last_successful_update_timestamp_seconds=one_c_timestamp,
            )

        set_db_metrics_cache(snapshot)
        _apply_database_up(snapshot)


async def collect_metrics_for_scrape() -> None:
    _apply_bot_up()
    await refresh_database_up_if_needed()


def export_prometheus_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
