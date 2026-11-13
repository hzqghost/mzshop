"""用户 CRUD。响应统一为 {code, data, msg}，code=0 成功（与 dxGrid.js 的约定一致）。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import SUPER_ADMIN
from ..db import get_db
from ..deps import require_user
from ..models import User
from ..security import hash_password

router = APIRouter(prefix="/api/v1/users", dependencies=[Depends(require_user)])

FIELDS = ("username", "real_name", "email", "phone")


def ok(data=None):
    return {"code": 0, "data": data, "msg": "ok"}


def fail(msg: str, status: int = 400):
    raise HTTPException(status_code=status, detail=msg)


def _apply(user: User, values: dict) -> None:
    for f in FIELDS:
        if f in values and values[f] is not None:
            setattr(user, f, str(values[f]).strip())
    if "status" in values:
        user.status = 1 if values["status"] else 0
    if values.get("password"):
        user.password_hash = hash_password(values["password"])


@router.get("")
def list_users(db: Session = Depends(get_db)):
    rows = db.scalars(select(User).order_by(User.id)).all()
    return ok([u.to_dict() for u in rows])


@router.post("")
def create_user(values: dict, db: Session = Depends(get_db)):
    username = str(values.get("username", "")).strip()
    if not username:
        fail("用户名不能为空")
    if username == SUPER_ADMIN["username"]:
        fail("用户名已存在")
    if not values.get("password"):
        fail("密码不能为空")
    user = User(username=username, password_hash="", status=1)
    _apply(user, values)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fail("用户名已存在")
    return ok(user.to_dict())


@router.put("/{user_id}")
def update_user(user_id: int, values: dict, db: Session = Depends(get_db)):
    user = db.get(User, user_id) or fail("用户不存在", 404)
    values.pop("username", None)  # 登录名创建后不可改
    _apply(user, values)
    db.commit()
    return ok(user.to_dict())


@router.delete("/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id) or fail("用户不存在", 404)
    db.delete(user)
    db.commit()
    return ok()
