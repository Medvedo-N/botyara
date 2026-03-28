from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Role(str, Enum):
    DEV = 'dev'
    SENIOR_MANAGER = 'senior_manager'
    MANAGER = 'manager'
    USER = 'user'
    NO_ACCESS = 'no_access'


class OperationType(str, Enum):
    INBOUND = 'IN'
    OUTBOUND = 'OUT'


class Item(BaseModel):
    name: str
    qty: int = 0
    norm: int = 0
    crit_min: int = 0
    is_active: bool = True
    photo_file_id: str | None = None


class StockEntry(BaseModel):
    name: str
    quantity: int = 0
    norm: int = 0
    crit_min: int = 0
    photo_file_id: str | None = None


class OperationResult(BaseModel):
    operation: OperationType
    item: str
    quantity: int
    balance: int
    op_id: str | None = None


class MovementRequest(BaseModel):
    item: str
    quantity: int = Field(gt=0)
    user_id: int
    op_id: str | None = None
    comment: str | None = None
