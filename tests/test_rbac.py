import unittest

from app.models.domain import Role
from app.services.rbac import RbacService
from app.storage.memory import MemoryStorage


class RbacTests(unittest.TestCase):
    def setUp(self):
        self.storage = MemoryStorage(superadmin_tg_id=999)
        self.storage._roles[1] = Role.USER
        self.storage._roles[2] = Role.SENIOR_MANAGER
        self.storage._roles[3] = Role.MANAGER
        self.rbac = RbacService(storage=self.storage, superadmin_tg_id=999)

    def test_user_has_no_inbound_access(self):
        self.assertFalse(self.rbac.has_permission(1, 'inventory.inbound'))

    def test_senior_manager_users_permissions(self):
        self.assertTrue(self.rbac.has_permission(2, 'users.view'))
        self.assertFalse(self.rbac.has_permission(2, 'users.manage'))

    def test_manager_cannot_view_users(self):
        self.assertFalse(self.rbac.has_permission(3, 'users.view'))


if __name__ == '__main__':
    unittest.main()
