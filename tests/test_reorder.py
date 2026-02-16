import asyncio
import unittest

from app.services.notifications import LowStockNotifier
from app.services.reorder import ReorderService
from app.storage.memory import MemoryStorage


class _FakeBot:
    def __init__(self):
        self.messages = []

    async def send_message(self, chat_id, text):
        self.messages.append((chat_id, text))


class ReorderTests(unittest.TestCase):
    def _run(self, coro):
        return asyncio.run(coro)

    def test_create_or_update_open_without_duplicates(self):
        storage = MemoryStorage(superadmin_tg_id=1)
        # set critical state
        storage._items['Фильтр'] = storage._items['Фильтр'].model_copy(update={'qty': 5, 'norm': 50, 'crit_min': 5})
        notifier = LowStockNotifier(chat_id=-1003886113183, fallback_chat_id=None, throttle_minutes=120)
        bot = _FakeBot()
        service = ReorderService(storage, notifier=notifier, bot=bot)

        self._run(service.check_and_upsert('Фильтр'))
        first = storage.get_open_reorder('Фильтр')
        self.assertIsNotNone(first)
        self.assertEqual(first['to_order'], 45)

        # repeat trigger should update same record, not duplicate
        storage._items['Фильтр'] = storage._items['Фильтр'].model_copy(update={'qty': 4})
        self._run(service.check_and_upsert('Фильтр'))
        second = storage.get_open_reorder('Фильтр')
        self.assertIsNotNone(second)
        self.assertEqual(second['qty_now'], 4)
        self.assertEqual(second['to_order'], 46)

    def test_notification_called_for_critical(self):
        storage = MemoryStorage(superadmin_tg_id=1)
        storage._items['Масло'] = storage._items['Масло'].model_copy(update={'qty': 5, 'norm': 30, 'crit_min': 5})
        notifier = LowStockNotifier(chat_id=-1003886113183, fallback_chat_id=None, throttle_minutes=120)
        bot = _FakeBot()
        service = ReorderService(storage, notifier=notifier, bot=bot)

        self._run(service.check_and_upsert('Масло'))
        self.assertEqual(len(bot.messages), 1)


if __name__ == '__main__':
    unittest.main()
