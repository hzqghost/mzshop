"""Shopify 店铺配置、官方分类、分类关联和主动同步任务。"""
import gzip
import json
from http.client import IncompleteRead
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import SHOPIFY_API_VERSION, SHOPIFY_MAX_RETRIES, SHOPIFY_WEBHOOK_BASE_URL
from ..catalog import applicable_attributes
from ..db import get_db
from ..deps import require_user
from ..models import (GeoRegion, Platform, ShopAttribute, ShopCategory, ShopGoods, ShopGoodsSku, ShopGoodsStore,
                      ShopLanguage, ShopifyAttributeMap, ShopifyCategoryMap, ShopifyProductMap,
                      ShopifyStoreConfig, ShopifySyncTask, ShopifyTaxonomyAttribute,
                      ShopifyTaxonomyAttributeValue, ShopifyTaxonomyCategory,
                      ShopifyTaxonomyCategoryAttribute, StockLocation, Store)
from ..shopify_client import CONNECTION_QUERY, ShopifyError, graphql, normalize_domain
from ..listquery import build_filter, build_sort, clamp_page, parse_json

router = APIRouter(prefix="/api/v1/shopify", dependencies=[Depends(require_user)])

WEBHOOK_LIST = """query { webhookSubscriptions(first: 250) { nodes { id topic uri } } }"""
WEBHOOK_CREATE = """
mutation AddWebhook($topic: WebhookSubscriptionTopic!, $input: WebhookSubscriptionInput!) {
  webhookSubscriptionCreate(topic: $topic, webhookSubscription: $input) {
    webhookSubscription { id topic uri } userErrors { field message }
  }
}
"""


def ok(data=None):
    return {"code": 0, "data": data, "msg": "ok"}


def fail(msg: str, status: int = 400):
    raise HTTPException(status_code=status, detail=msg)


def _fmt(value):
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else None


def _shopify_store(db: Session, sid: int) -> Store:
    row = db.execute(select(Store, Platform).join(Platform, Platform.id == Store.platform_id)
                     .where(Store.id == sid)).first()
    if not row:
        fail("店铺不存在", 404)
    store, platform = row
    if platform.code.lower() != "shopify" and platform.name_en.lower() != "shopify":
        fail("该店铺不属于 Shopify 平台")
    return store


def _dict(c: ShopifyStoreConfig | None) -> dict:
    if not c:
        return {"configured": False, "shop_domain": "", "region_id": None, "language_code": "",
                "default_location_gid": "", "stock_location_id": 0, "publication_gid": "", "currency": "",
                "sync_enabled": True, "connection_status": "unchecked", "last_error": ""}
    return {"configured": True, "store_id": c.store_id, "shop_domain": c.shop_domain,
            "shop_gid": c.shop_gid, "region_id": c.region_id, "language_code": c.language_code,
            "default_location_gid": c.default_location_gid, "stock_location_id": c.stock_location_id,
            "publication_gid": c.publication_gid,
            "currency": c.currency, "sync_enabled": bool(c.sync_enabled),
            "connection_status": c.connection_status, "last_connected_at": _fmt(c.last_connected_at),
            "last_error": c.last_error or ""}


TAXONOMY_ASSET = ("https://github.com/Shopify/product-taxonomy/releases/download/v{version}/"
                  "{kind}.{locale}.json.gz")


def _taxonomy_data(locale: str, kind: str = "categories") -> dict:
    url = TAXONOMY_ASSET.format(version=SHOPIFY_API_VERSION, kind=kind, locale=locale)
    last_error = None
    for _ in range(3):
        request = Request(url, headers={"User-Agent": "mzShop-taxonomy-import"})
        try:
            with urlopen(request, timeout=120) as response:
                return json.loads(gzip.decompress(response.read()).decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, IncompleteRead) as exc:
            last_error = exc
    raise HTTPException(status_code=502, detail=f"下载 Shopify {locale} {kind} 失败：{last_error}") from None


def _flat_taxonomy(payload: dict) -> dict[str, dict]:
    """只保留分类导入所需字段，避免官方文件中的属性/退货原因长期占用内存。"""
    result = {}
    for vertical in payload.get("verticals") or []:
        for item in vertical.get("categories") or []:
            gid = str(item.get("id") or "")
            if gid:
                result[gid] = {
                    "parent_id": str(item.get("parent_id") or ""),
                    "level": int(item.get("level") or 0),
                    "name": str(item.get("name") or ""),
                    "full_name": str(item.get("full_name") or ""),
                    "is_leaf": not bool(item.get("children")),
                    "attributes": [{"gid": str(a.get("id") or ""), "handle": str(a.get("handle") or ""),
                                    "name": str(a.get("name") or ""),
                                    "description": str(a.get("description") or ""),
                                    "extended": bool(a.get("extended"))}
                                   for a in (item.get("attributes") or []) if a.get("id")],
                }
    return result


def _flat_attributes(payload: dict) -> dict[str, dict]:
    return {str(row.get("id")): {"handle": str(row.get("handle") or ""), "name": str(row.get("name") or ""),
                                 "description": str(row.get("description") or ""),
                                 "values": [{"gid": str(v.get("id") or ""), "handle": str(v.get("handle") or ""),
                                             "name": str(v.get("name") or "")}
                                            for v in (row.get("values") or []) if v.get("id")]}
            for row in (payload.get("attributes") or []) if row.get("id")}


def _taxonomy_item(row: ShopifyTaxonomyCategory) -> dict:
    return {
        "id": row.id, "taxonomy_gid": row.taxonomy_gid, "category_id": row.category_id,
        "parent_gid": row.parent_gid, "level": row.level, "name_zh": row.name_zh,
        "full_name_zh": row.full_name_zh, "name_en": row.name_en,
        "full_name_en": row.full_name_en, "is_leaf": bool(row.is_leaf),
        "is_active": bool(row.is_active), "version": row.version,
        "updated_at": _fmt(row.updated_at),
    }


@router.post("/taxonomy/import")
def import_taxonomy(db: Session = Depends(get_db)):
    """从 Shopify 官方 product-taxonomy 最新 release 同步中英文分类，不删除历史分类。"""
    zh_payload = _taxonomy_data("zh-CN")
    version = str(zh_payload.get("version") or "")[:30]
    zh_rows = _flat_taxonomy(zh_payload)
    en_payload = _taxonomy_data("en")
    version = version or str(en_payload.get("version") or "")[:30]
    en_rows = _flat_taxonomy(en_payload)
    if not zh_rows or not en_rows:
        fail("Shopify 官方分类文件为空", 502)
    values = []
    for gid, zh in zh_rows.items():
        en = en_rows.get(gid) or {}
        values.append({
            "taxonomy_gid": gid,
            "category_id": gid.rsplit("/", 1)[-1],
            "parent_gid": str(zh.get("parent_id") or ""),
            "level": int(zh.get("level") or 0),
            "name_zh": str(zh.get("name") or "")[:255],
            "full_name_zh": str(zh.get("full_name") or "")[:2000],
            "name_en": str(en.get("name") or "")[:255],
            "full_name_en": str(en.get("full_name") or "")[:2000],
            "is_leaf": 1 if zh.get("is_leaf") else 0,
            "is_active": 1,
            "version": version,
        })
    db.execute(update(ShopifyTaxonomyCategory).values(is_active=0))
    table = ShopifyTaxonomyCategory.__table__
    for start in range(0, len(values), 500):
        stmt = mysql_insert(table).values(values[start:start + 500])
        stmt = stmt.on_duplicate_key_update(
            category_id=stmt.inserted.category_id, parent_gid=stmt.inserted.parent_gid,
            level=stmt.inserted.level, name_zh=stmt.inserted.name_zh,
            full_name_zh=stmt.inserted.full_name_zh, name_en=stmt.inserted.name_en,
            full_name_en=stmt.inserted.full_name_en, is_leaf=stmt.inserted.is_leaf,
            is_active=1, version=stmt.inserted.version,
        )
        db.execute(stmt)
    db.commit()
    # 属性和属性值使用官方 attributes 分发文件；分类文件提供实际适用关系及扩展 handle。
    zh_attr_payload = _taxonomy_data("zh-CN", "attributes")
    en_attr_payload = _taxonomy_data("en", "attributes")
    zh_attrs, en_attrs = _flat_attributes(zh_attr_payload), _flat_attributes(en_attr_payload)
    del zh_attr_payload, en_attr_payload
    attribute_values = []
    for gid, zh in zh_attrs.items():
        en = en_attrs.get(gid) or {}
        attribute_values.append({"taxonomy_gid": gid, "handle": zh.get("handle", "")[:180],
                                 "name_zh": zh.get("name", "")[:255], "name_en": en.get("name", "")[:255],
                                 "description_zh": zh.get("description", "")[:2000],
                                 "description_en": en.get("description", "")[:2000],
                                 "is_active": 1, "version": version})
    db.execute(update(ShopifyTaxonomyAttribute).values(is_active=0))
    attr_table = ShopifyTaxonomyAttribute.__table__
    for start in range(0, len(attribute_values), 500):
        stmt = mysql_insert(attr_table).values(attribute_values[start:start + 500])
        stmt = stmt.on_duplicate_key_update(handle=stmt.inserted.handle, name_zh=stmt.inserted.name_zh,
            name_en=stmt.inserted.name_en, description_zh=stmt.inserted.description_zh,
            description_en=stmt.inserted.description_en, is_active=1, version=stmt.inserted.version)
        db.execute(stmt)
    db.commit()
    attr_ids = {gid: rid for gid, rid in db.execute(select(ShopifyTaxonomyAttribute.taxonomy_gid,
                                                           ShopifyTaxonomyAttribute.id))}
    taxonomy_value_rows = []
    for gid, zh in zh_attrs.items():
        en_values = {v["gid"]: v for v in (en_attrs.get(gid) or {}).get("values", [])}
        for value in zh.get("values", []):
            en_value = en_values.get(value["gid"]) or {}
            taxonomy_value_rows.append({"attribute_id": attr_ids[gid], "taxonomy_gid": value["gid"],
                "handle": value["handle"][:255], "name_zh": value["name"][:255],
                "name_en": en_value.get("name", "")[:255], "is_active": 1, "version": version})
    db.execute(update(ShopifyTaxonomyAttributeValue).values(is_active=0))
    value_table = ShopifyTaxonomyAttributeValue.__table__
    for start in range(0, len(taxonomy_value_rows), 500):
        stmt = mysql_insert(value_table).values(taxonomy_value_rows[start:start + 500])
        stmt = stmt.on_duplicate_key_update(attribute_id=stmt.inserted.attribute_id, handle=stmt.inserted.handle,
            name_zh=stmt.inserted.name_zh, name_en=stmt.inserted.name_en, is_active=1,
            version=stmt.inserted.version)
        db.execute(stmt)
    db.commit()
    category_ids = {gid: rid for gid, rid in db.execute(select(ShopifyTaxonomyCategory.taxonomy_gid,
                                                               ShopifyTaxonomyCategory.id))}
    db.execute(update(ShopifyTaxonomyCategoryAttribute).values(is_active=0))
    relation_values = []
    for category_gid, zh in zh_rows.items():
        en_by_key = {(a["gid"], a["handle"]): a for a in (en_rows.get(category_gid) or {}).get("attributes", [])}
        for item in zh.get("attributes", []):
            en_item = en_by_key.get((item["gid"], item["handle"])) or {}
            relation_values.append({"taxonomy_category_id": category_ids[category_gid],
                "taxonomy_attribute_id": attr_ids[item["gid"]], "handle": item["handle"][:180],
                "name_zh": item["name"][:255], "name_en": en_item.get("name", "")[:255],
                "description_zh": item["description"][:2000],
                "description_en": en_item.get("description", "")[:2000],
                "is_extended": 1 if item["extended"] else 0, "is_active": 1})
    relation_table = ShopifyTaxonomyCategoryAttribute.__table__
    for start in range(0, len(relation_values), 500):
        stmt = mysql_insert(relation_table).values(relation_values[start:start + 500])
        stmt = stmt.on_duplicate_key_update(taxonomy_attribute_id=stmt.inserted.taxonomy_attribute_id,
            name_zh=stmt.inserted.name_zh, name_en=stmt.inserted.name_en,
            description_zh=stmt.inserted.description_zh, description_en=stmt.inserted.description_en,
            is_extended=stmt.inserted.is_extended, is_active=1)
        db.execute(stmt)
    db.commit()
    inactive = db.scalar(select(func.count()).select_from(ShopifyTaxonomyCategory).where(
        ShopifyTaxonomyCategory.is_active == 0)) or 0
    return ok({"version": version, "imported": len(values), "inactive": int(inactive),
               "attributes": len(attribute_values), "attribute_values": len(taxonomy_value_rows),
               "category_attributes": len(relation_values)})


@router.get("/taxonomy")
def list_taxonomy(take: int = Query(50), skip: int = Query(0), sort: str | None = None,
                  filter: str | None = None, db: Session = Depends(get_db)):
    fields = {
        "id": (ShopifyTaxonomyCategory.id, "num"),
        "category_id": (ShopifyTaxonomyCategory.category_id, "str"),
        "level": (ShopifyTaxonomyCategory.level, "num"),
        "name_zh": (ShopifyTaxonomyCategory.name_zh, "str"),
        "full_name_zh": (ShopifyTaxonomyCategory.full_name_zh, "str"),
        "name_en": (ShopifyTaxonomyCategory.name_en, "str"),
        "full_name_en": (ShopifyTaxonomyCategory.full_name_en, "str"),
        "is_leaf": (ShopifyTaxonomyCategory.is_leaf, "bool"),
        "is_active": (ShopifyTaxonomyCategory.is_active, "bool"),
        "version": (ShopifyTaxonomyCategory.version, "str"),
        "updated_at": (ShopifyTaxonomyCategory.updated_at, "str"),
    }
    stmt = select(ShopifyTaxonomyCategory)
    condition = build_filter(parse_json(filter, "筛选"), fields)
    if condition is not None:
        stmt = stmt.where(condition)
    total = int(db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0)
    order = build_sort(parse_json(sort, "排序"), fields)
    skip, take = clamp_page(skip, take)
    rows = db.scalars(stmt.order_by(*(order or [ShopifyTaxonomyCategory.category_id]))
                      .offset(skip).limit(take)).all()
    return ok({"items": [_taxonomy_item(row) for row in rows], "total": total})


@router.get("/taxonomy/options")
def taxonomy_options(q: str = "", take: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    stmt = select(ShopifyTaxonomyCategory).where(ShopifyTaxonomyCategory.is_active == 1)
    q = q.strip()
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        term = "%" + escaped + "%"
        stmt = stmt.where(or_(ShopifyTaxonomyCategory.category_id.like(term, escape="\\"),
                              ShopifyTaxonomyCategory.full_name_zh.like(term, escape="\\"),
                              ShopifyTaxonomyCategory.full_name_en.like(term, escape="\\")))
    rows = db.scalars(stmt.order_by(ShopifyTaxonomyCategory.is_leaf.desc(),
                                    ShopifyTaxonomyCategory.full_name_zh).limit(take)).all()
    return ok([{"id": row.id, "category_id": row.category_id,
                "text": row.full_name_zh or row.full_name_en, "full_name_en": row.full_name_en,
                "is_leaf": bool(row.is_leaf)} for row in rows])


@router.get("/taxonomy/attributes")
def list_taxonomy_attributes(take: int = Query(50), skip: int = Query(0), sort: str | None = None,
                             filter: str | None = None, db: Session = Depends(get_db)):
    fields = {
        "id": (ShopifyTaxonomyAttribute.id, "num"), "taxonomy_gid": (ShopifyTaxonomyAttribute.taxonomy_gid, "str"),
        "handle": (ShopifyTaxonomyAttribute.handle, "str"), "name_zh": (ShopifyTaxonomyAttribute.name_zh, "str"),
        "name_en": (ShopifyTaxonomyAttribute.name_en, "str"), "is_active": (ShopifyTaxonomyAttribute.is_active, "bool"),
        "version": (ShopifyTaxonomyAttribute.version, "str"), "updated_at": (ShopifyTaxonomyAttribute.updated_at, "str"),
    }
    stmt = select(ShopifyTaxonomyAttribute)
    condition = build_filter(parse_json(filter, "筛选"), fields)
    if condition is not None:
        stmt = stmt.where(condition)
    total = int(db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0)
    order = build_sort(parse_json(sort, "排序"), fields)
    skip, take = clamp_page(skip, take)
    rows = list(db.scalars(stmt.order_by(*(order or [ShopifyTaxonomyAttribute.name_zh, ShopifyTaxonomyAttribute.id]))
                           .offset(skip).limit(take)))
    counts = dict(db.execute(select(ShopifyTaxonomyAttributeValue.attribute_id, func.count())
        .where(ShopifyTaxonomyAttributeValue.attribute_id.in_([row.id for row in rows]),
               ShopifyTaxonomyAttributeValue.is_active == 1)
        .group_by(ShopifyTaxonomyAttributeValue.attribute_id)).tuples().all()) if rows else {}
    return ok({"items": [{"id": row.id, "taxonomy_gid": row.taxonomy_gid, "handle": row.handle,
        "name_zh": row.name_zh, "name_en": row.name_en, "description_zh": row.description_zh,
        "description_en": row.description_en, "value_count": int(counts.get(row.id, 0)),
        "is_active": bool(row.is_active), "version": row.version, "updated_at": _fmt(row.updated_at)} for row in rows],
        "total": total})


@router.get("/taxonomy/attributes/{attribute_id}/values")
def list_taxonomy_attribute_values(attribute_id: int, take: int = Query(50), skip: int = Query(0),
                                   sort: str | None = None, filter: str | None = None,
                                   db: Session = Depends(get_db)):
    if not db.get(ShopifyTaxonomyAttribute, attribute_id):
        fail("Shopify 标准属性不存在", 404)
    fields = {
        "id": (ShopifyTaxonomyAttributeValue.id, "num"),
        "taxonomy_gid": (ShopifyTaxonomyAttributeValue.taxonomy_gid, "str"),
        "handle": (ShopifyTaxonomyAttributeValue.handle, "str"),
        "name_zh": (ShopifyTaxonomyAttributeValue.name_zh, "str"),
        "name_en": (ShopifyTaxonomyAttributeValue.name_en, "str"),
        "is_active": (ShopifyTaxonomyAttributeValue.is_active, "bool"),
        "version": (ShopifyTaxonomyAttributeValue.version, "str"),
    }
    stmt = select(ShopifyTaxonomyAttributeValue).where(ShopifyTaxonomyAttributeValue.attribute_id == attribute_id)
    condition = build_filter(parse_json(filter, "筛选"), fields)
    if condition is not None:
        stmt = stmt.where(condition)
    total = int(db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0)
    order = build_sort(parse_json(sort, "排序"), fields)
    skip, take = clamp_page(skip, take)
    rows = db.scalars(stmt.order_by(*(order or [ShopifyTaxonomyAttributeValue.name_zh,
                                                ShopifyTaxonomyAttributeValue.id])).offset(skip).limit(take))
    return ok({"items": [{"id": row.id, "taxonomy_gid": row.taxonomy_gid, "handle": row.handle,
        "name_zh": row.name_zh, "name_en": row.name_en, "is_active": bool(row.is_active),
        "version": row.version} for row in rows], "total": total})


def _local_category_paths(db: Session) -> tuple[list[ShopCategory], dict[int, str]]:
    rows = list(db.scalars(select(ShopCategory).order_by(ShopCategory.sort_order, ShopCategory.id)))
    by_id = {row.id: row for row in rows}
    paths = {}
    for row in rows:
        current, names, seen = row, [row.name], {row.id}
        while current.parent_id in by_id and current.parent_id not in seen:
            current = by_id[current.parent_id]
            seen.add(current.id)
            names.append(current.name)
        paths[row.id] = " / ".join(reversed(names))
    return rows, paths


@router.get("/category-maps")
def list_category_maps(db: Session = Depends(get_db)):
    categories, paths = _local_category_paths(db)
    mappings = {row.category_id: row for row in db.scalars(select(ShopifyCategoryMap))}
    taxonomy_ids = [row.taxonomy_category_id for row in mappings.values()]
    taxonomy = {row.id: row for row in db.scalars(select(ShopifyTaxonomyCategory).where(
        ShopifyTaxonomyCategory.id.in_(taxonomy_ids)))} if taxonomy_ids else {}
    items = []
    for category in sorted(categories, key=lambda row: paths[row.id]):
        mapping = mappings.get(category.id)
        target = taxonomy.get(mapping.taxonomy_category_id) if mapping else None
        items.append({
            "id": category.id, "category_id": category.id, "category_name": category.name,
            "category_full_name": paths[category.id], "taxonomy_category_id": target.id if target else None,
            "taxonomy_category_code": target.category_id if target else "",
            "taxonomy_full_name": (target.full_name_zh or target.full_name_en) if target else "",
            "taxonomy_active": bool(target.is_active) if target else False,
            "updated_at": _fmt(mapping.updated_at) if mapping else None,
        })
    return ok(items)


@router.put("/category-maps/{category_id}")
def bind_category(category_id: int, body: dict, db: Session = Depends(get_db)):
    if not db.get(ShopCategory, category_id):
        fail("mzShop 分类不存在", 404)
    try:
        taxonomy_id = int(body.get("taxonomy_category_id"))
    except (TypeError, ValueError):
        fail("请选择 Shopify 标准分类")
    target = db.get(ShopifyTaxonomyCategory, taxonomy_id)
    if not target or not target.is_active:
        fail("Shopify 标准分类不存在或已失效")
    mapping = db.scalar(select(ShopifyCategoryMap).where(ShopifyCategoryMap.category_id == category_id))
    if mapping:
        mapping.taxonomy_category_id = taxonomy_id
    else:
        db.add(ShopifyCategoryMap(category_id=category_id, taxonomy_category_id=taxonomy_id))
    db.commit()
    return ok({"category_id": category_id, "taxonomy_category_id": taxonomy_id,
               "taxonomy_full_name": target.full_name_zh or target.full_name_en})


@router.delete("/category-maps/{category_id}")
def unbind_category(category_id: int, db: Session = Depends(get_db)):
    mapping = db.scalar(select(ShopifyCategoryMap).where(ShopifyCategoryMap.category_id == category_id))
    if not mapping:
        fail("该分类尚未绑定 Shopify 标准分类", 404)
    db.delete(mapping)
    db.commit()
    return ok()


def _resolved_taxonomy_category(db: Session, category_id: int):
    current, seen = db.get(ShopCategory, category_id), set()
    while current and current.id not in seen:
        seen.add(current.id)
        mapping = db.scalar(select(ShopifyCategoryMap).where(ShopifyCategoryMap.category_id == current.id))
        if mapping:
            target = db.get(ShopifyTaxonomyCategory, mapping.taxonomy_category_id)
            if target and target.is_active:
                return target, current.id
        current = db.get(ShopCategory, current.parent_id) if current.parent_id else None
    return None, None


@router.get("/category-attributes")
def category_attributes(category_id: int, db: Session = Depends(get_db)):
    if not db.get(ShopCategory, category_id):
        fail("mzShop 分类不存在", 404)
    target, bound_category_id = _resolved_taxonomy_category(db, category_id)
    if not target:
        return ok({"taxonomy_category": None, "items": []})
    rows = db.execute(
        select(ShopifyTaxonomyCategoryAttribute, ShopifyTaxonomyAttribute)
        .join(ShopifyTaxonomyAttribute, ShopifyTaxonomyAttribute.id == ShopifyTaxonomyCategoryAttribute.taxonomy_attribute_id)
        .where(ShopifyTaxonomyCategoryAttribute.taxonomy_category_id == target.id,
               ShopifyTaxonomyCategoryAttribute.is_active == 1)
        .order_by(ShopifyTaxonomyCategoryAttribute.name_zh, ShopifyTaxonomyCategoryAttribute.id)
    ).all()
    maps = {m.category_attribute_id: m for m in db.scalars(select(ShopifyAttributeMap).where(
        ShopifyAttributeMap.category_id == category_id))}
    local_ids = [m.local_attribute_id for m in maps.values()]
    local_attrs = {a.id: a for a in db.scalars(select(ShopAttribute).where(ShopAttribute.id.in_(local_ids)))} if local_ids else {}
    items = []
    for relation, base in rows:
        mapping = maps.get(relation.id)
        local = local_attrs.get(mapping.local_attribute_id) if mapping else None
        value_count = db.scalar(select(func.count()).select_from(ShopifyTaxonomyAttributeValue).where(
            ShopifyTaxonomyAttributeValue.attribute_id == base.id,
            ShopifyTaxonomyAttributeValue.is_active == 1)) or 0
        items.append({"id": relation.id, "handle": relation.handle,
            "name_zh": relation.name_zh or base.name_zh, "name_en": relation.name_en or base.name_en,
            "description_zh": relation.description_zh or base.description_zh,
            "is_extended": bool(relation.is_extended), "value_count": int(value_count),
            "local_attribute_id": local.id if local else None, "local_attribute_name": local.name if local else "",
            "local_input_type": local.input_type if local else "", "mapped_value_count": len(mapping.value_map or {}) if mapping else 0})
    return ok({"taxonomy_category": {"id": target.id, "category_id": target.category_id,
        "full_name": target.full_name_zh or target.full_name_en, "bound_category_id": bound_category_id}, "items": items})


@router.get("/category-attributes/{relation_id}/mapping")
def attribute_mapping_detail(relation_id: int, category_id: int, db: Session = Depends(get_db)):
    relation = db.get(ShopifyTaxonomyCategoryAttribute, relation_id) or fail("Shopify 分类属性不存在", 404)
    if not db.get(ShopCategory, category_id):
        fail("mzShop 分类不存在", 404)
    local_attrs = applicable_attributes(db, category_id)
    values = db.scalars(select(ShopifyTaxonomyAttributeValue).where(
        ShopifyTaxonomyAttributeValue.attribute_id == relation.taxonomy_attribute_id,
        ShopifyTaxonomyAttributeValue.is_active == 1).order_by(ShopifyTaxonomyAttributeValue.name_zh)).all()
    mapping = db.scalar(select(ShopifyAttributeMap).where(
        ShopifyAttributeMap.category_id == category_id, ShopifyAttributeMap.category_attribute_id == relation_id))
    return ok({"local_attributes": [{"id": a.id, "name": a.name, "input_type": a.input_type,
                                      "options": a.options or []} for a in local_attrs],
               "taxonomy_values": [{"id": v.id, "taxonomy_gid": v.taxonomy_gid,
                                      "name": v.name_zh or v.name_en, "name_en": v.name_en} for v in values],
               "mapping": {"local_attribute_id": mapping.local_attribute_id,
                           "value_map": mapping.value_map or {}} if mapping else None})


@router.put("/category-attributes/{relation_id}/mapping")
def save_attribute_mapping(relation_id: int, body: dict, db: Session = Depends(get_db)):
    relation = db.get(ShopifyTaxonomyCategoryAttribute, relation_id) or fail("Shopify 分类属性不存在", 404)
    try:
        category_id, local_attribute_id = int(body.get("category_id")), int(body.get("local_attribute_id"))
    except (TypeError, ValueError):
        fail("分类或本地属性参数不正确")
    if not db.get(ShopCategory, category_id):
        fail("mzShop 分类不存在", 404)
    local = db.get(ShopAttribute, local_attribute_id)
    if not local or local.id not in {a.id for a in applicable_attributes(db, category_id)}:
        fail("本地属性不存在或不适用于该分类")
    raw_map = body.get("value_map") or {}
    if not isinstance(raw_map, dict):
        fail("属性值映射格式不正确")
    options = set(str(x) for x in (local.options or []))
    try:
        cleaned = {}
        for key, raw_values in raw_map.items():
            if str(key) not in options:
                continue
            values = raw_values if isinstance(raw_values, list) else [raw_values]
            values = list(dict.fromkeys(int(value) for value in values if value))
            if values:
                cleaned[str(key)] = values
    except (TypeError, ValueError):
        fail("属性值映射包含无效值")
    all_value_ids = {value for values in cleaned.values() for value in values}
    valid_value_ids = set(db.scalars(select(ShopifyTaxonomyAttributeValue.id).where(
        ShopifyTaxonomyAttributeValue.attribute_id == relation.taxonomy_attribute_id,
        ShopifyTaxonomyAttributeValue.is_active == 1, ShopifyTaxonomyAttributeValue.id.in_(all_value_ids)))) if all_value_ids else set()
    if valid_value_ids != all_value_ids:
        fail("部分 Shopify 属性值不存在或不属于该属性")
    mapping = db.scalar(select(ShopifyAttributeMap).where(
        ShopifyAttributeMap.category_id == category_id, ShopifyAttributeMap.category_attribute_id == relation_id))
    if not mapping:
        mapping = ShopifyAttributeMap(category_id=category_id, category_attribute_id=relation_id,
                                      local_attribute_id=local_attribute_id)
        db.add(mapping)
    mapping.local_attribute_id = local_attribute_id
    mapping.value_map = cleaned
    db.commit()
    return ok({"category_id": category_id, "category_attribute_id": relation_id,
               "local_attribute_id": local_attribute_id, "value_map": cleaned})


@router.delete("/category-attributes/{relation_id}/mapping")
def delete_attribute_mapping(relation_id: int, category_id: int, db: Session = Depends(get_db)):
    mapping = db.scalar(select(ShopifyAttributeMap).where(
        ShopifyAttributeMap.category_id == category_id, ShopifyAttributeMap.category_attribute_id == relation_id))
    if not mapping:
        fail("该属性尚未建立映射", 404)
    db.delete(mapping)
    db.commit()
    return ok()


@router.get("/stores/{sid}")
def get_config(sid: int, db: Session = Depends(get_db)):
    _shopify_store(db, sid)
    c = db.scalar(select(ShopifyStoreConfig).where(ShopifyStoreConfig.store_id == sid))
    regions = [{"id": r.id, "name": r.name} for r in db.scalars(select(GeoRegion).order_by(GeoRegion.sort_order, GeoRegion.id))]
    languages = [{"code": x.code, "name": x.name, "default": bool(x.is_default)} for x in db.scalars(
        select(ShopLanguage).where(ShopLanguage.status == 1).order_by(ShopLanguage.sort_order, ShopLanguage.id))]
    locations = [{"id": x.id, "name": x.name} for x in db.scalars(select(StockLocation).where(
        StockLocation.status == 1).order_by(StockLocation.id))]
    return ok({"config": _dict(c), "regions": regions, "languages": languages, "stock_locations": locations})


@router.put("/stores/{sid}")
def save_config(sid: int, body: dict, db: Session = Depends(get_db)):
    _shopify_store(db, sid)
    try:
        domain = normalize_domain(body.get("shop_domain"))
    except ShopifyError as e:
        fail(str(e))
    try:
        region_id = int(body.get("region_id"))
    except (TypeError, ValueError):
        fail("请选择价格区域")
    if not db.get(GeoRegion, region_id):
        fail("价格区域不存在")
    lang = str(body.get("language_code") or "").strip()
    if lang and not db.scalar(select(ShopLanguage.id).where(ShopLanguage.code == lang, ShopLanguage.status == 1)):
        fail("商品语言不存在或未启用")
    c = db.scalar(select(ShopifyStoreConfig).where(ShopifyStoreConfig.store_id == sid))
    domain_changed = c is None or c.shop_domain != domain
    if not c:
        c = ShopifyStoreConfig(store_id=sid, shop_domain=domain, region_id=region_id)
        db.add(c)
    c.shop_domain = domain
    c.region_id = region_id
    c.language_code = lang
    c.default_location_gid = str(body.get("default_location_gid") or "").strip()
    try:
        stock_location_id = int(body.get("stock_location_id") or 0)
    except (TypeError, ValueError):
        fail("本地库存地点参数不正确")
    if stock_location_id and not db.get(StockLocation, stock_location_id):
        fail("本地库存地点不存在")
    c.stock_location_id = stock_location_id
    c.publication_gid = str(body.get("publication_gid") or "").strip()
    c.currency = str(body.get("currency") or "").strip().upper()
    if c.currency and (len(c.currency) != 3 or not c.currency.isalpha()):
        fail("币种应为 3 位字母编码")
    c.sync_enabled = 1 if body.get("sync_enabled", True) else 0
    if domain_changed:
        c.connection_status = "unchecked"
        c.shop_gid = ""
        c.last_connected_at = None
        c.last_error = None
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fail("该 Shopify 域名已绑定其它店铺")
    db.refresh(c)
    return ok(_dict(c))


@router.post("/stores/{sid}/test")
def test_connection(sid: int, body: dict | None = None, db: Session = Depends(get_db)):
    _shopify_store(db, sid)
    c = db.scalar(select(ShopifyStoreConfig).where(ShopifyStoreConfig.store_id == sid))
    raw_domain = (body or {}).get("shop_domain") or (c.shop_domain if c else "")
    try:
        domain = normalize_domain(raw_domain)
        data, request_id = graphql(domain, CONNECTION_QUERY)
    except ShopifyError as e:
        if c:
            c.connection_status, c.last_error = "error", str(e)[:2000]
            db.commit()
        fail(str(e), 502)
    shop = data.get("shop") or {}
    scopes = {x.get("handle") for x in (data.get("currentAppInstallation") or {}).get("accessScopes", [])}
    required = {"write_products", "write_inventory", "read_locations", "read_publications", "read_orders",
                "read_metaobjects", "write_metaobjects", "read_metaobject_definitions",
                "write_metaobject_definitions"}
    missing = sorted(required - scopes)
    if c:
        c.shop_gid = str(shop.get("id") or "")
        c.currency = str(shop.get("currencyCode") or c.currency or "")
        c.connection_status = "ok" if not missing else "error"
        c.last_connected_at = datetime.now()
        c.last_error = ("缺少权限：" + "、".join(missing)) if missing else None
        db.commit()
    return ok({"shop": shop, "locations": (data.get("locations") or {}).get("nodes", []),
               "publications": (data.get("publications") or {}).get("nodes", []),
               "scopes": sorted(scopes), "missing_scopes": missing, "request_id": request_id})


@router.post("/stores/{sid}/webhooks/register")
def register_webhooks(sid: int, db: Session = Depends(get_db)):
    _shopify_store(db, sid)
    cfg = db.scalar(select(ShopifyStoreConfig).where(ShopifyStoreConfig.store_id == sid))
    if not cfg or cfg.connection_status != "ok": fail("请先完成 Shopify 连接测试")
    if not SHOPIFY_WEBHOOK_BASE_URL.lower().startswith("https://"):
        fail("请先配置公网可信 HTTPS 的 SHOPIFY_WEBHOOK_BASE_URL")
    uri = SHOPIFY_WEBHOOK_BASE_URL + "/api/v1/shopify/webhooks"
    data, _ = graphql(cfg.shop_domain, WEBHOOK_LIST)
    existing = {(x.get("topic"), x.get("uri")) for x in (data.get("webhookSubscriptions") or {}).get("nodes", [])}
    topics = ["ORDERS_CREATE", "ORDERS_UPDATED", "ORDERS_CANCELLED", "ORDERS_PAID",
              "FULFILLMENTS_CREATE", "FULFILLMENTS_UPDATE", "REFUNDS_CREATE"]
    created, skipped = [], []
    for topic in topics:
        if (topic, uri) in existing:
            skipped.append(topic); continue
        payload, _ = graphql(cfg.shop_domain, WEBHOOK_CREATE, {"topic": topic, "input": {"uri": uri}})
        errors = (payload.get("webhookSubscriptionCreate") or {}).get("userErrors") or []
        if errors: fail("；".join(x.get("message") or str(x) for x in errors), 502)
        created.append(topic)
    return ok({"uri": uri, "created": created, "skipped": skipped})


def _enqueue(db: Session, goods_ids: list[int], store_ids: list[int] | None) -> dict:
    goods_ids = sorted({int(x) for x in goods_ids if int(x) > 0})
    if not goods_ids:
        fail("请选择商品")
    found = set(db.scalars(select(ShopGoods.id).where(ShopGoods.id.in_(goods_ids))))
    if found != set(goods_ids):
        fail("部分商品不存在")
    sku_goods = set(db.scalars(select(ShopGoodsSku.goods_id).where(
        ShopGoodsSku.goods_id.in_(goods_ids), ShopGoodsSku.status == 1).distinct()))
    missing_sku = len(set(goods_ids) - sku_goods)
    if missing_sku:
        fail(f"选中商品中有 {missing_sku} 个没有启用的 SKU，不能推送库存")
    stmt = (select(ShopGoodsStore.goods_id, ShopGoodsStore.store_id)
            .join(ShopifyStoreConfig, ShopifyStoreConfig.store_id == ShopGoodsStore.store_id)
            .where(ShopGoodsStore.goods_id.in_(goods_ids), ShopGoodsStore.allowed == 1,
                   ShopifyStoreConfig.sync_enabled == 1, ShopifyStoreConfig.connection_status == "ok"))
    if store_ids:
        stmt = stmt.where(ShopGoodsStore.store_id.in_({int(x) for x in store_ids}))
    pairs = list(db.execute(stmt))
    if not pairs:
        bound = db.scalar(select(func.count()).select_from(ShopGoodsStore).where(
            ShopGoodsStore.goods_id.in_(goods_ids), ShopGoodsStore.allowed == 1)) or 0
        if not bound:
            fail("选中商品没有绑定可以上架的 Shopify 店铺")
        configured = db.scalar(select(func.count()).select_from(ShopifyStoreConfig).where(
            ShopifyStoreConfig.store_id.in_(select(ShopGoodsStore.store_id).where(
                ShopGoodsStore.goods_id.in_(goods_ids), ShopGoodsStore.allowed == 1)))) or 0
        if not configured:
            fail("Shopify 店铺尚未配置")
        fail("Shopify 店铺未启用或连接状态不是正常，请先在店铺管理中测试连接")
    created = skipped = 0
    for gid, sid in pairs:
        goods = db.get(ShopGoods, gid)
        link = db.scalar(select(ShopGoodsStore).where(
            ShopGoodsStore.goods_id == gid, ShopGoodsStore.store_id == sid))
        active = db.scalar(select(func.count()).select_from(ShopifySyncTask).where(
            ShopifySyncTask.goods_id == gid, ShopifySyncTask.store_id == sid,
            ShopifySyncTask.status.in_(("pending", "running"))))
        if active:
            skipped += 1
            continue
        db.add(ShopifySyncTask(store_id=sid, goods_id=gid, action="upsert_product",
                               status="pending", max_retries=SHOPIFY_MAX_RETRIES))
        created += 1
    db.commit()
    return {"created": created, "skipped": skipped, "eligible": len(pairs)}


@router.post("/goods/{gid}/enqueue")
def enqueue_one(gid: int, body: dict | None = None, db: Session = Depends(get_db)):
    return ok(_enqueue(db, [gid], (body or {}).get("store_ids")))


@router.post("/goods/batch-enqueue")
def enqueue_batch(body: dict, db: Session = Depends(get_db)):
    if not isinstance(body.get("ids"), list):
        fail("商品参数不正确")
    return ok(_enqueue(db, body["ids"], body.get("store_ids")))


@router.get("/goods/{gid}/status")
def goods_status(gid: int, db: Session = Depends(get_db)):
    rows = list(db.execute(select(ShopifyProductMap, Store).join(Store, Store.id == ShopifyProductMap.store_id)
                           .where(ShopifyProductMap.goods_id == gid).order_by(Store.name)))
    return ok([{"store_id": m.store_id, "store_name": s.name, "product_gid": m.product_gid,
                "sync_status": m.sync_status, "last_synced_at": _fmt(m.last_synced_at),
                "last_error": m.last_error or ""} for m, s in rows])


@router.get("/tasks")
def list_tasks(take: int = Query(50), skip: int = Query(0), sort: str | None = None,
               filter: str | None = None, db: Session = Depends(get_db)):
    fields = {
        "id": (ShopifySyncTask.id, "num"), "goods_id": (ShopifySyncTask.goods_id, "num"),
        "goods_no": (ShopGoods.goods_no, "str"), "goods_name": (ShopGoods.name, "str"),
        "store_id": (ShopifySyncTask.store_id, "num"), "store_name": (Store.name, "str"),
        "action": (ShopifySyncTask.action, "str"), "status": (ShopifySyncTask.status, "str"),
        "retry_count": (ShopifySyncTask.retry_count, "num"),
        "created_at": (ShopifySyncTask.created_at, "str"),
        "started_at": (ShopifySyncTask.started_at, "str"),
        "finished_at": (ShopifySyncTask.finished_at, "str"),
        "request_id": (ShopifySyncTask.request_id, "str"),
        "error_message": (ShopifySyncTask.error_message, "str"),
    }
    stmt = (select(ShopifySyncTask, ShopGoods.goods_no, ShopGoods.name, Store.name)
            .join(ShopGoods, ShopGoods.id == ShopifySyncTask.goods_id)
            .join(Store, Store.id == ShopifySyncTask.store_id))
    condition = build_filter(parse_json(filter, "筛选"), fields)
    if condition is not None:
        stmt = stmt.where(condition)
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = int(db.scalar(count_stmt) or 0)
    order = build_sort(parse_json(sort, "排序"), fields)
    stmt = stmt.order_by(*(order or [ShopifySyncTask.id.desc()]))
    skip, take = clamp_page(skip, take)
    rows = db.execute(stmt.offset(skip).limit(take)).all()
    items = [{"id": t.id, "goods_id": t.goods_id, "goods_no": goods_no, "goods_name": goods_name,
              "store_id": t.store_id, "store_name": store_name, "action": t.action, "status": t.status,
              "retry_count": t.retry_count, "max_retries": t.max_retries,
              "next_retry_at": _fmt(t.next_retry_at), "started_at": _fmt(t.started_at),
              "finished_at": _fmt(t.finished_at), "created_at": _fmt(t.created_at),
              "request_id": t.request_id, "error_message": t.error_message or ""}
             for t, goods_no, goods_name, store_name in rows]
    return ok({"items": items, "total": total})


@router.post("/tasks/{task_id}/retry")
def retry_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(ShopifySyncTask, task_id) or fail("同步任务不存在", 404)
    if task.status not in ("failed", "cancelled"):
        fail("只有失败或已取消的任务可以重试")
    active = db.scalar(select(func.count()).select_from(ShopifySyncTask).where(
        ShopifySyncTask.goods_id == task.goods_id, ShopifySyncTask.store_id == task.store_id,
        ShopifySyncTask.status.in_(("pending", "running")))) or 0
    if active:
        fail("该商品和店铺已有等待或执行中的任务")
    task.status = "pending"
    task.retry_count = 0
    task.next_retry_at = None
    task.locked_at = task.started_at = task.finished_at = None
    task.request_id = ""
    task.error_message = None
    db.commit()
    return ok({"id": task.id, "status": task.status})


@router.post("/tasks/batch-retry")
def batch_retry_tasks(body: dict, db: Session = Depends(get_db)):
    raw = body.get("ids")
    if not isinstance(raw, list) or not 1 <= len(raw) <= 500:
        fail("请选择 1~500 个同步任务")
    try:
        ids = list(dict.fromkeys(int(x) for x in raw if not isinstance(x, bool) and int(x) > 0))
    except (TypeError, ValueError):
        fail("同步任务参数不正确")
    tasks = {t.id: t for t in db.scalars(select(ShopifySyncTask).where(
        ShopifySyncTask.id.in_(ids)).order_by(ShopifySyncTask.id.desc()))}
    updated = skipped = 0
    active_pairs = set(db.execute(select(ShopifySyncTask.goods_id, ShopifySyncTask.store_id).where(
        ShopifySyncTask.status.in_(("pending", "running")))).all())
    for task_id in ids:
        task = tasks.get(task_id)
        if not task or task.status not in ("failed", "cancelled"):
            skipped += 1
            continue
        pair = (task.goods_id, task.store_id)
        if pair in active_pairs:
            skipped += 1
            continue
        task.status = "pending"
        task.retry_count = 0
        task.next_retry_at = None
        task.locked_at = task.started_at = task.finished_at = None
        task.request_id = ""
        task.error_message = None
        active_pairs.add(pair)
        updated += 1
    db.commit()
    return ok({"updated": updated, "skipped": skipped})


@router.delete("/tasks/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(ShopifySyncTask, task_id) or fail("同步任务不存在", 404)
    if task.status in ("pending", "running"):
        fail("等待中或处理中的任务不能删除")
    db.delete(task)
    db.commit()
    return ok()
