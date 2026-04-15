"""
Repository pattern для работы с доменными сущностями.
Абстрагирует детали конкретного хранилища (Sheets, PostgreSQL, etc).
"""
from __future__ import annotations

import abc
from typing import Optional

from app.models.domain import Item, StockEntry


class InventoryRepository(abc.ABC):
    """Абстрактный репозиторий для работы с остатками товаров."""

    @abc.abstractmethod
    def get_item(self, name: str) -> Optional[Item]:
        """Получить товар по названию."""
        pass

    @abc.abstractmethod
    def list_items(self, *, active_only: bool = True) -> list[Item]:
        """Получить список всех товаров."""
        pass

    @abc.abstractmethod
    def list_active_items(self) -> list[Item]:
        """Получить список активных товаров, отсортированный по названию."""
        pass

    @abc.abstractmethod
    def list_stock(self) -> list[StockEntry]:
        """Получить текущие остатки в формате StockEntry."""
        pass

    @abc.abstractmethod
    def add_or_update_item(
        self,
        name: str,
        *,
        norm: int,
        crit_min: int,
        qty: int,
        is_active: bool = True,
        photo_file_id: Optional[str] = None,
    ) -> None:
        """Создать или обновить товар (UPSERT)."""
        pass

    @abc.abstractmethod
    def deactivate_item(self, name: str) -> None:
        """Деактивировать товар."""
        pass

    @abc.abstractmethod
    def add_inbound(self, item: str, quantity: int, user_id: int, op_id: Optional[str] = None) -> int:
        """Добавить приход товара, вернуть новый остаток."""
        pass

    @abc.abstractmethod
    def add_outbound(self, item: str, quantity: int, user_id: int, op_id: Optional[str] = None) -> int:
        """Отпустить товар (списание), вернуть новый остаток."""
        pass

    @abc.abstractmethod
    def get_stock(self, item: str) -> int:
        """Получить текущий остаток товара."""
        pass

    @abc.abstractmethod
    def get_item_limits(self, item: str) -> tuple[Optional[int], Optional[int]]:
        """Получить норму и критический минимум товара (норма, крит_мин)."""
        pass

    @abc.abstractmethod
    def upsert_reorder_open(self, item: str, *, qty_now: int, norm: int, crit_min: int) -> None:
        """Создать или обновить открытый заказ на переказ."""
        pass

    @abc.abstractmethod
    def get_open_reorder(self, item: str):
        """Получить открытый заказ на переказ товара."""
        pass

    @abc.abstractmethod
    def get_item_photo(self, item: str) -> Optional[str]:
        """Получить file_id фото товара."""
        pass

    @abc.abstractmethod
    def set_item_photo(self, item: str, photo_file_id: str) -> None:
        """Установить фото для товара."""
        pass


class GoogleSheetsInventoryRepository(InventoryRepository):
    """
    Реализация репозитория для Google Sheets.
    Оборачивает существующий StoragePort (GoogleSheetsStorage).
    """

    def __init__(self, storage_port):
        """
        Args:
            storage_port: Экземпляр GoogleSheetsStorage, реализующий StoragePort
        """
        self.storage = storage_port

    def get_item(self, name: str) -> Optional[Item]:
        return self.storage.get_item(name)

    def list_items(self, *, active_only: bool = True) -> list[Item]:
        return self.storage.list_items(active_only=active_only)

    def list_active_items(self) -> list[Item]:
        return self.storage.list_active_items()

    def list_stock(self) -> list[StockEntry]:
        return self.storage.list_stock()

    def add_or_update_item(
        self,
        name: str,
        *,
        norm: int,
        crit_min: int,
        qty: int,
        is_active: bool = True,
        photo_file_id: Optional[str] = None,
    ) -> None:
        return self.storage.add_item(
            name,
            norm=norm,
            crit_min=crit_min,
            qty=qty,
            is_active=is_active,
            photo_file_id=photo_file_id,
        )

    def deactivate_item(self, name: str) -> None:
        return self.storage.deactivate_item(name)

    def add_inbound(self, item: str, quantity: int, user_id: int, op_id: Optional[str] = None) -> int:
        return self.storage.add_inbound(item, quantity, user_id, op_id)

    def add_outbound(self, item: str, quantity: int, user_id: int, op_id: Optional[str] = None) -> int:
        return self.storage.add_outbound(item, quantity, user_id, op_id)

    def get_stock(self, item: str) -> int:
        return self.storage.get_stock(item)

    def get_item_limits(self, item: str) -> tuple[Optional[int], Optional[int]]:
        return self.storage.get_item_limits(item)

    def upsert_reorder_open(self, item: str, *, qty_now: int, norm: int, crit_min: int) -> None:
        return self.storage.upsert_reorder_open(item, qty_now=qty_now, norm=norm, crit_min=crit_min)

    def get_open_reorder(self, item: str):
        return self.storage.get_open_reorder(item)

    def get_item_photo(self, item: str) -> Optional[str]:
        return self.storage.get_item_photo(item)

    def set_item_photo(self, item: str, photo_file_id: str) -> None:
        return self.storage.set_item_photo(item, photo_file_id)
