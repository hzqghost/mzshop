"""系统通用属性：校验、币种字典、默认币种种子。表结构见 contracts/ddl/012_sys_attr.sql。"""
import json
import re

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Supplier, SupplierCatalogItem, SysAttrType, SysAttrValue

CURRENCY_CODE = "currency"
_TYPE_CODE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,29}$")
_FIELD = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,29}$")
_EXT_TYPES = {"integer", "number", "text", "checkbox", "input"}

CURRENCY_SCHEMA = [{
    "group": "finance",
    "caption": "财务属性",
    "items": [{"type": "number", "caption": "对人民币汇率", "field": "cny_rate", "required": 0, "min": 0}],
}]
CURRENCY_VALUES = (
    {"cn_name": "人民币", "en_name": "Chinese Yuan", "code": "CNY", "sort_order": 1, "ext_values": {"cny_rate": 1}},
    {"cn_name": "美元", "en_name": "US Dollar", "code": "USD", "sort_order": 2, "ext_values": None},
    {"cn_name": "欧元", "en_name": "Euro", "code": "EUR", "sort_order": 3, "ext_values": None},
)


def fail(msg: str, status: int = 400):
    raise HTTPException(status_code=status, detail=msg)


def fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def _text(raw, label: str, size: int, required: bool = False) -> str:
    v = str(raw or "").strip()
    if required and not v:
        fail(f"请填写{label}")
    if len(v) > size:
        fail(f"{label}最长 {size} 个字符")
    return v


def schema_fields(schema) -> dict[str, dict]:
    fields = {}
    for group in schema or []:
        for item in group.get("items") or []:
            fields[item["field"]] = item
    return fields


def parse_schema(raw) -> list | None:
    """扩展字段 schema：分组数组。空串 / null 表示没有扩展字段。"""
    if raw in (None, "", "null"):
        return None
    if isinstance(raw, str):
        if len(raw) > 8000:
            fail("扩展字段 Schema 过长")
        try:
            raw = json.loads(raw)
        except ValueError:
            fail("扩展字段 Schema 不是合法的 JSON")
    if raw in (None, []):
        return None
    if not isinstance(raw, list):
        fail("扩展字段 Schema 须为分组数组")
    out = []
    seen = set()
    for group in raw:
        if not isinstance(group, dict) or not isinstance(group.get("items") or [], list):
            fail("扩展字段 Schema 的分组格式不正确")
        items = []
        for item in group.get("items") or []:
            if not isinstance(item, dict):
                fail("扩展字段 Schema 的字段格式不正确")
            field = str(item.get("field") or "").strip()
            kind = str(item.get("type") or "text").strip()
            if not _FIELD.match(field):
                fail(f"扩展字段名不合法：{field or '空'}")
            if kind not in _EXT_TYPES:
                fail(f"扩展字段类型不支持：{kind}")
            if field in seen:
                fail(f"扩展字段名重复：{field}")
            seen.add(field)
            clean = {"type": "number" if kind == "input" else kind, "caption": _text(item.get("caption"), "扩展字段标题", 50) or field, "field": field}
            if item.get("required"):
                clean["required"] = 1
            for key in ("min", "max", "minLength", "maxLength"):
                if item.get(key) not in (None, ""):
                    try:
                        clean[key] = int(item[key]) if key.endswith("Length") or kind == "integer" else float(item[key])
                    except (TypeError, ValueError):
                        fail(f"扩展字段 {field} 的 {key} 不是数字")
            items.append(clean)
        out.append({"group": _text(group.get("group"), "分组标识", 30), "caption": _text(group.get("caption"), "分组标题", 50), "items": items})
    return out or None


def _coerce_ext(item: dict, raw):
    kind = item["type"]
    caption = item.get("caption") or item["field"]
    if kind == "checkbox":
        return bool(raw)
    if kind == "text":
        text = str(raw if raw is not None else "").strip()
        min_len = int(item.get("minLength") or 0)
        max_len = int(item.get("maxLength") or 100)
        if len(text) < min_len or len(text) > max_len:
            fail(f"{caption}长度需在 {min_len}~{max_len}")
        return text
    if kind == "integer":
        try:
            num = int(raw)
        except (TypeError, ValueError):
            fail(f"{caption}需为整数")
        if isinstance(raw, float) and not raw.is_integer():
            fail(f"{caption}需为整数")
    else:
        try:
            num = float(raw)
        except (TypeError, ValueError):
            fail(f"{caption}需为数字")
    if "min" in item and num < item["min"]:
        fail(f"{caption}不能小于 {item['min']}")
    if "max" in item and num > item["max"]:
        fail(f"{caption}不能大于 {item['max']}")
    return num


def clean_ext(schema, raw, base: dict | None) -> dict | None:
    """按 schema 整理扩展值。raw 为本次提交的字段（可只含改过的键），与 base 合并。"""
    fields = schema_fields(schema)
    if raw in (None, "", {}):
        incoming = {}
    elif isinstance(raw, str):
        try:
            incoming = json.loads(raw)
        except ValueError:
            fail("扩展字段不是合法的 JSON")
    elif isinstance(raw, dict):
        incoming = raw
    else:
        fail("扩展字段格式不正确")
    if not isinstance(incoming, dict):
        fail("扩展字段格式不正确")
    merged = dict(base or {})
    for key, value in incoming.items():
        if key not in fields:
            continue
        if value in (None, ""):
            merged.pop(key, None)
        else:
            merged[key] = _coerce_ext(fields[key], value)
    for key, item in fields.items():
        if item.get("required") and key not in merged:
            fail(f"请填写{item.get('caption') or key}")
    return merged or None


def ensure_currency(db: Session) -> None:
    """没有「币种」类型时写入类型和人民币 / 美元 / 欧元。已有类型则不补回被删掉的取值。"""
    row = db.scalar(select(SysAttrType).where(SysAttrType.code == CURRENCY_CODE))
    if row is not None:
        return
    row = SysAttrType(code=CURRENCY_CODE, cn_name="币种", en_name="Currency", is_tree=0, use_code=1,
                      ext_schema=CURRENCY_SCHEMA, sort_order=1)
    db.add(row)
    db.flush()
    for item in CURRENCY_VALUES:
        db.add(SysAttrValue(type_id=row.id, cn_name=item["cn_name"], en_name=item["en_name"], code=item["code"],
                            sort_order=item["sort_order"], ext_values=item["ext_values"], status=1))
    db.commit()


def enabled_codes(db: Session, type_code: str) -> set[str]:
    type_id = db.scalar(select(SysAttrType.id).where(SysAttrType.code == type_code))
    if not type_id:
        return set()
    rows = db.scalars(select(SysAttrValue.code).where(
        SysAttrValue.type_id == type_id, SysAttrValue.status == 1, SysAttrValue.code.is_not(None)))
    return {str(code).upper() for code in rows if code}


def normalize_currency(db: Session, raw, previous: str | None = None) -> str:
    """业务侧币种：空为未设置；新值必须是启用中的币种编码。未改动的旧值允许暂时保留。"""
    code = str(raw or "").strip().upper()
    if code and (len(code) != 3 or not code.isalpha() or not code.isascii()):
        fail("币种为 3 位英文代码，如 USD / CNY")
    prev = str(previous or "").strip().upper()
    if not code or code == prev:
        return code
    if code not in enabled_codes(db, CURRENCY_CODE):
        fail(f"币种「{code}」不在通用属性中，请先到「属性值」里维护")
    return code


def currency_usage(db: Session, code: str) -> tuple[int, int]:
    if not code:
        return 0, 0
    suppliers = db.scalar(select(func.count()).where(Supplier.default_currency == code)) or 0
    items = db.scalar(select(func.count()).where(SupplierCatalogItem.currency == code)) or 0
    return int(suppliers), int(items)


def _usage_message(suppliers: int, items: int) -> str:
    parts = []
    if suppliers:
        parts.append(f"{suppliers} 个供应商")
    if items:
        parts.append(f"{items} 个目录条目")
    return "、".join(parts)


def type_dict(row: SysAttrType, value_count: int = 0) -> dict:
    schema = row.ext_schema or None
    return {"id": row.id, "code": row.code, "cn_name": row.cn_name, "en_name": row.en_name or "",
            "is_tree": bool(row.is_tree), "use_code": bool(row.use_code), "sort_order": row.sort_order,
            "ext_schema": schema, "ext_schema_text": json.dumps(schema, ensure_ascii=False, indent=2) if schema else "",
            "value_count": value_count, "created_at": fmt(row.created_at), "updated_at": fmt(row.updated_at)}


def value_dict(row: SysAttrValue) -> dict:
    return {"id": row.id, "type_id": row.type_id, "parent_id": row.parent_id, "cn_name": row.cn_name,
            "en_name": row.en_name or "", "code": row.code or "", "sort_order": row.sort_order,
            "ext_values": row.ext_values or {}, "status": bool(row.status),
            "created_at": fmt(row.created_at), "updated_at": fmt(row.updated_at)}


def apply_type(db: Session, row: SysAttrType, values: dict, creating: bool) -> None:
    if "code" in values or creating:
        code = _text(values.get("code"), "标识码", 30, required=True)
        if not _TYPE_CODE.match(code):
            fail("标识码只能是字母、数字、下划线，以字母开头，最长 30 位")
        if not creating and code != row.code:
            used = db.scalar(select(func.count()).where(SysAttrValue.type_id == row.id)) or 0
            if used:
                fail("该类型已有属性值，不能修改标识码")
        dup = db.scalar(select(SysAttrType.id).where(SysAttrType.code == code, SysAttrType.id != (row.id or 0)))
        if dup:
            fail(f"标识码已存在：{code}")
        row.code = code
    if "cn_name" in values or creating:
        row.cn_name = _text(values.get("cn_name"), "中文名称", 50, required=True)
    if "en_name" in values or creating:
        row.en_name = _text(values.get("en_name"), "英文名称", 50)
    if "is_tree" in values or creating:
        is_tree = 1 if values.get("is_tree") else 0
        if row.id and not is_tree and row.is_tree:
            linked = db.scalar(select(func.count()).where(SysAttrValue.type_id == row.id, SysAttrValue.parent_id.is_not(None))) or 0
            if linked:
                fail("已有下级的属性值，不能取消树型")
        row.is_tree = is_tree
    if "use_code" in values or creating:
        row.use_code = 1 if values.get("use_code", True if creating and row.code == CURRENCY_CODE else False) else 0
    if "sort_order" in values or creating:
        sort_order = int(values.get("sort_order") or 0)
        if sort_order < 0 or sort_order > 999999:
            fail("排序值需在 0~999999 之间")
        row.sort_order = sort_order
    if "ext_schema_text" in values or "ext_schema" in values or creating:
        raw = values.get("ext_schema_text", values.get("ext_schema"))
        row.ext_schema = parse_schema(raw)
    if row.code == CURRENCY_CODE:
        if not row.use_code:
            fail("币种必须启用编码")
        if row.is_tree:
            fail("币种是平铺属性，不能设为树型")


def _parent_ok(db: Session, type_id: int, parent_id: int | None, self_id: int | None) -> None:
    if parent_id is None:
        return
    parent = db.get(SysAttrValue, parent_id)
    if parent is None or parent.type_id != type_id:
        fail("上级必须是同一个属性类型里的属性值")
    seen = set()
    cursor = parent
    while cursor is not None and cursor.id not in seen:
        if self_id is not None and cursor.id == self_id:
            fail("上级不能是自己或自己的下级")
        seen.add(cursor.id)
        cursor = db.get(SysAttrValue, cursor.parent_id) if cursor.parent_id else None


def apply_value(db: Session, row: SysAttrValue, values: dict, creating: bool) -> None:
    if creating:
        type_id = int(values.get("type_id") or 0)
    else:
        type_id = row.type_id
        if "type_id" in values and int(values.get("type_id") or 0) not in (0, type_id):
            fail("不能修改属性值所属的类型")
    attr_type = db.get(SysAttrType, type_id) or fail("属性类型不存在", 404)
    if creating:
        row.type_id = type_id
    if "cn_name" in values or creating:
        row.cn_name = _text(values.get("cn_name"), "中文名称", 100, required=True)
    if "en_name" in values or creating:
        row.en_name = _text(values.get("en_name"), "英文名称", 100)
    if "sort_order" in values or creating:
        sort_order = int(values.get("sort_order") or 0)
        if sort_order < 0 or sort_order > 999999:
            fail("排序值需在 0~999999 之间")
        row.sort_order = sort_order
    if "status" in values:
        row.status = 1 if values.get("status") else 0
    elif creating:
        row.status = 1

    if attr_type.is_tree and ("parent_id" in values or creating):
        raw_parent = values.get("parent_id")
        parent_id = None if raw_parent in (None, "", 0, "0") else int(raw_parent)
        _parent_ok(db, type_id, parent_id, None if creating else row.id)
        row.parent_id = parent_id
    elif not attr_type.is_tree:
        row.parent_id = None

    old_code = row.code or ""
    if attr_type.use_code and ("code" in values or creating):
        code = _text(values.get("code"), "编码", 50, required=True)
        if attr_type.code == CURRENCY_CODE:
            code = code.upper()
            if len(code) != 3 or not code.isalpha() or not code.isascii():
                fail("币种编码为 3 位英文代码，如 USD / CNY")
        dup = db.scalar(select(SysAttrValue.id).where(
            SysAttrValue.type_id == type_id, func.lower(SysAttrValue.code) == code.lower(),
            SysAttrValue.id != (row.id or 0)))
        if dup:
            fail(f"编码已存在：{code}")
        if not creating and old_code and code != old_code and attr_type.code == CURRENCY_CODE:
            suppliers, items = currency_usage(db, old_code)
            if suppliers or items:
                fail(f"编码 {old_code} 已被{_usage_message(suppliers, items)}使用，不能修改")
        row.code = code
    elif not attr_type.use_code and creating:
        row.code = None

    parent_id = row.parent_id
    dup_name = db.scalar(select(SysAttrValue.id).where(
        SysAttrValue.type_id == type_id, SysAttrValue.cn_name == row.cn_name,
        SysAttrValue.parent_id.is_(None) if parent_id is None else SysAttrValue.parent_id == parent_id,
        SysAttrValue.id != (row.id or 0)))
    if dup_name:
        fail(f"同一上级下中文名称已存在：{row.cn_name}")

    if "ext_values" in values or creating:
        row.ext_values = clean_ext(attr_type.ext_schema, values.get("ext_values"), None if creating else row.ext_values)


def assert_value_deletable(db: Session, row: SysAttrValue) -> None:
    children = db.scalar(select(func.count()).where(SysAttrValue.parent_id == row.id)) or 0
    if children:
        fail("请先删除下级属性值")
    attr_type = db.get(SysAttrType, row.type_id)
    if attr_type and attr_type.code == CURRENCY_CODE and row.code:
        suppliers, items = currency_usage(db, row.code)
        if suppliers or items:
            fail(f"币种 {row.code} 已被{_usage_message(suppliers, items)}使用，不能删除")


def option_dict(row: SysAttrValue) -> dict:
    label = f"{row.cn_name}（{row.code}）" if row.code else row.cn_name
    return {"id": row.id, "code": row.code or "", "cn_name": row.cn_name, "en_name": row.en_name or "", "label": label}
