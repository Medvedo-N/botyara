from __future__ import annotations

import json
import logging
from urllib.parse import quote, unquote

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
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
    При пустом запросе показывает все товары. При вводе текста - фильтрует по названию.
    """
    query = update.inline_query
    if query is None or update.effective_user is None:
        return

    user_id = update.effective_user.id
    search_text = (query.query or '').strip().lower()

    logger.info(json.dumps({'event': 'inline_query_received', 'user_id': user_id, 'query': search_text}))

    inventory = context.application.bot_data['inventory_service']
    try:
        all_items = inventory.storage.list_stock()
    except Exception as exc:
        logger.exception(json.dumps({'event': 'inline_query_error', 'user_id': user_id, 'error': str(exc)}))
        await query.answer(results=[], cache_time=1, is_personal=True)
        return

    # Фильтруем и сортируем товары
    matched_items = []
    if not search_text:
        # Пустой запрос: показываем все товары с остатком > 0
        matched_items = [item for item in all_items if item.quantity > 0]
    else:
        # Есть запрос: фильтруем и сортируем
        starts_with = []
        contains = []
        for item in all_items:
            if item.quantity <= 0:
                continue
            name_lower = item.name.lower()
            if name_lower.startswith(search_text):
                starts_with.append(item)
            elif search_text in name_lower:
                contains.append(item)
        matched_items = starts_with + contains

    # Формируем результаты для Telegram
    results = []
    for i, item in enumerate(matched_items[:50]):  # Ограничение API Telegram
        text = f"Выбран товар: {item.name}\nОстаток: {item.quantity} шт.\n\nУкажите, сколько взять."
        description = f'Остаток: {item.quantity} шт.'
        kb = _take_qty_keyboard(item.name)

        # Для упрощения используем только текстовые результаты без фото
        results.append(
            InlineQueryResultArticle(
                id=f'item-text-{i}',
                title=item.name,
                description=description,
                input_message_content=InputTextMessageContent(message_text=text),
                reply_markup=kb,
            )
        )

    logger.info(
        json.dumps({
            'event': 'inline_results_ready',
            'user_id': user_id,
            'query': search_text,
            'results_count': len(results),
        })
    )

    # Короткое время кеширования, чтобы данные были актуальными
    cache_time = 5 if not search_text else 60
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
