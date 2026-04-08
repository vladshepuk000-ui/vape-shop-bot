"""Екстрена кнопка — пріоритетний запит на терміновий дзвінок."""
import logging

from aiogram import Router, Bot
from aiogram.types import Message

from keyboards.main_menu import BTN_EMERGENCY
from config import settings

logger = logging.getLogger(__name__)
router = Router()

CLIENT_RESPONSE = (
    "🆘 Ваш запит отримано!\n\n"
    "Менеджер зв'яжеться з вами найближчим часом.\n"
    "Якщо не можете чекати — телефонуйте: {phone}"
)

MANAGER_ALERT = (
    "⚠️ ТЕРМІНОВИЙ ЗАПИТ ⚠️\n\n"
    "Клієнт: {full_name}\n"
    "Username: @{username}\n"
    "Telegram ID: {user_id}\n\n"
    "Потрібен ТЕРМІНОВИЙ дзвінок!"
)


@router.message(lambda m: m.text == BTN_EMERGENCY)
async def handle_emergency(message: Message, bot: Bot) -> None:
    user = message.from_user
    username = user.username or "—"

    # Намагаємось сповістити менеджера, але відповідаємо клієнту в будь-якому разі
    manager_chat_id = settings.MANAGER_CHAT_ID
    if manager_chat_id:
        try:
            await bot.send_message(
                chat_id=int(manager_chat_id),
                text=MANAGER_ALERT.format(
                    full_name=user.full_name,
                    username=username,
                    user_id=user.id,
                ),
            )
            logger.warning("EMERGENCY від user_id=%d — менеджера сповіщено", user.id)
        except Exception as e:
            # Не блокуємо відповідь клієнту якщо чат менеджера недоступний
            logger.error(
                "EMERGENCY від user_id=%d — не вдалося надіслати менеджеру: %s",
                user.id, e,
            )
    else:
        logger.error(
            "EMERGENCY від user_id=%d — MANAGER_CHAT_ID не налаштований у .env",
            user.id,
        )

    # Клієнт завжди отримує відповідь
    await message.answer(
        CLIENT_RESPONSE.format(phone=settings.AGENCY_PHONE or "—")
    )
