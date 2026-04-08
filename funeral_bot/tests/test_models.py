"""Тести CRUD-функцій бази даних."""
import pytest
from db import models


# ---------------------------------------------------------------------------
# Клієнти та згода
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_new_client(db):
    client = await models.get_or_create_client(db, telegram_id=111)
    assert client["telegram_id"] == 111
    assert client["consent_given"] == 0


@pytest.mark.asyncio
async def test_get_existing_client(db):
    await models.get_or_create_client(db, telegram_id=222)
    client = await models.get_or_create_client(db, telegram_id=222)
    assert client["telegram_id"] == 222  # без дублювання


@pytest.mark.asyncio
async def test_consent_false_by_default(db):
    await models.get_or_create_client(db, telegram_id=333)
    assert not await models.has_consent(db, 333)


@pytest.mark.asyncio
async def test_set_and_check_consent(db):
    await models.get_or_create_client(db, telegram_id=444)
    await models.set_consent(db, 444)
    assert await models.has_consent(db, 444)


@pytest.mark.asyncio
async def test_has_consent_unknown_user(db):
    """Користувач без запису в БД — згоди немає."""
    assert not await models.has_consent(db, 99999)


# ---------------------------------------------------------------------------
# Замовлення
# ---------------------------------------------------------------------------

@pytest.fixture
async def client_with_consent(db):
    await models.get_or_create_client(db, telegram_id=555)
    await models.set_consent(db, 555)
    return 555


@pytest.mark.asyncio
async def test_create_and_get_order(db, client_with_consent):
    uid = client_with_consent
    order_id = await models.create_order(
        db,
        client_id=uid,
        client_name="Тест Тестович",
        client_phone="+380501234567",
        client_city="Київ",
    )
    assert isinstance(order_id, int)
    order = await models.get_order(db, order_id)
    assert order["client_id"] == uid
    assert order["status"] == "pending"


@pytest.mark.asyncio
async def test_update_order_status(db, client_with_consent):
    uid = client_with_consent
    order_id = await models.create_order(
        db, client_id=uid,
        client_name="Тест", client_phone="0501234567", client_city="Львів",
    )
    await models.update_order_status(db, order_id, "confirmed")
    order = await models.get_order(db, order_id)
    assert order["status"] == "confirmed"


@pytest.mark.asyncio
async def test_cancel_order_by_owner(db, client_with_consent):
    uid = client_with_consent
    order_id = await models.create_order(
        db, client_id=uid,
        client_name="Тест", client_phone="0501234567", client_city="Одеса",
    )
    await models.update_order_status(db, order_id, "confirmed")
    result = await models.cancel_order(db, order_id, uid)
    assert result is True
    order = await models.get_order(db, order_id)
    assert order["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_order_by_stranger(db, client_with_consent):
    """Чужий користувач не може скасувати замовлення."""
    uid = client_with_consent
    order_id = await models.create_order(
        db, client_id=uid,
        client_name="Тест", client_phone="0501234567", client_city="Харків",
    )
    await models.update_order_status(db, order_id, "confirmed")
    stranger_id = 99999
    result = await models.cancel_order(db, order_id, stranger_id)
    assert result is False
    order = await models.get_order(db, order_id)
    assert order["status"] == "confirmed"  # не змінився


@pytest.mark.asyncio
async def test_get_client_orders_returns_own_only(db):
    """Клієнт бачить лише свої замовлення."""
    await models.get_or_create_client(db, telegram_id=601)
    await models.get_or_create_client(db, telegram_id=602)
    await models.set_consent(db, 601)
    await models.set_consent(db, 602)

    await models.create_order(db, client_id=601, client_name="А", client_phone="0501111111", client_city="Київ")
    await models.create_order(db, client_id=602, client_name="Б", client_phone="0502222222", client_city="Львів")

    orders_601 = await models.get_client_orders(db, 601)
    assert len(orders_601) == 1
    assert orders_601[0]["client_id"] == 601
