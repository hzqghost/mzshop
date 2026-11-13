"""样式配置的读写（表 sys_ui_style，每个用户每种配置一行，data 存 JSON）。"""
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import UiStyle
from .ui_style import KINDS


def load(db: Session, user_id: int | None, kind: str) -> dict[str, Any]:
    spec = KINDS[kind]
    if user_id is None:
        return dict(spec.defaults)
    row = db.scalar(select(UiStyle).where(UiStyle.user_id == user_id, UiStyle.kind == kind))
    return spec.merge(row.data if row and isinstance(row.data, dict) else {})


def save(db: Session, user_id: int, kind: str, values: dict[str, Any]) -> dict[str, Any]:
    """传入的项覆盖原值，没传的保持原值；未知项或非法值抛 ValueError。"""
    spec = KINDS[kind]
    merged = load(db, user_id, kind)
    for key, value in values.items():
        if key not in spec.defaults:
            raise ValueError(f"未知的配置项：{key}")
        if not spec.valid(key, value):
            raise ValueError(f"配置值不合法：{key}")
        merged[key] = value
    row = db.scalar(select(UiStyle).where(UiStyle.user_id == user_id, UiStyle.kind == kind))
    if row is None:
        db.add(UiStyle(user_id=user_id, kind=kind, data=merged))
    else:
        row.data = merged
    db.commit()
    return merged


def reset(db: Session, user_id: int, kind: str) -> dict[str, Any]:
    row = db.scalar(select(UiStyle).where(UiStyle.user_id == user_id, UiStyle.kind == kind))
    if row is not None:
        db.delete(row)
        db.commit()
    return dict(KINDS[kind].defaults)


def body_attrs(db: Session, user_id: int | None) -> dict[str, Any]:
    """页面渲染用：当前用户的表格 / 表单样式及 body 上的 class、变量。"""
    grid = load(db, user_id, "grid")
    form = load(db, user_id, "form")
    g, f = KINDS["grid"].body_attrs(grid), KINDS["form"].body_attrs(form)
    return {
        "grid_style": grid,
        "body_class": " ".join(c for c in ("mdm-ui2", g["class"], f["class"]) if c),
        "body_style": ";".join(s for s in (g["style"], f["style"]) if s),
    }
