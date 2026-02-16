from __future__ import annotations

import json

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.fsm.states import DialogState
from app.bot.keyboards.main import main_menu


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    context.user_data['state'] = DialogState.IDLE.value
    await update.message.reply_text('Ботяра готов. Выберите действие.', reply_markup=main_menu())


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text('Формат ввода для операций: <товар>,<кол-во>. Например: Фильтр,2')


async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    context.user_data['state'] = DialogState.IDLE.value
    await update.message.reply_text('Состояние сброшено.', reply_markup=main_menu())


def log_update_context(update: Update, state: str, action: str) -> str:
    payload = {
        'event': 'telegram_update',
        'update_id': update.update_id,
        'user_id': update.effective_user.id if update.effective_user else None,
        'chat_id': update.effective_chat.id if update.effective_chat else None,
        'state': state,
        'action': action,
    }
    return json.dumps(payload, ensure_ascii=False)
