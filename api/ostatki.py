from fastapi import APIRouter, Body, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from db.session import async_session
from db import crud

router = APIRouter()

@router.post("/api/ostatki")
async def handle_ostatki(data=Body(...)):
    try:
        async with async_session() as session:
            inserted = await crud.process_inventory_data_async(data, session)
        return {"status": "success", "inserted": inserted}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка обработки данных: {e}")
