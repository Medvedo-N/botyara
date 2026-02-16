from __future__ import annotations

from app.models.domain import MovementRequest, OperationResult, OperationType
from app.storage.interface import StoragePort


class InventoryService:
    def __init__(self, storage: StoragePort) -> None:
        self.storage = storage

    def inbound(self, request: MovementRequest) -> OperationResult:
        to_location = request.to_location or 'main'
        balance = self.storage.add_inbound(
            item=request.item,
            quantity=request.quantity,
            to_location=to_location,
            user_id=request.user_id,
            op_id=request.op_id,
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
        balance = self.storage.add_outbound(
            item=request.item,
            quantity=request.quantity,
            from_location=from_location,
            user_id=request.user_id,
            op_id=request.op_id,
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
        balance = self.storage.add_move(
            item=request.item,
            quantity=request.quantity,
            from_location=from_location,
            to_location=to_location,
            user_id=request.user_id,
            op_id=request.op_id,
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
        balance = self.storage.add_write_off(
            item=request.item,
            quantity=request.quantity,
            from_location=from_location,
            user_id=request.user_id,
            op_id=request.op_id,
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
