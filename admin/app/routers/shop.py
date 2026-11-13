"""自有商品目录：分类、属性、商品（含图片、SKU）、图片上传。响应 {code, data, msg}。"""
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import case, delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..catalog import applicable_attributes, is_leaf
from ..config import BASE_DIR
from ..db import get_db
from ..deps import require_user
from .shop_i18n import inline_languages, load_inline, purge_translations, save_inline
from ..listquery import build_filter, build_sort, clamp_page, parse_json
from ..models import Brand, ShopAttribute, ShopCategory, ShopGoods, ShopGoodsImage, ShopGoodsSku, ShopTranslation

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
    return {"id": c.id, "parent_id": c.parent_id, "name": c.name, "full_name": full_name, "sort_order": c.sort_order,
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
        "weight_g": g.weight_g, "status": bool(g.status), "sku_count": sku_count, "stock": stock,
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


def _check_images(raw) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_IMAGES:
        fail(f"图片最多 {MAX_IMAGES} 张")
    urls = []
    for u in raw:
        u = str(u).strip()
        if not u:
            continue
        if len(u) > 500 or not (u.startswith("/static/uploads/") or u.lower().startswith(("http://", "https://"))):
            fail("图片地址不合法")
        urls.append(u)
    return list(dict.fromkeys(urls))


def _apply_goods(db: Session, g: ShopGoods, values: dict, creating: bool) -> list[str] | None:
    if "goods_no" in values or creating:
        g.goods_no = _text(values, "goods_no", "商品编码", 64, required=True)
    if "name" in values or creating:
        g.name = _text(values, "name", "商品名称", 200, required=True)
    if "category_id" in values or creating:
        cid = _int(values, "category_id", "分类")
        if cid and db.get(ShopCategory, cid) is None:
            fail("分类不存在")
        # 商品只能挂在末级分类；只在新建或换分类时校验，分类后来长出子级的老商品不影响它保存其它字段
        if cid and (creating or cid != g.category_id) and not is_leaf(db, cid):
            fail("商品只能选择末级分类，请选择该分类下的子分类")
        g.category_id = cid
    # 品牌：页面传 brand_id（品牌管理里的品牌），同时把名称冗余到旧列 brand，列表 / 导出口径不变；
    # 没传 brand_id 时仍接受旧字符串 brand（Excel / 采集等外部入口）
    if "brand_id" in values:
        bid = _int(values, "brand_id", "品牌")
        b = db.get(Brand, bid) if bid else None
        if bid and b is None:
            fail("品牌不存在")
        g.brand_id = bid
        g.brand = b.name if b else ""
    elif "brand" in values or creating:
        g.brand = _text(values, "brand", "品牌", 100)
    if "supplier" in values or creating:
        g.supplier = _text(values, "supplier", "供应商", 100)
    if "source_url" in values or creating:
        g.source_url = _text(values, "source_url", "货源链接", 500)
    if g.source_url and not g.source_url.lower().startswith(("http://", "https://")):
        fail("货源链接需以 http:// 或 https:// 开头")
    for f, label in (("cost_price", "拿货价"), ("sale_price", "销售价"), ("shipping_fee", "运费")):
        if f in values or creating:
            setattr(g, f, _money(values, f, label))
    if "weight_g" in values or creating:
        raw = values.get("weight_g")
        g.weight_g = None if raw in (None, "") else _int(values, "weight_g", "重量")
    if "description" in values:
        g.description = str(values.get("description") or "")[:20000]
    if "status" in values:
        g.status = 1 if values["status"] else 0
    elif creating:
        g.status = 0
    if "attr_values" in values or "category_id" in values or creating:
        g.attr_values = _check_attr_values(db, g.category_id, values.get("attr_values", g.attr_values))
    if "images" in values:
        images = _check_images(values["images"])
        g.main_image_url = images[0] if images else ""
        return images
    return None


def _replace_images(db: Session, goods_id: int, urls: list[str]) -> None:
    db.execute(delete(ShopGoodsImage).where(ShopGoodsImage.goods_id == goods_id))
    db.add_all(ShopGoodsImage(goods_id=goods_id, url=u, sort_order=i) for i, u in enumerate(urls))


def _sku_stats(db: Session, ids: list[int]) -> dict[int, tuple[int, int]]:
    if not ids:
        return {}
    q = (select(ShopGoodsSku.goods_id, func.count(), func.coalesce(func.sum(ShopGoodsSku.stock), 0))
         .where(ShopGoodsSku.goods_id.in_(ids)).group_by(ShopGoodsSku.goods_id))
    return {gid: (int(n), int(s)) for gid, n, s in db.execute(q)}


def _get_goods(db: Session, gid: int) -> ShopGoods:
    return db.get(ShopGoods, gid) or fail("商品不存在", 404)


def _goods_query_fields(db: Session) -> dict:
    """列表可筛选 / 排序的字段白名单：字段名 → (SQL 表达式, 类型)。含计算列和各语言的商品名。"""
    profit = ShopGoods.sale_price - ShopGoods.cost_price - ShopGoods.shipping_fee
    sku_count = select(func.count()).where(ShopGoodsSku.goods_id == ShopGoods.id).scalar_subquery()
    stock = select(func.coalesce(func.sum(ShopGoodsSku.stock), 0)).where(ShopGoodsSku.goods_id == ShopGoods.id).scalar_subquery()
    fields = {
        "id": (ShopGoods.id, "num"), "goods_no": (ShopGoods.goods_no, "str"), "name": (ShopGoods.name, "str"),
        "category_id": (ShopGoods.category_id, "num"), "brand": (ShopGoods.brand, "str"),
        "brand_id": (ShopGoods.brand_id, "num"), "supplier_id": (ShopGoods.supplier_id, "num"),
        "supplier": (ShopGoods.supplier, "str"), "cost_price": (ShopGoods.cost_price, "num"),
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


@router.get("/goods")
def list_goods(take: int | None = None, skip: int = 0, sort: str | None = None, filter: str | None = None,
               db: Session = Depends(get_db)):
    """不带 take 返回全部（数组）；带 take 做服务端分页，返回 {items, total}。
    sort / filter 为 DevExtreme 表格的 JSON 参数，字段见 _goods_query_fields。"""
    q = select(ShopGoods)
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
    stats = _sku_stats(db, [g.id for g in rows])
    items = _attach(db, "goods", [_goods_dict(g, *stats.get(g.id, (0, 0))) for g in rows], ["name"])
    return ok(items if take is None else {"items": items, "total": total})


@router.get("/goods/{gid}")
def get_goods(gid: int, db: Session = Depends(get_db)):
    g = _get_goods(db, gid)
    images = db.scalars(select(ShopGoodsImage.url).where(ShopGoodsImage.goods_id == gid)
                        .order_by(ShopGoodsImage.sort_order, ShopGoodsImage.id)).all()
    detail = {**_goods_dict(g, *_sku_stats(db, [gid]).get(gid, (0, 0))), "description": g.description or "",
              "attr_values": g.attr_values or {}, "images": list(images)}
    return ok(_attach(db, "goods", [detail], ["name", "description", "attr_values"])[0])


@router.post("/goods")
def create_goods(values: dict, db: Session = Depends(get_db)):
    g = ShopGoods()
    images = _apply_goods(db, g, values, True)
    db.add(g)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        fail("商品编码已存在")
    if images:
        _replace_images(db, g.id, images)
    save_inline(db, "goods", g, values.get("i18n"))
    db.commit()
    return ok(_attach(db, "goods", [_goods_dict(g)], ["name"])[0])


@router.put("/goods/{gid}")
def update_goods(gid: int, values: dict, db: Session = Depends(get_db)):
    g = _get_goods(db, gid)
    images = _apply_goods(db, g, values, False)
    if images is not None:
        _replace_images(db, gid, images)
    _save(db, "商品编码已存在", "goods", g, values)
    return ok(_attach(db, "goods", [_goods_dict(g, *_sku_stats(db, [gid]).get(gid, (0, 0)))], ["name"])[0])


@router.post("/goods/batch-status")
def batch_goods_status(body: dict, db: Session = Depends(get_db)):
    """批量上架 / 下架。body: {"ids": [1,2,...], "status": true|false}；返回实际更新的条数。"""
    ids = body.get("ids")
    if not isinstance(ids, list) or not ids or len(ids) > 500 or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        fail("请选择 1~500 个商品")
    if not isinstance(body.get("status"), bool):
        fail("参数不合法")
    res = db.execute(update(ShopGoods).where(ShopGoods.id.in_(ids)).values(status=1 if body["status"] else 0))
    db.commit()
    return ok({"updated": res.rowcount})


@router.delete("/goods/{gid}")
def delete_goods(gid: int, db: Session = Depends(get_db)):
    g = _get_goods(db, gid)
    purge_translations(db, "sku", list(db.scalars(select(ShopGoodsSku.id).where(ShopGoodsSku.goods_id == gid))))
    purge_translations(db, "goods", [gid])
    db.execute(delete(ShopGoodsImage).where(ShopGoodsImage.goods_id == gid))
    db.execute(delete(ShopGoodsSku).where(ShopGoodsSku.goods_id == gid))
    db.delete(g)
    db.commit()
    return ok()


# ---------------------------------------------------------------- SKU
def _sku_dict(s: ShopGoodsSku) -> dict:
    return {"id": s.id, "goods_id": s.goods_id, "sku_code": s.sku_code, "spec_name": s.spec_name,
            "cost_price": float(s.cost_price), "sale_price": float(s.sale_price), "stock": s.stock,
            "status": bool(s.status)}


def _apply_sku(s: ShopGoodsSku, values: dict, creating: bool) -> None:
    if "sku_code" in values or creating:
        s.sku_code = _text(values, "sku_code", "SKU编码", 64, required=True)
    if "spec_name" in values or creating:
        s.spec_name = _text(values, "spec_name", "规格", 200)
    for f, label in (("cost_price", "拿货价"), ("sale_price", "销售价")):
        if f in values or creating:
            setattr(s, f, _money(values, f, label))
    if "stock" in values or creating:
        s.stock = _int(values, "stock", "库存", -1_000_000, 1_000_000_000)
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
    _apply_sku(s, values, True)
    db.add(s)
    _save(db, "SKU编码已存在", "sku", s, values)
    return ok(_attach(db, "sku", [_sku_dict(s)], ["spec_name"])[0])


def _get_sku(db: Session, gid: int, sid: int) -> ShopGoodsSku:
    s = db.get(ShopGoodsSku, sid)
    if s is None or s.goods_id != gid:
        fail("SKU不存在", 404)
    return s


@router.put("/goods/{gid}/skus/{sid}")
def update_sku(gid: int, sid: int, values: dict, db: Session = Depends(get_db)):
    s = _get_sku(db, gid, sid)
    _apply_sku(s, values, False)
    _save(db, "SKU编码已存在", "sku", s, values)
    return ok(_attach(db, "sku", [_sku_dict(s)], ["spec_name"])[0])


@router.delete("/goods/{gid}/skus/{sid}")
def delete_sku(gid: int, sid: int, db: Session = Depends(get_db)):
    s = _get_sku(db, gid, sid)
    purge_translations(db, "sku", [s.id])
    db.delete(s)
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
