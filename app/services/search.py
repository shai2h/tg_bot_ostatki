from datetime import datetime
from sqlalchemy import insert, select

from app.db.database import async_session_maker

from app.warehouse_stock.models import UserQueryLog  # новая модель
from app.warehouse_stock.models import WarehouseStocks


async def log_user_query(user_id: int, query: str):
    async with async_session_maker() as session:
        await session.execute(
            insert(UserQueryLog).values(
                user_id=user_id,
                query=query,
                timestamp=datetime.now()
            )
        )
        await session.commit()


async def get_user_query_history(user_id: int):
    async with async_session_maker() as session:
        stmt = (
            select(UserQueryLog.query)
            .where(UserQueryLog.user_id == user_id)
            .order_by(UserQueryLog.timestamp.desc())
            .limit(10)
        )
        result = await session.execute(stmt)
        return [row[0] for row in result.all()]


async def find_products_by_query(query: str) -> dict:
    async with async_session_maker() as session:
        stmt = select(WarehouseStocks).where(
            WarehouseStocks.name.ilike(f"%{query}%") |
            WarehouseStocks.kod.ilike(f"%{query}%") |
            WarehouseStocks.articul.ilike(f"%{query}%")
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

        products = {}
        for item in rows:
            if item.kod not in products:
                products[item.kod] = {
                    "name": item.name,
                    "kod": item.kod,
                    "vid": item.vid,
                    "brend": item.brend,
                    "articul": item.articul,
                    "price": item.price,
                    "stocks": []
                }
            products[item.kod]['stocks'].append({
                "sklad": item.sklad,
                "ostatok": item.ostatok
            })
        return products
