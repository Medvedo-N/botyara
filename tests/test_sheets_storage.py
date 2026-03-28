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
        return _FakeExec(lambda: {'values': self.rows.get(range, [])})

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
        storage._users_cache = None
        storage._users_cache_ts = 0.0
        storage._photo_cache = None
        storage._photo_cache_ts = 0.0
        return storage

    def test_upsert_updates_only_qty_column_and_keeps_limits(self):
        storage = self._storage_with_rows({'items!A:E': [['Фильтр', '10', '50', '5', 'true']]})
        storage._upsert_balance(' фильтр ', 12)

        self.assertEqual(storage._service._sheets.values_api.updated, [('items!B1', [12])])
        self.assertEqual(storage._service._sheets.values_api.appended, [])

    def test_get_item_parses_numeric_cells_with_spaces_and_decimals(self):
        storage = self._storage_with_rows({'items!A:E': [['Фильтр', ' 10 ', '50.0', '5,9', 'true']]})
        item = storage.get_item('фильтр')
        self.assertIsNotNone(item)
        self.assertEqual(item.qty, 10)
        self.assertEqual(item.norm, 50)
        self.assertEqual(item.crit_min, 5)

    def test_list_stock_skips_invalid_rows_and_tolerates_mixed_numeric_values(self):
        storage = self._storage_with_rows(
            {
                'items!A:E': [
                    ['', '10', '20', '1', 'true'],
                    ['   ', '7', '8', '1', 'true'],
                    ['Фильтр', ' 10 ', '', '5,9', 'true'],
                    ['Масло', None, '30.0', '', 'true'],
                ]
            }
        )
        rows = storage.list_stock()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].name, 'Фильтр')
        self.assertEqual(rows[0].quantity, 10)
        self.assertEqual(rows[0].norm, 0)
        self.assertEqual(rows[0].crit_min, 5)
        self.assertEqual(rows[1].name, 'Масло')
        self.assertEqual(rows[1].quantity, 0)
        self.assertEqual(rows[1].norm, 30)
        self.assertEqual(rows[1].crit_min, 0)

    def test_get_open_reorder_parses_numbers_robustly(self):
        storage = self._storage_with_rows({'reorder!A:G': [['Фильтр', ' 7 ', '20.0', '3,2', '13', 'OPEN', 'ts']]})
        reorder = storage.get_open_reorder('ФИЛЬТР')
        self.assertEqual(
            reorder,
            {
                'item_name': 'Фильтр',
                'qty_now': 7,
                'norm': 20,
                'crit_min': 3,
                'to_order': 13,
                'status': 'OPEN',
            },
        )

    def test_get_user_role_handles_user_id_with_spaces(self):
        storage = self._storage_with_rows({'users!A:D': [[' 12345 ', 'U', 'manager', 'true']]})
        self.assertEqual(storage.get_user_role(12345).value, 'manager')


if __name__ == '__main__':
    unittest.main()
