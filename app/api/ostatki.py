from fastapi import APIRouter, Body, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import async_session_maker
from app.warehouse_stock.models import WarehouseStocks
from sqlalchemy import insert
from typing import List, Dict, Any


router = APIRouter()


@router.post("/api/ostatki")
async def receive_ostatki(data: List[Dict[str, Any]] = Body(...)):
    try:
        async with async_session_maker() as session:
            for item in data:
                stmt = insert(WarehouseStocks).values(**item)
                await session.execute(stmt)
            await session.commit()
        return {"status": "ok", "inserted": len(data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
