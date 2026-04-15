from __future__ import annotations

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
    query = update.inline_query
    if query is None or update.effective_user is None:
        return
    user_id = update.effective_user.id
    q = (query.query or '').strip().lower()
    logger.info(json.dumps({'event': 'take_inline_query_received', 'user_id': user_id, 'query': q}))

    inventory = context.application.bot_data['inventory_service']
    try:
        rows = inventory.storage.list_stock()
    except Exception as exc:
        logger.exception(json.dumps({'event': 'take_inline_results_built', 'user_id': user_id, 'count': 0, 'error': str(exc)}))
        await query.answer(results=[], cache_time=1, is_personal=True)
        return
    if q.startswith('take'):
        q = q.removeprefix('take').strip()

    # Фильтруем и группируем товары по релевантности
    exact_match = []      # Название точно совпадает с запросом
    starts_with = []      # Название начинается с запроса
    contains = []         # Запрос содержится в названии

    for row in rows:
        name = str(getattr(row, 'name', '')).strip()
        try:
            qty = int(getattr(row, 'quantity', 0))
        except Exception:
            continue
        if not name or qty <= 0:
            continue

        name_lower = name.lower()

        # Пропускаем, если есть фильтр и товар не подходит
        if q:
            if name_lower == q:
                exact_match.append((name, qty, row))
            elif name_lower.startswith(q):
                starts_with.append((name, qty, row))
            elif q in name_lower:
                contains.append((name, qty, row))
            # Иначе не подходит - пропускаем
        else:
            # Нет фильтра - показываем все товары, отсортированные по названию
            contains.append((name, qty, row))

    # Объединяем результаты по приоритету: точное совпадение -> начинается с -> содержит
    sorted_items = exact_match + starts_with + contains

    results = []
    for seq, (name, qty, row) in enumerate(sorted_items, start=1):
        text = f'📦 {name}\nОстаток: {qty}'
        kb = _take_qty_keyboard(name)
        photo = getattr(row, 'photo_file_id', None)

        if photo:
            results.append(
                InlineQueryResultCachedPhoto(
                    id=f'take-photo-{seq}',
                    photo_file_id=photo,
                    title=name,
                    description=f'Остаток: {qty}',
                    caption=text,
                    reply_markup=kb,
                )
            )
        else:
            results.append(
                InlineQueryResultArticle(
                    id=f'take-article-{seq}',
                    title=name,
                    description=f'Остаток: {qty}',
                    input_message_content=InputTextMessageContent(text),
                    reply_markup=kb,
                )
            )

    logger.info(json.dumps({'event': 'take_inline_results_built', 'user_id': user_id, 'query': q, 'count': len(results), 'exact': len(exact_match), 'starts': len(starts_with), 'contains': len(contains)}))
    await query.answer(results=results, cache_time=1, is_personal=True)


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
            from app.models.domain import MovementRequest

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
