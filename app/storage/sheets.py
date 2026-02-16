from __future__ import annotations

from datetime import datetime, timezone
import time
from collections.abc import Callable
from typing import Any

import google.auth
from googleapiclient.discovery import build

import os
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
            return (
                self._service.spreadsheets()
                .values()
                .get(spreadsheetId=self.spreadsheet_id, range=range_name)
                .execute(num_retries=self.retries)
            )

        return self._retry(_do).get('values', [])

    def _append(self, range_name: str, values: list[Any]) -> None:
        def _do() -> Any:
            return (
                self._service.spreadsheets()
                .values()
                .append(
                    spreadsheetId=self.spreadsheet_id,
                    range=range_name,
                    valueInputOption='USER_ENTERED',
                    body={'values': [values]},
                )
                .execute(num_retries=self.retries)
            )

        self._retry(_do)

    @staticmethod
    def _normalize_key(value: str) -> str:
        return value.strip().lower()

    @staticmethod
    def _parse_notify(value: str | None) -> bool:
        if value is None:
            return False
        normalized = value.strip().lower()
        return normalized in {'true', '1', 'yes', 'y', 'да', 'д'}

    def _find_balance_row(self, item: str) -> int | None:
        target_item = self._normalize_key(item)
        rows = self._read('balances!A:D')
        for idx, row in enumerate(rows, start=1):
            if len(row) < 1:
                continue
            if self._normalize_key(row[0]) == target_item:
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
        for row in self._read('balances!A:A'):
            if row and self._normalize_key(row[0]) == self._normalize_key(name):
                return Item(name=row[0])
        return None

    def list_items(self) -> list[Item]:
        return [Item(name=row[0]) for row in self._read('balances!A:A') if row]

    def add_inbound(self, item: str, quantity: int, user_id: int, op_id: str | None = None) -> int:
        if op_id and self._operation_exists(op_id):
            return self.get_stock(item)
        new_balance = self.get_stock(item) + quantity
        self._upsert_balance(item, new_balance)
        if op_id:
            self._record_ledger(op_id, 'IN', item, quantity, user_id)
        return new_balance

    def add_outbound(self, item: str, quantity: int, user_id: int, op_id: str | None = None) -> int:
        if op_id and self._operation_exists(op_id):
            return self.get_stock(item)
        current = self.get_stock(item)
        if current < quantity:
            raise ValueError('insufficient stock')
        new_balance = current - quantity
        self._upsert_balance(item, new_balance)
        if op_id:
            self._record_ledger(op_id, 'OUT', item, quantity, user_id)
        return new_balance

    def get_stock(self, item: str) -> int:
        target_item = self._normalize_key(item)
        current = 0
        rows = self._read('balances!A:D')
        for row in rows:
            if len(row) >= 2 and self._normalize_key(row[0]) == target_item:
                try:
                    current = int(row[1])
                except ValueError:
                    current = 0
        return current

    def get_item_limits(self, item: str) -> tuple[int | None, bool]:
        target_item = self._normalize_key(item)
        rows = self._read('balances!A:D')
        min_qty: int | None = None
        notify = False
        for row in rows:
            if len(row) >= 1 and self._normalize_key(row[0]) == target_item:
                if len(row) >= 3:
                    try:
                        min_qty = int(row[2])
                    except (ValueError, TypeError):
                        min_qty = None
                if len(row) >= 4:
                    notify = self._parse_notify(row[3])
        return min_qty, notify

    def _upsert_balance(self, item: str, quantity: int) -> None:
        row_num = self._find_balance_row(item)
        if row_num is not None:

            def _do() -> Any:
                return (
                    self._service.spreadsheets()
                    .values()
                    .update(
                        spreadsheetId=self.spreadsheet_id,
                        range=f'balances!B{row_num}',
                        valueInputOption='USER_ENTERED',
                        body={'values': [[quantity]]},
                    )
                    .execute(num_retries=self.retries)
                )

            self._retry(_do)
            return
        self._append('balances!A:D', [item, quantity, '', 'false'])

    def list_stock(self) -> list[StockEntry]:
        result: list[StockEntry] = []
        for row in self._read('balances!A:D'):
            if len(row) < 2:
                continue
            try:
                qty = int(row[1])
            except ValueError:
                qty = 0
            result.append(StockEntry(name=row[0], quantity=qty))
        return result

    def _load_users_cache(self) -> dict[int, Role]:
        now = time.time()
        if self._users_cache is not None and (now - self._users_cache_ts) < 60:
            return self._users_cache

        data: dict[int, Role] = {}
        for row in self._read('users!A:D'):
            if len(row) < 4:
                continue
            user_id_raw, _name, role_raw, active_raw = row[:4]
            if not user_id_raw.isdigit():
                continue
            if active_raw.strip().lower() not in {'true', '1', 'yes', 'да'}:
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
