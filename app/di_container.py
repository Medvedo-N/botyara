from typing import Optional

# Здесь будут импорты ваших реальных сервисов
# from app.services.inventory import InventoryService
# from app.services.rbac import RbacService
# from app.storage.repository import InventoryRepository, SqlAlchemyInventoryRepository


class DIContainer:
    """
    Простой IoC-контейнер для управления зависимостями.
    Гарантирует, что сервисы создаются как синглтоны (по необходимости).
    """
    def __init__(self):
        self._inventory_repo = None
        self._inventory_service = None
        self._rbac_service = None

    def get_inventory_repo(self): # -> InventoryRepository:
        if self._inventory_repo is None:
            # TODO: Инициализация БД (например, session_factory)
            # self._inventory_repo = SqlAlchemyInventoryRepository(...)
            pass
        return self._inventory_repo

    def get_inventory_service(self): # -> InventoryService:
        if self._inventory_service is None:
            # Внедряем зависимость (репозиторий) в сервис
            repo = self.get_inventory_repo()
            # self._inventory_service = InventoryService(storage=repo)
            pass
        return self._inventory_service

    def get_rbac_service(self): # -> RbacService:
        if self._rbac_service is None:
            # TODO: Инициализация RBAC
            # self._rbac_service = RbacService(...)
            pass
        return self._rbac_service


# Глобальный экземпляр контейнера (для простоты доступа из хендлеров)
# В идеале он прокидывается через middleware бота
container = DIContainer()