# Бот остатков (tg_bot_ostatki)

Сервис принимает остатки товаров от **1С**, сохраняет их в **PostgreSQL** и отвечает пользователям в **MAX** (и опционально Telegram) через бота.

**Стек:** FastAPI + PostgreSQL + MAX Bot (режим `polling`).

> Если что-то пошло не так и вы не уверены — **не удаляйте volumes и не меняйте `.env` без согласования** с ответственным за проект.

---

## Что делает сервис

| Компонент | Назначение |
|-----------|------------|
| `POST /api/ostatki` | 1С отправляет полный снимок остатков |
| Бот (polling) | Пользователи ищут товары по названию / артикулу / коду |
| Health endpoints | Проверка состояния приложения, БД, 1С и бота |

---

## Быстрый старт (Docker — основной способ)

### 1. Перейти в каталог проекта

```bash
cd tg_bot_ostatki
```

### 2. Проверить `.env`

Файл `.env` **не хранится в Git**. Если его нет — скопируйте шаблон:

```bash
cp .env_example .env
```

Минимально нужно заполнить:

```env
DB_USER=...
DB_PASS=...
DB_NAME=...

MAX_TOKEN=...          # токен MAX-бота
BOT_RUN_MODE=polling   # НЕ менять без согласования
```

### 3. Запустить

```bash
docker compose build app
docker compose up -d
```

### 4. Проверить, что всё поднялось

```bash
docker compose ps
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
curl http://localhost:8000/health/1c
curl http://localhost:8000/health/bot
```

**Ожидаемый результат:**

| Endpoint | Что значит |
|----------|------------|
| `/health/live` → `200` | Приложение запущено |
| `/health/ready` → `200` | База данных доступна |
| `/health/1c` → `status: ok` | 1С недавно присылала остатки |
| `/health/1c` → `status: stale` | Остатки давно не обновлялись (см. раздел «Проблемы») |
| `/health/bot` → `runtime_running: true` | Бот работает |

### 5. Посмотреть логи

```bash
docker compose logs -f app
```

---

## Ежедневные команды

```bash
# Статус контейнеров
docker compose ps

# Логи приложения
docker compose logs -f app

# Логи базы
docker compose logs -f db

# Перезапуск только приложения (без потери данных)
docker compose restart app

# Остановка
docker compose stop

# Запуск после остановки
docker compose up -d
```

---

## Health endpoints (шпаргалка)

```bash
curl http://localhost:8000/health/live    # жив ли процесс
curl http://localhost:8000/health/ready   # доступна ли БД
curl http://localhost:8000/health/1c      # когда 1С последний раз обновляла остатки
curl http://localhost:8000/health/bot     # состояние бота
```

Старый endpoint `/health` тоже работает (`{"status":"ok"}`), но для диагностики используйте endpoints выше.

---

## Если что-то случилось

### Приложение не отвечает

```bash
docker compose ps
docker compose logs --tail=100 app
docker compose restart app
```

Если не помогло:

```bash
docker compose up -d --build app
```

### `/health/ready` возвращает 503

База данных недоступна.

```bash
docker compose ps db
docker compose logs --tail=100 db
docker compose restart db
# подождать 10–20 секунд
docker compose restart app
curl http://localhost:8000/health/ready
```

### `/health/1c` → `status: stale`

1С давно не присылала остатки (порог по умолчанию — 300 секунд, настраивается через `ONE_C_STALE_AFTER_SECONDS`).

**Что проверить:**

1. Работает ли обмен 1С → `POST /api/ostatki`
2. Доступен ли сервер с 1С до `http://<хост>:8000/api/ostatki`
3. Логи: `docker compose logs -f app | grep -i ostatki`

Это **не останавливает** контейнер — бот продолжает отвечать по старым данным.

### Бот не отвечает в MAX

```bash
curl http://localhost:8000/health/bot
docker compose logs --tail=200 app | grep -iE 'bot|max|polling|error'
```

Проверить в `.env`:

- `MAX_TOKEN` заполнен
- `BOT_RUN_MODE=polling` (не `webhook`!)

Перезапуск:

```bash
docker compose restart app
```

### Контейнер `app` постоянно перезапускается

```bash
docker compose logs --tail=200 app
```

Частые причины: неверный `.env`, нет подключения к БД, невалидный токен бота.

### Нужно обновить код

```bash
git pull
docker compose build app
docker compose up -d app
docker compose logs -f app
```

### Применить миграции БД (если попросили после обновления)

```bash
docker compose exec app alembic current
docker compose exec app alembic upgrade head
```

> **Не выполняйте** `alembic stamp head` без согласования с ответственным.

---

## Что НЕЛЬЗЯ делать

| Команда / действие | Почему опасно |
|--------------------|---------------|
| `docker compose down -v` | **Удалит данные PostgreSQL** |
| Удаление Docker volume вручную | Потеря остатков и истории запросов |
| Менять `BOT_RUN_MODE` на `webhook` | Поиск остатков в боте перестанет работать |
| Коммитить `.env` в Git | Утечка паролей и токенов |
| Удалять таблицу `user_query_log` | Это история запросов пользователей |
| Запускать `monitoring/monitoring_runner.py` | Устаревший мониторинг с `systemctl`, не нужен в Docker |

---

## Откат (rollback)

Если после обновления что-то сломалось:

```bash
# 1. Остановить Docker-версию
docker compose stop app

# 2. Если на сервере ещё есть старый systemd-сервис:
sudo systemctl start tg-bot.service
sudo systemctl status tg-bot.service
```

Если systemd уже отключён — откатите Git и пересоберите:

```bash
git checkout <предыдущий_коммит>
docker compose build app
docker compose up -d app
```

---

## PostgreSQL уже работает отдельно

Если база **уже есть** в Docker и содержит production-данные, **не создавайте новый пустой volume**.

### Вариант A — использовать существующий volume

В `.env` укажите имя существующего volume:

```env
POSTGRES_VOLUME_NAME=<имя_существующего_volume>
```

### Вариант B — подключиться к уже работающему контейнеру БД

Запускать только `app`:

```bash
# В .env добавить:
# EXISTING_DB_HOST=<имя_pg_контейнера>
# EXISTING_DB_NETWORK=<docker_network>

docker compose -f docker-compose.yml -f docker-compose.existing-db.yml up -d app
```

---

## Локальный запуск без Docker (только для разработки)

```bash
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows

pip install -r requirements.txt
cp .env_example .env
```

В `.env` для локального запуска:

```env
DB_HOST=localhost
API_HOST=127.0.0.1
BOT_RUN_MODE=polling
```

```bash
alembic upgrade head
python run.py --mode polling
```

---

## Переменные окружения

| Переменная | Обязательна | Описание |
|------------|-------------|----------|
| `DB_USER`, `DB_PASS`, `DB_NAME` | Да | Подключение к PostgreSQL |
| `MAX_TOKEN` | Для бота | Токен MAX-бота |
| `BOT_TOKEN` | Нет | Telegram (если используется) |
| `BOT_RUN_MODE` | Нет | `polling` (по умолчанию) — **рекомендуется** |
| `ONE_C_STALE_AFTER_SECONDS` | Нет | Порог устаревания остатков (default: 300) |
| `LOG_LEVEL` | Нет | `INFO` по умолчанию |
| `APP_PUBLISH_PORT` | Нет | Порт на хосте (default: 8000) |
| `POSTGRES_VOLUME_NAME` | Нет | Имя Docker volume для БД |

Полный шаблон — в файле `.env_example`.

---

## API endpoints

| Метод | Путь | Кто вызывает |
|-------|------|--------------|
| `POST` | `/api/ostatki` | 1С |
| `GET` | `/health/live` | Docker healthcheck, мониторинг |
| `GET` | `/health/ready` | Мониторинг |
| `GET` | `/health/1c` | Мониторинг загрузки от 1С |
| `GET` | `/health/bot` | Мониторинг бота |
| `POST` | `/webhook` | MAX (только в режиме `webhook`) |
| `GET` | `/docs` | Swagger UI |

---

## Структура проекта (кратко)

```
tg_bot_ostatki/
├── app/
│   ├── api/          # FastAPI: остатки, health, webhook
│   ├── bot/          # MAX/Telegram бот (handlers, polling)
│   ├── services/     # Бизнес-логика (поиск, синхронизация остатков)
│   ├── db/           # Подключение к PostgreSQL
│   └── migrations/   # Alembic-миграции
├── docker-compose.yml
├── Dockerfile
├── run.py            # Точка входа
├── .env              # Секреты (не в Git!)
└── .env_example      # Шаблон переменных
```

---

## Резервное копирование БД

Перед крупными изменениями:

```bash
docker compose exec db pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc > backup_$(date +%Y%m%d).dump
```

Восстановление (только по согласованию с ответственным):

```bash
docker compose exec -T db pg_restore -U "$DB_USER" -d "$DB_NAME" --clean < backup_YYYYMMDD.dump
```

---

## Кому писать

По вопросам архитектуры, токенов, `.env`, миграций и production-деплоя — обращайтесь к **ответственному за проект** (владелец репозитория).

Коллегам достаточно уметь: `docker compose up -d`, проверить health endpoints, посмотреть логи и перезапустить `app`.
