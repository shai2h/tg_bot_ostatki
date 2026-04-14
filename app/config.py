from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DB_HOST: str
    DB_PORT: int
    DB_USER: str
    DB_PASS: str
    DB_NAME: str
    DATABASE_URL: str = ""

    BOT_TOKEN: str | None = None
    MAX_TOKEN: str | None = None
    MAX_WEBHOOK_SECRET: str | None = None
    MAX_WEBHOOK_URL: str | None = None
    BOT_RUN_MODE: str = "polling"
    INTERNAL_API_BASE_URL: str | None = None
    PROCESS_MESSAGE_ENDPOINT: str = "/process_message"

    MONITOR_BOT_TOKEN: str | None = None
    MONITOR_CHAT_ID: str | None = None

    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000

    API_CHECK_INTERVAL: int = 60
    API_TIMEOUT_THRESHOLD: int = 300
    BOT_CHECK_INTERVAL: int = 120
    BOT_RESTART_ATTEMPTS: int = 3

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    @model_validator(mode="before")
    @classmethod
    def build_database_url(cls, values: dict) -> dict:
        values = dict(values)
        if not values.get("DATABASE_URL"):
            values["DATABASE_URL"] = (
                f"postgresql+asyncpg://{values['DB_USER']}:{values['DB_PASS']}@"
                f"{values['DB_HOST']}:{values['DB_PORT']}/{values['DB_NAME']}"
            )
        return values

    @property
    def api_base_url(self) -> str:
        return self.INTERNAL_API_BASE_URL or f"http://{self.API_HOST}:{self.API_PORT}"

    @property
    def webhook_path(self) -> str:
        return "/webhook"


settings = Settings()
