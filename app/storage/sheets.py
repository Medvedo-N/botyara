from __future__ import annotations

from datetime import datetime, timezone
import os
import time
from collections.abc import Callable
from typing import Any

import google.auth
from googleapiclient.discovery import build

from app.models.domain import Item, Role, StockEntry
from app.storage.interface import StoragePort

SHEETS_SCOPE = ['https://www.googleapis.com/auth/spreadsheets']


class GoogleSheetsStorage(StoragePort):
    def __init__(self, spreadsheet_id: str, timeout_seconds: int = 10, retries: int = 3) -> None:
        if not spreadsheet_id:
            raise ValueError('SPREADSHEET_ID is required for sheets backend')
        self.spreadsheet_id = spreadsheet_id
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        credentials, _ = google.auth.default(scopes=SHEETS_SCOPE)
        self._service = build('sheets', 'v4', credentials=credentials, cache_discovery=False)
        self._users_cache: dict[int, Role] | None = None
        self._users_cache_ts: float = 0.0

    def _retry(self, action: Callable[[], Any]) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                return action()
            except Exception as exc:  # pragma: no cover
                last_error = exc
                if attempt == self.retries:
                    break
                time.sleep(min(0.5 * attempt, 2.0))
        raise RuntimeError(f'sheets operation failed: {last_error}')

    def _read(self, range_name: str) -> list[list[str]]:
        def _do() -> dict[str, Any]:
            return self._service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
            ).execute(num_retries=self.retries)

        return self._retry(_do).get('values', [])

    def _append(self, range_name: str, values: list[Any]) -> None:
        def _do() -> Any:
            return self._service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption='USER_ENTERED',
                body={'values': [values]},
            ).execute(num_retries=self.retries)

        self._retry(_do)

    @staticmethod
    def _normalize_key(value: str) -> str:
        return value.strip().lower()

    @staticmethod
    def _parse_bool(value: str | None) -> bool:
        if value is None:
            return False
        return value.strip().lower() in {'true', '1', 'yes', 'да', 'y'}

    def _items_rows(self) -> list[list[str]]:
        return self._read('items!A:E')

    def _find_item_row(self, item: str) -> int | None:
        target = self._normalize_key(item)
        for idx, row in enumerate(self._items_rows(), start=1):
            if row and self._normalize_key(row[0]) == target:
                return idx
        return None

    def _operation_exists(self, op_id: str | None) -> bool:
        if not op_id:
            return False
        target = self._normalize_key(op_id)
        for row in self._read('ledger!A:A'):
            if row and self._normalize_key(row[0]) == target:
                return True
        return False

    def _record_ledger(self, op_id: str, op_type: str, item: str, quantity: int, user_id: int) -> None:
        ts_utc = datetime.now(timezone.utc).isoformat()
        self._append('ledger!A:F', [op_id, ts_utc, op_type, item, quantity, user_id])

    def get_item(self, name: str) -> Item | None:
        target = self._normalize_key(name)
        for row in self._items_rows():
            if not row:
                continue
            if self._normalize_key(row[0]) != target:
                continue
            qty = int(row[1]) if len(row) > 1 and row[1].isdigit() else 0
            norm = int(row[2]) if len(row) > 2 and row[2].isdigit() else 0
            crit = int(row[3]) if len(row) > 3 and row[3].isdigit() else 0
            active = self._parse_bool(row[4] if len(row) > 4 else 'true')
            return Item(name=row[0], qty=qty, norm=norm, crit_min=crit, is_active=active)
        return None

    def list_items(self, *, active_only: bool = True) -> list[Item]:
        out: list[Item] = []
        for row in self._items_rows():
            if not row:
                continue
            qty = int(row[1]) if len(row) > 1 and row[1].isdigit() else 0
            norm = int(row[2]) if len(row) > 2 and row[2].isdigit() else 0
            crit = int(row[3]) if len(row) > 3 and row[3].isdigit() else 0
            active = self._parse_bool(row[4] if len(row) > 4 else 'true')
            item = Item(name=row[0], qty=qty, norm=norm, crit_min=crit, is_active=active)
            if active_only and not item.is_active:
                continue
            out.append(item)
        return out

    def list_active_items(self) -> list[Item]:
        return sorted(self.list_items(active_only=True), key=lambda item: item.name.lower())

    def add_item(self, name: str, *, norm: int, crit_min: int, qty: int, is_active: bool = True) -> None:
        row = self._find_item_row(name)
        if row is None:
            self._append('items!A:E', [name, qty, norm, crit_min, 'true' if is_active else 'false'])
            return

        def _do() -> Any:
            return self._service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f'items!A{row}:E{row}',
                valueInputOption='USER_ENTERED',
                body={'values': [[name, qty, norm, crit_min, 'true' if is_active else 'false']]},
            ).execute(num_retries=self.retries)

        self._retry(_do)

    def deactivate_item(self, name: str) -> None:
        row = self._find_item_row(name)
        if row is None:
            raise ValueError('item not found')

        def _do() -> Any:
            return self._service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f'items!E{row}',
                valueInputOption='USER_ENTERED',
                body={'values': [['false']]},
            ).execute(num_retries=self.retries)

        self._retry(_do)

    def add_inbound(self, item: str, quantity: int, user_id: int, op_id: str | None = None) -> int:
        if op_id and self._operation_exists(op_id):
            return self.get_stock(item)
        current = self.get_item(item)
        if current is None:
            self.add_item(item, norm=0, crit_min=0, qty=quantity, is_active=True)
            if op_id:
                self._record_ledger(op_id, 'IN', item, quantity, user_id)
            return quantity
        new_qty = current.qty + quantity
        self._upsert_balance(current.name, new_qty)
        if op_id:
            self._record_ledger(op_id, 'IN', current.name, quantity, user_id)
        return new_qty

    def add_outbound(self, item: str, quantity: int, user_id: int, op_id: str | None = None) -> int:
        if op_id and self._operation_exists(op_id):
            return self.get_stock(item)
        current = self.get_item(item)
        if current is None or current.qty < quantity:
            raise ValueError('insufficient stock')
        new_qty = current.qty - quantity
        self._upsert_balance(current.name, new_qty)
        if op_id:
            self._record_ledger(op_id, 'OUT', current.name, quantity, user_id)
        return new_qty


    def _upsert_balance(self, item: str, qty: int) -> None:
        row = self._find_item_row(item)
        if row is None:
            self._append('items!A:E', [item, qty, 0, 0, 'true'])
            return

        def _do() -> Any:
            return self._service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f'items!B{row}',
                valueInputOption='USER_ENTERED',
                body={'values': [[qty]]},
            ).execute(num_retries=self.retries)

        self._retry(_do)

    def get_stock(self, item: str) -> int:
        record = self.get_item(item)
        if not record or not record.is_active:
            return 0
        return record.qty

    def list_stock(self) -> list[StockEntry]:
        return [StockEntry(name=x.name, quantity=x.qty, norm=x.norm, crit_min=x.crit_min) for x in self.list_items(active_only=True)]

    def get_item_limits(self, item: str) -> tuple[int | None, int | None]:
        record = self.get_item(item)
        if not record or not record.is_active:
            return None, None
        return record.norm, record.crit_min

    def upsert_reorder_open(self, item: str, *, qty_now: int, norm: int, crit_min: int) -> None:
        rows = self._read('reorder!A:G')
        row_num = None
        for idx, row in enumerate(rows, start=1):
            if row and self._normalize_key(row[0]) == self._normalize_key(item) and len(row) >= 6 and row[5].strip().upper() == 'OPEN':
                row_num = idx
                break
        to_order = max(norm - qty_now, 0)
        payload = [item, qty_now, norm, crit_min, to_order, 'OPEN', datetime.now(timezone.utc).isoformat()]
        if row_num is None:
            self._append('reorder!A:G', payload)
            return

        def _do() -> Any:
            return self._service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f'reorder!A{row_num}:G{row_num}',
                valueInputOption='USER_ENTERED',
                body={'values': [payload]},
            ).execute(num_retries=self.retries)

        self._retry(_do)

    def get_open_reorder(self, item: str):
        for row in self._read('reorder!A:G'):
            if not row:
                continue
            if self._normalize_key(row[0]) != self._normalize_key(item):
                continue
            if len(row) < 6 or row[5].strip().upper() != 'OPEN':
                continue
            return {
                'item_name': row[0],
                'qty_now': int(row[1]) if len(row) > 1 and row[1].isdigit() else 0,
                'norm': int(row[2]) if len(row) > 2 and row[2].isdigit() else 0,
                'crit_min': int(row[3]) if len(row) > 3 and row[3].isdigit() else 0,
                'to_order': int(row[4]) if len(row) > 4 and row[4].isdigit() else 0,
                'status': 'OPEN',
            }
        return None

    def upsert_user(self, user_id: int, name: str, role: Role, active: bool = True) -> None:
        rows = self._read('users!A:D')
        row_num = None
        for idx, row in enumerate(rows, start=1):
            if row and row[0].isdigit() and int(row[0]) == user_id:
                row_num = idx
                break
        payload = [user_id, name, role.value, 'true' if active else 'false']
        if row_num is None:
            self._append('users!A:D', payload)
        else:
            def _do() -> Any:
                return self._service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=f'users!A{row_num}:D{row_num}',
                    valueInputOption='USER_ENTERED',
                    body={'values': [payload]},
                ).execute(num_retries=self.retries)
            self._retry(_do)
        self._users_cache = None

    def _load_users_cache(self) -> dict[int, Role]:
        now = time.time()
        if self._users_cache is not None and (now - self._users_cache_ts) < 60:
            return self._users_cache

        data: dict[int, Role] = {}
        for row in self._read('users!A:D'):
            if len(row) < 4:
                continue
            user_id_raw, _name, role_raw, active_raw = row[:4]
            if not user_id_raw.isdigit() or not self._parse_bool(active_raw):
                continue
            role_key = role_raw.strip().lower()
            if role_key in {r.value for r in Role}:
                data[int(user_id_raw)] = Role(role_key)

        self._users_cache = data
        self._users_cache_ts = now
        return data

    def get_user_role(self, user_id: int) -> Role:
        users = self._load_users_cache()
        if user_id in users:
            return users[user_id]
        superadmin = os.getenv('SUPERADMIN_TG_ID', '').strip()
        if superadmin.isdigit() and user_id == int(superadmin):
            return Role.DEV
        return Role.NO_ACCESS
