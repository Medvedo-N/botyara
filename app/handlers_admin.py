from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.handlers_sheet import sheet_command as sheet_cmd


async def sheet_admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin wrapper for /sheet command."""
    await sheet_cmd(update, context)
