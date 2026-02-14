from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Role(str, Enum):
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    TECH = "tech"
    VIEWER = "viewer"
    NO_ACCESS = "no_access"


class OperationType(str, Enum):
    IN_ = "IN"
    OUT = "OUT"
    MOVE = "MOVE"
    WRITE_OFF = "WRITE_OFF"


class User(BaseModel):
    tg_id: int
    name: str = ""
    role: Role = Role.NO_ACCESS
    active: bool = True


class Location(BaseModel):
    location_id: str
    location_name: str
    active: bool = True


class Item(BaseModel):
    sku: str
    name: str
    unit: str = "шт"
    active: bool = True


class Balance(BaseModel):
    location_id: str
    sku: str
    qty: int = Field(default=0, ge=0)


class Operation(BaseModel):
    op_id: str
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    op_type: OperationType
    sku: str
    qty: int = Field(gt=0)
    user_tg_id: int
    from_location: Optional[str] = None
    to_location: Optional[str] = None
    comment: str = ""


class LedgerRow(BaseModel):
    ts: str
    op_id: str
    op_type: OperationType
    sku: str
    qty: int
    from_location: Optional[str] = None
    to_location: Optional[str] = None
    user_tg_id: int
    comment: str = ""
