from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.warehouse_stock.models import OstatkiMeta, WarehouseStocks

logger = logging.getLogger(__name__)

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def deduplicate_ostatki_rows(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique_data: dict[tuple[str, str], dict[str, Any]] = {}
    for item in data:
        key = (item["kod"], item["sklad"])
        unique_data[key] = item
    return list(unique_data.values())


async def replace_ostatki_snapshot(
    session: AsyncSession,
    data: list[dict[str, Any]],
) -> tuple[datetime, int]:
    """Atomically replace warehouse_stock snapshot and update ostatki_meta."""
    started = time.perf_counter()
    received_count = len(data)
    final_data = deduplicate_ostatki_rows(data)
    now = datetime.now(MOSCOW_TZ).replace(tzinfo=None)

    logger.info(
        "1C ostatki sync started received_rows=%s unique_rows=%s",
        received_count,
        len(final_data),
    )

    async with session.begin():
        await session.execute(delete(WarehouseStocks))
        if final_data:
            await session.execute(insert(WarehouseStocks), final_data)

        meta_stmt = pg_insert(OstatkiMeta).values(id=1, last_updated=now)
        meta_stmt = meta_stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={"last_updated": now},
        )
        await session.execute(meta_stmt)

    duration_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "1C ostatki sync completed unique_rows=%s duration_ms=%s",
        len(final_data),
        duration_ms,
    )
    return now, len(final_data)
