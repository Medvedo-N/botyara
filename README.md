# botyara

Сервис Telegram-бота на FastAPI для Cloud Run.

## Стабильность webhook (база)

- `POST /webhook` всегда отвечает `200 OK`.
- Дубли `update_id` и `op_id` дедуплицируются (LRU+TTL).
- Невалидный payload логируется и обрабатывается без падения.
- `GET /healthz` возвращает живость сервиса.

## Storage backend

Выбранный backend задаётся через ENV `STORAGE_BACKEND`:

- `mock` — локально/тесты.
- `sheets` — реальное хранилище Google Sheets (**текущий real-storage путь**).
- `appsscript` — зарезервировано, пока не реализовано.

## Storage контракт

`app/services/storage.py` (единый интерфейс `StorageAdapter`):

- `get_user(tg_id) -> User | None`
- `list_locations() -> list[Location]`
- `search_items(query: str, page: int, page_size: int) -> (list[Item], has_more: bool)`
- `get_balance(location_id: str, sku: str) -> Balance`
- `apply_operation(op: Operation) -> Balance`
- `get_history(filters...) -> list[LedgerRow]`

## Схема листов Google Sheets

- `catalog(sku,name,unit,active)`
- `locations(location_id,location_name,active)`
- `users(tg_id,name,role,active)`
- `balances(location_id,sku,qty)`
- `ledger(ts,op_id,op_type,sku,qty,from_location,to_location,user_tg_id,comment)`

`ledger` — источник истории, `balances` — кэш для быстрых ответов.

## Роли (RBAC)

Источник ролей — лист `users`.

- Если пользователь найден в `users` и `active=true`, роль берётся из таблицы.
- Если не найден — `нет доступа`.
- Bootstrap fallback: `SUPERADMIN_TG_ID` даёт доступ superadmin для первичного входа.

## Операции склада

В `📦 Склад` реализованы:

- `➕ Приход (IN)`
- `➖ Выдача (OUT)`
- `⚠️ Списание (WRITE_OFF)`
- `🔁 Перемещение (MOVE)`
- `🔎 Остатки`

Проверки:

- `qty > 0`
- `OUT/WRITE_OFF: qty <= остаток`
- `MOVE: from_location != to_location`
- только активные товары/локации
- `op_id` идемпотентен через проверку `ledger`

## ENV

- `BOT_TOKEN` (или fallback `TELEGRAM_TOKEN`)
- `STORAGE_BACKEND=mock|sheets|appsscript`
- `SPREADSHEET_ID` (обязательно для `sheets`)
- `SUPERADMIN_TG_ID` (bootstrap)
- `ENV=prod|staging`
- `PORT` (Cloud Run)

## Локальный запуск

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

## Ручные проверки

```bash
curl http://localhost:8080/healthz
```

Далее в Telegram:

1. `/start`
2. `📦 Склад -> 🔎 Остатки` и получить число.
3. `📦 Склад -> ➕ Приход` и выполнить операцию.
4. `📦 Склад -> ➖ Выдача` и проверить, что остаток обновился.

## Cloud Build Trigger → Cloud Run

1. Создать trigger на ветку (`develop`/`main`).
2. Trigger выполняет `docker build` и `gcloud run deploy` (см. `cloudbuild.yaml`).
3. В Cloud Run задать env-переменные.
4. После деплоя обновить webhook Telegram:

```bash
curl -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
  -d "url=https://<your-cloud-run-url>/webhook"
```
