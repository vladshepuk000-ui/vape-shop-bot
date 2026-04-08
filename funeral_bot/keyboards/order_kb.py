"""Клавіатури для процесу оформлення замовлення."""
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def consent_keyboard() -> InlineKeyboardMarkup:
    """Кнопки підтвердження згоди на обробку персональних даних."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Погоджуюсь", callback_data="consent:accept")
    builder.button(text="❌ Відмовляюсь", callback_data="consent:decline")
    builder.adjust(2)
    return builder.as_markup()


def confirmation_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Кнопки підтвердження або скасування заявки перед відправкою."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Підтвердити", callback_data=f"confirm_order:{order_id}")
    builder.button(text="❌ Скасувати", callback_data=f"cancel_order:{order_id}")
    builder.adjust(2)
    return builder.as_markup()


def cancel_active_order_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Кнопка скасування вже відправленої заявки (до дзвінка менеджера)."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🚫 Скасувати заявку", callback_data=f"cancel_order:{order_id}")
    builder.adjust(1)
    return builder.as_markup()
