import unittest

from app.models import Operation, OperationType
from app.services.storage import MockStorageAdapter, ValidationError


class StorageTests(unittest.TestCase):
    def test_out_cannot_go_negative(self):
        storage = MockStorageAdapter()
        op = Operation(
            op_id="op-out-1",
            op_type=OperationType.OUT,
            sku="SKU-001",
            qty=999,
            from_location="main",
            user_tg_id=1,
        )
        with self.assertRaises(ValidationError):
            storage.apply_operation(op)

    def test_move_updates_both_locations(self):
        storage = MockStorageAdapter()
        op = Operation(
            op_id="op-move-1",
            op_type=OperationType.MOVE,
            sku="SKU-001",
            qty=2,
            from_location="main",
            to_location="shop",
            user_tg_id=1,
        )
        storage.apply_operation(op)
        self.assertEqual(storage.get_balance("main", "SKU-001").qty, 25)
        self.assertEqual(storage.get_balance("shop", "SKU-001").qty, 10)

    def test_duplicate_op_id_is_idempotent(self):
        storage = MockStorageAdapter()
        op = Operation(
            op_id="op-dup-1",
            op_type=OperationType.OUT,
            sku="SKU-001",
            qty=3,
            from_location="main",
            user_tg_id=1,
        )
        first = storage.apply_operation(op)
        second = storage.apply_operation(op)
        self.assertEqual(first.qty, 24)
        self.assertEqual(second.qty, 24)


if __name__ == "__main__":
    unittest.main()
