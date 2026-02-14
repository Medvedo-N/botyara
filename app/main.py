from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from app.config import VERSION, TELEGRAM_TOKEN, SPREADSHEET_ID
from app.sheets_client import read_range

app = FastAPI(title="botyara", version=VERSION)

telegram_app: Application | None = None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Ботяра запущен ✅\nВерсия: {VERSION}"
    )


async def sheet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    values = read_range(SPREADSHEET_ID, "A1")
    a1 = values[0][0] if values and values[0] else "(пусто)"
    await update.message.reply_text(f"A1: {a1}")


@app.on_event("startup")
async def startup():
    global telegram_app

    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(CommandHandler("sheet", sheet_command))

    await telegram_app.initialize()


@app.get("/")
async def root():
    return {"status": "ok", "version": VERSION}


@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}


# (можно оставить для диагностики)
@app.get("/sheet-test")
async def sheet_test():
    values = read_range(SPREADSHEET_ID, "A1")
    return {"ok": True, "range": "A1", "values": values}
