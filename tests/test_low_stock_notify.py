import asyncio
import unittest

from app.services.notifications import LowStockNotifier


class _FakeBot:
    def __init__(self):
        self.messages = []

    async def send_message(self, chat_id, text):
        self.messages.append((chat_id, text))


class LowStockNotifierTests(unittest.TestCase):
    def _run(self, coro):
        return asyncio.run(coro)

    def test_notify_on_threshold_crossing(self):
        notifier = LowStockNotifier(chat_id=-1003886113183, fallback_chat_id=None, throttle_minutes=120)
        bot = _FakeBot()

        sent = self._run(
            notifier.maybe_notify_low_stock(
                bot,
                item='Мыло',
                prev_qty=6,
                new_qty=5,
                min_qty=5,
                notify=True,
            )
        )
        self.assertTrue(sent)
        self.assertEqual(len(bot.messages), 1)

    def test_no_notify_without_crossing_prev_gt_min(self):
        notifier = LowStockNotifier(chat_id=-1003886113183, fallback_chat_id=None, throttle_minutes=120)
        bot = _FakeBot()

        sent = self._run(
            notifier.maybe_notify_low_stock(
                bot,
                item='Мыло',
                prev_qty=5,
                new_qty=4,
                min_qty=5,
                notify=True,
            )
        )
        self.assertFalse(sent)
        self.assertEqual(len(bot.messages), 0)

    def test_no_notify_when_notify_flag_false(self):
        notifier = LowStockNotifier(chat_id=-1003886113183, fallback_chat_id=None, throttle_minutes=120)
        bot = _FakeBot()

        sent = self._run(
            notifier.maybe_notify_low_stock(
                bot,
                item='Мыло',
                prev_qty=6,
                new_qty=5,
                min_qty=5,
                notify=False,
            )
        )
        self.assertFalse(sent)
        self.assertEqual(len(bot.messages), 0)

    def test_throttling_blocks_repeat_notifications(self):
        notifier = LowStockNotifier(chat_id=-1003886113183, fallback_chat_id=None, throttle_minutes=120)
        bot = _FakeBot()

        first = self._run(
            notifier.maybe_notify_low_stock(
                bot,
                item='Мыло',
                prev_qty=6,
                new_qty=5,
                min_qty=5,
                notify=True,
            )
        )
        second = self._run(
            notifier.maybe_notify_low_stock(
                bot,
                item='Мыло',
                prev_qty=8,
                new_qty=5,
                min_qty=5,
                notify=True,
            )
        )

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(len(bot.messages), 1)


if __name__ == '__main__':
    unittest.main()
