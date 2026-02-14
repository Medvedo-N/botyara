from __future__ import annotations
import os

from app.domain.models import Role, User
from app.infra.repos_memory import UserRepo


def _parse_ids(env_name: str) -> set[int]:
    raw = os.getenv(env_name, "").strip()
    if not raw:
        return set()
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


class AuthService:
    def __init__(self, user_repo: UserRepo):
        self.user_repo = user_repo
        self.admin_ids = _parse_ids("ADMIN_IDS")
        self.senior_admin_ids = _parse_ids("SENIOR_ADMIN_IDS")

    def resolve_role(self, tg_id: int) -> Role:
        if tg_id in self.senior_admin_ids:
            return Role.SENIOR_ADMIN
        if tg_id in self.admin_ids:
            return Role.ADMIN
        return Role.USER

    def get_or_create_user(self, tg_id: int, full_name: str = "", username: str = "") -> User:
        role = self.resolve_role(tg_id)
        u = self.user_repo.get(tg_id)

        if u is None:
            u = User(tg_id=tg_id, full_name=full_name, username=username, role=role)
            return self.user_repo.upsert(u)

        # если роль повысилась через ENV — обновляем
        if u.role != role and role in (Role.ADMIN, Role.SENIOR_ADMIN):
            u.role = role
            self.user_repo.upsert(u)

        return u
