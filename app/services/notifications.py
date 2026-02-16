from __future__ import annotations

from datetime import datetime, timedelta, timezone

from telegram import Bot


class LowStockNotifier:
    def __init__(self, *, chat_id: int | None, fallback_chat_id: int | None, throttle_minutes: int = 120) -> None:
        self.chat_id = chat_id
        self.fallback_chat_id = fallback_chat_id
        self.throttle_minutes = throttle_minutes
        self._last_notified_at: dict[str, datetime] = {}

    def _target_chat_id(self) -> int | None:
        return self.chat_id if self.chat_id is not None else self.fallback_chat_id

    def _is_throttled(self, item: str) -> bool:
        key = item.strip().lower()
        last = self._last_notified_at.get(key)
        if last is None:
            return False
        return datetime.now(timezone.utc) - last < timedelta(minutes=self.throttle_minutes)

    def _mark_notified(self, item: str) -> None:
        self._last_notified_at[item.strip().lower()] = datetime.now(timezone.utc)

    async def maybe_notify_low_stock(
        self,
        bot: Bot,
        *,
        item: str,
        prev_qty: int,
        new_qty: int,
        min_qty: int | None,
        notify: bool,
        norm: int | None = None,
        to_order: int | None = None,
    ) -> bool:
        target_chat_id = self._target_chat_id()
        if target_chat_id is None or not notify or min_qty is None:
            return False
        if not (prev_qty > min_qty and new_qty <= min_qty):
            return False
        if self._is_throttled(item):
            return False

        if norm is not None and to_order is not None:
            text = f'🔴 Критический минимум: {item}. Остаток: {new_qty}. Норма: {norm}. Заказать: {to_order}.'
        else:
            text = f'🔴 Критический минимум: {item}. Остаток: {new_qty}. Минимум: {min_qty}.'

        await bot.send_message(chat_id=target_chat_id, text=text)
        self._mark_notified(item)
        return True
