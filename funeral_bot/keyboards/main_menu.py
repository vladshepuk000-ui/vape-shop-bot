"""Головне меню бота."""
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# Кнопки головного меню
BTN_EMERGENCY   = "🆘 Потрібна допомога прямо зараз"
BTN_CATALOG     = "⚰️ Послуги поховання"
BTN_PACKAGES    = "🪨 Виготовлення памятників"
BTN_ORDER       = "🔧 Встановлення памятників"
BTN_STATUS      = "🔍 Статус замовлення"
BTN_CONTACTS    = "📍 Контакти"

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_EMERGENCY)],
        [KeyboardButton(text=BTN_CATALOG), KeyboardButton(text=BTN_PACKAGES)],
        [KeyboardButton(text=BTN_ORDER)],
        [KeyboardButton(text=BTN_STATUS)],
        [KeyboardButton(text=BTN_CONTACTS)],
    ],
    resize_keyboard=True,
    input_field_placeholder="Оберіть дію",
)
