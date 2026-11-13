"""品牌字典：商品库结构化品牌（shop_goods.brand_id / supplier_catalog_item.brand_id 引用）。响应 {code, data, msg}。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_user
from ..models import Brand, ShopGoods, SupplierCatalogItem
from .shop_i18n import load_inline, purge_translations, save_inline

router = APIRouter(prefix="/api/v1/brands", dependencies=[Depends(require_user)])


def ok(data=None):
    return {"code": 0, "data": data, "msg": "ok"}


def fail(msg: str, status: int = 400):
    raise HTTPException(status_code=status, detail=msg)


def _fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def _text(values: dict, f: str, label: str, size: int, required: bool = False) -> str:
    v = str(values.get(f) or "").strip()
    if required and not v:
        fail(f"{label}不能为空")
    if len(v) > size:
        fail(f"{label}最长 {size} 个字符")
    return v


def _usage(db: Session, bid: int) -> tuple[int, int]:
    items = db.scalar(select(func.count()).where(SupplierCatalogItem.brand_id == bid)) or 0
    goods = db.scalar(select(func.count()).where(ShopGoods.brand_id == bid)) or 0
    return int(items), int(goods)


def _brand_dict(db: Session, b: Brand) -> dict:
    items, goods = _usage(db, b.id)
    return {"id": b.id, "name": b.name, "logo_url": b.logo_url, "website": b.website, "remark": b.remark,
            "sort_order": b.sort_order, "status": bool(b.status), "item_count": items, "goods_count": goods,
            "created_at": _fmt(b.created_at), "updated_at": _fmt(b.updated_at)}


def _attach(db: Session, items: list[dict]) -> list[dict]:
    """挂上启用的非默认语言译文 i18n: {语言: {name: 值}}，列表 / 弹窗表单直接绑定。"""
    m = load_inline(db, "brand", [d["id"] for d in items], ["name"])
    for d in items:
        d["i18n"] = m[d["id"]]
    return items


def _apply(db: Session, b: Brand, values: dict, creating: bool) -> None:
    if "name" in values or creating:
        b.name = _text(values, "name", "品牌名称", 100, required=True)
    for f, label, size in (("logo_url", "Logo 地址", 500), ("website", "官网地址", 255), ("remark", "备注", 500)):
        if f in values or creating:
            setattr(b, f, _text(values, f, label, size))
    if b.website and not b.website.lower().startswith(("http://", "https://")):
        fail("官网地址需以 http:// 或 https:// 开头")
    if "sort_order" in values or creating:
        so = int(values.get("sort_order") or 0)
        if so < 0 or so > 999999:
            fail("排序值需在 0~999999 之间")
        b.sort_order = so
    if "status" in values:
        b.status = 1 if values["status"] else 0
    elif creating:
        b.status = 1


def _save(db: Session, b: Brand, values: dict) -> None:
    """flush（检查名称唯一）→ 保存随行品牌译文 → commit；任何一步失败整体回滚。"""
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        fail("品牌名称已存在")
    save_inline(db, "brand", b, values.get("i18n"))
    db.commit()


@router.get("")
def list_brands(db: Session = Depends(get_db)):
    rows = db.scalars(select(Brand).order_by(Brand.sort_order, Brand.id))
    return ok(_attach(db, [_brand_dict(db, b) for b in rows]))


@router.post("")
def create_brand(values: dict, db: Session = Depends(get_db)):
    b = Brand()
    _apply(db, b, values, True)
    db.add(b)
    _save(db, b, values)
    return ok(_attach(db, [_brand_dict(db, b)])[0])


@router.put("/{bid}")
def update_brand(bid: int, values: dict, db: Session = Depends(get_db)):
    b = db.get(Brand, bid) or fail("品牌不存在", 404)
    old_name = b.name
    _apply(db, b, values, False)
    if b.name != old_name:  # 商品里的品牌名是冗余快照，改名后同步，列表按品牌名筛选才一致
        db.execute(update(ShopGoods).where(ShopGoods.brand_id == bid).values(brand=b.name))
    _save(db, b, values)
    return ok(_attach(db, [_brand_dict(db, b)])[0])


@router.delete("/{bid}")
def delete_brand(bid: int, db: Session = Depends(get_db)):
    b = db.get(Brand, bid) or fail("品牌不存在", 404)
    items, goods = _usage(db, bid)
    if items or goods:
        parts = []
        if items:
            parts.append(f"{items} 个目录条目")
        if goods:
            parts.append(f"{goods} 个商品")
        fail(f"该品牌已被 {'、'.join(parts)} 使用，不能删除")
    purge_translations(db, "brand", [bid])
    db.delete(b)
    db.commit()
    return ok()


@router.post("/move")
def move_brand(body: dict, db: Session = Depends(get_db)):
    """拖动排序：把 id 移到 target_id 之前（after=false）或之后（after=true），并把全部品牌的排序值按新顺序重排（10、20、30…）。"""
    bid, tid = body.get("id"), body.get("target_id")
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in (bid, tid)) or bid == tid:
        fail("参数不合法")
    rows = list(db.scalars(select(Brand).order_by(Brand.sort_order, Brand.id)))
    moving = next((r for r in rows if r.id == bid), None)
    if moving is None or not any(r.id == tid for r in rows):
        fail("品牌不存在", 404)
    rows.remove(moving)
    pos = next(i for i, r in enumerate(rows) if r.id == tid)
    rows.insert(pos + 1 if body.get("after") else pos, moving)
    for i, r in enumerate(rows):
        r.sort_order = (i + 1) * 10
    db.commit()
    return ok()
