from __future__ import annotations

import logging
import re

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

from app.bot.fsm.scenarios import parse_inventory_input, parse_stock_item_input, start_state_for_action
from app.bot.fsm.states import DialogState
from app.bot.keyboards.main import main_menu
from app.models.domain import MovementRequest

logger = logging.getLogger(__name__)



async def fsm_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    state = DialogState(context.user_data.get('state', DialogState.IDLE.value))
    if state == DialogState.IDLE:
        return
    await text_router_handler(update, context)


async def text_router_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return

    text = (update.message.text or '').strip()
    normalized = _normalize_text(text)
    state = DialogState(context.user_data.get('state', DialogState.IDLE.value))

    logger.info('ROUTER HIT text=%s state=%s', normalized, state.value)

    action = _menu_action(normalized)
    if action is not None:
        if action == 'CANCEL':
            context.user_data['state'] = DialogState.IDLE.value
            await update.message.reply_text('Сценарий отменён.', reply_markup=main_menu())
            raise ApplicationHandlerStop

        if state != DialogState.IDLE:
            context.user_data['state'] = DialogState.IDLE.value

        context.user_data['state'] = start_state_for_action(action).value
        prompts = {
            'IN': 'Введите приход: <товар>,<кол-во>',
            'OUT': 'Введите выдачу: <товар>,<кол-во>',
            'MOVE': 'Введите перемещение: <товар>,<кол-во> (между main -> reserve)',
            'WRITE_OFF': 'Введите списание: <товар>,<кол-во>',
            'STOCK': 'Введите товар для остатков: <товар> (можно: товар,1 или товар:1)',
        }
        await update.message.reply_text(prompts[action], reply_markup=main_menu())
        raise ApplicationHandlerStop

    inventory_service = context.application.bot_data['inventory_service']
    rbac_service = context.application.bot_data['rbac_service']

    try:
        if state == DialogState.WAITING_STOCK:
            item = parse_stock_item_input(text)
            if not item:
                await update.message.reply_text(
                    'Ожидаю название товара. Пример: мыло. Или нажмите ❌ Отмена',
                    reply_markup=main_menu(),
                )
                raise ApplicationHandlerStop

            rbac_service.require_permission(update.effective_user.id, 'inventory.read')
            stock = inventory_service.get_stock(item=item, location='main')
            await update.message.reply_text(f'Остаток {item}: {stock}', reply_markup=main_menu())
            context.user_data['state'] = DialogState.IDLE.value
            raise ApplicationHandlerStop

        parsed = parse_inventory_input(text)
        if parsed is None:
            if state != DialogState.IDLE:
                await update.message.reply_text(
                    'Ожидаю название товара. Пример: мыло. Или нажмите ❌ Отмена',
                    reply_markup=main_menu(),
                )
                raise ApplicationHandlerStop
            await fallback_handler(update, context)
            raise ApplicationHandlerStop

        item, quantity = parsed
        if state == DialogState.WAITING_INBOUND:
            rbac_service.require_permission(update.effective_user.id, 'inventory.inbound')
            result = inventory_service.inbound(MovementRequest(item=item, quantity=quantity, user_id=update.effective_user.id, to_location='main'))
            await update.message.reply_text(f'Приход выполнен. Остаток: {result.balance}', reply_markup=main_menu())
        elif state == DialogState.WAITING_OUTBOUND:
            rbac_service.require_permission(update.effective_user.id, 'inventory.outbound')
            result = inventory_service.outbound(MovementRequest(item=item, quantity=quantity, user_id=update.effective_user.id, from_location='main'))
            await update.message.reply_text(f'Выдача выполнена. Остаток: {result.balance}', reply_markup=main_menu())
        elif state == DialogState.WAITING_MOVE:
            rbac_service.require_permission(update.effective_user.id, 'inventory.move')
            result = inventory_service.move(
                MovementRequest(item=item, quantity=quantity, user_id=update.effective_user.id, from_location='main', to_location='reserve')
            )
            await update.message.reply_text(f'Перемещение выполнено. Остаток в reserve: {result.balance}', reply_markup=main_menu())
        elif state == DialogState.WAITING_WRITE_OFF:
            rbac_service.require_permission(update.effective_user.id, 'inventory.write_off')
            result = inventory_service.write_off(MovementRequest(item=item, quantity=quantity, user_id=update.effective_user.id, from_location='main'))
            await update.message.reply_text(f'Списание выполнено. Остаток: {result.balance}', reply_markup=main_menu())
        else:
            await fallback_handler(update, context)
            raise ApplicationHandlerStop
    except PermissionError:
        await update.message.reply_text('Нет прав на эту операцию.', reply_markup=main_menu())
    except ValueError as exc:
        await update.message.reply_text(f'Ошибка операции: {exc}', reply_markup=main_menu())

    context.user_data['state'] = DialogState.IDLE.value
    raise ApplicationHandlerStop


async def fallback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    logger.info('FALLBACK HIT text=%s', update.message.text)
    await update.message.reply_text('Не понял запрос. Нажмите /help.', reply_markup=main_menu())


def _normalize_text(text: str) -> str:
    lowered = text.lower()
    no_symbols = re.sub(r'[^\w\s]+', ' ', lowered, flags=re.UNICODE)
    return ' '.join(no_symbols.split())


def _menu_action(normalized_text: str) -> str | None:
    if not normalized_text:
        return None

    if 'отмена' in normalized_text:
        return 'CANCEL'
    if 'остатк' in normalized_text:
        return 'STOCK'
    if normalized_text.startswith('приход') or ' приход' in normalized_text or 'поступлен' in normalized_text:
        return 'IN'
    if normalized_text.startswith('взять') or 'взять' in normalized_text or 'выдач' in normalized_text:
        return 'OUT'
    if normalized_text.startswith('перемещ') or 'перемещ' in normalized_text:
        return 'MOVE'
    if normalized_text.startswith('брак') or 'брак' in normalized_text or 'списан' in normalized_text:
        return 'WRITE_OFF'
    return None
