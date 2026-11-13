from fastapi import Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from . import style_store
from .config import BASE_DIR
from .deps import current_user

templates = Jinja2Templates(directory=BASE_DIR / "templates")


def render_page(request: Request, db: Session, name: str, context: dict | None = None):
    """渲染后台内页：自动带上当前用户的表格 / 表单样式（body 的 class 和变量）。"""
    user = current_user(request)
    ctx = {"user": user, **style_store.body_attrs(db, user["id"] if user else None), **(context or {})}
    return templates.TemplateResponse(request, name, ctx)
