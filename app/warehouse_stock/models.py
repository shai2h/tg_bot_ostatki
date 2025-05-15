from db.database import Base
from sqlalchemy import Column, Integer, JSON, String


class Hotels(Base):
    __tablename__ = "warehouse_stock"

    id = Column(Integer, primary_key=True)
    articul = Column(String, nullable=True)
    name = Column(nullable=False)
    vid = Column(String)
    brend = Column(String)
    kod = Column(Integer)
    price = Column(Integer)
    ostatok = Column(Integer)
    sklad = Column(String)