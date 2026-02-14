import unittest

from app.bot.router import _menu_action_from_text


class RouterTextRoutingTests(unittest.TestCase):
    def test_menu_text_variants_resolved(self):
        self.assertEqual(_menu_action_from_text("Остатки"), "stock:balances")
        self.assertEqual(_menu_action_from_text("📦 Остатки"), "stock:balances")
        self.assertEqual(_menu_action_from_text("Приход"), "op:start:IN")
        self.assertEqual(_menu_action_from_text("📥 Приход"), "op:start:IN")
        self.assertEqual(_menu_action_from_text("Взять товар"), "op:start:OUT")
        self.assertEqual(_menu_action_from_text("📄 Взять товар"), "op:start:OUT")
        self.assertEqual(_menu_action_from_text("Брак"), "op:start:WRITE_OFF")
        self.assertEqual(_menu_action_from_text("⚠️ Брак"), "op:start:WRITE_OFF")

    def test_unknown_text_returns_none(self):
        self.assertIsNone(_menu_action_from_text("непонятно"))


if __name__ == "__main__":
    unittest.main()
