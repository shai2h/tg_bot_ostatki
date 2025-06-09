
from pydantic_settings import BaseSettings
from pydantic import model_validator


class Settings(BaseSettings):
    DB_HOST: str
    DB_PORT: int
    DB_USER: str
    DB_PASS: str
    DB_NAME: str
    DATABASE_URL: str = ""

    BOT_TOKEN: str
    
    # Настройки мониторинг-бота
    MONITOR_BOT_TOKEN: str  # Токен второго бота для мониторинга (Zabbix)
    MONITOR_CHAT_ID: str    # ID канала куда слать уведомления (наш Zabbix канал)
    
    # API настройки
    API_HOST: str
    API_PORT: int
    
    # Настройки мониторинга
    API_CHECK_INTERVAL: int = 60        # Интервал проверки API (секунды)
    API_TIMEOUT_THRESHOLD: int = 300    # Время без запросов = проблема (секунды)
    BOT_CHECK_INTERVAL: int = 120       # Интервал проверки бота (секунды)
    BOT_RESTART_ATTEMPTS: int = 3       # Попытки перезапуска бота

    @model_validator(mode='before')
    @classmethod
    def build_database_url(cls, values: dict) -> dict:
        values["DATABASE_URL"] = (
            f"postgresql+asyncpg://{values['DB_USER']}:{values['DB_PASS']}@{values['DB_HOST']}:{values['DB_PORT']}/{values['DB_NAME']}"
        )
        return values

    class Config:
        env_file = ".env"


settings = Settings()
print("DATABASE_URL =", settings.DATABASE_URL)