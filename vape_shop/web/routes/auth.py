import os
import hashlib
from fastapi import APIRouter, Request, Form, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
templates = Jinja2Templates(directory=BASE_DIR)

router = APIRouter()

ADMIN_PASSWORD = os.getenv("ADMIN_WEB_PASSWORD", "admin123")
SESSION_TOKEN = hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest()


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
async def login(request: Request, password: str = Form(default="")):
    if not password:
        return templates.TemplateResponse(request, "login.html", {"error": "Введи пароль"})
    if password == ADMIN_PASSWORD:
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie("session", SESSION_TOKEN, httponly=True, max_age=86400 * 7)
        return response
    return templates.TemplateResponse(request, "login.html", {"error": "Невірний пароль"})


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session")
    return response
