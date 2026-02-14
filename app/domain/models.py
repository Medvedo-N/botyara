from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from datetime import datetime


class Role(str, Enum):
    USER = "USER"
    ADMIN = "ADMIN"
    SENIOR_ADMIN = "SENIOR_ADMIN"


class TxnType(str, Enum):
    IN_ = "IN"
    OUT = "OUT"
    WRITE_OFF = "WRITE_OFF"
    DEFECT = "DEFECT"


@dataclass
class User:
    tg_id: int
    full_name: str = ""
    username: str = ""
    role: Role = Role.USER
    is_active: bool = True
    created_at: datetime = datetime.utcnow()


@dataclass
class Location:
    id: str
    name: str
    is_active: bool = True


@dataclass
class Item:
    id: str
    name: str
    unit: str = "шт"
    is_active: bool = True


@dataclass
class InventoryTxn:
    id: str
    type: TxnType
    item_id: str
    location_id: str
    qty: float
    created_by: int
    comment: str = ""
    created_at: datetime = datetime.utcnow()
