from aiogram.fsm.state import State, StatesGroup


class OrderForm(StatesGroup):
    choosing_product   = State()
    choosing_quantity  = State()
    entering_phone     = State()
    choosing_delivery  = State()
    entering_address   = State()
    entering_notes     = State()
    choosing_payment   = State()
    confirmation       = State()
    waiting_screenshot = State()
