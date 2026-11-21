"""重构香水商品属性为 Shopify 官方属性/属性值。

预览：admin/.venv/Scripts/python contracts/ddl/033_rebuild_perfume_attributes.py
执行：admin/.venv/Scripts/python contracts/ddl/033_rebuild_perfume_attributes.py --apply
回滚：admin/.venv/Scripts/python contracts/ddl/033_rebuild_perfume_attributes.py --rollback <备份.json>

影响：删除香水分类现有属性定义、译文、映射及 36 个商品的旧属性值；创建当前
Shopify Eaux de Parfum 类别的全部官方属性代理，选项显示官方中英文名称，值映射
到 shopify_taxonomy_attribute_value.id。执行前自动备份，单事务提交。
"""
import argparse
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "admin"))

from sqlalchemy import delete, select
from app.catalog import ancestor_ids
from app.db import SessionLocal
from app.models import (ShopAttribute, ShopCategory, ShopGoods, ShopTranslation,
                        ShopifyAttributeMap, ShopifyCategoryMap, ShopifyTaxonomyAttribute,
                        ShopifyTaxonomyAttributeValue, ShopifyTaxonomyCategory,
                        ShopifyTaxonomyCategoryAttribute)


def row_dict(row, fields):
    return {field: getattr(row, field) for field in fields}


ATTR_FIELDS = ("id", "category_ids", "name", "input_type", "options", "decimal_places", "unit",
               "is_required", "sort_order", "status")
TR_FIELDS = ("id", "entity_type", "entity_id", "lang_code", "field_name", "content")
MAP_FIELDS = ("id", "category_id", "category_attribute_id", "local_attribute_id", "value_map")


def context(db):
    categories = list(db.scalars(select(ShopCategory).order_by(ShopCategory.id)))
    root = next((row for row in categories if row.name == "香水"), None)
    if not root:
        raise RuntimeError("找不到根分类“香水”")
    category_ids = [row.id for row in categories if root.id in ancestor_ids(db, row.id)]
    mapping = db.scalar(select(ShopifyCategoryMap).where(ShopifyCategoryMap.category_id == root.id))
    if not mapping:
        raise RuntimeError("香水根分类尚未绑定 Shopify 标准分类")
    target = db.get(ShopifyTaxonomyCategory, mapping.taxonomy_category_id)
    relations = list(db.execute(
        select(ShopifyTaxonomyCategoryAttribute, ShopifyTaxonomyAttribute)
        .join(ShopifyTaxonomyAttribute,
              ShopifyTaxonomyAttribute.id == ShopifyTaxonomyCategoryAttribute.taxonomy_attribute_id)
        .where(ShopifyTaxonomyCategoryAttribute.taxonomy_category_id == target.id,
               ShopifyTaxonomyCategoryAttribute.is_active == 1)
        .order_by(ShopifyTaxonomyCategoryAttribute.id)
    ))
    return root, category_ids, target, relations


def relation_values(db, relation, base):
    values = list(db.scalars(select(ShopifyTaxonomyAttributeValue).where(
        ShopifyTaxonomyAttributeValue.attribute_id == base.id,
        ShopifyTaxonomyAttributeValue.is_active == 1
    ).order_by(ShopifyTaxonomyAttributeValue.name_zh,
               ShopifyTaxonomyAttributeValue.name_en,
               ShopifyTaxonomyAttributeValue.id)))
    raw_names = [str(value.name_zh or value.name_en or value.handle or value.id) for value in values]
    duplicated = {name for name, count in Counter(raw_names).items() if count > 1}
    rows = []
    for value, raw_name in zip(values, raw_names):
        display = raw_name
        if raw_name in duplicated:
            display = f"{raw_name} [{value.handle or value.taxonomy_gid.rsplit('/', 1)[-1]}]"
        rows.append((value, display, str(value.name_en or value.name_zh or display)))
    return rows


def preview(db):
    root, category_ids, target, relations = context(db)
    attrs = list(db.scalars(select(ShopAttribute)))
    old = [row for row in attrs if not row.category_ids or set(row.category_ids) & set(category_ids)]
    goods = list(db.scalars(select(ShopGoods).where(ShopGoods.category_id.in_(category_ids))))
    counts = []
    for relation, base in relations:
        counts.append({"handle": relation.handle, "name": relation.name_zh or base.name_zh,
                       "values": len(relation_values(db, relation, base))})
    return {"root_category_id": root.id, "category_ids": category_ids,
            "shopify_category": target.full_name_zh or target.full_name_en,
            "delete_attributes": [{"id": row.id, "name": row.name} for row in old],
            "goods_count": len(goods), "create_official_attributes": counts}


def backup(db, old_attrs, goods):
    old_ids = [row.id for row in old_attrs]
    translations = list(db.scalars(select(ShopTranslation).where(
        ShopTranslation.entity_type == "attribute", ShopTranslation.entity_id.in_(old_ids)))) if old_ids else []
    mappings = list(db.scalars(select(ShopifyAttributeMap).where(
        ShopifyAttributeMap.local_attribute_id.in_(old_ids)))) if old_ids else []
    return {"attributes": [row_dict(row, ATTR_FIELDS) for row in old_attrs],
            "translations": [row_dict(row, TR_FIELDS) for row in translations],
            "attribute_maps": [row_dict(row, MAP_FIELDS) for row in mappings],
            "goods": [{"id": row.id, "attr_values": row.attr_values or {}} for row in goods],
            "created_attribute_ids": []}


def migrate(db):
    root, category_ids, target, relations = context(db)
    attrs = list(db.scalars(select(ShopAttribute)))
    old_attrs = [row for row in attrs if not row.category_ids or set(row.category_ids) & set(category_ids)]
    goods = list(db.scalars(select(ShopGoods).where(ShopGoods.category_id.in_(category_ids))))
    data = backup(db, old_attrs, goods)
    backup_dir = Path(tempfile.gettempdir()) / "mzshop-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / "033_perfume_attributes.json"
    backup_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    old_ids = [row.id for row in old_attrs]
    if old_ids:
        db.execute(delete(ShopifyAttributeMap).where(ShopifyAttributeMap.local_attribute_id.in_(old_ids)))
        db.execute(delete(ShopTranslation).where(ShopTranslation.entity_type == "attribute",
                                                 ShopTranslation.entity_id.in_(old_ids)))
        db.execute(delete(ShopAttribute).where(ShopAttribute.id.in_(old_ids)))

    created = {}
    official = {}
    for order, (relation, base) in enumerate(relations, 1):
        values = relation_values(db, relation, base)
        name_zh = str(relation.name_zh or base.name_zh or relation.handle)
        name_en = str(relation.name_en or base.name_en or relation.handle)
        attribute = ShopAttribute(category_ids=[root.id], name=name_zh, input_type="multiselect",
            options=[display for _, display, _ in values], decimal_places=0, unit="",
            is_required=0, sort_order=order * 10, status=1)
        db.add(attribute)
        db.flush()
        created[relation.id] = attribute
        official[relation.handle] = {
            "attribute": attribute,
            "by_en": {str(value.name_en).lower(): display for value, display, _ in values if value.name_en},
            "value_map": {display: [value.id] for value, display, _ in values},
        }
        db.add(ShopTranslation(entity_type="attribute", entity_id=attribute.id, lang_code="en",
            field_name="name", content=name_en))
        option_translation = json.dumps([english for _, _, english in values], ensure_ascii=False)
        # shop_translation.content 是 MySQL TEXT；超大官方值集由标准属性值页面按需查看，避免超过 64KB。
        if len(option_translation.encode("utf-8")) <= 60000:
            db.add(ShopTranslation(entity_type="attribute", entity_id=attribute.id, lang_code="en",
                field_name="options", content=option_translation))
        for category_id in category_ids:
            db.add(ShopifyAttributeMap(category_id=category_id, category_attribute_id=relation.id,
                local_attribute_id=attribute.id, value_map=official[relation.handle]["value_map"]))

    aroma = {"花香调": "floral", "果香调": "fruity", "柑橘调": "citrus", "清新调": "fresh",
             "木质调": "woody", "东方调": "oriental", "馥奇调": "fougere",
             "美食调": "gourmand", "皮革调": "leather", "海洋调": "aquatic"}
    seasons = {"春夏": ["spring", "summer"], "秋冬": ["fall", "winter"],
               "四季": ["spring", "summer", "fall", "winter"]}
    gender = {5: "female", 6: "unisex", 7: "male"}

    def picks(handle, names):
        item = official.get(handle)
        return [item["by_en"][name] for name in names if item and name in item["by_en"]]

    for goods_row in goods:
        old = goods_row.attr_values or {}
        new = {}
        if old.get("香调") in aroma:
            values = picks("olfactory-family", [aroma[old["香调"]]])
            if values:
                new[official["olfactory-family"]["attribute"].name] = values
        if old.get("适用季节") in seasons:
            values = picks("season", seasons[old["适用季节"]])
            if values:
                new[official["season"]["attribute"].name] = values
        if goods_row.category_id in gender:
            values = picks("target-gender", [gender[goods_row.category_id]])
            if values:
                new[official["target-gender"]["attribute"].name] = values
        if old.get("包装") == "原装盒装":
            values = picks("presentation-type", ["boxed"])
            if values:
                new[official["presentation-type"]["attribute"].name] = values
        goods_row.attr_values = new

    db.commit()
    data["created_attribute_ids"] = [row.id for row in created.values()]
    backup_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return backup_path, len(created), len(goods)


def rollback(db, path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    created = [int(value) for value in data.get("created_attribute_ids") or []]
    if created:
        db.execute(delete(ShopifyAttributeMap).where(ShopifyAttributeMap.local_attribute_id.in_(created)))
        db.execute(delete(ShopTranslation).where(ShopTranslation.entity_type == "attribute",
                                                 ShopTranslation.entity_id.in_(created)))
        db.execute(delete(ShopAttribute).where(ShopAttribute.id.in_(created)))
    for row in data["attributes"]:
        db.execute(ShopAttribute.__table__.insert().values(**row))
    for row in data["translations"]:
        db.execute(ShopTranslation.__table__.insert().values(**row))
    for row in data["attribute_maps"]:
        db.execute(ShopifyAttributeMap.__table__.insert().values(**row))
    for row in data["goods"]:
        goods = db.get(ShopGoods, int(row["id"]))
        if goods:
            goods.attr_values = row["attr_values"]
    db.commit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rollback")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        if args.rollback:
            rollback(db, args.rollback)
            print("回滚完成")
        elif args.apply:
            path, attrs, goods = migrate(db)
            print(json.dumps({"status": "applied", "attributes": attrs, "goods": goods,
                              "backup": str(path)}, ensure_ascii=False))
        else:
            print(json.dumps(preview(db), ensure_ascii=False, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
