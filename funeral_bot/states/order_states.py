"""FSM-стани для оформлення замовлення."""
from aiogram.fsm.state import State, StatesGroup


class OrderForm(StatesGroup):
    # Крок 1: підтвердження згоди на обробку персональних даних
    waiting_for_consent = State()

    # Кроки збору контактних даних
    waiting_for_name  = State()
    waiting_for_phone = State()
    waiting_for_city  = State()

    # Крок підтвердження перед відправкою
    waiting_for_confirmation = State()
