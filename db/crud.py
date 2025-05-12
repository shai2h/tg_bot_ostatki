# db/crud.py
from db.models import Product, Stock
from sqlalchemy.ext.asyncio import AsyncSession

async def process_inventory_data_async(data: list, db: AsyncSession):
    inserted = 0
    for item in data:
        product = Product(
            name=item.get("name"),
            article=item.get("article"),
            brand=item.get("brand"),
            code=item.get("code"),
            type=item.get("type"),
            price=item.get("price"),
        )
        db.add(product)
        await db.flush()

        for stock in item.get("stock", []):
            db.add(Stock(
                city=stock["city"],
                status=stock["status"],
                product_id=product.id
            ))
        inserted += 1

    await db.commit()
    return inserted
