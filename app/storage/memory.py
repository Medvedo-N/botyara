from __future__ import annotations

from app.models.domain import Item, Role, StockEntry
from app.storage.interface import StoragePort


class MemoryStorage(StoragePort):
    def __init__(self, superadmin_tg_id: int = 0) -> None:
        self._items: dict[str, Item] = {
            'Фильтр': Item(name='Фильтр', qty=20, norm=50, crit_min=5, is_active=True),
            'Масло': Item(name='Масло', qty=10, norm=30, crit_min=5, is_active=True),
        }
        self._roles: dict[int, Role] = {}
        self._users: dict[int, tuple[str, Role, bool]] = {}
        self._op_results: dict[str, tuple[str, int]] = {}
        self._reorder_open: dict[str, dict] = {}
        if superadmin_tg_id:
            self._roles[superadmin_tg_id] = Role.DEV

    @staticmethod
    def _norm(value: str) -> str:
        return value.strip().lower()

    def get_item(self, name: str) -> Item | None:
        target = self._norm(name)
        for item in self._items.values():
            if self._norm(item.name) == target:
                return item
        return None

    def list_items(self, *, active_only: bool = True) -> list[Item]:
        items = list(self._items.values())
        if active_only:
            items = [x for x in items if x.is_active]
        return items

    def list_active_items(self) -> list[Item]:
        return sorted(self.list_items(active_only=True), key=lambda item: item.name.lower())

    def add_item(self, name: str, *, norm: int, crit_min: int, qty: int, is_active: bool = True) -> None:
        item = self.get_item(name)
        if item:
            self._items[item.name] = Item(name=item.name, norm=norm, crit_min=crit_min, qty=qty, is_active=is_active)
            return
        self._items[name] = Item(name=name, norm=norm, crit_min=crit_min, qty=qty, is_active=is_active)

    def deactivate_item(self, name: str) -> None:
        item = self.get_item(name)
        if not item:
            raise ValueError('item not found')
        self._items[item.name] = Item(name=item.name, qty=item.qty, norm=item.norm, crit_min=item.crit_min, is_active=False)

    def _resolve_item(self, item: str) -> Item:
        existing = self.get_item(item)
        if existing:
            return existing
        created = Item(name=item, qty=0, norm=0, crit_min=0, is_active=True)
        self._items[item] = created
        return created

    def add_inbound(self, item: str, quantity: int, user_id: int, op_id: str | None = None) -> int:
        if op_id and op_id in self._op_results:
            return self._op_results[op_id][1]
        record = self._resolve_item(item)
        new_qty = record.qty + quantity
        self._items[record.name] = Item(name=record.name, qty=new_qty, norm=record.norm, crit_min=record.crit_min, is_active=True)
        if op_id:
            self._op_results[op_id] = (record.name, new_qty)
        return new_qty

    def add_outbound(self, item: str, quantity: int, user_id: int, op_id: str | None = None) -> int:
        if op_id and op_id in self._op_results:
            return self._op_results[op_id][1]
        record = self._resolve_item(item)
        if record.qty < quantity:
            raise ValueError('insufficient stock')
        new_qty = record.qty - quantity
        self._items[record.name] = Item(name=record.name, qty=new_qty, norm=record.norm, crit_min=record.crit_min, is_active=record.is_active)
        if op_id:
            self._op_results[op_id] = (record.name, new_qty)
        return new_qty

    def get_stock(self, item: str) -> int:
        record = self.get_item(item)
        if not record or not record.is_active:
            return 0
        return record.qty

    def get_item_limits(self, item: str) -> tuple[int | None, int | None]:
        record = self.get_item(item)
        if not record or not record.is_active:
            return None, None
        return record.norm, record.crit_min

    def list_stock(self) -> list[StockEntry]:
        return [
            StockEntry(name=x.name, quantity=x.qty, norm=x.norm, crit_min=x.crit_min)
            for x in sorted(self.list_items(active_only=True), key=lambda i: i.name)
        ]

    def upsert_reorder_open(self, item: str, *, qty_now: int, norm: int, crit_min: int) -> None:
        to_order = max(norm - qty_now, 0)
        self._reorder_open[self._norm(item)] = {
            'item_name': item,
            'qty_now': qty_now,
            'norm': norm,
            'crit_min': crit_min,
            'to_order': to_order,
            'status': 'OPEN',
        }

    def get_open_reorder(self, item: str):
        return self._reorder_open.get(self._norm(item))

    def upsert_user(self, user_id: int, name: str, role: Role, active: bool = True) -> None:
        self._users[user_id] = (name, role, active)
        if active:
            self._roles[user_id] = role
        else:
            self._roles.pop(user_id, None)

    def get_user_role(self, user_id: int) -> Role:
        return self._roles.get(user_id, Role.NO_ACCESS)
