from app.db.database import Base
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy import BigInteger
from datetime import datetime
from sqlalchemy import UniqueConstraint

class WarehouseStocks(Base):
    __tablename__ = "warehouse_stock"

    id = Column(Integer, primary_key=True)
    articul = Column(String, nullable=True)
    name = Column(String, nullable=False)
    vid = Column(String)
    brend = Column(String)
    kod = Column(String)
    price = Column(String)
    ostatok = Column(String)
    sklad = Column(String)

    __table_args__ = (
        UniqueConstraint("kod", "sklad", name="uix_kod_sklad"),
    )


class UserQueryLog(Base):
    __tablename__ = "user_query_log"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    query = Column(String, nullable=False)
    timestamp = Column(DateTime, nullable=False)


class OstatkiMeta(Base):
    __tablename__ = "ostatki_meta"
    id = Column(Integer, primary_key=True)
    last_updated = Column(DateTime, nullable=False)