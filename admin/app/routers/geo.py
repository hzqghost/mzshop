"""国家地区树，以及可重复勾选国家的区域。响应 {code, data, msg}。"""
import re
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_user
from ..models import GeoNode, GeoRegion, GeoRegionCountry, ShopGoodsRegion, SupplierCatalogItemRegion

geo_router = APIRouter(prefix="/api/v1/geo", dependencies=[Depends(require_user)])
region_router = APIRouter(prefix="/api/v1/regions", dependencies=[Depends(require_user)])

_CODE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,9}$")


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


def _int(raw, label: str, lo: int = 0, hi: int = 999999) -> int:
    if raw in (None, ""):
        return 0
    try:
        n = int(raw)
    except (TypeError, ValueError):
        fail(f"{label}不正确")
    if n < lo or n > hi:
        fail(f"{label}需在 {lo}~{hi} 之间")
    return n


def _geo_dict(g: GeoNode) -> dict:
    return {
        "id": g.id, "parent_id": g.parent_id, "code": g.code, "name_zh": g.name_zh, "name_en": g.name_en,
        "is_leaf": bool(g.is_leaf), "sort_order": g.sort_order,
        "created_at": _fmt(g.created_at), "updated_at": _fmt(g.updated_at),
    }


def _children_map(db: Session) -> dict[int, list[int]]:
    children: dict[int, list[int]] = defaultdict(list)
    for gid, pid in db.execute(select(GeoNode.id, GeoNode.parent_id)):
        children[pid].append(gid)
    return children


def _descendants(children: dict[int, list[int]], gid: int) -> set[int]:
    out: set[int] = set()
    stack = list(children.get(gid, []))
    while stack:
        cur = stack.pop()
        if cur in out:
            continue
        out.add(cur)
        stack.extend(children.get(cur, []))
    return out


def _apply_geo(db: Session, g: GeoNode, values: dict, creating: bool) -> None:
    if "code" in values or creating:
        code = _text(values, "code", "编码", 10, required=True).upper()
        if not _CODE.match(code):
            fail("编码为 1~10 位字母、数字、下划线或连字符")
        g.code = code
    if "name_zh" in values or creating:
        g.name_zh = _text(values, "name_zh", "中文名", 50, required=True)
    if "name_en" in values or creating:
        g.name_en = _text(values, "name_en", "英文名", 80, required=True)
    if "sort_order" in values or creating:
        g.sort_order = _int(values.get("sort_order"), "排序")
    if "parent_id" in values or creating:
        pid = _int(values.get("parent_id"), "父ID")
        if g.id and pid == g.id:
            fail("上级不能是自己")
        if pid and db.get(GeoNode, pid) is None:
            fail("上级不存在")
        if g.id and pid and pid in _descendants(_children_map(db), g.id):
            fail("上级不能是自己的下级")
        g.parent_id = pid
    if "is_leaf" in values or creating:
        g.is_leaf = 1 if values.get("is_leaf", True) else 0
    if g.id and g.is_leaf and _children_map(db).get(g.id):
        fail("还有下级时不能标为子节点")
    if g.parent_id:
        parent = db.get(GeoNode, g.parent_id)
        if parent and parent.is_leaf:
            parent.is_leaf = 0


def _save_geo(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fail("编码已存在")


@geo_router.get("")
def list_geo(db: Session = Depends(get_db)):
    rows = db.scalars(select(GeoNode).order_by(GeoNode.sort_order, GeoNode.code, GeoNode.id))
    return ok([_geo_dict(g) for g in rows])


@geo_router.post("")
def create_geo(values: dict, db: Session = Depends(get_db)):
    g = GeoNode()
    _apply_geo(db, g, values, True)
    db.add(g)
    _save_geo(db)
    return ok(_geo_dict(g))


@geo_router.put("/{gid}")
def update_geo(gid: int, values: dict, db: Session = Depends(get_db)):
    g = db.get(GeoNode, gid) or fail("国家地区不存在", 404)
    _apply_geo(db, g, values, False)
    _save_geo(db)
    return ok(_geo_dict(g))


@geo_router.delete("/{gid}")
def delete_geo(gid: int, db: Session = Depends(get_db)):
    g = db.get(GeoNode, gid) or fail("国家地区不存在", 404)
    if db.scalar(select(func.count()).select_from(GeoNode).where(GeoNode.parent_id == gid)):
        fail("还有下级，不能删除")
    used = db.scalar(select(func.count()).select_from(GeoRegionCountry).where(GeoRegionCountry.geo_id == gid)) or 0
    if used:
        fail(f"已被 {int(used)} 个区域使用，不能删除")
    db.delete(g)
    db.commit()
    return ok()


def _ancestors(nodes: dict[int, GeoNode], node: GeoNode) -> list[GeoNode]:
    out = []
    seen = set()
    cur = nodes.get(node.parent_id)
    while cur and cur.id not in seen:
        seen.add(cur.id)
        out.append(cur)
        cur = nodes.get(cur.parent_id)
    return out


def _normalize_scope(nodes: dict[int, GeoNode], ids: list[int]) -> list[int]:
    """全球 / 洲单独勾选时只保留该节点，不展开成国家。某个国家被勾选时，丢掉盖住它的上级。"""
    chosen = [nodes[i] for i in ids]
    chosen_ids = {node.id for node in chosen}
    covered = set()
    for node in chosen:
        if node.is_leaf:
            covered.update(parent.id for parent in _ancestors(nodes, node))
    kept = []
    for node in chosen:
        if not node.is_leaf:
            if node.id in covered:
                continue
            if any(parent.id in chosen_ids and parent.id not in covered for parent in _ancestors(nodes, node)):
                continue
        kept.append(node.id)
    return kept


def _country_ids(db: Session, raw) -> list[int]:
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        fail("国家格式不正确")
    ids: list[int] = []
    for item in raw:
        try:
            gid = int(item)
        except (TypeError, ValueError):
            fail("国家格式不正确")
        if gid > 0 and gid not in ids:
            ids.append(gid)
    if not ids:
        return []
    nodes = {row.id: row for row in db.scalars(select(GeoNode))}
    if any(gid not in nodes for gid in ids):
        fail("所选国家地区不存在")
    return _normalize_scope(nodes, ids)


def _ordered_countries(nodes: dict[int, GeoNode], ids: list[int]) -> list[dict]:
    def key(gid: int):
        chain = []
        seen = set()
        cur = nodes.get(gid)
        while cur and cur.id not in seen:
            seen.add(cur.id)
            chain.append(cur)
            cur = nodes.get(cur.parent_id)
        chain.reverse()
        return tuple((n.sort_order, n.code) for n in chain)

    out = []
    for gid in sorted(ids, key=key):
        g = nodes.get(gid)
        if g:
            out.append({"id": g.id, "code": g.code, "name_zh": g.name_zh, "name_en": g.name_en, "is_leaf": bool(g.is_leaf)})
    return out


def _region_rows(db: Session) -> list[dict]:
    regions = db.scalars(select(GeoRegion).order_by(GeoRegion.sort_order, GeoRegion.id)).all()
    links: dict[int, list[int]] = defaultdict(list)
    for region_id, geo_id in db.execute(select(GeoRegionCountry.region_id, GeoRegionCountry.geo_id)):
        links[region_id].append(geo_id)
    nodes = {g.id: g for g in db.scalars(select(GeoNode))}
    out = []
    for region in regions:
        countries = _ordered_countries(nodes, links.get(region.id, []))
        out.append({
            "id": region.id, "name": region.name, "sort_order": region.sort_order,
            "country_ids": [c["id"] for c in countries], "countries": countries,
            "created_at": _fmt(region.created_at), "updated_at": _fmt(region.updated_at),
        })
    return out


def _one_region(db: Session, region: GeoRegion) -> dict:
    for row in _region_rows(db):
        if row["id"] == region.id:
            return row
    fail("区域不存在", 404)


def _apply_region(db: Session, region: GeoRegion, values: dict, creating: bool) -> list[int] | None:
    if "name" in values or creating:
        region.name = _text(values, "name", "区域名称", 100, required=True)
    if "sort_order" in values or creating:
        region.sort_order = _int(values.get("sort_order"), "排序")
    if "country_ids" in values or creating:
        return _country_ids(db, values.get("country_ids"))
    return None


def _replace_countries(db: Session, region_id: int, ids: list[int]) -> None:
    db.execute(delete(GeoRegionCountry).where(GeoRegionCountry.region_id == region_id))
    for gid in ids:
        db.add(GeoRegionCountry(region_id=region_id, geo_id=gid))


def _save_region(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fail("区域名称已存在")


@region_router.get("")
def list_regions(db: Session = Depends(get_db)):
    return ok(_region_rows(db))


@region_router.post("")
def create_region(values: dict, db: Session = Depends(get_db)):
    region = GeoRegion()
    ids = _apply_region(db, region, values, True)
    db.add(region)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        fail("区域名称已存在")
    _replace_countries(db, region.id, ids or [])
    _save_region(db)
    return ok(_one_region(db, region))


@region_router.put("/{rid}")
def update_region(rid: int, values: dict, db: Session = Depends(get_db)):
    region = db.get(GeoRegion, rid) or fail("区域不存在", 404)
    ids = _apply_region(db, region, values, False)
    if ids is not None:
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            fail("区域名称已存在")
        _replace_countries(db, region.id, ids)
    _save_region(db)
    return ok(_one_region(db, region))


@region_router.post("/move")
def move_region(body: dict, db: Session = Depends(get_db)):
    """拖动排序：把 id 移到 target_id 之前或之后，全部区域的 sort_order 按新顺序重排为 10、20、30…。"""
    rid, tid = body.get("id"), body.get("target_id")
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in (rid, tid)) or rid == tid:
        fail("参数不合法")
    rows = list(db.scalars(select(GeoRegion).order_by(GeoRegion.sort_order, GeoRegion.id)))
    moving = next((row for row in rows if row.id == rid), None)
    if moving is None or not any(row.id == tid for row in rows):
        fail("区域不存在", 404)
    rows.remove(moving)
    pos = next(i for i, row in enumerate(rows) if row.id == tid)
    rows.insert(pos + 1 if body.get("after") else pos, moving)
    for i, row in enumerate(rows):
        row.sort_order = (i + 1) * 10
    db.commit()
    return ok()


@region_router.delete("/{rid}")
def delete_region(rid: int, db: Session = Depends(get_db)):
    region = db.get(GeoRegion, rid) or fail("区域不存在", 404)
    catalog_used = db.scalar(select(func.count()).where(SupplierCatalogItemRegion.region_id == rid)) or 0
    goods_used = db.scalar(select(func.count()).where(ShopGoodsRegion.region_id == rid)) or 0
    parts = []
    if catalog_used:
        parts.append(f"{int(catalog_used)} 条产品区域价格")
    if goods_used:
        parts.append(f"{int(goods_used)} 条商品区域价格")
    if parts:
        fail("已被 " + "、".join(parts) + "使用，不能删除")
    db.execute(delete(GeoRegionCountry).where(GeoRegionCountry.region_id == rid))
    db.delete(region)
    db.commit()
    return ok()
