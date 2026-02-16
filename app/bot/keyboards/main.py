from telegram import KeyboardButton, ReplyKeyboardMarkup


def main_menu(*, can_inbound: bool = True, can_users_view: bool = False) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton('Остатки'), KeyboardButton('Взять')]]
    if can_inbound:
        rows.append([KeyboardButton('Приход')])
    if can_users_view:
        rows.append([KeyboardButton('Пользователи')])
    rows.append([KeyboardButton('❌ Отмена')])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)
