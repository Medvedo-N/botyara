from __future__ import annotations

import json
import logging
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

from app.bot.fsm.scenarios import parse_inventory_input, parse_positive_int, parse_stock_item_input, start_state_for_action
from app.bot.fsm.states import DialogState
from app.bot.keyboards.main import main_menu
from app.bot.keyboards.stock import stock_pagination_keyboard
from app.bot.keyboards.take import take_confirm_keyboard, take_items_keyboard, take_qty_keyboard
from app.models.domain import MovementRequest

logger = logging.getLogger(__name__)
PAGE_SIZE = 12


def _stock_marker(qty: int, norm: int | None, crit: int | None) -> str:
    # Status policy:
    # - 🔴 if qty <= crit
    # - 🟡 if crit < qty <= norm
    # - 🟢 if qty > norm
    crit_value = crit if crit is not None else 0
    norm_value = norm if norm is not None else crit_value
    if qty <= crit_value:
        return '🔴'
    if qty <= norm_value:
        return '🟡'
    return '🟢'


def _reset_take_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in ['take_item', 'take_qty', 'take_custom_qty']:
        context.user_data.pop(key, None)


def _reset_add_item_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in ['add_item_name', 'add_item_norm', 'add_item_crit', 'add_item_qty']:
        context.user_data.pop(key, None)


def _reset_user_add_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in ['new_user_id', 'new_user_name']:
        context.user_data.pop(key, None)


def _reset_all(context: ContextTypes.DEFAULT_TYPE) -> None:
    _reset_take_state(context)
    _reset_add_item_state(context)
    _reset_user_add_state(context)


def _format_stock_lines(rows) -> list[str]:
    return [
        f"{_stock_marker(entry.quantity, entry.norm, entry.crit_min)} {entry.name} — {entry.quantity} (норма {entry.norm}, крит {entry.crit_min})"
        for entry in rows
    ]


def _format_reorder_line(*, name: str, qty: int, norm: int) -> str:
    need = max(norm - qty, 0)
    return f"• {name} — остаток: {qty}, норма: {norm}, заказать: {need}"


def build_reorder_request_text(context: ContextTypes.DEFAULT_TYPE, *, user_id: int) -> str:
    logger.info(json.dumps({'event': 'reorder_request_started', 'user_id': user_id}))
    inventory = context.application.bot_data['inventory_service']
    try:
        rows = inventory.storage.list_stock()
    except Exception as exc:
        logger.exception(json.dumps({'event': 'reorder_request_failed', 'user_id': user_id, 'error': str(exc)}))
        return 'Не удалось сформировать заявку. Попробуйте позже.'

    if not rows:
        logger.info(json.dumps({'event': 'reorder_request_built', 'user_id': user_id, 'count': 0, 'status': 'empty'}))
        return 'Список товаров пуст.'

    lines: list[str] = []
    invalid_rows = 0
    for row in rows:
        name = str(getattr(row, 'name', '')).strip()
        try:
            qty = int(getattr(row, 'quantity', 0))
            norm = int(getattr(row, 'norm', 0))
        except Exception:
            invalid_rows += 1
            continue
        if not name:
            invalid_rows += 1
            continue
        if qty < norm:
            lines.append(_format_reorder_line(name=name, qty=qty, norm=norm))

    if invalid_rows:
        logger.warning(json.dumps({'event': 'reorder_invalid_row', 'user_id': user_id, 'count': invalid_rows}))

    if not lines:
        logger.info(json.dumps({'event': 'reorder_request_built', 'user_id': user_id, 'count': 0, 'status': 'all_norm'}))
        return 'Все товары в норме. Заявка не требуется.'

    logger.info(json.dumps({'event': 'reorder_request_built', 'user_id': user_id, 'count': len(lines), 'status': 'ok'}))
    return '📋 Заявка на закуп\n\n' + '\n'.join(lines)


def build_stock_page(context: ContextTypes.DEFAULT_TYPE, page: int, page_size: int = PAGE_SIZE) -> tuple[str, InlineKeyboardMarkup | None, int]:
    inventory = context.application.bot_data['inventory_service']
    if not hasattr(inventory, 'storage'):
        fallback = inventory.list_stock()
        if fallback == 'Остатков нет.':
            return 'Остатков нет.', None, 1
        return fallback, None, 1

    logger.info(json.dumps({'event': 'stock_page_build_started', 'requested_page': page}))
    try:
        data = inventory.storage.list_stock()
    except Exception as exc:
        logger.exception(
            json.dumps(
                {
                    'event': 'stock_page_build_failed',
                    'requested_page': page,
                    'error': str(exc),
                }
            )
        )
        return 'Не удалось загрузить остатки. Попробуйте позже.', None, 1
    if not data:
        return 'Остатков нет.', None, 1
    data = sorted(data, key=lambda item: item.name.lower())
    lines = _format_stock_lines(data)

    total_pages = max((len(lines) + page_size - 1) // page_size, 1)
    safe_page = min(max(page, 1), total_pages)
    start = (safe_page - 1) * page_size
    end = start + page_size
    page_lines = lines[start:end]
    header = f'Остатки (стр. {safe_page}/{total_pages}):'
    text = f"{header}\n" + '\n'.join(page_lines)
    markup = stock_pagination_keyboard(page=safe_page, total_pages=total_pages)
    return text, markup, safe_page


async def show_stock_list(update: Update, context: ContextTypes.DEFAULT_TYPE, *, page: int = 1) -> None:
    if update.message is None:
        return
    text, markup, _ = build_stock_page(context, page)
    await update.message.reply_text(text, reply_markup=markup or _menu_for_user(context, update.effective_user.id))


async def fsm_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    state = DialogState(context.user_data.get('state', DialogState.IDLE.value))
    if state == DialogState.IDLE:
        return
    await text_router_handler(update, context)


def _menu_for_user(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    rbac = context.application.bot_data['rbac_service']
    try:
        can_inbound = rbac.has_permission(user_id, 'inventory.inbound')
        can_users_view = rbac.has_permission(user_id, 'users.view')
    except Exception:
        logger.exception('menu_permissions_failed user_id=%s', user_id)
        can_inbound = True
        can_users_view = False
    return main_menu(can_inbound=can_inbound, can_users_view=can_users_view)


async def _start_take_flow(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    rbac = context.application.bot_data['rbac_service']
    if not rbac.has_permission(user_id, 'inventory.outbound'):
        await update.message.reply_text('Нет прав на операцию «Взять».', reply_markup=_menu_for_user(context, user_id))
        return

    logger.info(json.dumps({'event': 'take_flow_started', 'user_id': user_id}))
    inventory = context.application.bot_data['inventory_service']
    try:
        rows = inventory.storage.list_stock()
    except Exception as exc:
        logger.exception(json.dumps({'event': 'take_flow_failed', 'user_id': user_id, 'error': str(exc)}))
        context.user_data['state'] = DialogState.IDLE.value
        _reset_take_state(context)
        await update.message.reply_text('Не удалось загрузить товары для выдачи. Попробуйте позже.', reply_markup=_menu_for_user(context, user_id))
        return
    if not rows:
        context.user_data['state'] = DialogState.IDLE.value
        _reset_take_state(context)
        await update.message.reply_text('Список товаров пуст. Сначала сделайте приход.', reply_markup=_menu_for_user(context, user_id))
        return
    context.user_data['state'] = DialogState.TAKE_SELECT_ITEM.value
    _reset_take_state(context)
    await update.message.reply_text('Выберите товар:', reply_markup=take_items_keyboard(rows))


async def text_router_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return

    user_id = update.effective_user.id
    text = (update.message.text or '').strip()
    normalized = _normalize_text(text)
    state = DialogState(context.user_data.get('state', DialogState.IDLE.value))

    rbac_for_log = context.application.bot_data['rbac_service']
    try:
        if hasattr(rbac_for_log, 'get_role'):
            role = rbac_for_log.get_role(user_id).value
        else:
            role = 'unknown'
    except Exception:
        role = 'role_lookup_failed'
        logger.exception('router_role_lookup_failed user_id=%s', user_id)
    logger.info('ROUTER HIT text=%s state=%s role=%s', normalized, state.value, role)

    action = _menu_action(normalized)
    if action is not None:
        if action == 'CANCEL':
            _reset_all(context)
            context.user_data['state'] = DialogState.IDLE.value
            await update.message.reply_text('Сценарий отменён.', reply_markup=_menu_for_user(context, user_id))
            raise ApplicationHandlerStop

        if action == 'USERS':
            rbac = context.application.bot_data['rbac_service']
            if not rbac.has_permission(user_id, 'users.view'):
                await update.message.reply_text('Нет доступа к разделу пользователей.', reply_markup=_menu_for_user(context, user_id))
            else:
                kb = InlineKeyboardMarkup([[InlineKeyboardButton('➕ Добавить', callback_data='users:add')], [InlineKeyboardButton('❌ Отмена', callback_data='cancel')]])
                await update.message.reply_text('👥 Пользователи', reply_markup=kb)
            _reset_all(context)
            context.user_data['state'] = DialogState.IDLE.value
            raise ApplicationHandlerStop

        if action == 'OUT':
            _reset_all(context)
            await _start_take_flow(update, context, user_id)
            raise ApplicationHandlerStop

        if action == 'STOCK':
            logger.info(json.dumps({'event': 'stock_action_received', 'user_id': user_id}))
            _reset_all(context)
            context.user_data['state'] = DialogState.IDLE.value
            rbac_service = context.application.bot_data['rbac_service']
            try:
                can_view_stock = rbac_service.has_permission(user_id, 'inventory.view')
            except Exception as exc:
                logger.exception(
                    json.dumps(
                        {
                            'event': 'stock_permission_check_failed',
                            'user_id': user_id,
                            'error': str(exc),
                        }
                    )
                )
                await update.message.reply_text('Не удалось проверить права на просмотр остатков. Попробуйте позже.', reply_markup=_menu_for_user(context, user_id))
                raise ApplicationHandlerStop
            if not can_view_stock:
                await update.message.reply_text('Нет прав на просмотр остатков.', reply_markup=_menu_for_user(context, user_id))
                raise ApplicationHandlerStop
            await show_stock_list(update, context, page=1)
            raise ApplicationHandlerStop

        if action == 'REORDER':
            _reset_all(context)
            context.user_data['state'] = DialogState.IDLE.value
            rbac_service = context.application.bot_data['rbac_service']
            try:
                can_view_stock = rbac_service.has_permission(user_id, 'inventory.view')
            except Exception:
                await update.message.reply_text('Не удалось сформировать заявку. Попробуйте позже.', reply_markup=_menu_for_user(context, user_id))
                raise ApplicationHandlerStop
            if not can_view_stock:
                await update.message.reply_text('Нет прав на формирование заявки.', reply_markup=_menu_for_user(context, user_id))
                raise ApplicationHandlerStop
            text_out = build_reorder_request_text(context, user_id=user_id)
            await update.message.reply_text(text_out, reply_markup=_menu_for_user(context, user_id))
            raise ApplicationHandlerStop

        if state != DialogState.IDLE:
            _reset_all(context)
            context.user_data['state'] = DialogState.IDLE.value

        context.user_data['state'] = start_state_for_action(action).value
        prompts = {
            'IN': 'Введите приход: <товар>,<кол-во>',
        }
        await update.message.reply_text(prompts[action], reply_markup=_menu_for_user(context, user_id))
        raise ApplicationHandlerStop

    inventory_service = context.application.bot_data['inventory_service']
    rbac_service = context.application.bot_data['rbac_service']

    try:
        if state == DialogState.WAITING_STOCK:
            item = parse_stock_item_input(text)
            if not item:
                await update.message.reply_text('Ожидаю название товара. Пример: мыло. Или нажмите ❌ Отмена', reply_markup=_menu_for_user(context, user_id))
                raise ApplicationHandlerStop

            rbac_service.require_permission(user_id, 'inventory.view')
            stock = inventory_service.get_stock(item=item)
            if hasattr(inventory_service, 'storage'):
                norm, crit = inventory_service.storage.get_item_limits(item)
            else:
                norm, crit = (None, None)
            marker = _stock_marker(stock, norm, crit)
            text_out = f'{marker} {item} — {stock}'
            if norm is not None and crit is not None:
                text_out += f' (норма {norm}, крит {crit})'

            kb = None
            if rbac_service.has_permission(user_id, 'users.view'):
                kb = InlineKeyboardMarkup([[InlineKeyboardButton('🗑 Убрать товар', callback_data=f'delete:item:{item}')]])
            await update.message.reply_text(text_out, reply_markup=kb or _menu_for_user(context, user_id))
            context.user_data['state'] = DialogState.IDLE.value
            raise ApplicationHandlerStop

        if state == DialogState.TAKE_SELECT_QTY and context.user_data.get('take_custom_qty'):
            value = parse_positive_int(text)
            if value is None:
                await update.message.reply_text('Введите число. Например: 3', reply_markup=take_qty_keyboard())
                raise ApplicationHandlerStop
            context.user_data['take_qty'] = value
            context.user_data['take_custom_qty'] = False
            context.user_data['state'] = DialogState.TAKE_CONFIRM.value
            item = context.user_data.get('take_item', '')
            await update.message.reply_text(f'Взять «{item}» — {value} шт?', reply_markup=take_confirm_keyboard())
            raise ApplicationHandlerStop

        if state == DialogState.ADD_ITEM_NAME:
            context.user_data['add_item_name'] = text
            context.user_data['state'] = DialogState.ADD_ITEM_NORM.value
            await update.message.reply_text('Введите норму (число):')
            raise ApplicationHandlerStop

        if state == DialogState.ADD_ITEM_NORM:
            value = parse_positive_int(text)
            if value is None:
                await update.message.reply_text('Введите число. Например: 50')
                raise ApplicationHandlerStop
            context.user_data['add_item_norm'] = value
            context.user_data['state'] = DialogState.ADD_ITEM_CRIT.value
            await update.message.reply_text('Введите крит минимум (число):')
            raise ApplicationHandlerStop

        if state == DialogState.ADD_ITEM_CRIT:
            value = parse_positive_int(text)
            if value is None:
                await update.message.reply_text('Введите число. Например: 5')
                raise ApplicationHandlerStop
            context.user_data['add_item_crit'] = value
            context.user_data['state'] = DialogState.ADD_ITEM_QTY.value
            await update.message.reply_text('Введите количество прихода сейчас (число):')
            raise ApplicationHandlerStop

        if state == DialogState.ADD_ITEM_QTY:
            value = parse_positive_int(text)
            if value is None:
                await update.message.reply_text('Введите число. Например: 20')
                raise ApplicationHandlerStop
            context.user_data['add_item_qty'] = value
            kb = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton('✅ Сохранить', callback_data='additem:save')],
                    [InlineKeyboardButton('❌ Отмена', callback_data='cancel')],
                ]
            )
            await update.message.reply_text('Сохранить товар?', reply_markup=kb)
            raise ApplicationHandlerStop

        if state == DialogState.USER_ADD_ID:
            if not text.isdigit():
                await update.message.reply_text('Введите TG ID числом.')
                raise ApplicationHandlerStop
            context.user_data['new_user_id'] = int(text)
            context.user_data['state'] = DialogState.USER_ADD_NAME.value
            await update.message.reply_text('Введите имя пользователя:')
            raise ApplicationHandlerStop

        if state == DialogState.USER_ADD_NAME:
            context.user_data['new_user_name'] = text
            context.user_data['state'] = DialogState.USER_ADD_ROLE.value
            kb = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton('user', callback_data='userrole:user'), InlineKeyboardButton('manager', callback_data='userrole:manager')],
                    [InlineKeyboardButton('senior_manager', callback_data='userrole:senior_manager'), InlineKeyboardButton('dev', callback_data='userrole:dev')],
                    [InlineKeyboardButton('❌ Отмена', callback_data='cancel')],
                ]
            )
            await update.message.reply_text('Выберите роль:', reply_markup=kb)
            raise ApplicationHandlerStop

        parsed = parse_inventory_input(text)
        if parsed is None:
            if state != DialogState.IDLE:
                await update.message.reply_text('Используйте кнопки. Или нажмите ❌ Отмена', reply_markup=_menu_for_user(context, user_id))
                raise ApplicationHandlerStop
            await fallback_handler(update, context)
            raise ApplicationHandlerStop

        item, quantity = parsed
        if state == DialogState.WAITING_INBOUND:
            rbac_service.require_permission(user_id, 'inventory.inbound')
            result = inventory_service.inbound(MovementRequest(item=item, quantity=quantity, user_id=user_id))
            kb = InlineKeyboardMarkup([[InlineKeyboardButton('➕ Добавить товар', callback_data='additem:start')]])
            await update.message.reply_text(f'Приход выполнен. Остаток: {result.balance}', reply_markup=kb)
        else:
            await fallback_handler(update, context)
            raise ApplicationHandlerStop
    except PermissionError:
        await update.message.reply_text('Нет прав на эту операцию.', reply_markup=_menu_for_user(context, user_id))
    except ValueError as exc:
        await update.message.reply_text(f'Ошибка операции: {exc}', reply_markup=_menu_for_user(context, user_id))

    _reset_all(context)
    context.user_data['state'] = DialogState.IDLE.value
    raise ApplicationHandlerStop


async def fallback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    state = context.user_data.get('state', DialogState.IDLE.value)
    logger.info('FALLBACK HIT text=%s state=%s', update.message.text, state)
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
    if 'пользоват' in normalized_text:
        return 'USERS'
    if 'остатк' in normalized_text:
        return 'STOCK'
    if 'заявк' in normalized_text:
        return 'REORDER'
    if normalized_text.startswith('приход') or ' приход' in normalized_text or 'поступлен' in normalized_text:
        return 'IN'
    if normalized_text.startswith('взять') or 'взят' in normalized_text or 'выдач' in normalized_text:
        return 'OUT'
    return None
