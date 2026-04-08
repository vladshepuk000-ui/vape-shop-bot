"""Тест регресії: кнопки меню під час FSM-форми замовлення.

Баг 1: користувач у стані waiting_for_phone натискав кнопку каталогу —
отримував помилку валідації номера телефону замість переходу в каталог.

Баг 2: якщо переривали на кроці підтвердження — замовлення залишалось
у БД зі статусом pending (фантомний запис).

Фікс: interrupt_order_with_menu очищає стан та скасовує pending-замовлення.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

from db.database import _SCHEMA
from db import models
from states.order_states import OrderForm
from keyboards.main_menu import (
    BTN_CATALOG, BTN_PACKAGES, BTN_ORDER, BTN_STATUS, BTN_EMERGENCY,
)
from handlers.order import PHONE_RE, _MENU_BUTTONS, interrupt_order_with_menu


# ---------------------------------------------------------------------------
# Допоміжні функції
# ---------------------------------------------------------------------------

def _make_state(storage: MemoryStorage, user_id: int = 1) -> FSMContext:
    key = StorageKey(bot_id=0, chat_id=user_id, user_id=user_id)
    return FSMContext(storage=storage, key=key)


def _make_message(text: str, user_id: int = 1) -> MagicMock:
    msg = MagicMock()
    msg.text = text
    msg.from_user = MagicMock()
    msg.from_user.id = user_id
    msg.answer = AsyncMock()
    return msg


# ---------------------------------------------------------------------------
# Тест: _MENU_BUTTONS містить усі кнопки головного меню
# ---------------------------------------------------------------------------

def test_menu_buttons_set_is_complete():
    assert BTN_CATALOG  in _MENU_BUTTONS
    assert BTN_PACKAGES in _MENU_BUTTONS
    assert BTN_ORDER    in _MENU_BUTTONS
    assert BTN_STATUS   in _MENU_BUTTONS
    assert BTN_EMERGENCY in _MENU_BUTTONS


# ---------------------------------------------------------------------------
# Тест: interrupt_order_with_menu очищає стан і відповідає користувачу
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("btn_text", [
    BTN_CATALOG,
    BTN_PACKAGES,
    BTN_EMERGENCY,
    BTN_STATUS,
])
async def test_interrupt_clears_state_for_menu_buttons(btn_text):
    storage = MemoryStorage()
    state = _make_state(storage)

    # Ставимо FSM у стан waiting_for_phone
    await state.set_state(OrderForm.waiting_for_phone)
    await state.update_data(client_name="Тест", service_id=1)

    msg = _make_message(btn_text)
    await interrupt_order_with_menu(msg, state)

    # Стан має бути очищений
    current_state = await state.get_state()
    assert current_state is None, f"Стан не очищено при кнопці {btn_text!r}"

    # Дані FSM теж мають бути стерті
    data = await state.get_data()
    assert data == {}, "FSM-дані не очищено"

    # Бот має відповісти користувачу
    msg.answer.assert_called_once()


@pytest.mark.asyncio
async def test_interrupt_works_from_any_fsm_state():
    """Перерва спрацьовує з будь-якого кроку форми."""
    storage = MemoryStorage()

    for fsm_state in [
        OrderForm.waiting_for_consent,
        OrderForm.waiting_for_name,
        OrderForm.waiting_for_phone,
        OrderForm.waiting_for_city,
        OrderForm.waiting_for_confirmation,
    ]:
        state = _make_state(storage, user_id=fsm_state.state.__hash__() % 10000)
        await state.set_state(fsm_state)

        msg = _make_message(BTN_CATALOG)
        await interrupt_order_with_menu(msg, state)

        current = await state.get_state()
        assert current is None, f"Стан {fsm_state} не очищено"


# ---------------------------------------------------------------------------
# Регресія: до фікса process_phone отримував текст кнопки і падав з помилкою
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("btn_text", [
    BTN_CATALOG, BTN_PACKAGES, BTN_EMERGENCY, BTN_STATUS, BTN_ORDER,
])
def test_menu_button_texts_fail_phone_regex(btn_text):
    """Текст кнопок меню не є валідним номером.

    До фікса: process_phone ловив ці повідомлення і виводив помилку формату.
    Після фікса: interrupt_order_with_menu перехоплює їх першим.
    Цей тест документує, що кнопки дійсно не є номерами — бот мав реагувати
    не помилкою номера, а скасуванням форми.
    """
    phone = btn_text.strip().replace(" ", "").replace("-", "")
    assert not PHONE_RE.match(phone), (
        f"Текст кнопки {btn_text!r} не повинен проходити як номер телефону"
    )


# ---------------------------------------------------------------------------
# Баг 2: фантомне pending-замовлення при перериванні на кроці підтвердження
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_interrupt_at_confirmation_cancels_pending_order():
    """Якщо перервати на waiting_for_confirmation — pending-замовлення скасовується."""
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        await conn.executescript(_SCHEMA)
        await conn.commit()

        uid = 7001
        await models.get_or_create_client(conn, uid)
        await models.set_consent(conn, uid)
        order_id = await models.create_order(
            conn, client_id=uid,
            client_name="Тест", client_phone="0501234567", client_city="Київ",
        )
        # Переконуємось, що заявка pending
        order = await models.get_order(conn, order_id)
        assert order["status"] == "pending"

        # Мокаємо get_connection щоб хендлер використав нашу in-memory БД
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def fake_get_connection():
            yield conn

        storage = MemoryStorage()
        state = _make_state(storage, user_id=uid)
        await state.set_state(OrderForm.waiting_for_confirmation)
        await state.update_data(order_id=order_id)

        msg = _make_message(BTN_CATALOG, user_id=uid)

        with patch("handlers.order.get_connection", fake_get_connection):
            await interrupt_order_with_menu(msg, state)

        # FSM очищено
        assert await state.get_state() is None

        # Замовлення скасовано в БД
        order = await models.get_order(conn, order_id)
        assert order["status"] == "cancelled", (
            f"Очікувався статус 'cancelled', отримано '{order['status']}'"
        )


@pytest.mark.asyncio
async def test_interrupt_without_order_id_does_not_crash():
    """Перерва на ранньому кроці (без order_id в FSM) — без помилок."""
    storage = MemoryStorage()
    state = _make_state(storage, user_id=8001)
    await state.set_state(OrderForm.waiting_for_name)
    # order_id відсутній у даних

    msg = _make_message(BTN_CATALOG, user_id=8001)
    await interrupt_order_with_menu(msg, state)  # не має кидати виключення

    assert await state.get_state() is None
