import asyncio
import unittest

from telegram.ext import ApplicationHandlerStop

from app.bot.handlers_text import build_reorder_request_text, text_router_handler
from app.models.domain import StockEntry


class _FakeMessage:
    def __init__(self, text: str = ''):
        self.text = text
        self.sent = []

    async def reply_text(self, text, reply_markup=None):
        self.sent.append((text, reply_markup))


class _FakeUser:
    def __init__(self, user_id: int):
        self.id = user_id


class _FakeStorage:
    def __init__(self, rows=None, raises: Exception | None = None):
        self._rows = rows or []
        self._raises = raises

    def list_stock(self):
        if self._raises:
            raise self._raises
        return self._rows


class _FakeInventory:
    def __init__(self, storage):
        self.storage = storage


class _FakeRbac:
    def __init__(self, can_view=True):
        self.can_view = can_view

    def has_permission(self, user_id, permission):
        if permission == 'inventory.view':
            return self.can_view
        return True

    def get_role(self, user_id):
        class _Role:
            value = 'manager'

        return _Role()


class _FakeContext:
    def __init__(self, storage, *, can_view=True):
        self.user_data = {'state': 'IDLE'}
        self.application = type(
            'App',
            (),
            {'bot_data': {'inventory_service': _FakeInventory(storage), 'rbac_service': _FakeRbac(can_view=can_view)}},
        )()


class _FakeUpdate:
    def __init__(self, text='Заявка', user_id=100):
        self.message = _FakeMessage(text)
        self.effective_user = _FakeUser(user_id)
        self.callback_query = None


class ReorderRequestButtonTests(unittest.TestCase):
    def _run(self, coro):
        return asyncio.run(coro)

    def test_reorder_includes_only_qty_below_norm_and_computes_need(self):
        rows = [
            StockEntry(name='Мыло', quantity=12, norm=30, crit_min=5),
            StockEntry(name='Перчатки', quantity=20, norm=20, crit_min=5),
            StockEntry(name='Тряпки', quantity=8, norm=10, crit_min=2),
        ]
        context = _FakeContext(_FakeStorage(rows))
        text = build_reorder_request_text(context, user_id=100)
        self.assertIn('📋 Заявка на закуп', text)
        self.assertIn('Мыло — 18', text)
        self.assertIn('Тряпки — 2', text)
        self.assertNotIn('Перчатки', text)

    def test_reorder_when_all_items_are_normal(self):
        rows = [StockEntry(name='Мыло', quantity=30, norm=30, crit_min=5)]
        context = _FakeContext(_FakeStorage(rows))
        text = build_reorder_request_text(context, user_id=100)
        self.assertEqual(text, 'Все товары в норме. Заявка не требуется.')

    def test_reorder_empty_list(self):
        context = _FakeContext(_FakeStorage([]))
        text = build_reorder_request_text(context, user_id=100)
        self.assertEqual(text, 'Список товаров пуст.')

    def test_reorder_skips_invalid_rows(self):
        rows = [
            type('Row', (), {'name': '', 'quantity': '3', 'norm': '10'})(),
            type('Row', (), {'name': 'Антисептик', 'quantity': '5', 'norm': '20'})(),
            type('Row', (), {'name': 'Битая', 'quantity': object(), 'norm': '10'})(),
        ]
        context = _FakeContext(_FakeStorage(rows))
        text = build_reorder_request_text(context, user_id=100)
        self.assertIn('Антисептик', text)
        self.assertNotIn('Битая', text)

    def test_reorder_storage_exception(self):
        context = _FakeContext(_FakeStorage(raises=RuntimeError('boom')))
        text = build_reorder_request_text(context, user_id=100)
        self.assertEqual(text, 'Не удалось сформировать заявку. Попробуйте позже.')

    def test_reorder_button_routes_without_crash(self):
        rows = [StockEntry(name='Мыло', quantity=1, norm=2, crit_min=0)]
        context = _FakeContext(_FakeStorage(rows))
        update = _FakeUpdate('Заявка')
        with self.assertRaises(ApplicationHandlerStop):
            self._run(text_router_handler(update, context))
        self.assertIn('📋 Заявка на закуп', update.message.sent[0][0])


if __name__ == '__main__':
    unittest.main()
