from __future__ import annotations

from functools import lru_cache

from telegram.ext import Application

from app.bot.router import register_handlers
from app.config import Settings, get_settings
from app.services.inventory import InventoryService
from app.services.rbac import RbacService
from app.storage.interface import StoragePort
from app.storage.memory import MemoryStorage
from app.storage.sheets import GoogleSheetsStorage


@lru_cache(maxsize=1)
def get_storage(settings: Settings | None = None) -> StoragePort:
    settings = settings or get_settings()
    backend = settings.STORAGE_BACKEND.lower()
    if backend == 'sheets':
        return GoogleSheetsStorage(spreadsheet_id=settings.SPREADSHEET_ID)
    return MemoryStorage(superadmin_tg_id=settings.SUPERADMIN_TG_ID)


@lru_cache(maxsize=1)
def get_inventory_service() -> InventoryService:
    return InventoryService(storage=get_storage())


@lru_cache(maxsize=1)
def get_rbac_service() -> RbacService:
    settings = get_settings()
    return RbacService(storage=get_storage(settings), superadmin_tg_id=settings.SUPERADMIN_TG_ID)


@lru_cache(maxsize=1)
def build_telegram_application() -> Application:
    settings = get_settings()
    application = Application.builder().token(settings.BOT_TOKEN).build()
    register_handlers(application)
    application.bot_data['inventory_service'] = get_inventory_service()
    application.bot_data['rbac_service'] = get_rbac_service()
    application.bot_data['settings'] = settings
    return application
