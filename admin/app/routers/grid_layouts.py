"""表格布局：每个用户、每个表格（grid_key）一份，设置菜单「保存布局 / 恢复布局」用。只能看到和改自己的。响应 {code, data, msg}。"""
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_user
from ..models import GridLayout

router = APIRouter(prefix="/api/v1/grid-layouts")

MAX_JSON = 200000  # 布局内容的体积上限，防止塞大对象


def ok(data=None):
    return {"code": 0, "data": data, "msg": "ok"}


def _valid_grid_key(key: str) -> str:
    key = (key or "").strip()
    if not key or len(key) > 100:
        raise HTTPException(400, "表格标识不合法")
    return key


@router.get("")
def get_layout(grid_key: str, user: dict = Depends(require_user), db: Session = Depends(get_db)):
    row = db.scalar(select(GridLayout).where(GridLayout.user_id == user["id"], GridLayout.grid_key == _valid_grid_key(grid_key)))
    return ok({"layout": row.layout} if row else None)


@router.post("")
def save_layout(body: dict, user: dict = Depends(require_user), db: Session = Depends(get_db)):
    """覆盖保存。body: {grid_key, layout: {state, editMode}}；state 是 DevExtreme 表格状态（不含筛选/选中），editMode 可为 null"""
    key = _valid_grid_key(body.get("grid_key"))
    layout = body.get("layout")
    if not isinstance(layout, dict) or not isinstance(layout.get("state") or {}, dict) or not layout.get("state"):
        raise HTTPException(400, "布局内容不合法")
    if "editMode" in layout and layout["editMode"] is not None and not isinstance(layout["editMode"], str):
        raise HTTPException(400, "布局内容不合法")
    if len(json.dumps(layout, ensure_ascii=False)) > MAX_JSON:
        raise HTTPException(400, "布局内容过大")
    row = db.scalar(select(GridLayout).where(GridLayout.user_id == user["id"], GridLayout.grid_key == key))
    if row is None:
        db.add(GridLayout(user_id=user["id"], grid_key=key, layout=layout))
    else:
        row.layout = layout
    db.commit()
    return ok()
