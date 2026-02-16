from __future__ import annotations

from telegram import Bot

from app.services.notifications import LowStockNotifier
from app.storage.interface import StoragePort


class ReorderService:
    def __init__(self, storage: StoragePort, notifier: LowStockNotifier | None = None, bot: Bot | None = None) -> None:
        self.storage = storage
        self.notifier = notifier
        self.bot = bot

    async def check_and_upsert(self, item: str) -> None:
        qty = self.storage.get_stock(item)
        norm, crit_min = self.storage.get_item_limits(item)
        if norm is None or crit_min is None:
            return
        if qty > crit_min:
            return

        self.storage.upsert_reorder_open(item, qty_now=qty, norm=norm, crit_min=crit_min)

        if self.notifier and self.bot:
            await self.notifier.maybe_notify_low_stock(
                self.bot,
                item=item,
                prev_qty=qty + 1,
                new_qty=qty,
                min_qty=crit_min,
                notify=True,
            )
