from __future__ import annotations

from dataclasses import dataclass

from app.models.domain import Role
from app.storage.interface import StoragePort

PERMISSIONS: dict[Role, set[str]] = {
    Role.DEV: {'inventory.view', 'inventory.inbound', 'inventory.outbound', 'users.view', 'users.manage'},
    Role.SENIOR_MANAGER: {'inventory.view', 'inventory.inbound', 'inventory.outbound', 'users.view'},
    Role.MANAGER: {'inventory.view', 'inventory.inbound', 'inventory.outbound'},
    Role.USER: {'inventory.view', 'inventory.outbound'},
    Role.NO_ACCESS: set(),
}


@dataclass
class RbacService:
    storage: StoragePort
    superadmin_tg_id: int

    def get_role(self, user_id: int) -> Role:
        if user_id == self.superadmin_tg_id:
            return Role.DEV
        return self.storage.get_user_role(user_id)

    def has_permission(self, user_id: int, permission: str) -> bool:
        role = self.get_role(user_id)
        return permission in PERMISSIONS.get(role, set())

    def require_permission(self, user_id: int, permission: str) -> Role:
        role = self.get_role(user_id)
        if permission not in PERMISSIONS.get(role, set()):
            raise PermissionError(f'permission denied: {permission} for role {role.value}')
        return role
