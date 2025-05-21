from fastapi import APIRouter, Body, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import async_session_maker
from app.warehouse_stock.models import WarehouseStocks, OstatkiMeta
from sqlalchemy import insert
from typing import List, Dict, Any
from sqlalchemy.dialects.postgresql import insert

from datetime import datetime, timedelta, timezone

router = APIRouter()

moscow_tz = timezone(timedelta(hours=3))  # задаем часовой пояс +3

import logging
from pprint import pformat  # в начало файла

logger = logging.getLogger(__name__)

@router.post("/api/ostatki")
async def receive_ostatki(data: List[Dict[str, Any]] = Body(...)):
    try:
        async with async_session_maker() as session:
            now = datetime.now(moscow_tz)

            for item in data:
                try:
                    stmt = insert(WarehouseStocks).values(**item)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["kod", "sklad"],
                        set_={
                            "ostatok": item["ostatok"],
                            "price": item["price"],
                            "name": item["name"],
                            "vid": item["vid"],
                            "brend": item["brend"],
                            "articul": item.get("articul"),
                            "updated_at": now,
                        }
                    )
                    await session.execute(stmt)
                except Exception as row_error:
                    logger.error("шибка при вставке строки:\n%s", pformat(item))
                    logger.exception(row_error)
                    raise  # пробросим дальше — чтобы сразу видеть причину

            try:
                meta_stmt = insert(OstatkiMeta).values(id=1, last_updated=now)
                meta_stmt = meta_stmt.on_conflict_do_update(
                    index_elements=["id"],
                    set_={"last_updated": now}
                )
                await session.execute(meta_stmt)
            except Exception as meta_error:
                logger.error("Ошибка при записи meta-таблицы (OstatkiMeta)")
                logger.exception(meta_error)
                raise

            await session.commit()
        return {"status": "ok", "processed": len(data)}

    except Exception as e:
        logger.exception("🔥 Общая ошибка API /api/ostatki")
        raise HTTPException(status_code=500, detail=str(e))


