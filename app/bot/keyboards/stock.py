from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def stock_pagination_keyboard(*, page: int, total_pages: int) -> InlineKeyboardMarkup:
    nav_row: list[InlineKeyboardButton] = []
    if page > 1:
        nav_row.append(InlineKeyboardButton('⬅️ Назад', callback_data=f'stock:page:{page - 1}'))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton('➡️ Вперёд', callback_data=f'stock:page:{page + 1}'))

    rows: list[list[InlineKeyboardButton]] = []
    if nav_row:
        rows.append(nav_row)
    rows.append([InlineKeyboardButton('🔄 Обновить', callback_data=f'stock:refresh:{page}')])
    rows.append([InlineKeyboardButton('🏠 Меню', callback_data='stock:menu')])
    return InlineKeyboardMarkup(rows)
