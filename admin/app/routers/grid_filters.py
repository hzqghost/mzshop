"""表格过滤器模板：每个用户、每个表格（grid_key）下的命名过滤器。只能看到和改自己的。响应 {code, data, msg}。"""
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_user
from ..models import GridFilter

router = APIRouter(prefix="/api/v1/grid-filters")

MAX_PER_GRID = 50
MAX_JSON = 20000  # 过滤器表达式的体积上限，防止塞大对象


def ok(data=None):
    return {"code": 0, "data": data, "msg": "ok"}


def _dict(f: GridFilter) -> dict:
    return {"id": f.id, "name": f.name, "filter_value": f.filter_value}


def _valid_grid_key(key: str) -> str:
    key = (key or "").strip()
    if not key or len(key) > 100:
        raise HTTPException(400, "表格标识不合法")
    return key


@router.get("")
def list_templates(grid_key: str, user: dict = Depends(require_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(GridFilter).where(GridFilter.user_id == user["id"], GridFilter.grid_key == _valid_grid_key(grid_key))
                      .order_by(GridFilter.name))
    return ok([_dict(f) for f in rows])


@router.post("")
def save_template(body: dict, user: dict = Depends(require_user), db: Session = Depends(get_db)):
    """同名模板直接覆盖（更新其内容）。body: {grid_key, name, filter_value}"""
    key = _valid_grid_key(body.get("grid_key"))
    name = str(body.get("name") or "").strip()
    if not name or len(name) > 50:
        raise HTTPException(400, "模板名称不能为空且最长 50 个字符")
    value = body.get("filter_value")
    if not isinstance(value, list) or not value:
        raise HTTPException(400, "过滤器内容为空，没有可保存的条件")
    if len(json.dumps(value, ensure_ascii=False)) > MAX_JSON:
        raise HTTPException(400, "过滤器内容过大")
    row = db.scalar(select(GridFilter).where(GridFilter.user_id == user["id"], GridFilter.grid_key == key, GridFilter.name == name))
    if row is None:
        count = len(db.scalars(select(GridFilter.id).where(GridFilter.user_id == user["id"], GridFilter.grid_key == key)).all())
        if count >= MAX_PER_GRID:
            raise HTTPException(400, f"每个表格最多保存 {MAX_PER_GRID} 个模板")
        row = GridFilter(user_id=user["id"], grid_key=key, name=name, filter_value=value)
        db.add(row)
    else:
        row.filter_value = value
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(400, "模板名称已存在")
    return ok(_dict(row))


@router.delete("/{tid}")
def delete_template(tid: int, user: dict = Depends(require_user), db: Session = Depends(get_db)):
    row = db.get(GridFilter, tid)
    if row is None or row.user_id != user["id"]:
        raise HTTPException(404, "模板不存在")
    db.delete(row)
    db.commit()
    return ok()
