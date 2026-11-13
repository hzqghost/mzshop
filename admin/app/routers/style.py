"""Grid / Form 样式配置接口。只要求登录，每个人只能改自己的。响应 {code, data, msg}。"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import style_store
from ..db import get_db
from ..deps import require_user
from ..ui_style import KINDS

router = APIRouter(prefix="/api/v1/ui-style")


def _kind(kind: str) -> str:
    if kind not in KINDS:
        raise HTTPException(404, "未知的样式类型")
    return kind


@router.post("/{kind}/save")
def save(kind: str, body: dict[str, Any], user: dict = Depends(require_user), db: Session = Depends(get_db)):
    values = body.get("values")
    if not isinstance(values, dict):
        raise HTTPException(400, "参数不合法")
    try:
        data = style_store.save(db, user["id"], _kind(kind), values)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"code": 0, "data": data, "msg": "ok"}


@router.post("/{kind}/reset")
def reset(kind: str, user: dict = Depends(require_user), db: Session = Depends(get_db)):
    return {"code": 0, "data": style_store.reset(db, user["id"], _kind(kind)), "msg": "ok"}
