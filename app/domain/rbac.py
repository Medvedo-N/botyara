from __future__ import annotations
from dataclasses import dataclass
from .models import Role, TxnType


@dataclass(frozen=True)
class PermissionError(Exception):
    message: str


def require_role(user_role: Role, min_role: Role) -> None:
    order = {Role.USER: 0, Role.ADMIN: 1, Role.SENIOR_ADMIN: 2}
    if order[user_role] < order[min_role]:
        raise PermissionError(f"Недостаточно прав: нужно {min_role}, у тебя {user_role}")


def min_role_for_txn(txn_type: TxnType) -> Role:
    # стартуем консервативно
    if txn_type in (TxnType.IN_, TxnType.OUT, TxnType.WRITE_OFF, TxnType.DEFECT):
        return Role.ADMIN
    return Role.ADMIN
