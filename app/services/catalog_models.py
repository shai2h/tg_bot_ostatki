from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CatalogAvailability(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str | None = None
    label: str | None = None


class CatalogWarehouseAvailability(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    status: str | None = None
    label: str | None = None


class CatalogProduct(BaseModel):
    model_config = ConfigDict(extra="ignore")

    price_id: int | None = None
    product_id: str | None = None
    title: str
    code: str | None = None
    article: str | None = None
    brand: str | None = None
    category: str | None = None
    image: str | None = None
    retail_price: Decimal | None = None
    retail_price_display: str | None = None
    availability: CatalogAvailability | None = None
    warehouses: list[CatalogWarehouseAvailability] = Field(default_factory=list)
    product_url: str | None = None

    @field_validator("retail_price", mode="before")
    @classmethod
    def _parse_retail_price(cls, value: Any) -> Decimal | None:
        if value is None or value == "":
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None


class CatalogSearchResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    query: str = ""
    count: int = 0
    has_more: bool = False
    exact_match: bool = False
    catalog_search_url: str | None = None
    products: list[CatalogProduct] = Field(default_factory=list)
