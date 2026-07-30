from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.warehouse_stock.models import WarehouseStocks


async def ping_database(session: AsyncSession) -> None:
    """Lightweight PostgreSQL availability check."""
    await session.execute(text("SELECT 1"))


async def count_warehouse_stock_rows(session: AsyncSession) -> int:
    """Return current row count in warehouse_stock."""
    result = await session.execute(select(func.count()).select_from(WarehouseStocks))
    return int(result.scalar_one())
