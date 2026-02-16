from __future__ import annotations

from app.models.domain import Item, Role, StockEntry
from app.storage.interface import StoragePort


class MemoryStorage(StoragePort):
    def __init__(self, superadmin_tg_id: int = 0) -> None:
        self._items: dict[str, Item] = {
            'Фильтр': Item(name='Фильтр'),
            'Масло': Item(name='Масло'),
        }
        self._stock: dict[str, int] = {
            'Фильтр': 20,
            'Масло': 10,
        }
        self._limits: dict[str, tuple[int | None, bool]] = {
            'фильтр': (5, True),
            'масло': (5, True),
        }
        self._roles: dict[int, Role] = {}
        self._op_results: dict[str, tuple[str, int]] = {}
        if superadmin_tg_id:
            self._roles[superadmin_tg_id] = Role.DEV

    @staticmethod
    def _norm(value: str) -> str:
        return value.strip().lower()

    def get_item(self, name: str) -> Item | None:
        for item_name, item in self._items.items():
            if self._norm(item_name) == self._norm(name):
                return item
        return None

    def list_items(self) -> list[Item]:
        return list(self._items.values())

    def _resolve_item_name(self, item: str) -> str:
        existing = self.get_item(item)
        if existing:
            return existing.name
        self._items[item] = Item(name=item)
        return item

    def add_inbound(self, item: str, quantity: int, user_id: int, op_id: str | None = None) -> int:
        if op_id and op_id in self._op_results:
            return self._op_results[op_id][1]
        item_name = self._resolve_item_name(item)
        self._stock[item_name] = self._stock.get(item_name, 0) + quantity
        if op_id:
            self._op_results[op_id] = (item_name, self._stock[item_name])
        return self._stock[item_name]

    def add_outbound(self, item: str, quantity: int, user_id: int, op_id: str | None = None) -> int:
        if op_id and op_id in self._op_results:
            return self._op_results[op_id][1]
        item_name = self._resolve_item_name(item)
        current = self._stock.get(item_name, 0)
        if current < quantity:
            raise ValueError('insufficient stock')
        self._stock[item_name] = current - quantity
        if op_id:
            self._op_results[op_id] = (item_name, self._stock[item_name])
        return self._stock[item_name]

    def get_stock(self, item: str) -> int:
        resolved = self.get_item(item)
        if not resolved:
            return 0
        return self._stock.get(resolved.name, 0)

    def get_item_limits(self, item: str) -> tuple[int | None, bool]:
        return self._limits.get(self._norm(item), (None, False))

    def list_stock(self) -> list[StockEntry]:
        return [StockEntry(name=item, quantity=qty) for item, qty in sorted(self._stock.items())]

    def get_user_role(self, user_id: int) -> Role:
        return self._roles.get(user_id, Role.NO_ACCESS)
