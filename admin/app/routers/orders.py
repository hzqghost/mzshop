"""Shopify 订单镜像、Webhook 幂等与极简退货入库。"""
import base64
import hashlib
import hmac
import json
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..config import SHOPIFY_CLIENT_SECRET
from ..db import SessionLocal, get_db
from ..deps import require_user
from ..inventory import StockError, change_stock, enqueue_inventory
from ..listquery import build_filter, build_sort, clamp_page, parse_json
from ..models import (BundleRevision, ShopGoods, ShopGoodsSku, ShopOrder, ShopOrderLine, ShopRefund,
                      ShopRefundLine, ShopifyBundleMap, ShopifyStoreConfig, ShopifyVariantMap,
                      ShopifyWebhookEvent, ShopReturn, ShopReturnLine, StockLocation, Store)
from ..shopify_client import ShopifyError, graphql

router = APIRouter(prefix="/api/v1/orders", dependencies=[Depends(require_user)])
webhook_router = APIRouter(prefix="/api/v1/shopify/webhooks")


def ok(data=None): return {"code": 0, "data": data, "msg": "ok"}
def fail(msg, status=400): raise HTTPException(status_code=status, detail=msg)
def _fmt(value): return value.strftime("%Y-%m-%d %H:%M:%S") if value else None


ORDER_QUERY = """
query SyncOrder($id: ID!) {
  order(id: $id) {
    id name processedAt updatedAt cancelledAt displayFinancialStatus displayFulfillmentStatus
    currencyCode presentmentCurrencyCode
    totalPriceSet { shopMoney { amount } presentmentMoney { amount } }
    totalDiscountsSet { shopMoney { amount } }
    totalTaxSet { shopMoney { amount } }
    lineItems(first: 250) { nodes {
      id name sku quantity currentQuantity unfulfilledQuantity
      variant { id }
      lineItemGroup { id title quantity variantId }
      originalUnitPriceSet { shopMoney { amount } }
      discountedTotalSet { shopMoney { amount } presentmentMoney { amount } }
      totalDiscountSet { shopMoney { amount } presentmentMoney { amount } }
      taxLines { priceSet { shopMoney { amount } presentmentMoney { amount } } }
    } }
    fulfillments(first: 250) { fulfillmentLineItems(first: 250) { nodes { quantity lineItem { id } } } }
  }
}
"""


def _dt(value):
    if not value: return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)


def _amount(node, side="shopMoney") -> Decimal:
    try: return Decimal(str((node or {}).get(side, {}).get("amount") or 0)).quantize(Decimal("0.01"))
    except Exception: return Decimal("0.00")


def _sum_tax(lines, side):
    return sum((_amount(x.get("priceSet"), side) for x in lines or []), Decimal("0.00"))


def sync_order(db: Session, cfg: ShopifyStoreConfig, order_gid: str) -> ShopOrder:
    data, _ = graphql(cfg.shop_domain, ORDER_QUERY, {"id": order_gid})
    remote = data.get("order") or {}
    if not remote.get("id"): raise ShopifyError("Shopify 订单不存在或应用无权读取")
    order = db.scalar(select(ShopOrder).where(ShopOrder.store_id == cfg.store_id,
        ShopOrder.external_order_gid == remote["id"]).with_for_update())
    if not order:
        order = ShopOrder(store_id=cfg.store_id, external_order_gid=remote["id"], order_no=remote.get("name") or "",
                          shop_currency=remote.get("currencyCode") or cfg.currency or "USD",
                          presentment_currency=remote.get("presentmentCurrencyCode") or remote.get("currencyCode") or cfg.currency or "USD")
        db.add(order); db.flush()
    order.order_no = remote.get("name") or order.order_no
    order.financial_status = str(remote.get("displayFinancialStatus") or "").lower()
    order.fulfillment_status = str(remote.get("displayFulfillmentStatus") or "").lower()
    order.cancel_status = "cancelled" if remote.get("cancelledAt") else "active"
    order.total_price = _amount(remote.get("totalPriceSet")); order.presentment_total_price = _amount(remote.get("totalPriceSet"), "presentmentMoney")
    order.total_discount = _amount(remote.get("totalDiscountsSet")); order.total_tax = _amount(remote.get("totalTaxSet"))
    order.processed_at, order.cancelled_at, order.last_external_updated_at = _dt(remote.get("processedAt")), _dt(remote.get("cancelledAt")), _dt(remote.get("updatedAt"))
    fulfilled = {}
    for fulfillment in remote.get("fulfillments") or []:
        for item in (fulfillment.get("fulfillmentLineItems") or {}).get("nodes", []):
            gid = str((item.get("lineItem") or {}).get("id") or "")
            fulfilled[gid] = fulfilled.get(gid, 0) + int(item.get("quantity") or 0)
    variant_maps = {x.variant_gid: x for x in db.scalars(select(ShopifyVariantMap).where(
        ShopifyVariantMap.store_id == cfg.store_id))}
    group_parents = {}
    changed_skus = set()
    for item in (remote.get("lineItems") or {}).get("nodes", []):
        group = item.get("lineItemGroup") or {}
        group_gid = str(group.get("id") or "")
        if not group_gid or group_gid in group_parents: continue
        variant_map = variant_maps.get(str(group.get("variantId") or ""))
        parent_sku = db.get(ShopGoodsSku, variant_map.sku_id) if variant_map else None
        bundle_map = db.scalar(select(ShopifyBundleMap).where(
            ShopifyBundleMap.store_id == cfg.store_id, ShopifyBundleMap.parent_sku_id == parent_sku.id)) if parent_sku else None
        parent = db.scalar(select(ShopOrderLine).where(ShopOrderLine.order_id == order.id,
            ShopOrderLine.line_type == "bundle_parent", ShopOrderLine.external_group_gid == group_gid))
        if not parent:
            parent = ShopOrderLine(order_id=order.id, external_line_gid=None, external_group_gid=group_gid,
                line_type="bundle_parent", title=group.get("title") or "组合装", quantity=int(group.get("quantity") or 1))
            db.add(parent); db.flush()
        if parent_sku:
            goods = db.get(ShopGoods, parent_sku.goods_id)
            parent.goods_id, parent.sku_id, parent.sku_code = parent_sku.goods_id, parent_sku.id, parent_sku.sku_code
            parent.spec_name, parent.unit_cost = parent_sku.spec_name, parent_sku.cost_price
            parent.title = group.get("title") or (goods.name if goods else parent.title)
        parent.bundle_revision_id = bundle_map.revision_id if bundle_map else 0
        group_parents[group_gid] = parent
    paid = order.financial_status == "paid" and order.cancel_status == "active"
    for item in (remote.get("lineItems") or {}).get("nodes", []):
        line_gid = str(item.get("id") or "")
        line = db.scalar(select(ShopOrderLine).where(
            ShopOrderLine.order_id == order.id, ShopOrderLine.external_line_gid == line_gid).with_for_update())
        variant_map = variant_maps.get(str((item.get("variant") or {}).get("id") or ""))
        sku = db.get(ShopGoodsSku, variant_map.sku_id) if variant_map else None
        group_gid = str((item.get("lineItemGroup") or {}).get("id") or "")
        parent = group_parents.get(group_gid)
        if not line:
            line = ShopOrderLine(order_id=order.id, external_line_gid=line_gid, external_group_gid=group_gid,
                parent_line_id=parent.id if parent else 0, line_type="bundle_component" if parent else "normal",
                title=item.get("name") or "", quantity=int(item.get("quantity") or 0))
            db.add(line); db.flush()
        if sku:
            line.goods_id, line.sku_id, line.sku_code = sku.goods_id, sku.id, sku.sku_code
            line.spec_name, line.unit_cost = sku.spec_name, sku.cost_price
        line.bundle_revision_id = parent.bundle_revision_id if parent else 0
        line.quantity = int(item.get("quantity") or 0)
        line.unit_original_price = _amount(item.get("originalUnitPriceSet"))
        line.allocated_subtotal = _amount(item.get("discountedTotalSet")); line.presentment_subtotal = _amount(item.get("discountedTotalSet"), "presentmentMoney")
        line.allocated_discount = _amount(item.get("totalDiscountSet")); line.presentment_discount = _amount(item.get("totalDiscountSet"), "presentmentMoney")
        line.allocated_tax = _sum_tax(item.get("taxLines"), "shopMoney"); line.presentment_tax = _sum_tax(item.get("taxLines"), "presentmentMoney")
        desired_fulfilled = int(fulfilled.get(line_gid, 0))
        desired_reserved = int(item.get("unfulfilledQuantity") or 0) if paid else 0
        if sku and cfg.stock_location_id:
            shipped_delta = max(0, desired_fulfilled - int(line.fulfilled_quantity))
            reserve_delta = desired_reserved - int(line.reserved_quantity)
            if shipped_delta or reserve_delta:
                change_stock(db, sku.id, cfg.stock_location_id, "ship" if shipped_delta else ("reserve" if reserve_delta > 0 else "release"),
                    f"order-sync:{order.id}:{line_gid}:{desired_fulfilled}:{desired_reserved}",
                    delta_on_hand=-shipped_delta, delta_reserved=reserve_delta,
                    reference_type="order_line", reference_id=line.id, remark=f"Shopify订单 {order.order_no}")
                changed_skus.add(sku.id)
        line.fulfilled_quantity = max(int(line.fulfilled_quantity), desired_fulfilled)
        line.reserved_quantity = desired_reserved
        line.cancelled_quantity = max(0, line.quantity - int(item.get("currentQuantity") or line.quantity))
    enqueue_inventory(db, changed_skus, cfg.store_id)
    return order


def sync_refund_payload(db: Session, cfg: ShopifyStoreConfig, payload: dict) -> None:
    order_gid = f"gid://shopify/Order/{payload.get('order_id')}"
    order = sync_order(db, cfg, order_gid)
    refund_gid = str(payload.get("admin_graphql_api_id") or f"gid://shopify/Refund/{payload.get('id')}")
    refund = db.scalar(select(ShopRefund).where(ShopRefund.store_id == cfg.store_id,
        ShopRefund.external_refund_gid == refund_gid))
    if not refund:
        transactions = payload.get("transactions") or []
        amount = sum((Decimal(str(x.get("amount") or 0)) for x in transactions if x.get("kind") == "refund"), Decimal("0"))
        refund = ShopRefund(order_id=order.id, store_id=cfg.store_id, external_refund_gid=refund_gid,
                            amount=amount, processed_at=_dt(payload.get("processed_at") or payload.get("created_at")))
        db.add(refund); db.flush()
    for raw in payload.get("refund_line_items") or []:
        line_item = raw.get("line_item") or {}
        line_gid = str(line_item.get("admin_graphql_api_id") or f"gid://shopify/LineItem/{raw.get('line_item_id')}")
        line = db.scalar(select(ShopOrderLine).where(ShopOrderLine.order_id == order.id,
            ShopOrderLine.external_line_gid == line_gid))
        if not line: continue
        existing = db.scalar(select(ShopRefundLine).where(ShopRefundLine.refund_id == refund.id,
            ShopRefundLine.order_line_id == line.id))
        quantity = int(raw.get("quantity") or 0)
        if not existing:
            existing = ShopRefundLine(refund_id=refund.id, order_line_id=line.id, quantity=quantity,
                subtotal=Decimal(str(raw.get("subtotal") or 0)), tax=Decimal(str(raw.get("total_tax") or 0)),
                restock_type=str(raw.get("restock_type") or ""))
            db.add(existing)
        db.flush()
        line.refunded_quantity = int(db.scalar(select(func.coalesce(func.sum(ShopRefundLine.quantity), 0)).where(
            ShopRefundLine.order_line_id == line.id)) or 0)


@webhook_router.post("")
async def receive_webhook(request: Request):
    raw = await request.body()
    signature = request.headers.get("X-Shopify-Hmac-Sha256", "")
    expected = base64.b64encode(hmac.new(SHOPIFY_CLIENT_SECRET.encode(), raw, hashlib.sha256).digest()).decode()
    if not SHOPIFY_CLIENT_SECRET or not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Webhook 签名无效")
    domain = request.headers.get("X-Shopify-Shop-Domain", "").lower()
    topic = request.headers.get("X-Shopify-Topic", "")
    webhook_id = request.headers.get("X-Shopify-Webhook-Id", "")
    try: payload = json.loads(raw)
    except ValueError: raise HTTPException(status_code=400, detail="Webhook JSON 无效")
    with SessionLocal() as db:
        cfg = db.scalar(select(ShopifyStoreConfig).where(ShopifyStoreConfig.shop_domain == domain))
        if not cfg: raise HTTPException(status_code=404, detail="Shopify 店铺未配置")
        if db.scalar(select(ShopifyWebhookEvent.id).where(ShopifyWebhookEvent.store_id == cfg.store_id,
            ShopifyWebhookEvent.webhook_id == webhook_id)):
            return ok()
        external = str(payload.get("admin_graphql_api_id") or payload.get("id") or "")
        event = ShopifyWebhookEvent(store_id=cfg.store_id, webhook_id=webhook_id, topic=topic,
            external_resource_id=external, payload_sha256=hashlib.sha256(raw).hexdigest(), status="processed")
        db.add(event)
        try:
            if topic == "refunds/create":
                sync_refund_payload(db, cfg, payload)
            else:
                order_id = payload.get("order_id") if topic.startswith("fulfillments/") else payload.get("id")
                gid = (f"gid://shopify/Order/{order_id}" if topic.startswith("fulfillments/") else
                       str(payload.get("admin_graphql_api_id") or f"gid://shopify/Order/{order_id}"))
                if topic.startswith("orders/") or topic.startswith("fulfillments/"):
                    sync_order(db, cfg, gid)
                else:
                    event.status = "ignored"
            event.processed_at = datetime.now(); db.commit()
        except (ShopifyError, StockError, Exception) as exc:
            db.rollback()
            raise HTTPException(status_code=500, detail=str(exc)[:500])
    return ok()


def _line_dict(line: ShopOrderLine):
    return {"id": line.id, "line_type": line.line_type, "parent_line_id": line.parent_line_id,
            "sku_code": line.sku_code, "title": line.title, "spec_name": line.spec_name,
            "quantity": line.quantity, "reserved_quantity": line.reserved_quantity,
            "fulfilled_quantity": line.fulfilled_quantity, "refunded_quantity": line.refunded_quantity,
            "returned_sellable_quantity": line.returned_sellable_quantity,
            "returned_unavailable_quantity": line.returned_unavailable_quantity,
            "allocated_subtotal": float(line.allocated_subtotal), "allocated_discount": float(line.allocated_discount),
            "allocated_tax": float(line.allocated_tax), "unit_cost": float(line.unit_cost)}


@router.get("")
def list_orders(take: int | None = Query(None), skip: int = 0, sort: str | None = None,
                filter: str | None = None, db: Session = Depends(get_db)):
    stmt = select(ShopOrder, Store).join(Store, Store.id == ShopOrder.store_id)
    fields = {"id": (ShopOrder.id, "num"), "store_name": (Store.name, "str"), "order_no": (ShopOrder.order_no, "str"),
              "financial_status": (ShopOrder.financial_status, "str"), "fulfillment_status": (ShopOrder.fulfillment_status, "str"),
              "cancel_status": (ShopOrder.cancel_status, "str"), "shop_currency": (ShopOrder.shop_currency, "str"),
              "total_price": (ShopOrder.total_price, "num"), "total_discount": (ShopOrder.total_discount, "num"),
              "total_tax": (ShopOrder.total_tax, "num"), "processed_at": (ShopOrder.processed_at, "str")}
    condition = build_filter(parse_json(filter, "筛选"), fields)
    if condition is not None:
        stmt = stmt.where(condition)
    total = int(db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0)
    order_by = build_sort(parse_json(sort, "排序"), fields)
    requested_take = take
    if take is not None:
        skip, take = clamp_page(skip, take); stmt = stmt.offset(skip).limit(take)
    rows = db.execute(stmt.order_by(*(order_by or [ShopOrder.id.desc()])))
    items = [{"id": o.id, "store_id": o.store_id, "store_name": s.name, "order_no": o.order_no,
        "financial_status": o.financial_status, "fulfillment_status": o.fulfillment_status,
        "cancel_status": o.cancel_status, "shop_currency": o.shop_currency, "total_price": float(o.total_price),
        "total_discount": float(o.total_discount), "total_tax": float(o.total_tax),
        "processed_at": _fmt(o.processed_at), "updated_at": _fmt(o.updated_at)} for o, s in rows]
    return ok(items if requested_take is None else {"items": items, "total": total})


@router.get("/{order_id}")
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.get(ShopOrder, order_id) or fail("订单不存在", 404)
    lines = db.scalars(select(ShopOrderLine).where(ShopOrderLine.order_id == order.id).order_by(
        ShopOrderLine.parent_line_id, ShopOrderLine.id))
    return ok({"id": order.id, "order_no": order.order_no, "shop_currency": order.shop_currency,
               "lines": [_line_dict(x) for x in lines]})


@router.post("/{order_id}/returns")
def confirm_return(order_id: int, body: dict, db: Session = Depends(get_db)):
    order = db.get(ShopOrder, order_id) or fail("订单不存在", 404)
    cfg = db.scalar(select(ShopifyStoreConfig).where(ShopifyStoreConfig.store_id == order.store_id))
    if not cfg or not cfg.stock_location_id: fail("店铺未绑定 mzShop 库存地点")
    values = body.get("lines")
    if not isinstance(values, list) or not values: fail("请选择退货组件")
    ret = ShopReturn(order_id=order.id, store_id=order.store_id, status="received",
                     received_at=datetime.now(), remark=str(body.get("remark") or "").strip()[:500])
    db.add(ret); db.flush()
    try:
        for raw in values:
            line = db.get(ShopOrderLine, int(raw.get("order_line_id")))
            if not line or line.order_id != order.id or line.line_type == "bundle_parent" or not line.sku_id:
                fail("退货订单行不合法")
            sellable, unavailable = int(raw.get("sellable_quantity") or 0), int(raw.get("unavailable_quantity") or 0)
            quantity = sellable + unavailable
            remain = line.fulfilled_quantity - line.returned_sellable_quantity - line.returned_unavailable_quantity
            if quantity <= 0 or quantity > remain: fail("退货数量超过可退数量")
            item = ShopReturnLine(return_id=ret.id, order_line_id=line.id, quantity=quantity,
                sellable_quantity=sellable, unavailable_quantity=unavailable,
                reason=str(raw.get("reason") or "").strip()[:200]); db.add(item); db.flush()
            change_stock(db, line.sku_id, cfg.stock_location_id,
                "return_sellable" if unavailable == 0 else "return_unavailable", f"return:{ret.id}:{line.id}",
                delta_on_hand=quantity, delta_unavailable=unavailable,
                reference_type="return", reference_id=ret.id, remark=f"订单 {order.order_no} 退货入库")
            enqueue_inventory(db, {line.sku_id}, order.store_id)
            line.returned_sellable_quantity += sellable; line.returned_unavailable_quantity += unavailable
        db.commit()
    except StockError as exc: db.rollback(); fail(str(exc))
    return ok({"id": ret.id})
