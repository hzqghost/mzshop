"""销售运费模板、区域规则与运费试算。响应 {code, data, msg}。"""
from decimal import Decimal, InvalidOperation, ROUND_CEILING

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..attr_dict import normalize_currency
from ..db import get_db
from ..deps import require_user
from ..models import (GeoRegion, ShippingPackageBox, ShippingPackageGroup, ShippingPackageGroupImage, ShippingTemplate,
                      ShippingTemplateRule, ShopGoods, ShopGoodsRegion, ShopGoodsSku, ShopGoodsStore, Store)

router = APIRouter(prefix="/api/v1/shipping-templates", dependencies=[Depends(require_user)])
package_router = APIRouter(prefix="/api/v1/shipping-packages", dependencies=[Depends(require_user)])


def ok(data=None):
    return {"code": 0, "data": data, "msg": "ok"}


def fail(msg: str, status: int = 400):
    raise HTTPException(status_code=status, detail=msg)


def _fmt(value):
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else None


def _text(values: dict, key: str, label: str, max_len: int, required=False) -> str:
    value = str(values.get(key) or "").strip()
    if required and not value:
        fail(f"请填写{label}")
    if len(value) > max_len:
        fail(f"{label}最长 {max_len} 个字符")
    return value


def _money(raw, label: str, required=False) -> Decimal | None:
    if raw in (None, ""):
        if required:
            fail(f"请填写{label}")
        return None
    try:
        value = Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        fail(f"{label}格式不正确")
    if value < 0 or value > Decimal("9999999999.99"):
        fail(f"{label}超出范围")
    return value


def _cm(raw, label: str) -> Decimal:
    value = _money(raw, label, True)
    if value <= 0 or value > Decimal("99999999.99"):
        fail(f"{label}必须大于 0")
    return value


def _positive_int(raw, label: str, required=False) -> int | None:
    if raw in (None, ""):
        if required:
            fail(f"请填写{label}")
        return None
    if isinstance(raw, bool):
        fail(f"{label}格式不正确")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        fail(f"{label}格式不正确")
    if value <= 0 or value > 1000000000:
        fail(f"{label}必须大于 0")
    return value


def _rule_dict(rule: ShippingTemplateRule, region_name="") -> dict:
    money = lambda x: float(x) if x is not None else None
    return {
        "id": rule.id, "template_id": rule.template_id, "region_id": rule.region_id,
        "region_name": region_name or ("默认规则" if rule.region_id == 0 else ""),
        "priority": rule.priority, "fixed_fee": money(rule.fixed_fee),
        "first_weight_g": rule.first_weight_g, "first_fee": money(rule.first_fee),
        "additional_weight_g": rule.additional_weight_g, "additional_fee": money(rule.additional_fee),
        "arrival_days_min": rule.arrival_days_min, "arrival_days_max": rule.arrival_days_max,
    }


def _template_dict(db: Session, template: ShippingTemplate, with_rules=True) -> dict:
    money = lambda x: float(x) if x is not None else None
    data = {
        "id": template.id, "name": template.name, "currency": template.currency,
        "calc_type": template.calc_type, "volume_divisor": template.volume_divisor,
        "free_threshold": money(template.free_threshold),
        "min_fee": money(template.min_fee), "max_fee": money(template.max_fee),
        "no_match_action": template.no_match_action, "status": bool(template.status),
        "remark": template.remark or "", "created_at": _fmt(template.created_at),
        "updated_at": _fmt(template.updated_at),
    }
    if with_rules:
        rows = db.execute(select(ShippingTemplateRule, GeoRegion.name).outerjoin(
            GeoRegion, GeoRegion.id == ShippingTemplateRule.region_id).where(
            ShippingTemplateRule.template_id == template.id).order_by(
            ShippingTemplateRule.priority, ShippingTemplateRule.id)).all()
        data["rules"] = [_rule_dict(rule, name or "") for rule, name in rows]
    return data


def _apply_template(db: Session, template: ShippingTemplate, values: dict, creating: bool) -> None:
    if "name" in values or creating:
        template.name = _text(values, "name", "模板名称", 100, True)
    if "currency" in values or creating:
        template.currency = normalize_currency(db, values.get("currency"), None if creating else template.currency)
        if not template.currency:
            fail("请选择币种")
    if "calc_type" in values or creating:
        calc_type = str(values.get("calc_type") or "")
        if calc_type not in ("fixed", "weight", "chargeable"):
            fail("计费方式不正确")
        template.calc_type = calc_type
    if "volume_divisor" in values or creating:
        template.volume_divisor = _positive_int(values.get("volume_divisor") or 5000, "体积重系数", True)
        if template.volume_divisor < 1000 or template.volume_divisor > 20000:
            fail("体积重系数需在 1000~20000 之间")
    for key, label in (("free_threshold", "免邮金额"), ("min_fee", "最低运费"), ("max_fee", "最高运费")):
        if key in values or creating:
            setattr(template, key, _money(values.get(key), label))
    if template.min_fee is not None and template.max_fee is not None and template.min_fee > template.max_fee:
        fail("最低运费不能高于最高运费")
    if "no_match_action" in values or creating:
        action = str(values.get("no_match_action") or "reject")
        if action not in ("reject", "default"):
            fail("未匹配处理方式不正确")
        template.no_match_action = action
    if "status" in values or creating:
        template.status = 1 if values.get("status", True) else 0
    if "remark" in values or creating:
        template.remark = _text(values, "remark", "备注", 500)


def _replace_rules(db: Session, template: ShippingTemplate, raw) -> None:
    if not isinstance(raw, list) or not raw:
        fail("请至少配置一条运费规则")
    region_ids: set[int] = set()
    rules = []
    for item in raw:
        if not isinstance(item, dict):
            fail("运费规则格式不正确")
        try:
            region_id = int(item.get("region_id") or 0)
            priority = int(item.get("priority") or 100)
        except (TypeError, ValueError):
            fail("区域或优先级格式不正确")
        if region_id in region_ids:
            fail("同一模板中每个区域只能配置一条规则")
        if region_id and db.get(GeoRegion, region_id) is None:
            fail("所选区域不存在")
        if priority < 0 or priority > 999999:
            fail("优先级范围为 0~999999")
        region_ids.add(region_id)
        rule = ShippingTemplateRule(template_id=template.id, region_id=region_id, priority=priority)
        if template.calc_type == "fixed":
            rule.fixed_fee = _money(item.get("fixed_fee"), "固定运费", True)
        else:
            rule.first_weight_g = _positive_int(item.get("first_weight_g"), "首重", True)
            rule.first_fee = _money(item.get("first_fee"), "首重费用", True)
            rule.additional_weight_g = _positive_int(item.get("additional_weight_g"), "续重单位", True)
            rule.additional_fee = _money(item.get("additional_fee"), "续重费用", True)
        rule.arrival_days_min = _positive_int(item.get("arrival_days_min"), "最快到达天数")
        rule.arrival_days_max = _positive_int(item.get("arrival_days_max"), "最慢到达天数")
        if rule.arrival_days_min and rule.arrival_days_max and rule.arrival_days_min > rule.arrival_days_max:
            fail("最快到达天数不能大于最慢到达天数")
        rules.append(rule)
    if template.no_match_action == "default" and 0 not in region_ids:
        fail("未匹配时使用默认规则，必须配置一条默认规则")
    db.execute(delete(ShippingTemplateRule).where(ShippingTemplateRule.template_id == template.id))
    db.add_all(rules)


@router.get("")
def list_templates(db: Session = Depends(get_db)):
    rows = db.scalars(select(ShippingTemplate).order_by(ShippingTemplate.name, ShippingTemplate.id)).all()
    return ok([_template_dict(db, row) for row in rows])


@router.get("/{template_id}")
def get_template(template_id: int, db: Session = Depends(get_db)):
    row = db.get(ShippingTemplate, template_id) or fail("运费模板不存在", 404)
    return ok(_template_dict(db, row))


@router.post("")
def create_template(values: dict, db: Session = Depends(get_db)):
    row = ShippingTemplate()
    _apply_template(db, row, values, True)
    db.add(row)
    try:
        db.flush()
        _replace_rules(db, row, values.get("rules"))
        db.commit()
    except IntegrityError:
        db.rollback()
        fail("模板名称已存在")
    return ok(_template_dict(db, row))


@router.put("/{template_id}")
def update_template(template_id: int, values: dict, db: Session = Depends(get_db)):
    row = db.get(ShippingTemplate, template_id) or fail("运费模板不存在", 404)
    _apply_template(db, row, values, False)
    try:
        db.flush()
        if "rules" in values:
            _replace_rules(db, row, values.get("rules"))
        db.commit()
    except IntegrityError:
        db.rollback()
        fail("模板名称已存在")
    return ok(_template_dict(db, row))


@router.delete("/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db)):
    row = db.get(ShippingTemplate, template_id) or fail("运费模板不存在", 404)
    used = int(db.scalar(select(func.count()).select_from(ShopGoodsRegion).where(
        ShopGoodsRegion.shipping_template_id == template_id)) or 0)
    if used:
        fail(f"该模板已被 {used} 条商品店铺记录使用，不能删除")
    db.execute(delete(ShippingTemplateRule).where(ShippingTemplateRule.template_id == template_id))
    db.delete(row)
    db.commit()
    return ok()


def _box_dict(box: ShippingPackageBox, group_count=0) -> dict:
    return {"id": box.id, "name": box.name, "length_cm": float(box.length_cm),
            "width_cm": float(box.width_cm), "height_cm": float(box.height_cm),
            "empty_weight_g": box.empty_weight_g, "status": bool(box.status),
            "remark": box.remark or "", "group_count": int(group_count),
            "created_at": _fmt(box.created_at), "updated_at": _fmt(box.updated_at)}


def _group_dict(group: ShippingPackageGroup, box: ShippingPackageBox | None, usage_count=0,
                images: list[ShippingPackageGroupImage] | None = None) -> dict:
    return {"id": group.id, "name": group.name, "current_box_id": group.current_box_id,
            "current_box_name": box.name if box else "", "status": bool(group.status),
            "remark": group.remark or "", "usage_count": int(usage_count),
            "images": [{"id": image.id, "url": image.url, "sort_order": image.sort_order}
                       for image in (images or [])],
            "created_at": _fmt(group.created_at), "updated_at": _fmt(group.updated_at)}


@package_router.get("/boxes")
def list_boxes(db: Session = Depends(get_db)):
    counts = dict(db.execute(select(ShippingPackageGroup.current_box_id, func.count()).group_by(
        ShippingPackageGroup.current_box_id)).all())
    rows = db.scalars(select(ShippingPackageBox).order_by(ShippingPackageBox.name, ShippingPackageBox.id)).all()
    return ok([_box_dict(row, counts.get(row.id, 0)) for row in rows])


def _apply_box(box: ShippingPackageBox, values: dict, creating: bool) -> None:
    if "name" in values or creating:
        box.name = _text(values, "name", "箱型名称", 100, True)
    for field, label in (("length_cm", "外部长"), ("width_cm", "外部宽"), ("height_cm", "外部高")):
        if field in values or creating:
            setattr(box, field, _cm(values.get(field), label))
    if "empty_weight_g" in values or creating:
        raw = values.get("empty_weight_g") or 0
        try:
            box.empty_weight_g = int(raw)
        except (TypeError, ValueError):
            fail("空箱重量格式不正确")
        if box.empty_weight_g < 0 or box.empty_weight_g > 1000000000:
            fail("空箱重量超出范围")
    if "status" in values or creating:
        box.status = 1 if values.get("status", True) else 0
    if "remark" in values or creating:
        box.remark = _text(values, "remark", "备注", 500)


@package_router.post("/boxes")
def create_box(values: dict, db: Session = Depends(get_db)):
    row = ShippingPackageBox()
    _apply_box(row, values, True)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback(); fail("箱型名称已存在")
    return ok(_box_dict(row))


@package_router.put("/boxes/{box_id}")
def update_box(box_id: int, values: dict, db: Session = Depends(get_db)):
    row = db.get(ShippingPackageBox, box_id) or fail("包装箱不存在", 404)
    _apply_box(row, values, False)
    try:
        db.commit()
    except IntegrityError:
        db.rollback(); fail("箱型名称已存在")
    return ok(_box_dict(row))


@package_router.delete("/boxes/{box_id}")
def delete_box(box_id: int, db: Session = Depends(get_db)):
    row = db.get(ShippingPackageBox, box_id) or fail("包装箱不存在", 404)
    used = int(db.scalar(select(func.count()).select_from(ShippingPackageGroup).where(
        ShippingPackageGroup.current_box_id == box_id)) or 0)
    if used:
        fail(f"该包装箱正被 {used} 个包装组使用，不能删除")
    db.delete(row); db.commit(); return ok()


@package_router.get("/groups")
def list_groups(db: Session = Depends(get_db)):
    rows = db.execute(select(ShippingPackageGroup, ShippingPackageBox).outerjoin(
        ShippingPackageBox, ShippingPackageBox.id == ShippingPackageGroup.current_box_id).order_by(
        ShippingPackageGroup.name, ShippingPackageGroup.id)).all()
    out = []
    image_map: dict[int, list[ShippingPackageGroupImage]] = {}
    for image in db.scalars(select(ShippingPackageGroupImage).order_by(
            ShippingPackageGroupImage.group_id, ShippingPackageGroupImage.sort_order,
            ShippingPackageGroupImage.id)).all():
        image_map.setdefault(image.group_id, []).append(image)
    for group, box in rows:
        usage = sum(int(db.scalar(select(func.count()).select_from(model).where(
            model.shipping_package_group_id == group.id)) or 0) for model in (ShopGoods, ShopGoodsSku, Store))
        out.append(_group_dict(group, box, usage, image_map.get(group.id)))
    return ok(out)


def _replace_group_images(db: Session, group_id: int, raw) -> None:
    if raw is None:
        return
    if not isinstance(raw, list) or len(raw) > 20:
        fail("包装组图片格式不正确或超过 20 张")
    urls: list[str] = []
    for item in raw:
        url = str(item.get("url") if isinstance(item, dict) else item or "").strip()
        if not url.startswith("/static/uploads/") or len(url) > 500:
            fail("包装组图片地址不正确")
        if url not in urls:
            urls.append(url)
    db.execute(delete(ShippingPackageGroupImage).where(ShippingPackageGroupImage.group_id == group_id))
    db.add_all(ShippingPackageGroupImage(group_id=group_id, url=url, sort_order=index)
               for index, url in enumerate(urls))


def _apply_group(db: Session, group: ShippingPackageGroup, values: dict, creating: bool) -> None:
    if "name" in values or creating:
        group.name = _text(values, "name", "包装组名称", 100, True)
    if "current_box_id" in values or creating:
        try:
            box_id = int(values.get("current_box_id") or 0)
        except (TypeError, ValueError):
            fail("当前包装箱格式不正确")
        box = db.get(ShippingPackageBox, box_id) if box_id else None
        if box is None or not box.status:
            fail("请选择启用的当前包装箱")
        group.current_box_id = box_id
    if "status" in values or creating:
        group.status = 1 if values.get("status", True) else 0
    if "remark" in values or creating:
        group.remark = _text(values, "remark", "备注", 500)


@package_router.post("/groups")
def create_group(values: dict, db: Session = Depends(get_db)):
    row = ShippingPackageGroup()
    _apply_group(db, row, values, True)
    db.add(row)
    try:
        db.flush()
        _replace_group_images(db, row.id, values.get("images", []))
        db.commit()
    except IntegrityError:
        db.rollback(); fail("包装组名称已存在")
    images = db.scalars(select(ShippingPackageGroupImage).where(
        ShippingPackageGroupImage.group_id == row.id).order_by(ShippingPackageGroupImage.sort_order)).all()
    return ok(_group_dict(row, db.get(ShippingPackageBox, row.current_box_id), images=images))


@package_router.put("/groups/{group_id}")
def update_group(group_id: int, values: dict, db: Session = Depends(get_db)):
    row = db.get(ShippingPackageGroup, group_id) or fail("包装组不存在", 404)
    _apply_group(db, row, values, False)
    try:
        if "images" in values:
            _replace_group_images(db, row.id, values.get("images"))
        db.commit()
    except IntegrityError:
        db.rollback(); fail("包装组名称已存在")
    images = db.scalars(select(ShippingPackageGroupImage).where(
        ShippingPackageGroupImage.group_id == row.id).order_by(ShippingPackageGroupImage.sort_order)).all()
    return ok(_group_dict(row, db.get(ShippingPackageBox, row.current_box_id), images=images))


@package_router.delete("/groups/{group_id}")
def delete_group(group_id: int, db: Session = Depends(get_db)):
    row = db.get(ShippingPackageGroup, group_id) or fail("包装组不存在", 404)
    used = sum(int(db.scalar(select(func.count()).select_from(model).where(
        model.shipping_package_group_id == group_id)) or 0) for model in (ShopGoods, ShopGoodsSku, Store))
    if used:
        fail(f"该包装组已被 {used} 条商品、SKU 或店铺记录使用，不能删除")
    db.execute(delete(ShippingPackageGroupImage).where(ShippingPackageGroupImage.group_id == group_id))
    db.delete(row); db.commit(); return ok()


def _resolve_package_box(db: Session, sku: ShopGoodsSku, goods: ShopGoods, store_id: int) -> ShippingPackageBox | None:
    store = db.get(Store, store_id)
    group_id = sku.shipping_package_group_id or goods.shipping_package_group_id or (
        store.shipping_package_group_id if store else 0)
    group = db.get(ShippingPackageGroup, group_id) if group_id else None
    if group is None or not group.status:
        return None
    box = db.get(ShippingPackageBox, group.current_box_id) if group.current_box_id else None
    return box if box is not None and box.status else None


def _volume_weight_g(length_cm: Decimal, width_cm: Decimal, height_cm: Decimal, divisor: int) -> int:
    grams = length_cm * width_cm * height_cm / Decimal(divisor) * Decimal(1000)
    return int(grams.to_integral_value(rounding=ROUND_CEILING))


def _calculate_group(db: Session, template: ShippingTemplate, region_id: int,
                     subtotal: Decimal, weight_g: int) -> dict:
    rule = db.scalar(select(ShippingTemplateRule).where(
        ShippingTemplateRule.template_id == template.id,
        ShippingTemplateRule.region_id == region_id).order_by(ShippingTemplateRule.priority).limit(1))
    if rule is None and template.no_match_action == "default":
        rule = db.scalar(select(ShippingTemplateRule).where(
            ShippingTemplateRule.template_id == template.id, ShippingTemplateRule.region_id == 0).limit(1))
    if rule is None:
        fail(f"运费模板「{template.name}」在目的区域没有可用规则")
    if template.calc_type == "fixed":
        original = rule.fixed_fee or Decimal("0")
    else:
        if weight_g <= 0:
            fail(f"运费模板「{template.name}」缺少有效计费重量")
        extra = max(weight_g - (rule.first_weight_g or 0), 0)
        units = (Decimal(extra) / Decimal(rule.additional_weight_g or 1)).to_integral_value(rounding=ROUND_CEILING)
        original = (rule.first_fee or Decimal("0")) + units * (rule.additional_fee or Decimal("0"))
    fee = Decimal("0") if template.free_threshold is not None and subtotal >= template.free_threshold else original
    if fee and template.min_fee is not None:
        fee = max(fee, template.min_fee)
    if template.max_fee is not None:
        fee = min(fee, template.max_fee)
    return {"template_id": template.id, "template_name": template.name, "rule": _rule_dict(rule),
            "subtotal": float(subtotal), "weight_g": weight_g, "original_fee": float(original),
            "fee": float(fee), "currency": template.currency,
            "free_shipping": bool(original and fee == 0)}


@router.post("/calculate-order")
def calculate_order(values: dict, db: Session = Depends(get_db)):
    """同模板商品合并计算，不同模板分组后相加。"""
    try:
        store_id = int(values.get("store_id") or 0)
        region_id = int(values.get("region_id") or 0)
    except (TypeError, ValueError):
        fail("店铺或区域格式不正确")
    lines = values.get("lines")
    if not store_id or not isinstance(lines, list) or not lines:
        fail("请选择店铺并提供订单商品")
    groups: dict[int, dict] = {}
    for line in lines:
        if not isinstance(line, dict):
            fail("订单商品格式不正确")
        try:
            sku_id = int(line.get("sku_id") or 0)
            quantity = int(line.get("quantity") or 0)
        except (TypeError, ValueError):
            fail("SKU 或数量格式不正确")
        if not sku_id or quantity <= 0 or quantity > 100000:
            fail("SKU 数量必须大于 0")
        sku = db.get(ShopGoodsSku, sku_id) or fail("SKU不存在", 404)
        goods = db.get(ShopGoods, sku.goods_id) or fail("商品不存在", 404)
        link = db.scalar(select(ShopGoodsStore).where(
            ShopGoodsStore.goods_id == goods.id, ShopGoodsStore.store_id == store_id,
            ShopGoodsStore.allowed == 1))
        if link is None:
            fail(f"商品「{goods.name}」不允许在该店铺销售")
        region_price = db.scalar(select(ShopGoodsRegion).where(
            ShopGoodsRegion.goods_id == goods.id, ShopGoodsRegion.region_id == region_id))
        if region_price is None or not region_price.shipping_template_id:
            fail(f"商品「{goods.name}」在目的区域没有可用的运费模板")
        template = db.get(ShippingTemplate, region_price.shipping_template_id)
        if template is None or not template.status:
            fail(f"商品「{goods.name}」绑定的运费模板不存在或已停用")
        unit_price = _money(line.get("unit_price"), "商品单价", True)
        group = groups.setdefault(template.id, {"template": template, "subtotal": Decimal("0"),
                                                 "weight_g": 0, "actual_weight_g": 0, "volume_weight_g": 0})
        group["subtotal"] += unit_price * quantity
        if template.calc_type in ("weight", "chargeable"):
            effective_weight = sku.weight_g or goods.weight_g
            if not effective_weight:
                fail(f"SKU「{sku.sku_code}」缺少重量，无法计算运费")
            actual_shipping_weight = effective_weight
            charge_weight = effective_weight
            if template.calc_type == "chargeable":
                box = _resolve_package_box(db, sku, goods, store_id)
                if box is None:
                    fail(f"SKU「{sku.sku_code}」没有可用包装组或当前包装箱，无法计算运费")
                actual_shipping_weight += box.empty_weight_g
                volume_weight = _volume_weight_g(box.length_cm, box.width_cm, box.height_cm, template.volume_divisor)
                group["volume_weight_g"] += volume_weight * quantity
                charge_weight = max(actual_shipping_weight, volume_weight)
            group["actual_weight_g"] += actual_shipping_weight * quantity
            group["weight_g"] += charge_weight * quantity
    currencies = {group["template"].currency for group in groups.values()}
    if len(currencies) != 1:
        fail("同一订单的运费模板币种不一致")
    results = []
    for group in groups.values():
        result = _calculate_group(db, group["template"], region_id, group["subtotal"], group["weight_g"])
        result.update({"actual_weight_g": group["actual_weight_g"],
                       "volume_weight_g": group["volume_weight_g"],
                       "chargeable_weight_g": group["weight_g"]})
        results.append(result)
    return ok({"groups": results, "fee": float(sum(Decimal(str(x["fee"])) for x in results)),
               "currency": next(iter(currencies))})


@router.post("/{template_id}/calculate")
def calculate(template_id: int, values: dict, db: Session = Depends(get_db)):
    template = db.get(ShippingTemplate, template_id) or fail("运费模板不存在", 404)
    if not template.status:
        fail("运费模板已停用")
    try:
        region_id = int(values.get("region_id") or 0)
    except (TypeError, ValueError):
        fail("区域格式不正确")
    subtotal = _money(values.get("subtotal"), "分组商品金额", True)
    actual_weight_g = _positive_int(values.get("weight_g"), "实际重量", template.calc_type in ("weight", "chargeable")) or 0
    volume_weight_g = 0
    chargeable_weight_g = actual_weight_g
    if template.calc_type == "chargeable":
        length = _cm(values.get("package_length_cm"), "包装长度")
        width = _cm(values.get("package_width_cm"), "包装宽度")
        height = _cm(values.get("package_height_cm"), "包装高度")
        volume_weight_g = _volume_weight_g(length, width, height, template.volume_divisor)
        chargeable_weight_g = max(actual_weight_g, volume_weight_g)
    result = _calculate_group(db, template, region_id, subtotal, chargeable_weight_g)
    result.update({"actual_weight_g": actual_weight_g, "volume_weight_g": volume_weight_g,
                   "chargeable_weight_g": chargeable_weight_g})
    return ok(result)
