import asyncio
import logging
import os
import sys
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.handlers import start, catalog, faq, contact, order, admin, repeat_order, waitlist, edit_product, broadcast, review, ai_chat
from bot.scheduler import setup_scheduler
from database.init_db import create_tables

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Логування у файл і консоль
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)


async def main():
    # Ініціалізація БД при старті
    await create_tables()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # Підключення роутерів
    dp.include_router(start.router)
    dp.include_router(catalog.router)
    dp.include_router(faq.router)
    dp.include_router(contact.router)
    dp.include_router(order.router)
    dp.include_router(admin.router)
    dp.include_router(repeat_order.router)
    dp.include_router(waitlist.router)
    dp.include_router(edit_product.router)
    dp.include_router(broadcast.router)
    dp.include_router(review.router)
    dp.include_router(ai_chat.router)  # останній — ловить все що не підійшло іншим

    # Запустити планувальник
    scheduler = setup_scheduler(bot)
    scheduler.start()
    logger.info("Планувальник запущено.")

    logger.info("Бот запускається...")
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
