"""供应商产品目录：供应商档案、品牌字典、目录条目（选品池）与 Excel 导入向导。响应 {code, data, msg}。"""
import json
import re
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from openpyxl import load_workbook
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import BASE_DIR
from ..attr_dict import enabled_codes, normalize_currency
from ..db import get_db
from ..deps import require_user
from ..listquery import build_filter, build_sort, clamp_page, parse_json
from ..models import Brand, ShopAttribute, ShopCategory, ShopGoods, ShopGoodsImage, Supplier, SupplierCatalogItem

router = APIRouter(prefix="/api/v1/supplier-catalog", dependencies=[Depends(require_user)])

MAX_UPLOAD = 10 * 1024 * 1024
MAX_ROWS = 5000
MAX_COLUMNS = 100
PREVIEW_ROWS = 20
MAX_ERRORS = 100
ITEM_STATUS = {0: "待核对", 1: "已核对", 2: "已选品", 3: "已忽略"}

# 导入可映射的标准字段；supplier_sku / name 必须映射
STANDARD_TARGETS = {
    "supplier_sku": "货号/SKU",
    "name": "产品名称",
    "brand_name": "品牌",
    "category_name": "分类",
    "price": "价格",
    "currency": "币种",
    "stock": "库存",
    "moq": "起订量",
    "main_image_url": "图片链接",
    "source_url": "产品链接",
    "description": "描述",
}

KEYWORD_MAP = {
    "supplier_sku": ("货号", "货品编号", "商品编码", "型号", "sku", "item", "model", "part"),
    "name": ("名称", "品名", "产品名", "商品名", "标题", "name", "title"),
    "brand_name": ("品牌", "brand"),
    "category_name": ("分类", "类目", "品类", "category"),
    "price": ("价格", "单价", "报价", "售价", "price"),
    "currency": ("币种", "货币", "currency"),
    "stock": ("库存", "数量", "stock", "qty", "quantity"),
    "moq": ("起订量", "moq"),
    "main_image_url": ("图片", "主图", "image", "pic"),
    "source_url": ("链接", "网址", "url", "link"),
    "description": ("描述", "详情", "说明", "description"),
}

PRICE_FREE = {"面议", "电议", "待定", "询价", "议价", "来电咨询"}


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


# 资料编辑器上传：图片走文件头校验；文档只允许白名单扩展名 + 对应文件头
MATERIAL_DIR = BASE_DIR / "static" / "uploads"
MAX_IMAGE_UPLOAD = 8 * 1024 * 1024
MAX_FILE_UPLOAD = 20 * 1024 * 1024
MAX_MEDIA = 20
IMAGE_EXT = {
    ".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",), ".png": (b"\x89PNG\r\n\x1a\n",),
    ".gif": (b"GIF87a", b"GIF89a"), ".webp": (b"RIFF",),
}
FILE_EXT = {
    ".pdf": (b"%PDF",),
    ".doc": (b"\xd0\xcf\x11\xe0",), ".xls": (b"\xd0\xcf\x11\xe0",), ".ppt": (b"\xd0\xcf\x11\xe0",),
    ".docx": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    ".xlsx": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    ".pptx": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    ".zip": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
}
TEXT_EXT = {".txt", ".csv"}


def _material_name(filename: str, ext: str) -> str:
    name = (filename or "").replace("\\", "/").split("/")[-1].strip()
    if not name or name in (".", ".."):
        name = "file" + ext
    return name[:180]


@router.post("/uploads")
async def upload_material(file: UploadFile = File(...)):
    """资料里的图片 / 文件。返回 {url, name, kind}，kind 为 image 或 file。"""
    filename = file.filename or ""
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    kind = "image" if ext in IMAGE_EXT else "file" if ext in FILE_EXT or ext in TEXT_EXT else ""
    if not kind:
        fail("仅支持图片（jpg/png/gif/webp）和文件（pdf/doc/docx/xls/xlsx/ppt/pptx/txt/csv/zip）")
    limit = MAX_IMAGE_UPLOAD if kind == "image" else MAX_FILE_UPLOAD
    data = await file.read(limit + 1)
    if not data:
        fail("文件是空的")
    if len(data) > limit:
        fail("图片不能超过 8MB" if kind == "image" else "文件不能超过 20MB")
    if kind == "image":
        if not data.startswith(IMAGE_EXT[ext]) or (ext == ".webp" and data[8:12] != b"WEBP"):
            fail("文件内容不是有效的图片")
    elif ext in FILE_EXT and not data.startswith(FILE_EXT[ext]):
        fail("文件内容与扩展名不符")
    elif ext in TEXT_EXT:
        head = data[:64].lstrip().lower()
        if head.startswith((b"mz", b"\x7felf", b"<script", b"<?php", b"<html", b"<!doctype")):
            fail("文件内容不被允许")
    folder = MATERIAL_DIR / datetime.now().strftime("%Y%m")
    folder.mkdir(parents=True, exist_ok=True)
    stored = uuid.uuid4().hex + ext
    (folder / stored).write_bytes(data)
    return ok({"url": f"/static/uploads/{folder.name}/{stored}", "name": _material_name(filename, ext), "kind": kind})


# 只认本系统写入的随机文件名，避免按正文里的地址删到目录外面
_UPLOAD_URL = re.compile(r"/static/uploads/\d{6}/[0-9a-f]{32}\.[a-z0-9]{1,8}")


def _upload_urls(html: str | None) -> set[str]:
    return set(_UPLOAD_URL.findall(html or ""))


def _upload_in_use(db: Session, url: str) -> bool:
    """产品资料、图片列表、附件列表、目录主图、商品图片、商品描述、品牌 Logo 任一还引用着这个地址，就不能删。"""
    like = f"%{url}%"
    if db.scalar(select(SupplierCatalogItem.id).where(SupplierCatalogItem.remark.like(like)).limit(1)):
        return True
    if db.scalar(select(SupplierCatalogItem.id).where(func.json_search(SupplierCatalogItem.images, "one", url, None, "$[*].url").isnot(None)).limit(1)):
        return True
    if db.scalar(select(SupplierCatalogItem.id).where(func.json_search(SupplierCatalogItem.attachments, "one", url, None, "$[*].url").isnot(None)).limit(1)):
        return True
    if db.scalar(select(SupplierCatalogItem.id).where(SupplierCatalogItem.main_image_url == url).limit(1)):
        return True
    if db.scalar(select(ShopGoods.id).where(ShopGoods.main_image_url == url).limit(1)):
        return True
    if db.scalar(select(ShopGoods.id).where(ShopGoods.description.like(like)).limit(1)):
        return True
    if db.scalar(select(ShopGoodsImage.id).where(ShopGoodsImage.url == url).limit(1)):
        return True
    if db.scalar(select(Brand.id).where(Brand.logo_url == url).limit(1)):
        return True
    return False


def _unlink_upload(url: str) -> bool:
    m = re.fullmatch(r"/static/uploads/(\d{6})/([0-9a-f]{32}\.[a-z0-9]{1,8})", url)
    if not m:
        return False
    path = (MATERIAL_DIR / m.group(1) / m.group(2)).resolve()
    root = MATERIAL_DIR.resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return False
    path.unlink()
    return True


def _listed_upload_urls(raw) -> set[str]:
    urls: set[str] = set()
    if not isinstance(raw, list):
        return urls
    for item in raw:
        url = item.get("url") if isinstance(item, dict) else item if isinstance(item, str) else ""
        if isinstance(url, str) and _UPLOAD_URL.fullmatch(url):
            urls.add(url)
    return urls


def _item_upload_urls(remark, images, attachments, main_image_url) -> set[str]:
    """这条产品上还挂着的本系统上传文件：资料、图片列表、附件列表、主图。"""
    urls = _upload_urls(remark) | _listed_upload_urls(images) | _listed_upload_urls(attachments)
    if isinstance(main_image_url, str) and _UPLOAD_URL.fullmatch(main_image_url):
        urls.add(main_image_url)
    return urls


def _release_uploads(db: Session, old_urls: set[str], new_urls: set[str]) -> None:
    """旧内容里有、新内容里没有，且没有其他地方引用的上传文件，从磁盘删除。"""
    for url in old_urls - new_urls:
        if not _upload_in_use(db, url):
            _unlink_upload(url)


_HTTP_URL = re.compile(r"^https?://\S{1,480}$")
_FILE_EXT = set(FILE_EXT) | TEXT_EXT


def _media_items(raw, kind: str, label: str) -> list[dict]:
    """图片列表 / 附件列表。图片允许已有的 http(s) 地址（导入的图片链接）；附件只收本系统上传。"""
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        fail(f"{label}格式不正确")
    if len(raw) > MAX_MEDIA:
        fail(f"{label}最多 {MAX_MEDIA} 个")
    out = []
    for item in raw:
        if isinstance(item, dict):
            url = str(item.get("url") or "").strip()
            name = str(item.get("name") or "").replace("\\", "/").split("/")[-1].strip()
        else:
            fail(f"{label}格式不正确")
        if len(url) > 500 or len(name) > 180:
            fail(f"{label}内容过长")
        own = _UPLOAD_URL.fullmatch(url)
        ext = ""
        leaf = url.split("?", 1)[0].split("#", 1)[0].rsplit("/", 1)[-1].lower()
        if "." in leaf:
            ext = "." + leaf.rsplit(".", 1)[-1]
        if kind == "image":
            if own:
                if ext not in IMAGE_EXT:
                    fail("图片列表只接受图片")
            elif not _HTTP_URL.fullmatch(url):
                fail("图片地址不合法")
        elif not own or ext not in _FILE_EXT:
            fail("附件地址不合法")
        out.append({"url": url, "name": name})
    return out


@router.post("/uploads/discard")
def discard_uploads(body: dict, db: Session = Depends(get_db)):
    """保存失败时丢掉刚刚上传、还没有任何资料引用的文件。"""
    urls = body.get("urls")
    if not isinstance(urls, list) or len(urls) > 50:
        fail("参数不正确")
    removed = 0
    for url in urls:
        if isinstance(url, str) and _UPLOAD_URL.fullmatch(url) and not _upload_in_use(db, url) and _unlink_upload(url):
            removed += 1
    return ok({"removed": removed})


def _commit(db: Session, dup_msg: str):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fail(dup_msg)


# ---------------------------------------------------------------- Excel 解析
def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _parse_excel(data: bytes, filename: str, has_header: bool, max_rows: int | None) -> tuple[list[dict], list[tuple[int, dict]], int]:
    """返回 (列信息, [(原表行号, {列key: 值})], 数据总行数)。列 key 用表头文本（重名加序号），无表头用 列N。"""
    if not (filename or "").lower().endswith((".xlsx", ".xlsm")):
        fail("仅支持 .xlsx / .xlsm 格式的 Excel")
    try:
        wb = load_workbook(BytesIO(data), read_only=True, data_only=True)
    except Exception:
        fail("文件不是有效的 Excel（.xlsx / .xlsm），或文件已损坏")
    ws = wb.active
    ncols = ws.max_column
    if ncols > MAX_COLUMNS:
        fail(f"列数过多（{ncols} 列，最多 {MAX_COLUMNS} 列）")
    if ncols == 0:
        fail("Excel 是空的")
    it = ws.iter_rows(values_only=True)
    headers: list[str] = []
    start_line = 1
    if has_header:
        first = next(it, None)
        if first is None:
            fail("Excel 是空的")
        headers = [_cell(v) for v in first]
        start_line = 2
    seen: dict[str, int] = {}
    columns = []
    for i in range(ncols):
        base = headers[i] if i < len(headers) and headers[i] else f"列{i + 1}"
        seen[base] = seen.get(base, 0) + 1
        key = base if seen[base] == 1 else f"{base} ({seen[base]})"
        columns.append({"key": key, "name": base, "sample": ""})
    rows: list[tuple[int, dict]] = []
    total = 0
    for line_no, r in enumerate(it, start=start_line):
        vals = [_cell(v) for v in r]
        if not any(vals):
            continue
        total += 1
        if total > MAX_ROWS:
            fail(f"一次最多导入 {MAX_ROWS} 行（第 {line_no} 行已超出）")
        if max_rows is None or len(rows) < max_rows:
            row = {}
            for i in range(ncols):
                if i < len(vals) and vals[i]:
                    row[columns[i]["key"]] = vals[i]
            rows.append((line_no, row))
        if total == 1:
            for i in range(ncols):
                if i < len(vals) and vals[i]:
                    columns[i]["sample"] = vals[i]
    return columns, rows, total


# ---------------------------------------------------------------- 供应商档案
def _supplier_dict(db: Session, s: Supplier) -> dict:
    cnt = db.scalar(select(func.count()).where(SupplierCatalogItem.supplier_id == s.id))
    return {"id": s.id, "name": s.name, "website": s.website, "contact_name": s.contact_name,
            "contact_phone": s.contact_phone, "contact_email": s.contact_email,
            "default_currency": s.default_currency, "remark": s.remark, "status": bool(s.status),
            "item_count": int(cnt), "has_mapping": bool(s.excel_mapping),
            "created_at": _fmt(s.created_at), "updated_at": _fmt(s.updated_at)}


def _apply_supplier(db: Session, s: Supplier, values: dict, creating: bool) -> None:
    if "name" in values or creating:
        s.name = _text(values, "name", "供应商名称", 100, required=True)
    for f, label, size in (("website", "官网地址", 255), ("contact_name", "联系人", 100),
                           ("contact_phone", "联系电话", 50), ("contact_email", "联系邮箱", 100),
                           ("remark", "备注", 500)):
        if f in values or creating:
            setattr(s, f, _text(values, f, label, size))
    if s.website and not s.website.lower().startswith(("http://", "https://")):
        fail("官网地址需以 http:// 或 https:// 开头")
    if "default_currency" in values or creating:
        s.default_currency = normalize_currency(db, values.get("default_currency"), None if creating else s.default_currency)
    if "status" in values:
        s.status = 1 if values["status"] else 0
    elif creating:
        s.status = 1


@router.get("/suppliers")
def list_suppliers(db: Session = Depends(get_db)):
    rows = db.scalars(select(Supplier).order_by(Supplier.id))
    return ok([_supplier_dict(db, s) for s in rows])


@router.post("/suppliers")
def create_supplier(values: dict, db: Session = Depends(get_db)):
    s = Supplier()
    _apply_supplier(db, s, values, True)
    db.add(s)
    _commit(db, "供应商名称已存在")
    return ok(_supplier_dict(db, s))


@router.put("/suppliers/{sid}")
def update_supplier(sid: int, values: dict, db: Session = Depends(get_db)):
    s = db.get(Supplier, sid) or fail("供应商不存在", 404)
    _apply_supplier(db, s, values, False)
    _commit(db, "供应商名称已存在")
    return ok(_supplier_dict(db, s))


@router.delete("/suppliers/{sid}")
def delete_supplier(sid: int, db: Session = Depends(get_db)):
    s = db.get(Supplier, sid) or fail("供应商不存在", 404)
    if db.scalar(select(func.count()).where(SupplierCatalogItem.supplier_id == sid)):
        fail("该供应商下还有目录条目，不能删除")
    db.delete(s)
    db.commit()
    return ok()


# ---------------------------------------------------------------- 属性名（映射用）
@router.get("/attributes")
def list_attribute_names(db: Session = Depends(get_db)):
    """启用中的商品属性名，导入映射「属性：xxx」目标用。"""
    rows = db.scalars(select(ShopAttribute).where(ShopAttribute.status == 1)
                      .order_by(ShopAttribute.sort_order, ShopAttribute.id))
    return ok([{"name": a.name, "input_type": a.input_type, "unit": a.unit} for a in rows])


# ---------------------------------------------------------------- 目录条目
def _item_dict(i: SupplierCatalogItem, supplier_name: str) -> dict:
    return {"id": i.id, "supplier_id": i.supplier_id, "supplier_name": supplier_name, "supplier_sku": i.supplier_sku,
            "name": i.name, "brand_id": i.brand_id, "brand_name": i.brand_name,
            "category_name": i.category_name, "category_id": i.category_id,
            "price": float(i.price) if i.price is not None else None, "currency": i.currency, "stock": i.stock,
            "moq": i.moq, "main_image_url": i.main_image_url,
            "images": i.images or [], "attachments": i.attachments or [],
            "source_type": i.source_type,
            "source_url": i.source_url, "source_file": i.source_file, "source_row": i.source_row,
            "attrs": i.attrs or {}, "mapped_attrs": i.mapped_attrs or {}, "description": i.description or "",
            "remark": i.remark or "",
            "status": i.status, "goods_id": i.goods_id,
            "created_at": _fmt(i.created_at), "updated_at": _fmt(i.updated_at)}


def _supplier_names(db: Session, ids: list[int]) -> dict[int, str]:
    if not ids:
        return {}
    return dict(db.execute(select(Supplier.id, Supplier.name).where(Supplier.id.in_(ids))).all())


def _apply_item(db: Session, i: SupplierCatalogItem, values: dict, creating: bool) -> None:
    if "supplier_id" in values or creating:
        sid = int(values.get("supplier_id") or 0)
        if not sid or db.get(Supplier, sid) is None:
            fail("请选择供应商")
        if creating or sid != i.supplier_id:
            dup = db.scalar(select(SupplierCatalogItem.id).where(
                SupplierCatalogItem.supplier_id == sid, SupplierCatalogItem.supplier_sku == values.get("supplier_sku", i.supplier_sku)).limit(1))
            if dup:
                fail("该供应商下已有相同货号")
        i.supplier_id = sid
    if "supplier_sku" in values or creating:
        i.supplier_sku = _text(values, "supplier_sku", "货号/SKU", 100, required=True)
    if "name" in values or creating:
        i.name = _text(values, "name", "产品名称", 300, required=True)
    for f, label, size in (("brand_name", "品牌", 100), ("category_name", "分类", 200),
                           ("moq", "起订量", 50), ("source_url", "产品链接", 500)):
        if f in values or creating:
            setattr(i, f, _text(values, f, label, size))
    if "images" in values or creating:
        images = _media_items(values.get("images"), "image", "图片列表")
        i.images = images or None
        i.main_image_url = images[0]["url"] if images else ""
    if "attachments" in values or creating:
        files = _media_items(values.get("attachments"), "file", "附件列表")
        i.attachments = files or None
    if "brand_id" in values or creating:
        bid = int(values.get("brand_id") or 0)
        if bid and db.get(Brand, bid) is None:
            fail("品牌不存在")
        i.brand_id = bid
    if "category_id" in values or creating:
        cid = int(values.get("category_id") or 0)
        if cid and db.get(ShopCategory, cid) is None:
            fail("分类不存在")
        i.category_id = cid
    if "price" in values or creating:
        raw = values.get("price")
        if raw in (None, ""):
            i.price = None
        else:
            try:
                d = Decimal(str(raw)).quantize(Decimal("0.01"))
            except (InvalidOperation, ValueError):
                fail("价格格式不正确")
            if d < 0 or d > Decimal("9999999999.99"):
                fail("价格超出范围")
            i.price = d
    if "currency" in values or creating:
        i.currency = normalize_currency(db, values.get("currency"), None if creating else i.currency)
    if "stock" in values or creating:
        raw = values.get("stock")
        i.stock = None if raw in (None, "") else int(raw)
    if "status" in values or creating:
        st = int(values.get("status") or 0)
        if st not in ITEM_STATUS:
            fail("状态不合法")
        i.status = st
    if "remark" in values or creating:
        raw = values.get("remark")
        if raw in (None, ""):
            i.remark = None
        elif not isinstance(raw, str):
            fail("资料格式不正确")
        elif len(raw) > 200_000:
            fail("资料最长 200000 个字符")
        elif "<script" in raw.lower() or "javascript:" in raw.lower():
            fail("资料里不能包含脚本")
        elif "blob:" in raw.lower() or "data:image" in raw.lower() or "data:application" in raw.lower():
            fail("资料里还有未上传的文件，请重新保存")
        else:
            i.remark = raw


def _items_query_fields(db: Session) -> dict:
    return {
        "id": (SupplierCatalogItem.id, "num"), "supplier_id": (SupplierCatalogItem.supplier_id, "num"),
        "supplier_sku": (SupplierCatalogItem.supplier_sku, "str"), "name": (SupplierCatalogItem.name, "str"),
        "brand_id": (SupplierCatalogItem.brand_id, "num"), "brand_name": (SupplierCatalogItem.brand_name, "str"),
        "category_name": (SupplierCatalogItem.category_name, "str"), "category_id": (SupplierCatalogItem.category_id, "num"),
        "price": (SupplierCatalogItem.price, "num"), "currency": (SupplierCatalogItem.currency, "str"),
        "stock": (SupplierCatalogItem.stock, "num"), "moq": (SupplierCatalogItem.moq, "str"),
        "source_type": (SupplierCatalogItem.source_type, "str"), "status": (SupplierCatalogItem.status, "num"),
        "goods_id": (SupplierCatalogItem.goods_id, "num"), "updated_at": (SupplierCatalogItem.updated_at, "str"),
    }


@router.get("/items")
def list_items(take: int | None = None, skip: int = 0, sort: str | None = None, filter: str | None = None,
               db: Session = Depends(get_db)):
    """不带 take 返回全部（数组）；带 take 做服务端分页，返回 {items, total}。"""
    q = select(SupplierCatalogItem)
    if take is None:
        q = q.order_by(SupplierCatalogItem.id.desc())
    else:
        fields = _items_query_fields(db)
        cond = build_filter(parse_json(filter, "筛选"), fields)
        if cond is not None:
            q = q.where(cond)
        total = db.scalar(select(func.count()).select_from(q.subquery()))
        skip, take = clamp_page(skip, take)
        q = q.order_by(*build_sort(parse_json(sort, "排序"), fields), SupplierCatalogItem.id.desc()).offset(skip).limit(take)
    rows = db.scalars(q).all()
    names = _supplier_names(db, [i.supplier_id for i in rows])
    items = [_item_dict(i, names.get(i.supplier_id, f"#{i.supplier_id}")) for i in rows]
    return ok(items if take is None else {"items": items, "total": total})


@router.get("/items/{iid}")
def get_item(iid: int, db: Session = Depends(get_db)):
    i = db.get(SupplierCatalogItem, iid) or fail("目录条目不存在", 404)
    return ok(_item_dict(i, _supplier_names(db, [i.supplier_id]).get(i.supplier_id, "")))


@router.post("/items")
def create_item(values: dict, db: Session = Depends(get_db)):
    i = SupplierCatalogItem(source_type="manual")
    _apply_item(db, i, values, True)
    db.add(i)
    _commit(db, "该供应商下已有相同货号")
    return ok(_item_dict(i, _supplier_names(db, [i.supplier_id]).get(i.supplier_id, "")))


@router.put("/items/{iid}")
def update_item(iid: int, values: dict, db: Session = Depends(get_db)):
    i = db.get(SupplierCatalogItem, iid) or fail("目录条目不存在", 404)
    old_urls = _item_upload_urls(i.remark, i.images, i.attachments, i.main_image_url)
    _apply_item(db, i, values, False)
    _commit(db, "该供应商下已有相同货号")
    _release_uploads(db, old_urls, _item_upload_urls(i.remark, i.images, i.attachments, i.main_image_url))
    return ok(_item_dict(i, _supplier_names(db, [i.supplier_id]).get(i.supplier_id, "")))


@router.post("/items/batch-status")
def batch_item_status(body: dict, db: Session = Depends(get_db)):
    ids = body.get("ids")
    if not isinstance(ids, list) or not ids or len(ids) > 500 or not all(isinstance(x, int) and not isinstance(x, bool) for x in ids):
        fail("请选择 1~500 个条目")
    if int(body.get("status") or -1) not in ITEM_STATUS:
        fail("状态不合法")
    res = db.execute(update(SupplierCatalogItem).where(SupplierCatalogItem.id.in_(ids)).values(status=int(body["status"])))
    db.commit()
    return ok({"updated": res.rowcount})


@router.delete("/items/{iid}")
def delete_item(iid: int, db: Session = Depends(get_db)):
    i = db.get(SupplierCatalogItem, iid) or fail("目录条目不存在", 404)
    old_urls = _item_upload_urls(i.remark, i.images, i.attachments, i.main_image_url)
    db.delete(i)
    db.commit()
    _release_uploads(db, old_urls, set())
    return ok()


# ---------------------------------------------------------------- Excel 导入
def _enabled_attr_names(db: Session) -> list[str]:
    return list(db.scalars(select(ShopAttribute.name).where(ShopAttribute.status == 1)))


def _suggest_mapping(template: dict | None, columns: list[dict], attr_names: list[str]) -> dict:
    """列映射建议：先套供应商保存的模板，再按表头关键字猜标准字段，最后按属性名猜「属性：xxx」。每个目标只建议一次。"""
    out, used = {}, set()
    attrs = sorted(attr_names, key=len, reverse=True)
    for col in columns:
        key, header = col["key"], col["name"]
        t = (template or {}).get(key)
        if t and (t in STANDARD_TARGETS or (t.startswith("attr:") and t[5:] in attr_names)) and t not in used:
            out[key], used = t, used | {t}
            continue
        low = header.lower()
        for target, kws in KEYWORD_MAP.items():
            if target in used:
                continue
            if any(kw in low for kw in kws):
                out[key], used = target, used | {target}
                break
        else:
            hit = next((an for an in attrs if an.lower() == low), None)
            if hit is None:
                hit = next((an for an in attrs if len(an) >= 2 and (an.lower() in low or low in an.lower())), None)
            if hit is not None and f"attr:{hit}" not in used:
                out[key], used = f"attr:{hit}", used | {f"attr:{hit}"}
    return out


@router.post("/import/preview")
async def import_preview(file: UploadFile = File(...), supplier_id: int = Form(...), has_header: int = Form(1),
                         db: Session = Depends(get_db)):
    supplier = db.get(Supplier, supplier_id) or fail("供应商不存在", 404)
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        fail("Excel 文件不能超过 10MB")
    columns, rows, total = _parse_excel(data, file.filename or "", bool(has_header), PREVIEW_ROWS)
    return ok({"file_name": file.filename or "", "columns": columns,
               "rows": [r for _, r in rows], "total_rows": total,
               "suggest": _suggest_mapping(supplier.excel_mapping, columns, _enabled_attr_names(db)),
               "has_template": bool(supplier.excel_mapping)})


def _clean_price(raw: str) -> Decimal | None:
    s = raw.strip().replace(",", "").replace("，", "").replace(" ", "").replace("\u00a0", "")
    for sym in ("¥", "￥", "$", "€", "£", "元", "RMB", "CNY", "USD"):
        s = s.replace(sym, "")
    if not s or s.lower() in PRICE_FREE or s in PRICE_FREE:
        return None
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError(raw)
    if not d.is_finite() or d < 0 or d > Decimal("9999999999.99"):
        raise ValueError(raw)
    return d.quantize(Decimal("0.01"))


@router.post("/import/run")
async def import_run(file: UploadFile = File(...), supplier_id: int = Form(...), has_header: int = Form(1),
                     mapping: str = Form(...), duplicate_mode: str = Form("skip"), save_mapping: int = Form(0),
                     db: Session = Depends(get_db)):
    """按列映射落库。duplicate_mode: skip 跳过同货号 / overwrite 覆盖更新（保留状态与已选品关系）。"""
    supplier = db.get(Supplier, supplier_id) or fail("供应商不存在", 404)
    if duplicate_mode not in ("skip", "overwrite"):
        fail("参数不合法")
    try:
        mapping = json.loads(mapping)
    except ValueError:
        fail("映射参数不是合法的 JSON")
    if not isinstance(mapping, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in mapping.items()):
        fail("映射参数不合法")
    attr_names = _enabled_attr_names(db)
    for t in mapping.values():
        if not t:
            continue
        if t not in STANDARD_TARGETS and not (t.startswith("attr:") and t[5:] in attr_names):
            fail(f"不支持的映射目标：{t}")
    targets = [t for t in mapping.values() if t]
    if len(targets) != len(set(targets)):
        fail("同一个目标字段只能映射一列")
    if targets.count("supplier_sku") != 1 or targets.count("name") != 1:
        fail("「货号/SKU」和「产品名称」必须各映射一列")
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        fail("Excel 文件不能超过 10MB")
    columns, rows, total = _parse_excel(data, file.filename or "", bool(has_header), None)
    col_keys = {c["key"] for c in columns}
    if any(k not in col_keys for k in mapping):
        fail("映射了文件中不存在的列，请重新解析文件")
    if not total:
        fail("Excel 里没有数据行")

    col_of = {t: k for k, t in mapping.items() if t}
    existing = dict(db.execute(select(SupplierCatalogItem.supplier_sku, SupplierCatalogItem.id)
                                .where(SupplierCatalogItem.supplier_id == supplier.id)).all())
    brands = {b.name.lower(): b.id for b in db.scalars(select(Brand)).all()}
    cat_counts: dict[str, int] = {}
    for _, name in db.execute(select(ShopCategory.id, ShopCategory.name)).all():
        cat_counts[name] = cat_counts.get(name, 0) + 1
    cats = {name.lower(): cid for cid, name in db.execute(select(ShopCategory.id, ShopCategory.name)).all()
            if cat_counts[name] == 1}

    def brand_id(name: str) -> int:
        key = name.lower()
        if key in brands:
            return brands[key]
        b = Brand(name=name)
        try:
            with db.begin_nested():
                db.add(b)
                db.flush()
        except IntegrityError:  # 并发下被别人先建了：取现成的
            b = db.scalar(select(Brand).where(Brand.name == name).limit(1))
            if b is None:
                raise
        brands[key] = b.id
        return b.id

    imported = updated = skipped = 0
    errors: list[dict] = []
    new_items: dict[str, SupplierCatalogItem] = {}
    currency_codes = enabled_codes(db, "currency")

    def add_error(line: int, msg: str) -> bool:
        errors.append({"row": line, "msg": msg})
        return len(errors) >= MAX_ERRORS

    for line_no, row in rows:
        def getv(t):
            return str(row.get(col_of[t]) or "").strip()

        sku, name = getv("supplier_sku"), getv("name")
        if not sku:
            if add_error(line_no, "货号/SKU 为空"):
                break
            continue
        if not name:
            if add_error(line_no, "产品名称为空"):
                break
            continue
        if len(sku) > 100 or len(name) > 300:
            if add_error(line_no, "货号或产品名称超长"):
                break
            continue
        try:
            price = _clean_price(getv("price")) if "price" in col_of else None
        except ValueError:
            if add_error(line_no, f"价格「{getv('price')[:50]}」格式不正确"):
                break
            continue
        currency = getv("currency").upper() if "currency" in col_of else ""
        if currency:
            if currency not in currency_codes:
                if add_error(line_no, f"币种「{currency}」不在通用属性中，请先到「属性值」里维护"):
                    break
                continue
        else:
            currency = supplier.default_currency or ""
            if currency and currency not in currency_codes:
                if add_error(line_no, f"供应商默认币种「{currency}」不在通用属性中"):
                    break
                continue
        stock = None
        if "stock" in col_of:
            raw = getv("stock").replace(",", "").replace("，", "").replace(" ", "")
            if raw:
                try:
                    stock = int(raw)
                except ValueError:
                    stock = None
                if stock is not None and (stock < 0 or stock > 2_000_000_000):
                    if add_error(line_no, f"库存「{getv('stock')}」超出范围"):
                        break
                    continue
        bname = getv("brand_name")[:100] if "brand_name" in col_of else ""
        cname = getv("category_name")[:200] if "category_name" in col_of else ""
        attrs = {k: v for k, v in row.items() if v}
        mapped_attrs = {t[5:]: getv(t) for t in targets if t.startswith("attr:") and getv(t)}
        values = dict(
            supplier_id=supplier.id, supplier_sku=sku, name=name,
            brand_name=bname, brand_id=brand_id(bname) if bname else 0,
            category_name=cname, category_id=cats.get(cname.lower(), 0),
            price=price, currency=currency, stock=stock,
            moq=getv("moq")[:50] if "moq" in col_of else "",
            main_image_url=getv("main_image_url")[:500] if "main_image_url" in col_of else "",
            source_url=getv("source_url")[:500] if "source_url" in col_of else "",
            description=getv("description")[:20000] if "description" in col_of else "",
            attrs=attrs, mapped_attrs=mapped_attrs or None,
            source_type="excel", source_file=(file.filename or "")[:255], source_row=line_no,
        )
        if sku in existing or sku in new_items:
            if duplicate_mode == "skip":
                skipped += 1
                continue
            item = new_items.get(sku) or db.get(SupplierCatalogItem, existing[sku])
            for f, v in values.items():
                setattr(item, f, v)
            updated += 1
        else:
            item = SupplierCatalogItem(**values)
            db.add(item)
            new_items[sku] = item
            imported += 1
    if save_mapping:
        supplier.excel_mapping = {k: v for k, v in mapping.items()}
    db.commit()
    return ok({"total": total, "imported": imported, "updated": updated, "skipped": skipped,
               "errors": errors, "error_count": len(errors)})
