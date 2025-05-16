from app.db.database import Base
from sqlalchemy import Column, Integer, String


from sqlalchemy import UniqueConstraint

class WarehouseStocks(Base):
    __tablename__ = "warehouse_stock"

    id = Column(Integer, primary_key=True)
    articul = Column(String, nullable=True)
    name = Column(String, nullable=False)
    vid = Column(String)
    brend = Column(String)
    kod = Column(String)      # ← строка, как ты указал
    price = Column(String)
    ostatok = Column(String)
    sklad = Column(String)

    __table_args__ = (
        UniqueConstraint("kod", "sklad", name="uix_kod_sklad"),
    )
