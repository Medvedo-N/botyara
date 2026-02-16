from __future__ import annotations

from datetime import datetime, timedelta, timezone

from telegram import Bot


class LowStockNotifier:
    def __init__(self, *, chat_id: int | None, fallback_chat_id: int | None, throttle_minutes: int = 120) -> None:
        self.chat_id = chat_id
        self.fallback_chat_id = fallback_chat_id
        self.throttle_minutes = throttle_minutes
        self._last_notified_at: dict[tuple[str, str], datetime] = {}

    def _target_chat_id(self) -> int | None:
        return self.chat_id if self.chat_id is not None else self.fallback_chat_id

    def _is_throttled(self, item: str, location: str) -> bool:
        key = (item.strip().lower(), location.strip().lower())
        last = self._last_notified_at.get(key)
        if last is None:
            return False
        return datetime.now(timezone.utc) - last < timedelta(minutes=self.throttle_minutes)

    def _mark_notified(self, item: str, location: str) -> None:
        key = (item.strip().lower(), location.strip().lower())
        self._last_notified_at[key] = datetime.now(timezone.utc)

    async def maybe_notify_low_stock(
        self,
        bot: Bot,
        *,
        item: str,
        location: str,
        prev_qty: int,
        new_qty: int,
        min_qty: int | None,
        notify: bool,
        actor_user_id: int,
        op_type: str,
    ) -> bool:
        target_chat_id = self._target_chat_id()
        if target_chat_id is None:
            return False
        if not notify:
            return False
        if min_qty is None:
            return False
        if not (prev_qty > min_qty and new_qty <= min_qty):
            return False
        if self._is_throttled(item, location):
            return False

        text = (
            '⚠️ Критический минимум!\n'
            f'Товар: {item}\n'
            f'Локация: {location}\n'
            f'Остаток: {new_qty}\n'
            f'Минимум: {min_qty}\n'
            f'Действие: {op_type}\n'
            f'Пользователь: {actor_user_id}'
        )
        await bot.send_message(chat_id=target_chat_id, text=text)
        self._mark_notified(item, location)
        return True
