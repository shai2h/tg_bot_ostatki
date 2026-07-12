"""
Prometheus pull-metrics for tg_bot_ostatki.

Minimal scrape surface (bot_up, database_up).
Extend with additional Gauges/Counters/Histograms in this module later.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest

from app.bot.health import bot_health
from app.config import settings
from app.db.database import async_session_maker
from app.db.health import ping_database
from app.observability.db_metrics_cache import (
    get_db_metrics_cache,
    set_db_metrics_cache,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Metric definitions — add more metrics here when needed
# ---------------------------------------------------------------------------

bot_up = Gauge("bot_up", "Bot runtime status")

database_up = Gauge("database_up", "Database availability")


@dataclass(frozen=True, slots=True)
class DatabasePingCache:
    database_up: int
    fetched_at: float


_db_cache_lock = asyncio.Lock()


def _apply_bot_up() -> None:
    bot_up.set(1 if bot_health.runtime_running else 0)


def _apply_database_up(snapshot: DatabasePingCache) -> None:
    database_up.set(snapshot.database_up)


async def _fetch_database_up() -> DatabasePingCache:
    async with async_session_maker() as session:
        await ping_database(session)
    return DatabasePingCache(database_up=1, fetched_at=time.monotonic())


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

        try:
            snapshot = await _fetch_database_up()
        except Exception:
            logger.exception("Failed to refresh database_up metric")
            snapshot = DatabasePingCache(database_up=0, fetched_at=time.monotonic())

        set_db_metrics_cache(snapshot)
        _apply_database_up(snapshot)


async def collect_metrics_for_scrape() -> None:
    _apply_bot_up()
    await refresh_database_up_if_needed()


def export_prometheus_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
