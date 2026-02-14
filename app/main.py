from fastapi import FastAPI
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import asyncio

from app.config import VERSION, TELEGRAM_TOKEN

app = FastAPI(title="botyara", version=VERSION)

telegram_app: Application | None = None


@app.on_event("startup")
async def startup():
    global telegram_app

    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start_command))

    asyncio.create_task(telegram_app.initialize())
    asyncio.create_task(telegram_app.start())


@app.on_event("shutdown")
async def shutdown():
    if telegram_app:
        await telegram_app.stop()
        await telegram_app.shutdown()


@app.get("/")
async def root():
    return {
        "status": "ok",
        "version": VERSION
    }


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Ботяра запущен ✅\nВерсия: {VERSION}"
    )
