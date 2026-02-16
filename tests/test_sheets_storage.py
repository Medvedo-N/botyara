import unittest

from app.storage.sheets import GoogleSheetsStorage


class _FakeExec:
    def __init__(self, callback):
        self._callback = callback

    def execute(self, num_retries=None):
        return self._callback()


class _FakeValues:
    def __init__(self, rows):
        self.rows = rows
        self.updated = []
        self.appended = []

    def get(self, spreadsheetId, range):
        return _FakeExec(lambda: {'values': self.rows if range == 'balances!A:C' else []})

    def update(self, spreadsheetId, range, valueInputOption, body):
        self.updated.append((range, body['values'][0]))
        return _FakeExec(lambda: {})

    def append(self, spreadsheetId, range, valueInputOption, body):
        self.appended.append((range, body['values'][0]))
        return _FakeExec(lambda: {})


class _FakeSheets:
    def __init__(self, rows):
        self.values_api = _FakeValues(rows)

    def values(self):
        return self.values_api


class _FakeService:
    def __init__(self, rows):
        self._sheets = _FakeSheets(rows)

    def spreadsheets(self):
        return self._sheets


class SheetsStorageUpsertTests(unittest.TestCase):
    def _storage_with_rows(self, rows):
        storage = object.__new__(GoogleSheetsStorage)
        storage.spreadsheet_id = 'test-sheet'
        storage.retries = 1
        storage.timeout_seconds = 1
        storage._service = _FakeService(rows)
        storage._retry = lambda fn: fn()
        return storage

    def test_upsert_updates_existing_balance_row(self):
        storage = self._storage_with_rows([['Фильтр', 'Main', '10']])
        storage._upsert_balance(' фильтр ', ' main ', 12)

        self.assertEqual(storage._service._sheets.values_api.updated, [('balances!A1:C1', [' фильтр ', ' main ', 12])])
        self.assertEqual(storage._service._sheets.values_api.appended, [])


if __name__ == '__main__':
    unittest.main()
