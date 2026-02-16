from __future__ import annotations

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

from app.bot.fsm.scenarios import parse_positive_int
from app.bot.fsm.states import DialogState
from app.bot.handlers_text import (
    _menu_for_user,
    _reset_add_item_state,
    _reset_all,
    _reset_take_state,
    _reset_user_add_state,
    build_stock_page,
)
from app.bot.keyboards.take import take_confirm_keyboard, take_qty_keyboard
from app.models.domain import MovementRequest, Role


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
    storage = inventory.storage

    if data == 'cancel':
        _reset_all(context)
        context.user_data['state'] = DialogState.IDLE.value
        await query.edit_message_text('Сценарий отменён.')
        await query.message.reply_text('Главное меню', reply_markup=_menu_for_user(context, user_id))
        raise ApplicationHandlerStop

    if data.startswith('stock:page:') or data.startswith('stock:refresh:'):
        try:
            page = int(data.split(':')[-1])
        except ValueError:
            page = 1
        text, markup, _ = build_stock_page(context, page)
        await query.edit_message_text(text, reply_markup=markup)
        raise ApplicationHandlerStop

    if data == 'stock:menu':
        _reset_all(context)
        context.user_data['state'] = DialogState.IDLE.value
        await query.edit_message_text('Возврат в меню.')
        await query.message.reply_text('Главное меню', reply_markup=_menu_for_user(context, user_id))
        raise ApplicationHandlerStop

    if data == 'users:add':
        if not rbac.has_permission(user_id, 'users.view'):
            await query.message.reply_text('Нет доступа.', reply_markup=_menu_for_user(context, user_id))
            raise ApplicationHandlerStop
        _reset_user_add_state(context)
        context.user_data['state'] = DialogState.USER_ADD_ID.value
        await query.message.reply_text('Введите TG ID:')
        raise ApplicationHandlerStop

    if data.startswith('userrole:'):
        if state != DialogState.USER_ADD_ROLE:
            raise ApplicationHandlerStop
        role_key = data.removeprefix('userrole:')
        if role_key not in {r.value for r in Role if r != Role.NO_ACCESS}:
            await query.message.reply_text('Неизвестная роль.')
            raise ApplicationHandlerStop
        new_user_id = context.user_data.get('new_user_id')
        new_user_name = context.user_data.get('new_user_name')
        if not isinstance(new_user_id, int) or not isinstance(new_user_name, str):
            _reset_user_add_state(context)
            context.user_data['state'] = DialogState.IDLE.value
            await query.message.reply_text('Данные пользователя потеряны. Начните заново.', reply_markup=_menu_for_user(context, user_id))
            raise ApplicationHandlerStop
        storage.upsert_user(new_user_id, new_user_name, Role(role_key), active=True)
        _reset_user_add_state(context)
        context.user_data['state'] = DialogState.IDLE.value
        await query.edit_message_text(f'Пользователь сохранён: {new_user_name} ({role_key})')
        await query.message.reply_text('Главное меню', reply_markup=_menu_for_user(context, user_id))
        raise ApplicationHandlerStop

    if data == 'additem:start':
        if not rbac.has_permission(user_id, 'inventory.inbound'):
            await query.message.reply_text('Нет доступа к добавлению товара.', reply_markup=_menu_for_user(context, user_id))
            raise ApplicationHandlerStop
        _reset_add_item_state(context)
        context.user_data['state'] = DialogState.ADD_ITEM_NAME.value
        await query.message.reply_text('Введите название товара:')
        raise ApplicationHandlerStop

    if data == 'additem:save':
        name = context.user_data.get('add_item_name')
        norm = context.user_data.get('add_item_norm')
        crit = context.user_data.get('add_item_crit')
        qty = context.user_data.get('add_item_qty')
        if not isinstance(name, str) or not isinstance(norm, int) or not isinstance(crit, int) or not isinstance(qty, int):
            await query.message.reply_text('Данные товара потеряны. Начните заново.', reply_markup=_menu_for_user(context, user_id))
            _reset_add_item_state(context)
            context.user_data['state'] = DialogState.IDLE.value
            raise ApplicationHandlerStop
        storage.add_item(name, norm=norm, crit_min=crit, qty=qty, is_active=True)
        _reset_add_item_state(context)
        context.user_data['state'] = DialogState.IDLE.value
        await query.edit_message_text(f'Товар «{name}» сохранён.')
        await query.message.reply_text('Главное меню', reply_markup=_menu_for_user(context, user_id))
        raise ApplicationHandlerStop

    if data.startswith('delete:item:'):
        item = data.removeprefix('delete:item:').strip()
        role = rbac.get_role(user_id)
        if role not in {Role.DEV, Role.SENIOR_MANAGER}:
            await query.message.reply_text('Недостаточно прав для удаления товара.', reply_markup=_menu_for_user(context, user_id))
            raise ApplicationHandlerStop
        storage.deactivate_item(item)
        await query.edit_message_text(f'Товар «{item}» убран из списка (is_active=false).')
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

        reorder = context.application.bot_data.get('reorder_service')
        if reorder is not None:
            await reorder.check_and_upsert(item)

        _reset_take_state(context)
        context.user_data['state'] = DialogState.IDLE.value
        await query.edit_message_text(f'Готово. Остаток: {result.balance}')
        await query.message.reply_text('Главное меню', reply_markup=_menu_for_user(context, user_id))
        raise ApplicationHandlerStop
