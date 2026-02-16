# botyara

Telegram-бот склада на `FastAPI + python-telegram-bot (async)` c webhook-моделью для Cloud Run.

## Архитектура (слои)

- `app/main.py` — FastAPI entrypoint, webhook, healthz, lifespan.
- `app/config.py` — конфиг через `pydantic-settings`.
- `app/di.py` — фабрики зависимостей (`settings/storage/services/telegram app`).
- `app/bot/` — router, handlers, FSM, keyboards.
- `app/services/` — бизнес-логика (`inventory.py`) и RBAC (`rbac.py`).
- `app/storage/` — порт `StoragePort` + реализации (`memory.py`, `sheets.py`).
- `app/models/` — доменные модели и DTO.

## ENV переменные

Обязательные:

- `BOT_TOKEN` — токен бота.

Рекомендуемые:

- `ENV` (`staging|prod`)
- `LOG_LEVEL` (`DEBUG|INFO|WARNING|ERROR`)
- `STORAGE_BACKEND` (`memory|sheets`)
- `SPREADSHEET_ID` (обязательно при `STORAGE_BACKEND=sheets`)
- `SUPERADMIN_TG_ID` (Telegram user id с полным доступом)
- `BASE_URL` (public url сервиса для webhook)
- `WEBHOOK_SECRET` (опционально, проверяется в `/webhook`)
- `PORT` (по умолчанию `8080`)

## Локальный запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export BOT_TOKEN=<token>
export STORAGE_BACKEND=memory
export SUPERADMIN_TG_ID=<your_tg_id>

uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Проверка health:

```bash
curl http://localhost:8080/healthz
# {"ok":true,"version":"2.0-fixed"}
```

## Docker / Cloud Run

```bash
docker build -t botyara:local .
docker run --rm -p 8080:8080 \
  -e BOT_TOKEN=<token> \
  -e STORAGE_BACKEND=memory \
  -e SUPERADMIN_TG_ID=<tg_id> \
  botyara:local
```

Cloud Run использует порт `8080` через `${PORT:-8080}` в `Dockerfile`.

## RBAC

Роли:

- `owner`
- `manager`
- `storekeeper`
- `viewer`

`SUPERADMIN_TG_ID` всегда работает как `owner`.

Права задаются централизованно в `app/services/rbac.py`.

## FSM / роутинг

Сценарии вынесены в `app/bot/fsm/`.

Порядок регистрации handlers:

1. Commands
2. Callbacks
3. Text Router
4. Fallback

В логах добавлены события `ROUTER HIT` и `FALLBACK HIT` для дебага маршрутизации.

## Тесты

```bash
python -m unittest discover -s tests -p 'test_*.py'
```
