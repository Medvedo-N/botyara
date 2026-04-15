"""
Базовый класс для FSM обработчиков.

Этот модуль реализует паттерн Command Router для состояний FSM.
Вместо гигантского if/elif в handlers_text.py, каждое состояние
обрабатывается отдельным методом класса, который наследует BaseFSMHandler.

Пример использования:
    class CustomFSMHandler(BaseFSMHandler):
        async def handle_add_item_name(self, update, context):
            # Логика для состояния ADD_ITEM_NAME
            pass

    # В router.py:
    handler = CustomFSMHandler()
    application.add_handler(MessageHandler(filters.TEXT, handler))
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes, ApplicationHandlerStop

from app.bot.fsm.states import DialogState
from app.di_container import container

logger = logging.getLogger(__name__)


class BaseFSMHandler:
    """
    Базовый класс маршрутизатора состояний FSM.
    
    Связывает DialogState с конкретными методами обработки.
    Автоматически маршрутизирует сообщения в зависимости от текущего состояния.
    
    Наследующий класс должен переопределить методы handle_* для каждого состояния.
    
    Пример:
        class MyFSMHandler(BaseFSMHandler):
            async def handle_add_item_name(self, update, context):
                text = update.message.text.strip()
                context.user_data['item_name'] = text
                context.user_data['state'] = DialogState.ADD_ITEM_NORM.value
                await update.message.reply_text("Введите норму:")
    """

    def __init__(self):
        """
        Инициализируем карту маршрутизации: Состояние -> Метод-обработчик.
        Все методы, начинающиеся с handle_, должны соответствовать состояниям.
        """
        self.state_routes = {
            DialogState.WAITING_STOCK: self.handle_waiting_stock,
            DialogState.TAKE_SELECT_QTY: self.handle_take_select_qty,
            DialogState.TAKE_INLINE_QTY: self.handle_take_inline_qty,
            DialogState.TAKE_CONFIRM: self.handle_take_confirm,
            DialogState.ADD_ITEM_NAME: self.handle_add_item_name,
            DialogState.ADD_ITEM_NORM: self.handle_add_item_norm,
            DialogState.ADD_ITEM_CRIT: self.handle_add_item_crit,
            DialogState.ADD_ITEM_QTY: self.handle_add_item_qty,
            DialogState.USER_ADD_ID: self.handle_user_add_id,
            DialogState.USER_ADD_NAME: self.handle_user_add_name,
            DialogState.USER_ADD_ROLE: self.handle_user_add_role,
            DialogState.WAITING_INBOUND: self.handle_waiting_inbound,
        }

    async def __call__(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Точка входа для обработки FSM сообщений.
        
        Логика:
        1. Проверяем, что это текстовое сообщение от пользователя
        2. Получаем текущее состояние из user_data
        3. Если состояние IDLE или не в routes, пропускаем (обработает text_router_handler)
        4. Иначе, вызываем соответствующий handler
        5. Выбрасываем ApplicationHandlerStop, чтобы остановить дальнейшую обработку
        """
        if update.message is None or update.effective_user is None:
            return

        state_value = context.user_data.get('state', DialogState.IDLE.value)
        try:
            state = DialogState(state_value)
        except ValueError:
            logger.warning(json.dumps({'event': 'invalid_state', 'state_value': state_value}))
            return

        if state == DialogState.IDLE:
            # Не в FSM - пропускаем, обработает text_router_handler
            return

        handler_method = self.state_routes.get(state)
        if not handler_method:
            # Неизвестное состояние
            logger.warning(json.dumps({'event': 'unknown_state', 'state': state.value}))
            return

        try:
            # Делегируем логику конкретному методу
            await handler_method(update, context)
        except Exception as exc:
            await self.handle_error(update, context, exc)
        finally:
            # Здесь можно добавить логику, которая срабатывает после любого обработчика
            pass

        # Останавливаем дальнейшую обработку цепочки обработчиков
        raise ApplicationHandlerStop

    # --- Обработчики конкретных состояний (переопределить в наследующем классе) ---

    async def handle_waiting_stock(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка состояния WAITING_STOCK (проверка остатков)."""
        pass

    async def handle_take_select_qty(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка состояния TAKE_SELECT_QTY (выбор количества для взятия)."""
        pass

    async def handle_take_inline_qty(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка состояния TAKE_INLINE_QTY (ввод количества в inline запросе)."""
        pass

    async def handle_take_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка состояния TAKE_CONFIRM (подтверждение выдачи товара)."""
        pass

    async def handle_add_item_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка состояния ADD_ITEM_NAME (ввод названия товара)."""
        pass

    async def handle_add_item_norm(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка состояния ADD_ITEM_NORM (ввод нормы товара)."""
        pass

    async def handle_add_item_crit(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка состояния ADD_ITEM_CRIT (ввод критического минимума)."""
        pass

    async def handle_add_item_qty(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка состояния ADD_ITEM_QTY (ввод начального количества товара)."""
        pass

    async def handle_user_add_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка состояния USER_ADD_ID (ввод ID пользователя)."""
        pass

    async def handle_user_add_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка состояния USER_ADD_NAME (ввод имени пользователя)."""
        pass

    async def handle_user_add_role(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка состояния USER_ADD_ROLE (ввод роли пользователя)."""
        pass

    async def handle_waiting_inbound(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка состояния WAITING_INBOUND (ввод количества для прихода товара)."""
        pass

    async def handle_error(self, update: Update, context: ContextTypes.DEFAULT_TYPE, exc: Exception) -> None:
        """
        Централизованная обработка ошибок для всех FSM обработчиков.
        
        Здесь должны обрабатываться типичные ошибки:
        - PermissionError: недостаточно прав
        - ValueError: некорректный ввод (неверное число, неизвестный товар, и т.д.)
        - Другие исключения: логирование и ответ пользователю
        
        Args:
            update: Telegram update
            context: контекст (user_data, bot, и т.д.)
            exc: исключение, которое было выброшено
        """
        user_id = update.effective_user.id if update.effective_user else "unknown"

        if isinstance(exc, PermissionError):
            logger.warning(json.dumps({'event': 'permission_denied', 'user_id': user_id, 'error': str(exc)}))
            await update.message.reply_text("❌ Недостаточно прав для этого действия.")

        elif isinstance(exc, ValueError):
            logger.info(json.dumps({'event': 'invalid_input', 'user_id': user_id, 'error': str(exc)}))
            await update.message.reply_text(f"❌ Ошибка: {exc}\n\nПопробуйте ещё раз.")

        else:
            logger.exception(json.dumps({'event': 'fsm_handler_error', 'user_id': user_id, 'error': str(exc)}))
            await update.message.reply_text("❌ Произошла ошибка. Попробуйте позже или напишите администратору.")
