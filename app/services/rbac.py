from __future__ import annotations

from dataclasses import dataclass

from app.models.domain import Role
from app.storage.interface import StoragePort

PERMISSIONS: dict[Role, set[str]] = {
    Role.OWNER: {'inventory.read', 'inventory.inbound', 'inventory.outbound', 'inventory.move', 'inventory.write_off'},
    Role.MANAGER: {'inventory.read', 'inventory.inbound', 'inventory.outbound', 'inventory.move', 'inventory.write_off'},
    Role.STOREKEEPER: {'inventory.read', 'inventory.inbound', 'inventory.outbound', 'inventory.move'},
    Role.VIEWER: {'inventory.read'},
    Role.NO_ACCESS: set(),
}


@dataclass
class RbacService:
    storage: StoragePort
    superadmin_tg_id: int

    def get_role(self, user_id: int) -> Role:
        if user_id == self.superadmin_tg_id:
            return Role.OWNER
        return self.storage.get_user_role(user_id)

    def require_permission(self, user_id: int, permission: str) -> Role:
        role = self.get_role(user_id)
        if permission not in PERMISSIONS.get(role, set()):
            raise PermissionError(f'permission denied: {permission} for role {role.value}')
        return role
