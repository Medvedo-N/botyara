# Развертывание на Google Cloud Run

## Требуемые переменные окружения

При развертывании на Cloud Run необходимо установить следующие переменные окружения:

### Обязательные:
- **BOT_TOKEN** - токен Telegram бота (от @BotFather)
  ```
  BOT_TOKEN=<your-telegram-bot-token>
  ```

### Опциональные:
- **ENV** - окружение (staging/production), по умолчанию: `staging`
  ```
  ENV=production
  ```

- **STORAGE_BACKEND** - способ хранения данных (memory/sheets), по умолчанию: `memory`
  ```
  STORAGE_BACKEND=sheets
  ```

- **SPREADSHEET_ID** - ID Google Sheets таблицы (если используется sheets backend)
  ```
  SPREADSHEET_ID=<your-spreadsheet-id>
  ```

- **SUPERADMIN_TG_ID** - ID Telegram администратора
  ```
  SUPERADMIN_TG_ID=<your-telegram-id>
  ```

- **WEBHOOK_SECRET** - секретный токен для webhook (рекомендуется)
  ```
  WEBHOOK_SECRET=<random-secret-string>
  ```

- **LOW_STOCK_NOTIFY_CHAT_ID** - ID чата для уведомлений о низком остатке
  ```
  LOW_STOCK_NOTIFY_CHAT_ID=<chat-id>
  ```

- **LOG_LEVEL** - уровень логирования (DEBUG/INFO/WARNING/ERROR), по умолчанию: `INFO`
  ```
  LOG_LEVEL=INFO
  ```

## Развертывание через gcloud CLI

```bash
# Аутентификация
gcloud auth login

# Установить проект
gcloud config set project PROJECT_ID

# Развернуть сервис
gcloud run deploy botyara \
  --source . \
  --region us-central1 \
  --port 8080 \
  --memory 512Mi \
  --cpu 1 \
  --timeout 3600 \
  --set-env-vars=BOT_TOKEN=<your-token>,ENV=production,STORAGE_BACKEND=memory
```

## Развертывание через Cloud Console

1. Перейти в Cloud Run
2. Создать новый сервис
3. Выбрать этот репозиторий
4. В разделе "Переменные окружения" установить:
   - BOT_TOKEN
   - Остальные необходимые переменные

## Webhook конфигурация

После развертывания, настроить webhook:

```bash
BOT_TOKEN=<your-token>
WEBHOOK_URL=https://<your-cloud-run-url>/webhook
SECRET=<your-webhook-secret>

curl -X POST "https://api.telegram.org/bot$BOT_TOKEN/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"$WEBHOOK_URL\", \"secret_token\": \"$SECRET\"}"
```

## Проверка здоровья сервиса

```bash
# Проверить статус
curl https://<your-cloud-run-url>/healthz

# Ответ:
# {
#   "ok": true,
#   "version": "2.0-fixed",
#   "env": "production",
#   "bot_token_set": true,
#   "storage_backend": "memory"
# }
```

## Устранение проблем

### Контейнер не запускается (timeout)

**Признаки:**
- Ошибка: "The user-provided container failed to start and listen on the port"
- Статус: "Container failed to start"

**Решение:**
1. Проверить логи: `gcloud run logs read botyara`
2. Убедиться что установлена переменная `BOT_TOKEN`
3. Увеличить timeout: `--timeout 3600` (до часа)
4. Проверить, что приложение корректно инициализируется

### BOT_TOKEN не установлен

Приложение запустится, но webhook не будет работать. `/healthz` будет возвращать `"bot_token_set": false`.

При попытке отправить webhook будет ошибка 503:
```
Bot is not configured. Set BOT_TOKEN environment variable.
```

### Проблемы с Google Sheets

Если используется `STORAGE_BACKEND=sheets`:
1. Убедиться что `SPREADSHEET_ID` установлен
2. Проверить что Cloud Run сервис имеет доступ к Google Sheets API
3. Использовать Service Account с правильными permissions

## Логирование

Логи отправляются в Cloud Logging. Просмотреть:

```bash
gcloud run logs read botyara --limit 100

# Или в Cloud Console:
# Cloud Logging -> Logs -> Resource: Cloud Run Revision -> botyara
```

## Масштабирование

По умолчанию используются:
- Memory: 512Mi
- CPU: 1
- Min instances: 0
- Max instances: 100

Для изменения:
```bash
gcloud run deploy botyara \
  --memory 1Gi \
  --cpu 2 \
  --min-instances 1 \
  --max-instances 50
```

## Security Best Practices

1. Использовать WEBHOOK_SECRET для проверки подлинности запросов
2. Не коммитить BOT_TOKEN в репозиторий
3. Использовать Cloud Secret Manager для хранения чувствительных данных
4. Ограничить доступ к Cloud Run через IAM
5. Регулярно проверять логи на ошибки и подозрительную активность
