import unittest

from app.models.domain import MovementRequest
from app.services.inventory import InventoryService
from app.storage.memory import MemoryStorage


class InventoryServiceTests(unittest.TestCase):
    def setUp(self):
        self.storage = MemoryStorage(superadmin_tg_id=123)
        self.service = InventoryService(self.storage)

    def test_inbound_increases_balance(self):
        result = self.service.inbound(MovementRequest(item='Фильтр', quantity=5, user_id=123))
        self.assertEqual(result.balance, 25)

    def test_outbound_fails_on_insufficient_stock(self):
        with self.assertRaises(ValueError):
            self.service.outbound(MovementRequest(item='Фильтр', quantity=999, user_id=123))

    def test_inbound_is_idempotent_by_op_id(self):
        first = self.service.inbound(MovementRequest(item='Фильтр', quantity=3, user_id=123, op_id='op-1'))
        second = self.service.inbound(MovementRequest(item='Фильтр', quantity=3, user_id=123, op_id='op-1'))
        self.assertEqual(first.balance, 23)
        self.assertEqual(second.balance, 23)
        self.assertEqual(self.storage.get_stock('Фильтр'), 23)

    def test_outbound_decreases_balance(self):
        result = self.service.outbound(MovementRequest(item='Фильтр', quantity=2, user_id=123))
        self.assertEqual(result.balance, 18)


if __name__ == '__main__':
    unittest.main()
