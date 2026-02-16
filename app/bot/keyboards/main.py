from telegram import KeyboardButton, ReplyKeyboardMarkup


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton('Приход'), KeyboardButton('Взять')],
            [KeyboardButton('Перемещение'), KeyboardButton('Брак')],
            [KeyboardButton('Остатки')],
        ],
        resize_keyboard=True,
    )
