from __future__ import annotations

from enum import Enum


class DialogState(str, Enum):
    IDLE = 'IDLE'
    WAITING_INBOUND = 'WAITING_INBOUND'
    WAITING_STOCK = 'WAITING_STOCK'
    TAKE_SELECT_ITEM = 'TAKE_SELECT_ITEM'
    TAKE_SELECT_QTY = 'TAKE_SELECT_QTY'
    TAKE_CONFIRM = 'TAKE_CONFIRM'
