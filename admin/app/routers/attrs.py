"""系统通用属性：属性类型、属性值。响应 {code, data, msg}。"""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..attr_dict import (
    CURRENCY_CODE, apply_type, apply_value, assert_value_deletable, enabled_codes, fail, option_dict, type_dict, value_dict,
)
from ..db import get_db
from ..deps import require_user
from ..models import SysAttrType, SysAttrValue

router = APIRouter(prefix="/api/v1/attrs", dependencies=[Depends(require_user)])


def ok(data=None):
    return {"code": 0, "data": data, "msg": "ok"}


def _counts(db: Session) -> dict[int, int]:
    return dict(db.execute(select(SysAttrValue.type_id, func.count()).group_by(SysAttrValue.type_id)).all())


@router.get("/types")
def list_types(db: Session = Depends(get_db)):
    counts = _counts(db)
    rows = db.scalars(select(SysAttrType).order_by(SysAttrType.sort_order, SysAttrType.id))
    return ok([type_dict(row, counts.get(row.id, 0)) for row in rows])


@router.post("/types")
def create_type(values: dict, db: Session = Depends(get_db)):
    row = SysAttrType()
    apply_type(db, row, values, True)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fail("标识码已存在")
    db.refresh(row)
    return ok(type_dict(row, 0))


@router.put("/types/{tid}")
def update_type(tid: int, values: dict, db: Session = Depends(get_db)):
    row = db.get(SysAttrType, tid) or fail("属性类型不存在", 404)
    apply_type(db, row, values, False)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fail("标识码已存在")
    db.refresh(row)
    return ok(type_dict(row, _counts(db).get(row.id, 0)))


@router.delete("/types/{tid}")
def delete_type(tid: int, db: Session = Depends(get_db)):
    row = db.get(SysAttrType, tid) or fail("属性类型不存在", 404)
    used = db.scalar(select(func.count()).where(SysAttrValue.type_id == tid)) or 0
    if used:
        fail("该类型下还有属性值，不能删除")
    if row.code == CURRENCY_CODE:
        fail("币种是系统预置类型，不能删除")
    db.delete(row)
    db.commit()
    return ok()


@router.get("/values")
def list_values(type_id: int, db: Session = Depends(get_db)):
    db.get(SysAttrType, type_id) or fail("属性类型不存在", 404)
    rows = db.scalars(select(SysAttrValue).where(SysAttrValue.type_id == type_id)
                      .order_by(SysAttrValue.sort_order, SysAttrValue.id))
    return ok([value_dict(row) for row in rows])


@router.post("/values")
def create_value(values: dict, db: Session = Depends(get_db)):
    row = SysAttrValue()
    apply_value(db, row, values, True)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fail("编码已存在")
    db.refresh(row)
    return ok(value_dict(row))


@router.put("/values/{vid}")
def update_value(vid: int, values: dict, db: Session = Depends(get_db)):
    row = db.get(SysAttrValue, vid) or fail("属性值不存在", 404)
    apply_value(db, row, values, False)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fail("编码已存在")
    db.refresh(row)
    return ok(value_dict(row))


@router.delete("/values/{vid}")
def delete_value(vid: int, db: Session = Depends(get_db)):
    row = db.get(SysAttrValue, vid) or fail("属性值不存在", 404)
    assert_value_deletable(db, row)
    db.delete(row)
    db.commit()
    return ok()


@router.get("/options")
def list_options(code: str, db: Session = Depends(get_db)):
    """某个类型下启用的取值，供业务下拉。币种用 code 作为选项值。"""
    type_id = db.scalar(select(SysAttrType.id).where(SysAttrType.code == code.strip()))
    if not type_id:
        return ok([])
    rows = db.scalars(select(SysAttrValue).where(SysAttrValue.type_id == type_id, SysAttrValue.status == 1)
                      .order_by(SysAttrValue.sort_order, SysAttrValue.id))
    data = [option_dict(row) for row in rows]
    if code.strip() == CURRENCY_CODE:
        data = [item for item in data if item["code"] and item["code"] in enabled_codes(db, CURRENCY_CODE)]
    return ok(data)
