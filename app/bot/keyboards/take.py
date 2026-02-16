from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.models.domain import StockEntry


def take_items_keyboard(rows: list[StockEntry]) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    current_row: list[InlineKeyboardButton] = []
    for entry in rows:
        if entry.quantity <= 0:
            continue
        current_row.append(InlineKeyboardButton(f"{entry.name} ({entry.quantity})", callback_data=f"take:item:{entry.name}"))
        if len(current_row) == 2:
            buttons.append(current_row)
            current_row = []
    if current_row:
        buttons.append(current_row)
    buttons.append([InlineKeyboardButton('❌ Отмена', callback_data='cancel')])
    return InlineKeyboardMarkup(buttons)


def take_qty_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton('➖ 1', callback_data='take:qty:1'), InlineKeyboardButton('➖ 5', callback_data='take:qty:5')],
            [InlineKeyboardButton('➖ 10', callback_data='take:qty:10'), InlineKeyboardButton('➖ 20', callback_data='take:qty:20')],
            [InlineKeyboardButton('✏️ Другое', callback_data='take:qty:custom')],
            [InlineKeyboardButton('❌ Отмена', callback_data='cancel')],
        ]
    )


def take_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton('✅ Подтвердить', callback_data='take:confirm')],
            [InlineKeyboardButton('❌ Отмена', callback_data='cancel')],
        ]
    )
