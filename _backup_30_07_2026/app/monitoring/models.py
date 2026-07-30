from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text
from app.db.database import Base

class MonitoringStatus(Base):
    """Таблица для отслеживания состояния системы"""
    __tablename__ = "monitoring_status"
    
    id = Column(Integer, primary_key=True)
    component = Column(String(50), unique=True, nullable=False)  # 'api_1c', 'telegram_bot'
    status = Column(String(20), nullable=False)  # 'ok', 'error', 'warning'
    last_check = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_success = Column(DateTime, nullable=True)
    error_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    notification_sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class MonitoringLog(Base):
    """Таблица для логов мониторинга"""
    __tablename__ = "monitoring_log"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    component = Column(String(50), nullable=False)
    event_type = Column(String(30), nullable=False)  # 'status_change', 'error', 'recovery'
    message = Column(Text, nullable=False)
    severity = Column(String(20), nullable=False)  # 'info', 'warning', 'error', 'critical'
    created_at = Column(DateTime, default=datetime.utcnow)
