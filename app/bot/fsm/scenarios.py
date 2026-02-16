from __future__ import annotations

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


def start_state_for_action(action: str) -> DialogState:
    mapping = {
        'IN': DialogState.WAITING_INBOUND,
        'OUT': DialogState.WAITING_OUTBOUND,
        'MOVE': DialogState.WAITING_MOVE,
        'WRITE_OFF': DialogState.WAITING_WRITE_OFF,
        'STOCK': DialogState.WAITING_STOCK,
    }
    return mapping[action]
