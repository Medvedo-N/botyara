from __future__ import annotations

import os

from app.models import Role
from app.services.storage import get_storage


def get_role(tg_id: int) -> Role:
    storage = get_storage()
    user = storage.get_user(tg_id)
    if user and user.active:
        return user.role

    bootstrap_superadmin = os.getenv("SUPERADMIN_TG_ID", "").strip()
    if bootstrap_superadmin.isdigit() and int(bootstrap_superadmin) == tg_id:
        return Role.SUPERADMIN

    return Role.NO_ACCESS


def can_access_admin(role: Role) -> bool:
    return role == Role.SUPERADMIN


def can_access_stock(role: Role) -> bool:
    return role in {Role.SUPERADMIN, Role.ADMIN, Role.TECH}
