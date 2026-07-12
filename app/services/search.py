from datetime import datetime
from sqlalchemy import insert, select, cast

from app.db.database import async_session_maker

from app.warehouse_stock.models import UserQueryLog  # новая модель
from app.warehouse_stock.models import WarehouseStocks

from sqlalchemy import insert, select, or_, and_
from sqlalchemy import Integer

from rapidfuzz import process, fuzz

from sqlalchemy import func

# Поиск через rapidfuzz
async def fuzzy_find_products(query: str, limit: int = 10) -> list:
    async with async_session_maker() as session:
        stmt = select(WarehouseStocks)
        result = await session.execute(stmt)
        rows = result.scalars().all()

    all_names = [f"{row.name} {row.articul or ''} {row.kod or ''}" for row in rows]

    matches = process.extract(query, all_names, scorer=fuzz.WRatio, limit=limit)

    result_products = []
    for _, score, idx in matches:
        row = rows[idx]
        result_products.append({
            "name": row.name,
            "vid": row.vid,
            "brend": row.brend,
            "kod": row.kod,
            "articul": row.articul,
            "price": row.price,
            "sklad": row.sklad,
            "ostatok": row.ostatok,
            "score": score
        })

    return result_products


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


ALL_CITIES = [
    "Владивосток", "Волжск", "Екатеринбург", "Краснодар", "Москва",
    "Нижний Новгород", "Новосибирск", "Омск", "Пермь", "Пятигорск",
    "Ростов-на Дону", "Санкт-Петербург", "Симферополь", "Ставрополь",
    "Тюмень", "Уфа", "Хабаровск", "Челябинск", "Ярославль"
]


def extract_city_and_query(text: str) -> tuple[str, str]:
    text = text.strip()
    for city in ALL_CITIES:
        if text.lower().startswith(city.lower()):
            remaining = text[len(city):].strip()
            return city, remaining
    return "", text


async def find_products_by_query(query: str) -> dict:
    city, pure_query = extract_city_and_query(query)

    async with async_session_maker() as session:
        stmt = select(WarehouseStocks).where(
            or_(
                WarehouseStocks.name.ilike(f"%{pure_query}%"),
                WarehouseStocks.kod.ilike(f"%{pure_query}%"),
                WarehouseStocks.articul.ilike(f"%{pure_query}%")
            )
        )

        if city:
            stmt = stmt.where(WarehouseStocks.sklad.ilike(f"%{city}%"))

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



async def find_products_by_query(query: str) -> dict:
    city, pure_query = extract_city_and_query(query)

    async with async_session_maker() as session:
        stmt = select(WarehouseStocks).where(
            or_(
                WarehouseStocks.name.ilike(f"%{pure_query}%"),
                WarehouseStocks.kod.ilike(f"%{pure_query}%"),
                WarehouseStocks.articul.ilike(f"%{pure_query}%")
            )
        )
        if city:
            stmt = stmt.where(WarehouseStocks.sklad.ilike(f"%{city}%"))

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


async def get_stocks_by_kod(kod: str, sklad: str):
    async with async_session_maker() as session:
        stmt = select(WarehouseStocks).where(
            WarehouseStocks.kod == kod,
            WarehouseStocks.sklad == sklad
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


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


async def find_products_by_text(query: str) -> dict:
    city, pure_query = extract_city_and_query(query)

    async with async_session_maker() as session:
        stmt = select(WarehouseStocks).where(
            or_(
                WarehouseStocks.name.ilike(f"%{pure_query}%"),
                WarehouseStocks.kod.ilike(f"%{pure_query}%"),
                WarehouseStocks.articul.ilike(f"%{pure_query}%")
            )
        )
        if city:
            stmt = stmt.where(WarehouseStocks.sklad.ilike(f"%{city}%"))

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