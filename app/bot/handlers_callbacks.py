from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer('Callback принят')
