"""mzShop 主库存：余额、流水和组合可售量。调用方负责提交事务。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import SHOPIFY_MAX_RETRIES
from .models import (BundleComponent, BundleRevision, ShopGoodsSku, ShopGoodsStore, ShopifyStoreConfig,
                     ShopifySyncTask, StockBalance, StockLedger)


class StockError(ValueError):
    pass


def available(balance: StockBalance | None) -> int:
    if not balance:
        return 0
    return max(0, int(balance.on_hand) - int(balance.reserved) - int(balance.unavailable) - int(balance.safety_stock))


def change_stock(db: Session, sku_id: int, location_id: int, event_type: str, idempotency_key: str,
                 delta_on_hand: int = 0, delta_reserved: int = 0, delta_unavailable: int = 0,
                 reference_type: str = "", reference_id: int = 0, remark: str = "") -> StockBalance:
    existing = db.scalar(select(StockLedger).where(StockLedger.idempotency_key == idempotency_key))
    if existing:
        return db.scalar(select(StockBalance).where(
            StockBalance.sku_id == existing.sku_id, StockBalance.location_id == existing.location_id))
    sku = db.get(ShopGoodsSku, sku_id)
    if not sku or sku.sku_type != "normal":
        raise StockError("库存只能调整普通 SKU")
    balance = db.scalar(select(StockBalance).where(
        StockBalance.sku_id == sku_id, StockBalance.location_id == location_id).with_for_update())
    if not balance:
        balance = StockBalance(sku_id=sku_id, location_id=location_id)
        db.add(balance)
        db.flush()
    after_on_hand = int(balance.on_hand) + int(delta_on_hand)
    after_reserved = int(balance.reserved) + int(delta_reserved)
    after_unavailable = int(balance.unavailable) + int(delta_unavailable)
    if min(after_on_hand, after_reserved, after_unavailable) < 0:
        raise StockError("库存余额不能小于 0")
    if after_reserved + after_unavailable > after_on_hand:
        raise StockError("占用库存与不可售库存合计不能超过在库数量")
    balance.on_hand, balance.reserved, balance.unavailable = after_on_hand, after_reserved, after_unavailable
    db.add(StockLedger(sku_id=sku_id, location_id=location_id, event_type=event_type,
        delta_on_hand=delta_on_hand, delta_reserved=delta_reserved, delta_unavailable=delta_unavailable,
        after_on_hand=after_on_hand, after_reserved=after_reserved, after_unavailable=after_unavailable,
        reference_type=reference_type, reference_id=reference_id, idempotency_key=idempotency_key,
        remark=remark[:500]))
    return balance


def bundle_available(db: Session, parent_sku_id: int, location_id: int) -> int:
    revision = db.scalar(select(BundleRevision).where(
        BundleRevision.parent_sku_id == parent_sku_id, BundleRevision.status == "published")
        .order_by(BundleRevision.version_no.desc()).limit(1))
    if not revision:
        return 0
    components = list(db.scalars(select(BundleComponent).where(
        BundleComponent.revision_id == revision.id).order_by(BundleComponent.sort_order, BundleComponent.id)))
    if not components:
        return 0
    balances = {x.sku_id: x for x in db.scalars(select(StockBalance).where(
        StockBalance.location_id == location_id,
        StockBalance.sku_id.in_([x.component_sku_id for x in components])))}
    return min(available(balances.get(x.component_sku_id)) // x.quantity for x in components)


def enqueue_inventory(db: Session, sku_ids: set[int], store_id: int | None = None) -> int:
    """库存变更后按商品/店铺合并任务；任务执行时读取最新余额，不保存过期库存快照。"""
    if not sku_ids:
        return 0
    goods_ids = set(db.scalars(select(ShopGoodsSku.goods_id).where(ShopGoodsSku.id.in_(sku_ids))))
    stmt = (select(ShopGoodsStore.goods_id, ShopGoodsStore.store_id)
            .join(ShopifyStoreConfig, ShopifyStoreConfig.store_id == ShopGoodsStore.store_id)
            .where(ShopGoodsStore.goods_id.in_(goods_ids), ShopGoodsStore.allowed == 1,
                   ShopifyStoreConfig.sync_enabled == 1, ShopifyStoreConfig.connection_status == "ok"))
    if store_id:
        stmt = stmt.where(ShopGoodsStore.store_id == store_id)
    created = 0
    for goods_id, target_store_id in db.execute(stmt):
        active = db.scalar(select(ShopifySyncTask.id).where(
            ShopifySyncTask.goods_id == goods_id, ShopifySyncTask.store_id == target_store_id,
            ShopifySyncTask.status.in_(("pending", "running"))).limit(1))
        if not active:
            db.add(ShopifySyncTask(store_id=target_store_id, goods_id=goods_id, action="sync_inventory",
                                   status="pending", max_retries=SHOPIFY_MAX_RETRIES))
            created += 1
    return created
