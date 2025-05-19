from fastapi import APIRouter, Body, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import async_session_maker
from app.warehouse_stock.models import WarehouseStocks
from sqlalchemy import insert
from typing import List, Dict, Any
from sqlalchemy.dialects.postgresql import insert

router = APIRouter()


@router.post("/api/ostatki")
async def receive_ostatki(data: List[Dict[str, Any]] = Body(...)):
    try:
        async with async_session_maker() as session:
            for item in data:
                stmt = insert(WarehouseStocks).values(**item)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["kod", "sklad"],  # ключ и склад по уникальным
                    set_={
                        "ostatok": item["ostatok"],
                        "price": item["price"],
                        "name": item["name"],
                        "vid": item["vid"],
                        "brend": item["brend"],
                        "articul": item.get("articul"),
                    }
                )
                await session.execute(stmt)
            await session.commit()
        return {"status": "ok", "processed": len(data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

