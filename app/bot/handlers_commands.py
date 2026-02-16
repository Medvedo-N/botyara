from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.fsm.states import DialogState
from app.bot.keyboards.main import main_menu


def _menu_for_user(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    rbac = context.application.bot_data['rbac_service']
    return main_menu(
        can_inbound=rbac.has_permission(user_id, 'inventory.inbound'),
        can_users_view=rbac.has_permission(user_id, 'users.view'),
    )


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    context.user_data['state'] = DialogState.IDLE.value
    await update.message.reply_text('Ботяра готов. Выберите действие.', reply_markup=_menu_for_user(context, update.effective_user.id))


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text('Формат ввода для операций: <товар>,<кол-во>. Например: Фильтр,2')


async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    context.user_data['state'] = DialogState.IDLE.value
    await update.message.reply_text('Состояние сброшено.', reply_markup=_menu_for_user(context, update.effective_user.id))
