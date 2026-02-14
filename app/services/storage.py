from __future__ import annotations

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


class StorageAdapter(ABC):
    @abstractmethod
    def get_user(self, tg_id: int) -> User | None:
        raise NotImplementedError

    @abstractmethod
    def list_locations(self) -> list[Location]:
        raise NotImplementedError

    @abstractmethod
    def search_items(self, query: str, page: int, page_size: int) -> tuple[list[Item], bool]:
        raise NotImplementedError

    @abstractmethod
    def get_balance(self, location_id: str, sku: str) -> Balance:
        raise NotImplementedError

    @abstractmethod
    def apply_operation(self, op: Operation) -> Balance:
        raise NotImplementedError

    @abstractmethod
    def get_history(
        self,
        sku: str | None = None,
        location_id: str | None = None,
        user_tg_id: int | None = None,
        limit: int = 20,
    ) -> list[LedgerRow]:
        raise NotImplementedError


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
            "SKU-004": Item(sku="SKU-004", name="Прокладка", unit="шт", active=True),
        }
        self.balances: dict[tuple[str, str], Balance] = {
            ("main", "SKU-001"): Balance(location_id="main", sku="SKU-001", qty=27),
            ("main", "SKU-002"): Balance(location_id="main", sku="SKU-002", qty=12),
            ("shop", "SKU-001"): Balance(location_id="shop", sku="SKU-001", qty=8),
        }
        self.ledger: dict[str, LedgerRow] = {}

    def get_user(self, tg_id: int) -> User | None:
        return self.users.get(tg_id)

    def list_locations(self) -> list[Location]:
        return [location for location in self.locations.values() if location.active]

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
        return self.balances.get((location_id, sku), Balance(location_id=location_id, sku=sku, qty=0))

    def apply_operation(self, op: Operation) -> Balance:
        if op.op_id in self.ledger:
            row = self.ledger[op.op_id]
            location_id = row.to_location or row.from_location or ""
            return self.get_balance(location_id=location_id, sku=row.sku)

        if op.qty <= 0:
            raise ValidationError("Количество должно быть больше нуля")

        self._require_active_item(op.sku)

        if op.op_type == OperationType.IN_:
            if not op.to_location:
                raise ValidationError("Для прихода нужна to_location")
            self._require_active_location(op.to_location)
            new_qty = self.get_balance(op.to_location, op.sku).qty + op.qty
            self.balances[(op.to_location, op.sku)] = Balance(location_id=op.to_location, sku=op.sku, qty=new_qty)
            ledger_row = LedgerRow(
                ts=op.ts,
                op_id=op.op_id,
                op_type=op.op_type,
                sku=op.sku,
                qty=op.qty,
                from_location=None,
                to_location=op.to_location,
                user_tg_id=op.user_tg_id,
                comment=op.comment,
            )
            self.ledger[op.op_id] = ledger_row
            return self.balances[(op.to_location, op.sku)]

        if op.op_type in {OperationType.OUT, OperationType.WRITE_OFF}:
            if not op.from_location:
                raise ValidationError("Для списания/выдачи нужна from_location")
            self._require_active_location(op.from_location)
            current = self.get_balance(op.from_location, op.sku).qty
            if op.qty > current:
                raise ValidationError("Недостаточно остатка")
            new_qty = current - op.qty
            self.balances[(op.from_location, op.sku)] = Balance(location_id=op.from_location, sku=op.sku, qty=new_qty)
            ledger_row = LedgerRow(
                ts=op.ts,
                op_id=op.op_id,
                op_type=op.op_type,
                sku=op.sku,
                qty=op.qty,
                from_location=op.from_location,
                to_location=None,
                user_tg_id=op.user_tg_id,
                comment=op.comment,
            )
            self.ledger[op.op_id] = ledger_row
            return self.balances[(op.from_location, op.sku)]

        if op.op_type == OperationType.MOVE:
            if not op.from_location or not op.to_location:
                raise ValidationError("Для перемещения нужны from_location и to_location")
            if op.from_location == op.to_location:
                raise ValidationError("Локации перемещения должны отличаться")
            self._require_active_location(op.from_location)
            self._require_active_location(op.to_location)
            source_current = self.get_balance(op.from_location, op.sku).qty
            if op.qty > source_current:
                raise ValidationError("Недостаточно остатка")
            source_new = source_current - op.qty
            target_new = self.get_balance(op.to_location, op.sku).qty + op.qty
            self.balances[(op.from_location, op.sku)] = Balance(location_id=op.from_location, sku=op.sku, qty=source_new)
            self.balances[(op.to_location, op.sku)] = Balance(location_id=op.to_location, sku=op.sku, qty=target_new)
            ledger_row = LedgerRow(
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
            self.ledger[op.op_id] = ledger_row
            return self.balances[(op.to_location, op.sku)]

        raise ValidationError("Неподдерживаемая операция")

    def get_history(
        self,
        sku: str | None = None,
        location_id: str | None = None,
        user_tg_id: int | None = None,
        limit: int = 20,
    ) -> list[LedgerRow]:
        rows = list(self.ledger.values())
        if sku:
            rows = [row for row in rows if row.sku == sku]
        if location_id:
            rows = [row for row in rows if row.from_location == location_id or row.to_location == location_id]
        if user_tg_id is not None:
            rows = [row for row in rows if row.user_tg_id == user_tg_id]
        rows.sort(key=lambda row: row.ts, reverse=True)
        return rows[:limit]

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
        rows = self._read("users!A2:D")
        for row in rows:
            if len(row) < 4:
                continue
            if str(row[0]).strip() != str(tg_id):
                continue
            active = str(row[3]).strip().upper() == "TRUE"
            if not active:
                return None
            role = self._parse_role(str(row[2]).strip())
            return User(tg_id=tg_id, name=str(row[1]), role=role, active=active)
        return None

    def list_locations(self) -> list[Location]:
        rows = self._read("locations!A2:C")
        out: list[Location] = []
        for row in rows:
            if len(row) < 3:
                continue
            active = str(row[2]).strip().upper() == "TRUE"
            if not active:
                continue
            out.append(Location(location_id=str(row[0]), location_name=str(row[1]), active=True))
        return out

    def search_items(self, query: str, page: int, page_size: int) -> tuple[list[Item], bool]:
        rows = self._read("catalog!A2:D")
        normalized = query.strip().lower()
        filtered: list[Item] = []
        for row in rows:
            if len(row) < 4:
                continue
            active = str(row[3]).strip().upper() == "TRUE"
            if not active:
                continue
            sku = str(row[0])
            name = str(row[1])
            unit = str(row[2])
            if normalized and normalized not in sku.lower() and normalized not in name.lower():
                continue
            filtered.append(Item(sku=sku, name=name, unit=unit, active=True))

        start = max(page, 0) * page_size
        end = start + page_size
        return filtered[start:end], end < len(filtered)

    def get_balance(self, location_id: str, sku: str) -> Balance:
        self._ensure_active_location(location_id)
        self._ensure_active_item(sku)
        rows = self._read("balances!A2:C")
        for row in rows:
            if len(row) < 3:
                continue
            if str(row[0]) == location_id and str(row[1]) == sku:
                return Balance(location_id=location_id, sku=sku, qty=int(float(row[2])))
        return Balance(location_id=location_id, sku=sku, qty=0)

    def apply_operation(self, op: Operation) -> Balance:
        existing = self._find_ledger_by_op_id(op.op_id)
        if existing:
            location_id = existing.to_location or existing.from_location
            if not location_id:
                raise ValidationError("Некорректная запись ledger")
            return self.get_balance(location_id=location_id, sku=existing.sku)

        if op.qty <= 0:
            raise ValidationError("Количество должно быть больше нуля")

        self._ensure_active_item(op.sku)
        balances = self._read_balances_map()

        if op.op_type == OperationType.IN_:
            if not op.to_location:
                raise ValidationError("Для прихода нужна to_location")
            self._ensure_active_location(op.to_location)
            key = (op.to_location, op.sku)
            balances[key] = balances.get(key, 0) + op.qty
            self._append_ledger(op)
            self._write_balances_map(balances)
            return Balance(location_id=op.to_location, sku=op.sku, qty=balances[key])

        if op.op_type in {OperationType.OUT, OperationType.WRITE_OFF}:
            if not op.from_location:
                raise ValidationError("Для выдачи/списания нужна from_location")
            self._ensure_active_location(op.from_location)
            key = (op.from_location, op.sku)
            current = balances.get(key, 0)
            if op.qty > current:
                raise ValidationError("Недостаточно остатка")
            balances[key] = current - op.qty
            self._append_ledger(op)
            self._write_balances_map(balances)
            return Balance(location_id=op.from_location, sku=op.sku, qty=balances[key])

        if op.op_type == OperationType.MOVE:
            if not op.from_location or not op.to_location:
                raise ValidationError("Для перемещения нужны from_location и to_location")
            if op.from_location == op.to_location:
                raise ValidationError("Локации перемещения должны отличаться")
            self._ensure_active_location(op.from_location)
            self._ensure_active_location(op.to_location)
            source_key = (op.from_location, op.sku)
            target_key = (op.to_location, op.sku)
            current_source = balances.get(source_key, 0)
            if op.qty > current_source:
                raise ValidationError("Недостаточно остатка")
            balances[source_key] = current_source - op.qty
            balances[target_key] = balances.get(target_key, 0) + op.qty
            self._append_ledger(op)
            self._write_balances_map(balances)
            return Balance(location_id=op.to_location, sku=op.sku, qty=balances[target_key])

        raise ValidationError("Неподдерживаемая операция")

    def get_history(
        self,
        sku: str | None = None,
        location_id: str | None = None,
        user_tg_id: int | None = None,
        limit: int = 20,
    ) -> list[LedgerRow]:
        rows = self._read("ledger!A2:I")
        out: list[LedgerRow] = []
        for row in rows:
            if len(row) < 9:
                continue
            ledger_row = LedgerRow(
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
            out.append(ledger_row)

        if sku:
            out = [row for row in out if row.sku == sku]
        if location_id:
            out = [row for row in out if row.from_location == location_id or row.to_location == location_id]
        if user_tg_id is not None:
            out = [row for row in out if row.user_tg_id == user_tg_id]

        out.sort(key=lambda row: row.ts, reverse=True)
        return out[:limit]

    def _read(self, a1_range: str) -> list[list[Any]]:
        resp = (
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=self.spreadsheet_id, range=a1_range)
            .execute()
        )
        return resp.get("values", [])

    def _append(self, a1_range: str, values: list[list[Any]]) -> None:
        (
            self.service.spreadsheets()
            .values()
            .append(
                spreadsheetId=self.spreadsheet_id,
                range=a1_range,
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": values},
            )
            .execute()
        )

    def _update(self, a1_range: str, values: list[list[Any]]) -> None:
        (
            self.service.spreadsheets()
            .values()
            .update(
                spreadsheetId=self.spreadsheet_id,
                range=a1_range,
                valueInputOption="USER_ENTERED",
                body={"values": values},
            )
            .execute()
        )

    def _parse_role(self, raw: str) -> Role:
        normalized = raw.strip().lower()
        if normalized == Role.SUPERADMIN.value:
            return Role.SUPERADMIN
        if normalized == Role.ADMIN.value:
            return Role.ADMIN
        if normalized == Role.TECH.value:
            return Role.TECH
        return Role.NO_ACCESS

    def _ensure_active_location(self, location_id: str) -> None:
        locations = self.list_locations()
        if location_id not in {location.location_id for location in locations}:
            raise NotFoundError("Локация не найдена или неактивна")

    def _ensure_active_item(self, sku: str) -> None:
        items, _ = self.search_items(query=sku, page=0, page_size=200)
        if sku not in {item.sku for item in items}:
            raise NotFoundError("Товар не найден или неактивен")

    def _read_balances_map(self) -> dict[tuple[str, str], int]:
        rows = self._read("balances!A2:C")
        out: dict[tuple[str, str], int] = {}
        for row in rows:
            if len(row) < 3:
                continue
            out[(str(row[0]), str(row[1]))] = int(float(row[2]))
        return out

    def _write_balances_map(self, balances: dict[tuple[str, str], int]) -> None:
        rows = [[location_id, sku, qty] for (location_id, sku), qty in balances.items()]
        rows.sort(key=lambda row: (row[0], row[1]))
        self._update("balances!A2:C", rows)

    def _find_ledger_by_op_id(self, op_id: str) -> LedgerRow | None:
        rows = self._read("ledger!A2:I")
        for row in rows:
            if len(row) < 9:
                continue
            if str(row[1]) != op_id:
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

    def _append_ledger(self, op: Operation) -> None:
        ts = op.ts or datetime.now(timezone.utc).isoformat()
        self._append(
            "ledger!A:I",
            [
                [
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
            ],
        )


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
