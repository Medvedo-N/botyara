from __future__ import annotations

import hashlib
import json
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from app.models import Balance, Item, LedgerRow, Location, Operation, OperationType, Role, User
from app.sheets_client import get_sheets_service


class StorageError(Exception):
    pass


class NotFoundError(StorageError):
    pass


class ValidationError(StorageError):
    pass


class ConcurrencyError(StorageError):
    pass


class StorageAdapter(ABC):
    @abstractmethod
    def get_user(self, tg_id: int) -> User | None: ...

    @abstractmethod
    def list_users(self) -> list[User]: ...

    @abstractmethod
    def add_or_update_user(self, tg_id: int, role: Role, name: str = "") -> User: ...

    @abstractmethod
    def set_user_active(self, tg_id: int, active: bool) -> None: ...

    @abstractmethod
    def list_locations(self) -> list[Location]: ...

    @abstractmethod
    def add_location(self, location_id: str, location_name: str) -> Location: ...

    @abstractmethod
    def rename_location(self, location_id: str, location_name: str) -> Location: ...

    @abstractmethod
    def archive_location(self, location_id: str) -> None: ...

    @abstractmethod
    def add_item(self, sku: str, name: str, unit: str = "шт") -> Item: ...

    @abstractmethod
    def rename_item(self, sku: str, name: str) -> Item: ...

    @abstractmethod
    def archive_item(self, sku: str) -> None: ...

    @abstractmethod
    def search_items(self, query: str, page: int, page_size: int) -> tuple[list[Item], bool]: ...

    @abstractmethod
    def get_balance(self, location_id: str, sku: str) -> Balance: ...

    @abstractmethod
    def apply_operation(self, op: Operation) -> Balance: ...

    @abstractmethod
    def get_history(
        self,
        sku: str | None = None,
        location_id: str | None = None,
        user_tg_id: int | None = None,
        limit: int = 20,
    ) -> list[LedgerRow]: ...


class MockStorageAdapter(StorageAdapter):
    def __init__(self):
        self.users: dict[int, User] = {}
        self.locations: dict[str, Location] = {
            "main": Location(location_id="main", location_name="Основной склад", active=True),
            "shop": Location(location_id="shop", location_name="Торговая точка", active=True),
        }
        self.items: dict[str, Item] = {
            "SKU-001": Item(sku="SKU-001", name="Фильтр", unit="шт", active=True),
            "SKU-002": Item(sku="SKU-002", name="Масло", unit="л", active=True),
            "SKU-003": Item(sku="SKU-003", name="Смазка", unit="уп", active=True),
        }
        self.balances: dict[tuple[str, str], int] = {
            ("main", "SKU-001"): 27,
            ("main", "SKU-002"): 12,
            ("shop", "SKU-001"): 8,
        }
        self.movements: dict[str, LedgerRow] = {}

    def get_user(self, tg_id: int) -> User | None:
        return self.users.get(tg_id)

    def list_users(self) -> list[User]:
        return sorted(self.users.values(), key=lambda u: u.tg_id)

    def add_or_update_user(self, tg_id: int, role: Role, name: str = "") -> User:
        user = User(tg_id=tg_id, name=name or f"user-{tg_id}", role=role, active=True)
        self.users[tg_id] = user
        return user

    def set_user_active(self, tg_id: int, active: bool) -> None:
        user = self.users.get(tg_id)
        if not user:
            raise NotFoundError("Пользователь не найден")
        self.users[tg_id] = user.model_copy(update={"active": active})

    def list_locations(self) -> list[Location]:
        return [location for location in self.locations.values() if location.active]

    def add_location(self, location_id: str, location_name: str) -> Location:
        if location_id in self.locations:
            raise ValidationError("Локация уже существует")
        location = Location(location_id=location_id, location_name=location_name, active=True)
        self.locations[location_id] = location
        return location

    def rename_location(self, location_id: str, location_name: str) -> Location:
        location = self.locations.get(location_id)
        if not location:
            raise NotFoundError("Локация не найдена")
        location = location.model_copy(update={"location_name": location_name})
        self.locations[location_id] = location
        return location

    def archive_location(self, location_id: str) -> None:
        location = self.locations.get(location_id)
        if not location:
            raise NotFoundError("Локация не найдена")
        self.locations[location_id] = location.model_copy(update={"active": False})

    def add_item(self, sku: str, name: str, unit: str = "шт") -> Item:
        if sku in self.items:
            raise ValidationError("Товар уже существует")
        item = Item(sku=sku, name=name, unit=unit, active=True)
        self.items[sku] = item
        return item

    def rename_item(self, sku: str, name: str) -> Item:
        item = self.items.get(sku)
        if not item:
            raise NotFoundError("Товар не найден")
        item = item.model_copy(update={"name": name})
        self.items[sku] = item
        return item

    def archive_item(self, sku: str) -> None:
        item = self.items.get(sku)
        if not item:
            raise NotFoundError("Товар не найден")
        self.items[sku] = item.model_copy(update={"active": False})

    def search_items(self, query: str, page: int, page_size: int) -> tuple[list[Item], bool]:
        normalized = query.strip().lower()
        filtered = [
            item
            for item in self.items.values()
            if item.active and (not normalized or normalized in item.sku.lower() or normalized in item.name.lower())
        ]
        start = max(page, 0) * page_size
        end = start + page_size
        return filtered[start:end], end < len(filtered)

    def get_balance(self, location_id: str, sku: str) -> Balance:
        self._require_active_location(location_id)
        self._require_active_item(sku)
        return Balance(location_id=location_id, sku=sku, qty=self.balances.get((location_id, sku), 0))

    def apply_operation(self, op: Operation) -> Balance:
        if op.op_id in self.movements:
            row = self.movements[op.op_id]
            location_id = row.to_location or row.from_location or ""
            return self.get_balance(location_id=location_id, sku=row.sku)

        if op.qty <= 0:
            raise ValidationError("Количество должно быть больше нуля")

        self._require_active_item(op.sku)

        if op.op_type == OperationType.IN_:
            if not op.to_location:
                raise ValidationError("Для прихода нужна to_location")
            self._require_active_location(op.to_location)
            key = (op.to_location, op.sku)
            self.balances[key] = self.balances.get(key, 0) + op.qty
            self._append_movement(op)
            return Balance(location_id=op.to_location, sku=op.sku, qty=self.balances[key])

        if op.op_type in {OperationType.OUT, OperationType.WRITE_OFF}:
            if not op.from_location:
                raise ValidationError("Для списания/выдачи нужна from_location")
            self._require_active_location(op.from_location)
            key = (op.from_location, op.sku)
            current = self.balances.get(key, 0)
            if op.qty > current:
                raise ValidationError("Недостаточно остатка")
            self.balances[key] = current - op.qty
            self._append_movement(op)
            return Balance(location_id=op.from_location, sku=op.sku, qty=self.balances[key])

        if op.op_type == OperationType.MOVE:
            if not op.from_location or not op.to_location:
                raise ValidationError("Для перемещения нужны from_location и to_location")
            if op.from_location == op.to_location:
                raise ValidationError("Локации перемещения должны отличаться")
            self._require_active_location(op.from_location)
            self._require_active_location(op.to_location)
            source_key = (op.from_location, op.sku)
            target_key = (op.to_location, op.sku)
            current = self.balances.get(source_key, 0)
            if op.qty > current:
                raise ValidationError("Недостаточно остатка")
            self.balances[source_key] = current - op.qty
            self.balances[target_key] = self.balances.get(target_key, 0) + op.qty
            self._append_movement(op)
            return Balance(location_id=op.to_location, sku=op.sku, qty=self.balances[target_key])

        raise ValidationError("Неподдерживаемая операция")

    def get_history(
        self,
        sku: str | None = None,
        location_id: str | None = None,
        user_tg_id: int | None = None,
        limit: int = 20,
    ) -> list[LedgerRow]:
        out = list(self.movements.values())
        if sku:
            out = [r for r in out if r.sku == sku]
        if location_id:
            out = [r for r in out if r.from_location == location_id or r.to_location == location_id]
        if user_tg_id is not None:
            out = [r for r in out if r.user_tg_id == user_tg_id]
        out.sort(key=lambda r: r.ts, reverse=True)
        return out[:limit]

    def _append_movement(self, op: Operation) -> None:
        self.movements[op.op_id] = LedgerRow(
            ts=op.ts,
            op_id=op.op_id,
            op_type=op.op_type,
            sku=op.sku,
            qty=op.qty,
            from_location=op.from_location,
            to_location=op.to_location,
            user_tg_id=op.user_tg_id,
            comment=op.comment,
        )

    def _require_active_location(self, location_id: str) -> None:
        location = self.locations.get(location_id)
        if location is None or not location.active:
            raise NotFoundError("Локация не найдена или неактивна")

    def _require_active_item(self, sku: str) -> None:
        item = self.items.get(sku)
        if item is None or not item.active:
            raise NotFoundError("Товар не найден или неактивен")


class GoogleSheetsStorageAdapter(StorageAdapter):
    def __init__(self, spreadsheet_id: str):
        if not spreadsheet_id:
            raise StorageError("GOOGLE_SHEETS_ID/SPREADSHEET_ID is required for sheets backend")
        self.spreadsheet_id = spreadsheet_id
        self.service = get_sheets_service()

    def get_user(self, tg_id: int) -> User | None:
        for row in self._read("users!A2:D"):
            if len(row) < 4 or str(row[0]).strip() != str(tg_id):
                continue
            active = str(row[3]).strip().upper() == "TRUE"
            if not active:
                return None
            return User(tg_id=tg_id, name=str(row[1]), role=self._parse_role(str(row[2])), active=True)
        return None

    def list_users(self) -> list[User]:
        out: list[User] = []
        for row in self._read("users!A2:D"):
            if len(row) < 4:
                continue
            out.append(
                User(
                    tg_id=int(row[0]),
                    name=str(row[1]),
                    role=self._parse_role(str(row[2])),
                    active=str(row[3]).strip().upper() == "TRUE",
                )
            )
        return sorted(out, key=lambda u: u.tg_id)

    def add_or_update_user(self, tg_id: int, role: Role, name: str = "") -> User:
        rows = self._read("users!A2:D")
        updated = False
        for i, row in enumerate(rows):
            if len(row) < 4:
                continue
            if str(row[0]).strip() == str(tg_id):
                rows[i] = [tg_id, name or (row[1] if len(row) > 1 else f"user-{tg_id}"), role.value, "TRUE"]
                updated = True
                break
        if not updated:
            rows.append([tg_id, name or f"user-{tg_id}", role.value, "TRUE"])
        self._update("users!A2:D", rows)
        return User(tg_id=tg_id, name=name or f"user-{tg_id}", role=role, active=True)

    def set_user_active(self, tg_id: int, active: bool) -> None:
        rows = self._read("users!A2:D")
        found = False
        for i, row in enumerate(rows):
            if len(row) < 4:
                continue
            if str(row[0]).strip() == str(tg_id):
                rows[i] = [row[0], row[1], row[2], "TRUE" if active else "FALSE"]
                found = True
                break
        if not found:
            raise NotFoundError("Пользователь не найден")
        self._update("users!A2:D", rows)

    def list_locations(self) -> list[Location]:
        out: list[Location] = []
        for row in self._read("locations!A2:C"):
            if len(row) < 3:
                continue
            if str(row[2]).strip().upper() != "TRUE":
                continue
            out.append(Location(location_id=str(row[0]), location_name=str(row[1]), active=True))
        return out

    def add_location(self, location_id: str, location_name: str) -> Location:
        rows = self._read("locations!A2:C")
        for row in rows:
            if len(row) >= 1 and str(row[0]).strip() == location_id:
                raise ValidationError("Локация уже существует")
        rows.append([location_id, location_name, "TRUE"])
        self._update("locations!A2:C", rows)
        return Location(location_id=location_id, location_name=location_name, active=True)

    def rename_location(self, location_id: str, location_name: str) -> Location:
        rows = self._read("locations!A2:C")
        for i, row in enumerate(rows):
            if len(row) >= 3 and str(row[0]).strip() == location_id:
                rows[i] = [location_id, location_name, row[2]]
                self._update("locations!A2:C", rows)
                return Location(location_id=location_id, location_name=location_name, active=str(row[2]).strip().upper() == "TRUE")
        raise NotFoundError("Локация не найдена")

    def archive_location(self, location_id: str) -> None:
        rows = self._read("locations!A2:C")
        for i, row in enumerate(rows):
            if len(row) >= 3 and str(row[0]).strip() == location_id:
                rows[i] = [row[0], row[1], "FALSE"]
                self._update("locations!A2:C", rows)
                return
        raise NotFoundError("Локация не найдена")

    def add_item(self, sku: str, name: str, unit: str = "шт") -> Item:
        rows = self._read("catalog!A2:D")
        for row in rows:
            if len(row) >= 1 and str(row[0]).strip() == sku:
                raise ValidationError("Товар уже существует")
        rows.append([sku, name, unit, "TRUE"])
        self._update("catalog!A2:D", rows)
        return Item(sku=sku, name=name, unit=unit, active=True)

    def rename_item(self, sku: str, name: str) -> Item:
        rows = self._read("catalog!A2:D")
        for i, row in enumerate(rows):
            if len(row) >= 4 and str(row[0]).strip() == sku:
                rows[i] = [sku, name, row[2], row[3]]
                self._update("catalog!A2:D", rows)
                return Item(sku=sku, name=name, unit=str(row[2]), active=str(row[3]).strip().upper() == "TRUE")
        raise NotFoundError("Товар не найден")

    def archive_item(self, sku: str) -> None:
        rows = self._read("catalog!A2:D")
        for i, row in enumerate(rows):
            if len(row) >= 4 and str(row[0]).strip() == sku:
                rows[i] = [row[0], row[1], row[2], "FALSE"]
                self._update("catalog!A2:D", rows)
                return
        raise NotFoundError("Товар не найден")

    def search_items(self, query: str, page: int, page_size: int) -> tuple[list[Item], bool]:
        normalized = query.strip().lower()
        filtered: list[Item] = []
        for row in self._read("catalog!A2:D"):
            if len(row) < 4 or str(row[3]).strip().upper() != "TRUE":
                continue
            sku, name, unit = str(row[0]), str(row[1]), str(row[2])
            if normalized and normalized not in sku.lower() and normalized not in name.lower():
                continue
            filtered.append(Item(sku=sku, name=name, unit=unit, active=True))
        start = max(page, 0) * page_size
        end = start + page_size
        return filtered[start:end], end < len(filtered)

    def get_balance(self, location_id: str, sku: str) -> Balance:
        self._ensure_active_location(location_id)
        self._ensure_active_item(sku)
        state = self._read_balances_state()
        qty, _, _ = state.get((location_id, sku), (0, 0, None))
        return Balance(location_id=location_id, sku=sku, qty=qty)

    def apply_operation(self, op: Operation) -> Balance:
        existing = self._find_movement_by_op_id(op.op_id)
        if existing:
            location_id = existing.to_location or existing.from_location or ""
            return self.get_balance(location_id, existing.sku)

        if op.qty <= 0:
            raise ValidationError("Количество должно быть больше нуля")

        for _ in range(3):
            try:
                return self._apply_operation_once(op)
            except ConcurrencyError:
                continue
        raise ConcurrencyError("Конкурентное изменение остатков, попробуйте ещё раз")

    def _apply_operation_once(self, op: Operation) -> Balance:
        self._ensure_active_item(op.sku)
        balances = self._read_balances_state()
        base_hash = self._balances_hash(balances)

        if op.op_type == OperationType.IN_:
            if not op.to_location:
                raise ValidationError("Для прихода нужна to_location")
            self._ensure_active_location(op.to_location)
            key = (op.to_location, op.sku)
            qty, ver, row = balances.get(key, (0, 0, None))
            balances[key] = (qty + op.qty, ver + 1, row)
            self._append_movement(op)
            self._write_balances_state(balances, expected_hash=base_hash)
            return Balance(location_id=op.to_location, sku=op.sku, qty=qty + op.qty)

        if op.op_type in {OperationType.OUT, OperationType.WRITE_OFF}:
            if not op.from_location:
                raise ValidationError("Для выдачи/списания нужна from_location")
            self._ensure_active_location(op.from_location)
            key = (op.from_location, op.sku)
            qty, ver, row = balances.get(key, (0, 0, None))
            if op.qty > qty:
                raise ValidationError("Недостаточно остатка")
            balances[key] = (qty - op.qty, ver + 1, row)
            self._append_movement(op)
            self._write_balances_state(balances, expected_hash=base_hash)
            return Balance(location_id=op.from_location, sku=op.sku, qty=qty - op.qty)

        if op.op_type == OperationType.MOVE:
            if not op.from_location or not op.to_location:
                raise ValidationError("Для перемещения нужны from_location и to_location")
            if op.from_location == op.to_location:
                raise ValidationError("Локации перемещения должны отличаться")
            self._ensure_active_location(op.from_location)
            self._ensure_active_location(op.to_location)
            from_key = (op.from_location, op.sku)
            to_key = (op.to_location, op.sku)
            f_qty, f_ver, f_row = balances.get(from_key, (0, 0, None))
            t_qty, t_ver, t_row = balances.get(to_key, (0, 0, None))
            if op.qty > f_qty:
                raise ValidationError("Недостаточно остатка")
            balances[from_key] = (f_qty - op.qty, f_ver + 1, f_row)
            balances[to_key] = (t_qty + op.qty, t_ver + 1, t_row)
            self._append_movement(op)
            self._write_balances_state(balances, expected_hash=base_hash)
            return Balance(location_id=op.to_location, sku=op.sku, qty=t_qty + op.qty)

        raise ValidationError("Неподдерживаемая операция")

    def get_history(
        self,
        sku: str | None = None,
        location_id: str | None = None,
        user_tg_id: int | None = None,
        limit: int = 20,
    ) -> list[LedgerRow]:
        rows = self._read("movements!A2:I") or self._read("ledger!A2:I")
        out: list[LedgerRow] = []
        for row in rows:
            if len(row) < 9:
                continue
            out.append(
                LedgerRow(
                    ts=str(row[0]),
                    op_id=str(row[1]),
                    op_type=OperationType(str(row[2])),
                    sku=str(row[3]),
                    qty=int(float(row[4])),
                    from_location=str(row[5]) if row[5] else None,
                    to_location=str(row[6]) if row[6] else None,
                    user_tg_id=int(row[7]),
                    comment=str(row[8]) if row[8] else "",
                )
            )
        if sku:
            out = [r for r in out if r.sku == sku]
        if location_id:
            out = [r for r in out if r.from_location == location_id or r.to_location == location_id]
        if user_tg_id is not None:
            out = [r for r in out if r.user_tg_id == user_tg_id]
        out.sort(key=lambda r: r.ts, reverse=True)
        return out[:limit]

    def _read(self, a1_range: str) -> list[list[Any]]:
        resp = self.service.spreadsheets().values().get(spreadsheetId=self.spreadsheet_id, range=a1_range).execute()
        return resp.get("values", [])

    def _append(self, a1_range: str, values: list[list[Any]]) -> None:
        self.service.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range=a1_range,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": values},
        ).execute()

    def _update(self, a1_range: str, values: list[list[Any]]) -> None:
        self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=a1_range,
            valueInputOption="USER_ENTERED",
            body={"values": values},
        ).execute()

    def _read_balances_state(self) -> dict[tuple[str, str], tuple[int, int, int | None]]:
        rows = self._read("balances!A2:D")
        out: dict[tuple[str, str], tuple[int, int, int | None]] = {}
        for idx, row in enumerate(rows, start=2):
            if len(row) < 3:
                continue
            qty = int(float(row[2]))
            ver = int(float(row[3])) if len(row) >= 4 and str(row[3]).strip() else 0
            out[(str(row[0]), str(row[1]))] = (qty, ver, idx)
        return out

    def _balances_hash(self, state: dict[tuple[str, str], tuple[int, int, int | None]]) -> str:
        data = sorted((loc, sku, qty, ver) for (loc, sku), (qty, ver, _) in state.items())
        return hashlib.sha256(json.dumps(data, ensure_ascii=False).encode()).hexdigest()

    def _write_balances_state(
        self,
        state: dict[tuple[str, str], tuple[int, int, int | None]],
        expected_hash: str,
    ) -> None:
        current_hash = self._balances_hash(self._read_balances_state())
        if current_hash != expected_hash:
            raise ConcurrencyError("Balances changed during operation")
        rows = [[loc, sku, qty, ver] for (loc, sku), (qty, ver, _) in state.items()]
        rows.sort(key=lambda r: (r[0], r[1]))
        self._update("balances!A2:D", rows)

    def _find_movement_by_op_id(self, op_id: str) -> LedgerRow | None:
        rows = self._read("movements!A2:I") or self._read("ledger!A2:I")
        for row in rows:
            if len(row) < 9 or str(row[1]) != op_id:
                continue
            return LedgerRow(
                ts=str(row[0]),
                op_id=str(row[1]),
                op_type=OperationType(str(row[2])),
                sku=str(row[3]),
                qty=int(float(row[4])),
                from_location=str(row[5]) if row[5] else None,
                to_location=str(row[6]) if row[6] else None,
                user_tg_id=int(row[7]),
                comment=str(row[8]) if row[8] else "",
            )
        return None

    def _append_movement(self, op: Operation) -> None:
        ts = op.ts or datetime.now(timezone.utc).isoformat()
        row = [
            ts,
            op.op_id,
            op.op_type.value,
            op.sku,
            op.qty,
            op.from_location or "",
            op.to_location or "",
            op.user_tg_id,
            op.comment,
        ]
        self._append("movements!A:I", [row])

    def _parse_role(self, raw: str) -> Role:
        normalized = raw.strip().lower()
        if normalized == Role.SUPERADMIN.value:
            return Role.SUPERADMIN
        if normalized == Role.ADMIN.value:
            return Role.ADMIN
        if normalized == Role.TECH.value:
            return Role.TECH
        if normalized == Role.VIEWER.value:
            return Role.VIEWER
        return Role.NO_ACCESS

    def _ensure_active_location(self, location_id: str) -> None:
        if location_id not in {location.location_id for location in self.list_locations()}:
            raise NotFoundError("Локация не найдена или неактивна")

    def _ensure_active_item(self, sku: str) -> None:
        items, _ = self.search_items(query=sku, page=0, page_size=300)
        if sku not in {item.sku for item in items}:
            raise NotFoundError("Товар не найден или неактивен")


_STORAGE: StorageAdapter | None = None


def get_storage() -> StorageAdapter:
    global _STORAGE
    if _STORAGE is not None:
        return _STORAGE

    backend = os.getenv("STORAGE_BACKEND", "mock").strip().lower()
    if backend == "sheets":
        _STORAGE = GoogleSheetsStorageAdapter(spreadsheet_id=os.getenv("GOOGLE_SHEETS_ID") or os.getenv("SPREADSHEET_ID", ""))
    elif backend == "appsscript":
        raise StorageError("appsscript backend is not implemented yet")
    else:
        _STORAGE = MockStorageAdapter()
    return _STORAGE
