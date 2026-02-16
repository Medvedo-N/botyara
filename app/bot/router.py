from __future__ import annotations

from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from app.bot.handlers_callbacks import callback_handler
from app.bot.handlers_commands import cancel_handler, help_handler, start_handler
from app.bot.handlers_text import fallback_handler, fsm_text_handler, text_router_handler


def register_handlers(application: Application) -> None:
    # Order: Commands -> Callbacks -> FSM handler (if active) -> Text Router -> Fallback
    application.add_handler(CommandHandler('start', start_handler))
    application.add_handler(CommandHandler('help', help_handler))
    application.add_handler(CommandHandler('cancel', cancel_handler))

    application.add_handler(CallbackQueryHandler(callback_handler))

    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), fsm_text_handler), group=1)
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), text_router_handler), group=2)
    application.add_handler(MessageHandler(filters.ALL, fallback_handler), group=3)
