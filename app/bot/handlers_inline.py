from __future__ import annotations

import difflib
import json
import logging
from urllib.parse import quote, unquote

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InlineQueryResultCachedPhoto,
    InputTextMessageContent,
    Update,
)
from telegram.ext import ApplicationHandlerStop, ContextTypes
from app.bot.fsm.states import DialogState
from app.models.domain import MovementRequest

logger = logging.getLogger(__name__)


def _encode_item(value: str) -> str:
    return quote(value, safe='')


def _decode_item(value: str) -> str:
    return unquote(value)


def _take_qty_keyboard(item_name: str) -> InlineKeyboardMarkup:
    encoded = _encode_item(item_name)
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton('Взять 1', callback_data=f'take2:qty:{encoded}:1'),
                InlineKeyboardButton('Взять 5', callback_data=f'take2:qty:{encoded}:5'),
            ],
            [InlineKeyboardButton('Указать количество', callback_data=f'take2:custom:{encoded}')],
        ]
    )


def _take_confirm_keyboard(item_name: str, qty: int, request_id: str) -> InlineKeyboardMarkup:
    encoded = _encode_item(item_name)
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton('✅ Подтвердить', callback_data=f'take2:confirm:{encoded}:{qty}:{request_id}')],
            [InlineKeyboardButton('❌ Отмена', callback_data=f'take2:cancel:{request_id}')],
        ]
    )


async def _edit_callback_message(query, text: str) -> None:
    try:
        await query.edit_message_caption(caption=text, reply_markup=None)
        return
    except Exception:
        pass
    await query.edit_message_text(text=text, reply_markup=None)


async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик inline запросов для выбора товаров.
    
    Логика:
    1. При пустом поиске (@bot) - показывает весь список товаров
    2. При вводе текста - ищет товары по названию с нечётким совпадением
    3. Сортировка: точные совпадения -> начинается с -> содержит -> fuzzy match
    4. Форматирование: одна строка = фото + название + количество
    """
    query = update.inline_query
    if query is None or update.effective_user is None:
        return

    user_id = update.effective_user.id
    search_text = (query.query or '').strip().lower()
    
    # Убираем префикс "take" если есть
    if search_text.startswith('take'):
        search_text = search_text.removeprefix('take').strip()

    logger.info(
        json.dumps({
            'event': 'inline_query_received',
            'user_id': user_id,
            'query': search_text
        })
    )

    inventory = context.application.bot_data['inventory_service']
    try:
        all_items = inventory.storage.list_stock()
    except Exception as exc:
        logger.exception(
            json.dumps({
                'event': 'inline_query_error',
                'user_id': user_id,
                'error': str(exc)
            })
        )
        await query.answer(results=[], cache_time=1, is_personal=True)
        return

    # Фильтруем и категоризуем товары
    exact_matches = []       # Название совпадает полностью
    starts_with_matches = [] # Название начинается с поиска
    contains_matches = []    # Поиск содержится в названии
    fuzzy_matches = []       # Нечёткое совпадение (difflib)

    item_names = [str(getattr(row, 'name', '')).strip() for row in all_items]

    for row in all_items:
        name = str(getattr(row, 'name', '')).strip()
        try:
            qty = int(getattr(row, 'quantity', 0))
        except Exception:
            continue

        if not name or qty <= 0:
            continue

        name_lower = name.lower()

        # Категоризируем товар в зависимости от поиска
        if not search_text:
            # Нет поиска - все товары в одну категорию
            exact_matches.append((name, qty, row))
        elif name_lower == search_text:
            exact_matches.append((name, qty, row))
        elif name_lower.startswith(search_text):
            starts_with_matches.append((name, qty, row))
        elif search_text in name_lower:
            contains_matches.append((name, qty, row))

    # Если поиск есть и не нашли по основным категориям, ищем fuzzy
    if search_text and not (exact_matches or starts_with_matches or contains_matches):
        # Используем difflib для нечёткого поиска
        close_matches = difflib.get_close_matches(search_text, item_names, n=10, cutoff=0.6)
        for close_name in close_matches:
            for row in all_items:
                if str(getattr(row, 'name', '')).strip() == close_name:
                    try:
                        qty = int(getattr(row, 'quantity', 0))
                        if qty > 0:
                            fuzzy_matches.append((close_name, qty, row))
                    except Exception:
                        pass
                    break

    # Объединяем результаты по приоритету
    sorted_items = exact_matches + starts_with_matches + contains_matches + fuzzy_matches

    # Лимит результатов (Telegram позволяет до 50, но обычно показывает ~10)
    sorted_items = sorted_items[:50]

    results = []
    for seq, (name, qty, row) in enumerate(sorted_items, start=1):
        photo = getattr(row, 'photo_file_id', None)
        
        # Форматирование: одна строка с фото, названием и количеством
        text = f'{name}\n📊 Кол-во: {qty}'
        description = f'Остаток: {qty} шт.'

        kb = _take_qty_keyboard(name)

        if photo:
            # С фото
            results.append(
                InlineQueryResultCachedPhoto(
                    id=f'item-photo-{seq}',
                    photo_file_id=photo,
                    title=name,
                    description=description,
                    caption=text,
                    reply_markup=kb,
                    parse_mode='HTML',
                )
            )
        else:
            # Без фото - текстовый результат
            results.append(
                InlineQueryResultArticle(
                    id=f'item-text-{seq}',
                    title=name,
                    description=description,
                    input_message_content=InputTextMessageContent(
                        message_text=text,
                        parse_mode='HTML',
                    ),
                    reply_markup=kb,
                    thumb_url=None,
                )
            )

    logger.info(
        json.dumps({
            'event': 'inline_results_ready',
            'user_id': user_id,
            'query': search_text,
            'total_results': len(results),
            'exact': len(exact_matches),
            'starts_with': len(starts_with_matches),
            'contains': len(contains_matches),
            'fuzzy': len(fuzzy_matches),
        })
    )

    # Не кешируем пустые запросы, чтобы список обновлялся
    cache_time = 0 if not search_text else 300
    await query.answer(results=results, cache_time=cache_time, is_personal=True)


async def chosen_inline_result_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chosen = update.chosen_inline_result
    if chosen is None:
        return
    logger.info(
        json.dumps(
            {
                'event': 'take_inline_result_selected',
                'user_id': chosen.from_user.id,
                'query': chosen.query,
                'result_id': chosen.result_id,
            }
        )
    )


async def take_inline_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    data = query.data or ''
    if not data.startswith('take2:'):
        return
    await query.answer()
    user_id = update.effective_user.id
    inventory = context.application.bot_data['inventory_service']
    if data.startswith('take2:custom:'):
        item = _decode_item(data.removeprefix('take2:custom:'))
        context.user_data['state'] = DialogState.TAKE_INLINE_QTY.value
        context.user_data['take_inline_item'] = item
        logger.info(json.dumps({'event': 'take_custom_qty_requested', 'user_id': user_id, 'item': item}))
        if query.message is not None:
            await query.message.reply_text(f'Введите количество для «{item}»:')
        else:
            await context.bot.send_message(chat_id=user_id, text=f'Введите количество для «{item}»:')
        raise ApplicationHandlerStop

    if data.startswith('take2:cancel:'):
        request_id = data.removeprefix('take2:cancel:')
        pending = context.application.bot_data.setdefault('take_pending_confirms', {})
        payload = pending.pop(request_id, None)
        if payload:
            item = payload['item']
            qty = payload['qty']
        else:
            item = 'Товар'
            qty = 0
        logger.info(json.dumps({'event': 'take_confirm_cancelled', 'user_id': user_id, 'item': item, 'qty': qty}))
        await _edit_callback_message(query, f'❌ Отменено\n{item} — {qty} шт.')
        raise ApplicationHandlerStop

    if data.startswith('take2:confirm:'):
        payload = data.removeprefix('take2:confirm:')
        encoded_item, qty_raw, request_id = payload.rsplit(':', 2)
        item = _decode_item(encoded_item)
        qty = int(qty_raw)
        processed = context.application.bot_data.setdefault('take_processed_confirms', set())
        confirm_key = f'{user_id}:{item}:{qty}:{request_id}'
        if confirm_key in processed:
            logger.info(json.dumps({'event': 'take_commit_duplicate_blocked', 'user_id': user_id, 'item': item, 'qty': qty}))
            raise ApplicationHandlerStop
        logger.info(json.dumps({'event': 'take_confirm_accepted', 'user_id': user_id, 'item': item, 'qty': qty}))
        logger.info(json.dumps({'event': 'take_commit_started', 'user_id': user_id, 'item': item, 'qty': qty}))
        try:
            rbac = context.application.bot_data['rbac_service']
            rbac.require_permission(user_id, 'inventory.outbound')
            op_id = f'inline-take:{user_id}:{item}:{qty}'
            result = inventory.outbound(MovementRequest(item=item, quantity=qty, user_id=user_id, op_id=op_id))
            processed.add(confirm_key)
            pending = context.application.bot_data.setdefault('take_pending_confirms', {})
            pending.pop(request_id, None)
        except Exception as exc:
            logger.exception(json.dumps({'event': 'take_commit_failed', 'user_id': user_id, 'item': item, 'qty': qty, 'error': str(exc)}))
            if query.message is not None:
                await query.message.reply_text(f'Не удалось списать «{item}»: {exc}')
            else:
                await context.bot.send_message(chat_id=user_id, text=f'Не удалось списать «{item}»: {exc}')
            raise ApplicationHandlerStop
        caption = f'✅ Выдано\n{item} — {qty} шт.\nОстаток: {result.balance}'
        logger.info(json.dumps({'event': 'take_commit_completed', 'user_id': user_id, 'item': item, 'qty': qty, 'balance': result.balance}))
        await _edit_callback_message(query, caption)
        raise ApplicationHandlerStop

    if data.startswith('take2:qty:'):
        payload = data.removeprefix('take2:qty:')
        encoded_item, qty_raw = payload.rsplit(':', 1)
        item = _decode_item(encoded_item)
        qty = int(qty_raw)
        request_id = str(getattr(query, 'id', update.update_id))
        pending = context.application.bot_data.setdefault('take_pending_confirms', {})
        pending[request_id] = {'item': item, 'qty': qty}
        logger.info(json.dumps({'event': 'take_confirm_requested', 'user_id': user_id, 'item': item, 'qty': qty}))
        text = f'Подтвердить выдачу?\n{item} — {qty} шт.'
        await _edit_callback_message(query, text)
        try:
            await query.edit_message_reply_markup(reply_markup=_take_confirm_keyboard(item, qty, request_id))
        except Exception:
            await query.edit_message_text(text=text, reply_markup=_take_confirm_keyboard(item, qty, request_id))
        raise ApplicationHandlerStop
