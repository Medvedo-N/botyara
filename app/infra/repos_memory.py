from __future__ import annotations
from typing import Dict, List, Optional
from uuid import uuid4

from app.domain.models import User, Location, Item, InventoryTxn

USERS: Dict[int, User] = {}
LOCATIONS: Dict[str, Location] = {}
ITEMS: Dict[str, Item] = {}
TXNS: Dict[str, InventoryTxn] = {}


class UserRepo:
    def get(self, tg_id: int) -> Optional[User]:
        return USERS.get(tg_id)

    def upsert(self, user: User) -> User:
        USERS[user.tg_id] = user
        return user


class LocationRepo:
    def list(self) -> List[Location]:
        return list(LOCATIONS.values())

    def create(self, name: str) -> Location:
        loc = Location(id=str(uuid4()), name=name)
        LOCATIONS[loc.id] = loc
        return loc


class ItemRepo:
    def list(self) -> List[Item]:
        return list(ITEMS.values())

    def create(self, name: str, unit: str = "шт") -> Item:
        item = Item(id=str(uuid4()), name=name, unit=unit)
        ITEMS[item.id] = item
        return item


class TxnRepo:
    def create(self, txn: InventoryTxn) -> InventoryTxn:
        TXNS[txn.id] = txn
        return txn

    def list(self) -> List[InventoryTxn]:
        return list(TXNS.values())
