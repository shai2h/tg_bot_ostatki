from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from sqlalchemy.dialects.postgresql import insert as pg_insert
from fastapi import APIRouter, Body, HTTPException
from sqlalchemy import insert, delete, text
import logging
from pprint import pformat

from app.db.database import async_session_maker
from app.warehouse_stock.models import WarehouseStocks, OstatkiMeta  # импорт моделей

router = APIRouter()
logger = logging.getLogger(__name__)

# Часовой пояс Москвы
moscow_tz = timezone(timedelta(hours=0))

@router.post("/api/ostatki")
async def receive_ostatki(data: List[Dict[str, Any]] = Body(...)):
    try:
        now = datetime.now(moscow_tz).replace(tzinfo=None)

        # очистка таблицы с FK
        async with async_session_maker() as cleanup_session:
            try:
                await cleanup_session.execute(text("DELETE FROM warehouse_stock"))
                await cleanup_session.commit()
                logger.info("Таблица warehouse_stock очищена (DELETE)")
            except Exception as delete_error:
                logger.error("Ошибка при очистке таблицы warehouse_stock")
                logger.exception(delete_error)
                raise

        unique_data = {}
        for item in data:
            key = (item['kod'], item['sklad'])
            unique_data[key] = item

        final_data = list(unique_data.values())

        # вставка данных
        async with async_session_maker() as session:
            for item in final_data:
                try:
                    stmt = insert(WarehouseStocks).values(**item)
                    await session.execute(stmt)
                except Exception as row_error:
                    logger.error("Ошибка при вставке строки:\n%s", pformat(item))
                    logger.exception(row_error)
                    raise

            try:
                meta_stmt = pg_insert(OstatkiMeta).values(id=1, last_updated=now)
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
        logger.exception("Общая ошибка API /api/ostatki")
        raise HTTPException(status_code=500, detail=str(e))
