from __future__ import annotations

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

from app.bot.fsm.scenarios import parse_positive_int
from app.bot.fsm.states import DialogState
from app.bot.handlers_text import _menu_for_user, _reset_take_state
from app.bot.keyboards.take import take_confirm_keyboard, take_qty_keyboard
from app.models.domain import MovementRequest


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    await query.answer()

    data = query.data or ''
    user_id = update.effective_user.id
    state = DialogState(context.user_data.get('state', DialogState.IDLE.value))
    inventory = context.application.bot_data['inventory_service']
    rbac = context.application.bot_data['rbac_service']

    if data == 'cancel':
        _reset_take_state(context)
        context.user_data['state'] = DialogState.IDLE.value
        await query.edit_message_text('Сценарий отменён.')
        await query.message.reply_text('Главное меню', reply_markup=_menu_for_user(context, user_id))
        raise ApplicationHandlerStop

    if data.startswith('take:item:'):
        item = data.removeprefix('take:item:').strip()
        context.user_data['take_item'] = item
        context.user_data['take_custom_qty'] = False
        context.user_data['state'] = DialogState.TAKE_SELECT_QTY.value
        await query.edit_message_text(f'Сколько взять «{item}»?', reply_markup=take_qty_keyboard())
        raise ApplicationHandlerStop

    if data.startswith('take:qty:'):
        if state != DialogState.TAKE_SELECT_QTY:
            raise ApplicationHandlerStop

        qty_raw = data.removeprefix('take:qty:')
        if qty_raw == 'custom':
            context.user_data['take_custom_qty'] = True
            await query.message.reply_text('Введите число. Например: 3')
            raise ApplicationHandlerStop

        qty = parse_positive_int(qty_raw)
        if qty is None:
            await query.message.reply_text('Введите число. Например: 3')
            raise ApplicationHandlerStop

        item = context.user_data.get('take_item')
        if not item:
            _reset_take_state(context)
            context.user_data['state'] = DialogState.IDLE.value
            await query.message.reply_text('Сначала выберите товар.', reply_markup=_menu_for_user(context, user_id))
            raise ApplicationHandlerStop

        context.user_data['take_qty'] = qty
        context.user_data['state'] = DialogState.TAKE_CONFIRM.value
        await query.edit_message_text(f'Взять «{item}» — {qty} шт?', reply_markup=take_confirm_keyboard())
        raise ApplicationHandlerStop

    if data == 'take:confirm':
        item = context.user_data.get('take_item')
        qty = context.user_data.get('take_qty')
        if not item or not isinstance(qty, int) or qty <= 0:
            _reset_take_state(context)
            context.user_data['state'] = DialogState.IDLE.value
            await query.message.reply_text('Данные операции потеряны. Начните заново.', reply_markup=_menu_for_user(context, user_id))
            raise ApplicationHandlerStop

        stock = inventory.get_stock(item)
        if qty > stock:
            context.user_data['state'] = DialogState.TAKE_SELECT_QTY.value
            await query.message.reply_text(f'Недостаточно остатка. Доступно: {stock}', reply_markup=take_qty_keyboard())
            raise ApplicationHandlerStop

        rbac.require_permission(user_id, 'inventory.outbound')
        result = inventory.outbound(MovementRequest(item=item, quantity=qty, user_id=user_id, op_id=f'take:{update.update_id}'))

        _reset_take_state(context)
        context.user_data['state'] = DialogState.IDLE.value
        await query.edit_message_text(f'Готово. Остаток: {result.balance}')
        await query.message.reply_text('Главное меню', reply_markup=_menu_for_user(context, user_id))
        raise ApplicationHandlerStop
