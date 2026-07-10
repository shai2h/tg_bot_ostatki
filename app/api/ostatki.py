from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from app.db.database import async_session_maker
from app.services.ostatki_sync import replace_ostatki_snapshot

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/api/ostatki")
async def receive_ostatki(data: list[dict[str, Any]] = Body(...)):
    try:
        async with async_session_maker() as session:
            _, unique_rows = await replace_ostatki_snapshot(session, data)
        return {"status": "ok", "processed": len(data), "unique_rows": unique_rows}
    except Exception:
        logger.exception("1C ostatki sync failed; transaction rolled back")
        raise HTTPException(status_code=500, detail="Failed to replace ostatki snapshot")
