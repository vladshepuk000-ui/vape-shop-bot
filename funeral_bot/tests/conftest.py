"""Спільні фікстури для тестів."""
import sys
import os

# Додаємо корінь funeral_bot до шляху імпорту
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Підставляємо фейкові змінні середовища до імпорту config
os.environ.setdefault("BOT_TOKEN", "0000000000:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
os.environ.setdefault("MANAGER_CHAT_ID", "-1001234567890")
os.environ.setdefault("ADMIN_IDS", "123456789")
os.environ.setdefault("AGENCY_PHONE", "+380501234567")

import pytest
import aiosqlite
from db.database import _SCHEMA


@pytest.fixture
async def db():
    """In-memory SQLite з повною схемою. Ізольована для кожного тесту."""
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        await conn.executescript(_SCHEMA)
        await conn.commit()
        yield conn
