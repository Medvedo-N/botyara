from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from app.config import SPREADSHEET_ID
from app.sheets_client import read_range

from app.config import VERSION, TELEGRAM_TOKEN

app = FastAPI(title="botyara", version=VERSION)

telegram_app: Application | None = None

@app.get("/sheet-test")
async def sheet_test():
    values = read_range(SPREADSHEET_ID, "A1")
    return {"ok": True, "range": "A1", "values": values}


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Ботяра запущен ✅\nВерсия: {VERSION}")


@app.on_event("startup")
async def startup():
    global telegram_app
    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start_command))
    await telegram_app.initialize()  # важно: только initialize, без start/polling


@app.get("/")
async def root():
    return {"status": "ok", "version": VERSION}


@app.post("/webhook")
async def webhook(request: Request):
    """Telegram будет POST'ить апдейты сюда."""
    if telegram_app is None:
        return {"ok": False, "error": "telegram_app not initialized"}

    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}

