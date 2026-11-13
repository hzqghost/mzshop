"""商品内容多语言（与后台界面语言无关）。

约定：shop_* 基础表里的文字就是默认语言；其他语言的译文存 shop_translation，读取时缺译回退到默认语言。
响应 {code, data, msg}。
"""
import json
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..catalog import applicable_attributes
from ..db import get_db
from ..deps import require_user
from ..models import Brand, ShopAttribute, ShopCategory, ShopGoods, ShopGoodsSku, ShopLanguage, ShopTranslation

router = APIRouter(prefix="/api/v1/shop", dependencies=[Depends(require_user)])

LANG_CODE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$")

# 可翻译字段：实体类型 → {字段: (录入类型, 最大长度, 中文名)}。录入类型 text / textarea / list(字符串数组) / map(键值，键为默认语言的键)
FIELDS = {
    "category": {"name": ("text", 100, "分类名称")},
    "attribute": {"name": ("text", 100, "属性名称"), "options": ("list", 100, "可选值"), "unit": ("text", 30, "单位")},
    "goods": {"name": ("text", 200, "商品名称"), "description": ("textarea", 20000, "商品描述"),
              "attr_values": ("map", 2000, "属性值")},
    "sku": {"spec_name": ("text", 200, "规格")},
    "brand": {"name": ("text", 100, "品牌名称")},
}
MODELS = {"category": ShopCategory, "attribute": ShopAttribute, "goods": ShopGoods, "sku": ShopGoodsSku,
          "brand": Brand}


def ok(data=None):
    return {"code": 0, "data": data, "msg": "ok"}


def fail(msg: str, status: int = 400):
    raise HTTPException(status_code=status, detail=msg)


def purge_translations(db: Session, entity_type: str, ids: list[int], field: str | None = None) -> None:
    """实体删除时清掉它的译文（无外键，应用层级联）；给了 field 则只清该字段的译文。"""
    if ids:
        q = delete(ShopTranslation).where(ShopTranslation.entity_type == entity_type, ShopTranslation.entity_id.in_(ids))
        if field:
            q = q.where(ShopTranslation.field_name == field)
        db.execute(q)


# ---------------------------------------------------------------- 语言
def _lang_dict(l: ShopLanguage) -> dict:
    return {"id": l.id, "code": l.code, "name": l.name, "is_default": bool(l.is_default),
            "sort_order": l.sort_order, "status": bool(l.status)}


def _languages(db: Session) -> list[ShopLanguage]:
    return list(db.scalars(select(ShopLanguage).order_by(ShopLanguage.sort_order, ShopLanguage.id)))


@router.get("/languages")
def list_languages(db: Session = Depends(get_db)):
    return ok([_lang_dict(l) for l in _languages(db)])


def _apply_lang(db: Session, l: ShopLanguage, values: dict, creating: bool) -> None:
    if creating:
        code = str(values.get("code") or "").strip()
        if not LANG_CODE.match(code):
            fail("语言代码格式不正确，如 en、ja、zh-CN")
        l.code = code
    if "name" in values or creating:
        name = str(values.get("name") or "").strip()
        if not name or len(name) > 50:
            fail("语言名称不能为空且最长 50 个字符")
        l.name = name
    if "sort_order" in values or creating:
        try:
            l.sort_order = int(values.get("sort_order") or 0)
        except (TypeError, ValueError):
            fail("排序需为整数")
    if "status" in values:
        l.status = 1 if values["status"] else 0
    elif creating:
        l.status = 1
    if values.get("is_default") and not l.is_default:
        if l.id is not None and any(db.scalars(select(ShopTranslation.id).where(
                ShopTranslation.lang_code == l.code).limit(1))):
            fail("该语言已有译文，不能直接设为默认语言（默认语言的内容存放在基础字段里）")
        db.execute(update(ShopLanguage).values(is_default=0))
        l.is_default = 1
        l.status = 1
    elif "is_default" in values and not values["is_default"] and l.is_default:
        fail("必须有一个默认语言，请直接把另一种语言设为默认")


@router.post("/languages")
def create_language(values: dict, db: Session = Depends(get_db)):
    l = ShopLanguage(is_default=0)
    _apply_lang(db, l, values, True)
    db.add(l)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fail("语言代码已存在")
    return ok(_lang_dict(l))


@router.put("/languages/{lid}")
def update_language(lid: int, values: dict, db: Session = Depends(get_db)):
    l = db.get(ShopLanguage, lid) or fail("语言不存在", 404)
    values.pop("code", None)  # 代码创建后不可改，译文按代码关联
    _apply_lang(db, l, values, False)
    if l.is_default and not l.status:
        fail("默认语言不能禁用")
    db.commit()
    return ok(_lang_dict(l))


@router.delete("/languages/{lid}")
def delete_language(lid: int, db: Session = Depends(get_db)):
    l = db.get(ShopLanguage, lid) or fail("语言不存在", 404)
    if l.is_default:
        fail("默认语言不能删除")
    db.execute(delete(ShopTranslation).where(ShopTranslation.lang_code == l.code))
    db.delete(l)
    db.commit()
    return ok()


# ---------------------------------------------------------------- 译文
def _entity(db: Session, entity_type: str, eid: int):
    if entity_type not in FIELDS:
        fail("不支持的类型", 404)
    return db.get(MODELS[entity_type], eid) or fail("对象不存在", 404)


def _default_values(entity_type: str, e) -> dict:
    """默认语言下的值；属性的「可选值」只对单选属性有意义。"""
    d = {f: getattr(e, f) for f in FIELDS[entity_type]}
    if entity_type == "attribute" and e.input_type not in ("select", "multiselect"):
        d.pop("options")
    if entity_type == "attribute" and e.input_type != "number":
        d.pop("unit")
    for f, (kind, _, _) in FIELDS[entity_type].items():
        if f in d and kind == "list":
            d[f] = d[f] or []
        elif f in d and kind == "map":
            d[f] = d[f] or {}
        elif f in d:
            d[f] = d[f] or ""
    return d


def _decode(kind: str, content: str):
    if kind in ("list", "map"):
        try:
            return json.loads(content)
        except ValueError:
            return [] if kind == "list" else {}
    return content


@router.get("/i18n/{entity_type}/{eid}")
def get_translations(entity_type: str, eid: int, db: Session = Depends(get_db)):
    e = _entity(db, entity_type, eid)
    defaults = _default_values(entity_type, e)
    langs = [l for l in _languages(db) if not l.is_default]
    rows = db.scalars(select(ShopTranslation).where(ShopTranslation.entity_type == entity_type,
                                                    ShopTranslation.entity_id == eid))
    trans: dict[str, dict] = {l.code: {} for l in langs}
    for r in rows:
        meta = FIELDS[entity_type].get(r.field_name)
        if r.lang_code in trans and meta and r.field_name in defaults:
            trans[r.lang_code][r.field_name] = _decode(meta[0], r.content)
    return ok({
        "fields": [{"field": f, "kind": FIELDS[entity_type][f][0], "label": FIELDS[entity_type][f][2]} for f in defaults],
        "defaults": defaults,
        "languages": [{"code": l.code, "name": l.name} for l in langs],
        "translations": trans,
    })


def _clean(kind: str, size: int, label: str, raw, default):
    """校验并规整一个字段的译文；返回 None 表示视为空（删除该译文）。"""
    if kind in ("text", "textarea"):
        v = str(raw or "").strip()
        if len(v) > size:
            fail(f"{label}最长 {size} 个字符")
        return v or None
    if kind == "list":
        if not isinstance(raw, list):
            fail(f"{label}格式不正确")
        v = [str(x).strip() for x in raw]
        if len(v) != len(default) and any(v):
            fail(f"{label}的数量需与默认语言一致（{len(default)} 个），按顺序一一对应")
        if any(len(x) > size for x in v):
            fail(f"{label}单项最长 {size} 个字符")
        return v if any(v) else None
    if not isinstance(raw, dict):
        fail(f"{label}格式不正确")
    v = {str(k): str(x).strip() for k, x in raw.items() if str(k) in default and str(x).strip()}
    if any(len(x) > size for x in v.values()):
        fail(f"{label}单项最长 {size} 个字符")
    return v or None


def inline_languages(db: Session) -> list[str]:
    """列表页 / 表单里直接显示的语言：启用的非默认语言。"""
    return [l.code for l in _languages(db) if not l.is_default and l.status]


def load_inline(db: Session, entity_type: str, ids: list[int], fields: list[str]) -> dict[int, dict]:
    """批量取译文，返回 {实体ID: {语言: {字段: 值}}}；缺译的字段给空值（文本 ""、键值 {}），便于表格/表单直接绑定。"""
    codes = inline_languages(db)

    def blank(f):
        return {"map": {}, "list": []}.get(FIELDS[entity_type][f][0], "")

    out = {i: {c: {f: blank(f) for f in fields} for c in codes} for i in ids}
    if ids and codes:
        rows = db.scalars(select(ShopTranslation).where(
            ShopTranslation.entity_type == entity_type, ShopTranslation.entity_id.in_(ids),
            ShopTranslation.lang_code.in_(codes), ShopTranslation.field_name.in_(fields)))
        for r in rows:
            out[r.entity_id][r.lang_code][r.field_name] = _decode(FIELDS[entity_type][r.field_name][0], r.content)
    return out


def save_inline(db: Session, entity_type: str, entity, i18n) -> None:
    """保存随实体一起提交的译文 `i18n: {语言: {字段: 值}}`，不提交事务；校验失败抛 400，调用方不 commit 即整体回滚。"""
    if i18n is None:
        return
    if not isinstance(i18n, dict):
        fail("参数不合法")
    allowed = set(inline_languages(db))
    data = {c: f for c, f in i18n.items() if c in allowed}  # 没启用的语言直接忽略
    _store(db, entity_type, entity, data, allowed)


@router.put("/i18n/{entity_type}/{eid}")
def save_translations(entity_type: str, eid: int, body: dict, db: Session = Depends(get_db)):
    """body: {"translations": {"en": {"name": "...", ...}, ...}}；传了的语言×字段整体覆盖，空值即删除该译文，没传的不动。"""
    e = _entity(db, entity_type, eid)
    langs = {l.code for l in _languages(db) if not l.is_default}
    data = body.get("translations")
    if not isinstance(data, dict):
        fail("参数不合法")
    _store(db, entity_type, e, data, langs)
    db.commit()
    return ok()


def _store(db: Session, entity_type: str, e, data: dict, langs: set) -> None:
    eid = e.id
    defaults = _default_values(entity_type, e)
    for code, fields in data.items():
        if code not in langs:
            fail(f"语言 {code} 不存在或是默认语言")
        if not isinstance(fields, dict):
            fail("参数不合法")
        for f, raw in fields.items():
            if f not in defaults:
                continue
            kind, size, label = FIELDS[entity_type][f]
            value = _clean(kind, size, label, raw, defaults[f])
            row = db.scalar(select(ShopTranslation).where(
                ShopTranslation.entity_type == entity_type, ShopTranslation.entity_id == eid,
                ShopTranslation.lang_code == code, ShopTranslation.field_name == f))
            if value is None:
                if row:
                    db.delete(row)
                continue
            content = json.dumps(value, ensure_ascii=False) if kind in ("list", "map") else value
            if row:
                row.content = content
            else:
                db.add(ShopTranslation(entity_type=entity_type, entity_id=eid, lang_code=code, field_name=f, content=content))
    db.flush()


# ---------------------------------------------------------------- 取某语言版本（供前台/下游使用，缺译回退默认语言）
def _load_trans(db: Session, entity_type: str, ids: list[int], lang: str) -> dict[tuple[int, str], str]:
    if not ids:
        return {}
    rows = db.scalars(select(ShopTranslation).where(
        ShopTranslation.entity_type == entity_type, ShopTranslation.entity_id.in_(ids), ShopTranslation.lang_code == lang))
    return {(r.entity_id, r.field_name): r.content for r in rows}


@router.get("/goods/{gid}/localized")
def localized_goods(gid: int, lang: str, db: Session = Depends(get_db)):
    """商品的指定语言版本：名称、描述、分类、属性、规格。缺译的字段回退为默认语言，`fallback` 列出回退了的字段。"""
    g = db.get(ShopGoods, gid) or fail("商品不存在", 404)
    langs = {l.code: l for l in _languages(db)}
    if lang not in langs or not langs[lang].status:
        fail("语言不存在或已禁用", 404)
    is_default = bool(langs[lang].is_default)
    fallback: list[str] = []

    def pick(entity_type, e, field, default):
        if is_default:
            return default
        raw = _load.get((entity_type, e.id, field))
        if raw is None:
            fallback.append(f"{entity_type}.{e.id}.{field}")
            return default
        return _decode(FIELDS[entity_type][field][0], raw)

    skus = list(db.scalars(select(ShopGoodsSku).where(ShopGoodsSku.goods_id == gid).order_by(ShopGoodsSku.id)))
    cat = db.get(ShopCategory, g.category_id) if g.category_id else None
    brand = db.get(Brand, g.brand_id) if g.brand_id else None
    attrs = applicable_attributes(db, g.category_id)  # 含上级分类继承来的属性
    _load = {}
    if not is_default:
        for et, ids in (("goods", [gid]), ("sku", [s.id for s in skus]), ("category", [cat.id] if cat else []),
                        ("brand", [brand.id] if brand else []), ("attribute", [a.id for a in attrs])):
            for (i, f), c in _load_trans(db, et, ids, lang).items():
                _load[(et, i, f)] = c

    attr_vals = g.attr_values or {}
    # 文本属性的译文（没有就是空字典）；不能用 pick 的回退结果，否则会把默认值当译文，挡住下面单选属性的可选值译文
    tr_vals = {} if is_default else _decode("map", _load.get(("goods", g.id, "attr_values"), "{}"))
    out_attrs = []
    for a in attrs:
        if a.name not in attr_vals:
            continue
        v = attr_vals[a.name]
        if a.input_type == "number":
            pass  # 数字不用翻译，单位在下面按语言取
        elif not is_default and isinstance(tr_vals, dict) and a.name in tr_vals:
            v = tr_vals[a.name]
        elif not is_default and a.input_type in ("select", "multiselect"):
            opts = _decode("list", _load.get(("attribute", a.id, "options"), "[]"))
            base = a.options or []

            def tr(x):  # 按序号取可选值译文，缺译回退默认值
                i = base.index(x) if x in base else -1
                return opts[i] if 0 <= i < len(opts) and opts[i] else x
            v = [tr(x) for x in v] if isinstance(v, list) else tr(v)
        unit = pick("attribute", a, "unit", a.unit) if a.input_type == "number" and a.unit else ""
        out_attrs.append({"name": pick("attribute", a, "name", a.name), "value": v, "unit": unit})
    return ok({
        "id": g.id, "goods_no": g.goods_no, "lang": lang,
        "name": pick("goods", g, "name", g.name), "description": pick("goods", g, "description", g.description or ""),
        "category": pick("category", cat, "name", cat.name) if cat else None,
        "brand": pick("brand", brand, "name", brand.name) if brand else None,
        "attributes": out_attrs,
        "skus": [{"id": s.id, "sku_code": s.sku_code, "spec_name": pick("sku", s, "spec_name", s.spec_name)} for s in skus],
        "fallback": fallback,
    })
