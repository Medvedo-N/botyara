import unittest

from app.bot.handlers_text import _menu_action, _normalize_text


class RouterTests(unittest.TestCase):
    def test_menu_actions(self):
        self.assertEqual(_menu_action(_normalize_text('Приход')), 'IN')
        self.assertEqual(_menu_action(_normalize_text('Взять')), 'OUT')
        self.assertEqual(_menu_action(_normalize_text('Остатки')), 'STOCK')
        self.assertEqual(_menu_action(_normalize_text('Пользователи')), 'USERS')

    def test_menu_actions_with_emoji_and_suffixes(self):
        self.assertEqual(_menu_action(_normalize_text('➕ Приход')), 'IN')
        self.assertEqual(_menu_action(_normalize_text('📦 Остатки')), 'STOCK')
        self.assertEqual(_menu_action(_normalize_text('Взять товар ✅')), 'OUT')

    def test_unknown_action(self):
        self.assertIsNone(_menu_action(_normalize_text('какой-то текст')))


if __name__ == '__main__':
    unittest.main()
