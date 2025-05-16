from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import settings

# Создаем движок подключения к PostgreSQL
engine = create_async_engine(settings.DATABASE_URL, echo=False)

# Фабрика сессий для использования через async with
async_session_maker = sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession
)

# Базовый класс для моделей SQLAlchemy
class Base(DeclarativeBase):
    pass
