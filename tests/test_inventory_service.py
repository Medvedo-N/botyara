import unittest

from app.models.domain import MovementRequest
from app.services.inventory import InventoryService
from app.storage.memory import MemoryStorage


class InventoryServiceTests(unittest.TestCase):
    def setUp(self):
        self.storage = MemoryStorage(superadmin_tg_id=123)
        self.service = InventoryService(self.storage)

    def test_inbound_increases_balance(self):
        result = self.service.inbound(MovementRequest(item='Фильтр', quantity=5, user_id=123, to_location='main'))
        self.assertEqual(result.balance, 25)

    def test_outbound_fails_on_insufficient_stock(self):
        with self.assertRaises(ValueError):
            self.service.outbound(MovementRequest(item='Фильтр', quantity=999, user_id=123, from_location='main'))

    def test_move_requires_different_locations(self):
        with self.assertRaises(ValueError):
            self.service.move(MovementRequest(item='Фильтр', quantity=1, user_id=123, from_location='main', to_location='main'))


    def test_inbound_is_idempotent_by_op_id(self):
        first = self.service.inbound(
            MovementRequest(item='Фильтр', quantity=3, user_id=123, to_location='main', op_id='op-1')
        )
        second = self.service.inbound(
            MovementRequest(item='Фильтр', quantity=3, user_id=123, to_location='main', op_id='op-1')
        )
        self.assertEqual(first.balance, 23)
        self.assertEqual(second.balance, 23)
        self.assertEqual(self.storage.get_stock('Фильтр', 'main'), 23)

    def test_move_is_idempotent_by_op_id(self):
        first = self.service.move(
            MovementRequest(item='Фильтр', quantity=2, user_id=123, from_location='main', to_location='reserve', op_id='op-move-1')
        )
        second = self.service.move(
            MovementRequest(item='Фильтр', quantity=2, user_id=123, from_location='main', to_location='reserve', op_id='op-move-1')
        )
        self.assertEqual(first.balance, 2)
        self.assertEqual(second.balance, 2)
        self.assertEqual(self.storage.get_stock('Фильтр', 'main'), 18)
        self.assertEqual(self.storage.get_stock('Фильтр', 'reserve'), 2)
    def test_write_off_decreases_balance(self):
        result = self.service.write_off(MovementRequest(item='Фильтр', quantity=2, user_id=123, from_location='main'))
        self.assertEqual(result.balance, 18)


if __name__ == '__main__':
    unittest.main()
