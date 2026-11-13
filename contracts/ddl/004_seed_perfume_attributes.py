"""给「香水」分类（根分类，其下子分类继承）写入常用属性；按名称判重，可重复执行。"""
import json
import sys

sys.path.insert(0, r"E:\www\xmvc\mzShop\admin")
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import engine
from app.models import ShopAttribute, ShopCategory, ShopTranslation

# (排序, 中文名, 英文名, 类型, 必填, [(中文可选值, 英文可选值)])
# 数字属性的 (小数位数, 默认语言单位, 英文单位)
UNITS = {"容量": (0, "ml", "ml"), "保质期": (0, "个月", "months")}

ATTRS = [
    (10, "浓度", "Concentration", "select", 1, [("香精", "Parfum / Extrait"), ("浓香水", "Eau de Parfum (EDP)"), ("淡香水", "Eau de Toilette (EDT)"),
                                               ("古龙水", "Eau de Cologne (EDC)"), ("清新淡香氛", "Eau Fraiche"), ("身体喷雾", "Body Mist")]),
    (20, "容量", "Volume", "number", 1, []),  # 数字，整数，单位 ml（见 UNITS）
    (30, "香调", "Fragrance Family", "select", 0, [("花香调", "Floral"), ("果香调", "Fruity"), ("柑橘调", "Citrus"), ("清新调", "Fresh"),
                                                  ("木质调", "Woody"), ("东方调", "Oriental"), ("馥奇调", "Fougere"), ("美食调", "Gourmand"),
                                                  ("皮革调", "Leather"), ("海洋调", "Aquatic")]),
    (40, "香名/系列", "Fragrance Name", "text", 0, []),
    (50, "成色", "Condition", "select", 0, [("全新", "New"), ("全新（无盒）", "New without box"), ("二手", "Pre-owned")]),
    (60, "包装", "Packaging", "select", 0, [("原装盒装", "Boxed"), ("无盒", "Unboxed"), ("试香装", "Tester"), ("礼盒套装", "Gift Set")]),
    (70, "前调", "Top Notes", "text", 0, []),
    (80, "中调", "Middle Notes", "text", 0, []),
    (90, "后调", "Base Notes", "text", 0, []),
    (100, "适用季节", "Season", "select", 0, [("春夏", "Spring/Summer"), ("秋冬", "Autumn/Winter"), ("四季", "All Seasons")]),
    (110, "持久度", "Longevity", "select", 0, [("短（3小时内）", "Short (under 3 hours)"), ("中等（3-6小时）", "Moderate (3-6 hours)"),
                                              ("持久（6小时以上）", "Long-lasting (6+ hours)")]),
    (120, "产品形态", "Format", "select", 0, [("喷雾", "Spray"), ("滚珠", "Roll-on"), ("倾倒式", "Splash"), ("固体香膏", "Solid")]),
    (130, "条形码", "UPC/EAN", "text", 0, []),
    (140, "产地", "Country of Origin", "text", 0, []),
    (150, "保质期", "Shelf Life", "number", 0, []),  # 数字，整数，单位 个月 / months
]

with Session(engine) as db:
    cat = db.scalar(select(ShopCategory).where(ShopCategory.name == "香水", ShopCategory.parent_id == 0))
    assert cat is not None, "找不到根分类「香水」"
    added = 0
    for sort, zh, en, typ, req, opts in ATTRS:
        if any(cat.id in (a.category_ids or []) for a in db.scalars(select(ShopAttribute).where(ShopAttribute.name == zh))):
            continue
        dec, unit, unit_en = UNITS.get(zh, (0, "", ""))
        a = ShopAttribute(category_ids=[cat.id], name=zh, input_type=typ, options=[o[0] for o in opts] if opts else None,
                          decimal_places=dec, unit=unit, is_required=req, sort_order=sort, status=1)
        db.add(a)
        db.flush()
        db.add(ShopTranslation(entity_type="attribute", entity_id=a.id, lang_code="en", field_name="name", content=en))
        if typ == "number" and unit_en:
            db.add(ShopTranslation(entity_type="attribute", entity_id=a.id, lang_code="en", field_name="unit", content=unit_en))
        if opts:
            db.add(ShopTranslation(entity_type="attribute", entity_id=a.id, lang_code="en", field_name="options",
                                   content=json.dumps([o[1] for o in opts], ensure_ascii=False)))
        added += 1
    db.commit()
    print("category", cat.id, "added", added, "of", len(ATTRS))
