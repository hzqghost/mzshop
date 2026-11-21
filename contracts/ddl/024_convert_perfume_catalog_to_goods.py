"""第一轮：香水分类下的供应商产品转成商品。

已确认口径：
- 一条产品一个商品；商品编码用供应商货号
- 中文名保持产品名；英文名用属性「英文名称」，名称含「5件套」时加 Gift Set
- 中英文描述留空；产品资料 remark 不写入商品
- 拿货价 0；报价写入区域「国内」；店铺 mzShop_fragrance 可以上架且商品上架
- 浓度、套装容量留空；成色固定「全新」，包装固定「原装盒装」
- 香调按 FAMILY 对照；对不上的适用季节不写
- 已有 goods_id 的条目跳过，可重复执行
"""
import json
import sys
from decimal import Decimal

sys.path.insert(0, r"E:\www\xmvc\mzShop\admin")

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import engine
from app.models import (
    Brand,
    GeoRegion,
    ShopAttribute,
    ShopCategory,
    ShopGoods,
    ShopGoodsImage,
    ShopGoodsRegion,
    ShopGoodsStore,
    ShopTranslation,
    Store,
    Supplier,
    SupplierCatalogItem,
    SupplierCatalogItemRegion,
)

STORE_CODE = "mzShop_fragrance"
REGION_NAME = "国内"
SET_MARK = "5件套"
SEASON_OK = {"春夏", "秋冬", "四季"}
FAMILY = {
    "柑橘调": "柑橘调",
    "柑橘芳香调": "柑橘调",
    "木质芳香调": "木质调",
    "木质辛香调": "木质调",
    "琥珀木质调": "木质调",
    "芳香馥奇调": "馥奇调",
    "琥珀馥奇调": "馥奇调",
    "花香果香调": "花香调",
    "琥珀花香调": "花香调",
    "芳香果香调": "果香调",
    "果香西普调": "果香调",
    "琥珀调": "东方调",
    "琥珀香草调": "东方调",
    "芳香调": "清新调",
}


def zh_part(value) -> str:
    text = str(value or "").strip()
    if " / " in text:
        return text.split(" / ", 1)[0].strip()
    return text


def descendants(db: Session, root_ids: list[int]) -> set[int]:
    rows = list(db.execute(select(ShopCategory.id, ShopCategory.parent_id)).all())
    by_parent: dict[int, list[int]] = {}
    for cid, parent_id in rows:
        by_parent.setdefault(parent_id, []).append(cid)
    out = set(root_ids)
    stack = list(root_ids)
    while stack:
        cur = stack.pop()
        for child in by_parent.get(cur, []):
            if child not in out:
                out.add(child)
                stack.append(child)
    return out


def option_en(db: Session, attr: ShopAttribute) -> dict[str, str]:
    raw = db.scalar(select(ShopTranslation.content).where(
        ShopTranslation.entity_type == "attribute",
        ShopTranslation.entity_id == attr.id,
        ShopTranslation.lang_code == "en",
        ShopTranslation.field_name == "options",
    ))
    zh = list(attr.options or [])
    en = json.loads(raw) if raw else []
    if len(en) != len(zh):
        raise SystemExit(f"属性「{attr.name}」中英文选项数量不一致")
    return dict(zip(zh, en))


def main() -> None:
    report = {
        "created": [],
        "skipped": [],
        "missing_required": [],
        "family_lossy": [],
        "season_unmapped": [],
        "attrs_not_written": {},
    }
    with Session(engine) as db:
        root = db.scalar(select(ShopCategory).where(ShopCategory.name == "香水", ShopCategory.parent_id == 0))
        if root is None:
            raise SystemExit("找不到根分类「香水」")
        cat_ids = descendants(db, [root.id])
        store = db.scalar(select(Store).where(Store.code == STORE_CODE))
        if store is None:
            raise SystemExit(f"找不到店铺 {STORE_CODE}")
        region = db.scalar(select(GeoRegion).where(GeoRegion.name == REGION_NAME))
        if region is None:
            raise SystemExit(f"找不到区域「{REGION_NAME}」")

        attrs = {a.name: a for a in db.scalars(select(ShopAttribute).where(ShopAttribute.status == 1))}
        for name in ("香调", "香名/系列", "容量", "包装", "适用季节", "成色"):
            if name not in attrs:
                raise SystemExit(f"缺少商品属性「{name}」")
        family_en = option_en(db, attrs["香调"])
        season_en = option_en(db, attrs["适用季节"])
        pack_en = option_en(db, attrs["包装"])
        condition_en = option_en(db, attrs["成色"])
        if "原装盒装" not in pack_en or "全新" not in condition_en:
            raise SystemExit("成色或包装的可选值里没有「全新」「原装盒装」")
        for src, dst in FAMILY.items():
            if dst not in (attrs["香调"].options or []):
                raise SystemExit(f"香调对照目标「{dst}」不在可选值里")

        items = list(db.scalars(
            select(SupplierCatalogItem)
            .where(SupplierCatalogItem.category_id.in_(cat_ids))
            .order_by(SupplierCatalogItem.id)
        ))
        for item in items:
            if item.goods_id:
                report["skipped"].append({"id": item.id, "sku": item.supplier_sku, "reason": "已有商品"})
                continue
            if item.category_id not in cat_ids or db.get(ShopCategory, item.category_id) is None:
                raise SystemExit(f"产品 {item.id} 分类无效")
            brand = db.get(Brand, item.brand_id) if item.brand_id else None
            supplier = db.get(Supplier, item.supplier_id) if item.supplier_id else None
            if brand is None or supplier is None:
                raise SystemExit(f"产品 {item.id} 缺少品牌或供应商")
            en_name = str((item.attrs or {}).get("英文名称") or "").strip()
            if not en_name:
                raise SystemExit(f"产品 {item.id} 没有英文名称")
            if SET_MARK in (item.name or ""):
                en_name = f"{en_name} Gift Set"
            if len(item.name or "") > 200 or len(en_name) > 200:
                raise SystemExit(f"产品 {item.id} 名称超长")
            if db.scalar(select(ShopGoods.id).where(ShopGoods.goods_no == item.supplier_sku)):
                raise SystemExit(f"商品编码已存在：{item.supplier_sku}")

            raw_attrs = item.attrs or {}
            mapped = item.mapped_attrs or {}
            values: dict[str, str] = {}
            values_en: dict[str, str] = {}
            gaps = []

            family_src = zh_part(raw_attrs.get("香调"))
            if family_src in FAMILY:
                values["香调"] = FAMILY[family_src]
                values_en["香调"] = family_en[FAMILY[family_src]]
                if family_src != FAMILY[family_src]:
                    report["family_lossy"].append({
                        "sku": item.supplier_sku, "from": str(raw_attrs.get("香调") or ""), "to": FAMILY[family_src],
                    })
            else:
                gaps.append(f"香调无法对照：{raw_attrs.get('香调')}")

            fragrance = str(mapped.get("香名/系列") or en_name.removesuffix(" Gift Set")).strip()
            if fragrance:
                values["香名/系列"] = fragrance[:200]
                values_en["香名/系列"] = fragrance[:200]

            volume = mapped.get("容量")
            if volume not in (None, ""):
                number = Decimal(str(volume))
                if number != number.to_integral():
                    raise SystemExit(f"产品 {item.id} 容量不是整数：{volume}")
                values["容量"] = format(number.to_integral(), "f")
                values_en["容量"] = values["容量"]
            else:
                gaps.append("容量为空")
                report["missing_required"].append({"sku": item.supplier_sku, "attr": "容量"})

            report["missing_required"].append({"sku": item.supplier_sku, "attr": "浓度"})

            values["成色"] = "全新"
            values_en["成色"] = condition_en["全新"]
            values["包装"] = "原装盒装"
            values_en["包装"] = pack_en["原装盒装"]

            season = str(mapped.get("适用季节") or "").strip()
            if season in SEASON_OK:
                values["适用季节"] = season
                values_en["适用季节"] = season_en[season]
            elif raw_attrs.get("季节与场景"):
                report["season_unmapped"].append({
                    "sku": item.supplier_sku, "value": str(raw_attrs.get("季节与场景")),
                })

            price_row = db.scalar(select(SupplierCatalogItemRegion).where(
                SupplierCatalogItemRegion.item_id == item.id,
                SupplierCatalogItemRegion.region_id == region.id,
            ))
            sale = None if price_row is None or price_row.price is None else Decimal(price_row.price).quantize(Decimal("0.01"))

            urls = []
            for image in item.images or []:
                url = str((image or {}).get("url") or "").strip() if isinstance(image, dict) else ""
                if url and url not in urls:
                    urls.append(url)
            urls = urls[:20]
            source_url = item.source_url if (item.source_url or "").lower().startswith(("http://", "https://")) else ""

            goods = ShopGoods(
                goods_no=item.supplier_sku,
                name=item.name,
                category_id=item.category_id,
                brand=brand.name,
                supplier=supplier.name,
                brand_id=brand.id,
                supplier_id=supplier.id,
                source_url=source_url,
                main_image_url=urls[0] if urls else "",
                cost_price=Decimal("0.00"),
                sale_price=sale if sale is not None else Decimal("0.00"),
                shipping_fee=Decimal("0.00"),
                attr_values=values or None,
                description="",
                status=1,
            )
            db.add(goods)
            db.flush()
            for i, url in enumerate(urls):
                db.add(ShopGoodsImage(goods_id=goods.id, url=url, sort_order=i))
            if sale is not None:
                db.add(ShopGoodsRegion(
                    goods_id=goods.id, region_id=region.id, price=sale, currency="CNY",
                ))
            db.add(ShopGoodsStore(goods_id=goods.id, store_id=store.id, allowed=1))
            db.add(ShopTranslation(
                entity_type="goods", entity_id=goods.id, lang_code="en", field_name="name", content=en_name,
            ))
            if values_en:
                db.add(ShopTranslation(
                    entity_type="goods", entity_id=goods.id, lang_code="en", field_name="attr_values",
                    content=json.dumps(values_en, ensure_ascii=False),
                ))
            item.goods_id = goods.id
            item.status = 2
            report["created"].append({
                "item_id": item.id, "goods_id": goods.id, "sku": item.supplier_sku,
                "name": item.name, "name_en": en_name, "sale": None if sale is None else str(sale),
                "attrs": values, "gaps": gaps,
            })

        for key in ("系列", "适合偏好", "香气印象", "香气关键词", "大牌香味参考", "箱规", "畅销", "香气方向", "规格"):
            report["attrs_not_written"][key] = "没有对应商品属性，或已由分类/其他属性表达，本轮不写入"

        db.commit()

    print(json.dumps({
        "created": len(report["created"]),
        "skipped": len(report["skipped"]),
        "missing_required": len(report["missing_required"]),
        "family_lossy": len(report["family_lossy"]),
        "season_unmapped": len(report["season_unmapped"]),
        "sample": report["created"][:2],
        "season_unmapped_values": report["season_unmapped"],
        "attrs_not_written": report["attrs_not_written"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
