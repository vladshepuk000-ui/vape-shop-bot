"""Хендлер кнопки «Контакти»."""
from aiogram import Router, F
from aiogram.types import Message

from config import settings
from keyboards.main_menu import BTN_CONTACTS

router = Router()


@router.message(F.text == BTN_CONTACTS)
async def show_contacts(message: Message) -> None:
    lines = ["📋 <b>Наші контакти</b>\n"]

    if settings.AGENCY_PHONE:
        lines.append(f"📞 Телефон: {settings.AGENCY_PHONE}")
    if settings.AGENCY_ADDRESS:
        lines.append(f"📍 Адреса: {settings.AGENCY_ADDRESS}")

    lines.append("\n🕐 Години роботи: цілодобово, 7 днів на тиждень")

    await message.answer("\n".join(lines), parse_mode="HTML")
