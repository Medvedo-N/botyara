from __future__ import annotations

import asyncio

from telegram import Bot

from app.models.domain import MovementRequest, OperationResult, OperationType
from app.services.notifications import LowStockNotifier
from app.storage.interface import StoragePort


class InventoryService:
    def __init__(self, storage: StoragePort, *, notifier: LowStockNotifier | None = None, bot: Bot | None = None) -> None:
        self.storage = storage
        self.notifier = notifier
        self.bot = bot

    def inbound(self, request: MovementRequest) -> OperationResult:
        to_location = request.to_location or 'main'
        prev_qty = self.storage.get_stock(request.item, to_location)
        balance = self.storage.add_inbound(
            item=request.item,
            quantity=request.quantity,
            to_location=to_location,
            user_id=request.user_id,
            op_id=request.op_id,
        )
        self._maybe_notify(
            item=request.item,
            location=to_location,
            prev_qty=prev_qty,
            new_qty=balance,
            actor_user_id=request.user_id,
            op_type=OperationType.INBOUND.value,
        )
        return OperationResult(
            operation=OperationType.INBOUND,
            item=request.item,
            quantity=request.quantity,
            to_location=to_location,
            balance=balance,
            op_id=request.op_id,
        )

    def outbound(self, request: MovementRequest) -> OperationResult:
        from_location = request.from_location or 'main'
        self._ensure_stock(request.item, request.quantity, from_location)
        prev_qty = self.storage.get_stock(request.item, from_location)
        balance = self.storage.add_outbound(
            item=request.item,
            quantity=request.quantity,
            from_location=from_location,
            user_id=request.user_id,
            op_id=request.op_id,
        )
        self._maybe_notify(
            item=request.item,
            location=from_location,
            prev_qty=prev_qty,
            new_qty=balance,
            actor_user_id=request.user_id,
            op_type=OperationType.OUTBOUND.value,
        )
        return OperationResult(
            operation=OperationType.OUTBOUND,
            item=request.item,
            quantity=request.quantity,
            from_location=from_location,
            balance=balance,
            op_id=request.op_id,
        )

    def move(self, request: MovementRequest) -> OperationResult:
        from_location = request.from_location or 'main'
        to_location = request.to_location or 'main'
        if from_location == to_location:
            raise ValueError('source and destination locations should differ')
        self._ensure_stock(request.item, request.quantity, from_location)
        prev_from_qty = self.storage.get_stock(request.item, from_location)
        balance = self.storage.add_move(
            item=request.item,
            quantity=request.quantity,
            from_location=from_location,
            to_location=to_location,
            user_id=request.user_id,
            op_id=request.op_id,
        )
        new_from_qty = self.storage.get_stock(request.item, from_location)
        self._maybe_notify(
            item=request.item,
            location=from_location,
            prev_qty=prev_from_qty,
            new_qty=new_from_qty,
            actor_user_id=request.user_id,
            op_type=OperationType.MOVE.value,
        )
        return OperationResult(
            operation=OperationType.MOVE,
            item=request.item,
            quantity=request.quantity,
            from_location=from_location,
            to_location=to_location,
            balance=balance,
            op_id=request.op_id,
        )

    def write_off(self, request: MovementRequest) -> OperationResult:
        from_location = request.from_location or 'main'
        self._ensure_stock(request.item, request.quantity, from_location)
        prev_qty = self.storage.get_stock(request.item, from_location)
        balance = self.storage.add_write_off(
            item=request.item,
            quantity=request.quantity,
            from_location=from_location,
            user_id=request.user_id,
            op_id=request.op_id,
        )
        self._maybe_notify(
            item=request.item,
            location=from_location,
            prev_qty=prev_qty,
            new_qty=balance,
            actor_user_id=request.user_id,
            op_type=OperationType.WRITE_OFF.value,
        )
        return OperationResult(
            operation=OperationType.WRITE_OFF,
            item=request.item,
            quantity=request.quantity,
            from_location=from_location,
            balance=balance,
            op_id=request.op_id,
        )

    def get_stock(self, item: str, location: str = 'main') -> int:
        return self.storage.get_stock(item=item, location=location)

    def list_stock(self) -> str:
        rows = self.storage.list_stock()
        if not rows:
            return 'Остатков нет.'
        return '\n'.join(f"{entry.name} [{entry.location}] = {entry.quantity}" for entry in rows)

    def _ensure_stock(self, item: str, quantity: int, location: str) -> None:
        current = self.storage.get_stock(item=item, location=location)
        if current < quantity:
            raise ValueError(f'not enough stock for {item} in {location}: have {current}, need {quantity}')

    def _maybe_notify(self, *, item: str, location: str, prev_qty: int, new_qty: int, actor_user_id: int, op_type: str) -> None:
        if not self.notifier or not self.bot:
            return
        min_qty, notify = self.storage.get_item_limits(item=item, location=location)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(
            self.notifier.maybe_notify_low_stock(
                self.bot,
                item=item,
                location=location,
                prev_qty=prev_qty,
                new_qty=new_qty,
                min_qty=min_qty,
                notify=notify,
                actor_user_id=actor_user_id,
                op_type=op_type,
            )
        )
