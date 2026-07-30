import os

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_USER", "postgres")
os.environ.setdefault("DB_PASS", "postgres")
os.environ.setdefault("DB_NAME", "postgres")
os.environ.setdefault("BOT_RUN_MODE", "polling")
os.environ.setdefault("API_HOST", "127.0.0.1")
os.environ.setdefault("API_PORT", "8000")
os.environ.setdefault("ONE_C_STALE_AFTER_SECONDS", "300")
os.environ.setdefault("LOG_LEVEL", "ERROR")
