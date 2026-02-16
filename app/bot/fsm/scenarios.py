from __future__ import annotations

import re

from app.bot.fsm.states import DialogState


def parse_inventory_input(text: str) -> tuple[str, int] | None:
    chunks = [chunk.strip() for chunk in text.split(',')]
    if len(chunks) != 2:
        return None
    item, quantity_raw = chunks
    if not item or not quantity_raw.isdigit():
        return None
    quantity = int(quantity_raw)
    if quantity <= 0:
        return None
    return item, quantity


def parse_stock_item_input(text: str) -> str | None:
    cleaned = text.strip()
    if not cleaned:
        return None
    match = re.match(r'^(?P<item>.+?)(?:\s*[:,]\s*\d+)?$', cleaned)
    if not match:
        return None
    item = match.group('item').strip()
    return item or None


def parse_positive_int(text: str) -> int | None:
    cleaned = text.strip()
    if not cleaned.isdigit():
        return None
    value = int(cleaned)
    if value <= 0:
        return None
    return value


def start_state_for_action(action: str) -> DialogState:
    mapping = {
        'IN': DialogState.WAITING_INBOUND,
        'OUT': DialogState.TAKE_SELECT_ITEM,
        'STOCK': DialogState.WAITING_STOCK,
    }
    return mapping[action]
