"""销售平台与店铺。店铺的「独立站」不入库，读取时取所属平台。响应 {code, data, msg}。"""
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_user
from ..models import (Platform, ShopCategory, ShopGoodsStore, ShopOrder, ShopifyBundleMap,
                      ShopifyProductMap, ShopifyStoreConfig, ShopifySyncTask, ShopifyVariantMap,
                      ShopifyWebhookEvent, ShippingPackageGroup, Store, StoreCategory)

platform_router = APIRouter(prefix="/api/v1/platforms", dependencies=[Depends(require_user)])
store_router = APIRouter(prefix="/api/v1/stores", dependencies=[Depends(require_user)])


def ok(data=None):
    return {"code": 0, "data": data, "msg": "ok"}


def fail(msg: str, status: int = 400):
    raise HTTPException(status_code=status, detail=msg)


def _fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def _text(values: dict, f: str, label: str, size: int, required: bool = False) -> str:
    v = str(values.get(f) or "").strip()
    if required and not v:
        fail(f"请填写{label}")
    if len(v) > size:
        fail(f"{label}最长 {size} 个字符")
    return v


def _website(values: dict, creating: bool, current: str = "") -> str:
    if "website" not in values and not creating:
        return current
    v = _text(values, "website", "网址", 255)
    if v and not v.lower().startswith(("http://", "https://")):
        fail("网址需以 http:// 或 https:// 开头")
    return v


def _flag(values: dict, creating: bool, current: int = 0) -> int:
    if "is_independent" not in values and not creating:
        return current
    return 1 if values.get("is_independent") else 0


def _platform_dict(p: Platform, store_count: int = 0) -> dict:
    return {
        "id": p.id, "code": p.code, "name": p.name, "name_en": p.name_en, "website": p.website,
        "market": p.market, "feature": p.feature, "remark": p.remark,
        "is_independent": bool(p.is_independent), "store_count": store_count,
        "created_at": _fmt(p.created_at), "updated_at": _fmt(p.updated_at),
    }


def _counts(db: Session) -> dict[int, int]:
    rows = db.execute(select(Store.platform_id, func.count()).group_by(Store.platform_id))
    return {pid: int(n) for pid, n in rows}


def _apply_platform(p: Platform, values: dict, creating: bool) -> None:
    if "code" in values or creating:
        p.code = _text(values, "code", "编码", 50, required=True)
    if "name" in values or creating:
        p.name = _text(values, "name", "平台名称", 100, required=True)
    if "name_en" in values or creating:
        p.name_en = _text(values, "name_en", "平台名称(en)", 100)
    p.website = _website(values, creating, p.website or "")
    if "market" in values or creating:
        p.market = _text(values, "market", "市场", 100)
    if "feature" in values or creating:
        p.feature = _text(values, "feature", "特性", 500)
    if "remark" in values or creating:
        p.remark = _text(values, "remark", "备注", 500)
    p.is_independent = _flag(values, creating, p.is_independent or 0)


def _save_platform(db: Session, p: Platform) -> None:
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        detail = str(getattr(e, "orig", e))
        if "uq_platform_code" in detail:
            fail("平台编码已存在")
        if "uq_platform_name" in detail:
            fail("平台名称已存在")
        fail("保存失败")
    db.refresh(p)


def _cat_by_id(db: Session) -> dict[int, ShopCategory]:
    return {c.id: c for c in db.scalars(select(ShopCategory)).all()}


def _root_of(cid: int, by_id: dict[int, ShopCategory]) -> ShopCategory | None:
    seen: set[int] = set()
    c = by_id.get(cid)
    while c and c.parent_id and c.parent_id not in seen:
        seen.add(c.id)
        nxt = by_id.get(c.parent_id)
        if nxt is None:
            break
        c = nxt
    return c


def _category_summary(ids: list[int], by_id: dict[int, ShopCategory]) -> dict:
    """列表展示：最多 5 个已覆盖的一级分类名称，以及已绑定的小类数量。"""
    roots: list[ShopCategory] = []
    seen: set[int] = set()
    leaf_n = 0
    for cid in ids:
        c = by_id.get(cid)
        if c is None:
            continue
        if c.parent_id:
            leaf_n += 1
        root = _root_of(cid, by_id)
        if root is None or root.id in seen:
            continue
        seen.add(root.id)
        roots.append(root)
    roots.sort(key=lambda c: (c.sort_order, c.id))
    shown = [{"id": c.id, "name": c.name} for c in roots[:5]]
    return {
        "category_ids": ids,
        "category_count": len(ids),
        "category_roots": shown,
        "category_root_total": len(roots),
        "category_leaf_count": leaf_n,
    }


def _store_dict(s: Store, p: Platform | None, category_ids: list[int] | None = None,
                cat_by_id: dict[int, ShopCategory] | None = None) -> dict:
    ids = list(category_ids or [])
    d = {
        "id": s.id, "platform_id": s.platform_id,
        "platform_name": p.name if p else "",
        "code": s.code, "name": s.name, "name_en": s.name_en, "website": s.website,
        "shipping_package_group_id": s.shipping_package_group_id,
        "feature": s.feature, "remark": s.remark,
        "is_independent": bool(p.is_independent) if p else False,
        "created_at": _fmt(s.created_at), "updated_at": _fmt(s.updated_at),
    }
    d.update(_category_summary(ids, cat_by_id or {}))
    return d


def _store_cat_map(db: Session, store_ids: list[int] | None = None) -> dict[int, list[int]]:
    stmt = select(StoreCategory.store_id, StoreCategory.category_id).order_by(StoreCategory.id)
    if store_ids is not None:
        if not store_ids:
            return {}
        stmt = stmt.where(StoreCategory.store_id.in_(store_ids))
    m: dict[int, list[int]] = defaultdict(list)
    for sid, cid in db.execute(stmt):
        m[sid].append(int(cid))
    return m


def _parse_category_ids(db: Session, raw) -> list[int]:
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        fail("分类格式不正确")
    ids: list[int] = []
    seen: set[int] = set()
    for item in raw:
        if isinstance(item, bool) or item in (None, ""):
            fail("分类不正确")
        try:
            cid = int(item)
        except (TypeError, ValueError):
            fail("分类不正确")
        if cid <= 0 or cid in seen:
            continue
        seen.add(cid)
        ids.append(cid)
    if not ids:
        return []
    found = set(db.scalars(select(ShopCategory.id).where(ShopCategory.id.in_(ids))))
    missing = [cid for cid in ids if cid not in found]
    if missing:
        fail("分类不存在")
    return ids


def _replace_store_cats(db: Session, store_id: int, ids: list[int]) -> None:
    db.execute(delete(StoreCategory).where(StoreCategory.store_id == store_id))
    for cid in ids:
        db.add(StoreCategory(store_id=store_id, category_id=cid))


def _load_store(db: Session, sid: int) -> tuple[Store, Platform]:
    row = db.execute(
        select(Store, Platform).join(Platform, Platform.id == Store.platform_id).where(Store.id == sid)
    ).first()
    if row is None:
        fail("店铺不存在", 404)
    return row


def _apply_store(db: Session, s: Store, values: dict, creating: bool) -> None:
    if "platform_id" in values or creating:
        raw = values.get("platform_id")
        if isinstance(raw, bool) or raw in (None, ""):
            fail("请选择平台")
        try:
            pid = int(raw)
        except (TypeError, ValueError):
            fail("请选择平台")
        if db.get(Platform, pid) is None:
            fail("请选择平台")
        s.platform_id = pid
    if "code" in values or creating:
        s.code = _text(values, "code", "编码", 50, required=True)
    if "name" in values or creating:
        s.name = _text(values, "name", "店铺名称", 100, required=True)
    if "name_en" in values or creating:
        s.name_en = _text(values, "name_en", "店铺名称(en)", 100)
    s.website = _website(values, creating, s.website or "")
    if "feature" in values or creating:
        s.feature = _text(values, "feature", "特性", 500)
    if "remark" in values or creating:
        s.remark = _text(values, "remark", "备注", 500)
    if "shipping_package_group_id" in values or creating:
        try:
            group_id = int(values.get("shipping_package_group_id") or 0)
        except (TypeError, ValueError):
            fail("默认包装组格式不正确")
        if group_id and db.get(ShippingPackageGroup, group_id) is None:
            fail("默认包装组不存在")
        s.shipping_package_group_id = group_id


def _save_store(db: Session, s: Store) -> None:
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        detail = str(getattr(e, "orig", e))
        if "uq_store_platform_code" in detail:
            fail("该平台下店铺编码已存在")
        if "uq_store_platform_name" in detail:
            fail("该平台下店铺名称已存在")
        fail("保存失败")
    db.refresh(s)


@platform_router.get("")
def list_platforms(db: Session = Depends(get_db)):
    counts = _counts(db)
    rows = db.scalars(select(Platform).order_by(Platform.code, Platform.id))
    return ok([_platform_dict(p, counts.get(p.id, 0)) for p in rows])


@platform_router.post("")
def create_platform(values: dict, db: Session = Depends(get_db)):
    p = Platform()
    _apply_platform(p, values, True)
    db.add(p)
    _save_platform(db, p)
    return ok(_platform_dict(p, 0))


@platform_router.put("/{pid}")
def update_platform(pid: int, values: dict, db: Session = Depends(get_db)):
    p = db.get(Platform, pid) or fail("平台不存在", 404)
    _apply_platform(p, values, False)
    _save_platform(db, p)
    n = db.scalar(select(func.count()).where(Store.platform_id == pid)) or 0
    return ok(_platform_dict(p, int(n)))


@platform_router.delete("/{pid}")
def delete_platform(pid: int, db: Session = Depends(get_db)):
    p = db.get(Platform, pid) or fail("平台不存在", 404)
    n = db.scalar(select(func.count()).where(Store.platform_id == pid)) or 0
    if n:
        fail(f"该平台下还有 {int(n)} 个店铺，不能删除")
    db.delete(p)
    db.commit()
    return ok()


@store_router.get("")
def list_stores(db: Session = Depends(get_db)):
    rows = list(db.execute(
        select(Store, Platform)
        .join(Platform, Platform.id == Store.platform_id)
        .order_by(Platform.code, Store.code, Store.id)
    ))
    cats = _store_cat_map(db, [s.id for s, _ in rows])
    by_id = _cat_by_id(db)
    return ok([_store_dict(s, p, cats.get(s.id, []), by_id) for s, p in rows])


@store_router.post("")
def create_store(values: dict, db: Session = Depends(get_db)):
    s = Store()
    _apply_store(db, s, values, True)
    db.add(s)
    _save_store(db, s)
    store, platform = _load_store(db, s.id)
    return ok(_store_dict(store, platform, []))


@store_router.put("/{sid}")
def update_store(sid: int, values: dict, db: Session = Depends(get_db)):
    s = db.get(Store, sid) or fail("店铺不存在", 404)
    _apply_store(db, s, values, False)
    _save_store(db, s)
    store, platform = _load_store(db, s.id)
    return ok(_store_dict(store, platform, _store_cat_map(db, [s.id]).get(s.id, []), _cat_by_id(db)))


@store_router.delete("/{sid}")
def delete_store(sid: int, db: Session = Depends(get_db)):
    s = db.get(Store, sid) or fail("店铺不存在", 404)
    if db.scalar(select(ShopOrder.id).where(ShopOrder.store_id == sid).limit(1)):
        fail("该店铺已有订单镜像，不能删除")
    db.execute(delete(StoreCategory).where(StoreCategory.store_id == sid))
    db.execute(delete(ShopGoodsStore).where(ShopGoodsStore.store_id == sid))
    db.execute(delete(ShopifySyncTask).where(ShopifySyncTask.store_id == sid))
    db.execute(delete(ShopifyVariantMap).where(ShopifyVariantMap.store_id == sid))
    db.execute(delete(ShopifyProductMap).where(ShopifyProductMap.store_id == sid))
    db.execute(delete(ShopifyBundleMap).where(ShopifyBundleMap.store_id == sid))
    db.execute(delete(ShopifyWebhookEvent).where(ShopifyWebhookEvent.store_id == sid))
    db.execute(delete(ShopifyStoreConfig).where(ShopifyStoreConfig.store_id == sid))
    db.delete(s)
    db.commit()
    return ok()


@store_router.get("/{sid}/categories")
def get_store_categories(sid: int, db: Session = Depends(get_db)):
    db.get(Store, sid) or fail("店铺不存在", 404)
    ids = _store_cat_map(db, [sid]).get(sid, [])
    return ok({"category_ids": ids})


@store_router.put("/{sid}/categories")
def save_store_categories(sid: int, body: dict, db: Session = Depends(get_db)):
    db.get(Store, sid) or fail("店铺不存在", 404)
    ids = _parse_category_ids(db, body.get("category_ids"))
    _replace_store_cats(db, sid, ids)
    db.commit()
    return ok(_category_summary(ids, _cat_by_id(db)))
