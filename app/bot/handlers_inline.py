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
        await query.answer(results=[], cache_time=0, is_personal=True)
        return
    if q.startswith('take'):
        q = q.removeprefix('take').strip()

    results = []
    seq = 0
    for row in rows:
        name = str(getattr(row, 'name', '')).strip()
        try:
            qty = int(getattr(row, 'quantity', 0))
        except Exception:
            continue
        if not name or qty <= 0:
            continue
        if q and q not in name.lower():
            continue
        text = f'📦 {name}\nОстаток: {qty}'
        kb = _take_qty_keyboard(name)
        photo = getattr(row, 'photo_file_id', None)
        seq += 1
        if photo:
            results.append(
                InlineQueryResultCachedPhoto(
                    id=f'take-photo-{seq}',
                    photo_file_id=photo,
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
    logger.info(json.dumps({'event': 'take_inline_results_built', 'user_id': user_id, 'count': len(results)}))
    await query.answer(results=results, cache_time=0, is_personal=True)


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

    if data.startswith('take2:qty:'):
        payload = data.removeprefix('take2:qty:')
        encoded_item, qty_raw = payload.rsplit(':', 1)
        item = _decode_item(encoded_item)
        qty = int(qty_raw)
        logger.info(json.dumps({'event': 'take_commit_started', 'user_id': user_id, 'item': item, 'qty': qty}))
        try:
            from app.models.domain import MovementRequest

            rbac = context.application.bot_data['rbac_service']
            rbac.require_permission(user_id, 'inventory.outbound')
            result = inventory.outbound(MovementRequest(item=item, quantity=qty, user_id=user_id, op_id=f'inline-take:{update.update_id}'))
        except Exception as exc:
            logger.exception(json.dumps({'event': 'take_commit_failed', 'user_id': user_id, 'item': item, 'qty': qty, 'error': str(exc)}))
            if query.message is not None:
                await query.message.reply_text(f'Не удалось списать «{item}»: {exc}')
            else:
                await context.bot.send_message(chat_id=user_id, text=f'Не удалось списать «{item}»: {exc}')
            raise ApplicationHandlerStop

        storage = inventory.storage
        photo = storage.get_item_photo(item)
        actor = update.effective_user.full_name or str(user_id)
        caption = f'✅ Выдача\nТовар: {item}\nКто взял: {actor}\nКоличество: {qty}\nОстаток: {result.balance}'
        logger.info(json.dumps({'event': 'take_commit_completed', 'user_id': user_id, 'item': item, 'qty': qty, 'balance': result.balance}))
        if query.message is not None:
            if photo:
                await query.message.reply_photo(photo=photo, caption=caption)
            else:
                await query.message.reply_text(caption)
        else:
            try:
                await query.edit_message_caption(caption=caption)
            except Exception:
                await query.edit_message_text(text=caption)
        raise ApplicationHandlerStop
