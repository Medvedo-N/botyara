from __future__ import annotations

import hashlib
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.bot.fsm import UserState
from app.config import VERSION
from app.models import Operation, OperationType, Role
from app.services.errors import IN_DEVELOPMENT_TEXT, NO_ACCESS_TEXT, UNKNOWN_ACTION_TEXT
from app.services.rbac import can_access_admin, can_access_stock, get_role
from app.services.storage import NotFoundError, ValidationError, get_storage

PAGE_SIZE = 5
logger = logging.getLogger(__name__)


def _role_name(role: Role) -> str:
    mapping = {
        Role.SUPERADMIN: "superadmin",
        Role.ADMIN: "admin",
        Role.TECH: "tech",
        Role.VIEWER: "viewer",
        Role.NO_ACCESS: "нет доступа",
    }
    return mapping[role]


def _main_menu(role: Role) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("📦 Склад", callback_data="menu:stock")],
        [InlineKeyboardButton("🧾 История", callback_data="menu:history")],
    ]
    if can_access_admin(role):
        rows.extend(
            [
                [InlineKeyboardButton("📍 Локации", callback_data="menu:locations")],
                [InlineKeyboardButton("👥 Пользователи", callback_data="menu:users")],
            ]
        )
    rows.append([InlineKeyboardButton("⚙️ Настройки", callback_data="menu:settings")])
    return InlineKeyboardMarkup(rows)


def _back_menu(target: str = "menu:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data=target)]])


def _stock_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Приход", callback_data="op:start:IN")],
            [InlineKeyboardButton("➖ Выдача", callback_data="op:start:OUT")],
            [InlineKeyboardButton("⚠️ Списание", callback_data="op:start:WRITE_OFF")],
            [InlineKeyboardButton("🔁 Перемещение", callback_data="op:start:MOVE")],
            [InlineKeyboardButton("🔎 Остатки", callback_data="stock:balances")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="menu:main")],
        ]
    )


def _locations_menu(mode: str) -> InlineKeyboardMarkup:
    storage = get_storage()
    rows = [
        [InlineKeyboardButton(loc.location_name, callback_data=f"{mode}:loc:{loc.location_id}")]
        for loc in storage.list_locations()
    ]
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu:stock")])
    return InlineKeyboardMarkup(rows)


def _items_menu(mode: str, query: str, page: int) -> InlineKeyboardMarkup:
    storage = get_storage()
    items, has_more = storage.search_items(query=query, page=page, page_size=PAGE_SIZE)
    rows = [
        [InlineKeyboardButton(f"{item.name} ({item.sku})", callback_data=f"{mode}:item:{item.sku}")]
        for item in items
    ]
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"{mode}:page:{query}:{page - 1}"))
    if has_more:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"{mode}:page:{query}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("🔎 Поиск товара", callback_data=f"{mode}:search")])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu:stock")])
    return InlineKeyboardMarkup(rows)


def _operation_label(op_type: OperationType) -> str:
    labels = {
        OperationType.IN_: "Приход",
        OperationType.OUT: "Выдача",
        OperationType.WRITE_OFF: "Списание",
        OperationType.MOVE: "Перемещение",
    }
    return labels[op_type]


def _parse_operation_type(raw: str) -> OperationType:
    if raw == OperationType.IN_.value:
        return OperationType.IN_
    return OperationType(raw)


def _normalize_text(text: str) -> str:
    cleaned = text.strip().lower()
    for emoji in ["📦", "📄", "📥", "⚠️", "⚠", "➕", "➖", "🔁", "🔎", "🧾", "📍", "👥", "⚙️", "⚙"]:
        cleaned = cleaned.replace(emoji, "")
    return " ".join(cleaned.split())


def _menu_action_from_text(text: str) -> str | None:
    normalized = _normalize_text(text)

    if normalized in {"остатки", "остаток"} or "остатк" in normalized:
        return "stock:balances"
    if normalized in {"взять товар", "выдача", "расход"} or normalized.startswith("взять товар"):
        return "op:start:OUT"
    if normalized in {"приход", "поступление"} or normalized.startswith("приход"):
        return "op:start:IN"
    if normalized in {"брак", "списание"} or "брак" in normalized or "списан" in normalized:
        return "op:start:WRITE_OFF"
    if normalized in {"перемещение", "переместить"} or "перемещ" in normalized:
        return "op:start:MOVE"
    if normalized in {"склад", "меню", "главное меню"}:
        return "menu:stock"

    return None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or update.message is None:
        return

    role = get_role(user.id)
    if role == Role.NO_ACCESS:
        await update.message.reply_text(NO_ACCESS_TEXT)
        return

    context.user_data["state"] = UserState.IDLE
    await update.message.reply_text(
        f"Ботяра запущен ✅\nВерсия: {VERSION}\nВаша роль: {_role_name(role)}",
        reply_markup=_main_menu(role),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text(
        "Команды:\n"
        "/start — главное меню\n"
        "/help — эта справка\n\n"
        "Быстрые действия текстом/кнопками:\n"
        "Остатки, Взять товар, Приход, Брак, Перемещение"
    )


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    user = update.effective_user
    if user is None:
        await query.edit_message_text(UNKNOWN_ACTION_TEXT, reply_markup=_back_menu())
        return

    role = get_role(user.id)
    data = query.data or ""

    if role == Role.NO_ACCESS:
        await query.edit_message_text(NO_ACCESS_TEXT, reply_markup=_back_menu())
        return

    if data in {"menu:main", "menu:back"}:
        context.user_data.clear()
        context.user_data["state"] = UserState.IDLE
        await query.edit_message_text("Главное меню", reply_markup=_main_menu(role))
        return

    if data == "menu:stock":
        if not can_access_stock(role):
            await query.edit_message_text(NO_ACCESS_TEXT, reply_markup=_back_menu())
            return
        await query.edit_message_text("Раздел: Склад", reply_markup=_stock_menu())
        return

    if data == "stock:balances":
        context.user_data["state"] = UserState.SELECT_LOCATION
        await query.edit_message_text("Выберите локацию", reply_markup=_locations_menu("balance"))
        return

    if data.startswith("balance:loc:"):
        location_id = data.split(":", maxsplit=2)[2]
        context.user_data["balance_location_id"] = location_id
        context.user_data["state"] = UserState.SELECT_ITEM
        await query.edit_message_text("Выберите товар", reply_markup=_items_menu("balance", query="", page=0))
        return

    if data.startswith("balance:search"):
        context.user_data["state"] = UserState.SEARCH_ITEM
        context.user_data["search_mode"] = "balance"
        await query.edit_message_text("Введите название или SKU товара")
        return

    if data.startswith("balance:page:"):
        _, _, _, search_query, page = data.split(":", maxsplit=4)
        await query.edit_message_text(
            "Выберите товар",
            reply_markup=_items_menu("balance", query=search_query, page=max(0, int(page))),
        )
        return

    if data.startswith("balance:item:"):
        sku = data.split(":", maxsplit=2)[2]
        location_id = context.user_data.get("balance_location_id")
        if not location_id:
            await query.edit_message_text("Сначала выберите локацию", reply_markup=_back_menu("stock:balances"))
            return
        balance = get_storage().get_balance(location_id=location_id, sku=sku)
        await query.edit_message_text(
            f"Остаток для {sku} в локации {location_id}: {balance.qty}",
            reply_markup=_back_menu("menu:stock"),
        )
        context.user_data["state"] = UserState.DONE
        return

    if data.startswith("op:start:"):
        op_type = _parse_operation_type(data.split(":", maxsplit=2)[2])
        context.user_data["op"] = {
            "op_type": op_type.value,
            "sku": None,
            "from_location": None,
            "to_location": None,
        }
        context.user_data["state"] = UserState.SELECT_LOCATION
        prompt = "Выберите локацию назначения" if op_type == OperationType.IN_ else "Выберите исходную локацию"
        await query.edit_message_text(prompt, reply_markup=_locations_menu("opfrom"))
        return

    if data.startswith("opfrom:loc:"):
        location_id = data.split(":", maxsplit=2)[2]
        op_data = context.user_data.get("op")
        if not isinstance(op_data, dict):
            await query.edit_message_text("Операция не инициализирована", reply_markup=_back_menu("menu:stock"))
            return
        op_type = _parse_operation_type(op_data["op_type"])
        if op_type == OperationType.IN_:
            op_data["to_location"] = location_id
        else:
            op_data["from_location"] = location_id
        context.user_data["op"] = op_data
        context.user_data["state"] = UserState.SELECT_ITEM
        await query.edit_message_text("Выберите товар", reply_markup=_items_menu("op", query="", page=0))
        return

    if data.startswith("op:search"):
        context.user_data["state"] = UserState.SEARCH_ITEM
        context.user_data["search_mode"] = "op"
        await query.edit_message_text("Введите название или SKU товара")
        return

    if data.startswith("op:page:"):
        _, _, _, search_query, page = data.split(":", maxsplit=4)
        await query.edit_message_text(
            "Выберите товар",
            reply_markup=_items_menu("op", query=search_query, page=max(0, int(page))),
        )
        return

    if data.startswith("op:item:"):
        sku = data.split(":", maxsplit=2)[2]
        op_data = context.user_data.get("op")
        if not isinstance(op_data, dict):
            await query.edit_message_text("Операция не инициализирована", reply_markup=_back_menu("menu:stock"))
            return
        op_type = _parse_operation_type(op_data["op_type"])
        op_data["sku"] = sku
        context.user_data["op"] = op_data

        if op_type == OperationType.MOVE and not op_data.get("to_location"):
            await query.edit_message_text("Выберите локацию назначения", reply_markup=_locations_menu("opto"))
            return

        context.user_data["state"] = UserState.INPUT_QTY
        await query.edit_message_text("Введите количество (число > 0)")
        return

    if data.startswith("opto:loc:"):
        location_id = data.split(":", maxsplit=2)[2]
        op_data = context.user_data.get("op")
        if not isinstance(op_data, dict):
            await query.edit_message_text("Операция не инициализирована", reply_markup=_back_menu("menu:stock"))
            return
        op_data["to_location"] = location_id
        context.user_data["op"] = op_data
        context.user_data["state"] = UserState.INPUT_QTY
        await query.edit_message_text("Введите количество (число > 0)")
        return

    if data == "op:confirm":
        await _execute_operation(update, context)
        return

    if data == "op:cancel":
        context.user_data.clear()
        context.user_data["state"] = UserState.IDLE
        await query.edit_message_text("Операция отменена", reply_markup=_stock_menu())
        return

    if data in {"menu:history", "menu:settings", "menu:locations", "menu:users"}:
        if data in {"menu:locations", "menu:users"} and not can_access_admin(role):
            await query.edit_message_text(NO_ACCESS_TEXT, reply_markup=_back_menu())
            return
        await query.edit_message_text(IN_DEVELOPMENT_TEXT, reply_markup=_back_menu())
        return

    await query.edit_message_text(UNKNOWN_ACTION_TEXT, reply_markup=_back_menu())


async def _execute_operation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    user = update.effective_user
    if user is None:
        await query.edit_message_text(UNKNOWN_ACTION_TEXT, reply_markup=_back_menu())
        return

    op_data = context.user_data.get("op")
    if not isinstance(op_data, dict):
        await query.edit_message_text("Операция не инициализирована", reply_markup=_back_menu("menu:stock"))
        return

    try:
        op = Operation(
            op_id=_build_op_id(update, op_data),
            op_type=_parse_operation_type(op_data["op_type"]),
            sku=str(op_data["sku"]),
            qty=int(op_data["qty"]),
            from_location=op_data.get("from_location"),
            to_location=op_data.get("to_location"),
            user_tg_id=user.id,
        )
        balance = get_storage().apply_operation(op)
    except (ValidationError, NotFoundError) as exc:
        await query.edit_message_text(str(exc), reply_markup=_back_menu("menu:stock"))
        return

    context.user_data.clear()
    context.user_data["state"] = UserState.DONE
    await query.edit_message_text(
        f"Готово ✅\nОперация: {_operation_label(op.op_type)}\nSKU: {op.sku}\nНовый остаток ({balance.location_id}): {balance.qty}",
        reply_markup=_stock_menu(),
    )


async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    state = context.user_data.get("state", UserState.IDLE)
    text = (update.message.text or "").strip()
    logger.warning("ROUTER HIT text=%r state=%s", text, state)

    action = _menu_action_from_text(text)
    if action:
        role = get_role(update.effective_user.id if update.effective_user else 0)
        if action == "menu:stock":
            if not can_access_stock(role):
                await update.message.reply_text(NO_ACCESS_TEXT)
                return
            context.user_data["state"] = UserState.IDLE
            await update.message.reply_text("Раздел: Склад", reply_markup=_stock_menu())
            return

        if action == "stock:balances":
            if not can_access_stock(role):
                await update.message.reply_text(NO_ACCESS_TEXT)
                return
            context.user_data.pop("op", None)
            context.user_data["state"] = UserState.SELECT_LOCATION
            await update.message.reply_text("Выберите локацию", reply_markup=_locations_menu("balance"))
            return

        if action.startswith("op:start:"):
            if not can_access_stock(role):
                await update.message.reply_text(NO_ACCESS_TEXT)
                return
            op_type = _parse_operation_type(action.split(":", maxsplit=2)[2])
            context.user_data["op"] = {
                "op_type": op_type.value,
                "sku": None,
                "from_location": None,
                "to_location": None,
            }
            context.user_data["state"] = UserState.SELECT_LOCATION
            prompt = "Выберите локацию назначения" if op_type == OperationType.IN_ else "Выберите исходную локацию"
            await update.message.reply_text(prompt, reply_markup=_locations_menu("opfrom"))
            return

    if state == UserState.SEARCH_ITEM:
        mode = context.user_data.get("search_mode", "balance")
        context.user_data["state"] = UserState.SELECT_ITEM
        await update.message.reply_text(
            "Результаты поиска",
            reply_markup=_items_menu(mode, query=text, page=0),
        )
        return

    if state == UserState.INPUT_QTY:
        try:
            qty = int(text.strip())
        except ValueError:
            await update.message.reply_text("Введите целое число больше нуля")
            return

        if qty <= 0:
            await update.message.reply_text("Количество должно быть больше нуля")
            return

        op_data = context.user_data.get("op")
        if not isinstance(op_data, dict):
            await update.message.reply_text("Операция не инициализирована")
            return
        op_type = _parse_operation_type(op_data["op_type"])
        if op_type == OperationType.MOVE and op_data.get("from_location") == op_data.get("to_location"):
            await update.message.reply_text("Локации перемещения должны отличаться")
            return

        op_data["qty"] = qty
        context.user_data["op"] = op_data
        context.user_data["state"] = UserState.CONFIRM

        summary = [
            f"Подтвердите операцию: {_operation_label(op_type)}",
            f"SKU: {op_data.get('sku')}",
            f"Количество: {qty}",
        ]
        if op_data.get("from_location"):
            summary.append(f"Откуда: {op_data['from_location']}")
        if op_data.get("to_location"):
            summary.append(f"Куда: {op_data['to_location']}")

        await update.message.reply_text(
            "\n".join(summary),
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("✅ Подтвердить", callback_data="op:confirm")],
                    [InlineKeyboardButton("❌ Отмена", callback_data="op:cancel")],
                ]
            ),
        )
        return

    logger.warning("FALLBACK HIT text=%r state=%s", text, state)
    await update.message.reply_text(UNKNOWN_ACTION_TEXT)



def _build_op_id(update: Update, op_data: dict) -> str:
    user_id = update.effective_user.id if update.effective_user else 0
    update_id = update.update_id or 0
    action = op_data.get("op_type", "")
    payload = f"{update_id}:{user_id}:{action}:{op_data.get('sku')}:{op_data.get('from_location')}:{op_data.get('to_location')}:{op_data.get('qty')}"
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    role = get_role(update.effective_user.id)
    if not can_access_admin(role):
        await update.message.reply_text(NO_ACCESS_TEXT)
        return

    args = context.args
    storage = get_storage()
    if not args or args[0] == "list":
        users = storage.list_users()
        text = "\n".join([f"{u.tg_id} | {u.role.value} | {'active' if u.active else 'blocked'}" for u in users[:40]]) or "Список пользователей пуст"
        await update.message.reply_text(text)
        return

    cmd = args[0]
    try:
        if cmd == "add" and len(args) >= 3:
            tg_id = int(args[1])
            role_val = Role(args[2].lower())
            user = storage.add_or_update_user(tg_id=tg_id, role=role_val)
            await update.message.reply_text(f"Пользователь добавлен: {user.tg_id} -> {user.role.value}")
            return
        if cmd in {"block", "unblock"} and len(args) >= 2:
            tg_id = int(args[1])
            storage.set_user_active(tg_id=tg_id, active=(cmd == "unblock"))
            await update.message.reply_text("Готово")
            return
    except Exception as exc:
        await update.message.reply_text(str(exc))
        return

    await update.message.reply_text("Использование: /users list | /users add <tg_id> <superadmin|admin|tech> | /users block <tg_id> | /users unblock <tg_id>")


async def locations_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    role = get_role(update.effective_user.id)
    if not can_access_admin(role):
        await update.message.reply_text(NO_ACCESS_TEXT)
        return

    args = context.args
    storage = get_storage()
    if not args or args[0] == "list":
        locs = storage.list_locations()
        text = "\n".join([f"{loc.location_id} | {loc.location_name}" for loc in locs]) or "Локации пусты"
        await update.message.reply_text(text)
        return

    try:
        if args[0] == "add" and len(args) >= 3:
            loc = storage.add_location(args[1], " ".join(args[2:]))
            await update.message.reply_text(f"Локация добавлена: {loc.location_id}")
            return
        if args[0] == "rename" and len(args) >= 3:
            loc = storage.rename_location(args[1], " ".join(args[2:]))
            await update.message.reply_text(f"Локация переименована: {loc.location_id}")
            return
        if args[0] == "archive" and len(args) >= 2:
            storage.archive_location(args[1])
            await update.message.reply_text("Локация архивирована")
            return
    except Exception as exc:
        await update.message.reply_text(str(exc))
        return

    await update.message.reply_text("Использование: /locations list | /locations add <id> <name> | /locations rename <id> <new_name> | /locations archive <id>")


async def items_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    role = get_role(update.effective_user.id)
    if not can_access_admin(role):
        await update.message.reply_text(NO_ACCESS_TEXT)
        return

    args = context.args
    storage = get_storage()
    if not args or args[0] == "list":
        items, _ = storage.search_items(query="", page=0, page_size=30)
        text = "\n".join([f"{i.sku} | {i.name} | {i.unit}" for i in items]) or "Номенклатура пуста"
        await update.message.reply_text(text)
        return

    try:
        if args[0] == "add" and len(args) >= 4:
            item = storage.add_item(args[1], " ".join(args[2:-1]), unit=args[-1])
            await update.message.reply_text(f"Товар добавлен: {item.sku}")
            return
        if args[0] == "rename" and len(args) >= 3:
            item = storage.rename_item(args[1], " ".join(args[2:]))
            await update.message.reply_text(f"Товар переименован: {item.sku}")
            return
        if args[0] == "archive" and len(args) >= 2:
            storage.archive_item(args[1])
            await update.message.reply_text("Товар архивирован")
            return
    except Exception as exc:
        await update.message.reply_text(str(exc))
        return

    await update.message.reply_text("Использование: /items list | /items add <sku> <name> <unit> | /items rename <sku> <new_name> | /items archive <sku>")

def register_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("users", users_command))
    application.add_handler(CommandHandler("locations", locations_command))
    application.add_handler(CommandHandler("items", items_command))
    application.add_handler(CallbackQueryHandler(callback_router))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))
