"""Хендлер /start."""
import logging

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from db.database import get_connection
from db.models import get_or_create_client
from keyboards.main_menu import main_menu
from config import settings

logger = logging.getLogger(__name__)
router = Router()


def _build_welcome_text() -> str:
    lines = [
        "Вітаємо у похоронному агентстві.\n",
        "Ми розуміємо, що ви зараз переживаєте важкий момент. "
        "Наша команда готова допомогти вам із організацією та оформленням усіх необхідних послуг.\n",
    ]
    lines.append("\nОберіть потрібний розділ нижче:")
    return "\n".join(lines)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    try:
        async with get_connection() as db:
            await get_or_create_client(db, message.from_user.id)
    except Exception as e:
        logger.error("DB error on /start for user %d: %s", message.from_user.id, e)

    await message.answer(_build_welcome_text(), reply_markup=main_menu)
    logger.info("Користувач %d: /start", message.from_user.id)
