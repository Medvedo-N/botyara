from __future__ import annotations

from telegram.ext import Application

from app.bot.router import register_handlers
from app.config import get_settings
from app.services.inventory import InventoryService
from app.services.notifications import LowStockNotifier
from app.services.rbac import RbacService
from app.services.reorder import ReorderService
from app.storage.interface import StoragePort
from app.storage.memory import MemoryStorage
from app.storage.sheets import GoogleSheetsStorage


def get_storage() -> StoragePort:
    settings = get_settings()
    backend = settings.STORAGE_BACKEND.lower()
    if backend == 'sheets':
        return GoogleSheetsStorage(spreadsheet_id=settings.SPREADSHEET_ID)
    return MemoryStorage(superadmin_tg_id=settings.SUPERADMIN_TG_ID)


def get_low_stock_notifier() -> LowStockNotifier:
    settings = get_settings()
    return LowStockNotifier(
        chat_id=settings.LOW_STOCK_NOTIFY_CHAT_ID,
        fallback_chat_id=settings.SUPERADMIN_TG_ID if settings.SUPERADMIN_TG_ID else None,
        throttle_minutes=settings.LOW_STOCK_THROTTLE_MINUTES,
    )


def get_reorder_service(storage: StoragePort, *, notifier: LowStockNotifier, application_bot) -> ReorderService:
    return ReorderService(storage=storage, notifier=notifier, bot=application_bot)


def get_inventory_service(storage: StoragePort, *, notifier: LowStockNotifier, reorder: ReorderService, application_bot) -> InventoryService:
    return InventoryService(storage=storage, notifier=notifier, reorder=reorder, bot=application_bot)


def get_rbac_service(storage: StoragePort) -> RbacService:
    settings = get_settings()
    return RbacService(storage=storage, superadmin_tg_id=settings.SUPERADMIN_TG_ID)


def build_telegram_application() -> Application:
    settings = get_settings()
    storage = get_storage()

    application = Application.builder().token(settings.BOT_TOKEN).build()
    register_handlers(application)

    notifier = get_low_stock_notifier()
    reorder_service = get_reorder_service(storage, notifier=notifier, application_bot=application.bot)
    inventory_service = get_inventory_service(storage, notifier=notifier, reorder=reorder_service, application_bot=application.bot)
    rbac_service = get_rbac_service(storage)

    application.bot_data['storage'] = storage
    application.bot_data['notifier'] = notifier
    application.bot_data['reorder_service'] = reorder_service
    application.bot_data['inventory_service'] = inventory_service
    application.bot_data['rbac_service'] = rbac_service
    application.bot_data['settings'] = settings
    return application
