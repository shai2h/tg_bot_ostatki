from db.session import async_session
from db.models import Product, Stock
from sqlalchemy.future import select
from datetime import datetime

async def get_product_response(query: str) -> str:
    async with async_session() as session:
        result = await session.execute(select(Product).filter(
            (Product.article.ilike(f"%{query}%")) |
            (Product.name.ilike(f"%{query}%")) |
            (Product.code.ilike(f"%{query}%"))
        ))
        products = result.scalars().all()

        if not products:
            return "\U0001F6D1 Номенклатура не найдена. Проверьте правильность ввода."

        response = f"\U0001F50D Актуальные остатки на {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
        for p in products:
            response += "―――――――――――――――\n\n"
            response += f"\U0001F537 Товар: {p.name}\n"
            response += f"\U0001F539 Вид: {p.type}\n"
            response += f"\U0001F539 Бренд: {p.brand}\n"
            response += f"\U0001F539 Артикул: {p.article}\n"
            response += f"\U0001F539 Код: {p.code}\n"
            response += f"\U0001F539 Цена: {p.price} ₽\n"
            response += f"\n\U0001F69A Наличие по городам:\n"
            for s in p.stocks:
                status = "Некорректное значение"
                try:
                    v = int(s.status)
                    if v == 1:
                        status = "В наличии"
                    elif v < 3:
                        status = "Несколько"
                    else:
                        status = "Много"
                except:
                    status = s.status
                response += f"\U0001F538 {s.city}: {status}\n"
        return response