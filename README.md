# 📦 Telegram Bot остатков

## 🔧 Описание
Этот бот позволяет искать товары по складам и получать актуальные остатки из 1С.

---

### 1. Установить зависимости

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

### 2. PostgreSQL

Создай базу данных и таблицы. Пример URL в `.env`:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/postgres
```

Применение миграций или создание вручную:

```sql
CREATE TABLE warehouse_stock (
    id SERIAL PRIMARY KEY,
    articul VARCHAR,
    name VARCHAR NOT NULL,
    vid VARCHAR,
    brend VARCHAR,
    kod VARCHAR,
    price VARCHAR,
    ostatok VARCHAR,
    sklad VARCHAR,
    UNIQUE (kod, sklad)
);

CREATE TABLE user_query_log (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    query VARCHAR NOT NULL,
    timestamp TIMESTAMP NOT NULL
);
```

---

### 3. Настройте переменные окружения

Создай `.env` файл или настрой переменные напрямую:

```env
BOT_TOKEN=токен_твоего_бота
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/postgres
```

---

### 4. Запусти бота

```bash
python run.py
```

---

## 📦 Доступные команды

- `/start` — Главное меню
- `Инструкция` — Как использовать
- `История запросов` — Последние запросы пользователя
- `Полный отчет XLSX` — Выгрузка остатков по складам

---

## 📁 Структура проекта

```text
tg_bot_ostatki/
├── app/
│   ├── bot/
│   │   └── handlers.py
│   ├── db/
│   │   └── database.py
│   ├── services/
│   │   └── search.py
│   └── warehouse_stock/
│       └── models.py
├── run.py
└── requirements.txt
```

---

## ⚙️ systemd юнит (для Linux сервера)

```ini
[Unit]
Description=Telegram Warehouse Bot
After=network.target postgresql.service

[Service]
User=user
WorkingDirectory=/home/user/tg_bot_ostatki
ExecStart=/home/user/tg_bot_ostatki/.venv/bin/python run.py
Restart=always
Environment="BOT_TOKEN=..." "DATABASE_URL=..."

[Install]
WantedBy=multi-user.target
```

---

## 🧪 Тестирование

Можно использовать `pytest` для модульных тестов.

---

## 🧼 Очистка временных файлов

Excel и TXT-файлы удаляются автоматически после отправки пользователю.

---
