import asyncio
import unittest

from telegram.ext import ApplicationHandlerStop

from app.bot.fsm.states import DialogState
from app.bot.handlers_callbacks import callback_handler
from app.bot.handlers_text import _stock_marker, text_router_handler
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
    def __init__(self):
        self._rows = [
            StockEntry(name='A', quantity=60, norm=50, crit_min=5),
            StockEntry(name='B', quantity=10, norm=50, crit_min=5),
            StockEntry(name='C', quantity=5, norm=50, crit_min=5),
        ]
        for idx in range(1, 13):
            self._rows.append(StockEntry(name=f'X{idx:02d}', quantity=1, norm=5, crit_min=1))

    def list_stock(self):
        return self._rows


class _FakeStorageEmpty:
    def list_stock(self):
        return []


class _FakeStorageBroken:
    def list_stock(self):
        raise RuntimeError('items range is invalid')


class _FakeInventory:
    def __init__(self, storage=None):
        self.storage = storage or _FakeStorage()


class _FakeRbac:
    def __init__(self, *, can_view: bool = True):
        self.can_view = can_view

    def require_permission(self, user_id, permission):
        if permission == 'inventory.view' and not self.can_view:
            raise PermissionError('no access')
        return None

    def has_permission(self, user_id, permission):
        if permission == 'inventory.view':
            return self.can_view
        return permission in {'inventory.outbound'}

    def get_role(self, user_id):
        class _Role:
            value = 'user'

        return _Role()


class _FakeRbacRoleLookupFails(_FakeRbac):
    def get_role(self, user_id):
        raise RuntimeError('rbac backend unavailable')


class _FakeRbacStockPermissionFails(_FakeRbac):
    def has_permission(self, user_id, permission):
        if permission == 'inventory.view':
            raise RuntimeError('rbac storage unavailable')
        return super().has_permission(user_id, permission)


class _FakeContext:
    def __init__(self, *, can_view: bool = True, rbac=None, storage=None):
        self.user_data = {'state': 'IDLE'}
        self.application = type(
            'App',
            (),
            {'bot_data': {'inventory_service': _FakeInventory(storage=storage), 'rbac_service': rbac or _FakeRbac(can_view=can_view)}},
        )()


class _FakeCallbackQuery:
    def __init__(self, data, message):
        self.data = data
        self.message = message
        self.edits = []

    async def answer(self, text=None):
        return None

    async def edit_message_text(self, text, reply_markup=None):
        self.edits.append((text, reply_markup))


class _FakeUpdate:
    def __init__(self, text='', user_id=100):
        self.message = _FakeMessage(text)
        self.effective_user = _FakeUser(user_id)
        self.callback_query = None


class StockListTests(unittest.TestCase):
    def _run(self, coro):
        return asyncio.run(coro)

    def test_stock_menu_shows_list_without_typing(self):
        context = _FakeContext()
        update = _FakeUpdate('Остатки')

        with self.assertRaises(ApplicationHandlerStop):
            self._run(text_router_handler(update, context))

        text, _ = update.message.sent[0]
        self.assertIn('Остатки (стр. 1/', text)
        self.assertIn('🟢 A — 60 (норма 50, крит 5)', text)
        self.assertIn('🟡 B — 10 (норма 50, крит 5)', text)
        self.assertIn('🔴 C — 5 (норма 50, крит 5)', text)

    def test_stock_pagination_next_page(self):
        context = _FakeContext()
        update = _FakeUpdate(user_id=100)
        msg = _FakeMessage()
        update.callback_query = _FakeCallbackQuery('stock:page:2', msg)

        with self.assertRaises(ApplicationHandlerStop):
            self._run(callback_handler(update, context))

        edited_text, _ = update.callback_query.edits[0]
        self.assertIn('Остатки (стр. 2/2)', edited_text)

    def test_stock_menu_no_access_returns_permission_message(self):
        context = _FakeContext(can_view=False)
        update = _FakeUpdate('Остатки')

        with self.assertRaises(ApplicationHandlerStop):
            self._run(text_router_handler(update, context))

        text, _ = update.message.sent[0]
        self.assertIn('Нет прав на просмотр остатков.', text)
        self.assertNotIn('Не понял запрос', text)

    def test_take_still_starts_when_stock_view_denied(self):
        context = _FakeContext(can_view=False)
        update = _FakeUpdate('Взять')

        with self.assertRaises(ApplicationHandlerStop):
            self._run(text_router_handler(update, context))

        text, _ = update.message.sent[0]
        self.assertIn('inline', text.lower())

    def test_stock_marker_thresholds(self):
        self.assertEqual(_stock_marker(5, 50, 5), '🔴')
        self.assertEqual(_stock_marker(20, 50, 5), '🟡')
        self.assertEqual(_stock_marker(51, 50, 5), '🟢')

    def test_router_does_not_crash_if_role_lookup_fails(self):
        context = _FakeContext(rbac=_FakeRbacRoleLookupFails())
        update = _FakeUpdate('Приход')

        with self.assertRaises(ApplicationHandlerStop):
            self._run(text_router_handler(update, context))

        text, _ = update.message.sent[0]
        self.assertIn('Введите приход', text)

    def test_take_start_does_not_crash_when_stock_is_empty(self):
        context = _FakeContext(storage=_FakeStorageEmpty())
        update = _FakeUpdate('Взять')

        with self.assertRaises(ApplicationHandlerStop):
            self._run(text_router_handler(update, context))

        text, _ = update.message.sent[0]
        self.assertIn('inline', text.lower())

    def test_take_start_does_not_crash_when_storage_is_broken(self):
        context = _FakeContext(storage=_FakeStorageBroken())
        update = _FakeUpdate('Взять')

        with self.assertRaises(ApplicationHandlerStop):
            self._run(text_router_handler(update, context))

        text, _ = update.message.sent[0]
        self.assertIn('inline', text.lower())

    def test_stock_action_does_not_crash_when_permission_check_fails(self):
        context = _FakeContext(rbac=_FakeRbacStockPermissionFails())
        update = _FakeUpdate('Остатки')

        with self.assertRaises(ApplicationHandlerStop):
            self._run(text_router_handler(update, context))

        text, _ = update.message.sent[0]
        self.assertIn('Не удалось проверить права на просмотр остатков', text)


if __name__ == '__main__':
    unittest.main()
