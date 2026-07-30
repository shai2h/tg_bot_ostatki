# Импорт всех моделей, чтобы Alembic знал о них

from app.warehouse_stock.models import WarehouseStocks, OstatkiMeta, UserQueryLog
from monitoring.models import MonitoringStatus, MonitoringLog
