from __future__ import annotations

import asyncio

from telegram import Bot

from app.models.domain import MovementRequest, OperationResult, OperationType
from app.services.notifications import LowStockNotifier
from app.services.reorder import ReorderService
from app.storage.interface import StoragePort


class InventoryService:
    def __init__(
        self,
        storage: StoragePort,
        *,
        notifier: LowStockNotifier | None = None,
        reorder: ReorderService | None = None,
        bot: Bot | None = None,
    ) -> None:
        self.storage = storage
        self.notifier = notifier
        self.reorder = reorder
        self.bot = bot

    def inbound(self, request: MovementRequest) -> OperationResult:
        balance = self.storage.add_inbound(item=request.item, quantity=request.quantity, user_id=request.user_id, op_id=request.op_id)
        return OperationResult(operation=OperationType.INBOUND, item=request.item, quantity=request.quantity, balance=balance, op_id=request.op_id)

    def outbound(self, request: MovementRequest) -> OperationResult:
        self._ensure_stock(request.item, request.quantity)
        prev_qty = self.storage.get_stock(request.item)
        balance = self.storage.add_outbound(item=request.item, quantity=request.quantity, user_id=request.user_id, op_id=request.op_id)
        self._after_decrease(item=request.item, prev_qty=prev_qty, new_qty=balance)
        return OperationResult(operation=OperationType.OUTBOUND, item=request.item, quantity=request.quantity, balance=balance, op_id=request.op_id)

    def get_stock(self, item: str) -> int:
        return self.storage.get_stock(item=item)

    def list_stock(self) -> str:
        rows = self.storage.list_stock()
        if not rows:
            return 'Остатков нет.'

        lines: list[str] = []
        for entry in rows:
            if entry.quantity > entry.norm:
                marker = '🟢'
            elif entry.quantity > entry.crit_min:
                marker = '🟡'
            else:
                marker = '🔴'
            lines.append(f"{marker} {entry.name} — {entry.quantity} (норма {entry.norm}, крит {entry.crit_min})")
        return '\n'.join(lines)

    def _ensure_stock(self, item: str, quantity: int) -> None:
        current = self.storage.get_stock(item=item)
        if current < quantity:
            raise ValueError(f'not enough stock for {item}: have {current}, need {quantity}')

    def _after_decrease(self, *, item: str, prev_qty: int, new_qty: int) -> None:
        norm, crit_min = self.storage.get_item_limits(item=item)
        if crit_min is None or norm is None:
            return

        if self.reorder:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop:
                loop.create_task(self.reorder.check_and_upsert(item))

        if not self.notifier or not self.bot:
            return

        to_order = max(norm - new_qty, 0)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(
            self.notifier.maybe_notify_low_stock(
                self.bot,
                item=item,
                prev_qty=prev_qty,
                new_qty=new_qty,
                min_qty=crit_min,
                notify=True,
                norm=norm,
                to_order=to_order,
            )
        )
