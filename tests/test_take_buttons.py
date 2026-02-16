import asyncio
import unittest

from telegram.ext import ApplicationHandlerStop

from app.bot.fsm.states import DialogState
from app.bot.handlers_callbacks import callback_handler
from app.bot.handlers_commands import start_handler
from app.bot.handlers_text import text_router_handler


class _FakeMessage:
    def __init__(self, text: str = ''):
        self.text = text
        self.sent = []

    async def reply_text(self, text, reply_markup=None):
        self.sent.append((text, reply_markup))


class _FakeUser:
    def __init__(self, user_id: int):
        self.id = user_id


class _FakeInventory:
    def __init__(self):
        self.stock = {'Мыло': 10}
        self.outbound_calls = []

    def get_stock(self, item: str):
        return self.stock.get(item, 0)

    @property
    def storage(self):
        class _S:
            def __init__(self, stock):
                self._stock = stock

            def list_stock(self):
                from app.models.domain import StockEntry
                return [StockEntry(name=k, quantity=v) for k, v in self._stock.items()]

        return _S(self.stock)

    def outbound(self, request):
        self.outbound_calls.append((request.item, request.quantity))
        self.stock[request.item] = self.stock.get(request.item, 0) - request.quantity

        class _R:
            balance = self.stock[request.item]

        return _R()


class _FakeRbac:
    def __init__(self, role='user'):
        self.role = role

    def require_permission(self, user_id, permission):
        allowed = {
            'user': {'inventory.view', 'inventory.outbound'},
            'manager': {'inventory.view', 'inventory.outbound', 'inventory.inbound'},
        }
        if permission not in allowed.get(self.role, set()):
            raise PermissionError('no access')
        return self.role

    def has_permission(self, user_id, permission):
        try:
            self.require_permission(user_id, permission)
            return True
        except PermissionError:
            return False


class _FakeContext:
    def __init__(self, role='user'):
        self.user_data = {'state': DialogState.IDLE.value}
        self.application = type('App', (), {'bot_data': {'inventory_service': _FakeInventory(), 'rbac_service': _FakeRbac(role)}})()


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
        self.update_id = 555


class TakeButtonsTests(unittest.TestCase):
    def _run(self, coro):
        return asyncio.run(coro)

    def test_happy_path_item_qty_confirm(self):
        context = _FakeContext(role='user')
        update = _FakeUpdate('Взять')
        with self.assertRaises(ApplicationHandlerStop):
            self._run(text_router_handler(update, context))
        self.assertEqual(context.user_data['state'], DialogState.TAKE_SELECT_ITEM.value)

        cb_message = _FakeMessage()
        cb_update = _FakeUpdate(user_id=100)
        cb_update.callback_query = _FakeCallbackQuery('take:item:Мыло', cb_message)
        with self.assertRaises(ApplicationHandlerStop):
            self._run(callback_handler(cb_update, context))
        self.assertEqual(context.user_data['state'], DialogState.TAKE_SELECT_QTY.value)

        cb_update.callback_query = _FakeCallbackQuery('take:qty:5', cb_message)
        with self.assertRaises(ApplicationHandlerStop):
            self._run(callback_handler(cb_update, context))
        self.assertEqual(context.user_data['state'], DialogState.TAKE_CONFIRM.value)

        cb_update.callback_query = _FakeCallbackQuery('take:confirm', cb_message)
        with self.assertRaises(ApplicationHandlerStop):
            self._run(callback_handler(cb_update, context))
        self.assertEqual(context.user_data['state'], DialogState.IDLE.value)

    def test_cancel_on_each_step(self):
        context = _FakeContext(role='user')
        for state in [DialogState.TAKE_SELECT_ITEM, DialogState.TAKE_SELECT_QTY, DialogState.TAKE_CONFIRM]:
            context.user_data['state'] = state.value
            cb_update = _FakeUpdate(user_id=100)
            cb_update.callback_query = _FakeCallbackQuery('cancel', _FakeMessage())
            with self.assertRaises(ApplicationHandlerStop):
                self._run(callback_handler(cb_update, context))
            self.assertEqual(context.user_data['state'], DialogState.IDLE.value)

    def test_take_more_than_stock(self):
        context = _FakeContext(role='user')
        context.user_data.update({'state': DialogState.TAKE_CONFIRM.value, 'take_item': 'Мыло', 'take_qty': 100})
        cb_update = _FakeUpdate(user_id=100)
        msg = _FakeMessage()
        cb_update.callback_query = _FakeCallbackQuery('take:confirm', msg)
        with self.assertRaises(ApplicationHandlerStop):
            self._run(callback_handler(cb_update, context))
        self.assertEqual(context.user_data['state'], DialogState.TAKE_SELECT_QTY.value)
        self.assertIn('Недостаточно остатка', msg.sent[0][0])

    def test_user_menu_has_take_without_inbound(self):
        context = _FakeContext(role='user')
        update = _FakeUpdate('/start')
        self._run(start_handler(update, context))
        text, markup = update.message.sent[0]
        self.assertIn('Ботяра готов', text)
        keyboard_texts = [btn.text for row in markup.keyboard for btn in row]
        self.assertIn('Взять', keyboard_texts)
        self.assertNotIn('Приход', keyboard_texts)


if __name__ == '__main__':
    unittest.main()
