from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, call

import pytest
from sqlalchemy import delete, insert

from app.services.ostatki_sync import deduplicate_ostatki_rows, replace_ostatki_snapshot
from app.warehouse_stock.models import OstatkiMeta, UserQueryLog, WarehouseStocks


def _sample_row(kod: str = "K1", sklad: str = "Москва") -> dict[str, str]:
    return {
        "articul": "A1",
        "name": "Product",
        "vid": "Type",
        "brend": "Brand",
        "kod": kod,
        "price": "100",
        "ostatok": "5",
        "sklad": sklad,
    }


def test_deduplicate_ostatki_rows_keeps_last_duplicate() -> None:
    rows = [
        _sample_row(kod="K1", sklad="Москва"),
        {**_sample_row(kod="K1", sklad="Москва"), "ostatok": "9"},
        _sample_row(kod="K2", sklad="Москва"),
    ]

    result = deduplicate_ostatki_rows(rows)

    assert len(result) == 2
    moscow_row = next(item for item in result if item["kod"] == "K1")
    assert moscow_row["ostatok"] == "9"


@pytest.mark.asyncio
async def test_replace_snapshot_uses_single_transaction() -> None:
    session = AsyncMock()
    transaction = AsyncMock()

    @asynccontextmanager
    async def fake_begin():
        yield session

    session.begin = fake_begin
    session.execute = AsyncMock()

    data = [_sample_row(), _sample_row(kod="K2")]
    updated_at, unique_rows = await replace_ostatki_snapshot(session, data)

    assert isinstance(updated_at, datetime)
    assert unique_rows == 2
    assert session.execute.await_count == 3

    delete_stmt = session.execute.await_args_list[0].args[0]
    insert_stmt = session.execute.await_args_list[1].args[0]
    meta_stmt = session.execute.await_args_list[2].args[0]

    assert delete_stmt.__class__.__name__ == "Delete"
    assert insert_stmt.__class__ == insert(WarehouseStocks).__class__
    assert meta_stmt.__class__.__name__ in {"Insert", "PostgreSQLInsert"}


@pytest.mark.asyncio
async def test_replace_snapshot_rollback_on_insert_error() -> None:
    session = AsyncMock()
    rolled_back = False

    @asynccontextmanager
    async def fake_begin():
        nonlocal rolled_back
        try:
            yield session
        except Exception:
            rolled_back = True
            raise

    session.begin = fake_begin

    async def execute_side_effect(stmt, *args, **kwargs):
        if stmt.__class__.__name__ == "Insert" or "Insert" in stmt.__class__.__name__:
            raise RuntimeError("insert failed")
        return AsyncMock()

    session.execute = AsyncMock(side_effect=execute_side_effect)

    with pytest.raises(RuntimeError, match="insert failed"):
        await replace_ostatki_snapshot(session, [_sample_row()])

    assert rolled_back is True


@pytest.mark.asyncio
async def test_replace_snapshot_does_not_touch_user_query_log() -> None:
    session = AsyncMock()

    @asynccontextmanager
    async def fake_begin():
        yield session

    session.begin = fake_begin
    session.execute = AsyncMock()

    await replace_ostatki_snapshot(session, [_sample_row()])

    executed_models = []
    for awaited in session.execute.await_args_list:
        stmt = awaited.args[0]
        table_name = getattr(getattr(stmt, "table", None), "name", None)
        if table_name:
            executed_models.append(table_name)

    assert executed_models == ["warehouse_stock", "warehouse_stock", "ostatki_meta"]
    assert UserQueryLog.__tablename__ not in executed_models
