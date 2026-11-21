"""自有商品目录：分类、属性、商品（含图片、SKU）、图片上传。响应 {code, data, msg}。"""
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import case, delete, func, select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..attr_dict import normalize_currency
from ..catalog import ancestor_ids, applicable_attributes, is_leaf
from ..config import BASE_DIR
from ..db import get_db
from ..deps import require_user
from .shop_i18n import inline_languages, load_inline, purge_translations, save_inline
from ..listquery import build_filter, build_sort, clamp_page, parse_json
from ..models import (
    Brand, BundleComponent, BundleRevision, GeoRegion, GoodsNoSequence, Platform, ShippingPackageGroup, ShippingTemplate, ShopAttribute, ShopCategory, ShopGoods, ShopGoodsImage, ShopGoodsRegion,
    ShopOrderLine,
    ShopGoodsSku, ShopGoodsSkuRegion, ShopGoodsStore, ShopTranslation, ShopifyProductMap, ShopifySyncTask, ShopifyVariantMap,
    StockBalance, StockLedger, Store, StoreCategory, Supplier, SupplierCatalogItem,
)

router = APIRouter(prefix="/api/v1/shop", dependencies=[Depends(require_user)])

INPUT_TYPES = {"text": "文本", "textarea": "多行文本", "select": "单选", "multiselect": "多选", "number": "数字"}
OPTION_TYPES = ("select", "multiselect")  # 有可选值的录入方式
MAX_DECIMALS = 6
MAX_IMAGES = 20
MAX_UPLOAD = 5 * 1024 * 1024
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
# 扩展名 → 文件头校验，不信任客户端给的 content-type
IMAGE_MAGIC = {
    ".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",), ".png": (b"\x89PNG\r\n\x1a\n",),
    ".gif": (b"GIF87a", b"GIF89a"), ".webp": (b"RIFF",),
}


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


def _money(values: dict, f: str, label: str) -> Decimal:
    raw = values.get(f)
    if raw in (None, ""):
        return Decimal("0.00")
    try:
        d = Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        fail(f"{label}格式不正确")
    if d < 0 or d > Decimal("9999999999.99"):
        fail(f"{label}超出范围")
    return d


def _int(values: dict, f: str, label: str, lo: int = 0, hi: int = 2_000_000_000, default: int = 0) -> int:
    raw = values.get(f)
    if raw in (None, ""):
        return default
    try:
        n = int(raw)
    except (TypeError, ValueError):
        fail(f"{label}需为整数")
    if not lo <= n <= hi:
        fail(f"{label}需在 {lo}~{hi} 之间")
    return n


def _commit(db: Session, dup_msg: str):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fail(dup_msg)


def _save(db: Session, dup_msg: str, entity_type: str, entity, values: dict) -> None:
    """flush（检查唯一约束）→ 保存随行译文 values["i18n"] → commit；任何一步失败整体回滚。"""
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        fail(dup_msg)
    save_inline(db, entity_type, entity, values.get("i18n"))
    db.commit()


def _attach(db: Session, entity_type: str, dicts: list[dict], fields: list[str]) -> list[dict]:
    """给输出字典挂上启用语言的译文 i18n: {语言: {字段: 值}}，缺译为空值，列表/表单可直接绑定。"""
    m = load_inline(db, entity_type, [d["id"] for d in dicts], fields)
    for d in dicts:
        d["i18n"] = m[d["id"]]
    return dicts


# ---------------------------------------------------------------- 分类
def _category_paths(db: Session) -> tuple[list[ShopCategory], dict[int, str]]:
    rows = db.scalars(select(ShopCategory).order_by(ShopCategory.sort_order, ShopCategory.id)).all()
    by_id = {c.id: c for c in rows}

    def path(c: ShopCategory) -> str:
        names, seen = [c.name], {c.id}
        while c.parent_id in by_id and c.parent_id not in seen:
            c = by_id[c.parent_id]
            seen.add(c.id)
            names.append(c.name)
        return " / ".join(reversed(names))

    return rows, {c.id: path(c) for c in rows}


def _category_dict(c: ShopCategory, full_name: str) -> dict:
    return {"id": c.id, "parent_id": c.parent_id, "code": c.code or "", "name": c.name, "full_name": full_name, "sort_order": c.sort_order,
            "status": bool(c.status), "created_at": _fmt(c.created_at)}


def _descendants(db: Session, cid: int) -> set[int]:
    rows = db.execute(select(ShopCategory.id, ShopCategory.parent_id)).all()
    children: dict[int, list[int]] = {}
    for i, p in rows:
        children.setdefault(p, []).append(i)
    out, stack = set(), [cid]
    while stack:
        for ch in children.get(stack.pop(), []):
            if ch not in out:
                out.add(ch)
                stack.append(ch)
    return out


def _apply_category(db: Session, c: ShopCategory, values: dict, creating: bool) -> None:
    if "code" in values or creating:
        c.code = _text(values, "code", "品类编码", 50) or None
    if "name" in values or creating:
        c.name = _text(values, "name", "分类名称", 100, required=True)
    if "parent_id" in values or creating:
        pid = _int(values, "parent_id", "上级分类")
        if pid and db.get(ShopCategory, pid) is None:
            fail("上级分类不存在")
        if c.id and (pid == c.id or pid in _descendants(db, c.id)):
            fail("上级分类不能是自己或自己的下级")
        # 商品只能挂末级分类：已经挂了商品的分类不能再长子分类
        if pid and (c.id is None or pid != c.parent_id) and db.scalar(
                select(ShopGoods.id).where(ShopGoods.category_id == pid).limit(1)):
            fail("上级分类下已有商品，不能再添加子分类；请先把商品移到其它分类")
        c.parent_id = pid
    if "sort_order" in values or creating:
        c.sort_order = _int(values, "sort_order", "排序", -1_000_000, 1_000_000)
    if "status" in values:
        c.status = 1 if values["status"] else 0
    elif creating:
        c.status = 1


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    rows, paths = _category_paths(db)
    items = [_category_dict(c, paths[c.id]) for c in sorted(rows, key=lambda c: paths[c.id])]
    return ok(_attach(db, "category", items, ["name"]))


@router.post("/categories")
def create_category(values: dict, db: Session = Depends(get_db)):
    c = ShopCategory()
    _apply_category(db, c, values, True)
    db.add(c)
    _save(db, "同一上级下分类名称已存在", "category", c, values)
    return ok(_attach(db, "category", [_category_dict(c, c.name)], ["name"])[0])


@router.put("/categories/{cid}")
def update_category(cid: int, values: dict, db: Session = Depends(get_db)):
    c = db.get(ShopCategory, cid) or fail("分类不存在", 404)
    _apply_category(db, c, values, False)
    _save(db, "同一上级下分类名称已存在", "category", c, values)
    return ok(_attach(db, "category", [_category_dict(c, c.name)], ["name"])[0])


@router.delete("/categories/{cid}")
def delete_category(cid: int, db: Session = Depends(get_db)):
    c = db.get(ShopCategory, cid) or fail("分类不存在", 404)
    if db.scalar(select(func.count()).select_from(ShopCategory).where(ShopCategory.parent_id == cid)):
        fail("该分类下还有子分类，不能删除")
    if db.scalar(select(func.count()).select_from(ShopGoods).where(ShopGoods.category_id == cid)):
        fail("该分类下还有商品，不能删除")
    # 属性可挂在多个分类：只摘掉该分类；摘完不再适用任何分类的属性连同译文一起删
    for a in db.scalars(select(ShopAttribute)).all():
        cats = list(a.category_ids or [])
        if cid not in cats:
            continue
        rest = [c for c in cats if c != cid]
        if rest:
            a.category_ids = rest
        else:
            purge_translations(db, "attribute", [a.id])
            db.delete(a)
    from ..models import ShopifyAttributeMap, ShopifyCategoryMap
    db.execute(delete(StoreCategory).where(StoreCategory.category_id == cid))
    db.execute(delete(ShopifyCategoryMap).where(ShopifyCategoryMap.category_id == cid))
    db.execute(delete(ShopifyAttributeMap).where(ShopifyAttributeMap.category_id == cid))
    purge_translations(db, "category", [cid])
    db.delete(c)
    db.commit()
    return ok()


# ---------------------------------------------------------------- 属性定义
def _attr_dict(a: ShopAttribute) -> dict:
    return {"id": a.id, "category_ids": a.category_ids or [], "name": a.name, "input_type": a.input_type,
            "options": a.options or [], "decimal_places": a.decimal_places, "unit": a.unit,
            "is_required": bool(a.is_required), "sort_order": a.sort_order, "status": bool(a.status)}


def _attr_category_ids(db: Session, raw) -> list[int]:
    """适用分类：id 数组，去重排序；空数组 = 所有分类通用。"""
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        fail("适用分类格式不正确")
    ids: list[int] = []
    for x in raw:
        try:
            cid = int(x)
        except (TypeError, ValueError):
            fail("适用分类格式不正确")
        if cid > 0 and cid not in ids:
            ids.append(cid)
    if ids and len(set(db.scalars(select(ShopCategory.id).where(ShopCategory.id.in_(ids))))) != len(ids):
        fail("适用分类不存在")
    return sorted(ids)


def _check_attr_name(db: Session, a: ShopAttribute) -> None:
    """同名属性不能有完全相同的适用分类集合；不同层级同名是允许的（就近一级生效）。"""
    cats = sorted(a.category_ids or [])
    rows = db.scalars(select(ShopAttribute).where(ShopAttribute.name == a.name).execution_options(autoflush=False))
    for other in rows:
        if other is a or (a.id is not None and other.id == a.id):
            continue
        if sorted(other.category_ids or []) == cats:
            fail("相同适用分类下已有同名属性")


def _apply_attr(db: Session, a: ShopAttribute, values: dict, creating: bool) -> None:
    if "category_ids" in values or creating:
        a.category_ids = _attr_category_ids(db, values.get("category_ids"))
    if "name" in values or creating:
        a.name = _text(values, "name", "属性名称", 100, required=True)
    if "input_type" in values or creating:
        t = str(values.get("input_type") or "text")
        if t not in INPUT_TYPES:
            fail("不支持的录入方式")
        a.input_type = t
    if "options" in values or creating:
        opts = values.get("options") or []
        if not isinstance(opts, list):
            fail("可选值格式不正确")
        opts = list(dict.fromkeys(str(o).strip() for o in opts if str(o).strip()))
        if any(len(o) > 100 for o in opts):
            fail("单个可选值最长 100 个字符")
        a.options = opts
    if a.input_type in OPTION_TYPES and not a.options:
        fail("单选 / 多选属性至少需要一个可选值")
    if a.input_type not in OPTION_TYPES:
        a.options = None
    # 数字属性：小数位数（0=整数）和单位（默认语言；其它语言的单位走译文）。非数字属性这两项恒为默认值
    if a.input_type == "number":
        if "decimal_places" in values or creating:
            a.decimal_places = _int(values, "decimal_places", "小数位数", 0, MAX_DECIMALS)
        if "unit" in values or creating:
            a.unit = _text(values, "unit", "单位", 30)
    else:
        a.decimal_places, a.unit = 0, ""
    if "is_required" in values:
        a.is_required = 1 if values["is_required"] else 0
    elif creating:
        a.is_required = 0
    if "sort_order" in values or creating:
        a.sort_order = _int(values, "sort_order", "排序", -1_000_000, 1_000_000)
    if "status" in values:
        a.status = 1 if values["status"] else 0
    elif creating:
        a.status = 1


@router.get("/attributes")
def list_attributes(category_id: int | None = None, db: Session = Depends(get_db)):
    """category_id 给定时返回「通用 + 该分类」且启用的属性（商品录入用），否则返回全部（管理用）。"""
    if category_id is not None:  # 含从上级分类继承来的属性，见 catalog.py
        rows = applicable_attributes(db, category_id)
    else:
        rows = db.scalars(select(ShopAttribute).order_by(ShopAttribute.sort_order, ShopAttribute.id))
    return ok(_attach(db, "attribute", [_attr_dict(a) for a in rows], ["name", "options", "unit"]))


@router.post("/attributes")
def create_attribute(values: dict, db: Session = Depends(get_db)):
    a = ShopAttribute()
    _apply_attr(db, a, values, True)
    _check_attr_name(db, a)
    db.add(a)
    _save(db, "该分类下已有同名属性", "attribute", a, values)
    return ok(_attach(db, "attribute", [_attr_dict(a)], ["name", "options", "unit"])[0])


@router.put("/attributes/{aid}")
def update_attribute(aid: int, values: dict, db: Session = Depends(get_db)):
    a = db.get(ShopAttribute, aid) or fail("属性不存在", 404)
    old_options = list(a.options or [])
    _apply_attr(db, a, values, False)
    _check_attr_name(db, a)
    i18n = values.get("i18n") if isinstance(values.get("i18n"), dict) else {}
    if list(a.options or []) != old_options and not any(isinstance(f, dict) and "options" in f for f in i18n.values()):
        purge_translations(db, "attribute", [a.id], "options")  # 可选值变了又没带新译文：旧译文按序号对应已错位，清掉
    _save(db, "该分类下已有同名属性", "attribute", a, values)
    return ok(_attach(db, "attribute", [_attr_dict(a)], ["name", "options", "unit"])[0])


@router.post("/attributes/move")
def move_attribute(body: dict, db: Session = Depends(get_db)):
    """拖动排序：把 id 移到 target_id 之前（after=false）或之后（after=true），并把全部属性的排序值按新顺序重排（10、20、30…）。"""
    aid, tid = body.get("id"), body.get("target_id")
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in (aid, tid)) or aid == tid:
        fail("参数不合法")
    rows = list(db.scalars(select(ShopAttribute).order_by(ShopAttribute.sort_order, ShopAttribute.id)))
    moving = next((r for r in rows if r.id == aid), None)
    if moving is None or not any(r.id == tid for r in rows):
        fail("属性不存在", 404)
    rows.remove(moving)
    pos = next(i for i, r in enumerate(rows) if r.id == tid)
    rows.insert(pos + 1 if body.get("after") else pos, moving)
    for i, r in enumerate(rows):
        r.sort_order = (i + 1) * 10
    db.commit()
    return ok()


@router.delete("/attributes/{aid}")
def delete_attribute(aid: int, db: Session = Depends(get_db)):
    a = db.get(ShopAttribute, aid) or fail("属性不存在", 404)
    from ..models import ShopifyAttributeMap
    db.execute(delete(ShopifyAttributeMap).where(ShopifyAttributeMap.local_attribute_id == aid))
    purge_translations(db, "attribute", [a.id])
    db.delete(a)  # 已录入商品的属性值留在商品 attr_values 里，不清理
    db.commit()
    return ok()


# ---------------------------------------------------------------- 商品
def _margin(g: ShopGoods) -> float | None:
    """毛利率 = (销售价 - 拿货价 - 运费) / 销售价；销售价为 0 时无意义。"""
    if not g.sale_price:
        return None
    return round(float((g.sale_price - g.cost_price - g.shipping_fee) / g.sale_price * 100), 1)


def _goods_dict(g: ShopGoods, sku_count: int = 0, stock: int = 0) -> dict:
    return {
        "id": g.id, "goods_no": g.goods_no, "name": g.name, "category_id": g.category_id,
        "brand": g.brand, "brand_id": g.brand_id, "supplier": g.supplier, "supplier_id": g.supplier_id,
        "source_url": g.source_url, "main_image_url": g.main_image_url,
        "cost_price": float(g.cost_price), "sale_price": float(g.sale_price), "shipping_fee": float(g.shipping_fee),
        "profit": float(g.sale_price - g.cost_price - g.shipping_fee), "margin_pct": _margin(g),
        "weight_g": g.weight_g, "shipping_package_group_id": g.shipping_package_group_id,
        "status": bool(g.status), "sku_count": sku_count, "stock": stock,
        "created_at": _fmt(g.created_at), "updated_at": _fmt(g.updated_at),
    }


def _number_text(a: ShopAttribute, v: str) -> str:
    """数字属性的值：必须是数字，小数位数不能超过定义；统一存成固定小数位的文本（0 位就是整数，如 "30"）。"""
    try:
        d = Decimal(v)
    except InvalidOperation:
        fail(f"属性「{a.name}」需为数字")
    if not d.is_finite() or abs(d) >= Decimal("1e12"):
        fail(f"属性「{a.name}」的数值超出范围")
    q = Decimal(1).scaleb(-a.decimal_places)
    if d != d.quantize(q):
        fail(f"属性「{a.name}」最多 {a.decimal_places} 位小数" if a.decimal_places else f"属性「{a.name}」需为整数")
    return format(d.quantize(q), "f")


def _check_attr_values(db: Session, category_id: int, raw) -> dict:
    """属性值按当前分类适用的、启用的属性定义校验：必填、单选值须在可选值内；未定义的属性名丢弃。"""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for a in applicable_attributes(db, category_id):
        if a.input_type == "multiselect":  # 多选：值是可选值的列表（按可选值的顺序存）
            got = raw.get(a.name)
            got = got if isinstance(got, list) else ([] if got in (None, "") else [got])
            picked = {str(x).strip() for x in got if str(x).strip()}
            if any(x not in (a.options or []) for x in picked):
                fail(f"属性「{a.name}」的值不在可选范围内")
            if not picked:
                if a.is_required:
                    fail(f"属性「{a.name}」必填")
                continue
            out[a.name] = [o for o in (a.options or []) if o in picked]
            continue
        v = str(raw.get(a.name) or "").strip()
        if not v:
            if a.is_required:
                fail(f"属性「{a.name}」必填")
            continue
        limit = 2000 if a.input_type == "textarea" else 200
        if len(v) > limit:
            fail(f"属性「{a.name}」最长 {limit} 个字符")
        if a.input_type == "select" and v not in (a.options or []):
            fail(f"属性「{a.name}」的值不在可选范围内")
        if a.input_type == "number":
            v = _number_text(a, v)
        out[a.name] = v
    return out


def _check_images(db: Session, goods_id: int, raw) -> list[dict]:
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_IMAGES:
        fail(f"图片最多 {MAX_IMAGES} 张")
    images = []
    seen = set()
    for item in raw:
        if isinstance(item, dict):
            u = str(item.get("url") or "").strip()
            try:
                sku_id = int(item.get("sku_id")) if item.get("sku_id") not in (None, "", 0, "0") else None
            except (TypeError, ValueError):
                fail("图片关联的 SKU 不合法")
        else:
            u, sku_id = str(item).strip(), None
        if not u:
            continue
        if len(u) > 500 or not (u.startswith("/static/uploads/") or u.lower().startswith(("http://", "https://"))):
            fail("图片地址不合法")
        if sku_id is not None:
            sku = db.get(ShopGoodsSku, sku_id)
            if sku is None or sku.goods_id != goods_id:
                fail("图片只能关联当前商品的 SKU")
        key = (u, sku_id)
        if key not in seen:
            images.append({"url": u, "sku_id": sku_id})
            seen.add(key)
    return images


def _apply_goods(db: Session, g: ShopGoods, values: dict, creating: bool) -> list[dict] | None:
    if "goods_no" in values or creating:
        g.goods_no = _text(values, "goods_no", "商品编码", 64, required=True)
    if "name" in values or creating:
        g.name = _text(values, "name", "商品名称", 200, required=True)
    if "category_id" in values or creating:
        cid = _int(values, "category_id", "分类")
        if not cid:
            fail("请选择分类")
        if db.get(ShopCategory, cid) is None:
            fail("分类不存在")
        # 商品只能挂在末级分类；只在新建或换分类时校验，分类后来长出子级的老商品不影响它保存其它字段
        if (creating or cid != g.category_id) and not is_leaf(db, cid):
            fail("商品只能选择末级分类，请选择该分类下的子分类")
        g.category_id = cid
    # 品牌：页面传 brand_id（品牌管理里的品牌），同时把名称冗余到旧列 brand，列表 / 导出口径不变；
    # 没传 brand_id 时仍接受旧字符串 brand（Excel 等外部入口）
    if "brand_id" in values or creating:
        bid = _int(values, "brand_id", "品牌")
        if not bid:
            fail("请选择品牌")
        b = db.get(Brand, bid)
        if b is None:
            fail("品牌不存在")
        g.brand_id = bid
        g.brand = b.name
    elif "brand" in values:
        g.brand = _text(values, "brand", "品牌", 100)
    if "supplier_id" in values or creating:
        sid = _int(values, "supplier_id", "供应商")
        if not sid:
            fail("请选择供应商")
        s = db.get(Supplier, sid)
        if s is None:
            fail("供应商不存在")
        g.supplier_id = sid
        g.supplier = s.name
    elif "supplier" in values:
        g.supplier = _text(values, "supplier", "供应商", 100)
    if "source_url" in values or creating:
        g.source_url = _text(values, "source_url", "货源链接", 500)
    if g.source_url and not g.source_url.lower().startswith(("http://", "https://")):
        fail("货源链接需以 http:// 或 https:// 开头")
    if "cost_price" in values or creating:
        g.cost_price = _money(values, "cost_price", "拿货价")
    # 销售价和运费改按区域保存。没带区域价格时仍接受商品上的旧字段（列表、外部入口）。
    if "region_prices" not in values:
        for f, label in (("sale_price", "销售价"), ("shipping_fee", "运费")):
            if f in values or creating:
                setattr(g, f, _money(values, f, label))
    if "weight_g" in values or creating:
        raw = values.get("weight_g")
        g.weight_g = None if raw in (None, "") else _int(values, "weight_g", "重量")
    if "shipping_package_group_id" in values or creating:
        g.shipping_package_group_id = _int(values, "shipping_package_group_id", "默认包装组")
        if g.shipping_package_group_id and db.get(ShippingPackageGroup, g.shipping_package_group_id) is None:
            fail("默认包装组不存在")
    if "description" in values:
        g.description = str(values.get("description") or "")[:20000]
    # 上架状态要等店铺记录写完再定：没有店铺记录时上架无效
    if creating and "status" not in values:
        g.status = 0
    if "attr_values" in values or "category_id" in values or creating:
        g.attr_values = _check_attr_values(db, g.category_id, values.get("attr_values", g.attr_values))
    if "images" in values:
        images = _check_images(db, g.id or 0, values["images"])
        g.main_image_url = next((x["url"] for x in images if x["sku_id"] is None), "")
        return images
    return None


def _store_link_dict(link: ShopGoodsStore, store: Store, platform: Platform | None) -> dict:
    return {
        "id": link.id, "store_id": store.id, "platform_id": store.platform_id,
        "platform_name": platform.name if platform else "",
        "store_name": store.name, "store_code": store.code,
        "allowed": bool(link.allowed),
        "product_url": link.product_url or "",
    }


def _goods_store_map(db: Session, goods_ids: list[int]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {i: [] for i in goods_ids}
    if not goods_ids:
        return out
    rows = db.execute(
        select(ShopGoodsStore, Store, Platform)
        .join(Store, Store.id == ShopGoodsStore.store_id)
        .outerjoin(Platform, Platform.id == Store.platform_id)
        .where(ShopGoodsStore.goods_id.in_(goods_ids))
        .order_by(ShopGoodsStore.id)
    ).all()
    for link, store, platform in rows:
        out.setdefault(link.goods_id, []).append(_store_link_dict(link, store, platform))
    return out


def _goods_store_dicts(db: Session, goods_id: int) -> list[dict]:
    return _goods_store_map(db, [goods_id]).get(goods_id, [])


def _with_stores(db: Session, g: ShopGoods, detail: dict) -> dict:
    detail["stores"] = _goods_store_dicts(db, g.id) if g.id else []
    return detail


def _store_record_count(db: Session, goods_id: int) -> int:
    if not goods_id:
        return 0
    return int(db.scalar(select(func.count()).select_from(ShopGoodsStore).where(ShopGoodsStore.goods_id == goods_id)) or 0)


def _store_bound_to_category(db: Session, store_id: int, category_id: int) -> bool:
    """店铺绑了当前商品分类，或绑了它的上级分类，才算匹配。"""
    if not category_id:
        return False
    chain = set(ancestor_ids(db, category_id))
    if not chain:
        return False
    bound = set(db.scalars(select(StoreCategory.category_id).where(StoreCategory.store_id == store_id)))
    return bool(chain & bound)


def _replace_goods_stores(db: Session, goods_id: int, raw, category_id: int) -> None:
    if not isinstance(raw, list):
        fail("店铺记录格式不正确")
    seen: set[int] = set()
    rows: list[tuple[int, int]] = []
    old_urls = dict(db.execute(select(ShopGoodsStore.store_id, ShopGoodsStore.product_url).where(
        ShopGoodsStore.goods_id == goods_id)).all())
    old_templates = dict(db.execute(select(ShopGoodsStore.store_id, ShopGoodsStore.shipping_template_id).where(
        ShopGoodsStore.goods_id == goods_id)).all())
    for item in raw:
        if not isinstance(item, dict):
            fail("店铺记录格式不正确")
        sid = _int(item, "store_id", "店铺")
        if not sid:
            continue
        if sid in seen:
            fail("同一个店铺只能有一条记录")
        store = db.get(Store, sid)
        if store is None:
            fail("店铺不存在")
        if not _store_bound_to_category(db, sid, category_id):
            fail(f"店铺「{store.name}」未绑定当前商品分类")
        seen.add(sid)
        allowed = 1 if item.get("allowed", True) else 0
        rows.append((sid, allowed))
    db.execute(delete(ShopGoodsStore).where(ShopGoodsStore.goods_id == goods_id))
    db.add_all(ShopGoodsStore(goods_id=goods_id, store_id=sid, shipping_template_id=old_templates.get(sid, 0),
                              allowed=allowed, product_url=old_urls.get(sid) or "")
               for sid, allowed in rows)


def _set_goods_status(db: Session, g: ShopGoods, values: dict, creating: bool) -> None:
    if "status" not in values:
        if creating:
            g.status = 0
        return
    on = bool(values["status"])
    if on and not g.main_image_url:
        fail("请至少保留一张商品共用图片，上架才能生效")
    if on and _store_record_count(db, g.id) == 0:
        fail("请先在「店铺」里添加记录，上架才能生效")
    g.status = 1 if on else 0


def _replace_images(db: Session, goods_id: int, images: list[dict]) -> None:
    db.execute(delete(ShopGoodsImage).where(ShopGoodsImage.goods_id == goods_id))
    db.add_all(ShopGoodsImage(goods_id=goods_id, sku_id=image["sku_id"], url=image["url"], sort_order=i)
               for i, image in enumerate(images))


def _sku_stats(db: Session, ids: list[int]) -> dict[int, tuple[int, int]]:
    if not ids:
        return {}
    q = (select(ShopGoodsSku.goods_id, func.count(), func.coalesce(func.sum(ShopGoodsSku.stock), 0))
         .where(ShopGoodsSku.goods_id.in_(ids)).group_by(ShopGoodsSku.goods_id))
    return {gid: (int(n), int(s)) for gid, n, s in db.execute(q)}


def _get_goods(db: Session, gid: int) -> ShopGoods:
    return db.get(ShopGoods, gid) or fail("商品不存在", 404)


def _opt_money(raw, label: str) -> Decimal | None:
    if raw in (None, ""):
        return None
    try:
        d = Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        fail(f"{label}格式不正确")
    if d < 0 or d > Decimal("9999999999.99"):
        fail(f"{label}超出范围")
    return d


def _price_range_error(lo, hi, sug) -> str | None:
    if lo is not None and hi is not None and lo > hi:
        return "最低售价不能高于最高售价"
    if sug is not None and lo is not None and sug < lo:
        return "建议售价不能低于最低售价"
    if sug is not None and hi is not None and sug > hi:
        return "建议售价不能高于最高售价"
    return None


def _days(raw, label: str) -> int | None:
    if raw in (None, ""):
        return None
    if isinstance(raw, bool):
        fail(f"{label}格式不正确")
    try:
        d = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        fail(f"{label}格式不正确")
    if d != d.to_integral_value() or d < 0 or d > 9999:
        fail(f"{label}需为 0~9999 的整数")
    return int(d)


def _days_range_error(fast, slow) -> str | None:
    if fast is not None and slow is not None and fast > slow:
        return "最快到达天数不能大于最慢到达天数"
    return None


def _money_out(v):
    return float(v) if v is not None else None


def _region_price_dict(row: ShopGoodsRegion, name: str, sort_order: int) -> dict:
    return {"id": row.id, "region_id": row.region_id, "region_name": name, "region_sort": sort_order,
            "price": _money_out(row.price), "suggested_price": _money_out(row.suggested_price),
            "min_price": _money_out(row.min_price), "max_price": _money_out(row.max_price),
            "currency": row.currency or "", "shipping_fee": _money_out(row.shipping_fee),
            "shipping_template_id": row.shipping_template_id,
            "arrival_days_min": row.arrival_days_min, "arrival_days_max": row.arrival_days_max,
            "tax": _money_out(row.tax)}


def _region_price_map(db: Session, goods_ids: list[int]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {i: [] for i in goods_ids}
    if not goods_ids:
        return out
    q = (select(ShopGoodsRegion, GeoRegion.name, GeoRegion.sort_order)
         .join(GeoRegion, GeoRegion.id == ShopGoodsRegion.region_id)
         .where(ShopGoodsRegion.goods_id.in_(goods_ids))
         .order_by(GeoRegion.sort_order, GeoRegion.id, ShopGoodsRegion.id))
    for row, name, sort_order in db.execute(q):
        out.setdefault(row.goods_id, []).append(_region_price_dict(row, name, sort_order))
    return out


def _mirror_region_snapshot(g: ShopGoods, rows: list[dict], regions: dict[int, GeoRegion]) -> None:
    """商品上的销售价、运费仍镜像排序最前的区域，给旧接口和规格默认价用。列表改看区域价格。没有区域行时清成 0。"""
    if not rows:
        g.sale_price = Decimal("0.00")
        g.shipping_fee = Decimal("0.00")
        return
    first = min(rows, key=lambda row: (regions[row["region_id"]].sort_order, row["region_id"]))
    g.sale_price = first["price"] if first["price"] is not None else Decimal("0.00")
    g.shipping_fee = first["shipping_fee"] if first["shipping_fee"] is not None else Decimal("0.00")


def _replace_region_prices(db: Session, g: ShopGoods, raw_rows, creating: bool) -> None:
    if raw_rows is None and not creating:
        return
    if not isinstance(raw_rows, list):
        fail("区域价格格式不正确")
    if len(raw_rows) > 100:
        fail("区域价格最多 100 条")
    old_currency = {}
    if g.id is not None:
        old_currency = dict(db.execute(select(ShopGoodsRegion.region_id, ShopGoodsRegion.currency)
                                        .where(ShopGoodsRegion.goods_id == g.id)).all())
    regions = {r.id: r for r in db.scalars(select(GeoRegion)).all()}
    seen: set[int] = set()
    parsed: list[dict] = []
    for raw in raw_rows:
        if not isinstance(raw, dict):
            fail("区域价格格式不正确")
        try:
            rid = int(raw.get("region_id") or 0)
        except (TypeError, ValueError):
            fail("请选择区域")
        if isinstance(raw.get("region_id"), bool) or rid not in regions:
            fail("请选择区域")
        if rid in seen:
            fail(f"区域「{regions[rid].name}」重复")
        seen.add(rid)
        row = {
            "region_id": rid,
            "price": _opt_money(raw.get("price"), "价格"),
            "suggested_price": _opt_money(raw.get("suggested_price"), "建议售价"),
            "min_price": _opt_money(raw.get("min_price"), "最低售价"),
            "max_price": _opt_money(raw.get("max_price"), "最高售价"),
            "currency": normalize_currency(db, raw.get("currency"), old_currency.get(rid, "")),
            "shipping_template_id": 0,
            "shipping_fee": _opt_money(raw.get("shipping_fee"), "运费"),
            "arrival_days_min": _days(raw.get("arrival_days_min"), "最快到达天数"),
            "arrival_days_max": _days(raw.get("arrival_days_max"), "最慢到达天数"),
            "tax": _opt_money(raw.get("tax"), "税费"),
        }
        try:
            row["shipping_template_id"] = int(raw.get("shipping_template_id") or 0)
        except (TypeError, ValueError):
            fail(f"{regions[rid].name}：运费模板格式不正确")
        if row["shipping_template_id"]:
            template = db.get(ShippingTemplate, row["shipping_template_id"])
            if template is None:
                fail(f"{regions[rid].name}：运费模板不存在")
        err = _price_range_error(row["min_price"], row["max_price"], row["suggested_price"])
        if err:
            fail(f"{regions[rid].name}：{err}")
        err = _days_range_error(row["arrival_days_min"], row["arrival_days_max"])
        if err:
            fail(f"{regions[rid].name}：{err}")
        parsed.append(row)
    if g.id is None:
        db.flush()
    db.execute(delete(ShopGoodsRegion).where(ShopGoodsRegion.goods_id == g.id))
    for row in parsed:
        db.add(ShopGoodsRegion(goods_id=g.id, **row))
    _mirror_region_snapshot(g, parsed, regions)


def _region_min_price(rows: list | None) -> tuple[float | None, str]:
    """区域价里的最低「价格」，以及给出这个价格的区域名（并列时按区域排序都列出来）。"""
    priced = [r for r in (rows or []) if r.get("price") is not None]
    if not priced:
        return None, ""
    low = min(r["price"] for r in priced)
    names = [r.get("region_name") or "" for r in priced if r["price"] == low and r.get("region_name")]
    return low, "、".join(names)


def _with_region_prices(db: Session, g: ShopGoods, detail: dict) -> dict:
    detail["region_prices"] = _region_price_map(db, [g.id]).get(g.id, [])
    return detail


def _en_lang_code(db: Session) -> str | None:
    return next((c for c in inline_languages(db) if c.lower().startswith("en")), None)


def _require_en_name(db: Session, values: dict, creating: bool) -> None:
    """启用了英文时，商品名称 (en) 必填。没带 i18n 的局部更新不拦。"""
    if "i18n" not in values and not creating:
        return
    code = _en_lang_code(db)
    if not code:
        return
    pack = values.get("i18n") if isinstance(values.get("i18n"), dict) else {}
    name = str((pack.get(code) or {}).get("name") or "").strip()
    if not name:
        fail("商品名称 (en)不能为空")


def _with_catalog(db: Session, g: ShopGoods, detail: dict) -> dict:
    item = db.scalar(select(SupplierCatalogItem).where(SupplierCatalogItem.goods_id == g.id).limit(1))
    detail["catalog_item_id"] = item.id if item else 0
    detail["catalog_item_name"] = item.name if item else ""
    detail["catalog_item_sku"] = item.supplier_sku if item else ""
    return detail


def _unbind_catalog(item: SupplierCatalogItem) -> None:
    item.goods_id = 0
    if item.status == 2:
        item.status = 1


def _bind_catalog_item(db: Session, g: ShopGoods, values: dict) -> None:
    """商品绑定产品池条目：写 supplier_catalog_item.goods_id；一个商品只绑一条，一条也只绑一个商品。"""
    if "catalog_item_id" not in values:
        return
    iid = _int(values, "catalog_item_id", "绑定产品")
    for old in list(db.scalars(select(SupplierCatalogItem).where(SupplierCatalogItem.goods_id == g.id))):
        if old.id != iid:
            _unbind_catalog(old)
    if not iid:
        return
    item = db.get(SupplierCatalogItem, iid) or fail("产品目录条目不存在", 404)
    if item.goods_id and item.goods_id != g.id:
        fail("该产品已绑定其他商品")
    item.goods_id = g.id
    if item.status in (0, 1):
        item.status = 2


def _catalog_bind_map(db: Session, goods_ids: list[int]) -> dict[int, SupplierCatalogItem]:
    """一个商品只绑一条产品；有多条时取 id 最小的那条。"""
    out: dict[int, SupplierCatalogItem] = {}
    if not goods_ids:
        return out
    rows = db.scalars(select(SupplierCatalogItem).where(SupplierCatalogItem.goods_id.in_(goods_ids))
                      .order_by(SupplierCatalogItem.id)).all()
    for item in rows:
        out.setdefault(item.goods_id, item)
    return out


def _list_goods_row(g: ShopGoods, stats: tuple[int, int], regions: list[dict], stores: list[dict],
                    catalog: SupplierCatalogItem | None) -> dict:
    detail = _goods_dict(g, *stats)
    low, names = _region_min_price(regions)
    detail["region_prices"] = regions
    detail["region_min_price"] = low
    detail["region_min_price_region"] = names
    detail["stores"] = stores
    detail["store_count"] = len(stores)
    detail["catalog_item_id"] = catalog.id if catalog else 0
    detail["catalog_item_name"] = catalog.name if catalog else ""
    detail["catalog_item_sku"] = catalog.supplier_sku if catalog else ""
    return detail


def _goods_query_fields(db: Session) -> dict:
    """列表可筛选 / 排序的字段白名单：字段名 → (SQL 表达式, 类型)。含计算列和各语言的商品名。"""
    profit = ShopGoods.sale_price - ShopGoods.cost_price - ShopGoods.shipping_fee
    sku_count = select(func.count()).where(ShopGoodsSku.goods_id == ShopGoods.id).scalar_subquery()
    stock = select(func.coalesce(func.sum(ShopGoodsSku.stock), 0)).where(ShopGoodsSku.goods_id == ShopGoods.id).scalar_subquery()
    region_min_price = (select(func.min(ShopGoodsRegion.price))
                        .where(ShopGoodsRegion.goods_id == ShopGoods.id, ShopGoodsRegion.price.is_not(None))
                        .correlate(ShopGoods).scalar_subquery())
    store_count = (select(func.count()).where(ShopGoodsStore.goods_id == ShopGoods.id)
                   .correlate(ShopGoods).scalar_subquery())
    catalog_name = (select(SupplierCatalogItem.name).where(SupplierCatalogItem.goods_id == ShopGoods.id)
                    .order_by(SupplierCatalogItem.id).limit(1).scalar_subquery())
    catalog_sku = (select(SupplierCatalogItem.supplier_sku).where(SupplierCatalogItem.goods_id == ShopGoods.id)
                   .order_by(SupplierCatalogItem.id).limit(1).scalar_subquery())
    fields = {
        "id": (ShopGoods.id, "num"), "goods_no": (ShopGoods.goods_no, "str"), "name": (ShopGoods.name, "str"),
        "category_id": (ShopGoods.category_id, "num"), "brand": (ShopGoods.brand, "str"),
        "brand_id": (ShopGoods.brand_id, "num"), "supplier_id": (ShopGoods.supplier_id, "num"),
        "supplier": (ShopGoods.supplier, "str"), "cost_price": (ShopGoods.cost_price, "num"),
        "region_min_price": (region_min_price, "num"),
        "store_count": (store_count, "num"),
        "catalog_item_name": (catalog_name, "str"), "catalog_item_sku": (catalog_sku, "str"),
        # 销售价、运费、利润、毛利率是排序最前区域的镜像，列表不再展示，筛选仍可用
        "sale_price": (ShopGoods.sale_price, "num"), "shipping_fee": (ShopGoods.shipping_fee, "num"),
        "profit": (profit, "num"),
        "margin_pct": (case((ShopGoods.sale_price > 0, func.round(profit / ShopGoods.sale_price * 100, 1)), else_=None), "num"),
        "sku_count": (sku_count, "num"), "stock": (stock, "num"), "status": (ShopGoods.status, "num"),
        "weight_g": (ShopGoods.weight_g, "num"),
        "updated_at": (ShopGoods.updated_at, "str"),  # 日期按文本匹配，如 contains 2026-11
    }
    for code in inline_languages(db):
        fields[f"i18n.{code}.name"] = (select(ShopTranslation.content).where(
            ShopTranslation.entity_type == "goods", ShopTranslation.entity_id == ShopGoods.id,
            ShopTranslation.lang_code == code, ShopTranslation.field_name == "name").scalar_subquery(), "str")
    return fields


def _query_ids(raw: str | None, label: str) -> list[int]:
    """解析列表查询使用的逗号分隔 ID；只接受正整数并限制数量。"""
    if not raw:
        return []
    try:
        ids = list(dict.fromkeys(int(x) for x in raw.split(",") if x.strip()))
    except ValueError:
        fail(f"{label}格式不正确")
    if not ids or len(ids) > 500 or any(i <= 0 for i in ids):
        fail(f"{label}格式不正确")
    return ids


@router.get("/goods")
def list_goods(take: int | None = None, skip: int = 0, sort: str | None = None, filter: str | None = None,
               store_ids: str | None = None,
               db: Session = Depends(get_db)):
    """不带 take 返回全部（数组）；带 take 做服务端分页，返回 {items, total}。
    sort / filter 为 DevExtreme 表格的 JSON 参数，字段见 _goods_query_fields。"""
    q = select(ShopGoods)
    selected_stores = _query_ids(store_ids, "店铺")
    if selected_stores:
        q = q.where(ShopGoods.id.in_(
            select(ShopGoodsStore.goods_id).where(ShopGoodsStore.store_id.in_(selected_stores))
        ))
    if take is None:
        q = q.order_by(ShopGoods.id.desc())
    else:
        fields = _goods_query_fields(db)
        cond = build_filter(parse_json(filter, "筛选"), fields)
        if cond is not None:
            q = q.where(cond)
        total = db.scalar(select(func.count()).select_from(q.subquery()))
        skip, take = clamp_page(skip, take)
        q = q.order_by(*build_sort(parse_json(sort, "排序"), fields), ShopGoods.id.desc()).offset(skip).limit(take)
    rows = db.scalars(q).all()
    ids = [g.id for g in rows]
    stats = _sku_stats(db, ids)
    regions = _region_price_map(db, ids)
    stores = _goods_store_map(db, ids)
    catalogs = _catalog_bind_map(db, ids)
    items = _attach(db, "goods", [
        _list_goods_row(g, stats.get(g.id, (0, 0)), regions.get(g.id, []), stores.get(g.id, []), catalogs.get(g.id))
        for g in rows
    ], ["name"])
    return ok(items if take is None else {"items": items, "total": total})


@router.get("/goods/{gid}")
def get_goods(gid: int, db: Session = Depends(get_db)):
    g = _get_goods(db, gid)
    images = db.scalars(select(ShopGoodsImage).where(ShopGoodsImage.goods_id == gid)
                        .order_by(ShopGoodsImage.sort_order, ShopGoodsImage.id)).all()
    detail = {**_goods_dict(g, *_sku_stats(db, [gid]).get(gid, (0, 0))), "description": g.description or "",
              "attr_values": g.attr_values or {},
              "images": [{"id": image.id, "url": image.url, "sku_id": image.sku_id,
                          "sort_order": image.sort_order} for image in images]}
    return ok(_attach(db, "goods", [_with_stores(db, g, _with_catalog(db, g, _with_region_prices(db, g, detail)))],
                      ["name", "description", "attr_values"])[0])


@router.post("/goods-no/generate")
def generate_goods_no(values: dict, db: Session = Depends(get_db)):
    """按最终前缀占用一个四位流水号；号码一经返回即不回收。"""
    cid = _int(values, "category_id", "分类")
    bid = _int(values, "brand_id", "品牌")
    category = db.get(ShopCategory, cid) if cid else None
    brand = db.get(Brand, bid) if bid else None
    if category is None:
        fail("请选择分类")
    if not is_leaf(db, category.id):
        fail("商品只能选择末级分类")
    if brand is None:
        fail("请选择品牌")
    category_code = (category.code or "").strip()
    if not category_code:
        fail("所选分类未设置品类编码")
    brand_code = (brand.code or "").strip() if brand.include_in_goods_no else "TH"
    if not brand_code:
        fail("所选品牌参与商品编码，但未设置品牌编码")
    prefix = brand_code + category_code
    if len(prefix) > 60:
        fail("品牌编码与品类编码拼接后不能超过 60 个字符")
    current = 0
    while current < 9999:
        stmt = mysql_insert(GoodsNoSequence).values(prefix=prefix, current_seq=1)
        stmt = stmt.on_duplicate_key_update(current_seq=GoodsNoSequence.current_seq + 1)
        db.execute(stmt)
        current = db.scalar(select(GoodsNoSequence.current_seq).where(GoodsNoSequence.prefix == prefix)) or 0
        candidate = f"{prefix}{current:04d}"
        if not db.scalar(select(ShopGoods.id).where(ShopGoods.goods_no == candidate).limit(1)):
            break
    if current > 9999 or db.scalar(select(ShopGoods.id).where(ShopGoods.goods_no == candidate).limit(1)):
        db.rollback()
        fail(f"编码前缀 {prefix} 的四位流水已用完")
    db.commit()
    return ok({"goods_no": candidate, "prefix": prefix, "sequence": current})


@router.post("/goods")
def create_goods(values: dict, db: Session = Depends(get_db)):
    g = ShopGoods()
    _require_en_name(db, values, True)
    images = _apply_goods(db, g, values, True)
    db.add(g)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        fail("商品编码已存在")
    if any(image["sku_id"] is not None for image in images or []):
        fail("请先保存商品并创建 SKU，再设置 SKU 专用图片")
    if images:
        _replace_images(db, g.id, images)
    if "region_prices" in values:
        _replace_region_prices(db, g, values.get("region_prices") or [], True)
    if "stores" in values:
        _replace_goods_stores(db, g.id, values.get("stores") or [], g.category_id)
    _set_goods_status(db, g, values, True)
    _bind_catalog_item(db, g, values)
    save_inline(db, "goods", g, values.get("i18n"))
    db.commit()
    return ok(_attach(db, "goods", [_with_stores(db, g, _with_catalog(db, g, _with_region_prices(db, g, _goods_dict(g))))], ["name"])[0])


@router.put("/goods/{gid}")
def update_goods(gid: int, values: dict, db: Session = Depends(get_db)):
    g = _get_goods(db, gid)
    _require_en_name(db, values, False)
    images = _apply_goods(db, g, values, False)
    if images is not None:
        _replace_images(db, gid, images)
    if "region_prices" in values:
        _replace_region_prices(db, g, values.get("region_prices") or [], False)
    if "stores" in values:
        _replace_goods_stores(db, gid, values.get("stores") or [], g.category_id)
    _set_goods_status(db, g, values, False)
    _bind_catalog_item(db, g, values)
    _save(db, "商品编码已存在", "goods", g, values)
    detail = _with_stores(db, g, _with_catalog(db, g, _with_region_prices(db, g, _goods_dict(g, *_sku_stats(db, [gid]).get(gid, (0, 0))))))
    return ok(_attach(db, "goods", [detail], ["name"])[0])


@router.post("/goods/batch-status")
def batch_goods_status(body: dict, db: Session = Depends(get_db)):
    """批量上架 / 下架。body: {"ids": [1,2,...], "status": true|false}；返回实际更新的条数。"""
    ids = body.get("ids")
    if not isinstance(ids, list) or not ids or len(ids) > 500 or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        fail("请选择 1~500 个商品")
    if not isinstance(body.get("status"), bool):
        fail("参数不合法")
    target_ids = ids
    if body["status"]:
        target_ids = []
        for goods in db.scalars(select(ShopGoods).where(ShopGoods.id.in_(ids))):
            links = list(db.scalars(select(ShopGoodsStore).where(
                ShopGoodsStore.goods_id == goods.id, ShopGoodsStore.allowed == 1)))
            if not links:
                continue
            target_ids.append(goods.id)
        if not target_ids:
            fail("选中的商品都没有配置可以上架的店铺")
    res = db.execute(update(ShopGoods).where(ShopGoods.id.in_(target_ids)).values(status=1 if body["status"] else 0))
    db.commit()
    return ok({"updated": res.rowcount, "skipped": len(ids) - len(target_ids)})


@router.delete("/goods/{gid}")
def delete_goods(gid: int, db: Session = Depends(get_db)):
    g = _get_goods(db, gid)
    sku_ids = list(db.scalars(select(ShopGoodsSku.id).where(ShopGoodsSku.goods_id == gid)))
    if sku_ids and db.scalar(select(ShopOrderLine.id).where(ShopOrderLine.sku_id.in_(sku_ids)).limit(1)):
        fail("该商品已有订单快照，不能删除；请改为下架")
    if sku_ids and (db.scalar(select(BundleComponent.id).where(BundleComponent.component_sku_id.in_(sku_ids)).limit(1)) or
                    db.scalar(select(BundleRevision.id).where(BundleRevision.parent_sku_id.in_(sku_ids)).limit(1))):
        fail("该商品 SKU 已被组合版本使用，不能删除")
    if sku_ids and db.scalar(select(StockLedger.id).where(StockLedger.sku_id.in_(sku_ids)).limit(1)):
        fail("该商品已有库存流水，不能删除；请改为下架")
    purge_translations(db, "sku", sku_ids)
    purge_translations(db, "goods", [gid])
    db.execute(delete(ShopGoodsImage).where(ShopGoodsImage.goods_id == gid))
    db.execute(delete(ShopGoodsSku).where(ShopGoodsSku.goods_id == gid))
    db.execute(delete(ShopGoodsSkuRegion).where(ShopGoodsSkuRegion.goods_id == gid))
    db.execute(delete(ShopGoodsRegion).where(ShopGoodsRegion.goods_id == gid))
    db.execute(delete(ShopGoodsStore).where(ShopGoodsStore.goods_id == gid))
    db.execute(delete(ShopifySyncTask).where(ShopifySyncTask.goods_id == gid))
    db.execute(delete(ShopifyVariantMap).where(ShopifyVariantMap.goods_id == gid))
    db.execute(delete(ShopifyProductMap).where(ShopifyProductMap.goods_id == gid))
    if sku_ids:
        db.execute(delete(StockBalance).where(StockBalance.sku_id.in_(sku_ids)))
    for item in list(db.scalars(select(SupplierCatalogItem).where(SupplierCatalogItem.goods_id == gid))):
        _unbind_catalog(item)
    db.delete(g)
    db.commit()
    return ok()


# ---------------------------------------------------------------- SKU
def _sku_dict(s: ShopGoodsSku) -> dict:
    return {"id": s.id, "goods_id": s.goods_id, "sku_code": s.sku_code, "spec_name": s.spec_name,
            "sku_type": s.sku_type, "weight_g": s.weight_g,
            "shipping_package_group_id": s.shipping_package_group_id,
            "cost_price": float(s.cost_price), "sale_price": float(s.sale_price), "stock": s.stock,
            "status": bool(s.status)}


def _apply_sku(s: ShopGoodsSku, values: dict, creating: bool, db: Session | None = None) -> None:
    if "sku_code" in values or creating:
        s.sku_code = _text(values, "sku_code", "SKU编码", 64, required=True)
    if "spec_name" in values or creating:
        s.spec_name = _text(values, "spec_name", "规格", 200)
    if "weight_g" in values or creating:
        raw_weight = values.get("weight_g")
        s.weight_g = None if raw_weight in (None, "") else _int(values, "weight_g", "SKU重量", lo=1)
    if "shipping_package_group_id" in values or creating:
        s.shipping_package_group_id = _int(values, "shipping_package_group_id", "包装组")
        if s.shipping_package_group_id and db and db.get(ShippingPackageGroup, s.shipping_package_group_id) is None:
            fail("包装组不存在")
    for f, label in (("cost_price", "拿货价"), ("sale_price", "销售价")):
        if f in values or creating:
            setattr(s, f, _money(values, f, label))
    if creating:
        s.stock = 0  # 旧汇总列仅兼容历史结构；主库存统一维护在 stock_balance。
    if "status" in values:
        s.status = 1 if values["status"] else 0
    elif creating:
        s.status = 1


@router.get("/goods/{gid}/skus")
def list_skus(gid: int, db: Session = Depends(get_db)):
    _get_goods(db, gid)
    items = [_sku_dict(s) for s in db.scalars(select(ShopGoodsSku).where(ShopGoodsSku.goods_id == gid)
                                               .order_by(ShopGoodsSku.id))]
    return ok(_attach(db, "sku", items, ["spec_name"]))


@router.post("/goods/{gid}/skus")
def create_sku(gid: int, values: dict, db: Session = Depends(get_db)):
    g = _get_goods(db, gid)
    s = ShopGoodsSku(goods_id=gid)
    values = {"cost_price": g.cost_price, "sale_price": g.sale_price, **values}  # 价格不填默认用商品价
    for f in ("cost_price", "sale_price"):
        if values[f] in (None, ""):
            values[f] = getattr(g, f)
    _apply_sku(s, values, True, db)
    db.add(s)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        fail("SKU编码已存在")
    _save(db, "SKU编码已存在", "sku", s, values)
    return ok(_attach(db, "sku", [_sku_dict(s)], ["spec_name"])[0])


@router.post("/goods/{gid}/skus/default")
def create_default_sku(gid: int, db: Session = Depends(get_db)):
    g = _get_goods(db, gid)
    if db.scalar(select(func.count()).select_from(ShopGoodsSku).where(ShopGoodsSku.goods_id == gid)):
        fail("商品已有 SKU，不能再创建默认 SKU")
    s = ShopGoodsSku(goods_id=gid, sku_code=g.goods_no, spec_name="",
                     cost_price=g.cost_price, sale_price=g.sale_price, stock=0, status=1)
    db.add(s)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fail("商品编码已被其它 SKU 使用，请手工填写 SKU 编码")
    db.refresh(s)
    return ok(_attach(db, "sku", [_sku_dict(s)], ["spec_name"])[0])


def _get_sku(db: Session, gid: int, sid: int) -> ShopGoodsSku:
    s = db.get(ShopGoodsSku, sid)
    if s is None or s.goods_id != gid:
        fail("SKU不存在", 404)
    return s


@router.put("/goods/{gid}/skus/{sid}")
def update_sku(gid: int, sid: int, values: dict, db: Session = Depends(get_db)):
    s = _get_sku(db, gid, sid)
    _apply_sku(s, values, False, db)
    goods = _get_goods(db, gid)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        fail("SKU编码已存在")
    _save(db, "SKU编码已存在", "sku", s, values)
    return ok(_attach(db, "sku", [_sku_dict(s)], ["spec_name"])[0])


@router.delete("/goods/{gid}/skus/{sid}")
def delete_sku(gid: int, sid: int, db: Session = Depends(get_db)):
    s = _get_sku(db, gid, sid)
    if db.scalar(select(ShopGoodsImage.id).where(ShopGoodsImage.goods_id == gid,
                                                 ShopGoodsImage.sku_id == sid).limit(1)):
        fail("该 SKU 还有专用图片，请先删除图片或改为商品共用图片")
    if db.scalar(select(BundleComponent.id).where(BundleComponent.component_sku_id == sid).limit(1)):
        fail("该 SKU 已被组合版本用作组件，不能删除")
    if db.scalar(select(BundleRevision.id).where(BundleRevision.parent_sku_id == sid).limit(1)):
        fail("该 SKU 已有组合版本，不能删除")
    if db.scalar(select(ShopOrderLine.id).where(ShopOrderLine.sku_id == sid).limit(1)):
        fail("该 SKU 已有订单快照，不能删除")
    if db.scalar(select(StockLedger.id).where(StockLedger.sku_id == sid).limit(1)):
        fail("该 SKU 已有库存流水，不能删除；请改为停用")
    purge_translations(db, "sku", [s.id])
    db.execute(delete(ShopGoodsSkuRegion).where(ShopGoodsSkuRegion.sku_id == sid))
    db.execute(delete(ShopifyVariantMap).where(ShopifyVariantMap.sku_id == sid))
    db.execute(delete(StockBalance).where(StockBalance.sku_id == sid))
    db.delete(s)
    db.commit()
    return ok()


def _sku_region_dict(row: ShopGoodsSkuRegion, sku: ShopGoodsSku, region: GeoRegion) -> dict:
    return {"id": row.id, "goods_id": row.goods_id, "sku_id": row.sku_id,
            "sku_code": sku.sku_code, "spec_name": sku.spec_name,
            "region_id": row.region_id, "region_name": region.name,
            "price": float(row.price) if row.price is not None else None,
            "suggested_price": float(row.suggested_price) if row.suggested_price is not None else None,
            "min_price": float(row.min_price) if row.min_price is not None else None,
            "max_price": float(row.max_price) if row.max_price is not None else None,
            "created_at": _fmt(row.created_at), "updated_at": _fmt(row.updated_at)}


def _apply_sku_region(db: Session, gid: int, row: ShopGoodsSkuRegion, values: dict, creating: bool) -> None:
    if "sku_id" in values or creating:
        try:
            sid = int(values.get("sku_id") or 0)
        except (TypeError, ValueError):
            fail("请选择 SKU")
        sku = db.get(ShopGoodsSku, sid)
        if not sku or sku.goods_id != gid:
            fail("请选择当前商品的 SKU")
        row.sku_id = sid
    if "region_id" in values or creating:
        try:
            rid = int(values.get("region_id") or 0)
        except (TypeError, ValueError):
            fail("请选择区域")
        if not db.get(GeoRegion, rid):
            fail("请选择区域")
        row.region_id = rid
    for field, label in (("price", "价格"), ("suggested_price", "建议售价"),
                         ("min_price", "最低售价"), ("max_price", "最高售价")):
        if field in values or creating:
            setattr(row, field, _opt_money(values.get(field), label))
    err = _price_range_error(row.min_price, row.max_price, row.suggested_price)
    if err:
        fail(err)
    if row.price is None and row.suggested_price is None and row.min_price is None and row.max_price is None:
        fail("SKU 区域价格至少填写一项")


@router.get("/goods/{gid}/sku-region-prices")
def list_sku_region_prices(gid: int, db: Session = Depends(get_db)):
    _get_goods(db, gid)
    rows = db.execute(select(ShopGoodsSkuRegion, ShopGoodsSku, GeoRegion)
                      .join(ShopGoodsSku, ShopGoodsSku.id == ShopGoodsSkuRegion.sku_id)
                      .join(GeoRegion, GeoRegion.id == ShopGoodsSkuRegion.region_id)
                      .where(ShopGoodsSkuRegion.goods_id == gid)
                      .order_by(GeoRegion.sort_order, ShopGoodsSku.id))
    return ok([_sku_region_dict(row, sku, region) for row, sku, region in rows])


@router.post("/goods/{gid}/sku-region-prices")
def create_sku_region_price(gid: int, values: dict, db: Session = Depends(get_db)):
    _get_goods(db, gid)
    row = ShopGoodsSkuRegion(goods_id=gid)
    _apply_sku_region(db, gid, row, values, True)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fail("同一个 SKU 在同一区域只能有一条价格")
    db.refresh(row)
    sku, region = db.get(ShopGoodsSku, row.sku_id), db.get(GeoRegion, row.region_id)
    return ok(_sku_region_dict(row, sku, region))


def _get_sku_region(db: Session, gid: int, row_id: int) -> ShopGoodsSkuRegion:
    row = db.get(ShopGoodsSkuRegion, row_id)
    if not row or row.goods_id != gid:
        fail("SKU 区域价格不存在", 404)
    return row


@router.put("/goods/{gid}/sku-region-prices/{row_id}")
def update_sku_region_price(gid: int, row_id: int, values: dict, db: Session = Depends(get_db)):
    row = _get_sku_region(db, gid, row_id)
    _apply_sku_region(db, gid, row, values, False)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fail("同一个 SKU 在同一区域只能有一条价格")
    db.refresh(row)
    return ok(_sku_region_dict(row, db.get(ShopGoodsSku, row.sku_id), db.get(GeoRegion, row.region_id)))


@router.delete("/goods/{gid}/sku-region-prices/{row_id}")
def delete_sku_region_price(gid: int, row_id: int, db: Session = Depends(get_db)):
    db.delete(_get_sku_region(db, gid, row_id))
    db.commit()
    return ok()


# ---------------------------------------------------------------- 图片上传
@router.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    ext = ("." + (file.filename or "").rsplit(".", 1)[-1].lower()) if "." in (file.filename or "") else ""
    if ext not in IMAGE_MAGIC:
        fail("仅支持 jpg / png / gif / webp 图片")
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        fail("图片不能超过 5MB")
    if not data.startswith(IMAGE_MAGIC[ext]) or (ext == ".webp" and data[8:12] != b"WEBP"):
        fail("文件内容不是有效的图片")
    folder = UPLOAD_DIR / datetime.now().strftime("%Y%m")
    folder.mkdir(parents=True, exist_ok=True)
    name = uuid.uuid4().hex + ext
    (folder / name).write_bytes(data)
    return ok({"url": f"/static/uploads/{folder.name}/{name}"})
