"""Точка входу — запуск бота."""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import settings
from db.database import init_db
from handlers import start, emergency, catalog, order, status, contacts

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    # Ініціалізація БД (створення таблиць)
    await init_db()
    logger.info("База даних ініціалізована.")

    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Реєстрація роутерів у порядку пріоритету
    dp.include_router(start.router)
    dp.include_router(emergency.router)
    dp.include_router(order.router)      # order раніше catalog, щоб callback order_* мали пріоритет
    dp.include_router(catalog.router)
    dp.include_router(status.router)
    dp.include_router(contacts.router)

    logger.info("Бот запускається...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        logger.info("Бот зупинено.")


if __name__ == "__main__":
    asyncio.run(main())
