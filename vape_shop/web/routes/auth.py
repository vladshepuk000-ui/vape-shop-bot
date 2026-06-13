import os
import secrets
import asyncpg
import aiohttp
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
templates = Jinja2Templates(directory=BASE_DIR)

router = APIRouter()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:jHInKjjHzgONUJeWLNNkoxIumLhqIjIs@tramway.proxy.rlwy.net:56512/railway"
)
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")


async def send_otp_email(email: str, code: str) -> bool:
    if not RESEND_API_KEY:
        return False
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            json={
                "from": "Vape Shop Admin <onboarding@resend.dev>",
                "to": [email],
                "subject": "Код для входу в адмін-панель",
                "html": f"""
                <div style="font-family:sans-serif;max-width:400px;margin:0 auto;padding:32px">
                    <h2 style="color:#1a1a2e">Вхід в адмін-панель</h2>
                    <p style="color:#6b7280">Твій одноразовий код:</p>
                    <div style="background:#f3f4f6;border-radius:12px;padding:24px;text-align:center;margin:16px 0">
                        <span style="font-size:36px;font-weight:700;letter-spacing:8px;color:#1a1a2e">{code}</span>
                    </div>
                    <p style="color:#9ca3af;font-size:13px">Код дійсний 10 хвилин. Якщо ти не запитував — просто ігноруй цей лист.</p>
                </div>
                """,
            },
        ) as resp:
            return resp.status == 200


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {
        "step": "email", "error": None, "email": ""
    })


@router.post("/login/send-code")
async def send_code(request: Request, email: str = Form(...)):
    email = email.lower().strip()

    # Дозволяємо вхід тільки адмін-email якщо він заданий
    if ADMIN_EMAIL and email != ADMIN_EMAIL.lower().strip():
        return templates.TemplateResponse(request, "login.html", {
            "step": "email",
            "error": "Цей email не має доступу до панелі",
            "email": email,
        })

    code = str(secrets.randbelow(900000) + 100000)
    expires = datetime.utcnow() + timedelta(minutes=10)

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            "INSERT INTO shop_owners (email) VALUES ($1) ON CONFLICT (email) DO NOTHING",
            email
        )
        await conn.execute(
            "UPDATE otp_codes SET used = TRUE WHERE email = $1 AND used = FALSE",
            email
        )
        await conn.execute(
            "INSERT INTO otp_codes (email, code, expires_at) VALUES ($1, $2, $3)",
            email, code, expires
        )
    finally:
        await conn.close()

    sent = await send_otp_email(email, code)
    if not sent:
        return templates.TemplateResponse(request, "login.html", {
            "step": "email",
            "error": "Не вдалося відправити листа. Перевір RESEND_API_KEY в налаштуваннях.",
            "email": email,
        })

    return templates.TemplateResponse(request, "login.html", {
        "step": "code", "error": None, "email": email
    })


@router.post("/login/verify-code")
async def verify_code(request: Request, email: str = Form(...), code: str = Form(...)):
    email = email.lower().strip()
    code = code.strip()

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        row = await conn.fetchrow(
            """SELECT id FROM otp_codes
               WHERE email = $1 AND code = $2 AND used = FALSE AND expires_at > NOW()
               ORDER BY id DESC LIMIT 1""",
            email, code
        )
        if not row:
            return templates.TemplateResponse(request, "login.html", {
                "step": "code",
                "error": "Невірний або застарілий код. Спробуй ще раз.",
                "email": email,
            })

        await conn.execute("UPDATE otp_codes SET used = TRUE WHERE id = $1", row["id"])
        owner = await conn.fetchrow("SELECT id FROM shop_owners WHERE email = $1", email)

        token = secrets.token_hex(32)
        expires = datetime.utcnow() + timedelta(days=7)
        await conn.execute(
            "INSERT INTO sessions (token, shop_owner_id, expires_at) VALUES ($1, $2, $3)",
            token, owner["id"], expires
        )
    finally:
        await conn.close()

    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie("session", token, httponly=True, max_age=86400 * 7, samesite="lax")
    return response


@router.get("/logout")
async def logout(request: Request):
    session = request.cookies.get("session")
    if session:
        conn = await asyncpg.connect(DATABASE_URL)
        try:
            await conn.execute("DELETE FROM sessions WHERE token = $1", session)
        finally:
            await conn.close()
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session")
    return response
