from __future__ import annotations

from app.models.domain import Item, Role, StockEntry
from app.storage.interface import StoragePort


class MemoryStorage(StoragePort):
    def __init__(self, superadmin_tg_id: int = 0) -> None:
        self._items: dict[str, Item] = {
            'Фильтр': Item(name='Фильтр'),
            'Масло': Item(name='Масло'),
        }
        self._stock: dict[tuple[str, str], int] = {
            ('Фильтр', 'main'): 20,
            ('Масло', 'main'): 10,
        }
        self._roles: dict[int, Role] = {}
        self._op_results: dict[str, tuple[str, str, int]] = {}
        if superadmin_tg_id:
            self._roles[superadmin_tg_id] = Role.OWNER

    def get_item(self, name: str) -> Item | None:
        return self._items.get(name)

    def list_items(self) -> list[Item]:
        return list(self._items.values())

    def add_inbound(self, item: str, quantity: int, to_location: str, user_id: int, op_id: str | None = None) -> int:
        if op_id and op_id in self._op_results:
            return self._op_results[op_id][2]
        self._items.setdefault(item, Item(name=item))
        key = (item, to_location)
        self._stock[key] = self._stock.get(key, 0) + quantity
        if op_id:
            self._op_results[op_id] = (item, to_location, self._stock[key])
        return self._stock[key]

    def add_outbound(self, item: str, quantity: int, from_location: str, user_id: int, op_id: str | None = None) -> int:
        if op_id and op_id in self._op_results:
            return self._op_results[op_id][2]
        key = (item, from_location)
        current = self._stock.get(key, 0)
        if current < quantity:
            raise ValueError('insufficient stock')
        self._stock[key] = current - quantity
        if op_id:
            self._op_results[op_id] = (item, from_location, self._stock[key])
        return self._stock[key]

    def add_move(
        self,
        item: str,
        quantity: int,
        from_location: str,
        to_location: str,
        user_id: int,
        op_id: str | None = None,
    ) -> int:
        if op_id and op_id in self._op_results:
            return self._op_results[op_id][2]
        if from_location == to_location:
            raise ValueError('source and destination locations should differ')

        from_key = (item, from_location)
        to_key = (item, to_location)
        from_current = self._stock.get(from_key, 0)
        if from_current < quantity:
            raise ValueError('insufficient stock')

        self._stock[from_key] = from_current - quantity
        self._stock[to_key] = self._stock.get(to_key, 0) + quantity
        if op_id:
            self._op_results[op_id] = (item, to_location, self._stock[to_key])
        return self._stock[to_key]

    def add_write_off(self, item: str, quantity: int, from_location: str, user_id: int, op_id: str | None = None) -> int:
        return self.add_outbound(item=item, quantity=quantity, from_location=from_location, user_id=user_id, op_id=op_id)

    def get_stock(self, item: str, location: str) -> int:
        return self._stock.get((item, location), 0)

    def list_stock(self) -> list[StockEntry]:
        return [StockEntry(name=item, location=location, quantity=qty) for (item, location), qty in sorted(self._stock.items())]

    def get_user_role(self, user_id: int) -> Role:
        return self._roles.get(user_id, Role.NO_ACCESS)
