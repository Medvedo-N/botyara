"""
Dependency Injection Container.
Управляет созданием и кешированием зависимостей (синглтоны).
"""
from __future__ import annotations

from typing import Optional

from app.di import (
    get_inventory_service,
    get_low_stock_notifier,
    get_rbac_service,
    get_reorder_service,
    get_storage,
)
from app.services.inventory import InventoryService
from app.services.notifications import LowStockNotifier
from app.services.rbac import RbacService
from app.services.reorder import ReorderService
from app.storage.interface import StoragePort
from app.storage.repository import GoogleSheetsInventoryRepository, InventoryRepository


class DIContainer:
    """
    Типизированный IoC-контейнер.
    Гарантирует одноразовое создание сервисов (синглтоны).
    """

    def __init__(self):
        self._storage: Optional[StoragePort] = None
        self._inventory_repo: Optional[InventoryRepository] = None
        self._low_stock_notifier: Optional[LowStockNotifier] = None
        self._reorder_service: Optional[ReorderService] = None
        self._inventory_service: Optional[InventoryService] = None
        self._rbac_service: Optional[RbacService] = None
        self._application_bot = None

    def set_application_bot(self, bot) -> None:
        """Установить экземпляр бота (требуется для сервисов, которые отправляют сообщения)."""
        self._application_bot = bot

    def get_storage(self) -> StoragePort:
        """Получить хранилище (StoragePort)."""
        if self._storage is None:
            self._storage = get_storage()
        return self._storage

    def get_inventory_repository(self) -> InventoryRepository:
        """Получить репозиторий товаров."""
        if self._inventory_repo is None:
            storage = self.get_storage()
            self._inventory_repo = GoogleSheetsInventoryRepository(storage)
        return self._inventory_repo

    def get_low_stock_notifier(self) -> LowStockNotifier:
        """Получить сервис уведомлений о низких остатках."""
        if self._low_stock_notifier is None:
            self._low_stock_notifier = get_low_stock_notifier()
        return self._low_stock_notifier

    def get_reorder_service(self) -> ReorderService:
        """Получить сервис переказов."""
        if self._reorder_service is None:
            storage = self.get_storage()
            notifier = self.get_low_stock_notifier()
            self._reorder_service = get_reorder_service(storage, notifier=notifier, application_bot=self._application_bot)
        return self._reorder_service

    def get_inventory_service(self) -> InventoryService:
        """Получить основной сервис работы с товарами."""
        if self._inventory_service is None:
            storage = self.get_storage()
            notifier = self.get_low_stock_notifier()
            reorder = self.get_reorder_service()
            self._inventory_service = get_inventory_service(
                storage, notifier=notifier, reorder=reorder, application_bot=self._application_bot
            )
        return self._inventory_service

    def get_rbac_service(self) -> RbacService:
        """Получить сервис RBAC (управление доступом)."""
        if self._rbac_service is None:
            storage = self.get_storage()
            self._rbac_service = get_rbac_service(storage)
        return self._rbac_service

    def reset(self) -> None:
        """Сбросить все кешированные сервисы (для тестирования)."""
        self._storage = None
        self._inventory_repo = None
        self._low_stock_notifier = None
        self._reorder_service = None
        self._inventory_service = None
        self._rbac_service = None


# Глобальный экземпляр контейнера
# Может быть переопределен в тестах или для специализированных конфигов
container: DIContainer = DIContainer()
