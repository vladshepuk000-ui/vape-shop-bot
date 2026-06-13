import os
import asyncpg
from fastapi import Cookie
from typing import Optional

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:jHInKjjHzgONUJeWLNNkoxIumLhqIjIs@tramway.proxy.rlwy.net:56512/railway"
)


async def verify_session(session: Optional[str] = Cookie(default=None)) -> bool:
    if not session:
        return False
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        row = await conn.fetchrow(
            "SELECT token FROM sessions WHERE token = $1 AND expires_at > NOW()",
            session
        )
        return row is not None
    finally:
        await conn.close()


async def get_current_shop_id(session: Optional[str] = Cookie(default=None)) -> Optional[int]:
    if not session:
        return None
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        row = await conn.fetchrow(
            "SELECT shop_owner_id FROM sessions WHERE token = $1 AND expires_at > NOW()",
            session
        )
        return row["shop_owner_id"] if row else None
    finally:
        await conn.close()
