from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.config import SPREADSHEET_ID
from app.sheets_client import read_range


async def sheet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    values = read_range(SPREADSHEET_ID, "A1")
    a1 = values[0][0] if values and values[0] else "(пусто)"
    await update.message.reply_text(f"A1: {a1}")