"""
Prometheus pull-metrics layer for FastAPI services.

Reusable pattern for company services:
  1. Event counters — increment at existing hook points (no SQL on scrape).
  2. In-memory gauges — read from application state (bot_health, etc.).
  3. DB gauges — refresh on TTL cache (batched lightweight queries).
  4. GET /metrics — Prometheus scrapes every 15s (default).

Copy this module structure to other services and keep metric names consistent
where cross-service dashboards are needed.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest
from sqlalchemy import select

from app.bot.health import bot_health
from app.config import settings
from app.db.database import async_session_maker
from app.services.ostatki_sync import count_warehouse_stock_rows, ping_database
from app.warehouse_stock.models import OstatkiMeta

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Metric definitions (extend here: histograms, labels per platform, etc.)
# ---------------------------------------------------------------------------

bot_up = Gauge(
    "bot_up",
    "Whether bot runtime is active with handlers registered (1=yes, 0=no).",
)

database_up = Gauge(
    "database_up",
    "Whether PostgreSQL responded to a lightweight ping (1=yes, 0=no).",
)

one_c_last_update_timestamp = Gauge(
    "one_c_last_update_timestamp",
    "Unix timestamp of the last successful 1C ostatki snapshot (0 if never).",
)

one_c_seconds_since_last_update = Gauge(
    "one_c_seconds_since_last_update",
    "Seconds since last 1C ostatki update (-1 if never received).",
)

warehouse_stock_rows = Gauge(
    "warehouse_stock_rows",
    "Current row count in warehouse_stock (cached, refreshed on TTL).",
)

user_queries_total = Counter(
    "user_queries_total",
    "Total user search queries recorded in user_query_log.",
)

bot_answers_total = Counter(
    "bot_answers_total",
    "Total successful bot answers sent to users.",
)

# Future extensions (examples — not exported yet):
# ostatki_sync_duration_seconds = Histogram(...)
# bot_errors_total = Counter(..., ["platform"])
# one_c_sync_rows_total = Counter(...)


@dataclass(frozen=True, slots=True)
class DbMetricsSnapshot:
    database_up: int
    one_c_last_update_timestamp: float
    one_c_seconds_since_last_update: float
    warehouse_stock_rows: int
    fetched_at: float


_db_cache: DbMetricsSnapshot | None = None
_db_cache_lock = asyncio.Lock()


def record_user_query() -> None:
    user_queries_total.inc()


def record_bot_answer() -> None:
    bot_answers_total.inc()


def invalidate_db_metrics_cache() -> None:
    """Call after 1C snapshot sync so the next scrape sees fresh DB gauges."""
    global _db_cache
    _db_cache = None


def _apply_bot_gauges() -> None:
    is_up = 1 if bot_health.runtime_running and bot_health.handlers_registered else 0
    bot_up.set(is_up)


def _apply_db_snapshot(snapshot: DbMetricsSnapshot) -> None:
    database_up.set(snapshot.database_up)
    one_c_last_update_timestamp.set(snapshot.one_c_last_update_timestamp)
    one_c_seconds_since_last_update.set(snapshot.one_c_seconds_since_last_update)
    warehouse_stock_rows.set(snapshot.warehouse_stock_rows)


def _last_updated_to_metrics(last_updated: datetime | None) -> tuple[float, float]:
    if last_updated is None:
        return 0.0, -1.0

    if last_updated.tzinfo is None:
        last_updated_utc = last_updated.replace(tzinfo=timezone.utc)
    else:
        last_updated_utc = last_updated.astimezone(timezone.utc)

    timestamp = last_updated_utc.timestamp()
    seconds_since = max(0.0, time.time() - timestamp)
    return timestamp, seconds_since


async def _fetch_db_snapshot() -> DbMetricsSnapshot:
    async with async_session_maker() as session:
        await ping_database(session)

        result = await session.execute(
            select(OstatkiMeta.last_updated).where(OstatkiMeta.id == 1)
        )
        last_updated = result.scalar_one_or_none()
        row_count = await count_warehouse_stock_rows(session)

    timestamp, seconds_since = _last_updated_to_metrics(last_updated)
    return DbMetricsSnapshot(
        database_up=1,
        one_c_last_update_timestamp=timestamp,
        one_c_seconds_since_last_update=seconds_since,
        warehouse_stock_rows=row_count,
        fetched_at=time.monotonic(),
    )


async def refresh_db_metrics_if_needed() -> None:
    global _db_cache

    ttl = settings.METRICS_DB_CACHE_TTL_SECONDS
    now = time.monotonic()
    if _db_cache is not None and (now - _db_cache.fetched_at) < ttl:
        _apply_db_snapshot(_db_cache)
        return

    async with _db_cache_lock:
        now = time.monotonic()
        if _db_cache is not None and (now - _db_cache.fetched_at) < ttl:
            _apply_db_snapshot(_db_cache)
            return

        try:
            _db_cache = await _fetch_db_snapshot()
        except Exception:
            logger.exception("Failed to refresh Prometheus DB metrics cache")
            if _db_cache is not None:
                stale = DbMetricsSnapshot(
                    database_up=0,
                    one_c_last_update_timestamp=_db_cache.one_c_last_update_timestamp,
                    one_c_seconds_since_last_update=_db_cache.one_c_seconds_since_last_update,
                    warehouse_stock_rows=_db_cache.warehouse_stock_rows,
                    fetched_at=time.monotonic(),
                )
                _db_cache = stale
            else:
                _db_cache = DbMetricsSnapshot(
                    database_up=0,
                    one_c_last_update_timestamp=0.0,
                    one_c_seconds_since_last_update=-1.0,
                    warehouse_stock_rows=0,
                    fetched_at=time.monotonic(),
                )

        _apply_db_snapshot(_db_cache)


async def collect_metrics_for_scrape() -> None:
    _apply_bot_gauges()
    await refresh_db_metrics_if_needed()


def export_prometheus_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
