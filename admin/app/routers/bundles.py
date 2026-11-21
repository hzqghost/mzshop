"""固定组合与单地点库存后台接口。"""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_user
from ..inventory import StockError, available, bundle_available, change_stock, enqueue_inventory
from ..listquery import build_filter, build_sort, clamp_page, parse_json
from ..models import (BundleComponent, BundleRevision, GeoRegion, ShopGoods, ShopGoodsRegion,
                      ShopGoodsSku, ShopGoodsSkuRegion, ShopifyStoreConfig, StockBalance,
                      StockLedger, StockLocation)

router = APIRouter(prefix="/api/v1/bundles", dependencies=[Depends(require_user)])
inventory_router = APIRouter(prefix="/api/v1/inventory", dependencies=[Depends(require_user)])


def ok(data=None): return {"code": 0, "data": data, "msg": "ok"}
def fail(msg, status=400): raise HTTPException(status_code=status, detail=msg)
def _fmt(value): return value.strftime("%Y-%m-%d %H:%M:%S") if value else None


def _location_dict(row: StockLocation) -> dict:
    return {"id": row.id, "code": row.code, "name": row.name, "status": bool(row.status),
            "remark": row.remark, "created_at": _fmt(row.created_at), "updated_at": _fmt(row.updated_at)}


def _apply_location(row: StockLocation, body: dict, creating: bool) -> None:
    if "code" in body or creating:
        code = str(body.get("code") or "").strip()
        if not code or len(code) > 50: fail("地点编码不能为空且不能超过 50 个字符")
        row.code = code
    if "name" in body or creating:
        name = str(body.get("name") or "").strip()
        if not name or len(name) > 100: fail("地点名称不能为空且不能超过 100 个字符")
        row.name = name
    if "remark" in body or creating:
        remark = str(body.get("remark") or "").strip()
        if len(remark) > 500: fail("备注不能超过 500 个字符")
        row.remark = remark
    if "status" in body or creating:
        row.status = 1 if body.get("status", True) else 0


def _save_location(db: Session, row: StockLocation) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback(); fail("库存地点编码或名称已存在")
    db.refresh(row)


def _components(db: Session, revision_id: int) -> list[dict]:
    rows = db.execute(select(BundleComponent, ShopGoodsSku, ShopGoods).join(
        ShopGoodsSku, ShopGoodsSku.id == BundleComponent.component_sku_id).join(
        ShopGoods, ShopGoods.id == ShopGoodsSku.goods_id).where(
        BundleComponent.revision_id == revision_id).order_by(BundleComponent.sort_order, BundleComponent.id))
    return [{"id": c.id, "component_sku_id": s.id, "sku_id": s.id, "sku_code": s.sku_code,
             "goods_id": s.goods_id, "goods_name": g.name, "spec_name": s.spec_name,
             "sku_type": s.sku_type, "cost_price": float(s.cost_price), "quantity": c.quantity,
             "sort_order": c.sort_order, "status": bool(s.status)} for c, s, g in rows]


def _bundle_prices(db: Session, sku: ShopGoodsSku | None) -> list[dict]:
    if not sku:
        return []
    bases = {x.region_id: x for x in db.scalars(select(ShopGoodsRegion).where(
        ShopGoodsRegion.goods_id == sku.goods_id))}
    overrides = {x.region_id: x for x in db.scalars(select(ShopGoodsSkuRegion).where(
        ShopGoodsSkuRegion.sku_id == sku.id))}
    region_ids = sorted(set(bases) | set(overrides))
    regions = {x.id: x for x in db.scalars(select(GeoRegion).where(GeoRegion.id.in_(region_ids)))} if region_ids else {}
    result = []
    for region_id in region_ids:
        base, override = bases.get(region_id), overrides.get(region_id)
        price = override.price if override and override.price is not None else (base.price if base else None)
        if price is None:
            continue
        result.append({"region_id": region_id, "region_name": regions.get(region_id).name if regions.get(region_id) else str(region_id),
                       "price": float(price), "currency": base.currency if base else "",
                       "source": "sku" if override and override.price is not None else "goods"})
    return result


def _revision_availability(db: Session, row: BundleRevision) -> list[dict]:
    if row.status == "disabled":
        return []
    components = list(db.scalars(select(BundleComponent).where(BundleComponent.revision_id == row.id)))
    locations = list(db.scalars(select(StockLocation).where(StockLocation.status == 1).order_by(StockLocation.id)))
    if not components:
        return [{"location_id": x.id, "location_name": x.name, "available": 0} for x in locations]
    sku_ids = [x.component_sku_id for x in components]
    location_ids = [x.id for x in locations]
    balances = {(x.location_id, x.sku_id): x for x in db.scalars(select(StockBalance).where(
        StockBalance.location_id.in_(location_ids), StockBalance.sku_id.in_(sku_ids)))} if location_ids else {}
    return [{"location_id": location.id, "location_name": location.name,
             "available": min(available(balances.get((location.id, component.component_sku_id))) // component.quantity
                              for component in components)} for location in locations]


def _revision(db: Session, row: BundleRevision) -> dict:
    sku = db.get(ShopGoodsSku, row.parent_sku_id)
    goods = db.get(ShopGoods, sku.goods_id) if sku else None
    prices = _bundle_prices(db, sku)
    availability = _revision_availability(db, row)
    return {"id": row.id, "parent_sku_id": row.parent_sku_id, "parent_sku_code": sku.sku_code if sku else "",
            "goods_id": sku.goods_id if sku else 0, "goods_name": goods.name if goods else "",
            "parent_spec_name": sku.spec_name if sku else "", "parent_status": bool(sku.status) if sku else False,
            "parent_cost_price": float(sku.cost_price) if sku else 0,
            "version_no": row.version_no, "status": row.status, "replaced_revision_id": row.replaced_revision_id,
            "remark": row.remark, "published_at": _fmt(row.published_at),
            "created_at": _fmt(row.created_at), "updated_at": _fmt(row.updated_at),
            "components": _components(db, row.id), "prices": prices,
            "price_text": "；".join(f"{x['region_name']}：{x['price']:,.2f}{(' ' + x['currency']) if x['currency'] else ''}" for x in prices),
            "availability": availability,
            "availability_text": "；".join(f"{x['location_name']}：{x['available']}" for x in availability)}


def _parse_components(db: Session, parent_sku_id: int, values) -> list[tuple[ShopGoodsSku, int]]:
    if not isinstance(values, list) or not values:
        fail("组合至少需要一个组件")
    result, seen = [], set()
    for item in values:
        try:
            sku_id, quantity = int(item.get("component_sku_id")), int(item.get("quantity"))
        except (AttributeError, TypeError, ValueError):
            fail("组件参数不正确")
        sku = db.get(ShopGoodsSku, sku_id)
        if not sku or not sku.status or sku.sku_type != "normal":
            fail("组件 SKU 不存在、已停用或不是普通 SKU")
        if sku_id == parent_sku_id or sku_id in seen or quantity <= 0 or quantity > 100000:
            fail("组件重复、数量不正确或引用了父 SKU")
        seen.add(sku_id); result.append((sku, quantity))
    return result


@router.get("")
def list_revisions(parent_sku_id: int | None = None, db: Session = Depends(get_db)):
    stmt = select(BundleRevision).order_by(BundleRevision.parent_sku_id, BundleRevision.version_no.desc())
    if parent_sku_id:
        stmt = stmt.where(BundleRevision.parent_sku_id == parent_sku_id)
    return ok([_revision(db, row) for row in db.scalars(stmt)])


@router.get("/component-options")
def component_options(q: str = "", take: int = 50, sku_id: int | None = None,
                      db: Session = Depends(get_db)):
    stmt = select(ShopGoodsSku, ShopGoods).join(ShopGoods, ShopGoods.id == ShopGoodsSku.goods_id).where(
        ShopGoodsSku.sku_type == "normal", ShopGoodsSku.status == 1)
    if sku_id:
        stmt = stmt.where(ShopGoodsSku.id == sku_id)
    elif q.strip():
        term = f"%{q.strip().replace('%', '\\%').replace('_', '\\_')}%"
        stmt = stmt.where((ShopGoodsSku.sku_code.like(term, escape="\\")) | (ShopGoods.name.like(term, escape="\\")))
    rows = db.execute(stmt.order_by(ShopGoodsSku.sku_code).limit(max(1, min(take, 100))))
    return ok([{"id": s.id, "sku_code": s.sku_code, "text": f"{s.sku_code} · {g.name} · {s.spec_name}"}
               for s, g in rows])


@router.get("/parent-options")
def parent_options(q: str = "", take: int = 100, db: Session = Depends(get_db)):
    stmt = select(ShopGoodsSku, ShopGoods).join(ShopGoods, ShopGoods.id == ShopGoodsSku.goods_id).where(
        ShopGoodsSku.status == 1)
    if q.strip():
        escaped = q.strip().replace("%", "\\%").replace("_", "\\_")
        term = f"%{escaped}%"
        stmt = stmt.where((ShopGoodsSku.sku_code.like(term, escape="\\")) | (ShopGoods.name.like(term, escape="\\")))
    rows = list(db.execute(stmt.order_by(ShopGoodsSku.sku_code).limit(max(1, min(take, 200)))))
    goods_ids = {s.goods_id for s, _ in rows}
    counts = {goods_id: count for goods_id, count in db.execute(
        select(ShopGoodsSku.goods_id, func.count(ShopGoodsSku.id)).where(
            ShopGoodsSku.goods_id.in_(goods_ids)).group_by(ShopGoodsSku.goods_id))} if goods_ids else {}
    result = [{"id": s.id, "sku_code": s.sku_code, "sku_type": s.sku_type,
               "is_dedicated": counts.get(s.goods_id, 0) == 1,
               "text": f"{s.sku_code} · {g.name} · {s.spec_name}{' · 独立商品' if counts.get(s.goods_id, 0) == 1 else ''}"}
              for s, g in rows]
    result.sort(key=lambda x: (not x["is_dedicated"], x["sku_code"]))
    return ok(result)


@router.post("")
def create_revision(body: dict, db: Session = Depends(get_db)):
    try: parent_sku_id = int(body.get("parent_sku_id"))
    except (TypeError, ValueError): fail("请选择组合父 SKU")
    parent = db.get(ShopGoodsSku, parent_sku_id)
    if not parent: fail("父 SKU 不存在", 404)
    if parent.sku_type == "normal": parent.sku_type = "bundle"
    components = _parse_components(db, parent_sku_id, body.get("components"))
    version = int(db.scalar(select(func.max(BundleRevision.version_no)).where(
        BundleRevision.parent_sku_id == parent_sku_id)) or 0) + 1
    row = BundleRevision(parent_sku_id=parent_sku_id, version_no=version, status="draft",
                         remark=str(body.get("remark") or "").strip()[:500])
    db.add(row); db.flush()
    db.add_all(BundleComponent(revision_id=row.id, component_sku_id=s.id, quantity=n, sort_order=i * 10)
               for i, (s, n) in enumerate(components, 1))
    db.commit(); db.refresh(row)
    return ok(_revision(db, row))


@router.put("/{revision_id}")
def update_revision(revision_id: int, body: dict, db: Session = Depends(get_db)):
    row = db.get(BundleRevision, revision_id) or fail("组合版本不存在", 404)
    if row.status != "draft": fail("只有草稿版本可以修改")
    components = _parse_components(db, row.parent_sku_id, body.get("components"))
    row.remark = str(body.get("remark") or "").strip()[:500]
    db.execute(delete(BundleComponent).where(BundleComponent.revision_id == row.id))
    db.add_all(BundleComponent(revision_id=row.id, component_sku_id=s.id, quantity=n, sort_order=i * 10)
               for i, (s, n) in enumerate(components, 1))
    db.commit(); db.refresh(row)
    return ok(_revision(db, row))


@router.post("/{revision_id}/publish")
def publish_revision(revision_id: int, db: Session = Depends(get_db)):
    row = db.get(BundleRevision, revision_id) or fail("组合版本不存在", 404)
    if row.status != "draft": fail("只有草稿版本可以发布")
    _parse_components(db, row.parent_sku_id, [{"component_sku_id": x.component_sku_id, "quantity": x.quantity}
        for x in db.scalars(select(BundleComponent).where(BundleComponent.revision_id == row.id))])
    old = db.scalar(select(BundleRevision).where(BundleRevision.parent_sku_id == row.parent_sku_id,
        BundleRevision.status == "published").with_for_update())
    if old:
        old.status = "disabled"; row.replaced_revision_id = old.id
    row.status, row.published_at = "published", datetime.now()
    db.commit(); db.refresh(row)
    return ok(_revision(db, row))


@router.delete("/{revision_id}")
def delete_revision(revision_id: int, db: Session = Depends(get_db)):
    row = db.get(BundleRevision, revision_id) or fail("组合版本不存在", 404)
    if row.status != "draft": fail("只有草稿版本可以删除")
    parent_sku_id = row.parent_sku_id
    db.execute(delete(BundleComponent).where(BundleComponent.revision_id == row.id)); db.delete(row); db.flush()
    if not db.scalar(select(BundleRevision.id).where(BundleRevision.parent_sku_id == parent_sku_id).limit(1)):
        parent = db.get(ShopGoodsSku, parent_sku_id)
        if parent: parent.sku_type = "normal"
    db.commit()
    return ok()


@inventory_router.get("/locations")
def list_locations(db: Session = Depends(get_db)):
    return ok([_location_dict(x) for x in db.scalars(select(StockLocation).order_by(StockLocation.id))])


@inventory_router.post("/locations")
def create_location(body: dict, db: Session = Depends(get_db)):
    row = StockLocation(); _apply_location(row, body, True); db.add(row); _save_location(db, row)
    return ok(_location_dict(row))


@inventory_router.put("/locations/{location_id}")
def update_location(location_id: int, body: dict, db: Session = Depends(get_db)):
    row = db.get(StockLocation, location_id) or fail("库存地点不存在", 404)
    _apply_location(row, body, False); _save_location(db, row)
    return ok(_location_dict(row))


@inventory_router.delete("/locations/{location_id}")
def delete_location(location_id: int, db: Session = Depends(get_db)):
    row = db.get(StockLocation, location_id) or fail("库存地点不存在", 404)
    if db.scalar(select(ShopifyStoreConfig.id).where(ShopifyStoreConfig.stock_location_id == location_id).limit(1)):
        fail("该地点已绑定 Shopify 店铺，不能删除")
    if db.scalar(select(StockBalance.id).where(StockBalance.location_id == location_id).limit(1)):
        fail("该地点已有库存余额，不能删除")
    if db.scalar(select(StockLedger.id).where(StockLedger.location_id == location_id).limit(1)):
        fail("该地点已有库存流水，不能删除")
    db.delete(row); db.commit(); return ok()


@inventory_router.get("/balances")
def list_balances(location_id: int | None = None, take: int | None = Query(None), skip: int = 0,
                  sort: str | None = None, filter: str | None = None, db: Session = Depends(get_db)):
    available_expr = func.greatest(StockBalance.on_hand - StockBalance.reserved - StockBalance.unavailable - StockBalance.safety_stock, 0)
    remark_expr = (select(StockLedger.remark).where(
        StockLedger.sku_id == StockBalance.sku_id,
        StockLedger.location_id == StockBalance.location_id
    ).order_by(StockLedger.id.desc()).limit(1).scalar_subquery())
    stmt = select(StockBalance, ShopGoodsSku, ShopGoods, StockLocation,
                  remark_expr.label("adjustment_remark")).join(
        ShopGoodsSku, ShopGoodsSku.id == StockBalance.sku_id).join(
        ShopGoods, ShopGoods.id == ShopGoodsSku.goods_id).join(
        StockLocation, StockLocation.id == StockBalance.location_id)
    if location_id: stmt = stmt.where(StockBalance.location_id == location_id)
    fields = {"id": (StockBalance.id, "num"), "sku_code": (ShopGoodsSku.sku_code, "str"),
              "goods_name": (ShopGoods.name, "str"), "spec_name": (ShopGoodsSku.spec_name, "str"),
              "location_name": (StockLocation.name, "str"), "on_hand": (StockBalance.on_hand, "num"),
              "reserved": (StockBalance.reserved, "num"), "unavailable": (StockBalance.unavailable, "num"),
              "safety_stock": (StockBalance.safety_stock, "num"), "available": (available_expr, "num"),
              "adjustment_remark": (remark_expr, "str")}
    condition = build_filter(parse_json(filter, "筛选"), fields)
    if condition is not None:
        stmt = stmt.where(condition)
    total = int(db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0)
    order = build_sort(parse_json(sort, "排序"), fields)
    requested_take = take
    if take is not None:
        skip, take = clamp_page(skip, take); stmt = stmt.offset(skip).limit(take)
    rows = db.execute(stmt.order_by(*(order or [ShopGoodsSku.sku_code, StockLocation.id])))
    items = [{"id": b.id, "sku_id": s.id, "goods_id": g.id, "sku_code": s.sku_code, "goods_name": g.name,
        "spec_name": s.spec_name, "location_id": l.id, "location_name": l.name, "on_hand": b.on_hand,
        "reserved": b.reserved, "unavailable": b.unavailable, "safety_stock": b.safety_stock,
        "available": available(b), "adjustment_remark": adjustment_remark}
        for b, s, g, l, adjustment_remark in rows]
    return ok(items if requested_take is None else {"items": items, "total": total})


@inventory_router.post("/adjust")
def adjust_stock(body: dict, db: Session = Depends(get_db)):
    try:
        sku_id, location_id = int(body.get("sku_id")), int(body.get("location_id"))
        on_hand = int(body.get("on_hand")); unavailable = int(body.get("unavailable", 0)); safety = int(body.get("safety_stock", 0))
    except (TypeError, ValueError): fail("库存参数不正确")
    if min(on_hand, unavailable, safety) < 0: fail("库存数量不能小于 0")
    if not db.get(StockLocation, location_id): fail("库存地点不存在")
    current = db.scalar(select(StockBalance).where(StockBalance.sku_id == sku_id,
        StockBalance.location_id == location_id).with_for_update())
    old_on, old_un = (current.on_hand, current.unavailable) if current else (0, 0)
    try:
        balance = change_stock(db, sku_id, location_id, "manual", f"manual:{uuid.uuid4().hex}",
            delta_on_hand=on_hand-old_on, delta_unavailable=unavailable-old_un,
            reference_type="manual", remark=str(body.get("remark") or "人工调整"))
        balance.safety_stock = safety; enqueue_inventory(db, {sku_id}); db.commit(); db.refresh(balance)
    except StockError as e: db.rollback(); fail(str(e))
    return ok({"id": balance.id, "available": available(balance)})


@inventory_router.get("/bundle-available/{parent_sku_id}")
def get_bundle_available(parent_sku_id: int, location_id: int, db: Session = Depends(get_db)):
    return ok({"parent_sku_id": parent_sku_id, "location_id": location_id,
               "available": bundle_available(db, parent_sku_id, location_id)})


@inventory_router.get("/ledger")
def list_ledger(take: int = 100, db: Session = Depends(get_db)):
    rows = db.scalars(select(StockLedger).order_by(StockLedger.id.desc()).limit(max(1, min(take, 500))))
    return ok([{"id": x.id, "sku_id": x.sku_id, "location_id": x.location_id, "event_type": x.event_type,
        "delta_on_hand": x.delta_on_hand, "delta_reserved": x.delta_reserved,
        "delta_unavailable": x.delta_unavailable, "after_on_hand": x.after_on_hand,
        "after_reserved": x.after_reserved, "after_unavailable": x.after_unavailable,
        "reference_type": x.reference_type, "reference_id": x.reference_id, "remark": x.remark,
        "created_at": _fmt(x.created_at)} for x in rows])
