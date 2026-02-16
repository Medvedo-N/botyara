import asyncio
import unittest

from telegram.ext import ApplicationHandlerStop

from app.bot.fsm.states import DialogState
from app.bot.handlers_commands import cancel_handler
from app.bot.handlers_text import fsm_text_handler


class _FakeMessage:
    def __init__(self, text: str):
        self.text = text
        self.sent = []

    async def reply_text(self, text, reply_markup=None):
        self.sent.append(text)


class _FakeUser:
    def __init__(self, user_id: int):
        self.id = user_id


class _FakeRbac:
    def require_permission(self, user_id, permission):
        return None

    def has_permission(self, user_id, permission):
        return True


class _FakeInventory:
    def get_stock(self, item: str):
        return 20


class _FakeApp:
    def __init__(self):
        self.bot_data = {
            'inventory_service': _FakeInventory(),
            'rbac_service': _FakeRbac(),
        }


class _FakeContext:
    def __init__(self, state: DialogState):
        self.user_data = {'state': state.value}
        self.application = _FakeApp()


class _FakeUpdate:
    def __init__(self, text: str):
        self.message = _FakeMessage(text)
        self.effective_user = _FakeUser(123)


class FsmFlowTests(unittest.TestCase):
    def _run(self, coro):
        return asyncio.run(coro)

    def test_wait_stock_plain_item_returns_stock_and_resets(self):
        update = _FakeUpdate('мыло')
        context = _FakeContext(DialogState.WAITING_STOCK)
        with self.assertRaises(ApplicationHandlerStop):
            self._run(fsm_text_handler(update, context))
        self.assertIn('мыло — 20', update.message.sent[0])
        self.assertEqual(context.user_data['state'], DialogState.IDLE.value)

    def test_after_success_no_fallback_message(self):
        update = _FakeUpdate('мыло')
        context = _FakeContext(DialogState.WAITING_STOCK)
        with self.assertRaises(ApplicationHandlerStop):
            self._run(fsm_text_handler(update, context))
        self.assertEqual(len(update.message.sent), 1)
        self.assertNotIn('Не понял запрос', update.message.sent[0])

    def test_wait_stock_accepts_with_comma_or_colon_number(self):
        update1 = _FakeUpdate('мыло, 1')
        context1 = _FakeContext(DialogState.WAITING_STOCK)
        with self.assertRaises(ApplicationHandlerStop):
            self._run(fsm_text_handler(update1, context1))
        self.assertIn('мыло — 20', update1.message.sent[0])

        update2 = _FakeUpdate('мыло:1')
        context2 = _FakeContext(DialogState.WAITING_STOCK)
        with self.assertRaises(ApplicationHandlerStop):
            self._run(fsm_text_handler(update2, context2))
        self.assertIn('мыло — 20', update2.message.sent[0])

    def test_cancel_resets_state(self):
        update = _FakeUpdate('/cancel')
        context = _FakeContext(DialogState.WAITING_STOCK)
        self._run(cancel_handler(update, context))
        self.assertEqual(context.user_data['state'], DialogState.IDLE.value)

    def test_menu_action_interrupts_wait_stock_and_starts_inbound(self):
        update = _FakeUpdate('Приход')
        context = _FakeContext(DialogState.WAITING_STOCK)
        with self.assertRaises(ApplicationHandlerStop):
            self._run(fsm_text_handler(update, context))
        self.assertEqual(context.user_data['state'], DialogState.WAITING_INBOUND.value)
        self.assertIn('Введите приход', update.message.sent[0])
        self.assertNotIn('Не понял запрос', update.message.sent[0])


if __name__ == '__main__':
    unittest.main()
