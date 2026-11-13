import hmac

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import SUPER_ADMIN
from ..db import get_db
from ..models import User
from ..security import verify_password

router = APIRouter()


def _session_user(id_: int, username: str, real_name: str, super_admin: bool) -> dict:
    return {"id": id_, "username": username, "real_name": real_name, "super": super_admin}


@router.post("/login/do")
def do_login(request: Request, username: str = Form(""), password: str = Form(""), db: Session = Depends(get_db)):
    username = username.strip()

    if hmac.compare_digest(username, SUPER_ADMIN["username"]) and hmac.compare_digest(password, SUPER_ADMIN["password"]):
        request.session["user"] = _session_user(SUPER_ADMIN["id"], username, SUPER_ADMIN["real_name"], True)
        return RedirectResponse("/", status_code=303)

    user = db.scalar(select(User).where(User.username == username))
    if user is None or not verify_password(password, user.password_hash):
        return RedirectResponse("/login?error=credentials", status_code=303)
    if not user.status:
        return RedirectResponse("/login?error=disabled", status_code=303)

    request.session["user"] = _session_user(user.id, user.username, user.real_name or user.username, False)
    return RedirectResponse("/", status_code=303)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
