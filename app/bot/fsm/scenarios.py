from __future__ import annotations

import re

from app.bot.fsm.states import DialogState


def parse_inventory_input(text: str) -> tuple[str, int] | None:
    chunks = [chunk.strip() for chunk in text.split(',')]
    if len(chunks) != 2:
        return None
    item, quantity_raw = chunks
    if not item:
        return None
    if not quantity_raw.isdigit():
        return None
    quantity = int(quantity_raw)
    if quantity <= 0:
        return None
    return item, quantity


def parse_stock_item_input(text: str) -> str | None:
    cleaned = text.strip()
    if not cleaned:
        return None

    # Accept: "item", "item, 1", "item:1" and ignore trailing number part.
    match = re.match(r"^(?P<item>.+?)(?:\s*[:,]\s*\d+)?$", cleaned)
    if not match:
        return None
    item = match.group('item').strip()
    return item or None


def start_state_for_action(action: str) -> DialogState:
    mapping = {
        'IN': DialogState.WAITING_INBOUND,
        'OUT': DialogState.WAITING_OUTBOUND,
        'MOVE': DialogState.WAITING_MOVE,
        'WRITE_OFF': DialogState.WAITING_WRITE_OFF,
        'STOCK': DialogState.WAITING_STOCK,
    }
    return mapping[action]


def is_active_state(state: DialogState) -> bool:
    return state != DialogState.IDLE
