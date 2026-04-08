"""Хендлер перевірки статусу замовлення клієнтом."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.database import get_connection
from db import models
from keyboards.main_menu import BTN_STATUS
from keyboards.order_kb import cancel_active_order_keyboard

router = Router()

STATUS_LABELS = {
    "pending":     "⏳ Очікує підтвердження",
    "confirmed":   "✅ Підтверджено — менеджер скоро зв'яжеться",
    "in_progress": "🔄 В обробці",
    "done":        "✔️ Виконано",
    "cancelled":   "❌ Скасовано",
}


def _order_card(order: dict) -> str:
    status = STATUS_LABELS.get(order["status"], order["status"])
    return (
        f"📋 <b>Заявка #{order['id']}</b>\n"
        f"Статус: {status}\n"
        f"Дата: {order['created_at'][:16].replace('T', ' ')}"
    )


@router.message(lambda m: m.text == BTN_STATUS)
async def show_status(message: Message) -> None:
    async with get_connection() as db:
        orders = await models.get_client_orders(db, message.from_user.id)

    if not orders:
        await message.answer("У вас ще немає замовлень.")
        return

    # Показуємо останні 5 замовлень
    for order in orders[:5]:
        kb = None
        if order["status"] in ("pending", "confirmed"):
            kb = cancel_active_order_keyboard(order["id"])
        await message.answer(
            _order_card(order), parse_mode="HTML", reply_markup=kb
        )
