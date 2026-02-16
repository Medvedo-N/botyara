from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Role(str, Enum):
    OWNER = 'owner'
    MANAGER = 'manager'
    STOREKEEPER = 'storekeeper'
    VIEWER = 'viewer'
    NO_ACCESS = 'no_access'


class OperationType(str, Enum):
    INBOUND = 'IN'
    OUTBOUND = 'OUT'
    MOVE = 'MOVE'
    WRITE_OFF = 'WRITE_OFF'


class Item(BaseModel):
    name: str


class StockEntry(BaseModel):
    name: str
    location: str
    quantity: int = 0


class OperationResult(BaseModel):
    operation: OperationType
    item: str
    quantity: int
    from_location: str | None = None
    to_location: str | None = None
    balance: int
    op_id: str | None = None


class MovementRequest(BaseModel):
    item: str
    quantity: int = Field(gt=0)
    user_id: int
    op_id: str | None = None
    from_location: str | None = None
    to_location: str | None = None
    comment: str | None = None
