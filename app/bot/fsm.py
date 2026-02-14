from __future__ import annotations

from enum import Enum


class UserState(str, Enum):
    IDLE = "IDLE"
    SELECT_LOCATION = "SELECT_LOCATION"
    SELECT_ITEM = "SELECT_ITEM"
    INPUT_QTY = "INPUT_QTY"
    CONFIRM = "CONFIRM"
    DONE = "DONE"
    SEARCH_ITEM = "SEARCH_ITEM"
