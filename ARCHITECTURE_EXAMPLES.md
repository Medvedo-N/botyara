"""
ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ НОВОЙ АРХИТЕКТУРЫ

Этот файл содержит примеры того, как использовать новые компоненты:
- InventoryRepository
- DIContainer
- BaseFSMHandler
"""

# ============================================================================
# 1. ИСПОЛЬЗОВАНИЕ INVENTORY REPOSITORY (вместо StoragePort)
# ============================================================================

# Раньше (старый способ с StoragePort):
# from app.storage.sheets import GoogleSheetsStorage
# storage = GoogleSheetsStorage(spreadsheet_id="...")
# item = storage.get_item("Мыло")

# Теперь (новый способ с репозиторием):
from app.storage.repository import GoogleSheetsInventoryRepository
from app.storage.sheets import GoogleSheetsStorage

storage_port = GoogleSheetsStorage(spreadsheet_id="...")
repository = GoogleSheetsInventoryRepository(storage_port)
item = repository.get_item("Мыло")
items = repository.list_active_items()

# ============================================================================
# 2. ИСПОЛЬЗОВАНИЕ DI CONTAINER (вместо context.application.bot_data)
# ============================================================================

# Раньше (теряем типы, IDE не подсказывает):
# inventory_service = context.application.bot_data['inventory_service']
# inventory_service.outbound(...)  # IDE не знает, что такое outbound()

# Теперь (строгая типизация):
from app.di_container import container

inventory_service = container.get_inventory_service()  # IDE знает все методы!
inventory_service.outbound(...)  # автодополнение работает

# В обработчиках:
async def inline_query_handler(update, context):
    # Старый способ:
    # inventory = context.application.bot_data['inventory_service']
    
    # Новый способ:
    inventory = container.get_inventory_service()
    rows = inventory.storage.list_stock()

# ============================================================================
# 3. СОЗДАНИЕ FSM HANDLER ВМЕСТО ОГРОМНОГО if/elif
# ============================================================================

from telegram import Update
from telegram.ext import ContextTypes
from app.bot.fsm.base_handler import BaseFSMHandler
from app.bot.fsm.states import DialogState

class InventoryFSMHandler(BaseFSMHandler):
    """Обработчик FSM для команд работы с товарами."""
    
    async def handle_add_item_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка ввода названия товара."""
        if not update.message or not update.message.text:
            return
        
        text = update.message.text.strip()
        if not text or len(text) > 100:
            await update.message.reply_text("❌ Название должно быть от 1 до 100 символов")
            return
        
        context.user_data['item_name'] = text
        context.user_data['state'] = DialogState.ADD_ITEM_NORM.value
        await update.message.reply_text(f"✅ Товар: {text}\n\nВведите норму остатка:")
    
    async def handle_add_item_norm(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка ввода нормы товара."""
        if not update.message or not update.message.text:
            return
        
        try:
            norm = int(update.message.text.strip())
            if norm <= 0:
                raise ValueError("Норма должна быть больше 0")
        except ValueError:
            raise ValueError("Введите целое положительное число")
        
        context.user_data['item_norm'] = norm
        context.user_data['state'] = DialogState.ADD_ITEM_CRIT.value
        await update.message.reply_text(f"✅ Норма: {norm}\n\nВведите критический минимум:")
    
    async def handle_add_item_crit(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка ввода критического минимума."""
        if not update.message or not update.message.text:
            return
        
        try:
            crit_min = int(update.message.text.strip())
            if crit_min < 0:
                raise ValueError("Критический минимум не может быть отрицательным")
        except ValueError:
            raise ValueError("Введите целое неотрицательное число")
        
        context.user_data['item_crit_min'] = crit_min
        context.user_data['state'] = DialogState.ADD_ITEM_QTY.value
        await update.message.reply_text(f"✅ Критический минимум: {crit_min}\n\nВведите начальное количество:")
    
    async def handle_add_item_qty(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка ввода начального количества товара."""
        if not update.message or not update.message.text:
            return
        
        try:
            qty = int(update.message.text.strip())
            if qty < 0:
                raise ValueError("Количество не может быть отрицательным")
        except ValueError:
            raise ValueError("Введите целое неотрицательное число")
        
        # Сохраняем товар в БД
        inventory = container.get_inventory_service()
        item_name = context.user_data.get('item_name')
        item_norm = context.user_data.get('item_norm', 0)
        item_crit = context.user_data.get('item_crit_min', 0)
        
        inventory.storage.add_item(
            name=item_name,
            norm=item_norm,
            crit_min=item_crit,
            qty=qty,
            is_active=True,
        )
        
        # Выходим из FSM
        context.user_data['state'] = DialogState.IDLE.value
        await update.message.reply_text(
            f"✅ Товар '{item_name}' успешно добавлен!\n"
            f"Количество: {qty}, Норма: {item_norm}, Крит. мин: {item_crit}"
        )
    
    async def handle_error(self, update: Update, context: ContextTypes.DEFAULT_TYPE, exc: Exception) -> None:
        """Централизованная обработка ошибок."""
        if isinstance(exc, ValueError):
            await update.message.reply_text(f"❌ {exc}\n\nПопробуйте ещё раз.")
        else:
            await update.message.reply_text("❌ Произошла ошибка. Попробуйте позже.")


# Регистрируем в router.py:
# from app.bot.fsm.handlers import InventoryFSMHandler
# inventory_fsm = InventoryFSMHandler()
# application.add_handler(MessageHandler(filters.TEXT, inventory_fsm))

# ============================================================================
# 4. ИНИЦИАЛИЗАЦИЯ КОНТЕЙНЕРА В main.py
# ============================================================================

from app.di_container import container

async def application_startup(app):
    """Инициализация при старте приложения."""
    container.set_application_bot(app.bot)
    
    # Теперь все сервисы готовы к использованию
    inventory_service = container.get_inventory_service()
    print(f"✅ Inventory Service initialized")


# ============================================================================
# 5. МИГРАЦИЯ СУЩЕСТВУЮЩИХ HANDLERS
# ============================================================================

# Вместо:
# async def fsm_text_handler(update, context):
#     if state == DialogState.WAITING_STOCK:
#         # обработка 1
#     elif state == DialogState.ADD_ITEM_NAME:
#         # обработка 2
#     elif state == DialogState.ADD_ITEM_NORM:
#         # обработка 3
#     ... (10+ elif)

# Используйте:
# class MyFSMHandler(BaseFSMHandler):
#     async def handle_waiting_stock(self, update, context):
#         # обработка 1
#     
#     async def handle_add_item_name(self, update, context):
#         # обработка 2
#     
#     async def handle_add_item_norm(self, update, context):
#         # обработка 3


# ============================================================================
# 6. ТЕСТИРОВАНИЕ С КОНТЕЙНЕРОМ
# ============================================================================

# Для тестов можно переопределить контейнер:
# from app.di_container import DIContainer, container
# 
# def test_inventory_service():
#     # Используем тестовый контейнер
#     test_container = DIContainer()
#     test_container.set_application_bot(MockBot())
#     
#     # Или сбросить кеш:
#     container.reset()
#     
#     # Теперь получаем сервис с нуля
#     service = container.get_inventory_service()
#     assert service is not None
