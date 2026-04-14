# FastAPI + MAX Bot

## What Was Added

- `obabot` integration for Max/Telegram-compatible handlers
- `POST /webhook` endpoint for MAX webhook delivery
- `POST /process_message` endpoint used by bot handlers
- `/start`, echo replies, inline keyboard, callback handling, and FSM state
- `uvicorn` launch with `polling` or `webhook` mode

## Install

```bash
pip install -r requirements.txt
```

## Environment

```env
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASS=postgres
DB_NAME=postgres

API_HOST=127.0.0.1
API_PORT=8000

MAX_TOKEN=your_max_token
BOT_TOKEN=optional_telegram_token
BOT_RUN_MODE=polling

MAX_WEBHOOK_URL=https://your-domain.com/webhook
MAX_WEBHOOK_SECRET=your_secret_value
```

## Run

Development with long polling:

```bash
python run.py --mode polling
```

Production with webhook:

```bash
python run.py --mode webhook
```

Direct `uvicorn` launch also works:

```bash
uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

## MAX Notes

- Webhook subscription is registered against `https://platform-api.max.ru/subscriptions`
- MAX sends the webhook secret in `X-Max-Bot-Api-Secret`
- Message formatting uses `markdown`
- Inline keyboard buttons include both `callback` and `link`

## Endpoints

- `POST /api/ostatki`
- `POST /process_message`
- `POST /webhook`
- `GET /health`
