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

    #API
    API_HOST: str
    API_PORT: int

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
