from __future__ import annotations

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

    def get_item(self, name: str) -> Item | None:
        for row in self._read('items!A:B'):
            if len(row) >= 1 and row[0].strip().lower() == name.strip().lower():
                return Item(name=row[0])
        return None

    def list_items(self) -> list[Item]:
        return [Item(name=row[0]) for row in self._read('items!A:A') if row]

    def add_inbound(self, item: str, quantity: int, to_location: str, user_id: int, op_id: str | None = None) -> int:
        new_balance = self.get_stock(item, to_location) + quantity
        self._append('ledger!A:F', ['IN', item, quantity, '', to_location, user_id])
        self._upsert_balance(item, to_location, new_balance)
        return new_balance

    def add_outbound(self, item: str, quantity: int, from_location: str, user_id: int, op_id: str | None = None) -> int:
        current = self.get_stock(item, from_location)
        if current < quantity:
            raise ValueError('insufficient stock')
        new_balance = current - quantity
        self._append('ledger!A:F', ['OUT', item, quantity, from_location, '', user_id])
        self._upsert_balance(item, from_location, new_balance)
        return new_balance

    def add_move(
        self,
        item: str,
        quantity: int,
        from_location: str,
        to_location: str,
        user_id: int,
        op_id: str | None = None,
    ) -> int:
        self.add_outbound(item, quantity, from_location, user_id, op_id)
        return self.add_inbound(item, quantity, to_location, user_id, op_id)

    def add_write_off(self, item: str, quantity: int, from_location: str, user_id: int, op_id: str | None = None) -> int:
        current = self.get_stock(item, from_location)
        if current < quantity:
            raise ValueError('insufficient stock')
        new_balance = current - quantity
        self._append('ledger!A:F', ['WRITE_OFF', item, quantity, from_location, '', user_id])
        self._upsert_balance(item, from_location, new_balance)
        return new_balance

    def get_stock(self, item: str, location: str) -> int:
        rows = self._read('balances!A:C')
        for row in rows:
            if len(row) >= 3 and row[0] == item and row[1] == location:
                try:
                    return int(row[2])
                except ValueError:
                    return 0
        return 0

    def _upsert_balance(self, item: str, location: str, quantity: int) -> None:
        self._append('balances!A:C', [item, location, quantity])

    def list_stock(self) -> list[StockEntry]:
        result: list[StockEntry] = []
        for row in self._read('balances!A:C'):
            if len(row) < 3:
                continue
            try:
                qty = int(row[2])
            except ValueError:
                qty = 0
            result.append(StockEntry(name=row[0], location=row[1], quantity=qty))
        return result

    def get_user_role(self, user_id: int) -> Role:
        for row in self._read('users!A:B'):
            if len(row) >= 2 and row[0].isdigit() and int(row[0]) == user_id:
                value = row[1].strip().lower()
                if value in {r.value for r in Role}:
                    return Role(value)
        return Role.NO_ACCESS
