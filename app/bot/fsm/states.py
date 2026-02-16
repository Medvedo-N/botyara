from __future__ import annotations

from enum import Enum


class DialogState(str, Enum):
    IDLE = 'IDLE'
    WAITING_INBOUND = 'WAITING_INBOUND'
    WAITING_OUTBOUND = 'WAITING_OUTBOUND'
    WAITING_MOVE = 'WAITING_MOVE'
    WAITING_WRITE_OFF = 'WAITING_WRITE_OFF'
    WAITING_STOCK = 'WAITING_STOCK'
