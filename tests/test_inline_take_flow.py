import asyncio
import unittest

from telegram.ext import ApplicationHandlerStop

from app.bot.handlers_inline import chosen_inline_result_handler, inline_query_handler, take_inline_callback_handler
from app.bot.handlers_text import fallback_handler
from app.models.domain import StockEntry


class _FakeInlineQuery:
    def __init__(self, query: str):
        self.query = query
        self.answered = None

    async def answer(self, results, cache_time=0, is_personal=True):
        self.answered = results


class _FakeMessage:
    def __init__(self):
        self.sent = []

    async def reply_text(self, text, reply_markup=None):
        self.sent.append((text, reply_markup))

    async def reply_photo(self, photo, caption=None):
        self.sent.append((caption or '', photo))


class _FakeUser:
    def __init__(self, user_id=10):
        self.id = user_id
        self.full_name = f'user-{user_id}'


class _FakeStorage:
    def list_stock(self):
        return [
            StockEntry(name='Мыло', quantity=10, norm=20, crit_min=5, photo_file_id='p1'),
            StockEntry(name='Антисептик', quantity=5, norm=20, crit_min=5),
            StockEntry(name='Ноль', quantity=0, norm=10, crit_min=1),
        ]

    def get_item_photo(self, item: str):
        return 'p1' if item == 'Мыло' else None


class _FakeInventory:
    def __init__(self):
        self.storage = _FakeStorage()
        self.calls = []

    def outbound(self, request):
        self.calls.append((request.item, request.quantity))

        class _R:
            balance = 9

        return _R()


class _FakeRbac:
    def require_permission(self, user_id, permission):
        return True


class _FakeContext:
    def __init__(self):
        self.user_data = {}
        self.application = type('App', (), {'bot_data': {'inventory_service': _FakeInventory(), 'rbac_service': _FakeRbac()}})()
        self.bot = type('Bot', (), {'send_message': self._send_message})()
        self.sent = []

    async def _send_message(self, chat_id, text):
        self.sent.append((chat_id, text))


class _FakeCallbackQuery:
    def __init__(self, data):
        self.data = data
        self.id = 'cb-id-1'
        self.message = _FakeMessage()
        self.edited = []

    async def answer(self, text=None):
        return None

    async def edit_message_caption(self, caption, reply_markup=None):
        self.edited.append(caption)

    async def edit_message_text(self, text, reply_markup=None):
        self.edited.append(text)

    async def edit_message_reply_markup(self, reply_markup=None):
        self.edited.append('markup-cleared')


class _FakeUpdate:
    def __init__(self):
        self.inline_query = None
        self.chosen_inline_result = None
        self.callback_query = None
        self.effective_user = _FakeUser()
        self.update_id = 777
        self.message = _FakeMessage()


class InlineTakeFlowTests(unittest.TestCase):
    def _run(self, coro):
        return asyncio.run(coro)

    def test_inline_query_take_returns_all_available_items(self):
        context = _FakeContext()
        update = _FakeUpdate()
        update.inline_query = _FakeInlineQuery('take')
        self._run(inline_query_handler(update, context))
        self.assertEqual(len(update.inline_query.answered), 2)

    def test_inline_query_filter_returns_only_matching_item(self):
        context = _FakeContext()
        update = _FakeUpdate()
        update.inline_query = _FakeInlineQuery('мыло')
        self._run(inline_query_handler(update, context))
        self.assertEqual(len(update.inline_query.answered), 1)

    def test_callback_take_one_requests_confirm_first(self):
        context = _FakeContext()
        update = _FakeUpdate()
        update.callback_query = _FakeCallbackQuery('take2:qty:%D0%9C%D1%8B%D0%BB%D0%BE:1')
        with self.assertRaises(ApplicationHandlerStop):
            self._run(take_inline_callback_handler(update, context))
        self.assertEqual(context.application.bot_data['inventory_service'].calls, [])
        self.assertTrue(any('Подтвердить выдачу?' in str(x) for x in update.callback_query.edited))

    def test_callback_take_five_requests_confirm_first(self):
        context = _FakeContext()
        update = _FakeUpdate()
        update.callback_query = _FakeCallbackQuery('take2:qty:%D0%9C%D1%8B%D0%BB%D0%BE:5')
        with self.assertRaises(ApplicationHandlerStop):
            self._run(take_inline_callback_handler(update, context))
        self.assertEqual(context.application.bot_data['inventory_service'].calls, [])
        self.assertTrue(any('Подтвердить выдачу?' in str(x) for x in update.callback_query.edited))

    def test_confirm_callback_commits_once(self):
        context = _FakeContext()
        update = _FakeUpdate()
        update.callback_query = _FakeCallbackQuery('take2:confirm:%D0%9C%D1%8B%D0%BB%D0%BE:5:req-1')
        with self.assertRaises(ApplicationHandlerStop):
            self._run(take_inline_callback_handler(update, context))
        self.assertEqual(context.application.bot_data['inventory_service'].calls[-1], ('Мыло', 5))
        self.assertTrue(any('✅ Выдано' in str(x) for x in update.callback_query.edited))

    def test_confirm_duplicate_callback_is_blocked(self):
        context = _FakeContext()
        update = _FakeUpdate()
        update.callback_query = _FakeCallbackQuery('take2:confirm:%D0%9C%D1%8B%D0%BB%D0%BE:5:req-1')
        with self.assertRaises(ApplicationHandlerStop):
            self._run(take_inline_callback_handler(update, context))
        with self.assertRaises(ApplicationHandlerStop):
            self._run(take_inline_callback_handler(update, context))
        self.assertEqual(len(context.application.bot_data['inventory_service'].calls), 1)

    def test_confirm_with_new_request_id_commits_again(self):
        context = _FakeContext()
        update1 = _FakeUpdate()
        update1.callback_query = _FakeCallbackQuery('take2:confirm:%D0%9C%D1%8B%D0%BB%D0%BE:1:req-1')
        with self.assertRaises(ApplicationHandlerStop):
            self._run(take_inline_callback_handler(update1, context))

        update2 = _FakeUpdate()
        update2.callback_query = _FakeCallbackQuery('take2:confirm:%D0%9C%D1%8B%D0%BB%D0%BE:1:req-2')
        with self.assertRaises(ApplicationHandlerStop):
            self._run(take_inline_callback_handler(update2, context))
        self.assertEqual(len(context.application.bot_data['inventory_service'].calls), 2)

    def test_callback_custom_switches_to_qty_state(self):
        context = _FakeContext()
        update = _FakeUpdate()
        update.callback_query = _FakeCallbackQuery('take2:custom:%D0%9C%D1%8B%D0%BB%D0%BE')
        with self.assertRaises(ApplicationHandlerStop):
            self._run(take_inline_callback_handler(update, context))
        self.assertEqual(context.user_data.get('state'), 'TAKE_INLINE_QTY')

    def test_confirm_cancel_does_not_commit(self):
        context = _FakeContext()
        update = _FakeUpdate()
        context.application.bot_data['take_pending_confirms'] = {'req-1': {'item': 'Мыло', 'qty': 5}}
        update.callback_query = _FakeCallbackQuery('take2:cancel:req-1')
        with self.assertRaises(ApplicationHandlerStop):
            self._run(take_inline_callback_handler(update, context))
        self.assertEqual(context.application.bot_data['inventory_service'].calls, [])
        self.assertTrue(any('❌ Отменено' in str(x) for x in update.callback_query.edited))

    def test_fallback_silent_for_service_updates(self):
        context = _FakeContext()
        # callback-like update
        callback_update = _FakeUpdate()
        callback_update.message = None
        self._run(fallback_handler(callback_update, context))
        # chosen inline result update
        chosen_update = _FakeUpdate()
        chosen_update.chosen_inline_result = type('Chosen', (), {'from_user': _FakeUser(), 'query': 'take', 'result_id': '1'})()
        self._run(chosen_inline_result_handler(chosen_update, context))


if __name__ == '__main__':
    unittest.main()
